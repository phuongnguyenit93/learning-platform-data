# JMSRedelivered, JMSXDeliveryCount và dấu vết phát lại trong JMS

## Mục tiêu học tập

Bài này tập trung vào **mô hình Message trong Jakarta Messaging (JMS)**, đặc biệt là hai dấu hiệu được JMS provider gắn vào message khi consumer nhận lại:

- **`JMSRedelivered`**: header kiểu boolean, truy cập qua `Message.getJMSRedelivered()`. Nó cho biết provider đánh dấu message đang được phát lại.
- **`JMSXDeliveryCount`**: property kiểu `int`, đọc bằng `Message.getIntProperty("JMSXDeliveryCount")`. Lần giao đầu có giá trị `1`, lần giao lại thông thường là `2`, `3`, ...
- **Dấu vết phát lại (redelivery trace)**: kết hợp hai tín hiệu trên với message ID, event/business ID, correlation ID, destination, thời điểm, consumer instance và kết quả xử lý để điều tra *vì sao cùng một message xuất hiện nhiều lần*.

Sau khi học, bạn có thể nhận diện redelivery; phân biệt delivery attempt với business processing attempt; hiểu các ranh giới về độ chính xác; cấu hình Spring JMS để lỗi thực sự dẫn đến rollback/redelivery; viết Java 17 đọc metadata; và xây cách logging, idempotency, retry, DLQ phù hợp.

> **Nguyên tắc:** `JMSRedelivered` và `JMSXDeliveryCount` là **thông tin chẩn đoán về giao nhận**, không phải bảo đảm rằng nghiệp vụ đã chạy bao nhiêu lần hay rằng không thể có xử lý trùng.

## 1. Redelivery là gì?

Một JMS message có thể được broker giao đến consumer nhưng **chưa được acknowledgement/commit thành công**. Nếu consumer rollback, session recover, kết nối bị đứt hoặc provider gặp sự cố trước khi việc nhận được xác nhận, message có thể được giao lại. Cùng một payload được nhìn thấy ở lần nhận mới, nhưng metadata phản ánh việc phát lại.

~~~text
Producer                 JMS broker                  Consumer
   │ send(OrderCreated)      │                           │
   ├─────────────────────────►│                           │
   │                          │ lần giao đầu               │
   │                          ├───────────────────────────►│
   │                          │ JMSRedelivered=false       │
   │                          │ JMSXDeliveryCount=1        │
   │                          │                            │ xử lý → lỗi/rollback
   │                          │◄───────────────────────────┤
   │                          │                            │
   │                          │ phát lại (redelivery)      │
   │                          ├───────────────────────────►│
   │                          │ JMSRedelivered=true        │
   │                          │ JMSXDeliveryCount=2        │
   │                          │                            │ xử lý → commit
   │                          │◄───────────────────────────┤
~~~

Đây là mô hình **điển hình** của một provider tuân thủ Jakarta Messaging. Thứ tự, thời gian chờ, số lần thử, việc chuyển message sang dead-letter queue (DLQ) và khả năng duy trì bộ đếm qua sự cố phụ thuộc provider và cấu hình broker.

### Ba khái niệm dễ bị trộn

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| **Delivery attempt** | Broker đã cố giao message này đến consumer bao nhiêu lần? | `JMSXDeliveryCount=3`: provider báo lần giao thứ ba. |
| **Processing attempt** | Code nghiệp vụ đã thật sự bắt đầu xử lý bao nhiêu lần? | Consumer có thể chết **trước** khi callback bắt đầu, dù đã có delivery. |
| **Business effect** | Giao dịch ngoài JMS đã thực sự xảy ra bao nhiêu lần? | DB có thể đã lưu đơn hàng một lần, dù callback được gọi hai lần. |

Ba số này không nhất thiết bằng nhau. Vì vậy **không** tính số lần thanh toán, gửi email hoặc ghi DB bằng `JMSXDeliveryCount`.

## 2. `JMSRedelivered`: header cảnh báo về khả năng nhận lại

### 2.1. Đọc trong Java

~~~java
// Đoạn mã bên trong method đã nhận jakarta.jms.Message.
boolean redelivered = message.getJMSRedelivered();
System.out.println("JMSRedelivered=" + redelivered);
~~~

`getJMSRedelivered()` trả về `boolean` và có thể ném `JMSException`. Đây là **JMS standard header**, không phải một property do ứng dụng tự đặt. Tên Java API là `getJMSRedelivered()` chứ không phải `getBooleanProperty("JMSRedelivered")`.

Khi producer gửi message, header này **không mang ý nghĩa ứng dụng**; provider thiết lập trạng thái liên quan đến redelivery khi giao message. Phương thức `setJMSRedelivered(boolean)` tồn tại trong interface để provider có thể thao tác với message implementation, **không** phải cách để producer khai báo hay điều khiển chính sách retry.

### 2.2. Ý nghĩa đúng của `true` và `false`

- `true`: provider cho biết message **có khả năng** đã từng được giao nhưng chưa được xác nhận. Specification dùng ngôn ngữ thận trọng: có khả năng, **không bảo đảm** code ứng dụng đã xử lý message lần trước.
- `false`: không được suy ra rằng *nghiệp vụ chắc chắn chưa từng chạy*. Producer có thể publish lại một sự kiện logic bằng message mới; dữ liệu có thể trùng từ nguồn; hoặc sự cố làm dấu vết delivery không phản ánh đầy đủ lịch sử.
- Trong trường hợp provider redeliver do session recovery hoặc lỗi hệ thống, JMS specification yêu cầu gắn redelivered flag và tăng delivery count theo các điều kiện quy định. Tuy vậy, bản thân flag chỉ là metadata từ broker.

Ví dụ: broker chuyển message đến consumer, nhưng JVM bị kill trước khi method listener chạy. Lần sau header `true`, mặc dù logic nghiệp vụ chưa từng bắt đầu. Ngược lại, producer tự gửi lần thứ hai cùng event ID thì đó là **JMS message mới** với flag có thể là `false`.

### 2.3. Header này không quyết định ACK

`JMSRedelivered` chỉ để **quan sát và giúp xử lý an toàn**. Không có nghĩa rằng message sẽ tự rollback hoặc tự chuyển DLQ. Việc ack/commit/rollback do session, listener container và broker policy quyết định.

Mẫu sai:

~~~java
// Sai: bỏ qua mọi message bị redeliver có thể làm mất nghiệp vụ.
if (message.getJMSRedelivered()) {
    return;
}
~~~

Nếu lần giao đầu chết trước khi lưu dữ liệu, lần hai là cơ hội để hoàn tất công việc. Thay vì bỏ qua dựa trên flag, hãy dùng **business idempotency key** cùng cơ chế ghi nhận đã xử lý vào kho dữ liệu bền vững.

## 3. `JMSXDeliveryCount`: số lần broker giao message

### 3.1. Đây là property chuẩn bắt buộc

Từ JMS 2.0 (và trong Jakarta Messaging 3.x), **provider phải đặt** `JMSXDeliveryCount` trên message khi consumer nhận. Nó là property `int` thuộc nhóm `JMSX...`, không phải header có getter chuyên dụng.

~~~java
// Đoạn trong method nhận jakarta.jms.Message.
int deliveryCount = message.getIntProperty("JMSXDeliveryCount");
System.out.println("deliveryCount=" + deliveryCount);
~~~

| Delivery count | Cách hiểu thông thường |
|---:|---|
| `1` | Provider đang giao message lần đầu. |
| `2` | Message được giao lại ít nhất một lần. |
| `3` | Message đang ở lần giao thứ ba theo bộ đếm provider. |
| `5` | Có lịch sử delivery lặp; cần xem retry, lỗi, DLQ và policy. |

**Ràng buộc theo specification:** nếu `JMSRedelivered=true` thì `JMSXDeliveryCount` phải **từ 2 trở lên**. Ngược lại, nếu metadata không thỏa ràng buộc đó, cần kiểm tra provider, phiên bản client, bridge hoặc dữ liệu kiểm thử.

### 3.2. Không có cam kết bộ đếm luôn chính xác tuyệt đối

Jakarta Messaging specification mục **3.5.11** nói rõ giá trị `JMSXDeliveryCount` **không được bảo đảm chính xác trong mọi tình huống**. Provider không bắt buộc persist bộ đếm đủ để bảo toàn nó qua mọi lần broker failure.

Hệ quả thực tế:

- `JMSXDeliveryCount=3` là thông tin chẩn đoán có ích, **không phải** chứng cứ kiểm toán tuyệt đối của ba lần chạy nghiệp vụ.
- Broker restart/failover, bridge hoặc chuyển DLQ/re-drive có thể khiến chuỗi quan sát không giống việc cộng `1` đều đặn trong mọi môi trường.
- Bộ đếm đo số lần **delivery** theo provider, không phân biệt consumer đã đọc header, chạy được logic hay commit side effect.
- Không xây **logic khấu trừ tiền, giới hạn số lần thực hiện nghiệp vụ, hoặc đúng-một-lần** chỉ bằng delivery count.

### 3.3. Không lọc bằng JMS selector trên property đặt lúc nhận

`JMSXDeliveryCount` được provider gắn **khi receive**; specification nêu rằng tác dụng của message selector trên property do provider thiết lập khi nhận là **undefined**. Vì vậy đừng thiết kế consumer chỉ nhận message bằng:

~~~sql
JMSXDeliveryCount > 3
~~~

Đây chỉ là **ví dụ selector không nên sử dụng**, không phải câu SQL để chạy. Thay vào đó: đọc delivery count **bên trong consumer**, dùng broker retry/DLQ policy để điều khiển số lần thử, và giám sát bằng logging/metrics.

### 3.4. Không tự đặt lại bằng `setIntProperty`

Không dùng producer để gán `JMSXDeliveryCount` như một application property thay thế bộ đếm provider. Chỉ provider mới có quyền quyết định giá trị chuẩn tại điểm nhận; producer muốn mang số lần retry ở **tầng nghiệp vụ** nên dùng property khác, chẳng hạn `appAttempt`, và làm rõ nó có nghĩa gì. Không đặt property mang tên bắt đầu `JMSX` cho mục đích riêng vì prefix được chuẩn JMS dành riêng.

## 4. Phân biệt header/property để đọc dấu vết chính xác

| Trường | Loại | Cách truy cập từ `jakarta.jms.Message` | Dùng để làm gì? |
|---|---|---|---|
| `JMSRedelivered` | Standard header, boolean | `getJMSRedelivered()` | Biết provider đánh dấu lần giao lại. |
| `JMSXDeliveryCount` | Standard provider property, int | `getIntProperty("JMSXDeliveryCount")` | Theo dõi delivery attempts theo broker. |
| `JMSMessageID` | Standard header, String | `getJMSMessageID()` | Phân biệt/đối chiếu message vật lý do provider gán. |
| `JMSCorrelationID` | Standard header, String | `getJMSCorrelationID()` | Nối request/response hoặc các bước workflow nếu ứng dụng gán. |
| `JMSTimestamp` | Standard header, long | `getJMSTimestamp()` | Timestamp liên quan lúc provider gửi message; **không phải** lúc retry gần nhất. |
| `JMSDestination` | Standard header, Destination | `getJMSDestination()` | Ghi nhận destination nhận/gửi. |
| `JMSExpiration` | Standard header, long | `getJMSExpiration()` | Thời điểm expiration theo TTL; `0` thường biểu thị không hết hạn. |
| `eventId` | App property, String | `getStringProperty("eventId")` | Định danh **sự kiện nghiệp vụ**, dùng cho idempotency. |
| `traceparent` | App property, String | `getStringProperty("traceparent")` | Chuyển trace context giữa service khi triển khai observability. |

Một JMS message có **header**, **properties** và **body**. `JMSRedelivered` thuộc header; `JMSXDeliveryCount` thuộc properties; `eventId` là tên do ứng dụng chọn. Trong Spring, bạn có thể truy cập metadata qua raw `jakarta.jms.Message` hoặc map sang Spring message headers, nhưng phải xác định rõ tên namespace.

### 4.1. `JMSMessageID` và `eventId` có vai trò khác nhau

Giả sử producer phát một nghiệp vụ `OrderCreated(order-84)`. JMS provider sinh `JMSMessageID=ID:abc`. Nếu broker giao lại **cùng JMS message**, ID thông thường vẫn dùng để nhận diện cùng message. Nếu producer gửi lại *một message mới* vì không chắc send trước đã thành công, provider có thể cấp `ID:def` dù event logic vẫn là `order-84`.

~~~text
A. Redelivery do rollback:
   first  → JMSMessageID=ID:abc, eventId=evt-84, count=1
   retry  → JMSMessageID=ID:abc, eventId=evt-84, count=2

B. Producer gửi trùng event logic:
   send 1 → JMSMessageID=ID:abc, eventId=evt-84, count=1
   send 2 → JMSMessageID=ID:def, eventId=evt-84, count=1
~~~

ID ở sơ đồ chỉ minh họa; định dạng thật tùy JMS provider. Khi message bị bridge, forward tới DLQ rồi re-drive hoặc tái tạo message, ID/header có thể thay đổi theo implementation. **Dùng `eventId` bền vững** (hoặc business key duy nhất có quy tắc rõ) cho dedup nghiệp vụ; dùng `JMSMessageID` để đối soát JMS delivery và broker log.

### 4.2. Correlation ID và trace ID không phải attempt counter

`JMSCorrelationID` thường được client đặt để nối request với response hoặc các message trong một quy trình, không phải bộ đếm giao lại. Với distributed tracing, `traceparent`/trace ID nối các span giữa service; redelivery có thể tạo **consumer span mới**, trong khi eventId vẫn giữ nguyên. Bảo tồn trace context khi gửi event giúp điều tra chuỗi sự kiện; đừng dùng correlation ID thay thế tính duy nhất của event nếu một workflow có nhiều event cùng correlation ID.

## 5. Khi nào metadata thay đổi?

### 5.1. Consumer rollback trong transacted Session

~~~text
Queue ─► consumer nhận M (count=1, redelivered=false)
                 │
                 ▼
              xử lý lỗi
                 │
            session.rollback()
                 │
                 ▼
       broker chuẩn bị giao lại M
                 │
                 ▼
       consumer nhận M (count=2, redelivered=true)
                 │
                 ▼
            session.commit()
~~~

Trong session được bật local transaction, `commit()` hoàn tất việc nhận theo transaction và `rollback()` yêu cầu đảo nhận và giao lại theo chính sách provider. Trong Spring `DefaultMessageListenerContainer`, `sessionTransacted=true` cho phép ném exception từ listener để container rollback; **không** cần gọi `session.rollback()` thủ công trong method `@JmsListener` thông thường.

### 5.2. `CLIENT_ACKNOWLEDGE` và `Session.recover()`

Với session **không transacted** ở mode `CLIENT_ACKNOWLEDGE`, client gọi `message.acknowledge()` để xác nhận. Một lời gọi ack theo chuẩn JMS sẽ xác nhận **tất cả message đã giao bởi session đó**, không chỉ message đang gọi.

Nếu cần yêu cầu giao lại các message chưa ack trong session này, ứng dụng có thể gọi `session.recover()`; specification yêu cầu đánh dấu `JMSRedelivered` và tăng `JMSXDeliveryCount` cho các message được giao lại vì recovery.

**Lưu ý:** `recover()` là thao tác session, không phải `rollback()` trong local transacted session. Đừng ack message trước rồi mới mong `recover()` khiến message đã được xác nhận quay về.

### 5.3. Connection failure hoặc consumer chết

Nếu consumer đã nhận M nhưng không ack/commit, broker có thể giao lại M cho consumer mới khi connection/session phục hồi. Lần giao trước **có thể** chưa từng gọi được listener. Nếu DB đã commit rồi mà JMS ack chưa commit, listener mới có thể xử lý trùng side effect. Đó là lý do cần idempotency.

### 5.4. `AUTO_ACKNOWLEDGE` và `DUPS_OK_ACKNOWLEDGE`

- `AUTO_ACKNOWLEDGE`: thời điểm acknowledgement do JMS API/provider quyết định theo cách nhận message. Trong nhận đồng bộ, việc receive thành công dẫn đến auto ack; trong callback JMS thuần, việc hoàn tất callback liên quan đến ack. Nó không cho phép ứng dụng tùy ý rollback bằng cách ném exception khi đang ở một Spring container.
- `DUPS_OK_ACKNOWLEDGE`: cho phép ack trì hoãn; có thể nhận trùng trong điều kiện failure. Cần hiểu semantics và provider trước khi chọn.
- **Spring đặc biệt quan trọng:** `DefaultMessageListenerContainer` với cấu hình mặc định `AUTO_ACKNOWLEDGE` thực hiện auto ack trước khi chạy listener; nếu method listener ném exception, **không có redelivery chỉ vì exception đó**. Muốn thử và vận hành redelivery có kiểm soát, hãy dùng transacted session hoặc transaction manager phù hợp.

| Sự kiện | Có thể redeliver? | Dấu vết dự kiến |
|---|---|---|
| `session.rollback()` trên JMS transacted session | Có, tùy hạn mức retry và policy | Lần sau `JMSRedelivered=true`, count tăng. |
| `session.recover()` sau giao chưa ack trên session không transacted | Có | Flag true, count tăng cho message được giao lại. |
| JVM/network chết trước khi ack/commit | Có | Cần kiểm tra message ID, count, consumer instance; số đếm có thể không chính xác sau failure. |
| Listener ném exception trong Spring container có `sessionTransacted=true` | Có | Container rollback, provider áp dụng redelivery policy. |
| Listener ném exception trong Spring `DefaultMessageListenerContainer` mặc định AUTO_ACK | Không dựa vào exception đó | Message có thể đã ack trước khi xử lý. |
| Producer gửi một message mới trùng payload | Đây **không phải** redelivery của cùng JMS message | `JMSMessageID` mới, count thường bắt đầu lại từ 1. |
| Consumer nhận và commit thành công | Không redeliver cùng message do retry thông thường | Không nên thấy lần giao lại nếu ack đã xác nhận. |

## 6. Những tình huống không được diễn giải sai

### 6.1. `JMSRedelivered=true` không chắc nghiệp vụ đã chạy

Broker có thể gửi message vào socket rồi connection chết trước khi callback bắt đầu. Lần sau được ghi nhận là redelivery, nhưng nghiệp vụ **chưa từng thực hiện**. Không bỏ qua M vì flag true.

### 6.2. `JMSRedelivered=false` không chắc nghiệp vụ là lần đầu

Một message logic có thể được publish trùng từ phía producer, HTTP retry, outbox relay hay hệ thống upstream. Mỗi JMS message mới đều có thể có count=1 dù `eventId` trùng nhau. Idempotency phải dựa vào event/business ID ổn định.

### 6.3. Count tăng không chứng minh lỗi nằm trong business handler

Message có thể bị rollback do database timeout, exception từ message converter, timeout của transaction, container shutdown hoặc lỗi hạ tầng. Log phải tách được thời điểm **received**, **processing_started**, **processing_failed**, **rollback**, **commit** nếu các sự kiện này được tầng ứng dụng quan sát. Không tự gán nhãn nguyên nhân chỉ từ count.

### 6.4. Count không luôn tăng mãi

Khi broker chuyển message sang DLQ, một quản trị viên re-drive, hoặc consumer dùng bridge/forward tạo JMS message khác, count có thể reset hoặc metadata thay đổi theo broker. Không thể coi `JMSXDeliveryCount` là số lần thử xuyên suốt mọi queue và broker.

### 6.5. Không dùng `JMSRedelivered` như điều kiện “chỉ xử lý khi false”

Dạng code dưới đây nguy hiểm:

~~~java
// Anti-pattern. Nếu lần đầu đã rollback trước khi hoàn tất,
// message bị bỏ qua vĩnh viễn ở lần giao sau.
if (!message.getJMSRedelivered()) {
    chargeCreditCard();
}
~~~

Lỗi vẫn tồn tại nếu thay flag bằng `JMSXDeliveryCount == 1`. Để bảo đảm charge không lặp, cần idempotency key do nghiệp vụ định nghĩa và cơ chế lưu trạng thái bền vững.

## 7. Lưu dấu vết redelivery bằng Java

### 7.1. Đọc metadata trong Spring `@JmsListener`

Spring Framework cho phép tham số là raw `jakarta.jms.Message`/`TextMessage` trong method `@JmsListener`. Nhờ đó mã có thể đọc đúng các field gốc:

~~~java
// Đoạn trong một bean đã cấu hình Spring JMS.
@JmsListener(destination = "orders.queue")
public void handle(TextMessage message) throws JMSException {
    boolean redelivered = message.getJMSRedelivered();
    int deliveryCount = message.getIntProperty("JMSXDeliveryCount");

    String jmsMessageId = message.getJMSMessageID();
    String correlationId = message.getJMSCorrelationID();
    String eventId = message.getStringProperty("eventId");
    String payload = message.getText();

    // Log structured metadata; không log payload nhạy cảm lên production log.
    log.info("jms_received eventId={} jmsMessageId={} correlationId={} "
                    + "redelivered={} deliveryCount={}",
            eventId, jmsMessageId, correlationId,
            redelivered, deliveryCount);

    process(payload, eventId); // Tầng nghiệp vụ cần idempotency.
}
~~~

**Đây là snippet, không phải lớp Java độc lập:** giả định đã có logger `log`, import `TextMessage`/`JMSException`, và hàm `process(...)`. Ở môi trường thực tế, nếu `process` ném exception, việc broker có giao lại hay không **phụ thuộc listener container/transaction configuration**, không chỉ annotation.

### 7.2. Nên log gì?

Một bản ghi cho **mỗi lần nhận** có thể gồm:

| Field log | Nguồn | Ý nghĩa điều tra |
|---|---|---|
| `eventId` / `businessKey` | Property/header do ứng dụng gán | Nhóm các lần thử cùng một sự kiện logic. |
| `jmsMessageId` | `getJMSMessageID()` | Phân biệt các JMS message thực tế. |
| `jmsCorrelationId` | `getJMSCorrelationID()` | Theo dấu một flow/request. |
| `jmsRedelivered` | `getJMSRedelivered()` | Provider đánh dấu redelivery. |
| `jmsDeliveryCount` | `getIntProperty("JMSXDeliveryCount")` | Quan sát số lần delivery. |
| `destination` | `getJMSDestination()` hoặc cấu hình listener | Queue/topic đang được xử lý. |
| `service`, `instanceId`, `consumerName` | Cấu hình service | Consumer nào nhận message. |
| `receivedAt`, `processingMs`, `outcome` | Application log | Thời điểm, độ trễ, kết quả xử lý. |
| `exceptionType` / `errorCode` | Error handling | Chẩn đoán nguyên nhân thất bại, không lộ bí mật. |
| `traceId` / `spanId` | Observability context | Nối consumer attempt với trace liên dịch vụ. |

Ví dụ structured log minh họa (các ID được đặt mẫu có chủ đích):

~~~json
{
  "event": "jms_message_received",
  "service": "billing-worker",
  "instanceId": "billing-02",
  "eventId": "evt-84",
  "jmsMessageId": "ID:abc",
  "jmsCorrelationId": "order-84",
  "destination": "billing.queue",
  "jmsRedelivered": true,
  "jmsDeliveryCount": 2,
  "receivedAt": "2026-10-30T01:15:20Z"
}
~~~

Ở lần giao tiếp theo, bổ sung log `processing_completed` hoặc `processing_failed` với **cùng eventId, messageId và attempt**, kèm thời gian xử lý. Đừng ghi toàn bộ payload chứa PII, bearer token, secret hay dữ liệu thanh toán chỉ để debug.

### 7.3. Các dấu vết khi không thấy event trong log

Thiếu log không chứng minh broker chưa delivery: connection có thể hỏng trước callback, app log có thể mất khi process chết, hoặc listener bị lỗi ở khâu conversion trước khi vào method. Dùng thêm broker metrics, DLQ count, container error handler, transaction logs và tracing để khép vòng điều tra.

## 8. Demo chạy được với Java 17, Spring Boot và ActiveMQ Artemis

Demo chủ động tạo **một lỗi xử lý ở lần nhận đầu**, để JMS transaction rollback. Khi broker giao lại, listener đọc `JMSRedelivered=true` và `JMSXDeliveryCount=2` rồi hoàn tất. Đây là minh họa local có kiểm soát, không mô phỏng mọi chính sách retry/HA trên production.

### 8.1. Chuẩn bị broker cục bộ

Cần **Docker**, **JDK 17+** và **Maven 3.9+**. Mở terminal, khởi chạy broker chính thức:

~~~bash
docker run --detach --rm --name jms-redelivery-demo \
  -p 61616:61616 -p 8161:8161 apache/artemis:latest-alpine
~~~

Ảnh container Artemis mặc định tạo user/password `artemis` và bật nhận message ở cổng `61616`. Đợi broker khởi động hoàn tất; dashboard thường ở `http://localhost:8161`. Đảm bảo không có broker khác dùng port này. Thử nghiệm trên broker rỗng; không tái sử dụng queue production.

Cấu trúc dự án:

~~~text
redelivery-demo/
├── pom.xml
└── src/main/
    ├── java/example/RedeliveryDemoApplication.java
    └── resources/application.properties
~~~

### 8.2. `pom.xml`

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
  <artifactId>redelivery-demo</artifactId>
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

### 8.3. `application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

Chỉ dùng credentials ví dụ cho máy học cục bộ; production phải lấy từ secret manager và bật TLS/quyền phù hợp.

### 8.4. `src/main/java/example/RedeliveryDemoApplication.java`

~~~java
package example;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.CommandLineRunner;
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
public class RedeliveryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RedeliveryDemoApplication.class, args);
    }

    @Bean
    DefaultJmsListenerContainerFactory redeliveryFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    CommandLineRunner publishOneMessage(JmsTemplate jmsTemplate) {
        return args -> jmsTemplate.send("lesson.redelivery.demo", session -> {
            TextMessage message = session.createTextMessage("order-42");
            message.setStringProperty("eventId", "evt-42");
            message.setJMSCorrelationID("order-42");
            return message;
        });
    }
}

@Component
class RedeliveryListener {

    // CHỈ DÙNG ĐỂ DEMO: không sử dụng biến trong RAM làm
    // cơ chế chống trùng / retry state trong production.
    private final AtomicBoolean failOnce = new AtomicBoolean(true);

    @JmsListener(destination = "lesson.redelivery.demo",
                 containerFactory = "redeliveryFactory")
    public void onMessage(TextMessage message) throws JMSException {
        String eventId = message.getStringProperty("eventId");
        boolean redelivered = message.getJMSRedelivered();
        int count = message.getIntProperty("JMSXDeliveryCount");

        System.out.printf(
                "received eventId=%s redelivered=%b deliveryCount=%d%n",
                eventId, redelivered, count);

        // Broker/provider đã gán ID. Đọc để liên hệ với broker log:
        String jmsId = message.getJMSMessageID();
        if (jmsId == null) {
            throw new IllegalStateException("JMSMessageID absent");
        }

        // Một lỗi cố ý duy nhất trong process đang chạy.
        if (failOnce.compareAndSet(true, false)) {
            throw new IllegalStateException("Simulated first-attempt failure");
        }

        System.out.println("processed eventId=" + eventId);
        // Method thành công -> container commit JMS local transaction.
    }
}
~~~

Đây là một **file Java duy nhất** có một public class và một package-private component; tên file phải trùng `RedeliveryDemoApplication.java`. Spring Boot tự cấu hình `JmsTemplate` và `ConnectionFactory` từ starter, còn `redeliveryFactory` quản lý listener session. Broker Artemis mặc định thường có auto-create address/queue; nếu tổ chức tắt auto-create, cần tạo trước `lesson.redelivery.demo`.

### 8.5. Chạy và kiểm tra

~~~bash
mvn spring-boot:run
~~~

Với queue rỗng, chỉ một instance demo chạy, broker khỏe, policy mặc định cho phép redelivery và không có message cũ, **ba dòng do code demo in ra** thường là:

~~~text
received eventId=evt-42 redelivered=false deliveryCount=1
received eventId=evt-42 redelivered=true deliveryCount=2
processed eventId=evt-42
~~~

Console còn có Spring/Artemis startup logs và stack trace của lần lỗi cố ý. Đây là kết quả kỳ vọng trong điều kiện demo; **không khẳng định stdout toàn tiến trình chỉ có ba dòng đó**. Khi broker áp dụng redelivery delay, dòng thứ hai có thể xuất hiện muộn hơn.

**Vì sao có lần giao lại?**

1. `publishOneMessage` dùng `JmsTemplate.send` để tạo một `TextMessage` và gắn `eventId`/`JMSCorrelationID`.
2. Listener đọc header/property ngay lúc message đến. `failOnce` từ `true` sang `false` và cố tình ném exception ở lần đầu.
3. `DefaultJmsListenerContainerFactory.setSessionTransacted(true)` khiến lỗi listener dẫn đến **rollback JMS transaction**, nên broker có thể phát lại message.
4. Ở lần nhận sau, provider gắn redelivery metadata; method không ném exception nữa, in dòng `processed` rồi container commit.
5. Một JVM restart giữa hai lượt sẽ đặt lại `failOnce=true`; ví dụ này dùng RAM chỉ để minh họa, **không phải** retry/idempotency production.

Đừng đổi ví dụ sang `AUTO_ACKNOWLEDGE` mặc định rồi kỳ vọng exception tự tạo redelivery: Spring `DefaultMessageListenerContainer` có semantics auto ack khác transacted listener.

Dừng ứng dụng bằng `Ctrl+C`, rồi dừng broker:

~~~bash
docker stop jms-redelivery-demo
~~~

## 9. Xây xử lý idempotent thay vì dựa vào hai flag

### 9.1. Cửa sổ lỗi phổ biến

~~~text
Consumer nhận M
    │
    ▼
Ghi DB thành công (DB COMMIT)
    │
    ▼
JVM chết trước JMS COMMIT
    │
    ▼
Broker redeliver M
    │
    ▼
Nếu không có dedup → ghi DB/gửi lệnh ngoài lần nữa!
~~~

Session transaction JMS và transaction database **không tự động là một transaction phân tán**. Chỉ dựa vào `JMSRedelivered` hoặc count không giải quyết được cửa sổ lỗi này.

### 9.2. Mẫu xử lý idempotency key với DB

Giả sử producer gắn `eventId` ổn định và ứng dụng có bảng `processed_events(event_id)` với **unique constraint**. Trong **cùng DB transaction** với business update:

~~~sql
BEGIN;

INSERT INTO processed_events(event_id)
VALUES ('evt-42')
ON CONFLICT (event_id) DO NOTHING;

-- Chỉ khi INSERT thực sự thêm 1 dòng, mới thực hiện business update
-- trong cùng transaction DB này.
UPDATE orders
SET status = 'PROCESSED'
WHERE order_id = 'order-42';

COMMIT;
~~~

**Lưu ý về mẫu SQL:** `ON CONFLICT` là cú pháp PostgreSQL; comments mô tả nhánh chương trình. Code thực tế phải kiểm tra số dòng được INSERT: **nếu INSERT bị conflict thì phải bỏ qua UPDATE**, còn nếu INSERT thành công thì UPDATE trong **cùng transaction DB**. Bảng và status ở đây là ví dụ; không sao chép hai lệnh SQL rồi chạy mù mà thiếu điều kiện nhánh.

Khi nhận lại cùng `eventId`, consumer phát hiện đã xử lý, kết thúc thành công để JMS commit. Nếu DB transaction rollback trước khi thành công, bản ghi dedup cũng rollback, lần redelivery kế tiếp vẫn có thể xử lý.

Nếu business effect là gọi payment gateway hoặc gửi email ngoài DB, unique constraint trong DB **không tự đảm bảo** ngoại tác đúng một lần. Cần idempotency token được dịch vụ đích hỗ trợ hoặc trạng thái saga/outbox nhất quán.

### 9.3. Đừng dùng `JMSMessageID` làm business dedup duy nhất

Message ID thường đủ để nhận ra việc broker giao **lại cùng một JMS message**, nhưng producer có thể publish duplicate logic với **message ID mới**. Dùng `eventId`/business key ổn định để bảo vệ nghiệp vụ, và lưu JMSMessageID bên cạnh làm trace kỹ thuật. Nếu producer chỉ gắn `JMSCorrelationID`, phải kiểm tra correlation đó có thực sự duy nhất theo từng event hay không.

### 9.4. Mẫu quyết định cho listener

~~~text
Nhận message
  │
  ├─ Log JMSMessageID, eventId, JMSRedelivered, JMSXDeliveryCount
  │
  ├─ Xác thực schema + business key
  │
  ├─ DB transaction:
  │    ├─ eventId đã xử lý? ──► bỏ qua business effect
  │    └─ chưa xử lý ────────► ghi dedup + business changes, commit DB
  │
  ├─ Hoàn tất listener → JMS commit
  │
  └─ Nếu thất bại trước JMS commit:
       rollback JMS → redelivery theo broker policy → thử lại an toàn
~~~

Nếu lỗi dữ liệu không thể sửa bằng retry (schema sai, ID không hợp lệ, permanent authorization error), nên quarantine/DLQ có kiểm soát, không retry vô hạn.

## 10. Retry và DLQ: vai trò của broker

JMS định nghĩa cách nhận, ack và transaction; **không chuẩn hóa** một bộ API chung cho mọi broker để cài toàn bộ retry delay, exponential backoff, max attempts, dead-letter address và replay UI. Ví dụ ActiveMQ Artemis có **redelivery delay**, **max-delivery-attempts** và **dead-letter-address** trong address settings; broker khác đặt tên/cơ chế khác.

Các câu hỏi phải trả lời khi thiết kế:

1. Bao nhiêu lần thử? Bao gồm lần giao đầu hay chỉ những lần phát lại? Đọc rõ semantics policy của broker.
2. Delay/backoff thế nào? Có jitter, tránh thundering herd hoặc lặp nhanh làm nghẽn DB không?
3. Khi lỗi vĩnh viễn, message đi đâu? DLQ có retention, quyền đọc, alert, lý do lỗi và công cụ re-drive chưa?
4. Khi re-drive có giữ `eventId`/correlationId không? JMSMessageID và JMSXDeliveryCount có bị thay đổi/reset theo broker không?
5. Consumer có khả năng idempotent không? Nếu không, re-drive thủ công có thể tái thực hiện tác động nghiệp vụ.
6. Khi `JMSXDeliveryCount` bất thường cao, có metrics/alert nhưng vẫn có policy broker độc lập để cắt retry loop không?

**Không xây retry server-side bằng việc người dùng tự `send()` lại một message mới trong `catch` mà không hiểu hệ quả:** thao tác này có thể tạo message ID mới, tăng số bản logic, biến count về 1 và làm mất dấu vết redelivery gốc.

### Quy tắc thực hành

- **Transient error:** thường cho rollback, redelivery có delay/backoff.
- **Permanent/poison message:** chuyển DLQ/quarantine, lưu error reason, hỗ trợ điều tra và re-drive sau khi sửa.
- **Side effect đã xảy ra:** dựa vào idempotency status, không chạy lại chỉ vì provider báo count=2.
- **Broker crash/failover:** quan sát bằng nhiều tín hiệu; chấp nhận khả năng delivery count không tuyệt đối đúng.

## 11. Điều tra sự cố từ log thực tế

### Tình huống A — count tăng từ 1 → 2 → 3, lỗi luôn là DB timeout

Khả năng: consumer rollback nhiều lần do dependency chậm. Kiểm tra timeout, connection pool, transaction, broker redelivery delay; tránh retry dồn dập. `JMSRedelivered=true` xác nhận trạng thái broker, nhưng không nói nguyên nhân DB timeout trừ khi có error log/trace.

### Tình huống B — count=1 ở cả hai lần, nhưng `eventId` giống nhau

Khả năng: **hai JMS message khác nhau** cùng thể hiện một event. So `JMSMessageID`: nếu khác ID, kiểm tra upstream producer retry, outbox relay, gửi trùng bởi scheduler/HTTP request. Nếu cùng ID mà metadata lạ, xem broker failover/bridge và client version. Bất kể nguyên nhân, idempotency cần bắt trùng theo event ID.

### Tình huống C — redelivered=true, count=2 nhưng không thấy log lần đầu

Có thể message đã được broker giao trước khi listener log; app chết, exception xảy ra ở converter, log mất hoặc message được consumer instance khác nhận. Tra cứu broker consumer/connection events, instance ID, startup/shutdown thời điểm đó và error logs. Không kết luận chắc chắn "đã xử lý một lần".

### Tình huống D — listener ném exception nhưng message biến mất khỏi queue

Kiểm tra Spring listener container **đang AUTO_ACK hay transacted**, có swallow exception/catch rồi return không, broker đã ack hoặc message vào DLQ chưa. Với Spring `DefaultMessageListenerContainer` mặc định AUTO_ACK, exception không mặc nhiên gây redelivery.

### Tình huống E — count=7, DLQ vẫn chưa nhận message

Kiểm tra cấu hình broker: max-delivery-attempts có thể lớn hơn 7, DLQ chưa được cấu hình, retry chưa kết thúc hoặc message đang ở queue khác. `JMSXDeliveryCount` không phải lệnh buộc chuyển DLQ; DLQ là policy broker.

### Tình huống F — payload giống hệt, message ID khác

Đây có thể là retry ở **tầng publish** (hai send) thay vì JMS redelivery. Phân biệt bằng eventId, JMSMessageID, producer logs và outbox record. Đừng dùng `JMSRedelivered` để đếm các lần upstream publish trùng.

## 12. Các anti-pattern thường gặp

| Anti-pattern | Vì sao nguy hiểm? | Cách sửa |
|---|---|---|
| `if (message.getJMSRedelivered()) return;` | Có thể bỏ mất message chưa xử lý lần đầu. | Dùng durable idempotency store. |
| `if (count >= 3) acknowledge();` | Ack có thể đánh dấu đã xong dù nghiệp vụ chưa thành công; count không hoàn toàn đáng tin. | Broker retry/DLQ policy và xử lý lỗi phân loại. |
| `getBooleanProperty("JMSRedelivered")` | Nhầm header với property chuẩn. | Dùng `getJMSRedelivered()`. |
| `getJMSXDeliveryCount()` | JMS `Message` không có getter chuyên dụng này. | Dùng `getIntProperty("JMSXDeliveryCount")`. |
| Giả định count=1 chắc chắn chưa từng có side effect | Producer có thể gửi duplicate event mới. | Dùng event ID/unique constraint. |
| Gửi lại bản copy message trong mọi `catch` | Có thể tạo message mới, đổi ID/reset counter, nhân duplicate. | Rollback transaction để broker redeliver. |
| Chỉ log payload và stack trace | Không đối chiếu được các attempts, dễ lộ dữ liệu. | Log structured IDs, count, flag, consumer instance và outcome. |
| Tạo selector `JMSXDeliveryCount > 3` | Tác dụng của selector với provider-on-receive property là undefined. | Đọc count khi nhận, dùng broker max attempts. |
| Catch exception rồi luôn return success | Listener container có thể commit, mất cơ hội redelivery. | Chỉ nuốt lỗi khi đã xử lý/đưa vào quarantine có bảo đảm. |
| Dùng biến `AtomicBoolean` trong RAM để chống trùng production | Mất trạng thái khi restart/scale sang instance khác. | DB dedup transaction hoặc idempotency service bền vững. |

## 13. Checklist dành cho Spring JMS production

- **Nhận message:** dùng raw `jakarta.jms.Message` hoặc mapped headers khi cần trace; luôn kiểm tra tương thích `jakarta.jms` với phiên bản Spring Boot/Framework.
- **Message identity:** producer tạo `eventId` bền vững và gắn correlation ID nếu có workflow liên quan; broker tự gán JMSMessageID.
- **Thông tin nhận:** log `JMSRedelivered` và `JMSXDeliveryCount` cùng messageId, eventId, destination, consumer instance, timestamp và trace ID.
- **Transaction:** xác định rõ listener container `sessionTransacted`, acknowledgement mode và DB transaction manager. Test fail trước và sau DB commit.
- **Idempotency:** unique key đủ phạm vi (tenant + eventId nếu hệ thống multi-tenant) và business changes nằm cùng DB transaction khi có thể.
- **Policy:** bật retry delay/backoff hợp lý, max attempts, DLQ, retention và alert; xác định cách re-drive không tạo trùng tác động.
- **Observability:** đo số message được nhận, số lần redelivery, failure/rollback, DLQ depth, processing latency, consumer backlog; không phụ thuộc mỗi count.
- **Diễn tập:** chạy lần nhận đầu lỗi, broker restart, consumer crash và producer double-send để thấy sự khác nhau của flag, count, messageId và eventId.

## 14. Câu hỏi tự kiểm tra

**1. `JMSRedelivered=true` có chứng minh business handler từng chạy không?** Không. Provider có thể đã giao message nhưng consumer chết trước khi code chạy.

**2. `JMSXDeliveryCount=2` được đọc ở đâu?** Từ `Message.getIntProperty("JMSXDeliveryCount")` trên message nhận vào, không phải setter hoặc một JMS header getter riêng.

**3. `JMSXDeliveryCount` có bắt buộc với Jakarta Messaging 3.x không?** Có. Từ JMS 2.0 provider phải gắn property kiểu `int` lúc nhận. Tuy nhiên spec không bảo đảm số đếm chính xác tuyệt đối sau mọi failure.

**4. `JMSRedelivered=true` mà count=1 có hợp chuẩn không?** Không đúng ràng buộc 3.5.11 của Jakarta Messaging, vì flag true yêu cầu count từ 2 trở lên. Kiểm tra provider/client/bridge.

**5. Producer gửi hai JMS message khác nhau nhưng cùng `eventId`, cả hai có thể có count=1 không?** Có. Đây là duplicate ở tầng logical event/producer, không nhất thiết là broker redelivery.

**6. Khi Spring `DefaultMessageListenerContainer` ở AUTO_ACK mặc định, listener ném lỗi có chắc broker gửi lại không?** Không. Container có thể ack trước khi gọi listener. Cần session transacted/transaction manager phù hợp để có rollback/redelivery.

**7. Vì sao không dùng selector `JMSXDeliveryCount > 5`?** Vì property này do provider gắn khi nhận; JMS specification nói tác dụng của selector trên provider-on-receive property là undefined.

**8. Count=3 có đồng nghĩa thanh toán đã bị trừ tiền ba lần?** Không. Nó nói về delivery attempt theo broker, không phải số lần business effect commit thành công.

**9. Làm sao điều tra cùng payload được nhận hai lần?** Đối chiếu JMSMessageID, eventId, JMSRedelivered, delivery count, producer logs, consumer instance, transaction outcomes và broker events.

**10. Cơ chế nào bảo vệ kết quả nghiệp vụ dù DB commit rồi JMS rollback?** Idempotency key bền vững, unique constraint/transaction cho những side effect trong DB; với side effect ngoài DB cần thêm idempotency/transactional outbox/saga tùy tình huống.

## 15. Tài liệu chính thức

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `3.4.7 JMSRedelivered`, `3.5.9 Jakarta Messaging-defined properties`, `3.5.11 JMSXDeliveryCount`, `6.2.10 Message acknowledgement`, `6.2.11 Duplicate delivery of messages`. Đây là nguồn quy chuẩn cho ý nghĩa và giới hạn của hai tín hiệu.
- [Jakarta Messaging 3.1 API: Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): getter header và property, `acknowledge()`, `JMSMessageID`/`JMSCorrelationID`.
- [Spring Framework: Annotation-driven listener endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): raw `jakarta.jms.Message`, tham số listener và mapped headers.
- [Spring Framework: Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): listener container và JMS transaction/rollback.
- [Spring Framework: Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate` và quy tắc cấu hình listener/transaction.
- [Spring Boot: JMS and ActiveMQ Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): `spring-boot-starter-artemis` và `spring.artemis.*`.
- [Apache Artemis: Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): broker container chính thức dùng trong ví dụ.
- [Apache Artemis: Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): redelivery, dead-letter và cấu hình queue/address theo broker.

**Ghi nhớ:** `JMSRedelivered` cho một **tín hiệu boolean**; `JMSXDeliveryCount` cho một **ước lượng số lượt delivery** do provider báo. Muốn tìm được *chính xác nguồn gốc trùng lặp và ngăn tác động nghiệp vụ lặp*, cần lưu **eventId/business key ổn định**, quan sát **messageId, correlationId, attempt/outcome** và phối hợp **transaction, idempotency, retry, DLQ**.
