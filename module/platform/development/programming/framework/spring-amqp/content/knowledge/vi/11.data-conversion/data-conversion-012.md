# Tương thích JSON với producer hoặc consumer không dùng Spring

Khi một ứng dụng **Spring AMQP** trao đổi thông điệp với hệ thống viết bằng Node.js, Python, Go hoặc một nền tảng không dùng Spring, cả hai bên **không chia sẻ Java class, Jackson annotations hay Spring-specific headers**. Chúng chỉ nhìn thấy một AMQP message gồm **body dạng byte**, các **message properties** và **headers**, được RabbitMQ chuyển qua exchange, binding và queue.

Vì vậy, để trao đổi JSON an toàn, điều quan trọng không chỉ là “có dùng JSON converter hay không” mà là **hai phía đồng ý cùng một hợp đồng dữ liệu (wire contract)**: UTF-8, content type, cấu trúc JSON, kiểu dữ liệu, phiên bản schema, định danh sự kiện, cách báo lỗi và cách xác nhận xử lý.

Bài thuộc chương **Chuyển đổi dữ liệu** của module **SPRING_AMQP**. Ta sẽ dùng `RabbitTemplate` và `@RabbitListener` cùng một producer và consumer **Node.js không dùng Spring** để thực hành cả hai chiều. Các phần cuối liên hệ đến publisher confirms, acknowledgment, retry, dead-letter, giao dịch và quan sát hệ thống nhằm xây dựng luồng bất đồng bộ đáng tin cậy.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt **JSON body**, **AMQP properties**, **headers** và **routing key**.
2. Thiết kế hợp đồng JSON độc lập với ngôn ngữ lập trình và Java type headers.
3. Cấu hình JSON `MessageConverter` cho `RabbitTemplate` và `@RabbitListener`.
4. Cho **producer Node.js → consumer Spring AMQP** trao đổi dữ liệu mà Node.js không cần gửi `__TypeId__`.
5. Cho **producer Spring AMQP → consumer Node.js** đọc dữ liệu mà không cần hiểu lớp Java.
6. Kiểm tra các lỗi thường gặp: `content_type` sai, UTF-8, double encoding, field đổi tên, số lớn, version không tương thích, unroutable messages và poison messages.
7. Giải thích giới hạn của publisher confirm, consumer ack, retry/DLQ và idempotency khi vận hành hệ thống liên ngôn ngữ.

## 2. Thực sự có gì trên đường truyền?

Ở tầng AMQP 0-9-1, RabbitMQ chuyển **byte của message body** cùng **message properties**. Một phần metadata do producer đặt; broker còn có metadata riêng cho lần giao đến consumer.

~~~mermaid
flowchart LR
    N["Node.js producer<br/>amqplib"] -->|"UTF-8 JSON body<br/>content_type=application/json"| X["Direct exchange<br/>interop.events"]
    X -->|"routing key order.created"| S["Queue<br/>interop.orders.spring"]
    X -->|"routing key order.created"| J["Queue<br/>interop.orders.node"]
    S --> L["@RabbitListener<br/>Spring AMQP"]
    J --> C["Node.js consumer<br/>JSON.parse"]
    SP["Spring producer<br/>RabbitTemplate"] -->|"UTF-8 JSON body"| X
~~~

| Phần của message | Ví dụ | Ai sử dụng? |
|---|---|---|
| **Body** | `{"eventId":"evt-1001","orderId":"ORD-1001"}` ở dạng UTF-8 bytes | JSON parser/serializer của mỗi bên |
| **`content_type`** (AMQP property) | `application/json` | Thông báo kiểu payload; JSON converter có thể dựa vào đây |
| **`content_encoding`** (AMQP property) | `utf-8` | Gợi ý cách giải mã bytes thành văn bản |
| **`message_id`** (AMQP property) | `evt-1001` | Truy vết và hỗ trợ chống trùng theo hợp đồng |
| **Headers** (AMQP field table) | `event-type=order.created`, `schema-version=1` | Metadata bổ sung, lọc hoặc routing nếu dùng headers exchange |
| **Exchange + routing key** | `interop.events` + `order.created` | RabbitMQ đối chiếu binding để đưa message tới queue |
| **Delivery metadata** | delivery tag, redelivered, consumer tag | Consumer dùng để xác nhận/quan sát lần giao, không nằm trong JSON body |

`content_type` **không làm JSON tự động hợp lệ**: một producer vẫn có thể khai báo `application/json` nhưng gửi bytes không parse được. Ngược lại, payload JSON hợp lệ mà không có content type phù hợp có thể không được converter nhận đúng tùy cấu hình thư viện.

Tương thích liên ngôn ngữ nghĩa là cả producer và consumer thống nhất **dữ liệu trên wire**. Không truyền trực tiếp đối tượng Java serialized qua ObjectOutputStream rồi kỳ vọng Node.js có thể giải mã, cũng không đặt Java class name làm một phần bắt buộc của hợp đồng bên ngoài.

## 3. Thiết kế JSON contract trước khi viết converter

Ví dụ sự kiện `OrderCreated` sử dụng một JSON object rõ ràng:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-1001",
  "orderId": "ORD-1001",
  "occurredAt": "2026-11-26T08:00:00Z",
  "amountMinorUnits": "125000",
  "currency": "VND"
}
~~~

### Các quy tắc cho hợp đồng liên ngôn ngữ

| Quy tắc | Lý do | Ví dụ |
|---|---|---|
| UTF-8, JSON object ở cấp cao nhất | Các nền tảng dễ giải mã thống nhất | Body là bytes của `{"eventId":"..."}` |
| Tên field ổn định, phân biệt chữ hoa/thường | JSON keys case-sensitive | `orderId` không tự tương đương `order_id` |
| `schemaVersion` là số nguyên rõ ràng | Cho phép nâng cấp contract có kiểm soát | `1`, không nhập nhằng `"1"` |
| `eventId` được giữ ổn định khi retry | Giúp consumer phát hiện xử lý trùng | `evt-1001` giữ nguyên sau publish retry |
| Thời gian theo ISO 8601 có timezone | Tránh sai lệch múi giờ / format | `2026-11-26T08:00:00Z` |
| Tiền và số lớn có biểu diễn được thỏa thuận | JavaScript `Number` không biểu diễn chính xác mọi số nguyên lớn | `amountMinorUnits` là chuỗi thập phân; validate trước khi tính toán |
| Field mới phải tương thích có chủ đích | Consumer cũ có thể không biết trường mới | Thêm field tùy chọn với default/ignore-unknown phù hợp |
| Không mặc định Java class name là schema | Node.js/Python không biết package của JVM | Contract là JSON + version, không phải `com.example.OrderCreated` |

**Tại sao `amountMinorUnits` là chuỗi?** Nếu một event có số nguyên vượt quá giới hạn chính xác của JavaScript Number (2^53 − 1), chuyển một số JSON lớn sang `Number` có thể làm mất chữ số. Có thể dùng số JSON khi hai phía bảo đảm miền giá trị nằm trong ngưỡng an toàn, hoặc quy ước chuỗi số thập phân và sử dụng kiểu `BigDecimal`/`BigInt` khi cần.

Sự kiện đi qua RabbitMQ thường là **event**, không phải lời gọi RPC đồng bộ. Không nên giả định client gửi xong có nghĩa một nghiệp vụ đã hoàn tất; cần trạng thái nghiệp vụ, tracing và acknowledgment riêng.

### Phân biệt field trong JSON với AMQP headers

~~~text
AMQP message
├─ body: UTF-8 JSON {"schemaVersion":1, "eventId":"evt-1001", ...}
├─ properties
│  ├─ content_type: "application/json"
│  ├─ content_encoding: "utf-8"
│  ├─ message_id: "evt-1001"
│  └─ delivery_mode: persistent
└─ headers
   ├─ event-type: "order.created"
   └─ schema-version: 1
~~~

Body và headers có thể chứa một số thông tin trùng nhau phục vụ mục đích khác nhau. Nếu lưu `schemaVersion` ở cả hai nơi, **phải định nghĩa rõ nguồn sự thật và kiểm tra tính nhất quán**, không tin một bên một cách mù quáng. Trong ví dụ này, consumer dùng `schemaVersion` trong **body** làm phiên bản hợp đồng.

## 4. Khởi tạo RabbitMQ và ứng dụng Spring

### 4.1. Broker và thông tin kết nối

Trong môi trường lab, có thể chạy RabbitMQ kèm Management:

~~~bash
docker run -d --name rabbitmq-interop-lab -p 127.0.0.1:5672:5672 -p 127.0.0.1:15672:15672 -e RABBITMQ_DEFAULT_USER=lab -e RABBITMQ_DEFAULT_PASS=lab123456 rabbitmq:4-management
~~~

RabbitMQ sử dụng AMQP trên cổng **5672**; Management thường truy cập tại **http://localhost:15672**. Tài khoản `lab/lab123456` chỉ dành cho máy học tập. Nếu máy có RabbitMQ trên cổng tương ứng, dùng broker hiện có hoặc đổi cổng, tránh tạo hai container trùng port. Trong triển khai thật, dùng secrets, TLS, quyền vhost tối thiểu và không công khai Management.

### 4.2. Dependency và phiên bản converter

Các ví dụ Java phía dưới nhắm tới **Spring Boot 3.x / Spring AMQP 3.x**, dùng Java 17+ và **Jackson 2**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-json</artifactId>
    </dependency>
</dependencies>
~~~

Trong dòng **Spring AMQP 3.x**, converter được minh họa là `Jackson2JsonMessageConverter`. Các dòng Spring AMQP mới dùng Jackson 3 có **`JacksonJsonMessageConverter`** và kiểu mapper/import tương ứng. **Không trộn API Jackson 2 và Jackson 3 giữa các dòng phiên bản**; hãy chọn converter phù hợp với phiên bản framework thực tế trước khi sao chép cấu hình.

`src/main/resources/application.yml`:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: lab
    password: lab123456
    listener:
      simple:
        acknowledge-mode: auto
        default-requeue-rejected: false
~~~

`default-requeue-rejected: false` trong lab giúp lỗi từ listener **không bị requeue vô hạn** khi bị reject theo đường xử lý thông thường. Ví dụ dưới sẽ khai báo dead-letter exchange (DLX) cho các queue. Trong production, cần thiết kế retry có backoff và phân loại lỗi tạm thời/lỗi dữ liệu trước khi áp dụng một chính sách chung.

## 5. Topology chung cho producer/consumer nhiều nền tảng

Ta chọn **DirectExchange** `interop.events` và routing key `order.created`. Hai queue cùng được bind bằng key này:

- `interop.orders.spring` để consumer Spring nhận.
- `interop.orders.node` để consumer Node.js nhận.

Nhờ là **hai queue khác nhau**, mỗi lần publish khớp binding sẽ có một bản sao cho mỗi queue. Nếu cả hai consumer đọc cùng **một** queue thì chúng chia việc, không cùng nhận từng message.

Thêm `interop.dlx` và `interop.invalid` để tách message bị reject không requeue:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InteropTopology {

    @Bean
    DirectExchange interopEventsExchange() {
        return new DirectExchange("interop.events", true, false);
    }

    @Bean
    DirectExchange interopDlx() {
        return new DirectExchange("interop.dlx", true, false);
    }

    @Bean
    Queue springQueue() {
        return QueueBuilder.durable("interop.orders.spring")
                .deadLetterExchange("interop.dlx")
                .deadLetterRoutingKey("invalid")
                .build();
    }

    @Bean
    Queue nodeQueue() {
        return QueueBuilder.durable("interop.orders.node")
                .deadLetterExchange("interop.dlx")
                .deadLetterRoutingKey("invalid")
                .build();
    }

    @Bean
    Queue invalidQueue() {
        return QueueBuilder.durable("interop.invalid").build();
    }

    @Bean
    Binding springBinding(
            @Qualifier("springQueue") Queue queue,
            @Qualifier("interopEventsExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange)
                .with("order.created");
    }

    @Bean
    Binding nodeBinding(
            @Qualifier("nodeQueue") Queue queue,
            @Qualifier("interopEventsExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange)
                .with("order.created");
    }

    @Bean
    Binding invalidBinding(
            @Qualifier("invalidQueue") Queue queue,
            @Qualifier("interopDlx") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange)
                .with("invalid");
    }
}
~~~

Spring AMQP có thể khai báo exchange, queue và binding qua `RabbitAdmin` khi ứng dụng kết nối. Hãy **khởi động ứng dụng Spring trước** để topology tồn tại rồi mới chạy ví dụ Node.js. Khi queue đã được tạo, đừng khai báo lại queue với arguments khác (đặc biệt là DLX), vì RabbitMQ có thể báo lỗi **inequivalent arg** và đóng channel.

## 6. Producer Node.js → consumer Spring AMQP

### 6.1. Spring deserialization từ JSON vào DTO cụ thể

Khi `@RabbitListener` nhận một tham số có kiểu rõ ràng, converter Jackson của Spring AMQP có thể sử dụng kiểu đó làm **kiểu đích suy luận (inferred type)**. Vì vậy **producer không dùng Spring không cần biết tên Java class hoặc gửi `__TypeId__`** chỉ để listener nhận được một record cụ thể.

Khai báo converter cho Spring Boot 3.x / Spring AMQP 3.x:

~~~java
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InteropJsonConfig {

    @Bean
    MessageConverter amqpJsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }
}
~~~

Trong ứng dụng dùng Spring Boot auto-configuration thông thường, bean `MessageConverter` của AMQP được áp dụng cho `RabbitTemplate` và listener container factory. Nếu bạn tự tạo `RabbitTemplate` hoặc `SimpleRabbitListenerContainerFactory` riêng, **phải gắn converter vào đúng bean thực sự sử dụng**; có bean converter trong context chưa đủ nếu factory tùy chỉnh bỏ qua nó.

Định nghĩa DTO:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderCreated(
        int schemaVersion,
        String eventId,
        String orderId,
        String occurredAt,
        String amountMinorUnits,
        String currency) {
}
~~~

`@JsonIgnoreProperties(ignoreUnknown = true)` cho phép consumer phiên bản cũ **bỏ qua field bổ sung** của producer mới khi hợp đồng cho phép. Nó **không thay thế validation**: field bắt buộc thiếu vẫn có thể ánh xạ thành `null` hoặc giá trị mặc định (như `int` thành 0) nếu không được kiểm tra.

Consumer:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class SpringOrderConsumer {
    private static final Logger log =
            LoggerFactory.getLogger(SpringOrderConsumer.class);

    @RabbitListener(queues = "interop.orders.spring")
    public void handle(OrderCreated event) {
        if (event.schemaVersion() != 1
                || event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()) {
            throw new IllegalArgumentException("Unsupported/invalid event");
        }

        // Thực tế: xác thực/kiểm tra trường dữ liệu còn lại và
        // xử lý idempotent theo event.eventId() trước khi ACK.
        log.info("Spring received eventId={}, orderId={}, currency={}",
                event.eventId(), event.orderId(), event.currency());
    }
}
~~~

Với `acknowledge-mode: auto` của **Spring AMQP listener container**, message thường được ACK **sau khi listener trả về thành công**. Khi listener ném exception, hành vi reject/requeue/dead-letter còn phụ thuộc cấu hình; không đồng nhất với `noAck=true` của RabbitMQ client.

### 6.2. Node.js gửi JSON không có Spring type headers

Đặt mã vào `node-producer.cjs` của dự án thử nghiệm Node.js, cài `amqplib` bằng `npm install amqplib`. Chạy bằng `node node-producer.cjs` sau khi ứng dụng Spring khai báo topology.

~~~javascript
const amqp = require("amqplib");
const { randomUUID } = require("node:crypto");

async function main() {
  const connection =
      await amqp.connect("amqp://lab:lab123456@localhost:5672");
  const channel = await connection.createConfirmChannel();
  let returned = false;

  channel.on("return", (msg) => {
    returned = true;
    console.error("Unroutable:", msg.fields.routingKey);
  });

  try {
    const event = {
      schemaVersion: 1,
      eventId: randomUUID(),
      orderId: "ORD-NODE-1001",
      occurredAt: new Date().toISOString(),
      amountMinorUnits: "125000",
      currency: "VND"
    };

    const body = Buffer.from(JSON.stringify(event), "utf8");

    const writable = channel.publish(
      "interop.events",
      "order.created",
      body,
      {
        contentType: "application/json",
        contentEncoding: "utf-8",
        deliveryMode: 2,
        messageId: event.eventId,
        headers: {
          "event-type": "order.created",
          "schema-version": event.schemaVersion
        },
        mandatory: true
      }
    );

    if (!writable) {
      console.warn("Publish buffer đầy: cần backpressure khi tải lớn");
    }

    await channel.waitForConfirms();
    if (returned) {
      throw new Error("Broker returned an unroutable message");
    }
    console.log("Broker confirmed publication:", event.eventId);
  } finally {
    await channel.close();
    await connection.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
~~~

Chú ý:

- `Buffer.from(JSON.stringify(event), "utf8")` tạo **bytes JSON thật**, không phải Java object serialization.
- `contentType`, `contentEncoding` và `messageId` trong `amqplib` được chuyển thành AMQP properties. **Không đặt `contentType` trong `headers` rồi hy vọng JSON converter tự đọc**.
- `deliveryMode: 2` yêu cầu persistent message; để tăng độ bền còn cần durable queue, publisher confirms và cấu hình broker phù hợp.
- `createConfirmChannel()` + `waitForConfirms()` giúp biết broker ACK/NACK ở mức publication. Cờ `mandatory` và sự kiện `return` giúp nhận biết message không có queue phù hợp. Trong ví dụ gửi một message, boolean `returned` đủ để minh họa; hệ thống publish đồng thời cần **tương quan return/confirm theo từng message**.
- Giá trị `writable=false` của `channel.publish()` biểu thị **backpressure của buffer**, không phải NACK từ broker. Trong production phải chờ cơ chế `drain`/điều tiết tải thay vì chỉ log cảnh báo.

Nếu `@RabbitListener` nhận `OrderCreated` đúng contract, log Spring sẽ chứa `ORD-NODE-1001`. Node.js không gửi `__TypeId__` mà listener vẫn có thể deserialize do **kiểu tham số cụ thể** đã được suy luận, với converter được cấu hình phù hợp.

## 7. Producer Spring AMQP → consumer Node.js

### 7.1. Cách thông thường: `RabbitTemplate.convertAndSend`

Khi đã có JSON converter, Spring có thể serialize DTO:

~~~java
rabbitTemplate.convertAndSend(
        "interop.events", "order.created", orderCreated);
~~~

Body trên wire là JSON. Một số converter Spring AMQP có thể tự thêm header kiểu như **`__TypeId__`** (và các header kiểu container liên quan) để hỗ trợ **Spring-to-Spring** chuyển kiểu Java. Consumer Node.js **không cần** và **không nên phụ thuộc** vào Java class name đó: chỉ cần đọc body JSON, content type và contract.

Nếu bên nhận không dùng Spring hoặc muốn kiểm soát **chính xác byte/properties** được gửi mà không kèm header phụ thuộc framework, có thể publish **raw AMQP Message** như phần dưới.

### 7.2. Producer tạo JSON raw, không cần Java type header

Spring Boot 3.x và Jackson 2:

~~~java
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class PortableOrderPublisher {
    private final RabbitTemplate rabbitTemplate;
    private final ObjectMapper objectMapper;

    public PortableOrderPublisher(RabbitTemplate rabbitTemplate,
                                  ObjectMapper objectMapper) {
        this.rabbitTemplate = rabbitTemplate;
        this.objectMapper = objectMapper;
    }

    public void send(OrderCreated event) throws JsonProcessingException {
        byte[] body = objectMapper.writeValueAsBytes(event);

        MessageProperties properties = new MessageProperties();
        properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
        properties.setContentEncoding(StandardCharsets.UTF_8.name());
        properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        properties.setMessageId(event.eventId());
        properties.setHeader("event-type", "order.created");
        properties.setHeader("schema-version", event.schemaVersion());

        rabbitTemplate.send(
                "interop.events",
                "order.created",
                new Message(body, properties));
    }
}
~~~

`send(exchange, routingKey, Message)` gửi bytes và message properties do bạn cung cấp, thay vì yêu cầu converter tự chọn kiểu payload. `ObjectMapper.writeValueAsBytes` tránh lỗi tự nối chuỗi JSON hoặc double encoding. Khi bên nhận chỉ cần JSON, đây là cách làm rõ **hợp đồng độc lập với Java type headers**.

Để thử, gọi `PortableOrderPublisher.send(...)` từ một tác vụ hoặc endpoint của ứng dụng. Ví dụ tạo event:

~~~java
OrderCreated event = new OrderCreated(
        1,
        java.util.UUID.randomUUID().toString(),
        "ORD-SPRING-1001",
        java.time.Instant.now().toString(),
        "125000",
        "VND");

portableOrderPublisher.send(event);
~~~

Đoạn trên là ví dụ cách gọi từ **một bean/component có `PortableOrderPublisher` được inject**, không phải mã chạy độc lập ở cấp file. Nếu chạy khi startup, nhớ rằng khởi động lại sẽ có thể phát event mới.

### 7.3. Node.js consumer dùng `JSON.parse`

Đặt vào `node-consumer.cjs`, cài `amqplib` rồi chạy bằng `node node-consumer.cjs`. Vì topology đã khai báo hai queue, Node.js chỉ consume **`interop.orders.node`**; Spring vẫn consume queue của riêng mình.

~~~javascript
const amqp = require("amqplib");

async function main() {
  const connection =
      await amqp.connect("amqp://lab:lab123456@localhost:5672");
  const channel = await connection.createChannel();
  await channel.prefetch(5);

  await channel.consume(
    "interop.orders.node",
    async (message) => {
      if (message === null) return;

      try {
        if (message.properties.contentType !== "application/json") {
          throw new Error("Unexpected content type");
        }

        const event = JSON.parse(message.content.toString("utf8"));

        if (event.schemaVersion !== 1 ||
            typeof event.eventId !== "string" ||
            typeof event.orderId !== "string" ||
            typeof event.amountMinorUnits !== "string") {
          throw new Error("Invalid event schema");
        }

        console.log("Node consumer:", event.eventId, event.orderId);

        // Production: ghi kết quả nghiệp vụ và đánh dấu eventId đã xử lý
        // bền vững, theo chiến lược idempotency, trước khi ACK.
        channel.ack(message);
      } catch (error) {
        console.error("Invalid or failed message:", error);
        // Không requeue: trong topology lab, message sẽ vào interop.invalid.
        channel.nack(message, false, false);
      }
    },
    { noAck: false }
  );

  console.log("Waiting on interop.orders.node");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
~~~

Node.js không cần biết `OrderCreated` là Java record, cũng không cần phân tích `__TypeId__`. Nó chỉ giải mã UTF-8, kiểm tra `contentType` và parse JSON theo contract. Nếu nhận dữ liệu lỗi, ví dụ dùng `nack(requeue=false)`; với DLX/binding ở mục 5, message có thể vào `interop.invalid` để điều tra. Trong production cần **phân biệt lỗi dữ liệu vĩnh viễn với lỗi tạm thời**; không nên đẩy mọi lỗi mạng/database sang DLQ ngay lần đầu.

Một message được publish vào `interop.events` có thể đến **cả hai queue** vì cả hai binding đều khớp. Điều này khác với hai consumer cạnh tranh đọc **cùng một queue**.

## 8. Thử nghiệm hai chiều và cách quan sát

Thứ tự thực hành:

1. Khởi động RabbitMQ, sau đó ứng dụng Spring Boot có `InteropTopology`, converter và listener.
2. Mở **RabbitMQ Management → Exchanges**, kiểm tra `interop.events` có kiểu `direct` và hai bindings cùng routing key `order.created`.
3. Kiểm tra **Queues and Streams** có `interop.orders.spring`, `interop.orders.node` và `interop.invalid`. Khi consumer Node chưa chạy, `interop.orders.node` giữ các message phù hợp ở **Ready**.
4. Chạy `node-producer.cjs`. Spring listener phải nhận JSON với event ID của Node; message đồng thời vào queue dành cho Node.
5. Khởi động `node-consumer.cjs` để xử lý các message đang chờ trên queue Node.
6. Từ ứng dụng Spring, gọi `PortableOrderPublisher.send(...)`. Kiểm tra log Node và Spring có cùng `eventId`, nhưng xử lý ở **hai queue riêng**.
7. Cố tình gửi JSON sai hoặc schemaVersion không hỗ trợ. Kiểm tra log lỗi và `interop.invalid`. Khi xem payload bằng **Get messages** trên UI, nhớ thao tác này có chế độ ACK/requeue và có thể thay đổi trạng thái message.

| Hướng gửi | Producer | Consumer | Kết quả mong đợi |
|---|---|---|---|
| Node → Spring | `JSON.stringify` + `Buffer` + AMQP properties | `@RabbitListener(OrderCreated)` | Spring deserialize DTO, không cần `__TypeId__` từ Node |
| Spring → Node | `ObjectMapper.writeValueAsBytes` + `RabbitTemplate.send` | `JSON.parse` trên buffer | Node đọc object theo JSON contract, không biết Java class |
| Spring → Node (converter) | `RabbitTemplate.convertAndSend` | `JSON.parse` | Node đọc body, bỏ qua Spring-specific type headers nếu có |
| Message JSON sai | Bất kỳ producer | Consumer / error handler | Reject theo chính sách, có thể dead-letter; không được requeue nóng vô hạn |
| Routing key sai | Bất kỳ producer | Không có queue phù hợp | Message có thể unroutable; cần publisher return/metrics để phát hiện |

**Giới hạn của snapshot Management:** `Ready=0` không chứng minh message đã được xử lý nghiệp vụ thành công; nó có thể đang `Unacked`, đã được ACK, đã chết ở DLQ hoặc đi sang queue khác. Dùng `eventId` và log của producer/consumer để theo dõi từng sự kiện.

## 9. Những lỗi tương thích thường gặp

| Triệu chứng | Nguyên nhân điển hình | Cách xử lý |
|---|---|---|
| Spring listener không convert body thành DTO | Chưa cấu hình JSON converter; factory thực tế không dùng converter; content type không phù hợp | Kiểm tra `MessageConverter` của `RabbitTemplate` và listener container factory, kiểm tra AMQP properties |
| Node nhận chuỗi JSON thay vì object | Đã `JSON.stringify` hai lần | Chỉ stringify đúng một lần; dùng `Buffer.from(JSON.stringify(object), "utf8")` |
| Body parse lỗi, hiển thị ký tự lạ | Encoding khác UTF-8, bytes bị biến đổi hoặc JSON không hợp lệ | Dùng UTF-8 ở cả hai bên, kiểm tra body bytes/`content_encoding` |
| Java DTO nhận `null` hoặc giá trị mặc định | Field name khác nhau, thiếu field hoặc khác kiểu | Chốt schema, validate required fields; không chỉ dựa vào constructor |
| Field mới làm consumer cũ lỗi | Consumer strict với unknown properties | Quy định backward compatibility; có thể bỏ qua field không nhận biết khi an toàn |
| Một số tiền hoặc ID bị đổi chữ số ở Node | JSON number vượt safe integer range | Dùng chuỗi thập phân hoặc số trong miền an toàn và kiểu số phù hợp |
| Node không hiểu `__TypeId__` | Đây là Spring type metadata, không phải contract JSON chung | Bỏ qua type headers ở Node; dùng body+schemaVersion |
| Java không deserialize được khi thiếu `__TypeId__` | Listener không có inferred concrete type hoặc cấu hình type mapper khác | Dùng listener tham số DTO cụ thể; nếu cần polymorphic, dùng mapping được kiểm soát |
| Spring startup báo `PRECONDITION_FAILED inequivalent arg` | Hai client khai báo cùng queue nhưng khác arguments | Một nơi sở hữu topology; đồng bộ durable, DLX, TTL và policy |
| Publish được nhưng consumer không nhận | Sai exchange, routing key, binding, vhost hoặc consumer chưa chạy | Kiểm tra bindings, Ready/Unacked và consumer count; bật mandatory/returns |
| Poison message cứ giao lại | Validation/JSON conversion lỗi và requeue không giới hạn | Phân loại lỗi; retry có giới hạn, backoff và DLQ |

### Đừng sử dụng Java type headers làm hợp đồng bên ngoài

`Jackson2JsonMessageConverter` và các cơ chế mapping kiểu của Spring có thể sử dụng các header như **`__TypeId__`**, **`__ContentTypeId__`**, **`__KeyTypeId__`** để diễn đạt thông tin kiểu Java khi chuyển dữ liệu Spring-to-Spring. Một publisher không dùng Spring **không bắt buộc tạo các header đó** nếu consumer có kiểu đích được suy luận phù hợp.

Khi consumer nhận dữ liệu từ bên ngoài, **không tự động tin class name do người gửi đưa vào header** và không mở rộng danh sách trusted packages vô hạn để “sửa nhanh” lỗi convert. Nếu cần polymorphism, xây một **registry mapping từ loại sự kiện được phép** sang DTO đã được kiểm soát, validate schema/version và giới hạn kiểu dữ liệu được tạo.

## 10. Versioning và kiểm thử contract

Một schema bền vững không thể chỉ phụ thuộc vào việc deserialize thành công ở hôm nay. Cần quy tắc thay đổi có kiểm soát:

| Thay đổi | Tác động có thể xảy ra | Chiến lược |
|---|---|---|
| Thêm field tùy chọn | Consumer cũ strict có thể báo unknown field | Cho phép ignore unknown nếu phù hợp; dùng default rõ ràng |
| Đổi tên `orderId` thành `id` | Consumer cũ thiếu required field | Giữ tên cũ hoặc hỗ trợ alias/phiên bản mới có lộ trình |
| Đổi `amountMinorUnits` từ string sang number | Mất chính xác hoặc lỗi kiểu ở hai phía | Tránh đổi kiểu trong cùng version; migration có kiểm thử |
| Đổi ngữ nghĩa một enum/string | Consumer xử lý sai dù parse JSON hợp lệ | Version contract và kiểm tra unknown values |
| Thêm field bắt buộc | Producer cũ không gửi được | Dùng default có kiểm soát hoặc phát hành version mới |
| Đổi cấu trúc lồng nhau | Deserialization có thể thất bại | Tạo contract mới, consumer hỗ trợ song song khi rollout |

Nên có **contract tests** kiểm tra bytes JSON thật, không chỉ Java object qua cùng mapper:

1. Fixture do **Node producer** tạo phải deserialize được trong **Spring listener** và đủ tất cả field bắt buộc.
2. Fixture do **Spring producer** tạo phải `JSON.parse` được trong **Node consumer**, không yêu cầu Java-specific headers.
3. Kiểm tra các trường hợp thiếu `eventId`, sai kiểu `schemaVersion`, timestamp lỗi, thêm field mới, chuỗi Unicode và số lớn.
4. Kiểm tra một message JSON không hợp lệ có đường xử lý lỗi rõ, không gây requeue vô hạn.
5. Kiểm tra message sai routing key được phát hiện qua publisher returns hoặc cơ chế giám sát, không bị coi là thành công chỉ vì lệnh gửi kết thúc.

Khi nâng cấp producer trước consumer hoặc ngược lại, ưu tiên chiến lược **expand → migrate → contract**: thêm field hỗ trợ trước, chuyển dần các consumer/producers, rồi loại bỏ field cũ sau khi xác minh không còn bên nào cần. Ghi `schemaVersion` trong payload giúp các bên xác định phiên bản mà không phụ thuộc Spring.

## 11. Độ tin cậy và bảo mật khi xử lý JSON bên ngoài

### 11.1. Publish thành công không phải tiêu thụ thành công

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Producer
    participant B as RabbitMQ broker
    participant C as Consumer
    P->>B: Publish JSON event
    B-->>P: Publisher confirm ACK/NACK
    Note over P,B: ACK publisher không đồng nghĩa consumer đã xử lý
    B->>C: Deliver message
    C->>C: Validate, idempotency, business commit
    C-->>B: Consumer ACK hoặc NACK
~~~

Phân biệt rõ:

- **Publisher confirm:** broker xác nhận publication ở mức giao thức publish; không chứng minh listener đã hoàn tất nghiệp vụ.
- **Publisher return:** với mandatory/returns phù hợp, producer nhận biết message không có queue đích; broker vẫn có thể ACK publication không định tuyến được.
- **Consumer acknowledgment:** consumer xác nhận delivery đã nhận/xử lý theo chế độ; không tự biến việc cập nhật database thành một transaction nguyên tử với RabbitMQ.
- **Kết quả nghiệp vụ:** trạng thái được ghi và kiểm tra trong hệ thống của consumer. Đây mới là tín hiệu quyết định một đơn đã xử lý hay chưa.

### 11.2. Chống mất và trùng sự kiện

Khi Node hoặc Spring producer timeout chờ publisher confirm, message **có thể đã vào queue dù producer chưa nhìn thấy ACK**. Retry có thể tạo bản sao. Consumer của cả hai phía nên áp dụng **idempotency** theo `eventId`: ghi nhận và kiểm tra event đã xử lý trong kho lưu trữ bền vững, kết hợp ràng buộc duy nhất hoặc transaction nghiệp vụ phù hợp. `redelivered=false` không chứng minh đây là event mới.

Nếu việc ghi database và phát message cần nhất quán, Spring service có thể dùng **transactional outbox**: lưu entity và event outbox trong cùng DB transaction, rồi publisher gửi theo job và cập nhật trạng thái sau confirm/return. Điều này khác với việc bật AMQP transaction đơn lẻ.

### 11.3. JSON từ đối tác là dữ liệu không tin cậy

- Giới hạn kích thước message và nesting depth thích hợp; JSON cực lớn hoặc lồng sâu có thể tiêu thụ bộ nhớ/CPU.
- Validate schema, required fields, length/format của ID, giá trị tiền, timestamp và trạng thái enum **trước** khi tạo side effect.
- Không deserialize thành lớp Java tùy ý dựa trên một header type do người gửi kiểm soát.
- Không ghi thẳng toàn bộ payload nhạy cảm vào log; log `eventId`, `schemaVersion`, queue, loại lỗi và correlation ID là chính.
- Cấu hình quyền publish/consume tối thiểu theo RabbitMQ vhost/exchange/queue; dùng TLS và secrets cho môi trường thật.
- Phân biệt **poison message** (JSON/schema sai, thường không nên requeue) với lỗi hạ tầng tạm thời (có thể retry có backoff và giới hạn).

DLQ là một kênh **điều tra và xử lý lại có kiểm soát**, không phải nơi lưu vô hạn tất cả message lỗi. Nếu consumer Node.js hoặc Spring reject message không requeue nhưng queue chưa cấu hình DLX phù hợp, message có thể bị loại bỏ. Cần kiểm chứng DLX và policy ngay từ giai đoạn tích hợp.

## 12. Bài tập thực hành

**Bài tập A — Node không gửi Spring type headers.** Chạy `node-producer.cjs` và xem log `SpringOrderConsumer`. Kiểm tra `eventId` và `schemaVersion` được nhận đúng. Giải thích vì sao `@RabbitListener(OrderCreated)` có thể deserialize khi không có `__TypeId__`.

**Bài tập B — Spring gửi JSON thuần.** Dùng `PortableOrderPublisher.send(...)`, cho `node-consumer.cjs` nhận và in `eventId`. Kiểm tra AMQP properties `content_type` và `message_id` trong Management; xác nhận Node không cần class Java.

**Bài tập C — Đổi kiểu dữ liệu.** Cho Node gửi `amountMinorUnits` là số JSON lớn hơn 2^53 − 1 thay vì chuỗi. So sánh nguy cơ sai số và đề xuất contract không làm mất độ chính xác giữa Java và JavaScript.

**Bài tập D — Poison message.** Gửi chuỗi không phải JSON nhưng khai `contentType=application/json`. Quan sát xử lý lỗi của converter/consumer và `interop.invalid`. Không dùng requeue vô hạn. Ghi lại lý do lỗi và phương án khôi phục có kiểm soát.

**Bài tập E — Sai routing key.** Gửi JSON hợp lệ vào `interop.events` với `order.unknown` và bật `mandatory`/returns. So sánh publisher confirm với trạng thái queue; giải thích vì sao “đã publish” không đủ để xác minh “đã đến đúng queue”.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Producer Node.js có phải gửi header `__TypeId__=com.example.OrderCreated` để Spring listener nhận được record `OrderCreated` không?

**Đáp án:** Không nhất thiết. Với JSON converter phù hợp và tham số listener có kiểu cụ thể, Spring có thể suy luận kiểu đích từ chữ ký phương thức. Header tên class Java không nên là hợp đồng bắt buộc giữa các ngôn ngữ.

**Câu 2.** Body chứa JSON hợp lệ nhưng `content_type=text/plain`. Có nên giả định Spring luôn parse nó thành DTO?

**Đáp án:** Không. Hành vi phụ thuộc converter và cấu hình/phiên bản. Producer nên đặt đúng `application/json` và consumer phải kiểm tra đường decode đã chọn.

**Câu 3.** Hai consumer Spring và Node.js cùng nhận một message từ cùng exchange bằng cách nào?

**Đáp án:** Tạo **hai queue khác nhau** có binding phù hợp từ cùng exchange. Hai consumer cùng một queue thường chia việc, không mỗi bên nhận một bản sao.

**Câu 4.** `confirm ACK` từ broker có chứng minh Node consumer đã commit database không?

**Đáp án:** Không. Nó xác nhận publication ở phía producer/broker; consumer ACK và kết quả nghiệp vụ là các mốc độc lập.

**Câu 5.** Nếu `JSON.parse` lỗi, nên `nack(requeue=true)` mãi cho đến khi parse được?

**Đáp án:** Không. JSON lỗi cố định không tự sửa qua retry. Nên reject không requeue rồi đưa vào DLQ phù hợp, ghi lý do và có quy trình sửa/replay an toàn.

**Câu 6.** Vì sao `eventId` không nên thay đổi khi producer retry cùng một sự kiện?

**Đáp án:** Giữ ID ổn định cho phép consumer nhận diện cùng công việc và thực hiện idempotency; ID đổi sau mỗi lần retry có thể làm cùng một nghiệp vụ bị thực hiện nhiều lần.

## 14. Ghi nhớ

- **Hợp đồng JSON trên wire** gồm UTF-8 body, `content_type=application/json`, tên/kiểu field, `schemaVersion`, `eventId` và quy ước lỗi; **không phụ thuộc Java class name**.
- **Node.js/Python → Spring AMQP:** dùng JSON converter và `@RabbitListener` nhận DTO cụ thể; khi kiểu đích có thể suy luận, producer ngoài Spring không cần gửi `__TypeId__`.
- **Spring AMQP → Node.js/Python:** dùng `RabbitTemplate.convertAndSend` với converter JSON hoặc gửi `Message` raw có content type, encoding và byte JSON chuẩn; consumer ngoài Spring giải mã theo contract.
- **Tương thích dữ liệu không tự bảo đảm giao nhận**. Hệ thống vẫn cần exchange/binding đúng, publisher confirms/returns, consumer ack, retry/DLQ, idempotency, giao dịch/outbox, bảo mật và giám sát.
