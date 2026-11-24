# UDP message header và địa chỉ nguồn trong Spring Integration

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **payload UDP**, **địa chỉ/cổng nguồn ở tầng mạng** và **header của Spring Integration `Message`**.
- Đọc đúng các header `ip_address`, `ip_port`, `ip_hostname` và `ip_packetAddress` từ một UDP inbound message.
- Dùng `IpHeaders` thay vì viết rải rác tên header dạng chuỗi; hiểu ý nghĩa, kiểu dữ liệu và sự khác nhau giữa header UDP với TCP.
- Cấu hình adapter nhận UDP, kiểm tra địa chỉ nguồn trong service activator và thử bằng một client thật.
- Biết khi nào có thể dùng `ip_packetAddress` để **gửi datagram phản hồi tới sender** qua outbound adapter.
- Phân tích ảnh hưởng của NAT, DNS, việc giả mạo IP, giới hạn datagram và vòng đời socket đối với cách sử dụng địa chỉ nguồn.

Bài thuộc chương **Adapter UDP** của module **SPRING_INTEGRATION_ADAPTERS**. Module này tập trung vào cách kết nối hệ thống bên ngoài vào Spring Integration bằng inbound/outbound adapter, gateway, poller và `MessageChannel`, áp dụng cho file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. **UDP message header và địa chỉ nguồn** là một phần quan trọng của *hợp đồng message*: handler nhận được cả dữ liệu nghiệp vụ lẫn một số thông tin về datagram đã đi vào hệ thống.

## 1. Bài toán: dữ liệu giống nhau từ nhiều thiết bị

Một collector mở cổng UDP `12004` để nhận telemetry:

~~~text
sensor=node-7;tempC=26.5
~~~

Có thể có hai sender cùng gửi nội dung đó:

- Thiết bị A gửi từ `192.0.2.31:51234`.
- Thiết bị B gửi từ `192.0.2.32:60127`.

Nếu handler chỉ đọc chuỗi payload, hai datagram trông giống nhau. Nhưng adapter UDP biết **địa chỉ nguồn mà socket nhận được** và có thể bổ sung thông tin này vào **message headers** để handler chẩn đoán, ghi metric, áp dụng kiểm soát mạng hoặc định tuyến phản hồi.

~~~mermaid
flowchart LR
    A["Thiết bị A\n192.0.2.31:51234"] -->|"UDP: sensor=node-7..."| S["UDP inbound socket\n:12004"]
    B["Thiết bị B\n192.0.2.32:60127"] -->|"UDP: sensor=node-7..."| S
    S --> M["DatagramPacketMessageMapper"]
    M --> I["Spring Integration Message\npayload = byte[]\nheaders = ip_address / ip_port / ip_packetAddress"]
    I --> C["MessageChannel"]
    C --> H["Validate / Service Activator"]
~~~

**Điểm cần nhớ:** thông tin nguồn trong header do bộ nhận suy ra từ datagram/socket. Sender **không gửi một JSON header tên `ip_address`** theo mặc định, và địa chỉ nguồn của datagram không chứng minh được danh tính nghiệp vụ của thiết bị.

Các địa chỉ `192.0.2.x` trong bài là địa chỉ minh họa thuộc dải dùng cho tài liệu. Khi thử thực tế, sử dụng địa chỉ của môi trường triển khai hoặc `127.0.0.1`.

## 2. Ba lớp dữ liệu không nên nhầm lẫn

| Khái niệm | Ví dụ | Sinh ra ở đâu? | Ý nghĩa |
|---|---|---|---|
| **UDP payload** | Byte UTF-8 của `sensor=node-7;tempC=26.5` | Ứng dụng sender | Dữ liệu mà hai bên thống nhất truyền. |
| **UDP/IP endpoint nguồn** | `192.0.2.31:51234` | Thông tin trên datagram/socket được mạng chuyển đến | Địa chỉ và port nguồn mà receiver *quan sát được*. |
| **Spring Message headers** | `ip_address`, `ip_port`, `id` | Framework tạo khi chuyển datagram thành `Message` | Metadata nội bộ để xử lý, định tuyến hoặc theo dõi. |

Một `Message<byte[]>` trong Spring Integration có thể được hình dung như sau:

~~~text
Message
├── payload: byte[] -> "sensor=node-7;tempC=26.5"
└── headers:
    ├── ip_address: "192.0.2.31"
    ├── ip_port: 51234
    ├── ip_hostname: "192.0.2.31"
    ├── ip_packetAddress: InetSocketAddress(192.0.2.31, 51234)
    ├── id: UUID do Spring tạo
    └── timestamp: thời điểm tạo Message
~~~

Các giá trị trên là **minh họa** cho UDP unicast và `lookupHost=false`. Tập header thực tế phụ thuộc adapter, phiên bản, cấu hình và đường xử lý. `id` và `timestamp` là metadata chung của Spring Messaging; chúng không phải `sequence` hoặc timestamp nghiệp vụ do thiết bị phát.

**Không mặc định serializing mọi message header ra mạng:** với UDP outbound adapter thông thường, payload được mã hóa thành bytes trong datagram; các header Spring Integration còn lại là dữ liệu nội bộ trừ khi bạn chủ động thiết kế giao thức gửi chúng.

## 3. Những header UDP cần biết

Lớp `org.springframework.integration.ip.IpHeaders` cung cấp tên header chính thức. Dùng hằng số này giúp tránh gõ nhầm khóa khi gọi `message.getHeaders().get(...)`.

| Tên header thực | Hằng số trong `IpHeaders` | Ý nghĩa | Kiểu dữ liệu thường gặp |
|---|---|---|---|
| `ip_address` | `IpHeaders.IP_ADDRESS` | Địa chỉ IP nguồn của gói UDP nhận được | `String` |
| `ip_port` | `IpHeaders.PORT` | **Port nguồn UDP từ xa**, không phải cổng listener của server | `Integer` |
| `ip_hostname` | `IpHeaders.HOSTNAME` | Hostname nguồn, hoặc chuỗi IP khi không reverse lookup | `String` |
| `ip_packetAddress` | `IpHeaders.PACKET_ADDRESS` | Địa chỉ socket nguồn đầy đủ lấy từ `DatagramPacket.getSocketAddress()` | `SocketAddress`, thường là `InetSocketAddress` |
| `ip_localInetAddress` | `IpHeaders.LOCAL_ADDRESS` | Địa chỉ cục bộ gắn với socket/endpoint khi có trong ngữ cảnh tương ứng | `InetAddress`, không phải lúc nào cũng có |
| `ip_ackTo` | `IpHeaders.ACK_ADDRESS` | Địa chỉ phục vụ cơ chế acknowledgment ở tầng ứng dụng của Spring Integration UDP | Phụ thuộc cơ chế ACK |
| `ip_ackId` | `IpHeaders.ACK_ID` | Mã tương quan cho acknowledgment của cơ chế UDP ACK | Phụ thuộc cơ chế ACK |

**Phân biệt rõ các header dễ nhầm:**

- `IpHeaders.PORT` là port nguồn **UDP**. `IpHeaders.REMOTE_PORT` tương ứng `ip_tcp_remotePort` dành cho **TCP**; không dùng hằng số TCP để đọc port nguồn của datagram UDP.
- `IpHeaders.PACKET_ADDRESS` chứa **cặp IP + port**, có thể truyền trực tiếp làm đích cho một UDP outbound handler có `destination-expression`.
- `ip_address` và `ip_hostname` có thể giống nhau khi tắt lookup-host, nhưng chúng biểu diễn hai ý nghĩa khác nhau.
- `ip_ackTo` và `ip_ackId` không phải luôn tồn tại trên mọi datagram; chỉ có ý nghĩa khi endpoint dùng giao thức ACK tương thích.
- `MessageHeaders.REPLY_CHANNEL` và `MessageHeaders.ERROR_CHANNEL` (nếu hiện diện) thuộc mô hình message nội bộ; chúng không tương đương với **UDP source address**.

Vì các header phụ thuộc ngữ cảnh, hãy kiểm tra null và kiểu trước khi dùng thay vì ép kiểu mọi giá trị ngay khi nhận message.

## 4. UDP inbound adapter tạo các header như thế nào?

Luồng nhận unicast đơn giản gồm:

~~~mermaid
flowchart LR
    D["UDP datagram"] --> R["UnicastReceivingChannelAdapter"]
    R --> P["DatagramPacketMessageMapper"]
    P --> M["Message<byte[]> với IP headers"]
    M --> C["MessageChannel"]
    C --> H["Handler nghiệp vụ"]
~~~

Trong Spring Integration, **`DatagramPacketMessageMapper`** ánh xạ một `DatagramPacket` nhận được thành `Message<byte[]>`. Thông tin `ip_packetAddress` phản ánh kết quả của `DatagramPacket.getSocketAddress()`; từ đây ta cũng đọc được địa chỉ nguồn/port của datagram.

Các dữ liệu này do **mạng và socket cung cấp**, không phải trường JSON do thiết bị tự khai báo. Nếu payload có `sensorId` thì đó là nhận dạng **nghiệp vụ**, còn `ip_address` là địa chỉ **mạng quan sát tại receiver**. Hai loại nhận dạng có thể dùng để đối chiếu nhưng không nên coi là tương đương.

### 4.1. Port nguồn khác port đích

Giả sử client tạo UDP socket được hệ điều hành cấp port `51234` rồi gửi đến server `127.0.0.1:12004`:

~~~text
Client socket: 127.0.0.1:51234
              UDP send
Server socket: 127.0.0.1:12004

Header ở message nhận:
  ip_address        = "127.0.0.1"
  ip_port           = 51234
  ip_packetAddress  = 127.0.0.1:51234
~~~

Cổng `12004` là **port mà server bind để lắng nghe**. Nó không phải giá trị `ip_port` của datagram nhận được. Nếu client đóng socket rồi mở một socket khác, port nguồn có thể thay đổi.

### 4.2. Hostname lookup và DNS

Theo mặc định, UDP inbound adapter **không thực hiện reverse DNS lookup** (`lookup-host=false`). Khi đó `ip_hostname` thường chứa chính chuỗi IP, giúp tránh thời gian chờ DNS trong các môi trường như Docker hoặc mạng nội bộ không có PTR record.

Khi bật `lookup-host=true`, framework có thể tra tên host nguồn qua DNS. Cách làm này có một số hệ quả:

- Reverse DNS có thể chậm, không tồn tại hoặc trả về giá trị không mong đợi.
- Hostname không phải chứng chỉ định danh, không đủ để xác thực thiết bị.
- Ghi metric theo hostname có thể làm tăng cardinality hoặc khó đối chiếu khi DNS thay đổi.

Chỉ bật reverse DNS nếu có nhu cầu rõ ràng, hệ thống DNS đáng tin cậy và đã đo ảnh hưởng hiệu năng. Khi xử lý định tuyến phản hồi, **`ip_packetAddress`** thường thích hợp hơn hostname đã tra ngược.

## 5. Ví dụ Java: nhận UDP và đọc header

### 5.1. Dependency

Trong Spring Boot có dependency management, khai báo các thư viện tích hợp:

~~~xml
<!-- pom.xml: trong phần <dependencies> -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

### 5.2. Khai báo inbound flow và channel

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.dsl.Udp;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class UdpHeaderFlowConfig {

    @Bean("udpRawInput")
    public MessageChannel udpRawInput() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow udpInboundFlow() {
        return IntegrationFlow.from(Udp.inboundAdapter(12004))
                .channel("udpRawInput")
                .get();
    }
}
~~~

`Udp.inboundAdapter(12004)` lắng nghe datagram UDP unicast; `channel("udpRawInput")` chuyển message đến một kênh nội bộ. Đây là endpoint **nhận theo sự kiện socket**, không cần cấu hình poller để đọc từng datagram.

### 5.3. Service Activator kiểm tra header nguồn

~~~java
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.ip.IpHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.stereotype.Component;

@Component
public class UdpHeaderInspector {

    private static final Logger log =
            LoggerFactory.getLogger(UdpHeaderInspector.class);

    @ServiceActivator(inputChannel = "udpRawInput")
    public void inspect(Message<byte[]> message) {
        byte[] bytes = message.getPayload();
        if (bytes.length == 0 || bytes.length > 512) {
            log.warn("Discard UDP datagram of size {}", bytes.length);
            return;
        }

        MessageHeaders headers = message.getHeaders();

        String sourceIp = headers.get(IpHeaders.IP_ADDRESS, String.class);
        Integer sourcePort = headers.get(IpHeaders.PORT, Integer.class);
        String sourceHost = headers.get(IpHeaders.HOSTNAME, String.class);
        SocketAddress sourceAddress =
                headers.get(IpHeaders.PACKET_ADDRESS, SocketAddress.class);

        if (sourceIp == null || sourcePort == null
                || !(sourceAddress instanceof InetSocketAddress)) {
            log.warn("Discard message without usable UDP source metadata");
            return;
        }

        // Chỉ minh họa; production phải validate encoding và schema.
        String payload = new String(bytes, StandardCharsets.UTF_8);

        log.info("UDP from {}:{} (host={}, packetAddress={})",
                sourceIp, sourcePort, sourceHost, sourceAddress);
        log.info("UDP sample payload={}", payload);
    }
}
~~~

Kết quả minh họa nếu gửi từ client trên máy nhận:

~~~text
UDP from 127.0.0.1:51234 (host=127.0.0.1, packetAddress=/127.0.0.1:51234)
UDP sample payload=sensor=node-7;tempC=26.5
~~~

Port nguồn có thể khác `51234`; chuỗi biểu diễn `InetSocketAddress` cũng có thể khác tùy Java và môi trường.

**Không xem code logging là parser production:** dữ liệu UDP cần được kiểm tra encoding UTF-8, giới hạn dung lượng, version, schema và ràng buộc nghiệp vụ. Nếu in payload không kiểm soát, log có thể chứa dữ liệu nhạy cảm hoặc ký tự phá định dạng. Trong production, ưu tiên log trường đã chuẩn hóa và ID tương quan với mức lấy mẫu phù hợp.

### 5.4. Nếu muốn đọc header trong SpEL

Bên cạnh Java, có thể đọc header từ expression của Spring Integration, ví dụ:

~~~text
headers['ip_address']
headers['ip_port']
headers['ip_packetAddress']
~~~

Dùng expression khi định tuyến qua router hoặc xác định đích của outbound adapter; dùng `IpHeaders` khi viết Java để IDE kiểm tra tên hằng số. Cả hai thao tác đều lấy **message header**, không lấy trực tiếp nội dung payload.

## 6. Thử nghiệm xác nhận địa chỉ nguồn thật

Mở ứng dụng Spring Boot có hai class phía trên. Từ PowerShell trên **cùng máy**, tạo `UdpClient` và để hệ điều hành cấp một port nguồn động:

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new(0)
try {
    $local = [System.Net.IPEndPoint]$client.Client.LocalEndPoint
    Write-Host "UDP source port: $($local.Port)"

    $text = "sensor=node-7;tempC=26.5"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)

    [void]$client.Send($bytes, $bytes.Length, "127.0.0.1", 12004)
}
finally {
    $client.Dispose()
}
~~~

Khi `udpInboundFlow` đã lắng nghe `12004`, so sánh **UDP source port** mà client in ra với `ip_port` trong log của `UdpHeaderInspector`. Hai số phải trùng trong thử nghiệm loopback này; `sourceIp` dự kiến là `127.0.0.1`.

Thử chạy lại đoạn PowerShell vài lần. Bạn có thể thấy port nguồn thay đổi, trong khi port đích của server vẫn là `12004`.

| Thao tác | Điều cần quan sát |
|---|---|
| Gửi từ client bind port động | `ip_port` là port client vừa dùng, không phải 12004 |
| Giữ một `UdpClient` và gửi nhiều datagram | Port nguồn thường ổn định trong vòng đời socket đó |
| Đóng rồi tạo client mới | Port nguồn có thể thay đổi |
| Gửi từ máy khác | `ip_address` thường là IP nguồn được mạng thấy, có thể bị NAT thay đổi |
| Gửi dữ liệu quá lớn | Phải xử lý giới hạn receive buffer, có thể mất/cắt ngắn datagram |

Gửi thành công ở client **không chứng minh** handler Spring Integration đã chạy. Nếu không có log, hãy kiểm tra server đang bind đúng UDP port, firewall, container network và việc `udpRawInput` có subscriber.

## 7. Dùng địa chỉ nguồn để gửi UDP phản hồi

### 7.1. Vì sao chỉ IP nguồn chưa đủ?

Một datagram nguồn `203.0.113.10:53021` không thể được phản hồi chính xác nếu handler chỉ lưu `203.0.113.10` rồi đoán port. Sender có thể dùng port động và thiết bị sau NAT có thể được ánh xạ thành port khác.

Header **`ip_packetAddress`** chứa cặp `IP:port` từ `DatagramPacket.getSocketAddress()`, phù hợp để làm đích phản hồi *trong cùng ngữ cảnh trao đổi*.

~~~mermaid
sequenceDiagram
    participant C as UDP client
    participant I as Inbound adapter
    participant H as Message handler
    participant O as Outbound adapter
    C->>I: Datagram từ IP:port nguồn
    I->>H: Message + ip_packetAddress
    H->>O: Payload ACK + giữ header nguồn
    O-->>C: Datagram gửi về ip_packetAddress
~~~

Đây là quy trình phản hồi do ứng dụng xây dựng. **UDP inbound adapter không tự trả lời mọi datagram**.

### 7.2. Ví dụ Java DSL: trả lời tới đúng sender

Spring Integration UDP outbound handler hỗ trợ **`destination-expression`** để xác định đích động từ message. Đồng thời, **`socket-expression`** cho phép dùng socket của inbound adapter để phát phản hồi từ cùng port server đã nhận, hữu ích khi client ở sau NAT.

Ví dụ một UDP echo/ACK tối giản trên **cổng khác là 12005**:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.dsl.Udp;

@Configuration
public class UdpReplyFlowConfig {

    @Bean
    public IntegrationFlow udpReplyFlow() {
        return IntegrationFlow
                .from(Udp.inboundAdapter(12005).id("udpReplyIn"))
                .<byte[], byte[]>transform(
                        bytes -> "ACK".getBytes(StandardCharsets.UTF_8))
                .handle(
                        Udp.outboundAdapter(
                                "headers['ip_packetAddress']")
                           .socketExpression("@udpReplyIn.socket"))
                .get();
    }
}
~~~

Ý nghĩa:

1. Inbound adapter nhận datagram trên **12005** và tạo message có `ip_packetAddress`.
2. Transformer biến payload thành `ACK`; transformer Spring Integration thông thường **giữ lại các header đầu vào** khi tạo message đầu ra.
3. `Udp.outboundAdapter("headers['ip_packetAddress']")` xác định đích bằng socket address của sender vừa gửi.
4. `.socketExpression("@udpReplyIn.socket")` sử dụng lại socket của adapter nhận, giúp datagram phản hồi đi ra từ **port 12005**.

**Điều kiện quan trọng:** nếu một bước trong luồng tự tạo `Message` mới, phải **giữ lại `IpHeaders.PACKET_ADDRESS`** nếu các bước sau cần trả lời. Đừng thay bằng một message chỉ có payload mà vô tình làm mất metadata định tuyến.

`socket-expression` không dùng chung với các tùy chọn **multicast** và **acknowledge** của UDP outbound adapter. Nếu muốn cơ chế ACK riêng, hãy xác định rõ contract và cấu hình tương thích ở cả hai bên.

### 7.3. Thử ACK bằng PowerShell

Chạy ứng dụng có `udpReplyFlow`. Trong PowerShell, gửi datagram đến `127.0.0.1:12005` rồi chờ ACK trên **cùng `UdpClient`**:

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new(0)
$client.Client.ReceiveTimeout = 3000

try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes("ping")
    [void]$client.Send($bytes, $bytes.Length, "127.0.0.1", 12005)

    $remote = [System.Net.IPEndPoint]::new(
        [System.Net.IPAddress]::Any, 0
    )
    $reply = $client.Receive([ref]$remote)

    Write-Host "Response from $remote"
    Write-Host ([System.Text.Encoding]::UTF8.GetString($reply))
}
finally {
    $client.Dispose()
}
~~~

Dự kiến thấy **`ACK`** từ port `12005`. Nếu quá 3 giây mà chưa có gói phản hồi, `Receive` ném timeout exception. Nguyên nhân có thể do server chưa lắng nghe, mạng/firewall chặn, hoặc mất header/destination trong luồng. Việc nhận ACK chứng minh *một datagram phản hồi* đã đến client, **không chứng minh rằng giao dịch nghiệp vụ được commit**.

Đây là minh họa trên localhost. **Không triển khai UDP echo công khai không giới hạn**: địa chỉ nguồn UDP có thể bị giả mạo khiến dịch vụ trở thành bộ phản xạ gói tin. Cần giới hạn mạng nguồn, tốc độ, kích thước phản hồi, xác thực theo hợp đồng và kiểm soát luồng trước khi mở cổng ra mạng bên ngoài.

## 8. Địa chỉ nguồn trong môi trường NAT và nhiều network interface

### 8.1. NAT có thể thay đổi thứ mà receiver quan sát

Giả sử sender ở mạng riêng có địa chỉ:

~~~text
Sender nội bộ: 10.0.1.5:53021
NAT gateway:   198.51.100.8:62044
Server ngoài:  203.0.113.20:12004
~~~

Khi datagram đi qua NAT, server bên ngoài có thể thấy:

~~~text
ip_address       = "198.51.100.8"
ip_port          = 62044
ip_packetAddress = 198.51.100.8:62044
~~~

Đó là **địa chỉ mạng được server quan sát**, không phải IP riêng của sender. Port mapping có thể thay đổi sau timeout hoặc khi sender mở socket mới. Nếu chỉ lưu `ip_packetAddress` rồi gửi lại nhiều phút sau, mapping cũ có thể đã hết hạn.

Việc trả lời từ **cùng socket/port** thường giúp tương thích với một số kiểu NAT, nhưng vẫn phải kiểm tra chính sách NAT/firewall thực tế; không có đảm bảo phản hồi luôn tới được thiết bị.

### 8.2. Multi-homed host và địa chỉ cục bộ

Server có thể có nhiều interface: Ethernet, Wi-Fi, VPN, mạng container. Các header **nguồn** cho biết endpoint từ xa; chúng không nhất thiết nói datagram đã vào qua NIC nào.

Để kiểm soát địa chỉ bind trên inbound adapter, có thể cấu hình **`local-address`** phù hợp và xác minh routing/network policy. Đừng mặc định header `ip_localInetAddress` luôn có hoặc đủ thông tin để xác định interface cho mọi trường hợp UDP; hãy kiểm tra trên phiên bản và topology cụ thể.

### 8.3. Khi nào nên dùng địa chỉ nguồn làm khóa?

**Không dùng `IP:port` làm danh tính thiết bị lâu dài.** DHCP, NAT, mobile network, VPN, container lifecycle và port động có thể thay đổi địa chỉ. Một thiết bị có thể đổi endpoint, còn nhiều thiết bị có thể dùng chung public IP.

Nếu cần xác định sensor chính xác, payload nên có `deviceId`, version, timestamp/sequence và cơ chế chứng thực phù hợp. Sau đó có thể lưu thông tin nguồn mạng dưới dạng metadata quan sát, hữu ích cho phát hiện bất thường hoặc debugging.

## 9. Tổ chức hợp đồng message để giữ metadata quan trọng

Một cách thiết kế an toàn là tách:

| Nhóm dữ liệu | Ví dụ | Tác dụng |
|---|---|---|
| **Payload nghiệp vụ** | `deviceId`, `seq`, `tempC` | Kiểm tra schema, lưu DB, tính toán |
| **Metadata từ mạng** | `ip_address`, `ip_port`, `ip_packetAddress` | Chẩn đoán, routing phản hồi ngắn hạn |
| **Metadata của Spring Messaging** | `id`, `timestamp`, `correlationId` nếu có | Theo dõi luồng nội bộ |
| **Context ứng dụng** | Authenticated device ID, tenant, trace ID | Phân quyền và quan sát khi đã được hệ thống xác minh |

Nếu cần chuyển tiếp sang JMS, AMQP, Kafka, HTTP hoặc lưu cơ sở dữ liệu, nên quyết định **field nào thuộc dữ liệu nghiệp vụ** và **field nào chỉ là metadata xử lý tại ingress**. Không nên tự động chép tất cả header vào một sự kiện phát ra bên ngoài: có thể làm lộ IP nguồn, thông tin topology nội bộ hoặc đối tượng Java không serializable.

Khi dùng transformer/filter/router trong Spring Integration, kiểm tra các bước có bảo toàn header cần thiết. Ví dụ một outbound adapter dùng `destination-expression="headers['ip_packetAddress']"` sẽ không hoạt động đúng nếu header bị loại trước khi tới endpoint.

### Ví dụ giữ header khi dựng Message mới

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<byte[]> createReply(
        Message<byte[]> incoming, byte[] replyBytes) {

    return MessageBuilder.withPayload(replyBytes)
            .copyHeaders(incoming.getHeaders())
            .build();
}
~~~

Ví dụ này giữ header để một outbound endpoint có thể đọc `IpHeaders.PACKET_ADDRESS`. Trong thực tế, chỉ chuyển tiếp **những metadata được phép và cần thiết**. Nếu nhận message từ nguồn không đáng tin cậy khác, phải kiểm soát header đầu vào thay vì cho phép bất kỳ caller nào áp đặt địa chỉ đích tùy ý.

## 10. Phân biệt ACK của Spring Integration và phản hồi tự thiết kế

Spring Integration UDP có các tùy chọn hỗ trợ **application-level acknowledgment**. Khi dùng cơ chế này, payload/framing có thể chứa thông tin phục vụ ACK; các header như `ip_ackTo` và `ip_ackId` liên quan đến việc xác định đích ACK và correlate phản hồi.

| Cơ chế | Phát sinh như thế nào? | Ý nghĩa |
|---|---|---|
| **Thông tin nguồn UDP** | Inbound adapter nhận một datagram | Biết IP/port mà mạng quan sát được |
| **`ip_packetAddress`** | Mapper điền socket address nguồn | Có thể dùng để gửi datagram ngược về sender |
| **Spring Integration UDP ACK** | Hai endpoint bật và hiểu cùng giao thức ACK | Xác nhận theo contract kỹ thuật của adapter |
| **ACK nghiệp vụ** | Receiver tự định nghĩa khi nào gửi | Có thể xác nhận parse, ghi bền, xử lý thành công tùy hợp đồng |
| **`replyChannel` nội bộ** | Spring Messaging/gateway dùng để trả kết quả trong ứng dụng | Không tự động là địa chỉ UDP đích |

Với các luồng quan trọng, phân biệt rõ ba trạng thái: **đã gửi**, **receiver đã nhận** và **nghiệp vụ đã commit**. Một ACK kỹ thuật không tự động tương đương `database transaction committed`. Retry sau timeout phải kèm ID/sequence và idempotency vì receiver có thể đã nhận gói trước đó.

## 11. Những sai lầm thường gặp

| Dấu hiệu | Nhầm lẫn thường thấy | Cách xử lý |
|---|---|---|
| Log `ip_port=51234` nhưng server listen 12004 | Tưởng `ip_port` là cổng server | Đây là **port nguồn** của sender; giữ port listener trong cấu hình server |
| Không có hostname thật | Tưởng header `ip_hostname` bị lỗi | Default `lookupHost=false` trả chuỗi IP; reverse DNS tùy chọn |
| Đọc `ip_tcp_remotePort` và nhận null | Dùng header TCP cho UDP | Dùng `IpHeaders.PORT` |
| Không trả lời được client | Chỉ giữ IP mà bỏ source port, header bị mất, hoặc dùng sai local socket | Giữ `ip_packetAddress`, kiểm tra destination-expression/socket-expression |
| Response tới nhầm thiết bị sau NAT | Dùng địa chỉ nguồn đã hết hạn hoặc replay | Không coi mapping NAT ổn định; phản hồi trong phiên trao đổi đang hoạt động |
| Dùng `ip_address` làm quyền truy cập | IP nguồn bị giả mạo, NAT, mạng không đáng tin | Xác thực message/device bằng protocol bảo mật phù hợp |
| Đã gửi UDP nhưng không có log handler | Gói thất lạc, sai bind, firewall hoặc adapter chưa start | Kiểm tra packet capture, lifecycle, channel subscription |
| Message không còn `ip_packetAddress` sau transform | Dựng message mới mà không copy header | Kiểm tra từng bước trong integration flow |
| Ghi toàn bộ headers ra broker | Lộ IP hoặc gửi object Java không phù hợp | Chuẩn hóa event DTO, chỉ giữ metadata cần thiết |
| Header `ip_ackId` không có | Chưa dùng protocol UDP ACK tương thích | Không giả định ACK headers tồn tại ở mọi gói |

Khi debug, đi theo thứ tự **gói đến host → inbound adapter chuyển datagram thành message → header mapper gắn metadata → channel dispatch → handler đọc header → outbound gửi phản hồi (nếu có)**. Kiểm tra từng bước bằng log giới hạn, metric và packet capture thay vì suy đoán từ một dòng log sender.

## 12. Kiểm thử phù hợp với từng lớp

| Lớp | Cách thử | Điều xác minh |
|---|---|---|
| Unit test handler | Tạo `Message<byte[]>` với `IpHeaders` chủ động thiết lập | Handler xử lý header null/kiểu sai/giới hạn bytes đúng |
| Integration test UDP | Gửi datagram thực đến port test | Framework ánh xạ source IP/port thành header |
| Echo/reply test | Gửi và chờ ACK bằng một socket client | Đích phản hồi chọn đúng `ip_packetAddress` và port nguồn |
| NAT/network test | Sender ở mạng khác/subnet/container | IP/port mà receiver quan sát và khả năng phản hồi thực tế |
| Security test | Datagram không hợp lệ, nhiều gói, giả lập lỗi schema | Không phản xạ payload tùy ý hoặc xử lý vượt tài nguyên |

Để kiểm tra nguồn chính xác ở unit test, có thể dựng message giả lập:

~~~java
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import org.springframework.integration.ip.IpHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<byte[]> sample = MessageBuilder
        .withPayload("sensor=node-7;tempC=26.5"
                .getBytes(StandardCharsets.UTF_8))
        .setHeader(IpHeaders.IP_ADDRESS, "127.0.0.1")
        .setHeader(IpHeaders.PORT, 53021)
        .setHeader(IpHeaders.PACKET_ADDRESS,
                new InetSocketAddress("127.0.0.1", 53021))
        .build();
~~~

Message dựng tay giúp test logic service, nhưng **không chứng minh `DatagramPacketMessageMapper` thực sự nhận đúng metadata**. Muốn xác minh ánh xạ của adapter, dùng test qua socket thật và so sánh source port client với log/header ở server.

## 13. Bảo mật và quan sát khi dùng IP header

Địa chỉ nguồn UDP ở tầng mạng là **thông tin quan sát**, không phải danh tính đáng tin. Datagram có thể được tạo với địa chỉ nguồn giả mạo ở một số đường mạng, và NAT/proxy có thể thay đổi địa chỉ mà receiver nhìn thấy. Vì vậy:

1. **Không xác thực hoặc phân quyền** bằng `ip_address` đơn lẻ khi nguồn không hoàn toàn tin cậy.
2. **Không gửi UDP response đến mọi `ip_packetAddress` một cách vô điều kiện** trên cổng public; giảm thiểu UDP reflection/amplification bằng rate limit, allowlist, phản hồi nhỏ và cơ chế chứng thực/nonce khi phù hợp.
3. **Giữ riêng network identity và device identity**. ID thiết bị, tenant và quyền truy cập cần được kiểm tra theo policy của ứng dụng.
4. **Giới hạn payload và log**; không ghi tất cả dữ liệu hoặc mỗi địa chỉ IP thành metric label nếu có số lượng IP rất lớn.
5. **Theo dõi vòng đời socket và hạ tầng**: port bind, firewall, NAT timeout, tình trạng listener, tình trạng nhận/lỗi/ACK; UDP không có tín hiệu kết nối bền như TCP.
6. **Nếu cần bảo mật nội dung**, dùng cơ chế mã hóa/xác thực thích hợp ở tầng ứng dụng hoặc transport/mạng bảo vệ; UDP thuần không tự cung cấp TLS.

Một bộ metric tối thiểu có thể gồm `udp_datagrams_received_total`, `udp_payload_invalid_total`, `udp_handler_failure_total`, `udp_reply_attempt_total` và `udp_reply_error_total`. Không dùng riêng `udp_reply_attempt_total` để khẳng định sender đã nhận phản hồi.

## 14. Bài thực hành mở rộng

Xây một receiver telemetry tại `12004` và một echo server dành riêng cho phòng lab tại `12005`.

**Phần A — Nhận diện nguồn:**

1. Gửi ba datagram từ **cùng một** `UdpClient` và ghi `ip_address`, `ip_port`, `ip_packetAddress`.
2. Đóng socket, mở một `UdpClient` mới và gửi lại. Quan sát port nguồn có thay đổi hay không.
3. Gửi từ một thiết bị khác trong LAN; đối chiếu IP nguồn, port nguồn và IP listener.
4. Bật/tắt `lookup-host` trong môi trường thử nghiệm có DNS phù hợp, so sánh `ip_hostname`, thời gian xử lý và kết quả khi DNS không có reverse record.
5. Thử một datagram sai schema hoặc quá 512 byte; xác định phần nào thuộc validate payload, phần nào thuộc metadata nguồn.

**Phần B — Gửi phản hồi:**

1. Bật `udpReplyFlow` ở `12005`, dùng PowerShell gửi `ping` và nhận `ACK`.
2. Đặt một transformer tạo message mới nhưng làm mất toàn bộ headers; giải thích vì sao `destination-expression` không còn biết địa chỉ gửi phản hồi.
3. Thay đổi để header nguồn được bảo toàn hoặc copy chọn lọc, xác minh ACK nhận được trên đúng socket client.
4. Đưa client sang mạng có NAT hoặc container và quan sát source endpoint do receiver thấy; thảo luận tác động của timeout và giới hạn firewall.
5. Đề xuất cách xác thực sender và ngăn UDP reflection trước khi cho phép phản hồi trên mạng ngoài.

**Câu hỏi tự đánh giá:**

- Vì sao `IpHeaders.PORT` không phải cổng UDP mà inbound adapter đang lắng nghe?
- `ip_hostname` khác `ip_address` như thế nào khi `lookup-host` được bật?
- Khi nào `ip_packetAddress` hữu ích hơn cặp `ip_address` và `ip_port`?
- Vì sao source IP/port không đủ làm khóa định danh của một cảm biến?
- Nếu handler gửi message sang Kafka, có nên mang `SocketAddress` nguyên bản sang event ở broker không?
- Tại sao phản hồi UDP không đồng nghĩa với Spring Integration gateway hoặc ACK nghiệp vụ bền vững?
- Nếu producer lấy dữ liệu từ SFTP bằng poller rồi gửi UDP, các IP header xuất hiện ở bước nào và theo transport nào?

## 15. Tài liệu tham khảo

- [Spring Integration Reference — IP Message Headers](https://docs.spring.io/spring-integration/reference/ip/msg-headers.html): danh sách header IP và ý nghĩa `ip_address`, `ip_port`, `ip_hostname`, ACK.
- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): inbound adapter, `lookup-host`, `destination-expression`, `socket-expression` và ví dụ trả lời theo `ip_packetAddress`.
- [Spring Integration Reference — IP Configuration Attributes](https://docs.spring.io/spring-integration/reference/ip/endpoint-reference.html): thuộc tính `lookup-host`, `local-address`, buffer và error channel.
- [Spring Integration Source — IpHeaders](https://github.com/spring-projects/spring-integration/blob/main/spring-integration-ip/src/main/java/org/springframework/integration/ip/IpHeaders.java): tên hằng số chính thức cho các header liên quan UDP/TCP.

## Kết luận

**UDP message header** giúp Spring Integration kết hợp payload nhận được với thông tin về endpoint mạng đã gửi datagram. Trong xử lý unicast cơ bản, các header **`ip_address`**, **`ip_port`**, **`ip_hostname`** và đặc biệt **`ip_packetAddress`** cho phép quan sát nguồn gửi và, khi được cấu hình phù hợp, định tuyến phản hồi về sender.

Hãy sử dụng chúng theo đúng ý nghĩa **metadata mạng**: phân biệt IP/port nguồn với cổng listener, bảo toàn header cần thiết khi transformer hoặc router, cân nhắc reverse DNS/NAT và không dùng địa chỉ nguồn thay cho xác thực thiết bị. Từ ranh giới UDP này, các luồng tiếp theo của **SPRING_INTEGRATION_ADAPTERS** có thể xử lý dữ liệu qua `MessageChannel` và nối đến cơ sở dữ liệu, HTTP, SFTP, JMS, AMQP, Kafka hoặc các hệ thống khác theo hợp đồng message đã định nghĩa.
