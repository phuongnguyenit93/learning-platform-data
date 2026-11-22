# Time-to-live, hết hạn và xử lý thông điệp đã quá thời điểm hữu ích

> **Chương:** Thứ tự và thời gian  
> **Phạm vi:** Apache ActiveMQ Classic và Apache Artemis trong luồng queue/topic bất đồng bộ bằng Java/JMS. Bài phân biệt **message expiration do broker xử lý** với **hạn sử dụng thực tế của nghiệp vụ**, thiết kế TTL không gia hạn vô ý khi retry/chuyển tiếp, và kiểm chứng trên broker. Ví dụ dùng JDK 17, `jakarta.jms` và Artemis 2.57.x/ActiveMQ Classic 6.x; khi dùng Classic 5.x cần chọn namespace/provider JMS tương ứng.

## 1. Hai chiếc đồng hồ: TTL của broker và deadline nghiệp vụ

Một ứng dụng giá vé phát sự kiện `FareQuoteReady` lúc 10:00 với báo giá chỉ còn hữu ích đến 10:00:05. Message bị giữ trong queue vì consumer đang tạm dừng; đến 10:00:08 mới có consumer nhận. Xử lý báo giá cũ lúc đó có thể tạo quyết định sai, ngay cả khi payload hoàn toàn hợp lệ.

Hệ thống cần xét **hai điều kiện độc lập**:

1. **Hết hạn ở broker:** producer gửi message với time-to-live (`TTL`). Provider gắn thời điểm hết hạn tuyệt đối vào header `JMSExpiration`. Broker hạn chế phân phối message đã hết hạn và xử lý nó theo chính sách expiry.
2. **Quá hạn nghiệp vụ:** một thuộc tính của chính sự kiện, ví dụ `businessDeadlineEpochMs`, chỉ thời điểm mà dữ liệu không còn được phép tác động đến nghiệp vụ. Consumer **phải tự kiểm tra** deadline, kể cả khi message vẫn chưa hết `JMSExpiration` hoặc đã được nhận trước lúc hết TTL.

```text
10:00:00          10:00:03            10:00:05              10:00:08
   │                 │                    │                     │
   ├── publish ──────┼── backlog ─────────┼── deadline ─────────┤
   │                                      │                     └── consumer online
   └───────────── TTL = 5 giây ──────────┘
                                          │
                             Broker không nên giao mới
                             Consumer vẫn phải kiểm tra deadline
```

**Không đồng nhất ba trạng thái:** `message được gửi thành công`, `message được phân phối` và `nghiệp vụ đã xử lý hợp lệ`. TTL chỉ giúp loại bỏ những message không còn đáng giao; nó **không thu hồi** cuộc gọi HTTP, giao dịch database hay kết quả mà consumer đã bắt đầu thực hiện.

| Tình huống | `JMSExpiration` | `businessDeadlineEpochMs` | Xử lý thích hợp |
|---|---|---|---|
| Báo giá có giá trị 5 giây | Có, khoảng 5 giây sau gửi | Cùng hạn báo giá hoặc ngắn hơn một biên an toàn | Broker expiry + kiểm tra tại consumer |
| Email marketing không cần gửi sau 7 ngày | Có thể đặt 7 ngày | Thường có hạn chiến dịch độc lập | Nếu quá hạn, không gửi email; lưu lý do bỏ qua |
| Sự kiện kế toán phải lưu đầy đủ | Thường `0` (không TTL) | Có thể có thời hạn SLA, nhưng không có nghĩa được xóa sự kiện | Giữ/replay/đối soát theo chính sách retention |
| Cache invalidation tạm thời | TTL ngắn có thể hợp lý | Consumer cần xác định cache version | Bỏ message stale hoặc ưu tiên version mới hơn |
| Lệnh hoàn tiền chưa được xử lý | Không tự hủy chỉ vì đợi lâu | Cần quy trình quyết định hợp lệ của nghiệp vụ | Escalate, bù trừ hoặc phê duyệt; **không** lặng lẽ drop |

TTL là **chính sách phân phối**, không phải công cụ giải quyết mọi yêu cầu lưu trữ hoặc tính đúng đắn nghiệp vụ.

## 2. JMS tính thời điểm hết hạn như thế nào?

Jakarta Messaging xác định:

\[
\text{JMSExpiration} =
\begin{cases}
0 & \text{nếu TTL = 0 (không hết hạn)}\\
t_{\text{send}} + \text{TTL}_{ms} & \text{nếu TTL > 0}
\end{cases}
\]

`t_send` là **thời điểm message được gửi**, tính bằng mili giây theo epoch (UTC). Với **transacted send**, thời điểm này là lúc client gọi gửi, **không phải lúc transaction commit**. `setTimeToLive(0)` là giá trị mặc định và có nghĩa **không tự hết hạn**.

Ví dụ:

| Thao tác | Kết quả |
|---|---|
| Gửi 10:00:00 với `setTimeToLive(3000)` | `JMSExpiration≈10:00:03` |
| Gửi trong transaction lúc 10:00:00, commit 10:00:05 | Message đã quá thời hạn ở thời điểm commit; không được giả định có thêm 3 giây từ commit |
| Gửi với `setTimeToLive(0)` | `JMSExpiration=0`, broker không tự hết hạn do TTL |
| Gửi với `setDeliveryDelay(10000)` và TTL 3000 ms | Thời điểm có thể giao đầu tiên **muộn hơn** expiration; message có thể hết hạn trước khi được phân phối |

**Ví dụ Jakarta Messaging API:**

```java
try (JMSContext context = factory.createContext(user, password)) {
    Queue queue = context.createQueue("quotes.live");
    context.createProducer()
        .setDeliveryMode(DeliveryMode.PERSISTENT)
        .setTimeToLive(3_000L)
        .send(queue, "quote-123");
}
```

Trong cách dùng JMS truyền thống, gọi `MessageProducer.setTimeToLive(3000)` trước `send`; có thể đặt TTL riêng cho mỗi lần gửi bằng overload `send` nhận delivery mode, priority và TTL. **Không** dùng `message.setJMSExpiration(...)` để ra lệnh đặt TTL: `JMSExpiration` là **header đầu ra do provider quản lý** trong quá trình gửi.

### Phân biệt TTL, delivery delay, redelivery delay và retention

| Tham số | Trả lời câu hỏi | Khi nào bắt đầu tính? |
|---|---|---|
| `timeToLive` | Message còn được phép giao trong bao lâu? | Tại `send` |
| `deliveryDelay` | Ít nhất phải đợi bao lâu trước lần giao đầu? | Tại `send` |
| `redelivery-delay` của Artemis | Sau rollback phải đợi bao lâu mới giao lại? | Khi cần lên lịch redelivery |
| `expiry-delay` của Artemis | Broker gắn expiry ra sao cho message đầu vào theo policy? | Khi broker áp dụng address settings |
| Data retention/audit policy | Cần giữ bằng chứng bao lâu dù message không còn được giao? | Theo yêu cầu lưu trữ và tuân thủ, không phải TTL JMS |

Một message có thể vừa chờ redelivery vừa tiến đến `JMSExpiration`. **Redelivery không tự gia hạn TTL**. Nếu TTL đã vượt quá, broker cần xử lý expiration thay vì cứ tiếp tục retry vô hạn.

## 3. Expiration không có nghĩa xóa vật lý đúng mili giây

JMS yêu cầu provider nỗ lực không phân phối message đã hết hạn nhưng **không cam kết độ chính xác tới từng mili giây**. Broker có thể phát hiện message expired trong lúc nhận vào, chuẩn bị dispatch, duyệt queue hoặc ở lần quét định kỳ. Vì vậy:

- Message có thể **tạm còn trong thống kê queue** sau thời điểm `JMSExpiration` cho đến khi broker quét/đụng tới nó; điều này không đồng nghĩa nó vẫn được phép giao mới.
- Trong một số race condition hoặc message đã được cấp cho consumer trước hạn, ứng dụng có thể thấy message dù hạn nghiệp vụ đã trôi qua. JMS specification **không bảo đảm tuyệt đối** mọi client không bao giờ nhận message expired.
- Expiration **không hủy** message đã được consumer nhận trước deadline và đang xử lý ở phía ứng dụng. Consumer phải kiểm tra hạn **trước side effect** và, nếu công việc kéo dài, kiểm tra lại ở điểm quyết định.
- Thời điểm hết hạn phụ thuộc đồng hồ producer/provider và broker. Đồng bộ đồng hồ bằng NTP, ghi timestamp UTC và quan sát clock skew; không thiết kế biên an toàn chỉ vài mili giây khi hệ thống phân tán có độ trễ lớn.

### Hạn kỹ thuật và hạn nghiệp vụ có thể lệch

Giả sử sự kiện được tạo lúc 10:00:00 với deadline 10:00:10, nhưng outbox relay chỉ gửi vào 10:00:08. Nếu relay luôn đặt `TTL=10000`, broker giữ message đến **10:00:18** — quá thời điểm sử dụng đúng tới **8 giây**.

**Cách đúng:** lưu một **deadline tuyệt đối** khi tạo sự kiện, sau đó mỗi lần gửi/retry tính lại TTL từ **phần thời gian còn lại**. Đừng gửi lại với TTL nguyên gốc, vì hành vi đó gia hạn hiệu lực ngoài ý muốn.

## 4. Artemis: chuyển message expired sang một expiry address

Artemis cho phép định tuyến message hết hạn đến một **expiry address** để điều tra thay vì bỏ ngay. Cấu hình này **khác** `dead-letter-address`: expiry dành cho **quá thời gian**, còn DLQ chủ yếu cho **thất bại xử lý/đủ số lần giao**. Không trộn hai loại message nếu cần vận hành và replay độc lập.

### 4.1. `broker.xml` cho lab

Đặt các fragment vào **các khối đã có** trong `<core>` của `broker.xml`, không tạo phần tử `<addresses>` hoặc `<address-settings>` trùng lặp.

**Bên trong `<address-settings>`:**

```xml
<!-- Expiry đúng cho address nguồn. -->
<address-setting match="quotes.live">
    <expiry-address>quotes.expired</expiry-address>
</address-setting>

<!-- Không tự vòng lại chính expiry address. -->
<address-setting match="quotes.expired">
    <expiry-address/>
</address-setting>
```

**Bên trong `<addresses>`:**

```xml
<address name="quotes.live">
    <anycast>
        <queue name="quotes.live"/>
    </anycast>
</address>

<address name="quotes.expired">
    <anycast>
        <queue name="quotes.expired"/>
    </anycast>
</address>
```

**Bên trong `<core>` nếu muốn quét nhanh hơn cho lab:**

```xml
<message-expiry-scan-period>1000</message-expiry-scan-period>
```

Đơn vị `message-expiry-scan-period` là **ms**; giá trị mặc định của Artemis 2.57.0 là **30.000 ms**, `-1` tắt reaper thread. Một giây chỉ thích hợp để dễ quan sát trong lab; cấu hình quá nhỏ khi có hàng triệu queue/message có thể làm tăng chi phí CPU/I/O. Cần restart/reload theo cơ chế bản broker đang chạy và xác minh XML được áp dụng bằng log/management trước khi test.

Nếu source message hết hạn, Artemis có thể đưa nó từ `quotes.live` sang `quotes.expired`, giữ các thuộc tính hỗ trợ điều tra; trong đó `_AMQ_ACTUAL_EXPIRY` là một thuộc tính Long chứa thời điểm **thực tế** broker xử lý expiry. Nếu không đặt `expiry-address` (hoặc chủ động khai báo rỗng), message expired bị **loại bỏ** khỏi queue thay vì chuyển đến nơi theo dõi. <https://artemis.apache.org/components/artemis/documentation/latest/message-expiry.html>

**Không nhầm ba mốc thời gian:**

- `JMSExpiration`: hạn kỹ thuật ban đầu của message (deadline để broker không phân phối tiếp).
- `_AMQ_ACTUAL_EXPIRY`: thời điểm Artemis đã phát hiện/xử lý sự kiện hết hạn.
- `businessDeadlineEpochMs`: hạn nghiệp vụ độc lập do ứng dụng định nghĩa và được bảo toàn qua luồng xử lý.

Với hàng đợi expiry dùng để audit, cần một **chính sách retention riêng** (ví dụ tối đa 7 ngày theo yêu cầu quản trị), quyền truy cập và giám sát. Việc chuyển message vào expiry queue **không có nghĩa dữ liệu được lưu mãi mãi hoặc an toàn để replay tự động**.

### 4.2. `expiry-delay`, `min-expiry-delay`, `max-expiry-delay` và `no-expiry`

Artemis còn có chính sách áp **hoặc điều chỉnh** hạn của message khi message đến address:

| Property trên `address-setting` | Tác dụng | Lưu ý |
|---|---|---|
| `no-expiry=true` | Xóa mọi expiration (`0`), bất kể producer đặt TTL nào | Đứng ưu tiên cao nhất; có thể vô hiệu hóa hạn hữu ích của nghiệp vụ |
| `expiry-delay=60000` | Gán 60 giây cho message **chưa có expiration** (`0`) | Không thay hạn đã đặt bởi producer |
| `min-expiry-delay=1000` | Nâng expiry delay thấp hơn 1 giây lên ít nhất 1 giây | Có thể **gia hạn** message lẽ ra phải hết hạn sớm |
| `max-expiry-delay=60000` | Giới hạn delay tối đa là 60 giây | Message chưa có expiration cũng có thể được gán hạn theo max |
| `expiry-address` | Đích của message đã hết hạn | Không phải nơi nhận message redelivery thất bại |

Thứ tự ưu tiên của Artemis: **`no-expiry` → `expiry-delay` → `min/max-expiry-delay`** (nhóm được chọn trước làm các nhóm sau không còn tác dụng). Mặc định `no-expiry=false`, `expiry-delay=-1`, min/max `-1`, nghĩa là không bật chính sách override. Nếu cấu hình của source áp dụng wildcard, hãy kiểm tra policy **thực sự khớp address** trước khi kết luận provider đặt sai TTL.

**Ví dụ một policy thay thế dành cho hệ thống nhận message từ nhiều producer không kiểm soát TTL:**

```xml
<address-setting match="quotes.live">
    <expiry-address>quotes.expired</expiry-address>
    <max-expiry-delay>10000</max-expiry-delay>
</address-setting>
```

Policy trên giới hạn/đặt TTL tương ứng **10 giây** ở broker; nó **không thể hiểu hạn nghiệp vụ** của từng báo giá nếu producer không truyền deadline. Ngược lại, `min-expiry-delay` có thể làm message tồn tại lâu hơn dự tính, nên chỉ dùng khi có lý do chắc chắn. **Đừng ghép hai `address-setting` cùng `match`**: khi thực hành, chọn **một** trong các biến thể cấu hình.

### 4.3. Vòng đời expiry queue

Artemis có thể **tự tạo expiry resources** (`auto-create-expiry-resources`) với các quy tắc prefix/suffix, nhưng queue tự tạo có thể chịu chính sách auto-delete. Với phòng lab cần kiểm tra đơn giản, việc **khai báo tường minh** `quotes.expired` như trên dễ audit hơn.

Nếu muốn message **đã chuyển vào expiry queue** cũng hết hạn sau 7 ngày, phải cấu hình riêng cho `quotes.expired` và tránh định tuyến nó trở lại chính nó; cần quyết định rõ đó là thời hạn giữ **bằng chứng**, không phải gia hạn cơ hội xử lý nghiệp vụ. Thay expiry queue bằng chính DLQ chung làm khó phân biệt “quá hạn” với “xử lý thất bại” và có thể phát sinh vòng lặp nếu policy được gắn quá rộng.

## 5. ActiveMQ Classic: expiration và quyết định đưa vào DLQ

Classic cũng tính `JMSExpiration` từ TTL ở phía producer, rồi broker/client kiểm tra khi message đi qua queue. Nhưng Classic **không dùng** `<expiry-address>` của Artemis. Đối với Classic, message hết hạn có thể đi qua **dead-letter strategy**.

**Ví dụ chỉ muốn bỏ expired messages trong một queue lab**, giữ cơ chế DLQ cho poison messages khác:

```xml
<!-- Đoạn trích đặt trong destinationPolicy/policyMap/policyEntries
     của conf/activemq.xml hoàn chỉnh. -->
<policyEntry queue="quotes.live">
    <deadLetterStrategy>
        <sharedDeadLetterStrategy processExpired="false"/>
    </deadLetterStrategy>
</policyEntry>
```

`processExpired="false"` nói với Classic **không đưa các expired messages vào DLQ** mà loại chúng đi. Nếu muốn giữ expired messages để đối soát thì **không bật** tùy chọn loại bỏ này; thiết kế dead-letter strategy riêng với phân loại rõ ràng, xác nhận cách broker ghi metadata để phân biệt expired với poison. Cấu hình `deadLetterStrategy` còn có tác động đến xử lý message không thể giao khác, vì vậy phải **review policy hiện có**, tránh ghi đè strategy nghiệp vụ chỉ vì muốn giảm expired backlog.

Không cấu hình expiration trên mọi DLQ bằng một policy wildcard `queue=">"` thiếu kiểm soát. Tài liệu Classic cảnh báo nếu bản ghi trong DLQ tiếp tục expire và được chuyển sang DLQ khác, có thể tạo **vòng lặp**. Đừng dùng `purge` như cách làm sạch expired queue khi chưa có chính sách lưu chứng cứ và phê duyệt xóa.

### Khác nhau về khả năng quan sát

| Câu hỏi | ActiveMQ Classic | Apache Artemis |
|---|---|---|
| Ai đặt hạn message? | Producer theo JMS TTL hoặc cơ chế provider tương ứng | Producer/JMS TTL và/hoặc address-setting override |
| Broker xử lý expired ra đâu? | Theo dead-letter strategy (`processExpired`), hoặc drop | `expiry-address`, hoặc drop nếu không có |
| Có queue riêng cho expiry? | Cần thiết kế từ dead-letter strategy/quan sát phù hợp; không có `expiry-address` của Artemis | Khai báo `expiry-address` và queue cụ thể, hoặc auto-create expiry resources |
| Chu kỳ quét? | Broker có kiểm tra expiry khi dispatch/destination scan; xem tham số phiên bản và metrics | `message-expiry-scan-period` ở `broker.xml` |
| Metadata quan sát? | `JMSExpiration`, broker stats, JMX expired count, destination policy | `JMSExpiration`, `_AMQ_ACTUAL_EXPIRY`, expiry queue và management counters |

Nên dùng **metrics expired/expiry routed**, backlog của expiry queue và consumer logs thay vì phỏng đoán từ một lần `QueueSize=0`: message có thể đã hết hạn, được consumer khác đọc, chuyển expiry hoặc bị xóa theo policy.

## 6. Cấu hình producer: deadline tuyệt đối, TTL còn lại và không gia hạn lúc retry

Đối với dữ liệu có hạn nghiệp vụ, nên tạo `businessDeadlineEpochMs` **ngay tại sự kiện nguồn**; mỗi lần relay/retry/chuyển tiếp dùng lại giá trị đó.

Ví dụ đơn hàng có báo giá chỉ có hiệu lực đến `deadlineEpochMs`. Cần chừa **biên an toàn** cho mạng, broker và độ lệch đồng hồ:

\[
\text{TTL còn lại} = \text{deadline} - \text{now} - \text{safetyMargin}
\]

Nếu kết quả `≤ 0`: **không gửi nữa** (bản ghi đã hết giá trị nghiệp vụ). Nếu kết quả `> 0`: đặt TTL đúng phần còn lại, không dùng TTL gốc.

**Đặc biệt quan trọng:** `setTimeToLive(0)` nghĩa là **không bao giờ hết hạn**. Vì vậy không viết `setTimeToLive(Math.max(0, remaining))` — khi `remaining≤0`, phép này vô tình biến message quá hạn thành message không có expiry!

### 6.1. Mã Java dùng được với cả hai provider JMS

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;

import java.time.Clock;

public final class DeadlinePublisher {
    private static final long SAFETY_MARGIN_MS = 250L;

    private final ConnectionFactory factory;
    private final Clock clock;

    public DeadlinePublisher(ConnectionFactory factory, Clock clock) {
        this.factory = factory;
        this.clock = clock;
    }

    // true = đã gọi send và provider trả về thành công.
    // false = chưa gửi vì đã qua deadline; trạng thái này phải audit riêng.
    public boolean publish(String user, String password,
                           String eventId, String payload,
                           long deadlineEpochMs) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        long remaining = deadlineEpochMs - clock.millis() - SAFETY_MARGIN_MS;
        if (remaining <= 0L) {
            System.out.println("SKIP_EXPIRED eventId=" + eventId);
            return false;
        }

        try (JMSContext context = factory.createContext(user, password)) {
            Queue queue = context.createQueue("quotes.live");
            context.createProducer()
                .setDeliveryMode(DeliveryMode.PERSISTENT)
                .setTimeToLive(remaining)
                .setProperty("eventId", eventId)
                .setProperty("businessDeadlineEpochMs", deadlineEpochMs)
                .send(queue, payload);
            return true;
        }
    }
}
```

Code sử dụng **API Jakarta Messaging chung** và `Clock` có thể thay bằng `Clock.fixed` trong unit test. Phần tạo `ConnectionFactory` phải dùng đúng provider:

- Classic 6.x: `org.apache.activemq:activemq-client` và `org.apache.activemq.ActiveMQConnectionFactory` — OpenWire.
- Artemis 2.x: `org.apache.artemis:artemis-jakarta-client` và `org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory` — Core.

Ví dụ dependency Jakarta cho Artemis:

```xml
<dependency>
    <groupId>org.apache.artemis</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.57.0</version>
</dependency>
```

**Giới hạn của công thức:** TTL được provider neo vào **thời điểm send thực tế**, có thể muộn hơn thời điểm ứng dụng tính `remaining`. Biên an toàn giúp giảm sai số nhưng **không bảo đảm** tuyệt đối khi đồng hồ lệch hoặc quá trình gửi bị treo. Do đó producer vẫn phải giữ deadline tuyệt đối trong message và consumer phải xác nhận lại trước khi có side effect. Khi gửi xảy ra timeout/mất phản hồi, giữ `eventId` và `deadlineEpochMs` cố định để retry/idempotency; đừng tạo event ID/deadline mới.

### 6.2. Consumer kiểm tra lại thời điểm hữu ích

Kể cả khi broker đã giao message trước `JMSExpiration`, worker có thể chờ trong RAM, xử lý chậm hoặc bị tạm dừng. Đặt kiểm tra deadline tại **điểm trước khi thay đổi nghiệp vụ**:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;

import java.time.Clock;

public final class DeadlineConsumer {
    public static void consumeOnce(ConnectionFactory factory,
                                   String user, String password,
                                   Clock clock) throws Exception {
        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue input = context.createQueue("quotes.live");
            Message message = context.createConsumer(input).receive(5_000L);
            if (message == null) {
                return;
            }

            String eventId = message.getStringProperty("eventId");
            if (!message.propertyExists("businessDeadlineEpochMs")) {
                // Chính sách lab: thiếu deadline -> bỏ qua, ghi metric;
                // production phải xử lý theo contract/schema của hệ thống.
                System.out.println("REJECT_MISSING_DEADLINE " + eventId);
                context.commit();
                return;
            }

            long deadline = message.getLongProperty("businessDeadlineEpochMs");
            if (clock.millis() >= deadline) {
                // Quá hạn nghiệp vụ: ACK bằng commit để không rollback vô hạn.
                // Audit bằng eventId; không gọi side effect.
                System.out.println("SKIP_STALE " + eventId);
                context.commit();
                return;
            }

            // Ví dụ: phép biến đổi chỉ trong RAM; chưa thực hiện side effect.
            String body = message.getBody(String.class);
            System.out.println("READY_TO_PROCESS " + eventId + " " + body);
            context.commit();
        }
    }
}
```

Trong hệ thống thật, đừng `commit()` input sau dòng `READY_TO_PROCESS` nếu chưa hoàn tất xử lý được bảo đảm. Nếu có DB/HTTP side effect, phải thiết kế transaction/outbox/idempotency và **kiểm tra deadline ngay trước side effect**. Đối với message đã được nhận nhưng đang xử lý chậm, kiểm tra hạn một lần lúc `receive()` chưa đủ.

**Phân loại bỏ qua nên có metric riêng:**

- `BROKER_EXPIRED`: broker tự hết hạn message chưa được giao.
- `APP_STALE`: consumer nhận được message nhưng kiểm tra deadline nghiệp vụ không còn hợp lệ.
- `APP_REJECTED`: thiếu/sai schema, không có deadline hợp lệ.
- `PROCESSED`: đã hoàn tất side effect đúng hạn theo quy trình nghiệp vụ.

Đừng gom tất cả vào `ERROR` hay retry liên tục message chắc chắn đã quá hạn. Một message stale cần xử lý như một **quyết định được ghi nhận**, không phải lỗi tạm thời.

## 7. Lab Artemis: chứng minh broker hết hạn và chuyển expiry queue

Lab này **không sử dụng DLQ**, chỉ expiry address riêng `quotes.expired`. Giả định các fragment ở mục 4.1 đã được áp dụng và broker `Artemis 2.57.x` đang chạy với Core protocol trên `tcp://127.0.0.1:61616`. Chỉ chạy trên queue lab trống, một producer và không có consumer khác.

### 7.1. Probe Java

```java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.UUID;

public final class ArtemisExpiryProbe {
    public static void main(String[] args) throws Exception {
        String user = System.getenv("BROKER_USER");
        String password = System.getenv("BROKER_PASSWORD");
        if (user == null || password == null) {
            throw new IllegalArgumentException("Missing broker credentials");
        }

        String eventId = "exp-" + UUID.randomUUID();
        ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(
            "tcp://127.0.0.1:61616");
        try {
            // Không có consumer ở source lúc message còn sống.
            try (JMSContext sender = factory.createContext(user, password)) {
                sender.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setTimeToLive(1_500L)
                    .setProperty("labEventId", eventId)
                    .send(sender.createQueue("quotes.live"), "expired-quote");
            }

            // Chờ vượt TTL. Không dùng 1.500 ms sát ranh giới clock.
            Thread.sleep(3_000L);

            try (JMSContext source = factory.createContext(user, password)) {
                Message unexpected = source.createConsumer(
                    source.createQueue("quotes.live")).receive(1_000L);
                if (unexpected != null) {
                    throw new IllegalStateException(
                        "Source delivered a message expected to be expired");
                }
            }

            // Expiry queue được tách riêng, không tiêu thụ queue DLQ.
            try (JMSContext inspect = factory.createContext(user, password)) {
                Message expired = inspect.createConsumer(
                    inspect.createQueue("quotes.expired")).receive(10_000L);
                if (expired == null ||
                    !eventId.equals(expired.getStringProperty("labEventId"))) {
                    throw new IllegalStateException("Expiry record missing");
                }

                if (expired.propertyExists("_AMQ_ACTUAL_EXPIRY")) {
                    System.out.println("actualExpiryEpochMs=" +
                        expired.getLongProperty("_AMQ_ACTUAL_EXPIRY"));
                }
                System.out.println("PASS: expired eventId=" + eventId);
            }
        } finally {
            factory.close();
        }
    }
}
```

**Điểm cần hiểu trước khi chạy:** ví dụ dùng consumer `AUTO_ACKNOWLEDGE` ở queue expiry nên **sẽ tiêu thụ bản ghi expiry của lab**. Nó không dành cho queue audit production. Với các lần chạy lặp, bảo đảm queue được cô lập; nếu đã có message expiry cũ, consumer có thể đọc message khác trước, làm assertion thất bại. Khi kiểm tra thực tế có dữ liệu, dùng `QueueBrowser` hoặc management API read-only và lọc theo ID thay vì ack bừa.

**Kết quả mong đợi:** không có message nào được nhận từ `quotes.live` sau 3 giây; có một message cùng `labEventId` ở `quotes.expired`; property `_AMQ_ACTUAL_EXPIRY` giúp thấy lúc broker thực sự chuyển expiry. Nếu broker dùng scan period mặc định 30 giây thay vì 1 giây, cần tăng thời gian quan sát/poll expiry queue; **không** suy rằng một lần `receive(1000)` trả null có nghĩa message đã được chuyển ngay lập tức.

### 7.2. Bốn phép thử phát hiện lỗi thiết kế

| Kịch bản | Cách thử | Điều cần xác minh |
|---|---|---|
| **A — hết hạn trước consumer** | TTL 1,5s, không tạo consumer trong 3s | Không giao mới; Artemis chuyển message sang expiry queue khi được quét |
| **B — đã nhận trước hạn, xử lý quá lâu** | Consumer nhận trong 0,5s, chờ 2,5s rồi mới tới side effect | Code kiểm tra `businessDeadlineEpochMs` và **không** làm side effect muộn |
| **C — deliveryDelay lớn hơn TTL** | `setDeliveryDelay(5000)`, `setTimeToLive(1500)` | Message có thể expired trước khi đủ điều kiện giao; không giả định vẫn sẽ nhận sau 5s |
| **D — transactional send commit muộn** | Gửi lúc T0 với TTL 1,5s trong transacted Session; commit sau T0+3s | Hạn bắt đầu lúc **send**, không gia hạn từ commit |
| **E — retry làm trôi deadline** | Tạo event deadline T0+5s; gửi ở T0+4s, retry ở T0+6s | Retry ở T0+6s bị **skip**, không phát với TTL gốc 5s |

Kịch bản B và E quan trọng hơn một phép thử broker thuần túy vì chúng chứng minh **không tạo tác dụng nghiệp vụ sau deadline**. Bài lab chỉ đo kết quả dự kiến; các ví dụ code trên chưa được thực thi trong môi trường học này.

## 8. Các lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân có khả năng | Cách kiểm tra và xử lý |
|---|---|---|
| Message tưởng phải hết hạn nhưng còn trong queue | TTL bị đặt `0`, policy `no-expiry`, hoặc scan chưa tới | Xem `JMSExpiration`, cấu hình address-setting, chu kỳ expiry reaper |
| Message biến mất khỏi source nhưng không ở expiry queue Artemis | `expiry-address` chưa đặt, không có queue đích hoặc policy khác đang hiệu lực | Xem `broker.xml` hiệu lực, log và address/queue thực |
| Classic có expired message trong DLQ chung | `processExpired` còn bật theo dead-letter strategy | Quyết định cần audit hay drop, cấu hình prefix/strategy phù hợp |
| Có expired message nhưng consumer vẫn đã xử lý | Message được nhận trước hết hạn, hoặc có race/prefetch/clock skew | Kiểm tra `businessDeadlineEpochMs` ngay trước side effect |
| Retry gửi lại message vô hạn thời gian | Mỗi retry dùng TTL ban đầu như lúc tạo event | Giữ deadline tuyệt đối, tính TTL còn lại; quá hạn thì không gửi |
| Message hết hạn quá sớm ở broker | Clock producer và broker lệch, TTL quá ngắn cho latency thực | Đồng bộ thời gian, quan sát `JMSExpiration`, tăng safety margin phù hợp |
| Queue expiry phình liên tục | Chưa có retention, không có workflow rà soát/xử lý | Đặt retention riêng và cảnh báo backlog/tuổi oldest message |
| Message hết hạn nhiều dù producer nhanh | Consumer chậm, backlog/paging, tắc downstream, TTL thấp hơn thời gian chờ | Đo age of oldest, enqueue-to-consume latency, throughput và expiry rate |
| Bật `min-expiry-delay` khiến message cũ vẫn sống | Broker đã gia hạn TTL tối thiểu | Xem thứ tự ưu tiên `no-expiry` / `expiry-delay` / min-max |

## 9. Quyết định bỏ qua, lưu giữ hay xử lý thông điệp đã stale

Khi message hết hạn hoặc quá thời điểm hữu ích, đừng mặc định “đó là lỗi nên retry”:

1. **Chỉ bỏ đi** nếu dữ liệu thực sự không còn giá trị và việc mất nó là chính sách được phê duyệt, ví dụ tick giá cũ có tick mới thay thế.
2. **Đưa vào expiry/audit queue** nếu cần điều tra nguyên nhân chậm trễ, đối soát SLA hoặc khôi phục có kiểm soát. Không gửi tự động message stale trở lại queue nguồn nếu deadline đã qua.
3. **Chuyển thành sự kiện khác** như `QuoteExpired` hoặc `TaskTimedOut` khi nghiệp vụ cần biết sự kiện đã mất hiệu lực. Event kết quả này có **eventId, loại, schema và TTL riêng**, không kéo dài tính hợp lệ của sự kiện gốc.
4. **Escalate hoặc yêu cầu quyết định thủ công** khi đó là lệnh tài chính, thanh toán, an toàn hoặc dữ liệu bắt buộc. TTL không phải quyền tự động xóa trách nhiệm xử lý nghiệp vụ.

Trong pipeline nhiều hop, mỗi hop phải **truyền nguyên deadline nghiệp vụ ban đầu**. Nếu hop B đọc message cũ rồi gửi kết quả đi với TTL mới hoàn toàn, message “sống lại” dù ý nghĩa đã hết. Với một số loại dữ liệu, nên đánh dấu **phiên bản** hoặc **sequence number** để bỏ thông tin cũ hơn dù nó còn TTL; TTL không đảm bảo thứ tự.

## 10. Checklist nghiệm thu

- [ ] Producer đặt TTL **bằng mili giây** và biết rõ `0` nghĩa là **không hết hạn**.
- [ ] `JMSExpiration` được phân biệt với `businessDeadlineEpochMs`; transacted send **không** đẩy điểm bắt đầu TTL sang lúc commit.
- [ ] Retry/outbox giữ nguyên `eventId` và deadline tuyệt đối, tính lại phần thời gian còn lại; không tạo TTL mới sau khi đã quá hạn.
- [ ] Consumer kiểm tra deadline trước side effect, kể cả khi broker vừa phân phối message hợp lệ về TTL.
- [ ] Artemis có `expiry-address`/queue đích hợp lệ hoặc chủ đích drop; không lẫn với DLQ; retention của expiry queue được quyết định rõ.
- [ ] Classic đã review `processExpired` và dead-letter strategy, không tạo vòng lặp expiration ở DLQ.
- [ ] Đã kiểm thử hết hạn khi backlog, delivery delay lớn hơn TTL, commit muộn, retry và clock skew.
- [ ] Có metrics cho expiry rate, thời gian nằm trong queue, backlog expiry và số sự kiện `APP_STALE`.

**Kết luận:** JMS TTL làm giảm nguy cơ **giao message đã quá hạn kỹ thuật**, nhưng không bảo đảm **không có tác dụng nghiệp vụ khi message đã stale**. Hệ thống đáng tin cậy phải giữ một deadline bất biến xuyên mọi lần gửi lại/chuyển tiếp, áp dụng policy expiry phù hợp ở Classic/Artemis và để consumer kiểm tra deadline ở điểm đưa ra quyết định cuối cùng.

## Tài liệu đối chiếu

1. [Jakarta Messaging 3.1 — JMSProducer.setTimeToLive](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/JMSProducer.html): `JMSExpiration`, TTL 0, thời điểm send và delivery delay.
2. [Jakarta Messaging 3.1 — MessageProducer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/MessageProducer.html): TTL qua `setTimeToLive` hoặc tham số `send`.
3. [Apache Artemis 2.57.0 — Message Expiry](https://artemis.apache.org/components/artemis/documentation/latest/message-expiry.html): expiry address, `_AMQ_ACTUAL_EXPIRY`, `no-expiry`, `expiry-delay`, min/max và reaper.
4. [ActiveMQ Classic — Message Expiry](https://activemq.apache.org/components/classic/documentation/message-expiry): cách tính và kiểm tra `JMSExpiration` ở broker/client, đồng hồ hệ thống.
5. [ActiveMQ Classic — Message Redelivery and DLQ Handling](https://activemq.apache.org/components/classic/documentation/message-redelivery-and-dlq-handling): `processExpired` và cảnh báo về expiration trên DLQ.
