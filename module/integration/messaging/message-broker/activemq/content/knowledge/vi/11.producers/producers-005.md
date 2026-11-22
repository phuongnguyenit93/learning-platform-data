# Timeout khi gửi và kết quả không xác định sau mất kết nối

> **Chương:** Producer  
> **Phạm vi:** Producer Java dùng JMS/Jakarta Messaging để gửi message vào Apache ActiveMQ Classic hoặc Apache Artemis. Bài tập trung vào **thời điểm broker đã nhận message nhưng producer chưa nhận được phản hồi**, cách đặt timeout, xử lý retry và bằng chứng kiểm thử. Ví dụ ứng dụng dùng Java 17 và `jakarta.jms`; cấu hình riêng cho Classic 6.x (OpenWire) và Artemis 2.x (Core).

## 1. Tình huống khó nhất: timeout nhưng message có thể đã được gửi

Giả sử dịch vụ thanh toán gửi sự kiện `PaymentAuthorized` với khóa nghiệp vụ `payment-714`. Lệnh `producer.send(...)` bị timeout sau 5 giây. Có thể đã xảy ra **một trong hai diễn biến không thể phân biệt từ lỗi phía client**:

```text
                       KỊCH BẢN A: CHƯA NHẬN
Producer                                       Broker
   | ---------- SEND(payment-714) ---X           |
   |                                            |
   | <--- timeout / connection lost             |
   |                                            |
   | Không có message được nhận                  |

                       KỊCH BẢN B: ĐÃ NHẬN
Producer                                       Broker
   | ---------- SEND(payment-714) ------------> |
   |                                  Lưu/routing message
   |           X----------- CONFIRM ------------ |
   | <--- timeout / connection lost             |
   |                                            |
   | Message đã được nhận, nhưng client không biết
```

Ở kịch bản B, gửi lại với **một event ID khác** có thể tạo message trùng. Ở kịch bản A, không gửi lại có thể làm mất sự kiện. Vấn đề còn tồn tại với transaction: nếu mạng đứt trong khi `commit()` đang được xử lý, client có thể không biết transaction đã commit hay chưa.

**Nguyên tắc:** timeout đo **giới hạn chờ của phía gọi**, không xác nhận message bị hủy trên broker. `JMSException`/`JMSRuntimeException` khi gửi do mất mạng cũng **không tự chứng minh** “broker chưa nhận message”. Jakarta Messaging đặc tả rằng khi gửi gặp lỗi, trạng thái đã gửi thành công hay chưa có thể **không xác định**. <https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html>

Điều cần thiết kế là một kết quả nghiệp vụ thứ ba: **IN_DOUBT** (chưa biết chắc), thay vì ép mọi exception thành `FAILED`.

## 2. Phân loại kết quả để tránh retry sai

| Thời điểm/quan sát | Trạng thái nên ghi nhận | Có thể khẳng định gì? | Cách xử lý |
|---|---|---|---|
| Kiểm tra payload, cấu hình hoặc kết nối **thất bại trước khi gọi send** | `NOT_SUBMITTED` | Lần gọi này chưa gửi message | Sửa dữ liệu/credential/endpoint; retry theo loại lỗi |
| `send` trả về thành công với **gửi đồng bộ được xác nhận bởi broker** | `BROKER_CONFIRMED` | Broker đã xác nhận theo mức bảo đảm của provider và chính sách durability | Ghi nhận đã publish; vẫn cần phân biệt với consumer xử lý xong |
| `send` timeout, mất socket hoặc nhận lỗi vận chuyển **khi yêu cầu đang bay** | `IN_DOUBT` | Không biết chắc broker có nhận/lưu hay không | Giữ **cùng eventId**, tra cứu đối soát hoặc retry có chống trùng |
| Gửi bất đồng bộ: phương thức `send` vừa return, callback chưa có | `PENDING_CONFIRMATION` | Chưa có xác nhận kết thúc gửi | Chờ callback trong giới hạn quản lý; không vội đánh dấu thành công |
| Gửi bất đồng bộ: `CompletionListener.onCompletion` | `BROKER_CONFIRMED` theo hợp đồng provider | Tương đương mức bảo đảm của gửi đồng bộ theo đặc tả | Ghi nhận hoàn tất |
| Gửi bất đồng bộ: `onException` hoặc timeout chờ callback | `IN_DOUBT` | Message có thể đã đi đến broker | Áp dụng đối soát/retry với ID ổn định |
| `commit()` của producer transaction mất kết nối | `IN_DOUBT` | Có thể commit đã áp dụng nhưng response bị mất | Không coi rollback/retry là bằng chứng transaction trước chưa commit |

Hai giới hạn cần nắm:

- **Gửi thành công ≠ nghiệp vụ đã xử lý thành công.** Xác nhận gửi chỉ nói về trách nhiệm broker đã nhận; nó không xác nhận consumer đã hoàn tất thanh toán. Bảo đảm durable còn tùy delivery mode, queue binding, journal và chính sách broker.
- **JMSMessageID không thay cho eventId nghiệp vụ.** Provider sinh `JMSMessageID` khi gửi; tạo message mới ở lần retry có thể tạo một `JMSMessageID` mới, dù nó là cùng sự kiện. Hãy dùng `eventId` được tạo **một lần** tại nguồn dữ liệu và giữ nguyên qua các lần thử.

## 3. Vì sao “send timeout” không phải một loại timeout duy nhất?

Khi người vận hành nói “send treo”, cần tách được nguyên nhân:

| Lớp chờ | Ví dụ | Điều kiện dừng | Ý nghĩa khi vượt ngưỡng |
|---|---|---|---|
| **Kết nối ban đầu** | DNS, TCP, TLS, authentication | Timeout connect/handshake hoặc số lần thử | Nếu chưa gọi send thì chưa gửi message của lần thử đó |
| **Chờ khôi phục kết nối** | Failover transport, reconnect Core | Reconnect attempts, retry interval, failover timeout | Có thể vẫn còn request cũ chưa rõ kết quả |
| **Chờ broker phản hồi cho send** | Gửi persistent đồng bộ | Classic send/failover timeout, Artemis `callTimeout` | Có thể broker đã xử lý nhưng reply không tới |
| **Broker backpressure/flow control** | Bộ nhớ/đĩa đầy, consumer chậm | Policy `BLOCK`/`FAIL` hoặc broker limit | Không đồng nghĩa broker chết hoặc socket mất |
| **Chờ transaction commit** | `Session.commit()`, `JMSContext.commit()` | Timeout call/connection | Có thể xảy ra trạng thái **commit in-doubt** |
| **Chờ callback gửi bất đồng bộ** | `CompletionListener` | Deadline do ứng dụng theo dõi | Send method trả về không có nghĩa callback đã xác nhận |

Đừng dùng `setTimeToLive(5000)` làm timeout gửi: **TTL** là thời gian sống của message **sau khi gửi**, không phải giới hạn thời gian chờ `send`. Tương tự, `deliveryDelay` chỉ lập lịch phân phối, không giải quyết tính không xác định.

### Gửi đồng bộ và gửi bất đồng bộ khác nhau ở bằng chứng

- **Classic:** Theo tài liệu, gửi `PERSISTENT` ngoài transaction mặc định đợi broker xác nhận; tùy chọn `useAsyncSend=true` có thể khiến `send` trả về trước khi biết message đã được broker nhận. Message persistent trong transaction chủ yếu được chốt tại `commit`.
- **Artemis Core:** `blockOnDurableSend=true` (mặc định) khiến gửi durable ngoài transaction chờ phản hồi; `blockOnNonDurableSend=false` (mặc định) khiến gửi non-durable có thể không chờ. Nếu transaction đang mở, chính `commit` là ranh giới xác nhận chính.
- **Jakarta Messaging asynchronous API:** `MessageProducer.send(..., CompletionListener)` tách việc gọi send và callback; callback `onCompletion` được yêu cầu có mức tin cậy tương đương gửi đồng bộ. Một lỗi khi gọi send hoặc callback `onException` **vẫn có thể không xác định trạng thái ở broker**. Không mặc định Classic hỗ trợ đầy đủ mọi tính năng gửi async theo JMS 2.0/3.1; kiểm tra bản client cụ thể trước khi sử dụng.

Chọn hình thức gửi phải khớp yêu cầu dữ liệu. Với sự kiện nghiệp vụ không được mất, ưu tiên **gửi persistent có xác nhận** và một quy trình retry an toàn; chỉ bật async không xác nhận nếu đã định nghĩa rõ rủi ro mất message.

## 4. Cấu hình timeout và retry của ActiveMQ Classic

Ở Classic, hai nguồn chặn `send()` thường gặp là **failover transport đang chờ kết nối trở lại** và **producer flow control do broker thiếu tài nguyên**. Hai cơ chế có timeout khác nhau; cấu hình một bên không thay thế bên kia.

### 4.1. Giới hạn lệnh gửi bị chặn khi failover

Ví dụ URI cho Classic 6.x/Jakarta Messaging, dùng một broker lab:

```java
import org.apache.activemq.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(
    "failover:(tcp://127.0.0.1:61616)" +
    "?timeout=5000" +
    "&maxReconnectAttempts=3" +
    "&startupMaxReconnectAttempts=3" +
    "&initialReconnectDelay=500");

// Chủ đích giữ gửi persistent đồng bộ khi chẩn đoán.
factory.setUseAsyncSend(false);
factory.setAlwaysSyncSend(true);
```

| Tùy chọn | Ý nghĩa |
|---|---|
| `failover:(tcp://...)` | Tự kết nối lại sau mất transport OpenWire; một URI cũng hợp lệ |
| `timeout=5000` | Giới hạn thời gian chờ của **send đang bị chặn bởi failover** (5.000 ms); timeout không đóng connection hoặc dừng quá trình reconnect |
| `maxReconnectAttempts=3` | Giới hạn số lần thử kết nối lại sau khi đã từng kết nối thành công |
| `startupMaxReconnectAttempts=3` | Giới hạn số lần thử ở giai đoạn chưa có kết nối ban đầu |
| `initialReconnectDelay=500` | Khoảng nghỉ ban đầu trước khi thử reconnect |
| `setUseAsyncSend(false)`, `setAlwaysSyncSend(true)` | Tránh tùy chọn gửi không chờ broker khi mục tiêu là kiểm chứng việc gửi persistent đã được xác nhận |

**Điểm dễ sai:** tài liệu Classic nói rõ `failover timeout` làm lệnh gửi hiện tại ném lỗi nhưng transport vẫn tiếp tục reconnect. Message của lần gửi đã lỗi **có thể được gửi lại ở thời điểm khác**; không được giả định provider đã thu hồi nó từ broker. Nếu cần giới hạn timeout khác cho thao tác send ở ActiveMQ Java client, `ActiveMQConnectionFactory.setSendTimeout(int)` là API đặc thù Classic, cần kiểm tra tương tác với failover và phiên bản thực tế. Hai timeout không tạo chứng nhận “không gửi trùng”.

Không biến tất cả timeout thành một “thời gian kết nối tối đa” tổng thể. Thời gian DNS/TLS, broker backpressure, các nhánh reconnect và việc đóng connection có thể vẫn cần cơ chế giám sát riêng ở tầng dịch vụ.

### 4.2. Broker flow control: đợi có chỗ trống hay trả lỗi?

Khi `memoryUsage`, `storeUsage` hoặc `tempUsage` đạt giới hạn, Classic có thể chặn producer. Một tùy chọn trong `activemq.xml` là:

```xml
<!-- Trích cấu hình: chỉnh trong <systemUsage> đang tồn tại,
     không tạo hai khối trùng nhau. -->
<systemUsage>
  <systemUsage sendFailIfNoSpaceAfterTimeout="3000">
    <memoryUsage>
      <memoryUsage limit="64 mb"/>
    </memoryUsage>
  </systemUsage>
</systemUsage>
```

`sendFailIfNoSpaceAfterTimeout=3000` đợi tối đa 3 giây vì thiếu tài nguyên, sau đó trả lỗi nếu vẫn không giải phóng đủ chỗ. `sendFailIfNoSpace=true` là biến thể có thể từ chối ngay. Khi cấu hình thật, **giữ lại** các thiết lập store/temp usage khác của broker và thử trên staging; ví dụ trên chỉ minh họa thuộc tính, không phải tệp `activemq.xml` hoàn chỉnh.

Khi được broker trả lỗi tài nguyên rõ ràng, cần phân biệt với **mất xác nhận qua mạng**. Tuy vậy, logic chung của producer vẫn nên có eventId và khả năng gửi lại an toàn. Đừng tắt flow control để “khắc phục” send timeout rồi làm đầy disk.

## 5. Cấu hình timeout của Artemis Core client

Artemis có nhóm thông số riêng cho blocking call, reconnection và gửi durable. Ví dụ cho Artemis 2.57.0 (một broker Core lab):

```java
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(
    "tcp://127.0.0.1:61616" +
    "?callTimeout=5000" +
    "&callFailoverTimeout=5000" +
    "&blockOnDurableSend=true" +
    "&reconnectAttempts=3" +
    "&retryInterval=1000");
```

| Tùy chọn | Ý nghĩa | Giới hạn cần hiểu |
|---|---|---|
| `callTimeout=5000` | 5 giây để chờ phản hồi cho một blocking Core call | Lỗi timeout không cho biết broker đã xử lý request chưa |
| `callFailoverTimeout=5000` | Giới hạn chờ trong giai đoạn failover (khác `callTimeout` bình thường) | Mặc định có thể là đợi vô hạn khi đang failover; cần giới hạn theo SLA |
| `blockOnDurableSend=true` | Chờ xác nhận cho non-transacted durable send | Không làm consumer hoàn tất nghiệp vụ; cần journal/binding durable phù hợp |
| `reconnectAttempts=3`, `retryInterval=1000` | Số lần và khoảng cách thử lại kết nối | Tự reconnect không giải quyết việc ứng dụng không biết lần send trước đã nhận chưa |

Với Artemis Core, tính bền vững của một send persistent còn phụ thuộc cấu hình broker: `journal-sync-non-transactional=true` (mặc định) và có queue durable để lưu message. Với transaction, `journal-sync-transactional=true` liên quan xác nhận `commit` đã được ghi bền vững. Thay các tùy chọn này để giảm latency có thể làm yếu đảm bảo khi mất điện hoặc broker crash.

Nếu cần tự động reattach session sau đứt mạng ngắn, Artemis có `confirmationWindowSize` để buffer/replay command theo protocol. **Đừng nhầm replay ở tầng Core với chống trùng nghiệp vụ**: sau broker restart, failover hoặc retry do ứng dụng, kết quả có thể vẫn in-doubt. Chiến lược eventId/idempotency vẫn cần có.

### Khi broker đầy ở Artemis

Với `address-full-policy=BLOCK`, producer có thể bị chặn chờ giải phóng tài nguyên; `FAIL` từ chối với lỗi; `PAGE` ghi message ra paging store. Không được khẳng định mọi timeout là do network. Ví dụ **một entry** trong `broker.xml` dành riêng cho queue lab:

```xml
<address-setting match="orders.intake">
    <max-size-bytes>1048576</max-size-bytes>
    <address-full-policy>BLOCK</address-full-policy>
</address-setting>
```

Tích hợp entry này vào `<address-settings>` đã có, không thêm phần tử trùng. Giới hạn 1 MiB ở đây chỉ để thực hành backpressure; ở production cần tính cả message size, paging/đĩa và mức tiêu thụ thực tế. Với `BLOCK`, send có thể kéo dài; timeout phía client và metrics của broker cần được đọc cùng nhau.

## 6. Mã Java: gửi có định danh ổn định và phân loại IN_DOUBT

Ví dụ dưới sử dụng giao diện `jakarta.jms`, nên có thể dùng cho hai provider nếu **chọn đúng dependency và cấu hình đồng bộ**. Message chứa `eventId` cố định; riêng Artemis có thể bật thêm tính năng dedup ở broker. Bài chủ động sử dụng `PERSISTENT` và synchronous send để việc `send` return có ý nghĩa xác nhận tốt nhất theo cấu hình đã chọn.

### 6.1. Dependency: chọn một provider cho mỗi ứng dụng

**Classic 6.4.x (OpenWire):**

```xml
<dependency>
  <groupId>org.apache.activemq</groupId>
  <artifactId>activemq-client</artifactId>
  <version>6.4.0</version>
</dependency>
```

**Artemis 2.57.0 (Core):**

```xml
<dependency>
  <groupId>org.apache.artemis</groupId>
  <artifactId>artemis-jakarta-client</artifactId>
  <version>2.57.0</version>
</dependency>
```

Không nhét cả hai provider vào project chỉ để đổi kết nối bằng cách sửa URI. Hãy cấu hình factory ở lớp khởi động theo broker được triển khai, còn `SendOnce` chỉ phụ thuộc `ConnectionFactory` chuẩn.

### 6.2. `SendOnce.java`

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.JMSRuntimeException;
import jakarta.jms.Queue;

public final class SendOnce {
    private SendOnce() {}

    public static final class SendInDoubt extends RuntimeException {
        public final String eventId;

        public SendInDoubt(String eventId, Throwable cause) {
            super("Send outcome unknown for eventId=" + eventId, cause);
            this.eventId = eventId;
        }
    }

    public static void publish(ConnectionFactory factory,
                               String user, String password,
                               String eventId, String payload,
                               boolean artemisCore) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId must be stable");
        }
        if (user == null || password == null) {
            throw new IllegalArgumentException("Missing credentials");
        }

        // Nếu tạo context thất bại ở đây thì send chưa được gọi.
        JMSContext ctx = factory.createContext(
            user, password, JMSContext.AUTO_ACKNOWLEDGE);
        try {
            Queue destination = ctx.createQueue("orders.intake");
            JMSProducer producer = ctx.createProducer()
                .setDeliveryMode(DeliveryMode.PERSISTENT)
                .setTimeToLive(0)
                .setProperty("eventId", eventId);

            // Chỉ có hiệu lực với Artemis hỗ trợ duplicate detection.
            // Không tái sử dụng một eventId cho các sự kiện khác nhau.
            if (artemisCore) {
                producer.setProperty("_AMQ_DUPL_ID", eventId);
            }

            try {
                producer.send(destination, payload);
                System.out.println("SEND_CONFIRMED eventId=" + eventId);
            } catch (JMSRuntimeException sendFailure) {
                // Lỗi ở ranh giới send không chứng minh broker chưa nhận.
                throw new SendInDoubt(eventId, sendFailure);
            }
        } finally {
            try {
                ctx.close();
            } catch (JMSRuntimeException closeFailure) {
                // Lỗi cleanup sau SEND_CONFIRMED không đảo ngược send.
                // Ở production: báo metrics/structured log và quản lý pool.
                System.err.println("WARN context close failed: " +
                    closeFailure.getClass().getSimpleName());
            }
        }
    }
}
```

**Ý nghĩa của mã:** `SendOnce` cố tình **không tự động gửi lại trong `catch`**. Khi có `SendInDoubt`, caller phải giữ sự kiện ở trạng thái chưa được xác nhận và tiếp tục theo chính sách retry đã xác định bên dưới. Không gửi message có payload mới chỉ vì thấy lần trước timeout.

Queue `orders.intake` phải tồn tại hoặc broker phải cho phép tạo destination; tài khoản phải có quyền gửi. Các dòng factory ở mục 4/5 là phần wiring cho `SendOnce.publish(...)`:

```java
// Ở ứng dụng Classic (dùng factory Classic của mục 4):
SendOnce.publish(factory, user, password, eventId, payload, false);

// Ở ứng dụng Artemis (dùng factory Artemis của mục 5):
SendOnce.publish(factory, user, password, eventId, payload, true);
// Sau khi không còn JMSContext/Connection dùng nó, đóng Artemis factory.
```

Giá trị `eventId` phải được tạo từ **lúc sự kiện nghiệp vụ hình thành** và được lưu bền vững; ví dụ `order-123:PaymentAuthorized:v1`. Khi retry, truyền lại **cùng `eventId` và cùng nội dung logic**, kể cả khi tiến trình Java đã khởi động lại. Không lấy ngẫu nhiên `UUID.randomUUID()` bên trong mỗi lần thử gửi.

### 6.3. Nếu gửi trong transaction

Khi dùng `JMSContext.SESSION_TRANSACTED`, `send()` có thể chỉ đưa message vào transaction chưa commit. Điểm quyết định chuyển thành `BROKER_CONFIRMED` là **`commit()` thành công**, không phải `send()` thành công:

```java
try (JMSContext ctx = factory.createContext(
        user, password, JMSContext.SESSION_TRANSACTED)) {
    Queue q = ctx.createQueue("orders.intake");
    // Có thể thêm _AMQ_DUPL_ID vào JMSProducer nếu dùng Artemis.

    ctx.createProducer()
       .setDeliveryMode(DeliveryMode.PERSISTENT)
       .setProperty("eventId", eventId)
       .send(q, payload);
    try {
        ctx.commit();
        System.out.println("COMMIT_CONFIRMED " + eventId);
    } catch (JMSRuntimeException commitFailure) {
        // Commit có thể đã xảy ra nhưng broker reply bị mất.
        throw new SendOnce.SendInDoubt(eventId, commitFailure);
    }
}
```

Không coi việc gọi `rollback()` sau một `commit()` timeout là bằng chứng broker đã rollback transaction trước đó. Với mất kết nối, một phiên session mới không thể “hoàn tác” giao dịch đã commit thành công trên broker cũ. Cần cùng một chiến lược đối soát và idempotency như với send không giao dịch.

## 7. Retry an toàn: cùng eventId, giới hạn lần thử và chống trùng

### 7.1. Mẫu outbox cho producer có cơ sở dữ liệu

Một giao dịch nghiệp vụ và việc gửi message vào broker thường là **hai hệ thống riêng**. Nếu ứng dụng lưu order vào DB rồi gửi message, ứng dụng có thể chết giữa hai bước. Mẫu **transactional outbox** giúp bảo đảm sự kiện không mất khỏi nguồn gửi:

```text
Transaction DB:
    UPDATE orders SET status = 'AUTHORIZED' WHERE id = ...
    INSERT INTO outbox(event_id, payload, state) VALUES (..., ..., 'PENDING')
COMMIT DB

Outbox relay:
    đọc outbox PENDING/RETRY_DUE (có lease để tránh hai relay cùng gửi)
    send(event_id không đổi)
       -> xác nhận: đánh dấu SENT
       -> timeout/in-doubt: ghi last_error, next_retry_at, giữ bản ghi
    lần retry dùng lại event_id cũ và payload logic cũ
```

Outbox bảo đảm dữ liệu cần publish đã tồn tại bền vững trong DB; nó **không tự mang lại exactly-once delivery**. Một relay có thể gửi thành công rồi chết trước khi cập nhật `SENT`, do đó cùng sự kiện vẫn có thể được gửi tiếp. Cần broker dedup hoặc consumer idempotent.

### 7.2. Artemis: cơ chế `_AMQ_DUPL_ID`

Artemis cung cấp duplicate detection theo **address**. Nếu JMS message có property chuỗi `_AMQ_DUPL_ID` và giá trị đó còn trong cache của address, lần gửi lại có cùng ID sẽ **không được route thêm lần nữa**. Cấu hình trong phần `<core>` của `broker.xml`:

```xml
<!-- Trích mục cần tích hợp vào broker.xml hiện có. -->
<id-cache-size>50000</id-cache-size>
<persist-id-cache>true</persist-id-cache>
```

Các giới hạn cần hiểu:

- Cache là **vòng tròn có giới hạn** theo address, ID cũ có thể bị đẩy ra nếu số lượng ID mới vượt kích thước. Một lần retry quá muộn khi ID đã bị thay thế vẫn có thể tạo bản trùng.
- Cache có thể lưu bền vững (`persist-id-cache=true` mặc định), nhưng còn phụ thuộc cấu hình và bộ lưu trữ; không coi nó là kho idempotency vô hạn.
- Hai sự kiện khác nhau **không được** dùng chung duplicate ID. Nếu gửi một batch transaction, phải thiết kế phạm vi ID phù hợp semantics transaction.
- Đây là tính năng **Artemis broker**; đừng giả định property `_AMQ_DUPL_ID` sẽ cung cấp dedup tương đương khi chuyển sang Classic.

### 7.3. Consumer vẫn phải idempotent

Ngay cả khi Artemis broker lọc trùng, xử lý ở consumer có thể bị lặp do redelivery/consumer crash. Một mẫu an toàn là lưu `eventId` vào bảng có **unique constraint** trong **cùng transaction cơ sở dữ liệu** với side effect:

```sql
-- Ví dụ PostgreSQL: một event chỉ gây một thay đổi nghiệp vụ.
BEGIN;

INSERT INTO processed_events(event_id)
VALUES ('payment-714')
ON CONFLICT (event_id) DO NOTHING;

-- Chỉ thực hiện UPDATE nghiệp vụ nếu INSERT ở trên thực sự thêm 1 dòng.
-- Sau đó COMMIT transaction DB.
COMMIT;
```

Đoạn SQL mô tả logic chứ chưa phải toàn bộ consumer. Trong mã thật, hãy kiểm tra `row count` của `INSERT`, thực hiện side effect chỉ khi mới thêm bản ghi, commit DB rồi mới acknowledge JMS. Nếu side effect là gọi API bên ngoài hoặc gửi tiền, cần idempotency key ở chính hệ thống đích; một unique constraint ở DB cục bộ không đủ để kiểm soát side effect ngoài transaction.

### 7.4. Chọn retry policy theo loại lỗi

| Loại kết quả | Quyết định | Vì sao |
|---|---|---|
| Sai payload/validation trước send | `REJECTED`, sửa dữ liệu | Lặp vô hạn không sửa được lỗi |
| Không kết nối được broker trước khi gửi | Retry có backoff và giới hạn | Chưa có message của lần gọi, nhưng cần tránh bão kết nối |
| `IN_DOUBT` do mất ACK hoặc timeout | Retry **cùng eventId** hoặc đối soát trước | Không bỏ sót sự kiện, tránh side effect trùng |
| Broker hết tài nguyên/flow control | Backoff, giới hạn concurrency; cảnh báo capacity | Retry nóng làm tình trạng đầy nặng thêm |
| Broker xác nhận gửi thành công | `SENT`, không tự retry | Phần consumer xử lý có vòng đời riêng |
| Không đủ quyền `send` | Dừng retry và xử lý cấu hình/quyền | Retry không khắc phục authorization |

Đặt **exponential backoff + jitter**, giới hạn tổng số lần hoặc tổng thời gian retry, và có hàng đợi/sổ theo dõi bản ghi cần xử lý thủ công. Retry vô hạn với `eventId` mới vừa tăng tải vừa làm trùng nghiệp vụ. Cần monitoring riêng cho số sự kiện `IN_DOUBT` theo thời gian.

## 8. Bài thực hành: chứng minh vì sao timeout có thể là “đã gửi”

### 8.1. Chuẩn bị

- Broker Classic hoặc Artemis **riêng cho lab**, queue durable `orders.intake`, bật persistent storage và tạo tài khoản có quyền gửi/đọc.
- Producer `SendOnce` ở mục 6, một consumer đơn giản in `eventId`, `JMSMessageID` và thời điểm nhận (không làm side effect thật).
- Đường mạng có proxy có thể **cắt kết nối từ client đến broker** (ví dụ Toxiproxy hoặc firewall lab) và một cách quan sát queue qua JMX/management UI.
- Dùng **một eventId cố định** `lab-send-001` và body cố định `order-created` qua các lần retry. Trong bài test nhiều kịch bản, dùng eventId khác nhau cho từng kịch bản để dữ liệu không lẫn nhau.

### 8.2. Các lần chạy

| Bài thử | Thời điểm can thiệp | Quan sát producer | Quan sát broker/consumer |
|---|---|---|---|
| A. Bình thường | Không cắt kết nối | `SEND_CONFIRMED` | Message có `eventId` tương ứng |
| B. Mất kết nối **trước send** | Ngắt broker trước khi tạo connection | Lỗi tạo context/kết nối | Không có message của lần chạy này |
| C. Đứt mạng **trong khi send** | Dùng proxy cắt kết nối trong cửa sổ gửi/ACK | Có thể `SendInDoubt` | **Có thể 0 hoặc 1 message**; kết quả phụ thuộc thời điểm cắt |
| D. Đứt sau broker đã nhận nhưng trước ACK đến client | Fault injection chặn đường trả ACK trong lab | Có thể timeout/`SendInDoubt` | Có thể tìm thấy message dù producer báo timeout |
| E. Retry cùng `eventId` | Gửi lại message từ lần C/D | Có thể `SEND_CONFIRMED` | Artemis dedup có thể giữ 1 bản; Classic có thể có 2 bản, consumer phải dedup |
| F. Broker backpressure | Giảm giới hạn lab, dừng consumer, làm đầy address | Send bị chậm hoặc timeout | Có `BLOCK`/usage metrics; không kết luận do đứt mạng |

**Thực tế:** tạo đúng cửa sổ “broker đã lưu nhưng reply chưa về” rất khó bằng một lệnh `docker stop` đơn giản. Broker có thể chưa nhận request, đã nhận nhưng chưa ghi journal, hoặc đã xử lý và gửi reply. Dùng proxy/chaos tool để điều khiển lưu lượng, đối chiếu log và queue status, rồi chấp nhận cả hai kết quả hợp lệ ở bài thử C. **Không viết một assertion giả định cứ timeout là message không tồn tại.**

### 8.3. Kết quả cần ghi

```text
eventId:
broker / client artifact / JDK:
send timestamp, duration, timeout setting:
transport / failover / blockOnDurableSend:
exception class, cause chain:
send state: NOT_SUBMITTED | BROKER_CONFIRMED | IN_DOUBT:
broker enqueued count before/after:
eventId occurrences in queue/consumer:
Artemis duplicate-detection cache enabled?:
retry count, final business outcome:
```

Nếu consumer đã ack message, `QueueSize=0` **không chứng minh broker chưa từng nhận nó**; hãy dùng log, eventId ở consumer và dữ liệu quan sát enqueue để đối soát. `EnqueueCount` cũng có thể reset khi restart, vì vậy mỗi phép đo cần timestamp và broker instance cụ thể.

## 9. Những cách xử lý sai cần tránh

1. **`catch (JMSException) { producer.send(message); }` ngay lập tức** — không giữ ID ổn định, không backoff, không xét khả năng message đã nhận.
2. **Mỗi lần thử tạo `eventId` mới** — biến retry thành các sự kiện khác nhau, vô hiệu hóa dedup theo khóa nghiệp vụ.
3. **Coi timeout là broker rollback** — timeout không ra lệnh thu hồi message; với transaction in-doubt có thể đã commit.
4. **Lấy `JMSMessageID` làm khóa idempotency** — giá trị này là định danh của JMS send, không ổn định qua lần tạo message mới.
5. **Dùng `Future.get(timeout)` rồi coi tác vụ bị hủy** — timeout của thread gọi không bảo đảm ngắt được lệnh `send`; socket/producer vẫn có thể hoạt động. Không dùng việc interrupt thread làm cơ chế rollback JMS.
6. **Bật async send chỉ để hết timeout** — có thể làm `send` return nhanh nhưng yếu đi bằng chứng broker nhận; lỗi có thể xuất hiện ở callback hoặc log.
7. **Chuyển `address-full-policy` sang `DROP` hoặc tắt flow control để tránh chờ** — đổi sự chậm thành mất message, trái mục tiêu tin cậy.
8. **Đánh dấu outbox `SENT` ngay trước send** — tiến trình chết giữa hai bước sẽ khiến sự kiện không còn cơ hội gửi.

## 10. Checklist vận hành cho một producer đáng tin cậy

| Câu kiểm tra | Điều kiện đạt |
|---|---|
| Một sự kiện có ID nghiệp vụ bất biến? | `eventId` được lưu trước khi gửi và dùng lại qua mọi retry |
| Biết chính xác mức xác nhận? | Chỉ đánh dấu thành công sau sync ACK/callback thành công hoặc `commit` thành công |
| Timeout có được phân lớp? | Phân biệt connect/reconnect, send ACK, broker flow control và transaction |
| Lỗi mất kết nối có trạng thái thứ ba? | Ghi nhận `IN_DOUBT`; không tự tuyên bố thất bại chắc chắn |
| Retry có kỷ luật? | Backoff + jitter + giới hạn + cùng ID; không gây bão broker |
| Có cơ chế chống trùng? | Artemis duplicate ID trong giới hạn cache **và/hoặc** idempotent consumer |
| Đã thử fault injection đúng lúc? | Có bài thử mất ACK trả về, thấy timeout có thể đi cùng message đã tồn tại |
| Quan sát được vấn đề production? | Metrics timeout/in-doubt/retry, broker flow control và số lần xử lý mỗi `eventId` |

Khi producer mất kết nối giữa lệnh gửi và phản hồi, **không có cách tổng quát để suy ra kết quả chỉ từ exception**. Thiết kế đúng là giữ trạng thái in-doubt, gắn định danh ổn định cho sự kiện, retry có kiểm soát và bảo đảm consumer xử lý idempotent. Các tham số timeout giúp hệ thống **không chờ vô hạn**, còn khả năng tránh mất/trùng phụ thuộc vào cơ chế xác nhận và xử lý nghiệp vụ sau timeout.

## Tài liệu chính thức

1. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): send errors và kết quả có thể không xác định; `CompletionListener`.
2. [ActiveMQ Classic — Failover Transport Reference](https://activemq.apache.org/components/classic/documentation/failover-transport-reference): `timeout`, reconnect và in-doubt commit.
3. [ActiveMQ Classic — Async Sends](https://activemq.apache.org/components/classic/documentation/async-sends): xác nhận gửi persistent và tác động của `useAsyncSend`.
4. [ActiveMQ Classic — Producer Flow Control](https://activemq.apache.org/components/classic/documentation/producer-flow-control): `sendFailIfNoSpaceAfterTimeout`, giới hạn broker và producer bị chặn.
5. [Apache Artemis — Guarantees of Sends and Commits](https://artemis.apache.org/components/artemis/documentation/latest/send-guarantees.html): `blockOnDurableSend`, journal sync và xác nhận gửi.
6. [Apache Artemis — Core Client Failover](https://artemis.apache.org/components/artemis/documentation/latest/client-failover.html): reconnect, `confirmationWindowSize` và failover.
7. [Apache Artemis — Duplicate Message Detection](https://artemis.apache.org/components/artemis/documentation/latest/duplicate-detection.html): `_AMQ_DUPL_ID`, cache theo address và giới hạn chống trùng.
8. [Apache Artemis — Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-settings.html): `address-full-policy` và flow control.
