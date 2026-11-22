# JmsTemplate: receive so với receiveAndConvert

## Mục tiêu học tập

Trong Spring Framework JMS, hai phương thức **`JmsTemplate.receive(...)`** và **`JmsTemplate.receiveAndConvert(...)`** đều dùng để **nhận một message đồng bộ** từ một JMS destination. Chúng có cùng cơ chế chờ message, nhưng khác **mức trừu tượng dữ liệu trả về**: một phương thức trả đối tượng JMS message (giữ header, properties, body type), phương thức kia chuyển đổi body qua `MessageConverter` thành một Java object.

Bài này giúp bạn nắm được:

1. Chính xác mỗi phương thức trả kiểu gì, lúc nào trả `null`, và các overload theo destination.
2. Khi nào cần thao tác `TextMessage`, `BytesMessage`, `MapMessage`, JMS headers/properties, hoặc chỉ cần payload như `String`/DTO.
3. Tác động của `SimpleMessageConverter`, converter JSON tùy biến, lỗi ép kiểu và version/schema.
4. Cơ chế **blocking** và `receiveTimeout`; vì sao mặc định có thể chờ vô thời hạn và không phù hợp với nhiều request HTTP.
5. Điểm rất quan trọng của **acknowledgement và transaction**: nhận xong không đồng nghĩa nghiệp vụ đã thành công. Với receive đồng bộ do `JmsTemplate` tự quản lý, thông điệp có thể đã được ack/commit trước khi code xử lý tiếp.
6. Cách thực hành Java 17+ với Spring Boot và ActiveMQ Artemis, kiểm thử selector và chọn `@JmsListener` khi xử lý liên tục.

**Phạm vi:** Spring Framework 6.x, Spring Boot 3.x, Jakarta Messaging (package `jakarta.jms`). Spring 5.x sử dụng namespace `javax.jms` và vài cách tự cấu hình khác; không trộn hai thế hệ API trong một dự án.

## 1. Bảng so sánh nhanh

| Tiêu chí | `receive(...)` | `receiveAndConvert(...)` |
| --- | --- | --- |
| Ý nghĩa | Nhận một JMS message nguyên bản | Nhận một JMS message rồi chuyển phần dữ liệu thành Java object |
| Kiểu trả về khai báo | `jakarta.jms.Message`, có thể `null` | `java.lang.Object`, có thể `null` |
| Nội dung trả về | Body type, JMS headers, message properties | Giá trị do `MessageConverter.fromMessage(...)` tạo ra |
| Có tự dùng `MessageConverter`? | **Không** | **Có**, sau khi nhận |
| Khi có `TextMessage` với converter mặc định | Vẫn là `TextMessage` | Thường là `String` |
| Khi có `BytesMessage` với converter mặc định | Vẫn là `BytesMessage` | Thường là `byte[]` |
| Khi có `MapMessage` với converter mặc định | Vẫn là `MapMessage` | Thường là `Map` |
| Khi có `ObjectMessage` với converter mặc định | Vẫn là `ObjectMessage` | Thường là object Java đã deserialize |
| Đọc `JMSMessageID`, correlation ID, property | Trực tiếp từ `Message` | Không còn `Message` trong kết quả; cần convention khác nếu muốn metadata |
| Chọn destination | Mặc định, `String`, hoặc `Destination` | Tương tự |
| Chọn lọc bằng JMS selector | `receiveSelected(...)` | `receiveSelectedAndConvert(...)` |
| Chờ message | Đồng bộ, có thể block | Đồng bộ, **cũng block** |
| Khi timeout không có message | `null` | `null` |
| Lỗi đặc trưng | JMS connection/receive/ack, body đọc không đúng type | Những lỗi đó **cộng thêm** lỗi converter/schema/type |
| Sử dụng phù hợp | Cần header/property hoặc tự kiểm soát parsing | Chỉ cần payload theo converter được hai bên thống nhất |

**Công thức để nhớ:**

~~~text
receive(destination)
    => jakarta.jms.Message (hoặc null)
    => TỰ đọc header, property, body

receiveAndConvert(destination)
    => receive(destination)
    => messageConverter.fromMessage(message)
    => Java Object (hoặc null)
~~~

Cả hai **tiêu thụ** message từ destination. `receiveAndConvert` không phải thao tác “xem trước” hay “đọc mà không xóa”. Không gọi liên tiếp hai phương thức trên **cùng một message** để so sánh: lần gọi thứ nhất có thể đã tiêu thụ nó.

## 2. Những phương thức được dùng thực tế

Các chữ ký tiêu biểu trong `org.springframework.jms.core.JmsTemplate`:

~~~java
// Nhận trực tiếp JMS Message:
Message receive();
Message receive(String destinationName);
Message receive(Destination destination);

// Nhận payload Java theo MessageConverter:
Object receiveAndConvert();
Object receiveAndConvert(String destinationName);
Object receiveAndConvert(Destination destination);

// Nhận với JMS selector:
Message receiveSelected(String destinationName, String messageSelector);
Object receiveSelectedAndConvert(String destinationName, String messageSelector);
~~~

Đây là **các chữ ký minh họa** (không phải các method bạn cần tự định nghĩa). Những API thực tế có thêm overload với default destination hoặc `Destination` object; kết quả mang khả năng nullable.

- `receive()` và `receiveAndConvert()` **không có tham số** chỉ hoạt động khi `JmsTemplate` đã được cấu hình default destination (`defaultDestination` hoặc `defaultDestinationName`).
- `receive("payments.in")` dùng tên destination dạng chuỗi; `DestinationResolver` của template xác định đó là queue/topic theo cấu hình, chẳng hạn `pubSubDomain=false` cho queue.
- `receive(queueObject)` nhận `jakarta.jms.Destination` do hạ tầng cung cấp; tránh nhập nhằng khi một hệ thống vừa queue vừa topic.
- `receiveSelected("payments.in", "kind = 'refund'")` lọc trên **JMS message properties/headers có thể truy vấn**, không truy vấn trực tiếp trường JSON trong body.
- `receiveAndConvert` trong `JmsTemplate` **không** có overload bắt bạn truyền `Class<T>` rồi trả về generic `T`. Đó là kiểu tiện ích có ở **`JmsMessagingTemplate`** (Spring Messaging abstraction) hoặc API khác. Với `JmsTemplate`, hãy kiểm tra `instanceof` trước khi cast.

Ví dụ một lời gọi có mục đích rõ:

~~~java
// Mảnh code trong Spring bean với JmsTemplate được inject.
Object payload = jmsTemplate.receiveAndConvert("orders.in");
if (payload instanceof String orderId) {
    processOrder(orderId);
} else if (payload == null) {
    // Không có message trước timeout; một số converter đặc biệt cũng có thể trả null.
} else {
    throw new IllegalArgumentException(
            "Expected String but got " + payload.getClass().getName());
}
~~~

`processOrder` là phương thức nghiệp vụ của bạn; đây là **mảnh code minh họa**, không phải ứng dụng độc lập. Chú ý: nếu nghiệp vụ `processOrder` ném exception **sau** khi receiveAndConvert đã trở về, việc rollback message **không tự xuất hiện**.

## 3. receive(): giữ lại JMS Message và metadata

`jakarta.jms.Message` là interface gốc của các JMS message. Nó mang các header và properties bên cạnh body. `receive()` cho phép bạn đọc chúng trước khi quyết định xử lý.

~~~java
// Mảnh code đặt trong service đã có JmsTemplate.
Message message = jmsTemplate.receive("billing.in");
if (message == null) {
    return;
}

String messageId = message.getJMSMessageID();
String correlationId = message.getJMSCorrelationID();
boolean redelivered = message.getJMSRedelivered();
String kind = message.getStringProperty("kind");

if (message instanceof TextMessage textMessage) {
    String body = textMessage.getText();
    // Decode JSON, xác thực schema, xử lý business...
} else if (message instanceof BytesMessage bytesMessage) {
    // Đọc bytes theo codec/schema đã thỏa thuận.
} else {
    // Xử lý rõ định dạng không mong đợi.
}
~~~

Cần imports `jakarta.jms.Message`, `TextMessage`, `BytesMessage`; phương thức chứa code phải xử lý `JMSException` hoặc khai báo `throws` thích hợp. Đoạn này chủ đích là code fragment.

Các trường metadata có ý nghĩa:

| Thành phần | Dùng khi nào | Lưu ý |
| --- | --- | --- |
| `JMSMessageID` | Theo dõi message và log | ID do provider cung cấp; không mặc định thay business idempotency key |
| `JMSCorrelationID` | Ghép request–reply / trace logic | Do application convention hoặc producer gán |
| `JMSType` | Truyền thông tin loại message nếu dự án dùng | Không tự được schema registry kiểm chứng |
| `JMSRedelivered` | Nhận biết message từng được giao trước đó | Không thay cơ chế idempotency |
| `JMSDestination` | Kiểm tra destination nhận | Có thể là queue/topic object tùy provider |
| `JMSTimestamp` | Thời gian do producer/provider gán | Không đồng nghĩa timestamp nghiệp vụ xảy ra |
| `message.getStringProperty("kind")` | Routing, filtering, observability | Là **JMS property**, không phải JSON field trong body |
| `JMSXDeliveryCount` | Đếm lần giao nếu broker hỗ trợ property chuẩn tùy chọn | Không phải ứng dụng/provider nào cũng expose giống nhau |

**Vì sao metadata quan trọng?** Giả sử một consumer cần xác minh `JMSCorrelationID` của response, kiểm tra `kind` trước khi parse body, và gắn `JMSMessageID` vào log. `receive()` có thể phù hợp vì trả về chính đối tượng JMS. Nếu sử dụng `receiveAndConvert`, metadata **không nằm trong Java String mặc định**; phải có convention/envelope hoặc converter tùy biến giữ metadata nếu thật sự cần.

### 3.1. Đọc body “thủ công” không làm receive() thành receiveAndConvert()

Với `TextMessage`:

~~~java
Message raw = jmsTemplate.receive("queue.one");

if (raw instanceof TextMessage text) {
    String json = text.getText();
    // json là text, chưa phải DTO.
}
~~~

`getText()` không parse JSON, không validate schema và không tự tạo DTO. Nếu muốn DTO typed, dùng JSON mapper rõ ràng hoặc cấu hình `MessageConverter` ở `receiveAndConvert`.

Với `ObjectMessage`, gọi `getObject()` có thể kích hoạt **Java native deserialization**, vốn phụ thuộc class Java và có rủi ro bảo mật. Đừng dùng `ObjectMessage` như mặc định cho mọi event qua biên giới service chỉ vì nó trả một Java object thuận tiện.

### 3.2. Không giữ Message lại rồi mới cố xác nhận

`receive()` qua `JmsTemplate` không giao cho bạn quyền sở hữu `Session`/`Connection` nằm dưới template. `JmsTemplate` đã điều phối acknowledgement/transaction và cleanup theo cấu hình trước khi phương thức trả về. Không viết logic “sau khi gọi API HTTP thành công thì tôi sẽ `message.acknowledge()`” rồi mặc định acknowledgment sẽ điều khiển đúng session do template đã đóng/trả về cache. Muốn ràng buộc xử lý nghiệp vụ và ack vào một transaction, xem phần transaction.

## 4. receiveAndConvert(): nhận rồi chuyển thành payload Java

`JmsTemplate` dùng một `org.springframework.jms.support.converter.MessageConverter`; interface chính có hai chiều:

~~~java
// Hình dạng interface (rút gọn; minh họa, không phải file tự biên dịch):
Message toMessage(Object object, Session session) throws JMSException;
Object fromMessage(Message message) throws JMSException;
~~~

`convertAndSend` dùng `toMessage`; `receiveAndConvert` dùng `fromMessage`. **Hai đầu cần cùng hợp đồng encoding/schema**, không chỉ cùng tên queue.

Converter mặc định thường là `SimpleMessageConverter`. Với message nhận:

| JMS message type | Java result thường có dưới SimpleMessageConverter | Lưu ý |
| --- | --- | --- |
| `TextMessage` | `String` | `getText()` có thể `null`; JSON vẫn là chuỗi |
| `BytesMessage` | `byte[]` | Không tự decode Protobuf/Avro/ZIP |
| `MapMessage` | `Map<String,Object>` | Các kiểu giá trị bị giới hạn bởi JMS MapMessage |
| `ObjectMessage` | Object Java `Serializable` | Có thể deserialize Java binary; class phải tương thích và được phép |
| Message type không hỗ trợ | Có thể trả nguyên `Message` hoặc báo lỗi tùy converter/version | Đọc đúng implementation/version; đừng cast mù quáng |

Đừng suy luận loại Java từ tên destination. `receiveAndConvert("orders.json")` không tự hiểu JSON; nếu message là `TextMessage` chứa JSON, converter mặc định trả **`String` JSON**, không phải `OrderDto`.

Ví dụ:

~~~java
Object data = jmsTemplate.receiveAndConvert("orders.json");

if (!(data instanceof String json)) {
    throw new IllegalStateException("Expected JSON text payload");
}

// Ví dụ với Jackson đã được cấu hình trong ứng dụng:
OrderEvent event = objectMapper.readValue(json, OrderEvent.class);
validate(event);
~~~

Đây là **mảnh code**, cần `objectMapper`, `OrderEvent`, `validate` và exception handling; nó thể hiện hai giai đoạn riêng: `MessageConverter` đọc message thành `String` và JSON mapper ánh xạ chuỗi thành DTO.

### 4.1. Converter tùy chỉnh thay đổi cả phía gửi và phía nhận

Khi cấu hình `MappingJackson2MessageConverter` (Spring Framework 6.x/Jackson 2) để serialize/deserialize JSON:

- Message có thể là `TextMessage` hoặc `BytesMessage` theo `targetType`; cần cấu hình rõ.
- Property type id giúp converter chọn DTO; sử dụng mapping alias ổn định thay vì công bố tùy ý Java class name.
- Type mapping phải được cấu hình thống nhất giữa producer/consumer; không được mở polymorphic deserialization rộng từ dữ liệu không tin cậy.
- Một `MessageConverter` bean trong Spring Boot có thể được tự gắn vào `JmsTemplate`; nhưng nếu bạn tự tạo nhiều template/factory thì phải bảo đảm chúng sử dụng converter mong muốn.
- Converter không giải quyết tự động schema versioning, backwards compatibility, redelivery, idempotency hoặc transaction.

Mảnh cấu hình tương thích với Spring Framework 6.x:

~~~java
@Bean
MappingJackson2MessageConverter invoiceJsonConverter() {
    var converter = new MappingJackson2MessageConverter();
    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    converter.setTypeIdMappings(Map.of(
            "invoice-v1", InvoiceEvent.class));
    return converter;
}
~~~

Đoạn này cần imports `org.springframework.context.annotation.Bean`, `java.util.Map`, `org.springframework.jms.support.converter.MappingJackson2MessageConverter`, `MessageType` và định nghĩa DTO `InvoiceEvent`. Đây không phải class chạy độc lập. Khi nâng sang Spring Framework khác có thay đổi Jackson converter, đối chiếu phiên bản thật trước khi sao chép.

### 4.2. Kiểm tra kiểu thay vì cast trực tiếp

Sai:

~~~java
OrderEvent event = (OrderEvent)
        jmsTemplate.receiveAndConvert("orders.in");
~~~

Nếu converter mặc định trả `String`, code sẽ ném `ClassCastException`. Quan trọng: message có thể **đã được tiêu thụ và ack** trước khi lỗi cast xuất hiện.

Cách tốt hơn:

~~~java
Object result = jmsTemplate.receiveAndConvert("orders.in");

if (result == null) {
    return;
}
if (result instanceof OrderEvent event) {
    handle(event);
} else {
    throw new IllegalStateException(
            "Unexpected payload: " + result.getClass().getName());
}
~~~

Đây là các **mảnh code** giả định có `OrderEvent` và `handle`. Chúng giúp bắt sai hợp đồng kiểu, **không** tự làm redelivery xảy ra nếu receive đã commit.

## 5. Timeout: cả hai đều nhận đồng bộ và có thể block

Dù tên có chữ `Convert`, `receiveAndConvert` **không** phải API asynchronous. Cả hai thực hiện `receive` theo cơ chế của `MessageConsumer` và chờ message trên **luồng đang gọi**.

Các giá trị `JmsTemplate.setReceiveTimeout(long)` trong Spring Framework:

| Giá trị | Ý nghĩa thực tế |
| --- | --- |
| Mặc định: `RECEIVE_TIMEOUT_INDEFINITE_WAIT` (giá trị `0`) | Chờ đến khi có message hoặc có lỗi/ngắt kết nối; có thể **block vô thời hạn** |
| `setReceiveTimeout(2000)` | Chờ khoảng tối đa 2.000 ms cho một lần receive; không có message thì trả `null` |
| `RECEIVE_TIMEOUT_NO_WAIT` hoặc số âm (ví dụ `-1`) | Kiểm tra ngay bằng semantics `receiveNoWait()`, không chủ động chờ |
| Giá trị dương nhỏ | Poll có giới hạn ngắn, nhưng vẫn là blocking trong khoảng đó |

~~~java
// Cấu hình một JmsTemplate đã inject, ở thời điểm khởi tạo/cấu hình app:
jmsTemplate.setReceiveTimeout(2_000L);

// Mỗi lời gọi receive/receiveAndConvert có thể chờ tới khoảng 2 giây:
Message raw = jmsTemplate.receive("reports.in");
Object converted = jmsTemplate.receiveAndConvert("reports.in");
~~~

**Không dùng nguyên đoạn này để so sánh cùng message**, vì hai lời gọi cùng queue tiêu thụ hai message khác nhau nếu có. Để so sánh kết quả, gửi hai message tương đương tới hai queue riêng, như lab ở phần 8.

Lưu ý:
- `null` từ `receive()` thường báo không nhận được message trong thời gian chờ; không khẳng định broker không bao giờ có message.
- `null` từ `receiveAndConvert()` có thể do không nhận message; với converter có khả năng trả `null` cho một body hợp lệ (ví dụ text `null`), **không thể phân biệt chỉ bằng giá trị null**. Hợp đồng nên không gửi payload có ý nghĩa “null” hoặc dùng raw `Message`/envelope.
- Deadline nhận message không tự là deadline của **toàn bộ nghiệp vụ**: sau khi nhận, API HTTP, DB hoặc converter có thể tiếp tục mất thời gian.
- Broker có selector, expiry/TTL, delayed delivery, competing consumer, quyền nhận... nên “queue có message” không bảo đảm lời gọi của bạn lấy đúng message đó ngay.
- Dùng no-wait trong vòng lặp bận, thiếu sleep/backoff, có thể tạo **busy polling** và gây tải broker/CPU. Dùng `@JmsListener` nếu cần xử lý liên tục.
- Không để một request HTTP gọi `receiveAndConvert()` vô hạn trên thread xử lý request. Nếu có cơ chế request-reply, dùng thời gian chờ và correlation ID riêng, hoặc kiến trúc async.

### 5.1. Cấu hình per-template, không mặc định per-call

`setReceiveTimeout` là setting của **template**, không phải tham số `receiveAndConvert("q", timeout)` trên `JmsTemplate`. Trong một ứng dụng đa nhiệm, không thay đổi timeout của shared template liên tục giữa các request vì dễ gây race và khó dự đoán. Có thể định nghĩa **hai template bean** dùng chung `ConnectionFactory` nhưng timeout khác nhau, hoặc chọn một giá trị thống nhất.

Ví dụ về cấu hình riêng (mảnh `@Configuration`):

~~~java
@Bean("shortPollJmsTemplate")
JmsTemplate shortPollJmsTemplate(ConnectionFactory cf) {
    JmsTemplate template = new JmsTemplate(cf);
    template.setReceiveTimeout(250L);
    return template;
}
~~~

Trong Spring Boot, nếu tự tạo `JmsTemplate` thay bean mặc định, hãy chú ý các setting converter, destination resolver, transaction/pooling mà ứng dụng đang dựa vào. Với Spring Boot nên dùng cơ chế cấu hình/configurer phù hợp phiên bản khi cần giữ toàn bộ auto-configuration.

## 6. Vị trí chính xác của converter so với acknowledgement/commit

Đây là điểm quyết định về tính đúng đắn và thường bị bỏ qua.

### 6.1. Đường xử lý của JmsTemplate

Ở mức khái niệm, trong Spring Framework 6.x:

~~~text
receiveAndConvert("orders.in")
    |
    +-- receive("orders.in")
    |     |
    |     +-- lấy Connection/Session
    |     +-- tạo MessageConsumer
    |     +-- nhận Message (blocking / timeout)
    |     +-- thực hiện ACK hoặc JMS local COMMIT nếu template sở hữu session
    |     +-- đóng/trả consumer và tài nguyên theo policy
    |
    +-- nếu Message != null:
    |     messageConverter.fromMessage(message)
    |
    +-- trả payload Object (hoặc null)
~~~

Đường đi **`receive()` tự quản lý phần tài nguyên và acknowledgement**. Khi gọi `receiveAndConvert()`, Spring trước hết thực hiện `receive()` rồi mới chuyển đổi message. Nếu session là một **JMS transaction cục bộ do chính template tạo ra**, commit xảy ra trong `receive`, tức **trước** converter. Nếu dùng `CLIENT_ACKNOWLEDGE` do template quản lý, việc acknowledge cũng có thể được thực hiện trong `receive` trước khi trả về.

Vì vậy:
- `MessageConverter.fromMessage(...)` ném exception **không bảo đảm** một message vừa nhận sẽ được redeliver trong local template-controlled receive.
- `handleBusiness(...)` ném exception sau khi `receiveAndConvert(...)` trả về cũng **không tự rollback** message đã được nhận.
- Một `receive()` nguyên bản cũng **không cho phép** tùy tiện giữ session mở rồi ack sau khi hoàn tất database, vì template kiểm soát vòng đời session.
- Chỉ đặt `jmsTemplate.setSessionTransacted(true)` **không** khiến phần code sau lời gọi receive trở thành một giao dịch dài bao gồm business logic. Nó có thể chỉ bảo đảm transaction cho **thao tác nhận**.

Đây là hành vi quan trọng của Spring `JmsTemplate`, không phải phát biểu rằng mọi JMS consumer trong mọi framework luôn ack trước handler.

### 6.2. Giao dịch được bao quanh từ bên ngoài

Nếu cần quá trình nhận/chuyển đổi/xử lý thuộc **một JMS transaction**, hãy cân nhắc transaction boundary do Spring quản lý:

~~~java
@Service
public class TransactionalPullWorker {

    private final JmsTemplate jmsTemplate;

    public TransactionalPullWorker(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Transactional(transactionManager = "jmsTransactionManager")
    public void pollOne() {
        Object payload = jmsTemplate.receiveAndConvert("jobs.in");
        if (payload == null) {
            return;
        }
        if (!(payload instanceof String jobId)) {
            throw new IllegalArgumentException("Unexpected message type");
        }
        performIdempotentWork(jobId); // Method nghiệp vụ do bạn triển khai.
    }

    private void performIdempotentWork(String jobId) {
        // Thực hiện logic phù hợp; ném exception nếu chưa hoàn tất.
    }
}
~~~

Đây là **mẫu class Spring**, cần imports `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional`, `JmsTemplate` và một bean `JmsTransactionManager` tên `jmsTransactionManager` dùng **cùng ConnectionFactory** thích hợp. `@Transactional` phải được gọi qua Spring proxy; tự gọi `this.pollOne()` có thể bỏ qua transaction advice.

Khi JMS session được ràng buộc với transaction bên ngoài:
- Commit/rollback JMS diễn ra tại cuối transaction thay vì được template tự commit ngay trong `receive`.
- Nếu converter hoặc business logic ném unchecked exception khiến transaction rollback, broker có thể giao lại message theo policy.
- **JmsTransactionManager không tự bao gồm transaction database**. Nếu `performIdempotentWork` ghi DB, cần outbox/inbox/idempotency hoặc hạ tầng transaction phối hợp được chứng minh. Không suy diễn exactly-once chỉ từ annotation.
- Nếu business work kéo dài, việc giữ JMS transaction lâu có chi phí và rủi ro khi broker/network thất bại; cân nhắc listener container và architecture khác.

### 6.3. Vì sao @JmsListener thường phù hợp hơn?

Với consumer liên tục:
- `DefaultMessageListenerContainer` hoặc container được cấu hình tương đương có thể quản lý vòng đời và JMS transaction qua **một listener invocation**.
- Khi listener ném exception và session được cấu hình `sessionTransacted=true`, transaction có thể rollback và dẫn tới redelivery tùy broker.
- Dùng concurrency, retry/DLQ, metric và graceful shutdown rõ ràng hơn việc đặt `receiveAndConvert` vào vòng lặp `while(true)`.
- Consumer vẫn cần idempotency: handler có thể xử lý database xong rồi chết trước khi JMS commit.

**Kết luận phần transaction:** Lựa chọn giữa `receive` và `receiveAndConvert` không phải công tắc điều khiển ACK. Trục phân biệt là **raw vs converted payload**; trục reliability nằm ở transaction/acknowledge/lifecycle.

## 7. Khi nào chọn phương thức nào?

### Trường hợp A — Nhận một text command đơn giản

Một batch tool chỉ cần lấy chuỗi `"rebuild-index"` từ queue riêng, chấp nhận nhận trong thời gian tối đa 2 giây. Hợp đồng chắc chắn body là `TextMessage`, không cần JMS metadata.

**Ưu tiên `receiveAndConvert`** với converter mặc định, kiểm tra kết quả là `String`, và thực thi nghiệp vụ trong transaction/reliability phù hợp.

### Trường hợp B — Cần trace/correlation, kiểm tra headers, routing

Service cần `JMSCorrelationID` để đối chiếu reply, `JMSRedelivered` để log, và property `tenant` để kiểm tra ngữ cảnh.

**Ưu tiên `receive`** vì nhận `Message`. Kiểm tra kiểu body, property, header; không phụ thuộc converter bị đổi trong auto-configuration.

### Trường hợp C — JSON schema nhiều version

Producer gửi text JSON có `schemaVersion`, `eventId`, `type`; consumer dùng Jackson để parse DTO theo version.

**Hai cách đều hợp lý:**
- `receive()` → kiểm tra headers/properties → đọc `TextMessage.getText()` → tự parse với Jackson.
- `receiveAndConvert()` → sử dụng JSON `MessageConverter` có type mappings/version validation phù hợp → nhận DTO hoặc object đã thống nhất.

Không giả định `SimpleMessageConverter` tự parse JSON.

### Trường hợp D — Lấy một message để làm business side effect quan trọng

Có payment, email, đặt chỗ hoặc update database. Nếu gọi `receiveAndConvert()` rồi làm nghiệp vụ bên ngoài mà không đặt transaction boundary, message có thể được ack trước lỗi nghiệp vụ.

**Không có phương thức nào tự giải quyết.** Chọn listener container có transacted session, hoặc bao quanh synchronous polling bằng external JMS transaction đúng cách. Thiết kế idempotent handler và retry/DLQ.

### Trường hợp E — Service cần tiêu thụ 24/7

Một consumer luôn sẵn sàng, scale ra nhiều instance và cần backpressure/monitoring.

**Ưu tiên `@JmsListener`** và cấu hình listener container; hạn chế vòng lặp polling bằng `receive`/`receiveAndConvert`. Đồng bộ phù hợp hơn cho tool quản trị, batch/poll có nhịp, test, hoặc trường hợp business buộc phải chủ động lấy một message.

## 8. Lab chạy được: hai queue để so sánh kết quả

Để thấy cùng một nội dung tạo ra hai kiểu kết quả khác nhau, **không** gọi `receive` và `receiveAndConvert` lần lượt trên **cùng một queue chỉ có một message**. Lab tạo **hai queue**, mỗi queue có một bản payload String.

Stack được chỉ định rõ: Java 17+, Spring Boot **3.5.x** (Spring Framework 6.x), Maven, và ActiveMQ Artemis embedded. Broker nhúng chỉ phục vụ thí nghiệm local, không để kiểm tra HA/persistence production.

### 8.1. Maven dependencies

Tạo project bằng https://start.spring.io/ với:
- Project: **Maven**, Java.
- Java **17** hoặc mới hơn được Boot 3.5 hỗ trợ.
- Spring Boot **3.5.x**.
- Group `com.example`, artifact `receive-demo`, package `com.example.receivedemo`.
- Dependency: **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`).

Thêm broker embedded vào `pom.xml` có Spring Boot parent/BOM:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

Boot quản lý version tương thích khi project đã dùng parent/BOM chuẩn. Trong project không có embedded broker dependency, `spring.artemis.mode=embedded` sẽ không hoạt động như mong muốn.

### 8.2. application.properties

Tạo file `src/main/resources/application.properties`:

~~~properties
spring.application.name=receive-demo
spring.main.web-application-type=none
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.raw,demo.converted
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

- `demo.raw` và `demo.converted` là **hai queue độc lập**, không phải hai consumer trên cùng message.
- `spring.jms.pub-sub-domain=false` chọn queue khi template resolve tên destination.
- Embedded persistence tắt vì chỉ phục vụ lab; restart không dùng để chứng minh backlog bền vững.

### 8.3. Java code hoàn chỉnh

Lưu `src/main/java/com/example/receivedemo/ReceiveDemoApplication.java`:

~~~java
package com.example.receivedemo;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class ReceiveDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReceiveDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner compareReceiveApis(JmsTemplate template) {
        return args -> {
            // Đặt giới hạn chờ để tránh treo lab khi cấu hình broker sai.
            template.setReceiveTimeout(2_000L);

            // Hai message chứa nội dung gần như giống nhau ở hai queue.
            template.send("demo.raw", session -> {
                TextMessage message =
                        session.createTextMessage("invoice-17");
                message.setStringProperty("eventType", "InvoiceReady");
                return message;
            });
            template.convertAndSend("demo.converted", "invoice-18");

            // Phương án 1: API trả JMS Message.
            Message raw = template.receive("demo.raw");
            if (!(raw instanceof TextMessage text)) {
                throw new IllegalStateException(
                        "Expected raw TextMessage but got " + raw);
            }

            System.out.println("RAW type=TextMessage");
            System.out.println("RAW body=" + text.getText());
            System.out.println("RAW eventType="
                    + text.getStringProperty("eventType"));

            // Phương án 2: converter mặc định trả String.
            Object converted =
                    template.receiveAndConvert("demo.converted");
            if (!(converted instanceof String body)) {
                throw new IllegalStateException(
                        "Expected converted String but got " + converted);
            }

            System.out.println("CONVERTED type=String");
            System.out.println("CONVERTED body=" + body);

            // Queue đã trống -> chờ tối đa 2 giây rồi null.
            Object empty =
                    template.receiveAndConvert("demo.converted");
            System.out.println(
                    "EMPTY result=" + (empty == null ? "null" : empty));
        };
    }
}
~~~

Mã chỉ dùng Java 17, Spring Boot 3.5 và Jakarta Messaging do starter cung cấp. Không cần `@EnableJms` vì không tạo `@JmsListener` trong lab; `JmsTemplate` được Boot auto-configure khi đúng classpath.

Chạy từ thư mục dự án:

~~~bash
./mvnw spring-boot:run
~~~

Trên PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Với hai queue mới trống, không có consumer khác cạnh tranh và `SimpleMessageConverter` mặc định, các dòng **nghiệp vụ** sẽ như sau (xen giữa log Spring/Artemis):

~~~text
RAW type=TextMessage
RAW body=invoice-17
RAW eventType=InvoiceReady
CONVERTED type=String
CONVERTED body=invoice-18
EMPTY result=null
~~~

Các dòng trên được in theo đúng thứ tự trong `ApplicationRunner`. Lần nhận rỗng chờ khoảng 2 giây; tổng thời gian thực tế có thể khác do khởi tạo và scheduling. Nếu chạy lại với broker/persistence bên ngoài có backlog hoặc consumer khác, kết quả phải được giải thích dựa trên trạng thái queue, không coi mẫu output là bảo đảm độc lập môi trường.

**Giải thích từng bước:**

1. `send("demo.raw", ...)` tự tạo `TextMessage` có body `invoice-17` và JMS property `eventType`.
2. `convertAndSend("demo.converted", "invoice-18")` dùng converter mặc định để tạo một `TextMessage` khác.
3. `receive("demo.raw")` trả đối tượng `TextMessage`, cho phép đọc property và `getText()`.
4. `receiveAndConvert("demo.converted")` tự đọc message rồi dùng `SimpleMessageConverter` trả `String`.
5. Lần `receiveAndConvert` tiếp theo không còn message trong queue, chờ tới timeout và trả `null`.

**Điều bài lab KHÔNG chứng minh:** rollback khi business logic thất bại, exactly-once processing, durability qua restart, hoặc hành vi conversion khi có JSON converter tùy chỉnh. Đó là các thuộc tính cấu hình/bài kiểm thử riêng.

### 8.4. Thay đổi lab để quan sát type mismatch

Đổi producer của `demo.converted` thành:

~~~java
// Mảnh thay thế cho dòng convertAndSend(String)
template.convertAndSend("demo.converted", new byte[] {65, 66});
~~~

Với `SimpleMessageConverter`, kết quả từ `receiveAndConvert("demo.converted")` giờ thường là `byte[]` chứ không phải `String`. Phần `instanceof String` sẽ thất bại; chính vì vậy **kiểm tra kiểu trước khi cast** rất quan trọng. Đổi sang `receive("demo.converted")` thì raw type là `BytesMessage`.

Thử nghiệm này cũng cho thấy lỗi cast trong code sau khi nhận không tự hoàn tác message đã được tiêu thụ.

## 9. JMS message selector: receiveSelected và receiveSelectedAndConvert

Nếu chỉ muốn lấy một nhóm message trong queue, sử dụng selector đúng JMS syntax. Selector thường so khớp **JMS message properties**, không phân tích JSON.

Ví dụ producer:

~~~java
// Mảnh code trong app có JmsTemplate.
jmsTemplate.send("jobs.in", session -> {
    TextMessage message = session.createTextMessage("job-101");
    message.setStringProperty("kind", "render");
    message.setIntProperty("priorityGroup", 2);
    return message;
});
~~~

Nhận raw:

~~~java
Message message = jmsTemplate.receiveSelected(
        "jobs.in", "kind = 'render' AND priorityGroup >= 2");

if (message instanceof TextMessage txt) {
    System.out.println(txt.getText());
}
~~~

Nhận đã convert (trên **message khác** đủ điều kiện):

~~~java
Object payload = jmsTemplate.receiveSelectedAndConvert(
        "jobs.in", "kind = 'render' AND priorityGroup >= 2");
~~~

Lưu ý:
- Cần **hai message** hợp lệ để hai ví dụ đều nhận được nội dung; ví dụ thứ nhất đã tiêu thụ bản đầu.
- JMS selector là biểu thức để broker/client nhận ra message đủ điều kiện theo quy tắc provider, không phải SQL database. Property không tồn tại hoặc kiểu dữ liệu khác có thể khiến message không khớp.
- `JMSType` và các header mà selector hỗ trợ có quy định riêng; đừng mặc định mọi JMS header đều truy vấn được bằng selector.
- `receiveSelectedAndConvert` vẫn chịu cùng converter, timeout và transaction semantics như `receiveAndConvert`.
- Selector không thay authorization của broker; một consumer được quyền đọc queue có thể tạo selector khác nếu không có kiểm soát.

## 10. Conversion exception và retry: lỗi ở đâu?

Hãy tách các pha để chẩn đoán:

~~~text
[Broker có message]
       |
[Nhận qua Session/MessageConsumer] ---- network/JMSException
       |
[JmsTemplate xử lý local ACK/COMMIT nếu nó quản lý Session]
       |
[Return Message ra receive()] -----> caller tự lấy body/header
       |
[Converter.fromMessage] ------------ conversion/schema/deserialization error
       |
[Return Object ra receiveAndConvert()]
       |
[Business logic] ------------------- DB/API/validation failure
~~~

Ví dụ các lỗi:

| Triệu chứng | Nguyên nhân khả dĩ | Điều cần làm |
| --- | --- | --- |
| `receive` trả `null` | Timeout, queue trống, selector không khớp | Phân biệt không có message với hỏng broker; kiểm tra metrics |
| `receiveAndConvert` trả `String` thay DTO | Converter mặc định đọc TextMessage | Cấu hình JSON converter hoặc parse chuỗi |
| `ClassCastException` sau receive | Caller ép kiểu sai Java result | `instanceof`, sửa contract, không cast mù |
| `MessageConversionException` | Converter không xử lý message type/schema | Kiểm tra converter bean, JMS type, type ID, schema |
| `JMSException`/Spring `JmsException` | Broker, session, permissions, timeout giao thức... | Log nguyên nhân gốc và trạng thái broker |
| `ClassNotFoundException`/`InvalidClassException` | ObjectMessage Java serialization không tương thích | Không dùng native serialized object làm contract liên dịch vụ |
| Consumer khác “ăn” message trước | Competing consumers trên queue | Xác định quyền sở hữu queue và nhóm consumer |
| Không thấy message trong Topic khi polling | Non-durable subscription không tồn tại lúc publish | Xác định domain/subscription/durability |
| Lỗi parsing JSON sau khi raw receive | JSON không hợp schema | Tách transport lỗi và validation lỗi; dùng quarantine/DLQ nếu cần |
| Gửi xong rồi receive chờ mãi | Sai queue/topic, tên, timeout, broker hoặc session/selector | Xác nhận đúng destination, nhận với finite timeout, kiểm tra broker |

**Cách xử lý poison message:** Đừng lấy đi lấy lại một message hỏng trong một loop không giới hạn. Thiết kế retry có backoff/max attempts, DLQ/quarantine và cảnh báo. Nếu dùng `receiveAndConvert` ngoài external transaction, conversion failure có thể diễn ra **sau local commit**, nên không trông cậy rằng broker sẽ tự đưa message lỗi trở lại hàng đợi.

## 11. Chiến lược kiểm thử và contract

### 11.1. Test tình huống tối thiểu

| Bài test | Kỳ vọng |
| --- | --- |
| `TextMessage("ok")` + `receive` | Raw object là `TextMessage`, đọc `getText()` được `ok` |
| `TextMessage("ok")` + `receiveAndConvert` | Converter mặc định trả `String "ok"` |
| `BytesMessage` + `receiveAndConvert` | Thường trả `byte[]` nếu dùng `SimpleMessageConverter` |
| Queue trống + timeout 500 ms | Hai phương thức trả `null` thay vì block vô hạn |
| Queue trống + timeout default | Lời gọi có thể chờ vô thời hạn; test không chạy trực tiếp vô giới hạn |
| Hai consumer tranh cùng queue | Một message có thể bị một consumer nhận, không phát hai bản |
| JSON TextMessage + converter mặc định | Java result là chuỗi JSON, không phải DTO |
| JSON TextMessage + converter JSON được gắn đúng | Có thể tạo DTO theo type/schema config |
| Header/property được gán | `receive` đọc được; `receiveAndConvert` đơn giản chỉ trả payload |
| Receive + business fail sau return | Không tự rollback JMS local commit |
| External JMS transaction + handler fail | Kiểm tra rollback/redelivery với broker thật và policy |
| Selector đúng và sai | Chỉ message có property phù hợp được nhận |
| Producer có type không được dự kiến | Phải báo lỗi type contract và bảo toàn observability |
| Message có `JMSRedelivered=true` | Log/đánh dấu được, nhưng vẫn dùng business ID chống trùng |

### 11.2. Vì sao test mock đơn thuần chưa đủ?

Unit test một custom `MessageConverter` rất hữu ích: nó kiểm tra `fromMessage` có cho ra đúng DTO không. Nhưng mock không chứng minh timeout, broker ack, transaction boundary, consumer concurrency hoặc DLQ. Cần integration test với broker cấu hình gần production (Artemis độc lập hoặc container) cho các hành vi vận chuyển.

Một kiểm thử đáng làm về reliability:

1. Gửi một message có `businessId` cố định vào queue test.
2. Nhận trong **JMS transaction bên ngoài**.
3. Trong converter/handler, chủ động ném lỗi chưa xử lý.
4. Xác minh transaction rollback và message có thể được redeliver theo broker policy.
5. Sau đó xử lý thành công với idempotency, kiểm tra business outcome không bị tạo hai lần.
6. Lặp lại không có external transaction để thấy vì sao `receiveAndConvert` không tự giữ message cho đến khi handler hoàn tất.

**Không chạy bài test phá dữ liệu trên broker chung.** Dùng queue riêng và cấu hình retry/DLQ đã được kiểm soát.

## 12. @JmsListener và JmsMessagingTemplate: đừng nhầm API

`@JmsListener`:

~~~java
@Component
class OrderListener {

    @JmsListener(destination = "orders.in")
    public void onOrder(String orderId) {
        // Spring container lắng nghe liên tục,
        // chuyển message vào method theo cấu hình converter.
    }
}
~~~

Đây là **mảnh class** yêu cầu imports `org.springframework.stereotype.Component`, `org.springframework.jms.annotation.JmsListener` và listener infrastructure. Nó không phải `receiveAndConvert` được viết lại theo cách bất đồng bộ: container có lifecycle, error handling và session transaction riêng.

`JmsMessagingTemplate`:
- Sử dụng abstraction `org.springframework.messaging.Message<?>`, khác `jakarta.jms.Message`.
- Có API typed `receiveAndConvert(destinationName, Class<T>)` trong các phiên bản Spring tương ứng.
- Việc chọn nó thay `JmsTemplate` là quyết định abstraction, không thay được nhu cầu timeout, transaction, idempotency hoặc broker setup.
- Nếu yêu cầu chủ yếu là payload/domain, API typed có thể hữu ích; nếu cần header JMS nguyên bản, `JmsTemplate.receive` dễ quan sát hơn.

## 13. Những sai lầm phổ biến

1. **Nghĩ `receiveAndConvert` không block.** Tên chỉ nói về conversion, không nói execution model.
2. **Đặt receive trong HTTP handler mà không có timeout.** Mặc định có thể chờ vô thời hạn, chiếm worker thread.
3. **Gọi receive rồi receiveAndConvert để “đọc cùng một message hai cách”.** Lần đầu đã nhận/tiêu thụ message; lần sau là một lần nhận độc lập.
4. **Tin converter mặc định tự parse JSON.** `TextMessage` thường trở thành `String`; DTO cần JSON codec/schema.
5. **Ép kiểu trực tiếp về DTO.** Converter có thể trả `String`, `byte[]`, `Map` hoặc object khác.
6. **Cho rằng chỉ `receiveAndConvert` mới có thể trả null.** Cả hai trả null nếu timeout, và converter tùy biến có thể có null payload.
7. **Cố gọi `acknowledge` sau business processing với message lấy từ template.** Session có thể đã ack/commit/đóng; không tự thiết lập semantics trễ.
8. **Dùng `setSessionTransacted(true)` rồi tưởng handler sau receive nằm trong JMS transaction.** Transaction local do template tạo có thể commit ngay khi receive.
9. **Bỏ qua conversion failure xảy ra sau commit.** Đặt transaction boundary đúng hoặc dùng listener container.
10. **Đọc JSON field qua JMS selector.** Selector truy vấn JMS properties/headers phù hợp, không parse payload JSON.
11. **Đặt no-wait trong vòng lặp không có backoff.** Tạo busy poll và tốn tài nguyên.
12. **Dùng ObjectMessage giữa các service độc lập mà không kiểm soát deserialization.** Coupling Java class và rủi ro bảo mật.
13. **Không thống nhất queue/topic domain.** Producer gửi topic, template receive queue cùng tên là hai destination logic khác nhau.
14. **Không tách broker delivery khỏi business success.** ACK/commit JMS và DB/HTTP side effect thường không atomic.
15. **Không có idempotency key hay DLQ.** Redelivery khi process crash vẫn có thể gây side effect trùng.

## 14. Checklist quyết định trước khi code

- **Dữ liệu:** Tôi cần JMS `Message` đầy đủ hay chỉ Java payload?
- **Metadata:** Có cần `JMSMessageID`, `CorrelationID`, `JMSRedelivered`, properties/selector không?
- **Converter:** Đúng `SimpleMessageConverter` hay converter JSON tùy chỉnh? Được cấu hình ở producer **và** consumer chưa?
- **Kiểu:** Result kỳ vọng là `String`, `byte[]`, `Map` hay DTO? Có `instanceof`/validation?
- **Destination:** Tên queue/topic đúng không? Có default destination nếu gọi overload không tham số?
- **Timeout:** Có giới hạn chờ và chiến lược xử lý `null` không? Có vô tình block HTTP thread?
- **Business ownership:** Message được lấy đi để làm công việc gì? Có ai cạnh tranh cùng queue không?
- **Reliability:** JMS local commit xảy ra lúc nào? Converter và business logic có nằm trong transaction ngoài không?
- **Idempotency:** Khi cùng message được redeliver, dữ liệu hoặc side effect có bị nhân đôi không?
- **Failure handling:** Conversion/schema error được quan sát, retry và đưa vào DLQ như thế nào?
- **Lifecycle:** Consumer là polling có nhịp, hay một service 24/7 nên dùng `@JmsListener`?
- **Integration test:** Đã thử broker thật, timeout, selector, type mismatch, rollback và retry chưa?

**Quy tắc kết luận:** Chọn **`receive()`** để lấy message JMS với header/property/body type và chủ động đọc dữ liệu; chọn **`receiveAndConvert()`** khi payload là điều bạn cần và converter đã được chuẩn hóa. Cả hai đều **synchronous receive** và đều cần thiết kế timeout, transaction, idempotency, retry/DLQ. Đừng dùng sự thuận tiện của converter để che đi thời điểm một message thực sự được xác nhận với broker.

## 15. Bài tập ôn luyện

1. Gửi `TextMessage("hello")` với JMS property `traceId="t-1"`. Viết hai đoạn code: một đoạn dùng `receive()` đọc body và property, đoạn còn lại dùng `receiveAndConvert()`; giải thích thông tin nào bị mất trong kết quả thứ hai.
2. Gửi duy nhất một message vào `task.in`, sau đó gọi `receive("task.in")` rồi `receiveAndConvert("task.in")` với timeout 1 giây. Vì sao lần sau có thể trả null?
3. Dùng `SimpleMessageConverter`, nhận payload JSON `{"amount":25}`. Java result thực chất là kiểu gì? Cần thêm những bước nào để có DTO `Payment`?
4. Một batch processor dùng `receiveAndConvert` rồi gọi payment API; payment thành công nhưng app crash trước khi ghi business outcome. Phân tích trạng thái JMS, cần idempotency key nào và giới hạn của JMS transaction đơn lẻ.
5. So sánh `setReceiveTimeout(0)`, `setReceiveTimeout(-1)` và `setReceiveTimeout(1500)`. Vì sao vòng lặp no-wait 100% CPU thường là thiết kế xấu?
6. Với `receiveSelectedAndConvert("orders.in", "kind = 'refund'")`, property `kind` nên được đặt ở đâu? Có thể đặt field `kind` chỉ trong JSON body rồi selector vẫn tự hiểu không?
7. Viết test integration cho converter cố tình throw exception trong và ngoài một JMS transaction bên ngoài, xác minh khác biệt về redelivery.
8. Hãy thay lab phần 8 để gửi `byte[]`, sau đó sửa nhánh xử lý với `instanceof byte[] bytes` và mô tả vì sao không nên cast cứng thành `String`.
9. Khi service muốn xử lý mọi message trong queue liên tục với 5 replicas và cần redelivery khi handler thất bại, nên chọn loop `receiveAndConvert` hay `@JmsListener`? Giải thích bằng ownership, transaction và lifecycle.

## Tài liệu tham khảo chính thức

- Spring Framework 6.2 — **Receiving a Message**, synchronous vs listener container: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Framework 6.2 — **Sending a Message / Message Converters**: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- Spring Framework 6.2 — **JmsTemplate API**: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework 6.2 — **SimpleMessageConverter**: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html
- Spring Framework — **Annotated JMS Listener Endpoints**: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Boot 3.5 — **JMS and Artemis support**: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Jakarta Messaging 3.1 — **Message, headers/properties, selectors and acknowledge**: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
