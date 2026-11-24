# Kiểm thử UDP bằng test channel trong Spring Integration

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của **test channel** khi kiểm thử adapter, gateway, poller và `MessageChannel` trong Spring Integration.
- Phân biệt unit test decoder, channel-only test không mở socket và integration test dùng UDP datagram thật.
- Dùng `DirectChannel` làm đầu vào, `QueueChannel` làm điểm thu kết quả và `receive(timeout)` để assert payload cùng header.
- Kiểm thử `Message<byte[]>`, strict UTF-8, DTO, `IpHeaders`, các trường hợp sai hợp đồng và trường hợp không có message.
- Khởi tạo UDP inbound adapter trên **cổng 0**, chờ `isListening()` hoặc `UdpServerListeningEvent`, gửi packet bằng `DatagramSocket`.
- Kiểm tra outbound UDP bằng một receiver giả độc lập ngay trên loopback mà không cần server bên ngoài.
- Sử dụng `@SpringIntegrationTest`, `MockIntegrationContext`, wire tap, timeouts và cleanup đúng mục đích.
- Tránh test flaky và không rút ra kết luận sai về đảm bảo giao hàng, thứ tự hoặc xử lý nghiệp vụ của UDP.

Bài thuộc chương **Adapter UDP** trong module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành tích hợp file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, đồng thời xử lý hợp đồng message, lỗi và vòng đời. Với UDP, một phép kiểm thử đáng tin cậy cần phân biệt rõ **kiểm tra message nội bộ** với **kiểm tra datagram đi qua socket**.

## 1. Bài toán: từ datagram đến một message có thể kiểm chứng

Giả sử một sensor gửi telemetry đến UDP receiver:

~~~text
v=1;sensor=node-7;seq=42
~~~

Hợp đồng:

- Payload là UTF-8 dài từ 1 đến 512 byte.
- `v=1` là phiên bản được hỗ trợ.
- `sensor` là ID hợp lệ; `seq` là số nguyên không âm.
- Inbound adapter chuyển datagram thành `Message<byte[]>`.
- Transformer tạo DTO `Telemetry("node-7", 42)`.
- Header nguồn được giữ khi flow cần chẩn đoán hoặc phản hồi sender.

Khi viết test, ít nhất có ba câu hỏi:

1. **Decoder có chuyển đúng byte array thành DTO không?**
2. **Flow có đưa DTO vào đúng channel, giữ header đúng không?**
3. **UDP adapter thật có bind socket, nhận datagram và sinh message đúng không?**

Một bài test đơn lẻ hiếm khi kiểm tra tốt cả ba. Tách chúng thành các mức để lỗi xuất hiện ở đâu thì báo đúng tầng đó.

~~~mermaid
flowchart LR
    A["UDP DatagramSocket client"] --> B["UDP inbound adapter"]
    B -->|"Message<byte[]>"| C["MessageChannel"]
    C --> D["Validate + Transformer"]
    D -->|"Message<Telemetry>"| E["QueueChannel - test sink"]
    E --> F["JUnit receive(timeout), assert"]
~~~

Trong bài, **test channel** là một `MessageChannel` được đặt vào luồng để JUnit thu và kiểm tra kết quả. Spring Integration không yêu cầu một class bắt buộc tên `TestChannel`. `QueueChannel` là lựa chọn thường dùng vì test có thể chủ động nhận message bằng phương thức `receive`.

## 2. Ba cấp độ kiểm thử cần tách

| Mức | Đầu vào | Có UDP socket thật? | Xác minh được |
|---|---|---|---|
| **Unit test** | `byte[]` đưa trực tiếp vào hàm decode | Không | Length guard, charset, schema, DTO, lỗi parse |
| **Channel-only test** | `Message<byte[]>` đưa vào `DirectChannel` | Không | Channel wiring, transformer, header propagation, output type |
| **UDP integration test** | `DatagramSocket.send` tới inbound adapter | Có, thường loopback | Bind, lắng nghe, UDP mapper, bytes thực nhận, header IP/port |
| **Network/LAN test** | Máy khác, VLAN, firewall, NAT | Có, qua hạ tầng thật | Kết nối/định tuyến và vận hành trong môi trường kiểm tra |

**Giới hạn quan trọng:** channel-only test **không** chứng minh cổng UDP đã được mở; loopback test **không** chứng minh UDP luôn giao hàng hoặc sẽ hoạt động xuyên NAT và firewall trong production.

## 3. Chọn DirectChannel và QueueChannel

Những API cần biết:

| Loại | Cách hoạt động | Vai trò trong test |
|---|---|---|
| `MessageChannel` | `send(Message)` và `send(Message, timeout)` | Đầu vào của flow |
| `SubscribableChannel` | Gửi message đến subscriber đăng ký | Cơ sở của các channel push |
| `DirectChannel` | Dispatch tới handler theo cơ chế đồng bộ | Bắt đầu flow trong test không socket |
| `PollableChannel` | `receive()`, `receive(timeout)` | Cho JUnit chờ kết quả |
| `QueueChannel` | Queue có thể giới hạn capacity | Test sink thu message |
| `PublishSubscribeChannel` | Phân phối tới các subscriber | Khi cần nhiều nhánh quan sát có chủ đích |

Ví dụ tối thiểu:

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

QueueChannel sink = new QueueChannel(8);
sink.send(MessageBuilder.withPayload("ok").build());

Message<?> result = sink.receive(1000);
if (result == null) {
    throw new AssertionError("No message in 1000 ms");
}
System.out.println(result.getPayload()); // ok
~~~

Ý nghĩa của timeout:

- `receive(0)`: lấy ngay nếu có, nếu không trả `null`.
- `receive(1000)`: đợi message tối đa khoảng 1000 ms; khi hết hạn thường trả `null`.
- `receive()`: có thể đợi vô hạn; **không nên dùng trong test có thể treo build**.

`QueueChannel(8)` có sức chứa 8 message; nếu đầy, phương thức send có thể phải chờ. **Đừng dùng queue vô hạn** để che giấu lỗi tạo quá nhiều message. Trong một suite nhiều test, phải drain queue hoặc tạo context/queue riêng để message từ bài trước không rơi sang bài sau.

**Không nhầm các thời hạn:** `QueueChannel.receive(1000)` chờ Spring Message; `DatagramSocket.setSoTimeout(1000)` chờ UDP datagram; `ack-timeout` của UDP sender chờ ACK theo một giao thức riêng nếu đã bật. Chúng không cùng một contract.

## 4. Dependency cho Spring Boot và JUnit 5

Ví dụ dùng Java 17+, Spring Boot quản lý version thư viện và Spring Integration IP:

~~~xml
<!-- Đặt trong phần <dependencies> của pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

`spring-integration-test` bổ sung `@SpringIntegrationTest` và `MockIntegrationContext`. Các ví dụ dùng `QueueChannel`/`@SpringJUnitConfig` có thể hoạt động chỉ với Spring Test và Spring Integration hiện hữu, còn công cụ mock chuyên biệt cần dependency test bổ sung.

## 5. Chuẩn bị decoder để kiểm thử độc lập

DTO của bản tin:

~~~java
public record Telemetry(String sensorId, long sequence) {
}
~~~

Parser xác thực length, UTF-8 và cấu trúc:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class TelemetryDecoder {

    private TelemetryDecoder() {}

    public static Telemetry decode(byte[] bytes) {
        if (bytes == null || bytes.length == 0 || bytes.length > 512) {
            throw new IllegalArgumentException("Expected 1..512 bytes");
        }

        final String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException("Invalid UTF-8", ex);
        }

        String[] fields = text.split(";", -1);
        if (fields.length != 3
                || !fields[0].equals("v=1")
                || !fields[1].startsWith("sensor=")
                || !fields[2].startsWith("seq=")) {
            throw new IllegalArgumentException("Invalid telemetry schema");
        }

        String sensorId = fields[1].substring("sensor=".length());
        String seqText = fields[2].substring("seq=".length());

        if (!sensorId.matches("[A-Za-z0-9_-]{1,32}")
                || !seqText.matches("\\d{1,18}")) {
            throw new IllegalArgumentException("Invalid telemetry value");
        }

        return new Telemetry(sensorId, Long.parseLong(seqText));
    }
}
~~~

Đây là **hợp đồng minh họa**, không phải chuẩn cho mọi thiết bị UDP. Parser nhận bytes, kiểm tra tính hợp lệ nhưng không biết gói đã mất trước socket hay bị cắt khi receiver dùng buffer quá nhỏ.

### 5.1. Unit test decoder

~~~java
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class TelemetryDecoderTest {

    @Test
    void decodesValidTelemetry() {
        byte[] bytes = "v=1;sensor=node-7;seq=42"
                .getBytes(StandardCharsets.UTF_8);
        Telemetry result = TelemetryDecoder.decode(bytes);

        assertEquals("node-7", result.sensorId());
        assertEquals(42L, result.sequence());
    }

    @Test
    void rejectsInvalidUtf8AndLength() {
        byte[] badUtf8 = {(byte) 0xC3, (byte) 0x28};

        assertThrows(IllegalArgumentException.class,
                () -> TelemetryDecoder.decode(badUtf8));
        assertThrows(IllegalArgumentException.class,
                () -> TelemetryDecoder.decode(new byte[513]));
        assertThrows(IllegalArgumentException.class,
                () -> TelemetryDecoder.decode(new byte[0]));
    }

    @Test
    void rejectsUnsupportedVersion() {
        byte[] invalid = "v=2;sensor=node-7;seq=42"
                .getBytes(StandardCharsets.UTF_8);
        assertThrows(IllegalArgumentException.class,
                () -> TelemetryDecoder.decode(invalid));
    }
}
~~~

Test này không cần Spring context; vì vậy nhanh, dễ lập lại và chỉ lỗi khi bộ chuyển đổi hoặc test case sai. Nó **chưa** kiểm tra channel wiring hoặc UDP adapter.

## 6. Channel-only test: DirectChannel -> Transformer -> QueueChannel

Đây là test quan trọng nhất khi người học muốn hiểu **test channel**. Test chủ động tạo `Message<byte[]>` rồi đưa vào một channel đã được cấu hình trong Spring context.

~~~mermaid
flowchart LR
    T["JUnit tạo Message<byte[]>"] --> A["rawUdpInput: DirectChannel"]
    A --> X["TelemetryDecoder"]
    X --> Q["decodedResults: QueueChannel"]
    Q --> V["JUnit assert DTO và headers"]
~~~

Ví dụ Spring Test:

~~~java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.IpHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(classes = UdpChannelTest.Config.class)
class UdpChannelTest {

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean("rawUdpInput")
        public MessageChannel rawUdpInput() {
            return new DirectChannel();
        }

        @Bean("decodedResults")
        public QueueChannel decodedResults() {
            return new QueueChannel(8);
        }

        @Bean
        public IntegrationFlow decodeFlow() {
            return IntegrationFlow.from("rawUdpInput")
                    .<byte[], Telemetry>transform(
                            TelemetryDecoder::decode)
                    .channel("decodedResults")
                    .get();
        }
    }

    @Autowired
    @Qualifier("rawUdpInput")
    MessageChannel input;

    @Autowired
    @Qualifier("decodedResults")
    QueueChannel results;

    @Test
    void convertsMessageAndPreservesSourceHeaders() {
        byte[] bytes = "v=1;sensor=node-7;seq=42"
                .getBytes(StandardCharsets.UTF_8);

        Message<byte[]> rawMessage = MessageBuilder.withPayload(bytes)
                .setHeader(IpHeaders.IP_ADDRESS, "192.0.2.31")
                .setHeader(IpHeaders.PORT, 53021)
                .build();

        assertTrue(input.send(rawMessage));

        Message<?> actual = results.receive(1000);
        assertNotNull(actual, "No DTO received by test channel");
        assertInstanceOf(Telemetry.class, actual.getPayload());

        Telemetry telemetry = (Telemetry) actual.getPayload();
        assertEquals("node-7", telemetry.sensorId());
        assertEquals(42L, telemetry.sequence());

        assertEquals("192.0.2.31",
                actual.getHeaders().get(IpHeaders.IP_ADDRESS));
        assertEquals(53021,
                actual.getHeaders().get(IpHeaders.PORT));

        assertNull(results.receive(0), "Unexpected extra result");
    }
}
~~~

Test này xác minh **Spring context nối đúng flow**, transformer được gọi, `Telemetry` đi vào test sink và header được giữ khi biến đổi payload.

**Nó không xác minh UDP source IP thật**: header `192.0.2.31:53021` được JUnit tự dựng. Để kiểm tra adapter tự ánh xạ header từ `DatagramPacket`, cần integration test qua socket thật như mục tiếp theo.

### 6.1. Test đường lỗi của flow

Đối với flow **đồng bộ** dùng `DirectChannel`, khi decoder ném lỗi, caller có thể nhận một exception từ đường dispatch. Tùy phiên bản Spring Integration, exception có thể được bọc thành `MessagingException`.

~~~java
byte[] invalid = {(byte) 0xC3, (byte) 0x28};

assertThrows(RuntimeException.class,
        () -> input.send(
            MessageBuilder.withPayload(invalid).build()));

assertNull(results.receive(100),
        "Invalid packet must not produce a DTO");
~~~

Đây là **đoạn test bổ sung** cho class ở trên; nếu dùng nhiều test trong cùng context, dọn queue giữa các test. Khi đổi sang `ExecutorChannel` hoặc error channel bất đồng bộ, exception có thể không ném về caller. Khi đó test phải chờ đúng error channel và assert `ErrorMessage` theo cấu hình, không dùng cùng giả định với `DirectChannel`.

### 6.2. Không dùng nhiều consumer tranh một QueueChannel

`QueueChannel` có semantics point-to-point: một message chỉ được một consumer lấy. Nếu test để cả JUnit và service activator cùng nhận từ `decodedResults`, kết quả có thể **không ổn định** vì consumer khác đã lấy message trước.

Muốn vừa chạy handler thật vừa quan sát, dùng **wire tap** hoặc một nhánh pub/sub có chủ đích. Không cho rằng thêm subscriber thứ hai vào `DirectChannel` sẽ tạo bản sao cho cả hai.

## 7. Integration test: gửi datagram thật vào UDP inbound adapter

Để kiểm tra **socket bind, byte array và IP header thực**, khởi tạo UDP inbound adapter trên **port 0**. Sau khi nó listening, lấy port thật và gửi datagram từ `DatagramSocket` trên loopback.

~~~mermaid
flowchart LR
    S["JUnit DatagramSocket<br/>client ephemeral port"] -->|"UDP tới 127.0.0.1"| U["UnicastReceivingChannelAdapter<br/>port=0"]
    U --> Q["udpPackets: QueueChannel"]
    Q --> A["JUnit receive(3000)<br/>assert bytes + source headers"]
~~~

Ví dụ dùng import của **Spring Integration 7.x**. Với **6.x**, `UnicastReceivingChannelAdapter` thuộc package `org.springframework.integration.ip.udp`.

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.ip.IpHeaders;
import org.springframework.integration.ip.udp.inbound.UnicastReceivingChannelAdapter;
import org.springframework.messaging.Message;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(classes = UdpSocketTest.Config.class)
class UdpSocketTest {

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean("udpPackets")
        public QueueChannel udpPackets() {
            return new QueueChannel(16);
        }

        @Bean("udpReceiver")
        public UnicastReceivingChannelAdapter receiver(
                @Qualifier("udpPackets") QueueChannel packets) {
            UnicastReceivingChannelAdapter adapter =
                    new UnicastReceivingChannelAdapter(0);
            adapter.setOutputChannel(packets);
            adapter.setReceiveBufferSize(2048);
            adapter.setLengthCheck(false);
            return adapter;
        }
    }

    @Autowired
    @Qualifier("udpPackets")
    QueueChannel captured;

    @Autowired
    @Qualifier("udpReceiver")
    UnicastReceivingChannelAdapter receiver;

    @Test
    void receivesRealUdpDatagram() throws Exception {
        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(5);

        while (!receiver.isListening()
                && System.nanoTime() < deadline) {
            Thread.sleep(20);
        }

        assertTrue(receiver.isListening(), "Listener not ready");
        int port = receiver.getPort();
        assertTrue(port > 0);

        byte[] bytes = "v=1;sensor=node-7;seq=42"
                .getBytes(StandardCharsets.UTF_8);

        int sourcePort;
        try (DatagramSocket client = new DatagramSocket(
                0, InetAddress.getByName("127.0.0.1"))) {

            sourcePort = client.getLocalPort();
            DatagramPacket packet = new DatagramPacket(
                    bytes, bytes.length,
                    InetAddress.getByName("127.0.0.1"), port);
            client.send(packet);
        }

        Message<?> message = captured.receive(3000);
        assertNotNull(message, "No Message from UDP adapter");
        assertInstanceOf(byte[].class, message.getPayload());
        assertArrayEquals(bytes, (byte[]) message.getPayload());

        assertEquals("127.0.0.1",
                message.getHeaders().get(IpHeaders.IP_ADDRESS));

        Integer ipPort = message.getHeaders()
                .get(IpHeaders.PORT, Integer.class);
        assertNotNull(ipPort);
        assertEquals(sourcePort, ipPort.intValue());

        assertNotNull(message.getHeaders()
                .get(IpHeaders.PACKET_ADDRESS));
        assertNull(captured.receive(0));
    }
}
~~~

Trong test này, `ip_port` được **so sánh với port nguồn của client thật**, không phải port của listener. Chính UDP adapter đã tạo thông tin header nguồn. Test còn kiểm tra byte array của một datagram nhận được giống byte array gửi đi.

### 7.1. Vì sao chọn port 0?

Nếu hard-code cổng `12017`, một test khác hoặc process đang chạy có thể đã chiếm cổng đó. Với UDP inbound unicast, truyền `0` khi khởi tạo adapter cho phép OS cấp một cổng trống.

**Chỉ lấy `getPort()` sau khi adapter đã `isListening()==true`** hoặc sau `UdpServerListeningEvent`. Tránh “tìm cổng rảnh” bằng cách mở một socket tạm, đóng nó rồi bind lại; trong khoảng giữa hai thao tác, process khác có thể chiếm cổng.

### 7.2. Chờ readiness đúng cách

Vòng chờ tối đa 5 giây trong test giúp giảm race condition giữa Spring context startup và thời điểm test gửi packet. Một lựa chọn khác là đăng ký listener cho `UdpServerListeningEvent`, dùng `CountDownLatch` chờ event và lấy port từ `event.getPort()`.

Nếu context có nhiều UDP inbound adapter, hãy xác minh event thuộc **đúng adapter** trước khi dùng port. Không dùng `Thread.sleep(3000)` cố định như bằng chứng listener đã sẵn sàng; thời gian startup có thể thay đổi giữa các runner.

### 7.3. Vì sao test chưa chứng minh UDP luôn đáng tin?

Mặc dù test trên loopback thường chạy ổn định, UDP vẫn **không bảo đảm** datagram đến đích, đúng thứ tự hay không trùng. Test này chỉ cho biết **một datagram cụ thể** đã đi qua adapter và đến test sink trong điều kiện kiểm thử.

Đối với kiểm thử mất gói, hãy bổ sung sequence, metric tại sender/receiver và môi trường mô phỏng network loss. Không kết luận mọi packet trên LAN/cloud sẽ đến chỉ vì loopback test pass.

## 8. Test outbound UDP với một collector giả trên loopback

Một UDP receiver nhỏ do JUnit sở hữu có thể kiểm tra chiều ngược: `Message<byte[]>` đi qua outbound adapter và được gửi thành **UDP datagram**.

~~~mermaid
flowchart LR
    J["JUnit Message<byte[]>"] --> D["toUdp: DirectChannel"]
    D --> O["Udp.outboundAdapter"]
    O -->|"UDP datagram"| C["DatagramSocket collector giả"]
    C --> A["JUnit assert byte[]"]
~~~

Cấu hình một socket nhận trên port 0 rồi dùng port đó làm đích outbound:

~~~java
import java.net.DatagramSocket;
import java.net.InetAddress;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.dsl.Udp;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class UdpOutboundTestConfig {

    @Bean("toUdp")
    public MessageChannel toUdp() {
        return new DirectChannel();
    }

    @Bean(destroyMethod = "close")
    public DatagramSocket testCollectorSocket() throws Exception {
        return new DatagramSocket(
                0, InetAddress.getByName("127.0.0.1"));
    }

    @Bean
    public IntegrationFlow outboundFlow(DatagramSocket testCollectorSocket) {
        return IntegrationFlow.from("toUdp")
                .handle(Udp.outboundAdapter(
                        "127.0.0.1",
                        testCollectorSocket.getLocalPort()))
                .get();
    }
}
~~~

JUnit test:

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(classes = UdpOutboundTestConfig.class)
class UdpOutboundTest {

    @Autowired
    @Qualifier("toUdp")
    MessageChannel toUdp;

    @Autowired
    DatagramSocket testCollectorSocket;

    @Test
    void sendsBytesToUdpCollector() throws Exception {
        byte[] sent = "v=1;sensor=node-7;seq=42"
                .getBytes(StandardCharsets.UTF_8);

        testCollectorSocket.setSoTimeout(3000);

        assertTrue(toUdp.send(
                MessageBuilder.withPayload(sent).build()));

        byte[] buf = new byte[2048];
        DatagramPacket packet = new DatagramPacket(buf, buf.length);
        testCollectorSocket.receive(packet);

        byte[] received = Arrays.copyOf(
                packet.getData(), packet.getLength());
        assertArrayEquals(sent, received);
    }
}
~~~

`setSoTimeout(3000)` ở đây là **timeout của socket UDP test collector**, không phải timeout của `QueueChannel`. Hai loại timeout cần được tách riêng khi đọc báo cáo test.

Ưu điểm: không cần máy collector thật và không hard-code port. Hạn chế: mới xác minh rằng **gói đã tới socket test**, chưa chứng minh receiver ngoài ứng dụng đã xử lý nghiệp vụ hoặc ghi bền vào database.

## 9. Wire tap: thu message nhưng vẫn chạy business flow

Nếu mục tiêu là quan sát message **trước hoặc sau transformer** mà không thay thế handler cuối, có thể dùng `wireTap` để tạo một nhánh chỉ dành cho test.

Ví dụ vị trí tap trước transformer:

~~~java
@Bean("rawAudit")
public QueueChannel rawAudit() {
    return new QueueChannel(16);
}

@Bean
public IntegrationFlow businessFlow() {
    return IntegrationFlow.from("rawUdpInput")
            .wireTap("rawAudit")
            .<byte[], Telemetry>transform(TelemetryDecoder::decode)
            .handle(telemetryService, "store")
            .get();
}
~~~

**Đây là đoạn minh họa**, giả định `telemetryService` là bean đã được inject và có method `store(Telemetry)`. Bài test có thể lấy `rawAudit.receive(1000)` và assert `byte[]` ban đầu. Muốn assert DTO, di chuyển tap **sau** transformer và đặt tên kênh phù hợp.

Lưu ý:

- Tap quan sát một điểm trong flow, không tự xác nhận database đã commit.
- Queue test phải có capacity hữu hạn và được drain sau test.
- Nếu main flow kết thúc bằng một handler không trả reply, hãy đặt tap **trước handler**.
- Không dùng hai consumer tranh nhau cùng `QueueChannel` nếu muốn JUnit luôn nhận được message.
- `DirectChannel` có nhiều subscriber không đồng nghĩa broadcast message tới mọi subscriber; cần wire tap hoặc channel pub/sub có chủ đích.

## 10. @SpringIntegrationTest và MockIntegrationContext

Module `spring-integration-test` có các công cụ kiểm thử context:

| Công cụ | Vai trò |
|---|---|
| `@SpringIntegrationTest` | Bật tiện ích Spring Integration Test Framework |
| `noAutoStartup` | Ngăn endpoint được chỉ định tự start, hữu ích khi không muốn mở network |
| `MockIntegrationContext` | Thay thế có kiểm soát một số `MessageSource`/`MessageHandler` trong context |
| `MockIntegration.mockMessageSource(...)` | Cấp message giả cho flow |
| `MockIntegration.mockMessageHandler(...)` | Ghi nhận và mô phỏng xử lý message |
| `resetBeans()` | Khôi phục endpoint sau khi đã mock, tránh ảnh hưởng test khác |

Ví dụ cố ý không cho UDP endpoint khởi động:

~~~java
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = UdpSocketTest.Config.class)
@SpringIntegrationTest(noAutoStartup = "udpReceiver")
class UdpWithoutNetworkTest {
    // Inject udpReceiver và kiểm tra lifecycle không tự start.
    // Muốn test logic sau inbound, gửi Message<byte[]>
    // trực tiếp vào channel kế tiếp thay vì mở socket.
}
~~~

Đối với **test socket thật ở mục 7**, không dùng `noAutoStartup` cho receiver đang cần kiểm tra. `MockIntegrationContext.substituteMessageHandlerFor(...)` nhắm vào endpoint tiêu thụ message có bean name phù hợp; không dùng bừa để thay socket và vẫn tuyên bố đã test UDP network. Khi dùng mock, cần `resetBeans()` trong `@AfterEach`.

Kết hợp theo mục tiêu:

- Kiểm tra parser: **unit test thuần**.
- Kiểm tra channel/transformer: **QueueChannel test sink**.
- Kiểm tra mapping UDP: **DatagramSocket thật**.
- Kiểm tra service bên ngoài có timeout hoặc side effects: **mock handler hoặc test container chuyên dụng**, không để phụ thuộc mạng production.

## 11. Test lỗi và test không có message

Các tình huống nên bao phủ:

| Input hoặc sự kiện | Kỳ vọng |
|---|---|
| Payload hợp lệ | Một DTO có field chính xác |
| Byte UTF-8 sai `C3 28` | Decoder báo lỗi, không tạo DTO |
| Version `v=2` | Schema bị từ chối |
| `sensor=` rỗng | ID không hợp lệ, từ chối |
| Sequence không phải số | Bị từ chối |
| Payload 513 byte | Vượt giới hạn 512, từ chối |
| Không gửi vào QueueChannel | `receive(timeout)` trả `null` |
| Adapter chưa listening | Test fail readiness có message rõ ràng |
| Gửi packet raw nhưng receiver bật length check | Có thể lỗi framing; hai phía phải tương thích |
| Gửi nhiều packet | Cần kiểm tra bằng sequence/count và hiểu giới hạn UDP |

Đặc biệt:

~~~java
assertNull(results.receive(100));
~~~

Assertion chỉ nói rằng **queue trống trong tối đa 100 ms**. Nó **không chứng minh datagram đã mất**. Message có thể chưa tới, đang được parse, bị reject hoặc đi nhầm channel.

Khi cần xác minh lỗi, nên assert **đúng điểm phát sinh lỗi**: decoder exception, error channel theo cấu hình, metric invalid hoặc log có kiểm soát. Packet bị mất trước socket **không thể tự sinh `ErrorMessage`** trong Spring Integration.

### 11.1. Test sequence, reorder và duplicate

UDP không đảm bảo thứ tự hoặc exactly-once. Nếu phải kiểm tra bộ xử lý sequence, **đưa message trực tiếp vào test channel** theo các thứ tự chủ động tạo:

~~~text
1, 2, 3       -> bình thường
1, 3, 2       -> gap quan sát rồi message đến muộn
1, 2, 2       -> khả năng duplicate
boot-42:100,
boot-43:1     -> epoch mới, không nối hai dải sequence
~~~

Nếu chạy bài test này qua socket, loopback có thể giao đúng thứ tự trong nhiều lần thử nhưng đó **không phải cam kết của UDP**. Với độ tin cậy nghiệp vụ, cần ID/epoch/sequence, ACK, retry và idempotency hoặc dùng broker/transport thích hợp.

## 12. Giảm flaky test trong CI

| Nguy cơ | Biện pháp |
|---|---|
| Cổng cố định đã bị chiếm | Dùng port 0 cho inbound test |
| Gửi trước khi socket ready | Chờ `isListening()` hoặc listening event |
| Test treo vô hạn | Timeout hữu hạn cho queue, socket và startup |
| Message tồn từ test trước | Drain queue hoặc dùng context/test sink riêng |
| Nhiều subscriber cạnh tranh | Chỉ một consumer cho test sink hoặc dùng wire tap |
| Delay môi trường thay đổi | Chờ điều kiện thay vì sleep mù |
| Cấu hình IPv4/IPv6 không khớp | Dùng `127.0.0.1` nhất quán hoặc kiểm tra interface |
| Không đóng socket | Try-with-resources, bean destroy, Spring lifecycle |
| CI trong container | Loopback thuộc network namespace của container; test cùng process |
| LAN/multicast/broadcast không hỗ trợ | Tách network tests ra khỏi unit/channel suite |

**Không retry một test flaky vô hạn để che lỗi.** Khi test fail, log tên endpoint, cổng thật, trạng thái listener, source address, số bytes, thời gian chờ và loại exception. Đừng ghi payload chứa dữ liệu nhạy cảm hoặc tạo metric có nhãn IP:port động không kiểm soát.

Ở môi trường CI có chính sách chặn bind UDP, các **unit test và channel-only test** vẫn có thể chạy. Chỉ mở socket khi runner hỗ trợ. Thử multicast, broadcast, NAT/VLAN nên thực hiện trong lab có topology phù hợp thay vì mặc định trên mọi runner.

## 13. Quan sát và diễn giải kết quả test

Một sơ đồ chẩn đoán:

~~~mermaid
flowchart TD
    A["JUnit tạo bytes"] --> B{"Send/dispatch thành công?"}
    B -->|Không| E1["Lỗi local/channel"]
    B -->|Có| C{"Listener đã listening?"}
    C -->|Không| E2["Lỗi lifecycle/bind"]
    C -->|Có| D{"QueueChannel nhận Message?"}
    D -->|Không| E3["Socket/mapper/routing/timeout"]
    D -->|Có| F{"Payload + headers đúng?"}
    F -->|Không| E4["Framing/decoder/schema"]
    F -->|Có| G["Assertion PASS"]
~~~

Một test pass ở `QueueChannel` không tự chứng minh transaction ở DB đã commit, đặc biệt nếu flow dùng executor hoặc broker bất đồng bộ. Nếu mục tiêu là xác nhận **hiệu ứng nghiệp vụ**, cần assert tại database, mock side-effect được gọi hoặc ACK nghiệp vụ đúng hợp đồng.

Trong Spring Integration, `MessageChannel.send()==true` chỉ nói lên kết quả dispatch theo contract của channel; nếu tiếp theo là UDP outbound, sender **vẫn chưa biết receiver có nhận packet không**.

## 14. Bài thực hành tổng hợp

Thiết kế suite cho luồng:

~~~text
UDP inbound -> Message<byte[]> -> TelemetryDecoder
            -> Message<Telemetry> -> Business service
~~~

Bài làm:

1. Tạo `TelemetryDecoder` và test các trường hợp hợp lệ, sai version, malformed UTF-8, quá kích thước.
2. Viết channel-only test với `DirectChannel` đầu vào và `QueueChannel` làm sink, assert DTO và headers giả lập.
3. Kiểm tra một packet lỗi không tạo DTO; phân biệt đường exception đồng bộ và error channel bất đồng bộ.
4. Tạo test UDP inbound thật bằng port 0, chờ listening rồi gửi `DatagramSocket` trên loopback.
5. Assert chính xác byte array, `ip_address`, `ip_port` và `ip_packetAddress` từ datagram thật.
6. Tạo outbound flow gửi tới một `DatagramSocket` test collector đang bind port 0; so sánh byte nhận.
7. Thêm wire tap trước và sau transformer, giải thích kiểu payload ở mỗi tap.
8. Chạy test theo nhóm song song, phát hiện các vấn đề queue còn message, port collision và lifecycle.
9. Tách bài kiểm tra broadcast/multicast trong LAN khỏi unit suite; xác định công cụ packet capture khi cần.
10. Nếu lưu telemetry vào database, viết một test riêng xác nhận commit/idempotency, không dựa hoàn toàn vào test sink.

**Câu hỏi tự đánh giá:**

- Vì sao `QueueChannel` phù hợp để làm test sink hơn `DirectChannel`?
- `receive(0)` khác `receive(3000)` ra sao?
- Unit test decoder có xác nhận UDP socket đã bind chưa?
- Vì sao port 0 giảm nguy cơ xung đột test?
- Vì sao cần đợi `isListening()` hoặc `UdpServerListeningEvent`?
- Header nguồn do test tự tạo khác gì header từ datagram thật?
- Vì sao hai consumer trên cùng `QueueChannel` làm test không ổn định?
- Mock handler có thể thay cho kiểm thử UDP network không?
- Vì sao `assertNull(queue.receive(100))` không chứng minh packet loss?
- Test channel có chứng minh được transaction ở DB đã commit chưa?

## 15. Tài liệu tham khảo

- [Spring Integration Reference — Testing support](https://docs.spring.io/spring-integration/reference/testing.html): `@SpringIntegrationTest`, `MockIntegrationContext` và mocking.
- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): cấu hình inbound/outbound, cổng 0, `isListening()`, event và length check.
- [Spring Integration Reference — MessageChannel Interfaces](https://docs.spring.io/spring-integration/reference/channel/interfaces.html): `MessageChannel`, `PollableChannel`, `SubscribableChannel`.
- [Spring Integration Reference — MessageChannel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html): `QueueChannel`, `DirectChannel`, timeout và capacity.
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html): queue channel hữu hạn và cấu hình.
- [Oracle Java DatagramSocket API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/DatagramSocket.html): bind, receive, send và `setSoTimeout`.

## Kết luận

**Kiểm thử UDP bằng test channel** cho phép JUnit thu một Spring Integration `Message` tại điểm xác định trong flow, thường bằng `QueueChannel.receive(timeout)`, rồi kiểm tra payload, header và kết quả chuyển đổi. Cách làm này tách phần nghiệp vụ khỏi socket, giúp test nhanh và có lỗi rõ ràng.

Nhưng **test channel không thay thế UDP integration test**. Hãy kết hợp unit test decoder, channel-only test và loopback test với port 0, readiness, timeout hữu hạn, dọn tài nguyên và tách test LAN riêng. Với dữ liệu quan trọng, tiếp tục kiểm tra ACK nghiệp vụ, lưu bền và idempotency. Phương pháp phân tầng ấy cũng áp dụng cho những adapter khác của **SPRING_INTEGRATION_ADAPTERS**, giúp mỗi test chứng minh đúng điều nó cần chứng minh mà không suy diễn UDP có đảm bảo giao hàng.
