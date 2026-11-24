# UDP outbound channel adapter trong Spring Integration

## Mục tiêu học tập

Hoàn thành bài học này, bạn có thể:

- Giải thích cách **UDP outbound channel adapter** chuyển một Spring Integration `Message` thành datagram gửi đến hệ thống ngoài.
- Cấu hình **UnicastSendingMessageHandler**, host, port và input **MessageChannel** bằng Java.
- Chuẩn hóa payload thành `byte[]`, xác lập hợp đồng dữ liệu, quan sát trạng thái gửi và thử nghiệm với UDP listener độc lập.
- Phân biệt việc message được chuyển đến outbound handler với việc phía đích thật sự nhận và xử lý thành công.
- Đánh giá các cơ chế kiểm tra độ dài, ACK, quản lý lỗi, vận hành socket và lựa chọn giữa unicast/multicast.

Bài thuộc chương **Adapter UDP** trong module **SPRING_INTEGRATION_ADAPTERS**. Module này hướng dẫn kết nối hệ thống bên ngoài với Spring Integration thông qua inbound/outbound adapter, gateway, poller và **MessageChannel**, cùng những luồng dùng file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Trong kiến trúc đó, UDP outbound adapter phụ trách đoạn cuối: **chuyển message nội bộ thành gói UDP gửi ra mạng**.

## 1. Bài toán: chuyển sự kiện telemetry sang thiết bị hoặc collector

Giả sử một dịch vụ Spring Boot nhận dữ liệu cảm biến từ database, Kafka hoặc HTTP, sau đó phải gửi số đo mới nhất đến một hệ thống giám sát có giao diện UDP tại `192.0.2.10:9999`. Mỗi sự kiện dùng payload UTF-8:

~~~text
sensor=node-7;tempC=26.5
~~~

Không cần viết `DatagramSocket` ở từng service nghiệp vụ. Ứng dụng gửi `Message<byte[]>` vào **MessageChannel**; outbound endpoint nhận message, tạo datagram và chuyển cho tầng mạng.

~~~mermaid
flowchart LR
    A["HTTP / Kafka / DB / Service"] --> B["Kiểm tra và mã hóa dữ liệu"]
    B -->|"Message<byte[]>"| C["udpOutboundRequests (MessageChannel)"]
    C --> D["UDP outbound adapter"]
    D -->|"UDP datagram"| E["Collector / thiết bị ngoài"]
~~~

**UDP outbound là một chiều.** Adapter không tự tạo một request/reply protocol và không bảo đảm datagram đến đích. Một lệnh gửi không ném lỗi chỉ thể hiện xử lý gửi tại phía ứng dụng và hệ điều hành, không xác nhận việc ghi nhận nghiệp vụ ở máy nhận.

## 2. UDP outbound adapter là gì?

Spring Integration có các endpoint chuyên trách Internet Protocol. Với UDP, thành phần thường dùng là:

- **`UnicastSendingMessageHandler`**: gửi datagram đến một host và port đích.
- **`MulticastSendingMessageHandler`**: gửi datagram đến nhóm multicast nếu hạ tầng mạng và các receiver hỗ trợ multicast.
- **`MessageChannel`**: cung cấp điểm ghép nối giữa producer nội bộ và outbound handler.
- **`Service Activator`**: đăng ký một message handler xử lý message từ input channel. Khi handler là UDP sender, tác vụ xử lý chính là phát datagram.

Không nên nhầm **outbound adapter** với **inbound adapter**: inbound adapter mở listener nhận gói từ mạng và phát `Message` vào luồng; outbound adapter nhận `Message` từ luồng rồi gửi ra mạng.

| Tiêu chí | UDP inbound | UDP outbound |
|---|---|---|
| Nguồn sự kiện | Datagram từ mạng | Message từ ứng dụng |
| Điểm kết nối | Output channel | Input channel |
| Thành phần unicast | `UnicastReceivingChannelAdapter` | `UnicastSendingMessageHandler` |
| Thông tin cốt lõi | Cổng/interface lắng nghe | Host và port đích |
| Kết quả | Message được chuyển vào luồng | Datagram được chuyển cho network stack |
| Có cần poller? | Không, nhận theo gói đến | Không, handler xử lý khi có message; producer ở phía trước *có thể* dùng poller |

Nếu nguồn ở đầu luồng là file hoặc cơ sở dữ liệu được quét định kỳ, **poller thuộc bước lấy dữ liệu nguồn**. Outbound UDP handler không cần lịch poll riêng cho mỗi datagram.

## 3. Kiến thức UDP cần nhớ khi gửi

Mỗi `Message` đến UDP outbound handler thường được ánh xạ thành một **UDP datagram**. Khác với TCP, UDP không có stream kết nối, không bảo đảm thứ tự, không bảo đảm gửi lại và không thực hiện kiểm soát luồng với receiver.

| Đặc tính | Ảnh hưởng thực tế |
|---|---|
| Datagram độc lập | Producer phải định nghĩa ranh giới bản tin, định dạng payload và giới hạn kích thước. |
| Có thể mất gói | Không thể lấy kết quả `send()` làm bằng chứng phía đích đã nhận. |
| Có thể nhận sai thứ tự | Thêm `sequence` hoặc timestamp nghiệp vụ nếu thứ tự quan trọng. |
| Có thể trùng gói | Receiver cần cơ chế idempotency nếu producer có retry hoặc thiết bị phát lại. |
| Không có backpressure tới sender | Gửi quá nhanh có thể làm đầy buffer ở network stack hoặc receiver và mất gói. |
| Kích thước datagram giới hạn | Nên dùng thông điệp nhỏ; tránh phân mảnh IP do gói quá lớn. |
| Không mã hóa và không xác thực | Không nên chuyển dữ liệu nhạy cảm trên UDP thuần qua mạng không đáng tin cậy. |

**Không được suy luận:** “`MessageChannel.send()` trả về `true`, vì vậy UDP đã được nhận tại máy đích.” Với một **DirectChannel**, `true` chỉ cho biết việc dispatch message đến subscriber đã được thực hiện theo contract của channel. Dù outbound handler gửi ra socket thành công, gói vẫn có thể mất giữa đường hoặc bị từ chối ở receiver.

Nếu yêu cầu nghiệp vụ là “bắt buộc nhận đủ từng sự kiện”, hãy cân nhắc một cơ chế giao hàng bền vững hơn (ví dụ HTTP với phản hồi nghiệp vụ, Kafka/JMS/AMQP phù hợp) hoặc thiết kế ACK, retry, deduplication và lưu trạng thái gửi ở tầng ứng dụng.

## 4. Thiết kế hợp đồng message

Sender phải biết **gửi gì**, **gửi đi đâu** và **phía nhận hiểu dữ liệu theo quy tắc nào**. Ví dụ hợp đồng cho một datagram:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

| Thành phần | Quy ước gợi ý | Lý do |
|---|---|---|
| Encoding | UTF-8 | Sender và receiver giải mã nhất quán. |
| Version | `v=1` | Hỗ trợ thay đổi schema theo thời gian. |
| Sensor ID | `node-7` | Xác định nguồn nghiệp vụ, không chỉ dựa vào IP. |
| Sequence | `1042`, tăng theo thiết bị | Hỗ trợ phát hiện trùng, gói đến muộn và ước lượng mất gói. |
| Temperature | `tempC=26.5` | Có đơn vị và định dạng thập phân nhất quán. |
| Kích thước tối đa | Ví dụ 512 byte | Giảm nguy cơ buffer quá nhỏ và phân mảnh. |
| Giá trị lỗi | Có quy tắc từ chối rõ ràng | Không để receiver suy đoán payload. |

Spring Integration **Message** chứa `payload` và `headers`; còn datagram là dữ liệu mạng. Header tùy ý trong `Message` (ví dụ `sensorId`, `correlationId`) **không mặc nhiên được truyền sang đầu nhận dưới dạng trường của payload**. Nếu receiver cần đọc một giá trị, hãy đặt nó vào cấu trúc payload hoặc thống nhất một protocol mapper riêng.

Với Java, nên mã hóa tường minh `StandardCharsets.UTF_8` và gửi `byte[]`, tránh phụ thuộc charset mặc định của máy. Với JSON/CBOR/Protobuf, chuyển đổi và kiểm tra schema trước khi gọi outbound handler.

## 5. Cấu hình Java: gửi UDP unicast

Ví dụ dùng Spring Boot có dependency **Spring Integration IP**. Khi sử dụng dependency management của Spring Boot, để Boot quản lý phiên bản thư viện tương thích.

~~~xml
<!-- pom.xml: khai báo bên trong <dependencies> -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

### 5.1. Chỉ định host và port

Tách cấu hình môi trường ra khỏi Java:

~~~yaml
# application.yml
app:
  udp:
    target-host: 127.0.0.1
    target-port: 9999
~~~

Trong ví dụ thử nghiệm, `127.0.0.1` là **loopback của môi trường chạy ứng dụng**. Nếu ứng dụng chạy trong Docker/container, địa chỉ này nằm bên trong network namespace của container, thường không phải địa chỉ máy host. Khi gửi sang collector thực tế, khai báo DNS hoặc IP của receiver có thể kết nối và cho phép **UDP trên cổng đích**.

### 5.2. Khai báo channel và outbound handler

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.ip.udp.outbound.UnicastSendingMessageHandler;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class UdpOutboundConfig {

    @Bean("udpOutboundRequests")
    public MessageChannel udpOutboundRequests() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "udpOutboundRequests")
    public UnicastSendingMessageHandler udpOutbound(
            @Value("${app.udp.target-host:127.0.0.1}") String targetHost,
            @Value("${app.udp.target-port:9999}") int targetPort) {
        return new UnicastSendingMessageHandler(targetHost, targetPort);
    }
}
~~~

Mỗi phần có một vai trò rõ ràng:

1. `DirectChannel` nhận message do service nghiệp vụ phát ra và chuyển cho handler đã đăng ký.
2. `@ServiceActivator(inputChannel = "...")` gắn outbound handler vào channel đó.
3. `UnicastSendingMessageHandler(host, port)` tạo handler gửi UDP unicast đến **một đích cấu hình sẵn**; constructor đơn giản không bật kiểm tra chiều dài hoặc yêu cầu ACK.
4. Bean handler được quản lý bởi Spring, nên tài nguyên socket và lifecycle của adapter gắn với application context.

**Lưu ý phiên bản:** import `org.springframework.integration.ip.udp.outbound.UnicastSendingMessageHandler` phù hợp với **Spring Integration 7.x**. Ở dòng **6.x**, class này nằm trong package `org.springframework.integration.ip.udp.UnicastSendingMessageHandler`. Hãy dùng import tương ứng với phiên bản thư viện do dự án quản lý; cách tạo `MessageChannel` và `@ServiceActivator` về cơ bản giữ nguyên.

### 5.3. Gửi message từ tầng nghiệp vụ

Tạo một service chỉ biết `MessageChannel`, không thao tác socket trực tiếp:

~~~java
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class TelemetryUdpPublisher {

    private final MessageChannel udpOutboundRequests;

    public TelemetryUdpPublisher(
            @Qualifier("udpOutboundRequests") MessageChannel channel) {
        this.udpOutboundRequests = channel;
    }

    public void publish(String sensorId, BigDecimal temperatureC) {
        if (sensorId == null ||
                !sensorId.matches("[A-Za-z0-9_-]{1,32}")) {
            throw new IllegalArgumentException("Invalid sensorId");
        }
        if (temperatureC == null) {
            throw new IllegalArgumentException("Missing temperature");
        }

        String body = "sensor=" + sensorId
                + ";tempC=" + temperatureC.toPlainString();

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > 512) {
            throw new IllegalArgumentException("UDP payload too large");
        }

        boolean dispatched = udpOutboundRequests.send(
                MessageBuilder.withPayload(bytes)
                    .setHeader("sensorId", sensorId) // Chỉ là header nội bộ
                    .build());

        if (!dispatched) {
            throw new IllegalStateException(
                    "Message was not dispatched to outbound handler");
        }
    }
}
~~~

Đây là **ví dụ gửi**; quy tắc miền giá trị của nhiệt độ, version/sequence, xác thực thiết bị và retry cần được bổ sung theo hợp đồng thực tế. `send()` có thể ném exception khi xử lý synchronous thất bại. Với `DirectChannel`, hàm `publish()` thường trả về sau khi handler đã xử lý lời gọi gửi, nhưng kết quả vẫn **không phải ACK từ collector**.

Để phát một gói minh họa sau khi ứng dụng Spring Boot khởi động, thêm bean sau vào cấu hình:

~~~java
import java.math.BigDecimal;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;

@Bean
public ApplicationRunner demoUdpSend(TelemetryUdpPublisher publisher) {
    return args -> publisher.publish(
            "node-7", new BigDecimal("26.5"));
}
~~~

Đặt phương thức `@Bean` bên trong class `@Configuration`; import ở trên là các import bổ sung. Bean này chỉ để thực hành và sẽ gửi một gói **mỗi lần ứng dụng khởi động**. Trong môi trường thực, việc gửi nên xuất phát từ sự kiện nghiệp vụ, scheduler hoặc pipeline tích hợp phù hợp.

## 6. Thử nghiệm bằng UDP listener độc lập

Một cách kiểm tra nhanh là cho một process khác **nghe UDP 9999** trên cùng máy. Nếu có PowerShell và .NET, mở terminal rồi chạy đoạn sau **trước khi khởi động ứng dụng Spring Boot**:

~~~powershell
$listener = [System.Net.Sockets.UdpClient]::new(9999)
try {
    Write-Host "Listening on UDP 9999..."
    $sender = [System.Net.IPEndPoint]::new(
        [System.Net.IPAddress]::Any, 0
    )
    $bytes = $listener.Receive([ref]$sender)
    Write-Host "From: $sender"
    Write-Host ("Payload: " +
        [System.Text.Encoding]::UTF8.GetString($bytes))
}
finally {
    $listener.Dispose()
}
~~~

Lệnh `Receive` trên là lệnh **chờ** cho đến khi có datagram, vì vậy terminal sẽ chưa in payload ngay. Khởi động Spring Boot với `app.udp.target-host=127.0.0.1` và `app.udp.target-port=9999`. Khi bean demo gửi, terminal receiver dự kiến in:

~~~text
Listening on UDP 9999...
From: 127.0.0.1:<source-port>
Payload: sensor=node-7;tempC=26.5
~~~

`<source-port>` là cổng gửi thực tế do hệ điều hành chọn; không nên hard-code giả định cổng nguồn bằng 9999. Khi receiver và Spring Boot chạy trên hai máy khác nhau, cần dùng địa chỉ đích có thể định tuyến, kiểm tra firewall/NAT và thực hiện thử nghiệm từ đúng mạng triển khai.

### Những kiểm tra cần tách biệt

| Kiểm tra | Bằng chứng | Chưa chứng minh điều gì |
|---|---|---|
| `MessageChannel.send()` trả `true` | Message được dispatch đến subscriber theo semantics của channel | UDP đã tới receiver. |
| Không có exception lúc handler gửi | Không phát hiện lỗi đồng bộ ở đường gửi | Mạng không mất gói, collector đã xử lý. |
| Listener nhận và in đúng payload | Một datagram đã đến endpoint thử nghiệm và giải mã đúng | Mọi datagram sau đó đều sẽ đến; hệ thống nghiệp vụ đã lưu. |
| Receiver phản hồi ACK có hợp đồng | Đã nhận ACK theo protocol đã thỏa thuận | Dữ liệu đã commit bền vững, trừ khi hợp đồng ACK định nghĩa rõ điều đó. |
| Collector lưu được bản ghi kèm ID/sequence | Luồng nghiệp vụ cụ thể đã hoàn thành ở collector | Các message khác đều đã xử lý. |

## 7. Cấu hình thay thế bằng Java DSL

Nếu dự án ưu tiên DSL, có thể mô tả endpoint outbound bằng một `IntegrationFlow`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.dsl.Udp;

@Configuration
public class UdpOutboundFlowConfig {

    @Bean
    public IntegrationFlow udpOutboundFlow() {
        return IntegrationFlow.from("udpOutboundRequests")
                .handle(Udp.outboundAdapter("127.0.0.1", 9999))
                .get();
    }
}
~~~

Cấu hình này có cùng ý tưởng: lấy message ở channel `udpOutboundRequests` rồi gửi UDP đến host/port đã chỉ định. Đây là **phương án thay thế**, không cấu hình đồng thời với `@ServiceActivator` ở mục 5 cho cùng luồng thử nghiệm, vì có thể tạo hai subscriber và cách dispatch khác dự kiến.

Dự án dùng DSL vẫn nên đưa host/port vào cấu hình môi trường thay vì giữ các literal như ví dụ. Các luồng nhiều bước có thể thêm transformer hoặc filter trước `.handle(Udp.outboundAdapter(...))`, hoặc nối từ các adapter nhận file, HTTP, JMS, AMQP, Kafka và dữ liệu DB. Nhờ vậy logic chuyển đổi và xác thực message nằm ngoài trách nhiệm gửi UDP.

## 8. Tùy chọn nâng cao: độ dài, ACK và đích động

### 8.1. Kiểm tra độ dài datagram

Spring Integration hỗ trợ tùy chọn **length check** ở cả phía gửi và nhận. Khi bật ở outbound, thư viện **thêm 4 byte đầu theo network byte order** để khai báo độ dài. Receiver tương thích có thể đối chiếu con số này với byte thực nhận để phát hiện packet bị cắt ngắn vì buffer quá nhỏ.

~~~java
// Ví dụ thay thế cách tạo handler trong mục 5:
UnicastSendingMessageHandler handler =
        new UnicastSendingMessageHandler(targetHost, targetPort);
handler.setLengthCheck(true);
return handler;
~~~

Đây không còn là payload UTF-8 thuần ở cấp datagram: receiver phải hiểu prefix đó và bật chế độ kiểm tra tương ứng (với Spring Integration inbound là `check-length`). Nếu dùng PowerShell listener ở mục 6 mà không bỏ 4 byte prefix, chuỗi hiển thị sẽ có byte phụ đầu gói.

Length check **chỉ hỗ trợ phát hiện cắt ngắn**, không khôi phục datagram đã mất và không bảo đảm truyền thành công.

### 8.2. Acknowledgment ở tầng ứng dụng

Spring Integration còn có tùy chọn **`acknowledge`** cho UDP outbound. Khi bật, sender cần cấu hình địa chỉ/cổng nhận ACK, timeout và receiver phải hỗ trợ header/protocol ACK mà thư viện thêm vào datagram. Receiver Spring Integration tương thích là kịch bản thường gặp; một UDP server tùy ý không tự hiểu các header này.

ACK có ý nghĩa khi cần biết receiver đã phản hồi theo **quy ước giao thức**. Nó vẫn không mặc định chứng minh dữ liệu đã được ghi vào DB hoặc xử lý đúng một lần. Phải thống nhất rõ thời điểm gửi ACK và hậu quả khi timeout: retry có thể tạo **gói trùng**.

Đừng bật `acknowledge` hoặc `check-length` cho một sender có receiver bên thứ ba khi chưa xác nhận hợp đồng binary framing với họ.

### 8.3. Host/port phụ thuộc từng message

Cấu hình host/port cố định là phù hợp khi ứng dụng gửi đến một collector. Với nhiều thiết bị/đích, Spring Integration còn hỗ trợ **destination expression** để chọn địa chỉ nhận dựa trên message runtime. Biểu thức đích phải trả về kiểu địa chỉ được hỗ trợ, chẳng hạn `SocketAddress`, URI hoặc chuỗi URI theo cú pháp mà endpoint yêu cầu.

Khi định tuyến theo header, cần **kiểm tra danh sách đích được phép**. Không để dữ liệu đầu vào không đáng tin cậy tự chọn tùy ý IP/port, vì ứng dụng có thể bị lợi dụng để phát gói UDP tới hệ thống khác.

**Một trường hợp nâng cao khác:** dùng `socket-expression` để gửi qua cùng socket với inbound receiver, hữu ích khi muốn trả lời UDP client đằng sau NAT bằng cổng mà client đã gửi tới. Tùy chọn này có ràng buộc với multicast và acknowledgment; hãy kiểm tra tài liệu phiên bản cụ thể trước khi triển khai. Nó không tự biến outbound adapter thành request/reply gateway.

## 9. Multicast: gửi đến một nhóm receiver

**Unicast** gửi đến một địa chỉ đích. **Multicast** gửi đến một địa chỉ nhóm IP; thiết bị nhận phải tham gia nhóm và hạ tầng mạng cần cho phép multicast.

~~~mermaid
flowchart LR
    A["Spring Integration publisher"] --> B["Multicast UDP group"]
    B --> C["Receiver A"]
    B --> D["Receiver B"]
    B --> E["Receiver C"]
~~~

Với multicast, Spring Integration cung cấp `MulticastSendingMessageHandler`. Cấu hình thường cần địa chỉ multicast, port, interface mạng phù hợp và phạm vi TTL; các receiver cần cấu hình join group tương ứng. Một lần gửi multicast không đảm bảo tất cả receiver đều thấy datagram.

Multicast thích hợp cho một số loại thông báo và dữ liệu phân phối trong mạng kiểm soát được. Nếu cần chắc chắn từng subscriber nhận đủ sự kiện, hãy cân nhắc broker pub/sub hoặc cách gửi có ACK, tracking và retry phù hợp.

## 10. Xử lý lỗi, backpressure và vòng đời

Một thiết kế outbound tốt cần phân biệt lỗi **trước khi gửi**, lỗi **trong khi gửi** và thất bại **sau khi gói rời sender**.

| Lớp lỗi | Ví dụ | Cách ứng xử |
|---|---|---|
| Validate/encode | Sensor ID sai, JSON lỗi, payload quá lớn | Từ chối trước adapter, đo tỷ lệ invalid và không retry vô hạn. |
| Dispatch trong ứng dụng | Channel không có subscriber, handler ném exception | Theo dõi exception và trạng thái endpoint; xử lý retry theo loại lỗi. |
| Socket/network cục bộ | Không phân giải được host, gửi lỗi, cấu hình mạng sai | Ghi nhận exception cụ thể, kiểm tra DNS/network và điều kiện retry. |
| Mạng/receiver | Firewall, packet loss, receiver down, buffer đầy | Phía gửi thường không biết; cần metric ở receiver hoặc protocol ACK. |
| Xử lý nghiệp vụ ở receiver | Parse hợp lệ nhưng DB không sẵn sàng | Cần phản hồi nghiệp vụ rõ ràng hoặc lưu bền trước khi xác nhận. |

**MessageChannel và tải:** nếu producer tạo hàng nghìn message/giây, `DirectChannel` xử lý dispatch đồng bộ và thường để luồng caller thực hiện việc gửi. Khi upstream cần bất đồng bộ, có thể dùng executor/queue channel hoặc một broker ở giữa, nhưng cần giới hạn hàng đợi, quy tắc xử lý quá tải và cơ chế lưu bền nếu không được mất message.

**Retry:** retry ở sender phải dựa vào chính sách nghiệp vụ và phân loại lỗi. Không nên retry mọi timeout mà không có `messageId`/`sequence`, vì receiver có thể đã nhận gói đầu. Cũng không nên lưu gói thất bại vô hạn trong bộ nhớ. Với giao hàng bắt buộc, kết hợp outbox/queue bền vững, ACK nghiệp vụ và deduplication ở receiver.

**Vòng đời:** Spring quản lý khởi tạo/dừng outbound handler, nhưng điều này không đảm bảo network luôn có thể gửi. Khi deploy, kiểm tra DNS đích, route, firewall, network policy và cấu hình interface, đặc biệt trong container/Kubernetes. Thiết lập metric để biết hệ thống đã **thử gửi bao nhiêu**, gặp **lỗi đồng bộ bao nhiêu** và, nếu có, receiver **xác nhận bao nhiêu**.

## 11. Bảo mật và quan sát

UDP thuần không tích hợp cơ chế xác thực hoặc mã hóa dữ liệu. Vì vậy:

- Chỉ gửi dữ liệu đến danh sách host/port cho phép và qua mạng phù hợp với mức độ nhạy cảm.
- Không dùng IP nguồn hoặc thông tin header dễ giả mạo làm định danh đáng tin cậy nếu không có cơ chế xác thực ở tầng ứng dụng.
- Nếu cần chống sửa đổi và replay, cân nhắc chữ ký/HMAC hoặc một protocol truyền thông có bảo vệ; kiểm tra nonce, timestamp và sequence theo chính sách.
- Đặt giới hạn kích thước payload, tốc độ gửi và mức log; không đưa khóa bảo mật hoặc payload nhạy cảm vào log debug.
- Đo số lượng message được chuẩn bị, được dispatch, lỗi gửi đồng bộ và tỷ lệ nhận ở phía đích. Nếu có ACK, tách ACK kỹ thuật với xác nhận xử lý nghiệp vụ.

Một dashboard chỉ ghi `udp_sent_total` ở sender có thể gây hiểu nhầm. Tốt hơn, bổ sung `udp_received_total`, `udp_invalid_total` và `udp_business_processed_total` ở receiver, ghép theo instance/thiết bị hoặc sequence khi thích hợp.

## 12. Lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Handler đã chạy nhưng collector không có dữ liệu | Sai host/port, firewall, receiver chưa nghe hoặc packet loss | Thử UDP listener độc lập; kiểm tra packet capture ở cả hai đầu. |
| Chạy trên máy local được, vào Docker thì không | `127.0.0.1` trong container trỏ tới chính container | Sử dụng địa chỉ DNS/IP có thể truy cập từ network container. |
| Receiver thấy ký tự lạ đầu gói | Sender bật `lengthCheck` nhưng receiver không xử lý 4 byte prefix | Đồng bộ framing ở hai phía. |
| Dùng `acknowledge=true` thì timeout | Receiver không hỗ trợ ACK, sai host/port ACK hoặc firewall chặn đường phản hồi | Kiểm tra protocol ACK và capture gói phản hồi. |
| Một số sự kiện trùng | Producer retry khi không rõ kết quả lần trước | Dùng ID/sequence và deduplication receiver. |
| Mất gói khi cao tải | Quá tốc độ xử lý/buffer của mạng hoặc receiver | Giới hạn tốc độ, đo queue/buffer, giảm packet size, cân nhắc transport khác. |
| Gửi thành công nhưng giá trị sai | Sender và receiver khác charset, kiểu số hoặc schema version | So sánh byte payload và quy ước dữ liệu. |
| Hai đích cùng được gửi ngoài dự kiến | Có nhiều subscriber trên channel hoặc lặp endpoint | Kiểm tra cấu hình luồng, số handler và semantics của channel. |

Khi điều tra, hãy đi theo chuỗi **producer tạo đúng message → channel dispatch → outbound handler gửi datagram → receiver nhận byte → receiver xác nhận nghiệp vụ**. Mỗi bước cần bằng chứng riêng, vì log ở bước trước không tự chứng minh bước sau.

## 13. Bài thực hành

Xây dựng luồng gửi sự kiện từ một service giả lập sang UDP collector với hợp đồng:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

Thực hiện theo thứ tự:

1. Cấu hình `target-host` và `target-port` ở application properties; tạo `DirectChannel` và UDP outbound handler.
2. Viết một publisher sinh `Message<byte[]>` UTF-8, kiểm tra giới hạn 512 byte và bổ sung `seq` tăng dần cho mỗi thiết bị.
3. Dùng PowerShell listener nhận 3 gói hợp lệ; đối chiếu chính xác byte, thứ tự và dữ liệu parse được.
4. Cố ý gửi sai host/port; ghi nhận điều sender có thể biết và điều không thể biết nếu không có receiver ACK.
5. Tăng tốc độ phát 1.000 gói với sequence liên tục; đo số gói nhận, số gói trùng và số sequence bị thiếu.
6. Thảo luận phương án khi collector dừng 30 giây: bỏ dữ liệu cũ, lưu queue bền vững, gửi lại hay đổi transport? Giải thích trade-off và hậu quả trùng lặp.

**Câu hỏi tự đánh giá:**

- `UnicastSendingMessageHandler` làm nhiệm vụ gì mà `MessageChannel` không làm?
- Một `MessageHeader` thêm ở sender có tự xuất hiện dưới dạng trường trong UDP payload không?
- Vì sao `lengthCheck=true` có thể khiến receiver UDP thuần đọc sai nội dung?
- Vì sao ACK kỹ thuật và ACK sau khi commit database là hai hợp đồng khác nhau?
- Khi nào nên chọn multicast, và điều kiện mạng nào phải thỏa mãn?
- Nếu producer nguồn đọc file bằng poller rồi gửi UDP, poller chịu trách nhiệm ở đoạn nào của luồng?

## 14. Tài liệu tham khảo

- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): cấu hình unicast/multicast, length check, ACK, Java DSL và destination expression.
- [Spring Integration Reference — IP Configuration Attributes](https://docs.spring.io/spring-integration/reference/ip/endpoint-reference.html): ý nghĩa các thuộc tính UDP inbound/outbound.
- [Spring Integration Reference — TCP and UDP Support](https://docs.spring.io/spring-integration/reference/ip.html): vị trí của UDP trong các endpoint IP.

## Kết luận

**UDP outbound channel adapter** tạo ranh giới rõ ràng giữa message trong ứng dụng Spring Integration và datagram gửi ra hệ thống ngoài. Với luồng unicast cơ bản, chỉ cần một **MessageChannel**, `UnicastSendingMessageHandler` và hợp đồng payload nhất quán giữa sender/receiver. Các nguồn như HTTP, file, SFTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu có thể đưa sự kiện vào channel này sau bước chuyển đổi phù hợp.

Để sử dụng UDP an toàn và có thể vận hành, cần cấu hình đúng đích, giới hạn kích thước và tốc độ, quản lý lỗi/ACK có chủ đích, đảm bảo schema nhất quán và hiểu rằng **gửi thành công ở sender không đồng nghĩa receiver đã xử lý thành công**.
