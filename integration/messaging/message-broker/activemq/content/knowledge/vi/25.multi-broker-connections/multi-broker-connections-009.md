# Thiết kế kết nối liên vùng với độ trễ, mất mạng và giới hạn băng thông

> **Chương:** Kết nối nhiều broker  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ với queue/topic, routing, JMS, producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Trọng tâm:** Thiết kế đường truyền **giữa hai vùng mạng/địa lý** khi có RTT lớn, mất kết nối từng phần và giới hạn băng thông. Ví dụ chính dùng **Artemis Core bridge** giữa hai broker độc lập, Java 17 và Jakarta JMS; phân biệt rõ với **ActiveMQ Classic Network of Brokers**. Các giá trị thời gian và dung lượng bên dưới dùng cho **lab**, không phải mặc định sản xuất.

## 1. Bài toán: gửi liên vùng không giống gửi trong một LAN

Hệ thống vận hành tại hai vùng A và B. Ứng dụng ở A phát sự kiện `OrderConfirmed`; dịch vụ xử lý hậu cần đặt ở B cần nhận các sự kiện ấy. Vùng A phải tiếp tục phục vụ khi đường WAN mất trong 20 phút. Đường A→B có độ trễ khứ hồi (RTT) khoảng 180 ms, giới hạn 40 Mbit/s, đôi lúc bị packet loss.

Đội phát triển cần làm rõ bốn cam kết **khác nhau**:

1. **Producer A được ACK khi nào?** Khi message đã được broker A ghi bền vững, hay phải chờ B?
2. **Trong 20 phút không có WAN, message nằm ở đâu?** Queue nguồn có đủ đĩa/giới hạn backlog và kế hoạch xử lý khi đầy không?
3. **WAN phục hồi, message có thể gửi lại không?** Nếu A chưa nhận xác nhận từ B, nó có thể truyền lại một message mà B thực tế đã nhận.
4. **Có thể hứa thứ tự và exactly-once không?** Bridge bảo vệ đường truyền ở cấp broker, nhưng không thay thế kiểm soát version/idempotency của ứng dụng.

### 1.1. Topology đề xuất cho luồng một chiều

~~~text
       REGION A (nhận đơn)                      WAN                       REGION B (hậu cần)

  Java producer --JMS--> Artemis A                                       Artemis B --> Java consumer
                              |                                              ^
                           address                                           |
                         orders.events                                      |
                       MULTICAST                                            |
                    /              \                                        |
           orders.local         wan.region-b.out -- Core bridge/TLS --------+
          (local queue)         (durable queue)                   forward to orders.remote.in
                                                                        (ANYCAST)
                                                                         |
                                                                orders.remote.process

  A ACK producer khi A commit local.
  Bridge giữ trách nhiệm chuyển bản copy trong wan.region-b.out.
  B ACK consumer khi business effect và JMS transaction hoàn tất.
~~~

**Đây là luồng chuyển sự kiện một chiều**, không phải một cụm broker thống nhất xuyên WAN và không phải cơ chế synchronous database replication. Mỗi vùng tự quản lý broker, storage, security và failure domain.

### 1.2. Bốn yêu cầu cần quyết định trước khi chọn cơ chế

| Yêu cầu | Câu hỏi thiết kế | Hệ quả |
|---|---|---|
| Availability của A | Khi WAN đứt, có tiếp tục nhận sự kiện không? | Cần durable queue tại A và chính sách disk/backpressure |
| RPO liên vùng | Chấp nhận mất tối đa bao nhiêu event chưa đến B nếu **toàn vùng A mất vĩnh viễn**? | Async bridge không tự hứa RPO=0 |
| RTO sau partition | WAN phục hồi thì backlog phải hết trong bao lâu? | Phải có năng lực **dư** so với lưu lượng mới |
| Ordering | Cần thứ tự theo order, tenant hay toàn hệ thống? | Quyết định partition/group key, khả năng xử lý song song và version guard |

Không bắt đầu bằng câu hỏi “tăng bao nhiêu connection?” trước khi biết hợp đồng nghiệp vụ. Nhiều connection không sửa được link thiếu băng thông hay hot key phải xử lý tuần tự.

## 2. Chọn đúng mô hình kết nối giữa các broker

| Phương án | Thích hợp khi | Đổi lại/điểm cần kiểm tra |
|---|---|---|
| **Artemis Core bridge A→B** | Chuyển một luồng message đã được route vào **queue nguồn cụ thể** đến address của broker khác; muốn A giữ backlog khi WAN đứt | Một chiều nếu chỉ cấu hình A→B; kết nối CORE, định tuyến, retry, duplicate detection và backpressure |
| **Artemis federation** | Cần liên kết queue/address giữa broker theo chính sách federation; chỉ chuyển dữ liệu theo demand/policy được cấu hình | Phải hiểu queue/address federation, policy match, demand, topology và version; không thay thế thiết kế RPO |
| **Artemis cluster** | Nhiều broker có cơ chế cluster routing/topology được hỗ trợ, thường gần nhau với độ trễ phù hợp | RTT cao/partition có thể gây vận hành và routing phức tạp; không mặc định dùng một cluster kéo dài xuyên địa lý |
| **Classic Network of Brokers** | Hệ dùng ActiveMQ Classic với demand forwarding/subscription network | Khác Core bridge; cần networkTTL, duplex, conduitSubscriptions, advisory/demand và loop policy |
| **Ứng dụng chuyển tiếp / outbox relay** | Cần filter, transform, policy theo tenant, reconciliation hoặc giao thức khác | Thêm code/trạng thái vận hành; phải tự thiết kế ACK, retry, dedup và observability |
| **Synchronous cross-region transaction** | Nghiệp vụ thật sự cần xác nhận từ vùng xa trước khi commit | RTT và availability chi phối latency; phức tạp hơn rất nhiều, không phải tính năng mặc định của JMS bridge |

**Khuyến nghị kiến trúc cho bài lab:** hai broker Artemis độc lập + một Core bridge rõ ràng từ queue dành riêng cho WAN tại A. Mô hình này dễ chứng minh: producer không phụ thuộc WAN trong đường gửi trực tiếp, trong khi bridge chịu trách nhiệm forward bền vững.

**Không cấu hình cầu A→B và B→A trên cùng địa chỉ một cách đối xứng rồi hy vọng broker tự chống vòng lặp.** Có thể phát sinh message loop, duplicate storm và amplification. Với luồng hai chiều, dùng **địa chỉ/queue tách biệt theo hướng** (`orders.a-to-b`, `orders.b-to-a`), định nghĩa origin/hop policy và test chống echo trước.

## 3. Phân biệt các mốc ACK trên đường A→B

Một message không có “một ACK duy nhất” cho toàn hệ thống.

~~~mermaid
sequenceDiagram
    participant P as Producer A
    participant A as Artemis A
    participant L as Queue WAN A
    participant B as Artemis B
    participant C as Consumer B

    P->>A: JMS send + commit persistent
    A->>L: Lưu reference trong durable queue
    A-->>P: Local JMS commit OK
    Note over P,B: Chưa thể kết luận B đã nhận
    L->>B: Core bridge forward message
    B-->>L: Broker-level confirmation
    Note over L,B: Timeout tại đây có thể khiến bridge gửi lại
    B->>C: Dispatch từ queue đích
    C->>C: Business transaction + idempotency
    C-->>B: JMS ACK / commit
~~~

**Mốc cần ghi trong telemetry:**

- `A_LOCAL_COMMITTED`: producer đã nhận kết quả commit của broker A.
- `B_BROKER_RECEIVED`: broker B chấp nhận bản forward, phụ thuộc chế độ persistence/ack của cầu nối.
- `B_BUSINESS_COMMITTED`: consumer B đã thực hiện side effect nghiệp vụ an toàn.
- `B_JMS_ACKED`: consumer B xác nhận delivery.

A trả lời producer **trước** khi B xử lý xong. Nếu vùng A mất hoàn toàn cùng các message **chưa forward**, vùng B có thể không bao giờ nhận chúng; đây là **RPO khác 0** cho một đường truyền bất đồng bộ, trừ khi có lớp replication/backup khác bảo vệ nguồn.

Nếu WAN lỗi đúng lúc broker B đã nhận message nhưng xác nhận không tới A, bridge có thể forward lại. Artemis bridge có **duplicate detection hỗ trợ**, nhưng consumer vẫn phải idempotent vì cache có giới hạn, còn retry nghiệp vụ/replay từ DLQ hoặc đường khác có thể gây lặp.

### 3.1. Phân biệt ACK JMS của producer với bridge acknowledgement

Một producer JMS không trực tiếp nhận “B đã xử lý xong” chỉ vì `send()` hoặc `commit()` trên A thành công. Bridge dùng cơ chế confirm riêng giữa broker A và B.

Cũng không nên suy rằng message đã biến mất khỏi queue WAN A thì nghiệp vụ ở B đã hoàn thành: đó là **ranh giới forward**, còn business handler/ACK ở B là ranh giới tiếp theo.

### 3.2. Không có distributed transaction mặc định

Một JMS transaction trên A không mở rộng thành transaction duy nhất gồm A, WAN, B và database của consumer. Tính bền vững local, duplicate detection ở bridge và consumer idempotency phải được thiết kế **phối hợp**, không gọi chúng là exactly-once end-to-end.

## 4. Cấu hình Artemis: nguồn A có hai queue từ một multicast address

Trên **broker A**, ứng dụng publish tới address `orders.events`. Nó được route đến:

- Queue `orders.local` cho xử lý trong vùng A (nếu có).
- Queue `wan.region-b.out` **chỉ dành cho Core bridge**. Không gắn consumer nghiệp vụ thông thường vào queue này, vì consumer cạnh tranh có thể lấy message trước khi bridge forward.

Mảnh `broker.xml` **bên trong phần `<addresses>` hiện hữu**:

~~~xml
<address name="orders.events">
    <multicast>
        <queue name="orders.local" durable="true"/>
        <queue name="wan.region-b.out" durable="true"/>
    </multicast>
</address>
~~~

**Tại sao MULTICAST?** Mỗi queue có **reference riêng** của cùng event, nên xử lý local không làm message trong queue dành cho WAN bị mất. Nếu cấu hình hai queue ANYCAST trên cùng address, broker có thể chọn **một** queue cho message, làm mất bản copy ở đường còn lại.

Nếu hệ thống không cần xử lý local, có thể chỉ tạo một queue nguồn cho bridge và dùng routing phù hợp, nhưng **không được vô tình tạo competing consumer** cho queue forward.

### 4.1. Destination của vùng B

Trên **broker B**, tạo address ANYCAST `orders.remote.in` và queue xử lý:

~~~xml
<address name="orders.remote.in">
    <anycast>
        <queue name="orders.remote.process" durable="true"/>
    </anycast>
</address>
~~~

Bridge ở A sẽ forward tới **address** `orders.remote.in` của B. B route message vào queue `orders.remote.process`. Phải **provision destination trước** hoặc xác nhận đúng auto-create policy; nếu B không route được, không xem kết nối TCP thành công là delivery hoàn tất.

### 4.2. Đừng để lại rule chồng lấn vô tình

Các mảnh trên phải được hợp nhất vào `broker.xml` đang có; **không tạo thêm phần tử `<addresses>` lặp lại** hoặc xóa address hiện hữu. Nếu dùng wildcard security/address-settings, kiểm tra rule thực sự match cả `orders.events` lẫn `orders.remote.in`.

Những tên queue/address khác nhau có chủ đích:

| Thành phần | Tên | Ý nghĩa |
|---|---|---|
| A: input address | `orders.events` | Publisher gửi bằng JMS Topic / multicast |
| A: local queue | `orders.local` | Xử lý nội vùng |
| A: bridge source queue | `wan.region-b.out` | Backlog chờ forward; không cho app khác consume |
| B: forwarding address | `orders.remote.in` | Đích Core bridge gửi tới |
| B: business queue | `orders.remote.process` | Consumer B xử lý dữ liệu |

## 5. Artemis Core bridge có reconnect, duplicate detection và TLS

### 5.1. Connector ở broker A trỏ đến broker B

Ví dụ khai báo trong `<connectors>` của **broker A**:

~~~xml
<connector name="region-b-core-tls">
    tcp://mq-b.internal.example:61617?sslEnabled=true;trustStorePath=/run/secrets/wan-ca.p12;trustStorePassword=REPLACE_WITH_SECRET;trustStoreType=PKCS12;verifyHost=true
</connector>
~~~

Các yêu cầu bắt buộc:

- `mq-b.internal.example` phải resolve từ broker A và **khớp DNS SAN** của chứng chỉ B.
- Port **61617** là ví dụ của acceptor TLS tại B, không phải mặc định cố định cho mọi broker.
- `sslEnabled=true` bật TLS trên Core connector; `verifyHost=true` bảo vệ danh tính endpoint.
- Truststore phải chứa CA đáng tin phù hợp; không dùng `trustAll=true` hoặc tắt hostname validation.
- `REPLACE_WITH_SECRET` chỉ là placeholder. **Không commit mật khẩu truststore thật vào Git/XML**; dùng cơ chế secret/password masking và quản lý file theo deployment/version. URI đã nội suy có thể bị lộ qua debug/diagnostics nên cần redaction.
- Với yêu cầu mTLS, bổ sung client keystore/cert và cấu hình acceptor yêu cầu client authentication. Server-auth TLS + username/password **khác** mTLS.

### 5.2. Acceptor ở broker B

Mảnh `<acceptors>` của **broker B**:

~~~xml
<acceptor name="wan-core-tls">
    tcp://0.0.0.0:61617?protocols=CORE;sslEnabled=true;keyStorePath=/run/secrets/broker-b.p12;keyStorePassword=REPLACE_WITH_SECRET;keyStoreType=PKCS12;needClientAuth=false
</acceptor>
~~~

Acceptor phải cho phép **CORE protocol** vì đây là **Artemis Core bridge**, không phải ActiveMQ Classic Network Connector. `0.0.0.0` bind các interface; firewall/network policy phải chỉ cho nguồn A được phép kết nối, không public port trực tiếp.

`needClientAuth=false` nghĩa là broker không yêu cầu client TLS certificate. Bridge vẫn cần **broker-level authentication** (user/password) và **permission send** trên B. Nếu sử dụng mTLS, thay đổi cấu hình hai đầu một cách nhất quán và ánh xạ certificate principal theo security backend thực tế.

### 5.3. Cấu hình bridge trên A

Mảnh trong phần `<bridges>` của **broker A**, **không áp dụng cho Classic**:

~~~xml
<bridge name="orders-a-to-b">
    <queue-name>wan.region-b.out</queue-name>
    <forwarding-address>orders.remote.in</forwarding-address>

    <user>wan-bridge</user>
    <password>REPLACE_WITH_SECRET</password>

    <retry-interval>1000</retry-interval>
    <retry-interval-multiplier>2.0</retry-interval-multiplier>
    <max-retry-interval>30000</max-retry-interval>

    <initial-connect-attempts>-1</initial-connect-attempts>
    <reconnect-attempts>-1</reconnect-attempts>

    <use-duplicate-detection>true</use-duplicate-detection>
    <confirmation-window-size>1048576</confirmation-window-size>
    <producer-window-size>1048576</producer-window-size>

    <static-connectors>
        <connector-ref>region-b-core-tls</connector-ref>
    </static-connectors>
</bridge>
~~~

Giải thích **từng lựa chọn liên quan WAN**:

| Thiết lập | Tác dụng | Điểm cần nhớ |
|---|---|---|
| `queue-name` | Bridge tiêu thụ từ **queue trên A** | Queue nên durable, không có consumer nghiệp vụ cạnh tranh |
| `forwarding-address` | Địa chỉ đích **ở B** | Phải route tới queue nghiệp vụ thật |
| `user/password` | Danh tính bridge xác thực tại broker B | Tách khỏi admin credential; không để secret plaintext trong repo |
| `retry-interval` | Khoảng retry ban đầu khi không kết nối được | Không dùng 0 ms gây reconnect storm |
| `retry-interval-multiplier` | Tăng khoảng retry sau các lần lỗi | Kết hợp `max-retry-interval` để giới hạn mức lùi |
| `max-retry-interval` | Chặn retry interval tăng vô hạn | Không thay thế alert khi WAN chết lâu |
| `initial-connect-attempts=-1` | Tiếp tục thử nếu B chưa sẵn sàng lúc bridge khởi động | Đặt policy theo yêu cầu vận hành; app A vẫn cần disk headroom |
| `reconnect-attempts=-1` | Thử lại lâu dài sau khi mất kết nối | Không tạo HA cho broker B và không bảo đảm có băng thông |
| `use-duplicate-detection=true` | Bridge gửi thông tin phát hiện duplicate theo khả năng broker | Cần remote duplicate cache; vẫn phải idempotent ở app |
| `confirmation-window-size` | Giới hạn/điều phối dữ liệu chưa được confirm ở cấp Core protocol | Không phải chính sách giới hạn bps của đường truyền |
| `producer-window-size` | Điều tiết producer flow-control khi bridge đẩy dữ liệu | Không biến băng thông WAN thành một giá trị QoS cố định |
| `static-connectors` | Tập endpoint broker B mà bridge thử kết nối | Tránh endpoint không được bảo vệ hoặc sai topology |

**Số 1 MiB là điểm khởi đầu của lab, không phải cấu hình tối ưu cho WAN 40 Mbit/s.** Tùy RTT, message size, broker credit/flow control và memory, giá trị cần được benchmark. Không tăng window vô hạn chỉ vì RTT cao: in-flight bytes tăng có thể làm căng RAM, áp lực retransmission và độ trễ failover.

Cấu hình bridge có thể có các tham số khác theo version. Khi triển khai, validate XML/schema và effective settings của **Artemis release đang chạy**, không ghép nguyên các tag này vào cấu hình Classic.

### 5.4. Quyền cho bridge tại B

Trên **broker B**, ánh xạ user `wan-bridge` vào role `wan-forwarder` qua security backend đang dùng (JAAS/properties/LDAP...). Mảnh `<security-settings>`:

~~~xml
<security-setting match="orders.remote.in">
    <permission type="send" roles="wan-forwarder"/>
    <permission type="consume" roles="orders-processor"/>
</security-setting>
~~~

Bridge chỉ cần quyền forward vào address đích, không cần tài khoản admin toàn broker. Nếu consumer B dùng `orders-processor` thì nó cần permission consume tương ứng.

Khi destination được provision tĩnh, nên hạn chế quyền tạo/xóa queue/address của service. Nếu có wildcard ACL hoặc management rule khác, phải đối chiếu **effective matching security-settings**.

### 5.5. Điều gì xảy ra nếu B không xác thực được bridge?

Trong tình huống B chặn user/permission, bridge có thể retry nhưng **không tiến độ**, queue WAN A tích backlog và eventual disk pressure tăng. Retry liên tục **không sửa được sai mật khẩu, chứng chỉ, RBAC hoặc protocol**.

Runbook phải phân biệt:

1. DNS/TCP/firewall.
2. TLS certificate/SAN/truststore.
3. Core protocol trên acceptor.
4. User/password authentication.
5. `send` permission và destination routing.
6. Quota/page/disk pressure tại B.

## 6. Giới hạn băng thông và hàng đợi: tính trước khi triển khai

Cho luồng A→B:

- \(\lambda\): tốc độ đến trong vùng A, message/giây.
- \(s\): kích thước message trung bình **trên đường truyền**, byte/message (không nhất thiết bằng body JSON).
- \(B\): băng thông hữu dụng trên WAN, byte/giây, sau overhead và các luồng tranh chấp.
- \(\mu\): tốc độ bridge thực sự chuyển thành công, message/giây.

Trong mô hình đơn giản, để queue WAN không tăng vô hạn khi liên kết ổn định:

\[
\lambda < \mu.
\]

Băng thông cần cho payload xấp xỉ:

\[
R_{\text{payload}} = \lambda \times s \times 8 \quad (\text{bit/s}).
\]

**Đừng nhầm Mbit/s với MiB/s** và đừng chỉ đo body size: TLS, Core frames, durable storage, replication, duplicate-detection metadata, packet overhead và các flow khác đều chiếm ngân sách thực.

### 6.1. Ví dụ: 300 message/s, 8 KiB/message, link 40 Mbit/s

Giả thiết:

- Tốc độ vào: \(\lambda = 300\) msg/s.
- Kích thước trung bình: \(s = 8\,192\) byte/message.
- Tổng lưu lượng payload: \(300 \times 8\,192 = 2\,457\,600\) B/s, tương đương **19,66 Mbit/s**.
- Link cap: **40 Mbit/s** tổng. Nếu chỉ chia số thô, giới hạn vật lý lý tưởng là khoảng **610 msg/s**, **trước mọi overhead**.
- Trong benchmark, giả sử forward rate bền vững đo được là \(\mu = 450\) msg/s khi link ổn định. Đây là **giả thiết đo minh họa**, không suy trực tiếp từ cấu hình bridge.

Vậy đầu vào 300 msg/s dùng khoảng 2/3 capacity chuyển của bridge (450 msg/s), tạo headroom để xử lý burst hoặc backlog. Nhưng link có thể được chia sẻ với các dịch vụ khác; \(\mu\) biến động theo tải, packet loss và I/O của hai broker.

### 6.2. Mất WAN 20 phút: backlog tối thiểu cần chứa

Nếu bridge không chuyển được message nào trong **1.200 giây**, trong khi producer vẫn phát 300 msg/s:

\[
N_{\text{backlog}} = 300 \times 1200 = 360\,000 \text{ message}.
\]

Payload tối thiểu tăng:

\[
D_{\text{payload}} = 360\,000 \times 8192
= 2\,949\,120\,000 \text{ B}
\approx 2.75 \text{ GiB}.
\]

**Đây chưa phải disk reservation đủ dùng.** Cần thêm journal record/queue-reference metadata, page files, large messages nếu có, broker/OS reserved space, watermark, snapshot/backup, HA replica và biên an toàn. Quy trình capacity nên chọn tình huống **peak input rate và outage dài hơn dự kiến**, không chỉ dùng trung bình.

Nếu A hết disk trong lúc B mất mạng, việc “bridge retry vô hạn” không giữ được availability. Phải có chính sách **backpressure/quota/fail-fast/traffic shedding** có chủ đích theo mức ưu tiên nghiệp vụ.

### 6.3. WAN trở lại, bao lâu mới hết backlog?

Với \(\lambda = 300\) msg/s tiếp tục vào và bridge chuyển \(\mu = 450\) msg/s, tốc độ rút backlog là:

\[
\mu - \lambda = 150 \text{ msg/s}.
\]

Thời gian lý tưởng để rút **360.000 message**:

\[
T_{\text{drain}} = \frac{360\,000}{150}
= 2400 \text{ giây} = 40 \text{ phút}.
\]

Đây là **RTO xử lý backlog riêng**, không phải broker restart RTO. Nếu bridge chỉ phục hồi bằng đúng 300 msg/s, backlog **không bao giờ hết** khi tải mới liên tục 300 msg/s. Nếu một hot group ở B xử lý chậm, queue B có thể tiếp tục tăng **dù bridge A đã drain xong**.

### 6.4. RTT và Bandwidth-Delay Product (BDP)

Với RTT 180 ms và link 40 Mbit/s:

\[
BDP = \frac{40\,000\,000 \times 0.18}{8}
= 900\,000 \text{ byte} \approx 879 \text{ KiB}.
\]

Đây là lượng dữ liệu có thể “nằm trên đường” khi cố sử dụng hết đường truyền ở điều kiện lý tưởng. BDP giúp hiểu vì sao một cửa sổ xác nhận/flow-control quá nhỏ **có thể** khiến throughput kém trên WAN RTT lớn.

**Không đồng nhất BDP với `confirmation-window-size` hoặc `producer-window-size` rồi cấu hình bằng một phép gán máy móc.** Những window của Artemis có nghĩa riêng, còn TCP window, broker paging, duplicate detection và I/O đều tác động throughput. Điều chỉnh lần lượt và **đo dữ liệu đã confirm**, in-flight bytes, RAM, CPU, p95/p99 và backlog dưới tình huống WAN có loss.

## 7. Backpressure: source queue phải có chính sách khi link chậm

Ở broker A, `wan.region-b.out` là vùng đệm durable cho kết nối liên vùng. Khi B chậm, bridge chậm, backlog tăng. Artemis có thể PAGE message theo address setting để không giữ toàn bộ backlog trong RAM.

Ví dụ mảnh `<address-settings>` **của A**, áp dụng cho address nguồn `orders.events`:

~~~xml
<address-setting match="orders.events">
    <address-full-policy>PAGE</address-full-policy>
    <max-size-bytes>67108864</max-size-bytes>
    <page-size-bytes>10485760</page-size-bytes>
</address-setting>
~~~

Diễn giải:

- `max-size-bytes=67108864` (64 MiB) là ngưỡng address memory theo broker policy, **không phải quota ổ đĩa giới hạn trong 64 MiB**.
- `page-size-bytes=10485760` (~10 MiB) là cỡ page file mục tiêu, không có nghĩa một page bao phủ đúng số message nhất định.
- PAGE giữ backlog có thể tiêu thụ về sau, nhưng **disk vẫn có thể đầy** khi WAN hỏng lâu.
- Những giá trị trong ví dụ là để quan sát paging ở lab; cần sizing theo workload thực, journal/large-message footprint và HA topology.

Vì `orders.local` và `wan.region-b.out` cùng address multicast, cả hai queue có thể ảnh hưởng size/queue references. Không dùng message count của chỉ `orders.local` để tính dung lượng WAN.

### 7.1. Mức cảnh báo và policy đề xuất

| Chỉ số | Cần theo dõi | Hành động khi vượt ngưỡng |
|---|---|---|
| Source WAN queue depth/oldest age | Số event chưa forward, độ trễ cũ nhất | Alert WAN/bridge stall và ước tính thời gian drain |
| Paging bytes/page count | Backlog chuyển ra disk | Theo dõi đĩa, giữ margin và kiểm tra cleanup |
| Broker disk free + growth rate | Khoảng thời gian còn trước full disk | Tăng capacity/chặn đầu vào có kiểm soát, không xóa journal |
| Bridge connected / confirmations | Bridge thật sự forward hay chỉ connected | Kiểm tra ACL, routing và B pressure |
| Effective bytes/sec | Thông lượng thực qua WAN | So với \(\lambda \times s\) và link cap |
| Retry/failure rate | Loss, TLS, auth, broker restart | Phân loại lỗi transient/permanent |
| B queue depth + consumer lag | Consumer B có xử lý kịp không | Scale consumer theo invariant, không chỉ scale bridge |
| DLQ/redelivery/duplicate | Business delivery có được kiểm soát không | Điều tra idempotency, poison và transaction |

Cần có **alert dự báo cạn disk**: ví dụ lấy tốc độ tăng bytes/giây trên volume và headroom, kết hợp nguồn message vào hiện tại để biết “còn bao nhiêu phút”. Không coi `reconnectAttempts=-1` là một chiến lược ứng phó disk đầy.

### 7.2. Rate limit phải được đặt ở đúng chỗ

`confirmation-window-size` và `producer-window-size` không phải bộ điều khiển **chính xác 40 Mbit/s**. Khi cần giới hạn lưu lượng:

- Thực thi **token bucket/rate limiter** ở producer/relay tại A theo message/s hoặc bytes/s, nhất là khi WAN dùng chung.
- Dùng network QoS/shaping ở egress hoặc VPN gateway do đội mạng quản lý, tính cả TLS/TCP overhead.
- Nếu dùng bridge có sẵn, đo/giám sát tốc độ và phối hợp policy ingress thay vì giả định bridge có property rate-limit toàn WAN.
- Ưu tiên traffic cấp thiết yếu khi backlog lớn, nhưng không để thứ tự nghiệp vụ bị phá do phân luồng sai.

**Giới hạn rate cứng thấp hơn tốc độ producer liên tục** sẽ làm backlog tăng vô hạn. Muốn vừa rate limit vừa ổn định, phải kiểm soát cả đầu vào hoặc có cơ chế discard/TTL được phê duyệt theo nghiệp vụ.

## 8. Lỗi mạng: partition, asymmetric failure và retry

Các kiểu lỗi cần test **khác nhau**:

| Lỗi | Bridge có thể quan sát | Rủi ro nghiệp vụ |
|---|---|---|
| WAN bị cắt hoàn toàn | Reconnect attempts, queue A tăng | RPO/RTO và disk headroom |
| Chỉ A→B không đi được | TCP/TLS timeout, reconnect | Cần đo cả hai hướng ACK/heartbeat |
| B nhận dữ liệu nhưng ACK từ B→A mất | A có thể retry message | Duplicate trên B |
| RTT 100 ms → 600 ms | Confirmation chậm, throughput giảm | SLO drain tụt; cần kiểm tra window/BDP |
| Packet loss 1–5% | TCP retransmission, connection churn | Tail latency, backpressure |
| B broker quá tải/đầy disk | ACK chậm, send reject/flow control | Đừng hiểu nhầm là WAN failure |
| Auth/TLS certificate hết hạn | Reconnect lặp lại nhưng không thành công | Retry vô hạn không tự sửa chứng chỉ |
| A broker restart | Bridge queue recovery, reconnect | Local durable messages phải còn, dedup phía B |
| B broker restart | Message đang chuyển có trạng thái chưa rõ | Source retransmit; consumer idempotent |
| DNS/failover sang B khác | Connection tới endpoint mới | Rủi ro split destination, duplicate/ordering |

**Ranh giới then chốt:** Không có một timeout/reconnect policy nào có thể phân biệt chắc chắn “remote chưa nhận” với “remote đã nhận nhưng mất phản hồi”. Do đó thiết kế phải an toàn với replay.

### 8.1. Không retry như nhau cho mọi lỗi

- Network timeout / broker restart: retry có backoff, giám sát backlog.
- Authentication denied, thiếu `send`, certificate SAN mismatch: **khắc phục cấu hình**; retry không giải quyết.
- Destination không tồn tại/route sai: provision và kiểm tra address/queue.
- B disk full hoặc paging quá tải: capacity/backpressure, không tăng concurrency mù quáng.
- Poison business message ở B: redelivery/DLQ riêng; **không** dùng bridge reconnect để xử lý lỗi nghiệp vụ.

### 8.2. Tạo lỗi WAN trên môi trường cách ly

Nếu lab có một **network namespace/container dành riêng cho bridge path** và quyền quản trị mạng, có thể dùng Linux traffic control để tạo delay/loss. Ví dụ **chỉ để tham khảo, không chạy trên host/production interface**:

~~~bash
# Chỉ trong container hoặc network namespace lab sở hữu riêng.
# Interface eth0 phải là NIC thử nghiệm, không phải mạng dùng chung.
tc qdisc replace dev eth0 root netem delay 90ms 15ms loss 1%

# Khi hoàn tất thí nghiệm, khôi phục:
tc qdisc del dev eth0 root
~~~

Lệnh tạo delay **một chiều** ở interface áp dụng; nếu muốn mô phỏng RTT ~180 ms, phải hiểu topology/hướng egress và đo RTT thực. `netem loss 1%` có thể tạo retransmissions lớn; không suy thẳng 1% message loss vì TCP có retry. Đừng chạy trên máy broker production, NIC dùng chung, hoặc node Kubernetes không cách ly.

Để mô phỏng **mất kết nối hoàn toàn**, dùng firewall/network isolation trên container/namespace lab theo runbook có khả năng khôi phục; không tự áp dụng rule nguy hiểm lên host thật.

## 9. Duplicate detection: giảm lặp ở cầu nối, không phải exactly-once nghiệp vụ

Artemis bridge có thể bật `use-duplicate-detection=true`. Cơ chế này bổ sung metadata giúp broker đích nhận diện những lần forward trùng theo duplicate-ID cache tương ứng.

Điều cần biết:

- Duplicate detection phụ thuộc cấu hình, hành vi của **broker đích** và phạm vi/cache life-cycle.
- Cache duplicate ID là **hữu hạn**; nếu ID cũ bị đẩy ra khỏi cache hoặc dữ liệu bị replay từ đường khác, duplicate vẫn có thể xuất hiện.
- Broker-level dedup **không** thay consumer idempotency sau khi database đã commit nhưng JMS ACK chưa commit.
- Duplicate detection của bridge không biến **hai ứng dụng dùng cùng eventId tự tạo** thành global exactly-once across every queue/broker.

Một cấu hình Artemis global liên quan duplicate-ID cache (phải kiểm tra với broker version) có thể là:

~~~xml
<!-- Trong broker.xml của B, tại vị trí hợp lệ trong core config. -->
<duplicate-id-cache-size>50000</duplicate-id-cache-size>
<persist-id-cache>true</persist-id-cache>
~~~

Tăng cache có thể giảm duplicate do retry trong một cửa sổ lớn hơn, nhưng tốn memory/store và **không thay thế unique constraint nghiệp vụ**. Kích thước cache nên dựa vào throughput và khoảng thời gian có thể replay, không chọn “50000 là đủ” cho mọi vùng.

### 9.1. Ranh giới idempotency ở consumer B

Ví dụ nghiệp vụ có bảng:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Trong CÙNG transaction với tác vụ nghiệp vụ của consumer:
INSERT INTO processed_events(event_id)
VALUES (?)
ON CONFLICT (event_id) DO NOTHING;
-- Chỉ áp dụng side effect khi INSERT thực sự tạo một hàng.
-- Commit DB trước khi commit JMS ACK.
~~~

Mẫu SQL ở đây dùng **PostgreSQL**. Nếu insert conflict, consumer biết event đã xử lý (trong phạm vi DB đã thiết kế), không chạy lại side effect, nhưng có thể ACK delivery để giải phóng queue.

**Chú ý:** Dùng cùng database transaction để ghi inbox/processed-events **và** thay đổi nghiệp vụ. Đừng ghi processed marker trước ở transaction riêng rồi crash khiến side effect chưa chạy nhưng lần sau bị bỏ qua.

Nếu ứng dụng cần đúng thứ tự cập nhật trên một order, bổ sung `aggregate_version`/optimistic lock. `JMSXGroupID` có thể giúp điều phối trong **queue B**, nhưng không tự bảo đảm global order giữa hai chiều hoặc nhiều bridges.

## 10. Java/Jakarta JMS: phát ở A, đọc ở B với eventId ổn định

Lab Java này chứng minh producer local commit và consumer B commit là **hai mốc riêng**. Nó không tự tạo Core bridge; broker.xml ở mục 4–5 là phần forwarding.

### 10.1. Maven

Dự án:

~~~text
cross-region-bridge-lab/
├── pom.xml
└── src/main/java/lab/CrossRegionJms.java
~~~

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab</groupId>
    <artifactId>cross-region-bridge-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.40.0</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 10.2. Java producer/consumer

Tạo `src/main/java/lab/CrossRegionJms.java`:

~~~java
package lab;

import java.util.UUID;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class CrossRegionJms {
    private static final String SOURCE_TOPIC = "orders.events";
    private static final String DESTINATION_FQQN =
            "orders.remote.in::orders.remote.process";

    private CrossRegionJms() {}

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            throw new IllegalArgumentException(
                    "Usage: send <eventId> <orderId> | consume");
        }

        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = required("BROKER_USER");
        String pass = required("BROKER_PASSWORD");
        ConnectionFactory factory = new ActiveMQConnectionFactory(url);

        switch (args[0]) {
            case "send" -> {
                if (args.length != 3) {
                    throw new IllegalArgumentException(
                            "send <stable-eventId> <orderId>");
                }
                send(factory, user, pass, args[1], args[2]);
            }
            case "consume" -> {
                if (args.length != 1) {
                    throw new IllegalArgumentException("consume");
                }
                consume(factory, user, pass);
            }
            default -> throw new IllegalArgumentException(
                    "Unknown mode: " + args[0]);
        }
    }

    private static void send(
            ConnectionFactory factory, String user, String pass,
            String eventId, String orderId) {

        try (JMSContext context = factory.createContext(
                user, pass, JMSContext.SESSION_TRANSACTED)) {
            TextMessage event = context.createTextMessage(
                    "OrderConfirmed orderId=" + orderId);
            event.setStringProperty("eventId", eventId);
            event.setStringProperty("originRegion", "region-a");
            event.setStringProperty("orderId", orderId);
            event.setStringProperty("JMSXGroupID", orderId);

            context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .send(context.createTopic(SOURCE_TOPIC), event);

            context.commit();
            System.out.println("A_LOCAL_COMMITTED"
                    + " eventId=" + eventId
                    + " orderId=" + orderId);
        }
    }

    private static void consume(
            ConnectionFactory factory, String user, String pass)
            throws Exception {

        try (JMSContext context = factory.createContext(
                user, pass, JMSContext.SESSION_TRANSACTED)) {

            // Artemis FQQN: consume đúng queue B dưới address B.
            JMSConsumer consumer = context.createConsumer(
                    context.createQueue(DESTINATION_FQQN));

            System.out.println("B_CONSUMER_READY");
            while (true) {
                Message raw = consumer.receive(5000);
                if (raw == null) {
                    System.out.println("B_IDLE");
                    continue;
                }

                try {
                    TextMessage event = (TextMessage) raw;
                    String eventId =
                            event.getStringProperty("eventId");
                    String orderId =
                            event.getStringProperty("orderId");
                    int deliveryCount = raw.propertyExists(
                            "JMSXDeliveryCount")
                            ? raw.getIntProperty("JMSXDeliveryCount") : 0;

                    System.out.println("B_RECEIVED"
                            + " eventId=" + eventId
                            + " orderId=" + orderId
                            + " deliveryCount=" + deliveryCount);

                    // Lab: mô phỏng side effect; KHÔNG có DB thật.
                    // Production:
                    // 1) Begin DB transaction.
                    // 2) INSERT eventId vào processed_events (unique).
                    // 3) Chỉ chạy business update nếu INSERT thành công.
                    // 4) Commit DB transaction.
                    // 5) Sau đó mới commit JMS ACK.
                    context.commit();
                    System.out.println("B_JMS_ACKED"
                            + " eventId=" + eventId);
                } catch (Exception failure) {
                    context.rollback();
                    throw failure;
                }
            }
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing environment variable " + name);
        }
        return value;
    }
}
~~~

**Giới hạn chính xác của chương trình:**

- `A_LOCAL_COMMITTED` chỉ là kết quả transaction **trên A**. Không kết luận message đã tới B.
- Producer dùng **JMS Topic** tại address MULTICAST `orders.events` để tạo reference vào cả hai queue ở A.
- Consumer dùng FQQN Artemis `orders.remote.in::orders.remote.process` để đọc đúng queue B. FQQN là cú pháp Artemis; đừng mặc nhiên dùng nó với Classic JMS client.
- `eventId` do caller cung cấp: **phải ổn định qua retry**. Không sinh UUID mới cho cùng một nghiệp vụ nếu send timeout và cần retry; UUID chỉ nên tạo **một lần khi event được tạo bền vững**.
- `JMSXGroupID` giúp điều phối các message cùng order tại queue B nếu provider/grouping config cho phép, nhưng bridge và nhiều producer không bảo đảm reorder toàn cục.
- Ví dụ **không có database**: `B_JMS_ACKED` chưa chứng minh side effect kinh doanh. Muốn idempotent thật, hiện thực giao dịch DB + unique eventId như mục 9.
- Khi consumer rollback hoặc connection fail, message có thể redeliver. Không dùng `JMSXDeliveryCount` như bằng chứng duy nhất message đã xử lý trước đó.

### 10.3. Lệnh chạy theo pha

Giả định broker A/B đã chạy, Core bridge kết nối được và các user có quyền đúng. Trong PowerShell:

~~~powershell
mvn -q -DskipTests package

# Terminal A: nối broker A local.
$env:BROKER_URL = "tcp://127.0.0.1:61616"
$env:BROKER_USER = "orders-publisher"
$env:BROKER_PASSWORD = "LAB_ONLY_PUBLISHER_PASSWORD"
mvn -q exec:java "-Dexec.mainClass=lab.CrossRegionJms" "-Dexec.args=send evt-1001 order-42"

# Terminal B: broker B local qua cổng map/host riêng của môi trường lab.
$env:BROKER_URL = "tcp://127.0.0.1:61626"
$env:BROKER_USER = "orders-processor"
$env:BROKER_PASSWORD = "LAB_ONLY_PROCESSOR_PASSWORD"
mvn -q exec:java "-Dexec.mainClass=lab.CrossRegionJms" "-Dexec.args=consume"
~~~

Cổng **61626** chỉ là ví dụ port mapping broker B trong lab; phải có mapping tương ứng. Không dùng credential thật trong tài liệu/Git. Trường hợp TLS production, URL user app phải dùng TLS/truststore phù hợp như chính sách triển khai; đừng lấy plain TCP mẫu local làm cấu hình production.

**Dấu hiệu quan sát:**

~~~text
Terminal A:
  A_LOCAL_COMMITTED eventId=evt-1001 orderId=order-42

Terminal B, nếu WAN/bridge/B có khả năng nhận:
  B_RECEIVED eventId=evt-1001 orderId=order-42 deliveryCount=1
  B_JMS_ACKED eventId=evt-1001
~~~

Đừng yêu cầu hai log xuất hiện sát nhau khi WAN có độ trễ hoặc partition. **Độ trễ end-to-end** cần đo từ event createdAt của producer đến business commit ở B, với clock được đồng bộ và trace correlation thích hợp.

## 11. Ordering, nhiều đường forward và thiết kế failover

### 11.1. Một thứ tự toàn hệ thống không thể tự có từ hai broker

Một bridge A→B trên một queue có thể giữ trình tự forward trong các điều kiện bình thường, nhưng **không nên hứa total order** khi:

- Nhiều producer độc lập cùng gửi message cho một aggregate.
- Có bridge thứ hai/đường DR cùng forward tới B.
- Có replay DLQ/backfill ngoài đường live.
- B xử lý song song các queue/group khác nhau.
- WAN reconnect và message bị redeliver.

Với nghiệp vụ cần thứ tự theo order, dùng một `aggregateVersion` từ nguồn dữ liệu đáng tin cậy và kiểm tra phiên bản ở consumer. `JMSXGroupID` giúp **affinity** trên queue, nhưng không phải công cụ reorder message có seq sai.

### 11.2. Hai vùng active-active là bài toán khác

Nếu A và B đều nhận write cho **cùng** account/order, một bridge hai chiều không giải quyết conflict:

~~~text
A accepts order-42 version=7
B accepts order-42 version=7 concurrently
A -> B and B -> A
=> Conflict, duplicate hoặc loop nếu thiếu cơ chế điều phối
~~~

Cần chọn một trong các chính sách có chứng minh:

- **Single-writer theo aggregate/region ownership**, có fencing khi chuyển quyền.
- **Conflict resolution rõ** với version/vector clock/commutative operation nếu domain cho phép.
- **Eventual consistency** với reconcile và audit nghiệp vụ.
- Cơ chế cơ sở dữ liệu/consensus thích hợp khi yêu cầu linearizable write; không tuyên bố JMS bridge cung cấp consensus.

Không tự gọi hai broker độc lập có bridge hai chiều là HA cluster. Việc một vùng mất không tự chuyển nguồn write sang vùng kia với zero RPO.

### 11.3. Kết nối HA của B không đồng nghĩa failover cả vùng

`static-connectors` có thể trỏ tới một hay nhiều endpoint của cụm B theo topology đúng, nhưng bridge chỉ có thể forward vào **destination có state/identity và HA phù hợp**. Không liệt kê tùy tiện hai broker **độc lập** có queue cùng tên như thể chúng là một queue logic; dữ liệu có thể bị tách, reorder hoặc không được tiêu thụ từ cả hai.

Phải hiểu B là active/backup replication, cluster routing, shared store hay độc lập. Kiểm thử restart và failover với persistent message trước khi khẳng định recovery.

## 12. Classic Network of Brokers: cùng mục tiêu, semantics khác

ActiveMQ Classic dùng **Network of Brokers** với các network connectors để forward message theo **remote demand/subscription** và policy. Nó **không tương đương 1:1** với Artemis Core bridge tiêu thụ một queue cố định.

Một mảnh XML cho **Classic lab**, dưới `<networkConnectors>` của `activemq.xml`:

~~~xml
<networkConnector
    name="classic-a-to-b"
    uri="static:(tcp://classic-b:61616)"
    duplex="false"
    networkTTL="1"
    conduitSubscriptions="true"/>
~~~

**Chỉ là ví dụ plaintext trong mạng lab cách ly**; production phải dùng SSL transport/cert/credential theo **Classic client/connector**, không copy các Netty parameter `sslEnabled` của Artemis sang Classic.

| Khía cạnh | Artemis Core bridge | Classic Network of Brokers |
|---|---|---|
| Nguồn gửi | Queue cụ thể do bridge consume | Network connector thường dựa trên **demand** từ broker khác |
| Đích | `forwarding-address` của broker từ xa | Destination theo network demand/subscriptions/policies |
| Giao thức nội bộ | Artemis Core | Classic OpenWire trong topology điển hình |
| Duplicate/loop | Bridge duplicate detection, kiến trúc hướng một chiều | Cần networkTTL, conduit subscriptions, duplex/loop policy |
| Backlog | Queue nguồn của bridge giữ message chờ forward | Phụ thuộc demand forwarding, persistence và broker policies |
| Cấu hình | `broker.xml` + `<bridges>` | `activemq.xml` + `<networkConnectors>` |

**Bẫy quan trọng:** Classic network connector **không tự tạo bản sao của mọi message vào mọi broker**. Nó quan sát demand và forward theo policy; nếu cần replication/audit feed bắt buộc, phải xác định demand, durable subscriptions, static includes và chiều link cụ thể theo phiên bản Classic.

Với Classic, các tùy chọn `networkTTL`, `duplex` và `conduitSubscriptions` ảnh hưởng hành vi network; không dùng bridge XML Artemis để sửa lỗi route Classic.

## 13. SLO và kịch bản kiểm thử lỗi bắt buộc

### 13.1. Các SLO nên chốt

| SLO | Công thức/ý nghĩa | Ví dụ quyết định |
|---|---|---|
| Publish latency A | Thời gian producer gửi/commit với broker A | Không lệ thuộc RTT WAN trong đường async |
| Forwarding lag | Thời gian event A được B nhận | p95/p99 dưới điều kiện WAN bình thường |
| Consumer business lag B | Event createdAt → B business commit | Bao gồm backlog B và downstream |
| WAN queue oldest age | Message chờ forward lâu nhất ở A | Alert sớm trước khi vượt SLA |
| Backlog drain RTO | Backlog / (effective forward rate − new arrival rate) | Phải có headroom chuyển tải |
| Cross-region RPO | Event đã commit ở A nhưng chưa tới B khi A mất vĩnh viễn | Async RPO > 0 nếu không có lớp bảo vệ khác |
| Duplicate tolerance | Side effect không xảy ra hai lần khi resend/redelivery | Unique eventId + transaction guard |
| Disk headroom | Bytes còn trống / tốc độ tăng dưới partition | Chịu được outage target + biên an toàn |

### 13.2. Fault-injection matrix

| Test | Cách làm trong lab | PASS khi |
|---|---|---|
| WAN RTT cao | Thêm delay trong namespace thử | Tốc độ/lag đo được, không sai tính đúng |
| Bandwidth thấp | Shaping trên bridge link lab | Backlog tăng theo mô hình; không làm đầy disk bất ngờ |
| WAN đứt 20 phút | Isolate đường A→B | Producer A local vẫn commit trong giới hạn capacity; queue WAN A giữ message |
| WAN trở lại | Restore route, quan sát drain | Queue WAN giảm; remote nhận đủ ID và không side effect trùng |
| Mất ACK bridge | Inject loss/asymmetric disruption | Bridge retry; duplicate detection/app idempotency bảo vệ |
| B restart | Stop/restart B trong lab | Persisted data B recover; A reconnect và forward tiếp |
| A restart | Stop/restart A khi queue WAN còn backlog | Queue durable và bridge tiếp tục forward sau recovery |
| B sai certificate | Cert SAN/CA không hợp lệ trong lab | TLS từ chối; **không** fallback plaintext/trustAll |
| Bridge user thiếu send | Rút role trên B ở lab | Authz denied, queue A tăng có alert |
| B queue/process chậm | Tạm dừng consumer B | Queue B tăng; bridge destination pressure được theo dõi |
| B disk gần đầy | Mô phỏng quota/disk cap trong lab | Chế độ flow-control được báo, không xóa message để “sửa” |
| Active-active duplicate | Replay cùng eventId có chủ đích | DB unique constraint không cho double side effect |

**Trong mọi test**, lưu eventId, region, timestamps UTC, message count, bytes, bridge connection status, queue depth/delivering, paging, disk free, DLQ và application commit. Không chỉ nhìn “TCP connected”.

### 13.3. Vận hành khi backlog lớn

Khi WAN phục hồi sau partition, tránh đẩy toàn bộ backlog sang B không giới hạn làm quá tải database hoặc API downstream. Có thể:

- Điều tiết producer đầu A nếu SLA cho phép.
- Điều chỉnh concurrency của consumer B theo **capacity downstream**, không tăng vô hạn.
- Thêm bandwidth/headroom tạm thời để drain, nếu được phép và không làm nghẽn dịch vụ khác.
- Định nghĩa ưu tiên theo **queue/topic riêng** chỉ khi thứ tự nghiệp vụ cho phép.
- Theo dõi message age và retry/DLQ; phân biệt poison message với network delivery failures.

Nếu backlog chứa message đã hết hạn nghiệp vụ, cần policy expiry/reconcile có phê duyệt. **Không purge queue WAN hoặc page/journal** để chạy nhanh khi chưa chấp nhận mất sự kiện.

## 14. Runbook chẩn đoán: producer A thành công nhưng B không thấy message

Đi theo từng bước, tránh đổi nhầm tầng:

1. **A local commit:** kiểm tra producer A dùng `orders.events`, routing MULTICAST và message persistent; có entry ở `wan.region-b.out` không?
2. **Queue WAN A:** queue depth/oldest age/delivering count; có consumer cạnh tranh nào vô tình lấy message khỏi queue nguồn không?
3. **Core bridge:** bridge đã deploy và connected? Queue-name, forwarding-address, retry/reconnect, broker logs, confirmations có tăng không?
4. **Transport WAN:** DNS, firewall, port, TLS handshake, SAN/truststore, packet loss, RTT và bandwidth shaping.
5. **Remote authentication:** bridge user được B chấp nhận không, role `send` trên `orders.remote.in` có hiệu lực không?
6. **B routing:** address ANYCAST `orders.remote.in` và queue `orders.remote.process` đã tồn tại chưa; có message vào không?
7. **B consumer:** đang consume đúng FQQN không? Queue count, delivering, DLQ, scheduled messages, idempotency/version guard.
8. **Storage pressure:** A/B page, journal, disk free và flow-control; bridge không thể khắc phục B disk full bằng retry ngắn hơn.
9. **Correlate eventId:** tìm event ở source, WAN queue, destination, app log và DB processed_events; đừng suy chỉ từ queue count hiện tại.
10. **Phân loại RPO/RTO:** Nếu A mất hẳn, event chưa replicate nằm ở đâu? Nếu WAN trở lại, drain có đủ headroom không?

**Tách lỗi theo dấu hiệu:** Nếu `wan.region-b.out` không có message thì xem producer/routing A; nếu queue WAN có backlog nhưng B không nhận thì xem bridge/WAN/B auth; nếu queue B có message nhưng app chưa xử lý thì xem consumer/downstream/DLQ. Những lỗi ấy đòi biện pháp hoàn toàn khác nhau.

## 15. Sai lầm thiết kế phải tránh

### 15.1. “Dùng hai broker là có RPO 0”

Hai broker độc lập với bridge **bất đồng bộ** không bảo đảm mọi event đã commit tại A đều được B nhận khi A mất hoàn toàn. Muốn RPO 0 cần một cơ chế đồng bộ/đồng thuận và đánh đổi latency/availability được thiết kế riêng; không tự gắn nhãn exactly-once cho bridge.

### 15.2. “Reconnect vô hạn nghĩa là hệ thống chịu được WAN chết vô hạn”

Không. Backlog và disk ở A có giới hạn. `reconnect-attempts=-1` chỉ nói client tiếp tục thử; cần capacity alert, backpressure và quyết định khi volume gần đầy.

### 15.3. “Bridge window 1 MiB tức link bị giới hạn ở 1 MiB/s”

Sai. Window là flow-control/in-flight confirmation budget, không phải bandwidth limiter. Dùng đo bytes/sec và QoS/rate limiting ở tầng thích hợp.

### 15.4. “Duplicate detection = exactly-once nghiệp vụ”

Sai. Cache có phạm vi và giới hạn, còn crash giữa DB commit và JMS ACK gây redelivery. Dùng unique eventId và transaction ở consumer.

### 15.5. “Có JMSXGroupID thì toàn vùng A/B xử lý đúng một thứ tự”

Không. Grouping có scope theo queue/consumer ownership; nhiều producer, bridges và replay có thể làm thứ tự nghiệp vụ khác nhau. Dùng aggregateVersion và source sequencing thực.

### 15.6. “Bridge hai chiều cho cùng address sẽ tự đồng bộ mọi thứ”

Có thể tạo echo loop, duplicate và active-active conflict. Cần hướng dữ liệu rõ, origin/hop guards hoặc ownership, không dùng topology đối xứng ngẫu nhiên.

### 15.7. “Chỉ test bằng cách kill broker”

Không đủ. Cần RTT cao, packet loss, asymmetric ACK loss, B backpressure, TLS/ACL failure, recovery queue và **disk near-full** trong môi trường cách ly.

## 16. Câu hỏi tự kiểm tra

**1. Producer A commit thành công rồi WAN đứt, B không nhận được event. A có sai không?**  
Không nhất thiết. Với async bridge, A đã commit **local**; event còn phải được forward qua queue WAN. Cần xem RPO contract và backlog/source durability.

**2. B đã ghi message nhưng A không nhận confirm, sự cố nào xảy ra?**  
Bridge có thể forward lại. Duplicate detection broker B giảm duplicate trong phạm vi cache, consumer vẫn phải idempotent.

**3. Vì sao link 40 Mbit/s có thể vẫn không chuyển được 610 message 8 KiB mỗi giây?**  
610 là **giới hạn lý tưởng theo payload**; Core/TLS/TCP overhead, loss, persistence, flow control và luồng tranh chấp làm effective rate thấp hơn.

**4. WAN mất 20 phút với 300 msg/s, 8 KiB/message. A cần tối thiểu bao nhiêu payload storage?**  
360.000 message, khoảng **2,75 GiB payload**; thực tế phải dự phòng journal/page metadata, HA, disk watermark và tăng trưởng giờ cao điểm.

**5. WAN phục hồi, bridge chuyển 450 msg/s nhưng producer tiếp tục 300 msg/s. Bao lâu rút hết 360.000 message?**  
Khoảng **40 phút** trong mô hình tốc độ ổn định, chưa tính biến động và queue downstream.

**6. Khi nào nên dùng Artemis federation thay vì Core bridge?**  
Khi cần mô hình queue/address federation theo policy/demand và hỗ trợ phiên bản/topology; Core bridge phù hợp luồng forward **một queue nguồn cố định**. Cả hai cần test failure/duplicates.

**7. Có thể dùng cùng bridge config với ActiveMQ Classic không?**  
Không. Classic dùng Network of Brokers/Network Connector (thường OpenWire), policy demand/networkTTL/conduit; Artemis Core bridge dùng queue-name/forwarding-address và Core connector.

**8. B thấy message trong queue nhưng business handler chưa commit thì bridge đã hoàn thành chưa?**  
Bridge có thể đã hoàn thành **forward**. Business commit/ACK là mốc độc lập, phải có consumer monitoring và idempotency.

## 17. Checklist triển khai liên vùng

- [ ] Đã định nghĩa SLA/SLO: source availability, cross-region RPO, RTO drain, processing lag và duplicate tolerance.
- [ ] Có topology tách vùng, **một chiều A→B** với queue nguồn riêng hoặc thiết kế hai chiều không vòng lặp.
- [ ] Publisher route đúng MULTICAST để tạo bản local và WAN; không có competing consumer cho WAN queue.
- [ ] Bridge dùng đúng `queue-name`, `forwarding-address`, CORE connector/acceptor và user có quyền `send` ở B.
- [ ] TLS hai đầu đúng CA/SAN/hostname; secret không commit Git, network policy giới hạn port WAN.
- [ ] Reconnect/backoff không gây storm; error auth/TLS được phân loại khỏi network outage.
- [ ] Có duplicate detection ở broker và **unique eventId + idempotent DB** ở consumer.
- [ ] Có aggregateVersion nếu nghiệp vụ cần ordering; không coi group ID là global lock.
- [ ] Đã tính \(\lambda \times s\), bandwidth budget, RTT/BDP, backlog outage và thời gian drain có headroom.
- [ ] Có disk margin và alert page/journal/backlog age khi WAN đứt; không dựa vào retry vô hạn.
- [ ] Có giới hạn ingress/egress QoS thích hợp; không hiểu sai confirmation window là bandwidth limit.
- [ ] Đã test full partition, asymmetric loss, delay, throttling, B disk pressure và broker restarts.
- [ ] Có kiểm thử destination routing và security deny cases.
- [ ] Có metrics trên **cả A và B**, correlation bằng eventId, log UTC, DLQ/redelivery và business commit.
- [ ] Đã phân biệt Artemis Core bridge, Artemis federation, cluster và Classic Network of Brokers.
- [ ] Không purge/delete queue hoặc xóa journal/page để xử lý sự cố WAN.

## 18. Kết luận

**Kết nối liên vùng đáng tin cậy bắt đầu bằng ranh giới trách nhiệm rõ ràng:** broker A commit local, queue WAN giữ sự kiện trong lúc mất mạng, bridge chuyển bất đồng bộ tới broker B, rồi consumer B hoàn tất nghiệp vụ độc lập. RTT cao làm các vòng xác nhận/flow-control ảnh hưởng throughput; packet loss và mất ACK tạo trạng thái gửi chưa chắc chắn; giới hạn băng thông khiến backlog cần disk và thời gian drain được tính trước.

**Artemis Core bridge** thích hợp cho luồng forward một queue nguồn cố định, có retry/duplicate detection và TLS; **Classic Network of Brokers** có cơ chế demand forwarding khác. Không giải pháp nào tự cấp exactly-once end-to-end, global ordering hay RPO 0 xuyên vùng. Thiết kế phải kết hợp **queue durable, bandwidth/headroom, backpressure, TLS/ACL, idempotent consumer, versioning, quan sát hai vùng và fault injection** để đường truyền vẫn vận hành an toàn khi liên kết không hoàn hảo.
