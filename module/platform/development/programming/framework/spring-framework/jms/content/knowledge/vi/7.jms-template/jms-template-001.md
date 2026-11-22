# Vai trò JmsTemplate trong quản lý thao tác và tài nguyên JMS

## 1. JmsTemplate giải quyết vấn đề gì?

`JmsTemplate` là lớp trung tâm trong `org.springframework.jms.core` của **Spring Framework JMS**. Nó cung cấp một **template** cho việc gửi message và nhận message **đồng bộ** qua Jakarta Messaging/JMS, để mã nghiệp vụ tập trung vào **gửi gì, tới đâu, nhận gì**, thay vì lặp lại việc tạo/đóng `Connection`, `Session`, `MessageProducer`, `MessageConsumer`, xử lý `JMSException` và điều phối resource với transaction của Spring.

Mục tiêu bài học:

1. Nhận diện **phần việc Spring làm hộ** và **phần ứng dụng vẫn phải chịu trách nhiệm**.
2. Hiểu vòng đời `ConnectionFactory → Connection → Session → Producer/Consumer` khi dùng `JmsTemplate`.
3. Phân biệt `send`/`receive`, `convertAndSend`/`receiveAndConvert`, `MessageCreator`, `MessagePostProcessor` và callback cấp thấp.
4. Biết tác động của `CachingConnectionFactory`, transaction, acknowledgement, timeout và ngoại lệ.
5. Thực hành ví dụ Spring Boot 3.x + Apache ActiveMQ Artemis, có mã chạy, lệnh và kết quả kiểm tra.

**Định nghĩa ngắn:** `JmsTemplate` **không phải broker**, không tự lưu message thay broker và không thay thế JMS provider. Nó là lớp ứng dụng của Spring, dùng `ConnectionFactory` để thao tác với provider, đồng thời quản lý resource một cách nhất quán.

### 1.1. Trước và sau khi dùng template

Với Jakarta Messaging API cổ điển (classic API), một thao tác send về cơ bản đi qua:

~~~text
ConnectionFactory
     │ createConnection()
     ▼
Connection
     │ createSession(...)
     ▼
Session
     │ createProducer(destination), createTextMessage(...)
     ▼
MessageProducer
     │ send(message)
     ▼
JMS provider ──────► Broker

finally: close MessageProducer, Session, Connection
~~~

Với Spring JMS:

~~~text
BusinessService
     │
     │ jmsTemplate.convertAndSend("orders.queue", orderId)
     ▼
JmsTemplate
     ├── lấy Session/Connection từ ConnectionFactory hoặc Spring transaction
     ├── tạo / dùng MessageProducer
     ├── tạo JMS Message (thông qua MessageConverter)
     ├── gửi message, áp dụng cấu hình QoS phù hợp
     ├── dịch JMSException sang Spring JmsException (unchecked)
     └── giải phóng resource theo đúng kiểu (đóng hoặc trả về cache/pool)
                    │
                    ▼
             JMS provider ───► Broker
~~~

**Điểm quan trọng:** “template giải phóng resource” không nhất thiết có nghĩa mỗi lần gọi đều làm **physical TCP connection đóng**. Nếu `ConnectionFactory` được bọc bởi `CachingConnectionFactory` hoặc pool, lệnh đóng logic của template có thể trả handle về cache/pool để tái sử dụng.

## 2. Phân công trách nhiệm theo tầng

| Thành phần | Trách nhiệm chính | Không chịu trách nhiệm cho |
| --- | --- | --- |
| `ConnectionFactory` (Jakarta JMS API) | Cung cấp `Connection` tới JMS provider; cấu hình xác thực, endpoint và các tham số provider | Quyết định nội dung message nghiệp vụ |
| `Connection` | Liên kết client với provider/broker, tạo `Session`; classic consumer cần connection được start | Tự đảm bảo mọi message xử lý đúng |
| `Session` | Tạo message, producer, consumer, queue/topic object; scope ack/transaction của JMS | Trở thành một đối tượng dùng đồng thời an toàn ở mọi thread |
| `MessageProducer` | Gửi message tới destination, áp dụng một số QoS | Lưu trữ message lâu dài phía broker |
| `MessageConsumer` | Nhận message; đồng bộ hoặc đăng ký listener tùy API | Bảo đảm business handler thành công |
| `JmsTemplate` | Bọc thao tác send/receive đồng bộ, vòng đời resource, callback, conversion, error translation | Hosting broker, tự retry mọi lỗi, tự bảo đảm end-to-end exactly-once |
| `MessageConverter` | Chuyển Java payload ⇄ JMS `Message` theo quy tắc converter | Tự suy schema bất kỳ không được cấu hình |
| Listener container / `@JmsListener` | Quản lý luồng consume bất đồng bộ, session/consumer dài hạn và lời gọi listener | Thay thế nhu cầu xác định transaction, DLQ, idempotency |
| JMS provider / broker | Triển khai giao thức/semantics JMS, delivery, store/routing và security | Tự hiểu nghiệp vụ order/payment của ứng dụng |

Bản thân **JMS chỉ là API và semantics**; `JmsTemplate` cần một provider như **Apache ActiveMQ Artemis**, ActiveMQ Classic, IBM MQ... và một broker/service thực. Đừng coi việc thêm dependency `spring-jms` mà không có JMS provider là một hệ thống gửi message hoàn chỉnh.

## 3. Gửi message không cần tự quản lý resource

### 3.1. Cách làm thủ công: rất dễ lặp mã

Mã dưới đây là **phương thức minh họa**, không phải chương trình độc lập. `factory` là một `jakarta.jms.ConnectionFactory` đã cấu hình để kết nối provider. `Connection` và `Session` mở/đóng theo try-with-resources, `MessageProducer` đóng bằng try-with-resources. Đây là cách thường phải thực hiện khi không có Spring:

~~~java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

static void sendManually(ConnectionFactory factory, String body)
        throws JMSException {
    try (Connection connection = factory.createConnection();
         Session session =
             connection.createSession(false, Session.AUTO_ACKNOWLEDGE)) {
        Queue queue = session.createQueue("orders.queue");
        try (MessageProducer producer = session.createProducer(queue)) {
            TextMessage message = session.createTextMessage(body);
            producer.send(message);
        }
    }
}
~~~

Giải thích:

- `createConnection()` cần provider phù hợp, credentials và network; có thể thất bại.
- `createSession(false, Session.AUTO_ACKNOWLEDGE)` tạo session không giao dịch; acknowledgement mode chủ yếu liên quan đến **message nhận**.
- `session.createQueue("orders.queue")` tạo đối tượng destination theo tên, **không tự đảm bảo broker đã provision queue**; chính sách auto-create phụ thuộc provider.
- Gửi message **không cần** `connection.start()`; start liên quan tới việc cho phép phân phối tới consumer classic API.
- Có nhiều kiểu exception `JMSException` checked phải xử lý hoặc khai báo.
- Nếu code nghiệp vụ có hàng chục thao tác gửi, việc tự viết phần mở/đóng/catch nhiều lần làm tăng nguy cơ xử lý thiếu và sai.

### 3.2. Cách dùng `JmsTemplate`

Khi Spring đã tạo bean `JmsTemplate` từ `ConnectionFactory`:

~~~java
import org.springframework.jms.core.JmsTemplate;

class OrderPublisher {
    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void sendOrder(String orderId) {
        jmsTemplate.convertAndSend("orders.queue", orderId);
    }
}
~~~

Đây là mảnh code service, không có `main`. Spring lo luồng tạo/lấy JMS session, convert `String` thành `TextMessage` (với converter mặc định), gửi rồi cleanup. Mã ứng dụng **không gọi `Connection.close()` hay `Session.close()`** trong mỗi send.

**Tối giản không có nghĩa mất kiểm soát:** khi cần thêm header/property hoặc tạo dạng message cụ thể, dùng các callback bên dưới.

## 4. Ba lối gửi phổ biến: convertAndSend, send và post-processor

### 4.1. `convertAndSend` — để converter tạo message

~~~java
jmsTemplate.convertAndSend("orders.queue", "order-42");
~~~

Với `SimpleMessageConverter` mặc định, `String` được đóng gói thành `TextMessage`. Từ phía caller, đây là lời gọi gọn nhất nếu payload thuộc kiểu mà converter hiểu.

Các mapping thường gặp của `SimpleMessageConverter`:

| Java payload | JMS message thường tạo |
| --- | --- |
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` | `MapMessage` (giá trị trong tập kiểu JMS hỗ trợ) |
| `Serializable` | `ObjectMessage` (khi không khớp loại trên) |

Không mặc định mọi POJO đều biến thành JSON. Nếu muốn JSON, Avro, Protobuf... thì cần **`MessageConverter` phù hợp** hoặc chủ động serialize. `ObjectMessage` sử dụng Java serialization, có những rủi ro an ninh và tương thích phiên bản; không deserialize payload Java từ nguồn không tin cậy một cách tùy tiện.

### 4.2. `send` + `MessageCreator` — tự tạo JMS Message

`MessageCreator` nhận `Session` do `JmsTemplate` cấp. Tại đó ứng dụng tạo message, đặt header/property cần thiết:

~~~java
import jakarta.jms.TextMessage;

jmsTemplate.send("orders.queue", session -> {
    TextMessage message = session.createTextMessage("order-42");
    message.setStringProperty("eventType", "ORDER_CREATED");
    message.setJMSCorrelationID("request-42");
    return message;
});
~~~

Đây là **callback sống trong phạm vi một thao tác**. Không giữ `Session`/`MessageProducer`/`Message` trong cache dài hạn để dùng sau khi callback kết thúc, vì Spring có thể đã trả session về pool, đóng resource hoặc có transaction khác.

`MessageCreator` thích hợp khi cần tạo:

- `TextMessage`, `BytesMessage`, `MapMessage`, `StreamMessage`, `ObjectMessage`.
- Message property do nghiệp vụ định nghĩa, như `eventType`, `tenantId` hoặc `schemaVersion`.
- Header JMS như `JMSCorrelationID` hay `JMSReplyTo`.
- Dạng body không thể biểu diễn bằng converter mặc định.

Lưu ý `JMSMessageID`, `JMSTimestamp` là header thường do provider cập nhật khi send. Không viết logic coi các giá trị do developer tự gán trước send luôn được giữ nguyên; xem JMS API và provider configuration.

### 4.3. `convertAndSend` + `MessagePostProcessor`

Nếu muốn dùng converter nhưng bổ sung header/property sau khi convert:

~~~java
jmsTemplate.convertAndSend(
    "orders.queue",
    "order-42",
    message -> {
        message.setStringProperty("eventType", "ORDER_CREATED");
        message.setJMSCorrelationID("request-42");
        return message;
    }
);
~~~

Trình tự là:

~~~text
Object Java
   │ MessageConverter.toMessage(value, session)
   ▼
JMS Message (ví dụ TextMessage)
   │ MessagePostProcessor.postProcessMessage(message)
   ▼
JMS Message đã có thêm headers/properties
   │ MessageProducer.send(...)
   ▼
Broker
~~~

`MessagePostProcessor` **không phải** consumer, không tự thực hiện tác vụ bất đồng bộ sau khi broker nhận message. Nó chạy **trước khi gửi** để chỉnh message đã chuyển đổi.

### 4.4. Chọn cách nào?

| Nhu cầu | Chọn |
| --- | --- |
| Gửi `String`/`byte[]`/payload đơn giản theo converter đang cấu hình | `convertAndSend` |
| Gửi payload đơn giản nhưng cần thêm property/header | `convertAndSend(..., MessagePostProcessor)` |
| Chủ động điều khiển body type/phương thức ghi JMS | `send(..., MessageCreator)` |
| Thực hiện nhiều thao tác dùng chung session hoặc producer trong một callback | `execute(SessionCallback)` / `execute(ProducerCallback)` |
| Muốn giao tiếp bất đồng bộ lâu dài | Producer vẫn dùng template; phía nhận ưu tiên listener container/`@JmsListener` |

## 5. Nhận message đồng bộ và giới hạn của JmsTemplate

Các phương thức chính:

- `receive("orders.queue")` trả về **`jakarta.jms.Message`** hoặc `null` khi hết hạn đợi/không có message theo cấu hình.
- `receiveAndConvert("orders.queue")` trả về **Java object đã convert**, hoặc `null` khi không nhận được message.
- `receiveSelected("orders.queue", "eventType = 'ORDER_CREATED'")` dùng **JMS selector** để lọc theo header/property được selector hỗ trợ; không dùng selector để truy vấn arbitrary JSON trong body.
- `receiveAndConvert()`/`receive()` không tham số dùng default destination đã được cấu hình, nếu có.

Ví dụ:

~~~java
Object result = jmsTemplate.receiveAndConvert("orders.queue");
if (result instanceof String text) {
    System.out.println("Received: " + text);
} else if (result == null) {
    System.out.println("Receive timeout");
} else {
    throw new IllegalStateException("Unexpected payload type: " +
            result.getClass().getName());
}
~~~

### 5.1. `receive()` có thể chặn thread

Synchronous receive **chặn thread gọi** theo receive timeout đã cấu hình. Nếu ứng dụng HTTP gọi `receive()` mà để chờ vô hạn, request có thể giữ thread, session và connection lâu, gây cạn thread/pool dưới tải.

Giá trị `JmsTemplate#setReceiveTimeout(long)` có đơn vị **milliseconds**:

| Giá trị | Hành vi |
| --- | --- |
| `0` | Chờ vô hạn cho đến khi có message/lỗi/đóng connection; tránh cho endpoint nhạy độ trễ |
| Số dương, ví dụ `5000` | Chờ tối đa khoảng 5 giây |
| Số âm, ví dụ `-1` | Không đợi, kiểm tra message sẵn có ngay (`receiveNoWait()`) |

Với Spring Boot:

~~~properties
spring.jms.template.receive-timeout=5s
~~~

Từ đó `receive(...)` được giới hạn khoảng 5 giây, sau đó trả `null` nếu không có message. **Không nhầm** nhận `null` do timeout với payload có body `null`: muốn phân biệt rõ, ưu tiên dùng raw `receive` và xác định hợp đồng message.

**Đừng viết listener chạy bằng vòng lặp vô hạn gọi `receive()` không có kiểm soát** trong Spring Boot nếu framework đã có hạ tầng listener container cho consumer bất đồng bộ.

### 5.2. Vì sao `@JmsListener` không đồng nghĩa `JmsTemplate.receive`?

| Tiêu chí | `JmsTemplate.receive` | `@JmsListener` / listener container |
| --- | --- | --- |
| Kiểu xử lý | Pull đồng bộ | Consumer được container duy trì, gọi handler khi có message |
| Thread | Thread của caller | Thread/executor của listener container |
| Session/consumer | Template tạo/lấy trong phạm vi thao tác | Container quản lý vòng đời lâu hơn và concurrency |
| Timeout | Caller đặt receive timeout | Container có polling/receive settings và lifecycle riêng |
| Lựa chọn phổ biến | Kiểm thử, batch có thời hạn, công cụ vận hành, một lượt request–reply | Service xử lý message liên tục |
| Retry/transaction | Phụ thuộc cấu hình template, transaction manager và business logic | Phụ thuộc cấu hình listener transaction/ack và broker redelivery |

**Tóm lại:** Spring JMS có hai nhánh bổ trợ nhau: `JmsTemplate` chủ yếu để **gửi và nhận đồng bộ**, còn **listener containers** để nhận bất đồng bộ. Không có chuyện JmsTemplate tự tạo một listener daemon sau khi gọi `convertAndSend`.

## 6. Cơ chế quản lý resource: Spring làm gì bên trong?

### 6.1. Một thao tác gửi

~~~text
1. Service gọi jmsTemplate.send(...)
2. Template tìm Session đang gắn với transaction Spring, nếu có
3. Nếu chưa có: lấy Connection từ ConnectionFactory và tạo Session theo config
4. Tạo MessageProducer cho destination
5. Gọi MessageCreator / converter / post-processor để tạo message
6. Gửi message bằng producer
7. Với local transacted session do template tự tạo:
   commit/rollback theo logic thao tác của template
8. Đóng producer và giải phóng Session/Connection phù hợp
   - session/connection độc lập: close handle
   - pooled/cached/transaction-bound: trả hoặc giữ theo wrapper/manager
9. Nếu Jakarta JMS báo lỗi: dịch sang Spring JmsException (unchecked)
~~~

Sơ đồ trên là **mô hình khái niệm**, không mô tả mọi call nội bộ giống nhau ở mọi phiên bản/provider. Ví dụ, transaction manager có thể cung cấp session đã được bind với thread; khi đó template **không được tự đóng/commit tài nguyên đang thuộc transaction bên ngoài** giữa chừng.

### 6.2. Một thao tác nhận

~~~text
1. Service gọi jmsTemplate.receive("orders.queue")
2. Template lấy Connection/Session tương thích
3. Resolve destination và tạo MessageConsumer
4. Đảm bảo connection có thể nhận message
5. Consumer.receive(timeout) / receiveNoWait()
6. Trả Message hoặc null
7. Ack/commit theo session, transaction và template config
8. Đóng consumer, giải phóng handle còn lại
~~~

Trong **AUTO_ACKNOWLEDGE** không giao dịch, việc receive hoàn tất có thể được ack trước khi code business sau `receive()` hoàn thành. Nếu business code sau khi nhận bị lỗi, message **không mặc nhiên** được broker redeliver. Đây là lý do xử lý quan trọng liên tục thường nên đặt trong listener container có transaction/redelivery policy rõ ràng.

### 6.3. Bảng quyền sở hữu resource

| Resource | Ai tạo/nhận trong thao tác template? | Có tự đóng thủ công không? |
| --- | --- | --- |
| `ConnectionFactory` | Bean do cấu hình Spring/Boot/JNDI cung cấp | Không; lifecycle do application context/hạ tầng quản lý |
| `Connection` | Template lấy từ factory, hoặc transaction manager giữ | Caller **không** tự đóng connection của template |
| `Session` | Template tạo/lấy; hoặc transaction-bound session | Caller **không** tự đóng session được truyền vào callback |
| `MessageProducer` | Template tạo/lấy cho send | Template dọn đúng scope |
| `MessageConsumer` | Template tạo/lấy cho receive | Template dọn đúng scope |
| `QueueBrowser` | `browse(...)` và callback browser | Template quản lý browser trong phạm vi callback |
| `Message` | Provider/Session tạo, truyền lại cho caller | Là dữ liệu JMS; phải tôn trọng message state, type và lifetime của session liên quan |
| Tài nguyên tự tạo trong callback bằng raw API | Caller tự tạo ngoài phần framework biết tới | **Caller phải xác định và đóng** đúng cách, tránh rò resource |

**Đừng truyền `Session` từ callback sang một thread khác để dùng sau:** JMS `Session` là ngữ cảnh đơn luồng. Việc template hỗ trợ nhiều thread gọi **không** cho phép nhiều thread thao tác đồng thời trên một session cụ thể.

### 6.4. `SessionCallback` và `ProducerCallback`

Khi API `send/receive` thông thường chưa đủ, template cho phép thực hiện logic trong callback nhận resource đã được mở hợp lệ. Ví dụ **mảnh code minh họa**, đặt trong service có `JmsTemplate jmsTemplate`:

~~~java
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import org.springframework.jms.core.ProducerCallback;

Integer sentCount = jmsTemplate.execute(
    (ProducerCallback<Integer>) (session, producer) -> {
        Queue queue = session.createQueue("demo.batch");
        for (int i = 1; i <= 3; i++) {
            Message message = session.createTextMessage("item-" + i);
            producer.send(queue, message);
        }
        return 3;
    }
);
~~~

**Lưu ý quan trọng về overload:** `execute(ProducerCallback<T>)` tạo producer theo cấu hình của template và callback có quyền gửi; với producer không gắn destination cố định, mẫu `producer.send(queue, message)` là hợp lệ. Đoạn trên không phải chương trình độc lập; cần JMS provider, imports và bean đã cấu hình. Spring quản lý lifecycle của session/producer được cấp cho callback; không đóng chúng bên trong callback.

Nếu muốn có nhiều send thành một **transaction nguyên tử**, đừng mặc định “một callback execute” tự tạo transaction xuyên ba send. Cần thiết lập transactional session hoặc transaction manager và kiểm chứng commit/rollback theo cấu hình; callback chủ yếu là cách **dùng chung phạm vi resource**.

`SessionCallback<T>` chỉ cấp `Session`, dành cho thao tác cần trực tiếp điều khiển session; `ProducerCallback<T>` cấp cả `Session` và `MessageProducer`. Với thao tác gửi đơn giản, `convertAndSend` hoặc `send(MessageCreator)` rõ ràng hơn.

## 7. CachingConnectionFactory: tối ưu resource nhưng không đổi nghĩa nghiệp vụ

JMS thao tác thường xuyên có thể phải tạo nhiều object trung gian. Spring cung cấp một số cách giảm chi phí khởi tạo:

### 7.1. `SingleConnectionFactory`

`SingleConnectionFactory` là wrapper giữ một **physical connection dùng chung** và thường lờ các lời gọi `close()` logic từ client, đến khi wrapper thực sự bị đóng/reset. Nó hữu ích trong một số môi trường standalone/test, nhưng bản thân nó **không cache mọi session/producer/consumer**.

### 7.2. `CachingConnectionFactory`

`CachingConnectionFactory` mở rộng `SingleConnectionFactory`, thêm cache:

- `Session` theo loại session/acknowledge mode.
- `MessageProducer` theo destination trong session.
- `MessageConsumer` theo destination, selector, `noLocal`, durable subscription name và một số thuộc tính cần thiết.
- Các producer/consumer phục vụ **TemporaryQueue/TemporaryTopic** không được cache theo chính sách của Spring.

Ví dụ (chỉ minh họa cấu hình bean, không áp dụng cùng lúc với auto-config khác một cách mù quáng):

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.connection.CachingConnectionFactory;

@Bean
CachingConnectionFactory cachingConnectionFactory(
        ConnectionFactory providerConnectionFactory) {
    CachingConnectionFactory cache =
            new CachingConnectionFactory(providerConnectionFactory);
    cache.setSessionCacheSize(10);
    cache.setCacheProducers(true);
    cache.setCacheConsumers(false);
    return cache;
}
~~~

**Đây là mảnh cấu hình**: trong một Spring Boot app đã auto-config connection factory, tự định nghĩa bean có thể gây vòng phụ thuộc hoặc ghi đè ý định auto-config nếu không đặt tên/qualifier rõ. Ưu tiên dùng **property cấu hình Boot** khi Boot đang quản lý factory, ví dụ:

~~~properties
spring.jms.cache.session-cache-size=5
~~~

Một số phiên bản Spring Boot bọc native connection factory bằng `CachingConnectionFactory` theo mặc định khi chưa bật native pooling. Kiểm tra cấu hình thực tế và log/bean graph của ứng dụng, không giả định mọi môi trường tự động có cùng topology.

### 7.3. Điều không được hiểu nhầm

- `JmsTemplate` **thread-safe sau khi cấu hình xong**, nên có thể dùng **singleton bean** được inject vào nhiều service/thread. Không đổi các thuộc tính như timeout/default destination liên tục trong runtime để tạo trạng thái “theo request” trên một singleton.
- `Session` **không thread-safe theo cách sử dụng thông thường của JMS**; đừng giữ `Session` được callback cấp để chia sẻ cho các thread.
- Cache/pool làm giảm chi phí tạo resource, **không** biến send thành exactly-once; cũng không đảm bảo listener xử lý xong.
- `session-cache-size` không tương đương “chính xác tối đa N session toàn app”. Spring cache theo mode; số lượng resource thực có thể cao hơn, và khi tải đỉnh còn có session tạm ngoài cache.
- Cache consumer có thể ảnh hưởng selector, durable subscription và cấu hình broker/prefetch. Với listener container vốn đã giữ consumer và có chiến lược cache riêng, không tự bật cache consumer trên mọi wrapper.
- Pool có giới hạn số connection/session và chính sách timeout riêng; phải quan sát số connection, consumer, session và lỗi exhaustion của provider.

Sơ đồ khái niệm:

~~~text
Thread A ─┐
Thread B ─┼─> singleton JmsTemplate
Thread C ─┘          │
                    ▼
             ConnectionFactory
                    │
                    ├── native provider ConnectionFactory
                    │
                    └── (có thể) CachingConnectionFactory / pool
                          │
                          ├─ cached Connection
                          ├─ Session cache theo mode
                          ├─ cached Producer (nếu bật)
                          └─ cached Consumer (nếu bật / phù hợp)
~~~

Khi template kết thúc một lời gọi, nó giải phóng **logical handle**; wrapper có thể tái sử dụng physical resource.

## 8. Exception translation: giảm phụ thuộc vào checked JMSException

Jakarta JMS API truyền thống có nhiều `jakarta.jms.JMSException` checked. Spring sử dụng `org.springframework.jms.JmsException` (unchecked) và các subclass để đưa lỗi lên layer nghiệp vụ.

~~~text
jakarta.jms.JMSException (checked)
        │ Spring JMS exception translator
        ▼
org.springframework.jms.JmsException (RuntimeException)
        │
        ├─ lỗi kết nối / thao tác / format đã được map khi có loại phù hợp
        └─ UncategorizedJmsException cho lỗi không phân loại được
~~~

Ví dụ:

~~~java
import org.springframework.jms.JmsException;

try {
    jmsTemplate.convertAndSend("orders.queue", "order-42");
} catch (JmsException ex) {
    // Không nuốt exception; quyết định retry/DLQ/alert theo policy.
    throw new IllegalStateException("Could not publish order event", ex);
}
~~~

`JmsTemplate` giúp code business không phải `throws JMSException` cho các thao tác template thông thường. Tuy nhiên **unchecked không có nghĩa lỗi biến mất**: network, broker down, auth fail, destination không hợp lệ hoặc schema mismatch vẫn cần handling, observability và chính sách retry.

Không catch mọi `RuntimeException` rồi tự động gửi lại vô điều kiện. Retry có thể tạo **message trùng** nếu lần gửi trước đã tới broker nhưng client không nhận được xác nhận; nghiệp vụ cần idempotency/business key.

## 9. Transaction và acknowledgement: ranh giới cần hiểu

### 9.1. Transaction của JMS là gì?

Trong JMS local transaction, các send/receive thuộc **một session giao dịch** có thể commit hoặc rollback cùng nhau theo semantics provider. Nhưng giao dịch JMS cục bộ **không mặc nhiên** bao gồm việc ghi database hay gọi HTTP. Một transaction cho database và một transaction cho JMS không trở thành transaction distributed chỉ vì cùng có `@Transactional`.

Spring cung cấp `JmsTransactionManager` cho local JMS transaction trên một `ConnectionFactory`. Khi session giao dịch đã được manager bind vào thread, `JmsTemplate` sẽ phát hiện và tham gia, thay vì tạo session rời, commit/close sai scope.

~~~text
Service @Transactional("jmsTransactionManager")
  ├─ template.convertAndSend("q1", "A")
  └─ template.convertAndSend("q2", "B")
           │
           ▼
 JmsTransactionManager quản lý Session/commit/rollback
           │
           ├─ commit nếu toàn bộ block thành công
           └─ rollback khi exception theo cấu hình transaction
~~~

Điều kiện của sơ đồ là hai thao tác dùng đúng `ConnectionFactory` và đúng transaction manager, không trộn nhiều factory/provider vô tình. Không tạo thêm một `Session` thủ công bằng connection khác trong block rồi kỳ vọng nó tự tham gia transaction đó.

### 9.2. Ví dụ transaction theo Spring (mảnh cấu hình minh họa)

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.connection.JmsTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Bean("jmsTransactionManager")
PlatformTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional("jmsTransactionManager")
public void publishPair() {
    jmsTemplate.convertAndSend("demo.orders", "order-created");
    jmsTemplate.convertAndSend("demo.audit", "audit-created");
}
~~~

Hai mảnh trên cần được đặt đúng class cấu hình/service Spring, có annotation/bean/field hợp lệ; **không phải file Java độc lập**. Bảo đảm transaction management được bật và đúng bean/qualifier. Trong Spring Boot, nếu đã có `JtaTransactionManager` hoặc transaction manager mặc định khác, cần đặt transaction manager JMS rõ tên như ví dụ thay vì dùng `@Transactional` không chỉ định và đoán.

**Một ngoại lệ JMS ném ra ở cuối transaction không được “sửa” chỉ bằng cách retry mù quáng.** Xác nhận semantics delivery, broker redelivery và idempotency của message.

### 9.3. `sessionTransacted` trên template khác gì transaction manager?

`JmsTemplate` có `sessionTransacted` để tạo transacted `Session` trong môi trường không được quản lý bởi Spring transaction manager. Với thao tác độc lập của template, commit/rollback local có thể xảy ra khi kết thúc **một lời gọi**. Điều đó **không gom nhiều lời gọi template liên tiếp thành một transaction nghiệp vụ**, trừ khi có transaction manager điều phối các lời gọi trong cùng scope.

| Trường hợp | Ai quản lý commit/rollback? |
| --- | --- |
| Template không giao dịch, AUTO_ACK | Provider + session acknowledge behavior |
| Template tạo transacted session cho một thao tác riêng | Template tự xử lý local transaction theo operation |
| `@Transactional("jmsTransactionManager")` với resource đúng | `JmsTransactionManager` quản lý transaction boundary |
| JTA + XA provider/resources cấu hình đúng | JTA transaction manager điều phối các resource XA |
| `@Transactional` đang dùng DB transaction manager | **Không mặc định** biến hoạt động JMS thành XA/atomic với DB |

Một pattern production phổ biến để khắc phục **dual-write problem** là **transactional outbox**: ghi business data và outbox record trong **cùng DB transaction**, rồi publisher riêng gửi tới JMS với retry/idempotency. Cần thiết kế consistency model, không chỉ thêm annotation.

### 9.4. Consumer ack/redo và xử lý nghiệp vụ

Giả sử service gọi `receiveAndConvert("q")`, sau đó cập nhật DB, và DB update lỗi. Nếu JMS receive đã được ack/commit trước khi DB lỗi, message có thể không quay lại queue. Để cần retry theo xử lý nghiệp vụ, dùng listener container với session transacted và redelivery policy, hoặc transaction manager phù hợp; đồng thời thiết kế **idempotency** vì lỗi giữa commit DB và commit JMS có thể tạo duplicate.

JmsTemplate đơn thuần không thay thế quy trình xử lý lỗi và kiểm soát transaction của người tiêu thụ.

## 10. QoS và default destination: JmsTemplate hỗ trợ gì?

Một số thông số quan trọng cho send:

- `deliveryMode`: persistent/nonpersistent theo semantics JMS.
- `priority`: độ ưu tiên, thường trong dải 0–9.
- `timeToLive`: số milliseconds trước khi message hết hạn theo cơ chế JMS provider.
- `deliveryDelay`: trì hoãn thời điểm message được phân phối nếu provider/JMS version hỗ trợ.
- `explicitQosEnabled`: template có dùng các QoS do nó cấu hình thay vì luôn theo default provider hay không.

Ví dụ Boot:

~~~properties
spring.jms.template.time-to-live=30s
spring.jms.template.priority=5
spring.jms.template.qos-enabled=true
~~~

Ở Boot 3.5, các property trên là cấu hình template, không phải Java code. Khi cấu hình QoS qua Boot, tính năng explicit QoS cũng có thể được bật bởi những thuộc tính tương ứng; dòng `qos-enabled=true` khiến ý định rõ ràng.

**Đừng đồng nhất message TTL với thời gian chờ của receive.**

~~~text
time-to-live=30s    → message có thời hạn sống phía delivery/broker
receive-timeout=5s  → thread gọi receive chỉ chờ tối đa 5 giây
~~~

Message có thể chưa hết TTL nhưng receive trả `null` vì không có message trong 5 giây. Ngược lại, message hết TTL sẽ không đảm bảo còn được broker phân phối dù caller chờ lâu.

**Default destination** cho phép `convertAndSend(payload)` hoặc `receive()` nếu app đã cấu hình một đích mặc định:

~~~properties
spring.jms.template.default-destination=demo.orders
~~~

Nhưng service có nhiều destination nên thường truyền rõ tên đích để dễ review/audit. Đặt default destination không tạo queue/topic vật lý bất kể provider; provisioning vẫn phụ thuộc broker.

## 11. Ví dụ hoàn chỉnh: Spring Boot 3.5.7 + Artemis

Mục tiêu: một ứng dụng Java 17+ chạy hai cặp send/receive đồng bộ, quan sát payload, correlation ID và sự khác nhau giữa `convertAndSend` với `send(MessageCreator)`. Demo này **không có listener** để tránh một consumer khác “giành” message trước khi `receive`.

Yêu cầu: Java 17+, Maven 3.9+, Docker, cổng localhost 61616 khả dụng, có khả năng tải dependency/image. Dùng **Apache ActiveMQ Artemis** broker riêng và namespace `jakarta.jms` của Spring 6/Boot 3.5.

### 11.1. Khởi động broker local

~~~bash
docker run --rm -d --name jms-template-demo \
  -p 127.0.0.1:61616:61616 \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  apache/artemis:latest-alpine
~~~

Đây là **tài khoản mẫu chỉ cho lab local**, không được sử dụng ở production. Nếu phiên bản Docker/OS yêu cầu cấu hình broker khác, dùng hướng dẫn chính thức của Artemis. Đợi broker sẵn sàng:

~~~bash
docker logs jms-template-demo
~~~

Không đưa broker demo này ra internet. Cơ chế auto-create queue phụ thuộc cấu hình broker; với image Artemis demo mặc định thường bật auto-create. Trong môi trường thật, nên provision queue/address và quyền truy cập trước.

### 11.2. Cấu trúc thư mục

~~~text
jms-template-guide/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/jms/JmsTemplateApplication.java
        └── resources/application.properties
~~~

### 11.3. Maven `pom.xml`

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
    <artifactId>jms-template-guide</artifactId>
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

`spring-boot-starter-artemis` mang vào Spring JMS và client/provider Artemis phù hợp. Khi bật auto-configuration, Boot tạo `ConnectionFactory` và `JmsTemplate` để inject. Việc cấu hình broker ở `spring.artemis.*` chỉ áp dụng cho **provider Artemis**, không phải phần chuẩn chung của JMS.

### 11.4. `src/main/resources/application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

# Synchronous receive waits at most 5 seconds in this lab.
spring.jms.template.receive-timeout=5s
~~~

Đây là cấu hình **lab dùng credential giả/được thiết lập local**. Với môi trường thật, **không commit mật khẩu thật**: dùng placeholders environment hoặc secret store; kết nối qua TLS và quyền broker tối thiểu. Nếu demo dùng cổng broker khác, sửa broker-url tương ứng.

### 11.5. `src/main/java/com/example/jms/JmsTemplateApplication.java`

~~~java
package com.example.jms;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsTemplateApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsTemplateApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JmsTemplate jmsTemplate) {
        return args -> {
            // 1. Converter tự tạo TextMessage từ String.
            jmsTemplate.convertAndSend(
                    "demo.template.orders",
                    "order-42"
            );

            Object payload = jmsTemplate.receiveAndConvert(
                    "demo.template.orders"
            );
            if (!(payload instanceof String text)) {
                throw new IllegalStateException(
                        "Expected String payload, got " + payload);
            }
            System.out.println("Received: " + text);

            // 2. MessageCreator tự tạo TextMessage và header.
            jmsTemplate.send("demo.template.audit", session -> {
                TextMessage message =
                        session.createTextMessage("audit-1");
                message.setJMSCorrelationID("demo-1");
                return message;
            });

            Message raw = jmsTemplate.receive("demo.template.audit");
            if (!(raw instanceof TextMessage auditMessage)) {
                throw new IllegalStateException(
                        "Expected TextMessage, got " + raw);
            }
            System.out.println(
                    "Audit: " + auditMessage.getText()
                    + ", correlation=" + auditMessage.getJMSCorrelationID()
            );
        };
    }
}
~~~

**Giải thích những gì mã nguồn *không* phải làm:**

1. Không tự tạo `Connection`, `Session` hoặc `MessageProducer` cho từng send.
2. Không tự tạo `MessageConsumer`/`connection.start()` cho từng receive.
3. Không tự close JMS resource của template.
4. Không tự catch `JMSException` chỉ để đóng session sau một thao tác.
5. Không tạo/chia sẻ `Session` giữa nhiều thread.
6. Không quản lý raw message conversion thủ công cho payload `String` ở cặp send/receive đầu.

**Giải thích những gì mã nguồn *vẫn phải* làm:**

1. Chọn destination, định nghĩa payload/schema và header nghiệp vụ.
2. Cấu hình receive timeout và xử lý response `null`/type mismatch.
3. Cấu hình connection factory/broker và quyền.
4. Kiểm soát transaction, retry và idempotency theo mục tiêu của hệ thống.
5. Quyết định cách xử lý lỗi/giám sát; `JmsTemplate` không tự ghi DB, không auto-retry mọi lỗi business.

### 11.6. Chạy project và output dự kiến

Từ thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Khi broker sẵn sàng, queue khả dụng, ứng dụng là consumer duy nhất của hai queue demo và các thao tác hoàn thành trong 5 giây, hai dòng do code in ra là:

~~~text
Received: order-42
Audit: audit-1, correlation=demo-1
~~~

Spring Boot và Artemis cũng in log khởi động/kết nối tùy môi trường; hai dòng trên là output nghiệp vụ, **không phải toàn bộ stdout**.

Sau demo:

~~~bash
docker stop jms-template-demo
~~~

**Chú ý về tính xác định:** nếu có producer/consumer khác đang dùng các queue demo, payload nhận được có thể khác. Để bài lab lặp lại được, dùng broker/queue riêng, không tái sử dụng queue từ kiểm thử cũ. Nếu broker chưa start/không xác thực được, ứng dụng ném exception thay vì có hai dòng trên; kiểm tra container log, URI, credential và quyền truy cập.

### 11.7. Phần ví dụ không chứng minh những gì?

- Không chứng minh exactly-once end-to-end hay atomicity giữa JMS và database.
- Không chứng minh ứng dụng tiêu thụ message liên tục; nó chỉ nhận **hai lần đồng bộ**.
- Không chứng minh broker production tự tạo queue; behavior auto-create phụ thuộc provider.
- Không cấu hình TLS/secret store; đây là lab local.
- Không kiểm thử failure/reconnect/duplicate message; phải thiết kế và kiểm thử riêng trong production.

## 12. Request–reply: tiện ích có sẵn nhưng không phải RPC bảo đảm tuyệt đối

`JmsTemplate.sendAndReceive(destination, messageCreator)` cung cấp một mẫu request–reply đồng bộ. Template tạo **temporary queue** làm điểm reply, đặt vào header `JMSReplyTo` của request, gửi rồi chờ phản hồi từ destination tạm.

~~~java
// Mảnh code minh họa; phải có service khác đọc "demo.rpc.requests",
// nhận JMSReplyTo và gửi response về đó.
Message reply = jmsTemplate.sendAndReceive(
    "demo.rpc.requests",
    session -> session.createTextMessage("ping")
);

if (reply == null) {
    System.out.println("Reply timeout");
}
~~~

Nếu **không có responder**, lời gọi có thể hết timeout và `reply == null`; ứng dụng không tự có một server RPC chỉ nhờ gửi request. Responder phải đọc `request.getJMSReplyTo()` và gửi tới `Destination` đó; có thể cần correlation ID khi dùng reply queue chung hoặc nhiều request đồng thời.

Temporary destination sống theo connection và chỉ owner connection được tạo consumer; connection của responder có thể **gửi** vào reply destination. Template lo dọn temporary queue/resource của lời gọi, nhưng không làm message trở nên durable sau khi requester disconnect. Timeout và idempotency vẫn do hệ thống xác định.

Nếu tác vụ RPC tốn lâu, cân nhắc asynchronous reply/event, job status hoặc callback thay vì giữ nhiều thread và session chờ.

## 13. Mở rộng: browsing, selector và nhiều message

### 13.1. JMS selector

~~~java
// Nhận message có property eventType = 'ORDER_CREATED' nếu sẵn có.
Message selected = jmsTemplate.receiveSelected(
    "orders.queue",
    "eventType = 'ORDER_CREATED'"
);
~~~

Selector là biểu thức lọc **header/property** của JMS, không phải parser JSON body. Nó có cú pháp và loại hỗ trợ do JMS định nghĩa; không nối một String selector từ input người dùng chưa kiểm soát.

### 13.2. QueueBrowser

`JmsTemplate.browse(...)` cho phép duyệt **snapshot xấp xỉ** message trên queue bằng `QueueBrowser` mà không tiêu thụ message theo semantics browse. Tuy nhiên những thay đổi đồng thời trong broker làm kết quả quan sát **không phải transaction snapshot bất biến**, và browser vẫn là một resource cần cleanup. Template quản lý browser trong phạm vi callback:

~~~java
import jakarta.jms.Message;
import java.util.Enumeration;
import org.springframework.jms.core.BrowserCallback;

Integer visible = jmsTemplate.browse(
    "orders.queue",
    (BrowserCallback<Integer>) (session, browser) -> {
        Enumeration<?> items = browser.getEnumeration();
        int count = 0;
        while (items.hasMoreElements()) {
            Object item = items.nextElement();
            if (item instanceof Message) {
                count++;
            }
        }
        return count;
    }
);
~~~

Đây là **mảnh code**, không phải ứng dụng runnable. `visible` có thể thay đổi khi producer/consumer cùng hoạt động; không dùng queue browser làm công cụ giám sát chính xác tuyệt đối dưới tải. Với monitoring nên dùng broker management API/metrics.

### 13.3. Gửi/nhận theo batch

Template có thể thực hiện nhiều lời gọi trong một service, nhưng:

- Mỗi lời gọi `convertAndSend` có ranh giới thao tác riêng nếu không có transaction/callback gom phù hợp.
- Một callback `execute` có thể dùng chung session/producer; không biến nó thành global transaction.
- Thứ tự gửi **không luôn đồng nghĩa thứ tự xử lý nghiệp vụ** khi có nhiều consumer, redelivery, priority hoặc reordering ở topology.
- Nếu phải gửi số lượng lớn, cân nhắc outbox/batch và hạn chế số connection/session; không nhồi cả triệu message vào một transaction kéo dài.

## 14. Chọn thiết kế trong các tình huống thực tế

| Tình huống | Thiết kế phù hợp | Điều phải kiểm soát |
| --- | --- | --- |
| API publish event nhanh | `JmsTemplate.convertAndSend` + connection factory thích hợp | Timeout send, QoS, error handling, retry/idempotency |
| Phải đặt header/property | `send(MessageCreator)` hoặc post-processor | Schema, property types, correlation |
| Cần nhận message một lượt có timeout | `receive/receiveAndConvert` | Thread blocking, `null`, ack boundary |
| Service xử lý queue liên tục | `@JmsListener` / listener container | Concurrency, transaction, redelivery, DLQ |
| Muốn request–reply đơn giản | `sendAndReceive` | Responder, temporary queue, timeout/correlation |
| Tải cao, rất nhiều request | `CachingConnectionFactory`/pool và tuning | Resource exhaustion, monitoring, session constraints |
| Gửi JMS cùng cập nhật database | Outbox hoặc XA/JTA khi thực sự được hỗ trợ | Dual-write, eventual consistency, idempotency |
| Cần chuyển đổi DTO thành JSON | Custom `MessageConverter` | Phiên bản schema, content type, validation |
| Cần nhiều thao tác trên cùng session | `execute(SessionCallback/ProducerCallback)` | Không giữ resource ngoài callback; rõ transaction |

## 15. Lỗi thường gặp và cách sửa

### Lỗi 1. Coi template như broker hoặc queue

`JmsTemplate` chỉ là wrapper client; nếu broker chưa hoạt động/đúng credential thì `convertAndSend` vẫn lỗi. **Sửa:** cấu hình `ConnectionFactory`/provider/broker và health check rõ.

### Lỗi 2. Tự đóng session/producer do template quản lý

Khi callback được cấp session, developer tự đóng nó hoặc lưu vào static field rồi tái dùng. Hành vi này phá lifecycle của Spring/pool. **Sửa:** chỉ thao tác đồng bộ trong callback; Spring dọn resource mà nó cấp. Resource tự tạo độc lập phải tự quản lý.

### Lỗi 3. Cho rằng mỗi send sẽ đóng TCP connection

Khi connection factory caching/pooling, logical close trả resource vào cache. **Sửa:** quan sát physical connection count và cache config thay vì suy từ số lời gọi `JmsTemplate`.

### Lỗi 4. Dùng session trên nhiều thread

`JmsTemplate` singleton thread-safe sau khi cấu hình, nhưng `Session` JMS không được chia sẻ dùng đồng thời tùy tiện. **Sửa:** inject template, tránh cất session vào singleton, không tạo async task sử dụng lại session callback.

### Lỗi 5. Receive chờ vô hạn

Đặt `receiveTimeout=0` trong endpoint có tải cao có thể giữ thread lâu. **Sửa:** timeout dương cho lời gọi sync; service tiêu thụ thường trực dùng listener container.

### Lỗi 6. Đọc `receiveAndConvert` mà không kiểm tra null/type

Timeout trả `null`; converter có thể trả `String`, `byte[]`, `Map` hoặc object theo config. **Sửa:** null-check, type-check, schema validation.

### Lỗi 7. Mặc định converter luôn dùng JSON

`convertAndSend(dto)` không có nghĩa tự serialize JSON. **Sửa:** cấu hình `MessageConverter` JSON phù hợp; test raw message type/body.

### Lỗi 8. Chỉ dùng `@Transactional` rồi nghĩ DB và JMS là một transaction

Nếu annotation gắn với transaction manager khác, JMS resource có thể không tham gia. **Sửa:** chỉ định manager, resource factory, hoặc triển khai outbox/JTA đúng cách.

### Lỗi 9. Dựa vào việc send thành công để kết luận business hoàn tất

Send thành công không xác nhận consumer đã xử lý, commit DB hoặc gửi response. **Sửa:** dùng ack/response/job state/outbox phù hợp semantics nghiệp vụ.

### Lỗi 10. Retry mù quáng khi timeout hoặc mất kết nối

Broker có thể đã nhận message nhưng client không biết kết quả. **Sửa:** idempotent handler, event ID duy nhất, deduplication, retry có backoff/giới hạn.

### Lỗi 11. Bật cache consumer mọi nơi

Consumer cached có thể tác động lâu tới subscription/prefetch; listener container quản lý consumer riêng. **Sửa:** cấu hình cache theo workload và provider, test under load, theo dõi các consumer còn active.

### Lỗi 12. Bỏ qua TLS và quyền broker

Password trong source hoặc plain TCP ra mạng production là rủi ro; template không tự thay thế auth/authorization. **Sửa:** externalized secrets, TLS, least privilege, audit access.

### Lỗi 13. Nhầm checked và unchecked exception

`JmsTemplate` thường ném Spring `JmsException` unchecked; `MessageCreator` vẫn có thể khai báo `jakarta.jms.JMSException` trong callback theo interface. **Sửa:** phân biệt JMS API bên trong callback với exception translation ở biên template; log root cause có sanitization.

### Lỗi 14. Không đặt TTL hay DLQ policy

Message cũ có thể còn trong queue, lỗi xử lý có thể lặp vô hạn. **Sửa:** thống nhất TTL, redelivery, dead-letter address, replay runbook và monitoring với broker.

## 16. Checklist cho code review/triển khai

- [ ] `ConnectionFactory` đến từ JMS provider đúng loại, endpoint và credentials hợp lệ; queue/topic đã được tạo/cấp quyền theo chính sách.
- [ ] `JmsTemplate` được inject như bean dùng chung sau cấu hình, không thay đổi settings theo từng request một cách cạnh tranh.
- [ ] Dùng `convertAndSend` khi converter hiểu payload; dùng `send(MessageCreator)` khi cần raw JMS type/headers.
- [ ] Không tạo/đóng/giữ `Connection`, `Session`, `Producer` do template quản lý ra ngoài callback.
- [ ] Đã phân biệt hoạt động đồng bộ `receive` với bất đồng bộ `@JmsListener`.
- [ ] Đã đặt `receiveTimeout` cho lời gọi sync và xử lý `null`.
- [ ] Có schema/message converter và kiểm tra dữ liệu, không deserialize Java object từ nguồn không tin cậy.
- [ ] Đã xác định ack/transaction manager đúng với `ConnectionFactory`, hiểu ranh giới JMS–DB.
- [ ] Có retry hữu hạn, idempotency key, xử lý poison messages/DLQ và quan sát timeout.
- [ ] Cache/pool đúng quy mô concurrency, không giả định physical close sau mỗi thao tác; có metrics connection/session/consumer.
- [ ] QoS, TTL, priority, delivery mode và selector được kiểm tra với broker thực.
- [ ] Credential được cấp từ environment/secret manager, không hardcode production; TLS và quyền tối thiểu.
- [ ] Integration test gồm broker unavailable, unauthorized send, duplicate, timeout, redelivery và graceful shutdown.

## 17. Câu hỏi ôn tập

**Câu 1. `JmsTemplate` thay thế `ConnectionFactory` được không?**  
Không. Template **cần** `ConnectionFactory` để lấy JMS connection/session; nó không trực tiếp là broker/provider.

**Câu 2. Dùng `JmsTemplate` có cần `try-with-resources` để close `Session` không?**  
Không với session mà template tạo/cấp cho callback. Template/transaction infrastructure xử lý lifecycle; chỉ tự dọn resource do chính mình tạo độc lập.

**Câu 3. Vì sao template dùng được như singleton?**  
Nó thread-safe **sau khi cấu hình**, vì mỗi thao tác lấy tài nguyên phù hợp qua factory/transaction. Điều đó không làm cho một `Session` JMS chia sẻ giữa thread trở nên an toàn.

**Câu 4. `convertAndSend("q", "hi")` khác `send("q", callback)` ở đâu?**  
Cái đầu dùng converter tạo JMS message từ Java object. Cái sau cho developer tạo và tùy chỉnh message bằng `Session` được template cấp.

**Câu 5. `receive` khác `@JmsListener`?**  
`receive` là lệnh sync có thể chặn thread caller; `@JmsListener` dùng container tạo consumer và gọi handler bất đồng bộ.

**Câu 6. Có phải `receiveAndConvert` luôn trả String?**  
Không. Nó phụ thuộc message type/converter; cũng có thể trả `null` khi không nhận được message trong timeout.

**Câu 7. Cache/pool có làm message exactly-once không?**  
Không. Cache tối ưu resource; guarantee delivery/processing cần thiết kế transaction, ack, retry, deduplication và idempotency.

**Câu 8. Một service vừa ghi DB vừa gửi JMS dưới `@Transactional` có atomic không?**  
Không mặc nhiên. Cần xem transaction manager; thường dùng outbox hoặc JTA/XA đúng hạ tầng nếu thật sự muốn distributed atomicity.

**Câu 9. `sendAndReceive` có tự viết responder không?**  
Không. Nó tạo temporary reply queue và chờ; một service khác phải đọc request và gửi reply.

**Câu 10. Khi callback ném lỗi `JMSException` thì sao?**  
Template dịch lỗi JMS thành một `JmsException` unchecked phù hợp để caller xử lý; session/producer được dọn theo lifecycle ngay cả khi lỗi. Nếu đang trong transaction, rollback/commit tuân theo transaction manager.

## 18. Tài liệu tham khảo chính thức

1. [Spring Framework 6.2 — Using Spring JMS: JmsTemplate, callbacks, resource caching và transactions](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
2. [Spring Framework — JMS overview: phân lớp core, converter, exception và listener](https://docs.spring.io/spring-framework/reference/6.2/integration/jms.html)
3. [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html)
4. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
5. [Spring Framework Javadoc — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
6. [Spring Framework — Message listener endpoints và `@JmsListener`](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
7. [Spring Boot 3.5 — JMS with Apache ActiveMQ Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html)
8. [Spring Boot 3.5 — Common Application Properties: `spring.jms.*`](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
9. [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
10. [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)
