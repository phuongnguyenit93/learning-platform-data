# Xử lý mất gói và tính không bảo đảm của UDP trong Spring Integration

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích chính xác các giới hạn của **UDP** về giao hàng, thứ tự, trùng lặp, xác nhận và kiểm soát tải.
- Phân biệt một gói **chưa từng đến socket**, một datagram **đến nhưng bị cắt ngắn**, một message **bị từ chối khi parse** và một message **đã nhận nhưng xử lý nghiệp vụ thất bại**.
- Sử dụng `deviceId`, `epoch` và `sequence` để phát hiện **khoảng sequence thiếu**, đồng thời hiểu vì sao khoảng thiếu chưa chứng minh gói đã mất vĩnh viễn.
- Cấu hình UDP inbound adapter, `MessageChannel` và service activator để kiểm tra, đo lường, nhận diện các gói đến muộn hoặc có khả năng trùng.
- Thiết kế **ACK, retry có giới hạn, idempotency và lưu bền** khi một sự kiện không được phép mất.
- Quyết định khi nào nên chấp nhận *best effort* của UDP và khi nào nên dùng HTTP, JMS, AMQP, Kafka, file/SFTP hoặc một cơ chế giao hàng khác.
- Thử nghiệm các kịch bản gửi thiếu, đảo thứ tự, gửi trùng, lỗi mạng và receiver restart bằng các bước có thể quan sát được.

Bài thuộc chương **Adapter UDP** của module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`, đồng thời xây dựng hợp đồng message, xử lý lỗi và vòng đời kết nối với file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. UDP là ví dụ rõ ràng cho nguyên tắc: **một adapter giúp đưa dữ liệu vào luồng message, nhưng độ tin cậy phụ thuộc cả giao thức truyền tải lẫn hợp đồng nghiệp vụ**.

## 1. Bài toán: thiết bị gửi 1.000 sự kiện nhưng collector chỉ xử lý 990

Một cảm biến gửi số đo cứ mỗi giây hoặc nhanh hơn qua UDP tới một collector Spring Boot:

~~~text
device=node-7;epoch=boot-42;seq=1001;value=26.5
device=node-7;epoch=boot-42;seq=1002;value=26.6
device=node-7;epoch=boot-42;seq=1003;value=26.5
device=node-7;epoch=boot-42;seq=1004;value=26.7
~~~

Collector chạy `UnicastReceivingChannelAdapter`, nhận `Message<byte[]>` rồi chuyển vào `MessageChannel`. Trong một khoảng quan sát, sender cho biết đã gọi gửi 1.000 lần nhưng phía lưu trữ chỉ có 990 bản ghi.

**Không được kết luận ngay rằng UDP làm mất chính xác 10 gói**. Cần phân biệt:

1. Sender có **thực sự tạo và giao đủ 1.000 datagram cho network stack** không?
2. Mỗi datagram có **đến máy nhận và tới UDP socket** không?
3. UDP inbound adapter có **đọc và phát message** cho mỗi datagram nhận được không?
4. Bộ chuyển đổi `byte[]` có **loại gói sai size, framing, encoding hoặc schema** không?
5. Service có **ghi DB thành công** không, hay transaction lỗi hoặc bị rollback?
6. Có gói **gửi lại/trùng**, đến **sai thứ tự**, hoặc sender **khởi động lại và đặt lại sequence** không?

~~~mermaid
flowchart LR
    A["Sender<br/>gửi datagram"] --> B["Mạng IP / firewall / NAT"]
    B --> C["UDP socket<br/>và kernel buffer"]
    C --> D["UDP inbound adapter"]
    D --> E["MessageChannel"]
    E --> F["Decode + validate"]
    F --> G["Service + DB"]
    A -.-> L1["Đo send_attempt"]
    C -.-> L2["Đo received"]
    F -.-> L3["Đo rejected"]
    G -.-> L4["Đo committed"]
~~~

Một message chưa được lưu có thể đã bị mất trên mạng, bị bỏ trước socket, bị từ chối ở converter hoặc lỗi ở downstream. Phương án xử lý cho từng trường hợp **khác nhau**.

## 2. “Không bảo đảm” trong UDP nghĩa là gì?

UDP là giao thức datagram không thiết lập kết nối, không cung cấp các đảm bảo kiểu TCP về truyền lại và thứ tự. Một lần gửi tương ứng một datagram; hệ điều hành sender có thể nhận lời gọi gửi mà datagram vẫn không tới nơi.

| Tính chất | UDP tự bảo đảm? | Ý nghĩa với Spring Integration |
|---|---|---|
| Datagrams được chuyển tới receiver | **Không** | Nếu gói mất trước socket, inbound adapter không có message để phát |
| Datagrams đến đúng thứ tự | **Không** | Handler có thể quan sát sequence 10, 12 rồi mới thấy 11 |
| Không có gói trùng ở tầng ứng dụng | **Không** | Retry hoặc cơ chế upstream có thể tạo dữ liệu lặp; receiver nên có ID để nhận diện |
| ACK từ receiver | **Không** | Phải triển khai giao thức ACK ở tầng ứng dụng hoặc dùng tùy chọn ACK tương thích giữa hai endpoint |
| Retry khi gói mất | **Không** | Phải có chính sách phát lại, timeout và nơi giữ bản ghi để retry |
| Backpressure tới sender | **Không** | Khi receiver quá tải, datagram có thể bị loại bỏ mà sender không hay biết |
| Lưu bền/replay | **Không** | Socket/kernel buffer không phải durable queue |
| Ranh giới từng datagram | **Có** | Receiver nhận từng đơn vị dữ liệu, không phải TCP byte stream |
| Checksum UDP/IP | Có cơ chế phát hiện một số lỗi truyền | Không đồng nghĩa bảo mật, xác thực sender hoặc giao hàng đáng tin cậy |

Sự kiện `MessageChannel.send(...)` trả về `true` ở sender chỉ nói lên việc dispatch message theo semantics của channel. Nếu outbound UDP handler đã gửi datagram mà không có exception, điều đó vẫn **không xác nhận** receiver đã nhận, parse hoặc ghi dữ liệu.

### 2.1. Datagram bị mất có thể xảy ra ở đâu?

- **Phía sender:** dữ liệu chưa serialize đúng, sai địa chỉ/port, lỗi DNS hoặc không có subscriber trong integration flow.
- **Lớp socket sender:** giới hạn kernel/send buffer, cấu hình interface và các lỗi I/O cục bộ.
- **Đường mạng:** tắc nghẽn, router/switch bỏ gói, policy firewall, NAT timeout, IP fragmentation không ghép lại được.
- **Máy nhận:** kernel receive buffer đầy, receiver chưa bind port, listener bị stop hoặc đang restart.
- **Spring Integration:** lỗi nhận/dispatch, handler đồng bộ chạy quá lâu, queue downstream đầy, lỗi mapper/framing.
- **Nghiệp vụ:** UTF-8/JSON sai, dữ liệu bị từ chối, DB lỗi, transaction rollback hoặc retry tạo trùng.

Hãy gọi đúng tên từng loại lỗi. **Gói không tới socket** không thể đi vào `errorChannel` của Spring Integration vì ứng dụng chưa hề tạo `Message` từ gói đó.

### 2.2. Checksum và framing có giải quyết được mất gói?

**Không.** Checksum giúp phát hiện một số sai lệch bit trong quá trình truyền. Tùy chọn UDP **length check** của Spring Integration có thể thêm prefix độ dài để receiver phát hiện một số datagram bị cắt ngắn bởi receive buffer.

Cả hai cơ chế này **không yêu cầu network gửi lại datagram**, không bảo đảm thứ tự, cũng không cung cấp xác nhận xử lý nghiệp vụ. Một datagram mất hoàn toàn thì receiver không có bytes để đối chiếu độ dài.

## 3. Vì sao sequence giúp quan sát nhưng không phải bằng chứng tuyệt đối?

Giao thức UDP không cung cấp số thứ tự nghiệp vụ. Sender có thể tự thêm:

~~~text
device=node-7;epoch=boot-42;seq=1001;value=26.5
~~~

Trong đó:

- **`device`**: định danh thiết bị theo hợp đồng, phải được xác thực nếu môi trường cần.
- **`epoch`**: định danh một lần khởi động hoặc thế hệ sequence, giúp tránh nhầm khi sender reset bộ đếm.
- **`seq`**: số thứ tự tăng dần **trong một epoch của một thiết bị**.
- **`value`**: dữ liệu nghiệp vụ, trong ví dụ là nhiệt độ hoặc số đo.

### 3.1. Những tình huống có thể thấy

| Thứ tự nhận được | Quan sát | Chưa thể kết luận |
|---|---|---|
| 101, 102, 103 | Liên tiếp | Không chứng minh mọi gói trước đó đã đến |
| 101, 103 | Có khoảng thiếu số 102 | 102 có thể đang đến muộn, sender bỏ qua 102 hoặc đã mất |
| 101, 103, 102 | 102 đến sau 103 | Có **đảo thứ tự**; chưa chắc mất gói |
| 101, 102, 102 | Cùng sequence xuất hiện lần hai | Có khả năng gửi trùng/retry; cần ID/epoch để xác nhận |
| 101, 102, 1 | Sequence giảm đột ngột | Có thể sender reboot/reset hoặc gói cũ đến muộn |
| boot-42: 101, boot-43: 1 | Bắt đầu epoch mới | Không nối hai bộ đếm thành cùng một dải sequence |

Một **khoảng thiếu** nên được đánh dấu là *gap observed*, không phải *permanent packet loss* ngay lập tức. Hệ thống có thể đợi một **reordering window** theo thời gian hoặc số sequence rồi mới ước lượng mất gói.

### 3.2. Sequence và event ID

Để nhận diện trùng trong nhiều lần restart, khóa của một sự kiện nên đủ ổn định, chẳng hạn:

~~~text
(deviceId, epoch, seq)
~~~

Nếu sender có nhiều stream độc lập, có thể cần thêm **stream ID**. Nếu ID có thể tái sử dụng sau khi hết dải hoặc reset, phải định nghĩa quy tắc epoch và rollover.

IP/port nguồn UDP không phù hợp làm khóa dài hạn vì có thể thay đổi do NAT, DHCP, thiết bị di động hoặc port động; một public IP cũng có thể đại diện cho nhiều thiết bị.

## 4. Thiết kế ba mức kỳ vọng giao hàng

| Mô hình | Cách hoạt động | Điểm mạnh | Đánh đổi |
|---|---|---|---|
| **Best effort** | Gửi UDP một lần, không yêu cầu ACK/retry | Độ trễ và overhead nhỏ, phù hợp số đo mới nhất | Mất gói có thể không được phục hồi |
| **At-least-once ở tầng ứng dụng** | Sender giữ sự kiện, retry tới khi nhận ACK phù hợp | Có thể phục hồi nhiều tình huống mất gói/ACK | Receiver có thể nhận trùng, cần idempotency |
| **Hiệu ứng nghiệp vụ một lần** | At-least-once + unique key/transaction ở receiver | Có thể tránh ghi nghiệp vụ trùng trong phạm vi thiết kế | Tốn trạng thái bền và phối hợp transaction; không phải đảm bảo sẵn của UDP |

Không gọi phương án thứ ba là **UDP exactly-once delivery**. Hai bên có thể tạo **hiệu ứng ghi dữ liệu một lần** bằng idempotency trong DB, nhưng network vẫn có thể giao lại nhiều lần; tính đúng đắn còn phụ thuộc transaction, nhận dạng event, retention, replay và các side effect khác.

**Chọn theo dữ liệu:**

- Nhiệt độ mới nhất được gửi lại đều đặn: mất một số gói thường có thể chấp nhận; hiển thị giá trị mới nhất và đo freshness.
- Số đếm tích lũy: có thể gửi **giá trị tổng hiện tại** thay vì mọi delta để dễ phục hồi sau mất gói.
- Lệnh mở khóa, thanh toán hoặc phát sinh nghiệp vụ không thể bỏ qua: cần xác nhận xử lý, lưu bền, chống trùng và thường nên chọn giao thức/broker đáng tin cậy hơn.
- Âm thanh/video thời gian thực: có thể dùng cơ chế thích nghi, jitter buffer, sequence, sửa lỗi hoặc giao thức chuyên dụng, thay vì cố truyền lại mọi gói quá muộn.

## 5. Cấu hình UDP inbound adapter và MessageChannel

Bài thực hành dùng **Spring Boot**, **Spring Integration IP**, **Java 17+** và cổng UDP `12018`. Với Spring Boot dependency management, thường có thể thêm:

~~~xml
<!-- pom.xml: nằm bên trong <dependencies> -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

Tạo một flow nhận UDP và đưa bytes vào channel:

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
public class UdpLossDemoConfig {

    @Bean("udpRawTelemetry")
    public MessageChannel udpRawTelemetry() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow udpLossInboundFlow() {
        return IntegrationFlow.from(
                    Udp.inboundAdapter(12018)
                        .receiveBufferSize(2048)
                        .lengthCheck(false))
                .channel("udpRawTelemetry")
                .get();
    }
}
~~~

Trong ví dụ:

1. `Udp.inboundAdapter(12018)` lắng nghe datagram UDP unicast.
2. `receiveBufferSize(2048)` là dung lượng để đọc **một datagram**, không phải hàng đợi cho nhiều gói.
3. `lengthCheck(false)` tương thích với sender dùng UDP raw UTF-8. Chỉ bật `lengthCheck(true)` khi sender và receiver cùng dùng framing của Spring Integration.
4. `DirectChannel` dispatch message đồng bộ; handler phải có chính sách rõ ràng nếu xử lý chậm hoặc phát sinh lỗi.
5. Không cần poller để lấy datagram; inbound adapter nhận theo socket, còn poller chỉ cần với nguồn dữ liệu khác như file/DB được kiểm tra theo lịch.

Tăng `receiveBufferSize` có thể giảm nguy cơ *cắt ngắn gói lớn*, nhưng không phục hồi gói đã mất trên mạng hoặc những datagram bị kernel loại vì socket receive queue đầy.

## 6. Tạo contract và parser để quan sát sequence

Ví dụ payload:

~~~text
device=node-7;epoch=boot-42;seq=1001;value=26.5
~~~

Định nghĩa DTO:

~~~java
import java.math.BigDecimal;

public record TelemetryDatagram(
        String deviceId,
        String epoch,
        long sequence,
        BigDecimal value) {
}
~~~

Parser chuyển raw bytes sang DTO và từ chối gói không hợp lệ:

~~~java
import java.math.BigDecimal;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class TelemetryDatagramParser {

    private TelemetryDatagramParser() {}

    public static TelemetryDatagram parse(byte[] bytes) {
        if (bytes.length == 0 || bytes.length > 512) {
            throw new IllegalArgumentException(
                    "UDP payload length outside 1..512 bytes");
        }

        final String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException(
                    "Malformed UTF-8 telemetry", ex);
        }

        String[] parts = text.split(";", -1);
        if (parts.length != 4
                || !parts[0].startsWith("device=")
                || !parts[1].startsWith("epoch=")
                || !parts[2].startsWith("seq=")
                || !parts[3].startsWith("value=")) {
            throw new IllegalArgumentException(
                    "Unexpected telemetry schema");
        }

        String device = parts[0].substring("device=".length());
        String epoch = parts[1].substring("epoch=".length());
        String seqText = parts[2].substring("seq=".length());
        String valueText = parts[3].substring("value=".length());

        if (!device.matches("[A-Za-z0-9_-]{1,32}")
                || !epoch.matches("[A-Za-z0-9_-]{1,40}")
                || !seqText.matches("\\d{1,18}")
                || !valueText.matches("-?\\d{1,3}(\\.\\d{1,2})?")) {
            throw new IllegalArgumentException(
                    "Invalid telemetry field");
        }

        long seq = Long.parseLong(seqText);
        BigDecimal value = new BigDecimal(valueText);
        return new TelemetryDatagram(device, epoch, seq, value);
    }
}
~~~

Parser chỉ bảo đảm **kích thước, charset, schema và định dạng các trường**. Nó **không** chứng minh datagram được gửi từ thiết bị hợp lệ hoặc rằng dữ liệu đã đến đúng thứ tự. Nếu triển khai thật, thêm xác thực message/device, kiểm soát version, ngưỡng đo, epoch và quota theo nguồn.

Với `lengthCheck(true)`, Spring Integration có thể dùng prefix độ dài 4 byte để phát hiện datagram bị cắt ngắn; muốn dùng phải thiết lập tương thích ở sender và receiver. Parser không thể tìm lại phần byte đã mất trước khi được gọi.

## 7. Theo dõi gap và gói đến muộn trong Service Activator

Ví dụ observer sau giữ **highest sequence** đã thấy theo mỗi `deviceId + epoch`. Nó giúp quan sát, chưa phải bộ chống trùng dùng cho giao dịch tiền hoặc cơ chế phục hồi message.

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.ip.IpHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class UdpSequenceObserver {

    private static final Logger log =
            LoggerFactory.getLogger(UdpSequenceObserver.class);

    // Demo: state trong memory, không bền sau restart.
    private final ConcurrentMap<String, Long> highestByStream =
            new ConcurrentHashMap<>();

    @ServiceActivator(inputChannel = "udpRawTelemetry")
    public void observe(Message<byte[]> message) {
        final TelemetryDatagram event;
        try {
            event = TelemetryDatagramParser.parse(message.getPayload());
        } catch (IllegalArgumentException ex) {
            log.warn("Rejected UDP telemetry: {}", ex.getMessage());
            return;
        }

        String sourceIp = message.getHeaders()
                .get(IpHeaders.IP_ADDRESS, String.class);
        String key = event.deviceId() + "|" + event.epoch();

        highestByStream.compute(key, (stream, previous) -> {
            if (previous == null) {
                log.info("First sequence in stream={}, seq={}, source={}",
                        stream, event.sequence(), sourceIp);
                return event.sequence();
            }

            if (event.sequence() > previous) {
                if (event.sequence() - previous > 1L) {
                    log.warn(
                        "GAP_OBSERVED stream={}, missing-range={}..{}",
                        stream, previous + 1L, event.sequence() - 1L);
                }
                return event.sequence();
            }

            log.info(
                "LATE_OR_DUPLICATE stream={}, seq={}, highest={}",
                stream, event.sequence(), previous);
            return previous;
        });

        // Việc quyết định ghi DB/ACK là bước riêng của ứng dụng.
        // Chưa được coi highestByStream là cơ chế dedup hoàn chỉnh.
    }
}
~~~

Đối với một khóa `device+epoch`, `ConcurrentHashMap.compute(...)` cập nhật trạng thái atomically trong phạm vi map của process. Tuy nhiên:

- `seq` nhỏ hơn `highest` có thể là **gói đến muộn**, không nhất thiết trùng. Muốn phân biệt phải lưu tập sequence đã thấy trong một **cửa sổ giới hạn**.
- Một gap có thể được lấp đầy khi gói đến muộn. Nên có *grace period* hoặc window trước khi thống kê “thiếu lâu dài”.
- Nếu chạy nhiều instance, mỗi instance nhìn thấy một tập gói khác nhau. Trạng thái in-memory cục bộ **không phải dữ liệu toàn cụm**.
- Nếu sender reboot và thay epoch, bắt đầu một stream mới; nếu epoch không đổi nhưng seq reset, observer có thể phân loại nhầm.
- Nếu không xóa stream không hoạt động, map có thể lớn vô hạn. Production phải đặt TTL/retention và giới hạn số stream.
- Logic quan sát **không thay thế unique constraint hoặc idempotency** khi dữ liệu không được ghi trùng.

Đây là ví dụ dùng nhận dạng và theo dõi, không phải giải pháp at-least-once hoàn chỉnh.

## 8. Gửi test để thấy gap, reorder và repeat

Khởi động ứng dụng với các class trên, mở PowerShell trên cùng host và gửi lần lượt sequence **1, 2, 4, 3, 4**:

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new()

try {
    foreach ($seq in @(1, 2, 4, 3, 4)) {
        $text = "device=node-7;epoch=boot-42;seq=$seq;value=26.5"
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)

        [void]$client.Send(
            $bytes, $bytes.Length, "127.0.0.1", 12018)
    }
}
finally {
    $client.Dispose()
}
~~~

Trong điều kiện loopback nhận đủ và đúng thứ tự gửi, log minh họa:

~~~text
First sequence in stream=node-7|boot-42, seq=1
GAP_OBSERVED stream=node-7|boot-42, missing-range=3..3
LATE_OR_DUPLICATE stream=node-7|boot-42, seq=3, highest=4
LATE_OR_DUPLICATE stream=node-7|boot-42, seq=4, highest=4
~~~

**Đọc đúng kết quả:** ví dụ trên **cố ý gửi sequence không liên tiếp** theo thứ tự [1, 2, 4, 3, 4]. Nó minh họa cách observer phát hiện và phân loại, **không phải phép đo tỷ lệ mất gói thật của mạng**. Khi UDP thực tế mất một datagram, không có log “datagram dropped” tự động ở tầng Spring vì không có message tương ứng.

Thêm các thử nghiệm:

1. Gửi `1, 2, 3, 4` để thấy luồng liên tiếp bình thường.
2. Gửi `1, 3` rồi chờ một khoảng hợp lý, quan sát gap chưa được lấp.
3. Gửi `1, 3, 2` để thấy gap có thể được bù bởi gói đến muộn.
4. Gửi lại `3` nhiều lần để kiểm tra observer không xem đó là message mới hơn.
5. Đổi `epoch=boot-43` và gửi `seq=1` để thử trường hợp thiết bị khởi động lại.
6. Tắt listener, gửi vài sequence, bật lại rồi gửi tiếp; xem hậu quả của thời gian không có socket nghe.

Việc `UdpClient.Send` hoàn tất **không chứng minh** receiver đã nhận. Với network test, nên kết hợp packet capture tại máy gửi và máy nhận, sequence, metric socket/adapter và kết quả ghi DB.

## 9. Ước lượng mất gói bằng số thứ tự

Khi **thực sự biết sender đã phát đủ dải liên tục**, ví dụ `seq=1..1000`, phía nhận có thể tính:

~~~text
Số sequence dự kiến      = 1000
Số sequence duy nhất nhận = 990
Số sequence chưa quan sát = 10

Tỷ lệ chưa quan sát = 10 / 1000 = 1%
~~~

Con số **1%** ở đây là tỷ lệ chưa quan sát trong cửa sổ đã xét, chỉ có thể xem gần như mất gói nếu thỏa mãn các giả định: sender thật sự phát đủ 1.000 event trong cùng epoch; không bỏ sequence; bên nhận đã đợi hết reordering window; đã loại trùng và không nhầm version/epoch.

Nếu collector ghi DB được 990 bản ghi nhưng inbound adapter nhận 998 datagram thì 8 bản ghi còn thiếu **có thể do validate hoặc lỗi downstream**. Phải có metric riêng cho từng bước:

| Metric gợi ý | Ý nghĩa |
|---|---|
| `udp_send_attempt_total` | Sender đã cố gọi gửi bao nhiêu datagram |
| `udp_send_local_error_total` | Lỗi encode/dispatch/socket gửi tại sender |
| `udp_receive_total` | Inbound adapter nhận và đưa vào xử lý bao nhiêu message |
| `udp_invalid_payload_total` | Gói bị reject vì size, encoding, framing hoặc schema |
| `udp_sequence_gap_observed_total` | Số khoảng sequence thiếu được quan sát ban đầu |
| `udp_sequence_late_total` | Message có sequence thấp hơn mức cao nhất đã thấy |
| `udp_duplicate_confirmed_total` | Trùng thực sự được xác nhận bằng ID/seen set hoặc DB unique |
| `udp_business_committed_total` | Số sự kiện đã commit thành công theo nghiệp vụ |
| `udp_ack_timeout_total` | Số lần sender chưa nhận ACK trong khoảng chờ, nếu dùng ACK |

Không ghi một `deviceId` hoặc `IP:port` mới thành label metric cho mọi thiết bị vô hạn; cardinality có thể bùng nổ. Dùng trace/log có giới hạn hoặc aggregation phù hợp.

## 10. ACK và retry có làm UDP đáng tin cậy hơn không?

**Có thể**, nhưng độ tin cậy mới đến từ **giao thức ứng dụng**, trạng thái bền và cơ chế xử lý lỗi do hai bên triển khai. UDP không tự tạo điều đó.

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant N as UDP network
    participant R as Receiver
    participant D as Database

    S->>N: eventId=abc, seq=42
    N->>R: Datagram
    R->>D: Validate + INSERT idempotent
    D-->>R: Transaction committed
    R-->>S: ACK(eventId=abc)
    Note over S: Nếu chưa có ACK trước timeout
    S->>N: Retry cùng eventId=abc
    N->>R: Datagram trùng có thể tới
    R->>D: Kiểm tra unique key / no-op
    R-->>S: ACK(eventId=abc) lần nữa
~~~

**Một protocol ACK nên quy định rõ:**

- ACK được gửi khi **socket nhận được gói**, khi **parser hợp lệ**, hay chỉ sau **transaction commit**?
- ACK chứa **event ID/sequence**, version, identity và thông tin xác thực nào?
- Sender chờ bao lâu, retry bao nhiêu lần, có *exponential backoff + jitter* và giới hạn tốc độ không?
- Sender lưu event ở đâu để retry sau restart? Trong RAM hay **durable outbox/queue**?
- Receiver xử lý thế nào khi nhận cùng event nhiều lần?
- Khi ACK bị mất nhưng DB đã commit, sender retry sẽ được nhận lại ACK như thế nào?
- Thời hạn retention của ID chống trùng và trạng thái pending là bao lâu?

**ACK kỹ thuật khác ACK nghiệp vụ.** Nếu receiver phản hồi ngay khi đọc datagram nhưng DB lỗi sau đó, sender có thể đã coi sự kiện hoàn thành trong khi dữ liệu chưa lưu.

### 10.1. Mất gói và mất ACK tạo hai kịch bản khác nhau

| Tình huống | Sender nhìn thấy | Receiver thực tế | Cần xử lý |
|---|---|---|---|
| Datagram không đến | ACK timeout | Không có event | Sender retry theo chính sách |
| Datagram đến, ACK mất | ACK timeout | Có thể đã commit | Sender retry; receiver idempotent và ACK lại |
| Datagram đến, DB lỗi | ACK timeout hoặc NACK theo protocol | Chưa commit | Retry sau khi nguồn lỗi được xử lý |
| ACK đến trễ | Có thể đã retry | Một hoặc nhiều bản sao tới receiver | Ghép ACK theo ID, chống trùng |
| Sender restart trước ACK | Pending event có thể mất nếu chỉ ở RAM | Trạng thái receiver chưa rõ | Durable outbox và phục hồi pending |

Một lời gọi gửi thành công **không xác nhận ACK**, còn ACK nhận được chỉ có ý nghĩa theo **thời điểm và hợp đồng** mà receiver hứa.

### 10.2. ACK do Spring Integration UDP hỗ trợ

Spring Integration có cơ chế **UDP application-level acknowledgement** tùy chọn giữa các endpoint tương thích, với cấu hình như `acknowledge`, địa chỉ/port ACK, `ack-timeout`; multicast còn có ngưỡng `min-acks-for-success` trong các phiên bản hỗ trợ.

Khi dùng tùy chọn này, sender/receiver phải cùng hiểu framing ACK của thư viện. Nó **không tự định nghĩa “đã commit database”**, không biến UDP thành broker bền vững và không cung cấp exactly-once effect cho nghiệp vụ của bạn.

Trong multicast, **đòi ACK từ mọi receiver** có nguy cơ tạo *ACK implosion* khi hàng trăm/thousands receiver phản hồi cùng lúc. `min-acks-for-success` chỉ xác định **số ACK tối thiểu**, không bảo đảm mọi thành viên nhóm đã xử lý. Hãy cân nhắc cơ chế phân phối đáng tin cậy khác khi cần xác nhận từng subscriber.

## 11. Idempotency ở receiver: chặn ghi trùng như thế nào?

Nếu sender retry cùng event, receiver có thể nhận nhiều datagram trùng nhau. Một cách kiểm soát hiệu quả là **unique key ở nơi lưu bền**.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE udp_telemetry (
    device_id    text NOT NULL,
    epoch        text NOT NULL,
    seq          bigint NOT NULL,
    measured_val numeric(12, 2) NOT NULL,
    received_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (device_id, epoch, seq)
);
~~~

Khi nhận một event đã được validate, ghi trong transaction:

~~~sql
INSERT INTO udp_telemetry (device_id, epoch, seq, measured_val)
VALUES ('node-7', 'boot-42', 42, 26.5)
ON CONFLICT (device_id, epoch, seq) DO NOTHING;
~~~

Nếu key đã tồn tại, bản ghi trùng **không được chèn thêm**. Nếu hệ thống còn tác động khác như phát sự kiện sang Kafka hoặc gọi HTTP, cũng phải thiết kế sao cho retry không nhân đôi side effect; một unique constraint trên bảng DB không tự chặn mọi side effect ở hệ thống khác.

**Thứ tự quan trọng khi ACK mang nghĩa “đã lưu bền”:**

1. Parse, kiểm tra version/schema và xác thực sender.
2. Mở transaction phù hợp.
3. Ghi bản ghi theo **idempotency key**; xử lý duplicate theo chính sách.
4. Commit transaction thành công.
5. Sau đó mới gửi **ACK nghiệp vụ** có cùng event ID.

Nếu ACK được gửi **trước commit** và process crash, sender có thể xóa pending event trong khi DB chưa lưu. Nếu commit thành công nhưng ACK thất lạc, sender có thể retry; receiver cần trả ACK cho bản ghi đã tồn tại, nếu hợp đồng cho phép.

**Không tự gửi NACK cho bất kỳ datagram không đáng tin cậy** mà không kiểm soát nguồn và kích thước, vì UDP source IP có thể bị giả mạo; hệ thống có thể trở thành bộ phản xạ UDP.

## 12. Sender lưu sự kiện ở đâu để retry?

Nếu sender chỉ giữ event trong một `ConcurrentHashMap` trong RAM, process restart sẽ làm mất danh sách pending. Một mô hình tin cậy hơn là **outbox bền**:

~~~mermaid
flowchart TD
    A["Nguồn nghiệp vụ"] --> B["Persist event + outbox"]
    B --> C["Sender đọc pending"]
    C --> D["UDP outbound handler"]
    D --> E["Network / Receiver"]
    E --> F["Validate + commit idempotent"]
    F --> G["ACK theo event ID"]
    G --> H["Đánh dấu outbox hoàn thành"]
    C --> I{"ACK timeout?"}
    I -->|Có| J["Retry có giới hạn / backoff"]
    J --> D
~~~

Những trường tối thiểu trong outbox:

~~~text
event_id, destination, payload_bytes, attempt_count,
next_attempt_at, state, created_at, last_error
~~~

Quy tắc:

- Chỉ xóa hoặc đánh dấu hoàn thành khi nhận đúng **ACK theo hợp đồng**.
- Khi timeout, không kết luận chắc chắn là gói mất; thực hiện retry với **cùng event ID**.
- Giới hạn số lần/thời gian retry và kích thước hàng pending; có metric và cơ chế xử lý sự kiện không thể gửi.
- Nếu phải gửi tới nhiều đích, lưu trạng thái theo **event + destination**, tránh một receiver ACK thay cho tất cả.
- Không đẩy các payload lỗi schema vào retry vô hạn; lỗi xác định thường cần sửa dữ liệu, không phải phát lại.
- Khi sender restart, tải lại pending theo trạng thái đã lưu.

Spring Integration giúp ghép `MessageChannel` và adapter vào pipeline này. Tuy nhiên, để có lưu bền/điều phối retry đáng tin cậy, cần DB/broker và transaction thích hợp; một `QueueChannel` chỉ tồn tại trong RAM không tự có tính bền.

## 13. Vì sao cần backoff và giới hạn retry?

Nếu collector tạm ngừng hoạt động trong 30 giây, hàng nghìn sender retry liên tục có thể khiến collector quá tải ngay lúc trở lại.

Chiến lược phù hợp thường gồm:

| Biện pháp | Ý nghĩa |
|---|---|
| **ACK timeout hợp lý** | Phù hợp RTT và độ trễ xử lý cam kết, tránh timeout quá ngắn |
| **Exponential backoff** | Tăng khoảng cách giữa các lần retry liên tiếp |
| **Jitter** | Tránh nhiều sender cùng retry vào đúng một thời điểm |
| **Max attempts hoặc max age** | Tránh giữ message lỗi vô hạn |
| **Rate limiting** | Không vượt sức chịu đựng của network và receiver |
| **Circuit breaker / pause có kiểm soát** | Giảm tải khi đích liên tục lỗi, nếu áp dụng vào kiến trúc |
| **Dead-letter / quarantine** | Điều tra lỗi không thể giải quyết bằng retry |
| **Metrics và cảnh báo** | Theo dõi pending queue, số retry, độ trễ ACK, tỷ lệ commit |

Các giá trị timeout, số lần retry và retention phải dựa trên yêu cầu nghiệp vụ. Dữ liệu telemetry “giá trị mới nhất” có thể bỏ những bản ghi quá cũ; lệnh thay đổi trạng thái quan trọng phải được xử lý bằng hợp đồng mạnh hơn.

## 14. Mất gói, đảo thứ tự và chính sách xử lý dữ liệu

Cách xử lý không chỉ dựa vào UDP mà còn tùy **ý nghĩa sự kiện**:

| Kiểu dữ liệu | Nếu mất một gói | Nếu gói đến muộn | Cách xử lý gợi ý |
|---|---|---|---|
| **Gauge**: nhiệt độ hiện tại | Giá trị mới tiếp theo có thể thay thế | Có thể bỏ gói cũ để không ghi đè giá trị mới | Chỉ cập nhật khi sequence/timestamp mới hơn |
| **Counter tích lũy** | Giá trị tổng kế tiếp có thể bù thông tin | Kiểm tra rollover/reset | Gửi tổng hiện tại và epoch |
| **Delta**: tăng thêm +1 | Có thể mất thay đổi vĩnh viễn | Phải bảo toàn logic order/dedup | ACK/retry/idempotency hoặc broker |
| **Command**: mở/đóng thiết bị | Mất lệnh là lỗi nghiêm trọng | Thực hiện trễ có thể nguy hiểm | Command ID, TTL, auth, ACK sau thực hiện |
| **Stream realtime** | Có thể che giấu một phần mất gói | Gói quá trễ không còn ích lợi | Jitter buffer, sequence, policy bỏ trễ |
| **Dữ liệu tài chính** | Không được phép mất | Không được phát sinh hai lần | Durable transport, transaction và idempotency |

Nếu nghiệp vụ chỉ cần **trạng thái mới nhất**, hãy xác định quy tắc “sự kiện có sequence mới hơn thắng”. Nếu phải **tích lũy từng delta**, bỏ gói cũ sẽ làm sai tổng; cần chính sách đảm bảo khác. Phân biệt hai loại sự kiện này trước khi viết retry.

### 14.1. Timestamp không thay thế sequence

Timestamp có thể giúp xử lý độ mới, nhưng đồng hồ giữa các thiết bị có thể lệch, nhảy giờ hoặc bị đồng bộ lại. Sequence trong một epoch phù hợp hơn để phát hiện gap theo thứ tự gửi; timestamp vẫn có thể dùng bổ sung cho **event time**, deadline và độ mới của dữ liệu.

### 14.2. Reorder window và giới hạn bộ nhớ

Muốn phân biệt `late` với `duplicate`, receiver có thể giữ tập sequence đã thấy trong **cửa sổ giới hạn** (ví dụ theo thời gian hoặc 256 sequence gần nhất). Khi sự kiện cũ vượt cửa sổ, hệ thống có thể không còn đủ trạng thái để xác minh nó đã từng đến.

Đừng giữ mọi sequence mãi mãi trong RAM. Với giao dịch cần độ tin cậy, dùng ID và nơi lưu bền có **unique constraint** phù hợp để quyết định idempotency.

## 15. Quản lý lifecycle và shutdown khi sử dụng UDP

UDP inbound adapter chỉ nhận khi socket đang lắng nghe. Khi service stop, restart, container redeploy hoặc port bị firewall chặn, sender có thể vẫn gọi `send()` thành công mà receiver không có message.

~~~mermaid
sequenceDiagram
    participant S as UDP sender
    participant A as Receiver cũ
    participant B as Receiver mới
    S->>A: seq=100
    Note over A: stop / shutdown
    S-->>A: seq=101 (có thể mất)
    Note over B: start + bind socket
    S->>B: seq=102
    Note over B: observer thấy khoảng thiếu 101
~~~

Cần quản lý:

1. **Readiness thực tế**: ứng dụng khởi động không đồng nghĩa listener đã bind. Có thể quan sát `UdpServerListeningEvent` hoặc `isListening()` theo API phiên bản.
2. **Thời gian stop/start**: datagram trong khoảng không có listener không được replay tự động.
3. **Công việc đang xử lý**: nếu downstream dùng `ExecutorChannel` hoặc queue, việc dừng listener không đồng nghĩa đã commit hết message.
4. **Rolling deployment**: nếu không chấp nhận mất gói trong cửa sổ chuyển instance, cần đảm bảo ở hệ thống gửi/điều phối hoặc chuyển sang broker.
5. **Multicast**: join group/network membership và interface có thể thay đổi lúc restart; cần xác nhận đã join và nhận thử gói.

Tùy chọn `SO_TIMEOUT` chỉ quy định thời gian chờ một lần socket `receive()`; nó **không làm sender tự retry**, không ngăn mất gói khi endpoint dừng và không thay thế timeout xử lý nghiệp vụ.

## 16. Bảo mật: ACK và retry có thể bị lợi dụng

Một UDP endpoint nhận gói từ nguồn không tin cậy cần cân nhắc:

- **Source IP/port có thể bị giả mạo** trong một số mạng. Không xác thực thiết bị chỉ bằng `ip_address` hoặc `ip_packetAddress`.
- **Trả ACK với payload lớn hơn yêu cầu** có thể tạo nguy cơ UDP reflection/amplification. Đặt phản hồi nhỏ, giới hạn tần suất và kiểm tra source/message.
- **Replay:** kẻ gửi lại một datagram cũ có thể tạo side effect nếu thiếu event ID, nonce/epoch và deduplication.
- **Flood:** lượng datagram lớn có thể làm đầy socket buffer, queue và hệ thống log. Cần giới hạn byte, tốc độ, số nguồn và CPU sử dụng.
- **Payload lỗi:** parser cần kiểm tra UTF-8, size, schema, miền giá trị trước khi xử lý tốn tài nguyên.
- **Dữ liệu nhạy cảm:** UDP thuần không mã hóa. Dùng một cơ chế xác thực/mã hóa phù hợp hoặc network bảo vệ khi cần.
- **ACK giả:** nếu sender tin mọi ACK không xác thực, có thể xóa pending event dù receiver thật chưa nhận; cần ràng buộc ACK với event và nguồn tin cậy.

Không triển khai echo/ACK công khai không kiểm soát và không dùng source port động làm danh tính dài hạn.

## 17. Chẩn đoán theo tầng khi nghi ngờ mất gói

| Hiện tượng | Nơi cần kiểm tra | Dữ liệu hữu ích |
|---|---|---|
| Sender thấy gửi thành công nhưng receiver không có log | IP/port, DNS, firewall, route, NAT, socket bind | Packet capture ở cả hai đầu |
| Chỉ mất gói khi payload lớn | PMTU, IP fragmentation, receive-buffer-size | Độ dài datagram, packet capture, config framing |
| Mất gói khi tải tăng | Kernel UDP queue, CPU, handler đồng bộ, executor backlog | UDP drop counters, tốc độ gửi/nhận và thời gian handler |
| Gap xuất hiện rồi được lấp | UDP reorder hoặc xử lý song song | Sequence, event time và reorder window |
| Cùng event xuất hiện nhiều lần | Retry ở sender, app workflow, event duplication | Event ID, số attempt, unique key |
| DB thiếu record dù adapter có nhận | Parser, filter, transaction, DB/broker outage | Metric reject/commit, exception và rollback |
| ACK timeout nhưng DB đã có record | ACK bị mất/chậm sau commit | Receiver log theo event ID và idempotency |
| Thiếu data sau deploy | Receiver chưa ready, socket stop, load balancer UDP | Lifecycle/readiness và khoảng sequence |
| Multicast A nhận nhưng B không | Membership, IGMP, interface, switch/router, TTL | Capture/IGMP join ở từng host |

**Tách ba mệnh đề quan trọng:**

- “Sender gọi gửi” không chứng minh “receiver nhận”.
- “Receiver nhận datagram” không chứng minh “message hợp lệ”.
- “Message hợp lệ” không chứng minh “nghiệp vụ đã commit”.

Nhờ cách tách này, ta đặt metric và cách phục hồi ở đúng tầng.

## 18. Kiểm thử có ý nghĩa

### 18.1. Test parser và observer

Kiểm tra các dữ liệu xác định:

- `seq=1,2,3`: không báo gap.
- `seq=1,3`: báo gap 2.
- `seq=1,3,2`: sequence 2 đến muộn, không được tự tuyên bố vĩnh viễn mất.
- `seq=1,2,2`: observer thấy gói cũ/có thể trùng; dedup cần seen state.
- `epoch=boot-42, seq=100` rồi `epoch=boot-43, seq=1`: không nối hai epoch.
- Payload >512 byte, invalid UTF-8, sai schema: parser reject, không ghi nghiệp vụ.

Unit test observer không cần socket; khi muốn xác minh binder/header Spring Integration, phải dùng integration test với UDP client thật.

### 18.2. Test network và overload

Trên môi trường **lab được kiểm soát**, dùng sender phát sequence liên tiếp và có số liệu **sender thực sự đã tạo/gửi**. Đo ở receiver bao nhiêu sequence duy nhất đã nhận sau cửa sổ reorder. Mô phỏng network loss bằng công cụ điều kiện mạng của môi trường test hoặc firewall lab, rồi so sánh packet capture hai phía.

Tránh thử network impairment trên đường mạng production. Nếu chỉ gửi thử `1,2,4`, bạn mới mô phỏng **khoảng sequence**, chưa chứng minh mạng đã làm mất datagram 3.

### 18.3. Test retry sau mất ACK

1. Receiver nhận event `abc`, commit vào DB.
2. Trong môi trường test, chủ động không trả ACK lần đầu.
3. Sender timeout và gửi lại **cùng event ID**.
4. Receiver nhận diện duplicate bằng unique key và không ghi thêm bản sao.
5. Receiver gửi ACK phù hợp; sender đánh dấu pending đã hoàn tất.
6. Restart sender/receiver trong lúc pending để kiểm tra tính bền và hành vi phục hồi.

Đây là phép thử tích hợp có ý nghĩa đối với mô hình at-least-once. Chỉ kiểm tra `UdpClient.Send` không đủ để xác nhận toàn bộ protocol.

## 19. Bài thực hành tổng hợp

Thiết kế một ứng dụng **nhận telemetry UDP → kiểm tra → lưu database → gửi ACK nghiệp vụ**, với hợp đồng:

~~~text
v=1;device=node-7;epoch=boot-42;seq=1042;value=26.5
~~~

Thực hiện:

1. Thêm `v` vào parser và kiểm tra version trước khi tạo DTO.
2. Viết `Udp.inboundAdapter(12018)`, nhận `Message<byte[]>` và validate kích thước/UTF-8/schema.
3. Theo dõi **highest sequence** để quan sát gap; sau đó thiết kế **seen window** để phân biệt gói đến muộn với gói trùng trong phạm vi nhất định.
4. Đưa event vào DB có `PRIMARY KEY(device, epoch, seq)` hoặc một idempotency key phù hợp; dùng transaction bảo đảm không ghi trùng.
5. Chỉ ACK theo nghĩa “đã lưu bền” sau khi commit; nếu event trùng đã tồn tại hợp lệ, trả ACK theo cùng event ID.
6. Phía sender giữ outbox pending, retry có timeout/backoff/jitter và giới hạn retry.
7. Giả lập mất packet, mất ACK, receiver stop 10 giây, sender restart và payload sai schema. Ghi metric ở từng bước.
8. So sánh công sức và hiệu quả với phương án publish trực tiếp vào Kafka/AMQP/JMS hoặc gọi HTTP có ACK nghiệp vụ.

**Câu hỏi tự đánh giá:**

- Vì sao `MessageChannel.send() == true` không đồng nghĩa collector đã lưu sự kiện?
- Vì sao `seq=10, 12` chưa đủ để kết luận `11` đã mất vĩnh viễn?
- Nếu nhận sequence thấp hơn `highest`, làm sao phân biệt late với duplicate?
- Tại sao sender phải retry bằng cùng event ID?
- Nếu ACK mất nhưng DB đã commit, làm gì để retry không tạo thêm bản ghi?
- Vì sao một `QueueChannel` trong RAM không bảo đảm giữ event sau process crash?
- Vì sao tăng UDP receive buffer không phục hồi datagram đã mất trên đường truyền?
- Với multicast, vì sao ACK từ một receiver không bảo đảm tất cả receiver đều thành công?
- Khi nào nên chấp nhận best effort và khi nào phải chọn broker/transport đáng tin cậy?
- Nếu nguồn là file/SFTP/DB dùng poller rồi outbound UDP, cần đặt trạng thái retry ở đâu để không mất sự kiện đã poll?

## 20. Tài liệu tham khảo

- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): unicast/multicast, length check, ACK, inbound/outbound UDP adapter.
- [Spring Integration Reference — IP Configuration Attributes](https://docs.spring.io/spring-integration/reference/ip/endpoint-reference.html): receive buffer, acknowledgment, timeout và error channel.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): semantics của `DirectChannel`, executor và queue.
- [RFC 768 — User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768): định nghĩa datagram UDP.
- [RFC 8085 — UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085): hướng dẫn ứng dụng dùng UDP an toàn, kích thước gói, congestion, retransmission và timeout.
- [RFC 8900 — IP Fragmentation Considered Fragile](https://www.rfc-editor.org/rfc/rfc8900): rủi ro khi dựa vào IP fragmentation.

## Kết luận

**UDP không bảo đảm datagram đến đích, đúng thứ tự, không trùng hay được xử lý thành công.** Trong Spring Integration, inbound/outbound adapter và `MessageChannel` cung cấp cấu trúc để kết nối và xử lý message, nhưng không thể tự phục hồi một datagram đã mất trước khi ứng dụng nhận.

Hãy bắt đầu bằng **hợp đồng payload có ID/epoch/sequence**, đo riêng gửi/nhận/validate/commit và phân biệt gap tạm thời với dữ liệu thiếu lâu dài. Khi ứng dụng cần tăng độ tin cậy, xây dựng ACK nghiệp vụ, retry có giới hạn, outbox bền và idempotency hoặc chọn HTTP, JMS, AMQP, Kafka hay một transport phù hợp. Giải pháp đúng phụ thuộc vào việc nghiệp vụ **có thể bỏ qua giá trị cũ** hay **bắt buộc ghi nhận mỗi sự kiện**.
