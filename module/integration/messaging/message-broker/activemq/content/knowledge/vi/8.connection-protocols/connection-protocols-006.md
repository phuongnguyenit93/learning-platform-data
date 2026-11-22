# Transport connector của Classic và acceptor, connector của Artemis

> **Chương:** Giao thức kết nối  
> **Phạm vi:** Apache ActiveMQ Classic và Apache Artemis trong hệ thống Java/JMS truyền thông điệp bất đồng bộ qua queue/topic. Trọng tâm là **endpoint mạng và chiều tạo kết nối**: Classic `transportConnector`, Artemis `acceptor` và `connector`. Bài không thay thế phần cấu hình queue, redelivery, DLQ hoặc hướng dẫn dựng môi trường tổng quát.

## 1. Phân biệt ba khái niệm trong một phút

Từ *connector* xuất hiện ở cả hai broker nhưng **không chỉ cùng một vai trò**. Khi đọc một cấu hình, cần xác định thành phần đang **mở cổng để nhận kết nối** hay chỉ **mô tả địa chỉ cần kết nối đi**.

| Thành phần | Định nghĩa ở đâu | Chiều kết nối | Việc nó thực hiện |
|---|---|---|---|
| **Classic `transportConnector`** | `<transportConnectors>` trong `conf/activemq.xml` | **Inbound**: socket của broker chờ client/broker khác kết nối | Bind/listen trên URI, ví dụ `tcp://0.0.0.0:61616`, nhận OpenWire hoặc giao thức khác tùy transport |
| **Classic `networkConnector`** | `<networkConnectors>` trong cấu hình broker | **Outbound** tới broker khác | Tạo network bridge theo `static:`/discovery; đây mới là khái niệm gần với “kết nối từ broker A sang broker B” |
| **Artemis `acceptor`** | `<acceptors>` trong `etc/broker.xml` | **Inbound**: socket của broker chờ kết nối | Bind/listen trên Netty TCP hoặc in-VM; một acceptor TCP có thể nhận nhiều wire protocol |
| **Artemis `connector`** | `<connectors>` trong `etc/broker.xml` | **Outbound**: mô tả cách liên hệ tới endpoint khác | Là một transport endpoint được tham chiếu bởi cluster connection, bridge, HA hoặc thành phần khác |

Sơ đồ hai node Artemis:

```text
Java/JMS client ──TCP(Core)──▶ [acceptor 61616] ARTEMIS A
                                           │
                  <connector name="peer-b">│  (địa chỉ outbound)
                                           ▼
                                   [acceptor 61616] ARTEMIS B
```

Trong sơ đồ, khai báo `<connector name="peer-b">` **chưa đủ để tự tạo kết nối**. Cần một cơ chế như `cluster-connection` hoặc core bridge tham chiếu tên connector. Ngược lại, `acceptor` sau khi broker khởi động thành công đã tạo listener tương ứng, dù chưa có client nào đến.

### Ba tầng phải cùng đúng

1. **Transport:** TCP, TLS trên TCP, in-VM… quyết định kết nối vật lý và mã hóa.
2. **Wire protocol:** Classic OpenWire, Artemis Core, AMQP 1.0, STOMP hoặc MQTT. Cùng TCP/61616 **không** có nghĩa cùng protocol.
3. **JMS provider phía Java:** `org.apache.activemq.ActiveMQConnectionFactory` của Classic nói OpenWire; `org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory` của Artemis nói Core. Hai class có thể đều triển khai `jakarta.jms.ConnectionFactory`, nhưng không vì thế mà truyền cùng loại gói tin.

JMS là API ứng dụng; `tcp://host:port` là địa chỉ transport; điều kiện tương thích nằm ở cả **provider** và **protocol mà listener chấp nhận**.

## 2. Classic: khai báo `transportConnector` để mở listener

Classic đọc danh sách listener từ phần `<transportConnectors>` bên trong `<broker>` của file `activemq.xml`. Ví dụ các phần tử cần **tích hợp vào file cấu hình hoàn chỉnh đang sử dụng**:

```xml
<transportConnectors>
    <!-- OpenWire: ActiveMQ Classic Java client -->
    <transportConnector name="openwire"
                        uri="tcp://0.0.0.0:61616"/>

    <!-- AMQP 1.0: ví dụ Apache Qpid JMS -->
    <transportConnector name="amqp"
                        uri="amqp://0.0.0.0:5672"/>

    <!-- STOMP: ví dụ ứng dụng dùng STOMP client -->
    <transportConnector name="stomp"
                        uri="stomp://0.0.0.0:61613"/>
</transportConnectors>
```

Ý nghĩa từng phần:

- `name` định danh transport connector để quản trị và nhận diện log. Nó **không** phải tên queue/topic.
- `uri` quyết định giao thức transport và địa chỉ mà socket **bind**. `0.0.0.0` nghĩa là nhận trên tất cả interface IPv4 của host/container; không phải địa chỉ mà client ở máy khác được phép dùng để kết nối.
- `tcp://...` trong cấu hình Classic là listener OpenWire điển hình; AMQP, STOMP, MQTT cần transport/connector thích hợp, trừ khi sử dụng cơ chế `AUTO`.
- Mỗi listener TCP cần một tổ hợp địa chỉ/port khả dụng. Không tạo hai listener độc lập cùng bind `0.0.0.0:61616` trên cùng host.

Nếu chỉ cần một listener cho toàn bộ client OpenWire, hãy **bỏ bớt connector không dùng**, giảm số cổng phải mở. Đối với nhiều giao thức, có thể tách cổng riêng để quan sát/bảo vệ từng nhóm hoặc bật tự nhận diện giao thức.

### Classic `tcp`, `nio`, `ssl` và `auto`

| URI ở phía Classic broker | Ý nghĩa | Điểm dễ hiểu sai |
|---|---|---|
| `tcp://0.0.0.0:61616` | TCP listener cho OpenWire | Không mã hóa dữ liệu |
| `nio://0.0.0.0:61616` | OpenWire listener dùng Java NIO phía broker | Client OpenWire thường vẫn sử dụng `tcp://hostname:61616`; `nio` chủ yếu là triển khai transport phía server |
| `ssl://0.0.0.0:61617` | OpenWire qua TLS | Cần SSL context/certificate hợp lệ và URI client tương ứng |
| `nio+ssl://0.0.0.0:61617` | Listener NIO kết hợp TLS | Là lựa chọn server-side; không suy rằng client bắt buộc dùng `nio+ssl` |
| `auto://0.0.0.0:61616` | Tự nhận diện OpenWire, STOMP, AMQP, MQTT trên cùng cổng | Cơ chế AUTO của Classic, không phải Artemis Core |
| `auto+ssl://0.0.0.0:61617` | AUTO trên TLS | Vẫn yêu cầu chứng chỉ, kiểm tra TLS và xác thực broker |
| `auto+nio://0.0.0.0:61616` | AUTO dùng NIO | Xác minh phiên bản Classic; AUTO xuất hiện từ 5.13.0 |

**Ví dụ thay OpenWire-only bằng AUTO:** chỉ dùng **một trong hai** listener dưới đây ở cùng cổng:

```xml
<!-- Phương án 1: chỉ OpenWire -->
<transportConnector name="openwire" uri="tcp://0.0.0.0:61616"/>

<!-- Phương án 2: thay thế listener trên bằng AUTO,
     không đặt cả hai cùng cổng 61616 -->
<transportConnector name="multi-protocol" uri="auto://0.0.0.0:61616"/>
```

Classic `AUTO` phát hiện một trong các wire protocol mà cơ chế đó hỗ trợ. Không nên coi nó tương đương Artemis `CORE`: một Artemis Core client không tự nhiên kết nối được với Classic AUTO listener.

### Các tham số URI và ký tự XML

Nếu một transport URI có nhiều option tách bằng `&`, cần **escape XML thành `&amp;`**. Ví dụ dưới đây dùng hai tham số thường gặp của OpenWire:

```xml
<transportConnector
    name="openwire-limited"
    uri="tcp://0.0.0.0:61616?wireFormat.maxFrameSize=10485760&amp;transport.soTimeout=30000"/>
```

`wireFormat.maxFrameSize` hạn chế kích thước frame OpenWire; giá trị có thể phải đồng bộ với client và chính sách xử lý message lớn. `transport.soTimeout` là một timeout socket, **không** thay thế các timeout xác thực, inactivity monitor hoặc chính sách tài nguyên của broker. Chỉ cấu hình option thực sự cần thiết và được tài liệu phiên bản đang chạy hỗ trợ.

### `networkConnector` của Classic không phải `transportConnector`

Một broker Classic A muốn tạo network bridge đi tới broker Classic B cần **cấu hình outbound riêng**, ví dụ:

```xml
<!-- Đặt trong <broker> của Classic A; không đặt ở <transportConnectors>. -->
<networkConnectors>
    <networkConnector
        name="to-classic-b"
        uri="static:(tcp://classic-b.internal:61616)"
        duplex="false"/>
</networkConnectors>
```

Broker B phải có `transportConnector` inbound lắng nghe ở cổng/địa chỉ đó; cấu hình network connector trên A không mở listener tại B. Network bridge có quy tắc forward message, subscriptions, TTL và reconnect riêng; **chỉ kết nối được TCP chưa chứng minh message đã đi đúng chiều**. Nếu dùng topology nhiều broker, cần kiểm thử thêm duplicate, loop và consumers qua bridge.

## 3. Artemis: `acceptor` để nhận, `connector` để đi

Artemis đặt cấu hình trong `etc/broker.xml`. Acceptor thường dùng Netty TCP, còn connector định nghĩa endpoint phía đích để một thành phần broker tham chiếu.

### 3.1. Acceptor: bind socket và chọn protocol

Ví dụ với **một cổng đa giao thức**:

```xml
<!-- Các phần tử con nằm bên trong <core> của broker.xml. -->
<acceptors>
    <acceptor name="client-port">tcp://0.0.0.0:61616?protocols=CORE,OPENWIRE,AMQP;connectionsAllowed=500</acceptor>
</acceptors>
```

Listener này:

- Bind TCP ở `0.0.0.0:61616`, nên client bên ngoài container có thể kết nối qua IP/DNS và port đã được publish/firewall cho phép.
- Chấp nhận **Core**, **OpenWire** và **AMQP 1.0** trên cùng cổng. Broker dùng dữ liệu handshake để phân biệt handler thích hợp.
- Giới hạn tối đa `500` connection tại acceptor qua `connectionsAllowed`. Khi đạt giới hạn, broker có thể từ chối kết nối mới; timeout/lỗi phía client tùy provider.
- **Không** mở STOMP/MQTT trên listener này vì không có trong `protocols`.

Trong Artemis, nếu **bỏ tham số `protocols`**, acceptor mặc định hỗ trợ các giao thức được bản broker cung cấp. Vì vậy cấu hình explicit allowlist là cách làm rõ mục đích, đặc biệt khi cổng dành riêng cho một nhóm ứng dụng.

**Ví dụ tách cổng theo vai trò:**

```xml
<acceptors>
    <acceptor name="core-only">tcp://0.0.0.0:61616?protocols=CORE</acceptor>
    <acceptor name="openwire-only">tcp://0.0.0.0:61617?protocols=OPENWIRE</acceptor>
    <acceptor name="amqp-only">tcp://0.0.0.0:5672?protocols=AMQP</acceptor>
</acceptors>
```

Mỗi acceptor là một listener riêng. Khi đổi từ cấu hình multi-protocol sang các cổng riêng, cần đổi **URI của ứng dụng** và các rule firewall/network policy; không thể chỉ thêm `protocols=AMQP` mà mong ứng dụng tự chuyển cổng.

### 3.2. Connector: endpoint có thể đi tới, không tự bind cổng

```xml
<connectors>
    <!-- Địa chỉ có thể quảng bá của chính node A cho các thành viên khác -->
    <connector name="node-a">tcp://artemis-a.internal:61616</connector>

    <!-- Endpoint phía node B mà node A cần liên hệ -->
    <connector name="node-b">tcp://artemis-b.internal:61616</connector>
</connectors>
```

Artemis dùng connector trong các tình huống như cluster connection, core bridge và một số cấu hình HA. **Chỉ khai báo hai `<connector>` chưa mở socket, chưa làm hai broker thành cluster, và chưa định tuyến bất kỳ queue nào.** Endpoint đích phải có acceptor tương ứng đang lắng nghe, DNS/đường mạng hoạt động, và security credentials phù hợp.

**Ví dụ tham chiếu connector trong cluster connection** (chỉ là phần cấu hình tối thiểu; cần hoàn thiện cluster security và cấu hình hai phía):

```xml
<cluster-connections>
    <cluster-connection name="orders-cluster">
        <address>orders.</address>
        <connector-ref>node-a</connector-ref>
        <retry-interval>1000</retry-interval>
        <message-load-balancing>ON_DEMAND</message-load-balancing>
        <max-hops>1</max-hops>
        <static-connectors>
            <connector-ref>node-b</connector-ref>
        </static-connectors>
    </cluster-connection>
</cluster-connections>
```

Ở đây `node-a` là connector đại diện địa chỉ của node hiện tại để công bố trong topology; `node-b` là thành viên ban đầu cần liên hệ. Để cấu hình thực sự hoạt động, **node B phải có broker riêng, acceptor phù hợp và cluster credentials tương thích**; có thể phải cấu hình chiều ngược lại theo topology. `<address>orders.</address>` là tiền tố address mà cluster connection quan tâm, không phải nơi khai báo một queue JMS.

Một connector được dùng cho **cluster Core** không phải công cụ chung để nối Artemis sang Classic chỉ vì Classic có port TCP. Hai sản phẩm chỉ liên thông khi cả hai bên sử dụng protocol/cơ chế bridge phù hợp (ví dụ OpenWire clients hoặc AMQP bridge với provider đúng), và cần kiểm chứng routing/message semantics riêng.

### 3.3. Không cần `<connector>` trên broker để một Java client bình thường kết nối

Ứng dụng JMS sử dụng Artemis client có thể khai báo URI trực tiếp:

```java
import jakarta.jms.ConnectionFactory;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

ConnectionFactory cf =
    new ActiveMQConnectionFactory("tcp://artemis-a.internal:61616");
```

Factory phía Java tự tạo client-side connector/transport cần thiết từ URI. Không cần thêm `<connector name="java-app">` vào `broker.xml` để đăng ký từng ứng dụng producer/consumer. Đó là điểm quan trọng giúp tránh làm phình cấu hình Artemis khi thêm microservice.

## 4. Ma trận chọn endpoint theo client và broker

| Client / wire protocol | Classic `tcp://...:61616` OpenWire | Classic `auto://...` | Artemis acceptor `protocols=CORE` | Artemis acceptor `protocols=CORE,OPENWIRE,AMQP` |
|---|:---:|:---:|:---:|:---:|
| Classic `ActiveMQConnectionFactory` / OpenWire | ✓ | ✓ | ✕ | ✓ |
| Artemis `ActiveMQConnectionFactory` / Core | ✕ | ✕ | ✓ | ✓ |
| JMS provider AMQP 1.0 / AMQP | ✕ | ✓ | ✕ | ✓ |
| STOMP client / STOMP | ✕ | ✓ | ✕ | ✕ |

Ký hiệu: **✓** có đường giao thức khả thi khi broker bật protocol và cấu hình đúng; **✕** không được listener đã nêu chấp nhận. Bảng **không** tự chứng nhận authentication, TLS, transactions, durable subscription, message mapping hoặc tất cả phiên bản client. Đặc biệt, “AMQP client” phải nói **AMQP 1.0** nếu kết nối broker theo ví dụ.

Ví dụ, một ứng dụng Java 17 dùng `jakarta.jms` vẫn có thể:

- Kết nối Classic 6.x qua **Classic OpenWire client** với URI `tcp://classic:61616`.
- Kết nối Artemis qua **Artemis Core client** với URI `tcp://artemis:61616`.
- Kết nối một acceptor Artemis bật `OPENWIRE` bằng **Classic OpenWire client** nếu tổ hợp phiên bản và chức năng đã được thử nghiệm.

Thay đổi URI mà **không đổi JMS provider** chỉ đổi vị trí đích; nó không dịch Core thành OpenWire. Một lỗi “port mở mà vẫn không kết nối được” thường bắt nguồn từ chỗ này.

### Ghi nhớ protocol và port

| Port ví dụ | Classic thường dùng | Artemis thường dùng | Điều cần xác minh |
|---|---|---|---|
| `61616` | OpenWire qua `tcp`, hoặc AUTO nếu cấu hình | Core/multi-protocol Netty | Listener thực tế có nhận protocol của client? |
| `61617` | Có thể là TLS hoặc connector bổ sung | Có thể là acceptor OpenWire hoặc TLS | Không suy đoán từ số port |
| `5672` | AMQP connector | AMQP acceptor | Có mở AMQP 1.0? TLS có bật? |
| `61613` | STOMP connector | STOMP acceptor (nếu cấu hình) | STOMP client và frame encoding đúng? |
| `1883` | MQTT connector | MQTT acceptor (nếu cấu hình) | Không nhầm MQTT với JMS |

Các số cổng là **quy ước thường gặp**, không được JMS hay tên broker bảo đảm. Cấu hình chạy thực tế mới quyết định service đang nghe ở đâu.

## 5. Bind address, địa chỉ mà client nhìn thấy và môi trường container

Phải phân biệt địa chỉ **bind/listen** với địa chỉ **được client hoặc broker khác sử dụng để kết nối**.

| Chuỗi | Ý nghĩa đúng | Không nên dùng cho |
|---|---|---|
| `0.0.0.0:61616` ở acceptor/transportConnector | Bind mọi IPv4 interface của container/host | URI đích trong ứng dụng chạy từ máy khác |
| `127.0.0.1:61616` | Chỉ loopback của **network namespace hiện tại** | Kết nối từ container/host khác nếu chưa publish/forward |
| `broker:61616` | DNS service/container trong cùng mạng Docker Compose | Client bên ngoài Docker nếu không có DNS phù hợp |
| `broker.company.internal:61616` | DNS reachable trong mạng triển khai | Bind trong container nếu hostname không thuộc interface của container |
| `localhost:61616` trong Java chạy ở host | Cổng host đã publish về broker | Java chạy trong một container khác vì `localhost` trỏ vào **chính container Java** |

Ví dụ Compose publish port chỉ lên máy phát triển:

```yaml
services:
  broker:
    # image và volumes cần cấu hình riêng
    ports:
      - "127.0.0.1:61616:61616"
```

Phía trong container broker vẫn phải bind listener trên interface thích hợp, thường `0.0.0.0:61616`. Java chạy trên host dùng `tcp://127.0.0.1:61616`, Java ở container khác dùng `tcp://broker:61616` qua mạng Docker. Bind host là `127.0.0.1` **chưa** có nghĩa traffic giữa container trong cùng network tự động bị chặn; phải cấu hình authentication và quyền broker.

### Vì sao địa chỉ Artemis `connector` không nên là `0.0.0.0`?

Acceptor dùng `0.0.0.0` để **lắng nghe**. Connector của node A được cluster/bridge dùng như địa chỉ **có thể đi tới**. Nếu ghi:

```xml
<!-- KHÔNG dùng làm địa chỉ quảng bá cho node khác -->
<connector name="node-a">tcp://0.0.0.0:61616</connector>
```

node B sẽ không có một địa chỉ ổn định để liên hệ với node A. Thay bằng DNS/IP mà B truy cập được như `tcp://artemis-a.internal:61616`. Đối với Kubernetes, cần xem service DNS, headless service, NAT, topology updates và pod lifecycle; không suy rằng hostname trong container tự động có thể truy cập từ mọi node.

Với Classic, `transportConnector` cũng là **địa chỉ bind**; khi dùng failover/topology updates, cần xác nhận broker công bố địa chỉ phù hợp với mạng client. Dùng cấu hình công bố/advertise do phiên bản hỗ trợ và kiểm tra từ môi trường client thực tế, đặc biệt khi có NAT hoặc reverse proxy.

## 6. Bảo mật transport: TLS và xác thực là hai việc riêng

Một client kết nối thành công qua TLS chưa chắc được quyền gửi message. Ngược lại, một client có username/password đúng nhưng truyền qua `tcp://` plaintext có thể làm lộ credentials và payload nếu đi qua mạng không tin cậy.

| Lớp | Classic | Artemis | Cách xác minh |
|---|---|---|---|
| Mã hóa kênh | `ssl://`, `nio+ssl://` hoặc `auto+ssl://` với SSL context | `sslEnabled=true` trên acceptor Netty và client transport tương ứng | TLS handshake, certificate chain, hostname verification |
| Xác thực client | `simpleAuthenticationPlugin`, JAAS hoặc cơ chế đã chọn | Security manager/JAAS, user/role; có thể mTLS | User đúng/sai, cert đúng/sai, log broker |
| Phân quyền | Authorization plugin theo destination | `security-settings` theo address/queue | Producer/consumer không đủ quyền phải bị từ chối |
| Exposure | Bind và firewall từng connector | Bind và firewall từng acceptor | Chỉ cổng cần thiết có thể truy cập |

**Classic TLS listener, sơ lược:**

```xml
<transportConnectors>
    <!-- Yêu cầu <sslContext> hợp lệ ở broker, không chỉ đổi scheme -->
    <transportConnector name="openwire-tls"
                        uri="ssl://0.0.0.0:61617"/>
</transportConnectors>
```

**Artemis TLS acceptor, sơ lược:**

```xml
<!-- Chỉ một phần cấu hình, không thể chạy nếu thiếu keystore và password. -->
<acceptor name="core-tls">tcp://0.0.0.0:61617?protocols=CORE;sslEnabled=true;keyStorePath=/etc/broker/tls/broker.p12;keyStoreType=PKCS12</acceptor>
```

Ở Artemis, phải cấp password cho keystore **theo cơ chế secret/masked credential được bản triển khai hỗ trợ** và cấu hình truststore cho phía client. Nếu dùng mTLS, xem thêm `needClientAuth=true` trên acceptor và truststore tin cậy certificate client. Không đẩy private key, password hoặc certificate chứa thông tin nhạy cảm lên Git. Không đặt `trustAll=true` trên connector để “chữa” lỗi certificate của production; hãy sửa chain/hostname/truststore đúng.

**Cảnh báo về URL chứa tham số:** Trong XML của Artemis, một số ví dụ của tài liệu dùng dấu `;` để phân tách option Netty. Với URI dùng `&`, phải XML-escape thành `&amp;` như ở Classic. Đọc cú pháp hợp lệ của đúng broker/version; một ký tự sai có thể khiến broker không parse được listener khi startup.

## 7. Java/JMS: kiểm chứng cùng một tên queue qua hai transport khác nhau

Để kiểm tra **transport**, hãy dùng một chương trình gửi và nhận message có mã định danh ngẫu nhiên trên một queue lab, chạy với **một provider tương ứng broker mỗi lần**. Không dùng việc mở được TCP socket làm bằng chứng đủ cho handshake, authentication và JMS.

### 7.1. Maven dependency theo broker

Giả sử JDK 17 và ứng dụng dùng `jakarta.jms`.

**Classic 6.4.x / OpenWire**:

```xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>activemq-client</artifactId>
    <version>6.4.0</version>
</dependency>
```

**Artemis 2.57.x / Core** (đưa vào **project test Artemis riêng**, thay thế dependency provider Classic):

```xml
<dependency>
    <groupId>org.apache.artemis</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.57.0</version>
</dependency>
```

Nếu dùng Classic 5.x, `activemq-client` thông thường thuộc namespace `javax.jms`, và có artifact client Jakarta riêng ở các bản 5.18.1+/5.19.x. Đừng ghép `javax.jms` và `jakarta.jms` bằng cách ép kiểu. Các ví dụ phía dưới chỉ dùng hai dòng client **Jakarta** đã nêu.

### 7.2. Phần kiểm thử JMS dùng chung

**`TransportProbe.java`:**

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import java.util.UUID;

public final class TransportProbe {
    private TransportProbe() {}

    public static void run(ConnectionFactory factory,
                           String user, String password) {
        String marker = "probe-" + UUID.randomUUID();
        try (JMSContext context =
                 factory.createContext(user, password, JMSContext.AUTO_ACKNOWLEDGE)) {
            Queue queue = context.createQueue("lab.transport.probe");

            context.createProducer().send(queue, marker);
            String received = context.createConsumer(queue)
                .receiveBody(String.class, 5000L);

            if (!marker.equals(received)) {
                throw new IllegalStateException(
                    "No matching message; received=" + received);
            }
            System.out.println("PASS " + marker);
        }
    }
}
```

Đoạn trên chỉ sử dụng `jakarta.jms.ConnectionFactory`, vì vậy có thể tái sử dụng giữa hai ứng dụng lab với **provider khác nhau**. Queue `lab.transport.probe` phải tồn tại hoặc broker cho phép auto-create; tài khoản phải có quyền gửi và nhận. Trong môi trường có nhiều test song song, dùng queue riêng mỗi lần chạy hoặc selector/correlation ID để không đọc message của test khác.

**Main class của ứng dụng Classic** (biên dịch cùng `activemq-client:6.4.0`):

```java
import org.apache.activemq.ActiveMQConnectionFactory;

public class ProbeClassic {
    public static void main(String[] args) {
        String user = System.getenv("BROKER_USER");
        String password = System.getenv("BROKER_PASSWORD");
        if (user == null || password == null) {
            throw new IllegalStateException("Missing broker credentials");
        }

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");
        TransportProbe.run(factory, user, password);
    }
}
```

**Main class của ứng dụng Artemis** (biên dịch cùng `artemis-jakarta-client:2.57.0`):

```java
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public class ProbeArtemis {
    public static void main(String[] args) {
        String user = System.getenv("BROKER_USER");
        String password = System.getenv("BROKER_PASSWORD");
        if (user == null || password == null) {
            throw new IllegalStateException("Missing broker credentials");
        }

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");
        try {
            TransportProbe.run(factory, user, password);
        } finally {
            factory.close();
        }
    }
}
```

Trong cả hai chương trình, chuỗi URI nhìn như nhau nhưng **provider phát protocol khác nhau**. Khi Artemis acceptor chỉ cho `CORE`, chương trình Artemis thành công và chương trình Classic dùng OpenWire bị từ chối ở tầng protocol. Khi thay `protocols=CORE,OPENWIRE` và cấu hình security tương thích, có thể thử cả hai provider trên Artemis; khi đó cần kiểm tra hành vi message ngoài phép thử cơ bản trước khi tuyên bố tương thích sản xuất.

Chương trình chỉ kiểm thử **connection + send/receive + quyền cơ bản**. Nó không chứng minh transaction, XA, durable subscription, DLQ, failover, độ bền message hoặc hiệu năng. Những tính năng đó có test riêng theo mục tiêu hệ thống.

### 7.3. Test theo ma trận

| Broker/config | Test client | Kết quả dự kiến |
|---|---|---|
| Classic `tcp://127.0.0.1:61616` OpenWire | `ProbeClassic` | PASS khi user/queue hợp lệ |
| Classic chỉ OpenWire | `ProbeArtemis` Core | FAIL: protocol không phù hợp |
| Artemis `protocols=CORE` | `ProbeArtemis` | PASS khi user/queue hợp lệ |
| Artemis `protocols=CORE` | `ProbeClassic` OpenWire | FAIL: protocol bị chặn |
| Artemis `protocols=CORE,OPENWIRE` | Cả hai probe, chạy **tách biệt** | Có thể PASS cho mỗi provider; cần kiểm tra tương thích version |
| Artemis `protocols=AMQP` | Artemis Core probe | FAIL: protocol bị chặn; muốn AMQP phải đổi provider |

Không chạy các test “FAIL theo chủ đích” trên môi trường sản xuất; dùng broker lab riêng và xem log phía server để phân biệt từ chối protocol với sai credentials.

## 8. Từ “cổng mở” đến “kết nối JMS tốt”: thứ tự kiểm chứng

### 8.1. Kiểm tra listener và mạng

Trên Linux chạy broker:

```bash
# Chỉ kiểm tra tiến trình đang LISTEN; không chứng minh JMS đã hoạt động.
ss -lnt | grep -E ':61616|:61617|:5672'

# Kiểm tra TCP từ đúng nơi chạy client (nếu có nc).
nc -vz broker.example.internal 61616
```

Trên PowerShell/Windows:

```powershell
Test-NetConnection broker.example.internal -Port 61616
```

Nếu test báo không kết nối được, kiểm tra từng lớp: broker đã khởi động, listener bind đúng interface/port, container publish port nếu cần, DNS, firewall, network policy và route. Đừng sửa mật khẩu JMS khi TCP chưa thể bắt tay.

### 8.2. Kiểm tra TLS nếu listener có mã hóa

```bash
# Chỉ dùng khi cổng thực sự được cấu hình TLS.
openssl s_client -connect broker.example.internal:61617 \
  -servername broker.example.internal
```

Đối chiếu certificate chain, ngày hết hạn, SAN/hostname và truststore của Java client. `openssl s_client` không tự chứng minh chương trình Java đã trust certificate hoặc được broker cấp quyền; vẫn phải chạy probe JMS qua URI TLS thích hợp.

### 8.3. Kiểm tra startup và trạng thái protocol

Tìm trong log Classic/Artemis:

- Listener nào **started** ở địa chỉ nào; có lỗi `BindException: Address already in use` hay không.
- Acceptor Artemis có khởi động protocol manager mà bạn yêu cầu, có cảnh báo tham số không hợp lệ không.
- Thông báo “bad magic”, “invalid wire format”, “protocol not recognized”, lỗi SSL handshake hoặc bị authentication từ chối.
- Node Artemis có kết nối cluster/bridge tới connector đích chưa; chỉ thấy `<connector>` trong XML không bảo đảm link đã active.

Sau khi `nc`/`Test-NetConnection` thành công, chuyển sang Java probe để kiểm tra **wire protocol + xác thực + JMS**. Nếu fail, ghi cả log server và stack trace client cùng timestamp để tránh chẩn đoán bằng việc đoán port.

## 9. Lỗi thực tế và cách xác định nguyên nhân

| Hiện tượng | Nguyên nhân thường gặp | Cách xác minh/sửa |
|---|---|---|
| `Connection refused` ngay lập tức | Không có listener ở host/port đích; bind vào loopback sai namespace | Xem `ss`, log startup, địa chỉ bind/published port |
| Timeout khi connect | Firewall, route, DNS, pod/service endpoint, connection limit hoặc listener chưa ready | Kiểm tra từ vị trí client; đối chiếu `connectionsAllowed` và log |
| TCP mở nhưng JMS connect lỗi ngay | Client nói Core vào OpenWire, OpenWire vào CORE-only acceptor, hoặc AMQP vào cổng khác | Ghi rõ client provider và `protocols`/transport URI |
| SSL handshake failure | Client kết nối plaintext vào TLS port hoặc không trust server certificate | So URL scheme, `sslEnabled`, keystore/truststore, cert hostname |
| Auth thành công nhưng gửi queue bị từ chối | User không có quyền send/consume trên address | Kiểm tra security/authorization, không mở rộng quyền tùy tiện |
| `Address already in use` | Hai connector/acceptor đang bind cùng IP:port | Đối chiếu toàn bộ listener và cổng Docker |
| Ứng dụng trong container connect `localhost` rồi fail | `localhost` là container ứng dụng, không phải broker | Dùng DNS service hoặc địa chỉ được expose |
| Artemis cluster không lên dù có `<connectors>` | Connector chưa được tham chiếu, remote acceptor không nghe hoặc cluster credentials sai | Kiểm tra `cluster-connection`, `connector-ref`, DNS và cluster auth |
| Artemis node khác connect tới `0.0.0.0` rồi fail | Dùng bind address làm địa chỉ advertised | Sửa connector thành DNS/IP mà remote node truy cập được |
| Classic network bridge không forward message | Chỉ mở transportConnector hoặc networkConnector chưa có subscription phù hợp | Kiểm tra `networkConnectors`, bridge status, demand/filter/TTL |
| Một port nhận nhiều protocol nhưng message mapping lạ | Khác JMS provider, AMQP mapping hoặc khác tính năng giữa broker | Kiểm thử header/body, selector, topic, transaction, redelivery |

### Phân tích một ca “Classic client sang Artemis”

Giả sử:

```text
Client: org.apache.activemq.ActiveMQConnectionFactory
Client URI: tcp://artemis.internal:61616
Broker: Artemis
Acceptor: tcp://0.0.0.0:61616?protocols=CORE
TCP test: PASS
JMS test: FAIL
```

Chẩn đoán: client Classic nói **OpenWire**, nhưng acceptor chỉ bật **Core**. Cách khắc phục phụ thuộc mục tiêu:

1. Giữ Classic client: cho phép `OPENWIRE` trên acceptor Artemis và chạy test tương thích client/provider.
2. Chuyển sang Artemis Core: đổi **dependency/provider JMS** trong ứng dụng (không chỉ đổi URL) rồi kết nối acceptor bật `CORE`.

Đừng chữa lỗi bằng cách vô hiệu authentication hay dùng cổng management console `8161`. Cổng quản trị HTTP không phải JMS transport.

## 10. Checklist cấu hình trước khi bàn giao

| Câu hỏi | Classic | Artemis |
|---|---|---|
| Thành phần nhận TCP có khai báo đúng? | `transportConnector` | `acceptor` |
| Thành phần kết nối broker khác có khai báo đúng? | `networkConnector` / network bridge | `connector` được tham chiếu bởi cluster/bridge/HA |
| Bind đúng interface và port? | `uri` của transportConnector | URL của acceptor |
| URI client dùng địa chỉ có thể truy cập? | `tcp://dns:port`, `ssl://...`, failover nếu áp dụng | `tcp://dns:port` của Artemis client, TLS option nếu áp dụng |
| Protocol có khớp provider? | OpenWire hoặc AUTO/AMQP/STOMP đã bật | `protocols=CORE,OPENWIRE,AMQP,...` rõ ràng |
| TLS được cấu hình đủ? | SSL context, cert, client trust | `sslEnabled`, keystore/truststore, xác minh hostname |
| Broker-to-broker chạy thật? | Bridge active và forward đúng message | Cluster/bridge active, connector-ref hợp lệ |
| Đã test ở tầng nào? | Socket → protocol → JMS → nghiệp vụ | Socket → protocol → JMS → nghiệp vụ |

**Tiêu chí nghiệm thu thực hành:** tạo được một Classic transportConnector hoặc Artemis acceptor theo đúng URI; Java client đúng provider gửi/nhận một message lab; thử một trường hợp cố ý sai protocol để thấy nguyên nhân; kiểm tra connector outbound Artemis chỉ có hiệu lực khi được tham chiếu; ghi lại bind address, endpoint mà client truy cập, wire protocol, TLS và log có dấu thời gian. Không đánh dấu PASS chỉ vì `telnet` hoặc `nc` mở được socket.

## Tài liệu chính thức đối chiếu

1. [ActiveMQ Classic — Configuring Transports](https://activemq.apache.org/components/classic/documentation/configuring-transports): `transportConnector`, URI TCP/NIO/SSL và server-side options.
2. [ActiveMQ Classic — AUTO Transport](https://activemq.apache.org/components/classic/documentation/auto): cơ chế tự phát hiện OpenWire, STOMP, AMQP, MQTT.
3. [ActiveMQ Classic — Networks of Brokers](https://activemq.apache.org/components/classic/documentation/networks-of-brokers): `networkConnector`, `static:`, bridge và outbound routing.
4. [Apache Artemis — Configuring the Transport](https://artemis.apache.org/components/artemis/documentation/latest/configuring-transports.html): `acceptors`, `connectors`, Netty TCP, TLS và các tham số.
5. [Apache Artemis — Protocols and Interoperability](https://artemis.apache.org/components/artemis/documentation/latest/protocols-interoperability.html): multi-protocol acceptor và các tên protocol `CORE`/`OPENWIRE`/`AMQP`/`STOMP`/`MQTT`.
6. [Apache Artemis — Clusters](https://artemis.apache.org/components/artemis/documentation/latest/clusters.html): `connector-ref`, `static-connectors`, cluster connection và topology.
