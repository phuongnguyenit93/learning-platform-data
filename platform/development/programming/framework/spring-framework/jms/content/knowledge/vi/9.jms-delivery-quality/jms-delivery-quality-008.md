# Vô hiệu hóa message ID hoặc timestamp: mục đích và đánh đổi trong Spring JMS

## Mục tiêu học tập

Trong Jakarta Messaging (JMS), khi producer gửi message, provider thường gán hai trường thuộc header là **JMSMessageID** và **JMSTimestamp**. Sinh ID và timestamp có thể gây một phần chi phí xử lý, đặc biệt với lượng message nhỏ rất lớn. Chuẩn JMS cho phép ứng dụng **đề nghị provider không gán** một hoặc cả hai trường này để có cơ hội tối ưu.

Bài học trình bày đầy đủ:

1. Vai trò của `JMSMessageID`, `JMSTimestamp` và thời điểm chúng được thiết lập.
2. Hai tùy chọn `MessageProducer.setDisableMessageID` và `setDisableMessageTimestamp`, tính chất **hint** chứ không phải mệnh lệnh bắt buộc.
3. Setter tương ứng trong Spring `JmsTemplate`: `setMessageIdEnabled` và `setMessageTimestampEnabled`, chú ý logic boolean đảo chiều.
4. Điều gì được và không được tối ưu, điều gì không thay đổi ở persistence, QoS, TTL, expiration, transaction hay redelivery.
5. Chi phí mất thông tin khi dùng request-reply, correlation ID, tracing, monitoring, DLQ, kiểm toán và đo latency.
6. Ví dụ Java 17 với Spring Boot, ActiveMQ Artemis và một thí nghiệm cho cả cấu hình thông thường và cấu hình gợi ý tắt.
7. Checklist quyết định và benchmark hiệu năng trước khi bật tối ưu trong production.

> **Ý chính:** Vô hiệu hóa JMS message ID/timestamp là **gợi ý tối ưu hóa** cho provider. Nếu provider chấp nhận, message ID sẽ là `null` và/hoặc timestamp bằng `0`. Nếu provider bỏ qua, hai header vẫn nhận giá trị bình thường. Không được viết logic nghiệp vụ dựa trên giả định provider bắt buộc chấp nhận.

## 1. Hai header chuẩn dùng để làm gì?

### 1.1. `JMSMessageID`

`JMSMessageID` là một trường header do **JMS provider gán khi gửi**. Đọc bằng:

~~~java
String id = message.getJMSMessageID();
~~~

Nếu được bật, ID thông thường mang tiền tố `ID:` và dùng để nhận diện message được provider gửi. Theo Jakarta Messaging specification 3.1, phạm vi bảo đảm duy nhất do provider xác định, ít nhất trong phạm vi một installation của provider; **không bảo đảm duy nhất trên mọi broker và mọi hãng**.

Những use case thường dùng header này:

- Đối chiếu log producer, broker và consumer.
- Tìm một message cụ thể trong công cụ quản trị.
- Theo dõi việc broker giao lại cùng một JMS message.
- Ghi dấu vết DLQ, re-drive và tình huống duplicate.
- Correlation kiểu request-reply, khi response đặt `JMSCorrelationID` bằng ID của request.

**Không đồng nhất JMSMessageID với ID nghiệp vụ.** Một event `OrderCreated` có thể được publisher gửi hai lần thành hai JMS message khác nhau, mỗi message có ID riêng; vì vậy dedup nghiệp vụ cần `eventId` hoặc business key độc lập.

### 1.2. `JMSTimestamp`

`JMSTimestamp` là số `long` kiểu epoch milliseconds cho biết **thời điểm message được giao cho provider để gửi**, đọc bằng:

~~~java
long timestamp = message.getJMSTimestamp();
~~~

Với send đồng bộ, specification quy định khi lời gọi send kết thúc, timestamp do provider đặt nằm trong khoảng thời gian từ lúc send được gọi tới lúc nó trả về. Điều đó **không** bảo đảm đây là:

- Thời điểm sự kiện nghiệp vụ thực sự phát sinh.
- Thời điểm transaction gửi message commit.
- Thời điểm broker ghi xong trên ổ đĩa hoặc gửi qua network.
- Thời điểm consumer thực sự nhận hoặc xử lý message.

Ví dụ event được lưu vào outbox lúc `10:00`, được relay gửi JMS lúc `10:15` và consumer nhận lúc `10:15:02`. Khi đó `eventCreatedAt`, `JMSTimestamp` và `receivedAt` là **ba mốc khác nhau**.

Một công thức gần đúng thường thấy:

~~~java
long timestamp = message.getJMSTimestamp();
if (timestamp > 0L) {
    long ageMillis = System.currentTimeMillis() - timestamp;
    // Đây là tuổi ước lượng, không phải đo end-to-end tuyệt đối.
}
~~~

Với các máy khác nhau, clock skew cũng ảnh hưởng kết quả. Nếu timestamp bằng `0` vì hint được chấp nhận, công thức **không còn hợp lệ**.

### 1.3. Các trường không nên bị nhầm

| Trường | Người chịu trách nhiệm | Ý nghĩa |
|---|---|---|
| `JMSMessageID` | Provider khi send | Định danh JMS message |
| `JMSTimestamp` | Provider khi send | Thời điểm handoff cho provider |
| `JMSCorrelationID` | Thường do application đặt | Nối request-response hoặc một workflow |
| `JMSExpiration` | Provider tính từ time-to-live | Thời điểm hết hạn của message |
| `JMSDeliveryTime` | Provider tính từ delivery delay | Thời điểm sớm nhất có thể giao |
| `JMSRedelivered` | Provider trước khi delivery | Dấu hiệu có thể đang giao lại |
| `JMSXDeliveryCount` | Provider, property khi receive | Số lượt provider đã delivery |
| `eventId` | Application property | ID logic ổn định để idempotency |
| `createdAt` | Business payload/property | Thời điểm tạo sự kiện nghiệp vụ |
| `traceparent` | Tracing propagation | Liên kết các span giữa dịch vụ |

Hai tùy chọn của bài này chỉ liên quan trực tiếp đến **JMSMessageID và JMSTimestamp**. Không có cơ sở để suy ra “tắt tất cả header”, “tắt TTL” hoặc “tắt redelivery”.

## 2. Vì sao có hai tùy chọn tối ưu?

Việc sinh một JMSMessageID có thể cần cấp số thứ tự, tạo cấu trúc ID provider-specific và ghi/truyền thêm byte. Tạo timestamp cần lấy thời gian và truyền thông tin thời gian. Với tải lớn, một số provider có thể giảm chi phí nếu ứng dụng tuyên bố rằng hai thông tin đó không được sử dụng.

JMS đưa ra hai **producer hints**:

~~~java
producer.setDisableMessageID(true);
producer.setDisableMessageTimestamp(true);
~~~

Nghĩa là: “Ứng dụng không phụ thuộc hai header đó; provider **có thể** không sinh chúng”.

~~~text
                 MessageProducer
                       |
              disable ID = true?
              disable time = true?
                       |
                       v
                    Provider
                   /        \
          Chấp nhận hint   Bỏ qua hint
                 |              |
          ID = null         ID = "ID:..."
          Time = 0          Time = epoch millis
                   \        /
                    Consumer
~~~

**Hai hint độc lập.** Provider có thể chấp nhận ID, bỏ qua timestamp hoặc ngược lại. Chuẩn JMS không cam kết mức tăng tốc nào; thông số CPU, latency, kích thước message và throughput phụ thuộc implementation.

### 2.1. Các giá trị mặc định

Nếu không cấu hình gì thêm:

- `setDisableMessageID(false)`: ID được bật.
- `setDisableMessageTimestamp(false)`: timestamp được bật.
- Spring `JmsTemplate` có `messageIdEnabled=true` và `messageTimestampEnabled=true` mặc định.

Do đó, trong phần lớn ứng dụng thông thường, hai header được giữ nguyên, thuận tiện cho truy vết và kiểm tra.

### 2.2. Quy tắc khi provider chấp nhận/bỏ qua

| Hint | Nếu provider chấp nhận | Nếu provider bỏ qua |
|---|---|---|
| Disable message ID | `getJMSMessageID() == null` | Một ID bình thường được gán |
| Disable timestamp | `getJMSTimestamp() == 0L` | Timestamp bình thường được gán |

Mọi kết quả ở hai nhánh trong bảng đều phù hợp với JMS standard. Vì vậy, các assertion dưới đây **không portable**:

~~~java
producer.setDisableMessageID(true);
producer.setDisableMessageTimestamp(true);
producer.send(message);

// Không được mặc định mọi provider bắt buộc thỏa:
assert message.getJMSMessageID() == null;
assert message.getJMSTimestamp() == 0L;
~~~

Việc **đọc lại getter của producer** cũng không chứng minh provider đã thực hiện tối ưu:

~~~java
boolean requestedIdDisabled = producer.getDisableMessageID();
boolean requestedTimeDisabled =
        producer.getDisableMessageTimestamp();
~~~

Chúng biểu thị setting/hint của producer. Để kiểm tra tác dụng, phải đọc header ở message đã gửi xong hoặc khi consumer nhận.

## 3. Cách dùng Jakarta Messaging API thuần

### 3.1. Classic API với `MessageProducer`

~~~java
// Snippet bên trong method có ConnectionFactory hợp lệ.
// Queue phải tồn tại hoặc broker có chính sách auto-create.
try (Connection connection = connectionFactory.createConnection();
     Session session =
             connection.createSession(Session.AUTO_ACKNOWLEDGE)) {

    Queue queue = session.createQueue("lesson.headers.hinted");

    try (MessageProducer producer = session.createProducer(queue)) {
        producer.setDisableMessageID(true);
        producer.setDisableMessageTimestamp(true);

        TextMessage message =
                session.createTextMessage("hello-jms");
        message.setStringProperty("eventId", "evt-100");

        producer.send(message); // synchronous send
        System.out.println(
                "id=" + message.getJMSMessageID());
        System.out.println(
                "timestamp=" + message.getJMSTimestamp());
    }
}
~~~

Import tương ứng từ package `jakarta.jms`: `Connection`, `ConnectionFactory`, `Session`, `Queue`, `MessageProducer` và `TextMessage`. Đây là **snippet**, không phải lớp chạy độc lập; cần broker và ConnectionFactory.

Với provider nhận cả hai hint, dòng in ra *có thể* là:

~~~text
id=null
timestamp=0
~~~

Với provider bỏ qua hint, ID sẽ có dạng `ID:...` và timestamp thường dương. Cả hai kết quả đúng spec. Không cần gọi `connection.start()` chỉ để **send**; `start()` chủ yếu cho phép nhận message.

### 3.2. Phạm vi tác động

Hai phương thức `setDisable...` là setting trên **MessageProducer instance** và ảnh hưởng tới những message được producer đó gửi. Không thay đổi chính sách toàn broker, toàn queue hoặc mọi producer cùng connection.

~~~text
Producer A [disable ID=false] ─┐
                               ├──► Queue orders
Producer B [disable ID=true] ──┘
                               |
                Consumer có thể thấy hai kiểu message:
                  ID bình thường và ID null
~~~

Một producer cùng một session có thể gửi nhiều message tuần tự. Tuy nhiên `Session` là đơn vị sử dụng **một thread điều khiển tại một thời điểm**; đừng đưa cùng session/producer cho nhiều thread chạy đồng thời.

### 3.3. Simplified API với `JMSContext` và `JMSProducer`

~~~java
// Snippet trong method có ConnectionFactory.
try (JMSContext ctx =
        connectionFactory.createContext(
                JMSContext.AUTO_ACKNOWLEDGE)) {
    Queue queue = ctx.createQueue("lesson.headers.hinted");

    ctx.createProducer()
       .setDisableMessageID(true)
       .setDisableMessageTimestamp(true)
       .send(queue, "hello-context");
}
~~~

`JMSProducer` có getter cho các hint tương ứng và hỗ trợ method chaining. Về semantics nó cũng là **hint**, không phải lệnh buộc header bị xóa. `JMSContext` bao gồm session ngầm, không nên giữ thành một field singleton rồi đưa nhiều request thread dùng chung.

### 3.4. Không set trực tiếp hai header trước send

~~~java
// Không dùng các setter này để ép tắt ID/timestamp:
message.setJMSMessageID(null);
message.setJMSTimestamp(0L);
producer.send(message);
~~~

Các setter `setJMSMessageID` và `setJMSTimestamp` tồn tại để **provider** thiết lập header khi send, không phải API ứng dụng để điều khiển QoS. Giá trị tự gán trước send có thể bị provider bỏ qua/ghi đè theo specification.

## 4. Cấu hình tương ứng trên Spring `JmsTemplate`

Spring cung cấp hai setter với tên **Enabled**:

~~~java
template.setMessageIdEnabled(false);
template.setMessageTimestampEnabled(false);
~~~

Đây là điểm dễ sai nhất vì chiều boolean **đảo ngược** so với Java JMS producer:

| Ý định | Jakarta `MessageProducer` | Spring `JmsTemplate` |
|---|---|---|
| Giữ message ID | `setDisableMessageID(false)` | `setMessageIdEnabled(true)` |
| Gợi ý tắt ID | `setDisableMessageID(true)` | `setMessageIdEnabled(false)` |
| Giữ timestamp | `setDisableMessageTimestamp(false)` | `setMessageTimestampEnabled(true)` |
| Gợi ý tắt timestamp | `setDisableMessageTimestamp(true)` | `setMessageTimestampEnabled(false)` |

### 4.1. Khai báo một lần trong cấu hình

~~~java
@Configuration
public class JmsConfig {
    @Bean
    JmsTemplate compactJmsTemplate(
            ConnectionFactory connectionFactory) {
        JmsTemplate t = new JmsTemplate(connectionFactory);
        t.setPubSubDomain(false); // Queue
        t.setMessageIdEnabled(false);
        t.setMessageTimestampEnabled(false);
        return t;
    }
}
~~~

Đây là class cấu hình, cần import `jakarta.jms.ConnectionFactory`, `JmsTemplate`, `@Bean` và `@Configuration`. Nếu ứng dụng dùng Spring Boot thì có thể dựa vào auto-configuration ở trường hợp mặc định; khai báo bean thủ công khi cần chính sách đặc biệt.

Spring tuyên bố `JmsTemplate` **thread-safe sau khi cấu hình**. Do đó phải thiết lập các hint **trước khi template được nhiều service dùng**, không đổi setter theo từng request.

### 4.2. Anti-pattern: đổi cấu hình chung khi đang gửi

~~~java
// SAI: sharedTemplate được nhiều thread gọi.
void sendForEvent(boolean needId, String payload) {
    sharedTemplate.setMessageIdEnabled(needId);
    sharedTemplate.convertAndSend("events", payload);
}
~~~

Thread A vừa set false, Thread B set true, rồi Thread A send có thể dùng setting của B. Không nên coi cặp thao tác setter + send là nguyên tử. Hãy cấu hình **hai template bean** cho hai chính sách cố định.

### 4.3. Hai bean cho hai policy

~~~java
@Bean("fullHeadersTemplate")
JmsTemplate fullHeadersTemplate(ConnectionFactory cf) {
    JmsTemplate t = new JmsTemplate(cf);
    t.setMessageIdEnabled(true);
    t.setMessageTimestampEnabled(true);
    return t;
}

@Bean("leanHeadersTemplate")
JmsTemplate leanHeadersTemplate(ConnectionFactory cf) {
    JmsTemplate t = new JmsTemplate(cf);
    t.setMessageIdEnabled(false);
    t.setMessageTimestampEnabled(false);
    return t;
}
~~~

Các method là snippet nằm trong class `@Configuration`. Hai template có thể dùng chung `ConnectionFactory` vì hint ở **producer/send policy**, không phải thuộc tính broker identity.

Nếu có nhiều bean cùng kiểu `JmsTemplate`, khi inject dùng `@Qualifier("leanHeadersTemplate")` hoặc cấu hình rõ `@Primary` để tránh ambiguity.

### 4.4. Có cần `setExplicitQosEnabled(true)`?

Không cần bật explicit QoS **chỉ để dùng hai hint**. `setExplicitQosEnabled(true)` điều khiển các giá trị **deliveryMode**, **priority** và **timeToLive** trong lời gọi send của JmsTemplate. Message ID/timestamp là các cấu hình producer hint độc lập.

Nếu đồng thời đổi persistent mode, TTL, priority, pooling hoặc transaction rồi đo throughput, bạn sẽ không biết cải thiện đến từ đâu. Hãy benchmark tách từng yếu tố.

## 5. Lợi ích hiệu năng có thể đạt được

### 5.1. Những khoản overhead có thể giảm

Provider có thể:

- Bớt công sinh message ID (ví dụ quản lý sequence/metadata riêng của implementation).
- Bớt thao tác lấy timestamp để điền header.
- Giảm byte header được serialize và truyền qua network hoặc ghi theo định dạng provider.
- Giảm một phần CPU xử lý header với tải số lượng message nhỏ rất lớn.

Những chi phí trên có thể có ý nghĩa ở hệ thống telemetry/metrics/event có **payload nhỏ và lưu lượng cao**. Tuy nhiên nếu bottleneck thực tế là broker disk I/O, network, độ trễ giao dịch, TLS, DB hoặc message conversion, thay đổi hai header có thể **không đo được lợi ích**.

JMS standard không bắt buộc provider tối ưu và không đưa ra % throughput tối thiểu. Provider có thể tiếp tục duy trì metadata nội bộ và bỏ qua hint. “Tối ưu đã được cấu hình” không đồng nghĩa “tối ưu đã thực sự diễn ra”.

### 5.2. Những thứ chắc chắn không được phép suy ra

| Câu nói | Đúng hay sai? |
|---|---|
| Tắt JMSMessageID để broker không cần biết message nào đang ack | **Sai.** Broker có thể có định danh nội bộ riêng. |
| Tắt JMSTimestamp làm message không bao giờ hết hạn | **Sai.** TTL/`JMSExpiration` là cơ chế khác. |
| Hai hint làm delivery mode chuyển từ PERSISTENT sang NON_PERSISTENT | **Sai.** Không tự chuyển mode. |
| Tắt ID là tắt duplicate hoặc redelivery | **Sai.** Ack/transaction/retry hoạt động độc lập. |
| Header có thể không tồn tại nếu provider chấp nhận | **Đúng.** ID `null`, timestamp `0`. |
| Gửi thành công chứng minh consumer đã xử lý | **Sai.** Cần ack/transaction, broker metrics hoặc xác nhận nghiệp vụ. |
| Hint có thể bị provider bỏ qua | **Đúng.** Đây là semantics chuẩn. |

### 5.3. Tối ưu không thay thế tuning

Có thể những tối ưu đem lại hiệu quả cao hơn gồm: giảm kích thước payload, dùng message converter hiệu quả, caching/pooling phù hợp, tránh tạo connection/session quá nhiều, tối ưu persistent store, điều chỉnh send/consumer concurrency, batching theo khả năng provider, giảm network hop. Các việc đó có tradeoff riêng; phải đo trên workload thực.

## 6. Đánh đổi của việc tắt `JMSMessageID`

### 6.1. Quan sát và điều tra sự cố

Nếu ID `null`, một công cụ log/broker console có thể không dùng được JMSMessageID để nối producer log với consumer log. Việc theo dõi một message qua queue, DLQ, retry và re-drive trở nên khó hơn.

Ví dụ hai lần delivery:

~~~text
Bình thường:
  messageId=ID:abc, deliveryCount=1
  messageId=ID:abc, deliveryCount=2

Đã disable ID và provider nhận hint:
  messageId=null, deliveryCount=1
  messageId=null, deliveryCount=2
~~~

JMSRedelivered và JMSXDeliveryCount vẫn có thể có ích, nhưng thiếu ID khiến việc liên hệ **một message vật lý cụ thể** với các lần delivery khác khó hơn.

### 6.2. Request-reply dùng JMSMessageID có thể hỏng

Một mẫu request-reply phổ biến:

~~~text
Requester gửi message R
  Request.JMSMessageID = "ID:R100"

Responder nhận R, tạo reply:
  Reply.JMSCorrelationID = Request.JMSMessageID

Requester nhận reply và match:
  Reply.JMSCorrelationID == "ID:R100"
~~~

Nếu request có `JMSMessageID=null`, responder không còn ID để điền vào correlation field, requester không còn khóa match theo cách cũ. **Không disable ID** nếu protocol request-reply của bạn dùng JMSMessageID. Nếu muốn dùng correlation do ứng dụng kiểm soát, cần thiết kế cả hai phía:

~~~java
// Trong MessageCreator của một request.
String requestId = java.util.UUID.randomUUID().toString();
message.setJMSCorrelationID(requestId);
~~~

Responder và requester phải thống nhất dùng cùng correlationId. `JMSCorrelationID` khác với JMSMessageID, do ứng dụng thường chủ động thiết lập; disable ID **không tự tắt correlation header**.

### 6.3. Business idempotency khác broker ID

JMSMessageID thường giúp nhận ra redelivery của **cùng một JMS message**, nhưng không đủ chống các bản publish trùng do producer:

~~~text
Producer gửi eventId=evt-900 lần 1:
   JMSMessageID=ID:111

Producer gửi cùng eventId=evt-900 lần 2:
   JMSMessageID=ID:222
~~~

Consumer có thể nhận cả hai và thực thi nghiệp vụ hai lần. Giải pháp bền vững là `eventId`/business key ổn định, database unique constraint, idempotency record và transaction phù hợp. Khi tắt ID, bảo đảm eventId có mặt và được bảo toàn qua retry/forward nếu hạ tầng hỗ trợ.

### 6.4. Không có JMS ID không có nghĩa không có broker internal ID

Broker vẫn có thể phải quản lý queue sequence, journal record, delivery tag hoặc identity riêng để ack/retry. JMS không quy định cấu trúc nội bộ. Chỉ được khẳng định **header JMSMessageID có thể null**; không suy đoán mọi ID trên broker biến mất.

## 7. Đánh đổi của việc tắt `JMSTimestamp`

### 7.1. Không được hiểu `0` là “gửi năm 1970”

Nếu provider nhận hint và `getJMSTimestamp()==0L`, hãy coi đó là **không có timestamp**. Mã tính tuổi message phải kiểm tra:

~~~java
long sentAt = message.getJMSTimestamp();

if (sentAt > 0L) {
    long approximateAge = System.currentTimeMillis() - sentAt;
    System.out.println("approxAgeMs=" + approximateAge);
} else {
    System.out.println("JMSTimestamp unavailable");
}
~~~

Nếu vẫn chạy `Instant.ofEpochMilli(0)`, dashboard có thể hiển thị `1970-01-01`, gây hiểu nhầm message tồn đọng 56 năm.

### 7.2. Tracing thời gian cần phân biệt các mốc

~~~text
10:00:00  business event phát sinh (eventCreatedAt)
10:15:00  outbox relay gửi JMS (JMSTimestamp nếu còn)
10:15:02  consumer nhận (receivedAt)
10:15:03  consumer hoàn tất xử lý (processedAt)
~~~

Mỗi mốc có ý nghĩa khác nhau. Bật timestamp giúp đối chiếu thời gian send, nhưng không thay thế timestamp nghiệp vụ. Nếu tắt thì ứng dụng có thể cung cấp `createdAt`, `publishedAt` hoặc trace span thích hợp, kèm chính sách đồng bộ đồng hồ.

Nhược điểm: tạo một property `publishedAtEpochMs` bằng `System.currentTimeMillis()` cũng phải lấy thời gian và thêm byte vào message; điều đó **có thể làm mất lợi ích** mong đợi từ việc tắt header chuẩn. Chỉ tạo timestamp tùy chỉnh khi có nhu cầu thật sự.

### 7.3. TTL/expiration không tự mất

JMS standard tính thời điểm hết hạn từ **time-to-live** và thời điểm gửi:

~~~text
JMSExpiration = sendTime + timeToLive
~~~

Nếu TTL bằng `0`, `JMSExpiration=0` nghĩa là không expire. Nếu TTL khác `0`, provider vẫn phải xử lý expiry theo spec/policy **ngay cả khi JMSTimestamp bị tắt**.

Ví dụ:

~~~java
producer.setDisableMessageTimestamp(true);
producer.setTimeToLive(5_000L);
producer.send(message);
~~~

Nếu provider chấp nhận hint, `getJMSTimestamp()` có thể là `0` nhưng `JMSExpiration` vẫn thể hiện deadline được tính từ TTL. **Tắt timestamp không phải cách vô hiệu hóa TTL.** Với transaction, TTL được tính từ thời điểm send, không phải thời điểm commit.

### 7.4. Delivery delay cũng độc lập

`JMSDeliveryTime` biểu thị thời điểm sớm nhất message có thể được giao dựa trên delivery delay. Đây là header khác với JMSTimestamp; tắt timestamp không có nghĩa tắt scheduled delivery. Kiểm tra broker/provider cụ thể nếu ứng dụng cần delay và expiry kết hợp.

### 7.5. Không có timestamp: cần quan sát theo cách khác

- Log producer send-call start/end để đo chi phí gọi.
- Log consumer received/processed timestamp theo đồng hồ cục bộ.
- Truyền trace context `traceparent` nếu triển khai distributed tracing.
- Với SLA end-to-end từ lúc phát sinh nghiệp vụ, dùng `eventCreatedAt` có nghĩa được chuẩn hóa.
- Với multi-host latency, đánh giá sai số đồng hồ và cách đo.
- Không lấy một timestamp absent hoặc `0` làm thời điểm send thật.

## 8. Bốn cấu hình cần phân biệt

| Trường hợp | `messageIdEnabled` | `messageTimestampEnabled` | Đánh đổi chính |
|---|---|---|---|
| A: mặc định | `true` | `true` | Giữ khả năng nhận diện và thời gian. |
| B: gợi ý tắt ID | `false` | `true` | Có thể giảm overhead ID, khó correlation kiểu ID. |
| C: gợi ý tắt timestamp | `true` | `false` | Có thể giảm overhead time, khó đo tuổi message. |
| D: gợi ý tắt cả hai | `false` | `false` | Tối ưu tiềm năng lớn hơn, giảm cả hai dấu vết. |

**Chỉ kết luận hiệu quả bằng benchmark.** Cùng tên queue không buộc mọi producer bật/tắt giống nhau; consumer phải đọc được cả trường hợp header có và không có khi bạn rollout từng phần.

## 9. Demo chạy được: Java 17, Spring Boot, Artemis

Demo có hai template cấu hình ổn định: một giữ ID/timestamp, một đề nghị tắt. Mỗi template gửi một TextMessage tới một Queue riêng, hai listener đọc header gốc. Không cần bắt provider phải nhận hint; output được diễn giải theo cả hai nhánh hợp lệ.

### 9.1. Chuẩn bị broker cục bộ

Cần JDK 17+, Maven 3.9+ và Docker. Khởi chạy Artemis thử nghiệm trên `localhost:61616`:

~~~bash
docker run --detach --rm --name jms-header-lab \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Kiểm tra broker khởi động:

~~~bash
docker logs jms-header-lab
~~~

Artemis image này dùng cho demo; chính sách broker mặc định thường cho auto-create queue. Trong môi trường có auto-create bị tắt, cần provision queue trước. User/password demo không được dùng cho production.

Cấu trúc:

~~~text
jms-header-lab/
├── pom.xml
└── src/main/
    ├── java/example/JmsHeaderLabApplication.java
    └── resources/application.properties
~~~

### 9.2. `pom.xml`

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
    <artifactId>jms-header-lab</artifactId>
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

### 9.3. `application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

### 9.4. `JmsHeaderLabApplication.java`

~~~java
package example;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsHeaderLabApplication {

    private static final String FULL_QUEUE = "lesson.header.full";
    private static final String HINT_QUEUE = "lesson.header.hinted";

    public static void main(String[] args) {
        SpringApplication.run(JmsHeaderLabApplication.class, args);
    }

    @Bean("fullHeadersTemplate")
    JmsTemplate fullTemplate(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setPubSubDomain(false);
        template.setMessageIdEnabled(true);
        template.setMessageTimestampEnabled(true);
        return template;
    }

    @Bean("leanHeadersTemplate")
    JmsTemplate leanTemplate(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setPubSubDomain(false);
        template.setMessageIdEnabled(false);
        template.setMessageTimestampEnabled(false);
        return template;
    }

    @Bean("demoListenerFactory")
    DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    ApplicationRunner publish(
            @Qualifier("fullHeadersTemplate") JmsTemplate full,
            @Qualifier("leanHeadersTemplate") JmsTemplate hinted,
            HeaderProbe probe) {
        return args -> {
            full.send(FULL_QUEUE, session ->
                    sample(session, "evt-full", "req-full"));
            hinted.send(HINT_QUEUE, session ->
                    sample(session, "evt-hinted", "req-hinted"));

            System.out.println("sentTwoMessages=true");
            System.out.println("receivedBoth=" + probe.awaitBoth());
        };
    }

    private static TextMessage sample(
            Session session, String eventId, String requestId)
            throws JMSException {
        TextMessage m = session.createTextMessage("payload:" + eventId);
        m.setStringProperty("eventId", eventId);
        m.setJMSCorrelationID(requestId);
        return m;
    }

    @Component
    public static class HeaderProbe {
        private final CountDownLatch received = new CountDownLatch(2);

        @JmsListener(destination = FULL_QUEUE,
                     containerFactory = "demoListenerFactory")
        public void onFull(TextMessage message) throws JMSException {
            print("full", message);
        }

        @JmsListener(destination = HINT_QUEUE,
                     containerFactory = "demoListenerFactory")
        public void onHinted(TextMessage message) throws JMSException {
            print("hinted", message);
        }

        private void print(String source, TextMessage message)
                throws JMSException {
            boolean idPresent = message.getJMSMessageID() != null;
            boolean timestampPresent = message.getJMSTimestamp() > 0L;

            System.out.printf(
                    "%s idPresent=%b timestampPresent=%b "
                  + "eventId=%s correlationId=%s%n",
                    source, idPresent, timestampPresent,
                    message.getStringProperty("eventId"),
                    message.getJMSCorrelationID());

            received.countDown();
        }

        boolean awaitBoth() throws InterruptedException {
            return received.await(15, TimeUnit.SECONDS);
        }
    }
}
~~~

**Giải thích:**

- Có một public class đúng tên file và một nested `@Component` listener.
- Hai `@Bean JmsTemplate` được cấu hình lúc khởi động; không dùng setter từ thread gửi.
- `MessageCreator` tạo message với `eventId` và `JMSCorrelationID` do ứng dụng chọn; các field đó có thể tồn tại dù JMSMessageID null.
- Listener nhận raw `jakarta.jms.TextMessage` để kiểm tra đúng header sau khi broker delivery.
- `CountDownLatch` phục vụ quan sát trong demo, không được dùng làm cơ chế ACK/dedup production.
- `setSessionTransacted(true)` điều khiển transaction ở listener và độc lập với hai producer hints.
- Queue phải tồn tại hoặc broker cho auto-create, không phải chỉ vì code gọi `send` mà chắc chắn có tài nguyên vật lý.

### 9.5. Chạy và diễn giải kết quả

Ở thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Nếu hai hint được provider chấp nhận, một **ví dụ** về các dòng do application in:

~~~text
full idPresent=true timestampPresent=true eventId=evt-full correlationId=req-full
hinted idPresent=false timestampPresent=false eventId=evt-hinted correlationId=req-hinted
sentTwoMessages=true
receivedBoth=true
~~~

**Không cam kết thứ tự stdout:** listener chạy bất đồng bộ; dòng `full/hinted` có thể xuất hiện trước hoặc sau `sentTwoMessages` và đổi chỗ. Console còn log Spring Boot/Artemis. Nếu provider bỏ qua một/both hint, `hinted idPresent` và `timestampPresent` có thể vẫn là `true`. Đó vẫn là hành vi hợp chuẩn, không phải bằng chứng code setter sai.

Nếu muốn quan sát số cụ thể, trong `HeaderProbe.print` có thể in:

~~~java
System.out.printf("id=%s timestamp=%d%n",
        message.getJMSMessageID(),
        message.getJMSTimestamp());
~~~

Thao tác phải diễn ra **sau khi message được nhận** hoặc sau synchronous send. Không đọc ID trong `MessageCreator` để kết luận, bởi callback này tạo message **trước khi send**.

Khi xong:

~~~bash
docker stop jms-header-lab
~~~

Container lab dùng `--rm`, không mount volume; dừng container sẽ bỏ dữ liệu broker. Không dùng cấu hình thử nghiệm này trong môi trường cần durability.

## 10. Có nên dùng timestamp hoặc ID riêng thay thế?

### 10.1. Business event ID

Đối với hệ thống có yêu cầu idempotency, `eventId` do producer cấp là lựa chọn tốt hơn ID provider cho **tính duy nhất của sự kiện logic**:

~~~java
message.setStringProperty("eventId", eventId);
~~~

Producer phải bảo toàn cùng `eventId` khi retry publish cùng một event. Consumer dùng unique constraint hoặc idempotency store để ngăn side effect lặp. Đừng dùng `JMSMessageID` làm business key duy nhất chỉ vì nó được bật.

### 10.2. Correlation ID

Có thể dùng application-defined `JMSCorrelationID` để match response, nếu cả hai phía thống nhất:

~~~java
message.setJMSCorrelationID(requestId);
~~~

Cần rõ phạm vi uniqueness; một correlationId có thể gom nhiều event cùng workflow. Không tự suy nó duy nhất từng message.

### 10.3. Business timestamp

Nếu cần thời điểm **business event ra đời**, đặt `eventCreatedAt` trong payload do domain tạo. Nếu cần publish time để báo cáo, có thể đặt `publishedAtEpochMs` bằng đồng hồ producer, nhưng việc này **cũng có chi phí**; tắt JMSTimestamp rồi thêm timestamp tương đương không nhất thiết tiết kiệm tài nguyên.

Phải phân biệt eventCreatedAt, publishedAt, broker ingest time, consumer receivedAt, committedAt và processedAt. Một timestamp đơn lẻ không kể được toàn bộ câu chuyện.

## 11. Kế hoạch benchmark: cách chứng minh lợi ích

Không viết “tăng throughput 20%” khi chưa đo. Dùng bốn biến thể A/B/C/D ở mục 8, đo trên cùng provider và payload:

1. **Chuẩn bị:** xác định broker version, client version, queue/topic, persistent mode, transaction/ack, TLS, pool và message size.
2. **Warm-up:** chạy đủ lâu để JIT và broker cache ổn định; không so lần chạy lạnh với lần chạy nóng.
3. **Cô lập biến:** chỉ thay hai hint; không đồng thời thay độ bền, TTL, batching, number of producers hoặc consumer load.
4. **Đo throughput:** messages/s của producer và consumer; bảo đảm không chỉ đẩy backlog lên broker.
5. **Đo latency:** p50/p95/p99 send call, CPU producer/broker, network bytes/message và error rate.
6. **Kiểm tra header:** tỷ lệ `JMSMessageID == null` và `JMSTimestamp == 0` ở consumer của mỗi biến thể.
7. **Đánh giá vận hành:** log trace, DLQ, request-reply, audit và incident triage còn đủ dữ liệu không?
8. **Lặp lại:** chạy nhiều vòng, hoán đổi thứ tự các biến thể để giảm thiên lệch bởi cache/tải nền.
9. **Ra quyết định:** chỉ bật hint khi tiết kiệm đáng kể và không có dependency lên header.
10. **Chuẩn bị rollback:** cấu hình có thể trả về `Enabled=true` bằng deployment/config đã được kiểm thử.

### Trường hợp kết quả khó hiểu

- **Hint đã đặt nhưng ID/timestamp vẫn có:** provider bỏ qua hint hoặc adapter không hỗ trợ; hợp chuẩn.
- **ID null, timestamp vẫn có:** provider chấp nhận một hint; hợp chuẩn.
- **Throughput không đổi:** chi phí header không đáng kể hoặc provider không tối ưu; không cần ép.
- **Latency tăng:** thay đổi workload/GC/caching hoặc provider path có overhead khác; cần phân tích lại.
- **Tracing hỏng:** consumer/tooling đang dựa vào header bị tắt; phải restore hoặc thiết kế lại.
- **Queue backlog tăng dù send nhanh:** producer throughput vượt consumer capacity; không coi là cải thiện toàn hệ thống.

## 12. Những lỗi phổ biến cần tránh

| Anti-pattern | Vì sao sai? | Cách sửa |
|---|---|---|
| `setMessageIdEnabled(true)` để “disable ID” | Spring dùng tên **Enabled**, true là giữ bật | Dùng `false` khi muốn hint tắt |
| `setDisableMessageID(false)` để “disable ID” | JMS dùng tên **Disable**, false là không tắt | Dùng `true` khi muốn hint tắt |
| Kiểm tra ID null trước `send` trong MessageCreator | Header chưa được provider thiết lập | Kiểm tra sau send hoặc ở consumer |
| Assert bắt buộc ID null/time 0 ở mọi broker | Hint có thể bị bỏ qua | Kiểm tra đúng semantics provider |
| Dùng `JMSTimestamp=0` để tính tuổi message | Cho tuổi giả rất lớn | Coi 0 là timestamp unavailable |
| Tắt ID trong request-reply dùng JMSMessageID | Mất khóa correlation | Giữ ID hoặc thiết kế correlationId riêng |
| Dùng ID provider để chống trùng nghiệp vụ | Hai publish trùng có ID khác nhau | Dùng eventId và durable idempotency |
| Coi tắt timestamp là tắt TTL | TTL/expiration độc lập | Kiểm tra `JMSExpiration` và policy |
| Đổi setter template mỗi request | Race trên cấu hình dùng chung | Dùng template profile bất biến |
| Tối ưu kèm đổi delivery mode/pool/batching | Không biết lợi ích đến từ đâu | Benchmark từng biến độc lập |
| Bỏ qua DLQ, trace, audit | Khó điều tra sự cố thật | Thiết kế observability trước rollout |
| Giả định tắt ID làm broker không có internal ID | JMS chỉ quy định header | Không suy luận implementation nội bộ |

## 13. Checklist trước production

- [ ] Consumer và adapter không dựa bắt buộc vào `getJMSMessageID()` hoặc `getJMSTimestamp()` của nhóm message này.
- [ ] Request-reply không cần request JMSMessageID làm correlation, hoặc đã chuyển sang protocol correlation độc lập.
- [ ] Có business `eventId` ổn định qua producer resend, hỗ trợ idempotency.
- [ ] Có nguồn timestamp nghiệp vụ/tracing cần thiết; không tính tuổi message từ timestamp zero.
- [ ] Quy tắc TTL, priority, delivery delay, persistence, transactions và ack không đổi ngoài ý muốn.
- [ ] Spring `JmsTemplate` được cấu hình một lần; không sửa setter từ request/worker thread.
- [ ] Đã kiểm tra provider **thực sự** chấp nhận hay bỏ qua từng hint.
- [ ] Đã benchmark thực tế throughput/latency/CPU và tác động lên consumer, không chỉ thời gian gửi.
- [ ] Monitoring, DLQ, retry, broker tools và audit vẫn đủ dấu vết để điều tra.
- [ ] Có phương án rollback về hai hint mặc định trong cấu hình đã được test.
- [ ] Đã thử với provider/client version, môi trường staging/prod tương ứng, không chỉ mock.
- [ ] Quyền truy cập broker và cấu hình queue/topic không bị thay đổi vì thí nghiệm header.

## 14. Câu hỏi tự kiểm tra

**1. Gọi `MessageProducer.setDisableMessageID(true)` có bảo đảm message ID null không?** Không. Nếu provider chấp nhận thì ID null; nếu bỏ qua thì ID bình thường.

**2. Gọi `JmsTemplate.setMessageIdEnabled(false)` nghĩa là gì?** Spring đề nghị provider không sinh message ID cho các message được gửi bởi template đó.

**3. Giá trị `getDisableMessageTimestamp()==true` có chứng minh timestamp trong message bằng 0 không?** Không. Getter nói setting producer, không nói provider có chấp nhận hint.

**4. Tắt timestamp có tự tắt TTL/expiration không?** Không. `JMSExpiration` là trường khác được tính theo time-to-live.

**5. `JMSTimestamp=0` có nên chuyển thành Instant 1970 không?** Không. Trong trường hợp hint được chấp nhận, 0 biểu thị timestamp không có.

**6. Vì sao request-reply có thể lỗi nếu tắt ID?** Vì một số protocol dùng JMSMessageID của request làm JMSCorrelationID ở reply, khiến requester không còn khóa match.

**7. Có nên dùng JMSMessageID làm unique business event key?** Không. Producer có thể gửi hai JMS message khác nhau cho cùng một event nghiệp vụ.

**8. Khi đã tắt hai hint mà throughput không tăng, code có chắc sai không?** Không. Provider có thể bỏ qua hint hoặc overhead ID/time quá nhỏ so với bottleneck khác.

**9. Các message cùng queue có thể vừa có ID vừa thiếu ID không?** Có, nếu được gửi từ các producer có chính sách khác nhau và provider chấp nhận hint ở producer tương ứng.

**10. Có cần `setExplicitQosEnabled(true)` chỉ để disable JMSMessageID không?** Không. Explicit QoS điều khiển các giá trị deliveryMode, priority, timeToLive riêng.

**11. Vì sao không đổi `setMessageTimestampEnabled` liên tục trên template singleton?** Vì nhiều thread gửi đồng thời sẽ thấy cấu hình chung bị thay đổi không nguyên tử.

**12. Muốn đo thời gian event được tạo, nên dùng trường nào?** Một business `eventCreatedAt` có semantics rõ, không đánh đồng với JMSTimestamp lúc provider nhận send.

**13. Khi tắt ID, `JMSXDeliveryCount` có tự biến mất không?** Không có quy tắc như vậy. Delivery count là provider property độc lập; việc đối chiếu nhiều lần delivery có thể khó hơn vì thiếu JMSMessageID.

**14. Kết quả nào của demo là hợp chuẩn?** Provider có thể chấp nhận cả hai, chỉ một, hoặc không hint nào; phần mềm phải xử lý các khả năng đó.

## 15. Tài liệu chính thức

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — mục **3.4.3 JMSMessageID**, **3.4.4 JMSTimestamp**, **3.4.5 JMSCorrelationID**, **3.4.9 JMSExpiration**, **3.4.13 JMSDeliveryTime** và **7.8 Message time-to-live**.
- [Jakarta Messaging — MessageProducer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer) — `setDisableMessageID`, `setDisableMessageTimestamp` và getters.
- [Jakarta Messaging — JMSProducer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmsproducer) — biến thể fluent qua JMSContext.
- [Jakarta Messaging — Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message) — ý nghĩa header và nguồn gán giá trị.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html) — `setMessageIdEnabled`, `setMessageTimestampEnabled`, QoS.
- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html) — template lifecycle và QoS.
- [Spring Boot 3.5 — JMS and Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html) — cấu hình Spring Boot.
- [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html) — broker demo.

**Tóm tắt:** Hai API tối ưu cho phép provider **bỏ qua việc sinh JMSMessageID/JMSTimestamp khi ứng dụng không phụ thuộc các header đó**. Spring dùng `messageIdEnabled=false` và `messageTimestampEnabled=false` để gửi hint. Hãy quyết định bằng yêu cầu tracing, request-reply, audit và benchmark trên broker thật, không dựa trên kỳ vọng rằng giảm header luôn tăng hiệu năng.
