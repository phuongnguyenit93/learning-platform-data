# Message body, properties và application headers trong AMQP

Trong một hệ thống dùng RabbitMQ, “message” không chỉ là chuỗi JSON hoặc đối tượng Java mà producer muốn gửi. Ở mức giao thức AMQP 0-9-1, một message có **body** (dữ liệu thực), **properties** (metadata chuẩn của message) và **headers** (bảng metadata mở rộng). Khi publish, producer còn cung cấp **exchange** và **routing key** để broker quyết định nơi định tuyến. Hiểu đúng ranh giới giữa các thành phần này giúp ứng dụng Spring AMQP truyền dữ liệu rõ ràng, xử lý message tương thích giữa các service và vận hành các luồng bất đồng bộ đáng tin cậy.

Bài này thuộc chương **Mô hình AMQP** của lộ trình **SPRING_AMQP**: học tích hợp RabbitMQ với Spring AMQP bằng RabbitTemplate, @RabbitListener, exchange, queue và binding; từ đó làm nền cho định tuyến, xác nhận giao nhận, retry, dead-letter, giao dịch và quan sát hệ thống.

## 1. Mục tiêu và bức tranh tổng thể

Sau bài học, bạn có thể:

- Giải thích vai trò của body, standard properties, application headers và phân biệt chúng với exchange/routing key.
- Chọn đúng nơi lưu payload nghiệp vụ, định danh, thông tin nội dung, dữ liệu truy vết và metadata dành cho routing.
- Tạo, gửi, nhận và kiểm tra từng thành phần bằng các API Message, MessageProperties, RabbitTemplate và @RabbitListener của Spring AMQP.
- Nhận diện giới hạn của metadata: các properties không tự bảo đảm giao nhận, thứ tự, tính duy nhất hoặc khả năng tương thích schema.

Sơ đồ dưới đây cho thấy producer gắn body và metadata vào message, còn exchange sử dụng thông tin định tuyến để đưa message đến queue:

~~~mermaid
flowchart LR
    P["Producer<br/>RabbitTemplate"] -->|"publish(exchange, routing key, message)"| X["Exchange"]
    X -->|"binding khớp"| Q["Queue"]
    Q --> C["Consumer<br/>@RabbitListener"]
    M["Message<br/>body: byte[]<br/>properties: metadata chuẩn<br/>headers: key/value"] -.-> P
~~~

**Điểm dễ nhầm:** exchange và routing key thuộc lệnh publish (routing envelope), không phải các application headers. Khi consume, Spring AMQP có thể cung cấp các trường như receivedExchange và receivedRoutingKey trong MessageProperties để người nhận biết đường đi của message; đây là thông tin nhận được, không biến chúng thành application headers lúc publish.

## 2. Ba lớp thông tin trong một message

| Thành phần | Trả lời câu hỏi | Nội dung điển hình | Ai sử dụng? |
|---|---|---|---|
| **Message body** | “Việc gì đã xảy ra hoặc cần xử lý?” | JSON, text, byte nhị phân, Avro/Protobuf | Consumer hoặc bộ chuyển đổi message |
| **Standard properties** | “Message này cần được diễn giải, liên hệ và giao nhận ra sao?” | contentType, contentEncoding, messageId, correlationId, deliveryMode, expiration, replyTo | Producer, consumer, Spring AMQP và một số tính năng RabbitMQ |
| **Application headers** | “Có những nhãn mở rộng nào đi cùng message?” | tenant-id, event-version, trace-id, source-system | Logic ứng dụng; headers exchange nếu dùng kiểu exchange này |
| **Publish envelope** | “Broker phải đưa message đi đâu?” | exchange, routing key, mandatory flag | RabbitMQ khi publish và định tuyến |

Ví dụ, một service đặt hàng publish sự kiện:

~~~yaml
publish:
  exchange: orders.events         # Tham số của lệnh publish
  routingKey: order.created       # Tham số của lệnh publish
message:
  body: '{"event":"OrderCreated","orderId":"O-1001","total":250000}'
  properties:
    contentType: application/json
    contentEncoding: UTF-8
    deliveryMode: PERSISTENT
    messageId: 7c8d2af4-59c6-496a-8939-e506d8a4864b
    correlationId: request-42
    headers:
      tenant-id: shop-vn
      event-version: 1
      trace-id: trace-abc
~~~

Đây là biểu diễn **minh họa để dễ đọc**, không phải định dạng wire hay cấu trúc YAML RabbitMQ bắt buộc. Trên đường truyền, body là bytes; standard properties và headers được mã hóa theo AMQP. Trường headers là một phần của tập basic properties ở mức giao thức, nhưng được tách ra khi giải thích vì nó chứa các key/value do ứng dụng mở rộng.

## 3. Message body: dữ liệu thực nhưng broker không tự hiểu schema

Body là dãy bytes. RabbitMQ thường không phân tích nội dung JSON, XML hay object trong body khi định tuyến qua direct/topic/fanout exchange. Việc biến object thành bytes, và ngược lại, là trách nhiệm của producer, consumer hoặc MessageConverter.

Các định dạng phổ biến:

- **JSON:** dễ quan sát, phổ biến trong hệ thống tích hợp đa ngôn ngữ; cần thỏa thuận schema, kiểu dữ liệu và encoding.
- **Text:** hữu ích cho message đơn giản nhưng khó mở rộng cấu trúc.
- **Protobuf/Avro hoặc bytes tùy biến:** có thể gọn và hỗ trợ schema riêng, nhưng consumer cần biết cách giải mã.

Ví dụ body JSON:

~~~json
{
  "event": "OrderCreated",
  "orderId": "O-1001",
  "customerId": "C-27",
  "total": 250000,
  "currency": "VND"
}
~~~

Message chứa bytes của JSON trên, không chứa trực tiếp một object Java có thể dùng ở mọi runtime. Nếu producer dùng UTF-8 thì consumer cũng phải giải mã phù hợp. Đừng suy ra body luôn là UTF-8 chỉ vì giao diện quản trị RabbitMQ hiển thị nó giống văn bản.

**contentType** và **contentEncoding** mô tả cách hiểu body, nhưng việc gắn hai properties này không tự chuyển object thành JSON. Ví dụ, khai báo contentType là application/json trong khi body thực tế là Java serialized object sẽ gây lỗi cho consumer và làm sai hợp đồng dữ liệu.

### Body nên chứa gì?

Body nên chứa dữ liệu nghiệp vụ cần thiết để consumer thực hiện hành động: ID đơn hàng, loại sự kiện, số tiền, trạng thái hoặc đường dẫn tham chiếu tới dữ liệu lớn. Với một event, ưu tiên payload độc lập và có schema rõ ràng. Không chuyển bí mật, thông tin cá nhân không cần thiết hoặc object graph cồng kềnh chỉ vì gửi message thuận tiện.

Nếu một trường quyết định **ý nghĩa nghiệp vụ** của event hoặc bắt buộc để xử lý và lưu trữ, thường nên đặt nó trong body. Nếu trường chủ yếu phục vụ metadata liên service, quan sát hoặc chính sách chung, headers/properties có thể hợp lý hơn. Đây là quy ước thiết kế, không phải giới hạn cứng của AMQP.

## 4. Standard properties: metadata chuẩn hóa

AMQP 0-9-1 định nghĩa tập basic properties. Trong Spring AMQP, bạn thao tác với chúng thông qua lớp **org.springframework.amqp.core.MessageProperties**.

| Property | Ý nghĩa | Cách dùng, lưu ý |
|---|---|---|
| **contentType** | Kiểu nội dung body | Thường là application/json, text/plain, application/octet-stream; hữu ích cho converter |
| **contentEncoding** | Cách mã hóa nội dung | Ví dụ UTF-8 đối với text/JSON; các bên phải thống nhất quy tắc |
| **deliveryMode** | Chế độ giao message | NON_PERSISTENT hoặc PERSISTENT; chỉ một yếu tố của độ bền |
| **messageId** | Định danh do producer gán | Phục vụ log, truy vết, chống xử lý trùng ở cấp ứng dụng; broker không tự bảo đảm duy nhất |
| **correlationId** | Khóa liên hệ message với workflow/request | Thường dùng cho request/reply, các bước cùng một giao dịch nghiệp vụ |
| **replyTo** | Nơi gửi response trong mẫu request/reply | Có thể là queue hoặc địa chỉ reply do cơ chế RPC sử dụng; không bảo đảm sẽ có reply |
| **timestamp** | Mốc thời gian do publisher cung cấp | Không nên coi là thời điểm broker đã nhận hoặc đã xử lý |
| **type** | Nhãn phân loại message | Có thể hỗ trợ định tuyến logic của consumer, nhưng direct/topic exchange không tự dựa vào trường này |
| **appId** | Định danh ứng dụng phát hành | Hữu ích cho quan sát và đối soát |
| **priority** | Độ ưu tiên message | Chỉ có tác dụng khi queue hỗ trợ ưu tiên, ví dụ có x-max-priority |
| **expiration** | TTL riêng cho message | Giá trị chuỗi số mili giây, ví dụ "60000"; khác thời hạn timeout của request |
| **userId** | Thông tin publisher | RabbitMQ có cơ chế kiểm tra userId với tài khoản kết nối; không tự đặt tùy ý |
| **headers** | Bảng key/value mở rộng | Chứa application headers và có thể cả header do framework/broker thêm |

Một số thuộc tính ít được sử dụng như clusterId tồn tại vì lý do tương thích lịch sử. Không nên xây hợp đồng nghiệp vụ mới dựa vào chúng.

### 4.1. contentType không phải message converter

Với Spring AMQP:

- **RabbitTemplate.send(...)** gửi một đối tượng Message đã có body bytes và MessageProperties.
- **RabbitTemplate.convertAndSend(...)** chuyển object sang Message qua MessageConverter đang được cấu hình, sau đó gửi.
- **@RabbitListener** có thể nhận Message thô hoặc tham số đã được chuyển đổi tùy cấu hình listener/converter và kiểu tham số phương thức.

Nếu dùng SimpleMessageConverter mặc định, hành vi với String, byte[] và Serializable không giống việc cấu hình converter JSON. Vì thế, không nên mặc định rằng convertAndSend một POJO sẽ tạo JSON. Một hệ thống dùng JSON cần cấu hình converter tương ứng hoặc tự serialize rõ ràng.

### 4.2. deliveryMode không đồng nghĩa “đã giao thành công”

PERSISTENT yêu cầu broker lưu message theo cơ chế bền vững thích hợp, nhưng không thay thế các điều kiện khác. Để thiết kế khả năng sống sót sau lỗi broker, còn cần xét loại và độ bền của queue, topology, publisher confirms, replication và chính sách vận hành.

Ngoài ra:

- **Publisher confirm** xác nhận kết quả broker chấp nhận/xử lý publish theo cơ chế confirm; nó không chứng minh consumer đã thực hiện nghiệp vụ.
- **Consumer acknowledgement** liên quan việc consumer xác nhận delivery đã được xử lý; nó độc lập với messageId và deliveryMode.
- **MessageId** không cung cấp exactly-once; consumer vẫn nên thiết kế xử lý idempotent khi có khả năng nhận lại message.

### 4.3. expiration và priority có điều kiện

Property expiration được biểu diễn dưới dạng chuỗi mili giây, ví dụ "30000" cho TTL 30 giây. Queue cũng có thể quy định TTL qua x-message-ttl; nếu cả hai cùng áp dụng, giới hạn nhỏ hơn quyết định thời gian hiệu lực. Việc message hết TTL và bị loại hoặc dead-letter còn phụ thuộc trạng thái queue và chính sách dead-letter.

Priority chỉ hữu ích nếu queue được cấu hình hỗ trợ ưu tiên. Gắn priority=9 không ép một queue thông thường sắp xếp lại message, càng không bảo đảm thứ tự hoàn tất xử lý khi có nhiều consumer.

## 5. Application headers: metadata mở rộng và quy ước hợp đồng

Headers là bảng **key/value** ở cấp message. Khác với body, headers thường là dữ liệu nhỏ để consumer quyết định chính sách xử lý hoặc để broker định tuyến qua headers exchange. Trường headers chấp nhận những kiểu được AMQP field table hỗ trợ, chẳng hạn chuỗi, boolean, các kiểu số, bytes, timestamp, mảng và bảng lồng nhau; không nên mặc định giá trị có thể là một object Java bất kỳ.

Ví dụ một quy ước cho hệ thống event:

| Header | Ví dụ | Ý nghĩa |
|---|---|---|
| **tenant-id** | shop-vn | Phân vùng dữ liệu/tenant của ứng dụng |
| **event-version** | 1 | Phiên bản schema sự kiện do các service thỏa thuận |
| **trace-id** | trace-abc | Liên hệ log/trace giữa các thành phần |
| **source-system** | checkout-service | Nguồn phát message phục vụ chẩn đoán |
| **region** | vn | Dùng làm tiêu chí xử lý hoặc định tuyến bằng headers exchange |

Đặt tên header nhất quán, viết tài liệu về kiểu và ngữ nghĩa của từng key, có phương án khi thiếu header. Ví dụ, event-version là Number, không nên giả định khi nhận lại chắc chắn là String "1"; tùy producer/converter, kiểu thực có thể khác nhau trong nhóm các kiểu số.

### 5.1. Headers exchange thật sự đọc headers nào?

**Direct exchange** đối chiếu routing key theo binding key; **topic exchange** so khớp mẫu routing key; **fanout exchange** phát tới các queue đã binding. Các exchange này không tự xem một header tùy chỉnh tên event-type hay tenant-id là routing key.

Ngược lại, **headers exchange** so khớp các trường header theo binding arguments. Ví dụ:

~~~text
Message headers:
  region = "vn"
  channel = "mobile"

Binding của queue A với headers exchange:
  x-match = "all"
  region = "vn"
  channel = "mobile"

=> Message phù hợp binding của queue A.
~~~

Trong ví dụ này, x-match là **đối số của binding** để chỉ cách so khớp (all/any), không phải một application header mà publisher phải gắn vào message. Lựa chọn exchange nào là quyết định thiết kế topology; headers không thay thế routing key cho direct/topic exchange.

### 5.2. Phân biệt header ứng dụng với header hệ thống

RabbitMQ có thể bổ sung các header như **x-death** khi message bị dead-letter; Spring AMQP hoặc JSON converter cũng có thể sử dụng các header metadata riêng để mô tả kiểu đối tượng. Chúng không nhất thiết là một phần của hợp đồng nghiệp vụ do bạn sở hữu.

Tránh dùng tên trùng với các header broker/framework dự trữ; đừng tự giả lập x-death để ghi nhận số lần retry. Header tùy chỉnh như retry-attempt chỉ là dữ liệu do ứng dụng tự quản, không tự làm broker retry. Khi dựa vào metadata về dead-letter, cần hiểu cơ chế và dữ liệu broker thực sự cung cấp.

## 6. Thực hành: gửi và nhận message có body, properties, headers

Ví dụ sau dùng **Spring Boot + spring-boot-starter-amqp**, RabbitMQ đang chạy, Jackson ObjectMapper có trên classpath. Ta muốn gửi event OrderCreated, giữ body JSON rõ ràng, gắn thông tin truy vết và nhận lại qua listener. Đoạn code tập trung vào metadata; trong ứng dụng thật cần bổ sung cấu hình kết nối, xử lý lỗi và nghiệp vụ.

### 6.1. Khai báo exchange, queue và binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderRabbitConfiguration {

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange("orders.events", true, false);
    }

    @Bean
    Queue ordersCreatedQueue() {
        return QueueBuilder.durable("orders.created.q").build();
    }

    @Bean
    Binding ordersCreatedBinding(Queue ordersCreatedQueue,
                                 DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersCreatedQueue)
                .to(ordersExchange)
                .with("order.created");
    }
}
~~~

Exchange và queue được khai báo durable, direct binding dùng routing key order.created. Những thứ này là topology; chúng không nằm trong body hoặc application headers của từng message.

### 6.2. Publisher dùng RabbitTemplate.send(...)

Ở đây ta chủ động serialize JSON và tạo MessageProperties để thấy chính xác phần nào đi vào body và phần nào đi vào metadata.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

@Service
public class OrderEventPublisher {
    private final RabbitTemplate rabbitTemplate;
    private final ObjectMapper objectMapper;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate,
                               ObjectMapper objectMapper) {
        this.rabbitTemplate = rabbitTemplate;
        this.objectMapper = objectMapper;
    }

    public void publishOrderCreated(String orderId, String tenantId)
            throws JsonProcessingException {
        Map<String, Object> event = Map.of(
                "event", "OrderCreated",
                "orderId", orderId
        );
        byte[] body = objectMapper.writeValueAsBytes(event);

        MessageProperties properties = new MessageProperties();
        properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
        properties.setContentEncoding(StandardCharsets.UTF_8.name());
        properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        properties.setMessageId(UUID.randomUUID().toString());
        properties.setCorrelationId(orderId);
        properties.setHeader("tenant-id", tenantId);
        properties.setHeader("event-version", 1);
        properties.setHeader("source-system", "checkout-service");

        Message message = new Message(body, properties);
        rabbitTemplate.send("orders.events", "order.created", message);
    }
}
~~~

Đọc code theo ba nhóm:

1. **Body:** biến body chứa bytes JSON tạo bởi ObjectMapper.
2. **Properties và headers:** messageId, correlationId, contentType, deliveryMode và các custom headers nằm trong MessageProperties.
3. **Routing:** "orders.events" và "order.created" là tham số truyền cho RabbitTemplate.send; broker dùng chúng để tìm queue.

Đây là cách gửi message một chiều. Giá trị trả về của send không phải xác nhận rằng nghiệp vụ consumer đã chạy. Muốn phát hiện publish bị từ chối, unroutable message hoặc lỗi giao nhận, cần cấu hình riêng publisher confirms/returns và cơ chế xử lý tương ứng.

### 6.3. Consumer nhận Message thô với @RabbitListener

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

import java.io.IOException;

@Component
public class OrderCreatedListener {
    private final ObjectMapper objectMapper;

    public OrderCreatedListener(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @RabbitListener(queues = "orders.created.q")
    public void onMessage(Message message) throws IOException {
        MessageProperties props = message.getMessageProperties();

        if (!MessageProperties.CONTENT_TYPE_JSON.equals(props.getContentType())) {
            throw new IllegalArgumentException("Unexpected content type");
        }

        Object tenantHeader = props.getHeaders().get("tenant-id");
        if (!(tenantHeader instanceof String)
                || ((String) tenantHeader).isBlank()) {
            throw new IllegalArgumentException("Missing tenant-id");
        }

        Object versionHeader = props.getHeaders().get("event-version");
        if (!(versionHeader instanceof Number)
                || ((Number) versionHeader).intValue() != 1) {
            throw new IllegalArgumentException("Unsupported event-version");
        }

        JsonNode payload = objectMapper.readTree(message.getBody());
        String orderId = payload.path("orderId").asText();
        if (orderId.isBlank()) {
            throw new IllegalArgumentException("Missing orderId");
        }

        // Thay bằng logic nghiệp vụ có khả năng xử lý trùng an toàn.
        System.out.printf("orderId=%s, tenant=%s, messageId=%s%n",
                orderId, tenantHeader, props.getMessageId());
    }
}
~~~

Với Message thô, consumer tự kiểm tra contentType, header và schema body. Trong ứng dụng dùng typed listener, Spring AMQP có thể chuyển đổi message thành String/POJO nếu converter và cấu hình phù hợp. Việc nhận POJO thuận tiện nhưng không xóa nhu cầu xác thực schema và quản lý phiên bản.

**Lưu ý về ví dụ:** để dễ thấy ranh giới metadata, listener đọc body trực tiếp bằng ObjectMapper. Mọi exception ở listener cần được kết nối với chính sách retry, requeue và dead-letter phù hợp. Nếu cứ requeue một message lỗi schema, hệ thống có thể xử lý lặp đi lặp lại mà không tiến triển.

### 6.4. Khi nào dùng convertAndSend(...)?

Nếu đã cấu hình converter JSON nhất quán giữa publisher và listener, có thể gửi object và bổ sung header qua MessagePostProcessor:

~~~java
rabbitTemplate.convertAndSend(
        "orders.events",
        "order.created",
        orderCreatedEvent,
        message -> {
            message.getMessageProperties().setHeader("event-version", 1);
            message.getMessageProperties().setHeader("tenant-id", tenantId);
            return message;
        }
);
~~~

Trong snippet này, orderCreatedEvent và tenantId là dữ liệu đã tồn tại trong ứng dụng. Body sinh ra phụ thuộc MessageConverter được cấu hình trên RabbitTemplate. Cần kiểm tra loại bytes, contentType và header kiểu dữ liệu mà converter thực sự phát, đặc biệt khi producer/consumer dùng các phiên bản framework hoặc ngôn ngữ khác nhau.

## 7. Những metadata dễ bị hiểu sai khi nhận message

MessageProperties của Spring AMQP có thêm thông tin được điền tại **phía consumer**, ví dụ:

| Metadata nhận được | Diễn giải đúng |
|---|---|
| **receivedExchange** | Exchange mà RabbitMQ báo cho delivery nhận được |
| **receivedRoutingKey** | Routing key của delivery nhận được |
| **consumerQueue** | Queue mà listener đang lấy message |
| **deliveryTag** | Mã delivery theo channel, phục vụ ack/nack trong phạm vi channel đó |
| **redelivered** | Cờ broker báo message có thể đã được giao trước đó; không phải số lần xử lý chính xác |

Không dùng deliveryTag làm business event ID vì giá trị này gắn với channel/delivery, không ổn định qua các lần nhận lại. Không dùng redelivered=false để suy ra chắc chắn “chưa consumer nào từng thấy message”, và không xem redelivered=true là số lần retry. Đối với tính duy nhất nghiệp vụ, hãy định nghĩa idempotency key rõ ràng, thường là một event ID trong body hoặc messageId do producer tạo với cam kết ổn định.

### MessageId hay correlationId?

- **messageId** trả lời “message/event cụ thể này là gì?”. Một event đã tạo nên có ID ổn định nếu được phát lại có chủ đích.
- **correlationId** trả lời “message này thuộc yêu cầu/luồng tương tác nào?”. Một request có thể liên quan nhiều messages cùng correlationId.
- **trace-id header** trả lời “những thao tác phân tán nào thuộc cùng dấu vết quan sát?”. Có thể trùng hoặc khác correlationId tùy thiết kế tracing.

Ví dụ đơn hàng O-1001 có ba events OrderCreated, PaymentAuthorized và ShipmentScheduled. Ba events có **messageId khác nhau** nhưng có thể cùng correlationId=O-1001; một trace-id có thể nối các bước xử lý qua service. Không đánh đồng ba khái niệm.

## 8. Thiết kế hợp đồng message có khả năng phát triển

Hợp đồng message cần mô tả cả body và metadata; đừng chỉ chia sẻ một class Java giữa producer và consumer. Một hợp đồng tối thiểu cho OrderCreated có thể gồm:

~~~yaml
eventName: OrderCreated
schemaVersion: 1
contentType: application/json
contentEncoding: UTF-8
routing:
  exchange: orders.events
  routingKey: order.created
requiredHeaders:
  tenant-id: string
  event-version: integer
body:
  event: string
  orderId: string
optionalProperties:
  messageId: unique-event-id
  correlationId: workflow-id
~~~

Đây là mẫu hợp đồng nội bộ minh họa, không phải file cấu hình Spring Boot. Hãy xác định rõ trường bắt buộc, ý nghĩa khi thiếu, phiên bản schema và cách consumer bỏ qua trường chưa hiểu.

Một số nguyên tắc:

1. **Version hợp đồng tường minh.** Nếu event-version đổi từ 1 sang 2, consumer phải biết tương thích hay cần xử lý khác. Không thay đổi ý nghĩa trường âm thầm.
2. **Tránh khóa chặt vào kiểu Java.** Một số converter dùng headers kiểu dữ liệu của framework; hệ thống liên ngôn ngữ nên ưu tiên schema và kiểu wire được thỏa thuận.
3. **Giữ metadata nhỏ.** Message body hoặc kho dữ liệu phù hợp là nơi lưu payload lớn; headers lớn làm tăng băng thông, bộ nhớ và độ phức tạp xử lý.
4. **Không tin metadata từ producer một cách vô điều kiện.** tenant-id, role, region và thông tin định danh phải được kiểm tra theo quyền của kết nối/ngữ cảnh nghiệp vụ. Một header không tự tạo ra cơ chế xác thực hoặc phân quyền.
5. **Chuẩn hóa truy vết.** Log các ID phù hợp, quản lý cách truyền trace context, tránh log toàn bộ body và headers khi chúng có dữ liệu nhạy cảm.

## 9. Kết nối với routing, retry, dead-letter và độ tin cậy

| Tình huống | Metadata liên quan | Điều metadata **không** tự làm |
|---|---|---|
| Gửi OrderCreated tới đúng queue | exchange + routing key + binding; đôi khi headers exchange | Không tự tạo binding hoặc queue |
| Gửi JSON giữa hai microservice | body + contentType + contentEncoding + schema version | Không tự kiểm tra JSON hợp lệ |
| Theo dõi một workflow | messageId, correlationId, trace-id | Không bảo đảm message không trùng |
| Lưu message qua khởi động lại | deliveryMode và queue/topology durable cùng cơ chế broker | Không thay publisher confirms |
| Hết hạn một message | expiration hoặc queue TTL | Không phải timeout của xử lý nghiệp vụ |
| Chuyển message lỗi vào DLQ | DLX/DLQ policy/arguments, ack/nack/reject, metadata dead-letter | Header retry-attempt tự đặt không khiến broker retry |
| Gửi request và nhận reply | replyTo + correlationId và RPC/reply consumer | Không bảo đảm response được xử lý thành công |

Trong luồng xử lý bất đồng bộ đáng tin cậy, metadata chỉ là **dữ kiện đầu vào** cho chiến lược của hệ thống. Ví dụ, khi listener gặp lỗi payload:

~~~mermaid
flowchart TD
    A["Nhận delivery"] --> B{"Body / headers hợp lệ?"}
    B -->|Có| C["Thực hiện nghiệp vụ idempotent"]
    C --> D["Ack theo cấu hình listener"]
    B -->|Không| E["Áp dụng chính sách lỗi"]
    E --> F["Reject/nack, retry hoặc DLQ<br/>theo cấu hình thực tế"]
~~~

Việc exception dẫn tới retry, requeue hoặc dead-letter tùy listener container, error handler và cấu hình broker. Không có quy tắc “ném exception luôn đưa vào DLQ”. Khi thiết kế retry, cần phân biệt lỗi tạm thời (ví dụ dịch vụ phụ trợ không sẵn sàng) với lỗi vĩnh viễn (ví dụ schema không hợp lệ).

## 10. Bài tập thực hành và cách tự kiểm tra

**Bài tập A — Phân biệt các trường.** Với dữ liệu orderId=O-1001, routingKey=order.created, tenant-id=shop-vn, contentType=application/json và messageId=evt-001, hãy chỉ ra trường nào thuộc body, standard properties, application headers và publish envelope. Kết quả mong đợi: orderId trong body; contentType và messageId trong properties; tenant-id trong headers; routingKey trong envelope.

**Bài tập B — Thử nghiệm consumer.** Dùng publisher ở mục 6 gửi event, quan sát thông tin trong listener. Sau đó đổi contentType thành text/plain nhưng giữ body JSON. Listener mẫu sẽ từ chối trước khi parse, cho thấy converter hoặc consumer cần một hợp đồng đúng về nội dung. Khôi phục contentType sau thử nghiệm.

**Bài tập C — Thử phiên bản schema.** Đổi event-version từ 1 thành 2. Consumer mẫu sẽ từ chối vì chỉ chấp nhận phiên bản 1. Hãy đề xuất cách hỗ trợ cả hai phiên bản mà không làm sai ý nghĩa của payload.

**Bài tập D — Kiểm tra routing.** Giữ nguyên body/properties/headers nhưng đổi routing key từ order.created sang order.updated. Với topology chỉ có binding order.created, message không còn khớp binding hiện tại. Xem xét publisher returns/mandatory để phát hiện unroutable message thay vì suy diễn từ một lời gọi send không ném lỗi.

**Bài tập E — Phân tích redelivery.** Giả sử consumer đã ghi dữ liệu vào database nhưng chết trước ack, broker có thể giao lại message. Hãy xác định trường dùng để kiểm tra idempotency và lý do không sử dụng deliveryTag làm định danh nghiệp vụ.

## 11. Ghi nhớ khi triển khai Spring AMQP

- **Body là bytes của dữ liệu nghiệp vụ.** Thỏa thuận schema và encoding; contentType không thay thao tác serialize.
- **Properties là metadata chuẩn.** Dùng messageId, correlationId, deliveryMode, expiration, replyTo đúng mục đích và hiểu giới hạn của từng trường.
- **Application headers là key/value tùy biến.** Dùng cho context, version, tracing hoặc điều kiện của headers exchange; quản lý tên, kiểu và khả năng tương thích.
- **Exchange và routing key phục vụ định tuyến.** Chúng được truyền vào lệnh publish; direct/topic exchange không tự routing theo arbitrary headers.
- **RabbitTemplate.send gửi Message đã có bytes; convertAndSend dùng MessageConverter.** @RabbitListener có thể nhận Message hoặc dạng đã chuyển đổi.
- **Metadata không thay cơ chế độ tin cậy.** Publisher confirms, consumer ack, retry, DLQ, topology durable và idempotency cần được thiết kế riêng.

Khi biết một trường thuộc body, properties, headers hay publish envelope, bạn sẽ dễ đọc message trong RabbitMQ Management UI, debug vấn đề định tuyến và viết các consumer Spring AMQP ít phụ thuộc vào chi tiết của producer hơn.
