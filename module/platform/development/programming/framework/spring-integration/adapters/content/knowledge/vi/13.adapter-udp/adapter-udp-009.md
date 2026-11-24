# Broadcast trên mạng nội bộ với Spring Integration UDP

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **UDP broadcast IPv4** với unicast, multicast và cơ chế publish/subscribe của message broker.
- Tính **directed broadcast address** từ IP/subnet mask và giải thích limited broadcast `255.255.255.255`.
- Cấu hình Spring Integration UDP inbound/outbound adapter, `MessageChannel` và **`SO_BROADCAST`**.
- Gửi/nhận broadcast bằng Java và PowerShell trên hai máy trong cùng LAN; quan sát địa chỉ nguồn, firewall và interface.
- Thiết kế giao thức khám phá thiết bị (*service discovery*) với request ID, giới hạn phản hồi và kiểm soát tải.
- Hiểu các giới hạn về mất gói, NAT/VLAN, Wi-Fi, bảo mật và lựa chọn giải pháp khác khi cần nhiều subnet hoặc giao hàng tin cậy.

Bài thuộc chương **Adapter UDP** trong module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối các hệ thống ngoài vào Spring Integration qua inbound/outbound adapter, gateway, poller và `MessageChannel`, rồi xử lý hợp đồng message, lỗi và vòng đời khi tích hợp file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Với broadcast, **một sender cố gắng phát cùng một datagram đến nhiều host trong phạm vi mạng nội bộ**; việc phát không đồng nghĩa mọi receiver đã nhận hoặc xử lý.

## 1. Bài toán: tìm thiết bị chưa biết địa chỉ IP

Giả sử một ứng dụng điều khiển cần tìm các cảm biến trong LAN. Ứng dụng **chưa biết IP của từng cảm biến**, nhưng tất cả đều được thiết kế để lắng nghe UDP port `12019`.

Sender phát một datagram đến địa chỉ broadcast của subnet:

~~~text
v=1;type=DISCOVER;requestId=req-001
~~~

Những thiết bị nhận và chấp nhận gói có thể gửi **unicast response** về IP/port nguồn của sender:

~~~text
v=1;type=OFFER;requestId=req-001;device=node-7
~~~

~~~mermaid
sequenceDiagram
    participant A as Discovery sender
    participant N as IPv4 broadcast LAN
    participant B as Sensor B
    participant C as Sensor C
    A->>N: DISCOVER requestId=req-001
    N-->>B: Datagram nếu mạng cho phép
    N-->>C: Datagram nếu mạng cho phép
    B-->>A: OFFER unicast
    C-->>A: OFFER unicast
    Note over A: Thu thập phản hồi trong thời hạn
~~~

Đây là **giao thức ví dụ do ứng dụng tự định nghĩa**, không phải dịch vụ tự có của Spring Integration. Ứng dụng phải kiểm tra version, độ dài, source, deadline và trùng lặp, đồng thời không giả định mọi thiết bị đều phản hồi.

Broadcast thường thích hợp cho **tìm kiếm ban đầu trong một broadcast domain nhỏ**. Khi đã có danh sách địa chỉ thiết bị, những thao tác tiếp theo có thể chuyển sang unicast hoặc transport có xác nhận, xác thực và lưu bền rõ ràng.

## 2. Khái niệm IPv4 broadcast

**Broadcast** là phương thức gửi gói IPv4 đến một địa chỉ đại diện cho nhiều host trong phạm vi mạng nhất định. Trên một mạng Ethernet thông thường, IP broadcast có thể được đóng gói vào frame broadcast ở tầng liên kết. Tuy vậy, mỗi hệ điều hành, switch, AP, firewall và socket vẫn có chính sách riêng: **không thể cam kết mọi máy nhìn thấy hoặc chuyển gói tới ứng dụng**.

| Loại gửi | Đích minh họa | Receiver | Có join group? |
|---|---|---|---|
| Unicast | `192.168.10.25:12019` | Một endpoint theo địa chỉ IP/port đích | Không |
| IPv4 broadcast | `192.168.10.255:12019` với mạng /24 | Những host trong phạm vi subnet phù hợp nếu mạng/socket cho phép | Không |
| IPv4 multicast | `239.10.20.30:12019` | Các host đã join group tương ứng | Có |

**Broadcast khác multicast.** Multicast dùng địa chỉ nhóm và membership; broadcast không cần receiver join group. Broadcast cũng **khác message broker**, vốn có thể quản lý consumer, retry, durable queue hoặc replay theo cơ chế của broker.

### 2.1. Limited broadcast

`255.255.255.255` là địa chỉ **limited broadcast** của IPv4. Router thông thường **không chuyển tiếp** datagram này sang subnet khác. Máy sender có nhiều network interface có thể chọn đường phát tùy cấu hình route và OS; gửi đến địa chỉ này **không có nghĩa gửi lên tất cả NIC**.

Do đó trong lab có subnet xác định, nên tính directed broadcast cho interface cần thử và xác minh bằng packet capture.

### 2.2. Directed broadcast và subnet mask

Giả sử host A có IP `192.168.10.23` và mask `255.255.255.0` (CIDR `/24`):

~~~text
Host address:      192.168.10.23
Subnet mask:       255.255.255.0
Network address:   192.168.10.0
Broadcast address: 192.168.10.255
Host range:        192.168.10.1 .. 192.168.10.254
~~~

Công thức theo bit của IPv4:

~~~text
network   = IP AND netmask
broadcast = network OR (NOT netmask)
~~~

Thay đổi prefix sẽ thay đổi kết quả:

| Địa chỉ host | Prefix | Subnet | Broadcast |
|---|---|---|---|
| `192.168.10.23` | `/24` | `192.168.10.0/24` | `192.168.10.255` |
| `192.168.10.23` | `/23` | `192.168.10.0/23` | `192.168.11.255` |
| `192.168.10.23` | `/25` | `192.168.10.0/25` | `192.168.10.127` |

Vì thế `192.168.10.255` **không phải broadcast đúng cho mọi host** có IP bắt đầu bằng `192.168.10`. Phải đọc prefix thực tế từ interface và áp dụng phép tính; địa chỉ trong bài chỉ để minh họa.

### 2.3. Broadcast scope và router

Broadcast trong một VLAN/broadcast domain không tự động đi sang VLAN khác. Router thường chặn việc forward **directed broadcast** tới subnet khác để tránh bị lợi dụng thành tấn công khuếch đại kiểu Smurf; một số mạng Wi-Fi hoặc cloud cũng chủ động lọc broadcast.

Không nên mở directed broadcast forwarding trên router chỉ để làm bài lab. Nếu ứng dụng cần khám phá thiết bị qua nhiều subnet/VLAN, có thể triển khai **một discovery agent trong từng subnet** và tổng hợp kết quả qua HTTP/Kafka/JMS/AMQP hoặc một service registry.

### 2.4. IPv6 không có broadcast

**IPv6 không hỗ trợ broadcast như IPv4.** IPv6 sử dụng multicast với phạm vi (*scope*) cụ thể, ví dụ địa chỉ all-nodes link-local `ff02::1` trong những tình huống phù hợp. Không thể thay một địa chỉ IPv4 broadcast bằng một chuỗi IPv6 rồi giữ nguyên socket behavior; cơ chế multicast IPv6 cần được thiết kế, cấu hình interface và firewall riêng.

## 3. Spring Integration hỗ trợ broadcast qua UDP thế nào?

Spring Integration IP có các endpoint UDP unicast và multicast. Để phát **IPv4 broadcast**, có thể dùng **UDP outbound adapter thông thường** gửi datagram tới địa chỉ broadcast, cùng socket option **`SO_BROADCAST`**.

| Thành phần | Vai trò |
|---|---|
| `Udp.outboundAdapter(broadcastIp, port)` | Tạo UDP outbound handler gửi bytes tới IPv4 broadcast address |
| `SO_BROADCAST` | Socket option cho phép gửi broadcast, được Java hỗ trợ qua `DatagramSocket.setBroadcast(true)` |
| `Udp.inboundAdapter(port)` | Tạo UDP inbound listener nhận datagram trên cổng tương ứng |
| `MessageChannel` | Chuyển message giữa producer/handler và socket adapter |
| `@ServiceActivator` | Xác thực cú pháp DISCOVER, xử lý message và ghi nhận nguồn |
| `IpHeaders.IP_ADDRESS`, `IpHeaders.PORT` | Header IP/port nguồn mà receiver quan sát được |
| `MulticastSendingMessageHandler` | Dùng khi gửi tới **multicast group**, không phải yêu cầu bắt buộc cho IPv4 broadcast |

~~~mermaid
flowchart LR
    S["Producer nội bộ"] --> CH["MessageChannel"]
    CH --> O["UDP outbound adapter\nSO_BROADCAST"]
    O --> L["Broadcast subnet LAN"]
    L --> A["UDP inbound adapter A"]
    L --> B["UDP inbound adapter B"]
    L --> C["UDP inbound adapter C"]
    A --> H1["Handler A"]
    B --> H2["Handler B"]
    C --> H3["Handler C"]
~~~

UDP inbound nhận datagram theo socket, **không dùng poller** để kiểm tra từng gói đến. Poller chỉ xuất hiện nếu upstream là file, database hoặc một nguồn được truy vấn định kỳ rồi chuyển thông tin ra UDP.

## 4. Bật SO_BROADCAST trên Java DatagramSocket

Trước khi tích hợp vào Spring, có thể hiểu hoạt động bằng Java thuần:

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;

public class SendBroadcastOnce {

    public static void main(String[] args) throws Exception {
        String broadcastIp = "192.168.10.255"; // Lab /24
        int port = 12019;

        byte[] payload =
                "v=1;type=DISCOVER;requestId=req-001"
                        .getBytes(StandardCharsets.UTF_8);

        try (DatagramSocket socket = new DatagramSocket()) {
            socket.setBroadcast(true);
            DatagramPacket packet = new DatagramPacket(
                    payload,
                    payload.length,
                    InetAddress.getByName(broadcastIp),
                    port);
            socket.send(packet);
        }
    }
}
~~~

`DatagramSocket.setBroadcast(true)` bật `SO_BROADCAST`. Java có thể tạo socket mới với broadcast option đã bật trên một số hệ điều hành, nhưng cấu hình tường minh giúp giảm phụ thuộc môi trường. Việc bật option hoặc gọi `send()` thành công **không chứng minh packet đã đến** bất kỳ máy nào.

Nếu ứng dụng có nhiều NIC, việc chọn route/bind source address có thể ảnh hưởng đường phát. Với Wi-Fi, AP client isolation và chế độ tiết kiệm năng lượng của thiết bị cũng có thể làm broadcast khác với Ethernet. Kiểm tra bằng công cụ mạng trước khi quy lỗi cho adapter.

## 5. Cấu hình Spring Boot và Spring Integration Java DSL

Với Spring Boot có dependency management, có thể khai báo:

~~~xml
<!-- Trong <dependencies> của pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

### 5.1. Cấu hình flow inbound và outbound

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
public class UdpBroadcastConfiguration {

    // Địa chỉ ví dụ: thay bằng broadcast thật của NIC triển khai.
    public static final String BROADCAST_IP = "192.168.10.255";
    public static final int PORT = 12019;

    @Bean("broadcastOut")
    public MessageChannel broadcastOut() {
        return new DirectChannel();
    }

    @Bean("broadcastIn")
    public MessageChannel broadcastIn() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow broadcastOutboundFlow() {
        return IntegrationFlow.from("broadcastOut")
                .handle(
                    Udp.outboundAdapter(BROADCAST_IP, PORT)
                       .configureSocket(socket -> socket.setBroadcast(true)))
                .get();
    }

    @Bean
    public IntegrationFlow broadcastInboundFlow() {
        return IntegrationFlow.from(
                    Udp.inboundAdapter(PORT)
                       .receiveBufferSize(2048)
                       .lengthCheck(false))
                .channel("broadcastIn")
                .get();
    }
}
~~~

Trong cấu hình này:

1. `broadcastOut` là input channel cho UDP outbound handler. Nó không tự phát tin cho tới khi một producer gửi message vào.
2. `Udp.outboundAdapter(BROADCAST_IP, PORT)` chỉ định IP/port đích; đây là **broadcast address** đã tính theo subnet.
3. `.configureSocket(socket -> socket.setBroadcast(true))` cấu hình datagram socket của outbound adapter để cho phép gửi broadcast.
4. `Udp.inboundAdapter(PORT)` tạo listener. Để nhận broadcast, socket thường cần được bind trên **wildcard address** thích hợp (ví dụ `0.0.0.0`) và firewall cho phép UDP 12019.
5. `receiveBufferSize(2048)` là dung lượng cho **một datagram**. Nếu payload lớn hơn buffer, nó có thể bị cắt.
6. `lengthCheck(false)` dùng raw bytes. Nếu sender dùng Spring Integration `check-length=true`, receiver phải tương thích với prefix 4 byte hoặc sẽ giải mã sai.

**Khả năng tự nhận broadcast của sender** khi chạy hai flow trên một host phụ thuộc route và OS. Hãy kiểm thử bằng **hai máy khác nhau trong cùng LAN** để chứng minh packet thật sự được đưa qua hạ tầng mạng.

Trong production, host/port và danh sách subnet được phép phải là cấu hình kiểm soát được, thay vì dùng nguyên hằng số demo.

### 5.2. Một service phát DISCOVER khi có yêu cầu hợp lệ

~~~java
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class DiscoveryPublisher {

    private final MessageChannel channel;

    public DiscoveryPublisher(
            @Qualifier("broadcastOut") MessageChannel channel) {
        this.channel = channel;
    }

    public String discoverOnce() {
        String requestId = UUID.randomUUID().toString();
        String text = "v=1;type=DISCOVER;requestId=" + requestId;
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);

        if (payload.length == 0 || payload.length > 512) {
            throw new IllegalArgumentException("Invalid UDP payload size");
        }

        boolean dispatched = channel.send(
                MessageBuilder.withPayload(payload).build());

        if (!dispatched) {
            throw new IllegalStateException("UDP message not dispatched");
        }
        return requestId;
    }
}
~~~

Gọi `discoverOnce()` từ **tác vụ nội bộ hoặc thao tác quản trị có giới hạn tần suất**. Không nên cho một HTTP endpoint công khai phát broadcast tùy ý: nhiều request có thể làm tăng tải của toàn bộ LAN.

Giá trị `requestId` dùng để ghép OFFER với DISCOVER; **không phải ACK**. `MessageChannel.send()==true` chỉ nói lên kết quả dispatch nội bộ, không chứng minh thiết bị nào đã nhận.

### 5.3. Một receiver kiểm tra và đọc header nguồn

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.ip.IpHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class DiscoveryReceiver {

    private static final Logger log =
            LoggerFactory.getLogger(DiscoveryReceiver.class);

    @ServiceActivator(inputChannel = "broadcastIn")
    public void handle(Message<byte[]> message) {
        byte[] bytes = message.getPayload();

        if (bytes.length == 0 || bytes.length > 512) {
            log.warn("Discard discovery packet: invalid bytes={}",
                    bytes.length);
            return;
        }

        final String payload;
        try {
            payload = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException e) {
            log.warn("Discard discovery packet: invalid UTF-8");
            return;
        }

        if (!payload.matches(
                "v=1;type=DISCOVER;requestId=[A-Za-z0-9-]{1,64}")) {
            log.warn("Discard discovery packet: invalid schema");
            return;
        }

        String ip = message.getHeaders()
                .get(IpHeaders.IP_ADDRESS, String.class);
        Integer port = message.getHeaders()
                .get(IpHeaders.PORT, Integer.class);

        log.info("DISCOVER received from {}:{}, byteCount={}",
                ip, port, bytes.length);

        // Nếu cần OFFER: kiểm tra quyền, giới hạn tốc độ và gửi
        // unicast tới endpoint nguồn qua một outbound flow riêng.
    }
}
~~~

`IpHeaders.PORT` là **UDP source port**, có thể là cổng động của sender, không phải cổng listener 12019. Địa chỉ IP nguồn là thông tin mạng quan sát được, **không đủ xác thực thiết bị**. Một custom transformer phải giữ header cần thiết nếu bước sau dùng `ip_packetAddress` để gửi phản hồi.

Đoạn handler chỉ làm rõ việc nhận/validate; nó không tự gửi OFFER. Thêm phản hồi đòi hỏi thiết kế giao thức, danh sách nguồn được phép, giới hạn phản hồi và phòng chống giả mạo.

## 6. Kiểm thử trên hai máy trong cùng LAN

### 6.1. Cấu hình lab minh họa

~~~text
Máy A (sender):   192.168.10.23/24
Máy B (receiver): 192.168.10.45/24
IPv4 broadcast:   192.168.10.255
UDP port:         12019
~~~

Máy thật có địa chỉ hoặc mask khác thì **phải thay broadcast IP**. Broadcast tới `192.168.10.255` từ một NIC trên mạng `10.0.0.0/24` không phải bài thử hợp lệ.

### 6.2. Chạy UDP listener bằng PowerShell trên máy B

Dùng listener độc lập để biết lỗi thuộc mạng hay ứng dụng Spring:

~~~powershell
$receiver = [System.Net.Sockets.UdpClient]::new(12019)
$receiver.Client.ReceiveTimeout = 15000

try {
    Write-Host "Listening UDP on port 12019 ..."
    $source = [System.Net.IPEndPoint]::new(
        [System.Net.IPAddress]::Any, 0
    )
    $bytes = $receiver.Receive([ref]$source)

    Write-Host "Source: $source"
    Write-Host ([System.Text.Encoding]::UTF8.GetString($bytes))
}
finally {
    $receiver.Dispose()
}
~~~

Đoạn nhận chờ tối đa khoảng 15 giây; nếu chưa có gói, `Receive` sẽ phát sinh exception timeout. **Không chạy PowerShell listener và Spring inbound adapter đồng thời trên cùng host/port** trừ khi đã hiểu rõ socket reuse của OS và chủ đích cấu hình.

### 6.3. Gửi broadcast bằng PowerShell từ máy A

~~~powershell
$target = "192.168.10.255" # Thay theo subnet thật
$port = 12019

$client = [System.Net.Sockets.UdpClient]::new()
$client.EnableBroadcast = $true

try {
    $text = "v=1;type=DISCOVER;requestId=req-001"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    [void]$client.Send($bytes, $bytes.Length, $target, $port)

    Write-Host ("Broadcast attempt to {0}:{1}" -f $target, $port)
}
finally {
    $client.Dispose()
}
~~~

Khi B đang lắng nghe và mạng cho phép, B có thể thấy payload và source endpoint của A. Lời gọi `Send` ở A thành công **không có nghĩa B nhận**, càng không chứng minh mọi máy trong subnet đều nhận.

Đối với nhiều host, mỗi receiver cần mở đúng port, có firewall rule phù hợp và nằm trong broadcast domain cho phép. Máy C không có app lắng nghe trên cổng đích sẽ không nhận được `Message` cho business handler dù NIC có thể nhìn thấy broadcast frame.

### 6.4. Thử unicast để khoanh vùng lỗi

Trong khi B đang lắng nghe UDP 12019, A gửi unicast đến IP của B:

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new()
try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes(
        "v=1;type=DISCOVER;requestId=req-002"
    )
    [void]$client.Send(
        $bytes, $bytes.Length, "192.168.10.45", 12019
    )
}
finally {
    $client.Dispose()
}
~~~

| Unicast A → B | Broadcast A → LAN | Cần điều tra |
|---|---|---|
| Đến | Đến | Socket và đường mạng có thể hoạt động; chuyển sang kiểm tra flow Spring |
| Đến | Không | Broadcast address, `SO_BROADCAST`, Wi-Fi/AP, VLAN, firewall broadcast |
| Không | Không | IP/port sai, process chưa lắng nghe, firewall hoặc kết nối LAN |
| Không | Đến | Khác biệt đích/route hoặc firewall theo đích; cần capture xác nhận |

Unicast thành công chỉ chứng minh **đường unicast** hoạt động; các mạng có thể áp dụng chính sách khác cho broadcast.

### 6.5. Packet capture ở hai đầu

Trên máy Linux có quyền kiểm tra mạng:

~~~bash
sudo tcpdump -ni any 'udp port 12019'
~~~

Xác nhận tuần tự: **A phát trên interface nào**, **B có thấy packet ở NIC không**, **socket B có chuyển payload vào Spring MessageChannel không**. Capture ở NIC có thể thấy datagram bị firewall chặn trước khi process nhận, nên đừng coi việc capture được packet là bằng chứng business handler đã xử lý.

Với Windows, dùng công cụ capture phù hợp theo quyền được phép. Không sửa code Spring khi packet chưa đến interface receiver.

## 7. Phản hồi DISCOVER bằng unicast: yêu cầu riêng

Khi một receiver gửi OFFER, nó nên trả đến **địa chỉ/cổng UDP nguồn được quan sát**, không phát ngược một bản tin OFFER lớn qua broadcast.

~~~mermaid
flowchart TD
    A["DISCOVER broadcast"] --> B["Receiver validate requestId/schema"]
    B --> C{"Nguồn hợp lệ và còn quota?"}
    C -->|Không| X["Bỏ qua + metric"]
    C -->|Có| D["Tạo OFFER nhỏ"]
    D --> E["UDP unicast tới source IP:port"]
    E --> F["Sender gom kết quả theo requestId"]
~~~

Spring Integration inbound có thể đưa địa chỉ nguồn qua `IpHeaders.PACKET_ADDRESS`. Một outbound handler có `destinationExpression`/Java DSL tương ứng có thể định tuyến tới địa chỉ đó, miễn là header được giữ và đích đã được kiểm tra theo chính sách.

**Các nguyên tắc an toàn của giao thức discovery:**

1. Giới hạn kích thước DISCOVER và OFFER, version, định dạng request ID và phạm vi host được phép.
2. Chỉ trả lời những nguồn đã được xác thực/cho phép khi hệ thống yêu cầu; IP nguồn UDP có thể bị giả mạo.
3. Giới hạn một hoặc số lượng phản hồi nhỏ cho mỗi `requestId + deviceId`.
4. Thêm random delay/jitter trong môi trường có nhiều receiver để tránh hàng trăm OFFER dồn cùng lúc.
5. Sender thu OFFER trong **cửa sổ thời gian hữu hạn**, bỏ phản hồi sai request ID hoặc đến trễ.
6. Chống trùng theo `requestId + deviceId`, không chỉ dựa vào IP:port động.
7. Khi muốn lấy thông tin chi tiết hoặc dữ liệu nhạy cảm, chuyển sang unicast với xác thực thay vì đưa tất cả lên broadcast.

Việc không thấy OFFER **không chứng minh thiết bị offline**: DISCOVER có thể mất, OFFER có thể mất, receiver có thể từ chối hoặc bị firewall chặn.

## 8. Các giới hạn UDP ảnh hưởng tới broadcast

| Đặc tính | Hệ quả |
|---|---|
| UDP không có ACK mặc định | Sender không biết máy nào nhận được broadcast |
| Datagram có thể mất | Một host nhận, host khác không nhận là điều có thể xảy ra |
| Không đảm bảo thứ tự | Nhiều DISCOVER hoặc OFFER có thể đến khác thứ tự gửi |
| Không tự chống trùng | Sender retry có thể làm receiver xử lý lại cùng request ID |
| Không backpressure end-to-end | Broadcast quá dày có thể gây ngập LAN, socket buffer hoặc handler |
| Kích thước datagram có giới hạn | Gói lớn có nguy cơ phân mảnh, mất, bị truncate |
| Không có durable subscription | Host bật sau lúc broadcast sẽ không tự nhận lại gói đã bỏ lỡ |

**`check-length` của Spring Integration** thêm tiền tố độ dài **4 byte** khi hai phía cùng cấu hình. Nó giúp phát hiện một số trường hợp datagram bị cắt ngắn, **không phát lại gói đã mất** và không đảm bảo những máy chạy UDP server bên thứ ba tự hiểu prefix.

Tùy chọn `acknowledge` của Spring Integration UDP dành cho các endpoint hiểu cùng giao thức ACK. Không suy luận nó sẽ tạo xác nhận từ **mọi máy trong broadcast domain** hoặc đảm bảo transaction của từng thiết bị đã commit.

## 9. Bảo mật và hiệu năng

Broadcast có thể khiến nhiều host phải xử lý packet dù không phải tất cả đều quan tâm đến dữ liệu. Những rủi ro cần chú ý:

- **UDP reflection/amplification:** sender giả mạo IP nguồn có thể khiến nhiều receiver gửi phản hồi đến nạn nhân. Không trả OFFER lớn hoặc không giới hạn cho nguồn chưa xác thực.
- **Broadcast storm:** nhiều sender liên tục phát DISCOVER có thể tăng tải LAN, AP và mọi receiver. Áp dụng rate limit/backoff và giới hạn số lần thử.
- **Source spoofing:** `ip_address` và `ip_port` chỉ là thông tin nguồn mạng, không phải bằng chứng định danh.
- **Payload nhạy cảm:** UDP thuần không mã hóa; không đưa mật khẩu, token, dữ liệu khách hàng lên broadcast.
- **Parser không tin cậy:** kiểm tra giới hạn byte, UTF-8, version, cấu trúc và số trường trước khi gọi nghiệp vụ.
- **Log/metric quá tải:** không log toàn bộ bytes của mỗi gói hoặc tạo label theo mọi IP:port; nên ghi count, error class và sample có giới hạn.
- **Routing sai subnet:** không cho người dùng không tin cậy tự nhập bất kỳ broadcast address nào để phát gói vào mạng tùy ý.

Metric gợi ý: `broadcast_send_attempt_total`, `udp_inbound_total`, `discovery_invalid_total`, `discovery_reply_total`, `discovery_timeout_total`, `discovery_unique_devices`. Phân biệt rõ **số lần gửi**, **số datagram receiver nhận**, **số request hợp lệ** và **số thiết bị phản hồi duy nhất**.

## 10. Vòng đời và triển khai thực tế

Spring Integration quản lý vòng đời inbound/outbound endpoint trong `ApplicationContext`. Khi inbound UDP adapter chưa start/listening hoặc đang stop/restart, datagram đến có thể bị bỏ mà sender không có tín hiệu rõ ràng.

Trong triển khai thực:

- Kiểm tra port UDP được expose, địa chỉ bind và trạng thái `UdpServerListeningEvent`/`isListening()` của adapter ở phiên bản đang dùng.
- Socket nên có interface/bind phù hợp; bind chỉ loopback có thể không nhận broadcast từ LAN.
- Khi dùng Docker/Kubernetes, không giả định bridge/VPC/CNI sẽ forward broadcast; nhiều nền tảng giới hạn hoặc không hỗ trợ.
- Kiểm tra Wi-Fi client isolation, VLAN, broadcast filtering và firewall của từng máy.
- Với máy có nhiều NIC, xác định rõ broadcast address, route/interface thực sự sử dụng.
- Khi dừng service, không kỳ vọng broadcast trước đó được lưu trong mạng để gửi lại khi ứng dụng start.
- Nếu cần khám phá liên mạng, chạy một agent trong từng subnet hoặc dùng registry/broker thay cho mở broadcast forwarding qua router.

`SO_TIMEOUT` của socket nhận chỉ là thời gian chờ một lần `receive()`, không biến UDP thành giao thức có ACK/retry. `MessageChannel` cũng không thể phục hồi một datagram vốn chưa đến socket.

## 11. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Sender báo gửi thành công, receiver không log | Gửi sai subnet, firewall, AP/VLAN hoặc chưa listen | Tính lại broadcast, capture hai máy |
| PowerShell/Java gửi broadcast lỗi | Socket không bật `SO_BROADCAST`, policy OS | Bật `EnableBroadcast`/`setBroadcast(true)`, đọc exception |
| Máy A tự nhận broadcast nhưng B không | Local loopback khác đường LAN thật | Kiểm thử qua hai host và packet capture |
| Unicast nhận được, broadcast không | Network lọc broadcast hoặc sai broadcast IP | Kiểm tra IP/mask, switch, WLAN, OS firewall |
| Broadcast tới B nhưng Spring handler không thấy | Adapter chưa listening, bind sai interface, channel không có subscriber | Kiểm tra lifecycle, cổng và mapping |
| Một số máy nhận, một số không | Khác VLAN/subnet, firewall hoặc Wi-Fi isolation | So sánh topology, IP/prefix, packet capture từng máy |
| DISCOVER nhận, không thấy OFFER | Chưa triển khai response, trả sai source port, response bị chặn | Kiểm tra `ip_packetAddress`, capture unicast response |
| Payload bắt đầu bằng byte lạ | Sender bật length check nhưng receiver raw | Đồng bộ framing `check-length` |
| Khi nhiều host phản hồi thì quá tải | Response implosion, thiếu jitter/rate limit | Giới hạn tốc độ/phản hồi và deadline |
| Broadcast chạy trên LAN nhưng lỗi ở cloud | CNI/VPC không truyền broadcast | Dùng service registry, HTTP, broker hoặc discovery agent |

Điều tra theo thứ tự **sender serialize → outbound handler → socket gửi → receiver NIC → socket nhận → inbound adapter → MessageChannel → handler**. Log ở bước trước không tự chứng minh bước sau.

## 12. Bài thực hành tổng hợp

Thiết lập ít nhất hai máy A/B trong LAN được phép thử, có một UDP listener tại `12019`. Nếu có thêm máy C, dùng để quan sát fan-out.

**Phần A — Mạng và broadcast**

1. Đọc IP/prefix của NIC A và tính directed broadcast. Với `192.168.10.23/24`, kết quả phải là `192.168.10.255`.
2. Chạy PowerShell listener trên B và gửi một DISCOVER từ A bằng `EnableBroadcast = true`.
3. So sánh unicast A → B trên cùng port; dùng bảng khoanh vùng để giải thích khi chỉ unicast thành công.
4. Dùng packet capture xác nhận source/destination, interface và loại packet tại B.
5. Thử khi B bị tắt listener, sau đó bật lại. Gói trước đó **không được replay tự động**.

**Phần B — Spring Integration**

1. Tạo `broadcastOut` và `broadcastIn`, cấu hình Java DSL inbound/outbound như ví dụ.
2. Gửi một `Message<byte[]>` từ `DiscoveryPublisher` vào `broadcastOut`.
3. Kiểm tra `DiscoveryReceiver` xác thực size, UTF-8 và schema.
4. Ghi source IP/port từ header nhận; giải thích vì sao port nguồn không phải port listener.
5. Tạo một OFFER ngắn bằng unicast tới sender trong lab, kiểm soát tốc độ và request ID.
6. Thử payload sai schema, 513 byte và byte UTF-8 không hợp lệ, ghi metric lỗi.

**Phần C — Thiết kế và vận hành**

1. Giả lập 30 receiver gửi OFFER cùng lúc; đề xuất jitter, deadline và dedup.
2. Đưa B sang VLAN khác: giải thích vì sao broadcast không tự vượt router và thiết kế một agent/registry.
3. Thiết kế phương án discovery nếu mạng chỉ dùng IPv6.
4. So sánh broadcast, multicast, unicast và broker khi yêu cầu không được mất một sự kiện.
5. Nếu dữ liệu đầu vào là file/SFTP/DB do poller đọc, xác định poller nằm ở bước nào trước outbound adapter.

**Câu hỏi tự đánh giá:**

- Vì sao không thể đoán broadcast IP chỉ từ ba octet đầu của địa chỉ host?
- `255.255.255.255` khác địa chỉ broadcast cụ thể của subnet ra sao?
- `UnicastSendingMessageHandler` có thể gửi đến IPv4 broadcast address khi nào?
- `SO_BROADCAST=true` có đảm bảo mọi receiver đã nhận datagram không?
- Vì sao IPv4 multicast yêu cầu group membership còn broadcast thì không?
- Vì sao UDP broadcast thường không đi qua VLAN/router khác?
- Điều gì xảy ra khi hàng trăm receiver cùng trả lời OFFER?
- Vì sao nguồn IP/port không đủ làm định danh thiết bị?
- Nếu cần discovery trong mạng IPv6-only, nên thay đổi cơ chế gì?
- Khi nào cần chuyển từ broadcast discovery sang service registry hoặc broker?

## 13. Tài liệu tham khảo

- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): Java/DSL inbound/outbound, socket customizer, `check-length` và ACK.
- [Spring Integration Reference — TCP and UDP Support](https://docs.spring.io/spring-integration/reference/ip.html): vị trí UDP adapter trong mô hình endpoint.
- [Java DatagramSocket API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/DatagramSocket.html): `setBroadcast`, `SO_BROADCAST`, bind và receive.
- [RFC 919 — Broadcasting Internet Datagrams](https://www.rfc-editor.org/rfc/rfc919): nguyên tắc broadcast IPv4.
- [RFC 922 — Broadcasting Internet Datagrams in the Presence of Subnets](https://www.rfc-editor.org/rfc/rfc922): broadcast và subnet.
- [RFC 2644 — Default for Directed Broadcasts in Routers](https://www.rfc-editor.org/rfc/rfc2644): giới hạn chuyển tiếp directed broadcast.
- [RFC 8085 — UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085): tải, độ tin cậy, kích thước và an toàn khi dùng UDP.

## Kết luận

**IPv4 broadcast** cho phép một sender phát datagram đến phạm vi subnet để nhiều host có cơ hội nhận khi network, socket và firewall cho phép. Trong Spring Integration, ta dùng **UDP outbound adapter hướng tới broadcast address**, cấu hình **`SO_BROADCAST`** và các inbound adapter đưa `Message<byte[]>` vào `MessageChannel` để kiểm tra và xử lý.

Broadcast phù hợp cho discovery trong LAN nhỏ, nhưng **không đảm bảo tất cả thiết bị đã nhận**, không tự hoạt động xuyên VLAN/subnet và không có ACK, lưu bền hay replay. Hãy tính broadcast theo IP/mask thực tế, kiểm tra trên hai host, hạn chế phản hồi và tốc độ, giữ payload nhỏ, xác thực nguồn khi cần; với phạm vi rộng hoặc dữ liệu quan trọng, chọn unicast, multicast, service registry hoặc broker phù hợp.
