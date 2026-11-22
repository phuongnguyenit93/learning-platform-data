# DUPS_OK_ACKNOWLEDGE và đánh đổi giữa chi phí xác nhận với gửi lặp

> **Chương:** Xác nhận và giao dịch  
> **Phạm vi:** Chế độ xác nhận `Session.DUPS_OK_ACKNOWLEDGE` của JMS khi consumer Java đọc thông điệp từ Apache ActiveMQ Classic hoặc Artemis. Trọng tâm là **lazy acknowledgment**, tác động tới chi phí xác nhận, khả năng giao lại message khi gặp lỗi và cách lựa chọn chế độ phù hợp. Ví dụ dùng ActiveMQ Classic 5.x và API `javax.jms`; các lưu ý Artemis được nêu riêng.

## 1. Bài toán: xác nhận từng message có chi phí, xác nhận muộn có rủi ro

Một worker đọc 10.000 sự kiện telemetries/giây từ queue `metrics.raw`. Mỗi sự kiện chỉ phục vụ cập nhật bảng thống kê gần thời gian thực. Đội vận hành muốn giảm overhead của acknowledgment (ACK) để dành tài nguyên cho việc nhận và xử lý message.

JMS cho phép tạo session như sau:

~~~java
Session session = connection.createSession(
        false, Session.DUPS_OK_ACKNOWLEDGE);
~~~

Tên `DUPS_OK_ACKNOWLEDGE` thể hiện một hợp đồng: **ứng dụng chấp nhận khả năng nhận message trùng**, đổi lấy việc provider **được phép xác nhận delivery theo cách trì hoãn (lazy)**.

Điểm phải hiểu ngay:

- Đây là **chế độ acknowledgment của consumer session**, không phải tùy chọn retry của producer.
- JMS cho phép provider trì hoãn ACK; **không quy định** cứ đúng N message mới ACK một lần, khoảng bao lâu phải flush, hay luôn giảm được bao nhiêu gói tin.
- Khi kết nối/broker thất bại trước khi ACK đã có hiệu lực, một số message đã giao trước đó **có thể được giao lại**.
- Tình huống thử nghiệm có thể **không xuất hiện duplicate**: provider vẫn được quyền ACK nhanh và việc crash có thể xảy ra sau khi ACK đã hoàn tất.
- Việc có thể nhận trùng **không tự tạo bảo đảm xử lý nghiệp vụ at-least-once**. Trong chế độ này, ứng dụng không kiểm soát mốc ACK sao cho chắc chắn nằm sau khi database commit.

Bài học hướng tới quyết định có cơ sở: **khi nào giảm chi phí ACK đáng để chấp nhận duplicate, và khi nào phải dùng chế độ xác nhận chặt hơn?**

## 2. Hợp đồng JMS của DUPS_OK_ACKNOWLEDGE

JMS định nghĩa `DUPS_OK_ACKNOWLEDGE` là chế độ mà session **được phép xác nhận message một cách lười (lazily acknowledge delivery)**. Đổi lại, nếu JMS provider bị lỗi, ứng dụng có khả năng nhận lại những message đã được giao.

Cụm từ quan trọng là **được phép**:

- JMS không yêu cầu mỗi provider phải dùng cùng một thuật toán ACK batching.
- Provider có thể gửi ACK ngay, trì hoãn hoặc gom nhiều lần nhận, tùy triển khai và điều kiện tải.
- Không có API JMS chuẩn kiểu `flushDupsOkAcknowledgements()` để ứng dụng chủ động đẩy ACK đang chờ.
- Ứng dụng **không gọi `message.acknowledge()` để quyết định mốc ACK** như khi dùng `CLIENT_ACKNOWLEDGE`; trách nhiệm thuộc provider.

### 2.1. ACK đang xác nhận điều gì?

ACK báo cho broker rằng **delivery tới consumer/session đã được xác nhận theo hợp đồng JMS**. Đối với queue, message đã được ACK sẽ không còn pending để giao cho consumer khác theo đường xử lý thông thường. Đối với topic subscription, ACK hoàn tất trách nhiệm delivery đối với subscription tương ứng.

ACK **không có nghĩa**:

- Consumer đã ghi thành công mọi thay đổi vào database.
- Một lời gọi HTTP hoặc thanh toán bên ngoài đã hoàn tất.
- Message sẽ không bao giờ xuất hiện lần nữa dưới dạng một lần gửi nghiệp vụ mới.
- Producer không thể gửi trùng một `eventId`.

Nói cách khác, **ACK là trạng thái messaging**; việc hoàn thành nghiệp vụ thuộc về ứng dụng và hệ thống dữ liệu bên ngoài.

### 2.2. Một luồng nhận có ACK trì hoãn

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as JMS Consumer/Provider
    participant A as Logic ứng dụng
    B->>C: Deliver M1
    C->>A: receive() trả về M1
    A->>A: Xử lý M1
    Note over C,B: ACK có thể chưa được gửi
    B->>C: Deliver M2
    C->>A: receive() trả về M2
    A->>A: Xử lý M2
    Note over C,B: Provider có thể trì hoãn/gom ACK
    C-->>B: ACK cho một nhóm delivery
    Note over B: M1, M2 đã được xác nhận theo phạm vi ACK
~~~

Sơ đồ trên là **minh họa hành vi được phép**, không phải lịch ACK mà mọi phiên bản ActiveMQ bắt buộc tuân theo. Một provider có thể chọn gửi ACK trước đó.

## 3. Vì sao ACK ít hơn có thể tăng throughput?

Một acknowledgment có chi phí nhất định: giao tiếp client–broker, xử lý trạng thái delivery, cập nhật bộ đếm, đồng bộ luồng và đôi khi tương tác với các cơ chế lưu trữ. Trong một workload rất nhiều message nhỏ, chi phí này có thể đáng kể.

Giả sử **chỉ để mô hình hóa** một implementation gửi trung bình một ACK cho `B` message, với tốc độ nhận `R` message/giây:

\[
\text{ACK requests/s} \approx \frac{R}{B}
\]

Ví dụ `R = 20.000 message/s`:

| Kích thước nhóm giả định `B` | ACK requests/giây theo mô hình | Số message có thể còn trong nhóm chưa ACK tại một thời điểm |
|---:|---:|---|
| 1 | 20.000 | Gần 0–1 |
| 20 | 1.000 | Tới khoảng 20 |
| 100 | 200 | Tới khoảng 100 |
| 500 | 40 | Tới khoảng 500 |

Bảng **không mô tả tham số `B` chuẩn của JMS**, cũng không phải giới hạn duplicate của Classic hay Artemis. Provider có thể dùng thời gian, prefetch, byte size, điều kiện tải hoặc cách ACK khác; một ACK ở protocol cũng có thể bao phủ nhiều delivery. Số message thực tế có nguy cơ giao lại còn phụ thuộc đường truyền, trạng thái ACK, recovery và broker.

Điểm rút ra có thể kiểm chứng là: **giảm số lượt ACK có thể giảm overhead, nhưng kéo dài thời gian một delivery ở trạng thái chưa được broker xác nhận**. Khi có lỗi, broker có thể phải phát lại nhiều message hơn.

### 3.1. ACK batching có làm giảm độ trễ end-to-end?

Không nhất thiết. Khi ACK ít thường xuyên hơn:

- Client/broker có thể bớt một phần xử lý ACK.
- Thông lượng (messages/second) **có thể** cải thiện trong tình huống ACK là bottleneck.
- Broker có thể giữ nhiều message ở trạng thái delivering/unacknowledged lâu hơn.
- Khi consumer crash, backlog phát lại có thể lớn hơn.
- Với message lớn, business logic chậm hoặc disk/network đã là bottleneck, mức cải thiện có thể không đáng kể.

Đừng suy ra “DUPS_OK luôn nhanh hơn AUTO_ACKNOWLEDGE” từ tên mode. **Benchmark có kiểm soát** trên cùng workload, phiên bản broker/client, prefetch và phần cứng mới cho ra câu trả lời hữu ích.

## 4. Cửa sổ lỗi: message nào có thể được giao lại?

Giả sử consumer đã nhận ba message `M1`, `M2`, `M3`. Do ACK trì hoãn, broker chưa biết cả ba đã được xác nhận.

~~~text
Thời gian  Broker                              Consumer
---------  ----------------------------------  -------------------------------
t0         Deliver M1 --------------------->   receive M1; tính toán xong
t1         Deliver M2 --------------------->   receive M2; tính toán xong
t2         Deliver M3 --------------------->   receive M3; đang tính toán
t3         ACK nhóm chưa tới broker          crash/mất connection
t4         Recovery, các delivery chưa ACK
t5         M1/M2/M3 có thể được redeliver -> consumer mới
~~~

Trong kịch bản này, **M1 và M2 có thể được giao lại dù application code đã xử lý xong**, vì broker chưa nhận ACK có hiệu lực.

Ngược lại, nếu provider đã ACK M1/M2 trước `t3`, broker không cần redeliver chúng. Nếu ACK của M3 cũng có hiệu lực trước khi business logic của M3 hoàn thành, ứng dụng có thể **mất cơ hội xử lý lại M3** sau crash.

Vì vậy cần phân biệt hai khoảng lỗi:

| Khoảng lỗi | Trạng thái có thể xảy ra | Hệ quả |
|---|---|---|
| Business xử lý xong, broker **chưa nhận ACK** | Message vẫn được coi chưa hoàn tất | Có thể **xử lý trùng** sau recovery |
| Broker **đã chấp nhận ACK**, business chưa lưu bền kết quả | Message không còn để giao lại | Có thể **mất tác động nghiệp vụ** sau crash |
| Business và ACK đều hoàn tất | Không cần giao lại theo luồng bình thường | Trạng thái mong muốn |
| Consumer chưa được deliver message | Message có thể còn chờ trong queue | Không liên quan việc đã xử lý trùng |

**Không có ràng buộc portable nào trong `DUPS_OK_ACKNOWLEDGE` bắt ACK phải đến sau database commit của ứng dụng.** Nếu nghiệp vụ yêu cầu chắc chắn xử lý mỗi yêu cầu thanh toán, đây thường **không phải chế độ nên chọn**.

### 4.1. Gửi lặp ở đây là *redelivery*, không phải producer gửi lại

Cần tách hai hiện tượng:

1. **Broker redelivery**: cùng một message được phát lại vì delivery trước chưa được xác nhận.
2. **Producer duplicate publish**: producer tạo/gửi thêm một message mới chứa cùng sự kiện nghiệp vụ khi không biết lần gửi trước thành công hay chưa.

DUPS_OK chủ yếu ảnh hưởng **(1)**. Nó **không ngăn được (2)**, dù provider luôn ACK sớm. Một `eventId` ổn định và idempotency ở consumer cần xử lý cả hai đường.

## 5. So sánh với AUTO, CLIENT và transacted session

| Chế độ JMS | Ai quyết định lúc xác nhận? | Mức kiểm soát sau xử lý nghiệp vụ | Khả năng duplicate/redelivery |
|---|---|---|---|
| `AUTO_ACKNOWLEDGE` | Provider theo quy tắc tự động của JMS | Thấp; với `receive()` đồng bộ, việc ACK không đợi DB commit sau khi method trả về | Có thể phát lại trong các lỗi tùy thời điểm; không phải exactly-once |
| `DUPS_OK_ACKNOWLEDGE` | Provider, được phép trì hoãn/lazy ACK | Thấp; không có mốc ACK do ứng dụng kiểm soát | **Cho phép** nhận trùng nhiều hơn khi provider bị lỗi |
| `CLIENT_ACKNOWLEDGE` | Ứng dụng gọi `Message.acknowledge()` | Có thể ACK sau xử lý, với lưu ý ACK theo **toàn session** | Nếu crash sau xử lý trước ACK thì có thể redelivery |
| `SESSION_TRANSACTED` | Ứng dụng gọi `Session.commit()`/`rollback()` | Kiểm soát transaction JMS cho send/receive | Rollback hoặc chưa commit có thể redelivery; vẫn phải chống trùng qua DB |

Ở session có `transacted=true`, mode ACK truyền cho `createSession(...)` **không có hiệu lực như một lựa chọn độc lập**. Local JMS transaction có semantics của commit/rollback.

Ví dụ chọn một trong bốn mode:

~~~java
// JMS 1.1 / javax.jms:
Session auto = connection.createSession(
        false, Session.AUTO_ACKNOWLEDGE);

Session dups = connection.createSession(
        false, Session.DUPS_OK_ACKNOWLEDGE);

Session client = connection.createSession(
        false, Session.CLIENT_ACKNOWLEDGE);

Session tx = connection.createSession(
        true, Session.SESSION_TRANSACTED);
~~~

### 5.1. CLIENT_ACKNOWLEDGE cũng có thể giảm số lần ACK

Với `CLIENT_ACKNOWLEDGE`, gọi `message.acknowledge()` xác nhận **các message đã consume trong session tính từ lần xác nhận trước**, chứ không chỉ message đang cầm trong tay. Vì thế ứng dụng có thể xử lý một nhóm rồi ACK sau khi toàn bộ nhóm hoàn tất.

Tuy nhiên, điều đó đặt trách nhiệm lên ứng dụng:

- Không dùng cùng một session đồng thời từ nhiều worker.
- Không ACK nếu trong nhóm có message chưa xử lý thành công.
- Nếu xử lý thất bại, cân nhắc `Session.recover()` hoặc đóng session theo hợp đồng provider.
- Nếu cần rollback nguyên tử các receive/send trong broker, dùng transacted session.

Điểm khác với DUPS_OK là **ứng dụng chủ động chọn lúc ACK**, nên có thể đặt ACK **sau** transaction xử lý. Đổi lại, code phải quản lý trạng thái batch, lỗi và timeout cẩn thận.

### 5.2. Khi nào nên chọn mode nào?

| Nhu cầu | Gợi ý |
|---|---|
| Đọc stream telemetry mà việc phát lại vài bản không gây hại, một ít message mất do ứng dụng lỗi cũng nằm trong rủi ro chấp nhận được | Có thể benchmark `DUPS_OK_ACKNOWLEDGE` |
| Xử lý lệnh tạo hóa đơn, thanh toán, cập nhật tồn kho | Ưu tiên `CLIENT_ACKNOWLEDGE` sau xử lý hoặc session transacted, có idempotency |
| Muốn xác nhận từng nhóm message sau khi đã xử lý hết | `CLIENT_ACKNOWLEDGE` theo session hoặc transaction JMS theo batch |
| Muốn nhận và phát message khác như một đơn vị nguyên tử trong broker | Session transacted; kiểm tra giới hạn transaction bên ngoài broker |
| Muốn giảm duplicate end-to-end qua producer retry và consumer crash | Dùng event ID, inbox/unique key và ranh giới commit rõ; riêng ACK mode chưa đủ |

Đối với các luồng quan trọng, **DUPS_OK không phải lựa chọn mặc định chỉ vì throughput có vẻ cao**. Cần có dữ liệu benchmark và chấp nhận rõ ràng về khả năng xử lý trùng/lỡ xử lý.

## 6. Ví dụ Classic JMS 1.1: tạo workload có thể đo

Các chương trình sau dùng **ActiveMQ Classic 5.x** và client `org.apache.activemq:activemq-client` thuộc nhánh sử dụng `javax.jms`. Chọn phiên bản phù hợp broker/JDK. Chạy broker lab ở `tcp://localhost:61616`; ví dụ dùng user `app`, password `lab-secret` và queue `lab.dupsok.jobs`. Điều chỉnh credential theo broker lab thực tế.

Chúng ta cố ý dùng JMS 1.1 với `try/finally` vì `javax.jms.Connection` và `javax.jms.Session` trong API này không triển khai `AutoCloseable`.

### 6.1. Producer gửi 200 message PERSISTENT với event ID rõ

Tệp Java minh họa `DupsOkSeed.java`:

~~~java
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.JMSException;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class DupsOkSeed {
    private static final String URL = "tcp://localhost:61616";

    public static void main(String[] args) throws JMSException {
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(URL);

        Connection connection =
                factory.createConnection("app", "lab-secret");
        try {
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue("lab.dupsok.jobs");
                MessageProducer producer = session.createProducer(queue);
                try {
                    producer.setDeliveryMode(DeliveryMode.PERSISTENT);

                    for (int i = 1; i <= 200; i++) {
                        String eventId = "dupsok-lab-" + i;
                        TextMessage message = session.createTextMessage(
                                "{\"eventId\":\"" + eventId + "\"}");
                        message.setStringProperty("eventId", eventId);
                        producer.send(message);
                    }

                    // Producer transacted: commit mới hoàn tất việc gửi.
                    session.commit();
                    System.out.println("Sent 200 persistent messages");
                } catch (JMSException | RuntimeException error) {
                    try {
                        session.rollback();
                    } catch (JMSException rollbackFailure) {
                        error.addSuppressed(rollbackFailure);
                    }
                    throw error;
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
}
~~~

Chương trình tạo **một nhóm có ID `dupsok-lab-1` tới `dupsok-lab-200`**. Chạy trên queue lab rỗng; không chạy nhiều lượt seed mà không dọn/dùng prefix mới, vì như vậy sẽ cố ý gửi trùng event IDs từ producer và làm sai kết quả đo redelivery.

Producer này **không sử dụng DUPS_OK_ACKNOWLEDGE**; nó là nguồn message để consumer bên dưới thử nghiệm. Chế độ ACK chỉ có ý nghĩa với session nhận.

### 6.2. Consumer DUPS_OK có tùy chọn crash đột ngột

Tệp `DupsOkConsumer.java`:

~~~java
import javax.jms.Connection;
import javax.jms.JMSException;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.Queue;
import javax.jms.Session;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class DupsOkConsumer {
    private static final String URL = "tcp://localhost:61616";

    public static void main(String[] args) throws Exception {
        // Chỉ chạy "crash" trong môi trường lab.
        boolean crash = args.length > 0 && "crash".equals(args[0]);

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(URL);
        Connection connection =
                factory.createConnection("app", "lab-secret");

        try {
            Session session = connection.createSession(
                    false, Session.DUPS_OK_ACKNOWLEDGE);
            try {
                Queue queue = session.createQueue("lab.dupsok.jobs");
                MessageConsumer consumer = session.createConsumer(queue);
                try {
                    connection.start();
                    int received = 0;

                    while (true) {
                        Message m = consumer.receive(3_000L);
                        if (m == null) {
                            break;
                        }

                        received++;
                        String eventId = m.getStringProperty("eventId");
                        String deliveryCount =
                                m.propertyExists("JMSXDeliveryCount")
                                ? String.valueOf(m.getIntProperty(
                                        "JMSXDeliveryCount"))
                                : "unavailable";

                        System.out.printf(
                                "RECEIVED eventId=%s jmsId=%s "
                              + "redelivered=%s deliveryCount=%s%n",
                                eventId,
                                m.getJMSMessageID(),
                                m.getJMSRedelivered(),
                                deliveryCount);

                        // Giả lập một ít công việc; không gọi acknowledge().
                        Thread.sleep(40L);

                        if (crash && received == 20) {
                            System.err.println(
                                    "SIMULATED ABRUPT CRASH after 20 receives");
                            // Bỏ qua finally: mô phỏng process bị kill.
                            Runtime.getRuntime().halt(71);
                        }
                    }

                    System.out.println("Received this run: " + received);
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
}
~~~

**Điểm cần quan sát:**

1. `Session.DUPS_OK_ACKNOWLEDGE` được chọn khi tạo session không transacted.
2. Consumer **không gọi `message.acknowledge()`**; provider tự quyết định cách ACK lazy.
3. `connection.start()` bắt đầu delivery trước `receive()`.
4. `JMSRedelivered` và property `JMSXDeliveryCount` là tín hiệu quan sát, **không phải bằng chứng duy nhất** của duplicate nghiệp vụ.
5. Tùy chọn `crash` gọi `Runtime.halt(71)` để dừng **chính tiến trình Java consumer**, không tắt broker. Chỉ sử dụng trong lab; chương trình bỏ qua cleanup để mô phỏng sự cố bất ngờ.
6. Không dựa vào số `20` làm ngưỡng chưa ACK: provider có thể đã ACK một phần hoặc toàn bộ trước khi tiến trình dừng.

**Tại sao không gọi `consumer.close()` để mô phỏng crash?** Đóng consumer/session một cách bình thường cho provider cơ hội flush/hoàn tất trạng thái; hành vi đó khác process bị kill đột ngột. `halt()` phù hợp hơn cho phép thử cửa sổ ACK chưa hoàn tất, dù duplicate vẫn không được bảo đảm sẽ xảy ra.

### 6.3. Thứ tự chạy lab

1. Đảm bảo queue `lab.dupsok.jobs` trống và broker có persistence. Khởi động producer `DupsOkSeed` **một lần**.
2. Chạy `DupsOkConsumer crash`, lưu lại các dòng `eventId` đã in ở 20 lần nhận.
3. Chạy `DupsOkConsumer` không có đối số để consumer mới đọc phần còn lại.
4. So sánh `eventId` ở hai lượt. Những event ID có trong **cả hai lượt** là bằng chứng đã quan sát redelivery.
5. Nếu không trùng, ghi nhận kết quả; **không kết luận DUPS_OK không bao giờ gây duplicate**. Provider có thể đã xác nhận đủ sớm hoặc tình huống chưa chạm đúng cửa sổ lỗi.
6. Lặp lại trên queue mới với `AUTO_ACKNOWLEDGE` và `CLIENT_ACKNOWLEDGE` để đánh giá khác biệt. Với CLIENT mode, thêm logic ACK theo nhóm sau xử lý nếu muốn kiểm soát điểm xác nhận.

Khi quan sát chính xác, nhớ rằng `JMSMessageID` có thể được giữ giữa các lần **broker redelivery** cùng message, nhưng hai lần producer publish cùng event thường có thể có JMSMessageID khác nhau. **So sánh `eventId`** là bước quan trọng nhất để đánh giá duplicate ở tầng nghiệp vụ.

### 6.4. Không có duplicate trong một lần thử là kết quả hợp lệ

JMS cho phép DUPS_OK lazy ACK, nhưng **không hứa rằng provider nhất định phải trì hoãn ACK tới mốc kill**. Để thu được dữ liệu đáng tin:

- Lặp lại một số lượt với queue/test run ID khác nhau.
- Thử các kích thước tải và tốc độ consumer khác nhau.
- Ghi đúng phiên bản broker, thư viện ActiveMQ, chế độ persistence, prefetch, topology và thời điểm crash.
- Không thay nhiều biến cùng lúc; ghi số message **đã receive**, **đã process**, **đã redeliver** và **còn ở queue**.
- Tránh dùng một message duy nhất làm bằng chứng định lượng cho ACK batching.

## 7. ACK lazy, prefetch và broker metrics: ba tầng khác nhau

Trong ActiveMQ Classic, consumer có thể được prefetch nhiều message. Artemis có các cơ chế flow control/buffering riêng. Cần tách ba việc:

1. **Dispatch/prefetch:** broker/client đã đưa message tới bộ đệm consumer.
2. **Application receive:** mã Java thật sự nhận message từ `receive()` hoặc listener.
3. **Acknowledgment:** broker đã nhận ACK có hiệu lực đối với delivery.

Do vậy:

~~~text
Broker queue:    ready       delivering / unacknowledged
Consumer client: prefetched  delivered to application
Business DB:     processed   not yet processed
~~~

Không thể chỉ nhìn `queue depth = 0` để kết luận mọi message đã được ACK hoặc DB đã commit. Broker console và JMX có thể hiển thị riêng các chỉ số pending, dequeued, dispatched, in-flight hoặc delivering, tùy phiên bản.

Khi đo ảnh hưởng của DUPS_OK, nên quan sát:

| Chỉ số | Ý nghĩa |
|---|---|
| Message throughput (msg/s) | Hiệu năng tổng thể khi thay ACK mode |
| Consumer receive latency | Thời gian ứng dụng nhận message |
| Broker in-flight/delivering | Số message đã dispatch nhưng chưa hoàn tất theo broker |
| ACK/dequeue rate | Tần suất broker xác nhận/loại message khỏi backlog |
| Redelivery count | Message đã được giao lại; cần xem theo từng test ID |
| CPU client/broker | Có thực sự giảm overhead hay không |
| Network bytes/packets | Có giảm lưu lượng ACK hay không, đặc biệt khi nhiều message nhỏ |
| Disk/store load | ACK và transaction có tạo áp lực I/O không |
| Duplicate business events | Một `eventId` được xử lý mấy lần; đo bằng inbox/unique key |

Trong một số provider, `optimizeAcknowledge`/ack batching hoặc các tối ưu client là **cấu hình riêng**, không đồng nghĩa với bản thân mode DUPS_OK. Phải ghi rõ chúng có bật không để so sánh công bằng.

## 8. Chống xử lý trùng: event ID ổn định và inbox transaction

Nếu một message đã được ứng dụng xử lý nhưng broker chưa ghi nhận ACK, nó có thể được phát lại. Consumer cần nhận diện cùng một sự kiện nghiệp vụ qua các lần giao.

Ví dụ producer đặt một ID ổn định:

~~~java
TextMessage message = session.createTextMessage(payload);
message.setStringProperty("eventId", "EVT-1001");
producer.send(message);
~~~

Ở phía consumer, **không dùng riêng `JMSRedelivered`** để quyết định skip. Một producer có thể gửi hai message mới chứa cùng `eventId` và cả hai đều có `JMSRedelivered=false`.

### 8.1. SQL inbox để chống duplicate

Ví dụ dùng PostgreSQL:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(100) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Pseudo-code cho consumer:

~~~text
Receive message(eventId)
  BEGIN DB TRANSACTION
    INSERT INTO processed_events(consumer_name, eventId)
      ON CONFLICT DO NOTHING

    Nếu INSERT mới thành công:
      Áp dụng thay đổi nghiệp vụ trong CÙNG DB TRANSACTION
    Nếu eventId đã có:
      Không làm lại side effect
  COMMIT DB TRANSACTION
  ACK JMS theo mode đã chọn
~~~

**Điều kiện quan trọng:** ghi inbox và side effect trong cùng một transaction database hoặc cơ chế nguyên tử tương đương. Chỉ ghi một `HashSet` trong RAM không đủ, vì crash sẽ xóa lịch sử và các worker khác không cùng chia trạng thái.

### 8.2. Idempotency không vá được khoảng mất message do ACK quá sớm

Inbox ngăn **làm lại side effect**, nhưng không sửa được trường hợp:

~~~text
DUPS_OK provider ACK message
-> application chưa commit DB
-> process crash
-> broker không còn message để giao lại
~~~

Với dữ liệu quan trọng, nên chuyển sang `CLIENT_ACKNOWLEDGE` và **chỉ gọi ACK sau DB commit**, hoặc dùng transacted JMS receive/commit thích hợp. Vẫn cần inbox để xử lý trường hợp DB commit đã xong nhưng JMS ACK/commit chưa tới broker.

Đây là tiêu chí chọn DUPS_OK thiết thực nhất: **ứng dụng có thực sự chấp nhận rủi ro gắn với thời điểm ACK không do mình kiểm soát?**

## 9. Đổi sang CLIENT_ACKNOWLEDGE cho nghiệp vụ quan trọng

Ví dụ thay đoạn nhận trong consumer bằng session có ACK chủ động:

~~~java
Session session = connection.createSession(
        false, Session.CLIENT_ACKNOWLEDGE);

Queue queue = session.createQueue("billing.commands");
MessageConsumer consumer = session.createConsumer(queue);

try {
    connection.start();
    Message message = consumer.receive(5_000L);

    if (message != null) {
        // Phải commit nghiệp vụ + ghi inbox idempotent trước khi ACK.
        processAndCommitDatabaseTransaction(message);

        // Trong CLIENT_ACKNOWLEDGE, ACK bao phủ các message đã nhận
        // trong session kể từ lần ACK trước.
        message.acknowledge();
    }
} finally {
    consumer.close();
    session.close();
}
~~~

Đoạn code giả định đã có `Connection connection` và hàm `processAndCommitDatabaseTransaction(Message)` do ứng dụng triển khai. Với JMS 1.1, cần đóng `Connection` ở nơi sở hữu nó bằng `finally`.

Trong chương trình thực:

- Nếu DB xử lý thất bại: không gọi ACK, xử lý `session.recover()` hoặc đóng session để provider khôi phục delivery theo hợp đồng.
- Nếu DB đã commit mà consumer chết trước ACK: có thể nhận lại; inbox bảo vệ khỏi side effect trùng.
- Nếu một session đã nhận nhiều message, gọi ACK sẽ xác nhận cả phạm vi session. Khi cần ACK riêng từng công việc, dùng **mỗi worker một session** và thiết kế thứ tự nhận/ACK hợp lý.
- Nếu cần atomicity cho nhiều thao tác JMS, `SESSION_TRANSACTED` có `commit/rollback`; **không tự động nguyên tử với database transaction**.

Đổi mode là thay đổi hành vi delivery thực tế, vì vậy cần kiểm thử dưới crash/reconnect, không chỉ kiểm tra luồng thành công.

## 10. Classic và Artemis: hợp đồng JMS chung, chi tiết vận hành khác

Cả ActiveMQ Classic lẫn Artemis hỗ trợ ý nghĩa JMS của `DUPS_OK_ACKNOWLEDGE`, nhưng cách client/broker tối ưu xác nhận có thể khác nhau theo version và giao thức.

| Khía cạnh | ActiveMQ Classic | ActiveMQ Artemis |
|---|---|---|
| API Java truyền thống | JMS 1.1 `javax.jms.Session.DUPS_OK_ACKNOWLEDGE` ở client Classic tương thích | JMS provider tương thích namespace/version client đang dùng |
| Cách tạo session | `connection.createSession(false, Session.DUPS_OK_ACKNOWLEDGE)` | Tương đương trong API JMS, hoặc `JMSContext.DUPS_OK_ACKNOWLEDGE` với API hỗ trợ |
| Chi tiết ACK batching | Phụ thuộc cấu hình transport/client, prefetch và phiên bản | Phụ thuộc Artemis client/protocol/flow control và phiên bản |
| Duplicate do broker redelivery | Có thể quan sát `JMSRedelivered` và thuộc tính delivery count nếu provider hỗ trợ | Tương tự theo contract JMS, kiểm thử mapping của client |
| DLQ/redelivery policy | Chính sách Classic/ActiveMQ client và broker | Address settings của Artemis |
| Kiểm chứng | JMX/Web Console, client logs, fault injection | Management API/console, metric, fault injection |

Với Jakarta Messaging/JMS 2.0 API, cú pháp rút gọn có thể là:

~~~java
// Ví dụ API theo client Jakarta JMS hỗ trợ JMSContext.
try (jakarta.jms.JMSContext context =
             factory.createContext(
                     jakarta.jms.JMSContext.DUPS_OK_ACKNOWLEDGE)) {
    jakarta.jms.Queue queue = context.createQueue("metrics.raw");
    jakarta.jms.JMSConsumer consumer = context.createConsumer(queue);
    jakarta.jms.Message message = consumer.receive(3_000L);
    // Provider tự xử lý ACK lazy; ứng dụng cần chấp nhận duplicate.
}
~~~

`factory` trong ví dụ này phải là `jakarta.jms.ConnectionFactory` của provider tương thích, chẳng hạn Artemis Jakarta client phù hợp broker/JDK. Không trộn `javax.jms` của Classic 5.x với `jakarta.jms` trong cùng source. `JMSContext` thuộc API hiện đại hỗ trợ `AutoCloseable`; `Connection`/`Session` của JMS 1.1 ở ví dụ trước thì không.

**Đừng coi việc hai broker đều có mode DUPS_OK là lời hứa có cùng số message chưa ACK.** Sự khác nhau của prefetch, buffering, journal, transaction, topology và client library có thể làm kết quả crash/benchmark khác nhau.

## 11. Kịch bản kiểm chứng và cách diễn giải kết quả

### 11.1. So sánh chế độ ACK trên cùng workload

Lập ba lượt test độc lập, mỗi lượt queue riêng hoặc dọn dữ liệu giữa các lượt:

1. `AUTO_ACKNOWLEDGE`.
2. `DUPS_OK_ACKNOWLEDGE`.
3. `CLIENT_ACKNOWLEDGE` với ACK sau mỗi N message **đã xử lý thành công**, ví dụ N=50.

Giữ nguyên số producer, loại message, delivery mode, số consumer, payload, prefetch, broker persistence, network và thời gian đo. Không thay N và prefetch cùng lúc khi muốn rút kết luận từ một biến.

Ghi kết quả bằng bảng:

| Chỉ số | AUTO | DUPS_OK | CLIENT ACK theo nhóm |
|---|---:|---:|---:|
| Throughput (msg/s) | Đo | Đo | Đo |
| p95 latency nhận (ms) | Đo | Đo | Đo |
| CPU broker (%) | Đo | Đo | Đo |
| ACK/dequeue rate | Đo | Đo | Đo |
| Delivery trùng sau crash | Đếm | Đếm | Đếm |
| Business side effect trùng sau inbox | Đếm | Đếm | Đếm |

**Không điền sẵn con số tăng tốc** nếu chưa đo. Nếu throughput cải thiện nhỏ mà rủi ro khi crash lớn, cấu hình nhanh hơn trên giấy chưa chắc có giá trị vận hành.

### 11.2. Các kết luận phải tránh

- **“Không thấy duplicate trong lab nên mode bảo đảm không duplicate.”** Sai: chưa gặp đúng failure window.
- **“DUPS_OK giảm ACK nên chắc chắn không mất message.”** Sai: thời điểm ACK không gắn với commit nghiệp vụ.
- **“Cờ `JMSRedelivered=false` chứng minh event chưa xử lý lần nào.”** Sai: producer có thể publish trùng với JMS message mới.
- **“Queue trống nghĩa là consumer xử lý xong.”** Sai: prefetch/in-flight và ACK logic khác DB transaction.
- **“Producer bật `PERSISTENT` thì consumer DUPS_OK có exactly-once.”** Sai: persistence và acknowledgment giải quyết các rủi ro khác nhau.
- **“Có DLQ thì duplicate được giải quyết.”** Sai: DLQ dành cho lỗi theo policy, không tự khử side effect trùng.

### 11.3. Tiêu chí chấp nhận cho bài lab

Bài thực hành đạt khi:

1. Producer gửi được đúng 200 message có 200 `eventId` khác nhau trong một test run.
2. Consumer nhận từ queue với session `DUPS_OK_ACKNOWLEDGE` và không gọi ACK thủ công.
3. Có log đủ `eventId`, `JMSMessageID`, `JMSRedelivered` và `JMSXDeliveryCount` (nếu có).
4. Người học giải thích được vì sao crash mode **có thể** dẫn tới trùng và vì sao **không trùng** cũng hợp lệ.
5. Người học không suy từ một lần thử ra “tỷ lệ duplicate cố định của DUPS_OK”.
6. Có phương án chống trùng bằng inbox, và chỉ rõ rủi ro business chưa commit trước khi ACK.
7. Chọn được ACK mode phù hợp cho một luồng telemetry và một luồng thanh toán, kèm lý do.

## 12. Bài tập tình huống và lời giải

**Tình huống A — Metrics cập nhật lặp.** Một event có ID `metric-2026-11-17-001` chỉ ghi giá trị đo cuối cùng của thiết bị bằng phép upsert, nhận lại cùng giá trị không đổi kết quả. Đường dữ liệu cho phép mất một số mẫu vì còn cơ chế đồng bộ định kỳ.

**Hỏi:** DUPS_OK có thể dùng không?  
**Trả lời:** Có thể cân nhắc sau benchmark, vì duplicate được chấp nhận và thiếu một mẫu trong một số failure window không phá vỡ nghiệp vụ. Vẫn nên có event ID và giám sát lag.

**Tình huống B — Tính phí thẻ.** Consumer nhận lệnh `ChargeCard(orderId=O-1001)` rồi gọi API thanh toán không có idempotency key. Đội phát triển muốn chuyển AUTO sang DUPS_OK để tăng throughput.

**Hỏi:** Rủi ro chính?  
**Trả lời:** Nếu broker giao lại cùng lệnh, API có thể trừ tiền hai lần; nếu ACK xảy ra trước khi side effect được lưu bền, lệnh có thể không được thực hiện sau crash. Không chọn DUPS_OK cho luồng này khi chưa có idempotency/transaction và ranh giới ACK sau xử lý.

**Tình huống C — Một consumer nhận 50 message rồi mới ACK.** Một nhóm dùng `CLIENT_ACKNOWLEDGE`, gọi `acknowledge()` trên message thứ 50 sau khi xử lý hết 50 message.

**Hỏi:** Đó có phải ACK riêng message 50 không?  
**Trả lời:** Không. Theo JMS, đó là ACK cho **các message đã consume trong session** từ lần xác nhận trước. Nếu một message trong nhóm thất bại, không được ACK nhóm như đã hoàn tất. DUPS_OK không cho ứng dụng quyền chủ động chọn mốc ACK kiểu này.

**Tình huống D — Đóng consumer nhẹ nhàng rồi mở lại.** Test DUPS_OK nhận 10 message, `consumer.close()` và `connection.close()` bình thường, mở lại không thấy redelivery.

**Hỏi:** Có chứng minh mode không lazy ACK?  
**Trả lời:** Không. Provider có thể flush trạng thái lúc close, hoặc ACK đã có hiệu lực trước đó. Muốn thử failure window phải đưa vào crash/connection loss có kiểm soát và quan sát qua nhiều lượt.

**Tình huống E — Cùng `eventId` nhưng khác `JMSMessageID`.** Consumer thấy hai message có `eventId=EVT-99`, đều `JMSRedelivered=false`.

**Hỏi:** Có thể là duplicate không?  
**Trả lời:** Có. Đây có thể là hai lần producer gửi mới cùng một event. Cần deduplicate theo event ID nghiệp vụ; DUPS_OK chỉ liên quan cách ACK delivery, không ngăn producer gửi lặp.

## 13. Checklist áp dụng vào production

- [ ] Luồng này thực sự chấp nhận được duplicate và failure window với ACK do provider quyết định?
- [ ] Đã đo DUPS_OK so với AUTO/CLIENT/transacted trên **cùng** throughput và payload?
- [ ] Đã xác minh phiên bản broker/client, prefetch và các tối ưu ACK đang bật?
- [ ] Có event ID ổn định khi producer retry, cùng idempotent inbox/unique key tại consumer?
- [ ] Nếu DB side effect quan trọng, đã dùng mốc ACK/commit phù hợp **sau** DB commit?
- [ ] Có log `JMSMessageID`, `eventId`, redelivery count và quan sát queue in-flight?
- [ ] Đã thử kill consumer khi đang xử lý, reconnect và rollback ở chế độ đối chứng?
- [ ] Không dùng duplicate count từ một lần thử làm tỷ lệ lỗi mặc định của toàn hệ thống?
- [ ] Có cảnh báo về duplicate business events, backlog, latency và disk/store pressure?
- [ ] Hệ thống có quy trình replay/điều tra sự cố mà vẫn giữ event ID/idempotency?

## 14. Kết luận kỹ thuật

`Session.DUPS_OK_ACKNOWLEDGE` cho phép JMS provider **trì hoãn xác nhận delivery**, từ đó **có thể** giảm chi phí ACK và cải thiện throughput trong một số workload. Đổi lại, khi lỗi xảy ra trong lúc ACK chưa có hiệu lực, broker **có thể giao lại** những message ứng dụng đã thấy hoặc đã xử lý.

Chế độ này phù hợp nhất với consumer **thực sự chịu được việc nhận trùng** và không đòi hỏi một điểm ACK chính xác sau business commit. Với lệnh tài chính, hóa đơn hoặc cập nhật dữ liệu quan trọng, cần **CLIENT_ACKNOWLEDGE** hoặc **transacted session** có kiểm soát, kết hợp **event ID và idempotent consumer**.

Điều quyết định không nằm ở việc tên mode chứa “DUPS_OK”, mà ở hợp đồng thực tế: **ai chọn mốc ACK, những delivery nào có thể bị phát lại khi sự cố xảy ra, và việc xử lý trùng hoặc mất tác động nghiệp vụ có được chấp nhận hay không**.
