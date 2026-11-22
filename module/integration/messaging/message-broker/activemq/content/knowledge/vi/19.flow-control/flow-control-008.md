# Phát hiện consumer chậm, giới hạn tốc độ và bảo vệ hệ thống đích

## 1. Consumer chậm là triệu chứng; quá tải downstream mới có thể là nguyên nhân

Giả sử dịch vụ **Order Service** gửi **OrderPaid** tới queue **orders.paid**, còn consumer **Inventory Worker** cần gọi API giữ hàng trước khi ACK JMS. Trong giờ cao điểm, Order Service phát **120 message/giây**, trong khi API Inventory an toàn ở mức **60 request/giây**. Nếu worker cứ tăng concurrency và gọi API không giới hạn, hệ thống có thể xuất hiện **HTTP 429, timeout, cạn connection pool hoặc cascading failure**.

Cách xử lý đúng không phải luôn cố làm consumer chạy nhanh nhất. Cần **đo tốc độ, backlog, tuổi message**, rồi **giới hạn tốc độ và số tác vụ đang xử lý** theo năng lực thực của downstream. Backlog tăng có kiểm soát đôi khi an toàn hơn đẩy quá tải sang database hoặc API quan trọng.

~~~mermaid
flowchart LR
    P["Producer<br/>120 messages/s"] --> Q[("Artemis queue<br/>orders.paid")]
    Q --> C["JMS consumer<br/>bounded concurrency"]
    C --> L["Rate limiter<br/>global/per-instance"]
    L --> H["Inventory API<br/>60 requests/s"]
    H --> DB[("Inventory database")]
    H -->|2xx| A["Commit JMS<br/>sau khi xử lý an toàn"]
    H -->|429, 503, timeout| R["Rollback + retry có delay<br/>hoặc tạm ngừng nhận"]
    R --> Q
    Q --> M["Metrics<br/>backlog, age, in-flight"]
    H --> M
~~~

Bài thuộc chương **Điều tiết lưu lượng** trong module **INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ**. Trọng tâm là **phát hiện consumer chậm**, **giới hạn tốc độ xử lý**, và **bảo vệ hệ thống đích** khi tích hợp bằng JMS với **ActiveMQ Classic** hoặc **Artemis**. Các khái niệm ACK, DLQ và queue chỉ được nhắc ở những điểm trực tiếp ảnh hưởng đến flow control.

### Ba vòng điều tiết phải nhìn riêng

| Vòng điều tiết | Giới hạn cái gì? | Ví dụ |
| --- | --- | --- |
| Broker → consumer | Số byte/message đã dispatch nhưng chưa hoàn tất; prefetch/client buffer | Artemis consumerWindowSize, Classic queue prefetch |
| Consumer → downstream | Số request/giây, số request đồng thời và timeout | 20 requests/s mỗi instance, tối đa một HTTP request đang chạy |
| Producer → broker | Khả năng nhận thêm dữ liệu khi queue/backlog gây áp lực tài nguyên | Artemis address-full-policy, Classic producer flow control |

Giới hạn ở một vòng **không tự động bảo vệ hai vòng còn lại**. Chẳng hạn, giảm prefetch không bảo đảm Inventory API chỉ nhận 60 requests/s nếu có 20 consumer replica cùng chạy.

## 2. Nhận diện consumer chậm bằng tốc độ và tiến độ, không chỉ queue size

Ký hiệu trong một khoảng quan sát:

- **λ (lambda)**: tốc độ message **enqueue/routed vào queue** (message/s).
- **μ (mu)**: tốc độ message **ACK/hoàn tất** của nhóm consumer (message/s).
- **B**: số message đang chờ hoặc backlog cần xử lý theo định nghĩa metric.
- **I**: số message đã dispatch nhưng chưa ACK (**in-flight/delivering**).
- **W**: độ tuổi message cũ nhất chưa xử lý, hoặc **end-to-end lag**.
- **C**: số consumer đang kết nối.

Khi tốc độ gần ổn định và không có TTL, purge hoặc DLQ làm thay đổi số lượng:

\[
\Delta B \approx (\lambda - \mu) \times \Delta t
\]

Ví dụ **λ = 120 msg/s**, **μ = 60 msg/s**:

~~~text
Backlog tăng gần 60 message/s.
Sau 60 giây: tăng gần 3.600 message.
Sau 10 phút: tăng gần 36.000 message.
~~~

Một consumer nhận **20 msg/s** chưa chắc là chậm nếu queue chỉ có **5 msg/s**. Ngược lại, **100 msg/s** vẫn không đủ nếu lưu lượng vào **300 msg/s**. Chẩn đoán phải dựa trên **demand so với capacity**.

Nếu backlog là **36.000 message**, lưu lượng vào sau cao điểm hạ còn **40 msg/s** và consumer ổn định ở **100 msg/s**, tốc độ rút backlog ròng chỉ **60 msg/s**:

\[
T_{\text{drain}} \approx \frac{36000}{100 - 40}=600\text{ giây}
\]

Công thức chỉ là xấp xỉ: throughput, retry, TTL, message size và tải downstream thay đổi theo thời gian. Đặc biệt, khi **μ ≤ λ**, backlog **không thể tự cạn** nếu điều kiện giữ nguyên.

### Đừng nhầm các counter

| Tín hiệu | Dùng để kết luận | Điều chưa thể kết luận |
| --- | --- | --- |
| Queue message count/pending | Có bao nhiêu message chưa hoàn tất theo cách metric định nghĩa | Consumer có đang xử lý đúng nghiệp vụ hay không |
| Delivering/in-flight | Broker đã giao bao nhiêu message chưa ACK | Tất cả đã tới handler hoặc đang thực thi HTTP |
| Enqueue rate | Tốc độ producer tạo công việc | Tất cả công việc đều cần gọi downstream |
| ACK/dequeue rate | Tốc độ broker thấy message hoàn tất | Side effect thành công nếu consumer ACK sai thời điểm |
| Consumer count | Số consumer đang kết nối | Mỗi consumer có còn tiến triển hay không |
| Oldest message age | Độ trễ của phần tồn đọng lâu nhất | Mọi message đều có độ trễ bằng nhau |
| JMS redelivery count | Message bị giao lại theo policy | Downstream chắc chắn là nguồn lỗi |
| HTTP latency, 429/5xx, pool saturation | Downstream có dấu hiệu quá tải | Broker tự động có chính sách giảm tốc tương ứng |

Trên **Artemis**, lấy số liệu từ web console/management, JMX hoặc metrics exporter của broker: **message count, delivering count, consumer count, messages added, messages acknowledged, scheduled count, expired/DLQ** theo các trường thực tế mà phiên bản broker expose. Trên **ActiveMQ Classic**, các counter kiểu **QueueSize, InFlightCount, EnqueueCount, DequeueCount, ConsumerCount** qua JMX/web console có ý nghĩa gần tương ứng nhưng tên và phạm vi tính khác nhau. Không ghép trực tiếp hai bộ metric nếu chưa xác nhận định nghĩa.

### Dấu hiệu cảnh báo nên kết hợp

Một tín hiệu đáng tin hơn là:

~~~text
Queue có backlog đáng kể
AND oldest age liên tục tăng 5 phút
AND ACK rate thấp hơn enqueue rate trong cùng cửa sổ
AND consumer count > 0
~~~

Sau đó phân loại: **downstream chậm** (HTTP latency/429 tăng), **consumer bị treo** (in-flight ổn định rất cao, handler không tiến triển), **poison message** (redelivery cùng eventId lặp), hoặc **công suất đơn giản là nhỏ hơn nhu cầu**. Nếu queue không có message, tốc độ ACK thấp không phải dấu hiệu consumer chậm.

## 3. Phân biệt các loại nghẽn để không chữa sai bệnh

| Mẫu quan sát | Nguyên nhân hay gặp | Biện pháp nên ưu tiên |
| --- | --- | --- |
| Backlog tăng, HTTP 429 tăng | Đẩy tải vượt quota downstream | Giảm rate limit và concurrency, tôn trọng Retry-After nếu có |
| Backlog tăng, HTTP p99 tăng, connection pool cạn | Downstream chậm hoặc lock contention | Giảm in-flight, timeout, bulkhead, circuit breaker |
| Backlog tăng, consumer count = 0 | Không có consumer hoặc kết nối lỗi | Khôi phục consumer/credentials/deployment |
| Message đang delivering nhiều nhưng ACK gần 0 | Prefetch quá lớn hoặc handler bị kẹt | Giảm prefetch/window, xem thread dump và timeout |
| Đúng một eventId bị rollback liên tục | Poison message hoặc lỗi dữ liệu | Retry có giới hạn, DLQ/quarantine; không chỉ tăng replicas |
| Broker paging/disk tăng nhanh | Producer vượt khả năng tiêu thụ lâu dài | Capacity plan, address policy, producer admission control |
| CPU consumer 100%, downstream còn rảnh | Parse/serialization/computation là nút thắt | Profile, tối ưu code và tăng worker có kiểm soát |
| ACK rate ổn định theo quota và downstream khỏe | Rate limit đang bảo vệ thành công | Đánh giá backlog age và SLA trước khi tăng hạn mức |

**Slow consumer** là nhãn vận hành, không hẳn một bug. Consumer chủ động xử lý **10 msg/s** để tuân thủ quota downstream là **đúng thiết kế**; điều cần cảnh báo là backlog quá SLA, không phải đơn thuần tốc độ thấp.

### Tốc độ trung bình che giấu microburst

Một downstream chịu được **60 request/s trung bình** có thể vẫn sập nếu có burst 500 request trong vài mili giây. Vì vậy cần ít nhất hai điều khiển:

- **Rate limit**: tối đa số request theo thời gian, có burst size rõ.
- **Concurrency limit**: tối đa số tác vụ/request đồng thời.

Ví dụ API có p99 latency **400 ms** và quota **60 req/s**. Theo Little's Law, concurrent calls trung bình khoảng **60 × 0,4 = 24** ở mức p99 làm tham chiếu thận trọng, nhưng không được dùng p99 như mean chính xác. Nên đặt **bulkhead** dựa trên năng lực pool/DB, thử tải và headroom thực tế, chẳng hạn **tối đa 12 request đồng thời** khi hệ thống đích cần được bảo vệ chặt.

## 4. Artemis: cảnh báo slow consumer và giới hạn prefetch là hai việc khác nhau

Artemis có các tùy chọn **slow-consumer** trong **address-settings** để đánh giá tốc độ tiêu thụ và áp dụng policy như thông báo hoặc xử lý consumer theo hỗ trợ của phiên bản.

Ví dụ **broker.xml** trong phần **address-settings** đã tồn tại:

~~~xml
<address-setting match="orders.paid">
    <slow-consumer-threshold>10</slow-consumer-threshold>
    <slow-consumer-check-period>10</slow-consumer-check-period>
    <slow-consumer-policy>NOTIFY</slow-consumer-policy>
</address-setting>
~~~

Đây là **đoạn cấu hình**, không phải broker.xml hoàn chỉnh. Trong các bản Artemis hỗ trợ những thuộc tính này, **slow-consumer-threshold** biểu thị ngưỡng tốc độ tiêu thụ (message/s), **slow-consumer-check-period** là chu kỳ kiểm tra tính theo giây và **NOTIFY** tạo sự kiện/cảnh báo quản trị thay vì chủ động ngắt consumer. Hãy đối chiếu XML schema và mô tả chính xác của release đang chạy trước khi áp dụng.

**Ngưỡng 10 msg/s không thể được hiểu máy móc:** nếu chỉ có 2 msg/s đến queue, consumer hoàn toàn khỏe mạnh vẫn không thể ACK 10 msg/s. Vì thế cần kết hợp **backlog tồn tại, tuổi message và năng lực downstream**, không đặt alert chỉ từ một cấu hình ngưỡng.

Một số phiên bản hỗ trợ policy kiểu **KILL** để đóng consumer chậm. Đây là biện pháp mạnh: message chưa ACK có thể bị phát lại, load chuyển sang replica khác, tạo vòng lặp reconnect. **Bắt đầu bằng NOTIFY**, đo và khoanh vùng trước khi ngắt client tự động; KILL không tự tăng tốc downstream.

### Consumer window: giảm lượng message giữ sẵn ở client

Với Artemis JMS client, **consumerWindowSize** là giới hạn **theo byte** cho buffering/flow control phía consumer, **không phải requests/second**. Ví dụ:

~~~java
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

// Window bằng 0: hạn chế buffering/prefetch phía consumer,
// broker cấp message theo nhu cầu của consumer.
factory.setConsumerWindowSize(0);
~~~

Giảm window giúp hạn chế việc broker giao trước một lượng lớn message đang chờ trong client khi downstream chậm. Đổi lại, thông lượng và latency có thể giảm vì tăng số lần trao đổi broker–client. Đừng đặt **-1** (buffer không giới hạn theo provider) cho consumer không đủ memory hoặc downstream thường xuyên chậm.

**Window=0 không phải rate limiter.** Với mười consumer liên tục nhận/ACK nhanh, tổng requests/s vẫn có thể quá quota Inventory API. Cần giới hạn ở tầng application, được minh họa ở mục 7.

### Queue management không tự thực hiện business rate limiting

Các metric scheduled/delivering/ACK của Artemis hỗ trợ phát hiện backlog. Chúng không biết 429 của API Inventory có phải là lỗi tạm thời, hoặc có nên dừng nhận từ queue hay không. Chính ứng dụng cần **classify HTTP result**, **throttle**, quản lý **transaction JMS** và **circuit breaker** khi downstream suy giảm.

## 5. Classic: prefetch theo message và slow-consumer strategy

**ActiveMQ Classic** dùng cơ chế prefetch khác Artemis. Với Classic JMS client 5.x, có thể giảm **queuePrefetch** (đơn vị **số message**, không phải byte):

~~~java
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.ActiveMQPrefetchPolicy;

ActiveMQConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");
ActiveMQPrefetchPolicy prefetch = factory.getPrefetchPolicy();
prefetch.setQueuePrefetch(1);
~~~

Giá trị **1** làm giảm số message chưa xử lý bị giữ phía client, hữu ích khi xử lý chậm và cần phân phối công bằng giữa worker, nhưng có thể giảm throughput vì giao nhận nhiều round trip. Đo trước và sau thay đổi; không dùng default prefetch lớn với consumer kéo dài nhiều giây mà không đánh giá mức in-flight.

Classic còn có **slow consumer strategy** ở destination policy (ví dụ **AbortSlowConsumerStrategy** trong các release hỗ trợ). Cần cấu hình và thử riêng trên broker Classic; đây **không phải** cặp XML **slow-consumer-threshold/slow-consumer-policy** của Artemis. Một chiến lược tự hủy consumer có thể gây redelivery và churn, vì vậy chỉ bật có kiểm soát sau khi có biểu đồ tiến độ, nguyên nhân và rollback plan.

**Producer flow control** của Classic là một chủ đề khác: nó có thể chặn producer khi broker hết khả năng cấp tài nguyên. Không đánh đồng việc broker hạn chế producer với cơ chế giới hạn HTTP requests/s của consumer.

### Bảng chọn tham số không nhầm hai broker

| Mục đích | Artemis | Classic |
| --- | --- | --- |
| Giảm message buffer phía consumer | **consumerWindowSize**, thường tính bằng byte | **queuePrefetch**, tính theo số message |
| Phát hiện consumer chậm | **slow-consumer-\*** trên address-settings khi release hỗ trợ | Slow consumer strategy/destination policy |
| Bảo vệ tốc độ API/DB | **Ứng dụng rate limiter + bounded concurrency** | **Ứng dụng rate limiter + bounded concurrency** |
| Áp lực producer khi address đầy | **max-size-bytes/address-full-policy** | **producerFlowControl/systemUsage** |
| Nhận diện message xử lý lỗi | Redelivery/DLQ theo broker policy | RedeliveryPolicy/Dead Letter Strategy |
| Đánh giá sức khỏe | Queue/consumer/delivering/ACK + downstream metrics | JMX queue/in-flight/enqueue/dequeue + downstream metrics |

Không lấy cấu hình một broker áp vào broker còn lại. Consumer cần chọn đúng Artemis Jakarta client hoặc Classic javax client theo phiên bản và namespace đang sử dụng.


## 6. Thiết kế rate limiter theo quota thật của downstream

Một hạn mức **60 HTTP requests/giây** không tự áp dụng cho các consumer JMS. Ứng dụng phải chủ động phân chia ngân sách.

Nếu có **6 replica** Inventory Worker và muốn giữ **20% headroom** cho lưu lượng khác:

~~~text
Downstream quota = 60 request/s
Budget cho JMS workers = 60 × 0,8 = 48 request/s
6 replicas × 8 request/s = 48 request/s
~~~

Đây là **giới hạn sơ bộ theo trung bình**. Khi replica autoscale từ 6 lên 10, giới hạn cục bộ **8 req/s/replica** sẽ cho **80 req/s**, vượt quota. Vì vậy phải biết hệ thống cần **quota cục bộ** hay **quota toàn cụm**.

| Mô hình giới hạn | Cách triển khai | Khi nào phù hợp | Rủi ro |
| --- | --- | --- | --- |
| Per-instance fixed rate | Pacer, token bucket trong từng JVM | Số replica cố định, quota đủ lớn | Autoscaling làm tổng rate tăng |
| Per-instance quota động | Controller phân chia quota theo số replica đang khỏe | Cluster có autoscaling và config động | Thay đổi replica không đồng bộ có thể quá quota tạm thời |
| Cluster-global token bucket | Redis/gateway/service chung cấp permit | API đích có quota toàn cụm cứng | Rate-limiter store có thể thành nút thắt |
| Downstream admission control | API đích trả **429/503**, công bố Retry-After | Cần tầng bảo vệ cuối cùng | Consumer vẫn phải phản ứng bằng backoff; 429 không phải thành công |

**Không dùng JMSPriority, prefetch hay address-full-policy thay thế rate limit HTTP**. Chúng kiểm soát các giai đoạn khác của pipeline.

### Rate limit khác concurrency limit

- **Rate limit**: tối đa số lời gọi **bắt đầu** trên một khoảng thời gian.
- **Concurrency limit**: tối đa số lời gọi **đang in-flight** tại một thời điểm.
- **Timeout**: thời gian tối đa chấp nhận chờ cho một HTTP/DB operation.
- **Circuit breaker**: tạm dừng gọi API khi tỷ lệ lỗi/latency vượt ngưỡng trong một cửa sổ.
- **Retry budget**: khống chế số lần thử lại và chi phí retry, tránh retry storm.

Một client có rate limit **20 req/s** nhưng request timeout tới **120 giây** có thể tích lũy hàng trăm request in-flight nếu không giới hạn concurrency. Ngược lại, chỉ giới hạn concurrency 5 mà mỗi HTTP call chạy 20 ms có thể tạo **250 req/s**, vẫn vượt quota.

### Đặt permit trước khi nhận message nếu có thể

Với JMS consumer synchronous:

~~~text
chờ permit + capacity
    ↓
receive message
    ↓
gọi downstream với timeout và idempotency key
    ↓
DB/API xác nhận thành công
    ↓
commit JMS (ACK)
~~~

Ưu tiên **chờ permit trước receive()** thay vì receive rồi giữ message chưa ACK trong JVM rất lâu. Tuy nhiên, Artemis có client-side buffering theo **consumerWindowSize** và Classic có prefetch; ngay cả khi chưa gọi receive, một số message có thể đã được cấp đến client. Giảm window/prefetch giúp thu hẹp phần in-flight ngoài ý muốn.

Với **MessageListener bất đồng bộ**, broker có thể dispatch theo prefetch trong khi ứng dụng vẫn chờ slot. Không dùng callback để tạo một **ExecutorService queue không giới hạn**; phải dùng **bounded executor/semaphore** và cơ chế dừng intake trước khi bộ nhớ bị đầy.

## 7. Java/JMS Artemis: bảo vệ HTTP API bằng pacer, timeout và transaction

Bài thực hành sử dụng **Jakarta Messaging** với Artemis. Mỗi instance chạy **một consumer synchronous** nên chỉ có **một HTTP request in-flight**. Một pacer giới hạn **8 request bắt đầu/giây** trong instance; nếu có 6 replica, tổng ngân sách lý thuyết khoảng **48 request/s** trước retry và các hệ thống gọi API khác.

Consumer nhận từ queue **orders.paid**, lấy **eventId** và **TextMessage body**, gửi HTTP POST đến Inventory API với header **Idempotency-Key**, rồi **commit JMS chỉ sau khi API xác nhận 2xx**. Với 429/5xx/timeout, consumer rollback để broker redeliver theo policy, đồng thời chờ cooldown ngắn trước khi tiếp tục.

### 7.1. Chuẩn bị cấu hình

- Broker Artemis có **queue ANYCAST orders.paid** đã tạo và user có quyền consume, hoặc auto-create được phép ở môi trường lab.
- Inventory API tại **INVENTORY_URL**, nhận POST JSON và **có hợp đồng idempotency theo Idempotency-Key**. API phải trả 2xx **chỉ khi thao tác đã xử lý bền vững** hoặc trùng ID đã hoàn tất.
- JDK 17+, Maven, dependency Artemis Jakarta client phù hợp broker. Ví dụ tham chiếu **2.42.0**, cần pin theo phiên bản triển khai thật.
- Thử trên broker/endpoint lab, không nhắm vào API production vì thí nghiệm có cố ý tạo timeout và rollback.

POM tối giản:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab.messaging</groupId>
    <artifactId>artemis-guarded-consumer</artifactId>
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

### 7.2. Chương trình GuardedInventoryConsumer.java

~~~java
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSRuntimeException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

public final class GuardedInventoryConsumer {
    private static final int MAX_REQUESTS_PER_SECOND = 8;

    public static void main(String[] args) throws Exception {
        String brokerUrl = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String brokerUser = Objects.requireNonNull(
                System.getenv("BROKER_USER"), "Missing BROKER_USER");
        String brokerPassword = Objects.requireNonNull(
                System.getenv("BROKER_PASSWORD"),
                "Missing BROKER_PASSWORD");
        URI inventoryUrl = URI.create(Objects.requireNonNull(
                System.getenv("INVENTORY_URL"), "Missing INVENTORY_URL"));

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(brokerUrl);

        // Giảm message được buffer trước ở client khi downstream chậm.
        factory.setConsumerWindowSize(0);

        HttpClient http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();
        Pacer pacer = new Pacer(MAX_REQUESTS_PER_SECOND);

        try (JMSContext jms = factory.createContext(
                brokerUser, brokerPassword,
                JMSContext.SESSION_TRANSACTED)) {

            JMSConsumer consumer =
                    jms.createConsumer(jms.createQueue("orders.paid"));

            while (!Thread.currentThread().isInterrupted()) {
                // Chờ slot TRƯỚC receive: không giữ nhiều message unacked.
                pacer.awaitSlot();

                Message message;
                try {
                    message = consumer.receive(1000L);
                } catch (JMSRuntimeException connectionFailure) {
                    System.err.println("JMS receive failed; reconnect: "
                            + connectionFailure.getMessage());
                    break;
                }

                if (message == null) {
                    continue;
                }

                try {
                    if (!(message instanceof TextMessage)) {
                        throw new IllegalArgumentException(
                                "Expected TextMessage");
                    }

                    String eventId = message.getStringProperty("eventId");
                    if (eventId == null || eventId.isBlank()) {
                        throw new IllegalArgumentException(
                                "Missing eventId");
                    }
                    String json = ((TextMessage) message).getText();

                    HttpRequest request = HttpRequest.newBuilder(inventoryUrl)
                            .timeout(Duration.ofSeconds(5))
                            .header("Content-Type", "application/json")
                            .header("Idempotency-Key", eventId)
                            .POST(HttpRequest.BodyPublishers.ofString(json))
                            .build();

                    HttpResponse<Void> response = http.send(
                            request, HttpResponse.BodyHandlers.discarding());

                    int code = response.statusCode();
                    if (code >= 200 && code < 300) {
                        // API contract: 2xx nghĩa là side effect bền vững.
                        jms.commit();
                        System.out.println("ACK eventId=" + eventId);
                    } else {
                        System.err.println("Downstream HTTP " + code
                                + " eventId=" + eventId);
                        jms.rollback();  // Không ACK lỗi như thành công.

                        // Cooldown trước nhận message khác.
                        // Retry-After cần được parse/thực thi theo contract.
                        TimeUnit.MILLISECONDS.sleep(
                                code == 429 ? 2_000L : 1_000L);
                    }
                } catch (JMSRuntimeException jmsFailure) {
                    // Kể cả lỗi lúc JMS commit: ACK outcome có thể UNKNOWN.
                    System.err.println("JMS transaction uncertain: "
                            + jmsFailure.getMessage());
                    break; // Đóng context; tạo session mới ở tầng supervisor.
                } catch (IOException downstreamFailure) {
                    System.err.println("HTTP I/O: "
                            + downstreamFailure.getMessage());
                    try {
                        jms.rollback();
                    } catch (JMSRuntimeException rollbackFailure) {
                        break;
                    }
                    TimeUnit.MILLISECONDS.sleep(1_000L);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    try {
                        jms.rollback();
                    } catch (JMSRuntimeException ignored) {
                        // Phiên lỗi sẽ đóng, message có thể được phát lại.
                    }
                    break;
                } catch (Exception invalidMessage) {
                    // Payload hoặc property không hợp lệ: không ACK lặng lẽ.
                    System.err.println("Invalid message: "
                            + invalidMessage.getMessage());
                    try {
                        jms.rollback();
                    } catch (JMSRuntimeException rollbackFailure) {
                        break;
                    }
                    TimeUnit.MILLISECONDS.sleep(1_000L);
                    // Cần max-delivery-attempts + DLQ cho lỗi vĩnh viễn.
                }
            }
        }
    }

    // Pacer không cho burst trong một JVM, tính bằng đồng hồ monotonic.
    // Không phải limiter dùng chung giữa các replica.
    private static final class Pacer {
        private final long intervalNanos;
        private long nextNanos = System.nanoTime();

        Pacer(int requestsPerSecond) {
            if (requestsPerSecond <= 0) {
                throw new IllegalArgumentException("requestsPerSecond");
            }
            intervalNanos =
                    1_000_000_000L / requestsPerSecond;
        }

        void awaitSlot() throws InterruptedException {
            long now = System.nanoTime();
            long waitNanos = nextNanos - now;
            if (waitNanos > 0) {
                TimeUnit.NANOSECONDS.sleep(waitNanos);
            }
            nextNanos = Math.max(System.nanoTime(), nextNanos)
                    + intervalNanos;
        }
    }
}
~~~

**Phạm vi của ví dụ:**

- Một JVM chỉ có **một consumer synchronous**, nên **HTTP concurrency tối đa 1** trong JVM. Với nhiều JVM, tổng concurrency bằng tổng số consumer đang gọi API.
- **Pacer** có tốc độ tối đa gần **8 lần bắt đầu/giây mỗi instance**, không có bucket burst. Tốc độ thực có thể thấp hơn khi HTTP chậm. Nó không bảo đảm quota toàn cụm.
- **consumerWindowSize=0** chỉ hạn chế việc broker cấp trước message; không giới hạn HTTP requests/s.
- API phải xử lý **Idempotency-Key** ổn định. Nếu API xử lý xong nhưng phản hồi HTTP bị mất, consumer sẽ rollback và message có thể được giao lại; API cần trả kết quả idempotent thay vì thực hiện lần hai.
- JMS commit lỗi có thể có **outcome UNKNOWN**, nên không thể khẳng định rollback. Phiên JMS cần được tạo lại và eventId phải giúp xử lý an toàn khi message được redeliver.
- **HTTP 4xx** do payload sai cần cơ chế **quarantine hoặc bounded retry/DLQ**, không được rollback nóng vô hạn. Demo rollback rồi chờ để tránh ACK sai, còn chính sách DLQ nằm ở broker.
- Khi downstream trả **429** với **Retry-After**, production phải parse theo semantics hợp đồng (có thể là delay seconds hoặc HTTP date) và điều chỉnh tốc độ/cooldown, không hardcode mãi hai giây.
- HTTP 2xx chỉ được xem là hoàn tất nếu **hợp đồng downstream thực sự bảo đảm side effect đã bền vững**. Với API trả **202 Accepted** cho công việc còn xử lý bất đồng bộ, cần callback/tracking hoặc outbox riêng; không tự suy 202 là kết quả cuối cùng.
- Đoạn code **không** triển khai distributed limiter, dynamic rate adjustment, circuit breaker hoặc graceful drain toàn cụm. Chúng là bước vận hành tiếp theo, không thể thay bằng một vòng while đơn lẻ.

### 7.3. Chạy trong môi trường thử nghiệm

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61617"
$env:BROKER_USER = "artemis_app"
$env:BROKER_PASSWORD = "<your-artemis-password>"
$env:INVENTORY_URL = "http://127.0.0.1:8088/reservations"

mvn -q compile exec:java "-Dexec.mainClass=GuardedInventoryConsumer"
~~~

**INVENTORY_URL phải là API lab do người học kiểm soát**; URL ví dụ không có nghĩa một service đã sẵn có ở cổng 8088. Nếu Artemis publish ở 61616 hoặc Java chạy trong cùng Docker network, chỉnh BROKER_URL tương ứng. Mật khẩu chỉ là placeholder, không đưa secret thực vào repository hoặc log. Docker Compose .env không tự được nạp vào PowerShell của Maven.

### 7.4. Thí nghiệm HTTP chậm và 429

Thiết lập API lab theo ba chế độ, có thể dùng một mock server của nhóm:

| Chế độ mock API | Hành vi | Kết quả JMS/HTTP cần quan sát |
| --- | --- | --- |
| Healthy | Trả 200 sau khoảng 50 ms | Message được commit, API requests/s không vượt rate cấu hình một instance |
| Slow | Trả 200 sau 600–900 ms | HTTP in-flight của JVM vẫn bằng 1; ACK rate giảm, backlog/age có thể tăng |
| Overloaded | Trả 429 khi quá quota, có Retry-After | Consumer rollback, không ACK sai; redelivery theo broker, áp dụng cooldown |
| Transient failure | Trả 503 vài lần rồi 200 | Không mất event; message có thể giao lại, xử lý thành công sau phục hồi |
| Accepted async | Trả 202 nhưng chưa áp dụng nghiệp vụ | Bắt buộc xác định lại hợp đồng xử lý; không mặc định dùng code trên để ACK |

Nếu mock API không có idempotency, **không** chạy thử với dữ liệu gây side effect thật: trường hợp mất phản hồi HTTP có thể khiến nó áp dụng hai lần khi JMS redeliver.


## 8. Khi downstream quá tải: cooldown, backoff và circuit breaker

**HTTP 429 Too Many Requests** là tín hiệu downstream không muốn nhận tải hiện tại. **503 Service Unavailable**, timeout hoặc connection-pool exhaustion có thể cho thấy năng lực xử lý giảm. Consumer cần giảm **số yêu cầu mới** thay vì chỉ retry message nhanh hơn.

~~~mermaid
stateDiagram-v2
    [*] --> NORMAL
    NORMAL --> THROTTLED: HTTP 429 hoặc latency tăng
    THROTTLED --> NORMAL: ổn định trở lại
    NORMAL --> OPEN: quá nhiều 5xx/timeout
    THROTTLED --> OPEN: downstream tiếp tục lỗi
    OPEN --> HALF_OPEN: hết cooldown
    HALF_OPEN --> NORMAL: probe thành công
    HALF_OPEN --> OPEN: probe thất bại
~~~

- **NORMAL:** có permit và slot rồi mới receive; commit JMS sau downstream success.
- **THROTTLED:** giảm rate, chờ Retry-After/cooldown có jitter, không mở thêm concurrency. Message vừa nhận nhưng bị 429 thì rollback, để broker retry có delay.
- **OPEN:** ngừng lấy **công việc mới** từ queue trong một khoảng, không gọi API liên tục và không giữ vô hạn message chưa ACK trong RAM.
- **HALF_OPEN:** chỉ cho phép ít request thăm dò, timeout ngắn, tăng quota từ từ nếu ổn định.

Một thuật toán điều chỉnh kiểu **AIMD** có thể minh họa:

~~~text
Initial global rate = 40 requests/s
Nếu 429 vượt ngưỡng:
    rate = max(5, floor(rate * 0.5))
    cooldown = Retry-After + jitter
Nếu 60 giây không bị 429 và p95 ổn định:
    rate = min(target, rate + 2 requests/s)
Nếu 5xx/timeout liên tục:
    circuit OPEN, ngừng receive mới
~~~

Các con số trên chỉ là ví dụ. Khi API có quota **toàn cụm**, nhiều replica phải chia sẻ một rate limiter/controller; mỗi replica tự tăng rate không đồng nghĩa tổng rate an toàn.

### Retry-After, ACK và side effect trùng

Header HTTP **Retry-After** có thể là **số giây** hoặc **HTTP-date**, không luôn là một integer. Production client cần parse đúng và giới hạn thời gian chờ hợp lý. Nếu Artemis đã đặt **redelivery-delay**, không cộng thêm nhiều delay tùy ý khiến backlog vượt SLA.

**Không ACK khi gặp 429/503 để làm queue trống.** Nếu downstream chưa xử lý, ACK làm mất công việc. Nếu API đã xử lý xong nhưng response HTTP thất lạc, JMS có thể rollback và message được giao lại: lúc đó downstream phải deduplicate bằng **Idempotency-Key** ổn định. Tránh replay side effect chỉ vì consumer thấy JMSRedelivered=true.

## 9. Artemis: redelivery backoff và DLQ tránh vòng lặp nóng

Cấu hình minh họa ở **address-settings** của broker.xml cho queue lab **orders.paid**. Các thuộc tính phải được **gộp vào cùng một address-setting hiện hữu** phù hợp; không tạo hai block trùng match rồi mong chắc biết block nào có hiệu lực.

~~~xml
<address-setting match="orders.paid">
    <slow-consumer-threshold>10</slow-consumer-threshold>
    <slow-consumer-check-period>10</slow-consumer-check-period>
    <slow-consumer-policy>NOTIFY</slow-consumer-policy>
    <redelivery-delay>2000</redelivery-delay>
    <redelivery-multiplier>2.0</redelivery-multiplier>
    <max-redelivery-delay>30000</max-redelivery-delay>
    <max-delivery-attempts>5</max-delivery-attempts>
    <dead-letter-address>DLQ</dead-letter-address>
</address-setting>
~~~

- **redelivery-delay**: delay ban đầu khi cần giao lại, tránh retry ngay.
- **redelivery-multiplier** và **max-redelivery-delay**: tăng dần và giới hạn backoff.
- **max-delivery-attempts**: giới hạn giao lại đối với poison message.
- **dead-letter-address**: nơi broker chuyển message đã vượt ngưỡng theo policy; cần có DLQ address/queue và quyền phù hợp.
- **slow-consumer-policy=NOTIFY**: thông báo tình trạng chậm, **không** throttle HTTP.

Đây là đoạn XML minh họa; xác minh schema và khả năng của phiên bản Artemis đang dùng. Đừng thay đổi cấu hình production trước khi kiểm tra ảnh hưởng đến queue khác và DLQ đang tồn tại.

### Lỗi vĩnh viễn khác sự cố 429 hàng loạt

Một message không có **eventId** hoặc payload hỏng có thể sẽ thất bại ở mọi lần thử. Dùng **DLQ/quarantine, phân loại lỗi và cảnh báo theo eventId**. Ngược lại, nếu downstream ngừng hoạt động 30 phút và hàng nghìn message hợp lệ đều bị 503, để tất cả tiêu hao hết **max-delivery-attempts** rồi rơi vào DLQ có thể không phù hợp. Nên **mở circuit và ngừng intake**, giữ backlog durable chờ downstream hồi phục.

**Redelivery-delay không phải global rate limit.** Nếu một nghìn message khác nhau được dispatch và rollback, trì hoãn từng message hai giây chưa bảo đảm tổng requests/s nằm dưới quota. Rate limiting phải áp dụng **trước khi gọi downstream**, tốt nhất trước receive hoặc trước khi chấp nhận thêm message in-flight.


## 10. Khi queue tăng nhanh: backpressure ở broker và producer

Nếu consumer bị giới hạn tốc độ nhưng producer không giảm lưu lượng, broker phải chứa backlog. Artemis có **address-full-policy** để chọn cách xử lý áp lực tài nguyên.

Ví dụ đoạn XML tại **address-settings** của queue lab:

~~~xml
<address-setting match="orders.paid">
    <max-size-bytes>268435456</max-size-bytes>
    <address-full-policy>BLOCK</address-full-policy>
</address-setting>
~~~

**Đây là đoạn minh họa thay thế về policy tài nguyên**, không phải block thứ hai để chèn thêm cùng match với cấu hình redelivery ở mục 9. Khi triển khai, **gộp các thuộc tính vào một address-setting hợp lệ**, kiểm tra inheritance và xác minh trong console/JMX của broker. **max-size-bytes** liên quan ngưỡng tài nguyên/address cho flow control, **không phải quota disk tuyệt đối** cho tổng backlog persistent.

Các lựa chọn phổ biến:

| Policy | Hành vi khi vượt ngưỡng phù hợp | Đánh đổi |
| --- | --- | --- |
| **PAGE** | Dùng paging để giảm áp lực bộ nhớ/address | Disk có thể tăng rất nhanh, throughput/latency chịu I/O |
| **BLOCK** | Tạo backpressure bằng cách chặn/hoãn producer | Request upstream có thể bị treo nếu không có timeout và admission control |
| **FAIL** | Từ chối send khi không còn capacity theo policy | Producer phải có outbox/retry và thông báo lỗi rõ |
| **DROP** | Bỏ message tùy policy | Chỉ cho dữ liệu mất được; **không dùng cho OrderPaid** |

**PAGE không chữa consumer chậm**, nó chuyển cách lưu phần backlog. Theo dõi disk usage, paging rate, journal và thời gian drain; nếu disk cũng đầy, broker vẫn có thể không hoạt động bình thường. **BLOCK** bảo vệ broker nhưng chuyển áp lực lên producer; cần producer timeout, thread pool giới hạn và thiết kế không tạo deadlock khi producer và consumer giữ cùng resource.

### Tốc độ phát kéo dài cao hơn công suất sẽ không bền vững

Ví dụ quota Inventory API **60 req/s**, sáu worker được giới hạn ở **8 req/s mỗi replica** để chừa 20% headroom. Tổng throughput mục tiêu **48 req/s** khi downstream và consumer khỏe.

Nếu upstream phát **120 msg/s** liên tục trong 10 phút:

\[
B_{\text{tăng}} \approx (120-48)\times600 = 43\,200\text{ messages}
\]

Sau cao điểm, upstream giảm xuống **30 msg/s**, consumer vẫn duy trì **48 msg/s** thì tốc độ rút backlog ròng **18 msg/s**:

\[
T_{\text{drain}} \approx 43\,200/(48-30) = 2\,400\text{ giây} = 40\text{ phút}
\]

Nếu input vẫn cao hơn capacity, không có số lượng replica vô hạn, paging hay DLQ nào tự làm hết backlog mà vẫn bảo toàn toàn bộ công việc. Các lựa chọn thật là **nâng capacity downstream**, **áp quota/admission cho nguồn phát**, hoặc **đổi SLA/loại bỏ dữ liệu theo chính sách nghiệp vụ được phê duyệt**.

### Classic: producer flow control cùng mục đích, cấu hình khác

ActiveMQ Classic có **producerFlowControl** và các giới hạn tài nguyên **systemUsage**. Khi cấu hình destination policy, một producer có thể bị chặn nếu broker không còn capacity được phép. Cần kiểm thử giới hạn memory/store/temp và thời gian chờ producer. Không lấy XML **address-full-policy** của Artemis sang Classic.

## 11. Runbook: điều tra slow consumer không làm downstream sập thêm

Khi queue age hoặc tốc độ ACK phát cảnh báo, thực hiện theo thứ tự:

1. **Xác nhận đúng queue và broker**: consumer đang đọc destination nào, endpoint nào, có nhầm Artemis với Classic hoặc đọc nhầm tenant không?
2. **So cửa sổ đo**: enqueue rate, ACK rate, backlog/oldest age, delivering/in-flight, consumer count, HTTP p95/p99 và 429/503.
3. **Phân loại nguyên nhân**: consumer offline, handler treo, poison message, downstream hết quota, CPU consumer cạn hay upstream tăng đột biến.
4. **Bảo vệ downstream trước**: giảm rate và concurrency, áp timeout, mở circuit nếu cần; tránh restart hàng loạt khiến message đồng loạt redeliver.
5. **Bảo đảm dữ liệu không mất**: kiểm tra transaction/ACK sau side effect, idempotency, DLQ/expiry và outbox producer.
6. **Bảo vệ broker/upstream**: theo dõi paging/disk, cấu hình BLOCK/FAIL/PAGE phù hợp, áp admission control hoặc thông báo chế độ degradated cho upstream.
7. **Khôi phục có kiểm soát**: tăng rate từng nấc, chỉ scale replica nếu downstream có headroom hoặc có limiter global thực sự.
8. **Đóng incident** khi queue age trở lại SLA, 429/5xx giảm, in-flight ổn định và DLQ không tiếp tục tăng bất thường.

### Hai vòng phản hồi xấu cần tránh

**Retry storm:** consumer rollback ngay sau 429, broker giao lại ngay, downstream lại 429. Dùng cooldown/circuit breaker và redelivery backoff có kiểm soát.

**Autoscaling storm:** autoscaler nhìn backlog tăng rồi nhân bản worker trong lúc Inventory API đã bão hòa, dẫn đến HTTP latency tăng, ACK rate giảm và backlog càng lớn. Scale dựa trên **backlog + downstream headroom + quota phân phối**, không chỉ queue depth.

### Alert mẫu

| Cảnh báo | Ngưỡng minh họa | Điều cần kiểm tra |
| --- | --- | --- |
| Oldest message age tăng | Trên 60 giây liên tục 5 phút | SLO xử lý có nguy cơ vi phạm |
| In-flight không giảm | ACK rate gần 0 trong 2 phút | Handler treo, timeouts, prefetch |
| HTTP 429 | Trên 1% requests trong 3 phút | Limiter quá cao hoặc quota giảm |
| HTTP p99 latency | Trên 2 giây trong 5 phút | Downstream bão hòa |
| DLQ growth | Tăng liên tục theo eventType | Poison message, policy quá gắt |
| Paging/disk pressure | Gần mức dự phòng của broker | Cần giảm nguồn phát hoặc nâng lưu trữ |

**Đây là ngưỡng minh họa, không phải mặc định production.** Phải điều chỉnh theo SLO, message size, topology, service capacity, retry pattern và đặc tính tải. Đừng cảnh báo consumer là “slow” chỉ vì tốc độ ACK thấp hơn ngưỡng cố định khi queue thực tế không có công việc.


## 12. Tái hiện slow consumer bằng tải thử có kiểm soát

Để kiểm tra rate limit, tạo **100 message** với **eventId riêng** vào queue lab. Mock Inventory API phản hồi 200 sau 50 ms và ghi nhận request time; sau đó đổi mock sang chế độ chậm/429. Bài test phải dùng **tài khoản và endpoint riêng**, không gửi vào queue hoặc Inventory API production.

### 12.1. Producer tạo 100 message

Với cùng dependency Artemis Jakarta client trong mục 7, tạo **src/main/java/QueueLoadProducer.java**:

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.Objects;
import java.util.UUID;

public final class QueueLoadProducer {
    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = Objects.requireNonNull(
                System.getenv("BROKER_USER"), "Missing BROKER_USER");
        String password = Objects.requireNonNull(
                System.getenv("BROKER_PASSWORD"),
                "Missing BROKER_PASSWORD");

        String runId = UUID.randomUUID().toString();
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);

        try (JMSContext jms = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = jms.createQueue("orders.paid");

            for (int i = 1; i <= 100; i++) {
                String id = runId + "-" + i;
                String payload = "{\"eventId\":\"" + id
                        + "\",\"orderId\":\"ORD-" + i + "\"}";
                TextMessage message = jms.createTextMessage(payload);
                message.setStringProperty("eventId", id);
                message.setStringProperty("eventType", "OrderPaid");

                jms.createProducer()
                        .setDeliveryMode(DeliveryMode.PERSISTENT)
                        .send(queue, message);
            }
            jms.commit();
        }

        System.out.println("Enqueued 100 events; runId=" + runId);
    }
}
~~~

Chạy producer trong project Maven demo:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61617"
$env:BROKER_USER = "artemis_app"
$env:BROKER_PASSWORD = "<your-artemis-password>"

mvn -q compile exec:java "-Dexec.mainClass=QueueLoadProducer"
~~~

Mỗi message có **eventId ổn định trong một lần thử**; nếu cần retry sau commit outcome UNKNOWN, phải lấy lại các eventId của lượt cũ từ nguồn lưu bền vững thay vì tự tạo runId mới. Đoạn producer này chỉ phục vụ tải lab, **không** triển khai outbox.

### 12.2. Kịch bản kiểm thử có thể quan sát được

| Kịch bản | Cách làm | Điều cần xác minh |
| --- | --- | --- |
| A. Target khỏe | Mock API 200/50ms, consumer 8 req/s | Trong một instance, số request bắt đầu theo giây không vượt limiter có chủ đích; queue giảm dần |
| B. Target chậm | Mock 200 sau 700ms | HTTP in-flight ≤ 1; consumer ACK rate giảm, backlog/age có thể tăng |
| C. Target từ chối | Mock trả 429 cùng Retry-After | Không ACK nhầm; rollback/cooldown, message còn khả năng redeliver |
| D. Target lỗi tạm | Mock 503 vài lần rồi 200 | Message được xử lý sau phục hồi, downstream idempotency giữ side effect một lần |
| E. Target không phản hồi | Mock giữ kết nối lâu hơn timeout 5s | HTTP call timeout, JMS rollback, worker không treo vô hạn |
| F. Payload lỗi | Gửi message thiếu eventId | Bounded retry/DLQ hoặc quarantine; không vòng lặp nóng |
| G. Nhiều replica | Chạy 3/6/10 instance cùng queue lab | So tổng RPS và phân biệt per-instance với global quota |

Khi mock cố tình chậm hoặc trả 429, **một consumer tốt có thể khiến backlog tăng**. Tiêu chí PASS không chỉ là “queue về 0”, mà là **downstream không bị vượt capacity**, message còn được lưu an toàn, retry không bùng nổ, và backlog phục hồi đúng SLO khi downstream khỏe lại.

Lấy ảnh chụp metric theo **cùng cửa sổ thời gian**: messages added/ACK, pending/delivering, oldest age, HTTP requests/s, p95/p99, số 429/503 và idempotency-hit count. Đừng so một counter tích lũy của broker với một RPS đo trong một giây rồi kết luận sai.

### 12.3. Trường hợp không nên chạy tự động

Nếu API Inventory **không hỗ trợ Idempotency-Key**, một HTTP timeout sau khi server đã commit có thể khiến lần redelivery thực hiện side effect lần hai. Trước khi kiểm thử mất mạng với dữ liệu thật, thêm unique constraint/idempotency trong service đích hoặc dùng mock không thay đổi dữ liệu.

Nếu cần kiểm tra autoscaling, phải cố định tổng quota và quan sát tỷ lệ 429 khi thêm replica. Test chỉ hợp lệ khi mock hoặc API có chính sách quota rõ và đo được request thực.

## 13. Các lỗi thiết kế flow control rất dễ bỏ sót

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Tăng 10 replica khi downstream đã 429 | Tổng request tăng, downstream càng quá tải | Chia global quota, mở circuit hoặc nâng capacity đích trước |
| Chỉ giảm Artemis consumerWindowSize | Giảm buffer nhưng không giới hạn requests/s | Thêm application rate limiter/concurrency |
| Giảm Classic queuePrefetch rồi nghĩ đã giới hạn API | Prefetch đo bằng message, không phải request rate | Dùng rate limit riêng |
| Nhận message rồi sleep dài trước gọi API | Giữ message in-flight/unacked, làm nghẽn phân phối | Chờ permit trước receive nếu có thể |
| ACK trước khi API/DB xác nhận bền vững | Không thể retry an toàn khi downstream lỗi | Commit JMS sau kết quả nghiệp vụ được bảo đảm |
| Gặp 429 rồi rollback tức thì không delay | Retry storm, tăng tải API | Cooldown + broker redelivery policy |
| Gặp 503 kéo dài vẫn retry đến hết limit | Message hợp lệ đồng loạt rơi DLQ | Circuit breaker/tạm dừng intake, phục hồi có kiểm soát |
| Rate limit 8 mỗi replica, không xét replica count | Quota global bị vượt khi autoscale | Distributed limiter hoặc phân quota động |
| Đặt HTTP timeout 120 giây, concurrency vô hạn | In-flight phình to, cạn socket/thread/pool | Timeout + bulkhead + bounded queue |
| Dùng PAGE mà không theo dõi disk | Đổi memory pressure thành disk exhaustion | Theo dõi paging/disk và upstream admission |
| Dùng DROP cho dữ liệu đơn hàng | Mất message nghiệp vụ không hồi phục | BLOCK/FAIL với outbox hoặc PAGE có giới hạn |
| Tự KILL slow consumer khi không điều tra | Redelivery/reconnect churn, không giải quyết downstream | NOTIFY trước, triage theo metrics |
| Không đo oldest-message age | Queue nhỏ vẫn có thể chứa một message kẹt rất lâu | Alert age/lag và eventId |
| Bỏ qua idempotency khi HTTP timeout | API có thể đã thực hiện dù client không nhận response | Idempotency-Key, inbox và đối soát |

## 14. Checklist trước khi đưa consumer vào production

| Câu hỏi | Điều phải chứng minh |
| --- | --- |
| Có biết downstream quota thực không? | Quota theo giây/burst, số concurrent tối đa, quy tắc 429/Retry-After |
| Có phân biệt per-instance/global? | Khi replica scale, tổng request vẫn trong ngân sách |
| Có kiểm soát intake? | Permit/capacity trước receive, không tạo buffer không giới hạn |
| Có cấu hình prefetch/window phù hợp? | Artemis byte window hoặc Classic message prefetch được đo và tinh chỉnh |
| ACK có đúng lúc? | Chỉ sau DB/API side effect hoàn tất theo contract |
| Nếu HTTP timeout sau server commit? | eventId/Idempotency-Key giúp không tạo side effect trùng |
| Nếu downstream down kéo dài? | Circuit OPEN, không retry nóng, backlog durable và alert |
| Nếu message không hợp lệ vĩnh viễn? | Retry bounded, DLQ/quarantine và replay có kiểm soát |
| Nếu producer lớn hơn consumer lâu dài? | Backpressure/paging/FAIL và capacity plan, không che giấu backlog |
| Có thấy consumer chậm thực sự không? | Cùng đo enqueue, ACK, oldest age, in-flight, latency/429 của đích |
| Khi scale hoặc tăng limit? | Có thử tải minh chứng downstream còn headroom |
| Khi triển khai Classic/Artemis khác nhau? | Config đúng provider/release; không trộn window/prefetch hoặc XML policy |

**Kết luận:** phát hiện slow consumer cần **đo tiến độ trong tương quan với lượng công việc và sức khỏe downstream**, không chỉ nhìn queue depth hay tốc độ ACK thấp. Giới hạn tốc độ và số request đồng thời ở consumer là lớp bảo vệ trực tiếp cho API/DB; prefetch/window giảm mức in-flight trong client; redelivery backoff/DLQ kiểm soát retry; broker address policy và producer admission control bảo vệ hệ thống khi backlog tăng lâu dài. Với ActiveMQ Artemis hoặc Classic, mục tiêu đúng là **giữ dữ liệu an toàn và để toàn pipeline hồi phục có kiểm soát**, thay vì đẩy nhiều request nhất có thể vào một downstream đang quá tải.
