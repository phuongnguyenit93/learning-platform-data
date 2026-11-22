# JMSDestination, JMSType, JMSTimestamp và các header do provider quản lý

> **Chương:** Thiết kế thông điệp  
> **Phạm vi:** Hợp đồng header của Jakarta/Java Message Service (JMS) khi ứng dụng Java gửi và nhận message qua Apache ActiveMQ Classic hoặc Artemis. Bài tập trung vào thời điểm header được gán, bên chịu trách nhiệm gán, ý nghĩa khi quan sát và các sai lầm trong thiết kế. Mã chính dùng **ActiveMQ Classic 5.x + `javax.jms` (JMS 1.1)**; các trường bổ sung của JMS 2.0/Jakarta Messaging được chỉ rõ riêng.

## 1. Tình huống: cùng một message, thông tin nào đáng tin ở tầng nào?

Dịch vụ Order tạo sự kiện `OrderCreated` lúc 10:00:00, đưa nó vào queue lúc 10:00:05; worker Billing nhận lúc 10:00:09. Ở tầng nghiệp vụ, chúng ta muốn biết:

- **Message được gửi đến đích nào?** Đọc `JMSDestination`.
- **Đây là loại sự kiện nghiệp vụ nào?** Có thể dùng `JMSType` do ứng dụng đặt, hoặc property/schema riêng của sự kiện.
- **Lúc nào message được đưa cho JMS provider để gửi?** Đọc `JMSTimestamp`.
- **Lần gửi này được broker định danh ra sao?** Đọc `JMSMessageID`.
- **Message được yêu cầu lưu bền, ưu tiên và hết hạn thế nào?** Xem `JMSDeliveryMode`, `JMSPriority`, `JMSExpiration`.
- **Consumer có đang nhận lại một delivery trước đó?** Xem `JMSRedelivered` và, nếu provider hỗ trợ, property `JMSXDeliveryCount`.

Những thông tin đó **không tương đương nhau**: thời gian tạo sự kiện trong nghiệp vụ không nhất thiết bằng `JMSTimestamp`; `JMSType` không phải tên lớp Java; và `JMSMessageID` không thể thay thế một mã sự kiện nghiệp vụ ổn định qua các lần retry gửi.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **header do ứng dụng đặt** với **header do JMS provider gán hoặc cập nhật**.
2. Giải thích chính xác `JMSDestination`, `JMSType` và `JMSTimestamp`.
3. Dự đoán giá trị của các header **trước send, sau send và sau receive**.
4. Sử dụng JMS header selector và logging để kiểm tra message bằng Java.
5. Phân biệt `JMSTimestamp`, `JMSExpiration`, thời gian sự kiện nghiệp vụ và `JMSDeliveryTime` (API mới).
6. Thiết kế observability/idempotency mà không phụ thuộc sai vào các header do broker quản lý.

## 2. Hệ thống JMS header: ai quyết định giá trị?

JMS message có ba phần cần phân biệt:

- **Header chuẩn JMS**: những trường có tên cố định như `JMSDestination`, `JMSType`, `JMSTimestamp`.
- **Properties**: thuộc tính tùy chỉnh của ứng dụng và những thuộc tính JMSX/vendor, ví dụ `eventId`, `tenantId`, `JMSXDeliveryCount`.
- **Body**: dữ liệu nghiệp vụ dưới dạng `TextMessage`, `BytesMessage`, `MapMessage`, v.v.

Trong các header chuẩn, **không phải trường nào cũng do provider đặt**. Bảng phân loại ở JMS 1.1:

| Header | Bên chủ động gán/kiểm soát | Khi nào cần đọc? |
|---|---|---|
| `JMSDestination` | **Provider** gán từ destination thực tế của lần `send` | Chẩn đoán message được gửi tới queue/topic nào |
| `JMSMessageID` | **Provider** tạo cho lần gửi, trừ khi vô hiệu hóa ID được chấp nhận | Tra cứu delivery/lần gửi trong log broker |
| `JMSTimestamp` | **Provider** gán tại thời điểm giao message cho provider để gửi, trừ khi tùy chọn tắt timestamp được chấp nhận | Đo tuổi message gần đúng, tìm nghẽn giữa send và consume |
| `JMSDeliveryMode` | **Provider** gán theo lựa chọn delivery mode của producer/lần gửi | Phân biệt `PERSISTENT` với `NON_PERSISTENT` |
| `JMSPriority` | **Provider** gán theo độ ưu tiên của producer/lần gửi | Điều tra dispatch/priority |
| `JMSExpiration` | **Provider** xác định từ TTL của lần gửi | Biết mốc hết hạn, nếu có |
| `JMSRedelivered` | **Provider** cập nhật khi message được giao tới consumer | Phát hiện khả năng delivery lặp |
| `JMSCorrelationID` | **Ứng dụng** đặt | Liên kết request/reply hoặc transaction nghiệp vụ |
| `JMSReplyTo` | **Ứng dụng** đặt | Đích reply trong mẫu request/reply |
| `JMSType` | **Ứng dụng** đặt | Nhãn loại message theo hợp đồng nghiệp vụ |

**Điểm trọng tâm:** `JMSType` **không** phải trường provider tự sinh dựa trên `TextMessage`, `Queue` hay tên topic. JMS provider chuyển giá trị loại do ứng dụng cung cấp; ứng dụng phải định nghĩa semantics của giá trị đó.

Dù interface `Message` cung cấp một số setter cho header hệ thống, việc ứng dụng tự đặt `JMSDestination`, `JMSMessageID` hoặc `JMSTimestamp` **trước `send()` không tạo hợp đồng bảo đảm giữ nguyên**: provider có trách nhiệm đặt/chuẩn hóa các giá trị theo lần gửi. Vì vậy không “giả mạo timestamp” bằng cách gọi `message.setJMSTimestamp(...)`.

### 2.1. Trình tự khởi tạo và gửi

~~~mermaid
sequenceDiagram
    participant App as Java Producer
    participant Client as JMS Provider Client
    participant Broker as ActiveMQ Broker
    participant Worker as Java Consumer
    App->>App: Tạo TextMessage, setJMSType / properties
    App->>Client: producer.send(destination, message, options)
    Client->>Client: Gán/chuẩn hóa header do provider quản lý
    Client->>Broker: Chuyển message đến destination
    Broker->>Broker: Enqueue/route theo queue hoặc topic
    Client-->>App: send hoàn tất theo hợp đồng JMS
    Broker->>Worker: Deliver message, cập nhật redelivery nếu cần
    Worker->>Worker: Đọc header, xử lý nghiệp vụ
    Worker->>Broker: ACK hoặc transaction commit
~~~

Sơ đồ mô tả **trách nhiệm logic**, không khẳng định mọi provider đi qua từng bước đồng bộ hoặc duy nhất một lần truyền mạng. Đặc biệt, `send()` thành công không đồng nghĩa consumer đã commit dữ liệu nghiệp vụ.

## 3. `JMSDestination`: đích của lần gửi, không phải đường dẫn lịch sử

### 3.1. Ai quyết định `JMSDestination`?

Khi gửi, `MessageProducer` dùng destination gắn với producer hoặc destination truyền trực tiếp vào overload của `send`:

~~~java
Queue work = session.createQueue("orders.work");
MessageProducer producer = session.createProducer(work);

TextMessage message = session.createTextMessage("orderId=O-1001");
producer.send(message);
~~~

Sau lần gửi, provider đặt `JMSDestination` tương ứng với `orders.work`. Ở phía consumer:

~~~java
Destination actual = received.getJMSDestination();
~~~

Để xem nó là Queue hay Topic:

~~~java
if (actual instanceof Queue) {
    System.out.println(
            "Queue: " + ((Queue) actual).getQueueName());
} else if (actual instanceof Topic) {
    System.out.println(
            "Topic: " + ((Topic) actual).getTopicName());
}
~~~

Tên do client hiển thị có thể chịu ảnh hưởng của provider, namespace và giao thức; không nên parse kết quả `Destination.toString()` thành quy tắc nghiệp vụ.

### 3.2. Producer không gắn đích

Nếu một producer được tạo bằng `session.createProducer(null)` trong JMS 1.1, mỗi lần gửi phải chỉ rõ destination:

~~~java
MessageProducer producer = session.createProducer(null);

Queue work = session.createQueue("orders.work");
Topic events = session.createTopic("orders.events");

producer.send(work, session.createTextMessage("process O-1001"));
producer.send(events, session.createTextMessage("created O-1001"));
~~~

Hai message có `JMSDestination` **khác nhau** theo destination thực tế của từng lần gửi. Chính lời gọi `send(destination, ...)` quyết định đích, không phải tự chỉnh `message.setJMSDestination(...)`.

### 3.3. Forward, DLQ và lịch sử đích

Một consumer có thể nhận message, tạo message mới rồi gửi sang `orders.retry` hoặc broker có thể đưa message đến dead-letter queue. Trong các tình huống này:

- `JMSDestination` là thông tin chuẩn liên quan **destination của message theo lần gửi/delivery**; đừng coi nó là nhật ký bất biến của mọi đích từng đi qua.
- Một số broker giữ thông tin “original destination” bằng **metadata mở rộng** khi chuyển sang DLQ; tên property, cách đọc và tình huống có mặt của nó khác nhau giữa ActiveMQ Classic và Artemis.
- Nếu nghiệp vụ phải biết message ban đầu được phát từ luồng nào, ứng dụng nên lưu một trường hợp đồng như `originStream` hoặc `eventSource` trong metadata do mình quản lý.

**Một nhầm lẫn phổ biến:** consumer thấy một `JMSDestination` hợp lệ nên kết luận quyền truy cập, tenant và business routing đều an toàn. Header này **không phải bằng chứng xác thực**. Tenant/authorization phải được broker và ứng dụng kiểm tra theo cơ chế bảo mật.

## 4. `JMSType`: loại thông điệp do ứng dụng đặt

### 4.1. `JMSType` độc lập với Java class

Ví dụ:

~~~java
TextMessage message = session.createTextMessage(
        "{\"eventId\":\"E-1001\",\"orderId\":\"O-1001\"}");

message.setJMSType("order.created.v1");
~~~

`TextMessage` chỉ cho biết cách truy cập **body** qua `getText()`. `JMSType="order.created.v1"` cho biết **ý nghĩa nghiệp vụ** mà producer chủ động khai báo. Một `BytesMessage` cũng có thể dùng cùng `JMSType` nếu hai bên đã thỏa thuận payload format, nhưng đó có thể là thiết kế gây khó hiểu nếu format không được mô tả rõ.

Khác biệt quan trọng:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Lớp JMS message | `TextMessage` | Cách đọc/ghi body theo JMS API |
| `JMSType` | `order.created.v1` | Nhãn semantic do ứng dụng quy định |
| Property tùy chỉnh | `schemaVersion = 1` | Hỗ trợ phân phiên bản, filter, quan sát |
| Body | `{"eventId":"E-1001",...}` | Nội dung nghiệp vụ |

JMS không áp đặt danh mục giá trị `JMSType` như `OrderCreated` hay `InvoiceRequested`. Các producer/consumer phải có hợp đồng chung về ký tự, phân biệt hoa thường, phiên bản và ý nghĩa.

### 4.2. `JMSType` có thể không có

Nếu ứng dụng không gọi `setJMSType()`, trường có thể là `null`. Đừng viết consumer luôn gọi `message.getJMSType().equals("...")` mà không kiểm tra null.

Ví dụ an toàn:

~~~java
String type = message.getJMSType();
if ("order.created.v1".equals(type)) {
    // Xử lý sự kiện đúng loại.
}
~~~

Nên thiết kế cách xử lý message không có type, type không được hỗ trợ hoặc type không khớp với payload/schema, thay vì để exception ngẫu nhiên quyết định đường retry/DLQ.

### 4.3. Lọc bằng selector dựa trên `JMSType`

JMS selector cho phép dùng `JMSType` làm biểu thức lọc:

~~~java
MessageConsumer consumer = session.createConsumer(
        session.createQueue("orders.events.queue"),
        "JMSType = 'order.created.v1'");
~~~

Consumer sẽ chỉ nhận các message có `JMSType` tương ứng theo semantics selector. Đây là lọc trên **header chuẩn**, không cần thêm property `eventType` với giá trị lặp lại nếu hợp đồng đã chọn `JMSType` làm nhãn loại.

Cần nhớ:

1. Selector không parse JSON body và không tự xác nhận schema.
2. Với một queue có nhiều consumer dùng selector khác nhau, message không được “nhân bản theo selector”; nó vẫn thuộc queue đó và được dispatch tới consumer phù hợp.
3. Trên topic, mỗi subscription có thể có selector riêng; durable subscription và thay đổi selector phải theo đúng hợp đồng JMS/provider.
4. Nếu provider/client hỗ trợ protocol đa ngôn ngữ, cần kiểm tra cách map `JMSType` sang message annotation/property của protocol đó; không suy ra AMQP/MQTT client đều thấy cùng một header Java.

### 4.4. Thiết kế `JMSType` theo phiên bản

Cách đặt tên nhất quán có thể là:

~~~text
order.created.v1
order.cancelled.v1
invoice.issued.v2
payment.failed.v1
~~~

Khi consumer mới chỉ hỗ trợ `order.created.v1`, nó có thể dùng selector hoặc kiểm tra trực tiếp. Nhưng việc tăng lên `v2` cần có **hợp đồng thay đổi payload** và kế hoạch triển khai cùng producer/consumer.

**Không dùng `JMSType` làm mã định danh sự kiện duy nhất.** Hàng triệu sự kiện `order.created.v1` có thể cùng type. Mỗi sự kiện vẫn cần `eventId` riêng để chống xử lý trùng.

## 5. `JMSTimestamp`: thời điểm send theo JMS provider

### 5.1. Định nghĩa thực tế

`JMSTimestamp` là thời gian tính theo mili giây kể từ Unix epoch, do JMS provider đặt khi message được **giao cho provider để gửi**. Nó thường phản ánh thời điểm send xảy ra, **không phải**:

- Thời điểm đối tượng Java `TextMessage` được khởi tạo.
- Thời điểm sự kiện nghiệp vụ thực sự xảy ra.
- Thời điểm message được ghi bền hoàn toàn xuống disk.
- Thời điểm consumer nhận hoặc xử lý thành công.
- Thời điểm transaction chứa send được database downstream commit.

Ví dụ:

~~~text
10:00:00.000  Order Service commit thay đổi đơn hàng
10:00:02.300  Event được thêm vào transactional outbox
10:00:05.100  Worker outbox gọi JMS producer.send(...)
10:00:05.xxx  JMS provider gán JMSTimestamp gần thời điểm gửi
10:00:09.700  Billing consumer nhận message
10:00:10.200  Billing hoàn tất ghi DB và ACK
~~~

Nếu cần ghi **thời điểm nghiệp vụ**, đưa một `occurredAt` (ISO-8601/UTC) vào schema sự kiện. Nếu cần **thời điểm hàng đợi được đặt**, `JMSTimestamp` có thể hỗ trợ đo gần đúng. Hai giá trị không thể dùng thay thế.

### 5.2. Đọc timestamp và trường hợp bằng 0

~~~java
long timestampMillis = message.getJMSTimestamp();

if (timestampMillis > 0) {
    Instant sentAt = Instant.ofEpochMilli(timestampMillis);
    System.out.println("JMS send time: " + sentAt);
} else {
    System.out.println("JMSTimestamp absent/disabled");
}
~~~

Ví dụ cần import `java.time.Instant`. Timestamp bằng `0` nghĩa là không có mốc send đáng dùng trong trường đó; đừng tự chuyển thành ngày 1/1/1970 rồi hiển thị như một sự kiện nghiệp vụ thật.

### 5.3. Tắt timestamp là một *hint* của producer

Trong JMS 1.1, producer có API:

~~~java
producer.setDisableMessageTimestamp(true);
~~~

Đây là **yêu cầu/hint** để provider bỏ thao tác đặt timestamp, nhằm giảm công việc khi ứng dụng không cần nó. Tùy provider, yêu cầu có thể được bỏ qua. Khi được thực hiện, `JMSTimestamp` của message sẽ bằng `0`. Không dùng setter này để điều chỉnh timestamp thành một ngày tùy ý.

Vì vậy code quan sát phải chấp nhận `JMSTimestamp == 0`. Nếu hệ thống cần auditing hoặc tính độ trễ, hãy giữ timestamp mặc định và đo thử trên provider thực.

### 5.4. Đo “thời gian lưu tại broker” chỉ là gần đúng

Consumer có thể ước tính:

~~~java
long sentAt = message.getJMSTimestamp();
long now = System.currentTimeMillis();
if (sentAt > 0) {
    long apparentAgeMillis = now - sentAt;
    System.out.println("Approx. age(ms): " + apparentAgeMillis);
}
~~~

Đây không phải metric có độ chính xác tuyệt đối, vì:

- Đồng hồ giữa máy gửi và máy nhận có thể lệch.
- Producer có thể dùng transaction hoặc batching.
- JMS timestamp không chứa thời điểm broker đã fsync/replicate.
- Producer và consumer có thể xử lý message tại các thời điểm khác nhau trên nhiều node.

Hãy dùng đồng hồ hệ thống được đồng bộ và metric broker như enqueue-to-dequeue latency khi cần SLO nghiêm ngặt. Nếu `now - sentAt` âm, trước hết kiểm tra clock skew thay vì kết luận message “đi ngược thời gian”.

## 6. `JMSExpiration`, `JMSDeliveryTime` và mối liên hệ với timestamp

### 6.1. TTL dẫn đến expiration

Producer có thể chỉ định time-to-live:

~~~java
producer.send(
        message,
        DeliveryMode.PERSISTENT,
        4,
        60_000L); // TTL 60 giây
~~~

Provider xác định `JMSExpiration` là **thời điểm tuyệt đối** message hết hạn (mili giây epoch). Nếu TTL bằng `0`, `JMSExpiration` thông thường là `0`, tức không có mốc expiration do producer đặt.

Điều cần hiểu:

- `JMSTimestamp` và `JMSExpiration` cùng thuộc quản lý của provider nhưng **khác mục đích**.
- TTL là **khoảng sống**, còn `JMSExpiration` là **mốc tuyệt đối**.
- Một message persistent vẫn có thể hết hạn trước khi consumer nhận.
- Expiration không đồng nghĩa retry thất bại hoặc chuyển DLQ; Artemis có thể dùng `expiry-address`, còn Classic có chính sách expiry/DLQ theo cấu hình.

**Không tính `JMSExpiration = JMSTimestamp + TTL` bằng code nghiệp vụ khi `JMSTimestamp == 0`.** Provider vẫn có thể xác định expiration theo thời gian thực của send khi timestamp bị tắt; hãy đọc giá trị expiration mà provider đã đặt.

### 6.2. `JMSDeliveryTime` thuộc JMS 2.0/Jakarta Messaging

API JMS 2.0 giới thiệu header `JMSDeliveryTime`, đại diện mốc **message sớm nhất có thể được deliver** khi dùng delivery delay. Nó không có trong interface `javax.jms.Message` **JMS 1.1** của ví dụ Classic ở bài này.

So sánh ba mốc:

| Trường | Hỏi gì? | Ví dụ |
|---|---|---|
| `JMSTimestamp` | Khi nào message được đưa cho provider để gửi? | 10:00:05 |
| `JMSDeliveryTime` (JMS 2.0+) | Sớm nhất khi nào message được phép phát cho consumer? | 10:00:35 |
| `JMSExpiration` | Sau thời điểm nào message không còn hợp lệ để giao? | 10:01:05 |

Delivery delay **không phải TTL**: trì hoãn delivery không có nghĩa kéo dài expiration tương ứng một cách tự động. Khi dùng client Artemis Jakarta Messaging, có thể cấu hình delivery delay theo API phiên bản phù hợp; trong Classic 5.x/JMS 1.1, không sao chép thẳng những lời gọi của API mới.

## 7. Các header do provider quản lý khác: giá trị và giới hạn

### 7.1. `JMSMessageID`: định danh của lần gửi

Sau khi producer gọi `send()`, provider thường gán một ID dạng chuỗi:

~~~java
producer.send(message);
String providerId = message.getJMSMessageID();
System.out.println(providerId);
~~~

Theo hợp đồng JMS, ID được dùng để định danh message của provider và có thể xuất hiện trong log/management. Tuy nhiên:

- **Không dùng `JMSMessageID` làm business event ID** nếu một sự kiện có thể được gửi lại thành **message mới**. Hai lần send có thể tạo hai JMSMessageID khác nhau cho cùng `eventId`.
- Không dựa vào format của ID để suy ra user, tenant hoặc thứ tự thời gian.
- Không dùng JMSMessageID để thay thế khóa idempotency trong database downstream.

JMS 1.1 có `producer.setDisableMessageID(true)` như một **hint**. Nếu provider chấp nhận, `JMSMessageID` có thể là `null`; provider có thể bỏ qua hint tùy triển khai. Đừng viết mã nghiệp vụ bắt buộc ID này luôn có giá trị.

### 7.2. `JMSDeliveryMode`: yêu cầu lưu bền của lần gửi

JMS định nghĩa:

~~~java
DeliveryMode.PERSISTENT
DeliveryMode.NON_PERSISTENT
~~~

Có thể chọn mode ở producer hoặc từng lần send. Sau send, provider gán `JMSDeliveryMode` tương ứng. Không phải mọi thay đổi mode đều chỉ thay một flag: cách journal, giao dịch, replication, broker crash và hiệu năng có thể khác nhau.

**PERSISTENT không bảo đảm consumer xử lý “exactly once”.** Nếu Billing ghi database thành công nhưng crash trước ACK, broker có thể giao lại message; consumer vẫn cần event ID/idempotency.

### 7.3. `JMSPriority`: ưu tiên có giới hạn semantics

Giá trị JMS priority thuộc khoảng **0 đến 9**; giá trị mặc định thông dụng là **4**. Producer có thể đặt:

~~~java
producer.setPriority(8);
~~~

hoặc chỉ định priority khi send. Provider ghi giá trị priority thực tế vào header. Đừng mặc định những message priority cao sẽ luôn được xử lý trước tuyệt đối: prefetch, nhiều consumer, retry, persistence, broker policy và trạng thái in-flight có thể làm thứ tự quan sát khác kỳ vọng.

### 7.4. `JMSRedelivered`: khả năng đã giao trước đó

Ở phía consumer:

~~~java
boolean maybeRepeatedDelivery = message.getJMSRedelivered();
~~~

Provider đặt cờ này khi cho rằng message đang được **giao lại**. Có thể ghi thêm `JMSXDeliveryCount` nếu provider cung cấp:

~~~java
String count = message.propertyExists("JMSXDeliveryCount")
        ? String.valueOf(message.getIntProperty("JMSXDeliveryCount"))
        : "not available";
~~~

`JMSXDeliveryCount` là **property JMSX**, không phải header `JMSRedelivered` thứ hai. Cần kiểm tra hỗ trợ và hành vi theo phiên bản Classic/Artemis và client.

Hai giới hạn cần nhớ:

1. Một producer có thể gửi **hai message mới mang cùng eventId**; cả hai có thể có `JMSRedelivered=false`. Vì vậy cờ false **không chứng minh** chưa từng xử lý nghiệp vụ.
2. Cờ true báo hiệu delivery có thể đã xảy ra trước đó, **không chứng minh** database đã commit. Consumer phải xử lý idempotent trong cả hai trường hợp.

## 8. Header ứng dụng tự quản: `JMSCorrelationID`, `JMSReplyTo` và metadata nghiệp vụ

Để tránh dùng nhầm header provider, cần biết ba nơi ứng dụng có quyền thiết kế:

### 8.1. `JMSCorrelationID`

Ứng dụng thường sử dụng cho request/reply hoặc liên kết nhiều message:

~~~java
request.setJMSCorrelationID("request-8f21");
~~~

Với mô hình request/reply, responder có thể sao chép correlation ID của request vào reply theo hợp đồng của hai bên. Correlation ID **không bắt buộc duy nhất toàn hệ thống** và không tự được provider chuyển thành business event ID.

### 8.2. `JMSReplyTo`

Ứng dụng có thể đặt destination nhận reply:

~~~java
TemporaryQueue replies = session.createTemporaryQueue();
request.setJMSReplyTo(replies);
~~~

Đó là **ý định request/reply của ứng dụng**; nó không thay đổi `JMSDestination` của request. Request vẫn được gửi tới queue công việc; reply là message khác, được gửi tới destination mà request chỉ định trong `JMSReplyTo`. Temporary destination có vòng đời theo connection và chịu kiểm soát ACL/provider.

### 8.3. Property và body

Một thiết kế sự kiện dễ quan sát:

~~~java
TextMessage msg = session.createTextMessage(
        "{\"eventId\":\"E-1001\",\"orderId\":\"O-1001\","
      + "\"occurredAt\":\"2026-11-17T03:00:00Z\"}");

msg.setJMSType("order.created.v1");
msg.setStringProperty("eventId", "E-1001");
msg.setStringProperty("producerService", "order-service");
msg.setJMSCorrelationID("trace-req-123");
~~~

Ở đây:

- `JMSType` cho consumer biết loại sự kiện.
- `eventId` dùng chống xử lý trùng ở tầng nghiệp vụ.
- `occurredAt` là mốc thời gian nghiệp vụ (không phụ thuộc `JMSTimestamp`).
- `producerService` phục vụ log/quan sát; không phải dữ liệu xác thực.
- `JMSCorrelationID` liên kết luồng request/tracing theo hợp đồng.

Nếu message đi qua nhiều broker/protocol hoặc được transform, phải kiểm thử việc giữ lại header/property. Không giả định mọi client ngoài Java đều hỗ trợ y hệt header JMS.

## 9. Ví dụ Java Classic 5.x: in header trước và sau `send`

### 9.1. Chuẩn bị

Hai chương trình ví dụ ở phần này dùng:

- Broker **ActiveMQ Classic 5.x** đang lắng nghe tại `tcp://localhost:61616`.
- Client Maven artifact `org.apache.activemq:activemq-client`, chọn phiên bản **Classic 5.x tương thích với broker** và namespace `javax.jms`.
- Java 8 trở lên.
- Tài khoản lab `app / lab-secret` có quyền gửi/nhận queue `orders.headers.demo`; nếu broker lab không cấu hình user này thì thay bằng thông tin đăng nhập thực tế.
- Một queue test với backlog đã được dọn hoặc theo dõi riêng, để không trộn message cũ với kết quả mới.

Cấu trúc ví dụ dùng `try/finally` thay vì `try-with-resources` cho các interface `javax.jms.Connection`/`Session` của JMS 1.1, vì chúng **không** khai báo `AutoCloseable`.

### 9.2. Producer: client đặt `JMSType`, provider gán phần còn lại

File minh họa `HeaderProducer.java`:

~~~java
import java.time.Instant;
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.Destination;
import javax.jms.JMSException;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class HeaderProducer {
    private static final String BROKER = "tcp://localhost:61616";

    public static void main(String[] args) throws Exception {
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(BROKER);

        Connection connection =
                factory.createConnection("app", "lab-secret");
        try {
            Session session =
                    connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
            try {
                Queue queue = session.createQueue("orders.headers.demo");
                MessageProducer producer = session.createProducer(queue);
                try {
                    TextMessage message = session.createTextMessage(
                            "{\"eventId\":\"E-1001\",\"orderId\":\"O-1001\"}");
                    message.setJMSType("order.created.v1");
                    message.setJMSCorrelationID("request-123");
                    message.setStringProperty("eventId", "E-1001");

                    printHeaders("BEFORE SEND", message);

                    producer.send(
                            message,
                            DeliveryMode.PERSISTENT,
                            4,
                            60_000L); // TTL 60 giây

                    printHeaders("AFTER SEND", message);
                } finally {
                    producer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }

    private static void printHeaders(
            String stage, TextMessage message) throws JMSException {
        Destination destination = message.getJMSDestination();

        System.out.println("== " + stage + " ==");
        System.out.println("Destination = " + destination);
        System.out.println("Type = " + message.getJMSType());
        System.out.println("Message ID = " + message.getJMSMessageID());
        System.out.println("Correlation ID = "
                + message.getJMSCorrelationID());

        long sentAt = message.getJMSTimestamp();
        System.out.println("Timestamp(ms) = " + sentAt);
        System.out.println("Timestamp(UTC) = "
                + (sentAt > 0
                        ? Instant.ofEpochMilli(sentAt).toString()
                        : "not available"));

        System.out.println("Expiration(ms) = "
                + message.getJMSExpiration());
        System.out.println("Delivery mode = "
                + message.getJMSDeliveryMode());
        System.out.println("Priority = " + message.getJMSPriority());
    }
}
~~~

**Điều dự kiến quan sát:**

- Trước send: `JMSType="order.created.v1"` và `JMSCorrelationID="request-123"` đã có vì ứng dụng đặt. Một message mới thường chưa có provider-generated message ID/destination/timestamp thích hợp cho lần gửi.
- Sau send: `JMSDestination` phản ánh queue gửi, `JMSMessageID` thường được sinh và `JMSTimestamp` thường khác 0 nếu không tắt timestamp.
- `JMSDeliveryMode` phản ánh `PERSISTENT`, priority của lần gửi là `4`.
- `JMSExpiration` được tính theo TTL 60 giây; không dựa vào một giá trị cụ thể trong output vì thời điểm thực thi mỗi lần khác nhau.
- Nếu có một tùy chọn provider vô hiệu hóa header hoặc một đường gửi đặc thù, giá trị có thể khác. Hãy đối chiếu hợp đồng của client đang chạy.

Không dùng `connection.start()` trong producer đơn thuần: theo JMS 1.1, `start()` dùng để bắt đầu delivery cho consumer, không phải điều kiện bắt buộc để producer gọi `send()`.

### 9.3. Consumer: đọc header nhận được và ACK sau khi xử lý

File minh họa `HeaderConsumer.java`:

~~~java
import java.time.Instant;
import javax.jms.Connection;
import javax.jms.Destination;
import javax.jms.JMSException;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;
import javax.jms.Topic;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class HeaderConsumer {
    public static void main(String[] args) throws Exception {
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");

        Connection connection =
                factory.createConnection("app", "lab-secret");
        try {
            Session session = connection.createSession(
                    false, Session.CLIENT_ACKNOWLEDGE);
            try {
                Queue queue = session.createQueue("orders.headers.demo");

                // Lọc theo header JMSType, không parse body.
                MessageConsumer consumer = session.createConsumer(
                        queue, "JMSType = 'order.created.v1'");
                try {
                    connection.start();
                    Message received = consumer.receive(10_000L);

                    if (received == null) {
                        System.out.println("No matching message");
                        return;
                    }
                    if (!(received instanceof TextMessage)) {
                        session.recover();
                        throw new IllegalStateException(
                                "Expected TextMessage");
                    }

                    String eventId =
                            received.getStringProperty("eventId");
                    System.out.println("eventId = " + eventId);
                    System.out.println("JMSType = "
                            + received.getJMSType());
                    System.out.println("JMSDestination = "
                            + destinationName(received.getJMSDestination()));
                    System.out.println("JMSMessageID = "
                            + received.getJMSMessageID());
                    System.out.println("JMSTimestamp = "
                            + toTime(received.getJMSTimestamp()));
                    System.out.println("JMSExpiration = "
                            + toTime(received.getJMSExpiration()));
                    System.out.println("JMSRedelivered = "
                            + received.getJMSRedelivered());

                    if (received.propertyExists("JMSXDeliveryCount")) {
                        System.out.println("JMSXDeliveryCount = "
                                + received.getIntProperty("JMSXDeliveryCount"));
                    }

                    try {
                        handleIdempotently(
                                eventId,
                                ((TextMessage) received).getText());
                        received.acknowledge();
                    } catch (Exception error) {
                        session.recover();
                        throw error;
                    }
                } finally {
                    consumer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }

    private static String destinationName(Destination d)
            throws JMSException {
        if (d instanceof Queue) {
            return "queue:" + ((Queue) d).getQueueName();
        }
        if (d instanceof Topic) {
            return "topic:" + ((Topic) d).getTopicName();
        }
        return String.valueOf(d);
    }

    private static String toTime(long millis) {
        return millis > 0
                ? Instant.ofEpochMilli(millis).toString()
                : "none/0";
    }

    private static void handleIdempotently(
            String eventId, String payload) {
        // Demo: production ghi eventId với unique constraint trong DB.
        System.out.println("Handled " + eventId + ": " + payload);
    }
}
~~~

Lưu ý khi đánh giá tính đúng đắn:

- Hàm `handleIdempotently` trong ví dụ **chỉ in log**, chưa thực sự chống xử lý trùng. Ứng dụng thật cần lưu `eventId` trong database hoặc inbox có unique constraint, trong transaction với thay đổi nghiệp vụ.
- `CLIENT_ACKNOWLEDGE` xác nhận các message đã consume trong **session**, không chỉ riêng một message tùy ý nếu session đã nhận nhiều message.
- `session.recover()` dùng cho session **không transacted**, yêu cầu redelivery theo semantics của provider. Nếu dùng `SESSION_TRANSACTED` thì dùng `rollback()`/`commit()` thay thế.
- Timeout `receive(10_000L)` trả `null` không chứng minh queue không có message: còn có thể do selector, prefetch hoặc các consumer khác.
- `JMSType` là giá trị gốc do producer đặt; selector phải sử dụng đúng chuỗi (phân biệt hoa thường).

### 9.4. Thứ tự chạy và cách đọc output

Chạy producer trước, sau đó chạy consumer **trước khi TTL 60 giây hết**. Với classpath bao gồm các dependency Classic/JMS tương thích, gọi:

~~~text
java HeaderProducer
java HeaderConsumer
~~~

Ở hai terminal, có thể thử chạy consumer trước, sau đó producer. Cần dùng đúng cách chạy Java phù hợp cấu trúc dự án (Maven/Gradle hoặc explicit classpath). Nếu gửi nhiều lần với cùng `eventId`, đây là ví dụ hữu ích để thấy `JMSMessageID` có thể khác trong khi event ID nghiệp vụ vẫn như nhau.

Không so sánh output timestamp giữa hai máy chỉ bằng giờ hiển thị cục bộ; ưu tiên epoch milliseconds hoặc ISO-8601 UTC.

## 10. Bài thực hành kiểm chứng từng trường

### Thử nghiệm A — Thay destination, giữ `JMSType`

**Chuẩn bị:** ngoài `orders.headers.demo`, tạo queue test `orders.headers.audit` hoặc cho broker được phép auto-create trong môi trường lab.

Sửa một phiên bản producer thành:

~~~java
Queue first = session.createQueue("orders.headers.demo");
Queue second = session.createQueue("orders.headers.audit");

MessageProducer producer = session.createProducer(null);
TextMessage m1 = session.createTextMessage("E-2001");
m1.setJMSType("order.created.v1");
producer.send(first, m1);

TextMessage m2 = session.createTextMessage("E-2002");
m2.setJMSType("order.created.v1");
producer.send(second, m2);
~~~

**Dự kiến:** `m1.getJMSDestination()` và `m2.getJMSDestination()` khác nhau; `JMSType` giống nhau. Điều này chứng minh **destination là nơi gửi**, còn **type là nghĩa nghiệp vụ**. Hai consumer phải đọc hai queue khác nhau.

### Thử nghiệm B — Đổi `JMSType`, giữ destination

Gửi vào cùng `orders.headers.demo` hai message:

~~~java
TextMessage a = session.createTextMessage("A");
a.setJMSType("order.created.v1");
producer.send(a);

TextMessage b = session.createTextMessage("B");
b.setJMSType("order.cancelled.v1");
producer.send(b);
~~~

Consumer có selector `JMSType = 'order.created.v1'` chỉ phù hợp với message A. Message B vẫn có thể chờ trong queue cho consumer khác có selector phù hợp. **Selector không tự tạo queue riêng cho từng type.**

### Thử nghiệm C — Timestamp và TTL không tương đương

1. Gửi một message TTL 60 giây; in `JMSTimestamp` và `JMSExpiration`.
2. Gửi message khác TTL bằng 0; in `JMSExpiration`.
3. Thử `producer.setDisableMessageTimestamp(true)` (trong lab), gửi tiếp và so sánh giá trị `JMSTimestamp` và `JMSExpiration`.
4. Nếu provider bỏ qua hint, ghi nhận kết quả thực tế; không kết luận code đã sai chỉ vì timestamp vẫn xuất hiện.
5. Đợi message hết hạn với consumer offline, kiểm tra queue/expiry theo cấu hình broker.

**Giải thích:** TTL quyết định thời điểm hết hiệu lực; timestamp thể hiện mốc send khi provider có cung cấp. TTL bằng 0 không có nghĩa message luôn được lưu bền.

### Thử nghiệm D — Provider-generated ID và sự kiện gửi lặp

1. Tạo hai `TextMessage` khác nhau với cùng property `eventId="E-3001"`.
2. Gửi cả hai vào queue test.
3. So sánh hai `JMSMessageID` với `eventId`.
4. Trong consumer, kiểm tra cả hai có thể được nhận nhưng chỉ một lần ghi nghiệp vụ được phép commit nhờ unique `eventId`.

**Giải thích:** broker message identity và business event identity có nhiệm vụ khác nhau. Đừng deduplicate theo `JMSMessageID` nếu producer có thể retry một event bằng message mới.

### Thử nghiệm E — Redelivery thay đổi header nào?

1. Dùng một session transacted để nhận message.
2. Gọi `rollback()` thay vì `commit()` ở lần nhận đầu.
3. Nhận lại message; in `JMSRedelivered` và `JMSXDeliveryCount` nếu có.
4. Kiểm tra `eventId`, `JMSType` và `JMSDestination` vẫn phù hợp, sau đó `commit()`.
5. Nếu không nhận lại ngay, kiểm tra redelivery delay, client policy và tình trạng broker.

**Giải thích:** provider có thể cập nhật metadata giao lại, nhưng **không phải lúc nào `JMSRedelivered=true` cũng đồng nghĩa một lần xử lý nghiệp vụ đã hoàn tất**.

## 11. Các bẫy thường gặp và cách phòng tránh

| Nhận định hoặc lỗi | Vì sao sai | Cách làm đúng |
|---|---|---|
| “`JMSType` do ActiveMQ tự suy từ `TextMessage`.” | JMSType là nhãn ứng dụng đặt; TextMessage là cách chứa body | Gọi `setJMSType` theo hợp đồng schema |
| “`JMSDestination` là nơi message được tạo ra ban đầu.” | Nó gắn với destination trong quá trình send/delivery, không phải toàn bộ lịch sử route | Lưu `originStream`/event source nếu cần |
| “Sửa `setJMSDestination` sẽ chuyển message sang queue khác.” | Destination thực của send là argument/binding producer | Gọi đúng `producer.send(destination,...)` |
| “`JMSTimestamp` là thời điểm business event xảy ra.” | Provider đặt gần lúc send, có thể muộn hơn sự kiện | Đưa `occurredAt` vào schema nghiệp vụ |
| “Timestamp bằng 0 là lỗi dữ liệu thời gian 1970.” | Có thể đã tắt timestamp | Coi 0 là không có timestamp hợp lệ |
| “TTL=60s thì `JMSExpiration` luôn bằng `JMSTimestamp+60000` trong mọi chế độ.” | Timestamp có thể bị disable, provider vẫn tính expiry | Đọc `getJMSExpiration()`; không tính từ timestamp thiếu |
| “Message gửi thành công chứng minh consumer đã xử lý.” | Send kết thúc ở provider/broker, không phải business commit | Theo dõi ACK/commit, idempotency và SLA xử lý |
| “`JMSMessageID` là mã đơn hàng/sự kiện.” | Hai lần send cùng sự kiện có thể có ID khác nhau | Sử dụng `eventId` riêng và ổn định |
| “`JMSRedelivered=false` thì không có duplicate.” | Producer có thể gửi trùng qua hai message mới | Unique key hoặc inbox ở phía consumer |
| “`JMSXDeliveryCount` là header chuẩn `JMSRedelivered`.” | Đây là property hỗ trợ delivery count, không phải cùng field | Kiểm tra `propertyExists`, đọc count có phòng thủ |
| “Đặt `JMSPriority=9` sẽ luôn xử lý trước.” | Thực tế còn prefetch, consumer và broker policy | Thử nghiệm tải, không dựa vào thứ tự tuyệt đối |
| “Có thể gọi `getJMSDeliveryTime` trong JMS 1.1.” | Header này thuộc API JMS 2.0/Jakarta Messaging | Chọn API phiên bản đúng và kiểm tra dependency |

## 12. Checklist thiết kế header cho luồng messaging

Trước khi đưa event/lệnh vào ActiveMQ Classic hoặc Artemis, cần xác nhận:

- **Nơi gửi:** Producer thực sự dùng Queue hay Topic và tên destination nào? Khi in `JMSDestination`, có đúng kỳ vọng không?
- **Kiểu nghiệp vụ:** `JMSType` có danh mục giá trị rõ ràng, có version và hành vi xử lý type không hỗ trợ không?
- **Định danh:** `eventId` có ổn định qua retry gửi không, hay đang dùng nhầm `JMSMessageID`?
- **Thời gian:** Phân biệt `occurredAt` của nghiệp vụ, `JMSTimestamp` của provider và `JMSExpiration` của TTL?
- **Giao tiếp:** `JMSReplyTo` và `JMSCorrelationID` có được dùng nhất quán khi request/reply không?
- **Lưu bền:** `JMSDeliveryMode` và TTL có phù hợp với khả năng broker giữ message, durable subscription và downtime không?
- **Nhận trùng:** Consumer có xử lý idempotent bất kể `JMSRedelivered` là true hay false không?
- **Quan sát:** Log có destination/type/eventId/correlationId/timestamp/delivery count một cách an toàn, tránh lộ nội dung nhạy cảm không?
- **Liên thông:** Có kiểm thử mapping header khi đổi Classic ↔ Artemis hoặc đổi protocol/client không?
- **Phiên bản API:** Đang dùng `javax.jms` JMS 1.1, JMS 2.0 hay `jakarta.jms`? Các header/API mới như `JMSDeliveryTime` có được hỗ trợ đúng phiên bản không?

## 13. Tóm tắt kỹ thuật

**`JMSDestination`** do JMS provider xác định từ destination của lần gửi, phục vụ quan sát message đã được gửi đến đâu. **`JMSType`** là nhãn loại nghiệp vụ **do ứng dụng đặt**, có thể dùng trong selector và version contract. **`JMSTimestamp`** do provider ghi tại thời điểm giao message để gửi, là mốc kỹ thuật và không thay thế thời gian sự kiện nghiệp vụ.

Các header provider quản lý khác — `JMSMessageID`, `JMSDeliveryMode`, `JMSPriority`, `JMSExpiration`, `JMSRedelivered` và `JMSDeliveryTime` ở JMS 2.0+ — hỗ trợ vận hành, nhận diện delivery, expiry và đo độ trễ. Chúng **không** tự bảo đảm xử lý đúng một lần hoặc tạo ra định danh sự kiện nghiệp vụ ổn định.

Thiết kế message đáng tin cậy vì vậy cần kết hợp **header chuẩn JMS đúng vai trò**, **metadata nghiệp vụ do ứng dụng sở hữu** và **kiểm thử giá trị thực tế trước/sau send, receive và redelivery** trên đúng client/broker mà hệ thống sử dụng.
