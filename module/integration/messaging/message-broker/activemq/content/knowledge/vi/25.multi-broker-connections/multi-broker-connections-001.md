# Classic network of brokers và cơ chế store-and-forward

> **Chương:** Kết nối nhiều broker  
> **Phạm vi:** Apache ActiveMQ **Classic**, network connectors, demand forwarding, persistent storage (KahaDB), Java/JMS và kiểm chứng khi đường nối broker mất/phục hồi. Đây không phải cơ chế cluster/federation của Artemis hoặc broker HA dùng shared store.

Một hệ thống có producer đặt gần broker **A**, còn các worker xử lý đặt gần broker **B**. Producer chỉ gửi message cho A và worker chỉ nhận từ B. **Network of brokers** của ActiveMQ Classic cho phép A tạo một network bridge đến B; khi B có nhu cầu nhận phù hợp, A có thể chuyển tiếp message sang B. Nếu đường mạng gián đoạn, **persistent message đã commit và chưa được tiêu thụ có thể được giữ tại A**, chờ liên kết và remote consumer demand được khôi phục.

Từ khóa quan trọng là **demand**. Network of brokers **không tự động sao chép tất cả queues**, không bảo đảm cùng một message luôn tồn tại trên hai KahaDB và không biến A/B thành một broker logic duy nhất. Hiểu nhầm store-and-forward thành replication rất dễ dẫn tới sai thiết kế HA, sai dự trù disk và những lỗi xử lý trùng ở consumer.

## 1. Phân biệt message forwarding, phân phối tải và HA

| Nhu cầu | Classic network of brokers làm được gì? | Điều không được suy luận |
|---|---|---|
| Consumer B xử lý message được producer gửi tới A | A có thể forward qua network bridge theo demand từ B | B tự sở hữu toàn bộ backlog của A |
| Giữ message khi A–B bị đứt | A có thể giữ **persistent** backlog trong store của chính mình | Non-persistent message luôn sống qua crash |
| Worker ở A và B cùng tiêu thụ queue | Network consumer có thể cạnh tranh với local consumers | Có một queue vật lý dùng chung hay global FIFO |
| Một broker bị mất hoàn toàn | Network bridge có thể kết nối các broker còn khỏe theo topology | B tự là standby backup của A với bản sao hoàn chỉnh |
| Đảm bảo nghiệp vụ chỉ thực thi một lần | Không đáp ứng một mình | JMS ACK, forwarding và DB commit có một transaction nguyên tử |
| Kết nối broker Classic với Artemis | Cần cơ chế/protocol tương thích được thiết kế riêng | Copy XML networkConnector Classic vào Artemis broker.xml |

### 1.1. Sơ đồ cơ bản

~~~mermaid
flowchart LR
    P["Producer Java/JMS"] --> A["Classic Broker A<br/>KahaDB riêng"]
    A == "Network bridge<br/>theo demand" ==> B["Classic Broker B<br/>KahaDB riêng"]
    B --> C["Consumer Java/JMS"]
    L["Link A-B bị mất"] -. "Pending persistent<br/>vẫn có thể nằm ở A" .-> A
~~~

Cùng tên queue **LAB.NOB.JOBS** ở A và B **không có nghĩa cùng một cấu trúc dữ liệu**. A có thể lưu message cục bộ, sau đó dispatch cho network consumer và forward tới B. Mỗi broker quản lý storage, client connections và transaction state riêng.

### 1.2. Ví dụ message nghiệp vụ

~~~text
Destination: LAB.NOB.JOBS
DeliveryMode: PERSISTENT
commandId: cmd-4001
Body: {"type":"ReserveStock","orderId":"OD-1042"}

Producer kết nối A.
Fulfillment consumer kết nối B.
~~~

Consumer B có thể nhận **cmd-4001** khi network bridge tạo được đường forwarding phù hợp. Ngược lại, nếu B chưa có remote consumer demand và bridge chỉ hoạt động theo demand, **A có thể giữ message**, dù socket A–B vẫn kết nối.

**Bridge connected khác message forwarded; forwarded khác business completed.** Bốn trạng thái cần quan sát riêng: producer commit tại A, pending/demand trên A, message xuất hiện/dispatch tại B, và consumer B commit nghiệp vụ/JMS ACK.

## 2. Network connector khác transport connector

ActiveMQ Classic có hai nhóm cấu hình:

- **transportConnector:** endpoint mà broker mở cho client hoặc broker khác kết nối tới, ví dụ OpenWire TCP.
- **networkConnector:** cấu hình một broker chủ động tạo network bridge đến broker khác và xử lý demand subscriptions/destination forwarding.

~~~text
Producer → Broker A :61616       (transportConnector của A)

Broker A:
    networkConnector → static:(tcp://127.0.0.1:61617)
                                    |
                                    v
                             Broker B :61617
                             (transportConnector của B)

Consumer → Broker B :61617
~~~

Một **TCP dial A → B** không được diễn giải máy móc rằng toàn bộ traffic và tất cả destinations luôn chỉ đi A → B. Loại bridge, remote consumer demand, duplex, destination filters và broker routing mới quyết định message được phép di chuyển ra sao.

### 2.1. Demand forwarding hoạt động như thế nào?

~~~mermaid
sequenceDiagram
    participant C as Consumer B
    participant B as Broker B
    participant N as Network bridge A-B
    participant A as Broker A
    C->>B: Subscribe LAB.NOB.JOBS
    B->>N: Consumer demand qua advisory
    N->>A: Tạo network consumer phù hợp
    Note over A: Queue có pending message
    A->>N: Dispatch message theo demand
    N->>B: Forward tới remote destination
    B->>C: Deliver message
    C->>B: ACK / commit receive
~~~

Đây là trình tự **logic**, không mô tả chính xác từng frame, message journal record hoặc transaction nội bộ của mọi phiên bản Classic. Trong thực tế broker có thể prefetch/dispatch, quản lý network consumer acknowledgments và sử dụng persistence theo implementation.

Network bridges dựa vào thông tin **consumer advisories** để biết remote subscriptions. Tùy tiện tắt advisory support hoặc làm mất quyền/đường truyền advisory cần thiết có thể khiến bridge không phát hiện nhu cầu từ B.

### 2.2. Vì sao demand khác replication?

- **Demand-driven forwarding:** có remote consumer/subscription phù hợp, A mới có lý do chuyển message qua bridge.
- **Replication:** sao chép state/records để khôi phục khi một node mất, không phụ thuộc consumer B có online hay không.

Network of brokers mặc định gần với mô hình thứ nhất. Có thể chủ động cấu hình những dạng static demand/forced forwarding theo version, nhưng đó là thay đổi chính sách định tuyến, **không tự biến hai brokers thành HA replication**.

## 3. Cấu hình lab hai ActiveMQ Classic brokers

Chạy **hai tiến trình Classic riêng**, với các giá trị kiểm thử:

| Broker | brokerName | OpenWire TCP | KahaDB |
|---|---|---|---|
| A | **nob-a** | **127.0.0.1:61616** | **data/nob-a/kahadb** |
| B | **nob-b** | **127.0.0.1:61617** | **data/nob-b/kahadb** |

Hai broker phải có **data directory độc lập**. Không để hai tiến trình đồng thời sử dụng chung KahaDB. Vì A và B trên cùng host lab, các URI dùng loopback; khi chạy trên hai hosts, phải dùng DNS/IP private và mở firewall/TLS thích hợp.

### 3.1. Broker A: kết nối sang B

Những fragment sau phải được chèn **bên trong broker element tương ứng của Classic activemq.xml**:

~~~xml
<!-- Broker A, Classic activemq.xml -->
<persistenceAdapter>
    <kahaDB directory="data/nob-a/kahadb"/>
</persistenceAdapter>

<transportConnectors>
    <transportConnector name="openwire-a"
                        uri="tcp://127.0.0.1:61616"/>
</transportConnectors>

<networkConnectors>
    <networkConnector
            name="a-to-b"
            uri="static:(tcp://127.0.0.1:61617)"
            networkTTL="1"
            duplex="false"
            dynamicOnly="true"
            conduitSubscriptions="true"
            decreaseNetworkConsumerPriority="true">
        <dynamicallyIncludedDestinations>
            <queue physicalName="LAB.NOB.JOBS"/>
        </dynamicallyIncludedDestinations>
    </networkConnector>
</networkConnectors>
~~~

Giải thích:

- **static:(...)** là danh sách endpoint remote tường minh, không phải multicast discovery.
- **networkTTL=1** phù hợp topo một network hop A → B. **Không phải JMS message time-to-live tính bằng giây.**
- **duplex=false** giúp lab đơn giản, một connector do A khởi tạo thay vì cấu hình các đường đối xứng chưa kiểm chứng.
- **dynamicOnly=true** yêu cầu remote dynamic demand; nếu B không có consumer trên queue này, A **không bắt buộc chuyển** backlog.
- **conduitSubscriptions=true** cho phép gộp network subscriptions tương thích, giảm forward thừa trong những trường hợp phù hợp.
- **decreaseNetworkConsumerPriority=true** giúp ưu tiên consumer cục bộ so với network consumers khi cấu hình có hiệu lực, nhưng không tạo cam kết local-first tuyệt đối.
- **dynamicallyIncludedDestinations** giới hạn bridge vào queue được giao. Tránh wildcard toàn bộ queues của production.

**Đặc biệt:** chữ **static** trong URI chỉ là cách tìm broker remote; chữ **dynamic** trong **dynamicOnly** chỉ nhu cầu consumer. Hai khái niệm không đối lập nhau.

### 3.2. Broker B: listener, chưa cần networkConnector ngược

~~~xml
<!-- Broker B, Classic activemq.xml -->
<persistenceAdapter>
    <kahaDB directory="data/nob-b/kahadb"/>
</persistenceAdapter>

<transportConnectors>
    <transportConnector name="openwire-b"
                        uri="tcp://127.0.0.1:61617"/>
</transportConnectors>
~~~

B phải đặt **brokerName=nob-b** trong broker configuration, A là **nob-a**; không dùng chung brokerName hay data directory. Với lab một chiều theo demand, **B không cần thêm networkConnector tới A**. Thêm bridge đối xứng không có thiết kế có thể tạo duplicate network demand, loops hoặc đường forwarding khó quan sát.

**Các fragment không phải file activemq.xml hoàn chỉnh.** Nếu file đang có **persistenceAdapter**, **transportConnectors** hoặc **networkConnectors**, thêm/sửa entry ở đúng nơi; không nhân đôi cả phần tử gốc. Kiểm tra namespace Classic của XML và **server startup logs** để biết broker đã parse config và bridge kết nối thành công.

### 3.3. Phân quyền và kết nối thật

Ví dụ lab chưa có credentials/TLS. Trên production phải:

1. Dùng transport có TLS phù hợp (ví dụ Classic SSL/OpenWire transport đã cấu hình đúng keystore/truststore).
2. Cấp bridge principal/credentials chuyên dụng; không dùng admin wildcard.
3. Giới hạn TCP source Broker A → Broker B bằng private network/firewall.
4. Chỉ cho phép bridge subscriptions/destinations đúng hợp đồng, kể cả các advisory permissions cần thiết.
5. Bảo vệ JMX/web console riêng; mở OpenWire port không được đồng nghĩa mở console.

Nếu bridge báo authentication failure, **không tắt broker security** để chữa lỗi. Xác định principal, destination authorization và trạng thái advisory, rồi test lại bằng quyền hẹp.

## 4. Store-and-forward: điều kiện chính xác

### 4.1. Một message persistent đi qua những bước nào?

~~~text
1. Producer JMS gửi message PERSISTENT tới A, queue LAB.NOB.JOBS.
2. Producer hoàn tất transaction gửi tại A.
3. A duy trì message/reference ở persistent store theo trạng thái broker.
4. Consumer tại B xuất hiện; advisory/demand đến network bridge.
5. Network consumer ở A có thể dispatch pending message.
6. Bridge chuyển tiếp sang B theo đường và policy cho phép.
7. Consumer B receive và ACK/commit theo session của B.
~~~

Mốc producer **commit tại A** không đồng nghĩa message đã có ở B. Mốc bridge **forward** không đồng nghĩa consumer B đã cập nhật database. Cũng không có một transaction nguyên tử chung bao trùm **KahaDB A, KahaDB B và DB của ứng dụng**.

### 4.2. Link A–B down: broker A vẫn có thể nhận message

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant A as Broker A + KahaDB
    participant N as Network link
    participant B as Broker B
    participant C as Consumer B
    Note over N: Liên kết DOWN
    P->>A: Send PERSISTENT cmd-4001
    A->>A: Commit / lưu tại A
    A-->>P: Send OK
    Note over A: Message đang pending tại A
    Note over N: Liên kết UP
    C->>B: Subscribe queue
    B->>N: Demand được truyền khi bridge hoạt động
    N->>A: Tạo network consumer
    A->>N: Forward cmd-4001
    N->>B: Route message
    B->>C: Deliver message
~~~

Để message vẫn còn và có thể chuyển sau khi link phục hồi, tối thiểu cần:

- **DeliveryMode.PERSISTENT**, transaction producer đã commit.
- Persistence enabled và **KahaDB A nguyên vẹn**; không mất volume khi restart.
- Message chưa expired, bị quản trị xóa hoặc được consumer khác ACK.
- A/B kết nối lại, credentials và destination filter còn hợp lệ.
- Remote consumer/subscription demand xuất hiện khi bridge dùng dynamicOnly=true.
- Broker không chạm giới hạn disk/store làm quá trình gửi hoặc khôi phục thất bại.

**Nếu B không có consumer demand, A có thể tiếp tục giữ backlog dù network bridge connected.** Đây không phải bằng chứng bridge hỏng.

### 4.3. Một vài kết luận sai thường gặp

| Kết luận nhầm | Giải thích đúng |
|---|---|
| “A send OK thì B đã có message.” | Chỉ chứng minh kết quả gửi phía A theo transaction/transport. |
| “Bridge connected thì tự drain hết A.” | Cần remote demand và destination phù hợp nếu demand-driven. |
| “Persistent message thì B chắc chắn có bản sao khi A mất disk.” | Persistent message chưa forward có thể chỉ có ở KahaDB A. |
| “Store-and-forward đảm bảo exactly-once.” | Producer retry, bridge ACK ambiguity, consumer redelivery vẫn gây duplicate. |
| “Network TTL=1 nghĩa là message hết hạn sau một giây.” | Đây là giới hạn network hop, không phải JMS TTL. |
| “A và B là một queue global.” | Mỗi broker sở hữu queue/message state độc lập; không có global FIFO. |

## 5. Những thuộc tính networkConnector cần hiểu

| Tùy chọn | Tác dụng | Nguy cơ diễn giải sai |
|---|---|---|
| **uri** | Cách tìm endpoint remote (static, discovery hoặc transport khác phù hợp) | Đưa Artemis Core URI vào connector Classic mà không kiểm tra protocol |
| **networkTTL** | Hạn số network hops cho message/subscription | Nhầm với thời gian tồn tại JMS message |
| **duplex** | Cơ chế kết nối bridge hai chiều qua một liên kết khi được hỗ trợ | Tạo trùng connector đối xứng |
| **dynamicOnly** | Giới hạn forwarding theo dynamic demand | Kỳ vọng B lưu tất cả khi consumer offline |
| **conduitSubscriptions** | Gộp subscriptions tương thích theo bridge policy | Coi là business dedup |
| **decreaseNetworkConsumerPriority** | Tăng thiên hướng ưu tiên local consumer | Tưởng luôn local-first tuyệt đối |
| **suppressDuplicateQueueSubscriptions** | Hạn chế remote queue demand trùng trong topology có nhiều đường | Coi là exactly-once delivery |
| **dynamicallyIncludedDestinations** | Allowlist destinations có thể forward theo demand | Dùng wildcard quá rộng, vượt trust boundary |
| **excludedDestinations** | Loại những destinations không được forward | Quên loại DLQ/admin queue |
| **prefetchSize** khi hỗ trợ | Điều chỉnh dispatch/inflight của network consumer | Tưởng prefetch=1 loại mọi duplicate |

### 5.1. Network hop limit khác TTL thời gian

~~~text
networkTTL=1:
    A → B                  Một network hop
    A → B → C              Không mong muốn đi qua hai hops

JMS time-to-live=15 phút:
    Message có thể hết hạn theo thời gian ngay cả khi
    networkTTL=10 và network bridge còn đường truyền.
~~~

Tăng networkTTL chỉ mở rộng số hops cho phép, **không tạo remote consumer**, không sửa destination filter và không vô hiệu hóa JMS expiration. Với topology ba broker, phải thử cả **demand propagation** lẫn message forwarding theo đúng số hops.

### 5.2. Đừng nhầm static discovery với static forwarding

~~~xml
<networkConnector name="a-to-b"
                  uri="static:(tcp://127.0.0.1:61617)"
                  dynamicOnly="true"
                  networkTTL="1"/>
~~~

**URI static** cho A biết B ở đâu. **dynamicOnly=true** vẫn có nghĩa forwarding dựa trên dynamic demand. Nếu nghiệp vụ yêu cầu chuyển message sang B trước khi consumer B online, cần thiết kế **static subscriptions/static included destinations** phù hợp Classic version và thử hành vi storage ở B, chứ không chỉ nhìn thấy URI có chữ static.

### 5.3. Local consumers và remote network consumers

Khi A có consumer cục bộ và B cũng có consumer, network consumer có thể cạnh tranh để lấy message ở A. **decreaseNetworkConsumerPriority** là công cụ ảnh hưởng ưu tiên dispatch, không phải hợp đồng HA active/passive. Thứ tự thực tế còn chịu tác động của prefetch, timing, message priorities, selectors và các consumers đang available.

Nếu cần mọi message phải được xử lý tại A khi A khỏe và chỉ chuyển B lúc A fail, phải có **cơ chế điều phối consumer/route rõ ràng**. Không dựa duy nhất vào network consumer priority.

### 5.4. Conduit subscriptions đặc biệt quan trọng với topic

Nhiều remote topic subscribers trên B không nhất thiết cần A forward nhiều bản giống hệt trên mỗi network subscription. **conduitSubscriptions** cho phép gộp những network subscriptions phù hợp trong những điều kiện được hỗ trợ, giảm traffic không cần thiết qua bridge.

Nhưng topic subscribers vẫn nhận event theo semantics subscription riêng của chúng. Conduit **không chứng minh nghiệp vụ exactly-once**, và còn phải xét selectors, durable subscribers, broker paths, version và topology nhiều đường.


## 6. Queue, topic và remote subscription không có cùng semantics

### 6.1. Queue: xử lý cạnh tranh, không phải nhân bản mọi bản tin

Với queue **LAB.NOB.JOBS**, một consumer trên A và một consumer trên B có thể cùng tạo nhu cầu xử lý message đã được producer gửi vào A.

~~~text
Producer → Broker A / LAB.NOB.JOBS
                    |
                    +-- Local Consumer A
                    |
                    +-- Network Consumer A→B
                                  |
                                  v
                           Broker B / LAB.NOB.JOBS
                                  |
                           Consumer B
~~~

Một message được dispatch theo một đường tiêu thụ trong điều kiện bình thường, nhưng redelivery vẫn có thể xảy ra khi ACK/transaction không hoàn tất. Không dùng network of brokers để tuyên bố A và B có **một queue duy nhất với global ordering**.

**Tình huống khó:** nếu A đã có local consumer rất nhanh, nhiều messages có thể được xử lý ở A dù B có demand. Nếu A không có consumer, messages có thể đi B khi bridge active. Nếu cả A và B cùng có producers trên queue trùng tên, **thứ tự nghiệp vụ toàn mạng** càng không có cam kết chỉ nhờ JMS queue semantics.

### 6.2. Topic: fan-out hợp lệ và message có thể không được giữ khi offline

~~~mermaid
flowchart LR
    PA["Topic producer A"] --> TA["Topic A<br/>LAB.NOB.EVENTS"]
    TA --> SA["Subscriber A"]
    TA --> NB["Network bridge<br/>remote demand"]
    NB --> TB["Topic B<br/>LAB.NOB.EVENTS"]
    TB --> SB1["Subscriber B1"]
    TB --> SB2["Subscriber B2"]
~~~

Một event topic hợp lệ có thể được giao tới nhiều subscribers. Đó là **fan-out**, không phải duplicate queue processing. **conduitSubscriptions** có thể gộp nhu cầu trên đường bridge để hạn chế chuyển thừa; B vẫn phân phối tới các local subscribers theo subscription semantics của nó.

Với **non-durable topic subscriber**, khi client B offline thì nó không có cam kết nhận các event đã publish trước lúc đăng ký lại. Nếu bridge chỉ forward theo demand và B không có subscriber, A có thể không có lý do giữ event để chuyển sau.

Với **durable subscription**, cần thiết kế và kiểm thử riêng: client ID, subscription name, subscriber lifecycle, bridge demand propagation, networkTTL và policy của Classic version. Đừng suy rằng chỉ cần tạo một durable subscriber ở B là tất cả event đã phát từ A khi link down chắc chắn được lưu cho nó.

### 6.3. Temporary destinations và request–reply

**JMSReplyTo** có thể chứa TemporaryQueue. Destination tạm phụ thuộc connection tạo ra nó; routing qua broker network không tự đảm bảo reply đến được sau khi requester disconnect. Nếu có request–reply xuyên broker:

1. Kiểm tra bridge có hỗ trợ và được cấu hình forward temporary destinations theo topology không.
2. Đảm bảo chiều reply có đường và quyền send hợp lệ.
3. Không dùng TemporaryQueue làm nơi giữ kết quả đến muộn sau requester restart.
4. Dùng **requestId/correlationId** ổn định và reply queue có vòng đời phù hợp nếu cần recovery.

### 6.4. DLQ và advisory destinations

Không forward **DLQ** như một queue nghiệp vụ chỉ vì wildcard match tất cả destinations. DLQ thuộc quy trình điều tra/replay có owner rõ; chuyển DLQ sang broker khác có thể che nguyên nhân lỗi.

Advisory topics giúp bridge nhận consumer demand và các thông tin broker cần thiết, nhưng không có nghĩa mọi application user nên được quyền đọc mọi advisory. Khi bật authentication/authorization, kiểm tra quyền của **bridge principal** theo cấu hình Classic tương ứng.

## 7. Lab Java/JMS: gửi tại A, nhận tại B

Bài thực hành dùng **Classic JMS client** thuộc thế hệ **javax.jms** và **OpenWire TCP**. Ví dụ API tương thích JMS 1.1; với Spring Boot 3/Jakarta Messaging phải dùng client Jakarta đúng phiên bản và đổi import đồng bộ.

### 7.1. Điều kiện thực hành

- Hai broker Classic độc lập đã chạy: A **127.0.0.1:61616**, B **127.0.0.1:61617**.
- Network connector **a-to-b** của A đang kết nối được B.
- Queue **LAB.NOB.JOBS** dùng trong lab; không có dữ liệu production.
- Hai data directories KahaDB khác nhau và persistence enabled.
- Nếu bật authentication, cấp **MQ_USER/MQ_PASSWORD** cùng quyền đúng của lab. Nếu bridge dùng user khác, cấp quyền forwarding riêng.
- Có management console hoặc JMX để đọc queue metrics và bridge state.

### 7.2. Chương trình gửi và nhận

Tập tin **ClassicNetworkBridgeLab.java**:

~~~java
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.JMSException;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class ClassicNetworkBridgeLab {
    private static final String QUEUE = "LAB.NOB.JOBS";
    private static final String A = "tcp://127.0.0.1:61616";
    private static final String B = "tcp://127.0.0.1:61617";

    public static void main(String[] args) throws Exception {
        if (args.length == 2 && "send".equals(args[0])) {
            sendToA(args[1]);
        } else if (args.length == 1
                && "consume-b".equals(args[0])) {
            receiveFrom(B);
        } else if (args.length == 1
                && "consume-a".equals(args[0])) {
            receiveFrom(A);
        } else {
            System.out.println(
                "Usage: send <commandId> | consume-b | consume-a");
        }
    }

    private static void sendToA(String commandId)
            throws Exception {
        Connection conn = connect(A);
        try {
            Session session = conn.createSession(
                true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue(QUEUE);
                MessageProducer producer =
                    session.createProducer(queue);
                try {
                    producer.setDeliveryMode(DeliveryMode.PERSISTENT);

                    TextMessage message = session.createTextMessage(
                        "{\"type\":\"ReserveStock\","
                        + "\"orderId\":\"OD-1042\"}");
                    message.setStringProperty(
                        "commandId", commandId);

                    producer.send(message);
                    session.commit();

                    System.out.println(
                        "Committed on A, commandId=" + commandId
                        + ", JMSMessageID="
                        + message.getJMSMessageID());
                } catch (Exception error) {
                    session.rollback();
                    throw error;
                } finally {
                    producer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            conn.close();
        }
    }

    private static void receiveFrom(String brokerUrl)
            throws Exception {
        Connection conn = connect(brokerUrl);
        try {
            Session session = conn.createSession(
                true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue(QUEUE);
                MessageConsumer consumer =
                    session.createConsumer(queue);
                try {
                    conn.start();
                    Message received = consumer.receive(15000);

                    if (received == null) {
                        System.out.println(
                            "No message at " + brokerUrl);
                        return;
                    }

                    try {
                        if (!(received instanceof TextMessage)) {
                            throw new IllegalStateException(
                                "Expected TextMessage");
                        }
                        TextMessage msg = (TextMessage) received;
                        System.out.println(
                            "Received at " + brokerUrl
                            + ", commandId="
                            + msg.getStringProperty("commandId")
                            + ", JMSMessageID="
                            + msg.getJMSMessageID()
                            + ", redelivered="
                            + msg.getJMSRedelivered()
                            + ", body=" + msg.getText());

                        // LAB ONLY: không gọi DB hay API nghiệp vụ.
                        session.commit();
                    } catch (Exception error) {
                        session.rollback();
                        throw error;
                    }
                } finally {
                    consumer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            conn.close();
        }
    }

    private static Connection connect(String url)
            throws JMSException {
        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(url);

        String user = System.getenv("MQ_USER");
        String pass = System.getenv("MQ_PASSWORD");

        if (user != null && !user.trim().isEmpty()) {
            return factory.createConnection(user, pass);
        }
        return factory.createConnection();
    }
}
~~~

**Lưu ý:**

- Client cần dependency **org.apache.activemq:activemq-client** đúng thế hệ **javax.jms** và version Classic. Không biên dịch Java thuần thiếu thư viện.
- Hàm **sendToA** nhận **commandId** làm argument. Khi retry cùng một tác vụ logic, phải **dùng lại commandId**, không sinh một ID mới cho mỗi send attempt.
- **SESSION_TRANSACTED** giúp ví dụ chỉ rõ commit JMS ở A và B, nhưng không tạo cross-broker XA hoặc bảo đảm xử lý DB đúng một lần.
- Khi **receive(15000)** trả về null, consumer không có message để commit; nguyên nhân có thể là thiếu remote demand, bridge chưa active hoặc queue khác, không chỉ là producer lỗi.
- Kết quả in ra chỉ phản ánh lab, **không chứng minh business side effect thành công**.

### 7.3. Lab A — Demand xuất hiện trước khi gửi

Chạy trong sandbox:

~~~text
Terminal 1: java ClassicNetworkBridgeLab consume-b
Terminal 2: java ClassicNetworkBridgeLab send cmd-4001
~~~

Kết quả mong đợi: consumer trên B nhận message có **commandId=cmd-4001** mặc dù producer kết nối trực tiếp A. Xác minh bằng bridge state và queue metrics của A/B; không chỉ dựa trên log ứng dụng.

**Đạt:** giải thích được vai trò của remote consumer demand và network consumer tại A.

### 7.4. Lab B — Link khỏe nhưng B chưa có consumer

1. Dừng mọi consumer tại A và B.
2. Đảm bảo bridge A–B đang connected.
3. Gửi **cmd-4002** vào A.
4. Quan sát message pending tại A; đợi đủ thời gian để không nhầm với reconnect delay.
5. Start **consume-b**, quan sát demand xuất hiện và message đến B.
6. Kiểm tra B nhận đúng commandId, rồi commit receive.

**Đạt:** thấy **dynamicOnly=true** không tự forward toàn bộ backlog khi không có remote demand.

### 7.5. Lab C — B offline trong lúc producer tiếp tục gửi tại A

1. Dừng broker B, giữ A hoạt động.
2. Gửi **cmd-4003** và **cmd-4004** tới A bằng persistent send/commit.
3. Kiểm tra queue A còn pending messages và KahaDB A vẫn hợp lệ.
4. Start broker B, chờ network bridge reconnect.
5. Start **consume-b** đủ số lần; kiểm tra cả hai command IDs.
6. Đo thời gian drain backlog và queue counts A/B.

**Đạt:** mô tả được **store-and-forward của A** khi link down; không kết luận B có bản sao trước khi liên kết hồi phục.

### 7.6. Lab D — Có consumer ở A lẫn B

1. Start **consume-a** và **consume-b** cùng lúc.
2. Gửi 20 commandIds khác nhau vào A.
3. Quan sát consumer nào nhận message nào.
4. Thử **decreaseNetworkConsumerPriority** trong broker lab, restart/reload đúng theo version.
5. Ghi kết quả theo messageId/commandId và thời gian.

**Đạt:** nhận biết local/remote consumer là các đường tiêu thụ cạnh tranh và **không có cam kết chia đều 50/50 hoặc local-first tuyệt đối**.

## 8. Các cửa sổ lỗi làm message bị gửi hoặc xử lý trùng

### 8.1. Producer không chắc A đã commit

~~~text
t1: Producer gửi commandId=cmd-4001 tới broker A.
t2: A có thể đã commit persistent message.
t3: Network producer–A đứt trước phản hồi.
t4: Producer retry cùng commandId=cmd-4001.
t5: A có thể nhận thêm một message của cùng thao tác logic.
~~~

Network of brokers không tự biết hai **send attempts** là cùng một tác vụ nghiệp vụ chỉ vì body giống nhau. Dùng **commandId/eventId** ổn định và cơ chế idempotent consumer. Không dựa vào một **JMSMessageID** do provider cấp cho từng lần gửi mới để dedupe.

### 8.2. Bridge forward nhưng ACK local chưa rõ

~~~mermaid
sequenceDiagram
    participant A as Broker A
    participant N as Network Bridge
    participant B as Broker B
    A->>N: Dispatch cmd-4001
    N->>B: Forward message
    B-->>N: Kết quả forward
    Note over A,N: Đứt link trước khi A hoàn tất ACK
    A->>N: Có thể dispatch lại khi hồi phục
    N->>B: Có thể có bản forward thứ hai
~~~

Bridge có cơ chế xử lý network dispatch/ACK riêng, nhưng **không có một business transaction chung giữa hai stores**. Khi kết quả forward không chắc chắn, phải tính đến khả năng message bị giao lại ở đường network. Quan sát phụ thuộc Classic version, topology, prefetch và chính sách bridge.

### 8.3. Consumer B xử lý DB xong nhưng chưa commit JMS

~~~text
t1: Consumer B nhận cmd-4001.
t2: Database commit hiệu ứng nghiệp vụ.
t3: Process crash trước JMS session commit.
t4: Broker B có thể redeliver cmd-4001.
t5: Consumer phải phát hiện cmd-4001 đã xử lý.
~~~

Đây là **consumer redelivery**, không thể sửa bằng cách tăng networkTTL hoặc đổi direction của network connector.

### 8.4. Inbox và business idempotency

Bảng chống trùng minh họa trên PostgreSQL:

~~~sql
CREATE TABLE processed_commands (
    consumer_name TEXT NOT NULL,
    command_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, command_id)
);
~~~

Consumer nhận commandId và thực hiện:

~~~text
BEGIN DATABASE TRANSACTION
  INSERT processed_commands(consumer_name, command_id)
  ON CONFLICT DO NOTHING

  Nếu insert thành công:
      cập nhật nghiệp vụ trong cùng transaction
  Nếu commandId đã có:
      không thực hiện side effect lần hai
COMMIT DATABASE TRANSACTION

COMMIT JMS RECEIVE
~~~

Marker chống trùng và thay đổi nghiệp vụ trong cùng database phải **cùng transaction**; rollback nghiệp vụ phải rollback marker. Nếu có API ngoài (thanh toán/email), transaction SQL không bao trùm API, cần **downstream idempotency key** và cơ chế reconciliation.

**JMSMessageID** của message đi qua bridge có thể được giữ hoặc thay đổi theo provider/đường chuyển tiếp; không sử dụng nó làm khóa của một payment attempt. **commandId/paymentAttemptId** thuộc contract mới có ý nghĩa ổn định khi retry và replay.

## 9. Topology nhiều hops và vòng lặp

### 9.1. A → B → C

~~~mermaid
flowchart LR
    A["Broker A"] == "Bridge A-B" ==> B["Broker B"]
    B == "Bridge B-C" ==> C["Broker C"]
    C --> CC["Consumer C"]
~~~

Để một message của A đến được consumer C qua B, cần **networkTTL đủ số hops**, mỗi bridge đang connected, destination filters cho phép và **remote demand được truyền ngược về A**. Nếu A chỉ dùng networkTTL=1, không kỳ vọng message đi thêm hop thứ hai như thể TTL vô hạn.

Tăng TTL không tự tạo consumer demand hoặc sửa ACL. Khi C không nhận:

- C có consumer/subscription thực tế không?
- B có bridge tới C không?
- A có nhận được nhu cầu thông qua B không?
- Destination được included ở A/B hay bị excluded?
- TTL đủ hop trên tuyến cần thiết không?
- Message có expired theo thời gian không?
- Có local consumer ở A/B nhận message trước không?

### 9.2. Full mesh và các đường trùng

~~~text
A ↔ B
↕   ↕
C ↔ ...  (nhiều network paths)
~~~

Nhiều đường kết nối giữa brokers không mặc nhiên làm hệ thống an toàn hơn. Có thể phát sinh duplicate network demand, message bouncing hoặc dispatch theo đường không mong muốn khi failover. **networkTTL**, **conduitSubscriptions** và **suppressDuplicateQueueSubscriptions** có thể hạn chế những trường hợp phù hợp, nhưng **không thay idempotency**.

### 9.3. Duplex và connector ngược

Một network connector với **duplex=true** có thể cho phép bridge dùng một liên kết cho thông tin/demand hai chiều. Nếu đồng thời cấu hình A→B và B→A mà không kiểm tra semantics, có thể tạo nhiều bridges/demand không cần thiết.

**Cách làm đúng:** bắt đầu với topology nhỏ nhất, đo active bridges và đường message; chỉ thêm duplex hoặc links đối xứng khi có yêu cầu rõ, rồi test loop suppression cùng negative cases. Không xây full mesh chỉ để làm một consumer ở B nhận queue A.

### 9.4. Selectors và filtering

Khi remote consumers có **selectors**, broker network có thể chuyển demand gắn selector theo cơ chế Classic. Tuy nhiên, mapping selectors, network consumers, priority và subscription forwarding là nơi dễ xuất hiện message nằm ở broker không mong muốn.

**Phải test** với ít nhất một message matching và một message non-matching, có/không consumer cục bộ, rồi đo queue counts A/B. Đừng chỉ nhìn queue name match wildcard và kết luận selector được áp đúng ở mọi hop.


## 10. Quan sát network bridge và chứng minh store-and-forward

Một chỉ số riêng lẻ rất dễ gây hiểu lầm. **Bridge connected** chỉ nói có đường network phù hợp; **QueueSize tại A** chỉ nói về trạng thái queue A tại thời điểm đo; **consumer log tại B** chưa chứng minh business side effect đã commit.

| Quan sát | Câu hỏi cần trả lời | Dấu hiệu cần điều tra |
|---|---|---|
| **Broker A/B startup logs** | Connector có connect/reconnect không? | Authentication, TLS, DNS và transport failures |
| **NetworkConnector / NetworkBridge MBeans** | Bridge nào active, remote broker nào, có traffic/demand không? | Connector cấu hình nhưng chưa có active bridge |
| **A QueueSize / EnqueueCount / DequeueCount** | Message có đang tích tại A, đã được dispatch/ACK khỏi A chưa? | Backlog tăng nhưng B không nhận |
| **B QueueSize / InFlightCount / EnqueueCount** | Message forward có đến B không, consumer đã nhận chưa? | Message ở B nhưng chưa ACK |
| **ConsumerCount tại B** | Có consumer thực tạo remote demand không? | Queue tồn tại nhưng không có subscriber |
| **KahaDB usage tại A/B** | Outage backlog tăng có vượt disk limit không? | Store growth, high I/O latency |
| **DLQ/expiry metrics** | Message hết hạn/được cách ly ở đâu? | Queue gốc trống nhưng message đã expired/DLQ |
| **Business ID logs** | CommandId đã xuất hiện bao nhiêu lần? | Duplicate do resend/bridge/consumer redelivery |
| **Effective destination filters** | Queue có thuộc scope network connector không? | Link khỏe, nhưng destination không được forward |

Tên và cấu trúc MBean của Classic phụ thuộc **brokerName, version và cấu hình JMX**; hãy quan sát resource đúng của mỗi broker. Không hardcode tên MBean từ một môi trường khác rồi coi việc query rỗng là bridge down.

### 10.1. Kịch bản: bridge connected nhưng B không nhận

Kiểm tra theo thứ tự:

1. **B có consumer đang hoạt động trên queue thật chưa?** Không có consumer thì dynamic demand có thể không tồn tại.
2. **Network bridge có thấy remote demand chưa?** Advisory support hoặc bridge credentials có lỗi?
3. **Destination name và queue/topic type có khớp?** LAB.NOB.JOBS khác LAB.NOB.JOB.
4. **dynamicallyIncludedDestinations** có cho phép destination này không?
5. **networkTTL** có đủ khi có nhiều brokers không?
6. **A đã có local consumer nhận trước** hoặc message expired/được quản trị di chuyển chưa?
7. **Bridge có lỗi route/authorization** ở B không?

Đừng tăng networkTTL hoặc bật duplex vô điều kiện khi nguyên nhân thật chỉ là consumer B chưa kết nối.

### 10.2. Kịch bản: A backlog giảm nhưng B consumer vẫn im lặng

Message có thể đang **pending tại B**, **in-flight ở B**, đã được **consumer khác** lấy hoặc chuyển **DLQ**. Kiểm tra B QueueSize/InFlightCount/DequeueCount, network traffic, subscription và ACL. Một số queue metrics là snapshot chứ không phải phản ánh chính xác cùng thời điểm giữa hai broker.

### 10.3. Kịch bản: sau reconnect có nhiều lần xử lý cùng command

Đừng chỉ đếm **JMSMessageID**. Dùng log **commandId** xuyên producer, broker network và consumer; phân loại:

- Producer đã resend do không chắc commit A.
- Bridge đã forward nhưng kết quả ACK local chưa rõ.
- Consumer B rollback/crash sau DB commit.
- Message được replay thủ công từ DLQ hoặc nguồn outbox.

Mỗi nguyên nhân có cơ chế retry khác nhau, nhưng **cùng một khóa business idempotency** có thể bảo vệ hiệu ứng nghiệp vụ ở consumer.

### 10.4. Tránh xem queue bằng consumer AUTO_ACKNOWLEDGE

Một consumer chỉ định đọc message để “kiểm tra nó có trong queue không” có thể **ACK và lấy mất message**. Khi cần xem không phá hủy, ưu tiên **QueueBrowser**, management browse hoặc công cụ có contract read-only; đừng gửi một message mới rồi để test consumer vô tình ảnh hưởng hàng đợi production.

## 11. Security và giới hạn blast radius của bridge

NetworkConnector tạo một đường broker-to-broker có thể đọc và forward messages giữa các hệ thống. Đây là bề mặt cần phân quyền, không phải một socket “nội bộ nên mặc nhiên tin cậy”.

### 11.1. Ma trận cho phép tối thiểu

| Đường | Quy tắc |
|---|---|
| Application Producer → Broker A | Chỉ client nguồn được duyệt, credential JMS phù hợp |
| Broker A → Broker B | Chỉ private broker endpoints, TLS/mTLS nếu được yêu cầu, bridge user có quyền hẹp |
| Application Consumer → Broker B | Chỉ nguồn consumer hợp lệ và quyền consume queue |
| Application → web console/JMX | **DENY**, trừ workload quản trị được cấp quyền |
| Bridge → queue/DLQ không thuộc integration contract | Loại bằng destination filter và ACL |
| Internet → OpenWire/JMX/console | **DENY** nếu không có thiết kế gateway riêng, đã được thẩm định |

Chỉ mở OpenWire giữa A và B chưa đủ nếu broker principal có quyền đọc tất cả queues. Dùng **allowlist dynamicallyIncludedDestinations**, **excludedDestinations**, các security policies của Classic và cơ chế authentication phù hợp.

### 11.2. Advisory permissions

Bridge nhận thông tin từ remote broker về consumer demand. Khi broker sử dụng authorization nghiêm ngặt, cần bảo đảm bridge user có quyền cần thiết để nhận/tạo các thông tin network subscription và forward queue. Nếu thiếu, network connector có thể connected về TCP nhưng không forward đúng.

**Không cấp admin wildcard như cách sửa tạm rồi để nguyên production.** Tạo principal riêng, kiểm tra logs về authorization và thử chỉ với queue LAB.NOB.JOBS trong sandbox.

### 11.3. Tránh nối nhầm môi trường

Không nối **development → production** bằng wildcard network connector chỉ vì hai broker cùng OpenWire. Những message được forward theo demand có thể chứa dữ liệu nhạy cảm hoặc làm phát sinh side effect thật. Broker name, credentials, TLS truststore, destination namespace và network policies của từng môi trường phải độc lập.

**networkTTL** giới hạn số hops, **không phải** ranh giới bảo mật. Một message vẫn có thể bị chuyển tới broker không được phép nếu topology và access control bị cấu hình sai.

## 12. Store-and-forward có giới hạn tài nguyên

Khi B offline, A có thể tiếp tục nhận persistent messages. Nhưng backlog không thể tăng vô hạn: **KahaDB disk**, store usage policy, I/O, message expiration và producer flow control cuối cùng sẽ quyết định hệ thống còn tiếp nhận được không.

### 12.1. Ước lượng backlog

Giả sử A nhận **600 message/giây**, consumer B không hoạt động trong **20 phút**, mỗi message trung bình **4 KiB payload**:

~~~text
Backlog ≈ 600 msg/s × 1.200 s = 720.000 messages

Raw payload ≈ 720.000 × 4 KiB
            ≈ 2,75 GiB
~~~

Đây chỉ là **payload**, chưa gồm message headers, journal overhead, indexes, KahaDB file reuse, DLQ, transaction state và các queue khác. Thực tế cần **dư dung lượng đáng kể** và quan sát disk growth. Nếu backlog tăng trên nhiều brokers, tính riêng mỗi KahaDB vì không có storage pool chung.

Nếu sau outage consumer B xử lý ròng **900 message/giây** trong khi producer A vẫn gửi **600 message/giây**, tốc độ giảm backlog lý tưởng là:

~~~text
Net drain ≈ 900 - 600 = 300 messages/giây

Thời gian drain lý tưởng ≈ 720.000 / 300
                        = 2.400 giây ≈ 40 phút
~~~

Kết quả thực có thể dài hơn vì network bridge overhead, ACK batches, disk I/O, redelivery, prefetch, retries và consumer business latency. **Không lấy công thức này làm một SLO được đảm bảo** khi chưa benchmark.

### 12.2. Network throughput và store I/O

Trong giai đoạn phục hồi, broker A vừa nhận message mới vừa forward backlog; B vừa nhận forward messages vừa dispatch/ACK cho consumer. Cần theo dõi:

- **Enqueue/dequeue rate** của A và B.
- **Broker-to-broker throughput**, reconnect/retry rate.
- **StoreUsage và free disk** của cả A/B.
- **Oldest message age** và message expiration.
- **KahaDB write/flush latency**, JVM GC và client prefetch.
- **Consumer business throughput** và DLQ rate.

Tăng network prefetch quá mức có thể nâng throughput nhưng tăng số message in-flight và khó quan sát tại điểm lỗi. Giảm prefetch quá thấp lại có thể làm link nhàn rỗi chờ nhiều lượt dispatch. Chọn bằng số đo, không theo một giá trị cứng chung cho mọi queue.

### 12.3. Khi gần đầy disk

**Không xóa thủ công các file KahaDB** để tạo chỗ trống. Những biện pháp có kiểm soát gồm giảm rate producer, tăng capacity disk, phục hồi consumer/bridge, xử lý message hết hạn theo policy, hoặc dùng kế hoạch chuyển tải được thẩm định.

Nếu A hỏng storage khi chưa forward message, B **không phải một bản sao HA** để phục hồi chúng. Cần backup/replication/nguồn outbox độc lập, được thiết kế cho yêu cầu mất dữ liệu chấp nhận được.

## 13. Runbook sự cố link và sai routing

### 13.1. Khi A–B ngắt kết nối

1. **Xác nhận bridge down** bằng broker logs và NetworkBridge/NetworkConnector state.
2. **Kiểm tra producer gửi/commit vào A** có còn hoạt động; xác định backlog persistent đang ở A.
3. **Đo disk/KahaDB headroom và oldest pending age** trước khi outage kéo dài.
4. **Kiểm tra transport/TLS/auth/DNS/firewall** và mọi thay đổi connector config gần đây.
5. **Không purge queue A**, không chuyển toàn bộ backlog thủ công khi chưa đối chiếu.
6. Khôi phục đường kết nối rồi **xác nhận remote consumer B có demand**.
7. Quan sát **network forwarding, queue A giảm, B nhận/ACK** và so sánh commandId.
8. Ghi nhận message expired, DLQ hoặc có outcome chưa rõ; dùng reconciliation riêng.

### 13.2. Khi message cứ ở A dù B khỏe

Kiểm tra tuần tự: **consumer B?** → **queue name/routing?** → **bridge A–B active?** → **advisory/remote demand?** → **dynamicOnly và includes?** → **networkTTL?** → **local consumer A?** → **expiry/DLQ?**

Một TCP probe tới port B chỉ chứng minh cổng có thể kết nối, **không chứng minh demand forwarding**. Khi xác minh, dùng consumer JMS thực và một message test với commandId duy nhất.

### 13.3. Khi thấy forwarding loop hoặc duplicate

1. Vẽ sơ đồ tất cả **networkConnectors**, duplex mode và số links giữa từng cặp brokers.
2. Đọc **networkTTL**, conduitSubscriptions, queue subscription suppression và destination filters.
3. Kiểm tra có **producer resend**, message rollback, network ACK ambiguity và consumer B redelivery không.
4. So sánh **commandId**, không chỉ JMSMessageID.
5. Nếu cần đổi TTL/topology, triển khai trước với destination allowlist và canary.
6. Giữ nguyên consumer idempotency trong toàn bộ quá trình sửa.

Không bật full mesh để chữa một link down đơn lẻ khi chưa có yêu cầu định tuyến rõ ràng.

## 14. Các lab nâng cao có tiêu chí đạt

### Lab E — Restart A trước khi forward

1. Tắt B; gửi một số persistent messages vào A và commit.
2. Restart riêng A với đúng KahaDB data directory.
3. Kiểm tra pending tại A còn.
4. Khởi động B, tạo consumer demand rồi consume/commit.
5. Đối chiếu tất cả commandId.

**Đạt:** chứng minh recovery nhờ **persistence tại A**, không nhầm với replication sang B.

### Lab F — Ba brokers A → B → C

1. Dựng ba Classic brokers lab, mỗi broker có network listener và KahaDB riêng.
2. Thiết lập A → B và B → C, consumer chỉ ở C.
3. Thử networkTTL một hop; quan sát giới hạn forwarding.
4. Nâng TTL phù hợp, kiểm tra demand propagation/filter và đo message path.
5. Thử mất link B–C, quan sát backlog có thể tích ở đâu.

**Đạt:** phân biệt **hop limit** với JMSExpiration; nhận ra TTL cao không thay demand.

### Lab G — Topic subscribers

1. Cho phép topic test **LAB.NOB.EVENTS** trong destination filter của network bridge trên sandbox.
2. Tạo hai non-durable subscribers tại B, gửi một event từ A.
3. Quan sát forwarding và local fan-out.
4. Dừng cả hai subscribers B rồi gửi thêm event.
5. So sánh với cấu hình durable subscription có kiểm chứng riêng nếu cần.

**Đạt:** giải thích được **fan-out hợp lệ**, conduitSubscriptions và giới hạn non-durable subscriber khi offline.

### Lab H — Duplicate khi producer retry và khi consumer crash

1. Gửi hai message mới có cùng **commandId** từ producer tới A.
2. Để B consumer nhận cả hai nếu được route.
3. Dùng inbox unique (consumer_name, command_id) và chỉ cập nhật DB trong một transaction.
4. Lặp khi consumer crash sau DB commit trước JMS commit.
5. Ghi số message deliveries và số business updates thực.

**Đạt:** nhiều deliveries nhưng **một hiệu ứng nghiệp vụ**; không dedupe theo provider message ID.

### Lab I — Giới hạn an ninh của bridge

1. Bật auth trên A/B trong môi trường lab.
2. Cấp bridge principal có quyền cần thiết lên queue và advisory, không có admin wildcard.
3. Cố tình chặn network A→B; kiểm tra disconnect/reconnect logs.
4. Thử destination ngoài allowlist, xác nhận không forward.
5. Khôi phục quyền, quan sát backlog có demand đi lại.

**Đạt:** định nghĩa được nguồn, đích, credential và các destinations được phép.

### Lab J — Thử capacity khi B offline

1. Dùng producer có rate limit gửi persistent messages vào A.
2. Tắt B trong một cửa sổ sandbox được kiểm soát.
3. Đo backlog age, KahaDB disk growth và time-to-full.
4. Phục hồi B và đo net drain rate.
5. Đề xuất giới hạn producer/consumer capacity dựa trên số đo.

**Đạt:** có kế hoạch capacity; không giả định store-and-forward có dung lượng vô hạn.

## 15. Checklist trước khi triển khai network of brokers

- [ ] Xác định mục tiêu là **demand forwarding/load distribution**, không phải broker HA replication.
- [ ] Mỗi broker có **brokerName, transportConnector và KahaDB directory riêng**.
- [ ] Có sơ đồ networkConnector, direction, duplex và đường message.
- [ ] URI **static:(...)** tới đúng remote Classic endpoint, có TLS/auth/firewall phù hợp.
- [ ] **dynamicOnly** được chọn có chủ đích; thử cả trường hợp có và không có consumer demand.
- [ ] **dynamicallyIncludedDestinations/excludedDestinations** giới hạn đúng integration contract.
- [ ] **networkTTL** đủ hops nhưng không quá rộng; phân biệt với JMS message TTL.
- [ ] Đã xem tác động của **conduitSubscriptions** và suppression trong topology nhiều links.
- [ ] Không dựa vào local consumer priority để giả lập HA active/passive.
- [ ] Có policy riêng cho queue, topic, durable subscriber và temporary reply destinations.
- [ ] Message cần sống qua restart dùng **PERSISTENT**, transaction đã commit, broker store được bảo vệ.
- [ ] Có capacity plan cho **KahaDB/disk, backlog age, expiry và drain throughput** khi link down.
- [ ] Producer retry giữ **commandId/eventId** ổn định; consumer có inbox/business idempotency.
- [ ] Đã thử link loss, broker restart, consumer offline, local+remote consumer, network hops và ACK ambiguity.
- [ ] Quan sát được network bridge state, queue metrics A/B, DLQ/expiry và business outcomes.
- [ ] Bridge credentials/permissions có least privilege; console/JMX không mở cho mọi application user.
- [ ] Không chép networkConnector Classic vào Artemis; chọn cơ chế multi-broker theo sản phẩm thực tế.

**Kết luận:** **ActiveMQ Classic network of brokers** dùng **network bridge** và thông tin **remote consumer demand** để chuyển message giữa các brokers. Khi đường A–B gián đoạn, một **persistent message đã commit tại A** có thể được **store** trong KahaDB A rồi **forward** khi đường đi và consumer demand hồi phục. Nhưng nó **không tự tạo shared queue, broker replication/HA hoặc exactly-once business effect**. Vận hành đáng tin cậy đòi hỏi giới hạn destinations và network hops, bảo mật bridge, theo dõi backlog/disk khi mất link, cùng business IDs ổn định và idempotent consumers ở nơi xử lý.
