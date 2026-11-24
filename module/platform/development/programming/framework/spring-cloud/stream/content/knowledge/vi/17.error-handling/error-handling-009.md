# Giữ nguyên payload và metadata phục vụ điều tra

Khi một message không xử lý được, nhóm vận hành cần biết chính xác dữ liệu nào đã gây lỗi, message đến từ binding nào, những metadata nào đi kèm và lỗi xảy ra ở lần thử thứ mấy. Nếu chỉ ghi exception vào log rồi bỏ message, việc tái hiện sự cố hoặc phát lại dữ liệu sẽ rất khó. Nếu sửa payload để nhúng thông tin lỗi, dữ liệu gốc có thể bị thay đổi và không còn đủ tin cậy cho điều tra.

Trong Spring Cloud Stream, message gồm payload và headers. Khi xử lý thất bại, framework có thể phát một ErrorMessage chứa exception và message gốc; exception dạng MessagingException cũng có thể giữ failedMessage. Binder còn có cơ chế riêng để chuyển message lỗi vào dead-letter destination (DLQ). Thiết kế tốt cần giữ nguyên payload và các metadata nghiệp vụ quan trọng, bổ sung thông tin chẩn đoán riêng, đồng thời tránh sao chép credential hoặc header vận chuyển đã hết hiệu lực.

## 1. Phân biệt message gốc và error message

Message bình thường có hai phần:

- Payload: dữ liệu nghiệp vụ hoặc byte thô nhận từ broker.
- Headers: metadata như eventId, correlationId, schema version, content type, timestamp và thông tin vận chuyển do binder thêm.

Khi handler ném exception, Spring Messaging có thể biểu diễn lỗi bằng ErrorMessage. Payload của ErrorMessage là Throwable; message gốc được giữ riêng trong originalMessage nếu error handler nhận được thông tin đó. Nếu exception là MessagingException, nó còn có thể cung cấp failedMessage.

Ví dụ:

~~~java
@Bean
Consumer<OrderCreated> processOrder() {
    return event -> {
        orderService.process(event);
    };
}
~~~

Nếu orderService.process ném exception, framework chuyển lỗi qua cơ chế error handling của binding. ErrorMessage mô tả lỗi; nó không có nghĩa payload gốc đã bị thay bằng một đối tượng lỗi. Hãy lấy đúng message gốc từ ErrorMessage hoặc exception để điều tra.

## 2. Lấy lại originalMessage và failedMessage

Với một ErrorMessage, có thể lấy exception và message gốc như sau:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

public Message<?> findOriginalMessage(ErrorMessage errorMessage) {
    Throwable failure = errorMessage.getPayload();

    Message<?> original = errorMessage.getOriginalMessage();
    if (original == null && failure instanceof MessagingException messagingException) {
        original = messagingException.getFailedMessage();
    }
    return original;
}
~~~

Hai vị trí này là nguồn cần kiểm tra đầu tiên. Không phải mọi lỗi đều có originalMessage hoặc failedMessage. Lỗi có thể phát sinh trước khi framework tạo Message đã chuyển đổi, chẳng hạn lỗi deserialize hoặc lỗi kết nối broker. Trong trường hợp đó, binder có thể cung cấp dữ liệu thô và metadata vận chuyển trong phần mở rộng riêng. Hãy kiểm tra exception chain, headers và tài liệu binder của phiên bản đang triển khai; đừng giả định mọi lỗi đều có cùng cấu trúc.

Khi không tìm thấy message gốc, error handler nên ghi nhận rõ rằng dữ liệu gốc không có sẵn trong ErrorMessage và chuyển sang cơ chế lưu giữ do binder hỗ trợ. Không tạo một payload giả hoặc ghi đè nội dung lỗi để làm như message đã được bảo toàn.

## 3. Giữ nguyên payload, không nhúng thông tin lỗi vào dữ liệu nghiệp vụ

Payload ban đầu là bằng chứng về dữ liệu producer đã gửi. Không sửa trực tiếp payload để thêm stack trace, tên exception hoặc thời gian lỗi. Thay vào đó, lưu thông tin điều tra ở metadata riêng hoặc một envelope lỗi tách biệt.

Ví dụ message gốc:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "ORD-1001",
  "total": 250000
}
~~~

Thông tin điều tra nên được ghi ở trường riêng:

~~~json
{
  "failure": {
    "exceptionType": "com.example.InventoryUnavailableException",
    "message": "Inventory service timed out",
    "failedAt": "2026-11-24T06:30:00Z",
    "attempt": 3,
    "sourceBinding": "processOrder-in-0"
  },
  "original": {
    "eventId": "evt-1001",
    "orderId": "ORD-1001",
    "total": 250000
  }
}
~~~

Envelope này chỉ là định dạng lưu trữ/chuyển tiếp lỗi. Nếu consumer replay cần đọc đúng payload ban đầu, nó phải hiểu envelope và lấy trường original. Nếu yêu cầu giữ nguyên byte trên wire, không deserialize rồi serialize lại payload; hãy dùng DLQ native của binder hoặc lưu byte gốc cùng content type và metadata cần thiết.

## 4. Metadata nào cần giữ?

Không phải header nào cũng có giá trị khi điều tra. Hãy xác định allowlist metadata ứng dụng cần bảo toàn:

| Metadata | Mục đích |
|---|---|
| eventId | Định danh sự kiện gốc, hỗ trợ chống xử lý trùng và tra cứu |
| correlationId | Liên kết các bước trong cùng yêu cầu hoặc quy trình |
| causationId | Truy ra sự kiện/yêu cầu đã gây ra sự kiện hiện tại |
| eventType | Xác định loại sự kiện và handler dự kiến |
| schemaVersion | Chọn schema hoặc converter phù hợp khi điều tra/replay |
| contentType | Biết định dạng payload gốc |
| aggregateId | Xác định thực thể nghiệp vụ liên quan |
| traceparent hoặc traceId | Liên kết log, trace và span phân tán |
| tenantRef | Xác định phạm vi tenant nếu chính sách cho phép |
| sourceBinding/destination/group | Xác định nguồn nhận message và consumer group |

Metadata vận chuyển như delivery tag, consumer tag, offset, partition assignment hoặc trạng thái acknowledgement có thể chỉ hợp lệ trong lần giao nhận ban đầu. Không sao chép chúng một cách mù quáng vào message replay. Lưu chúng trong bản ghi điều tra nếu cần, nhưng phân biệt với metadata nghiệp vụ có thể tái sử dụng.

## 5. Chỉ sao chép header đã được cho phép

Ví dụ sau minh họa việc tạo message phục vụ điều tra từ payload gốc, chỉ sao chép một số header nghiệp vụ và bổ sung metadata lỗi:

~~~java
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

public Message<?> toDiagnosticMessage(ErrorMessage errorMessage) {
    Throwable failure = errorMessage.getPayload();
    Message<?> original = errorMessage.getOriginalMessage();

    if (original == null && failure instanceof MessagingException messagingException) {
        original = messagingException.getFailedMessage();
    }
    if (original == null) {
        throw new IllegalStateException("Original message is unavailable", failure);
    }

    List<String> allowedHeaders = List.of(
        "eventId",
        "correlationId",
        "causationId",
        "eventType",
        "schemaVersion",
        "aggregateId",
        "traceparent",
        MessageHeaders.CONTENT_TYPE
    );

    Map<String, Object> retainedHeaders = new HashMap<>();
    for (String name : allowedHeaders) {
        Object value = original.getHeaders().get(name);
        if (value != null) {
            retainedHeaders.put(name, value);
        }
    }

    return MessageBuilder.withPayload(original.getPayload())
        .copyHeaders(retainedHeaders)
        .setHeader("failureType", failure.getClass().getName())
        .setHeader("failureMessage", truncate(failure.getMessage()))
        .setHeader("failedAt", Instant.now().toString())
        .build();
}

private String truncate(String message) {
    if (message == null) {
        return "No exception message";
    }
    return message.length() > 500 ? message.substring(0, 500) : message;
}
~~~

Đoạn code là mẫu cho ứng dụng có các header tùy chỉnh như eventId và correlationId; hãy điều chỉnh allowlist theo hợp đồng thực tế. MessageHeaders.CONTENT_TYPE giúp lấy đúng tên header content type chuẩn của Spring Messaging. Hàm truncate trong ví dụ chỉ giới hạn độ dài; triển khai thực tế cần bổ sung redaction cho token, dữ liệu cá nhân và thông tin nhạy cảm có thể xuất hiện trong exception message.

Không dùng copyHeaders(original.getHeaders()) nếu message có thể chứa mọi loại header. Việc sao chép toàn bộ có thể đưa delivery tag, offset, thông tin nội bộ, token hoặc dữ liệu nhạy cảm sang destination khác. Chỉ giữ metadata mà hệ thống điều tra hoặc replay thực sự cần.

## 6. Gửi message lỗi đến một destination điều tra

Nếu ứng dụng chọn tự quản lý error flow, có thể dùng Consumer<ErrorMessage> làm custom error handler và gửi message đã giữ payload qua một output binding riêng:

~~~java
@Bean
Consumer<ErrorMessage> preserveOrderFailure(StreamBridge streamBridge) {
    return errorMessage -> {
        Message<?> diagnostic = toDiagnosticMessage(errorMessage);
        boolean sent = streamBridge.send("orders-failed-out-0", diagnostic);
        if (!sent) {
            throw new IllegalStateException("Failed to publish diagnostic message");
        }
    };
}
~~~

Khai báo error handler cho input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          error-handler-definition: preserveOrderFailure
        orders-failed-out-0:
          destination: orders.failed
          content-type: application/json
~~~

Custom handler có thể lưu message và thông tin lỗi theo định dạng của ứng dụng. Tuy nhiên, custom error handler là cơ chế thay thế các error handler do framework/binder cung cấp; khi đã khai báo custom handler, không thể giả định binder DLQ vẫn tự động chạy dù đã cấu hình. Nếu muốn sử dụng DLQ native, hãy để binder xử lý lỗi và cấu hình đúng thuộc tính DLQ thay vì đồng thời kỳ vọng custom handler và binder handler cùng xử lý một lỗi.

Giá trị boolean từ StreamBridge cho biết message được chấp nhận qua đường gửi của ứng dụng; nó không phải bằng chứng độc lập rằng broker đã lưu bền vững. Cần xử lý lỗi publish bất đồng bộ và cân nhắc outbox nếu việc lưu bản ghi điều tra phải nhất quán với thay đổi database.

## 7. Dùng DLQ do binder quản lý để giữ message gốc

Dead Letter Queue là lựa chọn phù hợp khi muốn broker/binder giữ message lỗi để điều tra, đối soát hoặc phát lại. Tên destination, metadata bổ sung và khả năng republish khác nhau theo binder.

Ví dụ Rabbit binder:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 3
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
~~~

auto-bind-dlq yêu cầu Rabbit binder tạo và cấu hình DLQ cho binding. republish-to-dlq yêu cầu binder republish message lỗi với metadata chẩn đoán bổ sung, ví dụ exception message hoặc stack trace, tùy phiên bản và cấu hình. Payload gốc được giữ cho các bước điều tra tiếp theo. Cần xem tài liệu Rabbit binder đang dùng để xác nhận cách đặt tên queue, routing và giới hạn kích thước header.

Kafka binder có cấu hình DLQ riêng, chẳng hạn enable-dlq và các thuộc tính liên quan đến DLT. Cần kiểm tra tài liệu Kafka binder cho phiên bản đang dùng, bao gồm cách giữ record key, headers, offset, partition và exception metadata. Pulsar binder có cơ chế dead-letter policy và subscription riêng; không sao chép thuộc tính Rabbit hoặc Kafka sang Pulsar.

Khi dùng DLQ native, kiểm tra message thực tế trong destination lỗi: payload có còn nguyên không, header ứng dụng nào được giữ, binder đã thêm header nào, và có thông tin về nguồn gốc/exception đủ để điều tra hay chưa. Đừng coi tên DLQ là bảo đảm rằng mọi header vận chuyển đều được giữ nguyên qua mọi broker.

## 8. Phân biệt retry, requeue và DLQ

Ba cơ chế này phục vụ các mục đích khác nhau:

| Cơ chế | Ý nghĩa | Dữ liệu được giữ ở đâu? |
|---|---|---|
| Retry trong ứng dụng | Gọi lại handler sau lỗi, thường với backoff và giới hạn số lần | Message vẫn nằm trong luồng xử lý hiện tại theo cơ chế framework/binder |
| Requeue/redelivery | Yêu cầu broker giao lại message | Broker giữ message theo semantics của queue, offset hoặc subscription |
| DLQ | Chuyển message lỗi sang destination riêng | Payload và metadata được giữ theo cách binder triển khai |

Retry không phải lúc nào cũng tạo một bản sao message mới. Requeue không đồng nghĩa với việc ghi lại payload. DLQ không tự sửa message hoặc giải quyết nguyên nhân lỗi. Hãy chọn chính sách theo loại lỗi và khả năng khôi phục.

Lỗi tạm thời như dịch vụ downstream timeout có thể retry với backoff. Lỗi dữ liệu cố định như schema không hợp lệ thường nên đưa vào DLQ sau số lần thử giới hạn. Nếu requeue vô hạn một message độc hại, nó có thể tạo vòng lặp và chặn các message khác trong queue hoặc partition.

## 9. Giữ dữ liệu thô khi lỗi xảy ra trước khi gọi function

Một số lỗi xảy ra trước khi function nhận được DTO, chẳng hạn JSON không parse được, schema không tương thích hoặc native deserializer thất bại. Khi đó, payload mà consumer code nhìn thấy có thể chưa tồn tại dưới dạng POJO. Message gốc có thể chứa byte[] hoặc dữ liệu thô được binder đặt trong metadata lỗi.

Trong tình huống này:

- Ưu tiên binder DLQ hoặc error path có thể giữ record/body gốc.
- Giữ content type, schema ID/version, key và headers liên quan.
- Nếu phải lưu trữ thủ công, lưu byte gốc cùng encoding, checksum và thông tin nguồn.
- Không deserialize bằng một kiểu gần giống rồi serialize lại để giả lập bản gốc.
- Lưu exception chain và phiên bản serializer/deserializer để có thể tái hiện lỗi.

Nếu payload gốc là byte[], có thể tính SHA-256 để xác nhận bản sao điều tra không bị thay đổi. Checksum không thay thế chữ ký số hoặc bằng chứng nguồn gốc, nhưng hữu ích để kiểm tra tính toàn vẹn khi lưu và chuyển file.

## 10. Lưu stack trace và thông tin lỗi an toàn

Stack trace và exception message có thể chứa SQL, URL nội bộ, tên host, đường dẫn file, dữ liệu request hoặc giá trị nhạy cảm. Không nên chèn toàn bộ stack trace vào header broker vì header có giới hạn kích thước và có thể được nhiều consumer đọc.

Một bản ghi chẩn đoán nên có:

- eventId và correlationId để tìm lại luồng nghiệp vụ.
- binding, destination, consumer group và binder.
- exception type và thông điệp lỗi đã được lọc.
- thời điểm lỗi, attempt/delivery count nếu có.
- schema version và content type.
- traceId/spanId nếu tracing được bật.
- tham chiếu đến log/trace hoặc object storage chứa chi tiết lớn hơn.

Nếu cần lưu stack trace đầy đủ, lưu trong hệ thống log hoặc kho điều tra có phân quyền, retention và audit phù hợp; đưa một reference ID vào metadata của failure record. Tránh ghi token, password, cookie, dữ liệu cá nhân hoặc payload nhạy cảm vào log và header DLQ. TLS bảo vệ đường truyền nhưng không thay thế kiểm soát quyền truy cập broker, DLQ và kho log.

## 11. Replay mà không làm sai metadata

Replay là phát lại message lỗi sau khi đã sửa nguyên nhân. Trước khi replay, cần phân biệt metadata nghiệp vụ với metadata vận chuyển:

- Giữ eventId gốc để truy vết và chống xử lý trùng.
- Giữ correlationId, causationId, aggregateId và schemaVersion nếu chúng còn ý nghĩa.
- Thêm replayId, replayedAt và replayAttempt để theo dõi lần phát lại.
- Không tái sử dụng delivery tag, consumer tag, offset hoặc acknowledgement handle từ lần giao cũ.
- Xác thực destination và schema đích trước khi phát lại.
- Dùng consumer idempotent vì replay có thể tạo xử lý lặp.

Không tự động replay mọi message trong DLQ ngay khi thấy lỗi đã giảm. Nên phân loại theo nguyên nhân, kiểm tra payload/schema, giới hạn tốc độ và có khả năng dừng replay. Với message có lỗi nghiệp vụ vĩnh viễn, cần sửa dữ liệu hoặc quyết định thủ công trước khi phát lại.

## 12. Kiểm thử khả năng bảo toàn payload và metadata

Kiểm thử cần xác nhận cả nội dung lẫn nguồn gốc:

- Gửi một message hợp lệ nhưng cố ý làm handler thất bại; xác nhận payload trong ErrorMessage/DLQ khớp message ban đầu.
- So sánh eventId, correlationId, eventType, schemaVersion và content type trước/sau khi chuyển sang error destination.
- Gửi payload dạng byte[] hoặc JSON sai cú pháp để kiểm tra đường lỗi conversion trước khi function được gọi.
- Xác nhận raw bytes hoặc checksum không thay đổi khi yêu cầu bảo toàn byte.
- Xác nhận exception type, message đã lọc và thời điểm lỗi được ghi nhận.
- Kiểm tra header nhạy cảm bị loại hoặc che trước khi ghi log/đưa vào DLQ.
- Kiểm tra retry count, redelivery metadata và DLQ routing theo binder.
- Replay một message đã lưu và xác nhận eventId gốc được giữ, replayId mới được thêm, consumer xử lý idempotent.
- Thử trường hợp error handler không thể publish sang error destination và xác nhận lỗi đó được quan sát/khôi phục.

Test Binder có thể kiểm tra ErrorMessage và logic handler trong phạm vi ứng dụng. Nó không thay thế integration test với Kafka, RabbitMQ hoặc Pulsar khi cần xác minh payload byte gốc, key, headers, DLQ, offset, ack/requeue và metadata do broker thêm.

## 13. Checklist điều tra message lỗi

- [ ] Đã lấy originalMessage hoặc MessagingException.failedMessage nếu có.
- [ ] Đã xác định payload là POJO, String hay byte[] thô.
- [ ] Đã giữ payload gốc; thông tin lỗi được lưu ở metadata hoặc envelope riêng.
- [ ] Đã giữ allowlist header nghiệp vụ và content type/schema version cần thiết.
- [ ] Đã tách header nghiệp vụ khỏi delivery tag, offset và metadata vận chuyển tạm thời.
- [ ] Đã ghi eventId, correlationId, source binding, exception type, timestamp và attempt.
- [ ] Đã lọc stack trace, exception message và dữ liệu nhạy cảm trước khi lưu.
- [ ] Đã chọn custom error handler hoặc binder DLQ theo đúng cơ chế, không giả định hai handler tự chạy đồng thời.
- [ ] Đã xác minh hành vi cụ thể với binder và broker đang triển khai.
- [ ] Đã có quy trình replay giới hạn tốc độ và bảo đảm idempotency.

Giữ nguyên payload và metadata có chọn lọc giúp nhóm phát triển tái hiện lỗi, xác định nguồn message và phát lại dữ liệu mà không làm sai hợp đồng nghiệp vụ. Trong Spring Cloud Stream, hãy tận dụng originalMessage/failedMessage khi có, dùng DLQ native khi cần bảo toàn theo broker, và chỉ xây dựng custom ErrorMessage handler khi đã hiểu rõ nó thay thế cơ chế xử lý lỗi mặc định nào. Payload gốc, metadata nghiệp vụ và thông tin chẩn đoán cần được lưu tách bạch, có kiểm soát truy cập và có thể kiểm chứng.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.1 — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/5.1/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
