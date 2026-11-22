# JMSDestination, JMSReplyTo và JMSCorrelationID

**Chủ đề:** Spring Framework - jms → Mô hình Message

Ba trường này thuộc **standard message headers** của Java Message Service (JMS), hiện chuẩn hóa trong **Jakarta Messaging**. Chúng cùng xuất hiện trong request/reply nhưng có nhiệm vụ khác nhau: xác định **nơi message được gửi tới**, **nơi mong nhận phản hồi**, và **mối liên hệ giữa request với reply**. Phân biệt đúng ba trường giúp xử lý những lỗi như reply đi nhầm queue, client lấy nhầm phản hồi và timeout dù broker đã nhận request.

## 1. Message header nằm ở đâu trong JMS?

JMS message gồm ba phần logic:

- **Header:** các trường chuẩn như `JMSMessageID`, `JMSDestination`, `JMSReplyTo`, `JMSCorrelationID`, `JMSPriority`, `JMSTimestamp`. Một số trường do provider gán khi send; một số do client được phép gán.
- **Properties:** metadata dạng tên–giá trị như `orderId` hoặc `traceId` do ứng dụng khai báo, ngoài những JMS-defined/provider-specific properties.
- **Body:** payload như chuỗi JSON, văn bản hoặc dữ liệu nhị phân theo message type.

Ba header của bài đều có getter/setter trong `jakarta.jms.Message`; chúng **không phải** ba ô body hay ba application properties. Trong Spring Framework 6+ và Spring Boot 3+, code JMS dùng `jakarta.jms.*`. Tài liệu và ứng dụng đời cũ có thể dùng `javax.jms.*`; cần chọn driver và API tương thích với cùng namespace.

| Header | Câu hỏi trả lời | Kiểu Java | Ai chịu trách nhiệm giá trị? |
| --- | --- | --- | --- |
| `JMSDestination` | Message này đi **đến destination nào**? | `jakarta.jms.Destination` | Provider đặt theo đích của thao tác send |
| `JMSReplyTo` | Consumer muốn trả lời thì **gửi về đâu**? | `jakarta.jms.Destination` hoặc `null` | Producer/requester chỉ định |
| `JMSCorrelationID` | Reply này **thuộc request nào**? | `String`, ngoài ra có dạng byte[] riêng provider | Ứng dụng thống nhất quy ước |

**Ví dụ:** một hệ thống gửi yêu cầu xử lý `order-42` vào queue `orders.requests` và mong câu trả lời về `orders.responses`:

~~~text
REQUEST
  JMSDestination   = orders.requests     (do provider gán khi send)
  JMSReplyTo       = orders.responses    (do requester gán)
  JMSCorrelationID = corr-a42           (do requester gán)
  Body             = order-42

REPLY
  JMSDestination   = orders.responses    (do provider gán khi send reply)
  JMSCorrelationID = corr-a42           (responder sao chép theo quy ước)
  Body             = accepted:order-42
~~~

`JMSDestination` của request **không phải** `orders.responses`. `JMSReplyTo` trên request không tự khiến broker tạo reply. `JMSCorrelationID` không tự tìm queue cho message; nó hỗ trợ ứng dụng đối chiếu các message liên quan.

## 2. JMSDestination: nơi message thực sự được gửi đến

### 2.1. Hợp đồng JMS

`Message.getJMSDestination()` trả về object `Destination` phản ánh nơi message được gửi. Theo Jakarta Messaging, khi gửi message:

1. Ứng dụng chọn destination qua đối tượng `MessageProducer` hoặc tham số `send(destination, message)`.
2. Provider thực hiện gửi và gán `JMSDestination` tương ứng với destination đó.
3. Giá trị `JMSDestination` do ứng dụng cố đặt sẵn trước send **bị bỏ qua tại thao tác send**.
4. Consumer nhận được message với `JMSDestination` tương đương destination đã dùng khi gửi.

Ví dụ JMS classic API, **đoạn minh họa với `session` đã được khởi tạo từ một connection hợp lệ**:

~~~java
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

Queue destination = session.createQueue("orders.requests");
TextMessage msg = session.createTextMessage("order-42");

try (MessageProducer producer = session.createProducer(destination)) {
    producer.send(msg);
    System.out.println(msg.getJMSDestination() != null);
}
~~~

Sau khi send đồng bộ thành công, dòng `System.out.println` in:

~~~text
true
~~~

Trên receiver, nếu chắc chắn destination là queue, có thể đọc tên thông qua `Queue.getQueueName()`; nếu là topic, dùng `Topic.getTopicName()`. Không dùng `Destination.toString()` như một định dạng ổn định xuyên các provider.

~~~java
import jakarta.jms.Destination;
import jakarta.jms.Queue;
import jakarta.jms.Topic;

Destination destination = message.getJMSDestination();
if (destination instanceof Queue q) {
    System.out.println("Queue name: " + q.getQueueName());
} else if (destination instanceof Topic t) {
    System.out.println("Topic name: " + t.getTopicName());
}
~~~

Đoạn trên cũng giả định `message` là `jakarta.jms.Message` đã được nhận. Nó không tự tạo tài nguyên hay broker.

### 2.2. Đừng dùng JMSDestination để tự định tuyến

Một nhầm lẫn phổ biến:

~~~java
message.setJMSDestination(queueA);
producer.send(queueB, message);
~~~

Nếu thao tác `send(queueB, message)` thành công, provider dùng **queueB** làm `JMSDestination`. Muốn đưa message tới một queue, truyền destination đó vào thao tác send hoặc tạo producer gắn sẵn với destination đúng. Có thể tạo anonymous producer bằng `session.createProducer(null)` rồi chỉ định destination cho từng lần gửi.

Trong Spring:

~~~java
jmsTemplate.convertAndSend("orders.requests", "order-42");
~~~

Ở đây `JmsTemplate` resolve tên queue và yêu cầu JMS provider gửi message. `JMSDestination` được provider thiết lập theo destination đó. Việc JMS `Queue` object được tạo từ tên không bảo đảm queue vật lý đã tồn tại trong broker: cách auto-create/provision queue thuộc cấu hình provider.

### 2.3. Một destination chưa nói hết đường đi nghiệp vụ

`JMSDestination` có thể là queue hoặc topic, nhưng không phản ánh mọi nội bộ định tuyến, địa chỉ mạng broker, subscription, tenant hay consumer thực tế. Một queue có nhiều consumer cạnh tranh; message vẫn có một `JMSDestination` tương ứng với queue. Nếu cần biết **ứng dụng nào** xử lý, hãy dùng quan sát hoạt động và business logs phù hợp, không suy ra từ header.

## 3. JMSReplyTo: đích nhận phản hồi do requester đề xuất

`Message.setJMSReplyTo(Destination replyTo)` đặt nơi **responder nên gửi message trả lời**. Sau khi nhận request, responder đọc `getJMSReplyTo()`, xử lý nghiệp vụ, tạo một **message mới** và gửi tới destination đã nhận được.

~~~text
Requester -------------------> request queue ------------------> Responder
   ^                                 |                               |
   |                                 | JMSReplyTo = reply queue      |
   |                                 v                               |
   +------------------------ reply queue <---------------------------+
                   (responder gửi message reply mới)
~~~

Ví dụ phần cốt lõi:

~~~java
// Requester, với request/producer/requestQueue/replyQueue đã chuẩn bị:
request.setJMSReplyTo(replyQueue);
producer.send(requestQueue, request);

// Responder, với incoming/replyProducer/reply đã được tạo:
if (incoming.getJMSReplyTo() != null) {
    replyProducer.send(incoming.getJMSReplyTo(), reply);
}
~~~

Đây là **hai đoạn trích từ hai phía**, không phải một chương trình độc lập. Cả sender và responder cần session/connection và destination hợp lệ.

**Các điểm quan trọng:**

- `JMSReplyTo` có thể là `Queue` hoặc `Topic`; kiểu thông dụng cho request/reply là reply queue.
- `JMSReplyTo=null` không làm JMS message sai. Message có thể là event một chiều và không đòi reply.
- `JMSReplyTo != null` **không cam kết** có reply, không cam kết thời hạn, cũng không bảo đảm nghiệp vụ xử lý thành công.
- Broker **không** tự dùng `JMSReplyTo` để đổi destination của request. Chỉ khi responder gửi reply, destination ấy mới trở thành destination của message mới.
- Consumer phải được cấp quyền gửi tới reply destination; việc có object trong header không cấp thêm quyền truy cập.

### 3.1. Reply queue cố định

Ví dụ nhiều requester gửi tới `orders.requests` và cùng khai báo `orders.responses`. Ưu điểm là destination tồn tại độc lập với requester, dễ monitor và vận hành. Đổi lại cần cách phân phối reply về đúng requester. Nếu hai client cùng consume một queue không selector, reply cho client A có thể bị client B lấy đi vì semantics queue là **competing consumers**.

Các cách giải quyết: một dispatcher duy nhất quản lý mọi reply; selector theo correlation/owner; hoặc reply queue riêng từng instance. Chọn theo số request đồng thời, chi phí consumer, quota broker và yêu cầu giữ reply muộn.

### 3.2. TemporaryQueue

JMS hỗ trợ `Session.createTemporaryQueue()` (hoặc `JMSContext.createTemporaryQueue()`) để tạo queue tạm có tên/identity riêng do provider cấp. Queue này thường được đặt làm `JMSReplyTo`.

~~~java
import jakarta.jms.TemporaryQueue;

// session là jakarta.jms.Session hợp lệ.
TemporaryQueue replyQueue = session.createTemporaryQueue();
request.setJMSReplyTo(replyQueue);
~~~

**Phạm vi quan trọng:** temporary queue gắn với **connection** tạo ra nó; chỉ connection ấy được phép tạo consumer để **nhận** từ queue tạm. Các connection khác có thể **gửi** message vào queue tạm. Queue tạm được dọn khi connection đóng, và nên được dọn sớm nếu không cần nữa.

~~~text
Requester: Connection A                 Responder: Connection B
  createTemporaryQueue() -> Temp-A
  receive(Temp-A) được phép                receive(Temp-A) không được phép
                                           send(Temp-A, reply) được phép
~~~

Nếu requester đóng connection ngay sau gửi request, reply về temporary queue có thể thất bại hoặc không còn nơi nhận. Với reply cần tồn tại ngay cả khi requester restart, cân nhắc destination bền vững và cơ chế tracking thay vì chỉ temporary queue.

## 4. JMSCorrelationID: nối reply với đúng request

`Message.setJMSCorrelationID(String)` cho phép client đặt correlation ID. Khi receiver đọc `getJMSCorrelationID()`, nó có thể biết reply tham chiếu request nào **theo hợp đồng ứng dụng**. JMS không tự chọn hoặc sao chép correlation cho mọi pattern request/reply.

### 4.1. Phân biệt JMSCorrelationID với JMSMessageID

| Trường | JMSMessageID | JMSCorrelationID |
| --- | --- | --- |
| Mục đích | Định danh **message này** | Liên kết message này với message/yêu cầu khác |
| Nguồn | Provider tạo khi send theo cơ chế JMS | Application chọn và đặt theo quy ước |
| Dạng thường thấy | `ID:...` (provider-generated) | `corr-...` hoặc copy `JMSMessageID` của request |
| Reply so với request | Hai message có ID riêng | Hai message có thể cùng correlation |
| Tự giống nhau? | Không | Chỉ khi phía gửi reply đặt như vậy |

Theo chuẩn, ID do provider tạo dùng tiền tố **`ID:`**. Nếu **ứng dụng tự tạo String correlation**, không đặt tiền tố `ID:`; dùng chẳng hạn `corr-` cộng UUID. Dạng `JMSCorrelationIDAsBytes` dùng cho một số provider/native clients không portable; khi không có nhu cầu tích hợp đặc thù, ưu tiên String.

### 4.2. Hai quy ước correlation thường gặp

**Quy ước A: requester tạo application correlation trước khi send.**

~~~text
Request:
  JMSMessageID      = ID:producer-001   (provider tự gán)
  JMSCorrelationID  = corr-7f20         (requester tự gán)
Reply:
  JMSMessageID      = ID:responder-888  (provider tự gán)
  JMSCorrelationID  = corr-7f20         (responder sao chép)
~~~

Ưu điểm: requester có ID từ trước, có thể tạo tracking map/selector ngay trước khi gửi. Đây là quy ước dùng trong ví dụ Spring ở phần 6.

**Quy ước B: dùng JMSMessageID của request làm correlation trên reply.**

~~~text
Request sau send:
  JMSMessageID      = ID:producer-001
  JMSCorrelationID  = null              (không bắt buộc)
Reply:
  JMSMessageID      = ID:responder-888
  JMSCorrelationID  = ID:producer-001    (copy request JMSMessageID)
~~~

Ưu điểm: không cần ứng dụng tạo riêng correlation của request. Nhược điểm: requester chỉ biết giá trị `JMSMessageID` sau khi send hoàn tất; với asynchronous send phải tuân thủ completion callback. Ngoài ra, producer có thể xin disable JMSMessageID theo khả năng provider, nên cần xác nhận chính sách trước khi chọn quy ước B.

**Không được pha lẫn hai quy ước.** Nếu requester đợi `corr-7f20` nhưng responder gửi `ID:producer-001`, response vẫn có thể đến đúng reply queue nhưng bị coi là không khớp.

### 4.3. Correlation không thay thế request ID nghiệp vụ

Một message có thể chứa:
- `JMSCorrelationID = corr-d138` để ghép request/reply hiện tại.
- Application property `orderId = order-42` để chỉ cùng đơn hàng dù có nhiều request.
- Application property `traceId = trace-e91a` để theo dõi toàn bộ luồng xuyên nhiều service.

Retry có thể tạo correlation mới trong khi vẫn là **cùng orderId hoặc business request ID**. Để chống xử lý lặp, dùng business/request identity thích hợp và lưu trạng thái idempotency; chỉ dựa vào JMSCorrelationID của một lần gửi không đủ.

## 5. Một request/reply hoàn chỉnh gắn cả ba header

Quy trình mẫu:

1. Requester chọn queue đích `orders.requests`.
2. Requester tạo hoặc lấy destination dành cho reply và gắn vào `JMSReplyTo`.
3. Requester chọn correlation ID theo quy ước A (hoặc dự định dùng request JMSMessageID theo quy ước B).
4. Requester gửi request. JMS provider điền `JMSDestination` theo queue thực tế.
5. Responder nhận request; đọc `JMSReplyTo` và thông tin correlation.
6. Responder xử lý nghiệp vụ, tạo reply **mới**, gắn correlation ID theo quy ước hai phía thống nhất.
7. Responder gửi reply tới destination trong `JMSReplyTo` của request. Provider điền `JMSDestination` cho reply.
8. Requester nhận và kiểm tra correlation + payload/status; nếu quá hạn, xử lý timeout theo chính sách nghiệp vụ.

~~~text
                              [BROKER]
Requester                         |                       Responder
   |-- Request -----------------> orders.requests ---------->|
   |   JMSDestination=orders.requests                        |
   |   JMSReplyTo=reply.destination                           |
   |   JMSCorrelationID=corr-123                             |
   |                                                          |
   |<-- Reply <---------------- reply.destination <------------|
   |    JMSDestination=reply.destination                      |
   |    JMSCorrelationID=corr-123                             |
   |                                                          |
   +-- Check correlation + result
~~~

**Hai phép kiểm tra khác nhau:**
- *Đúng địa chỉ?* Kiểm tra producer send đến queue phù hợp và provider ghi `JMSDestination` tương ứng.
- *Đúng lời đáp?* Kiểm tra `JMSCorrelationID` trên reply khớp request đang chờ.

Message đến đúng queue **vẫn có thể sai correlation**. Message mang correlation đúng **vẫn có thể bị gửi nhầm destination** và không bao giờ tới consumer mong đợi.

## 6. Ví dụ chạy được: Spring Boot + Artemis request/reply

Ví dụ dùng **Java 17+**, Spring Boot **3.x**, Jakarta JMS và Apache ActiveMQ Artemis. Một requester gửi yêu cầu `order-42`, responder xử lý rồi gửi `accepted:order-42`. Để tập trung vào header, hai thành phần nằm chung JVM nhưng trao đổi qua **broker thật**.

Requester sử dụng `JmsTemplate.sendAndReceive()`, phương thức Spring tạo temporary reply queue và đặt `JMSReplyTo` cho request. Responder chủ động đặt `JMSCorrelationID` trên reply. Chúng ta cũng đọc `JMSDestination` từ request nhận được để chứng minh provider đã điền trường này.

### 6.1. Chuẩn bị

Tạo dự án Maven từ [Spring Initializr](https://start.spring.io/), Java 17+, Group `com.example`, Artifact `jms-headers-demo`, dependency **Spring for Apache ActiveMQ Artemis** (artifact `org.springframework.boot:spring-boot-starter-artemis`). Khởi động Artemis broker bên ngoài tại `tcp://localhost:61616`, có quyền gửi và nhận trên queue `demo.header.requests`. Queue cần được provision hoặc cho phép auto-create ở broker.

Đặt hai biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD`. Tạo tệp `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=10s
# Demo tắt session caching để dễ quan sát vòng đời temporary destination.
spring.jms.cache.enabled=false
~~~

`spring.artemis.mode=native` yêu cầu broker đang chạy riêng; nó không khởi động broker tự động. `spring.jms.template.receive-timeout=10s` giới hạn thời gian chờ reply. Việc tắt cache dành cho demo; production có thể bật lại sau khi kiểm tra connection/session pooling và lifetime của temporary destinations.

Tạo tệp `src/main/java/com/example/JmsHeadersDemoApplication.java`:

~~~java
package com.example;

import java.util.UUID;
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JmsHeadersDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsHeadersDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner requester(JmsTemplate jmsTemplate) {
        return args -> {
            // Quy ước A: tự tạo correlation trước khi gửi request.
            String correlationId = "corr-" + UUID.randomUUID();

            Message reply = jmsTemplate.sendAndReceive(
                    "demo.header.requests",
                    session -> {
                        TextMessage request =
                                session.createTextMessage("order-42");
                        request.setJMSCorrelationID(correlationId);
                        return request;
                    });

            if (reply == null) {
                System.out.println("TIMEOUT");
                return;
            }

            if (!(reply instanceof TextMessage textReply)) {
                throw new IllegalStateException(
                        "Expected TextMessage as reply");
            }

            System.out.println("REPLY=" + textReply.getText());
            System.out.println("CORRELATION_MATCH="
                    + correlationId.equals(
                            textReply.getJMSCorrelationID()));
        };
    }
}

@Component
class HeaderResponder {

    private final JmsTemplate jmsTemplate;

    HeaderResponder(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @JmsListener(destination = "demo.header.requests")
    public void onRequest(Message request) throws JMSException {
        if (!(request instanceof TextMessage textRequest)) {
            throw new IllegalArgumentException(
                    "Expected TextMessage as request");
        }

        // Provider gán JMSDestination theo nơi request đã được gửi.
        System.out.println("REQUEST_DESTINATION_PRESENT="
                + (request.getJMSDestination() != null));

        // Requester (thông qua Spring) đã chỉ định nơi nhận reply.
        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            throw new IllegalArgumentException(
                    "Missing JMSReplyTo on request");
        }

        String correlationId = request.getJMSCorrelationID();
        if (correlationId == null) {
            throw new IllegalArgumentException(
                    "Missing JMSCorrelationID on request");
        }

        String payload = textRequest.getText();
        jmsTemplate.send(replyTo, session -> {
            TextMessage reply =
                    session.createTextMessage("accepted:" + payload);

            // Responder sao chép correlation theo quy ước A.
            reply.setJMSCorrelationID(correlationId);
            return reply;
        });
    }
}
~~~

Spring hỗ trợ nhận parameter raw `jakarta.jms.Message` trong `@JmsListener`, vì vậy phương thức responder có thể đọc ba header trực tiếp. Spring Boot với Artemis starter, bean `ConnectionFactory` và listener configuration hợp lệ sẽ thực hiện phần kết nối/cấp phát tài nguyên.

### 6.2. Chạy và quan sát

Trong thư mục gốc dự án Maven:

~~~bash
mvn spring-boot:run
~~~

Nếu dùng Maven wrapper trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Với broker sẵn sàng, quyền đầy đủ, queue tồn tại và không có message cũ gây nhiễu, ba dòng nghiệp vụ trên đường thành công:

~~~text
REQUEST_DESTINATION_PRESENT=true
REPLY=accepted:order-42
CORRELATION_MATCH=true
~~~

Các startup logs khác của Spring và broker cũng xuất hiện. Nếu quá 10 giây mà không có reply, requester in `TIMEOUT` thay vì hai dòng kết quả. Đây là **kết quả kỳ vọng có điều kiện**, không phải bằng chứng chương trình đã chạy trên một broker trong môi trường soạn bài.

**Giải thích:**

1. `sendAndReceive("demo.header.requests", ...)` gửi message đến request queue; `JMSDestination` của request được provider gán.
2. `sendAndReceive` tạo temporary queue, đặt nó làm `JMSReplyTo` và chờ reply; requester không tự đặt ReplyTo trong callback.
3. Requester tự đặt `JMSCorrelationID` là String bắt đầu `corr-`. Giá trị thực tế có UUID khác nhau mỗi lần chạy.
4. Responder lấy `request.getJMSReplyTo()`, tạo `TextMessage` mới và đặt correlation giống request.
5. `jmsTemplate.send(replyTo, ...)` đưa reply tới temporary queue. `JMSDestination` của reply là destination dùng để gửi reply.
6. Requester nhận message và kiểm tra `correlationId.equals(reply.getJMSCorrelationID())`.

Cũng có thể viết `@JmsListener` trả về dữ liệu và dùng `@SendTo` để Spring quản lý reply; khi cần kiểm soát correlation/headers chính xác, cách gửi thủ công trong ví dụ làm quy ước rõ hơn.

## 7. Tự gán header trong JMS classic API và JMS simplified API

### 7.1. Classic API với Message

Với một `Session` hợp lệ, có thể tạo request/reply destination rồi đặt hai header client-owned trước khi send:

~~~java
import java.util.UUID;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TextMessage;

// session đã được tạo qua ConnectionFactory/Connection.
Queue requestQueue = session.createQueue("orders.requests");
TemporaryQueue replyQueue = session.createTemporaryQueue();
String correlationId = "corr-" + UUID.randomUUID();

TextMessage request = session.createTextMessage("order-42");
request.setJMSReplyTo(replyQueue);
request.setJMSCorrelationID(correlationId);

try (MessageProducer producer = session.createProducer(requestQueue)) {
    producer.send(request);
}
~~~

Đây là đoạn mã **không độc lập** vì cần kết nối/session từ provider. Nếu muốn nhận từ replyQueue bằng classic API, consumer phải thuộc **connection đã tạo temporary queue** và cần `connection.start()` trước khi chờ bằng `receive(timeout)`. Một response đến từ connection khác có thể **gửi** vào temp queue đó.

### 7.2. Simplified API với JMSProducer

Trong API `JMSContext`, producer cho phép thiết lập header trực tiếp:

~~~java
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TemporaryQueue;

// context là JMSContext hợp lệ.
Queue requests = context.createQueue("orders.requests");
TemporaryQueue replies = context.createTemporaryQueue();

context.createProducer()
       .setJMSReplyTo(replies)
       .setJMSCorrelationID("corr-42")
       .send(requests, "order-42");
~~~

`JMSProducer.setJMSReplyTo(...)` và `JMSProducer.setJMSCorrelationID(...)` áp dụng cho những message producer đó gửi. Các giá trị header đặt trên `JMSProducer` **ghi đè** giá trị tương ứng đã đặt trực tiếp trên `Message`. Đừng nhầm với `JMSDestination`: trường này vẫn do provider gán theo destination của thao tác send.

### 7.3. Dùng Spring MessagePostProcessor

Để gửi payload đã convert và thêm application correlation (ví dụ gửi một chiều):

~~~java
import java.util.UUID;
import org.springframework.jms.core.JmsTemplate;

// jmsTemplate là bean đã được inject.
String correlationId = "corr-" + UUID.randomUUID();

jmsTemplate.convertAndSend(
        "orders.requests",
        "order-42",
        message -> {
            message.setJMSCorrelationID(correlationId);
            return message;
        });
~~~

Đây là một **đoạn service minh họa**, cần bean `JmsTemplate`. Nó **không tự tạo reply destination**, bởi `convertAndSend` không phải mô hình request/reply hoàn chỉnh. Có thể đặt `JMSReplyTo` trong post-processor khi đã có `Destination` và cơ chế đợi reply thích hợp, hoặc dùng `sendAndReceive` để Spring quản lý destination tạm.

## 8. Correlation ID và message selector

Khi nhiều requester dùng cùng **reply queue cố định**, một chiến lược là tạo consumer với selector cho `JMSCorrelationID` mong muốn. Ví dụ với JMS classic API:

~~~java
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;

// session, sharedReplyQueue, correlationId đã có.
// correlationId sinh từ UUID nên không chứa ký tự nháy đơn.
String selector = "JMSCorrelationID = '" + correlationId + "'";
MessageConsumer consumer =
        session.createConsumer(sharedReplyQueue, selector);
~~~

Đây là đoạn trích không độc lập: `consumer.receive(10_000)` cần connection đã `start()`, còn selector phải được hủy tài nguyên đúng lúc.

**Giới hạn rất quan trọng:** trong JMS selector, các header chuẩn có thể tham chiếu là `JMSDeliveryMode`, `JMSPriority`, `JMSMessageID`, `JMSTimestamp`, `JMSCorrelationID` và `JMSType`. **Không thể coi `JMSDestination` hoặc `JMSReplyTo` là hai selector header chuẩn.**

~~~text
JMSCorrelationID = 'corr-123'     -- selector có thể hợp lệ
JMSReplyTo = 'orders.responses'   -- không phải selector header chuẩn
JMSDestination = 'orders.req'     -- không phải selector header chuẩn
~~~

Các dòng là **minh họa cú pháp selector**, không phải lệnh SQL cơ sở dữ liệu. Việc chọn queue/topic thực hiện khi tạo consumer trên destination. Nếu selector lấy giá trị từ dữ liệu không đáng tin, phải tránh tạo biểu thức sai/khả năng injection bằng cách tự tạo correlation ID dạng an toàn hoặc escape string literal đúng quy tắc.

Lưu ý: dùng selector theo từng request có thể làm tăng số consumer và overhead broker khi lưu lượng lớn. Với nhiều request song song, cân nhắc một dispatcher trên shared reply queue, một temporary queue cho requester, hoặc quản lý pending requests bằng map correlation và giới hạn tài nguyên.

## 9. Những vấn đề request/reply thường gặp trong thực tế

### 9.1. Timeout không có nghĩa responder chưa xử lý

Requester đã gửi request thành công nhưng quá hạn nhận reply có thể do responder chậm, reply bị thất lạc, đích trả lời không còn, consumer không chạy hoặc route sai. Không nên retry vô điều kiện vì responder có thể đã commit nghiệp vụ. Dùng **business request ID** ổn định và xử lý idempotent để tránh thao tác lặp khi redelivery/retry.

### 9.2. Transaction có thể chặn request cho đến commit

Nếu request đang nằm trong transaction chưa commit, nó có thể chưa được chuyển tới consumer. Một caller giữ transaction đó rồi **chờ reply trước khi commit** có thể tự gây timeout. Thiết kế ranh giới transaction rõ: commit thao tác gửi trước giai đoạn chờ phản hồi, hoặc dùng orchestration bất đồng bộ.

JMS transaction không tự làm việc ghi database của responder và gửi reply thành một atomic transaction xuyên hai hệ thống. Cân nhắc outbox/inbox, xử lý bù hoặc JTA/XA khi thực sự cần và môi trường hỗ trợ.

### 9.3. Reply đến muộn hoặc đến nhiều lần

Nếu requester timeout và bỏ pending request nhưng reply đến sau đó, correlation ID chỉ nói nó thuộc request cũ; ứng dụng phải quyết định giữ, bỏ, log hoặc xử lý bù. Nếu responder redeliver request và gửi reply nhiều lần, requester phải biết cách chống duplicate. `JMSCorrelationID` tự nó **không bảo đảm exactly-once business processing**.

### 9.4. Bảo mật và tương thích provider

- Không đặt token, password hoặc dữ liệu cá nhân nhạy cảm vào correlation/header log.
- Kiểm tra ACL send/consume cho request queue và reply destination; header `JMSReplyTo` không phải proof of authorization.
- Không cho phép một bên không tin cậy tùy ý ép responder gửi dữ liệu nhạy cảm tới một destination ngoài phạm vi cho phép.
- Destination object có thể provider-specific; JMS không tự đảm bảo cross-broker protocol interoperability. Khi bridge message giữa các provider, cần kiểm tra cách ánh xạ `JMSReplyTo` và `JMSCorrelationID`. Đặc biệt, provider không bắt buộc giữ foreign `Destination` object không tương thích.

## 10. Bảng chẩn đoán lỗi

| Triệu chứng | Kiểm tra trước | Kết luận / hướng xử lý |
| --- | --- | --- |
| Requester gửi được nhưng responder không nhận | Queue/topic gửi thực tế, quyền, tên destination, listener status | Kiểm tra `JMSDestination` và queue broker; đừng sửa `JMSReplyTo` để khắc phục route của request |
| Responder nhận request nhưng không biết trả lời đâu | `request.getJMSReplyTo()` null? | Chọn hợp đồng một chiều hay request/reply; cung cấp reply destination nếu cần |
| Reply không đến requester | Responder gửi tới đâu? Reply destination còn tồn tại? | Đối chiếu `JMSReplyTo` của request với `JMSDestination` của reply |
| Reply vào đúng queue nhưng ứng dụng báo không khớp | Giá trị `JMSCorrelationID` của request/reply | Kiểm tra hai phía dùng cùng quy ước A hoặc B |
| Requester A nhận response của B | Shared reply queue, competing consumers, selector | Dùng temp queue, selector hoặc dispatcher đúng ownership |
| Selector không được chấp nhận | Có dùng `JMSReplyTo`/`JMSDestination` trong expression? | Chỉ sử dụng header/property được selector hỗ trợ |
| Client dừng, temporary reply queue biến mất | Lifetime của connection đã tạo temp queue | Dùng reply queue bền vững nếu cần nhận sau khi restart |
| Timeout ngẫu nhiên, xử lý lặp | Redelivery, retry, transaction, backlog | Theo dõi log/metrics; dùng business idempotency và deadline |
| Header correlation có tiền tố `ID:` do ứng dụng tự sinh | Nhầm application ID với JMSMessageID | Dùng `corr-...` cho application correlation; chỉ copy `ID:...` nếu theo quy ước B |
| `JmsTemplate.sendAndReceive()` chờ vô hạn | Receive timeout chưa cấu hình phù hợp | Đặt receive timeout hữu hạn và thiết kế xử lý `null` |

## 11. Ngộ nhận hay gặp

1. **“JMSDestination và JMSReplyTo cùng là destination nên có thể hoán đổi.”** Sai. Một bên là đích gửi hiện tại, một bên là địa chỉ reply tùy chọn.
2. **“setJMSDestination() chọn queue.”** Sai. Thao tác `send(...)` mới chỉ định queue/topic được gửi.
3. **“Broker nhìn JMSReplyTo và tự gửi reply.”** Sai. Responder hoặc lớp ứng dụng/framework được cấu hình phải tạo reply.
4. **“Correlation tự sinh và tự khớp.”** Sai. Ứng dụng phải định nghĩa rõ quy ước copy/tạo ID.
5. **“Reply có JMSMessageID giống request.”** Sai. Request và reply là hai message khác nhau; dùng correlation để liên kết.
6. **“Có correlation đúng thì message tự đến đúng client.”** Sai. Destination và cách consume/dispatch vẫn phải đúng.
7. **“Dùng cùng shared reply queue, client nào cũng có thể nhận rồi bỏ message không thuộc mình.”** Nguy hiểm. Message bị lấy khỏi queue có thể khiến requester đúng không bao giờ thấy.
8. **“Temporary queue thuộc session, nên connection khác có thể nhận.”** Sai. Quy tắc tiêu thụ gắn với connection đã tạo temporary destination.
9. **“JMSReplyTo khác null nghĩa là response bắt buộc và luôn thành công.”** Sai. Đó là gợi ý về nơi có thể trả lời, không phải cam kết về nghiệp vụ.
10. **“TIMEOUT = xử lý chắc chắn thất bại.”** Sai. Cần phân biệt delivery, processing và response.

## 12. Câu hỏi tự kiểm tra

**1.** Request gửi tới `orders.requests` nhưng khai báo `JMSReplyTo=orders.responses`. `JMSDestination` của request là gì?

**Đáp án:** `orders.requests`. Chỉ **reply message mới** được gửi vào `orders.responses` nếu responder quyết định gửi.

**2.** Reply có `JMSMessageID=ID:reply-9`; request có `JMSCorrelationID=corr-12`. Theo quy ước A, responder đặt correlation của reply bằng gì?

**Đáp án:** `corr-12`, không phải `ID:reply-9`.

**3.** Nếu chọn quy ước B (copy request JMSMessageID), lúc nào requester biết ID cần match?

**Đáp án:** Sau khi send request hoàn tất (hoặc sau callback hoàn tất với asynchronous send).

**4.** Có dùng selector `JMSReplyTo = 'my-replies'` theo JMS chuẩn không?

**Đáp án:** Không. Chỉ một tập header được chuẩn cho selector; `JMSCorrelationID` có thể dùng, còn `JMSReplyTo`/`JMSDestination` không nằm trong tập đó.

**5.** Vì sao temporary queue phù hợp request/reply nhưng dễ thất bại khi requester restart?

**Đáp án:** Nó gắn với connection đã tạo ra và bị dọn theo lifecycle connection; không phải destination lưu trữ reply dài hạn độc lập với requester.

**6.** Khi response có correlation đúng nhưng payload báo lỗi nghiệp vụ, có coi giao dịch thành công không?

**Đáp án:** Không. Correlation chỉ là liên kết; trạng thái thành công/thất bại phải kiểm tra trong payload, contract và transaction nghiệp vụ.

## Tài liệu đối chiếu

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — mục 3.4 message headers, 2.16 request/reply, 6.2.2 temporary destinations, 7.6 setting message headers.
- [Jakarta Messaging 3.1 API: Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message) — `getJMSDestination`, `getJMSReplyTo`, `getJMSCorrelationID` và các setters.
- [Jakarta EE Tutorial: Messaging Concepts](https://jakartaee.github.io/jakartaee-documentation/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html) — ví dụ request/reply, reply destination và correlation.
- [Spring Framework: Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate` và `MessageCreator`.
- [Spring Framework: Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — nhận raw JMS Message và response handling.
- [Spring Framework 6.2 Javadoc: JmsTemplate.sendAndReceive](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html) — tạo temporary reply queue và set `JMSReplyTo`.
- [Spring Boot 3.4: JMS](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html) — Artemis mode native và JMS auto-configuration.
