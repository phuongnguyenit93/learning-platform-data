# UDP inbound channel adapter trong Spring Integration

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của **UDP inbound channel adapter** khi đưa dữ liệu từ một hệ thống ngoài vào luồng xử lý Spring Integration.
- Phân biệt **datagram UDP**, **message** của Spring Integration và **MessageChannel** nhận dữ liệu.
- Cấu hình **UnicastReceivingChannelAdapter**, xử lý payload dạng byte và kiểm tra hợp đồng message.
- Gửi gói UDP để thử nghiệm, quan sát lỗi và xác định những điểm có thể mất dữ liệu.
- Đưa ra quyết định phù hợp về vòng đời kết nối, hiệu năng và bảo mật cho hệ thống nhận UDP.

Bài thuộc chương **Adapter UDP** của module **SPRING_INTEGRATION_ADAPTERS**. Trong hệ sinh thái adapter, gateway, poller và MessageChannel dùng để kết nối hệ thống bên ngoài với ứng dụng, UDP inbound adapter là điểm **nhận** datagram từ mạng, chuyển thành message nội bộ để các thành phần phía sau tiếp tục xử lý.

## 1. Bài toán: nhận dữ liệu từ thiết bị qua UDP

Giả sử nhiều cảm biến gửi nhiệt độ mỗi vài giây đến cổng UDP 9999 của một dịch vụ Spring Boot. Một gói tin có nội dung UTF-8:

~~~text
sensor=node-7;tempC=26.5
~~~

Ứng dụng cần tiếp nhận, kiểm tra định dạng, chuyển thành dữ liệu nghiệp vụ, ghi nhận và có thể chuyển tiếp đến cơ sở dữ liệu hoặc một hệ thống message khác.

Với Java thuần, ta có thể mở **DatagramSocket**, liên tục gọi hàm nhận, lấy địa chỉ người gửi, rồi tự kết nối việc nhận socket với tầng nghiệp vụ. **UDP inbound channel adapter** đóng gói phần nhận mạng và phát ra **Message** theo cơ chế Spring Integration, nhờ đó phần xử lý sau cổng mạng không cần biết cách đọc socket.

~~~mermaid
flowchart LR
    A["Cảm biến / hệ thống ngoài"] -->|"UDP datagram"| B["UDP socket :9999"]
    B --> C["UnicastReceivingChannelAdapter"]
    C -->|"Message<byte[]>"| D["MessageChannel"]
    D --> E["Validate / Decode / Transform"]
    E --> F["Service Activator"]
    F --> G["Xử lý nghiệp vụ / lưu trữ"]
~~~

**Điểm cần phân biệt:** inbound adapter là đầu vào của luồng; nó không tự lưu dữ liệu, đảm bảo giao hàng, hay trả lời người gửi. Các công việc đó thuộc về các thành phần khác hoặc giao thức khác.

## 2. UDP ảnh hưởng thế nào đến thiết kế luồng?

UDP là giao thức truyền **datagram**, không thiết lập kết nối như TCP. Mỗi lần gửi là một đơn vị dữ liệu riêng. Adapter nhận một datagram và cung cấp payload cho một message của Spring Integration.

| Thuộc tính của UDP | Hệ quả đối với inbound adapter |
|---|---|
| Không có phiên kết nối và bắt tay TCP | Adapter lắng nghe trên địa chỉ/cổng UDP; không quản lý một kết nối TCP cho mỗi thiết bị. |
| Không cam kết gói đến nơi | Message không được tạo nếu datagram bị mất trước khi tới bộ nhận. |
| Không đảm bảo thứ tự | Gói số 12 có thể được xử lý trước gói số 11; cần sequence number nếu thứ tự là yêu cầu nghiệp vụ. |
| Có thể trùng gói | Luồng xử lý nên có khóa định danh hoặc cơ chế idempotency nếu việc ghi nhận trùng gây hại. |
| Giữ ranh giới datagram | Không cần tự tách stream thành các bản tin như TCP, nhưng vẫn phải thống nhất định dạng bên trong payload. |
| Dung lượng datagram bị giới hạn | Nên giữ thông điệp nhỏ; gói lớn có nguy cơ phân mảnh IP và mất toàn bộ thông điệp nếu một mảnh thất lạc. |
| Không có backpressure đến sender | Khi máy nhận quá tải hoặc bộ đệm đầy, datagram có thể bị loại bỏ mà sender không biết. |

Giới hạn lý thuyết của payload UDP trên IPv4 là khoảng **65.507 byte** khi không có tùy chọn IP; đây không phải kích thước nên sử dụng mặc định. Trên mạng Internet, payload cỡ **1.200 byte hoặc nhỏ hơn** thường là lựa chọn thận trọng để giảm rủi ro phân mảnh, nhưng giới hạn thực tế phải được kiểm tra theo đường truyền và hợp đồng giữa hai phía.

**Khi nên dùng:** telemetry định kỳ, số liệu đo có thể cập nhật lại ở chu kỳ tiếp theo, phát hiện dịch vụ trong mạng nội bộ hoặc hệ thống chấp nhận một tỷ lệ mất gói đã định nghĩa. **Khi không nên dựa riêng vào UDP:** thanh toán, lệnh điều khiển quan trọng hoặc sự kiện bắt buộc xử lý đúng một lần. Nếu nghiệp vụ đòi xác nhận, gửi lại, đánh số thứ tự, chống trùng, bạn phải tự thiết kế thêm các cơ chế đó hoặc chọn một transport phù hợp hơn.

## 3. Những thành phần tham gia

**UnicastReceivingChannelAdapter** là thành phần thường dùng để nhận UDP unicast. Nó mở bộ nhận trên một cổng, nhận datagram và phát Spring Integration Message qua output channel.

**MessageChannel** vận chuyển message từ adapter đến một hoặc nhiều bước xử lý theo cấu hình. Với **DirectChannel**, việc dispatch đến subscriber về cơ bản xảy ra trong cùng luồng gọi; một handler xử lý lâu có thể làm chậm đường nhận.

**Service Activator** nhận message và thực hiện xử lý ứng dụng. Bạn có thể đặt transformer, filter, router, error handling và các adapter outbound ở phía sau để hoàn thiện luồng tích hợp.

| Thành phần | Nhiệm vụ trong ví dụ |
|---|---|
| UDP inbound adapter | Đọc datagram đến cổng 9999 và phát message. |
| DirectChannel | Đưa message từ adapter đến handler. |
| Service Activator | Kiểm tra dữ liệu và xử lý bản ghi cảm biến. |
| Outbound adapter hoặc handler khác | Tùy yêu cầu, lưu DB, gửi Kafka/AMQP hoặc gọi một dịch vụ ngoài. |
| Poller | **Không bắt buộc** để nhận UDP vì adapter nhận sự kiện từ socket; poller thường xuất hiện khi nguồn là kênh hoặc tài nguyên cần được lấy dữ liệu theo chu kỳ. |

Spring Integration cũng hỗ trợ các thành phần nhận **multicast** cho trường hợp các thiết bị phát đến một nhóm multicast. Bài này đi sâu vào unicast: một sender gửi datagram đến địa chỉ IP và cổng của ứng dụng nhận.

## 4. Hợp đồng message tại ranh giới UDP

UDP chuyển **byte**, không tự cung cấp JSON, UTF-8, schema hay đối tượng Java. Với cấu hình đơn giản, payload mà receiver đưa vào luồng là **byte[]**. Các bước tiếp theo cần thống nhất cách giải mã và kiểm tra dữ liệu.

Một hợp đồng message tối thiểu nên nêu rõ:

| Mục hợp đồng | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| Kiểu payload | Byte UTF-8 | Không mặc định mọi datagram là chuỗi hợp lệ. |
| Cấu trúc | sensor={id};tempC={value} | Đủ trường, đúng ký tự phân cách, đúng kiểu dữ liệu. |
| Giới hạn kích thước | Tối đa 512 byte | Từ chối datagram trống/quá cỡ theo nghiệp vụ. |
| Nhận dạng nguồn | IP, port, device ID | IP/port mạng chỉ là thông tin phụ trợ; device ID phải được kiểm tra theo chính sách hệ thống. |
| Phát hiện trùng và thứ tự | device ID + sequence | Thiết kế nếu nghiệp vụ cần, vì UDP không cung cấp. |
| Lỗi dữ liệu | Ghi metric và bỏ qua | Một gói xấu không được làm đứt toàn bộ đường nhận. |
| Khả năng tương thích | Version trong payload | Nên có khi giao thức hoặc schema sẽ thay đổi. |

Ngoài payload, Spring Integration có thể gắn các **header** mô tả địa chỉ/port bên gửi và thông tin message. Tên, kiểu và tập header cụ thể phụ thuộc phiên bản thư viện và cấu hình; hãy kiểm tra header thực nhận khi tích hợp. Không nên coi địa chỉ IP nguồn UDP là bằng chứng xác thực thiết bị vì địa chỉ nguồn có thể bị giả mạo ở một số bối cảnh mạng.

Một tùy chọn riêng của các thành phần UDP trong Spring Integration là **length check**: phía gửi và phía nhận có thể thống nhất tiền tố độ dài do thư viện bổ sung để phát hiện datagram bị cắt ngắn. Cả hai phía phải dùng cùng quy ước; nếu sender tự gửi UTF-8 thuần như ví dụ này thì giữ cấu hình mặc định, tránh bật length check một phía. Dù kiểm tra được độ dài, cơ chế này **không** biến UDP thành truyền tin tin cậy.

## 5. Cấu hình một UDP inbound channel adapter

Ví dụ dưới đây sử dụng Spring Boot và Spring Integration Java configuration. Thêm các dependency tương thích với phiên bản Spring Boot đang dùng; khi có Boot dependency management, thông thường không cần khai báo phiên bản cho từng thư viện Spring Integration.

~~~xml
<!-- pom.xml: đặt trong phần dependencies -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

Tạo một channel nhận message nội bộ và một adapter lắng nghe cổng UDP:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.ip.udp.UnicastReceivingChannelAdapter;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class UdpInboundConfig {

    // Cố định để minh họa; trong môi trường thực hãy lấy từ cấu hình.
    public static final int UDP_PORT = 9999;

    @Bean("udpDatagrams")
    public MessageChannel udpDatagrams() {
        return new DirectChannel();
    }

    @Bean
    public UnicastReceivingChannelAdapter udpInbound(
            @Qualifier("udpDatagrams") MessageChannel channel) {
        UnicastReceivingChannelAdapter adapter =
                new UnicastReceivingChannelAdapter(UDP_PORT);
        adapter.setOutputChannel(channel);
        return adapter;
    }
}
~~~

Diễn giải các dòng quan trọng:

1. **UnicastReceivingChannelAdapter(9999)** tạo bộ nhận UDP unicast trên cổng 9999 của máy chạy ứng dụng. Cổng này phải khả dụng và được phép nhận lưu lượng từ mạng liên quan.
2. **setOutputChannel(...)** chỉ định điểm đẩy message sau khi nhận datagram. Một producer có output channel là phần kết nối cốt lõi của Spring Integration.
3. Bean adapter tham gia vòng đời của Spring application context. Khi ứng dụng khởi động, bộ nhận được kích hoạt theo lifecycle; khi dừng, tài nguyên socket cần được đóng qua lifecycle của framework.
4. **DirectChannel** phù hợp với ví dụ xử lý nhanh, đồng bộ. Khi xử lý cần gọi dịch vụ chậm hay ghi khối lượng lớn, hãy tách nhận và xử lý qua kênh/asynchronous executor có giới hạn hàng đợi và kế hoạch xử lý quá tải.

Không cần tạo vòng lặp **while(receive)** hoặc một **@Scheduled poller** trong ứng dụng. Adapter đảm nhận phần đọc socket.

## 6. Xử lý và kiểm tra datagram

Bổ sung một service activator nhận **Message<byte[]>**. Ví dụ chủ động giới hạn độ dài và kiểm tra định dạng trước khi dùng dữ liệu đầu vào:

~~~java
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class UdpTelemetryHandler {

    private static final Logger log =
            LoggerFactory.getLogger(UdpTelemetryHandler.class);

    @ServiceActivator(inputChannel = "udpDatagrams")
    public void handle(Message<byte[]> message) {
        byte[] bytes = message.getPayload();

        if (bytes.length == 0 || bytes.length > 512) {
            log.warn("Discard UDP datagram: invalid size={}", bytes.length);
            return;
        }

        String payload = new String(bytes, StandardCharsets.UTF_8);
        String[] fields = payload.split(";", -1);

        boolean valid = fields.length == 2
                && fields[0].matches("sensor=[A-Za-z0-9_-]{1,32}")
                && fields[1].matches("tempC=-?\\d{1,3}(\\.\\d{1,2})?");

        if (!valid) {
            log.warn("Discard UDP datagram: invalid format");
            return;
        }

        // Thực tế: parse thành DTO, kiểm tra ngưỡng và chuyển tiếp.
        log.info("Accepted UDP telemetry: {}", payload);
    }
}
~~~

Đây là ví dụ **kiểm tra cú pháp** cho một format nhỏ, chưa phải parser nghiệp vụ hoàn chỉnh. Ứng dụng thật cần chuyển nhiệt độ thành số, kiểm tra miền giá trị, ràng buộc ID thiết bị, quy ước decimal, chống trùng nếu cần và bảo vệ nội dung log. Nếu hợp đồng dùng JSON hoặc protobuf, hãy đặt decoder/schema validator tương ứng sau adapter; không trộn việc giải mã phức tạp vào phần đọc socket.

Với Java, thao tác tạo chuỗi từ byte bằng UTF-8 thông thường có thể thay byte lỗi bằng ký tự thay thế. Nếu yêu cầu từ chối mọi payload UTF-8 không hợp lệ, sử dụng **CharsetDecoder** với **CodingErrorAction.REPORT** và bắt lỗi giải mã. Trong ví dụ trên, ký tự thay thế không khớp biểu thức kiểm tra nên datagram sẽ bị bỏ qua.

Một luồng phát triển đầy đủ có thể là:

~~~mermaid
flowchart TD
    A["UDP inbound adapter"] --> B["MessageChannel"]
    B --> C{"Dung lượng / decode hợp lệ?"}
    C -->|Không| D["Metric invalid + log có giới hạn"]
    C -->|Có| E{"Schema / quy tắc nghiệp vụ hợp lệ?"}
    E -->|Không| D
    E -->|Có| F["Bản ghi telemetry có kiểu rõ ràng"]
    F --> G["DB / event broker / xử lý tiếp"]
~~~

Trong mô hình này, loại bỏ gói không hợp lệ là **quyết định nghiệp vụ**. Việc ghi log không đồng nghĩa sender được thông báo lỗi: UDP inbound adapter không tự tạo một thông điệp phản hồi.

## 7. Thử nghiệm từ máy gửi

Khởi động ứng dụng có hai class cấu hình/handler trên. Chạy câu lệnh PowerShell sau trên cùng máy để gửi một datagram UTF-8 đến **127.0.0.1:9999**:

~~~powershell
$client = New-Object System.Net.Sockets.UdpClient
try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes(
        "sensor=node-7;tempC=26.5"
    )
    [void]$client.Send($bytes, $bytes.Length, "127.0.0.1", 9999)
}
finally {
    $client.Dispose()
}
~~~

Khi luồng hoạt động, ứng dụng sẽ ghi log tương tự:

~~~text
Accepted UDP telemetry: sensor=node-7;tempC=26.5
~~~

Thử thay payload thành **sensor=node-7;tempC=abc** để xác nhận handler phát hiện sai format, hoặc gửi một thông điệp lớn hơn 512 byte để kiểm tra giới hạn ứng dụng.

Nếu gửi từ **máy khác**, thay 127.0.0.1 bằng IP có thể truy cập của máy chạy ứng dụng, mở inbound rule UDP phù hợp trong firewall và kiểm tra Docker/Kubernetes/network policy nếu có. Một thao tác gửi không lỗi ở phía sender chỉ có nghĩa dữ liệu được giao cho network stack tại máy gửi; nó **không chứng minh** receiver đã nhận hoặc xử lý datagram.

### Các lớp kiểm tra nên tách biệt

| Cấp kiểm tra | Cách thực hiện | Xác nhận điều gì |
|---|---|---|
| Handler | Tạo message byte[] hợp lệ/sai và gọi xử lý trong test | Quy tắc format, giới hạn, luồng nhánh lỗi. |
| Adapter + channel | Chạy Spring context, gửi datagram vào cổng UDP test | Socket → adapter → MessageChannel → handler hoạt động. |
| Môi trường mạng | Gửi từ máy/thiết bị thật, xem log/metric và capture UDP | Firewall, IP, NAT, cổng, phân mảnh và lưu lượng thực tế. |
| Tải và độ bền | Tạo nhiều datagram với sequence tăng dần, đo số nhận | Tỷ lệ mất/trùng, độ trễ, hành vi khi xử lý quá tải. |

Tránh dùng thời điểm gọi **Send** làm thời điểm hệ thống đã xử lý thành công. Nếu cần chứng minh xử lý từng sự kiện, thiết kế thêm định danh và xác nhận ở tầng ứng dụng.

## 8. Xử lý lỗi và giới hạn tài nguyên

Một UDP listener hoạt động ổn trong thử nghiệm vẫn có thể đánh rơi datagram khi tải tăng. Hãy xem ba nhóm lỗi độc lập:

**Lỗi trước khi tạo message:** gói bị mất trên đường truyền, chặn bởi firewall, đến sai cổng, vượt năng lực socket buffer hoặc bị cắt ngắn. Handler Spring Integration không nhận được message để báo lỗi. Theo dõi số thứ tự, số gói phía sender và chỉ số hệ thống mạng nếu việc mất gói quan trọng.

**Lỗi khi chuyển đổi nội dung:** sai UTF-8, sai phiên bản schema, thiếu trường, số không hợp lệ. Nên giới hạn kích thước, validate và phân loại gói lỗi; tránh ném exception không kiểm soát ra đường nhận. Với message cần truy cứu, cân nhắc dead-letter/quarantine *sau khi* có thể tạo một record an toàn, nhưng không thể đưa vào dead-letter những gói vốn chưa tới ứng dụng.

**Lỗi xử lý phía sau:** database chậm, broker không sẵn sàng, handler hết thread hoặc hàng đợi đầy. Với **DirectChannel**, một handler đồng bộ chạy lâu có thể kéo dài thời gian dispatch ở đường nhận. Có thể dùng kênh có executor/hàng đợi giới hạn và thiết kế chính sách quá tải, nhưng việc thêm hàng đợi cũng không làm UDP có tính tin cậy. Nếu cần retry phía sau, phải tính tới trùng lặp và thời hạn lưu message.

Những cấu hình và hành vi cần cân nhắc khi vận hành:

- **Port và địa chỉ bind:** cấu hình cổng qua biến môi trường/application properties thay vì hard-code; xác định interface mạng cần nghe; tránh xung đột cổng giữa nhiều process.
- **Kích thước datagram và buffer:** thống nhất kích thước tối đa giữa sender/receiver; đánh giá buffer socket và mức phân mảnh trên mạng thực tế.
- **Thông lượng:** đặt thời gian xử lý, số thread, hàng đợi và giới hạn lưu lượng phù hợp; không tạo thread mới cho mỗi gói.
- **Error channel/handler:** ghi nhận lỗi xử lý trong Spring Integration theo mô hình ứng dụng; không hiểu lỗi nội bộ là thông báo UDP đã tới sender.
- **Vòng đời:** kiểm tra listener khởi động sau cấu hình, lắng nghe đúng cổng và dừng sạch khi ứng dụng shutdown; với container, kiểm tra UDP port mapping và thời gian dừng.
- **Quan sát:** đếm datagram nhận, datagram hợp lệ, datagram bị loại, số byte, thời gian xử lý và lỗi chuyển tiếp; gắn các chỉ số này với host/instance.

## 9. Bảo mật khi mở cổng UDP

Một cổng UDP nhận dữ liệu từ mạng là ranh giới đầu vào **không đáng tin cậy**. Không nên chỉ dựa vào IP nguồn vì có thể bị giả mạo, nhất là với hạ tầng không kiểm soát toàn bộ đường truyền.

Cần tối thiểu hóa bề mặt tấn công bằng cách giới hạn mạng/nguồn được phép gửi, xác thực thông điệp ở tầng ứng dụng khi cần, đặt giới hạn độ dài, kiểm tra schema trước khi chuyển tiếp và hạn chế ghi trực tiếp payload nhạy cảm vào log. Nếu giao thức có chữ ký hoặc HMAC, xác minh chữ ký và chống replay bằng timestamp/nonce/sequence; đây là logic của ứng dụng hoặc giao thức trao đổi, không phải bảo đảm sẵn có của UDP inbound adapter.

UDP thuần **không mã hóa**. Với dữ liệu cần bảo mật trong truyền tải, xem xét một giao thức có bảo vệ phù hợp (chẳng hạn DTLS ở tầng hệ thống, kênh mạng bảo vệ, hoặc thay transport khi yêu cầu cho phép). Không mặc định Spring Integration UDP inbound adapter tự bổ sung DTLS.

## 10. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách khoanh vùng |
|---|---|---|
| Khởi động lỗi do không bind được cổng | Cổng đã được process khác dùng, thiếu quyền hoặc bind sai interface | Kiểm tra process đang lắng nghe và cấu hình port; chọn cổng khả dụng. |
| Sender gửi thành công nhưng không thấy log | Sai IP/cổng, UDP bị chặn, chưa có subscriber, gói mất | Gửi thử loopback, kiểm tra firewall, capture datagram tại máy nhận và xác nhận adapter đã start. |
| Payload hiển thị ký tự lạ | Hai phía không thống nhất charset hoặc định dạng | Kiểm tra byte thực nhận, quy ước UTF-8 và schema. |
| Một số gói lớn bị lỗi hoặc mất | Phân mảnh, buffer nhỏ, giới hạn packet | Giảm kích thước, đo đường truyền, thống nhất giới hạn với sender. |
| Gói bị bác bỏ dù nhìn đúng | Hai bên khác hợp đồng framing/length check hoặc format | So sánh payload ở mức byte, xác nhận setting length check của cả hai phía. |
| Gói nhận bị thiếu khi tăng tải | Receive buffer đầy hoặc xử lý downstream quá chậm | Đo tốc độ gửi/nhận, duration handler, queue size; giới hạn tải và tách xử lý phù hợp. |
| Bản ghi nghiệp vụ trùng hoặc đảo thứ tự | Đặc tính của UDP hoặc cơ chế gửi lại ở ứng dụng | Thêm sequence/identity, logic idempotency và quy tắc cập nhật rõ ràng. |

Một cách điều tra hiệu quả là tách ba câu hỏi: **datagram có tới host không?**, **adapter có phát message không?**, **handler có xử lý hợp lệ không?**. Trả lời từng câu giúp xác định vấn đề thuộc mạng, cấu hình integration hay logic nghiệp vụ.

## 11. Phân biệt với outbound adapter và các cơ chế khác

- **UDP inbound adapter:** lắng nghe datagram, biến đầu vào mạng thành message và đưa vào channel.
- **UDP outbound adapter/message handler:** lấy message trong ứng dụng và gửi datagram ra đích. Nếu muốn phản hồi UDP, cần thiết kế đường gửi riêng và hợp đồng địa chỉ/port nhận phản hồi.
- **Gateway:** mô hình request/reply giúp biểu diễn tương tác gọi và nhận trả lời ở những transport/hình thức phù hợp. Một inbound UDP datagram đơn lẻ không đương nhiên tạo quy trình request/reply đáng tin cậy.
- **Poller:** lịch kích hoạt lấy message từ nguồn có thể poll; việc nhận socket UDP được kích hoạt bởi gói đến, nên không cần poller để đọc từng datagram.
- **MessageChannel:** trừu tượng hóa đường truyền message giữa các endpoint, giúp thay đổi cách xử lý, định tuyến hoặc chuyển tiếp mà không viết lại giao thức socket.

Điều này phù hợp với mục tiêu chung của module SPRING_INTEGRATION_ADAPTERS: nối file, SFTP, HTTP, JMS, AMQP, Kafka, cơ sở dữ liệu và các nguồn mạng vào một kiến trúc message. Với UDP, hợp đồng dữ liệu và quyết định xử lý mất gói đóng vai trò đặc biệt quan trọng vì transport không đảm bảo giao hàng.

## 12. Bài thực hành củng cố

Xây dựng receiver cho gói telemetry có hợp đồng sau:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

Yêu cầu triển khai:

1. Nhận UDP tại cổng được cấu hình và giữ payload ở dạng **byte[]** tới bước validate.
2. Giới hạn kích thước, kiểm tra UTF-8, version, sensor ID, sequence là số nguyên không âm và nhiệt độ trong miền hợp lệ.
3. Lưu sequence cuối theo thiết bị trong một bộ nhớ thử nghiệm; xác định rõ cách xử lý gói trùng và gói đến muộn. Thảo luận điều gì xảy ra khi ứng dụng restart hoặc chạy nhiều instance.
4. Ghi metric tổng datagram nhận, hợp lệ và bị loại; tạo thử các gói hợp lệ, lỗi schema, trùng sequence và đảo thứ tự.
5. Tăng tốc độ gửi để quan sát sự khác biệt giữa **DirectChannel** và một đường xử lý bất đồng bộ có giới hạn; nêu chính sách khi hàng đợi đầy.

**Câu hỏi tự đánh giá:**

- Vì sao gửi thành công từ một UDP client không đủ để kết luận dữ liệu đã được lưu?
- Vì sao chỉ bổ sung một **QueueChannel** không thể bảo đảm không mất datagram?
- Khi nào bạn nên dùng outbound handler, và khi nào cần thiết kế ACK/sequence ở tầng ứng dụng?
- Vì sao contract payload, kiểm soát độ dài và vòng đời listener là các quyết định thiết kế quan trọng ngang với việc chọn cổng UDP?

## Kết luận

**UDP inbound channel adapter** là điểm nối giữa datagram bên ngoài và message bên trong Spring Integration. Cấu hình cơ bản gồm một **UnicastReceivingChannelAdapter**, một **MessageChannel** và một handler nhận **Message<byte[]>**; từ đó có thể bổ sung validate, transform, routing và các bước tích hợp hệ thống khác.

Chất lượng của một luồng nhận UDP được quyết định bởi hợp đồng message rõ ràng, kiểm soát kích thước và tải, quan sát lỗi, bảo mật nguồn nhận và cách ứng dụng chấp nhận hoặc bù đắp đặc tính mất gói, trùng gói và đảo thứ tự của UDP.
