# Phân biệt mặc định của producer, provider và ứng dụng khi gửi JMS

> **Module:** Spring Framework – JMS  
> **Nhóm:** Chất lượng gửi  
> **Mục tiêu:** Biết chính xác QoS đang lấy từ đâu, giá trị mặc định nào được JMS quy định, cấu hình nào Spring thực sự truyền cho producer, và chính sách nào broker/provider có thể áp dụng sau cùng.

## Bạn sẽ học được gì?

1. Phân biệt ba tầng **producer**, **provider/broker** và **ứng dụng Spring** khi quyết định delivery mode, priority, time-to-live (TTL), delivery delay.
2. Nhớ đúng các giá trị mặc định theo đặc tả Jakarta Messaging và không coi chúng là chính sách lưu giữ vô hạn của broker.
3. Hiểu khác biệt giữa `MessageProducer.send(message)` dùng default producer, `send(message, mode, priority, ttl)` chỉ rõ QoS cho lượt gửi, và `JMSProducer.setDeliveryMode(...).setPriority(...).setTimeToLive(...)`.
4. Giải thích vì sao `JmsTemplate.setPriority(8)` **chưa chắc** làm message có priority 8 nếu chưa bật `setExplicitQosEnabled(true)`.
5. Biết ngoại lệ quan trọng: một số provider cho phép **cấu hình quản trị ghi đè cả giá trị QoS client yêu cầu**; kết quả phải được kiểm tra qua headers và provider.
6. Đọc đúng `JMSDeliveryMode`, `JMSPriority`, `JMSExpiration` và `JMSDeliveryTime` sau gửi/ở consumer; tránh đặt các header do provider quản lý bằng setter trên `Message`.
7. Cấu hình `JmsTemplate` ổn định trong Spring, viết thử nghiệm có broker, dự đoán tình huống TTL nhỏ hơn delivery delay và xây dựng policy ứng dụng an toàn.

## 1. Vì sao nói “mặc định” thường gây nhầm lẫn?

Câu “JMS mặc định gửi persistent, priority 4, không hết hạn” mô tả **giá trị mặc định của producer theo Jakarta Messaging**, nhưng chưa đủ để khẳng định mọi message ở production có đúng các header này.

Có ít nhất ba lớp:

- **Producer/API:** `MessageProducer` hoặc `JMSProducer` có các thuộc tính mặc định theo đặc tả. Khi lập trình viên thay chúng hoặc dùng overload gửi có QoS tường minh, client cung cấp một yêu cầu cụ thể.
- **Provider/broker:** implementation Jakarta Messaging, cấu hình `ConnectionFactory`, destination, address/routing, quyền, quota và chính sách quản trị. Provider có thể cấu hình default khác trong một số trường hợp và **đặc tả cho phép cơ chế admin override** đối với một số header; không phải provider nào cũng hỗ trợ.
- **Ứng dụng/framework:** business policy, bean `JmsTemplate`, `MessageCreator`/`MessageConverter`, quy tắc TTL theo loại sự kiện, yêu cầu retry/idempotency. Framework quyết định có **chủ động truyền** QoS vào lời gọi send hay để producer/provider sử dụng default.

```text
                   ỨNG DỤNG / SPRING
          business policy, JmsTemplate config
                       |
             explicitQoS = false/true?
                       |
                       v
                   JMS PRODUCER
    producer defaults hoặc send(mode, priority, ttl)
                       |
                       v
                   JMS PROVIDER
         ConnectionFactory/admin configuration
            optional QoS administrative override
                       |
                       v
            JMS HEADER THỰC TẾ + BROKER
         retention/quota/expiry/routing/permissions
                       |
                       v
                     CONSUMER
```

**Không tồn tại một công thức ưu tiên tuyệt đối giống nhau cho mọi provider** như “application luôn thắng provider” hoặc “broker luôn thắng client”. Hợp đồng chuẩn quy định giá trị mặc định, cách client yêu cầu QoS và quyền override của quản trị viên; khả năng hỗ trợ admin override cũng như chính sách cụ thể phụ thuộc provider.

Để debug đúng, cần nói rõ đang hỏi:

1. **Giá trị mặc định theo API là gì?**
2. **Đối tượng producer thực tế đang giữ giá trị nào?**
3. **Spring có truyền giá trị riêng khi gọi send không?**
4. **Provider có áp đặt một cấu hình quản trị lên message không?**
5. **Header trên message sau gửi/thực nhận là gì?**
6. **Destination có chính sách retention và failure nào khiến message vẫn bị mất/hết hạn không?**

Chỉ trả lời câu 1 rồi suy ra câu 6 là một sai lầm.

## 2. Bảng chuẩn: mặc định của producer theo Jakarta Messaging

Theo Jakarta Messaging API, các giá trị gốc là:

| Thành phần | Giá trị mặc định JMS | Ý nghĩa chính xác |
| --- | --- | --- |
| Delivery mode | `DeliveryMode.PERSISTENT` (giá trị int `2`) | Provider phải thực hiện mức bảo vệ vận chuyển persistent theo đặc tả |
| Priority | `4` | Mức ưu tiên bình thường, thang từ `0` thấp nhất đến `9` cao nhất |
| Time-to-live | `0` mili giây | Không đặt hạn hết hiệu lực dựa trên TTL; `JMSExpiration=0` nếu không có override |
| Delivery delay | `0` mili giây | Message không bị yêu cầu trì hoãn giao cho consumer |
| Message ID generation | Bật mặc định | Provider thường gán `JMSMessageID` khi send |
| Message timestamp generation | Bật mặc định | Provider thường gán `JMSTimestamp` khi send |

Bốn hằng số trong `jakarta.jms.Message` có thể được tham khảo là:

```java
Message.DEFAULT_DELIVERY_MODE    // PERSISTENT
Message.DEFAULT_PRIORITY         // 4
Message.DEFAULT_TIME_TO_LIVE     // 0L
Message.DEFAULT_DELIVERY_DELAY   // 0L
```

**Mặc định theo JMS không phải lời hứa rằng broker luôn có tài nguyên ổn định, giữ được mọi message vô hạn hay mọi subscriber sẽ nhận được.** Message còn chịu TTL sau override, quota, policy của destination, failure, transaction, durable subscription và cách consumer xử lý.

### 2.1. PERSISTENT không đồng nghĩa exactly-once nghiệp vụ

`DeliveryMode.PERSISTENT` yêu cầu provider bảo vệ message trong quá trình gửi tốt hơn `NON_PERSISTENT`; không có nghĩa:

- Consumer chắc chắn xử lý nghiệp vụ thành công.
- Message không bao giờ bị xóa bởi hạn mức lưu giữ, retention policy hoặc hết hạn.
- Một topic non-durable subscriber offline sẽ được replay mọi event bị bỏ lỡ.
- Một tác vụ không bao giờ chạy hai lần khi transaction rollback hoặc redelivery.
- Việc gửi JMS và ghi database tự nhiên trở thành một transaction nguyên tử.

Đặc tả phân biệt trách nhiệm **vận chuyển message tới destination** và **chính sách lưu giữ tại destination cho tới lúc được xác nhận**. Broker có thể áp đặt quota, dead-letter và retention riêng. Dù JMS có quy tắc delivery, hệ thống nghiệp vụ vẫn cần idempotency khi xảy ra redelivery, restart hoặc client retry trong trạng thái chưa rõ send đã thành công chưa.

### 2.2. Priority 4 và thang 0–9

- Priority `0..4` là nhóm thông thường; `5..9` là nhóm ưu tiên cao hơn.
- Priority cao **không phải FIFO tuyệt đối**, không bắt provider thực thi strict priority ordering.
- Nếu nhiều queue consumers, selectors, transactions hoặc redelivery, không suy luận thứ tự xử lý toàn hệ thống chỉ từ `JMSPriority`.
- Nếu ứng dụng tự đưa mọi message về priority 9, bạn triệt tiêu ý nghĩa phân cấp và có thể làm message ưu tiên thấp chờ lâu.

Dùng priority như **tín hiệu ưu tiên tương đối** với chính sách và metric được kiểm chứng trên broker, không phải cam kết SLA thời gian xử lý.

### 2.3. TTL = 0 không có nghĩa lưu vô hạn tại broker

TTL là thời gian message được phép sống theo cơ chế expiration của JMS. `0` nghĩa là **không hết hạn vì TTL**, không phải “lưu vô hạn bất kể quota, policy, destination, broker crash”.

Khi TTL lớn hơn 0, provider tính `JMSExpiration` theo thời điểm send và TTL. Đơn vị là **mili giây**. Ví dụ `60_000L` = 60 giây, không phải 60 phút.

Nếu message đã expired, provider **không được giao** message đó như thể còn hợp lệ. Cách message bị loại bỏ, ghi log hay chuyển expired-message address là tùy provider. Nếu sender nói “message không hết hạn” chỉ vì gọi `setTimeToLive(0)` nhưng có admin override TTL 20 giây, header thực nhận sẽ khác.

### 2.4. Delay = 0 khác TTL = 0

Delivery delay cho biết **sớm nhất khi nào được phép giao**; TTL cho biết **khi nào hết hạn**:

```text
send time: t0
  |
  +--- deliveryDelay = 5s ---> earliest delivery at t0 + 5s
  |
  +--- timeToLive   = 3s ---> expires at t0 + 3s
```

Ở ví dụ này, message **có thể hết hạn trước khi đủ điều kiện được giao**. Chọn delay và TTL phải xét cùng nhau, nhất là với delayed job, retry schedule hoặc workflow phải chờ.

Để có delayed dispatch đáng tin, xem cả TTL, backlog, provider delay implementation, clock/skew và retention policy; việc set delay đơn lẻ không bảo đảm message được giao chính xác tại thời điểm chỉ định.

## 3. Mặc định và override trong Classic JMS MessageProducer

`jakarta.jms.MessageProducer` có các setter:

```java
producer.setDeliveryMode(DeliveryMode.PERSISTENT);
producer.setPriority(7);
producer.setTimeToLive(45_000L);
producer.setDeliveryDelay(2_000L);
```

Những setter này cập nhật cấu hình **producer**. Nếu dùng `producer.send(message)`, provider sử dụng QoS producer/default áp dụng cho lần gửi đó, trừ chính sách override hợp lệ. Nếu dùng overload `send(message, mode, priority, ttl)`, ba giá trị đó được chỉ rõ **cho lần gửi cụ thể**, thay vì đọc ba default của producer.

### 3.1. Producer default

```java
// session và destination là Jakarta Messaging objects hợp lệ.
MessageProducer producer = session.createProducer(destination);
try {
    producer.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
    producer.setPriority(6);
    producer.setTimeToLive(20_000L);

    TextMessage a = session.createTextMessage("A");
    TextMessage b = session.createTextMessage("B");

    producer.send(a); // Yêu cầu theo producer defaults: NP / 6 / 20s
    producer.send(b); // Cùng producer defaults
} finally {
    producer.close();
}
```

Đây là mảnh code của ứng dụng đã có `jakarta.jms.Session` và provider, **không chạy chỉ bằng JDK**. Provider vẫn có thể có admin override. Đừng gọi API getter của `Message` **trước send** để kết luận các giá trị gửi cuối cùng: một số header do provider ghi tại lúc send.

### 3.2. Ghi đè ba QoS cho đúng một lần send

```java
MessageProducer producer = session.createProducer(destination);
try {
    producer.setDeliveryMode(DeliveryMode.PERSISTENT);
    producer.setPriority(4);
    producer.setTimeToLive(0L);

    TextMessage urgent = session.createTextMessage("URGENT");
    producer.send(
            urgent,
            DeliveryMode.PERSISTENT,
            9,
            5_000L
    ); // Yêu cầu explicit QoS cho riêng "URGENT"

    TextMessage normal = session.createTextMessage("NORMAL");
    producer.send(normal); // Dùng lại producer defaults: P / 4 / 0
} finally {
    producer.close();
}
```

**Phân biệt quan trọng:** explicit per-send QoS không biến producer defaults thành giá trị mới. Một lần gửi sau đó bằng `send(message)` lại theo producer state. Delivery delay, nếu có, là cấu hình của producer (hoặc phương thức tương ứng trong simplified API), không phải tham số thứ tư của overload `send(message, mode, priority, ttl)`.

### 3.3. Nhận diện provider-managed message headers

Sau một synchronous send thành công, có thể kiểm tra:

```java
System.out.println("mode=" + urgent.getJMSDeliveryMode());
System.out.println("priority=" + urgent.getJMSPriority());
System.out.println("expiration=" + urgent.getJMSExpiration());
System.out.println("deliveryTime=" + urgent.getJMSDeliveryTime());
```

Các dòng in thực tế **phụ thuộc provider, admin override và thời điểm send**, nên không thể ghi stdout cố định. Trong async send, các header do provider gán chỉ an toàn để đọc sau callback hoàn thành theo đặc tả.

**Không làm điều này để “thiết lập QoS”:**

```java
// SAI MỤC ĐÍCH: các setter header này không phải API client
// dùng để quyết định QoS khi gửi.
message.setJMSPriority(9);
message.setJMSDeliveryMode(DeliveryMode.PERSISTENT);
message.setJMSExpiration(System.currentTimeMillis() + 60_000);
```

Những setter trên `Message` là đường cho provider gán header; khi message được gửi, giá trị client tự nhét vào các header do provider quản lý sẽ bị bỏ qua/ghi đè. Để thiết lập QoS, dùng **producer setters**, overload của `send` hoặc cấu hình Spring thực sự chuyển tham số đến producer.

## 4. Simplified JMS API: JMSProducer có state riêng

Từ JMS 2.0/Jakarta Messaging, `JMSContext` và `JMSProducer` giúp giảm boilerplate:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.Queue;

public final class QosJmsProducer {
    private final ConnectionFactory connectionFactory;

    public QosJmsProducer(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public void publish() {
        try (JMSContext context =
                     connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

            Queue queue = context.createQueue("billing.jobs");

            JMSProducer producer = context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setPriority(8)
                    .setTimeToLive(30_000L)
                    .setDeliveryDelay(1_000L);

            producer.send(queue, "INV-42");
        }
    }
}
```

Đây là **một class Java dành cho project có Jakarta Messaging API/provider/broker**; không thể chạy bằng `javac` thuần JDK 17. Trước khi gửi, phải có tài nguyên queue hợp lệ hoặc cơ chế auto-create của provider; `createQueue(String)` tạo object handle chứ không phải API portable để provision physical broker queue.

Đặc điểm:

- `JMSProducer` giữ delivery mode, priority, TTL, delay của chính producer.
- `send(Destination, body)` gửi với cấu hình producer tại thời điểm gọi, chịu chính sách quản trị hỗ trợ bởi provider.
- `JMSProducer` có getter như `getDeliveryMode()`, `getPriority()`, `getTimeToLive()` và `getDeliveryDelay()` để kiểm tra **requested producer state**.
- Các getter **không chứng minh** broker đã áp dụng đúng nếu có administrative override.
- Những setting này không phải property trên payload String hoặc trên `Queue`.
- `setDisableMessageID(true)` và `setDisableMessageTimestamp(true)` là các **hint tối ưu** mà provider có thể chấp nhận hoặc bỏ qua; mặc định message ID và timestamp được bật.

### 4.1. Đừng biến “disable message ID” thành bảo đảm

```java
context.createProducer()
        .setDisableMessageID(true)
        .setDisableMessageTimestamp(true)
        .send(queue, "heartbeat");
```

Những lời gọi trên nói với provider rằng client không cần ID/timestamp cho message đó. Provider **được phép bỏ qua hint**; không thể coi kết quả `getJMSMessageID()==null` hoặc `getJMSTimestamp()==0` là chắc chắn. Không tắt ID nếu ứng dụng cần tracing, request/reply correlation theo message ID hoặc debug với broker.

Các hint này khác hẳn ba QoS chính `deliveryMode/priority/timeToLive`. Không gộp chúng vào flag `explicitQosEnabled` của Spring, vì Spring có cấu hình `setMessageIdEnabled` và `setMessageTimestampEnabled` riêng.

## 5. Provider/broker: hai điều dễ nhầm trong “mặc định”

### 5.1. Provider có thể cấu hình **mặc định khác đặc tả** theo quản trị

Một số provider cho phép cấu hình QoS mặc định qua administered `ConnectionFactory` hoặc môi trường broker. Khi client tạo producer và gọi `send(message)` mà không gửi QoS explicit, giá trị hiệu lực có thể phản ánh cấu hình quản trị.

Ví dụ giả định cho mục đích phân tích:

| Tầng | Delivery mode | Priority | TTL |
| --- | --- | --- | --- |
| Giá trị mặc định API chuẩn | PERSISTENT | 4 | 0 ms |
| Provider admin đã cấu hình cho producer mới | PERSISTENT | 6 | 120.000 ms |
| Producer không tự đổi QoS rồi gọi `send(message)` | Có thể dùng bộ admin trên | Có thể dùng 6 | Có thể dùng 120.000 |

Bảng này là **kịch bản giả lập**, không có nghĩa mọi broker dùng các số đó. Cần xem tài liệu và cấu hình provider cụ thể; nếu provider không cho thay defaults, producer mới thường có bộ mặc định chuẩn.

**Chỗ phải thận trọng:** admin policy là yếu tố triển khai. Có provider cho cấu hình connection-factory default, có provider cho policy theo destination, có provider cho override send-time. Không nhầm tất cả chúng là cùng một API chuẩn.

### 5.2. Provider còn có thể override cả **giá trị client chỉ rõ**

Đặc tả Jakarta Messaging `3.4.12` cho phép quản trị viên cấu hình provider **ghi đè các giá trị mà client chỉ định** cho:

- Delivery mode.
- Priority.
- Time-to-live.
- Delivery delay.

Nếu có override, các header `JMSDeliveryMode`, `JMSPriority`, `JMSExpiration` và `JMSDeliveryTime` phải phản ánh **giá trị quản trị đã áp dụng**. Đặc tả **không chuẩn hóa** cách khai báo override và **không bắt buộc** provider phải hỗ trợ tính năng này.

Vì vậy câu “`send(message, PERSISTENT, 9, 60_000)` luôn thắng cấu hình broker” là sai ở mức đặc tả. Lập trình viên có thể **yêu cầu** QoS explicit; triển khai broker có thể có cấu hình override hợp lệ và header thực nhận khác.

### 5.3. Effective QoS và destination retention là hai chuyện

Ngay cả khi `getJMSDeliveryMode()==PERSISTENT` và `getJMSExpiration()==0`:

- Queue có thể bị áp quota, policy discard, max size, hoặc expiry do broker.
- Topic consumer không tự tồn tại khi offline: non-durable subscription có semantics riêng; durable cần được tạo đúng trước khi publish.
- Broker có thể dùng DLQ sau retry.
- Phần xử lý nghiệp vụ sau receive có thể lỗi hoặc rollback.
- Không có thông số QoS nào tự bảo đảm atomicity giữa JMS send với một database transaction độc lập.

**Header gửi chỉ cho biết chính sách gửi áp dụng**, không phải báo cáo đảm bảo end-to-end nghiệp vụ đã hoàn tất.

## 6. Spring JmsTemplate: bộ default nội bộ khác default của producer

Đây là điểm học tập cốt lõi với Spring.

`JmsTemplate` có các property `deliveryMode`, `priority`, `timeToLive`, đồng thời có flag `explicitQosEnabled`.

Các giá trị nội bộ mặc định của `JmsTemplate` phù hợp JMS:

```text
deliveryMode       = Message.DEFAULT_DELIVERY_MODE  (PERSISTENT)
priority           = Message.DEFAULT_PRIORITY       (4)
timeToLive         = Message.DEFAULT_TIME_TO_LIVE   (0)
explicitQosEnabled = false
deliveryDelay      = -1  (không gọi setDeliveryDelay lên producer)
messageIdEnabled   = true
messageTimestampEnabled = true
```

Điểm đặc biệt: **`explicitQosEnabled=false` nghĩa là Spring không chủ động gửi bộ QoS nội bộ qua overload explicit**. Nó gọi producer send dạng dùng default, cho phép producer/provider áp dụng giá trị mặc định đã cấu hình.

Theo Spring JMS `JmsTemplate`:

- `setDeliveryMode(...)`, `setPriority(...)` và `setTimeToLive(...)` cập nhật **giá trị cấu hình nằm trong template**.
- Chỉ khi `setExplicitQosEnabled(true)`, `JmsTemplate` mới dùng bộ ba này khi thực hiện `send`.
- `setQosSettings(new QosSettings(...))` là API gom cấu hình và **bật explicit QoS**.
- `setDeliveryPersistent(boolean)` chỉnh delivery mode nội bộ; nó **không** bỏ qua yêu cầu bật explicit QoS.
- `setDeliveryDelay(...)` là một cơ chế **riêng**, được truyền bằng `MessageProducer.setDeliveryDelay` khi giá trị không âm; default của Spring là `-1`, tức không đặt delay lên producer. Nó **không nằm trong ba thuộc tính được gate bởi `explicitQosEnabled`**.
- `setMessageIdEnabled(...)` và `setMessageTimestampEnabled(...)` là các hint cấu hình riêng, không thuộc bộ ba QoS explicit; provider có quyền không chấp nhận tối ưu.

### 6.1. Bảng đối chiếu cấu hình Spring

| Spring config | Cách Spring xử lý ở phía client | Điều không được khẳng định |
| --- | --- | --- |
| `new JmsTemplate(cf)`, không sửa QoS | Dùng producer defaults khi send | Broker luôn đúng 2/4/0 |
| `setPriority(8)`, **không bật** explicit | Priority 8 nằm trong template nhưng send không truyền override 8 | Message thực tế luôn priority 8 |
| `setTimeToLive(15_000)`, explicit vẫn false | TTL 15s không được đưa vào overload explicit | Message chắc chắn hết hạn sau 15s |
| `setDeliveryMode(NON_PERSISTENT)`, explicit vẫn false | Chỉ đặt giá trị nội bộ | Message chắc chắn NON_PERSISTENT |
| `setExplicitQosEnabled(true)` | Gọi send với mode/priority/TTL của template | Admin provider không thể override |
| `setQosSettings(settings)` | Chọn mode/priority/TTL và bật explicit QoS | Loại bỏ mọi broker policy |
| `setDeliveryDelay(2_000)` | Spring đặt producer delivery delay 2s khi gửi | DeliveryDelay nhất thiết phải thuộc flag explicit QoS |
| `setDeliveryDelay(-1)` | Không đặt delivery delay từ Spring | Broker sẽ luôn dùng delay bằng 0 |
| `setMessageIdEnabled(false)` | Đưa hint tắt message ID tới producer | ID chắc chắn null |
| `setMessageTimestampEnabled(false)` | Đưa hint tắt timestamp tới producer | Timestamp chắc chắn bằng 0 |

**Hai giá trị trông như default đều tồn tại:** Spring có field `priority=4`, nhưng nếu `explicitQosEnabled=false`, Spring **không nhất thiết dùng field đó để override producer**. Đừng debug bằng cách đọc `getPriority()` trên bean `JmsTemplate` rồi kết luận header ở consumer là 4.

### 6.2. Flow của JmsTemplate gần với logic nào?

Mô hình giản lược theo implementation Spring:

```java
// PSEUDOCODE để giải thích, không phải file Java chạy độc lập.
if (deliveryDelay >= 0) {
    producer.setDeliveryDelay(deliveryDelay);
}

if (explicitQosEnabled) {
    producer.send(message, deliveryMode, priority, timeToLive);
} else {
    producer.send(message); // dùng producer/provider defaults
}
```

Sự khác nhau nằm ở **overload `send`**. Đúng đường gọi quan trọng hơn việc fields trong template có số 4/0/2 mặc định.

Để khẳng định broker thực nhận gì, **xem message headers ở send/receive cùng tài liệu provider**, không suy diễn từ code trên.

## 7. Spring JMS: hai template cho hai chính sách gửi

Ví dụ sử dụng Spring Framework 6+ hoặc 7+, Java 17+, namespace `jakarta.jms`, `spring-jms` và một `ConnectionFactory` đã cấu hình. Các file dưới đây **là các class thuộc project Spring cùng broker**, không thể biên dịch bằng `javac` JDK thuần vì cần dependencies, container và destination thật.

Giả định có queue `billing.jobs` tồn tại hoặc broker cho phép auto-create theo chính sách.

### 7.1. Bean thứ nhất: để provider dùng defaults

**File `QosSenderConfiguration.java`:**

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class QosSenderConfiguration {

    @Bean("providerDefaultsTemplate")
    public JmsTemplate providerDefaultsTemplate(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setPubSubDomain(false);
        // explicitQosEnabled mặc định false.
        // Không đặt mode/priority/TTL lên producer khi send.
        return template;
    }

    @Bean("applicationQosTemplate")
    public JmsTemplate applicationQosTemplate(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setPubSubDomain(false);

        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(7);
        template.setTimeToLive(60_000L);
        template.setExplicitQosEnabled(true);

        // Delivery delay là cấu hình riêng, không phải bộ ba QoS.
        template.setDeliveryDelay(2_000L);
        return template;
    }

    @Bean("jmsListenerContainerFactory")
    public DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setSessionTransacted(true);
        factory.setPubSubDomain(false);
        return factory;
    }
}
```

**Giải thích:**

- Hai template có **policy ổn định khác nhau**; không đổi `setPriority(...)` trên cùng một singleton mỗi request, gây race khi nhiều thread cùng gửi.
- Template `providerDefaultsTemplate` không chủ động chỉ định 2/4/0 dù fields nội bộ có giá trị đó. Provider/ConnectionFactory quản lý defaults của producer.
- Template `applicationQosTemplate` **yêu cầu** PERSISTENT, priority 7, TTL 60 giây cho mỗi send; delivery delay 2 giây. Broker admin vẫn có thể override nếu hỗ trợ và được cấu hình.
- Listener factory có local JMS transaction cho tiêu thụ; nó không làm hai template producer có chung một transaction DB.
- `@EnableJms` bật phát hiện `@JmsListener`; tên bean `jmsListenerContainerFactory` làm default factory cho ví dụ.

### 7.2. Producer dùng từng policy

**File `BillingSender.java`:**

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public final class BillingSender {

    private final JmsTemplate providerDefaultsTemplate;
    private final JmsTemplate applicationQosTemplate;

    public BillingSender(
            @Qualifier("providerDefaultsTemplate")
            JmsTemplate providerDefaultsTemplate,
            @Qualifier("applicationQosTemplate")
            JmsTemplate applicationQosTemplate) {
        this.providerDefaultsTemplate = providerDefaultsTemplate;
        this.applicationQosTemplate = applicationQosTemplate;
    }

    public void sendNormal(String invoiceId) {
        providerDefaultsTemplate.convertAndSend(
                "billing.jobs", invoiceId);
    }

    public void sendUrgent(String invoiceId) {
        applicationQosTemplate.convertAndSend(
                "billing.jobs",
                invoiceId,
                message -> {
                    message.setStringProperty("kind", "URGENT");
                    return message;
                });
    }
}
```

Ở đây `String` được `SimpleMessageConverter` mặc định chuyển thành `TextMessage`. `kind` là property ứng dụng, **không tự tạo JMS priority hay delivery mode**. Với `sendUrgent`, template truyền bộ QoS explicit, không phải vì property `kind="URGENT"`.

Một message gửi thành công **chưa có nghĩa listener hoàn tất nghiệp vụ**. Cần quan sát ack/commit, retry và tác dụng phụ.

### 7.3. Consumer kiểm tra **header thật**

**File `BillingQosInspector.java`:**

```java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public final class BillingQosInspector {

    @JmsListener(destination = "billing.jobs")
    public void inspect(Message message) throws JMSException {
        String deliveryMode =
                message.getJMSDeliveryMode() == DeliveryMode.PERSISTENT
                        ? "PERSISTENT" : "NON_PERSISTENT";

        System.out.println("messageId=" + message.getJMSMessageID());
        System.out.println("mode=" + deliveryMode);
        System.out.println("priority=" + message.getJMSPriority());
        System.out.println("expiration=" + message.getJMSExpiration());
        System.out.println("deliveryTime=" + message.getJMSDeliveryTime());
        System.out.println("redelivered=" + message.getJMSRedelivered());
    }
}
```

Listener nhận raw `jakarta.jms.Message` để đọc header. **Không ghi stdout cố định**: message ID, thời điểm, override broker, delivery mode/priority và redelivery phụ thuộc runtime.

Để có kết luận:

1. Gửi một message bằng `sendNormal`.
2. Gửi một message bằng `sendUrgent`.
3. Đọc **đúng message** bằng ID hoặc business key, so sánh mode/priority/expiration/deliveryTime giữa hai policy.
4. Nếu priority thực nhận khác 7, kiểm tra admin overrides, provider SDK config, template thực được inject và có đúng version library hay không.
5. Nếu TTL/delay không đúng kỳ vọng, đọc timeline của send, broker timing, clock và các policy expiration/delay.

### 7.4. Một ví dụ bẫy quen thuộc

```java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setPriority(9);
template.setTimeToLive(5_000L);
template.setDeliveryMode(DeliveryMode.NON_PERSISTENT);

// Chưa có template.setExplicitQosEnabled(true)!
template.convertAndSend("billing.jobs", "invoice-42");
```

Bẫy: developer nhìn code tưởng đã cấu hình QoS; thực tế Spring vẫn **gửi theo default của producer/provider**. Nếu ConnectionFactory được quản trị default PERSISTENT, priority 4, TTL 0, message có thể vẫn dùng PERSISTENT/4/0.

**Sửa:**

```java
template.setExplicitQosEnabled(true);
```

Sửa này khiến **client gửi QoS được yêu cầu**. Nếu provider đã có admin override tường minh thì phải kiểm tra chính sách quản trị; đừng nói “bật true là bảo đảm tuyệt đối”.

### 7.5. QosSettings gộp cấu hình

`JmsTemplate` còn hỗ trợ `setQosSettings(QosSettings)` để gom deliveryMode, priority và TTL:

```java
import jakarta.jms.DeliveryMode;
import org.springframework.jms.support.QosSettings;

template.setQosSettings(
        new QosSettings(DeliveryMode.PERSISTENT, 7, 60_000L));
```

Đoạn code thuộc project Spring JMS và giả định `template` đã được tạo. `setQosSettings` bật `explicitQosEnabled` trong implementation, khác với ba setter riêng. Khi dùng, kiểm tra đúng constructor/API ở version Spring của project. Không suy ra nó tự đặt delivery delay, disable ID/timestamp hoặc thay đổi provider retention.

## 8. Đọc header đúng thời điểm, tính TTL và delay

Giả định provider không admin override và dùng send time `t0`.

```text
t0 = 1 700 000 000 000 ms (giá trị ví dụ)

Producer / send:
  deliveryMode   = PERSISTENT
  priority       = 7
  timeToLive     = 60 000 ms
  deliveryDelay  = 2 000 ms

Provider-managed headers:
  JMSDeliveryMode = PERSISTENT
  JMSPriority     = 7
  JMSExpiration   = t0 + 60 000
  JMSDeliveryTime = t0 + 2 000
  JMSTimestamp    = gần thời điểm provider nhận yêu cầu gửi
```

Hệ thống thực có thể dùng thời gian gửi không trùng tuyệt đối với thời điểm code gọi `System.currentTimeMillis()`. Với transacted send, `JMSDeliveryTime` tính theo thời điểm **client send**, không phải chờ transaction commit rồi mới bắt đầu cộng delay. `JMSTimestamp` cũng đại diện thời điểm handoff cho provider, không nhất thiết là thời điểm message được thực tế truyền trên mạng hoặc consumer nhận.

### 8.1. Cách diễn giải các header

| Header | Ai quyết định lúc send? | Lưu ý |
| --- | --- | --- |
| `JMSDeliveryMode` | Provider dựa trên QoS được chọn hoặc admin override | Đọc được mode thực tế; không chứng minh nghiệp vụ exactly-once |
| `JMSPriority` | Provider dựa trên priority được chọn/override | Không bảo đảm strict processing order |
| `JMSExpiration` | Provider tính theo send time và TTL thực áp dụng | `0` nghĩa không expiry vì TTL |
| `JMSDeliveryTime` | Provider tính theo send time + delivery delay | Không được giao trước thời điểm này; không hứa giao đúng mili giây đó |
| `JMSTimestamp` | Provider gán khi gửi, trừ hint disable được chấp nhận | Không thay thế business event time |
| `JMSMessageID` | Provider tạo khi gửi, trừ hint disable được chấp nhận | Không thay thế business idempotency key |
| `JMSDestination` | Provider thể hiện đích gửi | Không lấy message.setJMSDestination để route |
| `JMSRedelivered` | Provider đặt khi redeliver | Phục vụ quan sát, không thay thế dedupe/transaction |

Một application-specific property như `message.setIntProperty("desiredPriority", 9)` **không tự chuyển thành** `JMSPriority=9`. Nếu muốn business metadata, cứ dùng property; nếu muốn JMS priority, dùng producer/template QoS.

### 8.2. TTL và delay cùng tác động đến message

Bảng ví dụ giả sử không admin override:

| TTL | Delay | Kết quả khả dĩ |
| --- | --- | --- |
| 0 ms | 0 ms | Có thể giao ngay khi broker sẵn sàng; không hết hạn theo TTL |
| 60.000 ms | 0 ms | Giao sớm, nhưng không giao sau thời điểm expired |
| 60.000 ms | 2.000 ms | Chỉ đủ điều kiện giao từ 2 giây, hết hạn sau 60 giây |
| 3.000 ms | 5.000 ms | Message có thể hết hạn **trước khi** đủ điều kiện giao |
| 0 ms | 10.000 ms | Không TTL expiry, nhưng chỉ đủ điều kiện từ 10 giây |
| 1.000 ms | 0 ms | Có thể hết hạn trong backlog nếu consumer chậm |

Không đặt TTL cực ngắn cho thông điệp bắt buộc xử lý nhưng có backlog lớn. Ngược lại, TTL=0 cho mọi event tạm thời có thể tăng backlog và chi phí lưu trữ. Chính sách nên theo **SLA nghiệp vụ** và khả năng consumer, không theo phỏng đoán “để 0 là an toàn nhất”.

## 9. Kiểm soát quyền và trách nhiệm giữa các lớp

### 9.1. Producer API chịu trách nhiệm gì?

- Tạo message, chọn destination, gọi send.
- Đặt default QoS hoặc per-send QoS.
- Cung cấp application properties như `businessId` và `eventType`.
- Thực hiện transaction phía producer nếu được cấu hình.
- Nhận lỗi send; khi kết quả không chắc chắn, quyết định retry có idempotency.

Producer **không** thể tự biến broker thành một kho message vô hạn, tự đảm bảo subscriber online hay buộc provider hỗ trợ override cấu hình theo ý mình.

### 9.2. Provider/broker chịu trách nhiệm gì?

- Triển khai giao thức/semantics JMS.
- Cấp `ConnectionFactory`/connection/session/producer/destination phù hợp.
- Gán message IDs, timestamps, delivery-related headers theo đặc tả.
- Thực hiện delay, expiration, priority theo hợp đồng và policy hỗ trợ.
- Áp dụng admin defaults hoặc overrides nếu provider hỗ trợ.
- Quản lý quota, retention, DLQ, rights, topic subscription backlog, persistence thực tế.
- Cung cấp console/metric/log để quan sát message đã enqueue, expired, redelivered hay rejected.

Không đem hành vi **một broker cụ thể** (ví dụ tự tạo queue, priority ordering chính xác, TTL redirection) suy rộng thành quy tắc của toàn Jakarta Messaging.

### 9.3. Ứng dụng/Spring chịu trách nhiệm gì?

- Chọn policy theo nghiệp vụ: event nào bắt buộc, chấp nhận mất hay không, thời hạn còn giá trị, có độ ưu tiên gấp không.
- Biến policy thành cấu hình `JmsTemplate` hoặc `JMSProducer` đúng.
- Quản lý `ConnectionFactory`, profiles, secrets, namespace, destination, logging và tracing.
- Duy trì idempotency, retry, outbox/transaction khi có dual write.
- Viết integration tests xác nhận QoS thực tế tại destination/consumer.
- Giám sát sender errors, broker quota/backlog/expiration/DLQ và business completion.

Một application property như `"priority"=9` hoặc `"ttlSeconds"=10` trong DTO **không có hiệu lực JMS** nếu code không chuyển nó vào producer QoS. Ngược lại, một chính sách broker “TTL tối đa 30 giây” có thể ảnh hưởng kể cả khi ứng dụng yêu cầu 60 giây theo cơ chế quản trị hỗ trợ.

## 10. Thứ tự quyết định: dùng mô hình đúng, tránh luật ưu tiên giả

Khi thấy giá trị cuối khác mong đợi, làm theo thứ tự phân tích **nguồn yêu cầu → lời gọi send → header thực tế**, không giả định luật tuyệt đối:

### Bước 1. Tìm người khởi tạo

- Code có gọi `new JmsTemplate(connectionFactory)` hay inject template khác?
- Có dùng `setQosSettings`? `setExplicitQosEnabled`?
- Có setter QoS trên `JMSProducer`/`MessageProducer`?
- Có per-send `send(..., mode, priority, ttl)`?
- Đang gửi qua method nào? `JmsTemplate.send` hay `convertAndSend`?

### Bước 2. Xác định QoS client **thực sự yêu cầu**

- `JmsTemplate` explicit=false → producer send defaults.
- `JmsTemplate` explicit=true → mode/priority/TTL theo template.
- `setDeliveryDelay` trong Spring với giá trị không âm → producer delay được đặt; mặc định -1 thì không.
- Per-send QoS classic API → yêu cầu ba giá trị cho đúng lần gửi đó.
- Setter header trực tiếp trên `Message` → **không phải** yêu cầu QoS hợp lệ.

### Bước 3. Xác định khả năng override bên provider

- Default trong `ConnectionFactory` có khác hằng số Jakarta Messaging không?
- Có admin policy thay client-specified QoS?
- Có destination-specific TTL/priority/delivery policy?
- Có quota, retention, permission hoặc scheduling behavior riêng?

### Bước 4. Đọc header và kết quả vận hành

- Ở sender sau synchronous send hoặc ở consumer: đọc mode, priority, expiration và deliveryTime.
- Kiểm tra backlog, priority distribution, expiration count, retention/DLQ, số subscriber và transaction.
- Khác biệt phải được phân loại: **Spring không truyền**, **producer default khác**, **provider admin override** hoặc **broker retention/failure**.
- Không coi log “send done” là xác nhận nghiệp vụ hoàn tất.

### Ma trận tình huống minh họa

Bảng dưới dùng **policy giả định của provider**: nếu không có explicit client QoS, producer có PERSISTENT / priority 6 / TTL 120 giây. Nếu có **admin override cưỡng chế**, provider đặt mode PERSISTENT / priority 5 / TTL 30 giây. Không khẳng định provider thực tế nào có cả hai chế độ.

| Trường hợp | Client yêu cầu | Kết quả cần kiểm chứng |
| --- | --- | --- |
| JMS producer mới, **không có** policy admin | Spec default P / 4 / 0 | Thường P / 4 / 0 |
| JMS producer mới, provider có admin default | Producer có thể nhận P / 6 / 120s | Có thể P / 6 / 120s |
| Spring setPriority(8), explicit=false | Producer defaults, **không yêu cầu 8** | Có thể vẫn P / 6 / 120s |
| Spring setPriority(8), TTL 60s, explicit=true | QoS của Spring được chuyển vào send | Thường priority 8 / TTL 60s nếu không admin override |
| JMS send explicit(priority=9, TTL=5s) | Giá trị của lần send cụ thể | Thường 9 / 5s nếu không admin override |
| Bất kỳ trường hợp nào, provider áp admin override | Bên client có thể yêu cầu khác | Header phản ánh admin values |
| Spring setDeliveryDelay(2s), explicit=false | Spring vẫn đặt producer delay 2s | Có thể là 2s; kiểm tra admin override và header |

Không sử dụng bảng để tiên đoán một broker chưa kiểm thử. Nó chỉ giúp xác định **điểm nào cần nhìn** khi debug.

## 11. Ví dụ Java 17 chạy độc lập: mô phỏng các lớp QoS

Đoạn dưới minh họa **cách suy luận**, không phải implementation JMS. Nó chạy chỉ bằng JDK 17, không gửi message, không có broker và không tuyên bố mô phỏng mọi quy tắc của provider. Các policy admin chỉ là **dữ liệu giả lập**.

Tạo tệp **`JmsQosLayersDemo.java`**:

```java
public final class JmsQosLayersDemo {

    record Qos(String mode, int priority, long ttlMs) {
        @Override
        public String toString() {
            return "mode=" + mode
                    + ", priority=" + priority
                    + ", ttlMs=" + ttlMs;
        }
    }

    static Qos chooseClientRequest(
            Qos producerDefaults,
            Qos applicationSettings,
            boolean explicitQosEnabled) {
        return explicitQosEnabled
                ? applicationSettings : producerDefaults;
    }

    static Qos optionalAdminOverride(
            Qos clientRequest, Qos enforcedByAdmin) {
        // Mô phỏng provider có chính sách ghi đè mọi trường.
        return enforcedByAdmin == null
                ? clientRequest : enforcedByAdmin;
    }

    public static void main(String[] args) {
        Qos jakartaSpec = new Qos("PERSISTENT", 4, 0);
        Qos providerDefaults = new Qos("PERSISTENT", 6, 120_000);
        Qos application = new Qos("NON_PERSISTENT", 8, 15_000);
        Qos adminEnforced = new Qos("PERSISTENT", 5, 30_000);

        Qos implicit = chooseClientRequest(
                providerDefaults, application, false);
        Qos explicit = chooseClientRequest(
                providerDefaults, application, true);

        System.out.println("JMS spec: " + jakartaSpec);
        System.out.println("Spring explicit=false: " + implicit);
        System.out.println("Spring explicit=true: " + explicit);
        System.out.println("After optional admin override: "
                + optionalAdminOverride(explicit, adminEnforced));
    }
}
```

Chạy:

```bash
javac JmsQosLayersDemo.java
java JmsQosLayersDemo
```

**Stdout chính xác:**

```text
JMS spec: mode=PERSISTENT, priority=4, ttlMs=0
Spring explicit=false: mode=PERSISTENT, priority=6, ttlMs=120000
Spring explicit=true: mode=NON_PERSISTENT, priority=8, ttlMs=15000
After optional admin override: mode=PERSISTENT, priority=5, ttlMs=30000
```

**Phải hiểu giới hạn của ví dụ:** đây là model minh họa **giả định** một provider đã đổi producer default và có quyền admin override. Nó không phát hiện provider từ runtime, không xác nhận mọi provider thực hiện cùng thuật toán, không thay thế JMS send/receive test. Giá trị cần học là: khi Spring explicit=false, application settings không tự động được dùng để override producer defaults; khi explicit=true, client phát yêu cầu QoS; admin override nếu được provider hỗ trợ vẫn có thể làm header thực tế khác.

### Vì sao cần demo này?

Nếu có bug “đã đặt priority 8 nhưng consumer thấy 6”:

- Đừng ngay lập tức kết luận provider vi phạm chuẩn.
- Kiểm tra Spring có dùng explicit QoS không.
- Kiểm tra producer default được quản trị hay không.
- Kiểm tra override của admin có áp dụng sau send không.
- Kiểm tra receiver đọc đúng `JMSPriority` của message tương ứng.

Đó là cách debug **theo bằng chứng**, không theo việc đặt một setter.

## 12. Quan hệ với Transaction, retry, ordering và business QoS

### 12.1. Gửi persistent không tự giải quyết dual write

Ví dụ OrderService:

1. Commit một đơn hàng vào database.
2. Publish `OrderCreated` lên topic/queue.
3. Nếu crash ở giữa, dữ liệu DB và message broker không nhất quán.

Việc chọn `PERSISTENT` ở producer chỉ điều khiển **delivery mode của message được gửi**; nó không đảm bảo atomicity giữa DB commit và JMS send. Dùng transactional outbox hoặc kiến trúc giao dịch phối hợp phù hợp; mọi retry phải có idempotency key.

### 12.2. Priority không bảo đảm thứ tự thực thi giữa nhiều worker

Một message priority 9 có thể đi trước message priority 4 trong broker, nhưng ordering cuối cùng còn phụ thuộc enqueue time, consumer prefetch, selector, concurrency, transaction và redelivery. Priority là **tín hiệu ưu tiên**, không phải cơ chế giải quyết race condition hoặc deadline.

Nếu SLA yêu cầu ưu tiên mạnh, cân nhắc queue riêng, số worker riêng, rate limit, backpressure và điều phối priority được provider hỗ trợ, thay vì chỉ đặt mọi message “gấp” = 9.

### 12.3. TTL cần phản ánh tuổi thọ nghiệp vụ

- Email kích hoạt tài khoản hết hiệu lực sau 15 phút: TTL có thể có ý nghĩa, nhưng business token expiry vẫn phải được xác minh ở consumer.
- Event audit bắt buộc không bỏ lỡ: TTL ngắn có thể nguy hiểm, trong khi lưu giữ quá lâu gây backlog. Cần policy retention và cơ chế xử lý failure riêng.
- Job khởi chạy sau 30 giây: delivery delay 30 giây và TTL 5 giây tạo mâu thuẫn, có nguy cơ hết hạn trước khi giao.
- Job tốn 10 phút để xử lý: TTL quyết định **deadline để delivery bắt đầu**, không nhất thiết là timeout của business processing sau khi message đã nhận; hai hạn cần tách.

### 12.4. Message ID không phải idempotency key

`JMSMessageID` do provider gán trên send và có thể thay đổi khi client retry bằng một message mới. Đừng chỉ dùng JMSMessageID để xác định hai request nghiệp vụ là cùng một hành động. Dùng `eventId` hoặc `requestId` ổn định do ứng dụng sinh, đưa vào message property/body và lưu kết quả xử lý idempotent.

### 12.5. Persistent delivery không thay thế durable subscription

Với topic, consumer non-durable offline có thể bỏ lỡ event dù producer gửi `PERSISTENT`. Durable subscription được tạo trước, danh tính ổn định và broker retention policy mới là một phần của giải pháp nhận event khi offline. Không nhầm “message persistence” với “subscription durability”.

## 13. Checklist kiểm thử trực tiếp trên broker

### Test A — Đo bộ mặc định của producer

1. Tạo một `MessageProducer`/`JMSProducer` mới trong application không có override QoS.
2. Đọc getters producer: mode, priority, TTL, delay.
3. Gửi message có `businessId` riêng.
4. Ở consumer đọc mode, priority, expiration và delivery time.
5. So sánh với bộ chuẩn PERSISTENT/4/0/0 và các cấu hình admin từ `ConnectionFactory`/broker.

Nếu provider không sử dụng bộ mặc định spec, cần xác minh xem có cấu hình quản trị được hỗ trợ không; không tự sửa mọi producer bằng hard-coded constants trước khi hiểu chính sách.

### Test B — Spring setter không có explicit flag

1. Tạo `JmsTemplate` có `setPriority(8)`, `setTimeToLive(10_000)` nhưng **không** `setExplicitQosEnabled(true)`.
2. Gửi message test có business ID.
3. Ở consumer đọc `JMSPriority` và `JMSExpiration`.
4. Quan sát chúng có thể phản ánh default producer/provider chứ không phản ánh số 8/10s.
5. Lặp lại với explicit=true và so sánh.

Đây là test quan trọng vì cách đọc source code dễ tưởng setter luôn có hiệu lực.

### Test C — Administrative override

1. Chỉ trong môi trường thử nghiệm, kiểm tra broker/provider có hỗ trợ admin override QoS không.
2. Nếu có, cấu hình ví dụ priority được cưỡng chế là 5.
3. Client cố gửi explicit priority 8.
4. Xem header sau send và tại consumer.
5. Xác minh header **phản ánh giá trị quản trị** nếu provider áp dụng override theo đặc tả.
6. Gỡ policy test để không ảnh hưởng message của ứng dụng khác.

Đừng cố chạy test này trên môi trường production không được phép thay đổi policy.

### Test D — TTL và delivery delay

1. Gửi message X với TTL 30s, delay 2s.
2. Gửi message Y với TTL 1s, delay 5s.
3. Ghi nhận `JMSTimestamp`/`JMSDeliveryTime`/`JMSExpiration`.
4. Kiểm tra X không được giao trước deliveryTime; Y không được giao nếu expired trước khi được phép delivery.
5. Quan sát broker expired counters và policy xử lý expired; không suy đoán dựa trên thời gian ngủ ở thread consumer.

### Test E — Gửi persistent nhưng consumer lỗi

1. Gửi message PERSISTENT vào queue có policy retention đủ phù hợp.
2. Consumer nhận nhưng cố tình fail trước ack/commit.
3. Quan sát rollback/redelivery, `JMSRedelivered` và `JMSXDeliveryCount` nếu được provider cung cấp.
4. Lặp lại một lần thành công với business idempotency.
5. Chứng minh persistent không giải quyết xử lý lặp ở business layer.

### Test F — Không có broker message đủ để chứng minh

1. Đọc event ID duy nhất trên sender.
2. Quan sát broker accepted/enqueued hoặc delivery counters.
3. Xác định consumer đã commit, trạng thái DB đã cập nhật.
4. Đo latency, backlog, expired count, DLQ và time-to-complete.
5. Phân biệt “send ok” với “processed exactly once” khi viết SLO.

## 14. Các lỗi phổ biến và cách sửa

**Lỗi 1: “Mặc định JMS là priority 4 nên production chắc chắn priority 4.”**

Chưa đúng. Đó là **spec default producer**, provider có thể cho cấu hình administered default/override. Cần đọc QoS thực nhận.

**Lỗi 2: “`JmsTemplate.setPriority(9)` đã đủ.”**

Không. Với `explicitQosEnabled=false`, Spring không dùng field priority của template làm explicit send value. Bật `setExplicitQosEnabled(true)` nếu đó là policy mong muốn.

**Lỗi 3: “Bật explicit QoS là bảo đảm thắng mọi policy broker.”**

Sai. Đặc tả cho phép admin override client-specified mode/priority/TTL/delay. Client chỉ có thể yêu cầu; kiểm chứng trên broker.

**Lỗi 4: “`setTimeToLive(0)` giúp message tồn tại mãi mãi.”**

Sai. Không expiry theo TTL, nhưng retention, quota, failure, topic subscription và cách consumer xử lý vẫn có thể khiến message không tồn tại như kỳ vọng.

**Lỗi 5: “DeliveryDelay 5s và TTL 2s vẫn được gửi sau 5s.”**

Không. Message có nguy cơ hết hạn trước earliest delivery. Phải xét cả hai trên cùng mốc send.

**Lỗi 6: “Muốn priority 9 chỉ cần `message.setJMSPriority(9)`.”**

Sai. `JMSPriority` là provider-managed header; truyền QoS qua producer/template. Setter header trên `Message` không phải cách portable để điều khiển send priority.

**Lỗi 7: “`JMSPriority` là thứ tự FIFO có thể kiểm chứng tuyệt đối.”**

Sai. JMS không bắt strict priority ordering; provider cố gắng ưu tiên theo mức, nhưng concurrent consumers có thể xử lý khác trình tự.

**Lỗi 8: “`setDeliveryDelay` luôn cần bật `explicitQosEnabled`.”**

Không đúng với implementation `JmsTemplate` hiện tại. Delay là cấu hình riêng; giá trị `>=0` được truyền vào producer ngay trước send, còn explicit flag kiểm soát **mode, priority, TTL**.

**Lỗi 9: “`setMessageIdEnabled(false)` làm JMSMessageID chắc chắn null.”**

Không. Đây là optimization hint. Provider có thể bỏ qua và vẫn gán ID.

**Lỗi 10: “Topic persistent đồng nghĩa mọi subscriber offline được nhận event.”**

Sai. Durable subscription là khái niệm riêng; subscriber non-durable có thể bỏ lỡ event đã publish khi không active.

**Lỗi 11: “Mỗi `JMSMessageID` trùng nghĩa là cùng nghiệp vụ.”**

Không. App phải thiết kế business ID; message ID của provider không tự giúp dedupe retry của cùng một hành động nghiệp vụ.

**Lỗi 12: “Đổi QoS setter trên một JmsTemplate singleton giữa các request là an toàn.”**

Không nên. `JmsTemplate` thread-safe **sau khi cấu hình xong**. Không biến cấu hình bean thành state thay đổi theo request concurrent; dùng template riêng theo policy hoặc cơ chế thiết kế an toàn.

**Lỗi 13: “Broker có backlog thì chỉ cần tăng priority.”**

Không đủ. Backlog có thể do thiếu consumer, xử lý chậm, DB lock, invalid schema, retry/DLQ hoặc quota. Dùng metric và root cause analysis, không mặc định QoS priority chữa được throughput.

## 15. Checklist thiết kế policy gửi trong ứng dụng

Trước khi merge một thay đổi liên quan JMS send, xác nhận:

- [ ] Đã xác định loại message và SLA thật: mất được không, deadline bao lâu, backlog tối đa bao nhiêu?
- [ ] Biết **JMS API defaults** của producer: PERSISTENT, priority 4, TTL 0, delay 0?
- [ ] Đã kiểm tra **producer effective defaults** từ provider/ConnectionFactory và admin docs?
- [ ] Trong Spring, có chủ động chọn `explicitQosEnabled` đúng mục đích không?
- [ ] Nếu explicit=true, đã cấu hình đủ **mode, priority, TTL**, không chỉ một field bỏ quên default?
- [ ] `setDeliveryDelay` có được xử lý riêng và có tương thích TTL?
- [ ] Có admin override nào ghi đè ngay cả explicit client QoS không?
- [ ] `JMSExpiration`/`JMSDeliveryTime` đã được đối chiếu trên message thực chưa?
- [ ] Priority 0–9 có chính sách nhất quán, không lạm dụng 9?
- [ ] Đã phân biệt message expiration với business deadline/timeout chưa?
- [ ] Đã phân biệt PERSISTENT với retention, durable subscription và business exactly-once?
- [ ] Có monitoring queue depth, expired count, redelivery, DLQ, sender errors và processing latency?
- [ ] Có idempotency key/transaction/outbox khi message tạo side effect hoặc cần nhất quán DB/JMS?
- [ ] Không phụ thuộc vào disable ID/timestamp hints cho logic bắt buộc?
- [ ] Đã viết integration test với provider và runtime config **thực tế**?

### Quy ước hữu ích cho team

Nên định nghĩa QoS **theo loại thông điệp** thay vì theo thói quen developer:

| Loại nghiệp vụ (ví dụ) | Định hướng policy cần thảo luận | Phải kiểm chứng thêm |
| --- | --- | --- |
| Cập nhật audit bắt buộc | Ưu tiên không mất, retention đủ, durable consumer | DB/JMS consistency, retry, DLQ |
| Nhắc nhở sắp hết hạn | TTL theo thời gian còn hữu ích | Backlog, expiry xử lý an toàn |
| Metrics/heartbeat không quan trọng | Có thể chấp nhận NON_PERSISTENT nếu mất được | Provider failure, throughput |
| Task cần xử lý gấp | Priority tương đối cao có điều kiện | Queue load, fairness, starvation |
| Job trì hoãn 30s | Delivery delay 30s, TTL phải phù hợp | Earliest delivery, clock và scheduling |

Đây chỉ là **định hướng phân tích**, không phải thông số cứng cho mọi hệ thống. TTL, mode và priority cuối cùng cần căn cứ SLA, provider support và test.

## 16. Tự kiểm tra kiến thức

**Câu 1.** Một `MessageProducer` mới theo mặc định JMS dùng delivery mode, priority, TTL và delay gì?

**Đáp án:** PERSISTENT, priority 4, TTL 0 ms (không expire vì TTL), delivery delay 0 ms.

**Câu 2.** Vì sao không thể kết luận mọi message ở production có bộ default trên?

**Đáp án:** Provider/ConnectionFactory có thể cấu hình administered defaults và đặc tả cho phép admin override một số client-specified QoS. Phải quan sát runtime.

**Câu 3.** Spring có `template.setPriority(9)` nhưng chưa bật explicit. Lời gọi `convertAndSend` chắc chắn gửi priority 9 không?

**Đáp án:** Không. `JmsTemplate` không truyền bộ ba QoS của template khi `explicitQosEnabled=false`.

**Câu 4.** Bật `template.setExplicitQosEnabled(true)` thay đổi điều gì?

**Đáp án:** Spring chuyển delivery mode, priority và TTL của template vào overload producer send explicit. Nó không làm provider admin override trở thành bất hợp lệ.

**Câu 5.** `MessageProducer.setPriority(7)` và `producer.send(message, PERSISTENT, 9, 5000)` khác nhau ở đâu?

**Đáp án:** Setter thay producer default; overload send tường minh chỉ định priority 9/TTL 5 giây/mode cho lần gửi đó. Lần `send(message)` tiếp theo vẫn dùng producer default, nếu không thay đổi.

**Câu 6.** `message.setJMSPriority(9)` có phải cách portable để gửi priority 9 không?

**Đáp án:** Không. Header do provider gán khi send. Hãy dùng producer QoS hoặc Spring template với explicit=true.

**Câu 7.** `setDeliveryDelay(2_000)` của Spring có bị gate bởi `explicitQosEnabled` không?

**Đáp án:** Không trong implementation `JmsTemplate` đang mô tả; Spring đặt producer delay khi giá trị không âm, còn explicit flag kiểm soát mode/priority/TTL.

**Câu 8.** Message có TTL 1 giây, delay 5 giây; có chắc consumer nhận sau 5 giây không?

**Đáp án:** Không. Nó có thể hết hạn trước khi được phép giao, nên không nên dùng hai giá trị mâu thuẫn như vậy.

**Câu 9.** `JMSExpiration=0` cho biết điều gì?

**Đáp án:** Không đặt thời điểm hết hạn theo TTL của JMS. Nó không hứa broker giữ message vĩnh viễn bất kể retention/quota.

**Câu 10.** Vì sao `priority=9` không bảo đảm thứ tự xử lý chính xác của worker?

**Đáp án:** Provider không bị bắt strict priority ordering; concurrency, prefetch, selectors, retry và nhiều consumer ảnh hưởng thứ tự.

**Câu 11.** Admin broker ép priority 5 dù client explicit priority 9. Message received có được phản ánh priority 5 không?

**Đáp án:** Nếu provider hỗ trợ và áp dụng admin override theo đặc tả, `JMSPriority` phải phản ánh giá trị admin đã chọn.

**Câu 12.** Producer gửi PERSISTENT vào topic, consumer non-durable tắt. Consumer khởi động lại có mặc nhiên nhận event bị bỏ lỡ không?

**Đáp án:** Không. Durable subscription là yêu cầu riêng.

**Câu 13.** `JMSMessageID` có phải idempotency key bền vững cho cùng một business operation được retry không?

**Đáp án:** Không. Có thể retry thành message khác với JMSMessageID khác; dùng business event/request ID do ứng dụng quản lý.

**Câu 14.** Tại sao cần quan sát QoS header ở consumer chứ không chỉ đọc config bean?

**Đáp án:** Header phản ánh QoS do provider thực sự áp dụng (bao gồm admin override), trong khi bean chỉ cho biết ý định/cấu hình phía Spring.

**Câu 15.** Một job gửi JMS thành công nhưng database update của consumer thất bại. Chọn PERSISTENT có tự sửa lỗi business không?

**Đáp án:** Không. Cần transaction/ack phù hợp, retry và idempotency; với dual write cần cơ chế nhất quán như outbox.

## Tóm tắt trọng tâm

**Có ba khái niệm “mặc định” khác nhau:**

- **Producer/JMS API default:** PERSISTENT, priority 4, TTL 0, delivery delay 0; hằng số chuẩn mô tả trạng thái ban đầu khi không có cấu hình khác.
- **Provider/broker-admin default/policy:** có thể định hình producer defaults hoặc override client-specified QoS nếu implementation hỗ trợ; còn quản lý retention, quota và destination semantics.
- **Application/Spring policy:** business requirements và cấu hình `JmsTemplate`; khi `explicitQosEnabled=false`, các field mode/priority/TTL của template không được đưa thành explicit send parameters; `true` thì có. Delay dùng đường riêng.

**Cách xác minh hiệu quả nhất:** xác định lời gọi send → kiểm tra template/producer state → đọc broker admin policy → đọc `JMSDeliveryMode`, `JMSPriority`, `JMSExpiration`, `JMSDeliveryTime` trên message thực → so sánh với kết quả nghiệp vụ. Đừng nhầm giá trị client **muốn gửi** với giá trị broker **đã áp dụng**, và cũng đừng nhầm header đã áp dụng với **business transaction thành công**.

### Tài liệu chính thức để tra cứu

1. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html), đặc biệt `3.4.11–3.4.13` về provider-managed headers, admin override và delivery time; `7` về sending semantics.
2. [Jakarta Messaging 3.1 — MessageProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer): defaults, setter và overload gửi tường minh.
3. [Jakarta Messaging 3.1 — JMSProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmsproducer): QoS fluent API, message ID/timestamp hints.
4. [Jakarta Messaging 3.1 — Message API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): default constants và các header do provider đặt.
5. [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): administered ConnectionFactory defaults, `JmsTemplate` và `explicitQosEnabled`.
6. [Spring Framework — JmsTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `setDeliveryMode`, `setPriority`, `setTimeToLive`, `setDeliveryDelay`, `setExplicitQosEnabled`, `setQosSettings` và message hints.
7. [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): `send`, `convertAndSend` và cách sử dụng template.
