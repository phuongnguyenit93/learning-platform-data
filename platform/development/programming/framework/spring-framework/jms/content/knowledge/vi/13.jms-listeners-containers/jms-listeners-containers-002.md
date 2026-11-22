# SessionAwareMessageListener và việc truy cập Session trong Spring JMS

## 1. Vấn đề: listener đôi khi cần nhiều hơn một Message

Trong Spring JMS, listener nhận các thông điệp từ một queue hoặc topic. Với tác vụ chỉ ghi log hoặc chuyển nội dung sang tầng nghiệp vụ, interface tiêu chuẩn **`jakarta.jms.MessageListener`** thường là đủ: phương thức `onMessage(Message)` chỉ nhận message.

Nhưng khi handler cần **tạo một response** tới `JMSReplyTo`, tạo một loại JMS message đặc biệt hoặc dùng các phương thức của `jakarta.jms.Session` **ngay trong lượt xử lý**, một message duy nhất có thể chưa đủ. Spring Framework cung cấp interface **`org.springframework.jms.listener.SessionAwareMessageListener<M extends Message>`**, truyền vào cả **message đã nhận** lẫn **JMS Session** mà listener container quản lý.

Chữ ký API trong Spring Framework 6.x:

```java
package org.springframework.jms.listener;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Session;

@FunctionalInterface
public interface SessionAwareMessageListener<M extends Message> {
    void onMessage(M message, Session session) throws JMSException;
}
```

*Đây là phần mô tả chữ ký API để học, không phải file cần tự viết trong project.* `M` là kiểu message (ví dụ `Message`, `TextMessage`); `Session` là đối tượng của Jakarta Messaging. Trong Spring Framework 6+ / Spring Boot 3+, import phải là `jakarta.jms.*`, không trộn với `javax.jms.*` của thế hệ cũ.

**Điểm quan trọng nhất:** `SessionAwareMessageListener` cho phép **dùng Session do container cấp trong phạm vi callback**, không có nghĩa developer được **sở hữu**, tự đóng, tự commit hay giữ Session đó lâu dài. Listener container vẫn quản lý vòng đời, transaction và concurrency.

### 1.1. Sơ đồ xử lý

```text
JMS Broker / requests.queue
             │
             ▼
DefaultMessageListenerContainer
   ├─ lấy Connection từ ConnectionFactory
   ├─ dùng Session để tạo MessageConsumer
   ├─ receive() một Message
   │
   ▼
SessionAwareMessageListener.onMessage(message, session)
   ├─ kiểm tra message type và schema
   ├─ xử lý logic nghiệp vụ
   ├─ request.getJMSReplyTo()
   ├─ session.createTextMessage("ACK:...")
   ├─ session.createProducer(replyTo).send(reply)
   └─ return hoặc throw exception
             │
             ▼
Container xử lý commit / rollback / ack / cleanup
             │
             └──────► Broker phân phối reply
```

Nếu `sessionTransacted=true` và Session của listener được expose, **nhận message và gửi reply qua cùng Session** nằm trong **một JMS local transaction**. Khi callback thành công, container có thể commit; khi callback lỗi, transaction được rollback theo cấu hình. Điều đó **không tự biến thao tác database** trong callback thành một phần của giao dịch JMS.

## 2. So sánh MessageListener, SessionAwareMessageListener và @JmsListener

| Tiêu chí | `jakarta.jms.MessageListener` | Spring `SessionAwareMessageListener` | Spring `@JmsListener` |
| --- | --- | --- | --- |
| Nguồn gốc | API Jakarta Messaging chuẩn | Interface riêng của Spring | Annotation + adapter của Spring |
| Chữ ký xử lý | `onMessage(Message)` | `onMessage(M, Session)` | Method tùy ý, ví dụ `handle(String)` |
| Nhận Session trực tiếp | Không qua chữ ký | Có, tham số thứ hai | **Có**, khi method khai báo `jakarta.jms.Session` |
| Checked JMSException | Không khai báo trong `onMessage` chuẩn | Cho phép `throws JMSException` | Method handler có thể khai báo exceptions |
| Chuyển payload tự động | Không, tự đọc raw Message | Không, tự đọc raw Message | Có thể qua `MessageConverter` và argument resolver |
| Chuyển response tự động | Không | Không, phải tự gửi hoặc dùng logic riêng | Có thể tự gửi từ return value với `JMSReplyTo` / `@SendTo` |
| Phụ thuộc Spring | Không, interface portable | Có | Có |
| Tình huống điển hình | Xử lý raw JMS, cần portable | Xử lý raw JMS **và thao tác cùng Session** | Listener nghiệp vụ thường ngày |

### 2.1. Standard MessageListener

```java
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import jakarta.jms.TextMessage;

class PlainListener implements MessageListener {
    @Override
    public void onMessage(Message message) {
        try {
            if (!(message instanceof TextMessage text)) {
                throw new IllegalArgumentException("Expected TextMessage");
            }
            System.out.println(text.getText());
        } catch (jakarta.jms.JMSException ex) {
            throw new IllegalStateException("Cannot read JMS message", ex);
        }
    }
}
```

Đoạn này là class minh họa, chưa đăng ký container. `MessageListener.onMessage` **không có `throws JMSException`**, vì thế ví dụ bắt checked `JMSException` và chuyển thành unchecked. Nếu phải gửi response, handler cần nguồn `ConnectionFactory`/`JmsTemplate` khác hoặc framework adapter giúp gửi; chữ ký chỉ nhận Message không cấp Session.

### 2.2. Spring SessionAwareMessageListener

```java
import jakarta.jms.Message;
import jakarta.jms.Session;
import jakarta.jms.JMSException;
import org.springframework.jms.listener.SessionAwareMessageListener;

class SessionAwareHandler implements SessionAwareMessageListener<Message> {

    @Override
    public void onMessage(Message message, Session session)
            throws JMSException {
        // message: message mà container nhận.
        // session: Session hiện tại do container cấp.
        // Xử lý và có thể tạo response bằng session.createTextMessage(...).
    }
}
```

Callback có thể khai báo `throws JMSException`; container xử lý lỗi và ranh giới ack/transaction theo cấu hình. **Không nuốt lỗi rồi `return` như xử lý thành công** nếu bạn muốn broker redeliver khi xử lý thất bại.

### 2.3. @JmsListener cũng có thể nhận Session

Spring Framework 6.x hỗ trợ `jakarta.jms.Session` như một argument được inject cho phương thức annotation-driven:

```java
import jakarta.jms.JMSException;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;

@JmsListener(destination = "demo.requests")
public void handle(TextMessage request, Session session)
        throws JMSException {
    // Dùng request và Session do listener adapter/container cung cấp.
}
```

Đây là mảnh method để đặt trong Spring-managed bean, **không phải ứng dụng độc lập**. Nếu dùng `@JmsListener`, hạ tầng adapter bên dưới cung cấp raw Message/Session khi cần; **không bắt buộc trực tiếp implement interface** `SessionAwareMessageListener`. Nếu không cần API Session, method `@JmsListener` nhận DTO/String thường gọn hơn.

**Chọn cách nào?** Dùng `@JmsListener` cho phần lớn consumer hiện đại; dùng `SessionAwareMessageListener` khi muốn kiểm soát raw JMS API trực tiếp và đăng ký rõ với `DefaultMessageListenerContainer` hoặc `SimpleMessageListenerContainer`. Tránh trộn hai listener cùng consume một queue demo vì chúng sẽ trở thành competing consumers.

## 3. Session được truyền vào thực chất là gì?

`jakarta.jms.Session` trong classic JMS API là **ngữ cảnh thao tác tuần tự** để:

- Tạo `TextMessage`, `BytesMessage`, `MapMessage`, `StreamMessage`, `ObjectMessage`.
- Tạo `Queue`/`Topic` object từ tên hoặc tạo `TemporaryQueue`/`TemporaryTopic` khi thích hợp.
- Tạo `MessageProducer`/`MessageConsumer` theo destination.
- Thực hiện các thao tác phụ thuộc vào transaction/acknowledgement của session.
- Duy trì thứ tự các thao tác dùng cùng session theo semantics JMS.

Các method thường thấy:

```java
// Mảnh code bên trong callback có jakarta.jms.Session session:
TextMessage reply = session.createTextMessage("ACK:order-42");
MessageProducer producer = session.createProducer(replyTo);
producer.send(reply);
producer.close();
```

Các method trên là API Jakarta JMS. Với Spring Boot 3+ dùng `jakarta.jms.Session`, không phải `org.hibernate.Session`, không phải HTTP Session, không phải Spring `WebSession`.

### 3.1. Session là scope, không phải singleton dùng chung

Mỗi lượt listener được container cấp một session phù hợp. Tùy container/concurrency, session có thể **được tái sử dụng** giữa các lượt trên cùng consumer thread hoặc tạo mới theo cache strategy. Vì vậy:

- Không lưu session vào static field hay singleton service.
- Không gửi session sang `CompletableFuture`, thread pool hoặc reactive pipeline để dùng sau khi `onMessage` trả về.
- Không dùng đồng thời một session từ nhiều thread; JMS Session về cơ bản là ngữ cảnh single-threaded.
- Không đóng session do container cấp bên trong callback.
- Không tự gọi `session.commit()` hoặc `session.rollback()` nếu **container** đang quản lý transaction. Hành vi commit/rollback phải theo một chủ sở hữu rõ ràng.
- Producer/consumer **tự tạo** trong callback phải được đóng đúng cách khi đã dùng xong, ví dụ `try-with-resources`; đừng nhầm đóng producer với đóng session.

### 3.2. Bảng quyền sở hữu resource

| Resource | Ai quản lý trong listener? | Có nên tự `close()` không? |
| --- | --- | --- |
| `ConnectionFactory` | Spring Boot/provider/ứng dụng | Không từ callback |
| `Connection` | Listener container / infrastructure | Không |
| `Session` truyền vào `onMessage` | Listener container | **Không** |
| `MessageConsumer` của container | Listener container | Không |
| `MessageProducer` tạo bằng `session.createProducer(...)` | Callback tạo trực tiếp | **Có**, sau khi send |
| `TextMessage` tạo bằng `session.createTextMessage(...)` | Session tạo object dữ liệu | Không có close riêng |
| Một `JMSContext` độc lập tự tạo khác | Code tự tạo | Có, nếu thật sự cần nhưng tránh tách transaction vô tình |

Dù callback có tham số `Session`, đừng tự xem mình đang viết code sở hữu raw JMS `Connection`. Session này có thể nằm trong local/JTA transaction hoặc wrapper; cách đóng tay sai có thể phá commit/rollback, redelivery và shutdown của container.

## 4. Cấu hình listener container để expose Session

Spring Framework có ít nhất hai listener container thường gặp:

- `DefaultMessageListenerContainer` (**DMLC**): dùng vòng lặp `MessageConsumer.receive()`, có recovery/concurrency và hỗ trợ transaction linh hoạt; phù hợp nhiều ứng dụng production.
- `SimpleMessageListenerContainer` (**SMLC**): dùng `MessageConsumer.setMessageListener()`; cấu trúc đơn giản hơn nhưng ít tính năng scheduling/recovery/transaction hơn DMLC.

Cả hai hỗ trợ `SessionAwareMessageListener` như alternative trực tiếp của standard `MessageListener`. **Một số JCA-based endpoint container không hỗ trợ interface riêng này theo cùng cách**, nên nếu cần tối đa portable giữa nhiều application server/resource adapter, cân nhắc standard `MessageListener` hoặc `@JmsListener` phù hợp.

### 4.1. Cấu hình DMLC bằng Java @Bean

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.SessionAwareMessageListener;

@Bean
DefaultMessageListenerContainer sessionContainer(
        ConnectionFactory nativeConnectionFactory,
        SessionAwareMessageListener<Message> listener) {
    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();
    container.setConnectionFactory(nativeConnectionFactory);
    container.setDestinationName("demo.requests");
    container.setMessageListener(listener);
    container.setExposeListenerSession(true);
    container.setSessionTransacted(true);
    container.setConcurrentConsumers(1);
    return container;
}
```

**Đây là mảnh method cấu hình**, cần bean `ConnectionFactory` và listener đã được khai báo và wire đúng. Trong một ứng dụng Spring Boot dùng `CachingConnectionFactory`, listener container thường nên lấy **native ConnectionFactory** để có quyền quản lý connection/recovery của chính nó. Project đầy đủ ở phần 8 dùng `ConnectionFactoryUnwrapper.unwrapCaching(...)` để xử lý điều này.

Các settings quan trọng:

- `setMessageListener(listener)` đăng ký handler raw; nếu chưa đăng ký, callback không được gọi.
- `setDestinationName(...)` chọn tên queue (mặc định DMLC dùng point-to-point/queue); topic cần cấu hình pub-sub domain.
- `setExposeListenerSession(true)` yêu cầu expose **listener Session** cho callback, mặc định Spring thường đã là `true`. Đặt tường minh trong demo để thấy ý nghĩa.
- `setSessionTransacted(true)` cho phép local JMS transaction khi không có transaction manager bên ngoài.
- `setConcurrentConsumers(1)` giữ demo một consumer; tăng concurrency đòi handler thread-safe, vì container có thể gọi cùng listener bean từ nhiều thread khác nhau.

### 4.2. `exposeListenerSession=true` và `false`

Theo Spring `AbstractMessageListenerContainer`:

| `exposeListenerSession` | Session callback được cấp | Ý nghĩa thực tế |
| --- | --- | --- |
| `true` (mặc định) | Tái dùng session của lượt nhận message | Reply gửi qua session này có thể tham gia **cùng JMS local transaction** |
| `false` | Có thể cấp **một session mới** lấy từ cùng connection | Hữu ích với một số provider có giới hạn, nhưng không được giả định receipt/reply cùng transaction |

Nếu provider yêu cầu session riêng cho outbound reply, hãy đánh giá transaction behavior trước khi đặt `false`. Với `JmsTemplate` được gọi **bên trong** listener, Spring còn có cơ chế expose thread-bound resource tùy transaction/config; để bảo đảm cùng session của callback trong bài này, cách đơn giản nhất là **dùng chính `Session session` được truyền vào**, tạo producer và gửi reply trực tiếp.

**Không suy luận rằng `setExposeListenerSession(false)` chỉ “ẩn tham số” mà không đổi semantics.** Nó có thể ảnh hưởng transaction và resource ownership.

## 5. Gửi reply qua Session được cấp: luồng xử lý chuẩn

Một use case phù hợp nhất với `SessionAwareMessageListener` là **request–reply**:

1. Producer gửi `TextMessage` đến queue request, gắn `JMSReplyTo` là một `Destination` và `JMSCorrelationID` do ứng dụng quy định.
2. Container nhận request và gọi `onMessage(request, session)`.
3. Handler xác minh message type, schema, `JMSReplyTo`, correlation ID.
4. Handler xử lý request.
5. Dùng **`session.createTextMessage(...)`** và **`session.createProducer(replyTo)`** để gửi reply.
6. Handler đóng producer tự tạo rồi trả về.
7. Container commit/ack hoặc rollback theo cấu hình.

Ví dụ:

```java
import jakarta.jms.Destination;
import jakarta.jms.InvalidDestinationException;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageFormatException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.springframework.jms.listener.SessionAwareMessageListener;

class ReplyingListener
        implements SessionAwareMessageListener<Message> {

    @Override
    public void onMessage(Message incoming, Session session)
            throws JMSException {
        if (!(incoming instanceof TextMessage request)) {
            throw new MessageFormatException("Expected TextMessage request");
        }

        Destination replyTo = request.getJMSReplyTo();
        String correlationId = request.getJMSCorrelationID();

        if (replyTo == null) {
            throw new InvalidDestinationException("Missing JMSReplyTo");
        }
        if (correlationId == null || correlationId.isBlank()) {
            throw new MessageFormatException("Missing correlation ID");
        }

        String requestBody = request.getText();
        TextMessage response =
                session.createTextMessage("ACK:" + requestBody);
        response.setJMSCorrelationID(correlationId);

        try (MessageProducer producer = session.createProducer(replyTo)) {
            producer.send(response);
        }
    }
}
```

Đây là **class minh họa có thể biên dịch khi có Spring JMS/Jakarta JMS dependencies**, nhưng cần container/broker/producer request để chạy luồng thực tế. Dùng `MessageProducer` trong try-with-resources vì Jakarta Messaging `MessageProducer` thực hiện `AutoCloseable`. Đóng producer **không đóng Session**. Vì `onMessage` được khai báo `throws JMSException`, các exception của API có thể truyền cho container xử lý.

### 5.1. Vì sao phải dùng `JMSReplyTo`, không tự suy queue?

`JMSReplyTo` là header kiểu **`Destination`**, không phải chuỗi tên queue. Nếu request không chỉ rõ reply destination, responder không thể tự biết nơi phản hồi theo chuẩn. Có thể chọn một reply destination mặc định do hệ thống quy định, nhưng phải là **business contract rõ ràng**.

`JMSCorrelationID` được echo để requester ghép response với request. Nếu hai bên chọn convention khác — ví dụ responder dùng request `JMSMessageID` nhưng requester kiểm tra application correlation — sẽ mismatch. Phải thống nhất trước khi triển khai.

### 5.2. Vì sao không tạo ConnectionFactory mới trong onMessage?

Cách sau **không cần thiết và có thể sai transaction**:

```java
// ANTI-PATTERN: được minh họa để tránh.
Connection anotherConnection = connectionFactory.createConnection();
Session anotherSession =
        anotherConnection.createSession(false, Session.AUTO_ACKNOWLEDGE);
// Gửi reply trên session khác rồi đóng connection.
// Việc send không tự chung transaction với receipt của listener!
```

Mỗi callback đã có Session từ container. Tạo connection/session độc lập làm tăng chi phí, có thể tạo một transaction khác; nếu worker lỗi sau khi gửi reply độc lập, requester có thể thấy response “thành công” trong khi receipt bị rollback và request được phát lại. Để có atomic local JMS receive+reply, dùng **cùng session đã cấu hình transacted**.

## 6. Transaction và acknowledgement: ranh giới phải rõ

### 6.1. Khi `sessionTransacted=true`

Với DMLC dùng local JMS transaction, sơ đồ:

```text
Broker                      Listener container / Session                  Broker
   │                                  │                                     │
   ├── request delivery ─────────────>│                                     │
   │                            onMessage(request, session)                │
   │                                  ├─ validate / calculate reply        │
   │                                  ├─ session.createProducer(replyTo)    │
   │                                  ├─ producer.send(response) ─────────>│
   │                                  │   chưa có hiệu lực ngoài txn        │
   │                                  └─ return thành công                  │
   │                                  │                                     │
   │                          container commit local JMS transaction        │
   │                          ┌─────────────┴──────────────┐                │
   │                          ▼                            ▼                │
   │                   request được ack            reply được công bố       │
   │                                                                       │
   └───────────────────── nếu lỗi: rollback receipt/reply ──────────────────┘
```

Nếu `onMessage` ném `JMSException` hoặc runtime exception mà container coi là xử lý thất bại, transaction được rollback; request có thể được redeliver theo broker policy. Reply send trong cùng session cũng rollback theo. Đây là lý do SessionAware listener có ích khi muốn **receive và reply ở cùng JMS local transaction**.

**Cảnh báo:** local JMS transaction không bao gồm database hay HTTP side effects. Nếu handler đã cập nhật DB rồi transaction JMS rollback, DB có thể đã commit nhưng request được giao lại. Cần idempotency key, dedup/outbox hoặc JTA/XA được cấu hình đúng nếu yêu cầu transaction phân tán; không chỉ thêm `sessionTransacted=true` là có exactly-once end-to-end.

### 6.2. Khi session không transacted

Trong `AUTO_ACKNOWLEDGE`, message có thể được ack sau khi `receive()` trả về thành công hoặc theo hành vi của provider/container trước khi code business hoàn thành; vì vậy không nên suy rằng một exception trong business luôn buộc broker redeliver. `CLIENT_ACKNOWLEDGE` có semantics khác, nhưng dùng raw `message.acknowledge()` sai thời điểm cũng có thể ack nhiều message đã nhận trên cùng session.

Với xử lý nghiệp vụ quan trọng, **chọn rõ transaction và redelivery policy** thay vì trông chờ default. Spring Boot có property `spring.jms.listener.session.transacted`, nhưng **nếu tự tạo `DefaultMessageListenerContainer` như trong bài**, cấu hình trực tiếp `setSessionTransacted(true)` trên bean là yếu tố quyết định cho container đó.

### 6.3. Ai được gọi commit, rollback và close?

| Thao tác | Nơi nên thực hiện khi DMLC quản lý transaction |
| --- | --- |
| `session.createTextMessage(...)` | Trong callback |
| `session.createProducer(replyTo)` | Trong callback |
| `producer.send(reply)` | Trong callback |
| `producer.close()` | Cuối scope producer được callback tự tạo |
| `session.commit()` | **Không tự gọi** — container/transaction manager điều phối |
| `session.rollback()` | **Không tự gọi** — báo lỗi bằng exception để container rollback |
| `session.close()` | **Không tự gọi** — container sở hữu |
| `connection.stop()/close()` | **Không tự gọi** — container sở hữu |

Ví dụ **sai**:

```java
@Override
public void onMessage(Message msg, Session session) throws JMSException {
    // Xử lý...
    session.commit(); // Sai trách nhiệm nếu container đã quản lý txn.
    session.close();  // Phá lifecycle / consumer container.
}
```

Một đoạn xử lý thất bại nhưng catch rồi bỏ qua exception có thể khiến container commit/ack thay vì retry:

```java
// Không làm:
try {
    processBusinessData();
} catch (RuntimeException ex) {
    log.warn("failed", ex);
    // Không rethrow: container có thể coi callback thành công.
}
```

Nếu lỗi **permanent** như schema sai, retry vô hạn cũng không hợp lý; cần chính sách DLQ/quarantine và quan sát nguyên nhân. Không tự commit/rollback thủ công để giải quyết tùy tiện.

## 7. Exception handling và concurrency

### 7.1. JMSException vs runtime exception

`SessionAwareMessageListener.onMessage` **được phép ném checked `JMSException`**, khác với `jakarta.jms.MessageListener.onMessage` chuẩn. Các lỗi có thể là:

- `MessageFormatException`: message không có kiểu/format yêu cầu.
- `InvalidDestinationException`: reply destination thiếu/không hợp lệ.
- `JMSSecurityException`: tài khoản thiếu quyền gửi reply.
- `JMSException`: provider/network/broker lỗi.
- `IllegalArgumentException`/runtime exception: schema/business validation thất bại.

Không giả định tất cả exception đều giống nhau:

| Loại lỗi | Có thể xử lý như thế nào? |
| --- | --- |
| Lỗi mạng/broker tạm thời | Retry có giới hạn + backoff theo policy |
| Sai JSON/schema hoặc thiếu JMSReplyTo | Reject/quarantine/DLQ; tránh retry vô tận |
| Business violation không thể sửa | Dùng error flow/DLQ theo contract |
| Timeout response | Phân biệt late reply với retry request |
| Duplicate/redelivery | Idempotent handler theo event/command ID |

Với DMLC, container có cơ chế xử lý exception/recovery; người dùng vẫn phải cấu hình policy broker, transaction và monitoring. **Không dùng exception unchecked để thay thế chiến lược lỗi**.

### 7.2. Thread safety

Một bean listener có thể được DMLC gọi **đồng thời** nếu cấu hình nhiều consumers. `SessionAwareMessageListener` không tự làm listener thread-safe:

- Ưu tiên handler stateless và inject các dependency thread-safe.
- Không lưu `Session`/`MessageProducer`/message hiện tại vào field dùng chung.
- Không dùng mutable `ArrayList`/counter không đồng bộ giữa callbacks.
- Nếu tăng `concurrentConsumers`, mỗi callback được cấp Session phù hợp cho thread xử lý của nó; không dùng chéo Session.
- Nếu cần ordering theo business key, thiết kế queue partitioning, JMSXGroupID, sequencing hoặc policy broker phù hợp thay vì tin chỉ cần giữ một listener bean.

Ví dụ **sai**:

```java
class UnsafeListener implements SessionAwareMessageListener<Message> {
    private Session lastSession; // Không giữ resource callback ở field.

    @Override
    public void onMessage(Message msg, Session session) {
        this.lastSession = session;
        // Thread khác có thể dùng nhầm session hoặc đã hết scope.
    }
}
```

Chú ý: cấu hình một concurrent consumer **giảm** một số race conditions trong lab, không tạo bảo đảm message không bao giờ bị redeliver, không bao giờ có duplicate hoặc ordering vĩnh viễn khi failover.

## 8. Demo chạy được: Spring Boot 3.5.7, Java 17+, Artemis, DMLC và reply cùng Session

Mục tiêu: tạo một **SessionAware listener thực sự** thay vì `@JmsListener`, đăng ký nó với `DefaultMessageListenerContainer`; requester dùng `JmsTemplate.sendAndReceive(...)` để tạo temporary reply queue và chờ response. Handler dùng **chính Session do DMLC cấp** để tạo `TextMessage` và `MessageProducer`, sau đó trả reply có cùng application correlation ID.

Môi trường: Java 17+, Maven, Docker, một broker Apache ActiveMQ Artemis local. Ví dụ dùng Spring Boot 3.5.7 và namespace `jakarta.jms` để tránh lẫn với API đời cũ.

### 8.1. Khởi động broker local

```bash
docker run --rm -d --name jms-session-aware-broker \
  -p 127.0.0.1:61616:61616 \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  apache/artemis:latest-alpine
docker logs jms-session-aware-broker
```

Chờ broker sẵn sàng. Đây là credential **chỉ cho lab** trên máy cá nhân; production cần secret manager, TLS, ACL và broker provisioning. Queue `demo.session.requests` phụ thuộc chính sách auto-create của broker demo; trong production nên tạo/cấp quyền rõ.

### 8.2. Cấu trúc project

```text
session-aware-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── resources/application.properties
    │   └── java/com/example/jms/SessionAwareApplication.java
    └── test/
        └── java/com/example/jms/SessionAwareApplicationTest.java
```

### 8.3. Maven pom.xml

```xml
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
    <artifactId>session-aware-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

### 8.4. application.properties

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

# Timeout khi requester đợi reply, không phải transaction timeout.
spring.jms.template.receive-timeout=5s
```

Các properties này phục vụ Artemis lab; production không commit mật khẩu thật. Ví dụ dùng JmsTemplate không transacted cho requester (mặc định), còn **DMLC responder** được cấu hình local transaction tường minh trong Java.

### 8.5. SessionAwareApplication.java — mã chạy đầy đủ

```java
package com.example.jms;

import java.util.Objects;
import java.util.UUID;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import jakarta.jms.InvalidDestinationException;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageFormatException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.SessionAwareMessageListener;

@SpringBootApplication
public class SessionAwareApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionAwareApplication.class, args);
    }

    @Bean
    SessionAwareMessageListener<Message> responder() {
        return (incoming, session) -> {
            if (!(incoming instanceof TextMessage request)) {
                throw new MessageFormatException(
                        "Expected TextMessage request");
            }

            Destination replyTo = request.getJMSReplyTo();
            if (replyTo == null) {
                throw new InvalidDestinationException(
                        "Request has no JMSReplyTo");
            }

            String correlationId = request.getJMSCorrelationID();
            if (correlationId == null || correlationId.isBlank()) {
                throw new MessageFormatException(
                        "Missing JMSCorrelationID");
            }

            TextMessage response =
                    session.createTextMessage("ACK:" + request.getText());
            response.setJMSCorrelationID(correlationId);

            // Dùng cùng Session container đã cấp, không tạo Connection mới.
            try (MessageProducer producer = session.createProducer(replyTo)) {
                producer.send(response);
            }
        };
    }

    @Bean
    DefaultMessageListenerContainer sessionAwareContainer(
            ConnectionFactory connectionFactory,
            SessionAwareMessageListener<Message> responder) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        // Boot có thể bao factory gốc bằng CachingConnectionFactory.
        // Listener container nên tự quản connection/recovery.
        container.setConnectionFactory(
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
        container.setDestinationName("demo.session.requests");
        container.setMessageListener(responder);
        container.setExposeListenerSession(true);
        container.setSessionTransacted(true);
        container.setConcurrentConsumers(1);
        container.setMaxConcurrentConsumers(1);
        return container;
    }

    @Bean
    CommandLineRunner runOnce(JmsTemplate template) {
        return args -> {
            String correlationId = "req-" + UUID.randomUUID();

            Message incoming = template.sendAndReceive(
                    "demo.session.requests",
                    session -> {
                        TextMessage request =
                                session.createTextMessage("order-42");
                        request.setJMSCorrelationID(correlationId);
                        return request;
                    });

            if (incoming == null) {
                throw new IllegalStateException("Reply timeout");
            }
            if (!(incoming instanceof TextMessage response)) {
                throw new IllegalStateException(
                        "Expected TextMessage response");
            }

            boolean matches = Objects.equals(
                    correlationId, response.getJMSCorrelationID());
            System.out.println("Reply: " + response.getText());
            System.out.println("Correlation matched: " + matches);

            if (!matches) {
                throw new IllegalStateException(
                        "Wrong response correlation ID");
            }
        };
    }
}
```

**Phân tích từng phần:**

1. `responder()` trả một bean kiểu `SessionAwareMessageListener<Message>`; nó nhận **JMS Message và Session** khi DMLC gọi, không dùng `@JmsListener`.
2. Phương thức kiểm tra `TextMessage`, `JMSReplyTo` và `JMSCorrelationID` trước khi xử lý. Nếu thiếu, ném exception để transaction của listener thất bại theo cấu hình.
3. `session.createTextMessage(...)` và `session.createProducer(replyTo)` dùng đúng **Session** được container cấp. `producer` được đóng sau khi send; không gọi `session.close()` hoặc `session.commit()`.
4. `DefaultMessageListenerContainer` dùng native connection factory nhờ `ConnectionFactoryUnwrapper.unwrapCaching(...)`, tránh dùng nhầm cached connection wrapper làm tầng lifecycle của listener. Class unwrap này có từ Spring Boot 3.4.x.
5. `setSessionTransacted(true)` để **receive+reply** có chung local JMS transaction; `setExposeListenerSession(true)` để callback được cấp chính Session đó.
6. `CommandLineRunner` dùng `JmsTemplate.sendAndReceive(...)` để tự tạo temporary reply queue, đặt `JMSReplyTo`, gửi request và đợi reply. Request có application-generated correlation ID; responder echo ID đó, caller kiểm tra lại.
7. DMLC là Spring `SmartLifecycle` và được khởi động trong quá trình refresh application context trước runner ở cấu hình bình thường; broker vẫn phải sẵn sàng để xử lý trong 5 giây.

**Không đặt thêm một `@JmsListener(destination="demo.session.requests")` vào project demo**; nó sẽ cạnh tranh nhận request với DMLC. Nếu cần minh họa annotation-driven, dùng một project riêng hoặc thay container, không chạy song song hai consumer của cùng queue.

### 8.6. Chạy ứng dụng

```bash
mvn spring-boot:run
```

Khi broker sẵn sàng, DMLC nhận message và gửi reply trong timeout, **hai dòng do code tự in** là:

```text
Reply: ACK:order-42
Correlation matched: true
```

Spring Boot/Artemis còn ghi startup logs; những dòng đó không cố định. UUID ngẫu nhiên không được in, chỉ được đối chiếu. Nếu broker chưa sẵn sàng hoặc responder lỗi, chương trình có thể ném `Reply timeout`, JMS connection exception hoặc lỗi broker khác.

Dừng broker sau bài lab:

```bash
docker stop jms-session-aware-broker
```

**Giới hạn ví dụ:** gửi và trả lời trong cùng ứng dụng để quan sát; requester/responder trong hệ thống thật có thể chạy ở hai JVM. Ví dụ chưa có TLS, secret manager production, DB transaction, outbox, DLQ policy hay kiểm tra failover/duplicate. Output được dự đoán theo code, không phải log thực nghiệm đã chạy.

## 9. Unit test: chứng minh listener dùng Session được truyền vào

Có thể test logic gửi reply mà **không cần broker** bằng Mockito. Mục tiêu là xác nhận listener tạo message/producer từ chính Session mà caller truyền vào và đóng producer của nó; test này **không xác nhận commit/rollback broker**, việc đó cần integration test có Artemis.

### 9.1. SessionAwareApplicationTest.java

```java
package com.example.jms;

import jakarta.jms.Destination;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.junit.jupiter.api.Test;
import org.springframework.jms.listener.SessionAwareMessageListener;
import jakarta.jms.Message;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class SessionAwareApplicationTest {

    @Test
    void replyUsesSuppliedSession() throws Exception {
        Session session = mock(Session.class);
        TextMessage request = mock(TextMessage.class);
        TextMessage response = mock(TextMessage.class);
        Destination replyTo = mock(Destination.class);
        MessageProducer producer = mock(MessageProducer.class);

        when(request.getText()).thenReturn("order-42");
        when(request.getJMSReplyTo()).thenReturn(replyTo);
        when(request.getJMSCorrelationID()).thenReturn("req-test");
        when(session.createTextMessage("ACK:order-42"))
                .thenReturn(response);
        when(session.createProducer(replyTo)).thenReturn(producer);

        SessionAwareMessageListener<Message> listener =
                new SessionAwareApplication().responder();
        listener.onMessage(request, session);

        verify(session).createTextMessage("ACK:order-42");
        verify(session).createProducer(replyTo);
        verify(response).setJMSCorrelationID("req-test");
        verify(producer).send(response);
        verify(producer).close();
    }
}
```

Chạy:

```bash
mvn test
```

Bài test chỉ dùng Mockito/JUnit từ `spring-boot-starter-test`, không tạo Spring context và không cần broker. **Kết quả mong đợi:** test pass nếu dependencies tải được và code đúng. Khi muốn kiểm tra atomic receipt/reply, triển khai integration test với broker thật: gây exception trước khi callback return và quan sát request redelivery/reply không được commit; cần giới hạn số retry và DLQ để tránh test chạy mãi.

## 10. Kết hợp cùng @JmsListener: chọn giao diện phù hợp

Đối với code mới, nhiều ứng dụng dùng `@JmsListener` vì cú pháp gọn, hỗ trợ conversion, validation, `@Header`, `@Payload` và return value. Chữ ký handler vẫn có thể nhận native Session:

```java
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class AnnotatedResponder {

    @JmsListener(destination = "demo.another.requests")
    public void handle(TextMessage request, Session session)
            throws JMSException {
        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            throw new IllegalArgumentException("Missing JMSReplyTo");
        }

        TextMessage reply =
                session.createTextMessage("ACK:" + request.getText());
        reply.setJMSCorrelationID(request.getJMSCorrelationID());

        try (MessageProducer producer = session.createProducer(replyTo)) {
            producer.send(reply);
        }
    }
}
```

Đây là **class minh họa riêng**, không nằm trong project demo ở phần 8. Muốn dùng cần kích hoạt annotation endpoints (thường Boot cấu hình, có thể dùng `@EnableJms`) và listener container factory thích hợp.

Một lựa chọn khác:

```java
@JmsListener(destination = "demo.another.requests")
public String handle(String payload) {
    return "ACK:" + payload;
}
```

Listener adapter có thể tự chuyển return value thành JMS reply khi request có `JMSReplyTo` (hoặc default reply destination/`@SendTo` theo cấu hình). Tuy vậy nếu phải kiểm soát raw JMS header, reply message type, correlation convention hoặc gửi qua **đúng Session** để tham gia local transaction, tham số Session/callback trực tiếp giúp code rõ ràng hơn.

**Không phải cứ thấy `Session` thì phải dùng interface SessionAware.** Interface và annotation là hai cách cấu hình listener; annotation cuối cùng cũng có thể dùng adapter hỗ trợ `SessionAwareMessageListener` ở tầng framework.

## 11. Những lỗi dễ mắc khi truy cập Session

| Lỗi | Tác động | Cách khắc phục |
| --- | --- | --- |
| Import `javax.jms.Session` trong Spring Boot 3 | Sai hệ Jakarta, compile/compatibility lỗi | Dùng `jakarta.jms.*` |
| Dùng `jakarta.jms.MessageListener` rồi khai báo `throws JMSException` | Không phù hợp chữ ký standard interface | Catch/translate exception hoặc dùng SessionAware |
| Tự `session.close()` trong callback | Container mất resource, lỗi consumer/transaction | Container quản lý lifecycle Session |
| Tự `session.commit()` khi container đang quản transaction | Phá transaction boundary | Return/throw để container commit/rollback |
| Tạo Connection khác để send reply | Reply có thể nằm ngoài transaction receive | Gửi qua supplied Session |
| `setExposeListenerSession(false)` nhưng tin reply vẫn chung transaction | Có thể dùng Session mới | Hiểu setting/provider; dùng `true` nếu cần cùng Session |
| Chia sẻ Session qua field/thread khác | Races, JMS IllegalStateException, lifecycle sai | Chỉ dùng trong callback/thread đang xử lý |
| Không đóng producer tự tạo | Rò producer/resource theo provider | Try-with-resources cho MessageProducer |
| Bật nhiều concurrent consumers với listener stateful | Data race và thứ tự xử lý khó kiểm soát | Stateless handler, idempotency và concurrency test |
| Nuốt exception sau lỗi DB | Container tưởng thành công, ack/commit không đúng | Throw để rollback khi lỗi retryable |
| Retry mãi message sai schema | Poison message loop | DLQ/quarantine, phân loại permanent error |
| `JMSReplyTo` null nhưng vẫn createProducer | Không biết reply destination | Validate header hoặc dùng fallback contract |
| Không echo correlation ID | Requester không ghép được response | Quy định và kiểm tra correlation |
| Dùng `JmsTemplate` mới bên trong callback và mặc định cùng Session | Có thể lấy connection/session khác | Ưu tiên trực tiếp supplied Session hoặc kiểm tra resource exposure |
| Trộn JMS local transaction với JDBC và tin atomic | Dual-write, DB/JMS có thể lệch | Idempotency, outbox hoặc XA/JTA đúng cấu hình |

### 11.1. Vì sao reply có thể đến mà request bị giao lại?

Nếu gửi reply bằng một Session độc lập, reply có thể commit trong khi receipt của request rollback. Requester nhận `ACK` nhưng broker redeliver request, worker thực hiện lại business logic. Nếu muốn receive+reply cùng JMS local transaction, dùng cùng Session và `sessionTransacted=true`. Nhưng ngay cả khi hai thao tác JMS commit cùng nhau, **database side effects vẫn cần thiết kế riêng**.

### 11.2. Vì sao không nên giữ Session sau callback?

Container có thể đưa Session về pool/cache, tái sử dụng, commit, rollback hoặc đóng tùy lifecycle. Một async task giữ reference có thể dùng Session thuộc message khác, đã đóng hoặc đang được thread khác dùng. Nếu cần công việc dài, lấy dữ liệu business cần thiết ra DTO và bàn giao cho một cơ chế async khác; muốn gửi message sau đó, dùng `JmsTemplate` với **thao tác mới** và transaction boundary đã thiết kế rõ.

## 12. Hướng dẫn vận hành và kiểm thử thực tế

### 12.1. Checklist production

- [ ] Chọn interface `SessionAwareMessageListener` vì có nhu cầu dùng **raw Session**, không chỉ vì tiện.
- [ ] Dùng đúng Jakarta namespace và Spring JMS version.
- [ ] DMLC/SMLC nhận đúng `ConnectionFactory`, destination, listener, concurrency và recovery settings.
- [ ] `exposeListenerSession` đúng semantics, không đổi vô ý làm tách transaction.
- [ ] Không tự close/commit/rollback Session do container cấp.
- [ ] Tự đóng resource trực tiếp tạo như `MessageProducer` trong callback.
- [ ] Có validation `Message` type, schema/version, `JMSReplyTo`, `JMSCorrelationID`.
- [ ] Chọn `sessionTransacted` hoặc transaction manager chủ đích.
- [ ] Có idempotency khi redelivery/duplicate; DB transaction không tự chung JMS transaction.
- [ ] Cấu hình broker ACL send/consume, TLS, credential/secret manager.
- [ ] Có DLQ, backoff, retry policy và giới hạn poison messages.
- [ ] Listener thread-safe khi tăng concurrent consumers; không giữ Session ở field/static.
- [ ] Requester có receive timeout, xử lý late/unknown reply.
- [ ] Có metrics consumer count, connection/session, error rate, redelivery, DLQ size, latency.
- [ ] Integration test với provider thật khi quan tâm commit/rollback và reply semantics.

### 12.2. Bài kiểm tra tích hợp đề xuất

1. Happy path: request `TextMessage` có `JMSReplyTo`/correlation → reply `ACK:` khớp trong thời gian chờ.
2. Thiếu replyTo: listener ném lỗi; không tự gửi vào destination ngẫu nhiên.
3. Sai message type: listener reject, message đi retry/DLQ theo policy.
4. Sai correlation ID: requester từ chối response không khớp.
5. Handler lỗi trước `return`: khi transacted, request được rollback và reply không commit.
6. Tăng `concurrentConsumers`: xác minh không có shared mutable Session và không xử lý chồng chéo sai.
7. Broker down/restart: DMLC recovery và shutdown không làm mất resource ngoài ý muốn.
8. DB commit trước JMS rollback: kiểm tra dedup của consumer; không tuyên bố exactly-once nếu chưa chứng minh.
9. Reply queue tạm hết vòng đời: responder xử lý failure/late reply an toàn.
10. Production ACL: worker được send vào `JMSReplyTo` hợp lệ, không có quyền quản trị dư.

## 13. Câu hỏi ôn tập

**1. SessionAwareMessageListener khác MessageListener ở đâu?**  
Nó là interface riêng của Spring, cung cấp thêm `Session` trong `onMessage(M, Session)` và cho phép `throws JMSException`.

**2. Vì sao không tự đóng Session trong callback?**  
Vì listener container sở hữu lifecycle, transaction và consumer dựa trên Session đó. Đóng tay có thể phá việc commit/rollback và recovery.

**3. Nếu muốn gửi reply trong cùng JMS transaction, dùng Session nào?**  
Session do container cấp với `exposeListenerSession=true` và cấu hình `sessionTransacted=true` hoặc transaction manager tương ứng.

**4. `MessageProducer` được callback tự tạo có phải đóng không?**  
Có; đóng producer khi dùng xong nhưng không đóng Session được container quản lý.

**5. Spring @JmsListener có thể truy cập Session không?**  
Có. Trong Spring 6.x, method `@JmsListener` có thể khai báo argument `jakarta.jms.Session` khi cần native JMS API.

**6. Session JMS có dùng chung nhiều thread được không?**  
Không. Hãy chỉ dùng trong phạm vi callback/thread; listener singleton vẫn có thể bị gọi đồng thời bởi nhiều consumer.

**7. `sessionTransacted=true` có làm DB và JMS atomic không?**  
Không. Nó xử lý local JMS transaction; DB là resource riêng trừ khi có cơ chế phối hợp đúng hoặc dùng outbox/idempotency.

**8. Khi listener ném `JMSException`, callback có phải tự rollback không?**  
Không, để container/transaction manager xử lý. Broker redelivery tùy policy.

**9. Nếu callback không cần raw Session thì nên dùng gì?**  
`@JmsListener` nhận payload/DTO đơn giản, hoặc standard `MessageListener` nếu cần API portable.

**10. Vì sao tạo một ConnectionFactory riêng trong onMessage có thể sai?**  
Vì tạo session/transaction mới, làm reply không nhất quán với receipt, tốn resource và khó xử lý lỗi.

## 14. Tài liệu tham khảo chính thức

1. [Spring Framework 6.2 — Receiving a Message: SessionAwareMessageListener và transaction](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
2. [Spring Framework 6.2 — SessionAwareMessageListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/SessionAwareMessageListener.html)
3. [Spring Framework 6.2 — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
4. [Spring Framework 6.2 — AbstractMessageListenerContainer: exposeListenerSession](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
5. [Spring Framework 6.2 — Annotation-driven Listener Endpoints và Session argument](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
6. [Spring Boot 3.5 — Artemis JMS](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html)
7. [Spring Boot 3.5 — ConnectionFactoryUnwrapper Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/jms/ConnectionFactoryUnwrapper.html)
8. [Jakarta Messaging 3.1 — Session và MessageProducer](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
9. [Jakarta Messaging 3.1 — MessageProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer)
10. [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)