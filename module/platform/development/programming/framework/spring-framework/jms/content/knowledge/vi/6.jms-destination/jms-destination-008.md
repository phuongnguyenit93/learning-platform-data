# Destination tạm thời và phạm vi vòng đời kết nối

> **Module:** Spring Framework – JMS  
> **Nhóm kiến thức:** Destination  
> **Trọng tâm:** `TemporaryQueue`, `TemporaryTopic`, connection ownership, request/reply và hệ quả khi connection đóng.

## Mục tiêu học tập

Kết thúc bài này, bạn cần có thể:

1. Giải thích `TemporaryQueue` và `TemporaryTopic` trong Jakarta Messaging, phân biệt với `Queue` và `Topic` lâu dài.
2. Phân biệt **session tạo** temporary destination với **connection sở hữu** temporary destination; dự đoán điều gì xảy ra khi đóng consumer, session, `JMSContext` hoặc connection.
3. Giải thích giới hạn bảo mật/ownership: chỉ connection tạo ra temporary destination được **tạo consumer** trên destination đó, trong khi producer trên connection khác vẫn có thể **gửi** vào nó.
4. Áp dụng `JMSReplyTo` và `JMSCorrelationID` trong mẫu request/reply; xử lý timeout, kết quả đến muộn, kết nối gián đoạn và dọn dẹp.
5. Dùng API Jakarta Messaging và Spring `JmsTemplate.sendAndReceive` đúng cách, không biến temporary destination thành hộp thư bền vững.
6. Chọn đúng giữa **temporary reply queue** và **named durable reply queue** theo tuổi thọ yêu cầu nghiệp vụ.

## 1. Temporary destination là gì?

Trong Jakarta Messaging (JMS), `Destination` là giao diện địa chỉ. `Queue` và `Topic` là hai loại destination cơ bản. Hai subtype **tạm thời** là:

```java
jakarta.jms.TemporaryQueue  // extends jakarta.jms.Queue
jakarta.jms.TemporaryTopic  // extends jakarta.jms.Topic
```

Các temporary destination có hai thuộc tính nhận diện:

- **Được provider cấp phát với danh tính riêng**, thường có tên nội bộ độc nhất mà ứng dụng không nên tự đoán hoặc tái sử dụng.
- **Có vòng đời gắn với connection đã tạo ra nó**, trừ khi ứng dụng xóa sớm qua `delete()`.

Trong ứng dụng, một client có thể gửi yêu cầu vào queue cố định `reports.requests` nhưng tạo temporary queue riêng để nhận phản hồi cho lần làm việc hiện tại:

```text
                    Queue thường: reports.requests
Request client --------------------------------------> Report service
     |                                                |
     |       request.JMSReplyTo = temporaryQueue       |
     |                                                |
     |<--------------------- reply --------------------+
     |
  TemporaryQueue thuộc connection của request client
```

Temporary destination **không** đồng nghĩa “message tạm”, “message có TTL ngắn”, “queue tự xóa khi đã đọc hết” hoặc “bộ nhớ chỉ nằm trong JVM”. Đây là **một loại địa chỉ do provider quản lý**, có tính chất *ownership* và *lifecycle* đặc biệt. Provider có thể phải tạo tài nguyên ngoài JVM.

### Khác biệt với tên Queue/Topic thông thường

| Tiêu chí | `Queue` / `Topic` thông thường | `TemporaryQueue` / `TemporaryTopic` |
| --- | --- | --- |
| Cách tạo object | `createQueue("name")`, `createTopic("name")` hoặc JNDI | `createTemporaryQueue()`, `createTemporaryTopic()` |
| Ai chọn tên? | Ứng dụng/admin và provider theo cấu hình | Provider sinh danh tính riêng |
| Có tạo tài nguyên vật lý bằng API chuẩn? | `createQueue(String)` / `createTopic(String)` chỉ tạo **handle**, không bảo đảm tạo resource thật | Lệnh temporary **yêu cầu provider tạo temporary destination** |
| Tuổi thọ | Theo cấu hình và quản trị broker | Theo **connection** sở hữu, hoặc đến lúc `delete()` |
| Ai có thể tạo consumer? | Consumer được phép bởi chính sách broker | **Chỉ connection sở hữu** (có thể nhiều session của connection đó) |
| Ai có thể gửi? | Producer có quyền send | Producer từ **connection khác** cũng có thể gửi nếu có reference/quyền phù hợp |
| Có thể dùng làm địa chỉ lâu dài sau restart client? | Có thể, tùy chính sách giữ destination | **Không**: khi connection gốc đóng, destination kết thúc |
| Mục đích thường gặp | Worker queues, event topics, stable reply queues | Reply tạm theo phiên request/reply |

Một temporary queue vẫn tuân theo mô hình queue khi có nhiều consumer đủ điều kiện **trong cùng connection**. Một temporary topic vẫn mang semantics publish/subscribe, nhưng subscriber/consumer phải thuộc connection sở hữu. Những quy tắc queue/topic cơ bản vẫn tồn tại; tính “temporary” bổ sung **lifecycle và giới hạn ownership**.

## 2. Chốt khái niệm: scope là **connection**, không phải session

Đây là điểm quan trọng nhất của bài.

Jakarta Messaging cung cấp phương thức tạo temporary destination ở `Session` hoặc `JMSContext` để thuận tiện cho người lập trình. Nhưng đối tượng tạm **không thuộc độc quyền session đã gọi create**; nó thuộc **connection bên dưới**.

```text
Connection A  [chủ sở hữu TemporaryQueue Q-temp-abc]
  |
  +-- Session A1  ---> createTemporaryQueue() -> Q-temp-abc
  |
  +-- Session A2  ---> createConsumer(Q-temp-abc)    [ĐƯỢC]
  |
  +-- Session A3  ---> createConsumer(Q-temp-abc)    [ĐƯỢC]
  |
  +-- Session A1 đóng                            [Q-temp vẫn còn]
  |
  +-- Connection A đóng ----------------------> [Q-temp bị xóa]


Connection B  [không sở hữu]
  |
  +-- Session B1  ---> createProducer(Q-temp-abc)  [có thể GỬI]
  |
  +-- Session B2  ---> createConsumer(Q-temp-abc)  [KHÔNG được]
```

Từ sơ đồ suy ra:

- `Session.close()` đóng session và consumer thuộc session đó; **nó không tự kết thúc temporary destination** nếu connection vẫn còn mở.
- Một session **khác của cùng connection** có thể tạo consumer trên temporary destination, dù không phải session tạo queue/topic.
- Một connection **khác** không được tạo consumer trên temporary destination do connection A tạo, kể cả nó biết tên hoặc nhận được object reference.
- Một connection khác **có thể gửi** reply vào temporary destination của A khi có địa chỉ và quyền thích hợp. Vì vậy mô hình request/reply giữa hai dịch vụ hoạt động.
- `Connection.close()` chấm dứt tài nguyên connection, bao gồm các temporary destination do nó tạo.
- Gọi `delete()` sớm có thể chấm dứt temporary destination trước khi connection đóng, sau khi không còn consumer đang dùng.

**Không trộn lẫn 3 cấp:** temporary destination lifetime = connection; consumer lifetime = consumer/session/connection; nội dung message lifetime = quy tắc delivery/ack/expiration trong phạm vi destination còn tồn tại.

### 2.1. Nếu đóng Session A1 thì sao?

Giả sử A1 đã tạo `Q-temp`. A2 cùng connection đang nghe Q-temp. Đóng A1 chỉ đóng tài nguyên session A1; A2 vẫn có thể tiếp tục nhận Q-temp khi connection còn hợp lệ. Ngược lại, khi A2 đóng, temporary queue không tự biến mất chỉ vì không còn listener: phải `delete()` hoặc đóng connection.

### 2.2. Nếu đóng JMSContext thì sao?

`JMSContext` kết hợp chức năng của connection và session trong simplified API. Điểm dễ nhầm:

- `connectionFactory.createContext(...)` tạo một application-managed context có một underlying connection và một session.
- Trong môi trường cho phép, `context.createContext(sessionMode)` tạo **context mới dùng chung connection**, với session khác.
- `JMSContext.close()` đóng **session** của context đó và các producer/consumer liên quan.
- Nếu **không còn context đang hoạt động** dùng connection bên dưới, `close()` cũng đóng connection → temporary destination kết thúc.
- Nếu **vẫn còn context khác dùng chung connection**, đóng một context **không đồng nghĩa đóng connection** → temporary destination có thể còn tồn tại.

Đừng diễn giải giản lược “đóng bất kỳ JMSContext nào là tất cả temporary queues bị xóa”. Phải biết context có thật sự đóng **underlying connection** hay không. Trong môi trường Jakarta EE có injected/container-managed `JMSContext`, container quản lý vòng đời; ứng dụng không được gọi `close()` tùy tiện.

### 2.3. Nếu connection chỉ stop, chứ không close?

`Connection.stop()` hoặc `JMSContext.stop()` tạm dừng delivery của connection; nó **không phải thao tác xóa** destination. Sau khi start lại, consumer có thể tiếp tục theo semantics JMS. Không dùng `stop()` để dọn temporary resource.

### 2.4. Nếu kết nối rơi đột ngột?

Về mặt hợp đồng, temporary destination sống theo connection. Khi broker phát hiện connection đã mất hoặc đóng, nó phải xử lý cleanup theo cơ chế provider. Việc phát hiện mất kết nối, keepalive/heartbeat và dọn tài nguyên trong thời gian thực có thể có độ trễ tùy broker. **Không dùng thời gian quan sát được của một lần crash để suy ra một thời hạn tồn tại cố định theo JMS.**

## 3. Tạo và xóa TemporaryQueue/TemporaryTopic trong API

### 3.1. Simplified API: JMSContext

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TemporaryTopic;

public final class TemporaryDestinations {
    private final ConnectionFactory connectionFactory;

    public TemporaryDestinations(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public void demonstrate() throws Exception {
        try (JMSContext context =
                     connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

            TemporaryQueue replies = context.createTemporaryQueue();
            TemporaryTopic notifications = context.createTemporaryTopic();

            // Tên do provider cấp, không phải tên broker portable.
            System.out.println("Reply queue: " + replies.getQueueName());
            System.out.println("Temporary topic: " + notifications.getTopicName());

            // Chỉ xóa khi không còn consumer sử dụng.
            notifications.delete();
            replies.delete();
        } // Đóng context, và underlying connection nếu không còn shared context.
    }
}
```

Đây là **class Java chạy trong ứng dụng có provider thật**, không phải chương trình standalone chỉ cần JDK. Cần dependency `jakarta.jms`, implementation provider, broker và `ConnectionFactory` đã cấu hình. Tên in ra **không cố định**, nên không cung cấp stdout bịa đặt.

`createTemporaryQueue()`/`createTemporaryTopic()` là lệnh cấp phát temporary destination. Chúng **khác** `createQueue(String)`/`createTopic(String)` vốn chỉ tạo object handle cho một tên provider-specific.

### 3.2. Classic API: Session tạo, Connection sở hữu

```java
Connection connection = connectionFactory.createConnection();
try {
    Session session = connection.createSession(
            false, Session.AUTO_ACKNOWLEDGE);

    TemporaryQueue replyQueue = session.createTemporaryQueue();
    MessageConsumer replies = session.createConsumer(replyQueue);

    connection.start();

    // ... gửi request và nhận reply ...
    replies.close();     // Đóng consumer trước.
    replyQueue.delete(); // Xóa temporary destination sớm.
    session.close();
} finally {
    connection.close();  // Dọn mọi resource còn lại.
}
```

Đây là đoạn minh họa classic `jakarta.jms` nằm trong một method có `connectionFactory`, cần imports và broker thực tế, không thể chạy riêng. Các lời gọi `createTemporaryQueue`, `createConsumer`, `delete` có thể ném `JMSException`; code sản xuất cần `try/finally` hoặc try-with-resources cho những đối tượng có thể đóng, không chỉ dựa vào happy path. Trong ví dụ, nếu một thao tác lỗi trước `replyQueue.delete()`, `connection.close()` vẫn là hàng rào dọn dẹp cuối cùng.

### 3.3. Quy tắc delete() và thứ tự cleanup

`TemporaryQueue.delete()`/`TemporaryTopic.delete()` xóa một destination đang còn tồn tại, nhưng **nếu còn receiver/subscriber đang sử dụng nó**, API có thể báo lỗi `JMSException`. Thứ tự an toàn cho một exchange đồng bộ:

1. Hủy/hoàn tất receive, đóng `JMSConsumer`/`MessageConsumer`.
2. Gọi `tempDestination.delete()` (nếu ứng dụng chủ động quản lý).
3. Đóng session/context/connection khi không còn cần; không tái sử dụng destination object sau khi đã delete.

```java
TemporaryQueue replyTo = context.createTemporaryQueue();
JMSConsumer replyConsumer = context.createConsumer(replyTo);
try {
    // Trao đổi request/reply trong lifetime của connection.
} finally {
    replyConsumer.close();
    replyTo.delete();
}
```

Đoạn này giả định `JMSContext context` đang mở, không chạy độc lập. `delete()` của interface temporary destination có checked `JMSException`, nên method chứa đoạn trên phải khai báo/handle exception phù hợp. Trong hệ thống cần audit lỗi cleanup, nếu thân `try` đã có lỗi mà `delete()` tiếp tục ném, cần giữ được nguyên nhân gốc thay vì làm nó bị che khuất.

### 3.4. Có cần gọi delete nếu sẽ đóng connection ngay?

Đặc tả xác định temporary destination tự được xóa khi connection đóng; có thể được thu hồi khi object được GC. Tuy nhiên, **không nên dựa vào garbage collection làm cơ chế cleanup đúng giờ**. Gọi `delete()` sớm có giá trị khi connection còn được tái sử dụng lâu (ví dụ trong pool/cache), vì broker có thể đang giữ tài nguyên reply queue dù exchange đã hết.

Không cố xóa một destination đang có active consumer; không tiếp tục gửi/nhận trên object đã delete. Nếu cleanup lỗi, cần ghi nhận mà không giả vờ request đã được xử lý thành công.

## 4. Tại sao connection khác gửi được nhưng không consume được?

Đây là tính chất giúp temporary destination trở thành “hộp thư phản hồi riêng”:

```text
CLIENT A (Connection A)                 SERVICE B (Connection B)
----------------------                 ------------------------
create TemporaryQueue T
create Consumer(T)                      KHÔNG được create Consumer(T)

send request
  JMSReplyTo = T             ----------> receive request
                                      |
                                      +-- send reply to T  [ĐƯỢC]
                                               |
Consumer(T) <----------------------------------+
```

**Ownership chỉ hạn chế việc tạo consumer**, không cấm tất cả producer bên ngoài. Cách thiết kế này giúp service xử lý request không giành quyền đọc các reply dành riêng cho client khác.

Nhưng ownership của temporary destination **không phải một cơ chế xác thực người dùng đầy đủ**. Ai được gửi/nhận trên broker vẫn cần quyền truy cập, authentication/TLS và chính sách theo provider. Nếu một đối tượng destination bị lộ, không mặc định rằng không ai gửi message giả vào đó; ứng dụng nên kiểm tra correlation, payload, provenance/trust boundary và quyền sender theo yêu cầu nghiệp vụ.

### TemporaryQueue và TemporaryTopic khác nhau ở đâu?

- `TemporaryQueue` là queue tạm: nhiều consumer **trên connection sở hữu** có thể cạnh tranh nhận reply. Trong request/reply bình thường thường dùng một consumer cho một queue, nhằm tránh phải định tuyến các reply giữa nhiều lời gọi.
- `TemporaryTopic` là topic tạm: consumer/subscription cũng phải thuộc connection sở hữu, nhưng một message publish có thể được phân phối theo semantics topic cho các subscription đủ điều kiện đang hoạt động.
- Không thể dùng durable topic subscription bền vững lâu dài trên temporary topic như một destination ổn định: loại đích này kết thúc theo connection. Đặc tả coi tạo durable subscription tới temporary topic là lỗi lập trình; provider có thể hoặc không phát hiện lỗi ngay.

**Chọn `TemporaryQueue` cho request/reply đơn người nhận** trừ khi yêu cầu đòi mô hình pub/sub trong một connection và provider hỗ trợ kịch bản tương ứng.

## 5. Mẫu request/reply: một connection sở hữu reply queue

Request/reply thường có hai phần destination:

- **Request destination cố định** (ví dụ queue `reports.requests`): service B có thể lắng nghe lâu dài.
- **Reply destination tạm** do client A tạo (ví dụ `temp://A/3F8...` là chuỗi minh họa, **không phải cú pháp chuẩn JMS**): chỉ consumer trên connection A mới được đọc.

### 5.1. Trình tự đầy đủ

```text
Client A                           Broker                         Service B
   |                                  |                               |
   |-- createTemporaryQueue(T) ------>|                               |
   |-- createConsumer(T) ------------>|                               |
   |-- send Request ----------------->|---- deliver request --------->|
   |    JMSReplyTo=T                   |                               |
   |    JMSCorrelationID=req-42        |                               |
   |                                  |<---- send Reply to T ----------|
   |<----------- receive Reply -------|     JMSCorrelationID=req-42   |
   |-- close consumer ---------------->|                               |
   |-- delete T ---------------------->|                               |
   |-- close connection -------------->|                               |
```

**Thứ tự có chủ đích:** tạo temporary reply queue và consumer **trước khi gửi request**, để giảm rủi ro reply đến sớm khi client chưa sẵn sàng. Việc gửi tới destination T từ service B **không** yêu cầu service B phải dùng cùng connection với A.

**JMS không tự làm RPC** khi bạn đặt `JMSReplyTo`. Responder phải lập trình: đọc header `request.getJMSReplyTo()`, xử lý yêu cầu, tạo message reply và gửi vào destination đó. `JMSCorrelationID` hỗ trợ ghép response với request nếu có nhiều exchange.

### 5.2. Correlation ID có hai chiến lược hay gặp

**Client-generated correlation ID:**

1. Client tạo ID duy nhất theo yêu cầu, ví dụ `req-42`.
2. Đặt `request.setJMSCorrelationID("req-42")` trước khi send.
3. Responder sao chép ID vào reply bằng `reply.setJMSCorrelationID(request.getJMSCorrelationID())`.
4. Client so khớp reply với ID chờ.

**Message-ID correlation:**

1. Provider gán `JMSMessageID` cho request khi send.
2. Responder đặt `reply.JMSCorrelationID = request.JMSMessageID`.
3. Client so sánh với `JMSMessageID` được gán cho request sau send.

Cả hai đều là **hợp đồng ứng dụng**, không phải JMS tự khẳng định mọi response sẽ có correlation đúng. Chọn một chiến lược nhất quán cho toàn bộ client và responder; nếu có retry, cân nhắc ID nghiệp vụ ổn định độc lập `JMSMessageID`.

Khi mỗi exchange dùng một temporary queue riêng, địa chỉ duy nhất đã giúp cô lập reply; correlation vẫn có ích cho kiểm tra, audit và phát hiện phản hồi lạ.

### 5.3. Timeout không đồng nghĩa request thất bại

Giả sử client chờ 3 giây, service xử lý mất 10 giây:

```text
t=0s      Client gửi Request, tạo TemporaryQueue T
t=3s      Client timeout, xóa T và/hoặc đóng connection A
t=10s     Service B hoàn thành, cố gửi Reply vào T
```

Reply có thể **không gửi được** vì destination T đã biến mất; hoặc bị broker từ chối/không giao theo chính sách provider. Nhưng request **có thể đã được xử lý thành công ở service B**. Vì vậy client **không được tự suy ra “timeout nghĩa là nghiệp vụ chưa chạy”**.

Khi retry request có side effect (đặt hàng, trừ tiền, gửi email), phải có khóa idempotency hoặc cơ chế truy vấn trạng thái. Responder có thể ghi kết quả vào kho bền vững, cho phép client hỏi lại bằng business request ID.

### 5.4. Những ranh giới độ tin cậy khác

- `DeliveryMode.PERSISTENT` trên reply không biến temporary queue thành địa chỉ có thể tồn tại sau khi connection A đóng.
- `JMSExpiration`/TTL của reply không kéo dài vòng đời T; reply sẽ không thể lấy lại từ T đã bị xóa.
- `AUTO_ACKNOWLEDGE`/transaction quyết định lúc provider coi message đã được nhận/commit, không tạo ra durable reply destination.
- `JMSMessageID` và `JMSCorrelationID` là header; neither tự kiểm chứng response có đúng quyền hoặc payload hợp lệ.
- `Connection.stop()` chỉ tạm dừng delivery; nếu client vẫn muốn nhận reply, cần khởi động lại connection khi đúng thời điểm.

## 6. Ví dụ Jakarta Messaging đầy đủ ở phía request client

Ví dụ dùng **Java 17+**, package `jakarta.jms` và provider đang chạy. Tệp sau là **một class hoàn chỉnh trong project đã có dependency và một `ConnectionFactory` thật**; không chạy bằng `javac` đơn lẻ vì không có broker và dependency Jakarta Messaging.

**Tệp `ReportRequestClient.java`:**

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TextMessage;

import java.util.Objects;
import java.util.UUID;

public final class ReportRequestClient {

    private final ConnectionFactory connectionFactory;

    public ReportRequestClient(ConnectionFactory connectionFactory) {
        this.connectionFactory =
                Objects.requireNonNull(connectionFactory);
    }

    public String requestReport(String reportId) throws JMSException {
        String requestId = UUID.randomUUID().toString();

        try (JMSContext context = connectionFactory.createContext(
                JMSContext.AUTO_ACKNOWLEDGE)) {

            Queue requests = context.createQueue("reports.requests");
            TemporaryQueue replyTo = context.createTemporaryQueue();

            // Tạo consumer trên cùng connection sở hữu replyTo.
            JMSConsumer replyConsumer = context.createConsumer(replyTo);
            try {
                TextMessage request = context.createTextMessage(reportId);
                request.setJMSReplyTo(replyTo);
                request.setJMSCorrelationID(requestId);

                context.createProducer().send(requests, request);

                // Chỉ chờ tối đa 3 giây, không chờ vô hạn.
                Message received = replyConsumer.receive(3_000L);
                if (received == null) {
                    throw new IllegalStateException(
                            "Report request timed out: " + requestId);
                }

                if (!(received instanceof TextMessage reply)) {
                    throw new IllegalStateException(
                            "Unexpected reply message type");
                }
                if (!requestId.equals(reply.getJMSCorrelationID())) {
                    throw new IllegalStateException(
                            "Reply correlation ID mismatch");
                }

                return reply.getText();
            } finally {
                // delete() yêu cầu không còn receiver active.
                replyConsumer.close();
                replyTo.delete();
            }
        }
    }
}
```

**Giải thích:**

1. `context.createTemporaryQueue()` yêu cầu provider cấp phát reply queue có lifetime của **underlying connection**.
2. `context.createConsumer(replyTo)` là hợp lệ vì consumer được tạo trong connection đó; nó cũng làm connection bắt đầu nhận khi `autoStart` theo mặc định.
3. Client đặt `JMSReplyTo` thành object `replyTo`. JMS sẽ vận chuyển reference qua message để responder có thể sử dụng; responder không cần tự đoán tên reply queue.
4. Correlation ID được client sinh và gắn vào request; responder trong ví dụ ở phần sau sẽ echo lại.
5. `receive(3_000L)` có thể trả `null` khi hết timeout hoặc ném runtime exception khi provider lỗi; không coi reply lúc nào cũng đến.
6. `finally` đóng consumer rồi xóa temporary queue. Sau đó context được đóng bằng try-with-resources. Nếu context dùng chung underlying connection với context khác, cần biết rõ điều đó khi suy luận lifecycle.
7. Vì các phương thức của classic `Message` và `TemporaryQueue.delete` có thể ném checked `JMSException`, method khai báo `throws JMSException`. Các phương thức `JMSContext`/`JMSProducer`/`JMSConsumer` trong simplified API thường báo lỗi thông qua `JMSRuntimeException`.

**Lưu ý thực tế:** `finally` ở đây minh họa trình tự cleanup. Trong code sản xuất, một exception từ `replyTo.delete()` có thể che khuất exception gốc từ send/receive; cần ghi nhận exception cleanup và giữ nguyên lỗi nghiệp vụ. Không hứa kết quả nếu broker không hoạt động, queue `reports.requests` chưa provision, hoặc không có responder.

### 6.1. Responder khác connection vẫn gửi được

Ở phía service B, sau khi nhận request trên **queue thường** `reports.requests`, responder:

1. Đọc `request.getJMSReplyTo()`; nếu null thì không thể trả về theo hợp đồng này.
2. Đọc request ID trong `JMSCorrelationID`.
3. Xử lý job; tạo một reply message.
4. Gửi reply đến object `Destination` lấy từ header.
5. Đặt `JMSCorrelationID` trong reply bằng ID request nhận được.

Một đoạn code JMS API minh họa trong session khác:

```java
// Giả định sessionB là jakarta.jms.Session của Service B,
// request là TextMessage đã nhận trên "reports.requests".
Destination replyTo = request.getJMSReplyTo();
if (replyTo == null) {
    throw new IllegalArgumentException("Missing JMSReplyTo");
}

TextMessage reply = sessionB.createTextMessage(
        "READY:" + request.getText());
reply.setJMSCorrelationID(request.getJMSCorrelationID());

MessageProducer producer = sessionB.createProducer(replyTo);
producer.send(reply);
producer.close();
```

Đây **không phải một tệp standalone**: `sessionB` và `request` cần môi trường JMS thật, transaction/ack và xử lý lỗi tương ứng. Producer của service B **không** tạo consumer trên T. Nó chỉ gửi, nên việc service B ở **connection khác** không vi phạm ownership rule.

### 6.2. Test end-to-end với provider

1. Provision queue `reports.requests` trên broker.
2. Chạy responder B nghe queue đó.
3. Khởi động client A và gọi `requestReport("report-42")` khi B đang hoạt động.
4. Xác nhận broker có temporary queue trong thời gian exchange, sau đó queue biến mất khi client cleanup.
5. Kiểm tra response string thực tế, ví dụ `"READY:report-42"` nếu responder implement đúng đoạn trên.
6. Ngắt connection A trước khi B trả; xác minh B xử lý late reply theo policy thay vì treo hoặc retry vô hạn.
7. Thử chạy nhiều request đồng thời, mỗi request có reply destination riêng, kiểm tra giới hạn tài nguyên và timeout.

**Không cung cấp stdout cố định** cho ví dụ JMS vì thời điểm giao nhận, tên queue tạm, kết nối và chính sách provider không xác định chỉ bằng code.

## 7. Spring JMS: request/reply với JmsTemplate

Trong Spring Framework dùng Jakarta Messaging, `JmsTemplate` quản lý phần lớn boilerplate gửi/nhận. Spring có phương thức:

```java
Message sendAndReceive(
        String destinationName,
        MessageCreator messageCreator);
```

Đây là **chữ ký rút gọn minh họa**; API thật có overload nhận `Destination` hoặc dùng default destination. Với implementation `JmsTemplate`, lời gọi này **tạo temporary reply queue** trong exchange, đưa queue vào `JMSReplyTo` của request, chờ reply rồi dọn tài nguyên.

### 7.1. Client Spring gửi request, nhận reply

Giả định Spring project đã cấu hình `jakarta.jms.ConnectionFactory`, `JmsTemplate` và broker. Có thể đặt timeout phù hợp khi cấu hình `JmsTemplate`:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class ReportJmsClientConfig {

    @Bean
    public JmsTemplate reportRequestTemplate(
            ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        template.setReceiveTimeout(3_000L);
        return template;
    }
}
```

**Tệp `ReportGateway.java`:**

```java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

import java.util.Optional;

@Service
public class ReportGateway {

    private final JmsTemplate template;

    public ReportGateway(
            @Qualifier("reportRequestTemplate") JmsTemplate template) {
        this.template = template;
    }

    public Optional<String> request(String reportId) throws JMSException {
        Message reply = template.sendAndReceive(
                "reports.requests",
                session -> session.createTextMessage(reportId));

        if (reply == null) {
            return Optional.empty(); // Timeout: kết quả nghiệp vụ chưa xác định.
        }
        if (!(reply instanceof TextMessage text)) {
            throw new IllegalStateException("Unexpected reply message type");
        }
        return Optional.of(text.getText());
    }
}
```

Hai file là **mã dùng trong Spring project** với dependency `spring-jms` và provider, không phải standalone JDK. Nếu gọi `request("report-42")`, kết quả **có thể** là `Optional.of("READY:report-42")` với responder ví dụ dưới, hoặc `Optional.empty()` khi timeout. Không thể hứa luôn nhận reply.

Spring quản lý temporary queue và consumer trong exchange; đừng giữ object temporary destination của lời gọi đó để dùng lại sau method return. Spring API cho phép cấu hình receive timeout; tránh dùng chờ vô hạn trong request đồng bộ.

### 7.2. Service Spring nhận request và gửi reply

**Tệp `ReportRequestResponder.java`:**

```java
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class ReportRequestResponder {

    private final JmsTemplate jmsTemplate;

    public ReportRequestResponder(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @JmsListener(destination = "reports.requests")
    public void respond(TextMessage request) throws JMSException {
        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            throw new IllegalArgumentException("JMSReplyTo is required");
        }

        String requestId = request.getJMSCorrelationID();
        if (requestId == null) {
            requestId = request.getJMSMessageID();
        }
        final String correlationId = requestId;

        String reportId = request.getText();
        jmsTemplate.send(replyTo, session -> {
            TextMessage reply =
                    session.createTextMessage("READY:" + reportId);
            reply.setJMSCorrelationID(correlationId);
            return reply;
        });
    }
}
```

Đoạn này cố ý nhận `TextMessage` thô để đọc `JMSReplyTo`; Spring `@JmsListener` hỗ trợ raw JMS message. Cần bật `@EnableJms` và có `jmsListenerContainerFactory` phù hợp, hoặc dùng cấu hình auto của Spring Boot; `JmsTemplate` được inject vào responder phải trỏ tới broker và được quyền gửi reply.

**Vì sao `jmsTemplate.send(replyTo, ...)`?** Tham số là object `Destination` từ header, không phải String name. Responder có thể gửi reply vào temporary queue từ connection **khác** (đúng semantics). Không tạo listener mới trên reply queue ở phía service; việc đó sẽ vi phạm ownership.

Ở nhánh request gốc có sẵn `JMSCorrelationID`, responder giữ nguyên ID đó. Nếu request không đặt ID (ví dụ đường `JmsTemplate.sendAndReceive` đơn giản), responder sử dụng `JMSMessageID` do provider gán để hỗ trợ log/correlation. Đây là một lựa chọn hợp đồng; khi cần đối chiếu nghiêm ngặt phải thống nhất strategy giữa client và service.

**Transaction lưu ý:** nếu responder cập nhật DB rồi gửi reply, local JMS transaction của listener không tự gộp DB và send của một `JmsTemplate` khác thành một atomic transaction. Với nghiệp vụ quan trọng, cần idempotency/outbox hoặc cách phối hợp transaction thích hợp.

### 7.3. Vì sao không nên tự lưu temporary reply queue trong Spring singleton?

Nhiều ứng dụng Spring dùng connection caching hoặc connection pooling. Một lời gọi `Connection.close()` trên **proxy** không nhất thiết đóng physical broker connection ngay, và một temporary destination tạo trên connection đã tái sử dụng có thể tồn tại khác với trực giác “hết method là mất”.

- Nếu cache/pool trả connection về thay vì đóng vật lý, **đừng dựa vào close proxy để kết luận broker đã dọn T ngay**.
- Spring `JmsTemplate.sendAndReceive` tự quản lý temporary queue trong phạm vi request, nên thường an toàn hơn tự tạo hàng nghìn queue rồi quên delete.
- Spring `CachingConnectionFactory` có cơ chế tránh cache producers/consumers với temporary destination theo implementation, nhưng không nên suy ra điều này loại bỏ mọi rủi ro memory leak khi tự viết resolver hoặc code cache.
- Nếu muốn dùng reply destination cố định hoặc xử lý nhiều request đồng thời trên một reply consumer, hãy thiết kế correlation và concurrency rõ ràng; không ngẫu nhiên tái sử dụng object `TemporaryQueue` đã thuộc một physical connection khác.

Một lỗi rất thường gặp là lưu `TemporaryQueue` làm field của singleton bean rồi dùng lại sau broker reconnect. Object cũ chỉ đại diện destination được tạo trên connection cũ; sau khi connection gốc đã đóng thì nó không còn là reply mailbox hợp lệ.

## 8. Request/reply trong một local transaction: điểm dễ mắc kẹt

Giả sử client dùng `JMSContext.SESSION_TRANSACTED`, cùng một transaction vừa **gửi request** vừa **chờ reply**:

```java
// CHỐNG MẪU: ngữ cảnh transacted, thiếu commit trước receive.
JMSContext context =
        connectionFactory.createContext(JMSContext.SESSION_TRANSACTED);

TemporaryQueue replyTo = context.createTemporaryQueue();
TextMessage request = context.createTextMessage("report-42");
request.setJMSReplyTo(replyTo);
context.createProducer().send(requests, request);

Message reply = context.createConsumer(replyTo).receive(5_000L);
// Responder có thể chưa nhận được request vì send chưa commit!
context.commit();
```

**Không triển khai đoạn trên**: đây là minh họa lỗi. Trong local JMS transaction, request sent chưa commit có thể chưa được broker giao cho responder; client lại chờ reply trước khi commit → timeout, treo theo timeout hoặc deadlock logic.

Cách tổ chức đúng:

1. Gửi request và **commit send** trước khi chờ reply nếu sử dụng transaction cho send.
2. Dùng transaction/ack rõ ràng cho bước nhận reply, tránh giữ một transaction chưa commit trong lúc chờ bên kia.
3. Hoặc dùng non-transacted JMS context cho exchange đồng bộ đơn giản, kết hợp timeout và idempotency thích hợp.
4. Tránh các transaction đồng bộ bao trùm HTTP request → JMS request → reply mà không có kế hoạch timeout, rollback và tài nguyên.

Jakarta EE Tutorial nêu rõ hạn chế này với local transaction. Mẫu request/reply cần tôn trọng ranh giới transactional, không phải “cứ bật transacted là đáng tin hơn”.

## 9. Chọn temporary reply hay reply queue có tên cố định?

| Yêu cầu | Temporary reply destination | Named reply Queue/Topic |
| --- | --- | --- |
| Request ngắn, client chờ trực tiếp vài giây | Thường phù hợp | Có thể dùng, nhưng cần tự xử lý multiplexing/correlation |
| Client có thể tắt và quay lại sau vài giờ | **Không phù hợp**; connection cũ biến mất | Phù hợp hơn khi provision, retention và delivery mode hỗ trợ |
| Service xử lý tác vụ mất vài phút/giờ | Rủi ro response đến sau khi temporary queue đã bị xóa | Có thể dùng stable reply queue hoặc trạng thái job trong DB/object store |
| Có nhiều request đồng thời | Mỗi exchange có thể tạo reply queue riêng; có chi phí tài nguyên | Một reply queue chia sẻ cần selector/dispatcher theo correlation ID |
| Muốn nhiều consumer ở các connection khác nhau cùng đọc reply | **Không được** với temporary destination | Có thể nếu policy/semantics queue/topic cho phép |
| Xóa khi client connection đóng | Tự động theo lifecycle | Không tự động, do quản trị broker |
| Cần consumer nhận lại sau restart client | Không thể coi đó là cùng mailbox | Có thể dùng queue bền vững với identity và retention phù hợp |

### Mẫu thay thế cho xử lý lâu

Ví dụ generate báo cáo mất 40 phút:

1. Client gửi lệnh `CreateReport` với `jobId` duy nhất vào **queue lâu dài**.
2. Service ghi nhận job, trả nhanh `ACCEPTED` (nếu cần) hoặc không cần giữ HTTP chờ.
3. Worker xử lý, ghi trạng thái `PENDING/RUNNING/DONE/FAILED` và kết quả vào kho bền vững.
4. Client kiểm tra trạng thái theo `jobId` hoặc nhận event qua cơ chế notification/queue **ổn định**.
5. Mọi request retry dùng cùng idempotency key; result không dựa vào temporary queue còn sống.

Temporary reply queue vẫn có thể được dùng cho **ACK nhanh**, nhưng không nên là nơi duy nhất nắm kết quả lâu dài.

## 10. Vòng đời và cleanup: bảng tình huống

Giả sử connection A tạo temporary queue T.

| Hành động | T còn tồn tại theo lifecycle không? | Consumer của A? |
| --- | --- | --- |
| Consumer A đóng | **Có**, nếu chưa `delete()` và connection vẫn mở | Consumer vừa đóng không hoạt động; có thể tạo consumer mới ở A |
| Session tạo T đóng | **Có**, nếu connection A vẫn mở | Consumer của session đó đóng; session khác cùng A có thể tạo consumer |
| Connection A `stop()` | **Có** | Delivery tạm dừng, không xóa T |
| Connection A `start()` lại | **Có** | Có thể tiếp tục nhận theo semantics provider |
| Một shared `JMSContext` đóng, underlying connection vẫn được context khác dùng | **Có** | Consumer của context đóng; context khác cùng connection có thể tạo consumer |
| `delete()` thành công khi không còn consumer đang dùng | **Không** | Consumer không còn đường hợp lệ để đọc T |
| Connection A thực sự `close()` | **Không** | Toàn bộ session/consumer thuộc A đóng |
| Connection A mất mà broker chưa phát hiện | Trạng thái cleanup thực tế có thể chưa hoàn tất ngay | Không coi T là mailbox đáng tin cậy sau failure |
| Client restart và lấy connection mới A2 | **Không phải connection A**, không nối lại T như trước | Phải tạo temporary destination mới nếu cần |

**Có thể có message đang chờ nhưng destination vẫn bị xóa vì connection đóng.** Không có cấu hình `PERSISTENT` nào “cứu” vòng đời T khỏi việc xóa.

Nếu provider có quản trị log/metric về temporary destinations, quan sát count theo connection, số destination không còn consumer, thời gian sống và cleanup sau timeout. Những metric này quan trọng khi tải request/reply lớn.

## 11. Minh họa Java 17 chạy độc lập: mô hình connection ownership

Để phân biệt session và connection, ví dụ sau chạy **hoàn toàn bằng JDK 17** và mô phỏng một số quy tắc permission/lifecycle. Đây **không phải implementation Jakarta Messaging**: không có broker, persistence, JMS headers, JMS transactions hoặc network.

Tạo tệp **`TemporaryScopeDemo.java`**:

```java
public final class TemporaryScopeDemo {
    static final class TemporaryMailbox {
        private final String ownerConnectionId;
        private boolean exists = true;

        TemporaryMailbox(String ownerConnectionId) {
            this.ownerConnectionId = ownerConnectionId;
        }

        boolean canConsume(String connectionId) {
            return exists && ownerConnectionId.equals(connectionId);
        }

        boolean canSend(String connectionId) {
            return exists; // Giả sử được broker cấp quyền send.
        }

        void closeCreatingSession() {
            // Session đóng không xóa destination của connection.
        }

        void closeOwnerConnection() {
            exists = false;
        }

        boolean exists() {
            return exists;
        }
    }

    public static void main(String[] args) {
        TemporaryMailbox reply = new TemporaryMailbox("conn-A");

        System.out.println("Owner consume: " +
                reply.canConsume("conn-A"));
        System.out.println("Same connection / other session: " +
                reply.canConsume("conn-A"));
        System.out.println("Other connection consume: " +
                reply.canConsume("conn-B"));
        System.out.println("Other connection send: " +
                reply.canSend("conn-B"));

        reply.closeCreatingSession();
        System.out.println("After session close: " + reply.exists());

        reply.closeOwnerConnection();
        System.out.println("After connection close: " + reply.exists());
    }
}
```

Biên dịch/chạy:

```bash
javac TemporaryScopeDemo.java
java TemporaryScopeDemo
```

**Stdout chính xác:**

```text
Owner consume: true
Same connection / other session: true
Other connection consume: false
Other connection send: true
After session close: true
After connection close: false
```

Trong ứng dụng JMS thật, `connectionId` không phải chuỗi client tùy đặt như mô phỏng; connection ownership do provider quản lý. Việc demo trả true cho `canSend("conn-B")` giả định sender có quyền; broker thật có thể từ chối nếu access control cấm. Mục đích demo là khắc sâu **connection ownership**, không thay thế bài test với provider.

## 12. Lỗi vận hành thường gặp và cách xử lý

### Lỗi 1 — “TemporaryQueue thuộc session, đóng session tạo queue là xóa queue”

**Sai:** lifecycle gắn connection. Một session khác trên cùng connection vẫn có thể consume. Kiểm tra underlying connection có thật sự đóng chưa.

### Lỗi 2 — “Responder phải kết nối vào cùng connection với requester”

**Sai:** responder chỉ **send**. Connection khác được phép gửi vào temporary destination khi có reference và quyền. Nó **không** được tự tạo consumer trên destination đó.

### Lỗi 3 — “TemporaryQueue là queue durable, vì message gửi PERSISTENT”

**Sai:** delivery mode không kéo dài vòng đời destination. Khi owning connection đóng, temporary queue bị xóa và pending reply không còn như mailbox cố định.

### Lỗi 4 — “Reply timeout đồng nghĩa service chưa làm gì”

**Sai:** service có thể đã thực hiện side effect và phản hồi đến muộn. Retry theo business ID/idempotency; khi cần, truy vấn kết quả bền vững thay vì chạy lại mù quáng.

### Lỗi 5 — “Có thể gửi vào queue cũ sau khi client reconnect”

**Không nên giả định:** temporary destination của connection cũ đã kết thúc. Tạo temporary queue mới trên connection mới và quảng bá reference mới qua `JMSReplyTo`.

### Lỗi 6 — “Đóng connection proxy từ pool là broker đã giải phóng mọi temp queue ngay”

**Không chắc:** cache/pool có thể giữ physical connection. Tập trung vào explicit cleanup, lifetime thực, resource metrics và thư viện request/reply được quản lý.

### Lỗi 7 — “Gọi delete() khi listener còn đang receive”

**Có thể lỗi:** API cho phép báo `JMSException` nếu receiver/subscriber còn dùng. Đóng consumer rồi delete; xử lý race nếu có thread khác đang nhận.

### Lỗi 8 — “Chỉ cần JMSReplyTo, broker tự gửi phản hồi”

**Sai:** service B phải đọc header, tạo reply và gửi. `JMSReplyTo` chỉ là địa chỉ mong muốn, không tự kích hoạt RPC.

### Lỗi 9 — “JMSCorrelationID luôn tự điền đúng”

**Sai:** quy tắc matching do ứng dụng/framework cung cấp; phải thống nhất client-generated ID hay echo `JMSMessageID`. Với `JmsTemplate.sendAndReceive` mỗi exchange có queue tạm, không suy ra nó tự đặt correlation theo nghiệp vụ.

### Lỗi 10 — “Một transaction local vừa send request vừa block receive thì ổn”

**Có thể deadlock/timeout:** message send chưa commit nên responder chưa nhận. Commit request trước khi chờ reply, hoặc chọn non-transacted exchange với ranh giới nghiệp vụ hợp lý.

### Lỗi 11 — “Temporary topic hỗ trợ durable subscriber sống sau restart”

**Sai:** temporary topic kết thúc khi connection đóng; durable subscription dài hạn cần topic ổn định và danh tính subscription thích hợp.

### Lỗi 12 — “Không cần dọn temporary queue vì Java GC sẽ lo”

**Nguy hiểm:** dọn do GC không có deadline; provider giữ tài nguyên ngoài JVM. Đóng consumer và delete chủ động nếu connection sống lâu, hoặc dùng API/framework quản lý lifecycle rõ ràng.

## 13. Kịch bản kiểm thử nên làm với broker thực

### Test A — Session close không xóa queue

1. Tạo `Connection A` và `Session A1`.
2. Tạo `TemporaryQueue T` bằng A1.
3. Tạo `Session A2` **trên cùng Connection A**; tạo consumer cho T bằng A2.
4. Đóng A1; để A2 và Connection A tiếp tục hoạt động.
5. Dùng producer trên Connection B gửi test message vào T; kiểm tra A2 vẫn có thể nhận.
6. Đóng consumer A2, delete T, đóng connection A.

Kết quả cần kiểm chứng: **Session A1 close không xóa T**. Không dự đoán tên T hoặc thời điểm routing chính xác theo broker.

### Test B — Connection khác gửi được, nhưng không consume được

1. A tạo T, A có consumer trên T.
2. B lấy reference T từ `JMSReplyTo` của request.
3. B tạo producer và gửi reply vào T — hợp lệ nếu policy cho phép.
4. B cố tạo consumer trên T — phải bị từ chối theo rule ownership (đường báo lỗi có thể khác giữa provider và API).
5. A nhận reply và kiểm tra correlation.

Kết quả cần kiểm chứng: **read restriction thuộc connection, write permission không phải connection exclusivity**.

### Test C — Timeout và late reply

1. Đặt reply timeout 2 giây.
2. Cho responder xử lý 10 giây; client timeout, đóng consumer, delete temporary queue.
3. Responder cố gửi reply đến T cũ; kiểm tra xử lý lỗi provider, log và retry policy.
4. Client truy vấn job state theo business ID để xác định request đã thành công hay chưa; không lặp side effect.

Kết quả: timeout **không** chứng minh request chưa xử lý.

### Test D — JMSContext chia connection

1. Trong Java SE, tạo `JMSContext primary`.
2. Dùng `primary.createContext(JMSContext.AUTO_ACKNOWLEDGE)` tạo context con trên cùng connection; provider/môi trường phải cho phép.
3. Tạo T bằng primary; tạo consumer T bằng context con.
4. Đóng primary trong lúc context con vẫn hoạt động.
5. Kiểm tra T còn tồn tại và context con còn tiêu thụ được; đóng context con cuối cùng và quan sát cleanup.

Không áp dụng bài test này nguyên xi cho injected/container-managed JMSContext trong Jakarta EE web/EJB container, nơi việc tự tạo thêm session và close context có hạn chế.

### Test E — Kiểm tra Spring caching và resource pressure

1. Dùng `JmsTemplate.sendAndReceive` thực hiện vài trăm request tuần tự, mỗi request có timeout hữu hạn.
2. Quan sát số temporary queues đang tồn tại qua admin console broker, connection count và memory/heap.
3. Tạo vài request timeout liên tục; bảo đảm resource về mức bình thường sau cleanup.
4. Bật CachingConnectionFactory hoặc pool theo cấu hình thực tế và lặp lại.
5. Kiểm tra không vô tình giữ object temporary destination ngoài exchange, không tạo consumer leak, không che lỗi send/receive.

Đừng đặt tiêu chí “mọi broker đều thu hồi trong đúng 0 ms”; quan sát xu hướng và chính sách cleanup của provider.

### Test F — Local transaction bị kẹt

1. Trong môi trường thử nghiệm, cấu hình `SESSION_TRANSACTED`, gửi request rồi receive trước commit.
2. Quan sát timeout hoặc request chưa được responder thấy.
3. Sửa bằng cách commit send trước receive hoặc tách transaction, kiểm tra responder nhận request.
4. Kết hợp idempotency và timeout khi dùng request/reply cho nghiệp vụ.

## 14. Checklist thiết kế

Trước khi chọn temporary destination trong JMS/Spring, hãy xác nhận:

- [ ] **Tuổi thọ nghiệp vụ:** reply có cần sống qua restart hoặc sau khi caller không còn online? Nếu có, không dùng temporary queue làm mailbox duy nhất.
- [ ] **Connection owner:** ai giữ connection thật sự mở đến khi reply xong? Có pooling/cache, reconnect, failover không?
- [ ] **Consumer owner:** mọi consumer của temporary destination có thực sự được tạo trong connection sở hữu không?
- [ ] **Producer bên ngoài:** responder có reference chính xác từ `JMSReplyTo` và quyền send không?
- [ ] **Correlation:** có request ID duy nhất, quy tắc echo/so khớp và business idempotency rõ ràng không?
- [ ] **Timeout:** thời hạn chờ bao lâu, retry thế nào, late reply được xử lý ra sao?
- [ ] **Transaction:** send request đã commit trước khi chờ reply chưa; transaction của responder có ảnh hưởng gì?
- [ ] **Cleanup:** consumer đóng trước delete, connection đóng cuối; có theo dõi lỗi cleanup không?
- [ ] **Broker policy:** queue quota, TTL, permissions, resource limits và cleanup khi node/network lỗi?
- [ ] **Quan sát:** số temporary destinations, pending replies, timeout rate, orphan requests, redelivery và business result status?

Một số hệ thống quy mô lớn dùng **stable reply queue + correlation dispatcher** để giảm overhead cấp phát temp queue từng request; đổi lại phải tự quản lý multiplexing, các reply đến muộn và concurrency. Không có lựa chọn tốt tuyệt đối, chỉ có hợp đồng vòng đời phù hợp.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Session S1 trên Connection A tạo T. S1 đóng, S2 cùng Connection A còn mở. S2 có thể tạo consumer trên T không?

**Đáp án:** Có. Temporary destination thuộc **connection**, không chỉ thuộc session tạo ra nó.

**Câu 2.** Service B trên Connection B nhận một request có `JMSReplyTo=T` của Connection A. B có thể gửi reply đến T không?

**Đáp án:** Có, nếu reference còn hợp lệ và có quyền send. Nhưng B **không được** tạo consumer trên T.

**Câu 3.** Client đóng Connection A sau khi gửi request nhưng trước reply. Dùng `PERSISTENT` có giữ T lại không?

**Đáp án:** Không. Destination tạm bị xóa khi owning connection đóng; persistent delivery không thay đổi lifetime của T.

**Câu 4.** Client tạo two JMSContext dùng chung underlying connection. Đóng context đầu tiên luôn xóa T?

**Đáp án:** Không. Nếu context thứ hai còn hoạt động trên connection đó, underlying connection chưa đóng; T vẫn có thể tồn tại.

**Câu 5.** `JMSReplyTo` có tự buộc JMS provider sinh một reply message?

**Đáp án:** Không. Ứng dụng responder phải tạo và send reply.

**Câu 6.** Một request timeout, service sau đó trả `READY`. Có thể kết luận service chưa thực hiện tác vụ khi timeout không?

**Đáp án:** Không. Timeout chỉ nói caller không nhận được reply trong thời gian chờ. Cần business ID/job state để biết kết quả thật.

**Câu 7.** Với local transaction, client gửi request rồi block receive trước commit: vì sao có thể bị kẹt?

**Đáp án:** Request chưa commit nên responder chưa được giao để xử lý; không có reply để client nhận.

**Câu 8.** Vì sao cần đóng consumer trước khi `TemporaryQueue.delete()`?

**Đáp án:** API có thể ném `JMSException` khi còn receiver đang dùng queue. Cleanup hợp lệ phải tôn trọng các tài nguyên đang hoạt động.

**Câu 9.** `TemporaryTopic` có thể là destination cho durable subscription qua nhiều lần restart không?

**Đáp án:** Không. Nó bị xóa theo owning connection, trái yêu cầu bền vững của durable subscription dài hạn.

**Câu 10.** Trong Spring, `JmsTemplate.sendAndReceive` có tạo temporary queue theo mỗi exchange không, và người dùng có cần lưu queue đó vào singleton không?

**Đáp án:** Implementation `JmsTemplate` tạo temporary reply queue cho exchange và quản lý vòng đời. Không giữ/reuse object đó trong singleton sau exchange.

**Câu 11.** Nếu một physical connection ở pool chưa đóng, gọi `close()` trên proxy có đủ để khẳng định temporary destination đã bị xóa không?

**Đáp án:** Không. Cần hiểu proxy/pool và cleanup cụ thể; nên explicit delete hoặc dùng framework quản lý.

**Câu 12.** Nếu cần kết quả của tác vụ chạy 40 phút sau khi caller restart, nên chọn gì?

**Đáp án:** Stable queue/job state/result store hoặc named reply queue với retention/correlation phù hợp, không phụ thuộc temporary destination của connection cũ.

## Kết luận

**Temporary destination là địa chỉ JMS có định danh do provider tạo và được sở hữu theo CONNECTION.** Session hoặc JMSContext chỉ là nơi cung cấp API tạo; một session khác cùng connection vẫn có thể consume. Connection khác **có thể send** vào địa chỉ tạm, nhưng **không được tạo consumer** ở đó. Đóng connection hoặc gọi `delete()` đúng lúc làm temporary destination hết vòng đời.

Mô hình này phù hợp với **request/reply ngắn hạn** nhờ `JMSReplyTo`, timeout và correlation. Với công việc dài, cần chịu lỗi/restart và kết quả bền vững, hãy sử dụng destination ổn định hoặc kho trạng thái nghiệp vụ. Thiết kế đúng temporary destination không chỉ là gọi `createTemporaryQueue()` mà còn phải hiểu **connection ownership, transaction, timeout, cleanup và broker resource policy**.

### Tài liệu tham khảo chính thức

1. [Jakarta Messaging 3.1 Specification — 6.2.2 Creating temporary destinations](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — scope theo connection, quyền consume, lifecycle và quyền send từ connection khác.
2. [Jakarta Messaging 3.1 — JMSContext API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext) — `createTemporaryQueue()`, `createTemporaryTopic()`, `createContext()` và `close()`.
3. [Jakarta EE Tutorial — JMS Concepts](https://jakarta.ee/learn/docs/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html) — temporary destinations, request/reply và cảnh báo local transaction.
4. [Jakarta Messaging — TemporaryQueue API](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/jms/temporaryqueue) — `delete()` và ràng buộc với active receivers.
5. [Jakarta Messaging 3.1 — TemporaryTopic API](https://javadoc.io/static/jakarta.jms/jakarta.jms-api/3.1.0/jakarta.messaging/jakarta/jms/TemporaryTopic.html) — lifetime và `delete()`.
6. [Spring Framework — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/jms/core/JmsTemplate.html) — `sendAndReceive` tạo temporary reply queue.
7. [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate`, `MessageCreator` và destination resolution.
8. [Spring Framework — CachingConnectionFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html) — cache connection/session và lưu ý temporary destinations.