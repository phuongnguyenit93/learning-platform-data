# Chọn khóa bản ghi bằng messageKeyExpression hoặc Kafka header

Kafka record có hai phần dữ liệu chính: **key** và **value**. Value thường chứa payload nghiệp vụ; key giúp Kafka định tuyến record đến partition và hỗ trợ các cách tổ chức dữ liệu theo thực thể. Với một luồng đơn hàng, chọn orderId làm key giúp các sự kiện của cùng đơn hàng thường đi vào cùng partition. Với topic dùng log compaction, key còn xác định nhóm record mà Kafka giữ lại giá trị mới nhất.

Spring Cloud Stream Kafka Binder cho phép đặt record key theo hai cách phổ biến: cấu hình **messageKeyExpression** để trích xuất key từ message đang gửi, hoặc đặt Kafka key header trực tiếp bằng **KafkaHeaders.KEY**. Cả hai cách đều tạo key cho Kafka record. Cần phân biệt chúng với header tùy chỉnh thông thường và với cơ chế partitioning chung của Spring Cloud Stream.

## 1. Kafka record key là gì?

Một Kafka record có thể hình dung như sau:

~~~text
ProducerRecord
  topic: orders.events
  partition: (do producer chọn hoặc chỉ định)
  key: "ORD-1001"
  value: {"orderId":"ORD-1001","status":"CONFIRMED"}
  headers:
    eventType: OrderConfirmed
    correlationId: corr-81
~~~

Key và value được tuần tự hóa riêng bằng key serializer và value serializer. Key là trường riêng của ProducerRecord, không phải một phần của JSON payload và cũng không phải một Kafka header thông thường.

Khi producer không chỉ định partition cụ thể, Kafka partitioner dùng key để chọn partition. Với key khác null, partitioner mặc định thường băm key để chọn partition trong topic. Với key null, Kafka producer có thể dùng chiến lược phân phối khác, chẳng hạn sticky partitioning; vì vậy không nên giả định message không có key sẽ được chia đều theo hash.

Các record cùng key thường được gửi đến cùng partition khi số partition và partitioning strategy không đổi. Kafka giữ thứ tự append trong từng partition, nên đây là cơ sở để duy trì thứ tự các sự kiện của cùng một thực thể. Không có thứ tự toàn cục giữa các partition.

## 2. Chọn key theo thực thể nghiệp vụ

Key nên đại diện cho thực thể mà ứng dụng muốn nhóm hoặc giữ thứ tự:

| Loại sự kiện | Key phù hợp | Lợi ích |
|---|---|---|
| Thay đổi trạng thái đơn hàng | orderId | Các sự kiện của một đơn hàng được gom về cùng partition |
| Giao dịch tài khoản | accountId | Các cập nhật của một tài khoản có thể xử lý tuần tự |
| Thay đổi hồ sơ khách hàng | customerId | Consumer dễ xây dựng projection theo khách hàng |
| Cập nhật tồn kho | sku | Các thay đổi của cùng sản phẩm được nhóm cùng key |

Ví dụ, nếu một đơn hàng lần lượt phát OrderCreated, OrderPaid và OrderShipped, dùng cùng orderId làm key giúp các record được ghi vào cùng partition. Consumer có thể đọc theo thứ tự broker ghi trong partition đó.

Không chọn key ngẫu nhiên cho mỗi message nếu mục tiêu là nhóm các sự kiện theo thực thể. Không chọn timestamp thay cho khóa nghiệp vụ khi cần ổn định theo thực thể: timestamp có thể trùng, lệch đồng hồ hoặc không phản ánh đúng thứ tự mà broker nhận record.

Key cần có giá trị và được chuẩn hóa giống nhau giữa các producer. Nếu một producer dùng customer-10, producer khác dùng CUSTOMER-10, chúng có thể bị định tuyến khác partition dù cùng chỉ một khách hàng.

## 3. Đặt key bằng messageKeyExpression

messageKeyExpression là thuộc tính riêng của Kafka Binder. Binder đánh giá biểu thức SpEL trên message đầu ra và dùng kết quả làm key của Kafka record.

Ví dụ, payload có kiểu:

~~~java
record OrderEvent(
        String orderId,
        String customerId,
        String eventType,
        long sequence) {}
~~~

Khai báo binding và biểu thức lấy key từ payload:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          content-type: application/json
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              messageKeyExpression: payload.orderId
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

Trong ví dụ:

- publishOrder-out-0 là output binding được hàm publishOrder sử dụng.
- destination ánh xạ binding đến topic orders.events.
- messageKeyExpression: payload.orderId lấy orderId từ payload của message đầu ra.
- key.serializer cho Kafka biết cách mã hóa key kiểu String thành byte.

Ví dụ hàm phát sự kiện:

~~~java
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderProducerConfiguration {

    @Bean
    Supplier<OrderEvent> publishOrder() {
        return () -> new OrderEvent(
                "ORD-1001",
                "CUS-01",
                "OrderCreated",
                1);
    }
}
~~~

Khi supplier phát message, Kafka Binder đánh giá biểu thức trên payload và tạo record có key ORD-1001. Key không cần được lặp lại trong value nếu consumer có thể lấy định danh từ key; tuy nhiên, giữ định danh trong payload cũng thường hữu ích để dữ liệu vẫn tự mô tả khi được chuyển sang hệ thống khác.

messageKeyExpression mặc định không được đặt. Nếu không có biểu thức và message cũng không mang Kafka key header, record có thể được gửi với key null; khi đó Kafka dùng partitioner mặc định cho record không có key.

## 4. Lấy key từ header tùy chỉnh bằng messageKeyExpression

Đôi khi key không nằm trong payload hoặc ứng dụng muốn giữ payload độc lập với cách định tuyến. Khi đó, producer có thể đặt một header tùy chỉnh rồi cấu hình messageKeyExpression đọc header đó.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderEvent> message = MessageBuilder
        .withPayload(new OrderEvent(
                "ORD-1002",
                "CUS-02",
                "OrderPaid",
                2))
        .setHeader("customerKey", "CUS-02")
        .build();
~~~

Cấu hình Kafka Binder:

Đây là phương án thay cho biểu thức lấy key từ payload ở phần trước; không cần cấu hình hai nguồn key khác nhau cho cùng binding.

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              messageKeyExpression: headers['customerKey']
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

Binder đọc customerKey từ MessageHeaders và sử dụng giá trị đó làm record key. Header tùy chỉnh chỉ trở thành key vì biểu thức tham chiếu đến nó. Nếu bỏ messageKeyExpression, customerKey chỉ là metadata thông thường; nó không tự động thay thế Kafka record key.

Biểu thức có thể đọc các header khác hoặc kết hợp logic SpEL. Hãy bảo đảm header luôn tồn tại, có kiểu mà key serializer hỗ trợ và không trả về null ngoài dự kiến. Nếu cần giá trị mặc định, có thể xử lý ngay khi tạo message hoặc dùng biểu thức có điều kiện, nhưng quy tắc key nên nhất quán giữa các producer.

## 5. Đặt key trực tiếp bằng KafkaHeaders.KEY

Nếu ứng dụng đã tạo Message<?>, có thể đặt Kafka key bằng header chuyên dụng KafkaHeaders.KEY. Đây là cách thuận tiện khi key đã có sẵn trong mã Java:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderEvent> message = MessageBuilder
        .withPayload(new OrderEvent(
                "ORD-1003",
                "CUS-03",
                "OrderShipped",
                3))
        .setHeader(KafkaHeaders.KEY, "ORD-1003")
        .build();
~~~

Khi dùng header chuyên dụng này, Kafka Binder có thể lấy giá trị làm key của record mà không cần khai báo messageKeyExpression. Cấu hình serializer cho key vẫn cần phù hợp với kiểu dữ liệu của key.

KafkaHeaders.KEY là tên hằng số hiện hành trong Spring Kafka. Ở các phiên bản cũ, tài liệu và mã nguồn có thể dùng KafkaHeaders.MESSAGE_KEY; hằng số MESSAGE_KEY đã bị deprecated để chuyển sang KEY từ Spring Kafka 2.9 và bị loại bỏ trong các phiên bản mới hơn. Khi nâng cấp, dùng hằng số tương ứng với phiên bản Spring Kafka trong dependency của dự án.

Ví dụ hoàn chỉnh dùng StreamBridge:

Khai báo output binding mà service sẽ gửi vào:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders.events
          content-type: application/json
      kafka:
        bindings:
          orderEvents-out-0:
            producer:
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final StreamBridge streamBridge;

    OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean publish(OrderEvent event) {
        Message<OrderEvent> message = MessageBuilder
                .withPayload(event)
                .setHeader(KafkaHeaders.KEY, event.orderId())
                .build();

        return streamBridge.send("orderEvents-out-0", message);
    }
}
~~~

Ở đây, orderEvents-out-0 phải được khai báo và ánh xạ tới topic Kafka tương ứng. Giá trị boolean của send cho biết message đã được chấp nhận qua binding/channel; nó không thay thế xác nhận broker đã lưu record hoặc consumer đã xử lý xong.

## 6. Chọn giữa messageKeyExpression và Kafka header

Hai cách đều có thể tạo cùng một record key. Chọn cách phù hợp với nơi ứng dụng đang giữ thông tin:

| Tình huống | Cách nên dùng |
|---|---|
| Key luôn lấy từ một trường payload | messageKeyExpression: payload.orderId |
| Key được tính từ metadata hoặc header nghiệp vụ | messageKeyExpression: headers['customerKey'] |
| Mã Java chủ động tạo Message<?> và biết key | KafkaHeaders.KEY |
| Hàm xử lý muốn giữ key nhận từ Kafka | Sao chép key nhận vào header đầu ra hoặc dùng expression đọc received key |
| Key cần được quyết định bởi một quy tắc SpEL tập trung | messageKeyExpression |

Tránh đặt nhiều nguồn key mâu thuẫn trong cùng một binding. Ví dụ, payload có orderId=ORD-1 nhưng header KafkaHeaders.KEY lại là ORD-2; người đọc khó xác định quy tắc nghiệp vụ nào đang được áp dụng. Chọn một nguồn chuẩn và kiểm thử record key thực tế.

## 7. Giữ key khi một Function chuyển tiếp message

Một processor có thể nhận message từ topic đầu vào rồi phát sang topic đầu ra. Nếu muốn giữ nguyên key, có thể cấu hình messageKeyExpression đọc header key nhận vào:

~~~yaml
spring:
  cloud:
    function:
      definition: forwardOrder
    stream:
      bindings:
        forwardOrder-in-0:
          destination: orders.in
          group: order-forwarder
        forwardOrder-out-0:
          destination: orders.out
      kafka:
        bindings:
          forwardOrder-out-0:
            producer:
              messageKeyExpression: headers['kafka_receivedMessageKey']
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

Kafka Binder đưa record key nhận vào message header kafka_receivedMessageKey (hằng số tương ứng trong Spring Kafka hiện hành là KafkaHeaders.RECEIVED_KEY). Biểu thức lấy giá trị này để tạo key cho record đầu ra.

Với một Function thông thường xử lý message, cấu hình trên là cách ngắn gọn để chuyển tiếp key. Với reactive function, ứng dụng cần tự sao chép header từ message đầu vào sang message đầu ra; không nên giả định mọi header tự được giữ khi tạo message mới.

Đoạn YAML minh họa cách lấy received key bằng expression. Với reactive function ở ví dụ tiếp theo, ứng dụng đặt trực tiếp KafkaHeaders.KEY trên message đầu ra; khi dùng cách này, không cần thêm messageKeyExpression cho cùng binding.

Ví dụ reactive function giữ key rõ ràng:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import reactor.core.publisher.Flux;

@Configuration
class OrderForwardingConfiguration {

    @Bean
    Function<Flux<Message<OrderEvent>>, Flux<Message<OrderEvent>>> forwardOrder() {
        return messages -> messages.map(input -> {
            OrderEvent output = transform(input.getPayload());

            return MessageBuilder.withPayload(output)
                    .setHeader(
                            KafkaHeaders.KEY,
                            input.getHeaders().get(KafkaHeaders.RECEIVED_KEY))
                    .build();
        });
    }
}
~~~

Trong ví dụ, key nhận từ Kafka được đặt lại vào header chuyên dụng KafkaHeaders.KEY của message đầu ra. Nếu dùng phiên bản Spring Kafka cũ, tên hằng số nhận có thể là RECEIVED_MESSAGE_KEY. Hãy dùng API phù hợp với dependency thực tế và kiểm thử sau khi nâng cấp.

Phương thức transform trong ví dụ đại diện cho logic biến đổi payload của ứng dụng; phần trọng tâm ở đây là giữ lại key trong lúc tạo message mới.

## 8. Phân biệt record key với partition-key-expression

Spring Cloud Stream có thuộc tính partitioning chung cho producer:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.orderId
            partition-count: 12
~~~

partition-key-expression và partition-count thuộc cơ chế partitioning của Spring Cloud Stream. Binder dùng key được trích xuất cùng partition selector để xác định partition đích. Với Kafka, topic partitioning đã được broker hỗ trợ tự nhiên; khi không dùng binder partitioning, Kafka partitioner chọn partition dựa trên record key.

messageKeyExpression là thuộc tính riêng của Kafka Binder để tạo Kafka record key. Hai thuộc tính có tên gần giống nhưng vai trò không hoàn toàn giống nhau:

| Thuộc tính | Vai trò |
|---|---|
| partition-key-expression | Lấy khóa cho cơ chế chọn partition chung của Spring Cloud Stream |
| partition-count | Số partition mục tiêu trong cơ chế binder partitioning; với Kafka còn là gợi ý provisioning |
| messageKeyExpression | Tạo key của Kafka ProducerRecord |
| KafkaHeaders.KEY | Đặt trực tiếp key của Kafka ProducerRecord |

Nếu chỉ cần Kafka chọn partition tự nhiên theo key, thường chỉ cần record key qua messageKeyExpression hoặc KafkaHeaders.KEY. Nếu cần binder partition selector tùy chỉnh, dùng partition-key-expression và cấu hình partition count phù hợp. Nếu nghiệp vụ cần cả định tuyến partition theo quy tắc riêng và key được lưu trên record để compaction/consumer tra cứu, hãy cấu hình rõ cả hai và kiểm tra chúng không mâu thuẫn.

Không nhầm record key với partition ID. Key là giá trị nghiệp vụ được ghi cùng record; partition ID là vị trí lưu record mà producer hoặc binder chọn. Hai record khác key vẫn có thể nằm cùng partition, và một partition chứa nhiều key.

## 9. Record key, Kafka headers và header mapping

Kafka Headers là tập metadata dạng key/value byte đi kèm record. Chúng khác với record key:

~~~text
Kafka record
  key: "ORD-1001"
  value: {...}
  headers:
    eventType: "OrderConfirmed"
    traceparent: "00-..."
    correlationId: "corr-81"
~~~

KafkaHeaders.KEY là Spring Messaging header đặc biệt được binder dùng để thiết lập record key. Một header tùy chỉnh như customerKey chỉ được dùng làm record key khi messageKeyExpression tham chiếu đến nó. Còn việc chuyển header tùy chỉnh sang Kafka Headers được điều khiển bởi header mapper và headerPatterns.

Ví dụ cấu hình chỉ cho phép một số header tùy chỉnh được truyền sang Kafka:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              headerPatterns: eventType,correlationId,traceparent
~~~

headerPatterns kiểm soát header metadata được map sang Kafka Headers; nó không thay thế messageKeyExpression và không biến mọi header thành record key. Không cần đưa key vào headerPatterns chỉ để đặt record key bằng KafkaHeaders.KEY.

## 10. Key serializer và kiểu dữ liệu

Kafka lưu key dưới dạng byte. Key serializer phải tương thích với kiểu Java mà biểu thức hoặc header trả về:

| Kiểu key trong ứng dụng | Serializer thường dùng |
|---|---|
| String | StringSerializer |
| byte[] | ByteArraySerializer |
| Integer | IntegerSerializer |
| Long | LongSerializer |

Nếu messageKeyExpression trả về String nhưng key serializer được cấu hình cho một kiểu khác, producer có thể gặp lỗi serialization. Với object tùy chỉnh, cần serializer tương ứng và một hợp đồng giải mã rõ ràng ở consumer.

Ví dụ cấu hình key kiểu Long:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishMetric-out-0:
            producer:
              messageKeyExpression: payload.accountNumber
              configuration:
                key.serializer: org.apache.kafka.common.serialization.LongSerializer
~~~

Đảm bảo accountNumber thực sự là Long, không phải chuỗi số. Không dựa vào chuyển đổi ngầm giữa String và Long. Nếu dùng native encoding, producer/consumer cần cấu hình serializer/deserializer tương ứng cho key và value; content-type không thay thế cấu hình native serializer.

## 11. Lưu ý về phiên bản và thứ tự đánh giá expression

Từ Spring Cloud Stream Kafka Binder 3.0, messageKeyExpression được đánh giá trước khi payload được chuyển đổi thành byte. Vì vậy, biểu thức có thể đọc payload Java, ví dụ payload.orderId, ngay cả khi binding dùng message converter. Với các phiên bản trước 3.0, payload có thể đã là byte[] tại thời điểm expression được đánh giá; khi đó, đọc trường payload thường không hoạt động trừ khi dùng native encoding. Cách tương thích hơn với phiên bản cũ là đặt key vào header rồi đọc headers['customerKey'].

Khi nâng cấp Spring Cloud Stream hoặc Spring Kafka:

- Kiểm tra phiên bản binder và Spring Kafka tương thích trong dependency management.
- Dùng KafkaHeaders.KEY và KafkaHeaders.RECEIVED_KEY ở các phiên bản hiện hành.
- Thay các hằng số cũ MESSAGE_KEY và RECEIVED_MESSAGE_KEY khi API đã loại bỏ chúng.
- Kiểm tra biểu thức messageKeyExpression sau khi thay đổi message converter hoặc native encoding.
- Kiểm tra producer thực tế đang dùng đúng key serializer.

Không chỉ dựa vào việc ứng dụng khởi động thành công. Một SpEL expression có thể hợp lệ về cú pháp nhưng trả null hoặc giá trị sai kiểu ở runtime.

## 12. Kiểm tra key ở consumer

Consumer có thể đọc key đã được Kafka gửi cùng record. Với Spring Messaging, Kafka Binder ánh xạ key nhận vào header KafkaHeaders.RECEIVED_KEY:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@Configuration
class OrderAuditConfiguration {

    @Bean
    Consumer<Message<OrderEvent>> auditOrder() {
        return message -> {
            Object recordKey =
                    message.getHeaders().get(KafkaHeaders.RECEIVED_KEY);

            System.out.printf(
                    "key=%s order=%s event=%s%n",
                    recordKey,
                    message.getPayload().orderId(),
                    message.getPayload().eventType());
        };
    }
}
~~~

Consumer nên xác nhận key có đúng định danh mong đợi và nhất quán với payload. Nếu key khác payload.orderId, có thể producer đã dùng một quy tắc khác hoặc message bị tạo sai. Với hệ thống dùng nhiều loại event, key có thể là aggregate ID chung thay vì một trường trùng tên trong mọi payload; hợp đồng cần nói rõ điều đó.

## 13. Key và log compaction

Kafka topic có thể dùng cleanup.policy=compact để giữ giá trị mới nhất theo key trong quá trình compaction. Ví dụ:

~~~text
key=ORD-1, value={status: CREATED}
key=ORD-2, value={status: CREATED}
key=ORD-1, value={status: PAID}
key=ORD-1, value={status: SHIPPED}
~~~

Sau compaction, Kafka có thể giữ record mới nhất cho ORD-1 và ORD-2 thay vì toàn bộ thay đổi của ORD-1. Vì vậy:

- Dùng key ổn định đại diện cho aggregate cần lưu trạng thái.
- Không dùng key ngẫu nhiên nếu muốn compaction gom các phiên bản của cùng thực thể.
- Dùng tombstone (record có key và value null) theo quy tắc Kafka để biểu diễn việc xóa key.
- Không dùng compact cho event log nếu consumer cần đọc đầy đủ lịch sử mọi sự kiện.

Record key cũng giúp consumer xây dựng state theo khóa và hỗ trợ truy vấn/đối soát. Tuy nhiên, compaction là tác vụ nền; không giả định bản cũ biến mất ngay sau khi record mới được ghi.

## 14. Các lỗi thường gặp khi chọn key

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tất cả record có key null | Expression không đọc được trường hoặc header không tồn tại | Kiểm tra SpEL, tên header và payload trước khi gửi |
| Lỗi serialization key | Key type không khớp key.serializer | Đặt serializer đúng kiểu hoặc chuẩn hóa kiểu key |
| Cùng thực thể đi nhiều partition | Key không ổn định hoặc producer dùng quy tắc khác nhau | Chuẩn hóa key và thống nhất partitioner |
| Header có customerKey nhưng record key vẫn null | Header thường không tự trở thành Kafka key | Dùng messageKeyExpression hoặc KafkaHeaders.KEY |
| Key đầu ra mất sau Function | Hàm tạo Message mới nhưng không sao chép/đặt lại key | Sao chép header nhận hoặc đặt lại KafkaHeaders.KEY |
| Consumer không thấy key | Đọc nhầm header metadata hoặc dùng API hằng số cũ | Đọc KafkaHeaders.RECEIVED_KEY theo phiên bản hiện hành |
| Key phân bố lệch tải | Một số aggregate tạo nhiều message hơn phần còn lại | Đo phân bố key; đánh giá lại khóa/shard mà không phá yêu cầu thứ tự |

Không dùng email, số điện thoại, access token hoặc dữ liệu nhạy cảm làm key thô nếu không cần thiết. Key được lưu cùng record và có thể xuất hiện trong công cụ quản trị, log hoặc bản sao dữ liệu. Ưu tiên ID nội bộ ổn định hoặc giá trị giả danh hóa theo chính sách dữ liệu của hệ thống.

## 15. Kiểm thử message key

Test binder của Spring Cloud Stream hữu ích để kiểm tra logic hàm và binding, nhưng không phải lúc nào cũng xác nhận được key thực tế do Kafka producer ghi. Với yêu cầu quan trọng, dùng integration test với Kafka broker (chẳng hạn Embedded Kafka hoặc môi trường container) và đọc ConsumerRecord để kiểm tra:

- Topic và partition thực tế.
- Record key sau serialization/deserialization.
- Value và headers đi cùng record.
- Nhiều event cùng aggregate có cùng key và được ghi vào cùng partition khi partition count không đổi.
- Function chuyển tiếp giữ đúng key nhận vào.
- Key null hoặc sai kiểu được phát hiện theo chính sách.

Khi kiểm thử messageKeyExpression, nên có ít nhất một test cho key lấy từ payload và một test cho key lấy từ header. Khi kiểm thử KafkaHeaders.KEY, xác nhận ConsumerRecord.key() bằng giá trị mong đợi; không chỉ kiểm tra MessageHeaders ở phía producer.

## 16. Checklist trước khi phát hành

- Chọn key theo aggregate hoặc thực thể cần nhóm, chẳng hạn orderId hoặc accountId.
- Xác định rõ key lấy từ payload, custom header hay KafkaHeaders.KEY.
- Nếu dùng messageKeyExpression, kiểm tra biểu thức trên đúng message đầu ra.
- Nếu dùng Kafka header, đặt KafkaHeaders.KEY và dùng API phù hợp phiên bản Spring Kafka.
- Đặt key.serializer đúng kiểu dữ liệu của key.
- Phân biệt record key với Kafka Headers và partition-key-expression.
- Với Function chuyển tiếp, giữ key đầu vào một cách tường minh.
- Kiểm tra key null, key sai kiểu, key không ổn định và phân bố lệch.
- Xác nhận record key và partition bằng integration test với Kafka.
- Đánh giá tác động của key đến ordering, log compaction, quyền riêng tư và hot partition.

messageKeyExpression phù hợp khi key có thể được trích xuất từ payload hoặc header bằng SpEL. KafkaHeaders.KEY phù hợp khi mã Java muốn đặt trực tiếp key cho Kafka record. Hai cách đều giúp Kafka định tuyến theo key và gom các sự kiện cùng thực thể vào một partition khi partitioning strategy ổn định. Cần giữ rõ ranh giới giữa record key, Kafka headers và binder partitioning; đồng thời kiểm tra serializer, phiên bản API và record thực tế để bảo đảm key được ghi đúng như hợp đồng.

## Tài liệu tham khảo

- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Tips and Tricks](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_tips.html)
- [Spring Cloud Stream — Partitioning with the Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/partitions.html)
- [Spring for Apache Kafka — KafkaHeaders API](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/support/KafkaHeaders.html)
