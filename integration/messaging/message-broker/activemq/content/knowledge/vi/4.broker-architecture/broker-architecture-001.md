# Các thành phần nhận kết nối, định tuyến, lưu trữ và phân phối thông điệp

> **Chương:** Kiến trúc broker  
> **Phạm vi:** Apache ActiveMQ Classic và Apache ActiveMQ Artemis khi tích hợp ứng dụng Java bằng JMS, từ việc chấp nhận kết nối đến khi thông điệp được xác nhận, gửi lại hoặc chuyển vào hàng đợi lỗi.

Một broker không chỉ là “hàng đợi ở giữa hai ứng dụng”. Nó là một hệ thống có nhiều tầng phối hợp: **nhận kết nối và kiểm soát truy cập**, **diễn giải đích nhận và định tuyến**, **giữ thông điệp theo chính sách lưu trữ**, **chọn consumer để phân phối**, rồi **ghi nhận kết quả ack/commit hoặc xử lý lỗi**. Hiểu các tầng này giúp trả lời các câu hỏi thường gặp: vì sao producer gửi thành công nhưng consumer chưa nhận, vì sao broker đầy bộ nhớ, vì sao message xuất hiện hai lần, và vì sao thêm broker khác chưa chắc làm thông điệp an toàn hơn.

## 1. Mục tiêu và mô hình toàn cảnh

Sau bài học, người học có thể:

1. Chỉ ra điểm vào của producer/consumer, nhiệm vụ của listener/acceptor, protocol, authentication và authorization.
2. Phân biệt **destination** ở API JMS với **address/queue** của Artemis và **queue/topic** trong ActiveMQ Classic; giải thích quy tắc anycast, multicast và competing consumers.
3. Mô tả vòng đời một message từ **send → route → store → dispatch → ack/commit**, kể cả khi bị rollback, timeout, hết hạn hoặc vào DLQ.
4. Nhận biết phần nào giữ trạng thái lâu dài, phần nào chỉ là bộ đệm; giải thích quan hệ giữa persistent delivery, durable subscription, journal, paging và HA.
5. Dùng các chỉ số thực tế để xác định nghẽn xảy ra ở phía nhận kết nối, tuyến định tuyến, storage hay consumer.

### 1.1. Sơ đồ các tầng

~~~mermaid
flowchart LR
    P["Producer Java/JMS"] --> T["Transport / acceptor<br/>TCP, TLS, protocol"]
    C["Consumer Java/JMS"] <-->|Kết nối, credit, ack| T
    T --> S["Xác thực / phân quyền<br/>connection, send, consume"]
    S --> R["Routing<br/>destination → address / queue"]
    R --> Q["Queue / subscription<br/>message đang chờ"]
    Q <--> M["Persistence / journal<br/>paging khi cần"]
    Q --> D["Dispatch<br/>consumer, credit, prefetch"]
    D --> T
    D --> A["Ack / commit / rollback"]
    A --> Q
    A --> E["Redelivery / DLQ / expiry"]
~~~

Mũi tên trong sơ đồ thể hiện **trách nhiệm logic**, không phải thứ tự chạy cứng của từng thread. Broker có thể xử lý mạng, định tuyến, lưu trữ và gửi cho consumer đồng thời. Một message cũng có thể cần ghi xuống storage trước khi producer nhận kết quả, hoặc chỉ được giữ tạm tùy **delivery mode**, transaction và cấu hình broker.

### 1.2. Hai chiều dữ liệu cần theo dõi

**Chiều đi:** producer tạo message → client serialize thành frame của protocol → broker nhận, kiểm tra quyền và đích → route vào queue/subscription → lưu hoặc đệm → dispatch tới consumer.

**Chiều phản hồi:** consumer thực thi logic → ack hoặc commit, hoặc rollback/đứt kết nối → broker cập nhật trạng thái message → xóa khỏi trạng thái pending, giao lại hoặc chuyển DLQ/expiry theo chính sách.

Một lần **send thành công** chỉ nói về phần việc của producer và broker ở thời điểm đó; nó **không xác nhận** rằng consumer đã hoàn tất cập nhật database hay gọi API ngoài.

## 2. Tầng nhận kết nối: socket, acceptor và protocol

### 2.1. Ứng dụng Java không “nói JMS” trực tiếp qua mạng

JMS (trong hệ mới còn gọi là Jakarta Messaging) là **API lập trình** cung cấp Connection/Session, Queue/Topic, Message, Producer và Consumer. Dữ liệu đi trên mạng nhờ **client library và protocol** thực tế, chẳng hạn ActiveMQ Core, OpenWire hoặc AMQP. Một client JMS không tự động tương thích với mọi cổng broker.

Ở mức triển khai:

- **ActiveMQ Classic:** thường dùng **transport connector** để mở endpoint; OpenWire là một protocol tiêu biểu cho Java client Classic. Các connector khác có thể được cấu hình cho AMQP, STOMP, MQTT, v.v.
- **ActiveMQ Artemis:** dùng **acceptor** để nhận kết nối. Một acceptor có thể cho phép một hoặc nhiều protocol được bật; Artemis có Core, AMQP và một số protocol khác tùy phiên bản, module và cấu hình.
- **Connector phía client hoặc cluster:** dùng để **kết nối ra ngoài**. Trong Artemis, cần phân biệt acceptor nhận kết nối với connector dùng cho kết nối của client/cluster; đừng coi mọi connector là cổng lắng nghe.
- **TLS:** bảo vệ đường truyền và có thể xác minh chứng chỉ; còn **authorization** quyết định danh tính được gửi/nhận/tạo queue ở đích nào.

Ví dụ cấu hình rút gọn theo từng sản phẩm:

**ActiveMQ Classic — một transport connector minh họa:**

~~~xml
<transportConnectors>
    <transportConnector
        name="openwire"
        uri="tcp://127.0.0.1:61616"/>
</transportConnectors>
~~~

**ActiveMQ Artemis — một acceptor minh họa:**

~~~xml
<acceptors>
    <acceptor name="artemis">
        tcp://127.0.0.1:61616?protocols=CORE,AMQP
    </acceptor>
</acceptors>
~~~

Hai đoạn XML là các **mảnh cấu hình minh họa**, không phải tệp cấu hình broker hoàn chỉnh. Cổng **61616** là giá trị hay gặp ở môi trường mẫu, không phải quy tắc bắt buộc. Địa chỉ loopback chỉ phục vụ thực hành tại máy; khi triển khai phải quy hoạch bind address, TLS, firewall, chứng chỉ và credential phù hợp.

### 2.2. Một kết nối được chấp nhận chưa đồng nghĩa mọi thao tác đều hợp lệ

Tại thời điểm kết nối, broker và client cần thống nhất protocol, phiên bản/tính năng liên quan, cơ chế xác thực và session. Sau đó, mỗi thao tác lên destination có thể cần quyền riêng:

| Yêu cầu từ client | Thành phần liên quan | Ví dụ thất bại |
|---|---|---|
| Mở TCP/TLS | Listener, network, trust store | Firewall chặn cổng; chứng chỉ sai hostname |
| Đăng nhập | Authentication | Username/password hoặc chứng chỉ không hợp lệ |
| Gửi vào queue/topic | Authorization + routing | Có quyền connect nhưng không có quyền send |
| Tạo queue/subscription | Broker configuration + create permission | API tạo handle thành công nhưng server không cho tạo queue |
| Đăng ký consumer | Authorization + subscription/queue | Consumer thiếu quyền consume |
| Duy trì kết nối | Heartbeat/keepalive, timeout, reconnect | Mất mạng làm session không còn hợp lệ |

**Lưu ý:** Gọi **JMSContext.createQueue("orders.commands")** tạo một **đối tượng Queue phía client**. Queue thật trên server chỉ xuất hiện nếu đã được khai báo, hoặc broker được cấu hình auto-create đúng điều kiện. Muốn chắc chắn, kiểm tra topology và quyền tạo đích trên server.

### 2.3. Connection, session và transaction

Một kết nối có thể mang nhiều tương tác gửi/nhận. Session/JMSContext là nơi gắn kết ngữ cảnh nhận message, chế độ xác nhận và transaction. Broker phải theo dõi consumer nào đang đăng ký, mỗi consumer có bao nhiêu message chưa ack, và transaction nào đang mở.

Với JMS:

- **AUTO_ACKNOWLEDGE:** provider xác nhận theo quy tắc của chế độ nhận hoặc callback; không nên suy luận rằng mọi cập nhật nghiệp vụ ngoài broker đã được commit.
- **CLIENT_ACKNOWLEDGE:** ứng dụng gọi acknowledge; thao tác ack trên một message có thể xác nhận **tất cả message đã tiêu thụ nhưng chưa ack trong cùng session**.
- **SESSION_TRANSACTED:** thao tác gửi/nhận trong session JMS được kết thúc bằng **commit** hoặc **rollback**. Transaction JMS thông thường **không tự bao trùm** transaction của database hay HTTP service khác.
- Trong Java, cần dùng **client library tương thích với namespace** **javax.jms** hoặc **jakarta.jms** của ứng dụng. Không trộn hai namespace trong cùng mã biên dịch.

## 3. Tầng định tuyến: từ destination tới queue/subscription

Routing trả lời câu hỏi: **message sau khi được chấp nhận sẽ nằm ở đâu, và nhóm consumer nào có thể nhận?**

### 3.1. Queue: phân phối công việc cho một consumer trong nhóm

Giả sử producer gửi lệnh thanh toán vào **payment.commands**. Hai worker cùng đăng ký queue này:

~~~mermaid
flowchart LR
    O["Order Service"] --> Q[("Queue payment.commands")]
    Q --> W1["Payment Worker 1"]
    Q --> W2["Payment Worker 2"]
~~~

Trong điều kiện bình thường, **mỗi lần phân phối một message từ queue chỉ hướng tới một consumer** của nhóm cạnh tranh. Broker có thể phân chia nhiều message cho các worker khác nhau, nhưng điều đó **không** bảo đảm mỗi message có đúng một lần **xử lý nghiệp vụ**. Khi worker mất kết nối, rollback hoặc không ack, message có thể được giao lại cho worker khác.

Queue thích hợp cho **command/job processing**: thanh toán, gửi tác vụ xuất báo cáo, tính phí, cập nhật tài liệu. Tăng số consumer có thể tăng throughput nếu tác vụ độc lập và downstream chịu được tải.

### 3.2. Topic: một sự kiện tới nhiều subscription

Giả sử một lần tạo đơn phải thông báo cho cả kho và dịch vụ email:

~~~mermaid
flowchart LR
    O["Order Service"] --> T[("Topic orders.events")]
    T --> S1["Subscription inventory"]
    T --> S2["Subscription notification"]
    S1 --> C1["Inventory Consumer"]
    S2 --> C2["Notification Consumer"]
~~~

Một message trên topic có thể được chuyển tới **nhiều subscription phù hợp**. Mỗi subscription có tiến độ nhận và chính sách tồn tại riêng.

- **Non-durable subscription** thường chỉ nhận trong thời gian subscriber đang hoạt động; message phát khi offline không mặc nhiên được giữ.
- **Durable subscription** có định danh và trạng thái tồn tại theo cơ chế JMS/provider, cho phép giữ thông điệp phù hợp khi subscriber offline nếu broker và message đáp ứng điều kiện liên quan.
- **Shared subscription** (khi API/provider hỗ trợ) cho nhiều consumer chia sẻ một subscription. Phân biệt “nhiều consumer của **cùng** subscription” với “nhiều subscription cần **mỗi nhóm một bản sao**”.
- **Message selector** có thể giới hạn message mà subscription/consumer quan tâm dựa trên property. Cần kiểm tra semantics lọc và chi phí thực tế trên broker đang dùng.

### 3.3. Điểm khác biệt quan trọng: Classic và Artemis

**ActiveMQ Classic** thường trình bày trực tiếp các JMS destination **queue** và **topic**, cùng các policy về dispatch, storage, redelivery và dead letter theo destination.

**ActiveMQ Artemis** xây dựng mô hình trên hai đối tượng:

1. **Address**: tên logic nhận message từ producer.
2. **Queue gắn với address**: nơi message được xếp chờ và được consumer nhận.

Hai kiểu routing chính trong Artemis:

| Routing type | Message vào address | Thường dùng cho |
|---|---|---|
| **ANYCAST** | Được định tuyến tới **một queue phù hợp** trên address | Phân phối công việc; nhiều consumer cùng queue sẽ cạnh tranh |
| **MULTICAST** | Được định tuyến tới **từng queue phù hợp** trên address | Pub/sub; mỗi queue/subscription nhận bản sao logic riêng |

Khi một address có nhiều queue **ANYCAST**, broker chọn một queue phù hợp theo chính sách routing; khi có nhiều consumer gắn vào **một queue**, dispatcher lại quyết định consumer nào nhận. Đây là **hai quyết định khác nhau**. Nếu address cho phép cả ANYCAST và MULTICAST, kết quả phụ thuộc routing type của message, protocol, mapping JMS và cấu hình; không nên đoán theo tên destination.

Ví dụ mô hình Artemis:

~~~text
Address: payment.commands        ANYCAST
  └── Queue: payment.commands
         ├── Payment Worker A
         └── Payment Worker B

Address: orders.events           MULTICAST
  ├── Queue: inventory.sub       → Inventory Service
  └── Queue: notification.sub    → Notification Service
~~~

**Queue tĩnh gắn vào multicast address** giúp diễn tả fan-out ở tầng broker. Không được đồng nhất việc khai báo queue tĩnh như trên với mọi chi tiết vòng đời của **JMS durable subscription**: subscription do JMS client tạo còn có quy tắc đặt tên, định danh, chia sẻ và xóa riêng.

### 3.4. Ví dụ khai báo địa chỉ và queue trên Artemis

Đoạn sau thuộc phần **addresses** của cấu hình Artemis, cho thấy rõ một queue ANYCAST và hai queue MULTICAST:

~~~xml
<addresses>
    <address name="payment.commands">
        <anycast>
            <queue name="payment.commands" durable="true"/>
        </anycast>
    </address>

    <address name="orders.events">
        <multicast>
            <queue name="inventory.sub" durable="true"/>
            <queue name="notification.sub" durable="true"/>
        </multicast>
    </address>
</addresses>
~~~

Khi worker cùng tiêu thụ **payment.commands**, message được chia theo cạnh tranh. Khi event được gửi vào **orders.events** với routing type MULTICAST, mỗi queue phù hợp có thể giữ một bản sao để nhóm tương ứng tiêu thụ.

Cấu hình trên chỉ dùng cho **Artemis**, không thể chép vào **ActiveMQ Classic**. Khi đặt queue tự động, routing type, durability hay tên address theo broker defaults, phải đọc lại cấu hình thực tế thay vì coi mặc định giống nhau qua các phiên bản.

### 3.5. Routing còn liên quan tới lọc và chuyển hướng

Các broker có thể hỗ trợ filter, selector, routing policy, virtual topic, composite destination hoặc divert/bridge tùy sản phẩm. Ví dụ:

- Consumer kho chỉ nhận event có property **eventType=OrderCreated**.
- Một đường kiểm toán nhận thêm bản sao message qua cơ chế cấu hình phù hợp.
- Hệ thống đẩy một số message sang khu vực xử lý khác hoặc broker khác.

Các cơ chế này ảnh hưởng số bản sao, chi phí lưu trữ và quyền truy cập. Không dùng từ **routing** như bảo đảm “message nào cũng tới được mọi consumer”.

## 4. Tầng lưu trữ: điều gì được giữ và giữ ở đâu?

Queue/subscription là **đơn vị logic**, trong khi broker phải quản lý cả metadata, message chưa được xác nhận, trạng thái transaction, journal trên đĩa và các bộ đệm để giao tiếp nhanh.

### 4.1. Persistent không đồng nghĩa toàn hệ thống không bao giờ mất dữ liệu

Trong JMS, producer có thể chỉ định **DeliveryMode.PERSISTENT** hoặc **NON_PERSISTENT**. Khi dùng persistent với destination bền vững và broker đã cấu hình persistence thích hợp, provider phải thực hiện bảo đảm lưu trữ tương ứng theo hợp đồng JMS. Tuy nhiên:

- **Đã gọi send** chưa đồng nghĩa transaction đã **commit** nếu session đang transacted.
- **Persistent message** không tự tạo durable topic subscription; một subscriber không bền vững vẫn có thể bỏ lỡ message phát khi offline.
- **Persistent storage** không tự cung cấp host dự phòng, backup ngoài máy hoặc kế hoạch khôi phục khi mất toàn bộ ổ đĩa.
- **NON_PERSISTENT** cho phép broker tối ưu tốc độ và có thể làm mất message chưa xử lý khi broker gặp sự cố.
- Thành công, lỗi hoặc timeout của lần gửi khi mất mạng có thể không cho ứng dụng biết chắc phía broker đã commit chưa. Producer phải có chính sách retry kèm **eventId/idempotency** nếu nghiệp vụ đòi hỏi chống trùng.

### 4.2. Bốn phần trạng thái thường gặp

| Thành phần | Chức năng | Vì sao cần hiểu |
|---|---|---|
| **Message store / journal** | Lưu dữ liệu persistent và sự kiện thay đổi trạng thái cần phục hồi | Ảnh hưởng độ bền, I/O và thời gian khởi động lại |
| **Metadata/bindings** | Ghi nhớ cấu hình/quan hệ của address, queue, subscription và transaction phù hợp | Mất metadata có thể khiến consumer không tìm thấy đích dù đã có data |
| **Bộ đệm / cursor / in-flight** | Giữ tham chiếu hoặc bản message sẵn sàng dispatch; theo dõi message đã phát nhưng chưa ack | Ảnh hưởng memory, độ công bằng và hiệu năng consumer |
| **Paging / cơ chế giới hạn bộ nhớ** | Quản lý backlog lớn khi message vượt ngân sách bộ nhớ theo chính sách | Không thể thay thế giới hạn dung lượng đĩa và giám sát backlog |

Ở **ActiveMQ Classic**, kiến trúc thường dùng **KahaDB** làm persistent message store và có **message cursor** để quản lý những message đang chờ dispatch. Broker còn theo dõi giới hạn sử dụng memory/store/temp và có thể áp dụng **producer flow control** khi tài nguyên cạn.

Ở **ActiveMQ Artemis**, kiến trúc sử dụng **journal** và các vùng liên quan đến bindings, page store và large-message handling. Artemis cung cấp các chính sách **address-full-policy** như **PAGE**, **BLOCK**, **FAIL** hoặc các giá trị khác tùy phiên bản; chọn chính sách quyết định broker phải làm gì khi address vượt giới hạn được cấu hình.

**Paging không phải backup và cũng không phải DLQ.** Paging giúp xử lý backlog lớn dựa trên storage và chính sách. Khi dung lượng đĩa cạn hoặc page store gặp lỗi, broker vẫn có thể ngừng nhận hoặc không tiếp tục xử lý như kỳ vọng.

### 4.3. Ghi vào journal và commit có ý nghĩa gì?

Một timeline đơn giản cho message persistent ở queue, trong session JMS có transaction:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Broker
    participant J as Journal / Storage
    participant Q as Queue
    P->>B: send(message)
    B->>B: Xác thực quyền, kiểm tra đích, route
    P->>B: commit JMS session
    B->>J: Lưu thay đổi transaction / message
    J-->>B: Hoàn tất theo policy lưu trữ
    B-->>P: Kết quả commit
    B->>Q: Message đủ điều kiện dispatch
~~~

Đây là **trình tự khái niệm**. Thời điểm ghi journal, batch, flush, index, dispatch và trả kết quả phụ thuộc implementation, phiên bản và chính sách đồng bộ storage. Không suy ra rằng mỗi bước tương ứng chính xác một disk write hoặc một network round trip.

Đối với thao tác nhận trong session transacted, **commit** xác nhận các lần receive thuộc transaction đó theo semantics JMS; **rollback** khiến message chưa được xác nhận có thể được giao lại. Broker dùng metadata và log để khôi phục trạng thái hợp lệ sau crash.

### 4.4. Hết hạn (expiry) khác với dead-letter (DLQ)

Một message có thể không còn được xử lý theo hai nhóm nguyên nhân khác nhau:

- **Expiration/TTL:** message quá thời hạn hữu ích; tùy broker và cấu hình, nó bị loại bỏ hoặc chuyển đến **expiry address/queue**.
- **Redelivery thất bại:** consumer rollback nhiều lần, không xử lý được message; theo policy, broker có thể chuyển tới **dead-letter address/queue**.

Đừng coi mọi message hết hạn đều vào DLQ, và đừng coi DLQ tự chứa toàn bộ lịch sử lỗi. Muốn điều tra, cần ghi eventId, JMSMessageID/correlationId, thời điểm, loại lỗi và số lần nhận/giao lại trong dữ liệu giám sát thích hợp.

## 5. Tầng phân phối: broker chọn consumer như thế nào?

Khi message đã vào queue, broker phải quyết định **khi nào** và **cho ai** giao.

### 5.1. Bốn yếu tố ảnh hưởng dispatch

1. **Consumer đăng ký ở đâu:** consumer phải gắn đúng queue hoặc subscription; chỉ kết nối vào broker không đủ.
2. **Consumer có thể nhận thêm không:** các cơ chế credit, window hoặc prefetch giới hạn số message gửi trước khi được ack/tiêu thụ.
3. **Queue có áp dụng group/selector/filter không:** một message có thể chỉ phù hợp với một tập consumer; group có thể cố giữ các message liên quan với cùng consumer.
4. **Broker và consumer còn tài nguyên không:** memory, network, disk, CPU, backlog và tốc độ xử lý của downstream quyết định độ trễ thực.

Trong **Classic**, thường gặp khái niệm **prefetch**: broker cho phép đẩy trước một số message tới consumer. Trong **Artemis**, có cơ chế **consumer window/credit** để kiểm soát số dữ liệu đang gửi. Hai cơ chế có mục đích tương tự ở mức flow control nhưng **khác tham số, đơn vị và chi tiết implementation**.

### 5.2. Queue depth không bằng tổng số message đang được xử lý

Giả sử có 100 message và hai consumer. Broker có thể đã dispatch một phần cho consumer nhưng vẫn đang chờ ack. Tuỳ broker/metric, số **pending**, **delivering/in-flight**, **scheduled/redelivery** và **acknowledged** có thể được thống kê riêng.

Nếu chỉ nhìn “queue depth giảm”, có thể kết luận nhầm rằng nghiệp vụ đã xong. Ví dụ worker nhận 30 message vào bộ đệm nhưng mất nhiều phút gọi API, backlog thấy trên một metric có thể giảm dù độ trễ end-to-end vẫn tăng.

Nên quan sát **queue count + delivering/in-flight + message age + consumer count + ack/dequeue rate** cùng lúc.

### 5.3. Thứ tự và chia tải

Với một queue và một consumer xử lý tuần tự, thứ tự có thể dễ kiểm soát hơn. Khi có nhiều consumer, redelivery, selector hoặc chuyển tuyến liên broker, **thứ tự hoàn thành xử lý nghiệp vụ** không mặc nhiên giống thứ tự gửi.

Nếu yêu cầu các cập nhật của cùng một đơn hàng đi theo thứ tự, có thể:

- Thiết kế message có **orderId**, **eventVersion** và quy tắc phát hiện sự kiện đến trễ.
- Dùng **message grouping** (ví dụ property **JMSXGroupID** khi provider hỗ trợ và cấu hình phù hợp).
- Phân vùng theo business key hoặc dùng một worker xử lý tuần tự cho khóa cụ thể.
- Chấp nhận rằng bảo đảm thứ tự có thể giới hạn parallelism; đo trên workload thật.

### 5.4. Backpressure: broker giữ hệ thống khỏi tự làm quá tải

Khi producer gửi nhanh hơn consumer xử lý, queue tăng. Broker có thể bắt đầu paging, block producer, trả lỗi hoặc áp dụng chính sách khác. Ở tầng client, cơ chế producer flow control và timeout ảnh hưởng trải nghiệm gửi.

Ví dụ **Order Service** phát 5.000 message/phút còn Payment Service chỉ xử lý 2.000 message/phút. Sau 10 phút, backlog có xu hướng tăng khoảng **30.000 message** nếu không có expiry, drop, purge, retry hoặc thay đổi tốc độ. Đây là minh họa tốc độ trung bình, không phải công thức cố định của một counter cụ thể.

Muốn xử lý: trước hết đo consumer và downstream. Thêm worker giúp khi xử lý song song còn dư năng lực; nếu database đã đạt giới hạn thì tăng worker có thể làm tình trạng tệ hơn. Cần đặt giới hạn backlog, quota, cảnh báo và cách ứng dụng phản hồi khi broker không nhận thêm.

## 6. Vòng đời một message cụ thể

Xét lệnh **ChargeOrder** gửi vào queue **payment.commands**:

| Giai đoạn | Trạng thái logic | Quan sát được ở đâu? | Rủi ro/lỗi điển hình |
|---|---|---|---|
| **1. Connect** | Producer có phiên kết nối hợp lệ | Connection/session metrics, auth logs | Sai protocol, TLS, credential |
| **2. Send** | Message tới broker hoặc transaction đang mở | Producer result, broker ingress counters | Network timeout, thiếu quyền send |
| **3. Route** | Broker xác định đích/queue phù hợp | Address/queue bindings, routing metrics | Sai queue name/routing type; queue chưa tồn tại |
| **4. Enqueue/store** | Message nằm chờ hoặc được lưu bền vững theo policy | Message count, store/journal/paging | Disk full, size limit, persistent config sai |
| **5. Dispatch** | Broker giao message cho consumer | Delivering/in-flight count, consumer count | Slow consumer, prefetch lớn, thiếu credit |
| **6. Process** | Consumer cập nhật nghiệp vụ | App log, tracing, database | DB timeout, HTTP 503, dữ liệu không hợp lệ |
| **7. Ack/commit** | Broker hoàn tất trạng thái nhận | Ack/dequeue metrics, message count | Mất kết nối trước ack; transaction rollback |
| **8. Recover** | Message có thể giao lại hoặc chuyển DLQ/expiry | Redelivery, DLQ, expiry metrics | Poison message, retry vô hạn, replay trùng |

Một message không nhất thiết đi qua bước lưu lâu dài nếu gửi NON_PERSISTENT, và một lần nhận có thể kết thúc bằng redelivery thay vì hoàn tất. Trong pub/sub, **mỗi subscription** có trạng thái nhận riêng, vì vậy một nhóm đã ack không có nghĩa nhóm khác đã xử lý.

### 6.1. Vết lỗi đáng chú ý: xử lý database xong nhưng chưa ack

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant DB as Database
    B->>C: Dispatch eventId=evt-42
    C->>DB: Ghi kết quả đơn hàng
    DB-->>C: Commit thành công
    Note over C,B: Kết nối mất trước ack
    B->>C: Redelivery eventId=evt-42
    C->>DB: Kiểm tra evt-42 đã xử lý?
    DB-->>C: Đã tồn tại
    C->>B: Ack hoặc commit JMS
~~~

Trong lần giao lại, ứng dụng phải nhận ra **eventId đã được xử lý**, không thu tiền lần thứ hai. Một **unique constraint** trên bảng inbox/processed_events, được ghi **cùng transaction database** với thay đổi nghiệp vụ, là cách phổ biến:

~~~sql
-- Minh họa PostgreSQL, chạy trong cùng transaction nghiệp vụ.
INSERT INTO processed_events (event_id)
VALUES ('evt-42')
ON CONFLICT (event_id) DO NOTHING;

-- Chỉ khi INSERT thực sự tạo dòng mới:
-- thực hiện cập nhật trạng thái/ghi sổ nghiệp vụ.
-- Sau khi database COMMIT thành công mới ack JMS.
~~~

Đoạn SQL là phác thảo cho luồng idempotency: chương trình cần kiểm tra **số dòng đã INSERT**, đặt unique index trên event_id và bao transaction đầy đủ. Broker không thể tự biết một transaction database bên ngoài đã commit.

## 7. Thực hành Java/JMS: nhận, commit, rollback qua một Artemis broker

Ví dụ sử dụng **API JMS 2.x với namespace javax.jms** và **ActiveMQ Artemis JMS client** tương thích. Nếu dự án dùng Jakarta Messaging, thay bằng dependency/client API **jakarta.jms** phù hợp thay vì trộn thư viện.

Chuẩn bị trước khi chạy:

- Một Artemis broker local đã bật persistence và acceptor tương thích client.
- Khai báo **address ANYCAST + queue payment.commands**, hoặc cấu hình auto-create đúng nhu cầu.
- Có user được cấp quyền connect/send/consume đối với queue này.
- Các biến môi trường **MQ_URL**, **MQ_USER**, **MQ_PASSWORD**, chẳng hạn MQ_URL là **tcp://localhost:61616** khi cổng local được cấu hình như vậy.
- Java dependency **org.apache.activemq:artemis-jms-client** thuộc phiên bản phù hợp với Java, broker và javax.jms. Chọn phiên bản cụ thể theo bộ thư viện của môi trường; ví dụ không giả định một phiên bản duy nhất cho mọi hệ thống.

Chương trình sau vừa tạo message persistent vừa xử lý bằng session JMS transacted:

~~~java
import java.util.UUID;
import javax.jms.ConnectionFactory;
import javax.jms.DeliveryMode;
import javax.jms.JMSConsumer;
import javax.jms.JMSContext;
import javax.jms.Message;
import javax.jms.Queue;
import javax.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class BrokerPipelineLab {
    private static final String QUEUE = "payment.commands";

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Use: send | receive | fail");
        }

        String url = requiredEnv("MQ_URL");
        String user = requiredEnv("MQ_USER");
        String pass = requiredEnv("MQ_PASSWORD");
        ConnectionFactory factory = new ActiveMQConnectionFactory(url);

        switch (args[0]) {
            case "send":
                send(factory, user, pass);
                break;
            case "receive":
                receive(factory, user, pass, false);
                break;
            case "fail":
                receive(factory, user, pass, true);
                break;
            default:
                throw new IllegalArgumentException("Unknown command: " + args[0]);
        }
    }

    private static void send(ConnectionFactory factory,
                             String user, String pass) throws Exception {
        try (JMSContext ctx = factory.createContext(
                 user, pass, JMSContext.SESSION_TRANSACTED)) {
            Queue destination = ctx.createQueue(QUEUE);

            TextMessage msg = ctx.createTextMessage(
                "{\"type\":\"ChargeOrder\",\"orderId\":\"OD-1001\"}");
            String eventId = UUID.randomUUID().toString();
            msg.setStringProperty("eventId", eventId);
            msg.setJMSCorrelationID("OD-1001");

            ctx.createProducer()
               .setDeliveryMode(DeliveryMode.PERSISTENT)
               .setTimeToLive(300_000)
               .send(destination, msg);

            ctx.commit(); // Transaction JMS send được hoàn tất.
            System.out.println("Committed send; eventId=" + eventId);
        }
    }

    private static void receive(ConnectionFactory factory,
                                String user, String pass,
                                boolean injectFailure) throws Exception {
        try (JMSContext ctx = factory.createContext(
                 user, pass, JMSContext.SESSION_TRANSACTED)) {
            Queue destination = ctx.createQueue(QUEUE);
            JMSConsumer consumer = ctx.createConsumer(destination);
            Message message = consumer.receive(5000);

            if (message == null) {
                System.out.println("No message available");
                return;
            }

            try {
                String id = message.getStringProperty("eventId");
                System.out.println("Received id=" + id
                    + ", redelivered=" + message.getJMSRedelivered());

                if (!(message instanceof TextMessage)) {
                    throw new IllegalArgumentException("Unexpected message type");
                }
                String body = ((TextMessage) message).getText();
                System.out.println("Payload=" + body);

                if (injectFailure) {
                    throw new IllegalStateException("Injected processing failure");
                }

                // Ứng dụng thật: thực hiện transaction database idempotent.
                // Chỉ khi thay đổi nghiệp vụ đã commit thành công:
                ctx.commit(); // Xác nhận receive trong transaction JMS.
                System.out.println("Committed receive");
            } catch (Exception e) {
                ctx.rollback(); // Message có thể được giao lại theo policy.
                throw e;
            }
        }
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isEmpty()) {
            throw new IllegalArgumentException("Missing env: " + key);
        }
        return value;
    }
}
~~~

**Cách thử theo thứ tự:**

1. Chạy **send**. Quan sát message được route tới **payment.commands**; nếu chưa có consumer, nó ở trạng thái chờ. Kiểm tra JMS transaction đã commit trước khi chương trình kết thúc.
2. Chạy **receive**. Quan sát payload và **Committed receive**; queue không còn message đang chờ nếu đây là message duy nhất và không có retry khác.
3. Chạy **send**, tiếp theo **fail**. Chương trình cố tình rollback rồi thoát với exception. Sau đó chạy **receive** và quan sát message giao lại theo redelivery policy. Thời điểm giao lại không cố định; phụ thuộc broker.
4. Gửi một message persistent khác, dừng broker **đúng quy trình**, khởi động lại rồi receive. Xác minh khả năng phục hồi của message đang chờ; bảo đảm instance dùng lại cùng persistent storage.
5. Chạy hai consumer cùng đọc queue và gửi nhiều message. So sánh **message count**, **delivering count**, tốc độ ack và log xử lý để quan sát cạnh tranh phân phối.

**Ranh giới của lab:** đây là mã để quan sát routing, storage, dispatch và commit JMS. Đoạn in payload **không phải** xử lý thanh toán thật. Khi thay bằng database, phải dùng idempotency key và transaction nghiệp vụ; JMS transaction riêng không biến toàn bộ thao tác thành một transaction phân tán.

### 7.1. Một bước mở rộng để thấy sự khác nhau queue/topic

Giữ cùng broker, tạo thêm address **orders.events** MULTICAST với hai queue **inventory.sub** và **notification.sub** như ở mục 3.4. Gửi một event có routing type MULTICAST, sau đó tạo consumer gắn từng queue.

Kết quả kỳ vọng: mỗi queue nhận bản sao tương ứng; ack trên **inventory.sub** không xóa bản sao chờ tại **notification.sub**. Đây là cách quan sát rõ sự khác biệt giữa **tầng routing** và **tầng dispatch**. Nếu thực hiện thông qua JMS Topic và durable subscriptions thay vì core queue API, hãy tạo/định danh subscription đúng semantics JMS của phiên bản đang dùng.

## 8. Redelivery, expiry, DLQ nằm ở đâu trong kiến trúc?

Khi consumer không thể hoàn thành, broker phải quyết định **message quay lại queue để thử tiếp** hay **được cách ly**. Quyết định này liên quan session, dispatch và policy; không phải do producer gửi lại mỗi khi consumer thất bại.

~~~mermaid
flowchart TD
    Q["Message đã nằm trong queue"] --> D["Dispatch tới consumer"]
    D --> P{"Xử lý thành công?"}
    P -->|Có| A["Ack / commit JMS"]
    P -->|Không| R["Rollback / session mất"]
    R --> L{"Chưa vượt giới hạn retry?"}
    L -->|Có| W["Redelivery sau delay"] --> Q
    L -->|Không| X["DLQ / dead-letter address"]
    Q --> TTL{"Message hết TTL?"}
    TTL -->|Có| E["Expiry queue hoặc discard theo policy"]
    TTL -->|Không| D
~~~

Sơ đồ thể hiện các khả năng logic, không khẳng định broker luôn kiểm tra TTL theo đúng thứ tự các ô. Message cũng có thể được dời, loại bỏ hoặc bị từ chối tùy cấu hình.

Ví dụ **Artemis address-settings**:

~~~xml
<address-settings>
    <address-setting match="payment.#">
        <dead-letter-address>DLQ</dead-letter-address>
        <expiry-address>EXPIRY</expiry-address>
        <max-delivery-attempts>5</max-delivery-attempts>
        <redelivery-delay>2000</redelivery-delay>
    </address-setting>
</address-settings>
~~~

Ví dụ trên minh họa năm lần thử theo delivery policy và trì hoãn redelivery **2.000 ms**. Cần **provision** address/queue nhận DLQ và EXPIRY hoặc cho phép auto-create phù hợp, đồng thời thử wildcard và policy với phiên bản broker đang dùng.

**ActiveMQ Classic** có cấu hình **redelivery policy** và **dead-letter strategy** riêng, trong đó có thể dùng các đích DLQ chung hoặc theo destination. Không chuyển trực tiếp XML **address-settings** của Artemis sang Classic.

Điểm cần quan sát:

- Lỗi **tạm thời** (database timeout) nên retry có delay/backoff và giới hạn.
- Message **sai schema** nên vào khu vực cách ly đủ sớm; retry vô hạn chỉ giữ queue bận.
- Message hết hạn có thể vào expiry theo policy; một message không nhất thiết đi qua DLQ.
- DLQ cần owner, cảnh báo, runbook xem nguyên nhân, sửa dữ liệu và **replay có kiểm soát**.
- Một message được replay có thể gây hiệu ứng lặp nếu consumer không có idempotency.

## 9. Khi nhiều broker xuất hiện, trách nhiệm các tầng thay đổi thế nào?

Ở một broker, điểm nhận kết nối, bảng định tuyến, queue và storage thường cùng trên một process/host. Khi mở rộng topology, phải phân biệt ba mục tiêu:

| Mục tiêu | Thành phần chính | Điều không tự được bảo đảm |
|---|---|---|
| **HA / failover** | Active/backup, replication hoặc shared storage, cơ chế reconnect và fencing | Thêm backup không tự tăng throughput |
| **Chia tải/routing liên broker** | Artemis cluster, hoặc Classic Network of Brokers theo thiết kế | Message không tự được sao chép bền vững lên mọi broker |
| **Trao đổi giữa miền/site** | Bridge/federation và các policy routing được lựa chọn | Không tự bảo đảm exactly-once business effect |

Với **Artemis cluster**, message có thể được forward theo trạng thái binding, routing và consumer của cluster. Điều này khác với **replication** nhằm phục vụ HA. Với **Classic Network of Brokers**, network connector có thể chuyển message dựa trên nhu cầu/subscription và cấu hình; không thể coi nó như một cặp active/backup của Artemis.

Ví dụ sự cố: producer gửi sang Broker A, consumer kết nối Broker B. Chỉ “hai broker đang online” chưa đủ để khẳng định consumer nhận được; phải kiểm tra **queue binding, đường cluster/network, protocol, quyền, chính sách forward** và trạng thái liên kết.

Việc client reconnect sau failover cũng không quyết định được một **commit đã hoàn tất ngay trước khi mất mạng** hay chưa. Ứng dụng cần dedup/idempotency để xử lý trường hợp kết quả commit mơ hồ và redelivery.

## 10. Quan sát các tầng qua metric và triệu chứng

Một broker có thể “còn sống” nhưng thông điệp không được xử lý đúng hạn. Chẩn đoán nên theo hành trình message:

| Triệu chứng | Tầng cần kiểm tra đầu tiên | Dấu hiệu để phân biệt |
|---|---|---|
| Không kết nối được | **Transport / authentication** | Port, protocol handshake, TLS, auth logs |
| Connect được nhưng send bị từ chối | **Authorization / routing** | Quyền send, queue/address không tồn tại, routing type không phù hợp |
| Send chậm tăng dần khi consumer dừng | **Storage / backpressure** | Queue backlog, disk I/O, journal latency, paging, producer blocked |
| Có backlog nhưng consumer không nhận | **Routing / dispatch** | Consumer count, queue binding, selector/filter, consumer credit |
| Message rời queue nhưng nghiệp vụ chậm | **Consumer / in-flight** | Delivering count, database latency, thời gian xử lý |
| Cùng một message được xử lý lại | **Ack / transaction / redelivery** | Rollback, reconnect, JMSRedelivered, delivery count |
| DLQ tăng | **Retry policy / consumer logic** | Số lần thử, lỗi parse/schema, downstream timeout |
| Mất message sau restart | **Durability / subscription / storage** | DeliveryMode, transaction commit, broker persistence, durable subscription |
| Tăng consumer không tăng throughput | **Backpressure downstream** | DB/API đạt ngưỡng, lock contention, queue age không giảm |

### 10.1. Một checklist metric tối thiểu

- **Connection/session/consumer count:** Có thực sự producer và consumer đang kết nối tới đúng broker/queue không?
- **Enqueue, dispatch, ack/dequeue rate:** Input, lượng giao và lượng hoàn tất có cân bằng không?
- **Message count, delivering/in-flight, scheduled/redelivery:** Message đang ở trạng thái nào?
- **Oldest-message age, end-to-end processing latency:** SLO có được đáp ứng không, kể cả khi depth nhỏ?
- **Store/journal disk usage, free disk, paging, memory, CPU:** Có nút nghẽn tài nguyên không?
- **DLQ, expiry, authentication/authorization failures:** Có lỗi cần xử lý ngay không?
- **HA/cluster link health:** Khi có nhiều broker, các node còn đúng vai trò và nhìn thấy nhau không?

Tên metric, bộ đếm và việc một message được tính tại thời điểm nào thay đổi giữa **Classic** và **Artemis**. Không cộng/trừ các counter khác định nghĩa để suy ra “mất message” khi chưa kiểm tra semantics của chúng.

### 10.2. Bảo mật tương ứng từng tầng

| Tầng | Kiểm soát phù hợp |
|---|---|
| **Nhận kết nối** | Bind interface cần thiết, firewall, TLS, giới hạn protocol/acceptor |
| **Đăng nhập và thao tác** | Authentication; RBAC/authorization theo address/queue/destination; nguyên tắc ít quyền nhất |
| **Định tuyến** | Quyền tạo đích, quyền gửi/consume; tránh subscription hoặc bridge vô ý làm lộ message |
| **Storage** | Quyền trên file/volume, mã hóa và backup theo yêu cầu, lưu giữ dữ liệu có giới hạn |
| **Phân phối và quan sát** | Không log credential/payload nhạy cảm; phân quyền dashboard, DLQ và công cụ replay |
| **Đa broker** | Mã hóa/xác thực liên node, quản lý secret và xác minh endpoint khi chuyển vai trò |

Không cho tài khoản producer tự động có quyền quản trị hoặc quyền đọc tất cả queue. Broker đang mở TLS nhưng ACL sai vẫn có thể rò rỉ thông điệp.

## 11. Bài thực hành phân tích kiến trúc qua sự cố

Thực hiện trên một broker dành cho học tập, với ít nhất một queue **payment.commands** và hai consumer giả lập.

### Tình huống A — Consumer đang offline

**Thao tác:** dừng tất cả consumer, gửi ba persistent message, xem message count và storage.  
**Giải thích:** broker nhận và xếp chờ dù chưa thể dispatch. Nếu queue durable/persistence phù hợp, message chưa ack có thể được phục hồi sau restart.  
**Tiêu chí đạt:** nêu được dữ liệu đang nằm ở tầng nào và điều kiện giữ được message khi broker khởi động lại.

### Tình huống B — Worker fail sau khi nhận

**Thao tác:** chạy lệnh **fail** trong chương trình Java rồi chạy **receive**.  
**Giải thích:** message có thể đã được đưa tới client nhưng chưa được commit; rollback dẫn tới redelivery theo broker policy.  
**Tiêu chí đạt:** không nhầm “đã dispatch” với “đã hoàn tất nghiệp vụ”; giải thích được trường hợp message lặp.

### Tình huống C — Không có queue tương ứng

**Thao tác:** producer gửi vào một tên mới trong môi trường **tắt auto-create**, và so sánh với môi trường được **bật auto-create** có quyền phù hợp.  
**Giải thích:** handle Destination của JMS không quyết định broker đã có queue thực. Routing lỗi có thể gây exception hoặc hành vi khác theo protocol/configuration; kiểm chứng trực tiếp.  
**Tiêu chí đạt:** tách được lỗi kết nối, lỗi quyền và lỗi provisioning/routing.

### Tình huống D — Một event cho hai dịch vụ

**Thao tác:** gửi event vào address **orders.events** MULTICAST có hai queue subscription; đọc và ack trên mỗi queue riêng.  
**Giải thích:** routing tạo bản sao theo queue; dispatcher chỉ phân phối cho consumer của từng queue.  
**Tiêu chí đạt:** nhận biết việc ack ở queue A không phải ack ở queue B.

### Tình huống E — Producer nhanh hơn consumer

**Thao tác:** gửi một loạt message, làm consumer xử lý chậm có chủ đích. Ghi số message pending, in-flight, tuổi message, paging và throughput.  
**Giải thích:** storage và backpressure hấp thụ chênh lệch tốc độ trong giới hạn tài nguyên; chúng không tạo thêm năng lực xử lý downstream.  
**Tiêu chí đạt:** đề xuất giới hạn, cảnh báo và thay đổi capacity dựa trên chỉ số, không chỉ dựa vào queue depth.

### Tình huống F — TTL và lỗi xử lý là hai nhánh khác nhau

**Thao tác:** thiết lập TTL ngắn cho một message, tạo một message khác cố tình rollback nhiều lần; quan sát expiry và DLQ theo policy.  
**Giải thích:** expiry liên quan thời hạn, DLQ thường liên quan failure/redelivery policy.  
**Tiêu chí đạt:** chỉ đúng đường đi cuối cùng của từng message và không phát lại mà thiếu dedup.

## 12. Các nhầm lẫn cần tránh

1. **“JMS chính là protocol TCP của ActiveMQ.”** JMS là API; transport/protocol do client và broker thống nhất.
2. **“Đã kết nối thì chắc chắn gửi/nhận được mọi queue.”** Quyền thao tác và queue binding là các kiểm tra khác.
3. **“Address và queue trong Artemis là một.”** Address để route; queue giữ message chờ consumer. Một address có thể có nhiều queue.
4. **“Queue có hai consumer sẽ tạo hai bản sao.”** Đây là cạnh tranh trên một queue; fan-out cần các subscription/queue tương ứng.
5. **“Persistent message luôn có người nhận sau offline.”** Với topic phải xem riêng durable subscription và điều kiện lưu trữ.
6. **“Broker đã dispatch thì message được xử lý xong.”** Chỉ ack/commit phù hợp mới hoàn tất ở tầng messaging; hiệu ứng database cần xác minh riêng.
7. **“Paging là bằng chứng không thể mất dữ liệu.”** Paging quản lý backlog/tài nguyên, không thay thế persistence và backup.
8. **“Một cluster tự đồng bộ toàn bộ queue lên tất cả node.”** Routing liên node và HA replication là các mục đích khác nhau.
9. **“Nhiều consumer giữ được thứ tự xử lý tổng thể.”** Concurrent processing và redelivery có thể làm thay đổi thứ tự hoàn thành.
10. **“Queue depth thấp nghĩa là không có vấn đề.”** Message có thể đã in-flight hoặc consumer đang bị treo ở downstream.

## 13. Checklist thiết kế một pipeline đáng tin cậy

- [ ] Xác định chính xác đang dùng **ActiveMQ Classic hay Artemis**, phiên bản, client library, namespace **javax.jms/jakarta.jms** và wire protocol.
- [ ] Mô tả endpoint nhận kết nối, TLS, authentication, authorization và quyền auto-create.
- [ ] Vẽ bảng **destination → address → queue/subscription → consumer** (theo mô hình sản phẩm).
- [ ] Chỉ định rõ queue cạnh tranh hay topic fan-out, selector, durable subscription và yêu cầu thứ tự.
- [ ] Chọn delivery mode và transaction; kiểm tra persistence sau restart của broker/host phù hợp.
- [ ] Thiết kế **eventId/idempotency** để xử lý redelivery và commit kết quả mơ hồ.
- [ ] Có policy cho retry, redelivery delay, DLQ, TTL/expiry, replay và retention.
- [ ] Đặt ngưỡng về memory, disk, paging, backlog và producer backpressure; thử consumer chậm.
- [ ] Giám sát queue count, in-flight, message age, ACK/dequeue rate, DLQ và storage usage.
- [ ] Nếu mở rộng đa broker, ghi rõ phần nào là routing/cluster, phần nào là HA/replication và đo bằng fault injection.

**Kết luận:** Khi một message “biến mất”, chậm hoặc xuất hiện lần nữa, hãy lần theo **năm điểm kiểm chứng**: kết nối đã hợp lệ chưa, routing vào queue nào, message được lưu theo policy nào, dispatcher đã giao cho consumer nào, và ack/commit có thực sự hoàn tất không. Chính chuỗi nguyên nhân này là nền tảng để xây dựng producer/consumer Java, xử lý transaction, redelivery, DLQ, bảo mật và vận hành ActiveMQ Classic hoặc Artemis một cách đáng tin cậy.
