# Artemis Core bridge và chuyển tiếp tin cậy giữa broker

> **Chương:** Kết nối nhiều broker  
> **Module:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic/Artemis, giao tiếp queue/topic bất đồng bộ, JMS acknowledgment, transaction, redelivery, DLQ và vận hành đáng tin cậy.  
> **Phạm vi chính:** **ActiveMQ Artemis Core bridge** giữa **hai Artemis brokers**, không phải ActiveMQ Classic network connector, JMS bridge hay một cluster connection. Bài dùng cấu hình `broker.xml` tương thích mô hình Artemis **2.57.0** và Java 17/`jakarta.jms.*` để kiểm chứng đường chuyển tiếp.

## 1. Bài toán: dữ liệu vào broker A nhưng phải được xử lý tại broker B

Hệ thống đặt **broker A** ở khu vực nhận đơn, **broker B** ở khu vực hoàn tất đơn hàng. Producer Java gửi command `ShipmentRequested` vào A; consumer ở B phải nhận các command này. Mạng A → B có thể ngắt trong vài phút và hai broker có **store độc lập**.

Yêu cầu:

1. Producer chỉ cần gửi tới **A**. Không yêu cầu producer phải biết endpoint hoặc trạng thái kết nối tới B.
2. B tạm dừng hoặc mạng đứt: command đã được A **commit bền vững** phải chờ, không biến mất chỉ vì bridge đang retry.
3. B khôi phục: bridge kết nối lại, **chuyển tiếp backlog** vào một queue phù hợp tại B.
4. Nếu B đã chấp nhận command nhưng xác nhận bị mất giữa đường, bridge có thể gửi lại mà **không tự tạo hai bản sao ở queue đích**, trong giới hạn duplicate detection được bảo toàn.
5. Consumer nghiệp vụ vẫn phải **idempotent** khi crash giữa xử lý DB và ACK JMS.

Sơ đồ lab:

~~~mermaid
flowchart LR
    P["Java producer"] -->|"JMS PERSISTENT, commit"| AS["Broker A / source address lab.bridge.source"]
    AS --> AQ[("Source queue lab.bridge.source")]
    AQ -->|"Core bridge: remote Core protocol"| BA["Broker B / target address lab.bridge.target"]
    BA --> BQ[("Target queue lab.bridge.target")]
    BQ --> C["Java consumer: process + commit"]
    AQ -.->|"B down: chờ, reconnect"| AQ
~~~

**Core bridge là một cơ chế broker-side:** Nó **consume từ một queue có sẵn trên A** và **forward tới một address ở B**. Source và target **không cần chung cluster**, không cần chung journal/DB store, và thông thường mỗi broker dùng storage độc lập.

### Mục tiêu cuối bài

Bạn có thể: cấu hình hai broker, giải thích chính xác `queue-name` và `forwarding-address`, phân tích xác nhận chuyển tiếp/duplicate detection, kiểm tra backlog khi đích lỗi, đặt retry/flow-control/security hợp lý và nêu giới hạn “once-and-only-once” ở tầng broker.

## 2. Phân biệt Core bridge với những cơ chế tương tự

| Giải pháp | Nguồn/đích | Đặc trưng | Khi nào nên chọn |
|---|---|---|---|
| **Artemis Core bridge** | **Một source queue** trên A → **target address** tại B qua Core protocol | Cấu hình ở source broker, reconnect và duplicate detection | Chuyển message tin cậy giữa hai Artemis brokers, kể cả hai cluster độc lập/WAN |
| **Artemis cluster connection** | Nhiều nodes trong một cluster Artemis | Topology, load balancing/redistribution, dùng bridge nội bộ | Các brokers cùng kiến trúc cluster, phân tải/HA theo cluster |
| **Artemis JMS bridge** | Hai JMS providers (có thể khác hãng) | JMS API, QoS modes, có thể cần XA cho once-and-only-once | Nguồn/đích không cùng loại hoặc chỉ có JMS API |
| **Artemis federation** | Policies upstream/downstream giữa brokers | Forwarding dựa vào demand/policy | Muốn kết nối theo nhu cầu hoặc kiến trúc federation |
| **Artemis divert** | Một source address → address khác **trong cùng broker** | Copy/move theo filter | Chuyển đường đi nội bộ một broker |
| **Classic network of brokers** | ActiveMQ **Classic** brokers | OpenWire/networkConnector, semantics khác | Hệ Classic, không dùng thay XML Core bridge của Artemis |

**Không trộn XML:** `<bridge>` ở đây nằm trong **Artemis `broker.xml`**; không đặt vào `activemq.xml` của ActiveMQ Classic. JMS producer/consumer được dùng **chỉ để tạo và kiểm tra message ở hai đầu**, còn chính bridge hoạt động bằng Artemis Core protocol, **không phải một process Java JMS custom**.

## 3. Đường đi của một message và ranh giới xác nhận

Giả sử producer gửi message `eventId=E100`:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant A as Broker A: source queue
    participant BR as Core bridge
    participant B as Broker B: target address/queue
    participant C as Target consumer
    P->>A: send persistent E100
    P->>A: JMS transaction commit
    A-->>P: commit thành công
    A->>BR: Message E100 từ source queue
    BR->>B: Forward E100 + duplicate ID
    B->>B: Check duplicate-ID cache; route vào target queue
    B-->>BR: Acknowledge/confirmation
    BR->>A: Source delivery được xác nhận
    B->>C: Deliver E100
    C->>C: Business processing
    C-->>B: JMS commit/ACK
~~~

**Đừng đọc sơ đồ như một XA transaction trải qua cả ba thành phần.** Bridge tiến hành chuyển tiếp và nhận xác nhận bất đồng bộ; có một **khoảng thời gian cùng message còn được xem là đang chuyển/đang giữ ở A và đã có bản sao tại B**. Nếu connection mất đúng khoảng này, A có thể gửi lại. Duplicate detection ở B là cơ chế xử lý tình huống đó.

### 3.1. Ba lớp “thành công” phải đo riêng

| Thông báo thành công | Chứng minh | **Không** chứng minh |
|---|---|---|
| Producer nhận JMS `commit()` thành công ở **A** | Broker A xác nhận transaction gửi tới source queue theo durability policy | B đã nhận hoặc consumer B đã xử lý |
| Bridge forward và nhận remote confirmation | Giai đoạn chuyển tiếp broker A→B đã được xác nhận theo bridge protocol | HTTP/DB nghiệp vụ của consumer B đã commit |
| Consumer ở **B** commit JMS sau side effect | B đã xác nhận delivery của consumer | Không có side effect trùng trong các lần xử lý trước đó |

Nếu consumer B đã ghi DB nhưng chết trước ACK, B vẫn có thể redeliver ngay cả khi Core bridge hoàn toàn khỏe. Vì vậy “exactly once” trong tài liệu Core bridge là **once-and-only-once forwarding tới broker đích trong điều kiện duplicate detection**, **không** là exactly-once business processing.

### 3.2. Vì sao source queue phải durable?

Một source message **non-persistent** có thể biến mất khi A restart. Để thực nghiệm đảm bảo tồn qua broker restart:

- Source queue tồn tại bền vững trên A.
- Producer gửi `DeliveryMode.PERSISTENT`.
- A bật broker persistence và storage hoạt động an toàn.
- Producer chờ `commit()` thành công trước khi coi command đã được chấp nhận.
- B có target queue durable và broker persistence phù hợp.
- Không xóa/purge source queue hoặc tắt bridge theo cách làm thay đổi trách nhiệm chuyển tiếp trong khi đang có backlog.

**Core bridge không “hồi sinh” message vốn đã bị mất ở A trước khi forward.** Nó bổ sung kết nối tin cậy **giữa brokers**, không thay thế persistence của source/target.

## 4. Thiết kế tên address/queue và hai Artemis instances

Để tránh nhầm *address* với *queue*, lab dùng tên dễ kiểm chứng:

| Nơi | Loại | Tên | Mục đích |
|---|---|---|---|
| Broker A | Source **address** anycast | `lab.bridge.source` | Producer gửi command vào A |
| Broker A | Source **queue** durable | `lab.bridge.source` | Bridge có tên queue cụ thể để consume |
| Broker A | Connector | `to-b-core` | Endpoint Core ở B |
| Broker A | Core bridge | `bridge-a-to-b` | Consume từ source queue rồi forward |
| Broker B | Target **address** anycast | `lab.bridge.target` | Nhận message bridge forward |
| Broker B | Target **queue** durable | `lab.bridge.target` | Consumer B nhận command |

Dùng một máy để diễn giải cấu hình, với:

~~~text
Broker A: tcp://127.0.0.1:61616
Broker B: tcp://127.0.0.1:61617
~~~

**Hai ports trên cùng máy chỉ kiểm thử kết nối giữa hai broker processes**, không chứng minh chịu lỗi host hoặc WAN. Mỗi instance phải có **thư mục data/journal/bindings/paging/large-messages riêng**; **không được** trỏ A/B vào cùng data folder nếu mục đích là hai brokers độc lập. Trên hai host, thay hostname/port và bật TLS/mTLS phù hợp.

### 4.1. Chuẩn bị hai broker riêng

Sử dụng hai Artemis instances độc lập đã được tạo bằng quy trình cài đặt tương ứng. Trên B, bảo đảm **acceptor hiện có** lắng nghe `127.0.0.1:61617` và **cho phép CORE**. Nếu chạy hai Artemis instances cùng host, thay đổi acceptor/management ports để không xung đột.

Không thêm một `<acceptor>` mới trùng port với acceptor khác. Nếu cần một fragment để hiểu URL acceptor ở B:

~~~xml
<!-- Minh họa; dùng/thay đổi acceptor hiện có, không khai báo trùng. -->
<acceptor name="artemis-core-b">
    tcp://0.0.0.0:61617?protocols=CORE
</acceptor>
~~~

**Bridge không dùng JMS Topic hay OpenWire failover URI.** Nó kết nối bằng Core transport tới connector được khai báo trên A.

## 5. Cấu hình broker B: destination phải có queue thực sự

Trên **B**, mở `ARTEMIS_B/etc/broker.xml`. Trong section `<addresses>` đang có, tạo một anycast destination:

~~~xml
<address name="lab.bridge.target">
    <anycast>
        <queue name="lab.bridge.target">
            <durable>true</durable>
        </queue>
    </anycast>
</address>
~~~

Điều kiện cần kiểm tra:

- Target **address** tên `lab.bridge.target`, target **queue** tên `lab.bridge.target`; nếu một trong hai sai, message có thể không route vào queue mong muốn.
- Broker B có `persistence-enabled=true` và storage đủ bền vững.
- Nếu B bật security, account mà bridge dùng có quyền **send** vào target address.
- Nếu consumer B dùng user khác, user đó có quyền **consume** từ target queue.

**Cảnh báo no-route:** Một remote broker có thể **nhận message tới address nhưng không có queue phù hợp**, dẫn đến không có backlog cho consumer. “Bridge connected” **không đồng nghĩa** business destination đã được provision. Luôn kiểm chứng B có **queue thực nhận message**, đặc biệt khi chạy flow-control, filter hoặc routing-type khác nhau.

### 5.1. Duplicate detection trên target broker

Artemis dùng một **duplicate-ID cache theo address**. Trong `<address-settings>` của B, có thể đặt cache riêng cho lab:

~~~xml
<address-setting match="lab.bridge.target">
    <id-cache-size>50000</id-cache-size>
    <address-full-policy>PAGE</address-full-policy>
</address-setting>
~~~

Trong `<core>` của B, xác nhận thuộc tính:

~~~xml
<persist-id-cache>true</persist-id-cache>
~~~

Đây là mảnh cấu hình bổ sung, **không thêm một section `<core>` trùng**; nếu `persist-id-cache` không được ghi rõ, default hiện hành của Artemis là **true**. Khi cache được persist, B có cơ hội nhận diện duplicate sau restart. Cache **hữu hạn**: ID cũ bị ghi đè khi vượt dung lượng; không bảo đảm chống trùng vô hạn.

**Không đặt `id-cache-size=0`** ở target nếu đang yêu cầu bridge duplicate detection; 0 tắt cache và làm mất lớp bảo vệ khi bridge phải resend.

## 6. Cấu hình broker A: queue nguồn và Core bridge

### 6.1. Source queue được bridge consume

Trên **A**, trong section `<addresses>` của `ARTEMIS_A/etc/broker.xml`, khai báo:

~~~xml
<address name="lab.bridge.source">
    <anycast>
        <queue name="lab.bridge.source">
            <durable>true</durable>
        </queue>
    </anycast>
</address>
~~~

**`queue-name` trong bridge phải đúng tên queue này**, không phải tên address bất kỳ hoặc FQQN tự đoán. Queue phải **đã tồn tại khi bridge được khởi tạo**; nếu broker A auto-creates queue sau khi bridge khởi động, bridge có thể không có source queue hợp lệ. Provision tường minh trước khi start hoặc reload bridge theo thủ tục được hỗ trợ.

**Không chạy một consumer nghiệp vụ khác cùng queue nguồn** rồi mong cả consumer đó và bridge đều nhận bản sao: chúng cạnh tranh cùng một queue. Nếu muốn giữ một bản local và chuyển một bản remote, dùng một multicast address với **hai queues**, trong đó bridge consume queue dành riêng cho nó, hoặc dùng divert/fan-out được thiết kế rõ.

### 6.2. Connector tới broker B

Trong section `<connectors>` **hiện có** của A:

~~~xml
<connector name="to-b-core">tcp://127.0.0.1:61617</connector>
~~~

Connector tên `to-b-core` cung cấp host/port và protocol transport cho bridge. **Đây không phải source queue**, không phải tên cluster; B phải có acceptor Core truy cập được ở đúng endpoint. Với TLS, connector phải có tham số SSL/truststore hoặc cơ chế chứng chỉ được version hỗ trợ.

### 6.3. Bridge đầy đủ tại source broker

Trong section `<bridges>` của A (**con trực tiếp của `<core>`**), đặt:

~~~xml
<bridge name="bridge-a-to-b">
    <queue-name>lab.bridge.source</queue-name>
    <forwarding-address>lab.bridge.target</forwarding-address>
    <routing-type>ANYCAST</routing-type>

    <ha>false</ha>
    <retry-interval>1000</retry-interval>
    <retry-interval-multiplier>2.0</retry-interval-multiplier>
    <max-retry-interval>10000</max-retry-interval>
    <initial-connect-attempts>-1</initial-connect-attempts>
    <reconnect-attempts>-1</reconnect-attempts>

    <use-duplicate-detection>true</use-duplicate-detection>
    <confirmation-window-size>262144</confirmation-window-size>
    <producer-window-size>1048576</producer-window-size>
    <concurrency>1</concurrency>

    <!-- Credential CHỈ dành cho lab: provision user này trên B. -->
    <user>bridge_lab</user>
    <password>lab-only-change-me</password>

    <static-connectors>
        <connector-ref>to-b-core</connector-ref>
    </static-connectors>
</bridge>
~~~

**Các fragment thuộc ba section khác nhau trong A**: `<addresses>`, `<connectors>` và `<bridges>`. Không copy ra nhiều section trùng hoặc tạo root mới. Trên một instance có security/credentials riêng, account `bridge_lab` phải được provision trên **B** với đúng password; secret mẫu **không được** sử dụng production.

**Vì sao đặt `routing-type=ANYCAST`?** Source nhận JMS Queue → anycast. Ở B cũng đã provision **anycast queue**. Nếu để routing-type `PASS` mà message origin mang routing type không khớp B, bridge có thể kết nối thành công nhưng message không route vào queue. Dùng `ANYCAST` tường minh khiến ví dụ dễ kiểm chứng. Khi target multicast cần fan-out, phải thiết kế lại routing type phù hợp.

### 6.4. Các tham số có tác dụng chính xác ở đâu?

| Tham số | Ý nghĩa | Nguy cơ khi hiểu sai |
|---|---|---|
| `name` | Định danh bridge, duy nhất trong broker A | Trùng tên gây lỗi cấu hình/management |
| `queue-name` | **Queue nội bộ tại A** mà bridge tiêu thụ | Không có queue → bridge không có nguồn hợp lệ |
| `forwarding-address` | **Address đích tại B** | Sai address → no-route hoặc sai luồng |
| `routing-type=ANYCAST` | Ghi routing type khi forward | Nếu `PASS` giữ MULTICAST nhưng B chỉ có anycast, không route đúng |
| `ha=false` | Không khám phá/đi theo HA topology của target | Không giúp B tự trở thành HA; standalone lab dùng false |
| `initial-connect-attempts=-1` | Thử kết nối ban đầu vô hạn | Nếu đặt số hữu hạn có thể bỏ cuộc khi B chưa sẵn sàng |
| `reconnect-attempts=-1` | Thử reconnect vô hạn sau mất kết nối | Không tự bảo đảm lưu lượng; backlog vẫn phải monitor |
| `retry-interval` | Backoff ban đầu 1.000 ms | Không phải thời gian chuyển message end-to-end |
| `retry-interval-multiplier=2.0` | Tăng độ trễ giữa retries | Nếu quên max, có thể đợi quá lâu |
| `max-retry-interval=10000` | Giới hạn backoff tại 10 giây | Không phải max outage duration |
| `use-duplicate-detection=true` | Đặt duplicate ID nếu chưa có, hỗ trợ target dedup | Không chống business duplicate do producer publish mới |
| `confirmation-window-size=262144` | Cửa sổ confirmation của Core connection | Đặt không phù hợp flow-control có thể gây nghẽn |
| `producer-window-size=1048576` | Credit/flow control producer phía bridge | Không đồng nghĩa source queue có dung lượng 1 MiB |
| `concurrency=1` | Một bridge worker để dễ kiểm thử | Tăng concurrency ảnh hưởng parallelism/order |
| `static-connectors` | Chỉ đến connector `to-b-core` | Không phải syntax `failover:(...)` của Classic |
| `user/password` | Tài khoản để bridge kết nối/ghi ở B | Sai quyền là lỗi remote, không phải lỗi source sender |

**Không thiết lập `reconnect-attempts=-1` rồi bỏ monitoring.** Nó giúp bridge tiếp tục thử sau outage nhưng cũng có nghĩa backlog có thể tăng lâu nếu B chết. Phải có giới hạn lưu trữ, cảnh báo queue age và runbook xử lý.

## 7. Vì sao duplicate detection tạo ra khả năng once-and-only-once forwarding?

### 7.1. “Đã nhận nhưng chưa biết” là cửa sổ lỗi quan trọng nhất

Xét chuỗi:

~~~text
t0  A có source message E100 chưa được bridge xác nhận.
t1  Bridge forward E100 với duplicate ID D100 tới B.
t2  B ghi nhận D100 vào duplicate-ID cache và route E100 vào target queue.
t3  Mạng A↔B đứt TRƯỚC KHI confirmation tới bridge.
t4  A vẫn coi E100 chưa được xác nhận, sẽ gửi lại sau reconnect.
t5  B thấy D100 đã tồn tại => bỏ bản forward trùng, không route thêm.
t6  Bridge nhận được confirmation hợp lệ, source queue được giải phóng.
~~~

Không có duplicate detection, một message có thể xuất hiện **hai lần ở target** nếu bridge resend sau acknowledgement-loss. Với duplicate detection, broker B kiểm tra property Core đặc biệt `_AMQ_DUPL_ID` và cache ID đã thấy theo **target address**. Nếu trùng và còn trong cache, message retry **không được route thành bản sao mới**.

### 7.2. Ba loại ID phải phân biệt

| Trường | Ai tạo/chịu trách nhiệm? | Dùng để làm gì? |
|---|---|---|
| `eventId` | Ứng dụng/domain | Idempotency nghiệp vụ xuyên producer retry, bridge, consumer replay |
| `JMSMessageID` | JMS provider/broker | Nhận diện một JMS message; có thể khác sau publish/replay |
| `_AMQ_DUPL_ID` | Artemis duplicate detection; bridge có thể tự thêm | Broker B loại bản forward trùng trong cache theo address |

**Nếu message ban đầu đã có duplicate ID**, bridge theo tài liệu sẽ không cần tự tạo ID khác. Vì vậy producer chỉ nên tự gắn `_AMQ_DUPL_ID` nếu hiểu rõ semantics và uniqueness; tái sử dụng ID không đúng có thể khiến B **bỏ message hợp lệ**.

### 7.3. Giới hạn của cache và tính bền vững

Artemis dùng **cache vòng hữu hạn trên mỗi address**. Khi số ID mới vượt dung lượng, ID cũ bị thay thế. Nếu sự cố kéo dài đủ lâu hoặc traffic target quá lớn, ID cũ đã bị evict, lần resend rất muộn có thể không còn được nhận diện là duplicate.

Nếu `persist-id-cache=true` (default hiện hành), cache được lưu bền vững, giúp sau B restart vẫn nhận diện được ID còn trong cache. Tuy nhiên:

- Cache persist **không làm cache vô hạn**.
- Quản trị xóa cache, cấu hình `id-cache-size=0` hoặc restore snapshot cũ có thể phá giả định.
- Nếu B gửi message tới consumer rồi consumer chưa ACK, B có thể **redeliver**; duplicate detection bridge không chặn vòng giao lại này.
- Producer gửi lại **một message mới** với cùng `eventId` nhưng duplicate ID khác thì B có thể nhận **cả hai**.

Do đó once-and-only-once forwarding là một bảo đảm ở **tầng broker**, trong các điều kiện về durable storage và duplicate-ID cache. **Consumer nghiệp vụ vẫn cần khóa idempotency** như unique `(consumerGroup,eventId)` trong DB.

### 7.4. Quan sát duplicate detection

Khi broker B phát hiện duplicate, Artemis có thể log warning `AMQ222059`: duplicate message detected; message will not be routed. Đừng xem mọi warning này là “message bị mất”: trong kịch bản bridge resend, đây thường là cơ chế **chặn bản trùng theo thiết kế**. Nhưng nếu warning liên tục với eventId hợp lệ mới, kiểm tra producer dùng lại duplicate ID hoặc cache bị cấu hình không tương thích.

## 8. Lưu lượng, confirmation window và backlog khi mạng chậm

### 8.1. Confirmation window khác producer credit

- `confirmation-window-size`: kích thước cửa sổ byte điều khiển các confirmation từ remote; liên quan khôi phục và nhịp xác nhận.
- `producer-window-size`: flow control giữa bridge-producer và broker B.
- `min-large-message-size`: ngưỡng xử lý large messages khi bridge chuyển payload lớn, không phải memory quota.
- `retry-interval` / `connection-ttl`: kiểm soát retry và phát hiện kết nối chết, không phải giới hạn hàng đợi.

**Lưu ý từ tài liệu Artemis:** Nếu bridge gửi tới một address có `address-full-policy=BLOCK` trong khi queue liên quan có `max-size-bytes`, hãy đảm bảo `confirmation-window-size <= max-size-bytes` để tránh luồng message bị **kẹt** do tương tác confirmation/flow control. Ví dụ confirmation window 256 KiB cần kiểm chứng phù hợp nếu destination configured BLOCK với `max-size-bytes=1 MiB`.

### 8.2. Backpressure không phải mất message

Nếu B dừng hoặc không có credit, tốc độ bridge forward có thể về 0, backlog ở A tăng:

~~~text
Producer A:       400 msg/s
Bridge forwarding: 0 msg/s khi B down
Backlog growth:    +400 msg/s
Sau 10 phút:      khoảng 240.000 messages (chưa tính TTL/expiry)
~~~

Khi B khôi phục, bridge bắt đầu chuyển backlog nhưng có thể chưa đủ tốc độ để bắt kịp ingress; ví dụ bridge chuyển 600 msg/s trong khi producer vẫn gửi 400 msg/s thì backlog giảm ròng khoảng 200 msg/s. Với 240.000 messages cần khoảng 1.200 giây để drain hết trong giả định tốc độ không đổi, không tính paging/large-message overhead.

**Phải đo disk/queue age của A**, vì “broker A chưa hết heap” không có nghĩa backlog paging/journal sẽ không làm đầy storage. Các chính sách `PAGE/BLOCK/FAIL` của source address, target address và disk threshold phải được thiết kế đồng bộ. Không bật `DROP` cho các command bắt buộc chỉ để bridge tiếp tục “chạy xanh”.

### 8.3. Concurrency không phải công tắc bảo toàn thứ tự

`concurrency=1` là mặc định và phù hợp lab muốn đối chiếu theo thứ tự. Nếu tăng `concurrency>1` để khai thác WAN latency, Artemis tạo nhiều bridge workers và thêm đường song song; throughput có thể tăng nhưng **không còn giả định một luồng dispatch đơn**. Ngay cả với concurrency 1, nhiều producers, priority, scheduled messages, redelivery hoặc consumer B xử lý song song vẫn có thể khiến **business commit order** khác send order.

Nếu cần thứ tự theo đơn hàng, hãy mang `aggregateId` và `sequence` ở message, dùng version check/idempotency tại hệ thống đích; không suy “bridge forward tin cậy” tự bảo đảm global FIFO.

## 9. Java 17 / Jakarta JMS lab: publish ở A và consume ở B

### 9.1. Chuẩn bị

- Artemis A đang chạy tại `tcp://127.0.0.1:61616`, A/B dùng **data directories riêng**.
- Artemis B đang chạy tại `tcp://127.0.0.1:61617` (hoặc cố tình dừng khi làm outage test).
- A đã có `lab.bridge.source`, connector `to-b-core`, bridge `bridge-a-to-b`.
- B đã có `lab.bridge.target` với anycast queue, duplicate cache và quyền `bridge_lab` phù hợp.
- Hai instances dùng phiên bản Artemis tương thích, Core acceptor B được expose; client JMS kết nối được với cả A/B.
- Đặt biến môi trường `ARTEMIS_USER`, `ARTEMIS_PASSWORD` cho tài khoản test JMS trên cả hai brokers. Account bridge riêng trong XML là đường **broker-to-broker**, không phải client credential.

POM Maven minh họa cho **ứng dụng lab**, dùng Java 17/Jakarta Messaging:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <artemis.version>2.57.0</artemis.version>
</properties>
<dependencies>
    <dependency>
        <groupId>org.apache.activemq</groupId>
        <artifactId>artemis-jakarta-client</artifactId>
        <version>${artemis.version}</version>
    </dependency>
</dependencies>
~~~

Trong môi trường thật, ghim client/broker/JDK theo compatibility matrix của phiên bản bạn triển khai. Lab không cần sửa code producer khi A forward đi B: **bridge là cấu hình broker A**.

### 9.2. Một lớp Java đủ để đo eventId, source/target và commit

File `ArtemisCoreBridgeLab.java`:

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.HashSet;
import java.util.Set;

public final class ArtemisCoreBridgeLab {
    private static final String A_URL = "tcp://127.0.0.1:61616";
    private static final String B_URL = "tcp://127.0.0.1:61617";

    private static final String SOURCE_QUEUE = "lab.bridge.source";
    private static final String TARGET_QUEUE = "lab.bridge.target";

    public static void main(String[] args) throws Exception {
        if (args.length != 3 ||
                !("send".equals(args[0]) || "receive".equals(args[0])) ||
                !args[1].matches("[A-Za-z0-9_-]{1,40}")) {
            usage();
            return;
        }

        int count;
        try {
            count = Integer.parseInt(args[2]);
        } catch (NumberFormatException failure) {
            usage();
            return;
        }

        if (count < 1 || count > 50) {
            throw new IllegalArgumentException("count phải từ 1..50");
        }

        String username = requiredEnv("ARTEMIS_USER");
        String password = requiredEnv("ARTEMIS_PASSWORD");

        boolean sending = "send".equals(args[0]);
        String url = sending ? A_URL : B_URL;

        ActiveMQConnectionFactory cf =
            new ActiveMQConnectionFactory(url);

        // Mỗi tiến trình dùng JMSContext / session transacted riêng.
        try (JMSContext ctx = cf.createContext(
                username, password, JMSContext.SESSION_TRANSACTED)) {

            if (sending) {
                send(ctx, args[1], count);
            } else {
                receive(ctx, args[1], count);
            }
        }
    }

    private static void send(
            JMSContext ctx, String runId, int count) throws Exception {

        Queue queue = ctx.createQueue(SOURCE_QUEUE);
        var producer = ctx.createProducer()
            .setDeliveryMode(DeliveryMode.PERSISTENT);

        for (int seq = 1; seq <= count; seq++) {
            String eventId = runId + ":" + seq;
            String json = "{\"eventId\":\"" + eventId
                + "\",\"operation\":\"ShipOrder\",\"seq\":" + seq + "}";

            TextMessage message = ctx.createTextMessage(json);
            message.setStringProperty("eventId", eventId);
            message.setStringProperty("runId", runId);
            message.setIntProperty("seq", seq);

            try {
                producer.send(queue, message);
                ctx.commit();

                System.out.printf(
                    "A_SEND_COMMITTED eventId=%s JMSMessageID=%s%n",
                    eventId, message.getJMSMessageID());
            } catch (Exception failure) {
                try {
                    ctx.rollback();
                } catch (RuntimeException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

    private static void receive(
            JMSContext ctx, String runId, int expected)
            throws Exception {

        Queue queue = ctx.createQueue(TARGET_QUEUE);
        // runId được validate nên có thể dùng trong selector lab.
        String selector = "runId = '" + runId + "'";
        JMSConsumer consumer = ctx.createConsumer(queue, selector);

        Set<String> seen = new HashSet<>();
        int committed = 0;
        int duplicates = 0;

        try {
            while (committed < expected) {
                Message message = consumer.receive(3000);
                if (message == null) {
                    break; // Bridge còn retry hay queue tạm thời rỗng.
                }

                try {
                    if (!(message instanceof TextMessage text)) {
                        throw new IllegalArgumentException(
                            "Demo chỉ hỗ trợ TextMessage");
                    }

                    String eventId =
                        text.getStringProperty("eventId");
                    int seq = text.getIntProperty("seq");

                    if (!seen.add(eventId)) {
                        duplicates++;
                        System.out.println(
                            "DUPLICATE_OBSERVED " + eventId);
                    }

                    // Demo: chỉ log; nghiệp vụ thật cần transaction DB
                    // idempotent theo (consumerGroup, eventId).
                    System.out.printf(
                        "B_RECEIVED id=%s seq=%d jmsId=%s "
                        + "redelivered=%s%n",
                        eventId, seq,
                        text.getJMSMessageID(),
                        text.getJMSRedelivered()
                    );

                    ctx.commit();
                    committed++;
                } catch (Exception failure) {
                    ctx.rollback();
                    throw failure;
                }
            }
        } finally {
            consumer.close();
        }

        System.out.printf(
            "B_COMMITTED=%d UNIQUE=%d DUPLICATES=%d EXPECTED=%d%n",
            committed, seen.size(), duplicates, expected);
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "Thiếu biến môi trường " + key);
        }
        return value;
    }

    private static void usage() {
        System.out.println(
            "ArtemisCoreBridgeLab send|receive <runId> <1..50>");
    }
}
~~~

**Vì sao không viết một JMS “bridge service” trong ứng dụng?** Java lab trên chỉ gửi vào A và nhận từ B; không có bất kỳ code nào nhận A rồi gửi B. Nếu B vẫn nhận đủ E100 sau khi bridge reconnect, đó là bằng chứng bridge thực hiện forwarding theo cấu hình.

**Giới hạn của bài test:** `HashSet` chỉ phát hiện duplicate **trong một lần chạy receiver**, không thay thế unique constraint DB across restarts. `receive(3000) == null` nghĩa là chưa có message phù hợp trong 3 giây, **không** chứng minh queue đích trống vĩnh viễn. Log `A_SEND_COMMITTED` là xác nhận A, chưa phải chứng cứ B đã ACK.

### 9.3. Vì sao producer không đặt duplicate ID thủ công?

Vì Core bridge đang cấu hình:

~~~xml
<use-duplicate-detection>true</use-duplicate-detection>
~~~

nó có thể tự gắn duplicate ID trước khi forward khi message chưa có. Đặt `_AMQ_DUPL_ID` một cách tùy tiện ở client lab có thể tạo va chạm ID và khiến B bỏ message hợp lệ. **Business eventId** vẫn được đặt rõ ràng để kiểm tra end-to-end.

## 10. Ba kịch bản kiểm chứng tin cậy

### Kịch bản A — Happy path

1. Start **B**, xác nhận `lab.bridge.target` có queue durable và Core acceptor lắng nghe port 61617.
2. Start **A**, xem log bridge đã kết nối target; kiểm tra bridge name/source queue đúng.
3. Xác nhận source/target queues không có message lab cũ và không có consumer ngoài bài.
4. Chạy `ArtemisCoreBridgeLab send HAPPY01 5`.
5. Quan sát sau khi bridge xử lý: source queue A giảm về 0, target queue B có **5** message (nếu consumer B chưa chạy).
6. Chạy `ArtemisCoreBridgeLab receive HAPPY01 5`; kỳ vọng `B_COMMITTED=5 UNIQUE=5 DUPLICATES=0`.
7. Kiểm tra target queue B về 0 sau JMS commit. Nếu sender đã commit ở A nhưng B không có message, kiểm tra bridge status, target address/routing, permissions và no-route.

### Kịch bản B — Target B ngừng trước khi producer gửi

1. Dùng một `runId` mới, ví dụ `DOWN01`. **Stop broker B sạch trong lab**, giữ nguyên store B.
2. Broker A vẫn chạy, Core bridge chuyển sang retry/reconnect.
3. Chạy `ArtemisCoreBridgeLab send DOWN01 5`. Producer vẫn có thể **commit vào A** nếu nguồn còn tài nguyên; điều đó không phụ thuộc B phải online ngay.
4. Trong console A, kiểm tra tồn tại **5 message chưa hoàn tất forwarding** ở queue nguồn (số ready/delivering có thể khác nhau theo in-flight state).
5. Start B. Đợi bridge reconnect và forward.
6. Trước khi chạy receiver B, xác nhận queue đích có 5 message và queue source đã được giải phóng sau confirmations; đo độ trễ phục hồi.
7. Chạy `ArtemisCoreBridgeLab receive DOWN01 5`: kỳ vọng năm eventId khác nhau, mỗi event ACK một lần.

**Điều chứng minh:** Broker A chịu trách nhiệm lưu message trong thời gian đích offline; bridge tự kết nối lại khi B trở lại. Nếu source queue có TTL/expiry, paging/quota, producer FAIL/BLOCK hoặc bị purge trong outage, kết quả có thể khác. **Retry không vô hiệu hóa các policy dữ liệu tại source.**

### Kịch bản C — Lỗi ngay sau target đã nhận, trước source được xác nhận

Đây là **cửa sổ có thể sinh duplicate khi không có duplicate detection**, nhưng rất khó kích hoạt deterministically bằng thao tác stop thông thường.

Quy trình phù hợp:

1. Trên môi trường **disposable**, chuẩn bị A/B durable, duplicate cache ở B được persist.
2. Dùng một lô eventId riêng; không có consumer B để queue target giữ backlog.
3. Theo dõi bridge confirmations và target queue; dùng fault injection có kiểm soát ở kết nối bridge A→B, không phá đồng thời KahaDB/journal hoặc file cache.
4. Sau reconnect, đối chiếu eventId nhận tại B, source backlog còn lại, số cảnh báo duplicate detection ở B (ví dụ `AMQ222059`).
5. Nếu có trùng JMS message đã được route ở B, kiểm tra cache size/persistence, bridge duplicate detection flag và liệu đó có thực sự là resend của **cùng** message hay là producer publish thêm message nghiệp vụ mới.

**Không cam kết mọi lần cắt mạng sẽ tạo log AMQ222059.** Chỉ khi fault rơi đúng sau target accept và trước source confirmation mới có khả năng bridge resend một message B đã thấy. Một lần thử không tạo warning vẫn có thể là bridge hoạt động đúng.

### Bảng nghiệm thu

| Chỉ số | Happy path | B down rồi phục hồi | Lost confirmation window |
|---|---|---|---|
| Producer commit trên A | Thành công | Thành công khi A còn capacity | Thành công trước khi test lỗi |
| Source queue giữ message chưa forward | Trong khoảng thời gian ngắn | Có, cho tới khi B nhận/confirm | Có thể có trong khi B đã nhận |
| Bridge reconnect | Không cần | **Có** | **Có** |
| Target queue khi chưa có consumer | 5 | 5 sau phục hồi | Không nên có 2 bản cùng eventId nếu cache còn ID |
| Unique business eventIds | 5 | 5 | 5 theo batch |
| Consumer JMS commit tại B | Sau nhận | Sau reconnect | Sau khôi phục |
| Cần idempotency nghiệp vụ | **Có** | **Có** | **Có** |

## 11. Failure matrix: sự cố ở đâu, queue nào phải được kiểm tra?

| Lỗi | Nơi bắt đầu điều tra | Kỳ vọng/hành động |
|---|---|---|
| Producer không kết nối A | Acceptors/security A, client JMS URL | Chưa có message được A commit; dùng retry/outbox có kiểm soát |
| A restart sau khi producer commit, B đang down | A persistence/source queue | Message persistent chưa hoàn tất forward vẫn còn nếu storage bền vững |
| B offline | Bridge retry status/log A, source queue age | Backlog A tăng; không tự bỏ message |
| B online nhưng bridge không connect | Connector port/TLS/Auth trên B | Kiểm tra `to-b-core`, endpoint, bridge user/role |
| Bridge connected nhưng B target queue trống | `forwarding-address`, `routing-type`, B address/queue binding | Sửa no-route; đừng suy đã delivery nghiệp vụ chỉ vì bridge connected |
| B nhận nhưng A không biết ack | Bridge confirmation/reconnect, target duplicate cache | Duplicate detection chặn resend, nếu ID còn cache |
| B restart và duplicate được route | `persist-id-cache`, `id-cache-size`, snapshot/cache eviction | Tăng/duy trì cache phù hợp, cần app idempotency |
| Receiver B crash trước ACK | Target queue redelivery/DLQ | Message có thể được xử lý lại; business idempotency |
| Source queue có một app consumer khác | Consumer count source queue | Consumer và bridge tranh message, làm “mất” bản sao remote |
| Không forward được do bridge filter | Filter expression và message properties | Message không khớp có thể nằm chờ mãi ở source queue |
| B áp `BLOCK`, flow control kẹt | Confirmation window, producer credit, address size | Kiểm tra `confirmation-window-size <= max-size-bytes` của policy |
| A đầy disk trong outage | Disk/page/journal, source address policy | Điều tiết producer, tăng capacity, không xóa journal/page files |
| Hai brokers cùng dữ liệu do trỏ chung data dir | Instance persistence config | **Sai kiến trúc**: Core bridge không cần shared store; tách ngay trên lab |

### 11.1. Bridge filter có thể khiến source queue nghẽn âm thầm

Artemis Core bridge có thể đặt filter:

~~~xml
<!-- Chỉ minh họa, không thêm vào lab chính: -->
<filter string="region = 'VN'"/>
~~~

Bridge khi ấy **chỉ tiêu thụ message khớp filter** từ source queue. Message không khớp **vẫn nằm trong queue**, không được tự route đi nơi khác. Nếu không có consumer khác, nó tích backlog. Nếu muốn copy tất cả message local nhưng chỉ gửi một phần sang remote, hãy thiết kế **queue riêng cho bridge** với queue filter khi route, hoặc một mô hình fan-out rõ ràng.

### 11.2. Source-to-target chỉ một hop, không tự định nghĩa luồng đi-về

Bridge A→B **không** mặc nhiên tạo đường B→A. Nếu cấu hình cả hai chiều trên cùng các address mà không có quy tắc chống vòng lặp, message có thể bị chuyển đi-về theo cách ngoài ý muốn. Dùng topology có hướng rõ, filter/property hop count, route ownership và các cơ chế duplicate detection/loop prevention thích hợp. Một duplicate cache hữu hạn **không phải** thiết kế thay thế cho vòng đời message có hướng.

### 11.3. Downstream failure khác bridge failure

Nếu receiver B xử lý thất bại:

- Message đã nằm ở B, có thể redeliver/DLQ **tại B**.
- Bridge không tự “lấy lại từ B để trả về A”.
- A có thể đã ACK nguồn sau khi B nhận và xác nhận.
- Lỗi business nên điều tra bằng receiver logs/target queue/DLQ, **không** đặt lại `reconnect-attempts` của bridge.

## 12. Bảo mật, HA và lựa chọn tham số production

### 12.1. Bridge remote credentials

Cấu hình demo dùng `bridge_lab` và một password **chỉ dành cho lab**. Production:

1. Cấp một service identity riêng chỉ có quyền send tới `lab.bridge.target` (hoặc tập address được phép), không dùng admin.
2. Bật TLS/mTLS cho connector A→B, xác thực hostname/CA và phân quyền tối thiểu.
3. Externalize secret theo phương thức Artemis/deployment hỗ trợ; không commit plaintext password vào repository hoặc in ra log.
4. Nếu cả hai brokers ở vùng mạng khác nhau, dùng firewall/ACL giới hạn các endpoint Core, tránh exposed admin surfaces.
5. Kiểm tra identity dùng bởi JMS producer A khác identity bridge remote B; không hoán đổi quyền send/consume mà không kiểm tra security semantics.

### 12.2. Bridge `ha=true` không biến hai standalone brokers thành HA cluster

Trong lab **B là một standalone broker**, nên cấu hình `ha=false`. Nếu B thật sự tham gia Artemis HA/cluster topology và bridge cần theo failover của target, có thể dùng `ha=true` cùng connector/discovery phù hợp. Nhưng không chỉ bật `ha=true` rồi coi B tự có replica, failover, shared-store hoặc quorum.

**Nếu source A có HA**, cũng cần bảo đảm bridge configuration và source queue tồn tại đúng trên node active sau failover. Core bridge không thay thế bất kỳ chính sách replication/shared-store nào dành cho broker A.

### 12.3. Chọn retry và flow-control theo SLA

| Quyết định | Gợi ý |
|---|---|
| `initial-connect-attempts=-1` | Giữ bridge chờ B khi startup, nếu SLA cho phép backlog |
| `reconnect-attempts=-1` | Tự khôi phục sau outage kéo dài; vẫn cần alert |
| Backoff từ 1s tới 10s | Tránh reconnect storm, cân đối RTO |
| `concurrency=1` | Dễ đối chiếu theo luồng; benchmark trước khi tăng |
| `confirmation-window-size` | Đặt phù hợp target `BLOCK/max-size-bytes`, không tùy tiện quá lớn |
| `producer-window-size` | Giảm nguy cơ bridge gửi vượt credit và gây memory pressure |
| `id-cache-size` target | Đủ để giữ ID của các message có thể retry trong thời gian relevant |
| `persist-id-cache=true` | Hữu ích khi B restart và còn cần dedup |
| Address full/disk policy tại A | Phải giữ backlog hoặc fail producer theo contract; không xóa message âm thầm |

**Không đưa một số cấu hình ở bảng này thành “con số tối ưu cho mọi hệ thống”.** Đo tải thật: message size, backlog khi WAN down, latency p95/p99, queue age, duplicate cache churn, CPU/GC và disk I/O.

## 13. Monitoring và runbook sự cố

### 13.1. Metrics cần có ở A và B

**Broker A (source):**

- Queue count/delivering/ready của `lab.bridge.source`.
- Oldest message age và tốc độ backlog growth khi B down.
- Bridge state: connected/disconnected, failures/reconnects, last successful confirmation, messages acknowledged/forwarded nếu management expose.
- Source journal/paging/disk free và producer send/commit latency.
- Alarm nếu bridge down quá SLA hoặc source queue tuổi message vượt ngưỡng.

**Broker B (target):**

- Target queue `lab.bridge.target` count/ready/delivering, enqueue/dequeue.
- Dup-ID cache size, duplicate warnings `AMQ222059`, persistence/restore status.
- Redelivery/DLQ, consumer failure và commit latency nghiệp vụ.
- Target address full/paging, disk utilization, Core acceptor/tls/auth failures.

**Ứng dụng:**

- `eventId`, `runId`, `JMSMessageID`, delivery count, business outcome, idempotency duplicate count.
- Không dùng eventId làm metric label high-cardinality; dùng structured logs/tracing khi cần điều tra.
- Nếu producer timeout trong lúc commit A, trạng thái commit có thể không xác định: dùng transactional outbox và giữ eventId ổn định.

### 13.2. Quy trình khi B offline nhiều phút

1. Xác minh B thật sự không thể nhận Core connection hay bridge bị auth/TLS sai; tránh kết luận từ một socket timeout duy nhất.
2. Quan sát **source queue ở A có giữ backlog** không; xác định message count và oldest age.
3. Ước lượng thời gian hết disk theo tốc độ tăng backlog/paging; nếu cần rate limit producer hoặc mở rộng volume.
4. Khôi phục B/đường mạng, không purge source queue hoặc restart liên tục A chỉ để “ép bridge chạy”.
5. Quan sát bridge reconnect; A backlog giảm, B target queue tăng trước khi consumer ACK.
6. Đối chiếu business eventIds, duplicate detection warnings, target redelivery/DLQ.
7. Nếu cần xử lý DLQ tại B, dùng runbook replay **tại B**; không tự gửi lại toàn bộ backlog từ A nếu bridge đã hoàn thành forward.

### 13.3. Checklist nghiệm thu trước production

- [ ] Cả A/B dùng storage độc lập, persistence enabled, queue source/target durable.
- [ ] Source queue tồn tại **trước bridge startup**; target address + queue đúng routing.
- [ ] Core connector và remote user/role hoạt động, TLS được kiểm chứng.
- [ ] Producer gửi persistent, chờ commit; test messageId/eventId.
- [ ] `use-duplicate-detection=true`; B có cache size/persistence đủ yêu cầu.
- [ ] Retry/backoff vô hạn hoặc hữu hạn được quyết định theo SLA, có alert.
- [ ] Target `BLOCK` không bị nghẽn do confirmation window quá lớn.
- [ ] Test B down/restart, A restart, network interruption và duplicate window trên môi trường disposable.
- [ ] B consumer idempotent, có redelivery/DLQ và version/schema contract.
- [ ] Có metric bridge state, source queue age, disk headroom và operational runbook.

## 14. Bài tập tự kiểm tra

1. `queue-name` trong Core bridge trỏ tới **queue A** hay **queue B**? **Queue A**, phải tồn tại khi bridge được khởi tạo.
2. `forwarding-address` chỉ **queue** hay **address** đích? **Address B**; B cần có queue với routing phù hợp.
3. Producer JMS commit thành công ở A, B đang offline. Điều đó có nghĩa producer phải gửi lại trực tiếp B không? **Không**; source queue A và bridge chịu trách nhiệm chờ/chuyển tiếp nếu durability còn hiệu lực.
4. B đã nhận E100 nhưng confirmation mất. Làm sao giảm nguy cơ B lưu hai bản E100? **Duplicate detection** qua `_AMQ_DUPL_ID` và cache target.
5. B crash rồi khôi phục, cache không persist. Việc resend còn có thể bị nhận là duplicate không? **Không bảo đảm**, tùy cache còn hay mất.
6. Nếu producer tự gửi thêm E100 như **message mới** không giữ duplicate ID, bridge detection có tự đảm bảo một business event không lặp không? **Không**, phải dùng eventId/idempotency.
7. A source queue có thêm một consumer nghiệp vụ. Nó có được “một bản sao độc lập” cùng bridge không? **Không**, consumer tranh message với bridge.
8. Bridge `routing-type=PASS` mang ANYCAST message sang B chỉ có multicast queue. Có thể không route không? **Có**, cần đồng nhất routing type.
9. Bridge đã forward thành công và A đã giải phóng message, nhưng consumer B rollback nhiều lần. Nên sửa retry bridge hay redelivery/DLQ ở B? **Redelivery/DLQ ở B**.
10. Vì sao `concurrency=5` không mặc nhiên phù hợp khi cần thứ tự toàn cục? **Nhiều bridge workers song song** có thể làm thứ tự nhận/hoàn tất khác.
11. Target address `BLOCK` với max-size nhỏ, bridge confirmation window rất lớn. Điều gì có thể xảy ra? **Flow control bị kẹt**; so confirmation window với max-size.
12. Tại sao Core bridge không thay thế broker HA policy? Vì nó **chuyển message giữa queues trên brokers khác**, không tạo shared-store/replication/quorum/fencing tự động.

## 15. Tài liệu chính thức và kết luận

- [Apache ActiveMQ Artemis — Core Bridges](https://artemis.apache.org/components/artemis/documentation/latest/core-bridges.html): `queue-name`, `forwarding-address`, retry, confirmation window, producer credits, duplicate detection, routing type và connectors.
- [Apache ActiveMQ Artemis — Duplicate Message Detection](https://artemis.apache.org/components/artemis/documentation/latest/duplicate-detection.html): property `_AMQ_DUPL_ID`, cache theo address, eviction/persistence và bridge resend.
- [Apache ActiveMQ Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): queue vs address, anycast/multicast, routing.
- [Apache ActiveMQ Artemis — Configuration Reference](https://artemis.apache.org/components/artemis/documentation/latest/configuration-index.html): bridge fields và defaults theo phiên bản.
- [Apache ActiveMQ Artemis — Configuration Reload](https://artemis.apache.org/components/artemis/documentation/latest/config-reload.html): các loại cấu hình bridge có thể reload và các trường hợp cần kiểm tra hiệu lực.
- [Apache ActiveMQ Artemis — Flow Control](https://artemis.apache.org/components/artemis/documentation/latest/flow-control.html): producer window/credits và sự tương tác backpressure.
- [Apache ActiveMQ Artemis — JMS Bridge](https://artemis.apache.org/components/artemis/documentation/latest/jms-bridge.html): so sánh khi phải nối những JMS providers khác Artemis.

**Kết luận:** **Artemis Core bridge consume từ một queue trên broker A rồi forward tới address trên broker B qua Core protocol**. Đường chuyển tiếp tin cậy cần **source/target persistence**, **queue/address/routing đúng**, **retry/reconnect**, **confirmation flow control**, và **duplicate detection được bảo toàn**. Khi B offline, backlog cần được giữ an toàn tại A; khi B trở lại, bridge tự chuyển tiếp những message chưa được xác nhận. Song **duplicate detection của bridge không bảo vệ side effect nghiệp vụ** sau khi B giao message cho consumer: phải tiếp tục dùng `eventId`, idempotency, JMS ACK đúng ranh giới và DLQ/runbook rõ ràng.
