# Đặt correlation ID và địa chỉ trả lời khi gửi thông điệp JMS

## 1. Bài toán: ai trả lời, và trả lời cho yêu cầu nào?

Trong JMS / Jakarta Messaging, gửi một message tới queue chỉ xác định được **địa chỉ đích của request**. Với các luồng request–reply, bên yêu cầu còn cần hai thông tin: **nơi nhận phản hồi** và **định danh để ghép phản hồi với đúng yêu cầu**. Hai JMS header tiêu chuẩn phục vụ việc này:

- **`JMSReplyTo`** chứa một đối tượng `jakarta.jms.Destination`: queue hoặc topic mà bên nhận nên gửi reply về.
- **`JMSCorrelationID`** chứa khóa tương quan: chuỗi dùng để liên hệ các message, phổ biến nhất là liên kết response với request.

Vì message có thể đến khác thứ tự, bị redeliver, hết hạn hoặc được xử lý bởi nhiều consumer, hai header này không thể thay thế cho nhau.

~~~text
Requester A                              Broker / Request queue                   Worker B
   │                                              │                                  │
   │  request body="order-42"                    │                                  │
   │  JMSReplyTo=reply-A                          │                                  │
   │  JMSCorrelationID=req-42                     │                                  │
   ├─────────────────────────────────────────────>│─────────────────────────────────>│
   │                                              │                         đọc JMSReplyTo
   │                                              │                         xử lý request
   │                                              │<─────────────────────────────────┤
   │                                              │  response body="ACK:order-42"   │
   │                                              │  JMSCorrelationID=req-42        │
   │<────────────────── reply-A ──────────────────│                                  │
   │  kiểm tra correlation ID                    │                                  │
~~~

**Điểm cốt lõi:**

1. `JMSReplyTo` trả lời câu hỏi **gửi kết quả đến đâu**.
2. `JMSCorrelationID` trả lời câu hỏi **kết quả này thuộc yêu cầu nào**.
3. Không có header nào tự biến JMS thành RPC bảo đảm thành công: ứng dụng vẫn cần responder, timeout, xử lý lỗi, correlation contract, retry và idempotency.

Bài này thuộc chủ đề **Gửi thông điệp** trong Spring JMS, vì vậy trọng tâm là **đặt header trên request khi gửi**, cách responder sử dụng và kiểm tra reply. Những đặc tính của broker, transaction và listener được đề cập khi cần để giải thích luồng gửi/nhận, không thay thế nội dung chuyên sâu của các chủ đề đó.

## 2. Phân biệt các header liên quan

| Header | Kiểu giá trị | Ai thường đặt? | Ý nghĩa |
| --- | --- | --- | --- |
| `JMSMessageID` | `String` có tiền tố `ID:` theo chuẩn | JMS provider khi send | Định danh **message cụ thể** mà provider gán |
| `JMSCorrelationID` | `String`, hoặc `byte[]` provider-native | Ứng dụng theo hợp đồng | Liên kết reply với request hoặc các message liên quan |
| `JMSReplyTo` | `Destination` (`Queue` hoặc `Topic`) | Requester | Destination được đề xuất để nhận reply |
| `JMSDestination` | `Destination` | Provider khi send | Destination của **message hiện tại**, không phải nơi phản hồi |
| `JMSType` | `String` | Ứng dụng nếu dùng | Phân loại thông điệp, không phải khóa correlation |
| Message properties | Các kiểu JMS property hỗ trợ | Ứng dụng/provider | Metadata riêng như `businessCommandId`, `schemaVersion` |

### 2.1. Vì sao không dùng JMSMessageID thay cho mọi ID?

`JMSMessageID` được provider gán lúc gửi. Với classic JMS, khi `MessageProducer.send(...)` trả về, object message đã được provider gán ID (trừ trường hợp provider chấp nhận cấu hình không tạo ID). ID này hữu ích để tham chiếu đến **một bản message**.

`JMSCorrelationID` khác: ứng dụng có quyền chỉ định giá trị để liên kết **nhiều message**. Ví dụ request và response có `JMSMessageID` khác nhau nhưng response có `JMSCorrelationID` trùng correlation của request.

Theo đặc tả JMS:

- `JMSMessageID` do provider tạo có tiền tố **`ID:`**.
- Giá trị `JMSCorrelationID` **do ứng dụng tự đặt** không được bắt đầu bằng **`ID:`**, vì tiền tố này dành cho message ID do provider tạo.
- `JMSCorrelationID` cũng có thể tham chiếu **một JMSMessageID thực**, khi đó chuỗi `ID:...` là ID có nguồn gốc provider, không phải tên tùy tiện do ứng dụng tự tạo.
- API `setJMSCorrelationIDAsBytes(byte[])` mang tính không portable; provider không bắt buộc hỗ trợ dạng bytes. Nên ưu tiên `setJMSCorrelationID(String)` nếu thiết kế mới.

Ví dụ **đúng** cho correlation ID do ứng dụng sinh:

~~~text
req-a4b8a169-4a0b-4a39-9b72-2d9a23c08e68
order-42-attempt-1
~~~

Ví dụ **sai convention** nếu ứng dụng tự đặt tùy tiện:

~~~text
ID:order-42
~~~

Không dựa vào `setJMSMessageID("ID:...")` để tự chọn ID của request: phương thức setter này phục vụ provider.

### 2.2. JMSReplyTo là Destination, không phải một String

`setJMSReplyTo(...)` đòi một object thực hiện `Destination`, không nhận chuỗi `"reply.queue"`. Khi dùng classic API:

~~~java
Queue replyQueue = session.createQueue("demo.replies");
TextMessage request = session.createTextMessage("order-42");

request.setJMSReplyTo(replyQueue);
request.setJMSCorrelationID("req-order-42");
~~~

Đây là **mảnh code** bên trong callback có `jakarta.jms.Session session`; cần imports `Queue` và `TextMessage`, và phương thức đang gọi phải cho phép ném `JMSException`. `createQueue("demo.replies")` tạo đối tượng đại diện tên queue. Nó **không bảo đảm broker tạo queue vật lý**; broker có thể auto-create hoặc đòi provision/cấp quyền trước.

Không nhầm `request.getJMSDestination()` với `request.getJMSReplyTo()`: trường đầu xác định queue nhận **request**, trường sau chỉ địa chỉ phản hồi.

### 2.3. Có thể để null không?

- `JMSReplyTo == null`: message không cung cấp địa chỉ reply. Nếu nghiệp vụ không yêu cầu phản hồi (event, fire-and-forget), điều này bình thường; nếu cần response, responder phải có fallback **được cấu hình trước** hoặc xử lý lỗi.
- `JMSCorrelationID == null`: request chưa cung cấp application correlation ID. Responder có thể dùng convention dựa trên `JMSMessageID`, nhưng hai phía phải thống nhất.
- Correlation ID không tự chứng minh tính xác thực; caller vẫn cần quyền broker và kiểm tra response đúng hợp đồng.

## 3. Hai quy ước correlation phổ biến

### 3.1. Quy ước A: application-generated request ID

Bên yêu cầu tạo `correlationId` **trước send**, đặt nó vào `JMSCorrelationID` của request. Responder **copy nguyên ID này** sang `JMSCorrelationID` của response.

~~~text
REQUEST
  JMSMessageID     = ID:provider-request-1
  JMSCorrelationID = req-abc
  JMSReplyTo       = reply.A

RESPONSE
  JMSMessageID     = ID:provider-response-2
  JMSCorrelationID = req-abc
  JMSDestination   = reply.A
~~~

Ưu điểm: caller biết ID trước khi gửi; dễ ghi map pending request, tracing/logging theo attempt và liên kết với hệ thống ngoài JMS. Nên dùng ID đủ duy nhất (ví dụ `"req-" + UUID.randomUUID()`), không dùng chỉ `"42"` khi nhiều service/client có thể trùng khóa.

Trong request–reply hiện đại, đây thường là lựa chọn dễ hiểu nhất **khi cả requester và responder cùng theo một hợp đồng**.

### 3.2. Quy ước B: JMSMessageID của request

Requester gửi request và lấy `JMSMessageID` được provider gán. Responder đặt `response.JMSCorrelationID = request.JMSMessageID`.

~~~text
REQUEST
  JMSMessageID     = ID:provider-request-1
  JMSCorrelationID = null
  JMSReplyTo       = reply.A

RESPONSE
  JMSMessageID     = ID:provider-response-2
  JMSCorrelationID = ID:provider-request-1
~~~

Ưu điểm: dùng trực tiếp ID provider. Giới hạn: requester không chắc biết ID cho đến khi send hoàn thành, cần bật sinh message ID và phải nhớ rằng **retry tạo một request mới có thể được gán JMSMessageID khác**.

### 3.3. Phải chọn một quy ước rõ ràng

| Quy tắc | Application-generated | JMSMessageID-based |
| --- | --- | --- |
| Requester biết ID trước send | Có | Không bảo đảm |
| Responder đặt correlation của reply bằng | `request.getJMSCorrelationID()` | `request.getJMSMessageID()` |
| Gắn với provider ID | Không | Có |
| Cần sinh ID đủ duy nhất | Ứng dụng chịu trách nhiệm | Provider tạo |
| Đổi provider/routing | Dễ giữ hợp đồng riêng | Phụ thuộc nghĩa ID provider |
| Retry và duplicate | Thiết kế attempt ID/business ID | Cần map message ID của attempt |

**Tuyệt đối không để requester áp dụng quy ước A nhưng responder lại áp dụng B.** JMS không tự buộc các bên đồng ý một cách tương quan. Viết convention thành contract và kiểm thử tích hợp.

## 4. Đặt JMSCorrelationID và JMSReplyTo bằng Spring JmsTemplate

Trong Spring Framework 6+ / Spring Boot 3+, lớp JMS thuộc `jakarta.jms.*`. Spring `JmsTemplate` quản lý `Connection`, `Session`, producer, exception translation trong phạm vi một thao tác, nhưng business code vẫn phải cung cấp destination/correlation.

### 4.1. `send(String, MessageCreator)` — tự thiết lập toàn bộ header

~~~java
import java.util.UUID;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.springframework.jms.core.JmsTemplate;

// Mảnh code trong một service đã được inject JmsTemplate:
String correlationId = "req-" + UUID.randomUUID();

jmsTemplate.send("demo.requests", session -> {
    Queue replyQueue = session.createQueue("demo.replies");
    TextMessage request = session.createTextMessage("order-42");
    request.setJMSReplyTo(replyQueue);
    request.setJMSCorrelationID(correlationId);
    return request;
});
~~~

Ý nghĩa:

1. `"demo.requests"` là **destination mà template gửi request tới**.
2. `replyQueue` là **địa chỉ mà responder sẽ gửi response tới**.
3. `correlationId` là **định danh mà caller dự kiến đối chiếu khi nhận**.
4. `MessageCreator` nhận `Session` được template cấp; callback không giữ resource để dùng sau.
5. Ví dụ chưa tạo consumer reply: đây chỉ là **mảnh code gửi thông điệp**, chưa phải request–reply hoàn chỉnh.

Nếu cần gửi đến một `Destination` object thay vì tên String, `JmsTemplate.send(Destination, MessageCreator)` có overload tương ứng.

### 4.2. `convertAndSend` và `MessagePostProcessor`

Nếu payload dễ convert (ví dụ `String` → `TextMessage`), vẫn có thể gắn header trước lúc gửi:

~~~java
import java.util.UUID;
import jakarta.jms.Queue;

Queue replyQueue = configuredReplyQueue;
String id = "req-" + UUID.randomUUID();

jmsTemplate.convertAndSend("demo.requests", "order-42", message -> {
    message.setJMSReplyTo(replyQueue);
    message.setJMSCorrelationID(id);
    return message;
});
~~~

`configuredReplyQueue` phải do code/service cấu hình hoặc inject hợp lệ; đoạn trên **không chạy độc lập**. `MessagePostProcessor` chạy sau bước chuyển payload thành JMS Message nhưng **trước khi producer send**. Không nhầm với xử lý response.

**Quy tắc thiết kế:** đặt correlation vào **header chuẩn** thay vì chỉ nhét vào JSON body nếu hệ thống muốn dùng JMS selector, adapter hay tooling JMS đọc được.

### 4.3. API Jakarta JMS thuần

~~~java
// Đoạn minh họa với ConnectionFactory đã cấu hình:
try (JMSContext ctx = connectionFactory.createContext()) {
    Queue requests = ctx.createQueue("demo.requests");
    TemporaryQueue replyTo = ctx.createTemporaryQueue();
    try {
        TextMessage request = ctx.createTextMessage("order-42");
        request.setJMSCorrelationID("req-order-42");
        request.setJMSReplyTo(replyTo);
        ctx.createProducer().send(requests, request);
    } finally {
        replyTo.delete();
    }
}
~~~

Đây **chỉ là ví dụ đặt header và send**: temporary reply queue đã bị xóa ngay sau gửi, nên **không thể dùng nguyên đoạn để chờ response**. Với request–reply thật phải tạo consumer, giữ `JMSContext` và temporary destination còn sống qua thời gian chờ, rồi mới xóa. Xem project hoàn chỉnh ở phần 7.

### 4.4. Lưu ý khi header được cấu hình trên JMSProducer

`JMSProducer` (simplified API) cũng cung cấp `setJMSReplyTo(...)` và `setJMSCorrelationID(...)`. Những thiết lập ở mức producer được áp dụng khi send và có thể ghi đè giá trị header trên object message. Nếu có hai nơi đặt cùng một header, rất dễ gửi sai reply destination hoặc correlation ID; nên thống nhất một cách.

## 5. Responder phải đọc hai header và gửi đúng reply

Trình tự responder:

1. Nhận message từ queue request; validate body/schema.
2. Gọi `request.getJMSReplyTo()`.
3. Chọn correlation convention A hoặc B; lấy ID tương ứng.
4. Tạo **một message response mới**.
5. Đặt `response.setJMSCorrelationID(id)`.
6. Gửi tới chính `Destination` lấy từ header.
7. Xử lý lỗi gửi reply, redelivery/duplicate và ghi log đã lọc thông tin nhạy cảm.

Ví dụ Spring `@JmsListener` dùng raw `TextMessage`:

~~~java
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
class ReplyWorker {
    private final JmsTemplate jmsTemplate;

    ReplyWorker(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @JmsListener(destination = "demo.requests")
    public void handle(TextMessage request) throws JMSException {
        Destination replyTo = request.getJMSReplyTo();
        String id = request.getJMSCorrelationID(); // convention A

        if (replyTo == null || id == null) {
            throw new IllegalArgumentException("Missing reply headers");
        }

        String body = request.getText();
        jmsTemplate.send(replyTo, session -> {
            TextMessage reply = session.createTextMessage("ACK:" + body);
            reply.setJMSCorrelationID(id);
            return reply;
        });
    }
}
~~~

Đây là class minh họa cần project Spring có `@JmsListener`, `ConnectionFactory` và broker. Spring JMS cho phép inject raw `jakarta.jms.Message`/subclass vào listener. Method trả `void` nên framework **không** tự gửi thêm response; việc send đã được gọi tường minh.

Ở quy ước B, responder sẽ dùng:

~~~java
String id = request.getJMSMessageID();
reply.setJMSCorrelationID(id);
~~~

Đây là **mảnh mã thay thế logic** trong responder, không phải hai câu lệnh độc lập chạy ngoài callback. Requester phải biết ID gốc của request để so sánh.

### 5.1. Spring listener có thể tự gửi reply từ return value

~~~java
@JmsListener(destination = "demo.requests")
public String handle(String request) {
    return "ACK:" + request;
}
~~~

Khi request có `JMSReplyTo`, Spring listener adapter có thể chuyển return value thành response gửi tới destination đó; `@SendTo` có thể định nghĩa default reply destination khi cần.

Nhưng việc **tự động gửi đến đúng địa chỉ** không phải bảo đảm mọi converter/adapter sẽ đặt `JMSCorrelationID` đúng convention ứng dụng. Nếu contract buộc responder echo một ID, cần kiểm thử raw JMS headers hoặc chủ động tạo response như ví dụ đầu mục.

## 6. Queue reply cố định và TemporaryQueue

### 6.1. Queue cố định

Requester dùng một queue đã được provision, ví dụ `app.reply`:

~~~text
JMSReplyTo = Queue("app.reply")
~~~

Ưu điểm: destination ổn định, có thể nhận reply sau khi requester reconnect nếu message còn tồn tại và broker/TTL/persistence cho phép. Nhược điểm: nếu nhiều request/instance cùng nhận từ queue, cần **selector, dispatcher hoặc routing** để tránh một requester consume response của người khác.

### 6.2. TemporaryQueue

Requester tạo `TemporaryQueue` qua `Session.createTemporaryQueue()` hoặc `JMSContext.createTemporaryQueue()`:

- Lifetime gắn với **connection tạo nó**; không phải session hay Java variable.
- Chỉ **connection sở hữu** được tạo consumer trên destination tạm đó.
- Producer trên connection khác **có thể gửi** đến destination, nếu broker cho phép.
- Khi owner connection đóng hoặc queue bị delete, late reply có thể mất đích.
- Phù hợp request–reply ngắn hạn; có chi phí create/delete destination và consumer.

Với một reply của một requester, `TemporaryQueue` thường dễ dùng hơn `TemporaryTopic`. `JMSReplyTo` vẫn có thể là `Topic`/`TemporaryTopic`, nhưng publish/subscribe có thể phân phối một reply tới nhiều subscriber, không còn semantics một người nhận.

| Tiêu chí | Reply queue cố định | TemporaryQueue |
| --- | --- | --- |
| Lifetime | Do broker/ứng dụng quản lý | Theo owner connection |
| Provision | Thường cấu hình sẵn | Provider tạo theo yêu cầu |
| Người được consume | Theo ACL/selector/concurrency | Chỉ consumer trên owner connection |
| Khi requester disconnect | Message có thể vẫn còn nếu được lưu phù hợp | Queue tạm không mặc định tồn tại |
| Concurrency | Phải xử lý correlation/routing | Đơn giản với một queue mỗi request |
| Hiệu năng | Ít tạo destination mới | Nhiều request có thể tạo nhiều destination |

**Không xóa temporary queue trước khi đợi response xong**. Nếu gọi `delete()` khi consumer vẫn đang dùng, JMS có thể ném `JMSException`; đóng consumer trước.

## 7. Demo chạy được với Java 17+, Spring Boot và Artemis

Project này cho thấy rõ hai header, cả producer và consumer, timeout và so khớp correlation. Requester dùng `JMSContext` (Jakarta Messaging simplified API) từ factory mà Spring cấp; responder dùng `@JmsListener` và `JmsTemplate`.

### 7.1. Khởi động broker demo

~~~bash
docker run --rm -d --name jms-correlation-demo \
  -p 127.0.0.1:61616:61616 \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  apache/artemis:latest-alpine
~~~

Đợi broker sẵn sàng và xem log bằng `docker logs jms-correlation-demo`. Tài khoản trên **chỉ dành cho lab local**. Với production, dùng secret store/TLS/ACL, không dùng password mẫu và nên pin phiên bản/image digest trong pipeline.

### 7.2. Cấu trúc thư mục

~~~text
jms-correlation-demo/
├── pom.xml
└── src/main/
    ├── resources/application.properties
    └── java/com/example/jms/CorrelationApplication.java
~~~

### 7.3. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jms-correlation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.4. `application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

`native` dùng broker Artemis chạy riêng. Demo phụ thuộc broker lab cho phép tạo queue `demo.rpc.requests` theo chính sách auto-create; nếu broker không cho, cần provision queue/address và cấp quyền. Cấu hình này không dùng cho production.

### 7.5. `CorrelationApplication.java` — mã đầy đủ

~~~java
package com.example.jms;

import java.util.Objects;
import java.util.UUID;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TextMessage;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class CorrelationApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorrelationApplication.class, args);
    }

    @Bean
    CommandLineRunner sendRequest(ConnectionFactory connectionFactory) {
        return args -> {
            String expectedId = "req-" + UUID.randomUUID();

            try (JMSContext context = connectionFactory.createContext()) {
                Queue requestQueue = context.createQueue("demo.rpc.requests");
                TemporaryQueue replyQueue = context.createTemporaryQueue();

                try (JMSConsumer consumer = context.createConsumer(replyQueue)) {
                    TextMessage request =
                            context.createTextMessage("order-42");
                    request.setJMSReplyTo(replyQueue);
                    request.setJMSCorrelationID(expectedId);
                    context.createProducer().send(requestQueue, request);

                    Message incoming = consumer.receive(5_000);
                    if (incoming == null) {
                        System.out.println("Reply timeout");
                        return;
                    }
                    if (!(incoming instanceof TextMessage reply)) {
                        throw new IllegalStateException(
                                "Expected TextMessage reply");
                    }

                    boolean match = Objects.equals(
                            expectedId, reply.getJMSCorrelationID());
                    System.out.println("Correlation matched: " + match);
                    System.out.println("Reply body: " + reply.getText());

                    if (!match) {
                        throw new IllegalStateException(
                                "Response correlation ID mismatch");
                    }
                } finally {
                    replyQueue.delete();
                }
            }
        };
    }
}

@Component
class OrderResponder {

    private final JmsTemplate jmsTemplate;

    OrderResponder(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @JmsListener(destination = "demo.rpc.requests")
    public void process(TextMessage request) throws JMSException {
        Destination replyTo = request.getJMSReplyTo();
        String id = request.getJMSCorrelationID();

        if (replyTo == null || id == null) {
            throw new IllegalArgumentException(
                    "Request must contain both reply headers");
        }

        String requestBody = request.getText();
        jmsTemplate.send(replyTo, session -> {
            TextMessage reply =
                    session.createTextMessage("ACK:" + requestBody);
            reply.setJMSCorrelationID(id);
            return reply;
        });
    }
}
~~~

Giải thích luồng:

1. Spring Boot tạo `ConnectionFactory` từ starter Artemis và các property. `@EnableJms` kích hoạt endpoint annotation (Boot cũng có hạ tầng auto-config khi starter phù hợp).
2. `CommandLineRunner` tạo ID ngẫu nhiên `req-...` cho request, không dùng tiền tố `ID:`.
3. Requester tạo `TemporaryQueue` và **consumer trên cùng owner context**, rồi mới gửi request. `JMSContext` tự start mặc định khi consumer được tạo; không cần classic `connection.start()` trong ví dụ này.
4. Request có `JMSReplyTo = replyQueue` và `JMSCorrelationID = expectedId`.
5. Spring `@JmsListener` đọc hai header rồi gửi reply bằng `JmsTemplate.send(replyTo, MessageCreator)`, **copy correlation ID**.
6. Requester nhận reply và kiểm tra ID trùng khớp. Không coi response là hợp lệ chỉ vì có message trên reply queue.
7. `try-with-resources` đóng consumer/context; `finally` xóa temporary queue sau khi consumer đã đóng. Nếu timeout, ứng dụng vẫn dọn tài nguyên.

### 7.6. Chạy và stdout kỳ vọng

Tại thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Nếu broker hoạt động, listener sẵn sàng và response nhận trước 5 giây, hai dòng business output là:

~~~text
Correlation matched: true
Reply body: ACK:order-42
~~~

Có thể có thêm log Spring/Artemis; UUID random không được in nên hai dòng này ổn định trên lần chạy thành công. Nếu responder không trả kịp:

~~~text
Reply timeout
~~~

Sau khi thực hành:

~~~bash
docker stop jms-correlation-demo
~~~

Ví dụ này **không tự chứng minh** exactly-once, database atomicity, failover hoặc TLS. Trong production, requester và responder có thể ở hai tiến trình khác nhau; khi đó phải kiểm tra broker routing cho destination reply và quy định timeout/ACL.

## 8. JmsTemplate.sendAndReceive(): Spring tạo địa chỉ reply giúp

`JmsTemplate.sendAndReceive(destination, MessageCreator)` cung cấp request–reply đồng bộ: template tạo temporary reply queue, gắn vào `JMSReplyTo`, gửi request, tạo consumer chờ reply và dọn tài nguyên theo phạm vi thao tác.

~~~java
// Mảnh code: cần một responder thật đọc "demo.rpc.requests".
Message reply = jmsTemplate.sendAndReceive(
    "demo.rpc.requests",
    session -> {
        TextMessage request =
                session.createTextMessage("order-42");
        request.setJMSCorrelationID("req-order-42");
        return request;
    }
);
if (reply == null) {
    System.out.println("Reply timeout");
}
~~~

Những điểm cần nhớ:

- `sendAndReceive` thường **tự đặt JMSReplyTo** là temporary queue của riêng lời gọi; đừng giả định một `JMSReplyTo` tự gán khác trong callback được giữ nguyên.
- Nếu response dùng application correlation ID, responder vẫn phải tuân thủ quy tắc echo hoặc cơ chế được adapter cấu hình rõ.
- Caller phải kiểm tra response `getJMSCorrelationID()` nếu nghiệp vụ cần xác thực ghép yêu cầu.
- Cần đặt timeout, ví dụ property Boot `spring.jms.template.receive-timeout=5s`, tránh chờ vô hạn.
- Không có responder thì `sendAndReceive` không tự tạo server. Nó cũng không tự bảo đảm rollback DB, retry/idempotency hoặc xử lý response đến muộn.

**Khi nào chọn cách nào?** `sendAndReceive` thích hợp request–reply đơn giản và dễ triển khai; tự quản lý `JMSReplyTo`/consumer phù hợp khi cần reply queue cố định, multiplexing nhiều request hoặc lifetime đặc biệt.

## 9. Nhiều request đồng thời trên shared reply queue

Một queue chung `app.reply` có thể chứa response cho `req-A`, `req-B`, `req-C` theo thứ tự **khác** thứ tự request. Chỉ đặt `JMSReplyTo = app.reply` không đủ để một caller biết message nào thuộc về mình.

~~~text
send req-A, corr=req-A ─┐
send req-B, corr=req-B ─┼─> request queue ──> responders
send req-C, corr=req-C ─┘                       │
                                              ▼
                                   app.reply: C, A, B
                                              │
                                    dispatcher/selector
                                              ▼
                               req-C → waiter C
                               req-A → waiter A
                               req-B → waiter B
~~~

Có hai chiến lược:

1. **Message selector:** tạo consumer chọn response có `JMSCorrelationID` khớp. Ví dụ cú pháp JMS selector: `JMSCorrelationID = 'req-123'`. Đặt timeout phù hợp; consumer có selector có thể tốn resource broker nếu tạo một consumer cho mỗi request.
2. **Một listener + dispatcher:** một consumer đọc reply queue, kiểm tra correlation và hoàn thành pending request/future trong bảng tra cứu của ứng dụng. Cần concurrency-safe map, timeout, cleanup, duplicate/unknown reply và xử lý nhiều replica.

Ví dụ **mảnh code** với `JmsTemplate`:

~~~java
String correlationId = "req-123";
String selector = "JMSCorrelationID = '" + correlationId + "'";

Message received = jmsTemplate.receiveSelected(
        "app.reply",
        selector
);
~~~

`receiveSelected` là nhận đồng bộ có thể block; nên cấu hình timeout. Chỉ ghép selector trực tiếp như trên khi ID do hệ thống sinh trong **tập ký tự an toàn đã validate**; input tùy ý có dấu nháy/escape phải được xử lý đúng cú pháp selector để tránh sai biểu thức. JMS selector lọc **header/property**, không tự truy vấn JSON trong body.

Với nhiều instance cùng lắng nghe một reply queue không có partition, responder gửi reply vào queue chung có thể bị instance **khác** nhận. Nếu pending `Future` chỉ ở memory của instance đầu, phải có thiết kế route/selector/ownership hoặc lưu trữ trạng thái chung — correlation ID một mình không đảm bảo route đúng replica.

## 10. Timeout, transaction, retry và idempotency

### 10.1. Response trễ

Khi requester timeout, reply vẫn có thể được gửi sau:

- Với `TemporaryQueue` đã bị delete hoặc owner connection đóng, reply có thể lỗi hoặc không còn đích hợp lệ.
- Với queue reply cố định, response trễ có thể tồn tại đến TTL hoặc cleanup policy.
- Nếu requester retry bằng attempt ID mới, late reply cũ phải không được ghép nhầm thành kết quả attempt mới.

Một cách ghi contract:

~~~text
businessCommandId = create-order-42
attemptCorrelationId = req-...-1
replyTimeout = 5s
retryPolicy = exponential backoff, bounded attempts
lateReplyPolicy = discard / store / reconcile
~~~

`businessCommandId` dành cho idempotency nghiệp vụ; `JMSCorrelationID` có thể biểu diễn một **attempt**. Không mặc định chúng giống nhau. Cần tránh tạo nhiều đơn hàng chỉ vì request bị gửi lại sau timeout.

### 10.2. Không đợi reply trước khi commit request trong cùng JMS transaction

~~~text
BEGIN JMS TRANSACTION
  send(request)      ← request chưa được commit
  receive(reply)     ← chờ worker
                       worker chưa thấy request
  timeout / lỗi logic
~~~

Nếu request được gửi trong một **JMS transacted session** chưa commit, consumer khác thường chưa thấy request để xử lý. Hãy tách transaction boundary: commit send trước khi đợi reply, hoặc thiết kế async job/result. Không giữ DB transaction mở trong suốt lượt chờ mạng mà không có lý do vận hành rõ.

### 10.3. Correlation không bảo đảm exactly-once

Một kịch bản:

1. Worker đã xử lý nghiệp vụ và commit.
2. Worker gửi reply, nhưng requester mất kết nối trước khi nhận.
3. Requester timeout, gửi lại request.
4. Worker nhận duplicate request.

Dù correlation ID được đặt đúng, business side effect có thể lặp. Cần idempotent handler, deduplication theo business command ID, transaction/outbox khi phù hợp, giới hạn retry, DLQ và giám sát redelivery.

### 10.4. TTL khác receive timeout

- **Time-to-live** của producer xác định thời gian message có thể được phân phối theo JMS expiration semantics.
- **Receive timeout** xác định thời gian thread đợi response trước khi trả `null` hoặc hết hạn.
- **Business deadline** là quy ước do hệ thống chọn.

Ba khái niệm này không tự động đồng bộ. Một reply còn TTL vẫn có thể đến sau khi requester đã hết thời gian chờ; ngược lại requester có thể chờ lâu hơn khi message đã hết hạn.

## 11. Bảo mật, tracing và kiểm thử

### 11.1. Không coi header là quyền truy cập

`JMSReplyTo` là destination do request cung cấp; nếu broker nhiều tenant hoặc có bridge, responder cần kiểm soát phạm vi destination mà nó có thể gửi tới. Một ID correlation dễ đoán hoặc bị log không phải token xác thực.

Các lớp bảo vệ cần có:

- Broker authentication và ACL send/consume/create destination; dùng quyền tối thiểu.
- TLS, hạn chế client truy cập broker và bảo vệ credential.
- Validate message schema, hạn chế payload/metadata nhạy cảm.
- Nếu cần, kiểm soát namespace reply destination, nhất là khi nhận request từ nguồn kém tin cậy.
- Không gắn dữ liệu cá nhân, mật khẩu hoặc session token vào correlation ID.

### 11.2. Logging hữu ích mà không lộ dữ liệu

~~~text
event=request_sent corr=req-... destination=demo.requests
event=reply_sent   corr=req-... result=success
event=reply_recv   corr=req-... latencyMs=18 matched=true
~~~

Không log toàn bộ body hoặc secrets. Correlation ID có thể dùng để nối log của requester/responder, nhưng distributed tracing thường có **trace ID / traceparent** riêng trong JMS properties/instrumentation. Không dùng correlation ID làm metrics label cho mọi request: cardinality quá cao.

### 11.3. Kiểm thử cần có

- Happy path: request có đủ `JMSReplyTo` và `JMSCorrelationID`, reply đến đúng destination với ID trùng.
- Request thiếu replyTo/correlation: responder từ chối hoặc fallback theo contract, không gửi sang đích ngẫu nhiên.
- Timeout: requester không treo thread vô hạn; consumer/temporary queue được dọn.
- Mismatch: response correlation sai bị loại bỏ hoặc đánh dấu lỗi, không trả kết quả như thành công.
- Concurrency: nhiều request tới cùng một reply queue không bị nhận chéo.
- Redelivery: request duplicate không tạo lại tác dụng phụ nghiệp vụ.
- Reconnect/failover: temporary destination cũ không được dùng mù quáng sau khi connection mới xuất hiện.
- Authorization: worker không thể gửi vào reply destination nếu thiếu quyền; lỗi phải được xử lý và quan sát.
- Schema/security: không nhận reply giả hoặc body sai định dạng chỉ vì correlation trùng.

## 12. Lỗi hay gặp và cách sửa

| Lỗi | Hậu quả | Giải pháp |
| --- | --- | --- |
| Gửi request không có `JMSReplyTo` | Responder không biết nơi phản hồi | Đặt Destination hoặc định nghĩa fallback rõ |
| Dùng String trực tiếp cho `setJMSReplyTo` | Sai chữ ký API | Resolve `Queue`/`Topic` trước |
| App-generated ID bắt đầu `ID:` | Sai quy ước reserved ID của JMS | Dùng tiền tố `req-` và UUID |
| Dùng `JMSMessageID` của response để nhận diện request | Đó là message khác, có ID mới | Kiểm tra response `JMSCorrelationID` |
| Responder tự sinh ID response mới | Không match request | Copy request correlation hoặc request message ID theo contract |
| Requester chọn convention A nhưng responder chọn B | Correlation mismatch | Thống nhất và test cross-service |
| Tạo TemporaryQueue rồi đóng connection trước reply | Destination hết vòng đời | Giữ owner connection đến timeout/response |
| Xóa TemporaryQueue khi consumer vẫn mở | Có thể ném JMSException | Close consumer rồi delete |
| Shared reply queue không có selector/dispatcher | Consumer nhận nhầm reply | Thiết kế correlation routing/multi-instance |
| Không đặt receive timeout | Thread có thể block mãi | Timeout hữu hạn và backpressure |
| Đợi reply trong uncommitted send transaction | Responder không thấy request | Commit send rồi mới chờ |
| Retry mà không có idempotency | Side effect lặp | Business command ID và dedup policy |
| Dựa vào correlation như security token | Dễ spoof | ACL/auth/TLS, kiểm tra nguồn và reply destination |
| Không xử lý reply muộn | Stale response gây sai hoặc queue tồn đọng | TTL, unknown/late reply handling |
| Dùng body JSON thay vì JMS header khi cần selector | Selector không đọc arbitrary body | Ghi JMSCorrelationID/property chuẩn |

## 13. Checklist áp dụng

1. Chọn rõ request destination, reply destination, message type.
2. `JMSReplyTo` là object `Destination` hợp lệ và có route/ACL phù hợp.
3. Chọn convention A hoặc B cho correlation, document ở cả producer/responder.
4. Nếu app tự sinh ID, dùng giá trị đủ duy nhất và không có tiền tố `ID:`.
5. Responder lấy replyTo từ request, đặt correlation của response đúng contract.
6. Requester kiểm tra ID của **response** trước khi coi reply hợp lệ.
7. Với TemporaryQueue, tạo consumer trên owner connection và xóa sau khi đóng consumer.
8. Với shared queue, có selector/dispatcher và xử lý nhiều instance.
9. Đặt timeout, retry hữu hạn, late reply policy, DLQ và metrics.
10. Tách rõ correlation ID, business idempotency key và trace ID.
11. Không đợi reply trên JMS transaction chưa commit request.
12. Kiểm thử cả broker outage, wrong header, wrong destination, duplicate và reconnect.

## 14. Câu hỏi tự kiểm tra

**1. JMSReplyTo là gì?**  
Là `Destination` mà người gửi đề xuất để nhận phản hồi; có thể là queue/topic thường hoặc tạm.

**2. JMSCorrelationID dùng để làm gì?**  
Liên hệ message với nhau, phổ biến nhất là ghép response với request.

**3. Hai request có thể dùng cùng một reply queue nhưng correlation khác nhau không?**  
Có. Lúc đó consumer/dispatcher phải ghép đúng response dựa trên correlation và quyền sở hữu.

**4. Vì sao application-generated correlation ID không được bắt đầu `ID:`?**  
Tiền tố đó dành cho provider-generated message ID theo đặc tả JMS.

**5. Convention A và B khác gì?**  
A: response correlation bằng `request.getJMSCorrelationID()`. B: response correlation bằng `request.getJMSMessageID()`.

**6. Gọi `session.createQueue("reply")` có tự tạo temporary queue không?**  
Không. Đó là đại diện queue theo tên; dùng `createTemporaryQueue()` nếu cần destination tạm do provider cấp.

**7. Khi nào requester có thể xóa temporary reply queue?**  
Sau khi kết thúc nhận response/timeout, đóng consumer rồi delete; không xóa ngay sau send.

**8. `JmsTemplate.sendAndReceive` có tự tạo responder không?**  
Không. Template chỉ gửi, tạo reply queue tạm và chờ; phía bên kia phải gửi phản hồi.

**9. Có phải mọi response đến đúng queue đều hợp lệ?**  
Không. Còn phải so correlation ID, loại message, schema và điều kiện bảo mật.

**10. Correlation ID có bảo đảm xử lý exactly-once không?**  
Không. Retry và redelivery vẫn có thể tạo duplicate; cần idempotency và transaction design.

## 15. Tài liệu chính thức

1. [Jakarta Messaging 3.1 Specification — JMSCorrelationID, JMSReplyTo, JMSMessageID](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
2. [Jakarta Messaging 3.1 API — Message header methods](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message)
3. [Jakarta Messaging 3.1 API — JMSContext](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext)
4. [Jakarta Messaging 3.1 API — TemporaryQueue](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/temporaryqueue)
5. [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
6. [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
7. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
8. [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
9. [Spring Boot — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
10. [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)
