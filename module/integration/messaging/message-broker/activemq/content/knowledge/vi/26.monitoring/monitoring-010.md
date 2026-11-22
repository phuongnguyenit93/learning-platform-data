# Phân biệt broker còn sống, broker sẵn sàng và luồng nghiệp vụ còn hoạt động

> **Chương:** Giám sát  
> **Phạm vi:** Apache ActiveMQ Classic và ActiveMQ Artemis trong hệ thống Java/JMS; áp dụng cho broker chạy trực tiếp, container hoặc Kubernetes. Trọng tâm là phân biệt **liveness**, **readiness** và **business-flow progress** để đặt probe, alert và hành động phục hồi đúng. Các endpoint/metrics ứng dụng tự định nghĩa trong bài **không phải tính năng mặc định** của mọi bản ActiveMQ.

Một broker có process Java đang chạy, cổng **61616** mở và console hiển thị **UP**, nhưng các lệnh thanh toán vẫn có thể không được xử lý. Ngược lại, một broker đang bảo trì và không cho **kết nối mới** có thể vẫn có process khỏe; việc lập tức kill/restart nó chỉ làm trầm trọng thêm tình trạng phục hồi journal. Khi một worker chưa nhận message vì không có đơn hàng mới, việc thấy **processed rate = 0** cũng không chứng minh dòng nghiệp vụ bị nghẽn.

Ba câu hỏi cần được trả lời bằng **ba nhóm tín hiệu khác nhau**:

1. **Broker còn sống (liveness):** tiến trình và phần cốt lõi của broker có còn hoạt động đến mức cần tiếp tục chạy, thay vì phải khởi động lại hay không?
2. **Broker sẵn sàng (readiness):** tại thời điểm này, broker có thể phục vụ **loại traffic đã định nghĩa** từ đúng client, qua đúng listener, credential, destination và giới hạn tài nguyên hay không?
3. **Luồng nghiệp vụ còn hoạt động (business progress):** các message cần xử lý có thực sự đi từ đầu vào đến **kết quả nghiệp vụ đã commit**, trong khoảng trễ được chấp nhận, hay chỉ đang chờ, retry, DLQ hoặc “ACK giả”?

**Đừng biến ba tín hiệu thành một cờ UP duy nhất.** Mỗi loại trả lời một câu hỏi vận hành và thường dẫn đến hành động khác nhau.

## 1. Bảng định nghĩa: đo cái gì và ai chịu trách nhiệm?

| Cấp | Đối tượng chính | Bằng chứng cần có | Khi thất bại nên làm gì? |
|---|---|---|---|
| **Liveness** | Broker JVM/process | Process sống, thành phần runtime thiết yếu không mắc lỗi không hồi phục; optional local heartbeat có hạn thời gian | Điều tra/crash recovery; restart **chỉ khi** lỗi thuộc loại không tự hồi phục |
| **Readiness** | Broker service đối với một đường dùng xác định | Kết nối đúng endpoint, TLS/auth hợp lệ, broker ở vai trò phục vụ, destination được phép, resource/admission policy cho phép thao tác yêu cầu | Ngừng route kết nối **mới**, xử lý quyền/TLS/disk/role; tránh restart mù quáng |
| **Business progress** | Producer → broker → consumer → DB/API/outcome | Có work cần xử lý; có kết quả thực đã commit; lag/age, retry, DLQ và kết quả đối soát nằm trong SLO | Tìm tầng nghẽn; khôi phục consumer/downstream, replay/đối soát có kiểm soát |

**Chủ thể sở hữu tín hiệu cũng khác nhau.** Liveness là trách nhiệm runtime/broker operator. Readiness có thể khác theo **producer, consumer, protocol hoặc queue**. Business progress cần instrumentation tại **ứng dụng và nguồn dữ liệu nghiệp vụ**, không thể suy ra từ broker socket đơn thuần.

### 1.1. Ba tín hiệu không có quan hệ bao hàm tuyệt đối

~~~mermaid
flowchart TD
    JVM["Broker process / JVM"] --> LIVE{"Liveness?"}
    LIVE -->|Không| RESTART["Điều tra restart / crash recovery"]
    LIVE -->|Có| READY{"Ready cho workload?"}
    READY -->|Không| DRAIN["Không nhận kết nối mới / điều tra dependency"]
    READY -->|Có| PATH["Đường JMS có thể nhận traffic"]
    PATH --> FLOW{"Business outcome có tiến triển?"}
    FLOW -->|Có| OK["Luồng đạt mục tiêu"]
    FLOW -->|Không| INVEST["Điều tra consumer, downstream, DB, retry, DLQ"]
~~~

Sơ đồ là **quy trình ra quyết định thường dùng**, không phải định luật rằng readiness luôn kéo theo business progress. Một broker có thể **sẵn sàng** nhưng không hề có work để xử lý; broker có thể **readiness=false** vì chặn client mới trong lúc một số consumer đang kết nối vẫn hoàn tất message cũ. Business flow có thể fail dù cả broker và connection healthy.

### 1.2. Ma trận triệu chứng thực tế

| Tình huống | Broker sống? | Broker ready? | Business flow? | Diễn giải |
|---|---|---|---|---|
| JVM đã dừng | **Không** | Không | Thường gián đoạn nếu không có HA | Sự cố process/node |
| TCP 61616 mở nhưng login JMS lỗi | Có thể **có** | **Không** đối với principal đó | Có thể ngừng | TCP accept chưa chứng minh authentication |
| Broker A live nhưng đang là passive/backup không phục vụ workload này | **Có** | **Không** cho đường dữ liệu chính | Có thể chạy qua active khác | Không tự restart backup vì “not ready” |
| Broker nhận send nhưng persistent store tới hạn | Có | **Có thể không** cho producer write | Có thể stall | Read/write readiness cần xét resource và transaction |
| Broker healthy, consumer đã dừng | Có | Có thể **có** | **Không**, nếu pending work quá SLO | Lỗi tầng xử lý, không phải broker process |
| Consumer ACK nhưng DB transaction thất bại bị nuốt lỗi | Có | Có | **Không đúng** | ACK không chứng minh kết quả nghiệp vụ |
| Queue trống vì không có đơn mới | Có | Có | **Bình thường** | Processed rate = 0 không phải stalled |
| DLQ tăng trong khi send vẫn thành công | Có | Có cho ingress | **Suy giảm** | Cần điều tra poison messages / retry |
| Producer gửi vào sai broker/queue | Có | Có tại endpoint đã kiểm | Luồng mục tiêu **không hoạt động** | Phải test đúng destination và business correlation |

### 1.3. Liveness và readiness có thể khác cho cùng broker

Một Artemis broker có nhiều **acceptors**: Core/JMS listener có thể hoạt động trong khi AMQP acceptor lỗi. Một Classic broker có OpenWire còn hoạt động nhưng web console/Jolokia bị chặn. Vì thế tuyên bố **broker ready** phải luôn ghi rõ **ready cho workload nào**, ví dụ:

~~~text
orders-core-producer-readiness:
  broker = orders-live
  protocol = CORE
  destination = orders.commands.v1
  operation = authenticated persistent send
  max latency = 3 s
~~~

Readiness của producer **không thay thế** readiness của consumer; readiness của web console **không phải** readiness của JMS data plane.

## 2. Liveness: cẩn thận với cơ chế restart tự động

Liveness nên phát hiện lỗi **không thể tự phục hồi** của tiến trình broker hoặc runtime. Nếu liveness phụ thuộc DNS, DB, service bên ngoài hoặc kết nối tới broker khác, mất một dependency ngắn có thể khiến bộ điều phối restart hàng loạt broker đang khỏe.

### 2.1. Các phép đo liveness thường dùng

- **Process status:** container/JVM có còn chạy không? Container runtime đã tự phát hiện PID chính chết, nên probe không cần mô phỏng lại vô nghĩa.
- **Local progress/heartbeat** được một thành phần runtime bên trong broker hoặc sidecar thiết kế đúng phát ra: có cập nhật trong thời hạn không, thread/loop có bị kẹt hoàn toàn không?
- **JVM GC, heap, deadlock/unresponsiveness:** log, thread dump, GC pause và memory có cho thấy runtime không tiến triển không?
- **Listener TCP:** có thể dùng như tín hiệu bổ sung, nhưng **socket open chỉ kiểm tra chặng mạng/accept**, chưa đủ chứng minh broker xử lý JMS khỏe.

**Anti-pattern:** đặt liveness là “gửi message sang broker thứ hai và đợi DB cập nhật”. Một DB outage sẽ khiến broker A bị restart dù process A hoàn toàn khỏe, tạo restart loop và kéo dài recovery journal.

### 2.2. Vì sao TCP port open chưa đủ?

~~~text
TCP connection tới :61616 = success
       |
       +-- JVM acceptor mở, nhưng auth reject
       +-- Broker chưa hoàn tất recovery/activation
       +-- Store hết chỗ, persistent send bị block
       +-- Queue đích không tồn tại, role không có send
       +-- Consumer/DB downstream đã chết
~~~

TCP probe đặc biệt có ích làm **lớp kiểm tra nông**, nhưng không được báo cáo là “readiness nghiệp vụ” nếu chưa qua JMS handshake và route. Tương tự, **curl /console** thành công chỉ nói web plane có phản hồi, không chứng minh Core/OpenWire acceptor có thể commit message.

### 2.3. Restart không phải biện pháp đầu tiên cho mọi failure

Không tự restart broker chỉ vì:

- Queue backlog tăng do consumer chậm.
- DLQ tăng do message sai schema.
- Broker chưa thành live do đang standby HA.
- Disk tới watermark gây producer backpressure.
- DNS/network tạm mất với downstream.
- Monitoring endpoint JMX/Jolokia đang lỗi nhưng messaging bình thường.

Trong các trường hợp đó, restart có thể phá thời gian phục hồi, tăng redelivery và tạo duplicate. **Liveness failure phải phản ánh lỗi tiến trình đáng restart**, không phải một sự kiện cần điều tra nghiệp vụ.

## 3. Readiness: định nghĩa một hợp đồng phục vụ cụ thể

Readiness trả lời câu hỏi: **có nên gửi workload mới tới endpoint này tại thời điểm hiện tại không?** Với broker, nó nên gắn với một đường dữ liệu cụ thể, ví dụ **producer persistent Core send tới orders.commands.v1**.

### 3.1. Những lớp readiness có mức tin cậy khác nhau

| Kiểm tra | Chứng minh | Chưa chứng minh |
|---|---|---|
| **TCP connect** | Port/socket có thể tiếp nhận kết nối ở tầng transport | JMS authentication, TLS identity, queue send |
| **TLS handshake + broker authentication** | Đường protocol và principal hợp lệ | Quyền trên destination; commit persistent send |
| **JMS connection/session + browse destination test** | Broker xử lý một số thao tác JMS và quyền browse tương ứng | Quyền send/consume trên queue thật, storage còn chỗ, business outcome |
| **Persistent send/commit vào queue probe riêng** | Ingress và transaction gửi được broker chấp nhận | Consumer nghiệp vụ chạy; queue thật có đúng routing/ACL |
| **Send + receive/commit trên queue probe riêng** | Một đường JMS nội bộ có thể nhận và trả message | Luồng nghiệp vụ thật đã xử lý |
| **End-to-end synthetic command qua business handler** | Luồng test tới kết quả đã được quan sát | Toàn bộ loại dữ liệu/ngữ cảnh thật đều không lỗi |

**Chọn probe đủ mạnh để trả lời mục đích**, không mặc định chạy end-to-end synthetic ở tần suất 5 giây. Active probe tạo message và tải; dùng queue chuyên dụng, TTL, giới hạn tần suất và audit.

### 3.2. HA active/backup: ready theo vai trò

Với Artemis hoặc Classic ở topology HA, một broker đang làm **backup/passive** có thể có process sống và lưu trạng thái phục hồi, nhưng **chưa phải endpoint tiếp nhận workload mới** như live/active. Khi xây readiness:

- Phân biệt **role/activation state** của node với tình trạng JVM.
- Một node backup **không được restart liên tục** chỉ vì data-plane readiness=false.
- Kiểm tra **service endpoint/client HA URI** và routing của load balancer có đưa traffic tới node đang live hay không.
- Không tự coi mọi node ở cùng một cluster đều tương đương cho mọi queue/address.

**Kết luận:** readiness là hợp đồng giữa **workload và điểm nhận traffic**, không phải một nhãn tuyệt đối trên mọi node của hệ HA.

### 3.3. Readiness với storage và flow control

Một broker có thể xác thực JMS connection và browse queue thành công, nhưng **persistent send** đang block do storeUsage, disk full, journal pressure hoặc address-full policy. Nếu workload quan trọng là producer persistent, readiness chỉ ở mức **connect+browse** phải được ghi là **shallow readiness**; bổ sung storage/admission metrics hoặc một send transaction trên queue probe để đánh giá sâu hơn.

Ngược lại, nếu broker tạm áp backpressure nhưng consumer vẫn đang **drain backlog**, hành động đúng có thể là **giảm ingress** thay vì kill broker. Cần phân biệt:

- **Ready to read/drain**: consumer có thể nhận/ACK.
- **Ready to accept new persistent writes**: producer có thể commit send đúng SLO.
- **Ready for management**: operator đọc JMX/Jolokia.

Đừng gộp ba nhóm vào một điều kiện restart.

## 4. Classic và Artemis: nơi lấy dữ kiện thực tế

Cả hai sản phẩm đều có **JMX management**, nhưng tên MBean/attributes và semantics có thể khác. Không copy một ObjectName Classic sang Artemis rồi kết luận broker mất metrics.

### 4.1. ActiveMQ Classic qua JMX/console

Một số attributes thường có ở destination MBean Classic:

| Chỉ số/MBean kiểu Classic | Ý nghĩa vận hành |
|---|---|
| **QueueSize** | Số message còn được queue quản lý ở thời điểm đo, theo semantics version |
| **EnqueueCount** | Tổng số vào queue theo counters |
| **DequeueCount** | Tổng số rời queue/được hoàn tất theo counters |
| **InFlightCount** | Message đã dispatch nhưng chưa ACK |
| **ConsumerCount** | Số consumers hiện gắn queue |
| **MemoryPercentUsage** | Áp lực usage của destination, không phải số byte toàn backlog |
| **Broker MemoryPercentUsage, StorePercentUsage, TempPercentUsage** | Memory/store/temp gần giới hạn policy chưa |
| **Network bridge/connector state** | Broker-to-broker link có kết nối/forward theo topology không |

Ví dụ pattern ObjectName, phải thay broker name và escape destination nếu cần:

~~~text
org.apache.activemq:type=Broker,brokerName=<name>,
  destinationType=Queue,destinationName=<queue-name>
~~~

**QueueSize = 0 không chứng minh tất cả nghiệp vụ đã thành công.** Message có thể đã expired, DLQ, chuyển sang broker khác hoặc bị ACK nhầm trước DB commit. EnqueueCount và DequeueCount là counters, không phải giao dịch nghiệp vụ bất biến xuyên restart hoặc thay đổi queue; phải hiểu reset và window của phiên bản.

### 4.2. ActiveMQ Artemis qua management

Artemis cung cấp queue/address/broker management qua **JMX**, console/Hawtio/Jolokia hoặc management APIs theo cấu hình. Các dữ kiện hữu ích:

| Dữ kiện Artemis | Cách diễn giải |
|---|---|
| **Queue message count** | Backlog theo queue |
| **Delivering count** | Message đang được giao cho consumer, chưa hoàn tất theo broker |
| **Consumer count** | Có consumer kết nối queue không |
| **Messages added / acknowledged** | Counters động thái vào/ra, có thể khác tên/semantics theo version |
| **Scheduled/redelivery/DLQ counts** | Pending vì delay/retry hay lỗi, không phải business success |
| **Address paging / disk usage / journal status** | Backpressure, nguy cơ storage hoặc recovery |
| **Broker activation/HA role** | Node hiện có phục vụ traffic phù hợp không |
| **Connection count / acceptor state** | Data plane connectivity, không chứng minh business outcome |

Artemis có cơ chế **address/queue routing**: một address có thể gắn nhiều queues. Đo **address tổng thể** không thay việc chọn **queue/subscription đích**; đặc biệt với MULTICAST, một subscription chậm có thể giữ backlog dù subscription khác đã hoàn tất.

### 4.3. Web console và Jolokia không phải health endpoint mặc định

Một số bản phân phối Classic/Artemis đưa Jolokia dưới web console; URL path, authentication và quyền phụ thuộc phiên bản. **Không giả định mọi broker có sẵn HTTP /health/live hoặc /health/ready** trên port 8161. Đây là endpoint có thể được **tự triển khai** bằng sidecar/exporter/agent, nhưng phải phân biệt với web console quản trị.

JMX/Jolokia nên nằm trong management network, có TLS và quyền hẹp. Để scrape chỉ số, ưu tiên read-only identity; không mở quyền purge/move message chỉ để giám sát. Lỗi scrape/credential của Jolokia có thể báo **observability degraded** trong khi data plane vẫn đang phục vụ.

## 5. Thiết kế ma trận health cho một luồng Java/JMS

Giả sử **orders-api** gửi command vào Artemis **orders.commands.v1**, worker xử lý và ghi **payment_results** trong PostgreSQL; khi lỗi vượt retry, message đi DLQ. Một bảng health đúng nên phân loại:

| Thành phần | Liveness | Readiness | Business progress |
|---|---|---|---|
| **Broker Orders** | JVM/process và service threads | Core auth, queue, persistent send, storage headroom | Không thể tự chứng minh payment_results đã commit |
| **Orders API producer** | App process | Có thể nhận request/commit outbox hoặc gửi JMS theo hợp đồng | Tỷ lệ yêu cầu được publish/accepted và kết quả đơn hàng |
| **Payment worker** | Worker process/threads | Có thể consume queue, DB/API dependency phù hợp | paymentAttemptId chuyển sang SUCCEEDED/FAILED có kiểm chứng |
| **PostgreSQL** | DB process | Connect/transactions phù hợp | Bản ghi/payment state đạt mục tiêu nghiệp vụ |
| **DLQ** | Không phải process | Queue quản trị có sẵn theo topology | DLQ count/age là **tín hiệu thất bại**, không phải throughput tốt |

### 5.1. Vì sao consumerCount > 0 chưa đủ?

Consumer vẫn kết nối broker nhưng có thể:

- Đang bị kẹt ở một HTTP API không có timeout.
- Thử lại cùng poison message rồi rollback vô hạn.
- Nhận message và ACK trước khi DB commit.
- Bị deadlock, thread pool cạn hoặc rate limit.
- Có consumerCount=1 nhưng xử lý được 0 message/phút khi backlog tăng.

Cần đo **completion rate, duration, oldest unfinished age, retries/DLQ và trạng thái side effect**, không chỉ số kết nối.

### 5.2. Broker ready nhưng business stalled

~~~mermaid
flowchart LR
    P["Orders API<br/>send success"] --> B["Broker<br/>JMS ready"]
    B --> Q["Queue pending ↑"]
    Q --> C["Worker connected<br/>ConsumerCount=1"]
    C --> D["DB/API downstream<br/>timeout"]
    D -. "Không có business commit" .-> O["Outcome stalled"]
~~~

Giải pháp đúng là kiểm tra **worker/downstream** và cơ chế retry/backoff, không restart broker khỏe chỉ vì dashboard “payment processed” về 0.

## 6. Java/JMS readiness probe: đọc không phá hủy

Ví dụ dưới đây dùng **Artemis JMS client thuộc thế hệ javax.jms (JMS 2.x)**. Với Spring Boot 3/Jakarta Messaging, đổi đồng bộ dependency/import sang **jakarta.jms** và Artemis Jakarta client. Với Classic, dùng **ActiveMQ Classic JMS client** tương ứng; không dùng constructor Artemis client như thể nó luôn kết nối được Classic OpenWire.

**Mục tiêu:** kiểm tra broker chấp nhận **JMS connection được xác thực** và một thao tác **QueueBrowser** trên queue probe riêng **ops.readiness**. Đây là **shallow JMS readiness**, không gửi/consume message nghiệp vụ.

### 6.1. BrokerReadiness.java

~~~java
package com.example.monitoring;

import javax.jms.JMSContext;
import javax.jms.Queue;
import javax.jms.QueueBrowser;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class BrokerReadiness {
    public static void main(String[] args) {
        try {
            String url = required("MQ_URL");
            String user = required("MQ_USER");
            String password = required("MQ_PASSWORD");
            String queueName = required("MQ_PROBE_QUEUE");

            ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);

            try (JMSContext ctx =
                    factory.createContext(user, password)) {

                Queue queue = ctx.createQueue(queueName);

                // Browser không remove/ACK message trong queue.
                // Có quyền browse mà không có quyền send là khả dĩ.
                QueueBrowser browser = ctx.createBrowser(queue);
                try {
                    // Không gọi receive(), không iterate body.
                    // Việc tạo browser kiểm tra một đường JMS
                    // và quyền theo provider/broker policy.
                    System.out.println("JMS_READINESS_OK");
                } finally {
                    browser.close();
                }
            }
        } catch (Exception failure) {
            System.err.println(
                "JMS_READINESS_FAIL: "
                + failure.getClass().getSimpleName());
            System.exit(2);
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.trim().isBlank()) {
            throw new IllegalArgumentException(
                "Missing environment variable: " + name);
        }
        return value;
    }
}
~~~

**Điều kiện để kết quả có ý nghĩa:**

- **ops.readiness** là queue đã provision sẵn, thuộc đúng broker và routing mà probe được phép xem. Nếu broker có auto-create queue, việc gọi **createQueue/createBrowser** có thể tương tác với tính năng auto-create tùy cấu hình, làm che lỗi queue thiếu. Dùng cơ chế kiểm tra provisioning qua management riêng hoặc tắt auto-create phù hợp trong lab.
- Tài khoản probe có quyền **browse đúng queue test**, không cần quyền quản trị toàn bộ broker và không cần đọc body nhạy cảm.
- **JMSContext** được đóng khi kết thúc; không giữ connection/session trong kube exec probe.
- Cấu hình **connect/call timeout của Artemis client theo đúng version** và timeout ngoài của probe. Một lời gọi treo vô hạn không được biến readiness probe thành process tích lũy tài nguyên.
- **Pass không chứng minh persistent send**, không chứng minh consumer nghiệp vụ và cũng không biết DB/API downstream khỏe.
- Trong Java 11+, **String.isBlank()** dùng được; nếu môi trường Java 8 phải đổi thành **trim().isEmpty()**.

**Kết quả mong đợi:** chương trình exit **0** khi tạo được JMS context và browse trên queue probe; exit **2** khi lỗi được bắt. Việc không iterate body cố ý giữ probe nhẹ và không đụng dữ liệu đang chờ.

### 6.2. Readiness không được dùng credentials của administrator

Probe chạy thường xuyên và có thể bị thu thập log. Cấp một principal hẹp cho **ops.readiness**. Nếu cần test producer **send capability** thay vì browse, dùng một **probe queue khác** với quyền send/browse/consume được thiết kế riêng, không nâng quyền admin cho probe đang chạy.

**Tuyệt đối không sử dụng AUTO_ACKNOWLEDGE consumer trên queue nghiệp vụ chỉ để kiểm tra readiness.** Một lần receive thành công có thể lấy mất message production.

### 6.3. Không nhầm broker readiness với trạng thái TCP

Ví dụ:

~~~text
tcp://broker:61616   → connect success
JMS auth             → fail vì credential hết hạn
QueueBrowser         → không chạy được

Kết luận:
  TCP reachable = TRUE
  JMS readiness cho principal/queue cụ thể = FALSE
  Broker JVM có thể vẫn live
~~~

Khi dashboard chỉ có **tcpSocket UP**, phải ghi nhãn **transport reachability**, không quảng bá nó là **broker fully ready**.

## 7. K8s probes: đúng tín hiệu, đúng hậu quả tự động

Kubernetes có **startupProbe**, **livenessProbe** và **readinessProbe**, nhưng hành động của chúng khác nhau:

- **startupProbe** cho tiến trình thời gian khởi động/recovery journal trước khi kích hoạt các probe còn lại.
- **livenessProbe** thất bại liên tục có thể khiến kubelet **restart container**.
- **readinessProbe** thất bại sẽ đánh dấu Pod **NotReady**, khiến Service ngừng chọn Pod đó làm endpoint mới khi phù hợp với cơ chế routing; **không tự kill broker**.

Readiness=false **không luôn cắt các kết nối TCP/JMS đã tồn tại**. Client có long-lived connection, prefetch và failover URI riêng; kiểm tra chúng khi Pod bị đánh dấu NotReady. Với StatefulSet/HA, readiness của standby có thể khác live node, phải cấu hình theo vai trò.

### 7.1. Ví dụ Kubernetes Pod/container fragment

~~~yaml
# Đây là fragment của container spec, KHÔNG phải Deployment đầy đủ.
# Container image phải có JRE, probe JAR/dependencies và env MQ_*.
ports:
  - name: core
    containerPort: 61616

startupProbe:
  tcpSocket:
    port: core
  periodSeconds: 5
  failureThreshold: 60

livenessProbe:
  tcpSocket:
    port: core
  periodSeconds: 30
  timeoutSeconds: 2
  failureThreshold: 5

readinessProbe:
  exec:
    command:
      - java
      - -cp
      - /opt/probes/*
      - com.example.monitoring.BrokerReadiness
  periodSeconds: 30
  timeoutSeconds: 8
  failureThreshold: 3
  successThreshold: 2
~~~

Đây là một **lab baseline có giới hạn**. Liveness bằng TCP **chỉ phát hiện port không thể kết nối**, không phát hiện mọi thread deadlock; nó cũng có thể restart broker khi listener tạm đóng trong quá trình phục hồi. Trong production, thay bằng **local broker progress signal** được triển khai/kiểm chứng riêng nếu có, tránh restart do một dependency ngoài. Không giả định ActiveMQ có sẵn **/live** hoặc **/ready** theo HTTP.

**Readiness exec cần có lớp Java thực sự được đóng gói** trong image, cùng JMS client libraries; không có file đó thì kubelet sẽ báo lỗi exec, không phải broker bị lỗi. Đặt timeout probe lớn hơn thời gian JVM khởi động thông thường và JMS timeout nội bộ nhưng không quá dài; tránh tạo JVM mới quá dày khi hàng trăm Pods cùng probe. Nếu cần quy mô lớn, cân nhắc long-running local health endpoint/sidecar với rate limit rõ ràng.

### 7.2. Không dùng chính synthetic business test làm liveness

Nếu readiness dùng việc **gửi và nhận message qua một queue đặc biệt**, sự cố storage có thể đánh NotReady là hợp lý cho producer. Nhưng dùng phép thử đó làm **liveness** có thể tạo restart storm đúng lúc broker đang recover hoặc store pressure. Còn synthetic business end-to-end có database/API thật **không được** là lý do tự động kill broker.

### 7.3. NetworkPolicy và management endpoint

JMS health probe nên dùng đường nội bộ tới broker, credential tối thiểu. **Không expose console/JMX/Jolokia public** chỉ để kubelet hoặc load balancer thực hiện health check. Nếu dùng custom exporter/HTTP endpoint, bind management/private interface, bảo vệ authentication và tạo NetworkPolicy cho các sources được duyệt.

## 8. Synthetic JMS: phân biệt data-plane smoke test với business-flow test

Khi cần chứng minh cả **send+receive+ACK/commit** của broker hoạt động, có thể dùng một queue **ops.synthetic.loopback** dành riêng cho probe. Đây là bài test **data plane**, mạnh hơn browse, nhưng **vẫn chưa chứng minh payment/order business handler đang hoạt động**.

### 8.1. Vì sao probe phải cô lập?

- Mỗi lần test tạo một message thật. Nếu dùng queue nghiệp vụ, có thể kích hoạt side effect ngoài ý muốn.
- Nhiều probes song song phải có **probeId riêng** để không tiêu thụ message của nhau.
- TTL/cadence nên hạn chế backlog, DLQ và storage overhead.
- Message test nên nhỏ, không chứa dữ liệu cá nhân hay credential.
- Probe dùng transaction gửi và nhận để không báo thành công khi send chưa commit.

### 8.2. ArtemisSyntheticLoopback.java

~~~java
package com.example.monitoring;

import java.util.UUID;
import javax.jms.DeliveryMode;
import javax.jms.JMSConsumer;
import javax.jms.JMSContext;
import javax.jms.Message;
import javax.jms.Queue;
import javax.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ArtemisSyntheticLoopback {
    public static void main(String[] args) throws Exception {
        String url = required("MQ_URL");
        String user = required("MQ_USER");
        String password = required("MQ_PASSWORD");

        String probeId = UUID.randomUUID().toString();
        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(url);

        try (JMSContext ctx = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {

            Queue queue = ctx.createQueue("ops.synthetic.loopback");
            String selector = "probeId = '" + probeId + "'";
            JMSConsumer consumer = ctx.createConsumer(queue, selector);

            try {
                TextMessage testMessage =
                    ctx.createTextMessage("synthetic-test");
                testMessage.setStringProperty("probeId", probeId);

                ctx.createProducer()
                   .setDeliveryMode(DeliveryMode.PERSISTENT)
                   .setTimeToLive(30000L)
                   .send(queue, testMessage);

                // Send transaction phải commit trước khi receive.
                ctx.commit();

                Message received = consumer.receive(5000L);
                if (received == null
                        || !probeId.equals(
                            received.getStringProperty("probeId"))) {
                    ctx.rollback();
                    throw new IllegalStateException(
                        "Synthetic loopback did not complete");
                }

                ctx.commit();
                System.out.println(
                    "SYNTHETIC_JMS_OK probeId=" + probeId);
            } catch (Exception failure) {
                ctx.rollback();
                throw failure;
            } finally {
                consumer.close();
            }
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.trim().isBlank()) {
            throw new IllegalArgumentException(
                "Missing environment variable: " + name);
        }
        return value;
    }
}
~~~

**Kết quả PASS** chứng minh một round-trip trên **ops.synthetic.loopback** thành công trong thời hạn; nó **không có worker nghiệp vụ**, không đi qua mọi queue/address, không kiểm tra DB và không đảm bảo độ trễ của tất cả JMS clients.

**Lưu ý vận hành:**

- Provision queue test trên đúng broker, quyền sender/consumer theo principal dành riêng, tránh auto-create vô tình.
- Tài khoản test không có quyền gửi sang queue thanh toán hoặc DLQ.
- TTL 30 giây là ví dụ để giới hạn tồn đọng khi consumer/probe lỗi; kiểm tra expiry policy để không biến expiry của probe thành DLQ nghiệp vụ.
- **JMS transaction đã commit send** mà receive fail không tự xóa message khỏi queue; selector riêng và TTL hạn chế tác động, nhưng vẫn cần cleanup/metrics.
- Một probe fail ngay sau send commit có thể để lại message test; không tái sử dụng probeId như một business ID.
- Đừng chạy mỗi giây trên hàng nghìn Pod. Đây nên là **synthetic riêng theo broker/route**, với cadence và chi phí được tính toán.
- Khi commit receive thất bại với kết quả không chắc chắn, báo probe inconclusive/fail, điều tra queue; không khẳng định message đã được ACK.


## 9. Business progress: đo kết quả nghiệp vụ, không đo mỗi JMS ACK

Tín hiệu sâu nhất không nằm trong broker mà ở **state chuyển đổi nghiệp vụ**. Ví dụ một luồng đặt hàng và thanh toán:

~~~mermaid
flowchart LR
    REQ["Order request"] --> OB["Outbox / command accepted"]
    OB --> Q["JMS order/payment queue"]
    Q --> W["Payment worker"]
    W --> DB["Payment result committed"]
    DB --> DONE["Order marked terminal"]
    W --> RETRY["Retry / DLQ / reconcile"]
    RETRY -. "Chưa là success" .-> DONE
~~~

Một lần producer send OK xác nhận **ingress** vào broker theo điều kiện gửi; một lần consumer ACK xác nhận message đã được xử lý về phía broker. Nhưng business SLO thường muốn biết **order/payment reached terminal state**. Vì vậy cần điểm đo được định nghĩa bằng **business ID** và **trạng thái cuối có thẩm quyền**.

### 9.1. Bộ metric tối thiểu cho từng flow

Đề xuất bốn nhóm, ví dụ cho flow **order-to-payment**. Tên dưới đây là **custom application metrics**, không phải tên MBean hoặc Prometheus metrics mặc định của Classic/Artemis.

| Metric đề xuất | Kiểu | Quy tắc ghi | Ý nghĩa |
|---|---|---|---|
| **business_flow_accepted_total** | Counter | Sau khi nguồn chấp nhận tác vụ bền vững, ví dụ DB outbox commit | Có bao nhiêu tác vụ logic đã vào pipeline |
| **business_flow_terminal_total** | Counter, label outcome | Sau khi trạng thái cuối SUCCEEDED/DECLINED/CANCELED được ghi bền vững | Có bao nhiêu tác vụ thực sự hoàn tất |
| **business_flow_oldest_unfinished_age_seconds** | Gauge | Tuổi lớn nhất của tác vụ đã accepted nhưng chưa có terminal outcome | Có work thực sự bị tồn quá lâu hay không |
| **business_flow_inflight_count** | Gauge | Số business IDs đã accepted nhưng chưa terminal, theo nguồn bền vững | Phạm vi backlog ở tầng domain |
| **business_flow_completion_latency_seconds** | Histogram | Từ accepted_at tới terminal_at của mỗi business ID | p95/p99 end-to-end theo SLO |
| **business_flow_duplicate_suppressed_total** | Counter | Consumer bỏ qua bản giao trùng nhờ inbox/unique constraint | Dấu hiệu retry/redelivery |
| **business_flow_reconciliation_pending_count** | Gauge | Side effect ngoài hệ thống chưa xác định kết quả | Phát hiện “unknown” không được che bằng ACK |
| **business_flow_dlq_total** | Counter | Khi message đi DLQ hoặc case được ghi nhận từ broker management | Error path đang xuất hiện |

**Quy tắc đếm:** cùng một **paymentAttemptId** bị deliver ba lần nhưng chỉ commit một terminal outcome thì **business_flow_terminal_total** chỉ tăng **một** cho logic operation đó. Counter **messages_received_total** có thể tăng ba; hai metrics phải có tên/semantics khác nhau.

### 9.2. Nguồn sự thật là dữ liệu đã commit

Ví dụ dùng bảng domain:

~~~sql
CREATE TABLE payment_attempts (
    payment_attempt_id TEXT PRIMARY KEY,
    accepted_at TIMESTAMPTZ NOT NULL,
    terminal_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    CHECK (status IN (
        'PENDING', 'PROCESSING',
        'SUCCEEDED', 'DECLINED', 'CANCELED', 'UNKNOWN'
    ))
);

CREATE INDEX payment_attempts_unfinished
    ON payment_attempts (accepted_at)
    WHERE terminal_at IS NULL;
~~~

Một truy vấn quan sát backlog nghiệp vụ (PostgreSQL):

~~~sql
SELECT
    COUNT(*) AS unfinished_count,
    COALESCE(
        EXTRACT(EPOCH FROM now() - MIN(accepted_at)),
        0
    ) AS oldest_unfinished_age_seconds
FROM payment_attempts
WHERE terminal_at IS NULL;
~~~

Đây là ví dụ bảng/truy vấn theo **domain contract**: phải điều chỉnh khi **UNKNOWN** hoặc **CANCELED** có semantics khác trong hệ thống thật. Không tự gán terminal_at cho UNKNOWN nếu payment provider vẫn cần reconciliation. Với bảng lớn, truy vấn liên tục mỗi vài giây có thể tăng DB load; ưu tiên aggregate/index/cache/exporter có kiểm soát và chọn scrape interval phù hợp.

### 9.3. Điểm tăng counter phải nằm sau kết quả bền vững

~~~text
Consumer nhận commandId=pay-105
  → kiểm tra inbox/idempotency
  → thực hiện xử lý được phép
  → DB transaction ghi terminal result
  → DB COMMIT thành công
  → ghi nhận business terminal metric
  → JMS receive transaction COMMIT/ACK
~~~

Có một failure window giữa **DB commit** và **JMS ACK**. Nếu crash ngay sau DB commit, broker có thể redeliver. Consumer dùng **inbox/unique key** sẽ tránh effect trùng. Counter trong RAM có thể bị mất khi process crash; vì thế **dashboard metric không được thay database trong reconciliation**. Nếu SLO cần số chính xác, xây tổng hợp từ terminal rows/events có ID ổn định hoặc cơ chế xuất metrics chống trùng phù hợp.

### 9.4. Không có work thì throughput 0 là bình thường

Một worker không xử lý message trong 20 phút có thể đang khỏe nếu **accepted_total không tăng**, **inflight_count=0** và **oldest_unfinished_age_seconds=0**. Không dùng điều kiện đơn độc:

~~~text
processed_per_second == 0  ⇒  lỗi
~~~

Thay bằng:

~~~text
Có work đang chờ quá SLO
AND
không có terminal outcome tiến triển trong cửa sổ hợp lý
⇒
nghi ngờ business flow stalled
~~~

Với workflow theo lịch, yêu cầu tiến triển có thể đến từ **expected schedule** chứ không chỉ pending queue. Ví dụ “mỗi đêm phải gửi báo cáo trước 07:00” cần deadline metric và job completion state; không giả định cứ có broker queue là đủ xác định có work.

## 10. Prometheus/SLO: alert có điều kiện, tránh báo động giả

Bộ metrics ở mục 9 là **metrics tùy chỉnh** do ứng dụng/exporter định nghĩa, đã có label **flow** ổn định. Các biểu thức dưới đây là mẫu **PromQL để gắn vào hệ thống metrics thực tế**, không chạy được nếu bạn chưa phát đúng metric names/labels.

### 10.1. Cảnh báo business flow bị dừng thật

~~~yaml
groups:
  - name: business-messaging
    rules:
      - alert: PaymentFlowStalled
        expr: |
          (
            business_flow_oldest_unfinished_age_seconds{
              flow="order-to-payment"
            } > 300
          )
          and on(flow)
          (
            increase(business_flow_terminal_total{
              flow="order-to-payment",outcome="committed"
            }[10m]) == 0
          )
        for: 5m
        labels:
          severity: critical
          service: payments
        annotations:
          summary: "Payment flow có work quá 5 phút và không tiến triển"
          description: "Kiểm tra consumer, DB/API, retry, DLQ và commit."
~~~

**Giải thích chính xác:**

- **oldest_unfinished_age_seconds > 300** đảm bảo có work cũ hơn 5 phút; queue/process idle không tự kích hoạt.
- **increase(terminal_total[10m]) == 0** nói chưa có terminal outcomes phù hợp trong 10 phút.
- **for: 5m** yêu cầu điều kiện tồn tại ổn định, hạn chế nhiễu tạm thời.
- **on(flow)** ghép hai chuỗi theo nhãn flow; nếu có nhiều tenants/regions, phải đưa thêm các dimensions có nghĩa hoặc aggregate tường minh, tránh ghép nhầm.
- Label **outcome="committed"** chỉ là một quy ước; production phải định nghĩa terminal outcomes nào được coi là progress. Nếu **DECLINED** là kết quả hợp lệ của thanh toán, nó cũng là một terminal outcome, không được bỏ khỏi metric tiến triển.

**Quan trọng:** các counters cần được xuất **ngay cả khi bằng 0** để PromQL không im lặng do series chưa tồn tại. Nếu metric bị missing, hãy có alert riêng về **telemetry missing/exporter down**; không diễn giải “không có series” thành success.

Nếu metric thực sự là **business_flow_terminal_total** không có nhãn outcome mà chỉ đếm mọi trạng thái cuối, hãy bỏ filter outcome. Nếu có nhiều outcome, sử dụng **sum by(flow)** trên tập outcomes hợp lệ trước khi so increase; không copy rule y nguyên khi data model khác.

### 10.2. Theo dõi ingress, terminal throughput và tuổi backlog

~~~promql
# Tốc độ nhận tác vụ logic (không phải JMS delivery attempts).
sum by (flow) (
  rate(business_flow_accepted_total[5m])
)

# Tốc độ hoàn tất tác vụ logic.
sum by (flow) (
  rate(business_flow_terminal_total[5m])
)

# Tác vụ cũ nhất chưa hoàn tất.
max by (flow) (
  business_flow_oldest_unfinished_age_seconds
)

# Số tác vụ đang chờ kết quả cuối.
sum by (flow) (
  business_flow_inflight_count
)
~~~

**Không trừ hai counters rồi mặc định ra chính xác số đang chờ**, nếu counters reset khi process restart, có duplicate deliveries, các nhánh hủy/expiry hoặc metrics chưa được scrape đúng. Gauge inflight nên tính từ **domain state** đã được thống nhất, không chỉ từ raw JMS queue depth.

### 10.3. Broker readiness và telemetry health là alerts khác nhau

Một số tín hiệu Prometheus thường dùng nhưng phải đặt tên đúng:

- **up == 0** của một scrape target chỉ nói **Prometheus không scrape được target**. Nếu exporter/Jolokia lỗi còn data plane healthy, đây là lỗi telemetry, không trực tiếp là broker liveness.
- Một **readiness gauge** nên thể hiện contract cụ thể: **broker_ready_for_orders_persistent_send** thay vì tên mơ hồ **broker_up**.
- **queue pending age** và **DLQ ingress rate** là tín hiệu broker/domain, không phải lý do liveness restart.
- **business_flow_oldest_unfinished_age_seconds** vượt SLO là dấu hiệu cần mở incident luồng nghiệp vụ, dù broker_ready vẫn bằng 1.

Ví dụ một bộ alerts phân tầng:

| Alert | Nguyên nhân dự kiến | Hành động ban đầu |
|---|---|---|
| **BrokerProcessDead** | JVM/container chết | Kiểm tra restart/crash recovery và HA |
| **BrokerJmsNotReady** | Auth/TLS/queue, role, admission hoặc storage | Ngừng route traffic mới và điều tra |
| **BrokerStoreNearFull** | Backlog hoặc disk growth | Giảm ingress, phục hồi consumer, capacity plan |
| **BusinessFlowStalled** | Có work quá SLO nhưng outcome không tăng | Điều tra end-to-end worker/DB/API |
| **BusinessDLQGrowing** | Retry lỗi kéo dài, poison message | Phân tích root cause, không bulk replay |
| **MonitoringScrapeMissing** | Exporter/Jolokia/ACL/network scrape lỗi | Khôi phục observability riêng |
| **SyntheticLoopbackFailed** | Một đường probe JMS send/receive lỗi | Kiểm tra queue probe và broker data plane |

Không cho tất cả alert severity=critical giống nhau. Một lỗi scrape có thể là warning, trong khi **business side effect không tiến triển** với backlog già hơn SLO là critical.

### 10.4. SLO chọn theo nghiệp vụ, không theo số tròn của broker

Ví dụ định nghĩa:

~~~text
SLI: thời gian từ accepted_at của paymentAttemptId
     đến terminal_at của một kết quả nghiệp vụ bền vững.

SLO: 99% payment attempts hoàn tất trong 120 giây
     trên rolling 7 ngày, trừ những trạng thái
     cần điều tra mà domain contract định nghĩa rõ.

Tín hiệu sự cố tức thời:
     oldest unfinished > 300 giây
     và không có completion trong 10 phút.

Tín hiệu xu hướng:
     p95/p99 end-to-end latency tăng,
     ingress > terminal throughput kéo dài,
     DLQ/reconciliation pending tăng.
~~~

**SLI/SLO và alert** là hai công cụ khác nhau. Một SLO có thể cho phép một tỷ lệ nhỏ các yêu cầu chậm, trong khi alert trên oldest age giúp vận hành can thiệp sớm. Chọn các cửa sổ **theo business deadline và traffic pattern**; không dùng cứng “5 phút” cho mọi hệ thống giao hàng, thông báo hay thanh toán.

## 11. Synthetic business flow: đo xuyên producer, broker và consumer

**JMS loopback** trong mục 8 chỉ kiểm tra queue probe. Nếu mục tiêu là “đơn hàng thử nghiệm đi qua hệ thống và nhận kết quả”, cần một **synthetic business transaction** chạy cùng đường xử lý thật nhưng **không gây side effect ngoài ý muốn**.

### 11.1. Mô hình an toàn

~~~mermaid
sequenceDiagram
    participant S as Synthetic runner
    participant P as Producer/outbox
    participant M as Broker
    participant W as Real business worker
    participant D as Isolated test datastore
    S->>P: TestOrder(syntheticId)
    P->>M: Publish command synthetic=true
    M->>W: Deliver theo route thật
    W->>D: Ghi test outcome, không charge tiền thật
    D-->>S: Terminal outcome by syntheticId
    S->>S: PASS nếu đúng ID, trạng thái và deadline
~~~

**Điều kiện quan trọng:** chỉ gắn **synthetic=true** trong payload **không tự an toàn** nếu một phần consumer vẫn gọi external API. Phải có test account/sandbox provider, idempotency và guard ở những đoạn có side effect. Không để synthetic command tạo email thật, charge tiền thật hoặc cấp hàng thật.

### 11.2. Định nghĩa pass/fail

Synthetic chỉ PASS khi:

1. Runner ghi **syntheticId** và thời điểm bắt đầu, rồi submit tác vụ test qua đường ingress thật.
2. Producer/outbox publish commit thành công hoặc nguồn bền vững nhận tác vụ.
3. Consumer nghiệp vụ đúng nhận/validate/handle message.
4. Kết quả test được **commit vào nguồn quan sát có thẩm quyền** và có cùng syntheticId.
5. Outcome thỏa **deadline**, ví dụ 20 giây ở sandbox hoặc một mức đã chọn phù hợp production-safe synthetic.
6. Không có duplicate side effect, DLQ hoặc kết quả sai được bỏ qua để báo PASS.

Khi FAIL, lưu **stage cuối đã thành công**, correlation ID, broker/queue name, timeouts, retry attempts; không gửi lại vô hạn với **syntheticId mới** khiến dashboard báo ảo rằng lúc nào cũng có progress.

### 11.3. Test command không thay thế business instrumentation

Một synthetic mỗi 5 phút có thể vẫn PASS khi một phiên bản schema production khác thất bại toàn bộ. Vì vậy cần kết hợp:

- **Synthetic** để chứng minh một đường E2E chuẩn còn hoạt động.
- **Real traffic metrics** để phát hiện segment/tenant/schema cụ thể bị stall.
- **DLQ/expiry/reconciliation** để nhìn nhánh lỗi.
- **Business state** để xác minh outcome chứ không chỉ JMS ACK.

Synthetic là **bằng chứng bổ sung**, không phải giấy chứng nhận mọi message thật đều đã xử lý đúng.

## 12. Hai broker, nhiều queue hoặc nhiều tenant: health theo đường đi

Một hệ thống nhiều broker có thể như sau:

~~~text
Orders Classic A
    → network bridge (store-and-forward)
    → Orders Classic B
    → Consumer
    → Database

Payments Artemis
    → Billing worker
    → Payment provider
~~~

Đừng có một biểu tượng **ALL BROKERS UP** rồi kết luận cả hai luồng order/payment khỏe.

### 12.1. Health graph theo dependency

| Thành phần | Tín hiệu hợp lý | Khi fail |
|---|---|---|
| **Classic A liveness** | JVM process/heartbeat | Có thể cần broker restart/recovery |
| **Classic A readiness** | OpenWire auth + send route + store headroom | Producer mới cần giảm tốc/đổi route |
| **Classic A→B bridge health** | Bridge connected, demand hiện diện, forward rate | Cần kiểm tra connector, remote consumer, TTL |
| **Classic B readiness** | JMS consume path cho worker | Chỉ phản ánh đường B, chưa có DB outcome |
| **Orders business progress** | orderId terminal outcome, backlog age | Điều tra bridge/consumer/DB theo stage |
| **Artemis Payments readiness** | Core/TLS/auth, address/queue, persistent send | Lỗi ingress payments |
| **Payments business progress** | paymentAttemptId terminal outcome và reconciliations | Lỗi worker/API/DB hoặc idempotency |

**Network bridge connected không chứng minh có demand.** Classic demand forwarding có thể giữ pending messages ở A khi B không có consumer; đây có thể là chính sách đúng hoặc là sự cố tiến triển nghiệp vụ, tùy mong đợi.

### 12.2. Readiness toàn ứng dụng có thể khác từng broker

Một ứng dụng Java dùng **ordersConnectionFactory** và **billingConnectionFactory** có thể phục vụ API chỉ đọc Orders khi Billing down. Nếu gộp readiness = “cả Orders và Billing phải UP”, scheduler có thể loại toàn bộ instance khỏi Service, khiến cả chức năng Orders không lỗi cũng bị ảnh hưởng.

Thiết kế readiness theo **critical path của mỗi endpoint/workload**, hoặc tách Deployment/Service khi dependency khác nhau. Với broker StatefulSet một node, readiness=false có thể khiến Service không có endpoint nào, nên phải có hành vi client/retry/HA được tính trước; không “remove traffic” mà quên toàn hệ không còn đích.

## 13. Runbook chẩn đoán: đi từ dấu hiệu đến lớp lỗi

### 13.1. Trường hợp A — Process sống, JMS readiness fail

1. Xác minh **JVM/process liveness** và broker role (live/backup/recovery).
2. Kiểm tra **đúng listener/port/protocol**, DNS, TLS handshake và credential.
3. Xác minh probe dùng queue và principal nào; browse permission có bị đổi không?
4. Xem broker **journal/paging/store/temp usage**, disk free và flow control.
5. Nếu broker đang recovery, xem thời gian khởi động và startup probe grace period.
6. Kiểm tra queue topology/auto-create; không “fix” bằng quyền admin wildcard.
7. Chỉ restart nếu chứng cứ cho thấy tiến trình không hồi phục; nếu issue là TLS/ACL/disk, xử lý đúng lớp.

**Không** cho một probe đổi password sai làm tất cả broker Pods restart.

### 13.2. Trường hợp B — Readiness PASS nhưng business progress FAIL

1. Có work thật không? Kiểm tra **accepted_total**, **inflight_count** và **oldest_unfinished_age**.
2. Xác minh destination/queue/subscription đúng tên và đúng broker.
3. Đọc **pending, delivering/inflight, consumerCount, enqueue/dequeue**.
4. Kiểm tra worker thread pool, processing latency, timeouts, DB locks và external API.
5. Phân biệt consumer **ACK trước** hay **sau khi business commit**.
6. Đọc retry/redelivery và DLQ, phân loại poison message/schema.
7. Đối soát theo business ID và xác nhận terminal outcome trước khi gọi là recovered.
8. Giữ broker chạy nếu nó vẫn hoạt động đúng; sửa consumer/downstream hoặc flow control.

**Điển hình:** broker UP, QueueSize=50.000, consumerCount=2 nhưng **terminal_total không tăng** và oldest age vượt deadline. Khả năng cao luồng xử lý bị nghẽn, không phải mạng tới broker mất.

### 13.3. Trường hợp C — Business metrics “không có dữ liệu”

Phân biệt ba trạng thái:

- **No traffic expected:** không có accepted tasks, inflight=0; processed rate=0 hợp lệ.
- **Telemetry missing:** Prometheus không scrape exporter, metrics series biến mất; không được coi là business khỏe.
- **Flow stalled:** có work chưa hoàn tất, age tăng và terminal outcomes không tăng.

Đặt alert riêng cho **metric availability**; không lấp missing metrics bằng số 0 tùy tiện trong dashboard rồi kết luận business stalled hay healthy.

### 13.4. Trường hợp D — Broker NotReady nhưng consumer đang drain

Một broker đang chặn writes vì storage pressure, nhưng consumer còn ACK được backlog. Nếu Kubernetes readiness=false làm các producer ngừng gửi mới, đây **có thể là hành vi bảo vệ phù hợp**. Restart broker ngay có thể mất cơ hội drain và khiến redelivery tăng.

Kiểm tra:

- Readiness failure thuộc **producer write path** hay cả read path?
- Consumer đang giảm QueueSize/oldest age không?
- Storage headroom có phục hồi theo ACK không?
- Client có tuyến HA khác an toàn không?
- Có cần rate-limit producer hoặc mở rộng disk không?

Hành động đúng có thể là **giảm ingress, tiếp tục drain, theo dõi recovery**.

## 14. Bài thực hành có tiêu chí nghiệm thu

### Lab A — TCP port UP, JMS auth thất bại

1. Chạy Artemis hoặc Classic sandbox; xác nhận protocol TCP listener mở.
2. Dùng TCP probe kiểm tra có thể connect.
3. Đưa credential probe sai vào **BrokerReadiness**.
4. Quan sát TCP vẫn UP nhưng Java readiness FAIL.
5. Khôi phục credential tối thiểu và kiểm tra PASS.

**Đạt:** giải thích được transport reachability khác authenticated JMS readiness, và broker không nên bị restart vì sai secret.

### Lab B — Broker process sống, consumer dừng

1. Producer gửi các command test có **business ID** ổn định.
2. Dừng consumer nhưng giữ broker chạy.
3. Quan sát JMS probe PASS, queue pending/oldest age tăng.
4. Đo **business terminal outcomes** không tăng.
5. Start consumer lại, đối chiếu số terminal outcomes và backlog age.

**Đạt:** chỉ ra lỗi business progress dù broker liveness và readiness vẫn đạt.

### Lab C — Không có traffic trong 30 phút

1. Dừng producer test, drain hết backlog.
2. Xác minh **unfinished_count=0**.
3. Giữ consumer đang chạy nhưng processed rate=0.
4. Kiểm tra rule **PaymentFlowStalled** không firing.
5. Tạo một tác vụ quá deadline có chủ đích, quan sát rule chỉ firing khi cả old work và no progress đồng thời đúng.

**Đạt:** phân biệt idle bình thường với stall có work.

### Lab D — Synthetic loopback không đi qua business worker

1. Provision queue **ops.synthetic.loopback**.
2. Chạy **ArtemisSyntheticLoopback**, quan sát PASS.
3. Dừng payment worker thật.
4. Chạy lại loopback, nó có thể vẫn PASS.
5. Đọc business_flow metrics, thấy backlog/domain outcomes không tiến triển.

**Đạt:** hiểu synthetic JMS data-plane PASS **không** chứng minh business E2E PASS.

### Lab E — Transaction chưa commit và ACK giả

1. Trong sandbox, viết consumer test nhận message nhưng để DB transaction cố ý rollback.
2. So sánh hai phiên bản: (a) consumer ACK/return trước DB commit; (b) xử lý đúng transaction/idempotency rồi mới JMS ACK.
3. Quan sát trường hợp (a) queue giảm nhưng không có terminal result.
4. Quan sát trường hợp (b) retry/redelivery và terminal result đúng business ID.
5. Ghi failure windows và nguồn sự thật cho outcome.

**Đạt:** không lấy DequeueCount làm thước đo duy nhất cho business success.

### Lab F — HA standby không phải broker chết

1. Trong topology HA sandbox được hỗ trợ, khởi động một node ở vai trò backup.
2. Xác nhận JVM/process alive nhưng chưa phục vụ data plane live theo hợp đồng.
3. Kiểm tra readiness theo role; không để liveness restart vòng lặp trên backup.
4. Thực hiện failover có kiểm soát, quan sát node được kích hoạt bắt đầu ready.
5. Đọc redelivery và pending messages sau failover.

**Đạt:** phân biệt liveness của process với readiness của **vai trò phục vụ**.

### Lab G — Store pressure gây producer backpressure

1. Dùng broker sandbox và quota nhỏ có chủ đích, nhưng **không lấp đầy disk thật của host**.
2. Gửi persistent messages với rate limit, giảm consumer throughput.
3. Quan sát store/page usage, send latency hoặc policy block.
4. Giữ consumer drain, đọc QueueSize/oldest age giảm.
5. Giảm ingress hoặc khôi phục quota, không dùng restart/purge như giải pháp đầu tiên.

**Đạt:** readiness producer có thể suy giảm vì storage trong khi liveness bình thường.

### Lab H — Exporter lỗi, broker vẫn phục vụ

1. Cho Classic/Artemis broker chạy và JMS producer/consumer vẫn giao dịch.
2. Tạm ngừng exporter/Jolokia scrape hoặc đổi read-only monitoring credentials trong sandbox.
3. Quan sát **Prometheus up=0** nhưng JMS data path có thể PASS.
4. Khôi phục exporter; bảo đảm alert được phân loại **monitoring degraded**, không tự gắn business down.
5. Xác minh management endpoint không bị mở public để “sửa scrape”.

**Đạt:** phân biệt observability failure với liveness, readiness và business outcome.

## 15. Checklist trước khi đưa health checks vào production

- [ ] Có định nghĩa **liveness**, **readiness theo workload** và **business progress** tách biệt.
- [ ] Liveness không phụ thuộc DB/API/broker thứ hai để tránh restart cascade.
- [ ] TCP listener check được ghi nhãn reachability, không gọi là end-to-end success.
- [ ] Readiness kiểm tra đúng protocol, credential, role, destination và, khi cần, persistent write capability.
- [ ] Passive/backup HA không bị restart vô hạn chỉ vì không ở vai trò live.
- [ ] Không mặc nhiên coi console/Jolokia HTTP response là JMS data-plane readiness.
- [ ] Probe credential có quyền hẹp, không có admin wildcard, không consume queue nghiệp vụ.
- [ ] Synthetic JMS dùng queue riêng, probe ID riêng, TTL/cadence và cleanup được quản lý.
- [ ] Synthetic business đi qua handler thật nhưng hoàn toàn an toàn với side effects.
- [ ] Có metrics theo **business ID**, terminal outcome sau commit và oldest unfinished age.
- [ ] Processed rate = 0 chỉ cảnh báo nếu có work theo hợp đồng và vượt SLO.
- [ ] Có alert **telemetry missing/exporter down** riêng, không im lặng hoặc suy luận khỏe.
- [ ] Broker queue metrics, DLQ, retries, consumerCount, inflight, storage và business metrics được đối chiếu.
- [ ] K8s readiness=false không bị nhầm là kill; liveness failure có restart budget và startup grace.
- [ ] Long-lived JMS connections, routing/HA và Service endpoint changes đã được fault-test.
- [ ] Có runbook riêng cho process chết, data-plane not ready, stalled business và scrape failure.
- [ ] SLO được định nghĩa từ **accepted_at đến terminal_at** theo nghiệp vụ, không chỉ từ JMS ACK.
- [ ] Đã thử idle, backlog, bad credentials, storage pressure, consumer down và failover trong sandbox.

**Kết luận:** Một broker **còn sống** nghĩa là tiến trình chưa gặp lỗi khiến nó phải khởi động lại; broker **sẵn sàng** nghĩa là một đường JMS cụ thể có thể phục vụ client đúng vai trò và điều kiện tài nguyên; **luồng nghiệp vụ còn hoạt động** chỉ được chứng minh khi các business IDs có kết quả cuối **được ghi bền vững trong SLO**. Với ActiveMQ Classic và Artemis, phải kết hợp **JVM/process signal, JMS probes, broker management metrics và outcome metrics từ ứng dụng**, nhưng tuyệt đối không dùng một kiểm tra TCP/JMX hoặc ACK count để thay thế tất cả. Phân biệt đúng ba cấp này giúp phản ứng chính xác: **restart khi runtime không hồi phục, điều tiết traffic khi broker không ready và điều tra consumer/downstream khi business stalled**.
