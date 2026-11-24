# Chuyển đổi byte array sang payload trong Spring Integration UDP

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **dữ liệu trong UDP datagram**, `Message<byte[]>`, payload văn bản và đối tượng nghiệp vụ.
- Giải mã `byte[]` thành UTF-8 **nghiêm ngặt**, kiểm tra độ dài tính theo byte, version và cấu trúc message.
- Ghép `UnicastReceivingChannelAdapter`, `MessageChannel`, `@Transformer` và `@ServiceActivator` để đưa dữ liệu UDP vào ứng dụng.
- Chuyển payload UTF-8, JSON hoặc binary thành DTO tương ứng; mã hóa DTO thành `byte[]` khi gửi ngược ra UDP.
- Giữ các header nguồn, phân loại lỗi chuyển đổi và kiểm thử bằng UDP client thật.
- Giải thích ảnh hưởng của kích thước datagram, framing, buffer, hiệu năng, bảo mật và vòng đời endpoint đến quá trình chuyển đổi.

Bài thuộc chương **Adapter UDP** trong module **SPRING_INTEGRATION_ADAPTERS**. Module dạy cách kết nối hệ thống ngoài vào Spring Integration bằng inbound/outbound adapter, gateway, poller và `MessageChannel`, đồng thời xử lý hợp đồng message, lỗi và vòng đời kết nối khi tích hợp file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Tại ranh giới UDP, **bytes phải được hiểu và xác thực theo một hợp đồng rõ ràng** trước khi trở thành dữ liệu nghiệp vụ.

## 1. Tại sao phải chuyển byte array?

Giả sử một cảm biến gửi datagram có nội dung UTF-8:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

UDP chỉ vận chuyển **bytes**, không tự khai báo đây là UTF-8, JSON hay một đối tượng Java. Khi nhận gói, Spring Integration UDP inbound adapter thường phát `Message<byte[]>` vào output channel, tức **payload hiện tại chính là mảng byte thô**.

~~~mermaid
flowchart LR
    A["Sensor / hệ thống ngoài"] -->|"UDP datagram"| B["UDP inbound adapter"]
    B -->|"Message<byte[]>"| C["Kiểm tra kích thước và charset"]
    C -->|"Message<String>"| D["Parse + schema validation"]
    D -->|"Message<TelemetryEvent>"| E["Service Activator"]
    E --> F["DB / Kafka / HTTP / hệ thống khác"]
~~~

Cụm từ *chuyển byte array sang payload* ở đây là biến **payload `byte[]` ban đầu** thành **payload có kiểu và ý nghĩa** như `String`, `TelemetryEvent`, `JsonNode` hoặc một kiểu dữ liệu nhị phân. Adapter phụ trách nhận gói; transformer phụ trách hiểu bytes; service nghiệp vụ xử lý đối tượng đã được kiểm tra.

Một datagram nhận thành công **chưa chắc** chứa chuỗi hợp lệ; một chuỗi hợp lệ **chưa chắc** có schema đúng; một DTO đúng schema **chưa chắc** đã được lưu thành công.

## 2. Ba lớp của message cần phân biệt

| Lớp | Dữ liệu minh họa | Nguồn và ý nghĩa |
|---|---|---|
| UDP payload trên mạng | Byte UTF-8 của `v=1;sensor=...` | Sender serialize theo hợp đồng |
| Spring `Message<byte[]>` | `byte[]` và các message headers | Inbound adapter tạo message từ datagram |
| Spring `Message<TelemetryEvent>` | Sensor ID, sequence và nhiệt độ đã parse | Transformer tạo dữ liệu cho tầng nghiệp vụ |

Ví dụ cùng một datagram qua hai bước:

~~~text
Inbound message:
  payload = byte[] [118, 61, 49, 59, ...]
  headers = {ip_address="192.0.2.31", ip_port=53021, ...}

Sau transformer:
  payload = TelemetryEvent("node-7", 1042, 26.5)
  headers = {ip_address="192.0.2.31", ip_port=53021, ...}
~~~

Các header này là metadata **nội bộ** của Spring Messaging. `ip_address`, `ip_port` hoặc `id` không tự nằm trong bytes của datagram và cũng không tự được truyền đi khi gửi bằng UDP outbound adapter. Nếu hệ thống đích cần một trường, bạn phải đưa trường đó vào payload theo giao thức đã thống nhất.

## 3. Xác định hợp đồng payload trước khi decode

| Mục | Quy ước cho ví dụ | Lý do |
|---|---|---|
| Charset | UTF-8 | Tránh phụ thuộc charset mặc định của môi trường |
| Version | `v=1` | Parser nhận biết định dạng được hỗ trợ |
| Format | `v=...;sensor=...;seq=...;tempC=...` | Thống nhất dấu phân cách, thứ tự và tên trường |
| Size | 1–512 byte | Tránh payload quá lớn, kiểm soát chi phí xử lý |
| Sensor ID | ASCII 1–32 ký tự | Tránh ID rỗng và dữ liệu không thuộc hợp đồng |
| Sequence | Số nguyên không âm | Hỗ trợ chống trùng, kiểm tra thứ tự |
| Temperature | Decimal theo °C | Có đơn vị, quy tắc parse và miền giá trị |
| Framing UDP | Raw, không có length prefix | Thống nhất `lengthCheck(false)` ở ví dụ |
| Gói không hợp lệ | Reject + metric/log lấy mẫu | Không sinh bản ghi nghiệp vụ từ dữ liệu sai |
| Bảo mật | Xác thực thiết bị nếu cần | Source IP không thay thế danh tính đáng tin cậy |

UDP không có schema, charset hoặc cơ chế đảm bảo giao hàng. **Hợp đồng payload do hai ứng dụng thỏa thuận.** Với JSON, protobuf hay CBOR, hãy viết contract cụ thể cho format đó và quản lý version.

## 4. Đếm byte trước khi biến thành String

Giới hạn datagram là giới hạn **số byte**, không phải số ký tự:

~~~java
import java.nio.charset.StandardCharsets;

String text = "nhiệt độ 😀";

int javaUnits = text.length();
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;
~~~

`String.length()` đếm các đơn vị UTF-16; `byte[].length` đếm bytes. Ký tự có dấu hoặc emoji có thể dùng nhiều byte UTF-8, nên `javaUnits` và `utf8Bytes` thường khác nhau.

Tại inbound:

~~~java
byte[] bytes = message.getPayload();
if (bytes.length == 0 || bytes.length > 512) {
    throw new IllegalArgumentException("UDP payload outside 1..512 bytes");
}
~~~

Tại outbound, hãy serialize trước rồi mới kiểm tra `bytes.length`.

## 5. Giải mã UTF-8: cách nhanh và cách nghiêm ngặt

### 5.1. Chuyển chuỗi thông thường

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

Chỉ định `StandardCharsets.UTF_8` giúp code nhất quán. Tuy nhiên, constructor `String` có thể thay sequence UTF-8 không hợp lệ bằng ký tự thay thế, khiến bytes lỗi vẫn tạo được chuỗi.

Ví dụ bytes `C3 28` không phải một sequence UTF-8 hợp lệ. Nếu muốn **từ chối** gói lỗi, không nên âm thầm thay byte.

### 5.2. Giải mã ở chế độ REPORT

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class StrictUtf8 {
    private StrictUtf8() {}

    public static String decode(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }
}
~~~

`CharsetDecoder` với `CodingErrorAction.REPORT` tạo kết quả với bytes UTF-8 hợp lệ và báo `CharacterCodingException` khi encoding không hợp lệ. Tạo decoder cho từng lần decode là lựa chọn đơn giản về trạng thái; không nên chia sẻ cùng một `CharsetDecoder` stateful giữa nhiều thread mà không quản lý đồng bộ.

Nếu payload là protobuf hoặc giao thức binary thì **không giải mã thành chuỗi**. Khi đó chọn parser bytes và thứ tự byte được quy định bởi protocol.

## 6. Cấu hình inbound UDP và ba MessageChannel

Ví dụ dùng Spring Boot, Spring Integration IP và Java 17+ để khai báo DTO bằng `record`. Khi Spring Boot đã quản lý dependency version, khai báo:

~~~xml
<!-- Trong phần dependencies của pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

Khởi tạo một UDP inbound adapter và ba kênh nội bộ:

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
public class UdpDecodeConfig {

    @Bean("udpRawBytes")
    public MessageChannel udpRawBytes() {
        return new DirectChannel();
    }

    @Bean("udpDecodedText")
    public MessageChannel udpDecodedText() {
        return new DirectChannel();
    }

    @Bean("udpTelemetryEvents")
    public MessageChannel udpTelemetryEvents() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow udpInboundFlow() {
        return IntegrationFlow.from(
                    Udp.inboundAdapter(12017)
                        .receiveBufferSize(2048)
                        .lengthCheck(false))
                .channel("udpRawBytes")
                .get();
    }
}
~~~

Diễn giải:

1. `Udp.inboundAdapter(12017)` lắng nghe datagram UDP unicast trên port 12017.
2. `receiveBufferSize(2048)` dành chỗ cho dữ liệu của **một datagram**, khác với giới hạn nghiệp vụ 512 byte. Gói lớn hơn buffer có thể bị cắt ngắn.
3. `lengthCheck(false)` yêu cầu giao thức **raw UDP**, phù hợp với client PowerShell gửi UTF-8 thuần. Nếu muốn length prefix của Spring Integration, phải bật tương thích cả sender và receiver.
4. `udpRawBytes` chứa bytes, `udpDecodedText` chứa chuỗi đã decode, `udpTelemetryEvents` chứa DTO.
5. Với `DirectChannel`, dispatch là đồng bộ; xử lý downstream lâu có thể ảnh hưởng hiệu năng nhận gói.

UDP inbound là endpoint nhận theo sự kiện socket, **không cần poller** để đọc datagram. Poller có thể tồn tại ở bước khác, ví dụ lấy file hoặc database trước khi đẩy message ra UDP outbound.

## 7. Tạo DTO và transformer cho hợp đồng telemetry

### 7.1. Đối tượng nghiệp vụ

Java 17+:

~~~java
import java.math.BigDecimal;

public record TelemetryEvent(
        String sensorId,
        long sequence,
        BigDecimal temperatureC) {
}
~~~

DTO tách dữ liệu nghiệp vụ khỏi dạng bytes, giúp bước lưu DB hoặc gửi Kafka xử lý kiểu rõ ràng.

### 7.2. Hai bước @Transformer

~~~java
import java.math.BigDecimal;
import java.nio.charset.CharacterCodingException;
import org.springframework.integration.annotation.Transformer;
import org.springframework.stereotype.Component;

@Component
public class UdpPayloadTransformers {

    @Transformer(
            inputChannel = "udpRawBytes",
            outputChannel = "udpDecodedText")
    public String decodeUtf8(byte[] bytes) {
        if (bytes.length == 0 || bytes.length > 512) {
            throw new IllegalArgumentException(
                    "UDP payload outside 1..512 bytes");
        }

        try {
            return StrictUtf8.decode(bytes);
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException(
                    "Invalid UTF-8 datagram", ex);
        }
    }

    @Transformer(
            inputChannel = "udpDecodedText",
            outputChannel = "udpTelemetryEvents")
    public TelemetryEvent parse(String text) {
        String[] fields = text.split(";", -1);

        if (fields.length != 4
                || !fields[0].equals("v=1")
                || !fields[1].startsWith("sensor=")
                || !fields[2].startsWith("seq=")
                || !fields[3].startsWith("tempC=")) {
            throw new IllegalArgumentException(
                    "Invalid telemetry structure");
        }

        String sensorId =
                fields[1].substring("sensor=".length());
        String sequenceText =
                fields[2].substring("seq=".length());
        String temperatureText =
                fields[3].substring("tempC=".length());

        if (!sensorId.matches("[A-Za-z0-9_-]{1,32}")
                || !sequenceText.matches("\\d{1,18}")
                || !temperatureText.matches(
                    "-?\\d{1,3}(\\.\\d{1,2})?")) {
            throw new IllegalArgumentException(
                    "Invalid telemetry value");
        }

        long sequence = Long.parseLong(sequenceText);
        BigDecimal temperature =
                new BigDecimal(temperatureText);

        if (temperature.compareTo(new BigDecimal("-50")) < 0
                || temperature.compareTo(new BigDecimal("150")) > 0) {
            throw new IllegalArgumentException(
                    "Temperature outside accepted range");
        }

        return new TelemetryEvent(
                sensorId, sequence, temperature);
    }
}
~~~

Bước một **kiểm tra kích thước + UTF-8**; bước hai **kiểm tra schema + parse**. Parser cố ý yêu cầu chính xác bốn trường theo thứ tự, `v=1`, sensor ID hợp lệ và nhiệt độ trong `[-50, 150]` độ C. Đây là **hợp đồng minh họa**, không phải chuẩn chung cho mọi thiết bị.

Spring Integration `@Transformer` nhận payload và tạo message mới với payload đã biến đổi; cơ chế transformer thường **bảo toàn những header thích hợp** từ message đầu vào. Nếu tự xây `Message` mới hoặc dùng endpoint đặc biệt, cần kiểm tra lại header sau mỗi bước.

### 7.3. Service Activator làm việc với DTO

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.ip.IpHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class TelemetryEventHandler {

    private static final Logger log =
            LoggerFactory.getLogger(TelemetryEventHandler.class);

    @ServiceActivator(inputChannel = "udpTelemetryEvents")
    public void handle(Message<TelemetryEvent> message) {
        TelemetryEvent telemetry = message.getPayload();

        String sourceIp = message.getHeaders()
                .get(IpHeaders.IP_ADDRESS, String.class);
        Integer sourcePort = message.getHeaders()
                .get(IpHeaders.PORT, Integer.class);

        log.info("Sensor={}, seq={}, UDP source={}:{}",
                telemetry.sensorId(),
                telemetry.sequence(), sourceIp, sourcePort);

        // Phần tiếp theo: kiểm tra trùng, ghi DB, gửi broker...
    }
}
~~~

Handler không cần biết format UDP thô; nó nhận `TelemetryEvent` đã qua bước parse. Log này chỉ để minh họa. Khi production, tránh ghi dữ liệu nhạy cảm hoặc log cho mọi datagram ở tải cao.

## 8. Phương án Java DSL cho bước byte[] → String

Nếu muốn cấu hình transformer ngay trong một flow, có thể dùng Java DSL như sau:

~~~java
import java.nio.charset.CharacterCodingException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.dsl.Udp;

@Configuration
public class UdpInlineDecodeFlow {

    @Bean
    public IntegrationFlow udpInlineFlow() {
        return IntegrationFlow.from(
                    Udp.inboundAdapter(12017)
                        .receiveBufferSize(2048))
                .<byte[], String>transform(bytes -> {
                    if (bytes.length == 0 || bytes.length > 512) {
                        throw new IllegalArgumentException("Invalid size");
                    }
                    try {
                        return StrictUtf8.decode(bytes);
                    } catch (CharacterCodingException ex) {
                        throw new IllegalArgumentException(
                                "Invalid UTF-8", ex);
                    }
                })
                .channel("udpDecodedText")
                .get();
    }
}
~~~

**Đây là phương án thay thế** phần inbound + transformer đầu tiên của mục 6–7. Không đăng ký đồng thời hai listener trên cùng cổng `12017`, và không đăng ký hai transformer cạnh tranh trên `udpRawBytes` nếu bạn muốn mỗi message được xử lý một lần. Các endpoint/transformer tiếp theo có thể được tái sử dụng ở channel `udpDecodedText`.

## 9. Bảo toàn header nguồn khi chuyển payload

UDP inbound adapter có thể đặt các header như:

| Hằng số Java | Tên header | Ý nghĩa |
|---|---|---|
| `IpHeaders.IP_ADDRESS` | `ip_address` | IP nguồn receiver quan sát |
| `IpHeaders.PORT` | `ip_port` | Port nguồn UDP, không phải port listener |
| `IpHeaders.HOSTNAME` | `ip_hostname` | Hostname hoặc IP theo cấu hình reverse lookup |
| `IpHeaders.PACKET_ADDRESS` | `ip_packetAddress` | `SocketAddress` nguồn đầy đủ |

Các giá trị này hỗ trợ chẩn đoán và định tuyến phản hồi. **Không dùng source IP như bằng chứng danh tính thiết bị**, vì NAT, DHCP và giả mạo IP có thể làm địa chỉ thay đổi hoặc không đáng tin.

Nếu tự tạo `Message` mới, có thể giữ header một cách tường minh:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<String> copySourceHeaders(
        Message<byte[]> incoming) throws Exception {
    String decoded = StrictUtf8.decode(incoming.getPayload());

    return MessageBuilder.withPayload(decoded)
            .copyHeaders(incoming.getHeaders())
            .build();
}
~~~

Trước khi copy, cần kiểm tra độ dài/schema như các ví dụ ở trên. Tùy pipeline, một số header có thể không nên truyền ra hệ thống khác: ví dụ `ip_packetAddress` là object Java nội bộ, không phải field tự nhiên của sự kiện Kafka/JMS/HTTP. Khi cần phản hồi UDP, phải giữ metadata đích cần thiết tới outbound handler; khi phát sự kiện ra broker, nên chuyển thành các field nghiệp vụ được phép.

## 10. JSON: từ bytes sang một DTO có cấu trúc

Payload UDP có thể là JSON:

~~~json
{"v":1,"sensorId":"node-7","sequence":1042,"temperatureC":26.5}
~~~

Quy trình nên là:

~~~mermaid
flowchart LR
    A["Message<byte[]>"] --> B["Size guard"]
    B --> C["Strict UTF-8 decode"]
    C --> D["JSON parser"]
    D --> E["Version + schema validation"]
    E --> F["Message<TelemetryEvent>"]
~~~

Với Jackson 2, khi dự án có dependency tương thích, tạo một DTO **giao thức** có cả trường `v` (Java 17+) để validate version trước khi chuyển thành DTO nghiệp vụ:

~~~java
import java.math.BigDecimal;

public record TelemetryJson(
        int v,
        String sensorId,
        long sequence,
        BigDecimal temperatureC) {
}
~~~

Sau đó parse và kiểm tra dữ liệu:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper()
        .configure(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, true)
        .configure(
            DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES,
            true);

String json = StrictUtf8.decode(bytes);
TelemetryJson wire = mapper.readValue(json, TelemetryJson.class);
if (wire.v() != 1
        || wire.sensorId() == null
        || !wire.sensorId().matches("[A-Za-z0-9_-]{1,32}")
        || wire.sequence() < 0
        || wire.temperatureC() == null
        || wire.temperatureC().compareTo(
                new java.math.BigDecimal("-50")) < 0
        || wire.temperatureC().compareTo(
                new java.math.BigDecimal("150")) > 0) {
    throw new IllegalArgumentException("Invalid JSON telemetry");
}
TelemetryEvent event = new TelemetryEvent(
        wire.sensorId(), wire.sequence(), wire.temperatureC());
~~~

Đoạn minh họa cần được đặt trong method có xử lý exception. Phương thức `readValue` chỉ giải mã JSON và mapping; ứng dụng vẫn phải kiểm tra version, miền giá trị, ID và sequence. `FAIL_ON_UNKNOWN_PROPERTIES` giúp phát hiện trường lạ; `FAIL_ON_MISSING_CREATOR_PROPERTIES` kiểm tra các tham số constructor bị thiếu trên những phiên bản Jackson 2 hỗ trợ cấu hình này. Việc tách DTO giao thức `TelemetryJson` khỏi DTO nghiệp vụ `TelemetryEvent` giúp kiểm soát version mà không làm rò dữ liệu tầng truyền tải sang service.

Lưu ý: code trên dùng API **Jackson 2 (`com.fasterxml.jackson.databind`)**. Nếu dự án dùng major version khác, chọn package/dependency tương ứng. Với JSON không đáng tin, giới hạn size, độ sâu lồng nhau, số trường và độ dài chuỗi trước khi xử lý tốn tài nguyên.

## 11. Binary payload: không phải mọi bytes đều là UTF-8

Giả sử thiết bị có giao thức 9 byte:

~~~text
Byte 0      : version (unsigned 8-bit)
Byte 1..2   : sensor ID (unsigned 16-bit, big-endian)
Byte 3..6   : sequence (unsigned 32-bit, big-endian)
Byte 7..8   : nhiệt độ x 10 (signed 16-bit, big-endian)
Tổng        : 9 byte
~~~

Parser nhị phân:

~~~java
import java.math.BigDecimal;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class BinaryTelemetryDecoder {

    public static TelemetryEvent decode(byte[] bytes) {
        if (bytes.length != 9) {
            throw new IllegalArgumentException("Expected 9 bytes");
        }

        ByteBuffer buf = ByteBuffer.wrap(bytes)
                .order(ByteOrder.BIG_ENDIAN);

        int version = Byte.toUnsignedInt(buf.get());
        int sensorId = Short.toUnsignedInt(buf.getShort());
        long sequence = Integer.toUnsignedLong(buf.getInt());
        short scaledTemperature = buf.getShort();

        if (version != 1) {
            throw new IllegalArgumentException(
                    "Unsupported version");
        }

        BigDecimal temperature =
                BigDecimal.valueOf(scaledTemperature, 1);

        return new TelemetryEvent(
                "sensor-" + sensorId, sequence, temperature);
    }
}
~~~

Ở đây `scaledTemperature=265` ứng với **26,5°C**. `ByteOrder.BIG_ENDIAN` và số byte phải theo đúng tài liệu giao thức; `ByteBuffer` mặc định big-endian nhưng việc khai báo tường minh giúp tránh hiểu nhầm. Kiểm tra chiều dài **chính xác** trước khi đọc, dùng chuyển đổi unsigned đúng loại và từ chối version không hỗ trợ.

Với protobuf, CBOR hoặc định dạng binary riêng, phải dùng parser tương ứng. `new String(bytes, UTF_8)` không tạo được một biểu diễn trung gian có nghĩa cho các payload này.

## 12. Chuyển đổi ngược DTO → byte[] khi gửi UDP outbound

Khi ứng dụng có `TelemetryEvent` và cần phát ra UDP, thực hiện chiều ngược:

~~~mermaid
flowchart LR
    A["TelemetryEvent"] --> B["Serialize theo contract"]
    B --> C["byte[] UTF-8"]
    C --> D["Kiểm tra byte length"]
    D --> E["UDP outbound adapter"]
    E --> F["UDP datagram"]
~~~

Encoder:

~~~java
import java.nio.charset.StandardCharsets;

public final class TelemetryEncoder {

    private TelemetryEncoder() {}

    public static byte[] encode(TelemetryEvent event) {
        if (event == null
                || event.sensorId() == null
                || !event.sensorId().matches("[A-Za-z0-9_-]{1,32}")
                || event.sequence() < 0
                || event.temperatureC() == null) {
            throw new IllegalArgumentException("Invalid event");
        }

        String text = "v=1"
                + ";sensor=" + event.sensorId()
                + ";seq=" + event.sequence()
                + ";tempC=" + event.temperatureC().toPlainString();

        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        if (bytes.length == 0 || bytes.length > 512) {
            throw new IllegalArgumentException(
                    "Encoded payload too large");
        }
        return bytes;
    }
}
~~~

Ghép vào một outbound flow:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.dsl.Udp;

@Configuration
public class UdpOutboundEncodeConfig {

    @Bean
    public IntegrationFlow telemetryOutboundFlow() {
        return IntegrationFlow.from("telemetryToUdp")
                .<TelemetryEvent, byte[]>transform(
                        TelemetryEncoder::encode)
                .handle(Udp.outboundAdapter("127.0.0.1", 12018))
                .get();
    }
}
~~~

Channel `telemetryToUdp` nhận `Message<TelemetryEvent>`; transformer đổi thành `byte[]`; outbound handler gửi gói đến receiver ở `127.0.0.1:12018`. Đây là **ví dụ gửi riêng**, không phải listener đang nhận ở port 12017. Trong Docker, loopback chỉ trỏ tới container hiện tại; khi gửi qua mạng, dùng host/IP có thể truy cập.

Nếu `MessageChannel.send()` trả về `true` hoặc outbound handler không ném exception, **vẫn chưa có bằng chứng receiver đã nhận và commit nghiệp vụ**. UDP thuần không có ACK tự động.

## 13. Framing, kích thước datagram và dữ liệu bị cắt

Có ba kích thước cần phân biệt:

| Kích thước | Ví dụ | Rủi ro |
|---|---|---|
| **Payload ứng dụng** | 512 byte UTF-8 | Vượt contract nghiệp vụ |
| **UDP payload trên mạng** | 512 byte raw hoặc 516 byte nếu có prefix 4 byte | Phải tính thêm framing |
| **Buffer đọc datagram** | `receiveBufferSize(2048)` | Datagram lớn hơn có thể bị cắt ngắn |

Khi bật Spring Integration `lengthCheck(true)`, sender thêm **4 byte prefix độ dài** và receiver tương thích đối chiếu độ dài trước khi chuyển payload vào channel. Với 512 byte nghiệp vụ, UDP payload trên dây là **516 byte**; cộng UDP header 8 byte và IPv4 header chuẩn 20 byte thì IP packet ví dụ là **544 byte** (không tính IP options/tunnel).

**Hai phía phải thống nhất framing**. Nếu sender raw còn receiver yêu cầu length prefix, bytes đầu payload có thể bị hiểu sai. Nếu chỉ kiểm tra `bytes.length <= 512`, một gói đã bị cắt có thể vô tình trông đúng giới hạn và lọt vào decoder; do đó size guard không chứng minh datagram đã nhận đủ.

Length check hỗ trợ phát hiện một số trường hợp cắt ngắn; nó **không** cứu datagram bị mất trước socket, không bảo đảm đúng thứ tự và không thay thế checksum/chữ ký. Khi payload lớn, hãy xem xét MTU/Path MTU, phân mảnh IP và transport khác nếu dữ liệu bắt buộc giao đủ.

## 14. Phân loại lỗi chuyển đổi

| Lỗi | Ví dụ | Hành vi phù hợp |
|---|---|---|
| Size | 0 hoặc 513 byte theo contract 1–512 | Reject, metric `udp_invalid_size_total` |
| Encoding | Bytes `C3 28` | Reject bởi decoder `REPORT` |
| Schema | Thiếu `seq`, sai số trường hoặc version | Reject, metric lỗi schema |
| Business rule | Nhiệt độ `999` | Reject hoặc quarantine theo chính sách |
| Datagram truncation | Receiver buffer quá nhỏ | Điều chỉnh buffer/framing, xác minh bằng capture |
| Network loss | Datagram không đến socket | Không có message cho transformer xử lý |
| Downstream unavailable | Database/broker dừng | Retry có giới hạn và idempotency nếu cần |

Khi transformer ném `IllegalArgumentException`, Spring Integration có thể bọc thành messaging exception; chính sách chuyển lỗi vào error channel phụ thuộc endpoint, channel và cấu hình cụ thể. Thiết kế rõ **error flow, metric và log** cho gói lỗi; không giả định mọi mất gói hoặc lỗi transport đều trở thành `ErrorMessage`.

Với dữ liệu không hợp lệ theo schema, retry vô hạn cùng bytes sẽ không sửa được nguyên nhân. Nếu nghiệp vụ yêu cầu lưu đủ bản ghi, cần ACK/retry ở tầng ứng dụng và nơi lưu bền hoặc đổi sang HTTP, Kafka, JMS, AMQP phù hợp.

## 15. Kiểm thử bằng UDP client thực tế

Khởi động ứng dụng Spring Boot có cấu hình và transformers mục 6–7. Dùng PowerShell trên cùng máy để gửi một datagram hợp lệ:

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new()
try {
    $text = "v=1;sensor=node-7;seq=1042;tempC=26.5"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    [void]$client.Send(
        $bytes, $bytes.Length, "127.0.0.1", 12017
    )
}
finally {
    $client.Dispose()
}
~~~

Log minh họa:

~~~text
Sensor=node-7, seq=1042, UDP source=127.0.0.1:<source-port>
~~~

`<source-port>` do hệ điều hành chọn và có thể đổi mỗi lần tạo `UdpClient`. Nó không phải port listener 12017.

### 15.1. Gửi bytes UTF-8 không hợp lệ

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new()
try {
    $invalid = [byte[]](0xC3, 0x28)
    [void]$client.Send(
        $invalid, $invalid.Length, "127.0.0.1", 12017
    )
}
finally {
    $client.Dispose()
}
~~~

`StrictUtf8.decode` phải từ chối gói trên. Hãy thử thêm:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5   # hợp lệ
v=1;sensor=node-7;seq=x;tempC=26.5      # seq sai
v=1;sensor=node-7;tempC=26.5             # thiếu field
v=2;sensor=node-7;seq=1042;tempC=26.5   # version sai
v=1;sensor=node-7;seq=1042;tempC=999    # ngoài miền
~~~

Đổi biến `$text` trong ví dụ gửi thành từng dòng (bỏ chú thích sau `#`). Với payload 513 byte, transformer phải reject trước khi decode.

### 15.2. Unit test chuyển đổi

~~~java
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class UdpPayloadTransformersTest {

    private final UdpPayloadTransformers converter =
            new UdpPayloadTransformers();

    @Test
    void convertsValidTelemetry() {
        byte[] bytes = ("v=1;sensor=node-7;seq=1042;tempC=26.5")
                .getBytes(StandardCharsets.UTF_8);

        TelemetryEvent event =
                converter.parse(converter.decodeUtf8(bytes));

        assertEquals("node-7", event.sensorId());
        assertEquals(1042L, event.sequence());
        assertEquals(0, event.temperatureC().compareTo(
                new java.math.BigDecimal("26.5")));
    }

    @Test
    void rejectsMalformedUtf8() {
        byte[] bad = {(byte) 0xC3, (byte) 0x28};
        assertThrows(IllegalArgumentException.class,
                () -> converter.decodeUtf8(bad));
    }

    @Test
    void rejectsOversizeMessage() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.decodeUtf8(new byte[513]));
    }
}
~~~

Unit test chứng minh logic converter theo bytes xác định. Integration test qua socket thật mới xác nhận được adapter nhận datagram, mapping header nguồn, routing qua channel và lifecycle. Chỉ gửi sau khi listener đã sẵn sàng; vì UDP không có đảm bảo giao hàng, một lần gửi trong test không phải bằng chứng tin cậy tổng quát.

## 16. Bảo mật, hiệu năng và quan sát

- **Validate sớm:** giới hạn kích thước byte trước khi decode hoặc parse JSON/protobuf; từ chối version và schema không hỗ trợ.
- **Tránh tạo đối tượng không giới hạn:** parser JSON có thể bị lạm dụng qua độ sâu, số trường và độ dài dữ liệu; đặt giới hạn phù hợp.
- **Dùng đúng decoder:** UTF-8 strict cho văn bản; `ByteBuffer`/protocol parser cho nhị phân; không đoán kiểu từ vài byte nếu hợp đồng không định nghĩa.
- **Không tin địa chỉ nguồn:** `ip_address` có thể thay đổi do NAT hoặc bị giả mạo ở một số môi trường; thực hiện xác thực thông điệp/device nếu cần.
- **Không log nguyên gói:** tránh lộ dữ liệu và log spam; log loại lỗi, kích thước, ID đã kiểm tra và metric với cardinality hợp lý.
- **Giữ transformer nhanh:** nếu `DirectChannel` nối trực tiếp xử lý chậm, nguy cơ rớt UDP tăng; tách sang executor/queue có giới hạn, nhưng việc tách kênh không biến UDP thành transport tin cậy.
- **Theo dõi vòng đời:** socket phải listening mới sinh được message; khi adapter stop/restart, datagram có thể bị mất trước bước chuyển đổi.

Các metric gợi ý gồm `udp_received_total`, `udp_decoded_total`, `udp_invalid_size_total`, `udp_invalid_encoding_total`, `udp_invalid_schema_total` và `udp_business_processed_total`. Đo riêng số gói receiver nhận và số record nghiệp vụ ghi thành công.

## 17. Bài thực hành củng cố

Xây một pipeline **UDP → `Message<byte[]>` → `TelemetryEvent` → database** theo hợp đồng:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

Yêu cầu:

1. Dùng `Udp.inboundAdapter(12017)` với raw UDP và receive buffer đủ lớn.
2. Viết transformer từ `byte[]` sang `String` bằng UTF-8 strict, kiểm tra giới hạn 512 byte.
3. Viết transformer từ `String` sang `TelemetryEvent`, kiểm tra version, sensor, sequence và nhiệt độ.
4. Bảo toàn `ip_address`/`ip_port` để quan sát nguồn gửi; không dùng địa chỉ nguồn làm danh tính tin cậy.
5. Gửi các gói hợp lệ, UTF-8 lỗi, version sai, schema sai, quá kích thước; phân loại lỗi bằng metric.
6. Viết encoder ngược từ DTO sang `byte[]` và gửi UDP tới một listener thử nghiệm, xác minh dữ liệu được round-trip.
7. Thử payload JSON và một payload binary 9 byte; chọn đúng decoder cho từng định dạng.
8. Giả lập database ngừng hoạt động, đề xuất cách xử lý retry/ACK/idempotency nếu không được mất dữ liệu.

**Câu hỏi tự đánh giá:**

- Vì sao `Message<byte[]>` chưa đủ để xử lý telemetry dưới dạng dữ liệu nghiệp vụ?
- `CharsetDecoder.REPORT` giải quyết điều gì?
- Vì sao dùng `String.length()` để giới hạn datagram UTF-8 có thể sai?
- Khi nào nên trả `TelemetryEvent` từ transformer, khi nào dùng `String` trung gian?
- Header `ip_packetAddress` có tự nằm trong UDP payload không?
- Vì sao không nên giải mã protobuf thành `String` trước khi parse?
- Nếu datagram đã bị cắt do buffer nhỏ, converter có phục hồi được phần byte mất không?
- Khi producer đọc file hoặc DB bằng poller rồi gửi UDP outbound, giới hạn byte cần đặt tại bước nào?

## 18. Tài liệu tham khảo

- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): datagram, inbound/outbound adapter và framing.
- [Spring Integration Reference — IP Message Headers](https://docs.spring.io/spring-integration/reference/ip/msg-headers.html): header nguồn UDP.
- [Spring Integration Reference — Message Transformation](https://docs.spring.io/spring-integration/reference/transformer.html): transformer và message payload.
- [Oracle CharsetDecoder API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html): UTF-8 strict và `CodingErrorAction.REPORT`.
- [RFC 8085 — UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085): rủi ro về kích thước datagram, phân mảnh và giao hàng.

## Kết luận

Trong Spring Integration, `byte[]` là **payload thô** được UDP inbound adapter đưa vào message. Để ứng dụng dùng an toàn, cần **kiểm tra byte length → decode theo charset/protocol → validate version và schema → tạo DTO có kiểu → xử lý nghiệp vụ**. Các transformer và `MessageChannel` giúp tách trách nhiệm nhận datagram khỏi logic hiểu dữ liệu và tích hợp với những hệ thống phía sau.

Khi truyền tiếp sang HTTP, file, SFTP, JMS, AMQP, Kafka hay cơ sở dữ liệu, hãy quy định rõ dữ liệu nào là payload nghiệp vụ, metadata nào cần giữ, quy tắc lỗi, timeout và lưu bền. **Chuyển đổi đúng kiểu không đảm bảo UDP giao hàng thành công hoặc transaction phía sau đã hoàn tất.**
