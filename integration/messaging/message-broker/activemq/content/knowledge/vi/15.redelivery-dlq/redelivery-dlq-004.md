# Redelivery delay, hệ số tăng và số lần giao tối đa của Artemis

> **Chương:** Gửi lại và DLQ  
> **Phạm vi:** Apache ActiveMQ **Artemis** khi consumer Java/JMS xử lý thất bại và message được broker phân phối lại. Tập trung vào năm tham số `redelivery-delay`, `redelivery-delay-multiplier`, `max-redelivery-delay`, `redelivery-collision-avoidance-factor` và `max-delivery-attempts`. Ví dụ dùng Artemis 2.57.x, JDK 17 và Jakarta Messaging (`jakarta.jms`); không áp dụng XML này cho ActiveMQ Classic.

## 1. Điều cần kiểm soát khi một message liên tục thất bại

Một consumer đọc `orders.retry.lab` rồi gọi `rollback()` vì hệ thống kiểm tra tồn kho chưa sẵn sàng. Nếu broker phân phối lại ngay lập tức, ứng dụng có thể nhận cùng một message hàng trăm lần mỗi giây (*retry thrashing*). Nếu bắt lỗi rồi gửi lại vô hạn, một message không thể xử lý sẽ chiếm tài nguyên mà không có điểm kết thúc.

Artemis cho phép cấu hình **thời gian chờ trước lần phân phối kế tiếp**, **cách tăng thời gian chờ qua các lần thất bại**, và **ngưỡng chấm dứt retry** ở phía broker:

```text
Consumer             Broker: orders.retry.lab               DLQ
   │  nhận lần 1                   │                           │
   ├── rollback ──────────────────▶│                           │
   │                    đợi 1 giây │                           │
   │◀──────────────── nhận lần 2 ──┤                           │
   ├── rollback ──────────────────▶│                           │
   │                    đợi 2 giây │                           │
   │◀──────────────── nhận lần 3 ──┤                           │
   ├── rollback ──────────────────▶│                           │
   │                    đợi 3 giây │                           │
   │◀──────────────── nhận lần 4 ──┤                           │
   ├── rollback ──────────────────▶│ ── chuyển tới DLQ ──────▶ │
   │                               │                           │
```

Sơ đồ sử dụng cấu hình mẫu ở mục 3: `redelivery-delay=1000`, multiplier `2.0`, cap `3000`, tối đa `4` lần giao và jitter `0`. **Lần giao đầu tiên cũng được tính** trong ngưỡng bốn lần; vì vậy chỉ có **ba khoảng chờ retry**, không phải bốn. Các mốc là lịch dự kiến, thời điểm nhận thực tế còn phụ thuộc scheduling, tải và consumer.

## 2. Khi nào Artemis bắt đầu đếm một lần giao thất bại?

Artemis theo dõi số lần giao của **message/queue reference**, không chỉ số lần Java gọi một hàm. Một message trở thành ứng viên redelivery khi broker cần thu hồi lần phân phối chưa được xác nhận, thường gặp:

- Consumer dùng `JMSContext.SESSION_TRANSACTED` nhận message rồi gọi `rollback()`.
- Consumer/session mất kết nối hoặc bị đóng khi vẫn còn message chưa được acknowledge/commit; broker thu hồi phần chưa được xác nhận.
- Consumer xử lý thất bại trong một transaction đã rollback; lỗi nghiệp vụ chỉ gây redelivery nếu application thực sự rollback hoặc không ACK.

Ngược lại, ứng dụng **bắt exception rồi commit** (hoặc đã ACK message ở chế độ phù hợp) sẽ không kích hoạt redelivery cho message ấy. Cấu hình broker không thể đoán rằng bước xử lý trong ứng dụng đã sai nếu ứng dụng xác nhận thành công.

### Những tín hiệu nên đọc

| Tín hiệu | Cách hiểu trong bài thực hành |
|---|---|
| `JMSXDeliveryCount=1` | Lần phân phối đầu trong phép thử mới |
| `JMSXDeliveryCount=2,3,...` | Các lần phân phối tiếp theo của cùng message |
| `JMSRedelivered=false` | Theo thông tin provider, đây chưa phải phân phối lại |
| `JMSRedelivered=true` | Provider đánh dấu message là bản phân phối lại |
| `JMSMessageID` và `labEventId` | Dùng để đối chiếu cùng một message qua nhiều lần nhận |
| Queue có scheduled message | Có message đang chờ đến hạn giao lại, **không đồng nghĩa bị mất** |

Trong một broker đơn lẻ và các lần rollback bình thường, `JMSXDeliveryCount` thường tăng lần lượt `1, 2, 3, 4`; `JMSRedelivered` chuyển thành `true` từ lần tiếp theo. Tuy nhiên, khi **broker crash trước khi lưu delivery count** hoặc với topology có redistribution/failover, đừng coi chỉ số này là bằng chứng kiểm toán tuyệt đối cho mọi lần giao đã xảy ra; xem mục 8.

## 3. Cấu hình Artemis rõ ràng trong `broker.xml`

Thêm hoặc chỉnh sửa **một entry** trong `<address-settings>` hiện hữu, rồi khai báo queue nguồn và queue DLQ ở `<addresses>`. Dưới đây là các **mảnh ghép để tích hợp**, không phải toàn bộ `broker.xml`; không tạo hai phần tử `<address-settings>` hoặc `<addresses>` trùng nhau.

### 3.1. Chính sách retry cho đúng address

```xml
<address-setting match="orders.retry.lab">
    <redelivery-delay>1000</redelivery-delay>
    <redelivery-delay-multiplier>2.0</redelivery-delay-multiplier>
    <max-redelivery-delay>3000</max-redelivery-delay>
    <redelivery-collision-avoidance-factor>0.0</redelivery-collision-avoidance-factor>
    <max-delivery-attempts>4</max-delivery-attempts>
    <dead-letter-address>orders.retry.dlq</dead-letter-address>
</address-setting>
```

Đơn vị delay là **mili giây**; `1000` là 1 giây, `3000` là 3 giây. `match` khớp **địa chỉ (address)** nơi message được gửi, không tùy tiện khớp một tên queue không cùng address. Ví dụ này cố ý dùng cùng tên address và queue để tránh nhập nhằng.

### 3.2. Định nghĩa destination đầu vào và đích DLQ tường minh

```xml
<address name="orders.retry.lab">
    <anycast>
        <queue name="orders.retry.lab"/>
    </anycast>
</address>

<address name="orders.retry.dlq">
    <anycast>
        <queue name="orders.retry.dlq"/>
    </anycast>
</address>
```

Hai fragment trên đặt **bên trong `<addresses>`** hiện có. Với routing `ANYCAST` và queue được tạo sẵn, Java JMS `createQueue("orders.retry.lab")`/`createQueue("orders.retry.dlq")` có tên rõ ràng và không phụ thuộc vào `auto-create-queues`. Bảo đảm broker bật persistence và message seed là `DeliveryMode.PERSISTENT` nếu bài kiểm thử còn bao gồm restart.

**Lỗi cấu hình có thể làm mất dữ liệu:** nếu đặt giới hạn `max-delivery-attempts` nhưng **không cấu hình `dead-letter-address`**, tài liệu Artemis quy định message sẽ bị **loại bỏ** khi vượt ngưỡng. Đừng thử nghiệm giới hạn retry trên message thật trước khi xác nhận address DLQ có queue nhận, policy không bị ghi đè và quyền quản trị/giám sát đầy đủ.

### 3.3. Bảng tham số và giá trị mặc định

| Tham số | Vai trò | Giá trị mặc định theo tài liệu Artemis 2.57.0 |
|---|---|---|
| `redelivery-delay` | Khoảng chờ ban đầu trước khi giao lại message vừa bị cancel/rollback | `0` ms — có thể retry ngay |
| `redelivery-delay-multiplier` | Hệ số nhân cho các khoảng chờ kế tiếp | `1.0` — khoảng chờ không tăng |
| `max-redelivery-delay` | Trần của thời gian chờ tăng dần | `10 × redelivery-delay` nếu không khai báo |
| `redelivery-collision-avoidance-factor` | Hệ số biến thiên ngẫu nhiên nhằm tránh retry đồng loạt | `0.0`; khoảng hợp lệ `0.0–1.0` |
| `max-delivery-attempts` | Số lần giao thất bại trước khi chuyển sang dead-letter address | `10`; `-1` để không giới hạn |
| `dead-letter-address` | Address nhận message sau khi hết lượt giao | Không có giá trị mặc định bắt buộc cho mọi address |

Các giá trị trong file `broker.xml` **đã tạo từ image** có thể ghi đè default của phần mềm. Luôn đọc cấu hình **đang có hiệu lực** trên broker thực tế, thay vì suy diễn từ bảng mặc định. `max-delivery-attempts=-1` nghĩa là không có giới hạn giao lại; nó không tự tạo chiến lược xử lý poison message.

## 4. Tính chính xác lịch chờ: delay, multiplier và cap

Khi `redelivery-collision-avoidance-factor=0`, mô hình thời gian chờ dự kiến sau lần giao thất bại thứ `n` (để giao lần thứ `n+1`) có thể viết:

\[
D_n = \min(D_{\max},\; D_0 \times m^{\,n-1})
\]

Trong đó:

- `D₀` = `redelivery-delay` (ms), dùng sau lần nhận thứ nhất;
- `m` = `redelivery-delay-multiplier`;
- `Dmax` = `max-redelivery-delay`;
- `n` = 1, 2, 3… **chỉ khi broker còn cho phép một lần giao kế tiếp**.

Với `D₀ = 1000 ms`, `m=2`, `Dmax=3000 ms`, `max-delivery-attempts=4`:

| Lần giao | `JMSXDeliveryCount` dự kiến | Kết quả xử lý | Độ trễ trước bước tiếp theo |
|---|---:|---|---|
| Lần 1 | 1 | Rollback | `min(3000, 1000)=1000 ms` rồi giao lần 2 |
| Lần 2 | 2 | Rollback | `min(3000, 2000)=2000 ms` rồi giao lần 3 |
| Lần 3 | 3 | Rollback | `min(3000, 4000)=3000 ms` rồi giao lần 4 |
| Lần 4 | 4 | Rollback | **Hết lượt: chuyển DLQ, không chờ để giao lần 5** |

Tổng thời gian chờ danh nghĩa trước bốn lần giao khoảng **6 giây**, chưa tính thời gian xử lý và scheduler. Không dùng phép cộng này làm ngưỡng timeout tuyệt đối trong một test integration: broker bận, consumer được schedule trễ hoặc có giao dịch kéo dài có thể làm thời điểm thực tế lệch.

**Phân biệt ngưỡng:** `max-delivery-attempts=4` trong bài tương ứng **bốn lần giao có thể thất bại** (một lần đầu + ba lần giao lại), chứ không phải “bốn lần retry sau lần đầu”. Ở lần thất bại cuối, broker chuyển message sang `dead-letter-address`. Việc có thể quan sát đủ bốn lần qua `receive()` phụ thuộc quy trình rollback và không có consumer khác cùng nhận message.

### Hai phép thử tư duy

1. Nếu `redelivery-delay=0`, nhân với `2` vẫn bằng 0: multiplier **không tự tạo độ trễ**. Phải chọn một base delay lớn hơn 0 nếu muốn tránh retry liên tục.
2. Nếu đặt `max-redelivery-delay=3000` nhưng quên `max-delivery-attempts`, khoảng cách giữa các lần giao sẽ được chặn ở 3 giây, **không đồng nghĩa** broker chỉ thử ba lần. Một tham số hạn chế **thời gian**, tham số kia hạn chế **số lần**.

## 5. Collision avoidance: giảm hàng loạt retry cùng một thời điểm

Trong môi trường nhiều consumer, các transaction cùng thất bại vì một database tạm mất kết nối có thể rollback gần như đồng thời. Nếu cùng chờ chính xác 2 giây, chúng lại truy cập database cùng lúc, tạo thác lỗi kế tiếp.

Tham số `redelivery-collision-avoidance-factor` thêm độ biến thiên ngẫu nhiên (*jitter*) vào delay tính toán, để trải các lần retry ra theo thời gian. Với hệ số `f` và biến ngẫu nhiên `r` thuộc `[0,1]`, có thể hình dung:

\[
D_{\text{thực}} \approx D_{\text{cơ sở}} \times (1 \pm f r)
\]

Artemis chọn dấu tăng/giảm và hệ số ngẫu nhiên; đây là mô hình minh họa biến thiên, không phải API cam kết một timestamp chính xác. Ví dụ `f=0.15` làm khoảng chờ xấp xỉ ±15% quanh giá trị cơ sở. Khi bật jitter, **không viết assertion thời gian chính xác từng mili giây**.

**Cấu hình sử dụng cho môi trường có nhiều consumer:**

```xml
<redelivery-delay>1000</redelivery-delay>
<redelivery-delay-multiplier>2.0</redelivery-delay-multiplier>
<max-redelivery-delay>15000</max-redelivery-delay>
<redelivery-collision-avoidance-factor>0.15</redelivery-collision-avoidance-factor>
```

Đây chỉ là bốn trường thay thế trong `address-setting`, **không** phải một policy XML hoàn chỉnh. Nên bật jitter sau khi đã kiểm thử mẫu không jitter vì những khoảng thời gian ngẫu nhiên khiến test thời gian khó đọc. Nếu ứng dụng phụ thuộc vào thứ tự message, cần hiểu rằng delay có thể khiến **message mới vượt qua message bị rollback**: broker chỉ trì hoãn message thất bại, các message khác có thể tiếp tục được phân phối. Không mặc định có FIFO tuyệt đối sau rollback.

## 6. Thực hành Java/JMS: đo bốn lần giao rồi kiểm tra DLQ

Mục tiêu: gửi **một** message mới, sử dụng **một consumer**, gọi `rollback()` bốn lần, ghi `JMSXDeliveryCount` và thời gian giữa các lần nhận, sau đó nhận chính message đó từ queue DLQ. Bài lab dùng **Core client** của Artemis; không trộn với ActiveMQ Classic `RedeliveryPolicy` ở client.

### 6.1. Maven dependency

```xml
<!-- pom.xml: bổ sung trong <dependencies> của ứng dụng JDK 17. -->
<dependency>
    <groupId>org.apache.artemis</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.57.0</version>
</dependency>
```

Thiết lập `maven.compiler.release=17` trong project. Dùng broker Artemis 2.57.x có queue/policy đã thiết lập ở mục 3; cung cấp `BROKER_USER` và `BROKER_PASSWORD` từ nguồn cấu hình an toàn của lab.

### 6.2. Chương trình `ArtemisRedeliveryProbe.java`

```java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class ArtemisRedeliveryProbe {
    private static final String SOURCE = "orders.retry.lab";
    private static final String DLQ = "orders.retry.dlq";
    private static final int MAX_ATTEMPTS = 4;

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + name);
        }
        return value;
    }

    public static void main(String[] args) {
        String user = requiredEnv("BROKER_USER");
        String password = requiredEnv("BROKER_PASSWORD");
        String url = System.getenv().getOrDefault(
            "BROKER_URL",
            "tcp://127.0.0.1:61616?consumerWindowSize=0");
        String eventId = "probe-" + UUID.randomUUID();

        ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(url);
        try {
            // Seed bằng một context khác: message đã gửi thành công trước
            // khi bắt đầu transaction đọc/rollback.
            try (JMSContext sender = factory.createContext(
                    user, password, JMSContext.AUTO_ACKNOWLEDGE)) {
                Queue source = sender.createQueue(SOURCE);
                sender.createProducer()
                      .setDeliveryMode(DeliveryMode.PERSISTENT)
                      .setProperty("labEventId", eventId)
                      .send(source, "DEMO-RETRY");
            }

            long previousAt = -1;
            try (JMSContext tx = factory.createContext(
                    user, password, JMSContext.SESSION_TRANSACTED)) {
                JMSConsumer consumer = tx.createConsumer(tx.createQueue(SOURCE));
                tx.start();

                for (int expected = 1; expected <= MAX_ATTEMPTS; expected++) {
                    Message message = consumer.receive(15_000L);
                    if (message == null) {
                        throw new IllegalStateException(
                            "Timed out waiting for attempt " + expected);
                    }
                    String observedId = message.getStringProperty("labEventId");
                    int count = message.getIntProperty("JMSXDeliveryCount");
                    boolean redelivered = message.getJMSRedelivered();
                    long now = System.nanoTime();
                    long deltaMs = previousAt < 0 ? -1
                        : TimeUnit.NANOSECONDS.toMillis(now - previousAt);

                    System.out.printf(
                        "attempt=%d deliveryCount=%d redelivered=%s deltaMs=%d%n",
                        expected, count, redelivered, deltaMs);

                    if (!eventId.equals(observedId) || count != expected) {
                        tx.rollback(); // không commit message không mong đợi
                        throw new IllegalStateException("Unexpected message/count");
                    }
                    previousAt = now;
                    tx.rollback(); // trigger delayed redelivery
                }
            }

            // Lần rollback thứ tư khiến message vượt ngưỡng -> DLQ.
            // AUTO_ACKNOWLEDGE chỉ tiêu thụ message DLQ của LAB này.
            try (JMSContext inspect = factory.createContext(
                    user, password, JMSContext.AUTO_ACKNOWLEDGE)) {
                Message moved = inspect.createConsumer(inspect.createQueue(DLQ))
                    .receive(10_000L);
                if (moved == null ||
                    !eventId.equals(moved.getStringProperty("labEventId"))) {
                    throw new IllegalStateException("Expected message missing in DLQ");
                }
                System.out.println("PASS: eventId=" + eventId + " reached DLQ");
            }
        } finally {
            factory.close();
        }
    }
}
```

**Giải thích các lựa chọn trong code:**

- `SESSION_TRANSACTED` khiến `rollback()` hoàn nguyên lần nhận hiện tại, kích hoạt cơ chế retry. `recover()` không thay thế rollback trong một transacted Session.
- `consumerWindowSize=0` là tùy chọn **Core client Artemis** dùng để giảm buffering trước ở client, giúp quan sát lần giao lại dễ hiểu hơn; không phải cấu hình bắt buộc cho production.
- `JMSXDeliveryCount` và `JMSRedelivered` là dấu hiệu xác minh số lần giao. Code chỉ assert count trong **lab sạch, một consumer**; không dùng nó như điều kiện nghiệp vụ cho một cluster đang có failover.
- `System.nanoTime()` dùng để đo **khoảng thời gian**, tránh ảnh hưởng khi đồng hồ hệ thống thay đổi. Giá trị `deltaMs` gồm cả thời gian Java xử lý và broker scheduling, nên chỉ cần gần 1.000/2.000/3.000 ms.
- Đọc DLQ bằng `AUTO_ACKNOWLEDGE` sẽ **tiêu thụ bản ghi thử nghiệm**. Không chạy chương trình trên DLQ chung chứa dữ liệu sự cố thật; khi điều tra production, dùng browser/management read-only.

### 6.3. Kết quả mong đợi

```text
attempt=1 deliveryCount=1 redelivered=false deltaMs=-1
attempt=2 deliveryCount=2 redelivered=true  deltaMs≈1000
attempt=3 deliveryCount=3 redelivered=true  deltaMs≈2000
attempt=4 deliveryCount=4 redelivered=true  deltaMs≈3000
PASS: eventId=probe-... reached DLQ
```

Các giá trị trên là **minh họa mong đợi**, không phải output đã chạy trong môi trường hiện tại. Độ trễ thực không đúng tuyệt đối từng ms. Nếu nhận lần 5, đầu tiên phải kiểm tra cấu hình hiệu lực trên đúng **address** và có consumer khác, cơ chế redistribution, hoặc một cấu hình `max-delivery-attempts` khác đang được ưu tiên.

## 7. Thử thay đổi từng biến để hiểu tác dụng

| Phép thử | Thay đổi duy nhất | Quan sát hợp lý |
|---|---|---|
| A — baseline | `delay=1000`, `multiplier=2`, `cap=3000`, `attempts=4`, `jitter=0` | Các lần giao khoảng 1s, 2s, 3s; sau thất bại thứ tư → DLQ |
| B — không có delay | `redelivery-delay=0` | Các lần giao lại có thể tới gần như tức thì; dễ tạo retry thrashing |
| C — không tăng dần | `redelivery-delay-multiplier=1.0` | Khoảng chờ gần như 1s cho mỗi lần retry |
| D — trần nhỏ hơn | `max-redelivery-delay=1500` | Khoảng chờ dự kiến 1s, 1.5s, 1.5s |
| E — chống va chạm | `redelivery-collision-avoidance-factor=0.15` | Các khoảng chờ có jitter, không thể assert 1000/2000/3000 chính xác |
| F — không có giới hạn | `max-delivery-attempts=-1` | Không tự chuyển DLQ theo số lần; **cần dừng test thủ công** |
| G — thành công giữa chừng | Ở lần nhận thứ ba gọi `commit()` thay vì rollback | Message được ACK và không đi DLQ |

Đổi từng trường ở `address-setting` rồi **xác minh broker đã nạp cấu hình mới** (đọc log/management, reload hoặc restart theo bản triển khai) trước khi đo lại. Tạo **message ID mới cho mỗi kịch bản** hoặc làm sạch queue lab bằng quy trình được phép; không đem dữ liệu retry của case trước trộn vào case sau.

## 8. Giới hạn và tình huống vận hành cần lưu ý

### 8.1. Không mặc định thứ tự FIFO sẽ được giữ sau rollback

Artemis chỉ trì hoãn **message bị cancel**, còn những message khác có thể được giao trong khi nó đang đợi. Một consumer có thể xử lý `order-102` trước `order-101` khi `order-101` rollback. Với workflow yêu cầu thứ tự theo mã đơn hàng, cần thiết kế key/grouping hoặc giới hạn concurrency phù hợp; đơn thuần tăng delay không đảm bảo thứ tự nghiệp vụ.

### 8.2. Delivery count sau crash không luôn phản ánh từng lần đã phát

Mặc định, Artemis chỉ persist delivery count khi message được rollback, không ghi bền vững **trước mỗi lần** dispatch. Nếu broker crash sau dispatch nhưng trước rollback, lần nhận sau khởi động có thể không tăng count như mong đợi hoặc `JMSRedelivered` chưa phản ánh đúng một lần đã xảy ra. Muốn ưu tiên độ chính xác của flag/count khi crash, có thể cấu hình ở `<core>`:

```xml
<persist-delivery-count-before-delivery>true</persist-delivery-count-before-delivery>
```

Đổi lại broker phát sinh thêm thao tác ghi journal mỗi lần giao, ảnh hưởng throughput. Cần benchmark và đánh giá mục tiêu nghiệp vụ; **không** suy rằng tùy chọn này biến consumer thành exactly-once.

### 8.3. Khi có cluster, failover và nhiều consumer

Bài thực hành ở mục 6 cố ý có **một broker, một message, một consumer** để đo chính xác các tham số. Trong network of brokers/cluster, redistribution, failover hoặc nhiều consumer cùng nhận có thể làm khác thứ tự và thời điểm; hãy kiểm thử theo topology thực tế, đặc biệt nếu yêu cầu đếm retry nhất quán xuyên node. Không dùng bảng thời gian lab đơn node để cam kết SLO cho cluster mà không có số liệu.

### 8.4. Định lượng tải và chọn tham số có lý do

Giả sử mỗi lần retry gọi một API đang lỗi tốn 200 ms. Khi `delay=0`, một message có thể liên tục gây tải; 10.000 message cùng thất bại làm vấn đề trầm trọng. Delay có multiplier và cap giúp giảm tần suất retry, còn jitter phân tán đỉnh đồng thời.

Chọn giá trị theo **thời gian khôi phục dự kiến** của dependency và yêu cầu nghiệp vụ:

| Ràng buộc | Hướng chọn |
|---|---|
| Lỗi tạm vài trăm ms | Base delay 0.5–2s, multiplier vừa phải |
| DB/API có thể mất vài chục giây | Base lớn hơn, multiplier >1, cap theo thời gian phục hồi |
| Không thể giữ message độc trong queue quá lâu | Đặt `max-delivery-attempts` hữu hạn, quan sát DLQ và xử lý riêng |
| Nhiều consumer có lỗi cùng lúc | Bật collision avoidance factor vừa phải, đo tải |
| Yêu cầu thời gian xử lý tối đa | Tính tổng khoảng chờ + thời gian xử lý + lịch scheduler; thử dưới tải thực |

Các khoảng trên là **điểm khởi đầu cho benchmark**, không phải giá trị tối ưu chung. Nếu phụ thuộc bên ngoài **không thể** xử lý một payload (lỗi schema, dữ liệu vĩnh viễn), tăng số lần retry chỉ trì hoãn việc đưa vào DLQ; thay vào đó cần phân loại lỗi và quan sát message thất bại.

## 9. Checklist rà soát nhanh

Trước khi đưa policy vào một broker Artemis đáng tin cậy:

1. `match` khớp **address thực** mà Java producer gửi đến; broker đã nạp đúng `broker.xml`.
2. `redelivery-delay` tính bằng **ms** và lớn hơn 0 nếu muốn tránh retry ngay.
3. `redelivery-delay-multiplier` và `max-redelivery-delay` đã được chọn cùng nhau; không nhầm cap thời gian với số lần giao.
4. `max-delivery-attempts` có giá trị hữu hạn theo yêu cầu vận hành; hiểu rằng **lần giao đầu đã được tính**.
5. Có `dead-letter-address` hợp lệ với queue nhận message; nếu không có, message có thể bị **loại bỏ** sau khi hết lượt.
6. Test `rollback()` theo các lần 1–4 và so `JMSXDeliveryCount`, thời gian, DLQ; test thêm nhánh `commit()` ở lần giữa.
7. Với nhiều consumer, kiểm tra jitter, thứ tự message và khả năng retry đồng loạt; với broker crash/cluster, đánh giá độ chính xác delivery count.
8. Giám sát số message thất bại, tần suất redelivery, số message đang đợi/scheduled, tồn đọng DLQ, và thời gian chờ thực tế. Tách cảnh báo lỗi vĩnh viễn khỏi lỗi dependency tạm thời.

**Kết luận:** `redelivery-delay` đặt khoảng chờ đầu, `redelivery-delay-multiplier` làm khoảng chờ tăng dần, `max-redelivery-delay` chặn đà tăng, `redelivery-collision-avoidance-factor` tránh các đợt retry đồng loạt, còn `max-delivery-attempts` chấm dứt vòng lặp bằng cách chuyển sang DLQ khi đã đủ lần thất bại. Muốn cấu hình thực sự đáng tin cậy phải kiểm chứng **cả khoảng thời gian lẫn điểm dừng**, không chỉ thấy consumer nhận lại message.

## Tài liệu chính thức

1. [Apache Artemis 2.57.0 — Message Redelivery and Undelivered Messages](https://artemis.apache.org/components/artemis/documentation/latest/undelivered-messages.html): tính delay, multiplier, collision avoidance, ngưỡng DLQ và giới hạn persistence của delivery count.
2. [Apache Artemis — Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-settings.html): `address-setting`, `match`, policy theo address và tham số.
3. [Apache Artemis — Configuration Reference](https://artemis.apache.org/components/artemis/documentation/latest/configuration-index.html): giá trị default và thuộc tính `persist-delivery-count-before-delivery`.
4. [Apache Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): cấu hình `ANYCAST`, address và queue khác nhau thế nào.
5. [Apache Artemis — Consumer Flow Control](https://artemis.apache.org/components/artemis/documentation/latest/flow-control.html): `consumerWindowSize` và tác động của client-side prefetch.
