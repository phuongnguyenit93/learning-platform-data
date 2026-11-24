# Unicast và multicast datagram trong Spring Integration

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt rõ **UDP unicast** và **UDP multicast** theo đích nhận, phạm vi phân phối, khả năng mở rộng và cách cấu hình.
- Hiểu mối quan hệ giữa **datagram**, địa chỉ IP, cổng UDP, **multicast group**, network interface, TTL và đường đi của gói trong mạng.
- Thiết lập các luồng inbound/outbound UDP unicast và multicast bằng **Spring Integration Java DSL**.
- Giải thích vì sao một lần gửi multicast không có nghĩa tất cả thành viên trong nhóm đã nhận gói.
- Thử nghiệm trên localhost/LAN, chẩn đoán lỗi membership, IGMP, firewall, buffer và định dạng payload.
- Chọn mô hình gửi phù hợp cho dữ liệu nghiệp vụ trong hệ thống tích hợp.

Bài này thuộc chương **Adapter UDP** của module **SPRING_INTEGRATION_ADAPTERS**. Module dùng adapter, gateway, poller và `MessageChannel` để nối các hệ thống ngoài với Spring Integration; các luồng có thể kết hợp file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Với UDP, điều quan trọng không chỉ là thêm một adapter, mà là xác định **ai nhận datagram**, **mạng có chuyển datagram tới họ không** và **ứng dụng xử lý việc mất gói như thế nào**.

## 1. Datagram UDP: đơn vị truyền của cả hai mô hình

UDP truyền dữ liệu theo **datagram**. Mỗi lần sender gửi một datagram, hệ điều hành tạo gói UDP gồm thông tin cổng nguồn, cổng đích, độ dài, checksum và phần payload. Receiver có thể đọc một datagram bằng một lần nhận, tùy kích thước bộ đệm.

Ví dụ, ứng dụng gửi payload UTF-8:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

Trong Spring Integration, **UDP outbound channel adapter** nhận `Message` từ input `MessageChannel` và gửi datagram; **UDP inbound channel adapter** nhận datagram rồi phát `Message` đến output channel. Payload thường được xử lý ở dạng `byte[]` trước khi giải mã.

Những tính chất nền tảng của UDP áp dụng cho **cả unicast và multicast**:

- **Không thiết lập phiên kết nối** như TCP; datagram có thể được gửi ngay khi biết địa chỉ đích.
- **Không cam kết giao hàng, đúng thứ tự hay đúng một lần**; gói có thể mất, đến muộn hoặc bị xử lý trùng ở tầng ứng dụng.
- **Không có backpressure end-to-end**. Receiver hoặc mạng quá tải có thể bỏ gói, sender thường không biết.
- **Giữ ranh giới datagram**. Phía nhận không phải tự tìm ký tự phân cách của stream như TCP, nhưng vẫn phải hiểu schema của payload.
- **Giới hạn độ dài**. Datagram quá lớn dễ bị phân mảnh IP hoặc cắt ngắn khi receiver cấp buffer không đủ.

Từ góc nhìn nghiệp vụ, việc outbound handler gửi thành công **không phải** xác nhận rằng receiver đã nhận, giải mã hoặc lưu dữ liệu.

## 2. Unicast: một đích mạng xác định

**Unicast** là gửi UDP datagram từ một endpoint tới **một địa chỉ IP đích và một cổng đích**.

~~~mermaid
flowchart LR
    A["Ứng dụng A<br/>UDP sender"] -->|"Datagram tới 192.0.2.20:12001"| B["Ứng dụng B<br/>UDP receiver"]
    C["Ứng dụng C"]:::muted
    classDef muted fill:#f4f4f4,stroke:#999
~~~

Ví dụ: collector trên máy `192.0.2.20` lắng nghe UDP cổng `12001`. Sender cấu hình đúng cặp `(192.0.2.20, 12001)` rồi phát một datagram đến địa chỉ đó. Nếu có 10 collector khác nhau và mỗi collector cần một bản sao, sender hoặc một thành phần trung gian phải thực hiện việc gửi đến từng đích riêng.

Unicast thường thích hợp với:

- Telemetry từ cảm biến tới collector cố định.
- Lệnh hoặc sự kiện gửi đến **một** thiết bị đích đã biết.
- Trao đổi qua mạng có định tuyến IP bình thường, không hỗ trợ multicast.
- Mô hình cần quản lý danh sách đích và xác nhận riêng cho từng thiết bị ở tầng ứng dụng.

**Lưu ý:** “một đích” mô tả địa chỉ IP và port ở tầng mạng. Nó không đồng nghĩa có đúng một process đang dùng cổng đó trong mọi cấu hình hệ điều hành và mạng, cũng không bảo đảm process đích đã xử lý datagram.

## 3. Multicast: một địa chỉ nhóm, nhiều người nhận tham gia

**Multicast** là mô hình sender gửi một datagram tới **địa chỉ nhóm multicast**. Các receiver muốn nhận phải **join group** trên interface mạng thích hợp và lắng nghe cổng tương ứng. Hạ tầng mạng quyết định việc phân phối gói tới những interface có thành viên nhóm.

Ví dụ cho IPv4: nhóm `239.10.20.30`, cổng `12002`.

~~~mermaid
flowchart LR
    S["Spring Integration<br/>multicast sender"] -->|"UDP tới 239.10.20.30:12002"| N["Switch / Router<br/>có hỗ trợ multicast"]
    N --> A["Receiver A<br/>join group"]
    N --> B["Receiver B<br/>join group"]
    C["Receiver C<br/>không join group"]:::muted
    classDef muted fill:#f4f4f4,stroke:#999
~~~

Trong một mạng hỗ trợ multicast, sender **không nhất thiết phải gửi riêng** một datagram cho mỗi receiver. Router/switch có thể nhân bản lưu lượng dọc đường phù hợp để đưa đến nhiều nơi. Vì vậy multicast hữu ích khi nhiều ứng dụng cần **cùng một luồng thông tin**.

### 3.1. Địa chỉ multicast IPv4

IPv4 dành dải **224.0.0.0/4** cho multicast (224.0.0.0 đến 239.255.255.255). Địa chỉ mẫu `239.10.20.30` nằm trong dải **239.0.0.0/8** dành cho *administratively scoped multicast*, thường được quản trị cho mạng nội bộ tổ chức.

Không chọn tùy tiện địa chỉ trong các dải multicast được dành riêng cho giao thức mạng hoặc dịch vụ đặc biệt. Khi triển khai, cần phối hợp với quản trị mạng để cấp nhóm, cổng và phạm vi sử dụng. Bài này dùng **IPv4** để minh họa; IPv6 cũng có multicast nhưng cách biểu diễn địa chỉ và scope khác.

### 3.2. Join group là bước của receiver

Join group thể hiện mong muốn nhận gói theo một địa chỉ nhóm, thường kèm **network interface** cụ thể. Trong IPv4, cơ chế như **IGMP** giúp host thông báo membership với mạng; switch có IGMP snooping và multicast router có thể dựa vào membership/routing để chuyển tiếp gói.

**Địa chỉ group không thay thế cổng UDP**: receiver cần join đúng nhóm và nhận trên cổng mà sender dùng. Một host có nhiều NIC cũng phải chọn đúng interface, nhất là khi vừa có Wi-Fi, Ethernet, VPN và mạng container.

### 3.3. TTL giới hạn phạm vi phát tán

Multicast outbound có thể đặt **TTL (Time To Live)**. Trong IPv4, mỗi router chuyển tiếp làm giảm TTL; TTL thấp giúp giới hạn phạm vi multicast. TTL **1** thường dành cho mạng cục bộ, nơi không cần router chuyển tiếp gói sang mạng khác. Muốn đi qua nhiều subnet phải có multicast routing cho phép, không chỉ tăng TTL.

TTL là **giới hạn phạm vi định tuyến**, không phải cơ chế bảo mật: receiver ở phạm vi được phép vẫn có thể quan sát payload nếu có đường mạng và quyền truy cập thích hợp.

## 4. Bảng so sánh unicast và multicast

| Tiêu chí | Unicast | Multicast |
|---|---|---|
| Địa chỉ đích | IP của một host cụ thể | IP của nhóm multicast |
| Receiver chủ động join group? | Không | Có, trên interface thích hợp |
| Một lần gửi cho nhiều receiver | Thường phải gửi lặp theo danh sách đích | Mạng có thể phân phối bản sao cho thành viên |
| Phụ thuộc hạ tầng mạng | IP routing và firewall bình thường | Membership, multicast forwarding, IGMP/snooping, cấu hình NIC |
| Sử dụng trên Internet/cloud | Thường dễ triển khai hơn | Có thể bị chặn hoặc không hỗ trợ bởi cloud/VPN/CNI |
| Sender biết ai đang nghe? | Biết địa chỉ đích cấu hình, không biết xử lý thành công | Không tự biết danh sách hay số receiver thực nhận |
| UDP có đảm bảo giao hàng? | Không | Không |
| Phù hợp | Gửi tới một collector/thiết bị | Phát cùng telemetry/config/thông báo đến một nhóm receiver |
| ACK nghiệp vụ cho từng receiver | Có thể thiết kế theo từng đích | Cần tính đến nhiều phản hồi, số lượng thành viên, duplicate/timeout |

### Multicast không phải broadcast

**Broadcast IPv4** gửi tới một phạm vi địa chỉ broadcast (ví dụ broadcast trong một subnet), các host của phạm vi có thể nhìn thấy tùy cấu hình. **Multicast** dùng địa chỉ nhóm và cơ chế membership. Hai hình thức này có mục tiêu, cách định tuyến và hành vi switch khác nhau.

Multicast cũng khác **publish/subscribe trên Kafka hoặc AMQP**: broker có thể quản lý subscriber, lưu trữ sự kiện và chính sách giao hàng. IP multicast chỉ truyền datagram trên mạng, không tự tạo consumer group, offset, durable queue hay cơ chế xử lý lại.

## 5. Unicast/multicast trong Spring Integration

Spring Integration cung cấp hai hướng nhận và hai hướng gửi:

| Hướng | Unicast | Multicast |
|---|---|---|
| Inbound | `UnicastReceivingChannelAdapter` | `MulticastReceivingChannelAdapter` |
| Outbound | `UnicastSendingMessageHandler` | `MulticastSendingMessageHandler` |
| Java DSL inbound | `Udp.inboundAdapter(port)` | `Udp.inboundMulticastAdapter(port, group)` |
| Java DSL outbound | `Udp.outboundAdapter(host, port)` | `Udp.outboundMulticastAdapter(group, port)` |

Bốn thành phần này là các **adapter/message handler** nối UDP vào mô hình message của Spring Integration. Các `MessageChannel` phía sau inbound hoặc phía trước outbound vẫn hoạt động theo semantics đã chọn như `DirectChannel`, `ExecutorChannel`, `QueueChannel`.

~~~mermaid
flowchart TB
    O["Nguồn ứng dụng: HTTP / file / Kafka / DB"] --> C["MessageChannel: toUdp"]
    C --> OUT["UDP outbound adapter"]
    OUT -->|"unicast hoặc multicast datagram"| NET["Mạng IP"]
    NET --> IN["UDP inbound adapter"]
    IN --> C2["MessageChannel: fromUdp"]
    C2 --> H["Validate / Transform / Service Activator"]
~~~

**Poller không dùng để “quét” datagram đang đến**: inbound UDP adapter tự nhận theo sự kiện của socket. Nhưng nguồn dữ liệu phía đầu luồng có thể dùng poller, chẳng hạn quét file hoặc database định kỳ rồi gửi mỗi bản ghi thành một UDP datagram.

**Lưu ý phiên bản import Java:** Spring Integration 7.x tổ chức các class nhận và gửi trong package `org.springframework.integration.ip.udp.inbound` và `org.springframework.integration.ip.udp.outbound`. Ở 6.x, các class này ở package `org.springframework.integration.ip.udp`. Ví dụ tiếp theo dùng **Java DSL** để tập trung vào cách ghép luồng và giảm phụ thuộc vào thay đổi package của class triển khai.

## 6. Thực hành Spring Integration bằng Java DSL

### 6.1. Dependency và hợp đồng dữ liệu

Với dự án Spring Boot quản lý dependency, thêm:

~~~xml
<!-- Khai báo trong <dependencies> của pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

Định nghĩa gói đơn giản ở dạng UTF-8, tối đa **512 byte**:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

Trong ứng dụng thực tế, hãy parse schema thành đối tượng nghiệp vụ, kiểm tra độ dài và giá trị, thêm version/sequence khi cần theo dõi mất/trùng/đảo thứ tự. `MessageHeaders` của Spring Integration không tự được chép thành trường dữ liệu ở datagram: thông tin nào receiver cần phải có quy ước truyền rõ ràng.

### 6.2. Cấu hình inbound và outbound đồng thời

Cấu hình dưới đây tạo **hai đường nhận** và **hai đường gửi**. Dùng cổng khác nhau để dễ quan sát khi học:

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
public class UdpDatagramFlows {

    public static final int UNICAST_PORT = 12001;
    public static final int MULTICAST_PORT = 12002;
    public static final String GROUP = "239.10.20.30";

    @Bean("fromUnicast")
    public MessageChannel fromUnicast() {
        return new DirectChannel();
    }

    @Bean("fromMulticast")
    public MessageChannel fromMulticast() {
        return new DirectChannel();
    }

    @Bean("toUnicast")
    public MessageChannel toUnicast() {
        return new DirectChannel();
    }

    @Bean("toMulticast")
    public MessageChannel toMulticast() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow unicastInboundFlow() {
        return IntegrationFlow.from(Udp.inboundAdapter(UNICAST_PORT))
                .channel("fromUnicast")
                .get();
    }

    @Bean
    public IntegrationFlow multicastInboundFlow() {
        return IntegrationFlow.from(
                    Udp.inboundMulticastAdapter(MULTICAST_PORT, GROUP))
                .channel("fromMulticast")
                .get();
    }

    @Bean
    public IntegrationFlow unicastOutboundFlow() {
        return IntegrationFlow.from("toUnicast")
                .handle(Udp.outboundAdapter("127.0.0.1", UNICAST_PORT))
                .get();
    }

    @Bean
    public IntegrationFlow multicastOutboundFlow() {
        return IntegrationFlow.from("toMulticast")
                .handle(Udp.outboundMulticastAdapter(GROUP, MULTICAST_PORT))
                .get();
    }
}
~~~

Đây là cấu hình **minh họa chạy trên một ứng dụng**; khi triển khai sender và receiver độc lập, mỗi service chỉ cần phần endpoint thuộc vai trò của mình. Địa chỉ `127.0.0.1` chỉ trỏ về host/container **đang chạy sender**, không trỏ tới tất cả thiết bị trên mạng.

Các bước chính:

1. `Udp.inboundAdapter(12001)` mở unicast listener trên UDP port 12001.
2. `Udp.inboundMulticastAdapter(12002, GROUP)` tạo listener tham gia nhóm multicast và nhận trên port 12002.
3. `Udp.outboundAdapter(...)` gửi datagram đến một IP/port.
4. `Udp.outboundMulticastAdapter(...)` gửi datagram đến nhóm/port.
5. Các channel `fromUnicast`, `fromMulticast`, `toUnicast`, `toMulticast` nối phần mạng với phần nghiệp vụ.

Khi chạy trên máy có nhiều network interface, có thể phải **chỉ định địa chỉ/interface** cho multicast theo môi trường. Cấu hình mặc định có thể chọn NIC không mong muốn, đặc biệt khi có VPN hoặc container network.

### 6.3. Service Activator xử lý datagram nhận được

~~~java
import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class UdpDatagramConsumer {

    private static final Logger log =
            LoggerFactory.getLogger(UdpDatagramConsumer.class);

    @ServiceActivator(inputChannel = "fromUnicast")
    public void onUnicast(Message<byte[]> message) {
        show("unicast", message.getPayload());
    }

    @ServiceActivator(inputChannel = "fromMulticast")
    public void onMulticast(Message<byte[]> message) {
        show("multicast", message.getPayload());
    }

    private void show(String type, byte[] payload) {
        if (payload.length == 0 || payload.length > 512) {
            log.warn("Discard {} datagram of size {}", type, payload.length);
            return;
        }

        String value = new String(payload, StandardCharsets.UTF_8);
        log.info("Received {}: {}", type, value);
    }
}
~~~

Đoạn này chỉ minh họa chuyển bytes thành log. Để dùng trong production, cần **decode UTF-8 nghiêm ngặt**, xác thực schema, giá trị và thiết bị, giới hạn log, phân loại lỗi/metric và xử lý duplicate nếu bản ghi không được phép trùng. Receiver không nên coi bất kỳ gói nào từ network là dữ liệu tin cậy.

### 6.4. Publisher lựa chọn unicast hoặc multicast

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class UdpDatagramPublisher {

    private final MessageChannel unicast;
    private final MessageChannel multicast;

    public UdpDatagramPublisher(
            @Qualifier("toUnicast") MessageChannel unicast,
            @Qualifier("toMulticast") MessageChannel multicast) {
        this.unicast = unicast;
        this.multicast = multicast;
    }

    public boolean sendUnicast(String telemetry) {
        return send(unicast, telemetry);
    }

    public boolean sendMulticast(String telemetry) {
        return send(multicast, telemetry);
    }

    private boolean send(MessageChannel channel, String telemetry) {
        byte[] bytes = telemetry.getBytes(StandardCharsets.UTF_8);
        if (bytes.length == 0 || bytes.length > 512) {
            throw new IllegalArgumentException("UDP payload length invalid");
        }
        return channel.send(MessageBuilder.withPayload(bytes).build());
    }
}
~~~

Từ controller, scheduler hoặc consumer Kafka, ứng dụng gọi `sendUnicast(...)` hay `sendMulticast(...)` theo đối tượng nhận. Giá trị `true` từ `MessageChannel.send` cho biết message đã được dispatch theo semantics của channel; **không chứng minh receiver UDP đã nhận**.

Đừng để API client chọn trực tiếp nhóm multicast, host/port hoặc interface nếu chưa kiểm tra quyền và danh sách đích được phép.

## 7. Một cấu hình tương đương bằng XML

Nếu dự án sử dụng Spring Integration namespace XML, có thể cấu hình inbound/outbound multicast như sau:

~~~xml
<int-ip:udp-inbound-channel-adapter
    id="multicastInput"
    channel="multicastReceived"
    port="12002"
    multicast="true"
    multicast-address="239.10.20.30"
    receive-buffer-size="2048"/>

<int-ip:udp-outbound-channel-adapter
    id="multicastOutput"
    channel="multicastToSend"
    host="239.10.20.30"
    port="12002"
    multicast="true"
    time-to-live="1"/>

<int:channel id="multicastReceived"/>
<int:channel id="multicastToSend"/>
~~~

Đây là **đoạn cấu hình** cần được đặt vào XML Spring Integration với namespace `int` và `int-ip` đúng phiên bản. Handler phía sau `multicastReceived` vẫn cần được định nghĩa để xử lý message. Thuộc tính `multicast="true"` và `multicast-address` ở inbound khiến listener tham gia group; ở outbound, `host` chính là địa chỉ nhóm.

Với unicast, sử dụng `multicast="false"` (hoặc mặc định phù hợp), `host` của máy đích và `port` lắng nghe, không yêu cầu group address.

## 8. Kiểm thử và quan sát trên máy thật

### 8.1. Kiểm thử unicast trên một máy

Chạy Spring Boot receiver với `unicastInboundFlow` và mở PowerShell trên **cùng máy**:

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new()
try {
    $text = "v=1;sensor=node-7;seq=1;tempC=26.5"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    [void]$client.Send($bytes, $bytes.Length, "127.0.0.1", 12001)
}
finally {
    $client.Dispose()
}
~~~

Khi adapter đang lắng nghe, log mong đợi:

~~~text
Received unicast: v=1;sensor=node-7;seq=1;tempC=26.5
~~~

Nếu không thấy log, trước hết xác minh receiver đã start, cổng 12001 chưa bị ứng dụng khác chiếm, handler `fromUnicast` được đăng ký và firewall không chặn gói.

### 8.2. Kiểm thử multicast trong LAN

Kiểm thử multicast đáng tin cậy hơn khi có **hai máy trong cùng LAN** (hoặc môi trường ảo hóa đã xác nhận hỗ trợ multicast):

1. Cho receiver A và receiver B cùng join `239.10.20.30:12002` trên interface đúng. Mỗi receiver có thể là một instance Spring Boot với `multicastInboundFlow`.
2. Cho sender phát một datagram bằng `sendMulticast("v=1;...")`.
3. Đối chiếu log ở **cả A và B**, kèm packet capture tại từng host nếu cần.
4. Tắt receiver B hoặc leave group; gửi tiếp và kiểm tra A vẫn nhận bình thường.
5. Cho một host C **không join group**; không dựa vào việc C có thể capture ở chế độ promiscuous để suy ra C là subscriber hợp lệ.
6. Tăng tốc độ gửi và thêm `seq` để tính tỷ lệ thiếu gói ở từng receiver.

Không kết luận multicast hỏng chỉ vì gửi và nhận trong cùng process không thấy log: nhiều hệ điều hành, card mạng, Docker/VPN hoặc chính sách **multicast loopback** có hành vi khác nhau. Kiểm tra thêm các máy thật trên cùng LAN trước khi điều chỉnh code.

### 8.3. Quan sát gói UDP trên mạng

Ở máy nhận Linux có thể dùng công cụ capture hợp lệ để đối chiếu group và port, ví dụ:

~~~bash
sudo tcpdump -ni any 'udp and (port 12001 or port 12002)'
~~~

Để kiểm tra riêng multicast cần quan sát địa chỉ đích `239.10.20.30`, nguồn gửi và interface nhận. Bản thân packet capture có thể thấy gói trước khi socket của ứng dụng nhận; vì vậy vẫn phải kiểm tra **log handler, group membership và buffer**.

Các chỉ số hữu ích gồm:

| Metric | Ý nghĩa |
|---|---|
| `udp_send_attempt_total` | Số lần ứng dụng gọi gửi datagram |
| `udp_send_error_total` | Lỗi đồng bộ khi encode/dispatch/send |
| `udp_receive_total{mode="unicast|multicast"}` | Số datagram inbound adapter chuyển vào luồng |
| `udp_invalid_payload_total` | Số gói bị loại vì schema/dung lượng |
| `udp_processed_total` | Số gói xử lý nghiệp vụ thành công |
| `udp_sequence_gap_total` | Số khoảng sequence thiếu mà receiver quan sát được |

Với multicast, tính metric **riêng cho từng receiver**. Một sender gửi 1.000 gói, receiver A nhận 998 và B nhận 995 là điều có thể xảy ra mà không có lỗi đồng bộ ở sender.

## 9. Các yếu tố mạng quyết định multicast thành công

Multicast không chỉ là một flag trong code.

| Tình huống | Hệ quả | Hướng xử lý |
|---|---|---|
| Receiver join sai group | Không nhận datagram gửi đến group mong đợi | Kiểm tra group address và port giữa hai phía |
| Join đúng group nhưng sai network interface | Socket không có đường nhận đúng | Chỉ định interface/multicast NIC; xem bảng định tuyến |
| TTL = 1 nhưng receiver khác subnet | Router thường không forward gói ra subnet khác | Thiết kế routing multicast, TTL và chính sách mạng |
| Switch có IGMP snooping nhưng không có membership phù hợp | Gói có thể không tới cổng của receiver | Kiểm tra IGMP joins và cấu hình querier/switch |
| Firewall hoặc AP isolation | Host có thể nhìn thấy lưu lượng khác nhưng không nhận multicast mong muốn | Kiểm tra firewall, Wi-Fi/AP, VLAN và network policy |
| Docker/Kubernetes/VPN không hỗ trợ multicast | Code hợp lệ nhưng gói không được chuyển tiếp | Dùng LAN hỗ trợ multicast hoặc giải pháp phân phối khác |
| Payload lớn hơn receive buffer | Datagram có thể bị cắt ngắn | Giảm payload, tăng bộ đệm phù hợp, thống nhất length check |
| Nhiều instance trên một host cùng bind port | Hành vi nhận khác nhau tùy OS/socket options | Xác minh `SO_REUSEADDR`, membership và cách bind trên môi trường thật |

**Không tự động suy luận:** multicast là “fan-out miễn phí” bất kể topology. Multicast tiết kiệm số lần gửi ở sender trong điều kiện mạng phù hợp, nhưng quản trị mạng, các receiver độc lập và khả năng quan sát thường phức tạp hơn unicast.

## 10. Kích thước datagram, length check và ACK

### 10.1. Datagram size và receive buffer

Một datagram UDP trên IPv4 có giới hạn lý thuyết payload khoảng **65.507 byte** (khi không có IP options), nhưng ứng dụng nên chọn kích thước **nhỏ hơn đáng kể** để tránh phân mảnh trên đường mạng. Với telemetry, kích thước vài trăm byte thường đủ; ví dụ bài này giới hạn **512 byte**.

Spring Integration inbound adapter có tùy chọn `receive-buffer-size` phục vụ buffer nhận từng datagram. Cần phân biệt nó với **socket receive buffer** của hệ điều hành. Tăng một buffer không tự giải quyết tình trạng rớt gói do mạng, sender gửi nhanh hoặc nghiệp vụ xử lý chậm.

### 10.2. Length check

Spring Integration UDP cho phép bật **length check**: outbound thêm tiền tố độ dài **4 byte theo network byte order**; inbound tương thích đối chiếu độ dài và phát hiện gói bị cắt ngắn. Phía gửi và nhận phải **cùng thống nhất chế độ**. Một receiver UDP thuần không biết prefix có thể giải mã sai nếu chỉ coi toàn bộ datagram là UTF-8.

Length check không sửa được datagram thất lạc và cũng không bảo đảm thứ tự.

### 10.3. Acknowledgment

Thư viện có hỗ trợ cơ chế **ACK ở tầng ứng dụng** khi cấu hình `acknowledge` và các thuộc tính liên quan. Sender có thể chờ ACK trong một khoảng thời gian; receiver phải hiểu **framing ACK** của Spring Integration.

Với multicast, có thể cấu hình **`min-acks-for-success`** khi bật ACK, nghĩa là sender yêu cầu ít nhất một số phản hồi từ receiver. Điều này **không tự chứng minh tất cả thành viên nhóm đã nhận**, vì sender không có danh sách membership chuẩn xác như broker pub/sub. ACK nhận gói cũng không nhất thiết chứng minh transaction tại receiver đã commit.

Nếu hệ thống bắt buộc gửi đủ mọi bản ghi, hãy thiết kế thêm ID, sequence, retry có kiểm soát, deduplication, lưu bền và ACK nghiệp vụ; cân nhắc JMS/AMQP/Kafka hoặc giải pháp khác nếu cần giao hàng có đảm bảo.

## 11. Bảo mật và giới hạn phạm vi

UDP unicast hoặc multicast đều có rủi ro khi nhận dữ liệu không đáng tin cậy:

- **Multicast group không phải cơ chế xác thực**. Một host có quyền truy cập mạng và cấu hình phù hợp có thể tham gia nhận hoặc gửi gói tới group.
- **TTL không mã hóa payload**, chỉ giới hạn phạm vi định tuyến; không dùng TTL để thay ACL/firewall.
- **IP nguồn có thể bị giả mạo** ở một số môi trường; không xác thực cảm biến bằng source IP đơn thuần.
- **Giới hạn kích thước, schema, phiên bản và lưu lượng** trước khi chuyển tiếp vào pipeline nghiệp vụ.
- Nếu cần chống sửa đổi/replay, thiết kế chữ ký/HMAC hoặc transport bảo vệ phù hợp và kiểm tra timestamp/sequence; UDP thuần không hỗ trợ sẵn.
- Với multicast nội bộ, thống nhất dải group được cấp, VLAN, interface, firewall và nhật ký vận hành với người quản trị mạng.

Không ghi mọi payload vào log ở production, đặc biệt khi telemetry chứa dữ liệu nhạy cảm hoặc tốc độ gửi lớn.

## 12. Khi nào chọn unicast và multicast?

| Tình huống | Lựa chọn gợi ý | Lý do |
|---|---|---|
| Một cảm biến gửi số liệu tới collector cố định | **Unicast** | Cấu hình đơn giản, mạng thông thường, một đích rõ ràng |
| Một máy phát đồng thời dữ liệu thời gian thực cho nhiều màn hình trong cùng LAN | **Multicast** khi mạng hỗ trợ | Một luồng dữ liệu cho nhiều subscriber, giảm gửi lặp |
| Các receiver trải trên nhiều VPC/cloud, VPN/CNI không hỗ trợ multicast | **Unicast hoặc broker** | Dễ định tuyến, xác nhận và vận hành hơn |
| Mỗi receiver cần dữ liệu khác nhau | **Unicast** | Gửi đích riêng và tùy biến payload từng người nhận |
| Mọi subscriber phải nhận đủ dữ liệu và có thể replay | **Broker có lưu bền** | Multicast UDP không có lưu trữ hoặc replay |
| Cần quan sát xác nhận của từng receiver | **Unicast + ACK nghiệp vụ**, hoặc broker | Theo dõi danh sách đích và trạng thái riêng |
| Dữ liệu có thể bị bỏ và chu kỳ sau sẽ thay thế | **Unicast/multicast UDP** tùy topology | Đơn giản, độ trễ thấp khi chấp nhận mất gói |

Các lựa chọn trên phụ thuộc vào **hợp đồng dữ liệu và yêu cầu nghiệp vụ**, không chỉ số lượng receiver. Ngay cả khi nhiều người nhận, multicast chỉ hữu ích nếu mạng thực sự triển khai và vận hành multicast phù hợp.

## 13. Bài thực hành tổng hợp

Thiết kế luồng theo mô hình sau:

~~~mermaid
flowchart TD
    A["Producer: dữ liệu cảm biến"] --> V["Validate + encode UTF-8"]
    V --> R{"Nhóm nhận?"}
    R -->|"1 collector"| U["toUnicast"]
    R -->|"N màn hình trong LAN"| M["toMulticast"]
    U --> OU["Unicast outbound"]
    M --> OM["Multicast outbound"]
    OU --> RU["Collector: UDP 12001"]
    OM --> RA["Màn hình A: join group"]
    OM --> RB["Màn hình B: join group"]
~~~

Yêu cầu:

1. Cấu hình một **unicast receiver** ở cổng 12001 và hai **multicast receivers** cùng join group `239.10.20.30` trên cổng 12002.
2. Gửi 10 datagram có `seq` tăng dần bằng unicast; xác nhận chỉ receiver unicast được đưa dữ liệu vào channel tương ứng.
3. Gửi 10 datagram tương tự bằng multicast; đối chiếu số gói từng receiver nhận được, ghi lại sự khác biệt theo interface/môi trường.
4. Thử tắt một receiver multicast, gửi thêm 10 gói rồi bật lại. Giải thích vì sao receiver đó **không tự nhận lại** các datagram đã bỏ lỡ.
5. Thử group address sai, port sai, interface khác, firewall rule và TTL thấp khi đi qua router. Viết cách phân biệt lỗi code và lỗi mạng.
6. Tăng tốc độ gửi để quan sát số sequence bị thiếu, phân tích receive buffer và tốc độ handler. Đề xuất chiến lược khi không thể chấp nhận mất gói.

**Câu hỏi tự đánh giá:**

- Vì sao một multicast sender không nhất thiết phải biết số lượng receiver?
- Có thể chỉ đổi IP đích từ unicast sang `239.10.20.30` mà receiver tự động thấy dữ liệu không? Vì sao?
- Phân biệt địa chỉ group, UDP port và network interface trong một cấu hình multicast receiver.
- `TTL=1` ảnh hưởng gì khi receiver ở subnet khác?
- Vì sao bật ACK mà vẫn không đủ chứng minh mọi subscriber đã hoàn thành xử lý nghiệp vụ?
- Nếu producer đọc DB bằng poller rồi phát multicast, poller hoạt động ở phần nào của luồng?
- Khi nào multicast UDP không phù hợp dù có tới hàng trăm người tiêu thụ?

## 14. Tài liệu tham khảo

- [Spring Integration Reference — TCP and UDP Support](https://docs.spring.io/spring-integration/reference/ip/intro.html): tổng quan bốn loại adapter UDP.
- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): unicast/multicast inbound/outbound, length check và ACK.
- [Spring Integration Reference — IP Configuration Attributes](https://docs.spring.io/spring-integration/reference/ip/endpoint-reference.html): ý nghĩa `multicast`, `multicast-address`, `time-to-live`, buffer và `min-acks-for-success`.
- [Spring Integration Java DSL — Udp](https://github.com/spring-projects/spring-integration/blob/main/spring-integration-ip/src/main/java/org/springframework/integration/ip/dsl/Udp.java): các factory `inboundAdapter`, `inboundMulticastAdapter`, `outboundAdapter` và `outboundMulticastAdapter`.

## Kết luận

**Unicast** chuyển một UDP datagram đến một địa chỉ đích xác định; **multicast** gửi tới địa chỉ nhóm để nhiều receiver đã join có thể nhận cùng luồng dữ liệu. Cả hai sử dụng UDP nên đều phải chấp nhận hoặc tự xử lý vấn đề mất gói, trùng gói, đảo thứ tự và giới hạn kích thước.

Trong **Spring Integration**, lựa chọn unicast hay multicast được thể hiện ở inbound/outbound UDP adapter, còn việc kiểm tra payload, xử lý lỗi, định tuyến, lưu trữ hoặc tích hợp với HTTP, file, SFTP, JMS, AMQP, Kafka và cơ sở dữ liệu vẫn được nối qua **MessageChannel**. Hãy chọn unicast khi có một đích rõ ràng hoặc cần trạng thái từng receiver; chỉ chọn multicast khi nhu cầu phân phối cùng dữ liệu, hạ tầng mạng và chính sách vận hành đáp ứng được mô hình nhóm.
