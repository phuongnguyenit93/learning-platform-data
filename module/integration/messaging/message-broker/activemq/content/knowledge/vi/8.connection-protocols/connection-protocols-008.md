# TCP, TLS, WebSocket và VM transport: phạm vi sử dụng

> **Chương:** Giao thức kết nối  
> **Bối cảnh thực hành:** Apache ActiveMQ Classic và Apache ActiveMQ Artemis, với Java/JMS producer–consumer, kết nối từ dịch vụ backend, client trình duyệt và broker nhúng trong bài kiểm thử.

Cùng một queue có thể được truy cập qua kết nối TCP thông thường, TCP được bảo vệ bằng TLS hoặc một gateway WebSocket. Trong bài test nhúng, ứng dụng thậm chí có thể trao đổi message với broker trong **cùng JVM** qua VM/In-VM transport. Những lựa chọn này **không thay đổi ý nghĩa queue, topic, ack hay transaction**; chúng quyết định **đường đi, mức bảo mật, khả năng truy cập và hành vi khi mất kết nối**.

Lỗi cấu hình thường xuất hiện khi nhầm **transport** với **protocol**: một cổng TCP mở được nhưng client không bắt tay JMS; trình duyệt tạo WebSocket thành công nhưng broker không hiểu subprotocol; hoặc client trỏ đến VM transport trong khi broker nằm ở process khác. Bài này cung cấp mô hình phân tầng, bảng chọn, cấu hình mẫu và quy trình kiểm chứng riêng cho từng kiểu kết nối.

## 1. Đặt đúng các lớp trước khi so sánh

Một producer Java dùng JMS thường đi qua các lớp sau:

~~~mermaid
flowchart LR
    A["Ứng dụng Java / JMS API"] --> C["JMS client library"]
    C --> P["Wire protocol<br/>OpenWire / Artemis Core / AMQP..."]
    P --> T["Transport<br/>TCP / TLS-over-TCP / WebSocket / In-VM"]
    T --> B["Broker acceptor / transport connector"]
    B --> Q["Queue / topic / address / subscription"]
~~~

**JMS** là API mà mã Java sử dụng; **OpenWire**, **Artemis Core**, **AMQP**, **STOMP** hay **MQTT** là các protocol có cách đóng gói và ngữ nghĩa riêng; **TCP**, **TLS**, **WebSocket**, **VM/In-VM** là các lựa chọn truyền thông giúp protocol đi từ client tới broker.

Bảng phân lớp để tránh lẫn:

| Tầng | Ví dụ | Trả lời câu hỏi |
|---|---|---|
| API | JMS / Jakarta Messaging, JMSContext | Ứng dụng gửi/nhận message bằng interface nào? |
| Wire protocol | OpenWire, Artemis Core, AMQP 1.0, STOMP, MQTT | Hai đầu hiểu loại frame, lệnh và semantics nào? |
| Transport | TCP, TLS trên TCP, WebSocket trên TCP/TLS, In-VM | Frame di chuyển bằng kênh nào? |
| Broker endpoint | Classic transport connector; Artemis acceptor | Broker nghe ở đâu, cho phép protocol nào? |
| Messaging semantics | Queue/topic, ack, transaction, redelivery | Message được lưu, chuyển và xác nhận thế nào? |

**Hệ quả quan trọng:** hai chương trình cùng dùng URI bắt đầu bằng **tcp://** chưa chắc tương thích. Client Classic mặc định có thể gửi **OpenWire**, còn client Artemis thường nói **Artemis Core**; broker phải có protocol tương ứng trên endpoint. TCP chỉ cung cấp luồng byte, không tự chuyển đổi protocol.

### 1.1. Bốn lựa chọn nhìn từ đường truyền

~~~text
1. TCP (không mã hóa ở transport):
   Java/JMS → wire protocol → TCP socket → broker

2. TLS trên TCP:
   Java/JMS → wire protocol → TLS → TCP socket → broker

3. WebSocket:
   Browser/client → HTTP Upgrade → WebSocket frames
                  → messaging subprotocol → broker/gateway
   ws://  = WebSocket trên TCP
   wss:// = WebSocket được bảo vệ bằng TLS

4. VM / In-VM:
   Java application ── gọi cơ chế truyền nội bộ JVM ── embedded broker
   Không đi qua socket TCP giữa hai process
~~~

TLS có thể được triển khai trực tiếp tại broker hoặc kết thúc ở reverse proxy/gateway. Trong trường hợp proxy kết thúc TLS, cần đánh giá riêng **đường từ proxy đến broker** có được mã hóa và xác thực hay không.

## 2. Bảng chọn nhanh theo tình huống sử dụng

| Tình huống | Transport nên xem xét | Lý do | Điều cần xác minh |
|---|---|---|---|
| Java backend và broker ở mạng test cục bộ, có cô lập | **TCP** | Cấu hình đơn giản, dễ phân tích packet/handshake | Network trust boundary, wire protocol, quyền JMS |
| Java service giao tiếp qua mạng nội bộ production | **TLS-over-TCP** | Bảo mật kết nối và xác minh danh tính broker | CA, hostname/SAN, tài khoản, firewall, reconnect |
| Kết nối giữa hai vùng mạng hoặc qua hạ tầng không hoàn toàn tin cậy | **TLS, có thể mTLS** | Mã hóa, xác thực hai chiều nếu cần | Quản lý chứng chỉ, rotation, peer verification |
| Ứng dụng trình duyệt cần dòng sự kiện trực tiếp | **WebSocket/WSS** hoặc gateway ứng dụng | Trình duyệt hỗ trợ WebSocket, không mở raw TCP tùy ý | Subprotocol, auth, Origin, proxy Upgrade, heartbeat |
| Ứng dụng test chạy cùng JVM với broker nhúng | **VM/In-VM** | Không cần mở port, nhanh và tiện cho integration test | Broker cùng process, lifecycle, isolation và cleanup |
| Hai chương trình Java chạy trên hai JVM/host khác nhau | **TCP/TLS** | In-VM không vượt ranh giới process | Địa chỉ, protocol, timeout, TLS |
| Client mobile/browser không nên nhận credential broker | **HTTPS API/gateway, phía sau có TLS tới broker** | Bảo vệ phân quyền và hợp đồng nghiệp vụ | Không đưa broker admin credential ra client |
| Yêu cầu chịu failover broker | **TCP/TLS + cấu hình reconnect/failover của client** | Transport đơn lẻ không tự xử lý failover | URI/driver phù hợp, duplicate/uncertain commit |

**Mặc định hợp lý cho hệ thống backend production:** giao tiếp qua **TLS** và client hỗ trợ reconnect thích hợp. **VM/In-VM** ưu tiên cho test nhúng hoặc ứng dụng thực sự chạy broker cùng process. **WSS** phù hợp cho kết nối từ trình duyệt khi có lý do cần streaming; không cần WebSocket nếu một API HTTP thông thường đã giải quyết yêu cầu.

## 3. TCP: lớp truyền dẫn cơ bản cho ứng dụng Java và broker

TCP cung cấp kết nối hai chiều với thứ tự byte và cơ chế phát lại gói ở tầng mạng. TCP **không biết message JMS**, không bảo đảm ứng dụng đã commit transaction, không cung cấp bí mật dữ liệu và cũng không bảo đảm broker sẽ còn sống sau khi socket được chấp nhận.

### 3.1. Classic và Artemis mở cổng khác nhau như thế nào?

Trong **ActiveMQ Classic**, broker thường khai báo **transport connector**. Một cấu hình ví dụ:

~~~xml
<!-- Mảnh cấu hình bên trong phần broker của activemq.xml -->
<transportConnectors>
    <transportConnector
        name="openwire-tcp"
        uri="tcp://127.0.0.1:61616"/>
</transportConnectors>
~~~

Một Java client Classic thường sử dụng:

~~~java
// Client API của ActiveMQ Classic, sử dụng thư viện phù hợp.
org.apache.activemq.ActiveMQConnectionFactory classicFactory =
    new org.apache.activemq.ActiveMQConnectionFactory(
        "tcp://127.0.0.1:61616");
~~~

**ActiveMQ Artemis** dùng **acceptor**. Ví dụ:

~~~xml
<!-- Mảnh cấu hình bên trong acceptors của broker.xml -->
<acceptors>
    <acceptor name="core-tcp">
        tcp://127.0.0.1:61616?protocols=CORE
    </acceptor>
</acceptors>
~~~

Client Artemis tương ứng:

~~~java
// Client Artemis JMS sử dụng Core protocol.
org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory artemisFactory =
    new org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory(
        "tcp://127.0.0.1:61616");
~~~

**Hai đoạn client không thể hoán đổi tùy tiện.** Tên cổng giống nhau không nói lên broker nào đang chạy hoặc protocol nào được chấp nhận. Artemis có thể bật thêm OpenWire trên acceptor phù hợp, nhưng phải kiểm chứng phiên bản/configuration; không suy ra tương thích chỉ từ URI **tcp://**.

Các cổng **61616**, **61617**, **61614** thường xuất hiện trong tài liệu/lab, nhưng đều là **ví dụ**, không phải cấu hình bắt buộc. Luôn đọc trạng thái listener thực tế.

### 3.2. Khi nào TCP không mã hóa phù hợp?

Có thể dùng cho:

- Bài test local, môi trường cô lập thực sự và không chứa dữ liệu nhạy cảm.
- Kiểm tra ban đầu broker–client cùng host để loại trừ lỗi TLS.
- Mạng thử nghiệm có firewall và giới hạn người truy cập rõ ràng.

Không nên coi “mạng nội bộ” mặc nhiên đủ an toàn cho production. Khi có nhiều máy, container, pod, nhiều nhóm quản trị hoặc hạ tầng chia sẻ, cần đánh giá nguy cơ nghe lén, giả mạo broker và lộ credential, rồi ưu tiên TLS.

### 3.3. Nhận biết lỗi TCP và lỗi protocol

| Hiện tượng | Phân lớp lỗi |
|---|---|
| **Connection refused** | Không có process nghe, bind sai interface/port hoặc kết nối bị từ chối |
| **Connection timeout** | Đường mạng/firewall/routing hoặc listener không phản hồi đúng hạn |
| TCP kết nối được rồi bị đóng ngay | Có thể **protocol mismatch**, TLS mismatch, policy hoặc timeout |
| Kết nối và login thành công nhưng send bị từ chối | **Authorization/routing**, không phải TCP |
| Send thành công nhưng consumer không nhận | Queue/topic/subscription/routing, ack hoặc consumer-side; không nhất thiết lỗi TCP |

Một phép thử mở socket chỉ chứng minh **cổng có thể nhận TCP**, chưa chứng minh protocol messaging tương thích hoặc queue đã có dữ liệu.

## 4. TLS: bảo vệ TCP, không thay đổi semantics của JMS

TLS cung cấp ba năng lực chính khi cấu hình đúng:

1. **Mã hóa** dữ liệu truyền trên đường kết nối.
2. **Xác minh server** bằng chứng chỉ và hostname; client không nên chỉ tin vì kết nối TCP thành công.
3. **Xác thực client bằng chứng chỉ (mTLS)** khi bật và triển khai đầy đủ. mTLS khác với user/password hoặc authorization trên destination.

### 4.1. Cơ chế trong một kết nối

~~~mermaid
sequenceDiagram
    participant C as Java/JMS client
    participant B as Broker TLS listener
    C->>B: TCP connect
    C->>B: TLS ClientHello
    B-->>C: Server certificate + TLS handshake
    C->>C: Verify CA chain / hostname / validity
    opt mTLS
        B->>C: Request client certificate
        C-->>B: Client certificate / proof of possession
    end
    C->>B: Messaging protocol handshake (over TLS)
    B-->>C: Protocol / auth response
    C->>B: JMS send, receive, ack, transaction
~~~

TLS handshake thành công **chưa đủ** để nói ứng dụng đã đăng nhập hoặc có quyền consume. Messaging client vẫn phải thực hiện bước wire protocol/authentication; sau đó broker áp dụng ACL cho destination.

### 4.2. KeyStore, TrustStore và danh tính

| Thành phần | Nội dung | Bên thường dùng |
|---|---|---|
| **Server keystore** | Private key + chứng chỉ broker | Broker (hoặc TLS-terminating proxy) |
| **Client truststore** | CA/chứng chỉ được tin cậy để xác minh broker | JMS client |
| **Client keystore** | Private key + chứng chỉ ứng dụng khi mTLS | Client khi broker yêu cầu |
| **Server truststore** | CA dùng để xác minh chứng chỉ client | Broker khi mTLS bật |

Tên DNS trong URL mà client kết nối phải khớp **Subject Alternative Name (SAN)** của chứng chỉ; không nên giải quyết lỗi hostname bằng cách tắt xác minh. Nếu truy cập qua load balancer, chứng chỉ phải phù hợp **hostname mà client thực sự dùng** và điểm kết thúc TLS.

**Rotation:** tránh phụ thuộc một file chứng chỉ có thể bị thay ngoài ý muốn mà không được process reload. Cần biết broker/proxy/client phiên bản đang dùng có reload cert động hay yêu cầu restart/reconnect, và thực hành thay CA/chứng chỉ trước khi hết hạn.

### 4.3. Artemis TLS acceptor: ví dụ có thể triển khai sau khi gắn secret

Artemis sử dụng TCP acceptor với tham số **sslEnabled=true**, ví dụ:

~~~xml
<!-- Fragment broker.xml: thay các giá trị ví dụ bằng secret và file thật. -->
<acceptors>
    <acceptor name="core-tls">
        tcp://0.0.0.0:61617?protocols=CORE;sslEnabled=true;keyStorePath=/opt/mq/certs/broker.p12;keyStoreType=PKCS12;keyStorePassword=REPLACE_VIA_SECRET
    </acceptor>
</acceptors>
~~~

Trong môi trường thật:

- Bảo vệ quyền đọc **broker.p12** và lấy password từ cơ chế secret/config injection tương thích phiên bản; **không commit mật khẩu thật** vào repository.
- Cấu hình **needClientAuth=true** và truststore server khi yêu cầu mTLS. Với xác thực một chiều, broker không cần yêu cầu client cert.
- Cho phép endpoint qua firewall chỉ từ vùng ứng dụng; **0.0.0.0** nghĩa là nghe trên mọi interface được hệ thống cấp, cần chủ đích.
- Không giả định bật **sslEnabled** cho toàn broker: thuộc tính ở **acceptor/connector**; có thể có cả cổng TCP thường và TLS riêng, hoặc endpoint tích hợp tùy kiến trúc.

Client Artemis cần chọn TLS và tin đúng CA. Ví dụ **URI minh họa** với Netty connector parameters:

~~~text
tcp://mq.internal.example:61617?sslEnabled=true;trustStorePath=/app/certs/mq-trust.p12;trustStoreType=PKCS12;trustStorePassword=REPLACE_VIA_SECRET;verifyHost=true
~~~

Cách cấu hình key/truststore và tên property khả dụng phụ thuộc phiên bản client Artemis; kiểm chứng bằng connection test với thư viện trong dự án. **Không đưa mật khẩu truststore vào chuỗi URL được log/trace trong production**; thay bằng kênh cấu hình bí mật của ứng dụng và client.

### 4.4. Classic TLS: transport URI khác Artemis

ActiveMQ Classic có **SSL transport**, ví dụ một transport connector:

~~~xml
<!-- Classic activemq.xml: cần sslContext/keystore phù hợp được cấu hình riêng. -->
<transportConnectors>
    <transportConnector
        name="openwire-tls"
        uri="ssl://0.0.0.0:61617?needClientAuth=false"/>
</transportConnectors>
~~~

Phía Classic client, API thường gặp là **ActiveMQSslConnectionFactory**, dùng địa chỉ bắt đầu bằng **ssl://** và cấu hình truststore/keystore của client:

~~~java
import org.apache.activemq.ActiveMQSslConnectionFactory;

ActiveMQSslConnectionFactory factory =
    new ActiveMQSslConnectionFactory("ssl://mq.internal.example:61617");

factory.setTrustStore("/app/certs/classic-trust.jks");
factory.setTrustStorePassword(System.getenv("MQ_TRUSTSTORE_PASSWORD"));

// Khi broker bật mTLS: cấu hình thêm client keyStore/secret.
~~~

Đây là **mảnh thiết lập**; broker Classic phải có **sslContext và khóa/chứng chỉ server** hợp lệ. Không thể chỉ đổi URI client thành **ssl://** rồi mong một cổng TCP thường tự biến thành TLS.

**Khác biệt cần nhớ:** Artemis thường thể hiện TLS trên URI **tcp://...?sslEnabled=true**; Classic thường thể hiện bằng **ssl://**. Không sao chép nguyên URI của sản phẩm này sang client sản phẩm kia.

### 4.5. Kiểm thử TLS độc lập trước khi chạy JMS

Khi có endpoint TLS và CA test:

~~~bash
openssl s_client \
  -connect mq.internal.example:61617 \
  -servername mq.internal.example \
  -verify_hostname mq.internal.example \
  -verify_return_error \
  -CAfile trusted-ca.pem
~~~

Lệnh kiểm tra **bắt tay TLS, chuỗi chứng chỉ và hostname**; kết quả tốt thường có thông tin xác minh thành công. Nếu cấu hình yêu cầu mTLS, bổ sung chứng chỉ và private key client bằng các tùy chọn thích hợp và bảo vệ key. Lệnh này **không phát message JMS**; sau TLS phải thử client với đúng protocol và credential.

Bài thử âm tính quan trọng:

- Kết nối bằng **hostname khác SAN** → phải bị từ chối khi xác minh hostname.
- Dùng **CA không được tin cậy** → phải thất bại.
- Trỏ **TLS client** vào **plaintext TCP port** hoặc ngược lại → bắt tay thất bại, không tự fallback sang plaintext.
- Client không có chứng chỉ khi broker bật **needClientAuth** → handshake phải thất bại theo cấu hình.

Nếu các phép thử âm tính vẫn kết nối được, hãy kiểm tra liệu ứng dụng đã vô tình **disable hostname/certificate verification** hoặc đang đi qua proxy kết thúc TLS với chính sách khác.

## 5. WebSocket: đường vào broker qua HTTP Upgrade

Trình duyệt không cho ứng dụng JavaScript mở một kết nối TCP tùy ý tới port broker. **WebSocket** tạo kênh hai chiều bắt đầu bằng **HTTP request nâng cấp kết nối (Upgrade)**. Sau handshake thành công, client và server trao đổi các **WebSocket frame**; bên trong frame vẫn cần một **messaging subprotocol** thích hợp như STOMP, AMQP hoặc MQTT khi broker hỗ trợ.

### 5.1. WebSocket khác gì TCP JMS thuần?

~~~mermaid
sequenceDiagram
    participant W as Browser / WS client
    participant R as Reverse proxy (optional)
    participant B as Broker WS endpoint
    W->>R: GET /messaging + Upgrade: websocket
    R->>B: Forward Upgrade + protocol headers
    B-->>R: HTTP 101 Switching Protocols
    R-->>W: HTTP 101
    W->>B: STOMP CONNECT frame over WebSocket
    B-->>W: STOMP CONNECTED
    W->>B: STOMP SUBSCRIBE / SEND
    B-->>W: MESSAGE frames
    W->>B: STOMP ACK (if client ack mode)
~~~

**HTTP 101** chỉ xác nhận bước chuyển sang WebSocket, không đảm bảo STOMP CONNECT thành công hoặc user có quyền subscribe. Trình duyệt có thể báo socket **OPEN** trong khi broker từ chối subprotocol/login, hoặc chỉ chấp nhận CONNECT nhưng destination name/routing không đúng.

Trong **ws://**, dữ liệu không được TLS bảo vệ. **wss://** là WebSocket trên TLS, nên có xác minh chứng chỉ tương tự HTTPS. Trong trang web HTTPS, trình duyệt thường chặn việc mở **ws://** vì mixed content; hãy dùng **wss://** khi triển khai web thật.

### 5.2. Classic: WebSocket transport connector

Classic hỗ trợ WebSocket ở các cấu hình/version phù hợp với messaging subprotocol được tích hợp, thường gặp STOMP qua WebSocket. Ví dụ transport connector:

~~~xml
<!-- Classic activemq.xml: endpoint WebSocket ví dụ trên cổng riêng. -->
<transportConnectors>
    <transportConnector name="stomp-ws" uri="ws://127.0.0.1:61614"/>
</transportConnectors>
~~~

Đây là mảnh cấu hình test. Không giả định URI **ws://** mang OpenWire theo cùng cách **tcp://**. Cần kiểm tra danh sách subprotocol mà bản Classic đang dùng hỗ trợ và loại client WebSocket tương ứng.

Để mở WSS, phải cấu hình TLS trực tiếp trên endpoint hỗ trợ hoặc đặt sau reverse proxy TLS thích hợp. Cấu hình URI **wss://** tại frontend mà backend vẫn chỉ có **ws://** không tự bảo đảm bảo mật đoạn proxy → broker.

### 5.3. Artemis: acceptor có giao thức phù hợp với WebSocket

Artemis có khả năng nhận kết nối WebSocket cho một số protocol qua các acceptor Netty được cấu hình phù hợp. Ví dụ tách một endpoint cho **STOMP** trong môi trường test:

~~~xml
<!-- Fragment Artemis broker.xml: kiểm tra WebSocket support
     và yêu cầu HTTP/Upgrade của phiên bản triển khai. -->
<acceptors>
    <acceptor name="stomp-endpoint">
        tcp://127.0.0.1:61614?protocols=STOMP
    </acceptor>
</acceptors>
~~~

**Phải kiểm tra thực tế** rằng phiên bản và cấu hình Netty acceptor này chấp nhận WebSocket Upgrade ở endpoint đã chọn, không chỉ kết nối TCP STOMP thuần. Nếu môi trường yêu cầu thêm tùy chọn HTTP/WebSocket hoặc reverse proxy, cấu hình chúng theo tài liệu của **phiên bản broker đang dùng**, sau đó xác nhận handshake 101 và STOMP CONNECTED. Một **acceptor nhận STOMP qua TCP** không tự chứng minh client WebSocket sẽ kết nối thành công.

Artemis cũng có thể phục vụ giao tiếp WebSocket cho protocol khác tùy phiên bản và acceptor; không dùng một client **STOMP/WebSocket** để nói chuyện với acceptor chỉ bật **CORE**.

### 5.4. JavaScript client: WebSocket vẫn cần STOMP và mapping destination

Ví dụ dùng thư viện **@stomp/stompjs** từ ứng dụng browser đã có bundler. Endpoint **wss://mq.example.test/messaging** và destination trong ví dụ chỉ hoạt động khi reverse proxy/Artemis/Classic đã cấu hình **đúng path, STOMP và mapping**:

~~~javascript
import { Client } from "@stomp/stompjs";

// Được cấp động theo phiên đăng nhập; tránh để broker password
// có quyền rộng trong mã frontend được phát công khai.
const sessionCredential = getShortLivedMessagingCredential();

const client = new Client({
  brokerURL: "wss://mq.example.test/messaging",
  connectHeaders: {
    login: sessionCredential.user,
    passcode: sessionCredential.secret
  },
  reconnectDelay: 5000,
  heartbeatIncoming: 10000,
  heartbeatOutgoing: 10000
});

client.onConnect = () => {
  client.subscribe(
    "/topic/orders.lifecycle.events.v1",
    (frame) => {
      console.log("Event:", frame.body);
      frame.ack();
    },
    { ack: "client-individual" }
  );
};

client.onStompError = (frame) => {
  console.error("STOMP rejected:", frame.headers.message);
};

client.activate();

// Khi UI không còn cần subscription:
// await client.deactivate();
~~~

**Các giả định bắt buộc:**

- Hàm **getShortLivedMessagingCredential** là *placeholder* cho cơ chế cung cấp credential thời hạn ngắn; phải được ứng dụng hiện thực an toàn. Không sao chép đoạn này và điền mật khẩu quản trị broker vào mã frontend.
- Cú pháp **/topic/** trong subscription là **quy ước mapping ví dụ**. Với Artemis, có thể cấu hình prefix anycast/multicast hoặc dùng tên address tương ứng; với Classic, cách map destination và phiên bản STOMP cần kiểm tra riêng. Dùng sai prefix có thể khiến subscribe không tới topic mong muốn.
- Thư viện STOMP **không được đảm bảo hoạt động** chỉ vì URI wss tồn tại; endpoint phải hỗ trợ WebSocket và subprotocol STOMP, authentication và destination đúng.
- **frame.ack()** xác nhận message theo chế độ STOMP đã yêu cầu; nó không tự xác nhận database đã commit. Cơ chế retry/redelivery phụ thuộc broker và chế độ subscription.

Trong ứng dụng thực tế, nếu browser chỉ cần tiến độ thanh toán của người dùng, một **backend gateway** nhận event từ broker và đẩy thông báo qua WSS có thể an toàn và dễ kiểm soát quyền hơn việc cho mọi browser kết nối trực tiếp tới broker.

### 5.5. WebSocket qua proxy: những điểm cần giữ

Một reverse proxy phải chuyển tiếp đúng cơ chế **HTTP Upgrade**, giữ các header liên quan (đặc biệt **Upgrade**, **Connection**, subprotocol) và có timeout phù hợp kết nối dài. Cần xem xét:

| Vấn đề | Hậu quả quan sát |
|---|---|
| Proxy không hỗ trợ/không chuyển Upgrade | HTTP 400/404/426 hoặc không nhận **101** |
| TLS/certificate không hợp lệ | Browser từ chối WSS trước khi có STOMP |
| Path ở frontend khác path backend | Có thể nhận 404 dù broker vẫn sống |
| Idle timeout quá ngắn | WebSocket rớt định kỳ khi không có message |
| Không có heartbeat/ping policy phù hợp | Đường đi hỏng nhưng client phát hiện chậm |
| Origin không được kiểm soát | Website khác có thể thử kết nối nếu chính sách server cho phép |
| Token không bị ràng buộc theo destination | Browser có thể subscribe dữ liệu không thuộc quyền |

**Origin không phải authentication**: chỉ dùng kiểm tra Origin để giảm rủi ro từ trang web không mong muốn; vẫn cần cơ chế xác thực và phân quyền cho người dùng/destination. Với trình duyệt, không thể tùy ý gửi mọi HTTP header khi khởi tạo WebSocket bằng WebSocket API chuẩn; chiến lược xác thực qua cookie, token, subprotocol hoặc STOMP CONNECT phải được thiết kế cùng gateway/broker.

**Heartbeat STOMP** và **WebSocket ping/pong** là các cơ chế ở tầng khác nhau. Chúng giúp phát hiện kết nối im lặng, nhưng không thay thế transaction/ack của messaging.

## 6. VM/In-VM transport: broker và client trong cùng JVM

**VM transport** ở đây có nghĩa **in-process communication**, **không phải máy ảo VMware/VirtualBox** và không phải việc hai container cùng host có thể gọi nhau không qua mạng. Client và broker phải chạy **trong cùng JVM process** khi dùng VM/In-VM của sản phẩm.

### 6.1. ActiveMQ Classic: VM transport và embedded broker

Trong Classic, URI dạng **vm://brokerName** có thể kết nối tới broker cùng JVM. Một số cấu hình Classic cho phép VM transport **tự tạo embedded broker** khi chưa có broker cùng tên; muốn tránh việc này trong test, dùng **create=false** và khởi động broker chủ động.

Ví dụ khởi động Classic broker nhúng rồi tạo kết nối VM:

~~~java
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.broker.BrokerService;
import javax.jms.Connection;
import javax.jms.Session;

public class ClassicVmExample {
    public static void main(String[] args) throws Exception {
        BrokerService broker = new BrokerService();
        broker.setBrokerName("my-embedded-broker");
        broker.setPersistent(false); // Lab: dữ liệu không được lưu bền vững.
        broker.setUseJmx(false);
        broker.start();
        broker.waitUntilStarted();

        try {
            ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(
                    "vm://my-embedded-broker?create=false");

            Connection connection = factory.createConnection();
            try {
                connection.start();
                Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
                try {
                    session.createQueue("lab.vm.commands");
                    // Tạo producer/consumer và gửi message tại đây.
                } finally {
                    session.close();
                }
            } finally {
                connection.close();
            }
        } finally {
            broker.stop();
            broker.waitUntilStopped();
        }
    }
}
~~~

Đoạn code trên là **skeleton** khởi tạo/test transport; nó không tự gửi/nhận message chỉ bằng **session.createQueue()**. Để kiểm chứng luồng đầy đủ, tạo producer, consumer trong cùng VM và gửi một text message rồi nhận lại.

**Lưu ý API:** với JMS 1.1, **javax.jms.Connection không triển khai AutoCloseable ở mọi API/version**. Vì vậy, trong ví dụ tổng quát tương thích rộng, nên dùng **try/finally + connection.close()** thay vì giả định có thể dùng try-with-resources. Nếu thư viện JMS tương ứng cung cấp AutoCloseable qua API mới, dùng cú pháp phù hợp sau khi kiểm tra version.

### 6.2. Artemis: In-VM transport khác triển khai Classic

Artemis có **In-VM transport** cho trường hợp broker được nhúng trong cùng JVM, thường dựa trên transport Core và connector/acceptor in-vm. Một URI được gặp trong ví dụ Artemis là **vm://0**, với **0** chỉ server ID trong JVM.

~~~text
# Ví dụ endpoint In-VM của Artemis; broker phải đã được khởi động
# trong cùng JVM và có acceptor/connector in-vm tương thích.
vm://0
~~~

Trong Java, khi embedded broker đã chạy và endpoint này được bật, client Artemis có thể được cấu hình:

~~~java
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory =
    new ActiveMQConnectionFactory("vm://0");

// Tạo JMSContext/Connection từ factory, gửi và nhận như với TCP.
~~~

**Khác biệt phải ghi nhớ:**

- **Classic vm://brokerName** và **Artemis vm://serverId** thuộc hai triển khai khác nhau; không dùng URI hay cách khởi động embedded broker của Classic cho Artemis.
- Artemis In-VM không biến một broker chạy ở JVM khác thành broker “local” chỉ vì cùng máy vật lý.
- In-VM cần lifecycle **khởi động broker trước, khởi tạo client sau, đóng client trước, dừng broker sau**.
- Nếu app test dùng broker in-memory/không persistent, message có thể biến mất khi process test kết thúc. **VM là cách truyền dữ liệu, không phải lời hứa durability**.

### 6.3. Khi nào VM/In-VM đáng dùng?

| Trường hợp | Phù hợp? | Vì sao |
|---|---|---|
| Unit/integration test với broker nhúng cùng process | Có | Không cần port/network bên ngoài |
| Demo API JMS nhỏ, chạy và dọn tài nguyên trong một JVM | Có | Dễ tạo môi trường biệt lập |
| Production monolith cố ý nhúng broker | Có thể, nhưng cần đánh giá kỹ | Lifecycle, storage, HA và nâng cấp gắn chặt vào ứng dụng |
| Hai Java service chạy JVM riêng trên cùng host | Không | Khác ranh giới process |
| Pod A kết nối broker container/pod B trên cùng node | Không | Cần TCP/TLS hoặc mạng được hỗ trợ |
| Test failover, firewall, TLS, broker độc lập | Không | In-VM bỏ qua các tầng đang muốn kiểm thử |

Đừng dùng toàn bộ test suite chỉ với VM/In-VM nếu production sử dụng TLS qua mạng: test VM không phát hiện lỗi truststore, SAN, firewall, proxy, TCP idle timeout hay wire protocol mismatch.

## 7. Một đoạn Java/JMS kiểm thử cùng hành vi qua các transport phù hợp

Với backend Java dùng Artemis Core, có thể dùng **cùng nghiệp vụ** để kiểm tra hai endpoint **TCP** và **TLS**; nếu broker nhúng có In-VM phù hợp, dùng cùng code để so hành vi messaging qua **vm://0**. Ví dụ dùng **JMS 2.x namespace javax.jms** và **artemis-jms-client** tương thích:

~~~java
import java.util.UUID;
import javax.jms.ConnectionFactory;
import javax.jms.DeliveryMode;
import javax.jms.JMSContext;
import javax.jms.JMSConsumer;
import javax.jms.Message;
import javax.jms.Queue;
import javax.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class TransportProbe {
    private static final String DEST = "lab.transport.commands";

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: send|receive <connection-uri>");
        }

        String user = requireEnv("MQ_USER");
        String password = requireEnv("MQ_PASSWORD");
        ConnectionFactory factory = new ActiveMQConnectionFactory(args[1]);

        try (JMSContext ctx = factory.createContext(
                 user, password, JMSContext.SESSION_TRANSACTED)) {

            Queue queue = ctx.createQueue(DEST); // Handle phía client.

            if ("send".equals(args[0])) {
                String eventId = UUID.randomUUID().toString();
                TextMessage message = ctx.createTextMessage(
                    "{\"task\":\"reindex\",\"id\":\"doc-42\"}");
                message.setStringProperty("eventId", eventId);

                ctx.createProducer()
                   .setDeliveryMode(DeliveryMode.PERSISTENT)
                   .send(queue, message);

                ctx.commit();
                System.out.println("Committed send: " + eventId);

            } else if ("receive".equals(args[0])) {
                JMSConsumer consumer = ctx.createConsumer(queue);
                try {
                    Message message = consumer.receive(5000);
                    if (message == null) {
                        System.out.println("No message received");
                        return;
                    }

                    System.out.println("Received: "
                        + message.getStringProperty("eventId"));
                    // Ứng dụng thật: commit nghiệp vụ idempotent trước.
                    ctx.commit();
                    System.out.println("Committed receive");
                } finally {
                    consumer.close();
                }

            } else {
                throw new IllegalArgumentException("Use send or receive");
            }
        }
    }

    private static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("Missing env var: " + key);
        }
        return value;
    }
}
~~~

**Yêu cầu trước khi chạy:**

- Queue **lab.transport.commands** đã được khai báo ANYCAST hoặc broker test đã được cấu hình auto-create đúng. **createQueue** trong JMS không bảo đảm queue vật lý tồn tại.
- Client **artemis-jms-client** đúng phiên bản, đúng namespace **javax.jms**. Nếu dùng Jakarta Messaging, đổi sang client và import **jakarta.jms** nhất quán.
- User được quyền gửi/nhận queue. Với **vm://0**, embedded broker đã chạy trong chính JVM của chương trình; hai lần chạy **java** riêng biệt là hai JVM, nên **không thể** coi hai tiến trình độc lập này là một phép thử In-VM kết nối chung.
- Địa chỉ kết nối và truststore của TLS được truyền từ cấu hình bí mật, không commit password vào source code hoặc argument lệnh nơi chúng có thể lộ trong process listing/log.

**Quan sát kỳ vọng:** khi TCP/TLS/VM đều đi tới **cùng queue trên cùng broker và cùng session semantics**, các message được gửi, nhận, commit và có thể redeliver theo cùng policy. Chúng khác ở cách **thiết lập kết nối, bảo vệ kênh, phạm vi truy cập và failure mode**; không nên thấy khác biệt nghiệp vụ nếu cùng cấu hình destination/ack.

### 7.1. Đừng dùng WebSocket URL với Artemis Core JMS factory

Ví dụ sau **không phải** phép thay thế tương đương:

~~~text
tcp://mq.internal:61616               ← Artemis Core JMS factory phù hợp
wss://mq.example.test/messaging        ← WebSocket client + subprotocol riêng
~~~

JMS factory của Artemis Core không tự biến thành STOMP-over-WebSocket chỉ nhờ đổi **tcp://** thành **wss://**. Nếu cần một giao thức dùng chung giữa Java backend và browser, phải chọn **client/protocol** hỗ trợ phía tương ứng, rồi xác minh mapping destination và ack. Trường hợp thường gặp: Java backend dùng **Core/TLS**, browser dùng **STOMP/WSS** qua gateway, cùng kết nối tới một topic/queue của broker đã cấu hình đúng.

## 8. So sánh vận hành: bảo mật, hiệu năng, độ tin cậy

| Tiêu chí | TCP | TLS-over-TCP | WebSocket/WSS | VM/In-VM |
|---|---|---|---|---|
| Phạm vi | Khác process/host qua mạng | Khác process/host qua mạng | Browser, proxy, client hỗ trợ WS | **Cùng JVM** |
| Mã hóa kênh | Không mặc định | Có khi cấu hình/xác minh đúng | **WSS** có; WS thường không | Không đi qua mạng, không dùng TLS theo cách TCP |
| Chứng chỉ server | Không | Có | WSS có | Không áp dụng như TCP |
| HTTP proxy / firewall web | Không tự phù hợp | Thường cần TCP pass-through hoặc proxy phù hợp | Thường thuận tiện nhờ HTTP Upgrade | Không có đường truyền mạng |
| Overhead | Thấp ở transport | TLS handshake và chi phí mã hóa | HTTP Upgrade + WS framing + có thể TLS | Thường ít overhead truyền mạng |
| Debug network | Socket/protocol logs | Thêm TLS logs/cert | Thêm HTTP 101, proxy, WS frame | Debug in-process |
| Crash broker | Socket mất, client cần reconnect | Tương tự TCP, thêm TLS handshake | WS đóng/timeout; client cần reconnect | Embedded broker cùng process có thể chết cùng app |
| Bảo đảm message delivery | Do broker/JMS policy | Không tăng tự động vì TLS | Do subprotocol và broker policy | Do broker/JMS policy |
| Tác vụ chính | Backend messaging | Backend messaging an toàn | Streaming tương tác hai chiều | Test/embedding |

**Không khẳng định một transport “luôn nhanh hơn” transport khác.** Hiệu năng phụ thuộc message size, batching, TLS cipher/hardware, persistent journal, transaction, network RTT, consumer credit/prefetch và tải broker. Với message bền vững, **I/O storage và ack/commit** có thể ảnh hưởng latency lớn hơn vài byte framing WebSocket.

### 8.1. Nên benchmark gì?

Benchmark ít nhất hai chiều:

1. **Kết nối:** thời gian bắt tay TCP, TLS, HTTP Upgrade hoặc khởi động embedded broker; tỷ lệ connect fail.
2. **Messaging:** send/commit latency p50/p95/p99, throughput message/s, kích thước payload, consumer ACK latency, redelivery.
3. **Tài nguyên:** CPU client/broker, memory, number of connections, broker disk I/O, TLS session reuse.
4. **Sự cố:** ngắt mạng, restart broker, rotate cert, idle timeout, WebSocket reconnect, queue backlog.

Ghi rõ khi benchmark có **persistent message** và **transacted session** hay không. Một benchmark gửi NON_PERSISTENT không ack không đại diện cho lệnh thanh toán cần durability.

## 9. Chẩn đoán: kết nối thành công ở tầng nào?

Một lệnh kiểm tra port hay HTTP status thường tạo cảm giác an toàn giả. Nên kiểm tra theo chuỗi sau:

~~~mermaid
flowchart TD
    A["Client không nhận message"] --> B{"Network/endpoint reachable?"}
    B -->|Không| N["DNS, port, bind, firewall"]
    B -->|Có| C{"Transport handshake OK?"}
    C -->|Không| T["TLS cert/SAN, WS Upgrade, transport mismatch"]
    C -->|Có| D{"Wire protocol và auth OK?"}
    D -->|Không| P["CORE vs OpenWire/STOMP/AMQP; credential"]
    D -->|Có| E{"Destination và ACL đúng?"}
    E -->|Không| R["Routing, queue binding, send/consume permission"]
    E -->|Có| F["Kiểm tra queue / subscription / in-flight / ack"]
~~~

### 9.1. Triệu chứng → nguyên nhân thường gặp

| Triệu chứng | Khả năng cao | Cách xác minh |
|---|---|---|
| **Connection refused** trên cổng dự kiến | Broker không nghe cổng, bind loopback, service chưa chạy | Kiểm tra listener/broker log/địa chỉ thực tế |
| **Timeout** khi connect | Firewall, route hoặc proxy không chuyển tiếp | Test network từ đúng host/container client |
| TCP test thành công, JMS handshake thất bại | Sai wire protocol hoặc server endpoint | Đối chiếu acceptor protocols, client library |
| TLS báo hostname mismatch | DNS sử dụng khác SAN của cert | Xem cert, SNI và URL client |
| TLS **wrong version number** hoặc EOF sớm | TLS client đang gặp plaintext port/proxy sai | Kiểm tra SSL enable và port/termination |
| WSS trả 400/404/426 thay vì 101 | Sai path, proxy Upgrade hoặc endpoint không hỗ trợ WS | Kiểm tra request/response HTTP và proxy config |
| WebSocket 101 nhưng STOMP báo ERROR | Subprotocol, credential hoặc destination mapping sai | Đọc STOMP CONNECTED/ERROR và log broker |
| WebSocket bị đóng sau một lúc idle | Proxy/load balancer timeout, heartbeat thiếu | Kiểm tra ping/pong, STOMP heartbeat và idle timeout |
| **vm://** không kết nối được | Broker không nằm cùng JVM, sai broker name/server ID | Kiểm tra embedded broker lifecycle |
| Connect được, gửi thành công, queue không có message | Sai routing/queue, TTL, subscription hoặc gửi tới broker khác | Đọc address/queue binding và counters |
| Consumer xử lý lặp sau reconnect | Ack/commit chưa chắc thành công trước khi mất kết nối | Kiểm tra redelivery và idempotency |

### 9.2. Ba lớp health check khác nhau

- **L1 – Transport:** socket TCP kết nối được, TLS handshake hợp lệ hoặc WS trả 101.
- **L2 – Protocol/auth:** client thực sự tạo session/connection được; STOMP CONNECTED hoặc JMS connection hợp lệ.
- **L3 – Nghiệp vụ:** gửi/nhận một message test trên destination chuyên dụng, kiểm tra ack/commit/latency.

Chỉ đạt L1 không nên báo cả hệ thống messaging đang khỏe. Đối với health check L3, tránh gửi message vào queue nghiệp vụ thực hoặc tạo backlog/alert ngoài ý muốn; dùng đích test có owner và retention rõ ràng.

## 10. Timeout, heartbeat, reconnect và kết quả commit mơ hồ

Transport ổn định hôm nay không có nghĩa ứng dụng sẽ tự phục hồi khi broker restart ngày mai.

### 10.1. Những loại thời gian chờ phải phân biệt

- **Connection timeout:** thời gian mở socket hoặc bắt tay.
- **Read/inactivity timeout:** thời gian không nhận dữ liệu, thường liên quan heartbeat ở tầng protocol.
- **TLS handshake timeout:** giới hạn thời gian đàm phán bảo mật.
- **WebSocket idle/proxy timeout:** proxy đóng khi không có traffic hoặc heartbeat phù hợp.
- **JMS receive timeout:** thời gian chờ một message, **không phải** thời gian kết nối còn sống.
- **Application processing timeout:** thời gian xử lý nghiệp vụ downstream; không được nhầm với mất kết nối broker.

Một consumer có thể **receive timeout** vì queue trống trong khi kết nối hoàn toàn khỏe. Ngược lại, socket có thể còn hiển thị tồn tại nhưng broker đã chuyển vai trò và client cần cơ chế phát hiện inactivity.

### 10.2. Reconnect không thay thế idempotency

Giả sử producer gửi một persistent message, broker đã commit nhưng TCP/TLS/WS đứt trước khi client nhận phản hồi. Producer có thể nhìn thấy timeout nhưng không biết broker đã lưu message hay chưa. Nếu retry một message mới, consumer có thể nhận hai message có cùng hiệu ứng nghiệp vụ.

Áp dụng:

- **eventId/commandId** ổn định qua các lần retry, không phát sinh ID mới cho cùng một yêu cầu nghiệp vụ.
- **Outbox** nếu cần đồng bộ transaction database với việc phát message.
- **Consumer idempotent** theo business key bằng unique constraint hoặc inbox.
- **Retry có giới hạn** và quan sát được.
- Client failover/reconnect **đúng với sản phẩm và protocol**. URI **failover:(...)** của Classic không thể sao chép nguyên sang Artemis rồi coi hành vi giống nhau.

### 10.3. TLS và WebSocket khi HA/failover

Nếu client kết nối broker qua **DNS/load balancer**, cần xác định ai chuyển tuyến khi node active chết, và endpoint mới có chứng chỉ hợp lệ cho hostname được dùng. Với WebSocket, proxy có thể giữ một socket cũ đã chết hoặc định tuyến reconnect sang node chưa có subscription; cần thử qua failure injection, không chỉ xem L4/L7 health endpoint.

Với In-VM, broker và ứng dụng thường cùng vòng đời process; **không có network failover** theo nghĩa hai broker độc lập. Nếu mục tiêu là kiểm thử HA, dùng TCP/TLS ở topology tương ứng.

## 11. Bài thực hành so sánh bốn transport có kiểm chứng

Sử dụng **broker lab** tách khỏi production. Chuẩn bị một queue ANYCAST **lab.transport.commands** và một topic/multicast address **lab.transport.events**, với permission gửi/nhận phù hợp. Giữ **payload và chính sách ack/transaction giống nhau** giữa các phép thử có thể so sánh.

### Lab A — TCP: phân biệt reachability và protocol

1. Chạy Artemis acceptor **CORE** trên một cổng TCP test.
2. Dùng **TransportProbe** ở mục 7 để send và receive qua **tcp://host:port**.
3. Ghi lại queue count trước/sau send, receive, commit.
4. Dùng một client cấu hình sai protocol hoặc port vào endpoint test để quan sát lỗi handshake.
5. Giải thích tại sao “TCP port mở” không chứng minh “JMS gửi được”.

**Đạt:** có log connect/send/commit/receive và chỉ ra được lỗi ở network, protocol hay queue.

### Lab B — TLS: chứng minh có xác minh danh tính

1. Tạo certificate với SAN khớp hostname test, cấu hình keystore server và CA/truststore client.
2. Mở Artemis TLS acceptor riêng, kết nối bằng URI/client TLS phù hợp.
3. Chạy send và receive, ghi latency so với TCP trên cùng cấu hình broker.
4. Thử **sai CA**, **sai hostname**, **TLS vào cổng plaintext** và kiểm tra tất cả thất bại theo kỳ vọng.
5. Nếu dùng mTLS, thử client không có certificate và một client certificate được tin cậy nhưng **không có quyền send**.

**Đạt:** phân biệt được **TLS handshake thành công**, **JMS login thành công** và **authorization thành công** bằng ba phép thử khác nhau.

### Lab C — WebSocket/WSS: kiểm tra toàn bộ HTTP Upgrade + STOMP

1. Cấu hình Classic WebSocket transport hoặc Artemis acceptor được xác nhận hỗ trợ WebSocket + STOMP.
2. Nếu đi qua reverse proxy, bật WSS, chuyển tiếp Upgrade và cấu hình path đã thống nhất.
3. Kết nối bằng một STOMP-over-WebSocket client; xác minh HTTP **101**, STOMP **CONNECTED**, sau đó SEND/SUBSCRIBE/ACK.
4. Ngắt WebSocket bất ngờ và kiểm tra subscription, in-flight và redelivery theo policy.
5. Để socket rỗi vượt qua một chu kỳ heartbeat, quan sát liệu proxy giữ kết nối hay đóng.
6. Thử endpoint không hỗ trợ WebSocket để phân biệt lỗi HTTP Upgrade với lỗi STOMP.

**Đạt:** không nhầm trạng thái browser socket **OPEN** với thành công ở tầng STOMP hoặc hoàn tất nghiệp vụ.

### Lab D — VM/In-VM: kiểm tra ranh giới process

1. Khởi động embedded broker trong **cùng JVM** với client.
2. Kết nối bằng **vm://brokerName** (Classic) hoặc **vm://serverId** (Artemis) phù hợp.
3. Gửi/nhận một text message và ack/commit.
4. Dừng embedded broker, xác minh client không thể tiếp tục trao đổi như trước.
5. Cố kết nối từ **JVM khác** chỉ bằng URI VM và chứng minh đó không phải transport liên tiến trình.

**Đạt:** giải thích được vì sao VM transport tiện cho integration test nhưng không thay thế test network/TLS hoặc broker tách process.

### Bảng ghi kết quả lab

| Phép thử | Kết nối | Protocol handshake | Send/commit | Receive/ack | Failure injection |
|---|---|---|---|---|---|
| TCP + Core | TCP socket | Artemis Core | Theo queue test | Theo consumer test | Sai port/protocol |
| TLS + Core | TLS + cert | Artemis Core | Cùng semantics TCP | Cùng semantics TCP | Sai CA/SAN |
| WSS + STOMP | HTTP 101 + TLS | STOMP CONNECTED | STOMP SEND | STOMP SUBSCRIBE/ACK | Proxy timeout/auth |
| In-VM + Core | Nội bộ JVM | Core/In-VM | Cùng semantics broker | Cùng semantics broker | Broker stop/sai JVM |

## 12. Các sai lầm kiến trúc thường gặp

1. **Đổi tcp:// thành ssl:// hoặc wss:// để “bật mã hóa”.** Client, endpoint và protocol phải được cấu hình hỗ trợ TLS hoặc WebSocket tương ứng. Đổi chuỗi URI không làm listener chuyển chế độ.
2. **Mở TLS nhưng bỏ xác minh hostname/certificate.** Khi đó có mã hóa nhưng tính xác thực server không được bảo đảm như kỳ vọng.
3. **Xem WSS là một protocol messaging.** WSS chỉ bảo vệ WebSocket; vẫn cần STOMP/AMQP/MQTT hoặc subprotocol thực sự được hỗ trợ.
4. **Dùng OpenWire, Core và STOMP như thể giống nhau.** Cùng là message broker nhưng frame, tính năng và mapping destination khác; test phải dùng đúng client.
5. **Dùng VM transport giữa hai process riêng.** VM/In-VM hoạt động trong cùng JVM, không dựa trên việc hai chương trình chạy cùng host.
6. **Dựa vào test VM để kết luận production TLS sẽ chạy.** Test VM bỏ qua firewall, DNS, proxy, chứng chỉ và lỗi kết nối thật.
7. **Exposing broker trực tiếp cho mọi browser với tài khoản dùng chung.** Việc WSS được mã hóa không bảo vệ quyền truy cập sai; cần token ngắn hạn, scope và backend gateway khi phù hợp.
8. **Nhìn TCP connect thành công rồi kết luận queue đã sẵn sàng.** Vẫn cần protocol/auth, destination binding, ACL và consumer.
9. **Xem reconnect là bảo đảm exactly-once.** Trong cửa sổ mất kết nối khi commit, kết quả có thể mơ hồ; ứng dụng phải idempotent.
10. **Tắt heartbeat vì kết nối WebSocket “vẫn xanh”.** Proxy/load balancer có thể đóng idle connection, còn lỗi half-open cần phương thức phát hiện phù hợp.

## 13. Checklist trước khi chọn transport cho một dịch vụ

- [ ] Xác nhận **Classic hay Artemis**, phiên bản broker và client, wire protocol được bật ở endpoint.
- [ ] Xác định client chạy **trình duyệt, backend process riêng hay cùng JVM** với broker.
- [ ] Chọn TCP, TLS, WS/WSS hoặc VM/In-VM theo ranh giới mạng và yêu cầu bảo mật; ghi rõ vì sao chọn.
- [ ] Có sơ đồ endpoint, bind interface, port, proxy/LB, protocol và destination mapping.
- [ ] Với TLS/WSS: xác minh CA, SAN, hostname, mTLS nếu cần và quy trình certificate rotation.
- [ ] Với WebSocket: kiểm tra HTTP Upgrade 101, subprotocol negotiation, login, Origin, heartbeat và proxy timeout.
- [ ] Với VM/In-VM: kiểm tra broker thật sự cùng JVM, lifecycle khởi động/đóng và chế độ persistence.
- [ ] Broker cho đúng quyền send/consume, không cấp credential quản trị cho client thường hoặc browser.
- [ ] Kiểm thử **transport handshake → protocol/auth → send/receive/ack** thành các bước riêng.
- [ ] Kiểm tra behavior khi cắt mạng/stop broker, reconnect, kết quả commit mơ hồ và consumer redelivery.
- [ ] Ghi các chỉ số connect failure, TLS failure, WS disconnect, queue age, in-flight và ACK latency.
- [ ] Tối thiểu một bài integration test dùng **đúng transport production**; không chỉ test embedded VM.

**Ghi nhớ:** TCP là nền tảng mạng, TLS bảo vệ kênh, WebSocket mở đường cho client/proxy HTTP và VM/In-VM phục vụ trao đổi **trong một JVM**. Cả bốn chỉ xác định **cách message đi tới broker**; độ bền, routing, transaction, redelivery và DLQ vẫn do broker cùng ứng dụng Java/JMS quyết định. Chọn đúng transport bằng cách xác minh **ranh giới process, wire protocol, danh tính kết nối và kịch bản lỗi** của hệ thống thực tế.
