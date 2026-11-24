# Nhận kết quả gửi, metadata bản ghi và lỗi gửi bất đồng bộ

Khi ứng dụng Spring Cloud Stream phát message tới Kafka, lời gọi gửi và việc broker xác nhận đã ghi record là hai thời điểm khác nhau. Với producer bất đồng bộ, ứng dụng có thể tiếp tục xử lý ngay sau khi đưa message vào luồng gửi, trong khi Kafka client vẫn đang chờ gửi request, nhận acknowledgement hoặc xử lý lỗi. Nếu chỉ kiểm tra lời gọi gửi ban đầu, ứng dụng có thể bỏ sót lỗi xảy ra sau đó.

Kafka binder cung cấp các cơ chế để quan sát kết quả gửi. Với Kafka message-channel binder, bạn có thể bật gửi đồng bộ bằng `sync`, nhận metadata của record thành công qua `recordMetadataChannel` và chuyển lỗi gửi bất đồng bộ tới error channel bằng `errorChannelEnabled`. Với Reactive Kafka binder, `resultMetadataChannel` cung cấp `SenderResult` gồm thông tin thành công, lỗi và metadata tương ứng.

Bài học này hướng dẫn cách chọn cơ chế phù hợp, đọc topic/partition/offset, liên kết kết quả với message gốc, xử lý lỗi gửi và kiểm thử các tình huống thành công, timeout hoặc broker từ chối ghi.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt việc message được chuyển vào kênh gửi với việc Kafka xác nhận đã ghi record.
- Giải thích sự khác nhau giữa gửi đồng bộ và bất đồng bộ.
- Cấu hình `sync` và `sendTimeoutExpression` cho Kafka producer binding.
- Nhận kết quả gửi thành công qua `recordMetadataChannel`.
- Đọc `KafkaHeaders.RECORD_METADATA` và các trường của `RecordMetadata`.
- Bật `errorChannelEnabled` để nhận lỗi gửi bất đồng bộ.
- Phân tích `KafkaSendFailureException`, message gốc và `ProducerRecord`.
- Dùng `resultMetadataChannel` của Reactive Kafka binder để nhận `SenderResult`.
- Thiết kế correlation, retry và quan sát kết quả gửi mà không tạo tác dụng phụ lặp.

## 1. Vòng đời của một lần gửi Kafka

Một producer gửi record qua nhiều bước:

1. Ứng dụng tạo Spring `Message<?>` và gửi vào output binding.
2. Spring Cloud Stream chuyển đổi payload, headers và tạo Kafka `ProducerRecord`.
3. Kafka producer đưa record vào buffer nội bộ và gửi request tới broker.
4. Broker kiểm tra request, ghi record vào partition và trả acknowledgement theo cấu hình `acks`.
5. Kafka client hoàn tất kết quả gửi hoặc báo lỗi.
6. Binder chuyển kết quả về ứng dụng thông qua cơ chế đồng bộ, metadata channel hoặc error channel đã cấu hình.

~~~mermaid
sequenceDiagram
    participant A as Spring Cloud Stream app
    participant B as Kafka binder
    participant P as Kafka producer
    participant K as Kafka broker
    A->>B: Send Message
    B->>P: ProducerRecord
    P-->>A: Return from async send
    P->>K: Produce request
    K-->>P: Ack / error
    P-->>B: Send completion
    B-->>A: RecordMetadata or ErrorMessage
~~~

Trong chế độ bất đồng bộ, ứng dụng có thể nhận lại quyền điều khiển trước bước 4 hoặc 5. Vì vậy:

- Lời gọi gửi không ném exception chưa chứng minh broker đã ghi record.
- Giá trị boolean từ một API gửi message thường chỉ xác nhận thao tác gửi vào channel được chấp nhận theo API đó; không nên mặc định đó là broker acknowledgement.
- Kết quả metadata thành công cho biết Kafka client đã hoàn tất lần gửi theo chính sách acknowledgement đang dùng.
- Kết quả gửi thành công không chứng minh consumer đã đọc hoặc xử lý record.

Cần xác định rõ tín hiệu nào trả lời câu hỏi nào: ứng dụng đã bàn giao message cho binder, broker đã ghi record, hay consumer đã hoàn tất nghiệp vụ.

## 2. Gửi đồng bộ và gửi bất đồng bộ

Kafka message-channel binder mặc định dùng producer bất đồng bộ. Thuộc tính Kafka producer `sync` cho phép chờ kết quả gửi trước khi hoàn tất thao tác xử lý message.

| Chế độ | Hành vi | Ưu điểm | Đánh đổi |
|---|---|---|---|
| `sync: false` | Gửi bất đồng bộ; không chờ broker acknowledgement trong luồng gọi hiện tại | Throughput tốt, không chặn caller lâu | Cần quan sát kết quả thành công/lỗi qua channel |
| `sync: true` | Chờ kết quả gửi trước khi trả về | Lỗi gửi có thể được báo trực tiếp trong luồng gọi | Tăng latency và giữ thread trong thời gian chờ |

### Cấu hình gửi đồng bộ

Ví dụ cấu hình output binding:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              sync: true
              sendTimeoutExpression: "headers['sendTimeoutMs']"
~~~

`sync: true` yêu cầu producer chờ kết quả gửi. `sendTimeoutExpression` là SpEL expression được đánh giá trên message để xác định thời gian chờ acknowledgement, tính bằng mili giây. Ví dụ trên lấy timeout từ header `sendTimeoutMs`. Nếu không cần timeout theo từng message, có thể bỏ thuộc tính này và dùng cấu hình mặc định của phiên bản.

Với gửi đồng bộ, lỗi gửi hoặc timeout có thể đi ngược về caller dưới dạng exception. Vì vậy, code phát message cần có chính sách bắt và xử lý lỗi phù hợp:

~~~java
public void publish(OrderCreated event) {
    try {
        streamBridge.send("publishOrder-out-0", event);
    }
    catch (RuntimeException ex) {
        log.error("Không gửi được OrderCreated {}", event.eventId(), ex);
        throw ex;
    }
}
~~~

Ví dụ minh họa đường đi lỗi đồng bộ. Trong ứng dụng thực tế, cần phân loại exception theo nguyên nhân, quyết định retry ở một tầng rõ ràng và dùng event ID ổn định để chống gửi trùng.

Không nên bật `sync: true` cho mọi luồng chỉ để dễ quan sát kết quả. Chờ acknowledgement trên từng message có thể giảm throughput và làm tăng thời gian xử lý của request hoặc function. Nếu cần theo dõi nhiều lần gửi đồng thời, cơ chế bất đồng bộ cùng correlation thường phù hợp hơn.

## 3. sendTimeoutExpression

`sendTimeoutExpression` được Kafka binder dùng khi gửi đồng bộ để xác định thời gian chờ acknowledgement. Giá trị được tính bằng mili giây.

Có thể dùng timeout cố định:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              sync: true
              sendTimeoutExpression: "5000"
~~~

Hoặc dùng header để mỗi message có ngân sách chờ riêng:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader("sendTimeoutMs", 3000L)
    .build();

streamBridge.send("publishOrder-out-0", message);
~~~

Khi dùng timeout theo header, bảo đảm kiểu dữ liệu và đơn vị là mili giây. Timeout quá ngắn có thể báo lỗi dù broker vẫn có thể hoàn tất request sau đó; timeout quá dài khiến thread bị giữ lâu khi broker hoặc mạng gặp sự cố.

Timeout không phải bằng chứng chắc chắn record chưa được ghi. Nếu client timeout sau khi broker đã ghi nhưng acknowledgement bị mất trên đường về, gửi lại có thể tạo record trùng. Với message nghiệp vụ quan trọng, hãy dùng event ID, idempotency và chiến lược retry có kiểm soát.

## 4. Nhận metadata của record gửi thành công

Kafka binder có thuộc tính `recordMetadataChannel`. Thuộc tính này nhận tên bean của một Spring `MessageChannel`. Khi gửi thành công, binder gửi message kết quả vào channel đó. Message chứa payload đã gửi sau conversion và header `KafkaHeaders.RECORD_METADATA` mang đối tượng `RecordMetadata` do Kafka client cung cấp.

Metadata cho biết record được ghi ở đâu:

| Trường metadata | Ý nghĩa |
|---|---|
| `topic()` | Tên topic nhận record |
| `partition()` | Partition mà record được ghi |
| `offset()` | Offset của record trong partition |
| `timestamp()` | Timestamp do producer/broker ghi nhận theo cấu hình |
| `serializedKeySize()` | Kích thước key sau serialization |
| `serializedValueSize()` | Kích thước value sau serialization |

Metadata giúp:
- Truy vết message tới topic, partition và offset.
- Đối chiếu record với dữ liệu quan sát từ Kafka CLI hoặc công cụ quản trị.
- Ghi nhận kết quả publish trong log hoặc audit.
- Phân tích phân phối partition và độ trễ gửi.
- Liên kết một lần gửi với nghiệp vụ gốc nếu ứng dụng có correlation ID.

### Khai báo channel nhận kết quả

Ví dụ tạo `DirectChannel` và xử lý kết quả:

~~~java
import org.apache.kafka.clients.producer.RecordMetadata;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.stereotype.Component;

@Configuration
class KafkaSendResultChannels {

    @Bean
    MessageChannel orderSendResults() {
        return new DirectChannel();
    }
}

@Component
class KafkaSendResultHandler {

    private static final Logger log = LoggerFactory.getLogger(KafkaSendResultHandler.class);

    @ServiceActivator(inputChannel = "orderSendResults")
    public void handleSuccessfulSend(Message<?> result) {
        RecordMetadata metadata = result.getHeaders().get(
            KafkaHeaders.RECORD_METADATA,
            RecordMetadata.class
        );

        if (metadata == null) {
            log.warn("Send result không có RecordMetadata");
            return;
        }

        log.info(
            "Kafka record written: topic={}, partition={}, offset={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    }
}
~~~

Cấu hình binder trỏ tới bean channel:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              recordMetadataChannel: orderSendResults
~~~

Tên `orderSendResults` phải khớp tên bean `MessageChannel`. Nếu bean không tồn tại hoặc tên cấu hình sai, binder không thể gửi kết quả tới channel mong muốn.

### Metadata không phải nội dung message nghiệp vụ

`RecordMetadata` là metadata do Kafka client cung cấp sau khi gửi. Nó không thay thế payload, event ID hoặc correlation ID. Khi cần tìm lại message nghiệp vụ, hãy ghi nhận cả event ID và metadata:

~~~java
log.info(
    "eventId={}, topic={}, partition={}, offset={}",
    eventId,
    metadata.topic(),
    metadata.partition(),
    metadata.offset()
);
~~~

Không dùng offset một mình làm định danh nghiệp vụ. Offset chỉ có ý nghĩa trong một topic partition cụ thể và có thể khác khi message được gửi lại hoặc phát lại vào topic khác.

## 5. Liên kết kết quả gửi với message gốc

Khi nhiều message được gửi đồng thời, các kết quả có thể hoàn tất theo thứ tự khác với thứ tự gửi. Không nên ghép kết quả theo vị trí trong danh sách hoặc giả định callback luôn về đúng thứ tự.

Dùng correlation ID ổn định cho từng lần gửi. Ví dụ:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setCorrelationId(event.eventId())
    .build();

streamBridge.send("publishOrder-out-0", message);
~~~

Kết quả thành công được chuyển tới `recordMetadataChannel` cùng message đã gửi và metadata. Ứng dụng có thể đọc correlation ID từ message headers và kết hợp với `RecordMetadata` để ghi log hoặc cập nhật trạng thái publish.

Một correlation ID nên:
- Duy nhất trong phạm vi các lần gửi đang chờ kết quả.
- Giữ nguyên khi retry cùng một sự kiện nghiệp vụ.
- Không chứa dữ liệu nhạy cảm.
- Có thể tìm trong log, trace hoặc bảng outbox.
- Có quy tắc hết hạn nếu ứng dụng lưu trạng thái chờ kết quả trong bộ nhớ.

Không dùng một biến toàn cục đơn lẻ để lưu correlation ID của lần gửi cuối cùng. Nhiều lần gửi đồng thời sẽ ghi đè lẫn nhau.

## 6. Bật error channel cho lỗi gửi bất đồng bộ

Khi producer gửi bất đồng bộ, một số lỗi chỉ xuất hiện sau khi lời gọi ban đầu đã trả về, chẳng hạn:
- Broker không khả dụng hoặc mất kết nối.
- Request hết thời gian chờ.
- Broker từ chối ghi do authorization hoặc topic không tồn tại.
- Lỗi serialization xảy ra trong quá trình producer xử lý record.
- Lỗi metadata hoặc network trong quá trình gửi.

Thuộc tính chung `errorChannelEnabled` của output binding cho phép chuyển lỗi gửi bất đồng bộ tới error channel nếu binder hỗ trợ cơ chế đó. Mặc định là `false`.

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            errorChannelEnabled: true
~~~

Khi dùng Kafka binder, payload của `ErrorMessage` cho lỗi gửi là `KafkaSendFailureException`. Exception này cung cấp:

- `getFailedMessage()`: Spring Messaging `Message<?>` ban đầu không gửi được.
- `getRecord()`: Kafka `ProducerRecord` được tạo từ message đó.
- `getCause()`: nguyên nhân gốc của lỗi gửi.

Producer error channel cần được xử lý ở ứng dụng. Kafka binder không tự động đưa lỗi gửi producer vào DLQ như một cơ chế consumer DLQ. Ứng dụng cần quyết định ghi nhận, retry, chuyển sang parking-lot hoặc báo lỗi cho hệ thống gọi.

### Xử lý lỗi gửi qua errorChannel

Ví dụ đăng ký một handler toàn cục và chỉ xử lý lỗi gửi Kafka:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.kafka.support.KafkaSendFailureException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;
import org.apache.kafka.clients.producer.ProducerRecord;

@Component
public class KafkaSendErrorHandler {

    private static final Logger log = LoggerFactory.getLogger(KafkaSendErrorHandler.class);

    @ServiceActivator(inputChannel = "errorChannel")
    public void handleApplicationError(ErrorMessage errorMessage) {
        Object payload = errorMessage.getPayload();

        if (payload instanceof KafkaSendFailureException failure) {
            Message<?> failedMessage = failure.getFailedMessage();
            ProducerRecord<?, ?> record = failure.getRecord();

            log.error(
                "Kafka send failed: topic={}, key={}, event={}",
                record.topic(),
                record.key(),
                failedMessage.getHeaders().get("eventId"),
                failure
            );

            // Ghi nhận lỗi và chuyển sang retry/parking-lot theo chính sách ứng dụng.
            return;
        }

        log.error("Application error: {}", payload);
    }
}
~~~

Global `errorChannel` có thể nhận nhiều loại lỗi ứng dụng, không chỉ lỗi producer Kafka. Vì vậy, handler cần kiểm tra kiểu payload hoặc định tuyến theo binding trước khi xử lý. Nếu dùng nhiều binder, không giả định mọi exception đều là `KafkaSendFailureException`.

Nếu cần handler riêng cho một output binding, có thể đăng ký subscriber cho error channel của destination theo quy tắc đặt tên của phiên bản Spring Cloud Stream đang sử dụng. Đối chiếu tài liệu phiên bản và kiểm thử tên channel thực tế; không tự suy ra tên từ topic mà chưa xác nhận.

## 7. Phân tích KafkaSendFailureException

Khi nhận lỗi gửi, hãy giữ lại đủ thông tin để điều tra:

| Thông tin | Mục đích |
|---|---|
| `failedMessage` | Biết payload và headers của message ứng dụng đã gửi |
| `ProducerRecord` | Biết topic, key, partition, timestamp và headers dự kiến |
| `cause` | Xác định lỗi mạng, timeout, serialization, authorization hoặc broker |
| `eventId` / correlation ID | Liên kết lỗi với nghiệp vụ và lần gửi |
| Binding name | Xác định output binding và cấu hình producer |
| Thời điểm và số lần thử | Phân tích lỗi tạm thời hay kéo dài |

Không log toàn bộ payload nếu payload chứa thông tin cá nhân, token hoặc dữ liệu thanh toán. Có thể ghi event ID, topic, key đã được kiểm soát, exception type và trace ID để truy vết.

### Phân loại lỗi gửi

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Network timeout, broker leader chuyển đổi | Retry có giới hạn và backoff |
| Cấu hình/quyền | Topic không tồn tại, ACL từ chối, credentials sai | Sửa cấu hình hoặc quyền; tránh retry vô hạn |
| Dữ liệu | Serialization thất bại do payload không hợp lệ | Cách ly message và điều tra dữ liệu |
| Quá tải | Buffer đầy, broker throttling | Giảm tốc độ, điều chỉnh capacity và quota |
| Không rõ kết quả | Timeout sau khi broker có thể đã ghi record | Retry với idempotency hoặc đối soát |

Không phải mọi timeout đều chứng minh broker chưa ghi record. Nếu acknowledgement bị mất sau khi record đã được ghi, retry có thể tạo bản ghi trùng. Khi message đại diện cho thao tác nghiệp vụ, producer nên mang event ID ổn định và consumer nên có cơ chế idempotent.

## 8. Phân biệt lỗi producer với DLQ của consumer

DLQ của Kafka binder thường xử lý record consumer không thể xử lý sau retry. Lỗi producer xảy ra ở chiều gửi và không tự động được đưa vào consumer DLQ.

| Loại lỗi | Nơi phát sinh | Cơ chế quan sát/xử lý |
|---|---|---|
| Producer send failure | Ứng dụng gửi → Kafka | `recordMetadataChannel` cho thành công; `errorChannelEnabled` cho lỗi bất đồng bộ |
| Consumer processing failure | Kafka → ứng dụng nhận | Retry, error handler và DLQ của consumer binding |
| Deserialization failure | Kafka client/binder giải mã record | Cơ chế xử lý deserialization riêng của binder |
| Downstream business failure | Function/service xử lý nghiệp vụ | Retry/recovery theo consumer và nghiệp vụ |

Nếu producer send thất bại, không có record hợp lệ ở topic đích để consumer DLQ xử lý. Ứng dụng gửi phải quyết định cách khôi phục message gốc.

## 9. Gửi bất đồng bộ với Reactive Kafka binder

Kafka message-channel binder và Reactive Kafka binder có cơ chế nhận kết quả khác nhau. Reactive Kafka binder được xây dựng trên Reactor Kafka. Từ phiên bản 4.0.3, binder hỗ trợ `resultMetadataChannel` để nhận `SenderResult<?>` của các lần gửi.

`SenderResult` cung cấp:
- `correlationMetadata()`: metadata do ứng dụng đính kèm để liên kết kết quả với lần gửi.
- `exception()`: lỗi nếu gửi thất bại.
- `recordMetadata()`: metadata Kafka của record gửi thành công.

Channel kết quả phải là `FluxMessageChannel`.

Ví dụ khai báo channel và handler:

~~~java
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.FluxMessageChannel;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import reactor.kafka.sender.SenderResult;

@Configuration
class ReactiveSendResultChannels {

    @Bean
    FluxMessageChannel orderSenderResults() {
        return new FluxMessageChannel();
    }
}

@Component
class ReactiveSendResultHandler {

    private static final Logger log = LoggerFactory.getLogger(ReactiveSendResultHandler.class);

    @ServiceActivator(inputChannel = "orderSenderResults")
    public void handleReactiveSendResult(SenderResult<String> result) {
        if (result.exception() != null) {
            log.error(
                "Reactive Kafka send failed, correlation={}",
                result.correlationMetadata(),
                result.exception()
            );
            return;
        }

        RecordMetadata metadata = result.recordMetadata();

        log.info(
            "Reactive send success, correlation={}, topic={}, partition={}, offset={}",
            result.correlationMetadata(),
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    }
}
~~~

Cấu hình binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              resultMetadataChannel: orderSenderResults
~~~

Khi gửi, ứng dụng gắn correlation ID:

~~~java
streamBridge.send(
    "publishOrder-out-0",
    MessageBuilder.withPayload(event)
        .setCorrelationId(event.eventId())
        .build()
);
~~~

Với reactive function, output message cần có correlation ID header để kết quả gửi có thể trả lại correlation metadata tương ứng. Giá trị correlation nên duy nhất ít nhất trong khoảng thời gian lần gửi đang chờ kết quả.

Không nhầm `resultMetadataChannel` của Reactive Kafka binder với `recordMetadataChannel` của Kafka message-channel binder. Hai cơ chế có kiểu channel và kiểu kết quả khác nhau.

## 10. So sánh hai cơ chế nhận kết quả

| Tiêu chí | Kafka message-channel binder | Reactive Kafka binder |
|---|---|---|
| Gửi đồng bộ | `sync: true` | Không dùng cùng thuộc tính binder này |
| Kết quả thành công | `recordMetadataChannel` | `resultMetadataChannel` |
| Kiểu channel | Spring `MessageChannel` | `FluxMessageChannel` |
| Payload/kết quả | Message có header `KafkaHeaders.RECORD_METADATA` | `SenderResult<?>` |
| Metadata | `RecordMetadata` | `RecordMetadata` |
| Lỗi gửi bất đồng bộ | Producer error channel khi bật `errorChannelEnabled` | `SenderResult.exception()` |
| Correlation | Dùng message ID/correlation header của ứng dụng | `SenderResult.correlationMetadata()` |
| Phiên bản hỗ trợ | Theo Kafka binder hiện hành | `resultMetadataChannel` từ 4.0.3 |

Chọn cơ chế phù hợp với binder mà ứng dụng thực sự sử dụng. Không đặt thuộc tính của reactive binder lên message-channel binder rồi mong nhận cùng một loại kết quả.

## 11. Retry và xử lý kết quả gửi lỗi

Khi nhận lỗi producer, ứng dụng có thể:
1. Ghi nhận message lỗi vào bảng outbox hoặc kho retry.
2. Phân loại exception.
3. Retry lỗi tạm thời theo số lần và backoff giới hạn.
4. Giữ nguyên event ID và correlation ID qua các lần thử.
5. Đưa lỗi vĩnh viễn vào parking-lot để điều tra.
6. Phát cảnh báo khi tỷ lệ lỗi hoặc thời gian chờ vượt ngưỡng.

Không nên retry ngay lập tức trong chính error handler mà không có giới hạn. Nếu broker đang mất kết nối, nhiều message có thể tạo retry storm và làm ứng dụng cạn thread hoặc buffer.

Một quy trình retry nên lưu:
- Event ID gốc.
- Số lần đã thử.
- Thời điểm thử gần nhất.
- Exception type và thông tin nguyên nhân.
- Topic/binding đích.
- Trạng thái hiện tại: PENDING, RETRYING, SENT hoặc PARKED.

### Tránh vòng lặp lỗi

Nếu error handler dùng chính output binding đang lỗi để phát message retry, message retry cũng có thể thất bại và quay lại error channel. Cần có giới hạn số lần thử và cơ chế parking-lot độc lập để chấm dứt vòng lặp.

Không đánh dấu event SENT chỉ vì `StreamBridge.send()` trả về thành công khi producer vẫn gửi bất đồng bộ. Chỉ cập nhật trạng thái đã được broker xác nhận khi nhận tín hiệu kết quả phù hợp với cấu hình producer.

## 12. Metadata và độ bền của lần gửi

Metadata thành công phải được diễn giải theo cấu hình Kafka producer. Kafka producer property `acks` quyết định mức acknowledgement mà producer chờ:

- `acks=0`: producer không chờ broker xác nhận; kết quả không cung cấp cùng mức bằng chứng về ghi bền vững như các chế độ có acknowledgement.
- `acks=1`: leader xác nhận sau khi ghi record vào log cục bộ.
- `acks=all` (hoặc `-1`): chờ các replica in-sync theo cấu hình broker xác nhận.

Với ứng dụng cần độ bền cao, hãy chọn `acks`, replication factor và `min.insync.replicas` phù hợp với chính sách Kafka cluster. `recordMetadataChannel` chỉ thông báo kết quả gửi của producer theo chính sách acknowledgement đã chọn; nó không tự nâng mức durability.

Ví dụ cấu hình producer:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          producerProperties:
            acks: all
            enable.idempotence: true
~~~

Đây là cấu hình Kafka client ở phạm vi binder. Nếu cấu hình ở cấp binding, dùng `spring.cloud.stream.kafka.bindings.<binding>.producer.configuration` theo tài liệu phiên bản. Khi bật idempotent producer, Kafka hạn chế duplicate do retry ở producer session; điều đó không thay thế idempotency nghiệp vụ khi ứng dụng phát lại event sau restart hoặc gửi lại từ outbox.

## 13. Quan sát và vận hành

Để biết hệ thống gửi có ổn định hay không, theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Send success count | Số lần gửi hoàn tất thành công |
| Send failure count | Số lần gửi thất bại |
| Send latency | Thời gian từ lúc gửi tới khi nhận kết quả |
| Timeout count | Số lần chờ acknowledgement vượt giới hạn |
| Pending sends | Số lần gửi chưa có kết quả |
| Error channel rate | Tần suất lỗi bất đồng bộ |
| Topic/partition distribution | Phân phối record giữa partition |
| Retry count | Số lần thử lại |
| Parking-lot count | Số message bị cách ly |
| Producer buffer wait | Thời gian chờ buffer/metadata/broker |

Log nên có event ID, correlation ID, binding, topic, partition, offset, exception type và trace ID. Không ghi toàn bộ payload nhạy cảm. Cần có metric cho pending sends và lỗi gửi để phát hiện tình huống ứng dụng vẫn nhận request nhưng Kafka không ghi được record.

Khi dừng ứng dụng, cần cho producer có thời gian flush/close theo lifecycle của binder. Nếu process bị kill ngay sau khi enqueue send bất đồng bộ nhưng trước khi producer hoàn tất, message có thể chưa được ghi. Với message quan trọng, kết hợp outbox bền vững và cơ chế xác nhận gửi.

## 14. Kiểm thử kết quả gửi và lỗi bất đồng bộ

### Kiểm thử metadata thành công

1. Khởi động Kafka broker và tạo topic có nhiều partition.
2. Cấu hình `recordMetadataChannel` với bean channel hợp lệ.
3. Gửi message có event ID.
4. Xác minh handler nhận message kết quả.
5. Đọc `KafkaHeaders.RECORD_METADATA`.
6. Kiểm tra topic, partition và offset.
7. Dùng Kafka consumer hoặc CLI xác nhận record thực sự tồn tại tại vị trí đó.

### Kiểm thử lỗi bất đồng bộ

1. Cấu hình `sync: false` và `errorChannelEnabled: true`.
2. Gửi message khi broker hoạt động để xác nhận đường success.
3. Mô phỏng broker không khả dụng hoặc từ chối request.
4. Xác minh error handler nhận `KafkaSendFailureException`.
5. Xác minh `failedMessage` và `ProducerRecord` có thông tin cần thiết.
6. Khôi phục broker và kiểm tra chính sách retry/parking-lot.
7. Xác minh message không bị đánh dấu SENT trước khi có kết quả thành công.

### Kiểm thử timeout và kết quả không rõ ràng

- Đặt timeout ngắn hơn thời gian broker phản hồi.
- Mô phỏng trường hợp broker ghi record nhưng acknowledgement về client bị trễ hoặc mất.
- Xác minh ứng dụng không giả định timeout đồng nghĩa record chưa tồn tại.
- Retry cùng event ID và kiểm tra idempotency/duplicate policy.

### Kiểm thử Reactive Kafka binder

- Dùng `FluxMessageChannel` làm `resultMetadataChannel`.
- Gửi message có correlation ID.
- Xác minh `SenderResult` chứa đúng correlation metadata.
- Kiểm tra `exception()` khi gửi thất bại và `recordMetadata()` khi thành công.
- Chạy nhiều send đồng thời và xác minh kết quả được ghép đúng correlation.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không nhận metadata thành công | Chưa khai báo bean channel hoặc sai tên `recordMetadataChannel` | Đối chiếu tên bean và cấu hình binding |
| Header metadata null | Message không phải kết quả thành công hoặc channel không nhận đúng message | Kiểm tra payload và header `KafkaHeaders.RECORD_METADATA` |
| Không thấy lỗi async | `errorChannelEnabled` chưa bật hoặc binder không hỗ trợ result async trong cấu hình đó | Kiểm tra property và binder version |
| Lỗi không tới handler | Chưa subscribe error channel hoặc handler không được khởi tạo | Kiểm tra Spring Integration flow và global error channel |
| Caller tưởng gửi thành công nhưng record không có | Đang gửi async và chỉ kiểm tra kết quả gọi ban đầu | Dùng metadata/error channel hoặc sync mode |
| Gửi đồng bộ làm throughput giảm | Mỗi lần gửi chờ acknowledgement | Đánh giá async result channel và batch phù hợp |
| Timeout rồi gửi lại tạo duplicate | Broker có thể đã ghi record trước khi response mất | Dùng event ID/idempotency và reconciliation |
| Error handler tạo retry loop | Retry không giới hạn hoặc gửi lại vào binding đang lỗi | Giới hạn attempts, backoff và parking-lot |
| Không nhận SenderResult | Đang dùng regular binder hoặc channel không phải FluxMessageChannel | Dùng Reactive Kafka binder và cấu hình đúng version |
| Correlation không khớp | ID không duy nhất hoặc function output không giữ correlation header | Gắn correlation ID ổn định và kiểm tra header |

## 16. Bài thực hành: theo dõi kết quả gửi OrderCreated

Xây dựng producer gửi `OrderCreated` tới topic `orders`:

1. Khai báo function hoặc service phát message qua binding `publishOrder-out-0`.
2. Gắn event ID và correlation ID ổn định vào message.
3. Cấu hình destination `orders`.
4. Khai báo bean `MessageChannel` nhận kết quả thành công.
5. Cấu hình `recordMetadataChannel` trỏ tới bean.
6. Bật `errorChannelEnabled: true`.
7. Viết handler nhận metadata và ghi topic, partition, offset cùng event ID.
8. Viết error handler nhận `KafkaSendFailureException` và lưu failed message/record/cause.
9. Gửi message khi broker hoạt động và xác minh metadata.
10. Dừng broker trong môi trường test và xác minh lỗi async được nhận.
11. Khởi động lại broker và thực hiện retry có giới hạn.
12. Kiểm tra timeout không làm ứng dụng tạo tác dụng phụ trùng.
13. Thử phiên bản Reactive Kafka binder với `resultMetadataChannel` và `SenderResult`.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Send mode | Biết rõ sync hay async |
| Timeout | Đơn vị và giới hạn chờ được cấu hình |
| Success channel | Nhận đúng message và RecordMetadata |
| Metadata | Có topic, partition, offset |
| Error channel | Bắt được lỗi async khi được bật |
| Failure payload | Đọc được failedMessage, ProducerRecord và cause |
| Correlation | Kết quả ghép đúng event gốc |
| Retry | Có giới hạn, backoff và parking-lot |
| Durability | Hiểu metadata theo cấu hình acks |
| Reactive binder | Dùng đúng FluxMessageChannel/SenderResult nếu áp dụng |
| Observability | Có log/metric success, failure, latency và retry |

## Kết luận

Kafka producer có thể gửi đồng bộ hoặc bất đồng bộ. Với Kafka message-channel binder, `sync` chờ kết quả gửi trong luồng gọi; `recordMetadataChannel` nhận kết quả thành công cùng `KafkaHeaders.RECORD_METADATA`; `errorChannelEnabled` chuyển lỗi gửi bất đồng bộ tới error channel. Payload lỗi là `KafkaSendFailureException`, chứa message gốc và `ProducerRecord`; ứng dụng tự quyết định retry hoặc cách ly lỗi.

Với Reactive Kafka binder từ phiên bản 4.0.3, `resultMetadataChannel` nhận `SenderResult` qua `FluxMessageChannel`, gồm correlation metadata, exception và RecordMetadata. Hãy ghép kết quả với event ID ổn định, diễn giải metadata theo chính sách `acks`, xử lý timeout như một kết quả có thể chưa rõ ràng và kiểm thử broker thực tế. Kết quả gửi thành công xác nhận producer hoàn tất theo cấu hình Kafka, không đồng nghĩa consumer đã xử lý nghiệp vụ.

## Tài liệu tham khảo

- [Spring Cloud Stream – Kafka Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream – Kafka Error Channels](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/error-channels.html)
- [Spring Cloud Stream – Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Apache Kafka – Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)
- [Reactor Kafka – Sender API](https://projectreactor.io/docs/kafka/release/reference/)

