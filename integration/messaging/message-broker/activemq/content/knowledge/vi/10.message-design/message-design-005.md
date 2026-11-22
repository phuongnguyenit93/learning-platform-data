# JMSDeliveryMode, JMSPriority, JMSExpiration và trạng thái gửi lại

## 1. Đọc đúng các header điều khiển vòng đời thông điệp

Trong chương **Thiết kế thông điệp** của module ActiveMQ Classic và Artemis, bốn nhóm thông tin dưới đây trả lời những câu hỏi khác nhau về **một message JMS**:

| Header/property trên message | Câu hỏi cần trả lời | Ai quyết định hoặc cập nhật? |
| --- | --- | --- |
| **JMSDeliveryMode** | Broker cần nỗ lực giữ message qua sự cố theo delivery mode nào? | Producer yêu cầu **PERSISTENT** hoặc **NON_PERSISTENT**; provider gán header khi gửi |
| **JMSPriority** | Message nên được ưu tiên ở mức nào khi chọn phân phối? | Producer yêu cầu mức **0–9**; provider/broker thực hiện theo chính sách |
| **JMSExpiration** | Từ lúc nào message không còn hợp lệ để tiếp tục giao? | Provider tính từ **time-to-live (TTL)** lúc gửi, trừ khi policy broker điều chỉnh |
| **JMSRedelivered** | Provider cho biết message này đang được giao lại hay không? | Provider/broker cập nhật khi redelivery |
| **JMSXDeliveryCount** | Message đã được giao bao nhiêu lần theo bộ đếm của provider? | Provider/broker cập nhật; là **JMSX property**, không phải JMS header chuẩn có getter riêng |

Bốn nhóm này **không thay thế nhau**. **PERSISTENT** không ngăn message hết TTL; **priority cao** không bảo đảm thành công; **JMSRedelivered=true** không chứng minh nghiệp vụ đã chạy lần trước; và **JMSXDeliveryCount** không thể thay cho khóa idempotency của ứng dụng.

Ví dụ một message **OrderPaid** có:

~~~text
JMSDeliveryMode     = PERSISTENT (2)
JMSPriority         = 8
JMSExpiration       = 0
JMSRedelivered      = false      (lần nhận đầu)
JMSXDeliveryCount   = 1          (khi provider cung cấp)
businessEventId     = "pay-932"  (application property)
~~~

Các trường đầu là **QoS/metadata do JMS provider quản lý**. **businessEventId** là property do ứng dụng tự đặt để xác định cùng một sự kiện nghiệp vụ qua cả hai trường hợp **broker redelivery** và **producer phải gửi lại do không rõ kết quả lần gửi trước**.

~~~mermaid
flowchart TD
    P["Producer đặt delivery mode, priority, TTL"] --> S["JMS provider gửi message"]
    S --> B["Broker route vào queue/subscription"]
    B --> E{"Đã hết hạn tại thời điểm xét giao?"}
    E -- Có --> X["Expire / expiry handling theo policy"]
    E -- Chưa --> D["Dispatch cho consumer"]
    D --> R{"Consumer xác nhận thành công?"}
    R -- Có --> A["ACK / commit: hoàn tất bản giao"]
    R -- Không --> Q{"Còn cho phép giao lại?"}
    Q -- Có --> RE["Redelivery: cập nhật trạng thái và delivery count"]
    RE --> E
    Q -- Không --> DLQ["Dead-letter theo policy"]
~~~

Sơ đồ là luồng **logic**. Cách Artemis và Classic thực hiện expiry, delay, DLQ, storage và đếm lần giao có thể khác nhau theo phiên bản, giao thức và cấu hình. Một message cũng có thể được gửi vào **topic** rồi tạo các bản phân phối cho nhiều subscription; việc ACK, retry và backlog của từng subscription có phạm vi độc lập.

## 2. JMSDeliveryMode: độ bền mong muốn, không phải kết quả nghiệp vụ

JMS có hai hằng số delivery mode:

| Hằng số Java | Giá trị | Ý nghĩa thực hành |
| --- | ---: | --- |
| **DeliveryMode.NON_PERSISTENT** | **1** | Chấp nhận đánh đổi độ bền để giảm chi phí; provider có thể mất message khi gặp một số sự cố |
| **DeliveryMode.PERSISTENT** | **2** | Yêu cầu JMS provider bảo đảm độ bền message theo hợp đồng và cấu hình persistence của provider |

Trong JMS, **PERSISTENT** là mode mặc định của producer nếu không cấu hình khác. Tuy vậy, ứng dụng nên **đặt tường minh** mode quan trọng để người review thấy rõ quyết định nghiệp vụ.

### Đặt mode bằng JMSProducer (Jakarta Messaging)

~~~java
import jakarta.jms.DeliveryMode;

// context là một JMSContext đã tạo từ connection factory.
context.createProducer()
       .setDeliveryMode(DeliveryMode.PERSISTENT)
       .send(queue, textMessage);
~~~

Hoặc bằng **MessageProducer** của API cổ điển:

~~~java
// session/queue đã được tạo.
MessageProducer producer = session.createProducer(queue);
producer.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
producer.send(message);
~~~

Có thể đặt **mode theo từng lần send**, thay vì thay đổi cấu hình producer dùng chung:

~~~java
// Classic javax.jms hoặc Jakarta JMS legacy API đều có dạng overload này.
producer.send(queue, message,
              DeliveryMode.PERSISTENT,
              7,       // priority
              30_000L  // TTL, milliseconds
);
~~~

Sau khi gửi, phía consumer kiểm tra:

~~~java
int mode = receivedMessage.getJMSDeliveryMode();
boolean persistent = (mode == DeliveryMode.PERSISTENT);
~~~

Đừng tự ý gán **message.setJMSDeliveryMode(...)** rồi mong broker giữ nguyên khi gửi: **delivery mode phải được đặt bằng lựa chọn gửi của producer/send API**. JMS provider là nơi gán metadata gửi cuối cùng.

### Mode PERSISTENT bảo đảm đến đâu?

PERSISTENT tăng khả năng sống sót của **message được broker chấp nhận và lưu theo chính sách**, nhưng cần phân biệt:

1. **Broker đã tiếp nhận message** với **producer đã nhận phản hồi send/commit**.
2. **Broker lưu message bền vững** với **hệ thống có replica/HA** để chịu hỏng máy hoặc mất ổ đĩa.
3. **Message còn trong queue** với **consumer đã hoàn thành side effect**.
4. **JMS transaction đã commit** với **transaction database ngoài JMS đã commit**.

Message persistent vẫn có thể bị **expire theo TTL**, bị chuyển DLQ theo chính sách lỗi, bị xóa do admin purge, hoặc chịu hạn mức retention/storage. Nếu broker hoặc client gửi bất đồng bộ/transaction, phải hiểu rõ mốc **acknowledgment của send** mà cấu hình cụ thể cung cấp.

**Không thể dùng PERSISTENT để kết luận “exactly-once xử lý nghiệp vụ”.** Nếu consumer ghi DB thành công nhưng mất kết nối trước khi ACK JMS, broker có thể giao lại. Nếu producer timeout sau khi broker nhận nhưng trước khi client thấy kết quả, producer cũng có thể gửi trùng dưới một **JMSMessageID mới**.

### Khi nào dùng NON_PERSISTENT?

Dùng cho dữ liệu có thể tái tạo hoặc chấp nhận mất, chẳng hạn cập nhật nhiệt độ mỗi giây, vị trí xe tức thời, tình trạng online. Ngay cả với NON_PERSISTENT, broker vẫn có thể **tạm giữ trong bộ nhớ** và chịu policy riêng; không được giả định message không bao giờ nằm trên đĩa trong bất kỳ cấu hình nào.

Chọn mode trên cơ sở **tác động khi mất** thay vì chỉ dựa vào benchmark thông lượng. Thường nên ưu tiên PERSISTENT cho thay đổi đơn hàng, thanh toán, tồn kho hoặc lệnh cần được xử lý đúng; sau đó phối hợp queue/subscription durable, transaction và idempotency.

## 3. JMSPriority: mức độ ưu tiên phân phối, không phải FIFO tuyệt đối

**JMSPriority** là một số nguyên từ **0 đến 9**, mặc định là **4**. JMS chia thành các mức thấp **0–4** và cao **5–9**; broker **có thể** xét mức ưu tiên khi chọn message để dispatch. Trong nhiều triển khai, message priority cao thường được phục vụ sớm hơn khi cùng chờ trong queue, nhưng **không có cam kết sắp xếp toàn cục tuyệt đối** cho mọi lịch trình và cấu hình.

~~~java
context.createProducer()
       .setPriority(9)
       .send(queue, urgentMessage);

context.createProducer()
       .setPriority(1)
       .send(queue, routineMessage);
~~~

Nếu consumer đã nhận hoặc broker đã dispatch message ưu tiên thấp vào vùng đệm (prefetch) trước khi message ưu tiên cao được gửi, priority cao **không thu hồi công việc đang chạy**. Nhiều producer, nhiều consumer, redelivery, message groups, cache, paging và transaction cũng làm thứ tự hoàn thành khác thứ tự ưu tiên.

### Minh họa hàng chờ

Một queue có ba message, tất cả đang chờ **trước khi** consumer bắt đầu:

| Message | Priority | Thời điểm enqueue | Kỳ vọng thực tế |
| --- | ---: | --- | --- |
| M1: Báo cáo ngày | 1 | 09:00:00 | Có thể được xử lý sau message khẩn |
| M2: Đơn hàng cần kiểm tra | 8 | 09:00:01 | Có khả năng được chọn trước M1 nếu broker hỗ trợ ưu tiên |
| M3: Cảnh báo thiết bị | 9 | 09:00:02 | Có khả năng được chọn sớm |

Đây là **xu hướng ưu tiên**, không phải yêu cầu broker luôn trả **M3 → M2 → M1**. Nếu một consumer đã prefetch M1 trước khi M3 xuất hiện, ứng dụng có thể hoàn thành M1 trước. Không dùng JMSPriority để xây dựng quy tắc nghiệp vụ “OrderCancelled phải đến trước OrderPaid”.

### Priority không phải deadline

Một message có **priority 9** nhưng đã hết hạn **JMSExpiration** thì không nên được phân phối chỉ vì ưu tiên cao. Ngược lại, một message có **priority 0** và TTL chưa hết vẫn có thể được nhận. Nếu muốn cách ly tác vụ quan trọng khỏi các tác vụ chậm, cân nhắc **queue riêng + consumer capacity/SLO riêng** thay vì kỳ vọng một hàng chờ nhiều loại công việc được điều phối hoàn hảo bằng priority.

**Starvation** cũng cần xem xét: dòng message ưu tiên cao đến liên tục có thể khiến message ưu tiên thấp phải chờ rất lâu. Quan sát oldest-message age theo priority và kiểm thử dưới tải thực tế.

## 4. JMSExpiration: thời điểm tuyệt đối suy ra từ TTL

**TTL (time-to-live)** là lựa chọn lúc **gửi**, thường tính bằng **mili giây**. **JMSExpiration** là **timestamp tuyệt đối** (mili giây kể từ Unix epoch) do JMS provider tính tại thời điểm gửi; nếu TTL bằng **0** thì **JMSExpiration = 0**, nghĩa là không tự hết hạn theo TTL JMS.

~~~java
// TTL: 15 giây.
context.createProducer()
       .setTimeToLive(15_000L)
       .send(queue, message);
~~~

Về logic thông thường:

~~~text
JMSExpiration ≈ thời điểm provider thực hiện send + TTL

Nếu send lúc 10:00:00.000 và TTL = 15_000 ms:
JMSExpiration tương ứng khoảng 10:00:15.000.

Nếu TTL = 0:
JMSExpiration = 0 (không có deadline JMS từ TTL).
~~~

**Không nên tự tính lại expiration dựa trên đồng hồ của consumer** rồi coi đó là header chuẩn; đọc **message.getJMSExpiration()**. Timestamp gửi (**JMSTimestamp**) và expiration có quan hệ trong cấu hình thông thường nhưng có thể chịu tùy chọn tắt timestamp hoặc chính sách provider/broker. Deadline nghiệp vụ tuyệt đối cũng có thể khác với TTL JMS.

### TTL bắt đầu từ lúc gửi, không phải lúc consumer nhận

Giả sử:

- Producer gửi M1 lúc **10:00:00** với TTL **5 giây**.
- Queue đang backlog; consumer sẵn sàng nhận lúc **10:00:07**.
- Dù message được gửi dưới **PERSISTENT**, M1 đã quá thời hạn JMS; provider có thể xử lý **expiration** và không giao như một message còn sống.

Ngược lại, message được **giao thành công trước thời điểm hết hạn** có thể vẫn đang được consumer xử lý sau thời điểm đó. Broker không thể tự hoàn tác một giao dịch database đã bắt đầu vì TTL vừa hết. Khi nghiệp vụ có hạn xử lý cứng (ví dụ mã OTP hoặc yêu cầu báo giá), consumer nên kiểm tra thêm deadline nghiệp vụ trong payload/header và áp dụng điều kiện giao dịch trước khi tạo side effect.

### Hết hạn không đồng nghĩa gửi tới DLQ

- **Expiration**: message quá TTL; broker có thể **loại bỏ** hoặc chuyển tới **expiry address/queue** tùy cấu hình.
- **Dead-letter**: message được giao nhưng xử lý thất bại, đạt ngưỡng retry/điều kiện dead-letter theo policy.
- **Rollback/redelivery**: message chưa được ACK và broker có thể giao lại nếu còn hợp lệ và trong ngưỡng retry.

Trong **Artemis**, expiry address và dead-letter address là **hai mục cấu hình khác nhau**. Trong **ActiveMQ Classic**, xử lý message hết hạn và dead-letter strategy cũng tùy policy. Không diễn giải “message không thấy trong queue” thành “chắc chắn nằm ở DLQ”.

### TTL có thể không đủ cho mọi SLA

Nếu event thực sự phải được xử lý **cuối cùng**, TTL ngắn có thể làm mất dữ liệu nghiệp vụ khi consumer bị sự cố. Với thanh toán hoặc công việc cần đối soát, thường dùng **PERSISTENT + TTL 0** (hoặc TTL đáp ứng chính sách dữ liệu) và đặt **business deadline** riêng. Nếu quá deadline, consumer quyết định reject/compensate thay vì mong broker xóa âm thầm mà vẫn giữ được khả năng audit.

## 5. JMSRedelivered: dấu hiệu message đã được giao trước đó

**JMSRedelivered** là **boolean header**, được JMS provider đặt khi message đang được giao lại sau một lần delivery chưa hoàn tất theo cơ chế broker/client. Trên consumer đọc bằng:

~~~java
boolean redelivered = message.getJMSRedelivered();
~~~

Thường thấy:

- **false** ở lần giao đầu.
- **true** ở lần giao lại sau rollback, session recover, connection failure hoặc các điều kiện redelivery của provider.

**JMSRedelivered=true không có nghĩa side effect chắc chắn đã chạy.** Consumer có thể chết ngay trước khi parse payload hoặc trước khi bắt đầu transaction database. Giá trị này chỉ là tín hiệu về **delivery lifecycle của broker**, không phải biên nhận nghiệp vụ.

### JMSXDeliveryCount: số lần delivery theo provider

Đây là **message property** nên truy cập qua JMS property API:

~~~java
if (message.propertyExists("JMSXDeliveryCount")) {
    int attempts = message.getIntProperty("JMSXDeliveryCount");
    System.out.println("JMSXDeliveryCount=" + attempts);
}
~~~

Trong nhiều Artemis/Classic client hiện đại, giá trị thường là **1** ở lần giao đầu, **2** ở lần giao thứ hai. Hãy kiểm tra phiên bản/provider và chính sách redelivery đang dùng; không suy rằng property luôn là thước đo chính xác số lần **business handler đã chạy**. Một message có thể được dispatch, rollback và redeliver trong khi logic nghiệp vụ chưa bắt đầu.

Bảng đối chiếu:

| Quan sát tại consumer | Điều có thể suy ra | Điều **không** suy ra được |
| --- | --- | --- |
| **JMSRedelivered=false** | Provider không đánh dấu đây là redelivery | Message nghiệp vụ chưa từng được producer gửi trước đó |
| **JMSRedelivered=true** | Provider xem đây là delivery lặp | Database chắc chắn đã commit lần trước |
| **JMSXDeliveryCount=3** | Provider đã ghi nhận ba lần delivery theo cơ chế của nó | Logic xử lý nghiệp vụ đã chạy và thất bại đúng ba lần |
| **JMSMessageID** không đổi qua lần giao lại | Thường đang nhìn cùng một JMS message được broker redeliver | Đây là khóa nghiệp vụ duy nhất xuyên mọi lần producer retry |
| **businessEventId** lặp giữa hai JMSMessageID | Producer có thể đã phát hai JMS messages mang cùng một sự kiện | Broker nhất thiết bị lỗi |

**Phân biệt producer retry và broker redelivery:**

~~~mermaid
flowchart TD
    E["Một sự kiện nghiệp vụ: businessEventId=pay-932"] --> P["Producer send"]
    P --> M1["Message JMS A / JMSMessageID=A"]
    M1 --> B["Broker delivery lần 1"]
    B --> F["Consumer rollback / crash trước ACK"]
    F --> R["Broker redeliver JMS A<br/>JMSRedelivered=true"]
    P --> T["Producer timeout: không biết send thành công?"]
    T --> P2["Producer gửi lại cùng businessEventId"]
    P2 --> M2["Message JMS B / JMSMessageID=B"]
~~~

**Nhánh redelivery** có thể giữ **JMSMessageID** của cùng message A và tăng delivery count. **Nhánh producer retry** có thể tạo message B mới, **JMSRedelivered=false** ngay lần đầu dù là **sự kiện nghiệp vụ trùng**. Vì vậy luôn dùng **businessEventId/eventId** ổn định để thực hiện idempotency, không chỉ dựa vào cờ redelivered.

## 6. Tương tác giữa expiration, persistence, priority và redelivery

Để dự đoán kết quả cần kết hợp cả bốn yếu tố với thời gian và trạng thái queue:

| Tình huống | JMSDeliveryMode | Priority | TTL | Kết quả cần chờ đợi |
| --- | --- | ---: | ---: | --- |
| OrderPaid phải xử lý và đối soát | PERSISTENT | 4–7 tùy SLA | 0 hoặc dài theo policy | Giữ backlog phù hợp; vẫn cần retry và idempotency |
| Bản cập nhật GPS liên tục | NON_PERSISTENT | 2 | 2 giây | Quá cũ có thể expire; ứng dụng lấy trạng thái mới nhất |
| Cảnh báo cần chú ý sớm | PERSISTENT | 9 | 30 giây | Có thể được ưu tiên nhưng không được nhận sau expiry |
| Hàng chờ tồn đọng vì consumer offline | PERSISTENT | 9 | 5 giây | PERSISTENT không cứu message sau khi TTL hết |
| Consumer rollback gần thời điểm TTL | PERSISTENT | 4 | 2 giây | Redelivery có thể không xảy ra nếu message đã expire |
| Producer timeout rồi retry cùng event | PERSISTENT | 4 | 0 | Có thể có **hai JMS messages**, mỗi message có delivery count riêng |

Sắp xếp ưu tiên chỉ có ý nghĩa giữa **những message còn đủ điều kiện delivery**. Expiration là điều kiện hợp lệ theo thời gian, còn redelivery là lịch sử giao nhận của message; một message có thể có **priority 9** và **JMSRedelivered=true** cùng lúc.

### Race condition: TTL có thể hết giữa các lần giao

Giả sử message có **TTL 10 giây**, được nhận lần đầu sau 7 giây, consumer xử lý lỗi và rollback sau 2 giây, broker đặt **redelivery delay 3 giây**. Khi broker thử giao lại, timestamp đã qua mốc hết hạn. Tùy cách áp dụng expiration policy, message có thể được xử lý như expired thay vì được giao lại. Không dùng **max-delivery-attempts=5** để cam kết sẽ nhận đủ 5 lần nếu TTL có thể kết thúc sớm hơn.

### High priority không khắc phục consumer quá chậm

Nếu worker chỉ xử lý một message mỗi phút mà producer gửi 100 message mỗi phút, tăng JMSPriority từ 4 lên 9 cho mọi message không tăng được công suất xử lý. Muốn cải thiện độ trễ cần consumer concurrency, quản lý prefetch, giới hạn lưu lượng, queue separation hoặc tối ưu dependency; priority chỉ định thứ tự ưu tiên tương đối.

## 7. Cấu hình Artemis: retry, DLQ và expiry kiểm chứng được

Artemis cho phép cấu hình theo **address-settings**. Ví dụ áp dụng cho những queue/address demo bắt đầu bằng **lab.headers.**, đặt vào phần **address-settings** hiện hữu của **broker.xml**:

~~~xml
<address-setting match="lab.headers.#">
    <dead-letter-address>DLQ</dead-letter-address>
    <expiry-address>ExpiryQueue</expiry-address>

    <redelivery-delay>2000</redelivery-delay>
    <redelivery-multiplier>2.0</redelivery-multiplier>
    <max-redelivery-delay>10000</max-redelivery-delay>
    <max-delivery-attempts>4</max-delivery-attempts>
</address-setting>
~~~

Nếu broker chưa có đích cho DLQ và expiry, một cấu hình địa chỉ/queue **ANYCAST** minh họa ở phần **addresses** có thể là:

~~~xml
<address name="DLQ">
    <anycast>
        <queue name="DLQ" durable="true"/>
    </anycast>
</address>
<address name="ExpiryQueue">
    <anycast>
        <queue name="ExpiryQueue" durable="true"/>
    </anycast>
</address>
~~~

Đây là **đoạn XML để ghép vào broker.xml đúng cấu trúc hiện có**, không phải tệp hoàn chỉnh; cần đối chiếu schema và cấu hình instance Artemis thực tế. Đích expiry/DLQ có thể đã được tạo bởi image hoặc policy; không khai báo trùng tên mà chưa kiểm tra.

Điểm tác động:

- **redelivery-delay**: độ trễ trước lần giao lại, giúp tránh vòng lặp rollback nóng.
- **redelivery-multiplier** và **max-redelivery-delay**: điều chỉnh backoff sau các lần thất bại.
- **max-delivery-attempts**: ngưỡng xử lý thất bại trước khi thực hiện dead-letter policy.
- **dead-letter-address**: nơi message lỗi bị chuyển sau khi đạt điều kiện.
- **expiry-address**: nơi message hết hạn có thể được chuyển đến.

**Các thiết lập trên không thay đổi JMSPriority hay tự tạo TTL.** TTL được producer đặt bằng **setTimeToLive**; broker có thể có các chính sách bổ sung điều chỉnh expiration theo release và address, nhưng phải tách rõ yêu cầu của producer với override của broker.

### Những tình huống cần kiểm chứng qua console

| Thao tác | Quan sát nên kiểm tra |
| --- | --- |
| Send message TTL rất ngắn, không có consumer | Message có thể rời queue nguồn sau expiration; nếu expiry policy áp dụng, xuất hiện ở ExpiryQueue |
| Rollback một message chưa hết hạn | **JMSRedelivered/JMSXDeliveryCount** thay đổi khi giao lại |
| Rollback lặp đến ngưỡng | Message chuyển DLQ nếu cấu hình và quyền phù hợp |
| Gửi priority 1 và 9 vào cùng queue trước khi có consumer | Quan sát thứ tự nhận; không coi thứ tự một lần là bảo đảm tuyệt đối |
| Restart broker khi có PERSISTENT message còn chờ | Message có thể còn sau restart nếu queue/storage/delivery mode đáp ứng |

Artemis có thể **xử lý expiry theo cơ chế quét hoặc lúc nhận/dispatch**, vì vậy metric queue và thời điểm nhìn thấy message trong expiry queue không nhất thiết thay đổi đúng tại một mili giây cố định. Quan sát theo một cửa sổ thời gian và kiểm tra log/policy.

## 8. ActiveMQ Classic: client redelivery policy khác Artemis address-settings

Với **ActiveMQ Classic**, ứng dụng JMS sử dụng **ActiveMQConnectionFactory** và có thể đặt **RedeliveryPolicy** trên client, ví dụ:

~~~java
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.RedeliveryPolicy;

ActiveMQConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

RedeliveryPolicy policy = factory.getRedeliveryPolicy();
policy.setInitialRedeliveryDelay(1000L);
policy.setRedeliveryDelay(2000L);
policy.setUseExponentialBackOff(true);
policy.setBackOffMultiplier(2.0);
policy.setMaximumRedeliveries(4);
~~~

Đặt policy **trước khi tạo Connection**. Ở Classic, cơ chế client redelivery phối hợp với broker dead-letter strategy; khi client vượt ngưỡng, có thể gửi tín hiệu poison acknowledgment để broker chuyển message theo DLQ policy. Cần kiểm tra broker **destinationPolicy/deadLetterStrategy** nếu muốn xác định queue DLQ và cách xử lý message expired cụ thể.

So sánh đúng phạm vi:

- **Artemis:** thường điều chỉnh redelivery, DLQ, expiry theo **address-settings trên broker**.
- **Classic:** có **RedeliveryPolicy trên client** cùng **dead-letter strategy trên broker**. Đổi client policy không tương đương với đổi địa chỉ DLQ của broker.
- Với cả hai: **JMSRedelivered/JMSXDeliveryCount** là thứ ứng dụng **quan sát khi nhận**, không phải một bộ đếm nghiệp vụ tự động đáng tin qua mọi producer retry.

Không copy XML Artemis vào cấu hình Classic hoặc lấy **ActiveMQConnectionFactory** của Classic để giả định mọi tùy chọn Artemis đều được hỗ trợ.

## 9. Thực hành Java/JMS trên Artemis: in header và gây redelivery thật

Ví dụ dưới đây dùng **Jakarta Messaging** trên ActiveMQ Artemis. Nó có ba chế độ:

- **redelivery:** gửi một PERSISTENT message, đọc headers, **rollback** lần nhận đầu, đọc lại rồi **commit**.
- **expiry:** gửi message TTL ngắn, đợi qua hạn trước khi mở consumer, xác minh không nhận như message còn hiệu lực.
- **priority:** gửi message priority thấp và cao **trước khi mở consumer**, quan sát thứ tự thực tế mà broker chọn, **không assert priority cao bắt buộc đến trước**.

### 9.1. Điều kiện chạy

Cần:

1. Broker Artemis đang chạy; Java client kết nối bằng **tcp://127.0.0.1:61616**, hoặc **61617** nếu đã map riêng host port cho Artemis.
2. Tài khoản có quyền send/consume và được **tạo queue ANYCAST tự động**, hoặc admin phải tạo trước các queue tương ứng. Ví dụ tạo queue tên duy nhất cho mỗi lần chạy để tránh message tồn từ lab cũ.
3. JDK 17+, Maven. Dùng dependency **artemis-jakarta-client** tương thích với broker. Ví dụ phiên bản dùng để mô tả API, cần pin lại theo môi trường triển khai.
4. Với chế độ redelivery, delay/broker policy phải cho phép lần giao lại trong thời gian chờ tối đa **30 giây**; nếu message bị chuyển DLQ ngay hoặc delay dài hơn, cần điều chỉnh policy lab.

Ví dụ **pom.xml** độc lập:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab.messaging</groupId>
    <artifactId>artemis-message-headers-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.42.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.2. Chương trình đầy đủ

Tạo **src/main/java/MessageHeadersLab.java**:

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.Objects;
import java.util.UUID;

public final class MessageHeadersLab {

    public static void main(String[] args) throws Exception {
        if (args.length != 1
                || (!"redelivery".equals(args[0])
                    && !"expiry".equals(args[0])
                    && !"priority".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Usage: redelivery | expiry | priority");
        }

        String brokerUrl = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = Objects.requireNonNull(
                System.getenv("BROKER_USER"), "Missing BROKER_USER");
        String password = Objects.requireNonNull(
                System.getenv("BROKER_PASSWORD"), "Missing BROKER_PASSWORD");

        String queueName = "lab.headers." + args[0] + "."
                + UUID.randomUUID().toString().replace("-", "");

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(brokerUrl);

        switch (args[0]) {
            case "redelivery":
                runRedelivery(factory, user, password, queueName);
                break;
            case "expiry":
                runExpiry(factory, user, password, queueName);
                break;
            case "priority":
                runPriority(factory, user, password, queueName);
                break;
            default:
                throw new IllegalStateException("Unknown mode");
        }

        System.out.println("Finished mode=" + args[0]
                + ", queue=" + queueName);
    }

    private static void runRedelivery(
            ActiveMQConnectionFactory factory,
            String user, String password, String queueName)
            throws Exception {
        try (JMSContext publisher = factory.createContext(
                     user, password, JMSContext.AUTO_ACKNOWLEDGE);
             JMSContext receiver = factory.createContext(
                     user, password, JMSContext.SESSION_TRANSACTED)) {

            Queue queue = publisher.createQueue(queueName);
            TextMessage outgoing = publisher.createTextMessage(
                    "OrderPaid:ORD-321");
            outgoing.setStringProperty("businessEventId", "pay-321");

            publisher.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setPriority(7)
                    .setTimeToLive(0)
                    .send(queue, outgoing);
            show("SENT", outgoing);

            JMSConsumer consumer = receiver.createConsumer(queue);
            Message first = consumer.receive(10000);
            requireMessage(first, "first delivery");
            show("FIRST", first);
            String firstId = first.getJMSMessageID();

            // Chưa commit JMS; broker có thể giao lại.
            receiver.rollback();

            Message second = consumer.receive(30000);
            requireMessage(second, "redelivery");
            show("AGAIN", second);

            if (!firstId.equals(second.getJMSMessageID())) {
                receiver.rollback();
                throw new IllegalStateException(
                        "Expected redelivery of same JMS message");
            }

            receiver.commit();
            System.out.println("ACK via receiver.commit()");
        }
    }

    private static void runExpiry(
            ActiveMQConnectionFactory factory,
            String user, String password, String queueName)
            throws Exception {
        try (JMSContext publisher = factory.createContext(
                     user, password, JMSContext.AUTO_ACKNOWLEDGE);
             JMSContext receiver = factory.createContext(
                     user, password, JMSContext.AUTO_ACKNOWLEDGE)) {

            Queue queue = publisher.createQueue(queueName);
            TextMessage outgoing = publisher.createTextMessage(
                    "Telemetry:temporary");

            publisher.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setPriority(8)
                    .setTimeToLive(1_200L)
                    .send(queue, outgoing);
            show("SENT", outgoing);

            // Đợi message quá hạn trước khi tạo consumer.
            Thread.sleep(2_500L);

            JMSConsumer consumer = receiver.createConsumer(queue);
            Message unexpected = consumer.receive(2_500L);
            if (unexpected != null) {
                show("UNEXPECTED", unexpected);
                throw new IllegalStateException(
                        "Expired message should not be delivered");
            }
            System.out.println("EXPIRED: consumer received none");
        }
    }

    private static void runPriority(
            ActiveMQConnectionFactory factory,
            String user, String password, String queueName)
            throws Exception {
        try (JMSContext publisher = factory.createContext(
                     user, password, JMSContext.AUTO_ACKNOWLEDGE);
             JMSContext receiver = factory.createContext(
                     user, password, JMSContext.AUTO_ACKNOWLEDGE)) {

            Queue queue = publisher.createQueue(queueName);
            TextMessage low = publisher.createTextMessage("LOW");
            TextMessage high = publisher.createTextMessage("HIGH");

            // Gửi cả hai trước khi có consumer nhận.
            publisher.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setPriority(1)
                    .send(queue, low);
            publisher.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setPriority(9)
                    .send(queue, high);

            JMSConsumer consumer = receiver.createConsumer(queue);
            Message one = consumer.receive(10000L);
            Message two = consumer.receive(10000L);
            requireMessage(one, "priority result 1");
            requireMessage(two, "priority result 2");

            show("RECV-1", one);
            show("RECV-2", two);
            System.out.println(
                    "Observe order; JMS priority is not strict FIFO");
        }
    }

    private static void show(String stage, Message message)
            throws JMSException {
        String deliveryCount = message.propertyExists("JMSXDeliveryCount")
                ? Integer.toString(
                        message.getIntProperty("JMSXDeliveryCount"))
                : "n/a";

        String mode = message.getJMSDeliveryMode()
                == DeliveryMode.PERSISTENT
                ? "PERSISTENT" : "NON_PERSISTENT";

        System.out.printf(
                "%s id=%s mode=%s priority=%d expiration=%d"
                + " redelivered=%s deliveryCount=%s%n",
                stage,
                message.getJMSMessageID(),
                mode,
                message.getJMSPriority(),
                message.getJMSExpiration(),
                message.getJMSRedelivered(),
                deliveryCount);
    }

    private static void requireMessage(Message message, String stage) {
        if (message == null) {
            throw new IllegalStateException(
                    "No message during " + stage
                    + "; inspect queue, retry delay and broker policy");
        }
    }
}
~~~

Code dùng các API **Jakarta Messaging** với **Artemis Jakarta client**. Mỗi lần chạy tạo **queue name mới**, tránh lẫn message của lần thử trước nhưng sẽ làm tăng số queue nếu broker cho phép auto-create. Dọn những queue thử nghiệm sau khi quan sát, chỉ thực hiện trên broker lab. Nếu broker tắt auto-create, thay phần tạo tên ngẫu nhiên bằng tên queue đã được admin khai báo đúng kiểu **ANYCAST**.

### 9.3. Cách chạy

Trong PowerShell, đặt thông tin thực của Artemis:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61617"
$env:BROKER_USER = "artemis_app"
$env:BROKER_PASSWORD = "<your-artemis-password>"

mvn -q compile exec:java "-Dexec.mainClass=MessageHeadersLab" "-Dexec.args=redelivery"
mvn -q compile exec:java "-Dexec.mainClass=MessageHeadersLab" "-Dexec.args=expiry"
mvn -q compile exec:java "-Dexec.mainClass=MessageHeadersLab" "-Dexec.args=priority"
~~~

Thay mật khẩu placeholder bằng mật khẩu thật. Nếu Artemis publish trên **61616** thay vì **61617** thì đổi URL cho phù hợp. Đừng dùng URL của ActiveMQ Classic cho **Artemis Jakarta client** trong bài thử này.

**Redelivery:** kỳ vọng thấy **FIRST** và **AGAIN** có cùng JMSMessageID; sau rollback, **JMSRedelivered** thường từ **false** sang **true**, **JMSXDeliveryCount** có thể từ **1** lên **2**. Nếu không nhận lại trong 30 giây, kiểm tra redelivery-delay và max-delivery-attempts; không tự suy là broker làm mất message.

**Expiry:** message PERSISTENT với TTL 1,2 giây vẫn không được giao sau khi đã chờ qua hạn nếu broker áp dụng TTL. Nếu có **ExpiryQueue** được cấu hình, bạn có thể kiểm tra message hoặc số liệu expiry ở đó. Trong thực tế đồng hồ và cơ chế quét expiry gây độ trễ quan sát; script chỉ kiểm tra **không nhận expired message trên queue nguồn**, không cam kết chính xác lúc queue metric giảm.

**Priority:** kết quả nhận có thể là **HIGH trước LOW** khi cả hai đang chờ, nhưng nếu bạn quan sát **LOW trước HIGH** trong một lần chạy thì đó chưa phải bằng chứng cấu hình hỏng. Kiểm tra broker support, prefetch, consumer window và lặp lại nhiều lần dưới tải phù hợp; không được dùng một thử nghiệm đơn lẻ làm hợp đồng sắp thứ tự.

## 10. Kiểm tra cùng header với ActiveMQ Classic (javax.jms)

Trong một dự án **ActiveMQ Classic 5.x** dùng namespace **javax.jms**, đặt delivery mode, priority và TTL bằng overload **MessageProducer.send**:

~~~java
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;

import org.apache.activemq.ActiveMQConnectionFactory;

// Đoạn đặt trong phương thức throws Exception.
// user, password là credential của Classic broker.
ActiveMQConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

Connection connection = factory.createConnection(user, password);
try {
    Session tx = connection.createSession(
            true, Session.SESSION_TRANSACTED);
    try {
        Queue queue = tx.createQueue("lab.classic.headers");
        MessageProducer producer = tx.createProducer(queue);
        try {
            TextMessage message =
                    tx.createTextMessage("OrderPaid:ORD-987");

            producer.send(
                    queue,
                    message,
                    DeliveryMode.PERSISTENT,
                    8,          // JMSPriority
                    15_000L);   // TTL: 15 giây

            tx.commit(); // Send nằm trong JMS transaction.
            System.out.println("DeliveryMode="
                    + message.getJMSDeliveryMode());
            System.out.println("Priority="
                    + message.getJMSPriority());
            System.out.println("Expiration="
                    + message.getJMSExpiration());
        } finally {
            producer.close();
        }
    } finally {
        tx.close();
    }
} finally {
    connection.close();
}
~~~

Mã minh họa rõ **mode/priority/TTL gắn với thao tác send**, còn JMS headers được provider gán trên message. Khi viết consumer Classic, đọc:

~~~java
// received là javax.jms.Message đã nhận.
boolean redelivery = received.getJMSRedelivered();
int priority = received.getJMSPriority();
long expiresAt = received.getJMSExpiration();

String count = received.propertyExists("JMSXDeliveryCount")
        ? Integer.toString(
                received.getIntProperty("JMSXDeliveryCount"))
        : "n/a";
~~~

Các đoạn Classic cần dependency **org.apache.activemq:activemq-client** đúng phiên bản và Java API tương thích. Không trộn import **javax.jms** của ví dụ Classic này với **jakarta.jms** của Artemis trong cùng file; mô hình JMS giống nhau nhưng binary/API artifact không đồng nhất.

### Khi producer gửi lặp trên Classic

Nếu Classic producer timeout, bạn phải kiểm tra xem client có cơ chế duplicate detection/producer sequence phù hợp hay không, nhưng ứng dụng **vẫn phải giữ idempotency key** qua các lần retry và đối soát theo nghiệp vụ. Một JMS message được gửi lần thứ hai từ ứng dụng có thể có **JMSMessageID khác**, dù payload giống nhau. Header **JMSRedelivered** không giải quyết tình huống này.

## 11. Thiết kế business event cùng các JMS header

Bên cạnh JMS headers, producer cần một hợp đồng dữ liệu rõ ràng, ví dụ:

~~~json
{
  "eventId": "pay-932",
  "eventType": "OrderPaid",
  "schemaVersion": 2,
  "orderId": "ORD-932",
  "paidAt": "2026-11-17T10:15:00Z"
}
~~~

Thông điệp có thể đi kèm application properties:

~~~java
message.setStringProperty("eventId", "pay-932");
message.setStringProperty("eventType", "OrderPaid");
message.setIntProperty("schemaVersion", 2);
~~~

**JMSMessageID** là định danh do JMS provider cấp cho một lần gửi. **eventId** là định danh nghiệp vụ; chỉ eventId mới được producer giữ nguyên khi retry cùng event qua timeout, outbox hoặc sự cố mạng.

Gợi ý cấu hình dựa trên yêu cầu thực:

| Loại thông điệp | Mode đề xuất để bắt đầu đánh giá | Priority đề xuất để thử tải | TTL cần cân nhắc | Xử lý khi redelivery |
| --- | --- | --- | --- | --- |
| **OrderPaid / ReserveInventory** | PERSISTENT | 4–7 | Thường không dùng TTL ngắn | Dedup bằng eventId + transaction DB |
| **Notification cần đến trong giờ làm việc** | PERSISTENT | 4 | Theo SLA nghiệp vụ, ví dụ 1 giờ | Idempotency cho email/SMS hoặc mã yêu cầu tại nhà cung cấp |
| **Telemetry vị trí hiện tại** | NON_PERSISTENT | 1–3 | Ngắn, ví dụ 2 giây | Có thể bỏ bản cũ và lấy snapshot mới |
| **Cảnh báo vận hành khẩn** | PERSISTENT | 8–9 | Đặt theo thời hạn hữu ích của cảnh báo | Dedup alertId; giám sát backlog |
| **Báo cáo batch không gấp** | PERSISTENT nếu không được mất | 1–3 | Thường đủ dài để qua bảo trì | Retry có giới hạn + idempotency |

Đây là **các điểm khởi đầu để thiết kế**, không phải chuẩn cấu hình bắt buộc. Thời hạn lưu trữ, quy định nghiệp vụ và khả năng xử lý thực tế mới quyết định TTL và độ bền cuối cùng.

### Idempotent consumer: chặn lặp ở transaction database

Nếu mỗi message **OrderPaid** cập nhật ledger, dùng khóa duy nhất **(consumerName, eventId)** với transaction DB cùng thao tác ledger:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Pseudocode:

~~~text
BEGIN DATABASE TRANSACTION
    INSERT processed_events(consumer_name, event_id)
    IF đã tồn tại:
        bỏ qua side effect
    ELSE:
        cập nhật nghiệp vụ
COMMIT DATABASE TRANSACTION

ACK/COMMIT JMS
~~~

Nếu DB commit xong nhưng JMS ACK lỗi, lần redelivery sẽ gặp **eventId đã được xử lý**, tránh cập nhật lần nữa rồi có thể ACK. Với API ngoài database như thanh toán/HTTP/email, cần idempotency key ở dịch vụ đích hoặc quy trình reconcile, vì transaction DB cục bộ không bao trùm side effect ở hệ thống khác.

## 12. Chẩn đoán message “mất”, “đến muộn” hoặc “được nhận lại”

| Triệu chứng | Kiểm tra header nào trước? | Khả năng cần điều tra |
| --- | --- | --- |
| Producer send thành công nhưng consumer không thấy message | **JMSExpiration**, TTL, destination | Message expired, routing sai, không có subscription, permission/selector |
| Message priority 9 đến sau priority 1 | **JMSPriority**, queue state | Prefetch, consumer đã dispatch message thấp, nhiều worker, policy priority |
| Message còn sau broker restart | **JMSDeliveryMode** | PERSISTENT, queue durable, storage/journal/HA |
| Message mất sau restart | **JMSDeliveryMode**, **JMSExpiration** | NON_PERSISTENT, hết hạn, queue/subscription không bền, policy/storage |
| Consumer nhận cùng JMSMessageID lần hai | **JMSRedelivered**, **JMSXDeliveryCount** | Rollback, connection drop, transaction JMS chưa commit |
| Consumer nhận cùng eventId nhưng hai JMSMessageID khác nhau | **eventId** và **JMSMessageID** | Producer resend/timeout, outbox relay gửi lại |
| Message đến DLQ trước khi đạt lần retry mong muốn | **JMSXDeliveryCount**, DLQ policy | max-delivery-attempts, client RedeliveryPolicy Classic, exception khác |
| Message hết hạn trong khoảng retry | **JMSExpiration**, delay | TTL ngắn hơn thời gian backlog + retry delay |
| Queue size bằng 0 nhưng công việc chưa hoàn tất | In-flight/ACK metric; eventId | Message đang ở consumer, đã ACK quá sớm, expired hoặc được move DLQ |

Khi điều tra, log có cấu trúc ít nhất gồm **eventId**, **JMSMessageID**, destination, **JMSDeliveryMode**, **JMSPriority**, **JMSExpiration**, **JMSRedelivered**, **JMSXDeliveryCount** (nếu có), thời điểm nhận, kết quả DB commit và kết quả JMS ACK. Tránh log credential hoặc payload chứa dữ liệu cá nhân không cần thiết.

### Thứ tự phân tích nên đi theo thời gian

1. **Lúc gửi:** producer đặt QoS options gì, send/commit có trả về thành công hay timeout?
2. **Lúc route/enqueue:** message vào đúng queue/subscription chưa, có queue tồn tại và quyền phù hợp không?
3. **Trong khi chờ:** message có hết TTL hoặc bị ưu tiên thấp kéo dài backlog không?
4. **Khi dispatch:** consumer nhận lần đầu hay redelivery, delivery count bao nhiêu?
5. **Sau xử lý:** database đã commit chưa, JMS ACK/commit đã thành công chưa?
6. **Khi không còn ở queue chính:** message đã ACK, expire, chuyển DLQ, bị admin purge hay route sang destination khác?

Chỉ từ **JMSRedelivered=false** hoặc **queue size=0** không thể kết luận một event chưa từng bị trùng, đã được xử lý đúng, hay bị mất ở producer.

## 13. Thí nghiệm tự kiểm chứng và tiêu chí đạt

### A. So PERSISTENT với NON_PERSISTENT

Gửi hai message vào **queue thử nghiệm còn tồn tại**, mỗi message có eventId khác nhau. Một message PERSISTENT, một message NON_PERSISTENT, TTL 0. Dừng broker theo kịch bản kiểm thử thích hợp rồi khởi động lại, không xóa volume dữ liệu. Quan sát khả năng nhận lại; cần lưu ý **NON_PERSISTENT không bảo đảm bị mất**, mà chỉ không có cùng cam kết độ bền. Để so sánh thực tế, lặp dưới các kiểu restart/failure được cho phép ở môi trường lab.

### B. So priority

Trước khi có consumer, enqueue nhiều message **priority 1** và **priority 9**, sau đó mở consumer và ghi thứ tự. Lặp khi bật prefetch/consumer concurrency khác nhau. Chỉ ra vì sao **có xu hướng ưu tiên** không đồng nghĩa **bảo đảm priority 9 luôn được xử lý xong trước priority 1**.

### C. Chứng minh expiry

Gửi một message **PERSISTENT + TTL 1.200 ms**, chờ quá 2 giây trước khi mở consumer. Xác nhận consumer không nhận message hết hạn; nếu đã cấu hình expiry queue, kiểm tra việc broker chuyển message theo policy. Đối chiếu **JMSExpiration** với thời điểm gửi và thời điểm quan sát, chú ý broker xử lý expiry có thể không đúng từng mili giây.

### D. Chứng minh redelivery

Receive bằng **SESSION_TRANSACTED**, log **JMSMessageID/JMSRedelivered/JMSXDeliveryCount**, rồi gọi **rollback()**. Receive lại và đối chiếu hai lần. Sau đó commit. Thử thay redelivery-delay và max-delivery-attempts để thấy tác động của broker policy. Nếu cần dead-letter, dùng queue test và thời hạn phù hợp để tránh làm nghẽn consumer.

### E. Chứng minh producer retry có thể trùng mà cờ redelivery vẫn false

Gửi **hai message khác nhau có cùng businessEventId**, ví dụ mô phỏng producer gửi lại sau timeout. Trên consumer, có thể thấy **hai JMSMessageID** và hai lần nhận đầu với **JMSRedelivered=false**. Dùng bảng **processed_events** để chỉ cho phép side effect xuất hiện một lần.

| Tiêu chí nghiệm thu | Đạt khi |
| --- | --- |
| Đọc chính xác JMSDeliveryMode/Priority/Expiration | Consumer và producer log đúng giá trị provider gán |
| Hiểu expiration | Phân biệt TTL tương đối lúc gửi với timestamp JMSExpiration tuyệt đối |
| Hiểu priority | Giải thích được vì sao không có thứ tự ưu tiên toàn cục tuyệt đối |
| Hiểu redelivery | Thấy rollback gây giao lại và đọc đúng trạng thái/counter |
| Phân biệt resend và redelivery | Biết rằng producer retry có thể sinh JMSMessageID mới cùng eventId |
| Phối hợp broker policy | Xác định được phần thuộc Artemis address-settings và Classic RedeliveryPolicy |
| Xử lý side effect an toàn | Dùng idempotency key ổn định, không phụ thuộc cờ JMSRedelivered |

## 14. Checklist thiết kế message trước khi đưa vào vận hành

- **JMSDeliveryMode:** dữ liệu mất đi có gây sai nghiệp vụ không? Broker có persistence, journal, queue/subscription bền và topology HA phù hợp chưa?
- **JMSPriority:** mức ưu tiên có thực sự cần không? Đã đo backlog/prefetch và starvation trên tải thật chưa?
- **JMSExpiration:** TTL bao nhiêu và dựa trên SLA nào? Việc message tự expire có chấp nhận được và có cần expiry archive/audit không?
- **Redelivery:** consumer dùng transaction hoặc ACK phù hợp? Retry delay, max attempts và DLQ đã cấu hình đúng trên Classic/Artemis chưa?
- **Định danh:** application eventId có giữ nguyên qua producer retry/outbox replay không? Consumer đã deduplicate ở transaction chứa side effect chưa?
- **Quan sát:** log/metrics đủ để phân biệt expired, DLQ, sent twice, broker redelivery và ACK thành công chưa?
- **Bảo mật:** ai được gửi, nhận, browse DLQ/expiry; payload và headers có lộ dữ liệu nhạy cảm không?

Với ActiveMQ Classic và Artemis, **JMSDeliveryMode** điều khiển yêu cầu độ bền, **JMSPriority** gợi ý thứ tự dispatch, **JMSExpiration** giới hạn thời hạn giao message, còn **JMSRedelivered/JMSXDeliveryCount** mô tả lịch sử giao lại của provider. Dùng chúng cùng nhau để thiết kế vận chuyển đáng tin cậy, đồng thời dựa vào **eventId, transaction nghiệp vụ và idempotency** để bảo vệ kết quả cuối cùng.
