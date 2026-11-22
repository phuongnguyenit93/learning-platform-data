# JMSMessageID, JMSTimestamp và thông tin do provider tạo

> **Mục tiêu:** hiểu **ai tạo từng trường metadata của một JMS message, khi nào trường đó có giá trị, cách đọc và giới hạn ý nghĩa**. Trọng tâm là `JMSMessageID` và `JMSTimestamp`, sau đó mở rộng sang các header/property mà JMS provider thiết lập khi gửi hoặc trước lúc giao tới consumer. Ví dụ theo **Jakarta Messaging 3.1**, gói `jakarta.jms` (Java 17+ / Spring Framework 6+ nếu dùng Spring). Các hệ JMS cũ có thể dùng `javax.jms` nhưng nguyên tắc cốt lõi tương tự.

## 1. Vì sao phải phân biệt “provider tạo” và “ứng dụng tạo”?

Một thông điệp có thể đi qua ba thời điểm rất khác nhau:

~~~text
Ứng dụng tạo TextMessage
  ├─ body: "OrderCreated"
  ├─ app property: eventId="evt-42"
  └─ JMSCorrelationID="req-21"          (ứng dụng tự đặt)
                 │
                 ▼
MessageProducer.send(message)
  ├─ provider gán JMSMessageID
  ├─ provider gán JMSTimestamp
  ├─ provider xác định JMSDestination, JMSDeliveryMode, JMSPriority,
  │   JMSExpiration và JMSDeliveryTime
  └─ broker nhận/xử lý send theo QoS và transaction
                 │
                 ▼
Consumer nhận cùng message
  ├─ đọc header do provider gán khi gửi
  ├─ provider đánh dấu JMSRedelivered nếu là lần giao lại
  └─ provider gán JMSXDeliveryCount khi nhận
                 │
                 ▼
Ứng dụng xử lý, ghi dữ liệu, ACK / commit
~~~

**Sai lầm nền tảng:** nhìn thấy một mã `JMSMessageID` hay thời điểm `JMSTimestamp` rồi kết luận rằng sự kiện nghiệp vụ chỉ xuất hiện một lần, message đã vào database của consumer, hoặc consumer đã xử lý xong. Các trường đó giúp **nhận diện, định tuyến và quan sát một message**, không thay thế transaction, acknowledgment hay trạng thái nghiệp vụ.

Một message JMS gồm ba phần:

| Phần | Ví dụ | Đặc điểm |
| --- | --- | --- |
| **Standard header** | `JMSMessageID`, `JMSTimestamp`, `JMSDestination`, `JMSCorrelationID` | Trường chuẩn của interface `Message`; mỗi trường có một chủ thể được phép đặt |
| **Properties** | `eventId`, `schemaVersion`, `JMSXDeliveryCount` | Thuộc tính kiểu số, boolean hoặc String; một số do ứng dụng, một số do provider quản lý |
| **Body** | `TextMessage` chứa JSON | Dữ liệu nghiệp vụ; schema và cách diễn giải do ứng dụng thống nhất |

`getPropertyNames()` liệt kê **properties**, không liệt kê các standard JMS headers. `JMSMessageID` đọc bằng `getJMSMessageID()`, không phải `getStringProperty("JMSMessageID")`.

## 2. Bảng phân quyền tạo header chuẩn

Bảng sau là phân loại theo **Jakarta Messaging 3.1, `Message` headers**. Điều quan trọng là **setter tồn tại trong API không có nghĩa ứng dụng được phép dùng setter đó để quyết định giá trị**.

| Trường | Ai đặt theo chuẩn? | Thời điểm có ý nghĩa | Đọc bằng |
| --- | --- | --- | --- |
| `JMSMessageID` | Provider trong thao tác send | Sau send đồng bộ hoàn tất; sau callback async | `getJMSMessageID()` |
| `JMSTimestamp` | Provider trong thao tác send | Sau send hoàn tất; sau callback async | `getJMSTimestamp()` |
| `JMSDestination` | Provider trong thao tác send | Đích dùng cho lần gửi | `getJMSDestination()` |
| `JMSDeliveryMode` | Provider trong thao tác send | `PERSISTENT` hoặc `NON_PERSISTENT` thực tế | `getJMSDeliveryMode()` |
| `JMSPriority` | Provider trong thao tác send | Priority 0–9 thực tế | `getJMSPriority()` |
| `JMSExpiration` | Provider tính từ TTL khi send | Mốc hết hạn của message; 0 nếu không đặt TTL | `getJMSExpiration()` |
| `JMSDeliveryTime` | Provider tính từ delivery delay khi send | Mốc sớm nhất cho phép delivery | `getJMSDeliveryTime()` |
| `JMSRedelivered` | Provider trước khi giao cho consumer | Gợi ý rằng message đang được phát lại | `getJMSRedelivered()` |
| `JMSCorrelationID` | Ứng dụng | Ghép request/reply hoặc trace tương quan | `getJMSCorrelationID()` |
| `JMSReplyTo` | Ứng dụng | Destination kỳ vọng nhận phản hồi | `getJMSReplyTo()` |
| `JMSType` | Ứng dụng | Loại message theo quy ước/provider | `getJMSType()` |

Các setter như `setJMSMessageID`, `setJMSTimestamp`, `setJMSPriority` hay `setJMSExpiration` là **public để provider có thể làm việc với message implementation khác**, không phải API cấu hình message của client. Nếu ứng dụng gọi chúng **trước send**, giá trị sẽ bị **bỏ qua và thay bằng giá trị do provider xác lập**. Muốn thay đổi delivery mode, priority, TTL, delivery delay, ứng dụng cấu hình trên `MessageProducer` / `JMSProducer` hoặc overload `send` tương ứng.

**Ngoại lệ hợp lệ:** `setJMSCorrelationID`, `setJMSReplyTo` và `setJMSType` là những setter ứng dụng có thể gọi trước send. Đừng tự điền timestamp hoặc message ID với ý định “giữ nguyên ID”; provider kiểm soát các trường này.

## 3. JMSMessageID: định danh của một lần gửi do provider gán

### 3.1. Ý nghĩa chính xác

`JMSMessageID` là một `String` provider cấp để nhận diện một **message được gửi**. Quy tắc chuẩn quan trọng:

1. Khi message mới được tạo, chưa có lý do để giả định ID đã tồn tại.
2. Trong thao tác `send`, **giá trị cũ của trường này bị bỏ qua**; khi `send` **đồng bộ trả về thành công**, trường chứa ID do provider cấp nếu tính năng cấp ID được bật.
3. Mọi message ID chuẩn phải có prefix **`ID:`**. **Phần sau prefix do provider quyết định**: có thể là chuỗi số, UUID, giá trị opaque khác; không tự parse theo một định dạng giả định.
4. Phạm vi duy nhất chính xác **do provider định nghĩa**, tối thiểu trong một installation gồm các router liên thông của provider. **Không có bảo đảm duy nhất toàn cầu giữa nhiều nhà cung cấp hoặc hai installation độc lập**.
5. ID là **opaque identifier**: không suy ra thời điểm tạo, địa chỉ broker, thứ tự phát hành hoặc khóa partition chỉ từ nội dung chuỗi.

Ví dụ một ID chỉ để minh họa, **không phải giá trị dự đoán khi chạy**:

~~~text
ID:4bb10a9d-6e10-4ac4-a150-bef5cabcd123
~~~

Khi hệ thống bridge qua hai provider, republish message, hoặc tạo bản sao event để gửi nhiều destination, không giả định ID JMS giữ nguyên xuyên suốt mọi ranh giới. Muốn nối các bản phát hành có cùng ý nghĩa nghiệp vụ, bổ sung **`eventId` / `businessMessageId`** do ứng dụng kiểm soát.

### 3.2. ID của message khác ID của nghiệp vụ

| Loại định danh | Ai cấp | Khi nào giữ ổn định? | Dùng cho |
| --- | --- | --- | --- |
| `JMSMessageID` | JMS provider khi send | Theo một message đã gửi trong phạm vi provider; có thể đổi nếu ứng dụng gửi lại như message mới | Truy vết ở broker/client; ghép reply qua request message ID khi cùng miền JMS |
| `eventId` / `commandId` | Ứng dụng phát sự kiện/lệnh | **Giữ nguyên qua retry của cùng sự kiện nghiệp vụ** | Idempotency, dedupe, audit theo nghiệp vụ |
| `orderId` | Hệ thống chủ dữ liệu | Theo bản ghi đơn hàng | Gắn nhiều sự kiện với cùng một entity |
| `JMSCorrelationID` | Ứng dụng | Theo quy ước tương quan request/reply hoặc workflow | Ghép trao đổi, trace nhiều message |

Tình huống dễ gây nhầm:

~~~text
Lần gửi A: eventId = evt-42 ; JMSMessageID = ID:aaa
        send thành công nhưng producer mất kết nối trước khi chắc chắn
Lần retry B: eventId = evt-42 ; JMSMessageID = ID:bbb
        consumer có thể nhận cả A và B
~~~

Đây là **hai message do producer gửi** nhưng chỉ là **một sự kiện nghiệp vụ**. Consumer cần khóa `eventId` và transaction/idempotency để không áp dụng hai lần cùng một thay đổi. Trái lại, khi **broker redeliver cùng message** sau rollback hoặc failure, ID JMS thường tiếp tục nhận diện cùng message, nhưng riêng ID đó vẫn không chứng minh side effect nghiệp vụ chưa từng được thực hiện.

### 3.3. Khi nào không có JMSMessageID?

`MessageProducer.setDisableMessageID(true)` và `JMSProducer.setDisableMessageID(true)` là **hint** tối ưu hóa; message IDs **được bật theo mặc định**.

- Nếu provider **chấp nhận** hint, `getJMSMessageID()` sẽ là **`null`**.
- Nếu provider **bỏ qua** hint, vẫn phải tạo ID bình thường.
- Đây không phải cờ bắt buộc provider phải tuân theo hoặc một cách ép một ID do client chọn.

Đừng bật nếu tracing, request/reply, kiểm thử hoặc công cụ vận hành của hệ thống đang dựa vào ID. Ngay cả khi ID luôn có, đừng dùng thay `eventId` để đảm bảo exactly-once business effect.

## 4. JMSTimestamp: thời điểm giao message cho provider để gửi

`JMSTimestamp` có kiểu **`long`**, đo bằng **milliseconds từ 1970-01-01T00:00:00Z (Unix epoch)**. Nó biểu diễn **thời điểm message được bàn giao cho provider để gửi**. Cụ thể, với synchronous `send`, giá trị được đặt trong khoảng từ **lúc gọi send đến lúc send trả về** (trừ khi timestamp bị vô hiệu hóa theo hint).

Một timeline:

~~~text
10:00:00.000  producer tạo TextMessage trong RAM
10:00:00.200  producer gọi send
10:00:00.210  JMSTimestamp được gán (minh họa)
10:00:00.450  send đồng bộ trả về
10:00:03.000  transaction JMS mới commit (nếu có)
10:00:05.500  consumer nhận message
10:00:05.800  consumer bắt đầu xử lý
10:00:06.100  DB commit nghiệp vụ
~~~

**`JMSTimestamp` không phải** thời điểm ứng dụng tạo object, broker flush xuống disk, JMS transaction commit, consumer nhận, hoặc nghiệp vụ xử lý xong. Giá trị có thể nằm trước commit nhiều giây; gửi bất đồng bộ hoặc bị queue ở client/provider càng làm ranh giới rõ hơn.

### 4.1. Chuyển epoch milliseconds thành thời gian dễ đọc

Java 17+ có thể chuyển theo timezone rõ ràng:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ReadJmsTimestamp {
    public static void main(String[] args) {
        long millis = 1_700_000_000_000L;
        Instant instant = Instant.ofEpochMilli(millis);
        ZonedDateTime vietnam = instant.atZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println(instant);
        System.out.println(vietnam);
    }
}
~~~

Lưu trong `ReadJmsTimestamp.java` rồi chạy:

~~~bash
javac ReadJmsTimestamp.java
java ReadJmsTimestamp
~~~

Kết quả chính xác với timestamp cố định trên:

~~~text
2023-11-14T22:13:20Z
2023-11-15T05:13:20+07:00[Asia/Ho_Chi_Minh]
~~~

**Đừng chia nhầm cho 1.000 hai lần.** `Instant.ofEpochMilli` nhận mili-giây; dữ liệu timestamp JMS không kèm một múi giờ riêng. Múi giờ chỉ xuất hiện **khi hiển thị**. Nếu đọc `getJMSTimestamp() == 0` do provider chấp nhận hint tắt timestamp, **không** hiển thị đó là “1970, lúc message được tạo” vì 0 lúc ấy mang nghĩa **timestamp không khả dụng**.

### 4.2. JMSTimestamp và đo latency

Bạn có thể tính một phép đo gần đúng:

~~~java
long sentMillis = message.getJMSTimestamp();
long observedMillis = System.currentTimeMillis();
if (sentMillis > 0) {
    long approximateAgeMillis = observedMillis - sentMillis;
    System.out.println("Approximate message age ms = "
            + approximateAgeMillis);
}
~~~

Đây là **code snippet bên trong consumer method** với biến `message` là `jakarta.jms.Message`; các import và exception `JMSException` được xử lý ở method bao ngoài. Giá trị có thể âm hoặc sai lệch khi đồng hồ producer/consumer/provider lệch nhau, đồng hồ hệ thống bị điều chỉnh, message qua bridge, hoặc receiver nằm ở môi trường có độ trễ khác. **Không** gọi đây là metric chính xác của “broker processing time”. Khi cần tracing đáng tin, ghi cả thời gian ứng dụng tạo event (do client cấp), thời gian send, enqueue, delivery, consumer start, DB commit bằng telemetry được chuẩn hóa; dùng monotonic clock đo **duration trong cùng tiến trình**.

### 4.3. Vô hiệu hóa timestamp là hint, không phải SLA

~~~java
producer.setDisableMessageTimestamp(true);
producer.send(message);

long timestamp = message.getJMSTimestamp();
~~~

Sau `send` đồng bộ thành công:

- Provider **chấp nhận** hint → `timestamp == 0`.
- Provider **bỏ qua** hint → timestamp vẫn là epoch milliseconds bình thường.

Mặc định timestamp **được bật**. Không tắt khi hệ thống cần dùng timestamp để chẩn đoán tuổi message, audit hoặc tương quan. Đặc biệt, **không phụ thuộc việc tắt timestamp để điều khiển TTL**: TTL và `JMSExpiration` có cơ chế tính riêng ở provider.

## 5. Các header khác do provider tính khi send

### 5.1. JMSDestination — message đã được gửi tới đâu?

`getJMSDestination()` trả về đối tượng destination của lần gửi (queue/topic). Với `MessageProducer` gắn đích, nó phản ánh destination producer dùng; với unidentified producer, phản ánh destination truyền vào `send(destination, message)`. Provider gán khi send; giá trị trước send bị bỏ qua.

Không giả định `toString()` của destination là tên queue chuẩn giữa mọi provider. Muốn lấy tên theo API, xác định kiểu:

~~~java
Destination destination = message.getJMSDestination();
if (destination instanceof Queue queue) {
    System.out.println("Queue: " + queue.getQueueName());
} else if (destination instanceof Topic topic) {
    System.out.println("Topic: " + topic.getTopicName());
}
~~~

Đây là snippet với `message` là `jakarta.jms.Message`, import `jakarta.jms.Destination`, `Queue`, `Topic`; `getQueueName/getTopicName` có thể ném `JMSException`. Cẩn trọng với bridge hoặc alias: tên vật lý/binding của broker có thể khác với định danh ứng dụng mong đợi.

### 5.2. JMSDeliveryMode — mode thực tế

`getJMSDeliveryMode()` phản ánh `DeliveryMode.PERSISTENT` hoặc `DeliveryMode.NON_PERSISTENT` được dùng khi gửi, thông qua cấu hình producer, overload `send` hoặc override quản trị (nếu broker hỗ trợ). `PERSISTENT` là mặc định của producer trong JMS API.

~~~java
int mode = message.getJMSDeliveryMode();
String label = mode == DeliveryMode.PERSISTENT
        ? "PERSISTENT"
        : "NON_PERSISTENT";
~~~

Đoạn trên là snippet dùng `jakarta.jms.DeliveryMode`. **PERSISTENT không chứng minh consumer đã xử lý.** Nó yêu cầu bảo đảm bền vững trong phạm vi chuẩn/provider; vận hành vẫn cần xem transaction, storage, HA, TTL, quota và hệ thống downstream.

### 5.3. JMSPriority — ưu tiên giao, không phải thứ tự tuyệt đối

`getJMSPriority()` có giá trị **0–9**, mặc định **4**, provider đặt theo QoS thực tế khi send. Có thể dùng `producer.setPriority(8)` hoặc overload `send(message, DeliveryMode.PERSISTENT, 8, ttl)` để yêu cầu ưu tiên. JMS **không bắt buộc provider tuân thủ chặt thứ tự priority** và không đảm bảo “priority cao thì xử lý xong sớm hơn”; concurrency, backlog, redelivery, selector và consumer performance còn ảnh hưởng.

### 5.4. JMSExpiration — mốc hết hạn từ time-to-live

Ứng dụng cấu hình `timeToLive` trên producer hoặc một overload `send` (đơn vị **mili-giây**). Provider tính:

~~~text
TTL > 0:
JMSExpiration ≈ thời điểm send + TTL

TTL = 0:
JMSExpiration = 0   (không đặt hạn do TTL)
~~~

Trong **transacted session**, mốc tính từ **thời điểm ứng dụng gửi**, không phải từ **thời điểm transaction commit**. Nếu producer send và đợi 40 giây mới commit trong khi TTL chỉ 10 giây, message có thể đã quá hạn khi transaction hoàn tất.

Theo specification, provider **nên** loại thông điệp chưa giao khi hết hạn nhưng **độ chính xác của expiry không được định nghĩa tuyệt đối**; consumer cũng không được dựa vào giả định “không thể nhận message hết hạn trong mọi trường hợp”. Với dữ liệu có hạn nghiệp vụ, kiểm tra hạn đó **tại consumer**, tách biệt policy expiry của broker.

### 5.5. JMSDeliveryTime — thời điểm sớm nhất có thể giao

`JMSDeliveryTime` là mốc Unix milliseconds được provider tính từ **thời gian send + delivery delay**, cũng tính từ send trước commit nếu đang trong transaction. Producer có thể gọi:

~~~java
producer.setDeliveryDelay(5_000L);  // yêu cầu chưa giao trước 5 giây
producer.setTimeToLive(30_000L);    // message có TTL 30 giây
producer.send(message);             // dùng hai cấu hình trên
~~~

**Sau send**, `message.getJMSDeliveryTime()` cho mốc sớm nhất được giao; đây **không phải** thời điểm delivery thực tế, không phải độ trễ xử lý. Nếu TTL nhỏ hơn delay, message có thể hết hạn trước khi đủ điều kiện giao.

Các giá trị QoS do quản trị viên cấu hình trên provider có thể **override** mode, priority, TTL hoặc delay của ứng dụng nếu provider hỗ trợ. Khi xảy ra override, trường header phải phản ánh giá trị được quản trị áp dụng; vì thế việc so sánh cấu hình client với header sau send/ở consumer là một phép kiểm tra hữu ích.

## 6. Metadata do provider đặt khi consumer nhận: JMSRedelivered và JMSXDeliveryCount

### 6.1. JMSRedelivered không phải một phần của send

`JMSRedelivered` do provider đặt **trước khi giao tới consumer**, không mang ý nghĩa trên message vừa send. Khi `getJMSRedelivered() == true`, đó là dấu hiệu message **có thể đã được giao trước đó mà chưa được ACK/commit**. Consumer nên cẩn thận với side effect lặp.

Nhưng `false` **không chứng minh** chưa từng xảy ra hiệu ứng nghiệp vụ trùng do một lần producer send mới, bridge hoặc tình huống đặc biệt. Điều quan trọng là kiểm tra idempotency theo **event ID nghiệp vụ**, không chỉ theo cờ này.

### 6.2. JMSXDeliveryCount là property chuẩn, không phải header

`JMSXDeliveryCount` là **mandatory property do provider gán khi nhận** theo Jakarta Messaging 3.1:

| Giá trị | Cách diễn giải |
| --- | --- |
| `1` | Lần giao đầu tiên theo thông tin provider |
| `2` trở lên | Message đã được giao lại ít nhất một lần |
| Có `JMSRedelivered=true` | `JMSXDeliveryCount` phải từ **2 trở lên** |

Đọc bằng:

~~~java
int attempts = message.getIntProperty("JMSXDeliveryCount");
boolean redelivered = message.getJMSRedelivered();
~~~

**Không coi count là con số chính xác trong mọi sự cố**: specification không yêu cầu provider lưu bền count qua mọi server crash. Không dùng `JMSXDeliveryCount` làm key duy nhất, không dùng để chứng minh số lần nghiệp vụ đã commit, và không dựa vào selector theo property **được provider gán lúc receive** vì hiệu lực selector như vậy là không xác định theo chuẩn.

### 6.3. Những JMSX property có thể xuất hiện thêm

JMS định nghĩa nhóm properties `JMSX...`:

| Property | Ai đặt | Mức hỗ trợ | Ghi chú |
| --- | --- | --- | --- |
| `JMSXDeliveryCount` | Provider khi receive | **Bắt buộc** | Lần giao, có giới hạn độ chính xác khi lỗi |
| `JMSXUserID` | Provider khi send | Tùy chọn | Danh tính người gửi theo provider |
| `JMSXAppID` | Provider khi send | Tùy chọn | Danh tính ứng dụng theo provider |
| `JMSXProducerTXID` | Provider khi send | Tùy chọn | Transaction ID của producer |
| `JMSXConsumerTXID` | Provider khi receive | Tùy chọn | Transaction ID của consumer |
| `JMSXRcvTimestamp` | Provider khi receive | Tùy chọn | Thời điểm provider giao tới consumer |
| `JMSXGroupID`, `JMSXGroupSeq` | Ứng dụng | Hỗ trợ theo chuẩn khi dùng grouping | Thứ tự/nhóm message theo cơ chế provider |

Một số provider còn có property riêng theo prefix `JMS_<vendor_name>`. Không giả định chúng tồn tại trên broker khác hoặc cố diễn giải field riêng như metadata có tính portable. Có thể tham khảo `ConnectionMetaData.getJMSXPropertyNames()` để xem những tên JMSX mà connection hỗ trợ, rồi vẫn phải kiểm tra từng message.

## 7. Phân biệt provider metadata và client metadata

`JMSCorrelationID` **không do provider tự tạo trên mỗi send** theo kiểu `JMSMessageID`. Ứng dụng tự đặt trước gửi để nối request với response hoặc nối các bước workflow.

Ví dụ request–reply:

~~~text
Producer gửi Request A
  ├─ JMSMessageID     = ID:req-A-123   (provider gán khi send)
  └─ JMSReplyTo       = reply.queue    (ứng dụng đặt trước send)

Consumer nhận Request A
  └─ gửi Response B với:
       JMSMessageID   = ID:res-B-456   (provider gán mới)
       JMSCorrelationID = ID:req-A-123 (ứng dụng copy từ request)
~~~

Đây chỉ là **chuỗi ví dụ**, không phải ID thật của provider. Với `JMSCorrelationID` chứa provider message ID, prefix `ID:` hợp lệ. Nếu ứng dụng dùng correlation string riêng, **không tự đặt tiền tố `ID:`** cho chuỗi tự tạo: chuẩn giữ prefix này cho giá trị ID do provider cấp. Byte-array correlation ID là trường hợp đặc biệt và không portable với mọi JMS provider.

Ứng dụng cũng có thể tự đặt:

~~~java
message.setJMSCorrelationID("checkout-request-42");
message.setJMSType("OrderCreated");
message.setStringProperty("eventId", "evt-42");
message.setLongProperty("eventOccurredAtMillis", 1_700_000_000_000L);
~~~

`eventOccurredAtMillis` là thời điểm nghiệp vụ do ứng dụng xác nhận; không nhất thiết bằng `JMSTimestamp`. Tên property nghiệp vụ nên rõ nghĩa, version hóa và có tài liệu hợp đồng. Với exactly-once business effect, consumer cần transaction kèm unique constraint trên (`consumerName`, `eventId`) hoặc cơ chế idempotency tương đương; `JMSMessageID` không thay thế được việc đó.

## 8. Thời điểm được đọc an toàn: trước send, sau send, async, transaction

| Mốc | `JMSMessageID` / `JMSTimestamp` | Các header provider-on-send khác | `JMSRedelivered` / `JMSXDeliveryCount` |
| --- | --- | --- | --- |
| Vừa tạo message | Chưa được provider cấp cho lần gửi hiện tại | Chưa phản ánh lần gửi | Chưa có ý nghĩa |
| Đang xây dựng message trước send | **Không** tự set | Không tự set trực tiếp vào `Message` | Không tự set |
| `send` **đồng bộ trả về thành công** | Có thể đọc giá trị do provider gán; ID có thể null/timestamp 0 khi hint được chấp nhận | Có thể đọc | Không suy diễn trạng thái consumer |
| `send` **bất đồng bộ vừa trả về** | **Chưa được đọc** | **Chưa được đọc** | Chưa có ý nghĩa |
| `CompletionListener` đã được gọi | Có thể đọc sau callback về hoàn tất; xem nhánh success/failure | Có thể đọc sau callback; thất bại thì không giả định metadata đầy đủ | Chưa có nghĩa delivery |
| Send đã chạy nhưng JMS transaction chưa commit | Header send đã được tính | Header có thể có giá trị | **Chưa chứng minh message visible cho consumer** |
| Consumer nhận message | Đọc metadata của message nhận | Đọc metadata do send thiết lập | Provider bổ sung thông tin giao/lần giao |

**Lỗi nguy hiểm với async send:** sau `producer.send(message, completionListener)` vừa return, ứng dụng không được vội đọc hoặc sửa message mà provider vẫn đang xử lý. Chỉ sử dụng các trường provider-on-send sau khi `CompletionListener` đã được gọi; khi thành công, `onCompletion` là thời điểm tiện nhất để log. Với lỗi async, không suy ra message chắc chắn chưa được broker tiếp nhận; đường truyền có thể hỏng khi phản hồi đang quay về.

`JMSMessageID`/`JMSTimestamp` là metadata của hành vi send; **JMS transaction commit** và **consumer acknowledgment/DB commit** là những ranh giới riêng. Với local JMS transaction, đừng dùng giá trị header có sẵn **trước commit** làm bằng chứng message đã giao thành công.

## 9. Ví dụ end-to-end trong Spring Boot 3.x: đọc trước và sau send

Ví dụ sử dụng **Java 17+**, **Spring Boot 3.x**, **Spring JMS/Jakarta Messaging**, một **JMS provider và broker đã cấu hình**. Có thể dùng dependency `org.springframework.boot:spring-boot-starter-artemis` với Artemis tương thích, connection settings và destination `jms.header.demo` đã sẵn sàng theo policy broker.

Tệp `src/main/java/com/example/jmsheaders/JmsHeadersApplication.java`:

~~~java
package com.example.jmsheaders;

import java.time.Instant;
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsHeadersApplication {
    public static void main(String[] args) {
        SpringApplication.run(JmsHeadersApplication.class, args);
    }

    @Bean
    ApplicationRunner publishSample(ConnectionFactory connectionFactory) {
        return args -> {
            try (Connection connection = connectionFactory.createConnection();
                 Session session = connection.createSession(
                         false, Session.AUTO_ACKNOWLEDGE)) {

                Queue queue = session.createQueue("jms.header.demo");
                try (MessageProducer producer = session.createProducer(queue)) {
                    producer.setTimeToLive(120_000L);
                    producer.setDeliveryDelay(1_000L);
                    producer.setDisableMessageID(false);
                    producer.setDisableMessageTimestamp(false);

                    TextMessage message = session.createTextMessage(
                            "Hello from producer");
                    message.setStringProperty("eventId", "evt-demo-001");
                    message.setJMSCorrelationID("request-demo-001");

                    // Không dựa vào provider headers trước send.
                    producer.send(message);

                    System.out.println("Producer eventId="
                            + message.getStringProperty("eventId"));
                    System.out.println("Producer JMSMessageID="
                            + message.getJMSMessageID());
                    System.out.println("Producer JMSTimestamp="
                            + describeTime(message.getJMSTimestamp()));
                    System.out.println("Producer JMSExpiration="
                            + message.getJMSExpiration());
                    System.out.println("Producer JMSDeliveryTime="
                            + message.getJMSDeliveryTime());
                }
            }
        };
    }

    static String describeTime(long millis) {
        return millis == 0L ? "unavailable"
                : Instant.ofEpochMilli(millis).toString();
    }
}

@Component
class HeaderConsumer {
    @JmsListener(destination = "jms.header.demo")
    public void handle(Message message) throws JMSException {
        System.out.println("Consumer JMSMessageID="
                + message.getJMSMessageID());
        System.out.println("Consumer JMSTimestamp="
                + JmsHeadersApplication.describeTime(
                        message.getJMSTimestamp()));
        System.out.println("Consumer JMSCorrelationID="
                + message.getJMSCorrelationID());
        System.out.println("Consumer eventId="
                + message.getStringProperty("eventId"));
        System.out.println("Consumer JMSRedelivered="
                + message.getJMSRedelivered());
        System.out.println("Consumer JMSXDeliveryCount="
                + message.getIntProperty("JMSXDeliveryCount"));
    }
}
~~~

**Cách thử:** chạy broker tương thích, cấu hình `ConnectionFactory` cho Spring Boot, tạo/cho phép auto-create queue theo policy broker, chạy ứng dụng. Có thể quan sát hai nhóm log producer và consumer; listener chạy bất đồng bộ nên **thứ tự dòng log của hai nhóm không có bảo đảm toàn cục**.

**Không có stdout cố định:** `JMSMessageID` do provider cấp; timestamp phụ thuộc thời điểm chạy; `JMSExpiration` và `JMSDeliveryTime` là mốc thực tế. `JMSXDeliveryCount` của một message lần đầu thường là 1, nhưng thứ tự listener nhận và lỗi/retry thay đổi theo runtime. Nếu broker không kết nối được, ứng dụng có thể lỗi ngay khi gửi, và không có log thành công nào để tuyên bố.

**Lý do ví dụ hợp lệ:**

1. `ConnectionFactory` được Spring Boot/provider cấu hình và inject; đây là JMS API trực tiếp để có quyền đọc object `TextMessage` **sau send**. `connection.start()` **không bắt buộc cho thao tác send đơn thuần**.
2. `Session.AUTO_ACKNOWLEDGE` ở session **gửi** không chứng minh consumer đã ACK. Đây là thuộc tính liên quan receive, không phải tín hiệu đồng bộ end-to-end.
3. `setDisableMessageID(false)` và `setDisableMessageTimestamp(false)` giữ hai trường quan sát **được yêu cầu bật**; giá trị provider gán mới được đọc sau `send` trả về.
4. `setTimeToLive(120_000L)` và `setDeliveryDelay(1_000L)` tạo các mốc thời gian để so sánh. Mốc delivery là **sớm nhất có thể giao**, không bắt buộc consumer nhận đúng 1 giây.
5. `@JmsListener` nhận `jakarta.jms.Message` nên có thể đọc header và property mà không chuyển message sang String sớm.
6. Có thể mở rộng listener để parse body, nhưng bài này chỉ kiểm tra metadata. Để kiểm thử redelivery, cấu hình **listener session transacted** và tạo lỗi xử lý có kiểm soát; không mặc định exception luôn tạo retry trên mọi container mode.

### Vì sao không đọc ID trong Spring MessageCreator / MessagePostProcessor?

Ví dụ Spring:

~~~java
jmsTemplate.send("jms.header.demo", session -> {
    TextMessage m = session.createTextMessage("Hello");
    // Tại đây message vẫn đang được TẠO, chưa được send.
    // m.getJMSMessageID() chưa phải ID của lần send sắp tới.
    return m;
});
~~~

Tương tự `MessagePostProcessor` của `JmsTemplate.convertAndSend(...)` chạy trong luồng chuẩn bị message trước send. **Không đặt logic audit về JMSMessageID vừa được provider cấp ở bước này**. `JmsTemplate.send(...)` trả về `void`; nếu yêu cầu lấy metadata sau send, có thể dùng classic JMS API trong ngữ cảnh session được quản lý thích hợp hoặc ghi nhận tại consumer/broker/tracing. Không tạo connection ngoài transaction context của Spring mà không hiểu sự khác biệt.

## 10. Ví dụ gửi bất đồng bộ: callback mới là ranh giới thông tin

Snippet sau đặt **bên trong phương thức đã có `MessageProducer producer` và `Message message`**, với `jakarta.jms.CompletionListener`:

~~~java
producer.send(message, new CompletionListener() {
    @Override
    public void onCompletion(Message completed) {
        try {
            System.out.println(
                    "Async JMSMessageID=" + completed.getJMSMessageID());
            System.out.println(
                    "Async JMSTimestamp=" + completed.getJMSTimestamp());
        } catch (JMSException ex) {
            System.err.println("Cannot read send metadata: "
                    + ex.getMessage());
        }
    }

    @Override
    public void onException(Message failed, Exception cause) {
        System.err.println("Async send failed: " + cause.getMessage());
    }
});
~~~

Chỉ sau khi callback được gọi mới được xem header provider-on-send hoặc tiếp tục sử dụng lại message object. Đoạn này không phải chương trình độc lập (cần import, connection/session/provider, lifecycle). **Không đóng producer/session/connection trong callback** và không gọi `commit/rollback` trên session sở hữu callback. Nếu ứng dụng thoát hoặc bỏ qua exception callback, có thể đánh mất thông tin lỗi publish. Khi dùng async sender, thiết kế rõ lifecycle, backpressure, metrics và retry/outbox.

## 11. Ba tình huống cần đối chiếu metadata với sự thật nghiệp vụ

### Tình huống A — producer gửi lại vì không thấy phản hồi

~~~text
Producer send(eventId=evt-42)
    broker đã nhận (JMSMessageID=ID:first)
    nhưng producer timeout
Producer retry(eventId=evt-42)
    broker nhận bản mới (JMSMessageID=ID:second)
Consumer xử lý cả hai bản
~~~

Hai `JMSMessageID` khác nhau không có nghĩa là hai sự kiện nghiệp vụ khác nhau. Một `eventId` ổn định, unique constraint và transaction nghiệp vụ là cơ chế chống trùng phù hợp.

### Tình huống B — broker phát lại vì consumer rollback

~~~text
Message ID: ID:first ; eventId=evt-42
  nhận lần 1: JMSXDeliveryCount=1, JMSRedelivered=false (thường gặp)
  xử lý lỗi / JMS rollback
  nhận lần 2: JMSXDeliveryCount>=2, JMSRedelivered=true
~~~

JMSMessageID có thể vẫn là cùng ID cho message đang redeliver. Nhưng consumer có thể đã commit **DB** trước khi JMS rollback; do đó “redelivered” không tự nói DB chưa thay đổi. Ngoài ra delivery count không được bảo đảm tuyệt đối khi server failure.

### Tình huống C — timestamp, TTL và transaction

~~~text
t = 0s: send với TTL = 5s, JMSTimestamp xấp xỉ t = 0s
t = 3s: JMS transaction vẫn chưa commit
t = 7s: commit
           → JMSExpiration đã tính từ t = 0s
           → message có thể đã hết hạn trước khi consumer nhận
~~~

`JMSTimestamp` không đợi commit và `JMSExpiration` cũng không tính lại từ commit. Nếu ứng dụng không nhận được message, cần quan sát **expiry, transaction, delay, broker policy, consumer selector và DLQ** trước khi kết luận đó là lỗi provider.

## 12. Logging, tracing và kiểm thử có kiểm soát

Một log hữu ích khi publish và consume nên ghi theo **cùng tên trường** để dễ đối chiếu:

| Field trong log | Nguồn | Giá trị sử dụng |
| --- | --- | --- |
| `eventId` / `commandId` | Client property/body | Nối retry, dedupe và kết quả nghiệp vụ |
| `jmsMessageId` | `getJMSMessageID()` | Tra cứu message trong broker, khi có |
| `jmsTimestampEpochMs` | `getJMSTimestamp()` | Thời điểm send theo provider, nếu khác 0 |
| `jmsDestination` | `getJMSDestination()` | Đích gửi/nhận, chuẩn hóa tên theo provider |
| `jmsCorrelationId` | `getJMSCorrelationID()` | Truy vết workflow/request–reply |
| `jmsExpiration` / `jmsDeliveryTime` | JMS headers | Hiểu thời hạn và delivery delay |
| `jmsRedelivered` / `jmsxDeliveryCount` | Provider khi receive | Quan sát việc giao lại |
| `consumerResult` | Ứng dụng | Thành công, lỗi, DB transaction/side effect |

Để tránh biến log thành rủi ro, không ghi credentials, token, payload nhạy cảm hoặc thông tin cá nhân chưa được kiểm soát. Bảo vệ quyền truy cập log, chuẩn hóa timezone (thường UTC) và đo độ lệch đồng hồ. Không lấy tính duy nhất toàn cục của JMSMessageID làm tiền đề cho hệ thống audit qua nhiều provider.

### Bộ thí nghiệm tự thực hiện

1. **Đọc trước/sau send:** tạo message, đọc ID/timestamp trước gửi để thấy trạng thái không được dùng làm bằng chứng; gửi đồng bộ, ghi ID/timestamp/destination/delivery mode/priority/expiration sau khi gửi và ở consumer.
2. **Hint disable:** thử `setDisableMessageID(true)` và `setDisableMessageTimestamp(true)` trên môi trường test. Ghi rõ provider/version và xem provider tôn trọng hay bỏ qua hint; đừng khẳng định mọi broker giống nhau.
3. **Retry producer:** gửi lại cùng `eventId` như một JMS send mới; kiểm tra JMSMessageID có thay đổi, consumer chống trùng dựa vào `eventId`.
4. **Redelivery consumer:** cấu hình JMS listener transaction để ném lỗi trước commit. Quan sát `JMSRedelivered` và `JMSXDeliveryCount`, sau đó chứng minh DB side effect không nhân đôi.
5. **TTL/delay/commit:** gửi với TTL ngắn, delay dài hoặc giữ transaction trước commit; đo `JMSExpiration` và `JMSDeliveryTime`, quan sát hành vi expiry của provider.
6. **Time-zone:** chuyển `JMSTimestamp` sang UTC và Asia/Ho_Chi_Minh với `Instant`; mô phỏng clock skew để chứng minh vì sao subtract hai wall-clock timestamp chỉ cho latency xấp xỉ.
7. **Request–reply:** gửi request có `JMSReplyTo`, consumer tạo response mới và set `JMSCorrelationID` bằng `JMSMessageID` của request; xác minh response có **JMSMessageID riêng**.

**Bằng chứng tối thiểu sau mỗi bài thử:** cấu hình provider và mode, ID nghiệp vụ, JMS ID, timestamp/TTL, số lần consumer nhận, kết quả transaction của DB và trace/log quan sát được. Tránh diễn giải “message có ID” như bằng chứng thành công toàn quy trình.

## 13. Những hiểu nhầm cần loại bỏ

1. **“Tạo TextMessage là đã có ID/timestamp chuẩn.”** Các header thuộc send do provider gán trong thao tác send; đọc trước send không chứng minh điều gì về message sắp phát.
2. **“Có setter `setJMSMessageID` nên client được tự chọn ID.”** Setter thuộc giao tiếp provider; giá trị client đặt trước send bị bỏ qua.
3. **“`JMSMessageID` là UUID toàn cầu.”** Chuẩn chỉ yêu cầu prefix `ID:` và uniqueness trong phạm vi tối thiểu của installation; định dạng còn lại do provider.
4. **“Retry một event luôn cùng JMSMessageID.”** Nếu ứng dụng thực hiện một send mới, provider có thể tạo ID khác; cần event ID riêng.
5. **“`JMSTimestamp` chính là lúc listener nhận message.”** Đây là thời điểm giao message cho provider để gửi; async, transaction, TTL, delay và backlog làm thời điểm nhận khác đi.
6. **“Timestamp 0 chứng tỏ message từ năm 1970.”** Có thể là dấu hiệu provider chấp nhận hint không tạo timestamp.
7. **“`JMSExpiration` lấy từ giờ consumer nhận.”** Nó được tính theo thời điểm send và TTL; trong transacted send không chờ transaction commit.
8. **“DeliveryTime là thời gian giao thật.”** Đó là thời điểm **sớm nhất** provider được phép giao message.
9. **“`JMSRedelivered=false` chứng minh nghiệp vụ chưa từng xử lý.”** Duplicate producer sends và side effects ngoài JMS vẫn có thể tồn tại.
10. **“`JMSXDeliveryCount` luôn chính xác sau mọi crash.”** Đó là metadata bắt buộc lúc receive nhưng không nhất thiết được persist chính xác qua mọi failure.
11. **“Mọi JMSX property đều luôn có.”** Nhiều trường JMSX là optional; metadata riêng vendor không portable.
12. **“`JmsTemplate` MessageCreator biết JMSMessageID.”** Callback tạo message chạy trước send, không phải lúc provider hoàn tất send.
13. **“Tắt timestamp là tắt TTL.”** Không; đây là hai cơ chế khác nhau.
14. **“Có JMSMessageID nghĩa là consumer đã ACK.”** ID chỉ mô tả metadata của send; ACK, transaction và kết quả nghiệp vụ cần xác nhận riêng.

## 14. Câu hỏi tự đánh giá

- Ai gán `JMSMessageID`, giá trị được phép bắt đầu bằng chuỗi gì và phạm vi uniqueness được đảm bảo đến đâu?
- Vì sao `eventId` ổn định qua retry còn JMSMessageID có thể thay đổi? Phải dedupe theo trường nào?
- `JMSTimestamp` đo thời điểm gì? Nó có phải enqueue, commit, receive hoặc business event time không?
- Khi nào đọc được provider-on-send metadata với synchronous và asynchronous send?
- Provider tạo những header nào cho `JMSExpiration`, `JMSDeliveryTime`, `JMSPriority` và `JMSDestination`? Client cấu hình chúng bằng cách nào?
- `JMSRedelivered` và `JMSXDeliveryCount` được đặt khi send hay khi receive? Vì sao hai trường ấy không bảo đảm exactly-once?
- Điều gì xảy ra nếu provider chấp nhận `setDisableMessageID(true)` hoặc `setDisableMessageTimestamp(true)`?
- Cần log và kiểm chứng thêm những gì để kết luận một sự kiện nghiệp vụ đã được xử lý an toàn?

**Kết quả học tập:** Có thể truy vết một message từ lúc tạo đến sau send, trong broker và tại consumer, phân biệt chính xác metadata do provider tự tạo với metadata ứng dụng quản lý, và dùng chúng để chẩn đoán hệ thống mà không suy diễn quá mức về độ tin cậy.

## Tài liệu chuẩn

1. [Jakarta Messaging 3.1 Specification – `3.4 Message header fields`](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): nguồn chuẩn cho chủ thể tạo từng header, JMSMessageID, JMSTimestamp, expiration, delivery time và giới hạn tương thích.
2. [Jakarta Messaging 3.1 – Message API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): signature getter/setter, header/property và exception.
3. [Jakarta Messaging 3.1 – MessageProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer): QoS, `setDisableMessageID`, `setDisableMessageTimestamp`, synchronous/async send.
4. [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate`, `MessageCreator` và cách Spring sử dụng JMS API.
5. [Spring Framework – Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): nhận `jakarta.jms.Message` qua `@JmsListener` và quản lý listener containers.