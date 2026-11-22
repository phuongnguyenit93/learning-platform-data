# Nhận Session để gửi phản hồi tùy chỉnh trong @JmsListener — Spring Framework JMS

## 1. Mục tiêu học tập

Một `@JmsListener` thông thường chỉ nhận payload và thực thi nghiệp vụ:

~~~java
@JmsListener(destination = "orders.requests")
public void handle(String payload) {
    System.out.println(payload);
}
~~~

Khi hệ thống cần **tạo reply bằng native JMS API**, Spring cho phép khai báo thêm tham số **`jakarta.jms.Session`** trên method. Đây là Session đang được listener container sử dụng để xử lý request, giúp responder tạo `MessageProducer`, các loại `Message` và gửi vào `JMSReplyTo` của message gốc.

Bài này giúp bạn:

1. Khai báo `@JmsListener` nhận **raw `jakarta.jms.Message`/`TextMessage` và `Session`**.
2. Phân biệt `Session` của listener với `ConnectionFactory`, `JmsTemplate`, producer, JMS message và destination.
3. Đọc `JMSReplyTo`, xử lý trường hợp null, tạo reply bằng `Session.createTextMessage(...)` và gửi bằng `Session.createProducer(...)`.
4. Bảo toàn `JMSCorrelationID` theo đúng giao thức request-reply; biết khi nào dùng request `JMSMessageID`.
5. Tùy chỉnh body, header/property, delivery mode, priority và TTL mà không làm thay đổi nhận request.
6. Hiểu local JMS transaction: **ACK request và send reply có thể cùng commit/rollback** khi dùng một Session transacted.
7. Biết tại sao **không được** `commit()`, `rollback()`, `close()` hoặc lưu Session vào field trong listener do container quản lý.
8. Phân biệt gửi thủ công với return value/`@SendTo`/`JmsResponse`, tránh **double reply**.
9. Chạy ví dụ **Java 17, Spring Boot 3.5, Artemis**: requester dùng `JmsTemplate.sendAndReceive(...)`, responder dùng injected Session.
10. Chẩn đoán request timeout, mất reply, duplicate, sai correlation, temporary queue hết hạn, lỗi transaction và DLQ.

> **Cốt lõi:** `Session` được inject vào một annotated listener là tài nguyên **thuộc listener container**. Sử dụng nó **ngay trong callback** để tạo và gửi phản hồi; để container/transaction manager quản lý commit, rollback, close và recovery.

## 2. Request-reply diễn ra như thế nào?

~~~text
Requester                             Responder / @JmsListener
     |                                         |
     | 1. tạo request TextMessage              |
     |    JMSReplyTo = temporary queue Q       |
     |    JMSCorrelationID = "req-42"           |
     |                                         |
     +------ send(request) ---> requests.queue +
                                               |
                                 2. nhận Message + Session
                                               |
                                 3. process payload
                                               |
                                 4. tạo reply TextMessage
                                    bằng cùng Session
                                               |
                                 5. gắn correlation, headers
                                               |
    <---- receive(reply) <--- reply queue Q ----+
     |                                         |
     | 6. kiểm tra correlation/status           |
     v                                         v
~~~

Ba header đặc biệt:

| Header | Do ai thiết lập? | Công dụng |
|---|---|---|
| `JMSReplyTo` | Requester, trước khi send | Địa chỉ `Destination` mà requester muốn nhận reply |
| `JMSCorrelationID` | Ứng dụng, thường trên cả request và reply | Liên hệ các message của cùng lượt giao tiếp |
| `JMSMessageID` | JMS provider khi send | Định danh JMS message; có thể dùng làm khóa correlation theo một protocol khác |

**Không đồng nhất** ba trường trên: `JMSReplyTo` là một `Destination`, còn correlation là `String`/provider-native value. Reply thường có **JMSMessageID mới** do provider cấp; responder không được tự gán JMSMessageID của reply thành ID của request.

### 2.1. Requester chọn cách nhận

- **TemporaryQueue**: thuận tiện cho request-reply ngắn hạn, người sở hữu connection tạo consumer để chờ reply; responder ở connection khác có thể gửi vào.
- **Fixed reply Queue**: có thể hoạt động qua requester restart nhưng phải giải quyết correlation selectors, quyền và message orphan/TTL.
- **Topic reply**: cần quan tâm subscription lifecycle; non-durable subscriber offline có thể mất reply.

`JMSReplyTo` có thể chứa Queue, Topic hoặc TemporaryQueue; không nên tự đoán kiểu bằng chuỗi tên. Một `TemporaryQueue` do provider quản lý có danh tính đặc biệt: **không tạo lại từ String tùy tiện**.

## 3. Vì sao @JmsListener nhận được Session?

Hạ tầng annotation Spring tạo listener container cho annotated endpoint. `MessagingMessageListenerAdapter` cung cấp raw incoming `Message` và native `Session` như các **additional arguments** để `DefaultMessageHandlerMethodFactory`/argument resolvers chọn đưa vào method.

Các dạng tham số được Spring hỗ trợ gồm:

- Raw `jakarta.jms.Message` hoặc subclass như `TextMessage`, khi phù hợp incoming type.
- **`jakarta.jms.Session`**, phục vụ truy cập native JMS API.
- Payload Java thông thường (`String`, DTO...) qua message converter.
- `org.springframework.messaging.Message<T>` gồm payload và mapped headers.
- `@Header(...)` cho một header và `@Headers Map<...>` cho nhiều headers.

Đây là khả năng chính thức của **Spring Framework 6+**, không cần một custom resolver chỉ để nhận `Session`.

### 3.1. Ví dụ tối thiểu

~~~java
import jakarta.jms.Message;
import jakarta.jms.Session;
import jakarta.jms.JMSException;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class NativeResponder {

    @JmsListener(destination = "orders.requests")
    public void onRequest(Message request, Session session)
            throws JMSException {

        System.out.println(
                "incomingMessageId=" + request.getJMSMessageID());
        System.out.println(
                "sessionTransacted=" + session.getTransacted());
    }
}
~~~

Class này **chưa chạy độc lập**: cần Spring context, `@EnableJms`, JMS connection factory, listener container và broker. Nhưng signature `Message request, Session session` là hợp lệ.

### 3.2. Nhận TextMessage trực tiếp

~~~java
@JmsListener(destination = "orders.requests")
public void handle(TextMessage request, Session session)
        throws JMSException {

    String orderId = request.getText();
    Destination replyTo = request.getJMSReplyTo();
}
~~~

Spring sẽ đưa raw `TextMessage` vào tham số nếu request thực sự là TextMessage. Nếu sender gửi `BytesMessage`, `MapMessage` hoặc loại không khớp, listener phải thay signature hoặc chuyển đổi phù hợp. Không mặc định tất cả message đều là `TextMessage`.

### 3.3. Payload và Session cùng lúc

~~~java
@JmsListener(destination = "orders.requests")
public void handle(String payload, Session session) throws JMSException {
    // payload được convert.
    // session được inject độc lập với payload.
}
~~~

Đây là lựa chọn đơn giản khi đã biết **reply destination cố định**. Để truy cập chính `request.getJMSReplyTo()` hoặc raw provider headers, nên thêm raw Message/đổi signature thành raw Message + Session.

### 3.4. Namespace Jakarta và Java 17

Với Spring Framework 6.x, Spring Boot 3.x:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
~~~

Không trộn `javax.jms` (phần lớn các dự án Spring 5 cũ) vào cùng Spring 6 JMS configuration.

## 4. Cách gửi phản hồi thủ công trong listener

### 4.1. Ví dụ nhỏ nhất nhưng có xử lý trường hợp thiếu destination

~~~java
@JmsListener(destination = "orders.requests")
public void onRequest(TextMessage request, Session session)
        throws JMSException {

    Destination replyTo = request.getJMSReplyTo();
    if (replyTo == null) {
        throw new IllegalArgumentException(
                "Request has no JMSReplyTo destination");
    }

    TextMessage reply = session.createTextMessage(
            "accepted:" + request.getText());

    String correlationId = request.getJMSCorrelationID();
    if (correlationId == null || correlationId.isBlank()) {
        throw new IllegalArgumentException(
                "Missing JMSCorrelationID");
    }

    reply.setJMSCorrelationID(correlationId);
    reply.setStringProperty("statusCode", "ACCEPTED");

    try (MessageProducer producer = session.createProducer(replyTo)) {
        producer.send(reply);
    }
    // Không commit, rollback hoặc close Session do container cấp.
}
~~~

Đây là **method snippet**, có thể nằm trong class `@Component` được Spring scan. Những bước chính:

1. Đọc `request.getJMSReplyTo()`.
2. Validate destination theo contract.
3. Dùng **Session được inject** để tạo **message mới**.
4. Copy correlation do requester chọn.
5. Gắn status code bằng JMS property.
6. Tạo producer từ cùng Session; gửi reply.
7. Đóng **producer do method tạo**, không đóng Session.
8. Method hoàn tất bình thường hoặc ném lỗi để container xử lý transaction.

### 4.2. Vì sao không gửi lại incoming Message?

~~~java
// Anti-pattern:
producer.send(request);
~~~

Incoming Message có body/header/properties thuộc request, có thể có provider-managed fields và dữ liệu nhạy cảm. Provider còn có thể đặt lại ID/timestamp khi send. Gửi lại nguyên message gây nhầm lẫn ý nghĩa. Tạo reply mới giúp định nghĩa rõ:

- Kiểu message (TextMessage, BytesMessage...).
- Body và schema.
- Status/result headers.
- Correlation ID.
- TTL và delivery mode.
- Quy tắc bảo mật dữ liệu.

### 4.3. Có thể tạo một producer không ràng destination

~~~java
try (MessageProducer producer = session.createProducer(null)) {
    producer.send(replyTo, reply);
}
~~~

JMS classic API cho phép producer được tạo với `Destination=null` rồi chọn destination trong từng send. Cách đó hữu ích khi cần gửi vài message đến destination khác nhau trong cùng Session. Không nên phát nhiều replies cho một request trừ khi giao thức quy định rõ.

### 4.4. Có cần gọi Session.createQueue(...) không?

Không nếu `JMSReplyTo` đã chứa `Destination` đúng:

~~~java
Destination replyTo = request.getJMSReplyTo();
MessageProducer producer = session.createProducer(replyTo);
~~~

Nếu bạn cố `session.createQueue(replyTo.toString())` thì có thể tạo tham chiếu sai, đặc biệt với TemporaryQueue. Hãy dùng **đúng đối tượng Destination được gửi kèm request**.

## 5. Xử lý trường hợp JMSReplyTo null

`JMSReplyTo` là header tùy chọn; không phải mọi message đều yêu cầu response. Có ba policy hợp lệ, phải do **hợp đồng nghiệp vụ** chọn:

| Policy | Mục đích | Cách hành động |
|---|---|---|
| Bắt buộc reply | Request-reply RPC/command | Từ chối request nếu thiếu `JMSReplyTo` |
| Reply vào queue mặc định | Hệ thống quy định fallback ổn định | Gửi tới Queue đã provision và requester biết |
| Không cần reply | Event/fire-and-forget | Xử lý rồi return bình thường |

Ví dụ fallback cố định:

~~~java
Destination replyTo = request.getJMSReplyTo();
if (replyTo == null) {
    replyTo = session.createQueue("orders.responses");
}
~~~

Đây chỉ là **snippet**. `Session.createQueue(name)` tạo **Queue object reference**, **không bảo đảm cấp phát queue vật lý** trong broker; cần provision hoặc chính sách auto-create đúng.

Nếu thiếu `JMSReplyTo` là lỗi **không thể tự sửa**, rollback vô hạn chỉ gây poison loop. Có thể đưa request vào DLQ/quarantine hoặc trả lỗi qua kênh được quản trị; không tự tạo tên Queue từ user input.

### 5.1. TemporaryQueue có thể biến mất khi requester đóng connection

Theo Jakarta Messaging, temporary destinations có phạm vi connection sở hữu. Chỉ connection đó được phép tạo consumer trên temporary destination, **nhưng các connection khác có thể gửi vào nó** nếu có destination reference và quyền phù hợp.

Tình huống:

~~~text
Requester tạo TemporaryQueue Q
   |
   +-- gửi request chứa JMSReplyTo=Q
   |
   +-- chờ reply 3s
   |
   +-- timeout, đóng connection → Q bị xóa
                                |
Responder xử lý lâu 10s ------+
   |
   +-- send reply to Q → có thể thất bại
~~~

JMS không bảo đảm một TemporaryQueue vẫn tồn tại sau khi requester connection đóng. Vì vậy cần deadline/timeout/late reply policy. Nếu responder xử lý hàng phút và requester có thể offline, fixed reply Queue hoặc async callback workflow có thể phù hợp hơn.

### 5.2. Địa chỉ phản hồi và bảo mật

Không coi `JMSReplyTo` là yêu cầu phải được tin tuyệt đối. Nếu ứng dụng nhận message từ nguồn không tin cậy và dùng một principal được quyền gửi mọi Queue, kẻ tấn công có thể cung cấp reply destination không mong muốn. Trong hệ thống nhiều tenant:

- Broker ACL phải giới hạn `send` theo account/namespace.
- Nếu contract cho phép, kiểm tra tên/loại destination và reply policy.
- Không log toàn bộ payload/header nhạy cảm.
- Quota/TTL hạn chế tài nguyên tạm.
- Không tạo Queue vật lý tùy tiện theo `JMSReplyTo.toString()`.

## 6. Thiết kế correlation ID

### 6.1. Có hai pattern được dùng rộng rãi

**Pattern A — requester tạo ID ngay từ đầu:**

~~~text
Request:
  JMSCorrelationID = req-42
  JMSMessageID = ID:provider-request-1

Reply:
  JMSCorrelationID = req-42
  JMSMessageID = ID:provider-reply-2
~~~

Responder echo request correlation vào reply. Đây là pattern dùng trong demo.

**Pattern B — reply dùng JMSMessageID của request làm correlation:**

~~~text
Request:
  JMSCorrelationID = null
  JMSMessageID = ID:provider-request-1

Reply:
  JMSCorrelationID = ID:provider-request-1
~~~

Hai pattern không tương đương ở phía requester. Nếu consumer trên reply queue dùng selector `JMSCorrelationID = 'req-42'`, response của pattern B **sẽ không match**. Hãy thống nhất protocol trước khi triển khai.

### 6.2. Khi có chính sách fallback

~~~java
String correlation = request.getJMSCorrelationID();

if (correlation == null || correlation.isBlank()) {
    // Chỉ thực hiện nếu protocol cho phép dùng request ID.
    correlation = request.getJMSMessageID();
}

if (correlation == null || correlation.isBlank()) {
    throw new IllegalArgumentException("Cannot derive correlation ID");
}

reply.setJMSCorrelationID(correlation);
~~~

Bản thân việc fallback không sai, nhưng chỉ phù hợp khi requester thực sự chấp nhận mô hình B. JMSMessageID có thể null nếu provider chấp nhận hint tắt ID. Do đó, **nếu contract đòi hỏi application correlation, không nên fallback tự động**; hãy reject request thiếu header.

### 6.3. Dùng đúng getter/setter

~~~java
String receivedCorrelation = request.getJMSCorrelationID();
reply.setJMSCorrelationID(receivedCorrelation);
~~~

Không dùng `reply.setJMSMessageID(request.getJMSMessageID())`: ID của reply do provider thiết lập khi gửi. `JMSCorrelationID` là trường do ứng dụng đặt để liên hệ request và response.

### 6.4. Correlation ID không thay thế event ID

`JMSCorrelationID` có thể đại diện cả một workflow gồm nhiều events. Với retry/redelivery, cần một **business request ID/event ID ổn định** để bảo đảm idempotency. `JMSXDeliveryCount` và `JMSRedelivered` cũng không chứng minh business handler đã chạy thành công trong lượt delivery trước.

## 7. Tùy chỉnh reply body và application properties

Session có các phương thức tạo message:

~~~java
TextMessage text = session.createTextMessage("ok");
BytesMessage bytes = session.createBytesMessage();
MapMessage map = session.createMapMessage();
ObjectMessage object = session.createObjectMessage();
~~~

Chúng là các kiểu native Jakarta JMS, không phải Spring Messaging Message. Trong thực tế:

- `TextMessage`: JSON/text nếu requester mong kiểu text.
- `BytesMessage`: binary payload có định dạng/schema rõ.
- `MapMessage`: dữ liệu key-value type giới hạn theo JMS.
- `ObjectMessage`: Java serialization; liên hệ rủi ro bảo mật/class compatibility. Không dùng tùy tiện cho hệ thống liên dịch vụ.

### 7.1. Tạo reply dạng text với metadata

~~~java
TextMessage reply = session.createTextMessage(
        "{\"status\":\"ACCEPTED\",\"orderId\":\"42\"}");

reply.setJMSCorrelationID("req-42");
reply.setStringProperty("statusCode", "ACCEPTED");
reply.setStringProperty("schemaVersion", "1");
reply.setStringProperty("requestEventId", "evt-42");
~~~

JSON ở đây là ví dụ cố định. Trong ứng dụng thật, không nối chuỗi user input để tạo JSON; dùng serializer và schema validation. `MessageConverter` của `JmsTemplate` **không tự chạy** khi bạn tạo raw `TextMessage` bằng Session.

### 7.2. Header và property không nên sao chép bừa bãi

JMS có header provider-owned như `JMSMessageID`, `JMSTimestamp`, `JMSExpiration` và các field do app được đặt như `JMSCorrelationID`. **Không sao chép toàn bộ headers** từ request sang reply; hãy chọn tối thiểu những trường contract yêu cầu, ví dụ correlation, schemaVersion, eventId, statusCode.

JMS properties tên bắt đầu `JMSX` hoặc `JMS_` có quy tắc provider/spec riêng. Tạo application properties như `statusCode`, `requestEventId`; không tùy tiện gắn các trường vào reserved namespace.

### 7.3. QoS per reply: delivery mode, priority và TTL

Có thể dùng producer send overload:

~~~java
import jakarta.jms.DeliveryMode;

try (MessageProducer producer = session.createProducer(replyTo)) {
    producer.send(
            reply,
            DeliveryMode.PERSISTENT,
            4,
            10_000L);
}
~~~

- `DeliveryMode.PERSISTENT` yêu cầu cấp độ delivery bền vững theo spec/provider; không biến TemporaryQueue thành queue sống qua connection close.
- Priority từ 0 đến 9, 4 thường là giá trị mặc định; không phải SLA tuyệt đối về order.
- TTL 10.000 ms; hết hạn thì broker có thể không giao message.
- Producer options này áp dụng cho lượt gửi reply đó, không tự thay cấu hình `JmsTemplate` của requester.

Không cần `JmsTemplate.setExplicitQosEnabled(true)` khi dùng **MessageProducer trực tiếp**. Thuộc tính `explicitQosEnabled` thuộc cấu hình cách `JmsTemplate` gọi send.

### 7.4. Timeout requester khác TTL reply

Requester có thể chờ 5 giây; reply TTL 10 giây; request business deadline có thể 3 giây. Ba cơ chế đó khác nhau:

| Thông số | Ai áp dụng? | Ý nghĩa |
|---|---|---|
| Receive timeout | Requester | Chờ tối đa bao lâu |
| Reply TTL | Producer và broker | Reply tồn tại/được giao trong bao lâu |
| Business deadline | Ứng dụng | Request còn giá trị nghiệp vụ hay không |

Nếu requester timeout, reply đến sau có thể trở thành orphan. Với temporary queue, connection requester đóng khiến reply không thể được nhận như cũ. Hãy thiết kế late reply handling, DLQ, logging và retry.

## 8. Vòng đời Session thuộc listener container

### 8.1. Có thể dùng gì trong callback?

~~~java
@JmsListener(destination = "orders.requests")
public void handle(Message request, Session session) throws JMSException {
    Destination replyTo = request.getJMSReplyTo();
    // Tạo Message, MessageProducer và gửi reply ở đây.
}
~~~

Nên:

- Đọc incoming headers/payload.
- Tạo native JMS Message bằng Session đang được container cấp.
- Tạo producer, gửi reply, đóng producer do mình tạo.
- Return thành công hoặc ném exception phù hợp để container quản lý transaction.

Không nên:

~~~java
session.commit();   // Container/transaction manager sở hữu commit.
session.rollback(); // Không tự chen transaction boundary.
session.close();    // Không đóng tài nguyên thuộc container.
~~~

Nếu listener factory dùng transacted Session, commit/rollback do container kiểm soát **sau khi callback kết thúc**. Trong JTA-managed session, quy tắc transaction lại thuộc JTA manager, càng không nên tự commit.

### 8.2. Không giữ Session vào singleton field

~~~java
// Anti-pattern: không an toàn về lifecycle và concurrency.
private Session savedSession;

@JmsListener(destination = "orders.requests")
public void onMessage(Message request, Session session) {
    savedSession = session;
}
~~~

Session có tính tuần tự, chỉ nên do một thread điều khiển ở một thời điểm. Sau callback container có thể trả Session vào cache, commit, rollback hoặc đóng. Dùng `savedSession` từ một thread khác có thể gây race, lỗi provider hoặc gửi message trong transaction sai.

### 8.3. Không truyền Session qua executor

~~~java
// Anti-pattern:
executor.submit(() -> sendReplyLater(session, request));
~~~

Callback có thể return trước khi task chạy; Session đã rời lifecycle của method. Nếu muốn xử lý bất đồng bộ, sao chép **dữ liệu bất biến** như requestId, payload và destination theo hợp đồng; sau đó tạo một JMS operation mới qua ConnectionFactory/JmsTemplate có transaction và error handling riêng. Nhưng send reply ấy **không còn tự nằm cùng JMS transaction nhận request**.

### 8.4. Đóng producer do mình tạo

~~~java
try (MessageProducer producer =
             session.createProducer(replyTo)) {
    producer.send(reply);
}
~~~

`MessageProducer` của classic JMS implements `AutoCloseable`; đóng producer không đóng Session. Nếu producer có lifecycle do pool/provider quản lý khác, hãy tuân theo cơ chế quản lý tương ứng, nhưng nguyên tắc chung là **listener không đóng Session của container**.

## 9. Transaction: nhận request và gửi reply cùng Session

### 9.1. Với factory transacted

Nếu listener container cấu hình:

~~~java
factory.setSessionTransacted(true);
~~~

thì, trong local JMS transaction, listener nhận request M và gửi reply R qua **chính Session đó**:

~~~text
JMS Transaction T
    |
    +-- receive request M
    |
    +-- xử lý payload
    |
    +-- producer.send(reply R) trên cùng Session
    |
    +-- listener method return
    |
    +-- container COMMIT T
             |
             +-- ACK request M
             +-- publish reply R
~~~

Nếu method ném exception khiến container rollback:

~~~text
JMS Transaction T
    |
    +-- receive request M
    +-- producer.send(reply R)
    +-- exception
    |
    +-- container ROLLBACK T
             |
             +-- M có thể được redeliver
             +-- R chưa commit bị hủy
~~~

**Đây là JMS local atomicity**, không phải bảo đảm mọi database update hoặc API bên ngoài tự rollback. Khi requester thấy reply, JMS transaction của responder đã cho phép reply được delivery; nhưng vẫn cần xem trạng thái nghiệp vụ ngoài JMS.

### 9.2. Vì sao không dùng một JmsTemplate khác tùy ý?

~~~java
// Trong listener:
jmsTemplate.convertAndSend("orders.responses", "accepted");
~~~

Đây là một cách gửi hợp lệ, nhưng không được **tự động suy** rằng nó nằm trong cùng Session/transaction nhận request. `JmsTemplate` có thể lấy Session khác từ ConnectionFactory/wrapper; với `JmsTransactionManager` hoặc JTA, resource binding có quy tắc riêng. Nếu mục tiêu là bảo vệ **ACK request + send reply trong cùng local JMS transaction**, dùng **injected Session** là cách rõ ràng nhất của bài.

### 9.3. Nếu factory không transacted?

Ở `DefaultMessageListenerContainer`, `AUTO_ACKNOWLEDGE` mặc định có thể acknowledge message **trước khi callback xử lý**. Nếu gửi reply thất bại, request có thể đã ACK và không được broker phát lại. Vì vậy nếu nghiệp vụ yêu cầu độ tin cậy, hãy cấu hình transacted listener và thử nghiệm lỗi send, exception, broker restart.

Đừng xem việc method `throws JMSException` là tự đủ để đảm bảo retry dưới mọi ack mode.

### 9.4. Đừng nuốt lỗi gửi

~~~java
try {
    producer.send(reply);
} catch (JMSException ex) {
    logger.error("Cannot reply", ex);
    // SAI nếu method return như thành công:
    // container có thể commit request.
}
~~~

Nếu lỗi cần rollback, để `JMSException` lan ra hoặc ném một runtime exception:

~~~java
try {
    producer.send(reply);
} catch (JMSException ex) {
    throw new IllegalStateException("Reply send failed", ex);
}
~~~

Việc quản lý retry/backoff, max attempts, DLQ cần được broker/container thiết kế rõ ràng. Một request thiếu reply destination không thể sửa bằng retry liên tục nên cần quarantine hoặc protocol error policy.

### 9.5. Database và HTTP side effects nằm ngoài local JMS transaction

Ví dụ:

~~~text
receive request
     |
     +-- DB update + DB COMMIT thành công
     |
     +-- send reply trong JMS transacted Session
     |
     +-- JMS COMMIT mất network, outcome không rõ
     |
     +-- broker có thể redeliver request
~~~

DB đã commit **không tự rollback**. Khi request được phát lại, handler có thể cập nhật dữ liệu lần nữa nếu thiếu idempotency. Nên gắn `requestId`/`eventId` ổn định và dùng unique constraint/idempotency record trong cùng DB transaction với business update, hoặc outbox/JTA/XA nếu kiến trúc yêu cầu. Cũng cần xử lý external API/payment idempotently.

### 9.6. Transaction requester và deadlock

Một requester có thể vô tình:

~~~text
requester transacted Session:
    send(request) chưa commit
    receive(reply) đang chờ
    commit() chỉ gọi sau reply
~~~

Responder chưa thấy request chưa commit, nên có thể không trả lời; requester timeout hoặc deadlock logic. Với `JmsTemplate.sendAndReceive` trong demo bên dưới, ta dùng **requester template non-transacted** và không đặt lời gọi trong một JMS transaction bên ngoài.

## 10. Khi nào dùng @SendTo hoặc JmsResponse thay vì Session?

Spring có phản hồi tự động; hãy chọn cách đơn giản nhất đáp ứng hợp đồng.

### 10.1. Return value và @SendTo

~~~java
@JmsListener(destination = "orders.requests")
@SendTo("orders.responses")
public String process(String orderId) {
    return "accepted:" + orderId;
}
~~~

Spring đóng gói return value thành JMS Message rồi gửi tới `JMSReplyTo` của request nếu có, hoặc default reply destination theo cấu hình `@SendTo`/listener. Đây là lựa chọn tốt nếu reply chỉ là payload đơn giản.

### 10.2. JmsResponse cho destination ở runtime

~~~java
@JmsListener(destination = "orders.requests")
public JmsResponse<String> process(String orderId) {
    return JmsResponse.forQueue(
            "accepted:" + orderId,
            "orders.status");
}
~~~

`JmsResponse` thuộc `org.springframework.jms.listener.adapter`. Đây là snippet minh họa cơ chế reply thông qua return value mà vẫn chọn destination theo runtime. Không cần thao tác trực tiếp native Session khi muốn framework xử lý converter/reply.

### 10.3. Session thủ công khi cần kiểm soát sâu

Dùng injected Session nếu cần:

- Tạo native `TextMessage`/`BytesMessage` cụ thể.
- Đọc chính đối tượng `JMSReplyTo`, đặc biệt TemporaryQueue.
- Thiết lập correlation ID và JMS properties chính xác theo protocol.
- Điều khiển per-send QoS của native producer.
- Gửi reply trong chính JMS local transaction của listener.
- Có multiple sends trong một transaction theo yêu cầu cụ thể.

### 10.4. Tránh double reply

~~~java
// Anti-pattern: tự send rồi return một String.
@JmsListener(destination = "orders.requests")
@SendTo("orders.responses")
public String handle(Message request, Session session)
        throws JMSException {
    sendReplyManually(request, session);
    return "accepted";
}
~~~

Framework có thể gửi reply tự động từ return value, tạo **hai replies** cho một request. Khi dùng `MessageProducer` để gửi reply thủ công, method thông thường nên là `void`, không dùng `@SendTo` để gửi thêm một reply nữa.

## 11. Demo end-to-end: Java 17 + Spring Boot 3.5 + ActiveMQ Artemis

Ví dụ này minh họa **đúng đề bài**:

- Requester gọi `JmsTemplate.sendAndReceive(...)`.
- Spring `JmsTemplate` tạo **TemporaryQueue** và tự đặt nó vào request `JMSReplyTo`.
- Request có app-defined `JMSCorrelationID="req-42"` và `eventId="evt-42"`.
- `@JmsListener` nhận `TextMessage request` và `Session session`.
- Handler tạo reply bằng **Session đó** và gửi tới **đúng request.getJMSReplyTo()**.
- Listener factory chạy local JMS transacted Session.
- Requester nhận reply và kiểm tra **body, correlation và statusCode**.

### 11.1. Điều kiện chạy

- Java 17+, Maven 3.9+, Docker.
- Port `61616` (messaging) và `8161` (console) còn trống.
- Không có consumer khác dùng queue demo.
- Chỉ dùng một broker thử nghiệm, không gửi message đến production.

Chạy Artemis bằng image chính thức:

~~~bash
docker run --detach --rm --name jms-session-reply-demo \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Xem log broker:

~~~bash
docker logs jms-session-reply-demo
~~~

Artemis demo thường bật auto-create queue; môi trường tắt auto-create cần provision `lesson.session.reply.requests` và quyền send/consume. TemporaryQueue cũng phải được broker hỗ trợ và tài khoản có quyền phù hợp. Credential ở đây chỉ dành cho lab cô lập.

### 11.2. Cấu trúc project

~~~text
jms-session-reply-demo/
├── pom.xml
└── src/main/
    ├── java/example/SessionReplyApplication.java
    └── resources/application.properties
~~~

### 11.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.5</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>jms-session-reply-demo</artifactId>
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

### 11.4. application.properties

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

### 11.5. SessionReplyApplication.java — file Java hoàn chỉnh

Tạo `src/main/java/example/SessionReplyApplication.java`:

~~~java
package example;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class SessionReplyApplication {

    private static final String REQUEST_QUEUE =
            "lesson.session.reply.requests";

    public static void main(String[] args) {
        SpringApplication.run(SessionReplyApplication.class, args);
    }

    @Bean
    JmsTemplate requesterTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        template.setSessionTransacted(false);
        template.setReceiveTimeout(10_000L);
        return template;
    }

    @Bean("replyListenerFactory")
    DefaultJmsListenerContainerFactory replyListenerFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
        factory.setPubSubDomain(false);
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    ApplicationRunner runRequestReply(JmsTemplate requesterTemplate) {
        return args -> {

            Message reply = requesterTemplate.sendAndReceive(
                    REQUEST_QUEUE,
                    session -> {
                        TextMessage request =
                                session.createTextMessage("order-42");
                        request.setJMSCorrelationID("req-42");
                        request.setStringProperty("eventId", "evt-42");
                        return request;
                    });

            if (!(reply instanceof TextMessage response)) {
                throw new IllegalStateException(
                        "No TextMessage reply within 10 seconds");
            }

            String body = response.getText();
            String correlationId = response.getJMSCorrelationID();
            String status = response.getStringProperty("statusCode");

            if (!"accepted:order-42".equals(body)) {
                throw new IllegalStateException(
                        "Unexpected reply body: " + body);
            }
            if (!"req-42".equals(correlationId)) {
                throw new IllegalStateException(
                        "Correlation mismatch: " + correlationId);
            }
            if (!"ACCEPTED".equals(status)) {
                throw new IllegalStateException(
                        "Unexpected status: " + status);
            }

            System.out.println("replyBody=" + body);
            System.out.println("correlationId=" + correlationId);
            System.out.println("statusCode=" + status);
            System.out.println("verified=true");
        };
    }

    @Component
    public static class ReplyListener {

        @JmsListener(
                destination = REQUEST_QUEUE,
                containerFactory = "replyListenerFactory")
        public void onRequest(TextMessage request, Session session)
                throws JMSException {

            Destination replyTo = request.getJMSReplyTo();
            if (replyTo == null) {
                throw new IllegalArgumentException(
                        "JMSReplyTo is required");
            }

            String correlationId = request.getJMSCorrelationID();
            if (correlationId == null || correlationId.isBlank()) {
                throw new IllegalArgumentException(
                        "JMSCorrelationID is required");
            }

            String eventId = request.getStringProperty("eventId");
            if (eventId == null || eventId.isBlank()) {
                throw new IllegalArgumentException("eventId is required");
            }

            TextMessage reply = session.createTextMessage(
                    "accepted:" + request.getText());
            reply.setJMSCorrelationID(correlationId);
            reply.setStringProperty("statusCode", "ACCEPTED");
            reply.setStringProperty("requestEventId", eventId);

            try (MessageProducer producer =
                         session.createProducer(replyTo)) {
                producer.send(reply);
            }

            System.out.println("replySendInvoked=true");
            // Không commit/rollback/close Session.
        }
    }
}
~~~

### 11.6. Giải thích mã

1. **`JmsTemplate` ở requester**: `sendAndReceive` dùng request queue làm destination gửi; tự tạo TemporaryQueue cho reply, đặt vào `JMSReplyTo`.
2. **Requester không transacted**: nếu request được gửi trong JMS transaction chưa commit rồi chờ reply ở cùng transaction, responder có thể chưa thấy request và gây deadlock/timeout.
3. **Listener factory**: dùng `DefaultJmsListenerContainerFactoryConfigurer` để giữ Boot defaults rồi đặt `sessionTransacted=true`, `concurrency=1`. Trong lab không cấu hình JTA transaction manager ngoài.
4. **`TextMessage request, Session session`**: Spring inject hai đối tượng đặc biệt do container cung cấp.
5. **`JMSReplyTo`**: chính TemporaryQueue mà `JmsTemplate` tạo, không cần tạo lại tên queue ở responder.
6. **Correlation**: request gắn `req-42`, reply echo nguyên giá trị; requester kiểm tra.
7. **Reply**: `session.createTextMessage`, set property, `session.createProducer(replyTo).send(reply)`.
8. **Transaction**: reply send dùng chính listener Session; container commit request và reply sau method thành công.
9. **`void` method**: không trả thêm value, tránh Spring tạo một reply tự động nữa.
10. **Không có DB**: demo không ngụ ý exactly-once business effects hay distributed transaction.

### 11.7. Chạy

Từ thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Với broker sạch, không có lỗi mạng/ACL, request queue không có consumer khác, output từ chính ứng dụng thường gồm:

~~~text
replySendInvoked=true
replyBody=accepted:order-42
correlationId=req-42
statusCode=ACCEPTED
verified=true
~~~

Thứ tự giữa listener log và requester log phụ thuộc scheduling (mặc dù reply chỉ có thể delivery sau khi giao dịch listener commit trong mô hình transacted). Spring Boot còn log startup và JMS infrastructure. Nếu timeout hoặc reply sai kiểu, runner ném exception; không in `verified=true`.

Trong Artemis console ở `http://localhost:8161`, kiểm tra request queue depth và consumer count. Temporary reply queue có thể đã được tự xóa sau khi operation kết thúc, nên không mong nó tồn tại lâu dài.

Dừng ứng dụng bằng `Ctrl+C`, dừng broker:

~~~bash
docker stop jms-session-reply-demo
~~~

Image đang chạy `--rm` và không có persistent volume nên dữ liệu demo không bền sau khi stop; không dùng cấu hình này cho production.

## 12. Phản hồi với QoS tùy chỉnh theo request

Khi cần reply chỉ có giá trị ngắn hạn, có thể dùng send overload:

~~~java
@JmsListener(
    destination = "orders.requests",
    containerFactory = "replyListenerFactory")
public void handle(TextMessage request, Session session)
        throws JMSException {

    Destination replyTo = request.getJMSReplyTo();
    if (replyTo == null) {
        throw new IllegalArgumentException("Missing JMSReplyTo");
    }

    String correlationId = request.getJMSCorrelationID();
    if (correlationId == null || correlationId.isBlank()) {
        throw new IllegalArgumentException("Missing correlation");
    }

    TextMessage reply = session.createTextMessage("ACCEPTED");
    reply.setJMSCorrelationID(correlationId);
    reply.setStringProperty("statusCode", "ACCEPTED");

    try (MessageProducer producer = session.createProducer(replyTo)) {
        producer.send(
                reply,
                jakarta.jms.DeliveryMode.PERSISTENT,
                6,
                3_000L);
    }
}
~~~

Đây là snippet, không phải file chạy độc lập. TTL 3 giây có thể làm reply hết hạn trước khi requester nhận nếu broker/network chậm. `PERSISTENT` không kéo dài vòng đời temporary queue sau connection close. Chọn QoS theo SLA và benchmark thực tế.

### 12.1. Tạo error reply khi business validation thất bại

Nếu request hợp lệ về giao thức nhưng nội dung vi phạm business rule (ví dụ order đã hủy), có thể **gửi error reply như một kết quả hợp lệ**:

~~~java
TextMessage reply = session.createTextMessage("rejected:cancelled");
reply.setJMSCorrelationID(correlationId);
reply.setStringProperty("statusCode", "REJECTED");
reply.setStringProperty("reasonCode", "ORDER_CANCELLED");

try (MessageProducer producer = session.createProducer(replyTo)) {
    producer.send(reply);
}
// Nếu policy quy định đây là business outcome,
// callback có thể return và JMS transaction commit.
~~~

Không biến mọi `JMSException`/database timeout thành `REJECTED` rồi commit request; lỗi hạ tầng thường cần rollback/retry thay vì giả lập một business rejection.

### 12.2. Khi thiếu JMSReplyTo vĩnh viễn

Nếu request được gửi không có `JMSReplyTo` nhưng contract đòi hỏi, rollback nhiều lần có thể dẫn đến poison loop. Hãy đặt retry limit, DLQ/quarantine, telemetry và quy trình sửa producer. Không cho một request malformed chặn mãi queue.

## 13. Requester quản lý TemporaryQueue trực tiếp (JMS classic API)

`JmsTemplate.sendAndReceive` tiện nhưng không phải lựa chọn duy nhất. Nếu requester cần định nghĩa selector/consumer đặc thù:

~~~java
// Snippet trong method có ConnectionFactory hợp lệ.
try (Connection connection =
             connectionFactory.createConnection();
     Session session = connection.createSession(
             Session.AUTO_ACKNOWLEDGE)) {

    Queue requests = session.createQueue("orders.requests");
    TemporaryQueue replyQueue = session.createTemporaryQueue();

    try (MessageProducer producer = session.createProducer(requests);
         MessageConsumer consumer =
                 session.createConsumer(replyQueue)) {

        connection.start();

        TextMessage request =
                session.createTextMessage("order-42");
        request.setJMSReplyTo(replyQueue);
        request.setJMSCorrelationID("req-42");

        producer.send(request);

        Message reply = consumer.receive(5_000L);
        if (reply == null) {
            throw new IllegalStateException("Reply timed out");
        }
        if (!"req-42".equals(reply.getJMSCorrelationID())) {
            throw new IllegalStateException("Wrong correlation");
        }
    }
}
~~~

Đây là snippet Java SE/standalone, yêu cầu các import từ `jakarta.jms` và broker. TemporaryQueue được tạo bằng requester session; reply consumer cũng dùng **connection sở hữu queue tạm**, đáp ứng giới hạn Jakarta Messaging. `connection.start()` cần để consumer nhận.

**Không thay `Session.AUTO_ACKNOWLEDGE` của requester bằng `SESSION_TRANSACTED` mà vẫn chờ reply trước commit**, vì request chưa commit có thể không được responder xử lý.

### 13.1. Fixed reply queue và selector

Nếu nhiều requesters dùng chung reply Queue, một consumer có thể lọc bằng `JMSCorrelationID`:

~~~java
MessageConsumer consumer = session.createConsumer(
        replyQueue,
        "JMSCorrelationID = 'req-42'");
~~~

`replyQueue` ở snippet này phải là một `Queue` được provision phù hợp. Đừng nối trực tiếp user input vào JMS selector mà không kiểm tra/escape; selector có cú pháp riêng, có thể tạo lỗi hoặc định tuyến sai. Nên sinh correlation IDs với charset/format cố định và ràng quyền/namespace giữa requesters.

## 14. Các failure modes quan trọng

### 14.1. Producer báo gửi thành công nhưng requester vẫn timeout

Kiểm tra:

1. `JMSReplyTo` có trỏ đúng destination requester đang nghe?
2. TemporaryQueue còn sống không? Requester đã close connection?
3. Reply đã được commit trong listener transacted Session chưa?
4. `JMSCorrelationID` có đúng contract và selector không?
5. Broker có quyền send/consume và destination routing phù hợp không?
6. TTL/expiration của reply có hết hạn không?
7. Có consumer khác đang tranh nhận fixed reply queue không?
8. Listener có throw trước send, conversion error hoặc DLQ?
9. Requester receive timeout có ngắn hơn processing latency không?
10. Có vấn đề failover hoặc broker restart làm mất subscription không?

Một dòng log `producer.send(reply)` trong callback **không chứng minh** reply đã được requester nhận.

### 14.2. Reply bị gửi hai lần

Nguyên nhân: listener gửi thủ công bằng Session **và** return value để Spring tạo reply tự động, hoặc request bị redeliver rồi code thiếu idempotency. Kiểm tra method có `void` không, có `@SendTo` không, correlation/eventId và transaction logs.

### 14.3. Correlation mismatch

Responder trả `request.getJMSMessageID()` trong khi requester chờ application-defined `request.getJMSCorrelationID()`, hoặc tạo UUID mới cho mỗi reply. Thống nhất một protocol và đặt regression test.

### 14.4. Session báo lỗi sau callback return

Có thể code lưu Session để dùng ở thread khác hoặc đã tự close/commit. Xem lifecycle và transaction owner. Dùng Session **chỉ trong callback**.

### 14.5. Reply gửi được nhưng request lại được redeliver

Nếu listener transaction rollback sau send chưa commit, reply chưa được publish (khi send cùng Session), request có thể được giao lại. Nếu requester vẫn từng thấy reply ở một giao dịch trước, có thể đang có duplicate logical request; cần dựa vào eventId và transaction outcomes.

### 14.6. JMS transaction commit nhưng DB side effect trùng

JMS transaction không bao trùm DB local transaction. Nếu DB commit trước rồi JMS commit thất bại, broker có thể redeliver request. Dùng idempotency table/unique constraint, transactional outbox, saga hoặc JTA/XA theo yêu cầu và hạ tầng thực tế.

### 14.7. Provider không hỗ trợ hoặc không cho TemporaryQueue

Requester tạo reply queue tạm thất bại vì ACL/quota/provider configuration. Có thể provision fixed reply Queue với correlation selectors và lifecycle riêng nếu phù hợp. Không tự động retry vô hạn theo cùng lỗi cấu hình.

### 14.8. Poison message trả lời không được

Request không có `JMSReplyTo`, ID sai hoặc schema lỗi. Nếu lần nào cũng rollback thì có thể thành poison message, làm tăng attempts và DLQ. Xây error taxonomy, max retries và quarantine; không tạo reply đích vô nghĩa chỉ để làm hài lòng code.

### 14.9. Nhiều requesters có chung correlation ID

Nếu requester sinh ID không đủ unique hoặc reuse giữa concurrent requests, reply selector có thể match sai. Dùng ID có scope uniqueness được xác định rõ, đủ entropy và không lộ thông tin nhạy cảm.

## 15. Quan sát, kiểm thử và bảo mật

### 15.1. Logging hữu ích

| Field | Tại sao cần? |
|---|---|
| `requestId`, `eventId` | Idempotency và nghiệp vụ |
| Request `JMSMessageID` | Theo dõi JMS delivery |
| Request/reply `JMSCorrelationID` | Đối chiếu exchange |
| `JMSReplyTo` type | TemporaryQueue/Queue/Topic |
| `JMSRedelivered`, `JMSXDeliveryCount` | Dấu hiệu retry/redelivery |
| `replyStatusCode`, `reasonCode` | Business outcome |
| `listenerId`, `brokerIdentity` | Xác định nơi xử lý |
| `sendAttempt`, `transactionOutcome` | Phân biệt send và commit |
| `requestLatencyMs`, `replyLatencyMs` | SLA |
| `timeout`, `expired`, `dlq` | Điều tra mất reply |

Không ghi toàn bộ body có chứa dữ liệu riêng tư vào production log. Số delivery count không chứng minh business method đã chạy đúng số lần, và một JMSMessageID có thể khác khi producer retry tạo message mới.

### 15.2. Test tối thiểu

- Requester gửi TextMessage có JMSReplyTo và correlation; reply mang đúng body/properties.
- Method `@JmsListener` có `Session` được inject, không tự khởi tạo Connection.
- Request thiếu JMSReplyTo được xử lý theo policy.
- Correlation ID sai được phát hiện ở requester.
- Thử `sessionTransacted=true` và lỗi producer send để xem rollback.
- Thử `AUTO_ACKNOWLEDGE` nếu cần chứng minh giới hạn của ack mode.
- Requester timeout trước reply; temp queue đóng và late reply được xử lý.
- Duplicate logical requestId: chỉ một business side effect.
- Broker restart, redelivery, DLQ và reply send failure.
- Topic/Queue routing, ACL và resource quota.
- Không có double reply do kết hợp `@SendTo` và manual send.

### 15.3. Bảo mật reply destination

- JMS broker phải xác thực và phân quyền `send`/`consume` theo principal.
- Không sử dụng user-input thô làm tên queue để phản hồi.
- Nếu một service có quyền gửi tới nhiều tenants, xem xét allowlist/prefix/tenant isolation.
- Chống abuse qua temporary queue quotas và per-request deadline.
- Không xem JMS selector là biện pháp phân quyền thay ACL.
- Các header như correlation IDs có thể đi vào log/trace, nên không chứa password, token hoặc PII.
- Validate message schema trước khi tác động đến DB/payment; tránh deserialization tùy tiện của ObjectMessage.

## 16. Checklist trước production

- [ ] `@JmsListener` là method trong Spring-managed bean, JMS annotation processing đã bật.
- [ ] Method nhận đúng `jakarta.jms.Message`/subclass và `jakarta.jms.Session`.
- [ ] `JMSReplyTo` được kiểm tra null/type và tuân thủ contract.
- [ ] Nếu cần reply bắt buộc, requester và responder thống nhất correlation protocol.
- [ ] Tạo reply message **mới**, không tái sử dụng request message.
- [ ] Chỉ sao chép những properties/headers nghiệp vụ cần thiết.
- [ ] Dùng `Session` được inject tạo producer và send để giữ JMS local transaction khi factory transacted.
- [ ] Đóng producer do method tạo; không tự close/commit/rollback Session của container.
- [ ] Không giữ Session trong field hoặc đưa sang executor/thread khác.
- [ ] Khi gửi reply thủ công, method có return type `void`, tránh double reply.
- [ ] Listener factory có ack/transaction mode rõ, thử exception và rollback.
- [ ] Requester không gửi request transacted rồi chờ reply trước commit.
- [ ] Receive timeout, reply TTL, business deadline và late reply policy thống nhất.
- [ ] Broker cho phép tạo/sử dụng reply destination, đặc biệt TemporaryQueue.
- [ ] Có business requestId/eventId ổn định và idempotency khi retry/redelivery.
- [ ] DB/external API side effects có chính sách nhất quán riêng.
- [ ] Retry/backoff, DLQ, quarantine và re-drive được định nghĩa rõ.
- [ ] Metrics/log đối chiếu request, reply và transaction outcome.
- [ ] Đã test broker restart, missing header, duplicate, timeout và security ACL.
- [ ] Không dùng credentials/queue/data của demo trong production.

## 17. Câu hỏi tự kiểm tra

**1. Một `@JmsListener` có thể nhận `Session` không?** Có, khi khai báo `jakarta.jms.Session` làm tham số được Spring hỗ trợ.

**2. Session đó có phải Session mới do method tự tạo không?** Không. Nó được listener infrastructure cấp cho lần nhận hiện tại.

**3. Muốn gửi reply đến đích mà requester yêu cầu, đọc gì?** `request.getJMSReplyTo()` trả `Destination`.

**4. `JMSReplyTo` có luôn tồn tại không?** Không, header tùy chọn; phải có policy khi null.

**5. Có nên gọi `session.commit()` trong listener không?** Không khi listener container/transaction manager đang quản lý transaction.

**6. Có nên lưu Session vào field để trả lời sau không?** Không; lifecycle và thread ownership thuộc callback/container.

**7. Vì sao dùng cùng Session cho ACK request và gửi reply?** Với transacted listener, hai JMS operations có thể cùng commit/rollback.

**8. Dùng `JmsTemplate.convertAndSend` từ một bean khác có chắc cùng transaction không?** Không mặc định; phải kiểm tra resource binding và factory/manager.

**9. JMSMessageID của reply có phải copy từ request không?** Không. Provider gán ID riêng; dùng JMSCorrelationID để liên kết.

**10. Nếu requester cung cấp `JMSCorrelationID=req-42`, responder làm gì?** Echo `req-42` vào reply JMSCorrelationID theo hợp đồng.

**11. `JMSMessageID` fallback phù hợp khi nào?** Khi protocol quy định reply correlation bằng request JMSMessageID và provider tạo ID bình thường.

**12. Vì sao không gửi thủ công rồi return `String` có `@SendTo`?** Spring có thể gửi reply thứ hai từ return value.

**13. TemporaryQueue có sống sau khi requester connection đóng không?** Không; lifecycle gắn với connection sở hữu.

**14. Gửi reply thành công có chứng minh requester đã nhận không?** Không; còn commit, routing, selector, TTL và timeout.

**15. Local JMS transaction có rollback database được không?** Không. Dùng idempotency/outbox hoặc transaction phân tán được thiết kế rõ.

**16. Kết quả business validation thất bại có thể trả reply `REJECTED` rồi commit không?** Có, nếu đó là outcome hợp lệ của giao thức và không phải lỗi hạ tầng.

**17. Message redelivery có nghĩa handler trước đã hoàn tất không?** Không; có thể broker đã deliver nhưng process chết trước xử lý.

**18. Vì sao request send trong transaction chưa commit rồi chờ reply có thể deadlock?** Responder có thể chưa thấy request để xử lý và gửi phản hồi.

## 18. Tài liệu chính thức

- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): Spring xác nhận `jakarta.jms.Session` là tham số hợp lệ, hỗ trợ custom reply; `@Header`, `@SendTo`, `JmsResponse`.
- [Spring Framework 6.2 — JmsListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html): method signatures, destination/container factory và cảnh báo transaction.
- [Spring Framework 6.2 — MessagingMessageListenerAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/adapter/MessagingMessageListenerAdapter.html): native Message/Session được đưa vào invocation.
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): listener containers, SessionAwareMessageListener.
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): transaction management, ConnectionFactory, request-reply.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `sendAndReceive(...)` tự tạo temporary reply queue.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `JMSReplyTo`, `JMSCorrelationID`, JMSMessageID, temporary destinations, send/transaction semantics.
- [Spring Boot 3.5 — JMS and Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): broker/configuration và JMS starter.
- [Spring Boot 3.5 — Messaging How-to](https://docs.spring.io/spring-boot/3.5/how-to/messaging.html): listener factory transaction configuration.
- [ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): broker dùng trong demo.

**Tóm tắt:** Trong `@JmsListener`, **`Session` là một loại method argument đặc biệt được Spring inject**. Dùng chính Session đó để tạo `TextMessage`/`MessageProducer`, lấy `JMSReplyTo` từ incoming request và gắn correlation theo giao thức. Để callback return hoặc ném lỗi, **không tự commit/rollback/close Session**. Khi cần reply đơn giản, `@SendTo` có thể gọn hơn; khi cần native JMS metadata, QoS và atomic receive+reply, `Session` trực tiếp là công cụ phù hợp.
