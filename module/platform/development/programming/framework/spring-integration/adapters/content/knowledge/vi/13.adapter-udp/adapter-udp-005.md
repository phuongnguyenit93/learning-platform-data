# Datagram packet size và giới hạn payload trong Spring Integration UDP

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **kích thước payload của ứng dụng**, **UDP datagram**, **IP packet**, **MTU/Path MTU**, **buffer nhận từng datagram** và **socket receive buffer**.
- Tính giới hạn UDP payload theo IPv4/IPv6 và giải thích vì sao giới hạn lý thuyết khoảng 65 KB không phải kích thước gửi phù hợp mặc định.
- Hiểu hiện tượng **IP fragmentation**, mất fragment, cắt ngắn datagram ở receiver và ảnh hưởng của NAT, VPN hoặc container.
- Cấu hình Spring Integration UDP inbound/outbound adapter để nhận message theo đúng kích thước, kiểm tra hợp đồng dữ liệu và dùng **`check-length`** khi hai phía cùng hỗ trợ.
- Thực hành gửi các payload nhỏ, đúng ngưỡng và quá ngưỡng; quan sát khác biệt giữa lỗi nghiệp vụ, lỗi cắt ngắn và lỗi mất gói.
- Thiết kế chính sách về giới hạn byte, throughput, retry/ACK và metric trước khi ghép luồng UDP với file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu.

Bài thuộc chương **Adapter UDP**, module **SPRING_INTEGRATION_ADAPTERS**. Module đưa các hệ thống ngoài vào Spring Integration bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; vì vậy cần xác lập **hợp đồng message** tại ranh giới truyền tải. Với UDP, *kích thước datagram* là phần quan trọng của hợp đồng: nó tác động trực tiếp đến khả năng nhận đầy đủ payload, lỗi mạng và chi phí xử lý ở cả hai phía.

## 1. Bài toán: gói telemetry nhỏ và gói JSON quá lớn

Một collector nhận sự kiện từ thiết bị qua UDP:

~~~text
v=1;sensor=node-7;seq=1042;tempC=26.5
~~~

Thông điệp chỉ vài chục byte. Nhưng khi một thiết bị đính kèm lịch sử đo, log lỗi hoặc JSON lồng sâu, payload có thể tăng lên 5 KB, 20 KB, thậm chí lớn hơn. Sender vẫn có thể tạo `DatagramPacket` và gọi `send()`; từ đó phát sinh những câu hỏi:

1. Datagram có bị phân mảnh trên đường mạng không?
2. Receiver cấp đủ byte để đọc datagram chưa?
3. Nếu receiver chỉ có buffer nhỏ, có biết payload đã bị cắt ngắn không?
4. Nếu payload đến đầy đủ nhưng vượt hạn mức nghiệp vụ, hệ thống sẽ xử lý thế nào?
5. Nếu phải lưu đủ tất cả sự kiện, UDP có đáp ứng được không?

~~~mermaid
flowchart LR
    P["Ứng dụng sender<br/>payload byte[]"] --> O["UDP outbound adapter"]
    O --> N["UDP + IP<br/>đường mạng / MTU"]
    N --> R["UDP inbound adapter<br/>DatagramPacket buffer"]
    R --> V{"Đủ byte<br/>và hợp lệ?"}
    V -->|Có| C["MessageChannel<br/>xử lý nghiệp vụ"]
    V -->|Không| E["Ghi metric lỗi<br/>loại gói / xử lý phù hợp"]
~~~

**Hai câu hỏi độc lập cần trả lời:** *Gói UDP có đến đầy đủ hay không?* và *payload đủ nhưng có vượt giới hạn nghiệp vụ hay không?* Tránh nhập hai tình huống này thành cùng một lỗi.

## 2. Phân biệt các loại kích thước

| Đại lượng | Đếm byte gì? | Ai kiểm soát? |
|---|---|---|
| **Application payload** | Dữ liệu nghiệp vụ sau khi encode, ví dụ UTF-8 JSON hoặc protobuf | Sender và hợp đồng giữa hai hệ thống |
| **Spring Integration UDP length prefix** | **4 byte thêm trước payload**, chỉ khi bật `check-length` phía gửi | Cấu hình Spring Integration của cả sender/receiver |
| **UDP payload** | Dữ liệu nằm sau 8 byte header UDP; gồm length prefix nếu được bật | Ứng dụng và framing adapter |
| **UDP datagram** | 8 byte UDP header + UDP payload | UDP/IP stack |
| **IP packet** | IP header + UDP datagram | IP stack, phụ thuộc IPv4/IPv6 và các header tùy chọn |
| **Link MTU** | Giới hạn gói IP mà một chặng mạng truyền mà không cần phân mảnh (theo ngữ cảnh cấu hình) | Interface/thiết bị mạng |
| **Path MTU (PMTU)** | MTU nhỏ nhất trên các chặng của đường truyền tới đích | Topology mạng; có thể thay đổi |
| **Adapter receive buffer** | Số byte mà receiver chuẩn bị để đọc **một datagram** | `receive-buffer-size` / `receiveBufferSize(...)` |
| **Socket receive buffer** | Bộ đệm kernel cho lưu lượng đang chờ socket đọc | `so-receive-buffer-size` / `soReceiveBufferSize(...)` |

**Lưu ý:** `byte[].length` là số byte, `String.length()` là số **UTF-16 code unit**. Với tiếng Việt, emoji và dữ liệu Unicode, hai con số này có thể khác nhau. Giới hạn UDP phải được áp dụng **sau bước encode**, theo `byte[].length`, không dựa vào số ký tự.

### Ví dụ cách đếm byte

Giả sử payload UTF-8 đúng **512 byte**, IPv4 header chuẩn 20 byte (không có IP options):

~~~text
Không bật length check:
  Application payload        512 byte
  UDP header                   8 byte
  IPv4 header                 20 byte
  -------------------------------
  Tổng IP packet             540 byte

Bật length check:
  Application payload        512 byte
  Spring length prefix         4 byte
  UDP header                   8 byte
  IPv4 header                 20 byte
  -------------------------------
  Tổng IP packet             544 byte
~~~

Nếu dùng IPv6 header chuẩn 40 byte và không có extension headers, hai tổng tương ứng là **560** và **564 byte**. Các tính toán này chưa bao gồm Ethernet framing, VLAN tag, VPN/tunnel overhead hoặc các header IP tùy chọn.

## 3. Giới hạn lý thuyết của UDP không phải giới hạn vận hành

UDP có phần `Length` dài 16 bit, bao gồm 8 byte UDP header và phần payload. Với IP packet thông thường:

| Trường hợp | Header IP chuẩn | UDP header | UDP payload tối đa lý thuyết |
|---|---:|---:|---:|
| IPv4, không có IP options | 20 byte | 8 byte | **65.507 byte** |
| IPv6, không có extension headers hoặc jumbogram | 40 byte | 8 byte | **65.527 byte** |

Đây là **giới hạn lý thuyết** theo kích thước packet IP thông thường, không phải cam kết của mạng thực tế hoặc buffer nhận. IPv6 có cơ chế *jumbogram* đặc biệt, nhưng không phải trường hợp phổ biến của UDP adapter; không thiết kế telemetry dựa vào ngoại lệ này.

Khi payload lên tới vài chục KB, gói IP thường lớn hơn MTU của nhiều chặng. Hệ điều hành có thể phân mảnh nếu giao thức và chính sách cho phép, hoặc báo lỗi gửi/từ chối gói. Việc API gửi không phát sinh exception **không chứng minh** rằng receiver đã nhận được datagram đầy đủ.

**Khuyến nghị:** đặt giới hạn payload dựa trên schema, nhu cầu nghiệp vụ, đường truyền và bài thử thật; không lấy 65.507 hoặc 65.527 byte làm `MAX_PAYLOAD` mặc định.

## 4. MTU, Path MTU và kích thước tránh phân mảnh

### 4.1. Công thức tính

Khi biết **PMTU** và không có lớp đóng gói bổ sung:

~~~text
Max UDP payload không phân mảnh
    = Path MTU - IP header - UDP header
~~~

Ví dụ với Ethernet MTU **1500 byte** trên đường truyền trực tiếp, không có tunnel và header tùy chọn:

| IP version | PMTU ví dụ | Header IP | Header UDP | UDP payload tối đa theo phép tính |
|---|---:|---:|---:|---:|
| IPv4 | 1500 | 20 | 8 | **1472 byte** |
| IPv6 | 1500 | 40 | 8 | **1452 byte** |
| IPv6, giả sử PMTU 1280 | 1280 | 40 | 8 | **1232 byte** |
| IPv4, giả sử PMTU 576 | 576 | 20 | 8 | **548 byte** |

Bảng trên giả định IP header cơ bản, không có extension/header option và không có overhead của đường hầm. Với Spring Integration `check-length=true`, phải **trừ thêm 4 byte** khỏi ngân sách dành cho **application payload**.

Chẳng hạn: trên PMTU IPv6 1280, UDP payload tối đa theo phép tính là 1232 byte. Nếu có prefix 4 byte thì phần ứng dụng tối đa theo phép tính là **1228 byte**.

### 4.2. Tại sao nhiều hệ thống chọn thông điệp nhỏ?

Một số ứng dụng chọn **khoảng 1200 byte hoặc nhỏ hơn** làm ngân sách UDP payload cho mạng có PMTU chưa biết rõ, nhằm tránh phân mảnh trong nhiều tình huống IPv6 phổ biến. Đây chỉ là **quy ước thiết kế có điều kiện**, không phải đảm bảo xuyên mọi mạng: IPv4 có thể có path MTU thấp hơn; VPN, GRE, IPsec hoặc overlay network có thể làm giảm ngân sách payload. RFC 8085 khuyến nghị ứng dụng tránh gửi datagram khiến IP packet vượt PMTU và sử dụng thông tin PMTU hoặc cơ chế khám phá PMTU khi phù hợp.

Với một hệ thống telemetry đơn giản, chọn **512 byte payload nghiệp vụ** thường đủ cho bản ghi nhỏ và dễ kiểm soát. Giá trị 512 trong bài là **hợp đồng minh họa**, không phải giới hạn UDP hoặc mặc định của Spring Integration.

### 4.3. Vì sao phân mảnh làm giảm độ tin cậy?

Giả sử ứng dụng tạo gói UDP mà IP phải tách thành nhiều fragment:

~~~mermaid
flowchart TD
    U["UDP datagram lớn"] --> F["IP fragmentation"]
    F --> A["Fragment 1"]
    F --> B["Fragment 2"]
    F --> C["Fragment 3"]
    A --> R["IP reassembly tại máy đích"]
    B --> R
    C --> R
    R --> D["UDP datagram hoàn chỉnh<br/>đưa tới socket"]
    X["Mất một fragment"] -.-> C
~~~

IP receiver cần đủ các fragment để dựng lại datagram hoàn chỉnh. Nếu một fragment mất hoặc bị firewall/NAT chặn, **toàn bộ datagram** có thể không tới UDP socket. **IPv4** có cơ chế fragmentation ở nguồn và một số router tùy trường hợp; với **IPv6**, router không tự phân mảnh packet, nguồn cần xử lý giới hạn PMTU hoặc sử dụng cơ chế phân mảnh được hỗ trợ.

Điều này giải thích vì sao **tăng buffer trong Spring Integration không thể cứu datagram bị mất trước khi vào socket**.

## 5. Hai tầng buffer ở UDP inbound adapter

Spring Integration có hai thuộc tính dễ nhầm:

| Thuộc tính XML | Java DSL | Tầng áp dụng | Khi quá nhỏ |
|---|---|---|---|
| `receive-buffer-size` | `receiveBufferSize(n)` | Sức chứa dữ liệu của **một `DatagramPacket`** khi adapter gọi receive | Datagram đến có thể bị **cắt ngắn**, phần dư không được nhận trong lần tiếp theo |
| `so-receive-buffer-size` | `soReceiveBufferSize(n)` | Socket/kernel receive buffer | Khi nhận nhiều gói nhanh, hàng đợi kernel có thể đầy và **bỏ datagram** |

Ví dụ:

~~~yaml
application-contract:
  max-payload-bytes: 512
transport:
  datagram-receive-buffer-bytes: 2048
  requested-socket-receive-buffer-bytes: 262144
~~~

Đây là **minh họa chính sách**; các key YAML này không tự động trở thành cấu hình của Spring Integration. Người triển khai phải gắn chúng vào adapter hoặc Java DSL.

Nếu ứng dụng giới hạn payload 512 byte, vì sao vẫn có thể dùng receive buffer **2048 byte**? Vì receiver có cơ hội **nhận đầy đủ và từ chối có chủ đích** các gói nằm trong khoảng 513–2048 byte, thay vì cắt ngắn xuống 512 khiến không biết sender đã gửi bao nhiêu byte.

Với datagram lớn hơn buffer, nếu không có framing phát hiện độ dài, receiver không nhất thiết biết có cắt ngắn: một packet dài 4096 byte có thể chỉ cung cấp 2048 byte cho adapter. **Ứng dụng không thể “đọc phần còn lại” của cùng datagram trong lần receive kế tiếp**.

### 5.1. Socket receive buffer không thay thế packet buffer

Giả sử kernel giữ được nhiều gói trong socket receive buffer nhưng adapter cấp mỗi `DatagramPacket` 256 byte. Một gói 800 byte **vẫn có thể bị cắt ngắn** khi socket trả dữ liệu cho adapter. Tăng `so-receive-buffer-size` mà giữ `receive-buffer-size=256` không giải quyết nguyên nhân này.

Ngược lại, đặt `receive-buffer-size=4096` nhưng handler tốn 500 ms/gói và sender phát 5.000 gói/giây thì kernel vẫn có thể không giữ kịp tất cả datagram.

### 5.2. Không giả định kích thước socket buffer được áp dụng tuyệt đối

`so-receive-buffer-size` là **giá trị yêu cầu** tới hệ điều hành; OS có thể điều chỉnh theo giới hạn và cách triển khai socket. Không dùng con số cấu hình để khẳng định kernel thực tế đang cấp chính xác bấy nhiêu byte.

Tương tự, `so-send-buffer-size` ở outbound liên quan đến socket gửi, không phải kích thước datagram nghiệp vụ; tăng send buffer không biến UDP thành transport có retry, ACK hay bảo đảm giao hàng.

## 6. Cấu hình Java DSL: receiver có giới hạn rõ ràng

Ví dụ dùng Spring Boot và Spring Integration IP. Nếu Spring Boot đang quản lý phiên bản dependency, thông thường không cần đặt version thủ công:

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

Tạo inbound adapter lắng nghe `12015`, có buffer nhận datagram 2048 byte và socket receive buffer theo yêu cầu 256 KiB:

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
public class UdpPacketSizeConfig {

    public static final int PORT = 12015;

    @Bean("udpRawPayloads")
    public MessageChannel udpRawPayloads() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow udpReceiverFlow() {
        return IntegrationFlow.from(
                    Udp.inboundAdapter(PORT)
                        .receiveBufferSize(2048)
                        .soReceiveBufferSize(262_144)
                        .lengthCheck(false))
                .channel("udpRawPayloads")
                .get();
    }
}
~~~

**Ý nghĩa các lựa chọn:**

1. `receiveBufferSize(2048)` dành chỗ để nhận một datagram tối đa 2048 byte theo cấu hình adapter; dữ liệu lớn hơn vẫn có nguy cơ bị cắt.
2. `soReceiveBufferSize(262_144)` yêu cầu tăng sức chứa ở kernel để chịu được các đợt gói đến dồn dập, tùy khả năng OS.
3. `lengthCheck(false)` dùng **datagram raw**. Sender PowerShell, Python hoặc thiết bị không biết framing Spring Integration có thể gửi UTF-8 trực tiếp.
4. `MessageChannel` là ranh giới giữa nhận UDP và xử lý nghiệp vụ. Với `DirectChannel`, handler phía sau nên thực hiện các thao tác nhanh hoặc bàn giao sang tầng xử lý phù hợp để hạn chế nghẽn.

**Không dùng poller để nhận từng datagram:** inbound UDP adapter chủ động lắng nghe socket. Một poller ở trước/sau luồng chỉ xuất hiện nếu có thành phần khác cần thăm dò như file, database hay `QueueChannel`.

## 7. Kiểm tra byte[] ở tầng nghiệp vụ

Adapter không tự biết schema telemetry hoặc mức 512 byte mà nghiệp vụ đã quy định. Tạo service activator kiểm tra giới hạn trước khi decode:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class UdpPayloadGuard {

    private static final Logger log =
            LoggerFactory.getLogger(UdpPayloadGuard.class);
    private static final int MAX_PAYLOAD_BYTES = 512;

    @ServiceActivator(inputChannel = "udpRawPayloads")
    public void accept(Message<byte[]> message) {
        byte[] bytes = message.getPayload();

        if (bytes.length == 0 || bytes.length > MAX_PAYLOAD_BYTES) {
            log.warn("UDP payload rejected, observedBytes={}", bytes.length);
            return;
        }

        final String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException ex) {
            log.warn("UDP payload rejected: invalid UTF-8");
            return;
        }

        // Ví dụ: chưa parse đầy đủ schema nghiệp vụ.
        log.info("UDP payload accepted: bytes={}", bytes.length);
        processTelemetry(text);
    }

    private void processTelemetry(String payload) {
        // Ứng dụng thật: validate schema, version, sensor ID, seq...
    }
}
~~~

Đây là **guard kích thước và UTF-8**, không phải full validator. Các bước tiếp theo vẫn phải xác minh `v`, `sensor`, `seq`, miền giá trị nhiệt độ, định danh thiết bị và chính sách chống trùng. Tránh log toàn bộ payload ở production khi dữ liệu nhạy cảm hoặc số lượng gói lớn.

**Một giới hạn quan trọng:** nếu một datagram 4096 byte bị cắt xuống còn 2048 byte ở lớp nhận, guard thấy 2048 byte và từ chối vì vượt 512. Nhưng với một hợp đồng chỉ cho phép 4096 byte và receive buffer nhỏ hơn, guard có thể vô tình chấp nhận **payload bị cắt** nếu các byte đầu vẫn trông hợp lệ. Muốn phát hiện cắt ngắn đáng tin hơn, cần cơ chế kiểm tra độ dài/framing tương thích hoặc hợp đồng dữ liệu có checksum, độ dài, chữ ký, sequence theo yêu cầu.

## 8. Giới hạn kích thước trước khi gửi UDP outbound

Kiểm soát ở **sender** giúp tránh tiêu tốn băng thông cho payload biết chắc sẽ bị receiver từ chối.

Ví dụ một publisher gửi `byte[]` UTF-8 vào `MessageChannel`:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class UdpTelemetryPublisher {

    private static final int MAX_PAYLOAD_BYTES = 512;
    private final MessageChannel outbound;

    public UdpTelemetryPublisher(
            @Qualifier("udpToCollector") MessageChannel outbound) {
        this.outbound = outbound;
    }

    public void publish(String telemetry) {
        if (telemetry == null) {
            throw new IllegalArgumentException("Missing telemetry");
        }

        byte[] encoded = telemetry.getBytes(StandardCharsets.UTF_8);
        if (encoded.length == 0 || encoded.length > MAX_PAYLOAD_BYTES) {
            throw new IllegalArgumentException(
                    "UDP encoded payload outside 1..512 bytes");
        }

        boolean dispatched =
                outbound.send(MessageBuilder.withPayload(encoded).build());
        if (!dispatched) {
            throw new IllegalStateException(
                    "UDP outbound message was not dispatched");
        }
    }
}
~~~

Để ghép publisher vào cấu hình ở mục 6, thêm hai bean sau **bên trong class `UdpPacketSizeConfig`**:

~~~java
@Bean("udpToCollector")
public MessageChannel udpToCollector() {
    return new DirectChannel();
}

@Bean
public IntegrationFlow udpOutboundFlow() {
    return IntegrationFlow.from("udpToCollector")
            .handle(Udp.outboundAdapter("127.0.0.1", PORT))
            .get();
}
~~~

Địa chỉ `127.0.0.1` phù hợp khi thử sender và receiver trên cùng host. Nếu ứng dụng chạy trong container, loopback này nằm **trong container**, không tự trỏ tới máy host. Khi triển khai thật, đặt IP/DNS và port đích vào configuration. Một payload được dispatch thành công đến outbound handler **không có nghĩa collector đã nhận**.

### Vì sao phải giới hạn bằng byte[] thay vì String?

~~~java
String message = "nhiệt-độ";
int javaUnits = message.length();
int utf8Bytes =
        message.getBytes(StandardCharsets.UTF_8).length;
~~~

Hai giá trị `javaUnits` và `utf8Bytes` có thể khác nhau, vì ký tự Unicode có số byte UTF-8 khác với số UTF-16 code unit. Dùng `encoded.length` khi kiểm tra ngân sách UDP.

## 9. Length check: phát hiện datagram bị cắt ngắn

Spring Integration UDP hỗ trợ tùy chọn **`check-length`**. Khi bật ở **outbound**, adapter đặt một **tiền tố dài 4 byte theo network byte order** trước dữ liệu. **Inbound** được cấu hình tương ứng sẽ sử dụng tiền tố độ dài này để đối chiếu với datagram nhận được, giúp phát hiện trường hợp buffer quá nhỏ làm mất phần đuôi gói.

~~~mermaid
flowchart LR
    A["Payload ứng dụng N byte"] --> B["Thêm length prefix 4 byte"]
    B --> C["UDP datagram chứa 4 + N byte dữ liệu"]
    C --> D["Receiver kiểm tra độ dài"]
    D --> E{"Độ dài đúng?"}
    E -->|Có| F["Chuyển payload sang MessageChannel"]
    E -->|Không| G["Xử lý lỗi theo adapter"]
~~~

Nếu sender gửi **512 byte payload**, phần dữ liệu của datagram mang tới UDP phải dành chỗ cho **516 byte** khi bật length check. Hãy trừ 4 byte này khi tính ngân sách PMTU.

### 9.1. Cấu hình cả hai phía

Ví dụ Java DSL **thay thế** cách cấu hình inbound/outbound ở các mục trước:

~~~java
@Bean
public IntegrationFlow lengthCheckedInbound() {
    return IntegrationFlow.from(
            Udp.inboundAdapter(12016)
               .receiveBufferSize(2048)
               .lengthCheck(true))
            .channel("udpRawPayloads")
            .get();
}

@Bean
public IntegrationFlow lengthCheckedOutbound() {
    return IntegrationFlow.from("udpToCollector")
            .handle(Udp.outboundAdapter("127.0.0.1", 12016)
                       .lengthCheck(true))
            .get();
}
~~~

Để thử riêng cấu hình trên, chỉ kích hoạt **một** bộ outbound subscriber và cổng inbound tương ứng; không đăng ký đồng thời outbound cũ cùng một channel nếu không cố ý thay đổi cách dispatch.

**Khả năng tương thích:** receiver PowerShell thông thường chỉ đọc raw bytes và sẽ nhìn thấy 4 byte prefix nếu sender Spring bật `lengthCheck(true)`. Ngược lại, receiver Spring bật `lengthCheck(true)` nhưng sender gửi raw UTF-8 sẽ không hiểu đúng khung dữ liệu. **Hai phía phải thống nhất giao thức** trước khi bật.

### 9.2. Length check giúp gì và không giúp gì?

| Tình huống | Length check có ích? | Giải thích |
|---|---|---|
| Packet tới socket nhưng bị cắt do receive buffer quá nhỏ | **Có** | Độ dài thực nhận không khớp thông tin khai báo |
| Gói mất hoàn toàn trên mạng | **Không** | Không có gói nào để kiểm tra |
| IP fragment thất lạc | **Không** | Socket thường không nhận được datagram hoàn chỉnh |
| Gói đến sai thứ tự | **Không** | Length prefix không có sequence number |
| Sender gửi sai schema nhưng đúng độ dài | **Không** | Không validate JSON/telemetry |
| Payload bị sửa nhưng giữ nguyên độ dài | **Không đủ** | Cần checksum/chữ ký phù hợp; length không phải xác thực |
| Receiver UDP bên thứ ba không biết framing | **Có nguy cơ lỗi** | Bốn byte đầu trở thành dữ liệu lạ |

**Không nhầm `check-length` với ACK.** Spring Integration còn có tùy chọn `acknowledge` phục vụ xác nhận ở tầng ứng dụng; các bên phải hỗ trợ đúng protocol. ACK kỹ thuật cũng chưa chắc đồng nghĩa giao dịch ở receiver đã commit.

## 10. Thử nghiệm với PowerShell: 511, 512, 513 và 2049 byte

Đối với cấu hình **`lengthCheck(false)`** tại cổng `12015`, chạy ứng dụng Spring Boot rồi dùng PowerShell gửi các gói raw. Mỗi payload được tạo thành ký tự ASCII `A`, nên **một ký tự tương đương một byte UTF-8**:

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new()
try {
    foreach ($size in @(511, 512, 513, 2049)) {
        $data = [byte[]]::new($size)
        for ($i = 0; $i -lt $size; $i++) {
            $data[$i] = 65  # ASCII 'A'
        }

        [void]$client.Send($data, $data.Length, "127.0.0.1", 12015)
        Write-Host "Sent UDP payload bytes: $size"
    }
}
finally {
    $client.Dispose()
}
~~~

**Kỳ vọng ở receiver trên một máy không mất gói:**

| Payload sender gửi | Adapter receive buffer | Guard nghiệp vụ 512 byte | Kỳ vọng |
|---|---:|---:|---|
| 511 byte | 2048 byte | Hợp lệ về kích thước | Được xử lý tiếp; vẫn cần validate schema |
| 512 byte | 2048 byte | Hợp lệ về kích thước | Được xử lý tiếp; vẫn cần validate schema |
| 513 byte | 2048 byte | Vượt giới hạn | Guard từ chối và tăng metric invalid |
| 2049 byte | 2048 byte | Vượt giới hạn | Có thể bị cắt ngắn ở receive; guard vẫn từ chối nếu nhận thấy quá 512 |

Bài thử trên dùng payload `AAAA...`, **không đạt schema telemetry** nếu ứng dụng đã triển khai validator đầy đủ. Kết quả ở bảng chỉ nói về **bước kiểm tra kích thước**, không phải toàn bộ pipeline nghiệp vụ.

**Giới hạn quan sát:** khi không bật length check, nếu datagram 2049 byte bị cắt thành 2048 byte thì handler có thể chỉ ghi `observedBytes=2048`; nó không được phép tuyên bố chắc chắn sender đã gửi đúng 2048 byte. Để chứng minh việc cắt ngắn, thử lại bằng cặp sender/receiver có length prefix tương thích và quan sát kết quả của bộ kiểm tra.

Trong một bài thử hiệu năng, nên đưa thêm `seq` vào payload, gửi nhiều gói và so sánh số sequence nhận được. Một lệnh `Send` PowerShell thành công chỉ cho biết hệ điều hành sender đã nhận lời gọi gửi, không đảm bảo receiver đã xử lý.

## 11. Phân biệt ba loại thất bại thường bị gom chung

~~~mermaid
flowchart TD
    A["Sender có datagram"] --> B{"Datagram có tới socket?"}
    B -->|Không| C["Packet loss / fragmentation / firewall"]
    B -->|Có| D{"Adapter đọc đủ datagram?"}
    D -->|Không| E["Receive buffer quá nhỏ / truncation"]
    D -->|Có| F{"Payload trong hợp đồng nghiệp vụ?"}
    F -->|Không| G["Reject theo schema/byte limit"]
    F -->|Có| H["Xử lý nghiệp vụ"]
~~~

| Nhóm lỗi | Dấu hiệu | Cách xác minh |
|---|---|---|
| **Mất gói trước socket** | Sender đã gọi gửi, receiver không có message | Packet capture hai đầu, firewall, MTU/fragment, số sequence bị thiếu |
| **Bị cắt ngắn khi nhận** | Handler thấy bytes ngắn hơn sender phát; độ dài có thể khớp tình cờ với buffer | Kiểm tra `receive-buffer-size`, bật compatible length check, so sánh capture và payload |
| **Vượt giới hạn nghiệp vụ** | Message đến đủ nhưng `byte[].length > MAX_PAYLOAD` | Guard tại receiver và metric invalid size |
| **Quá tải kernel/handler** | Thiếu message ở tốc độ gửi cao | Metric tốc độ, kernel UDP drop counter, thời gian xử lý, queue |
| **Sai charset/schema** | Số byte hợp lệ nhưng decode hoặc parse lỗi | Dùng UTF-8 decoder strict, version/field validator |
| **Sai framing Spring Integration** | Bật length check một phía, nội dung nhận có 4 byte lạ hoặc lỗi kiểm tra độ dài | So sánh cấu hình `check-length` sender/receiver |

Không dùng việc tăng buffer như một cách khắc phục chung cho mọi lỗi. Nguyên nhân là mất gói trên đường truyền, truncate ở tầng nhận, hay reject hợp đồng sẽ dẫn tới cách sửa rất khác nhau.

## 12. Thông lượng và giới hạn tài nguyên

Số byte trên mỗi gói chỉ là một phần bài toán. Đối với UDP, **tốc độ gói/giây**, số handler chạy đồng thời, số byte trong mỗi gói và thời gian xử lý đều ảnh hưởng tới nguy cơ mất dữ liệu.

Ví dụ: receiver xử lý trung bình **5 ms** cho một message theo đường xử lý đồng bộ đơn luồng, tương đương trần lý tưởng khoảng **200 message/giây** nếu không có độ trễ khác. Nếu sender phát 2.000 datagram/giây, buffer kernel chỉ có thể giảm ảnh hưởng trong một khoảng thời gian, không thể bù đắp nghẽn kéo dài.

**Thiết kế thực tế nên có:**

- Giới hạn số byte tại **sender** trước khi dispatch, ngay cả khi receiver cũng kiểm tra.
- `receive-buffer-size` đủ để nhận datagram đúng theo hợp đồng (bao gồm 4 byte prefix nếu dùng), có khoảng dự phòng hợp lý để phân loại gói vượt ngưỡng.
- `so-receive-buffer-size` được cấu hình theo thử nghiệm tải, kiểm tra khả năng OS áp dụng.
- Handler nhận dữ liệu nhanh, tránh công việc nặng làm nghẽn đường nhận; có thể bàn giao sang executor/hàng đợi **có giới hạn**, với chính sách khi đầy.
- Giới hạn tốc độ producer, batch logic ở tầng ứng dụng hoặc dùng broker nếu cần lưu bền/replay.
- Metric tại **sender, receiver, network và tầng nghiệp vụ**, đặc biệt tỷ lệ sequence bị thiếu.
- Phân biệt **UDP acknowledgment** (nếu có) với **ACK nghiệp vụ** và cơ chế lưu bền.

Việc chuyển từ `DirectChannel` sang xử lý bất đồng bộ có thể giúp socket reader giải phóng nhanh hơn, nhưng thêm queue sẽ tạo bài toán giới hạn bộ nhớ, độ trễ và backpressure ở các bước phía sau. Không có cấu hình channel nào tự tạo đảm bảo giao hàng từ mạng UDP.

## 13. Nếu thông điệp nghiệp vụ lớn hơn giới hạn đã chọn?

Có bốn hướng xử lý chính:

| Cách xử lý | Khi phù hợp | Đánh đổi |
|---|---|---|
| **Giảm payload**: bỏ trường thừa, rút gọn schema, dùng binary encoding | Telemetry chỉ cần vài trường | Cần quản lý version/schema và khả năng debug |
| **Nén nội dung** | Payload có độ lặp cao, kích thước đủ lớn để bù overhead | Tăng CPU, giới hạn giải nén, rủi ro payload không nén được |
| **Chia thành nhiều thông điệp ở tầng ứng dụng** | Có lý do bắt buộc giữ UDP và cần các chunk | Cần message ID, chunk index, total, timeout, chống trùng, giới hạn reassembly |
| **Đổi transport**: HTTP, TCP, JMS/AMQP/Kafka hoặc file/SFTP theo nhu cầu | Dữ liệu lớn, cần xác nhận/lưu bền/replay | Tăng chi phí kết nối/broker/độ phức tạp tích hợp |

### 13.1. Phân mảnh ở tầng ứng dụng khác phân mảnh IP

Nếu buộc truyền một bản tin lớn thành nhiều datagram nhỏ, mỗi chunk phải có **định danh bản tin**, **số thứ tự chunk**, **tổng số chunk** và cơ chế kiểm tra toàn vẹn. Receiver cần thời hạn ghép, bộ nhớ tối đa theo sender, chính sách khi thiếu chunk và cách chống trùng.

~~~text
msgId=ab12;part=1/3;data=...
msgId=ab12;part=2/3;data=...
msgId=ab12;part=3/3;data=...
~~~

Các dòng trên chỉ minh họa giao thức chunk, **không phải định dạng Spring Integration tự tạo**. Chia ở tầng ứng dụng cho phép quyết định gửi lại từng chunk và giới hạn kích thước mỗi UDP packet; tuy nhiên phải chịu trách nhiệm cho tính đúng đắn, bảo mật và giới hạn tài nguyên khi reassemble.

Không nên tự ghép một lượng vô hạn chunk vào memory để chờ gói cuối cùng. Kẻ gửi không đáng tin có thể lợi dụng giao thức ghép để làm đầy RAM.

## 14. Trường hợp cụ thể: kết nối nguồn file, HTTP, Kafka hoặc DB ra UDP

Giả sử ứng dụng lấy một JSON lớn từ HTTP hoặc Kafka rồi đưa thẳng qua outbound UDP adapter. Nếu không giới hạn kích thước **sau khi encode**, một message vốn hợp lệ ở HTTP/Kafka có thể vượt ngân sách UDP và làm mất dữ liệu.

~~~mermaid
flowchart LR
    SRC["File / SFTP / HTTP / JMS / AMQP / Kafka / DB"] --> T["Transform + validate schema"]
    T --> B["Serialize thành byte[]"]
    B --> L{"bytes <= MAX?"}
    L -->|Có| U["UDP outbound adapter"]
    L -->|Không| A["Báo lỗi / lưu bền / đổi transport / chia chunk"]
    U --> NET["UDP network"]
~~~

Khi nguồn là file hoặc database đọc theo lịch, **poller** phụ trách lấy message từ nguồn; **UDP outbound adapter** chịu trách nhiệm gửi datagram, không thay thế poller. Đối với inbound UDP, adapter phát `Message<byte[]>` vào `MessageChannel` để phần nghiệp vụ kiểm tra và chuyển tiếp sang các hệ thống khác.

**Quy tắc thực hành:** đặt `MAX_PAYLOAD_BYTES` tại ranh giới UDP, đo bằng bytes thực tế sau serialize. Đừng kỳ vọng MessageChannel, Kafka broker hay HTTP client tự điều chỉnh kích thước để phù hợp MTU của UDP.

## 15. Bảo mật và quan sát

Bên cạnh mất datagram, kích thước payload là rủi ro về tài nguyên và an ninh:

- **Giới hạn kích thước, số datagram/giây và số sender** theo chính sách; không cấp phát bộ nhớ tùy ý từ độ dài do client khai báo.
- **Không tin length prefix đơn lẻ**: nó là dữ liệu bên ngoài, không phải chữ ký xác thực. Nếu sender khai báo độ dài vô lý, phải từ chối và tránh tạo buffer theo giá trị ấy.
- **Validate schema và nguồn** trước khi xử lý sâu; source IP/port của UDP có thể bị giả mạo hoặc thay đổi do NAT.
- **Không ghi toàn bộ payload lớn** vào log. Ưu tiên log kích thước đã quan sát, mã lỗi, request/device ID đã kiểm tra, trạng thái adapter.
- **Kiểm soát giải nén và reassembly** nếu hệ thống nhận các bản tin nén/chia chunk; đặt max decompressed size và timeout.
- **Bảo vệ dữ liệu** bằng cơ chế xác thực/mã hóa thích hợp khi truyền qua mạng không đáng tin; UDP thuần không mã hóa.
- **Phân loại metric**: `udp_send_attempt_total`, `udp_receive_total`, `udp_size_rejected_total`, `udp_decode_error_total`, `udp_business_processed_total`, `udp_sequence_gap_total`.

Khi tạo dashboard, đo số byte **sender dự định gửi**, số byte **receiver thật sự thấy** và tỷ lệ hoàn thành nghiệp vụ. Không gắn nhãn high-cardinality (ví dụ mọi IP:port động) vào metric nếu có thể bùng nổ số chuỗi thời gian.

## 16. Bài thực hành củng cố

Thiết lập receiver tại UDP `12015`, `receiveBufferSize=2048`, `soReceiveBufferSize=262144`, hợp đồng payload `1..512 byte`. Ghi ít nhất ba metric: nhận gói, từ chối kích thước và xử lý thành công.

### Phần A — Kích thước và cấu hình

1. Gửi payload ASCII 511, 512, 513 và 2049 byte bằng PowerShell; ghi lại `observedBytes` và cách handler phân loại.
2. Dùng payload UTF-8 có dấu/emoji: kiểm tra vì sao `String.length()` không phải số byte thực gửi.
3. Thay `receiveBufferSize` từ 2048 xuống 256, gửi gói 500 byte và ghi nhận nguy cơ cắt ngắn.
4. Tăng riêng `soReceiveBufferSize` trong khi giữ `receiveBufferSize=256`; giải thích vì sao việc cắt ngắn vẫn có thể xảy ra.
5. Bật `lengthCheck` ở **cả sender và receiver**, tạo một thử nghiệm cắt ngắn có chủ đích rồi đối chiếu cơ chế phát hiện lỗi. Sau đó bật ở đúng một phía để quan sát lỗi không tương thích.

### Phần B — Tính toán và vận hành

1. Với MTU 1500, tính UDP payload tối đa tránh phân mảnh cho IPv4 và IPv6 không có header tùy chọn.
2. Tính lại ngân sách ứng dụng khi Spring Integration thêm 4 byte length prefix.
3. Giả sử sender phát 1.000 datagram/giây, mỗi datagram 512 byte payload: ước lượng dữ liệu payload **512.000 byte/giây**, chưa tính IP/UDP headers, link overhead hay packet loss.
4. Gửi gói có `seq` từ 1 đến 1.000, ghi số nhận và số thiếu; tăng tốc độ để xác định ngưỡng hệ thống bắt đầu mất gói.
5. Chọn giải pháp cho một JSON 20 KB cần giao hàng tin cậy: giảm schema, nén, chunk UDP hay chuyển sang transport khác? Nêu yêu cầu xác nhận và phục hồi khi receiver dừng.

**Câu hỏi tự đánh giá:**

- Vì sao payload 1.500 byte có thể phải phân mảnh trên đường có MTU 1.500?
- Khác biệt giữa `receive-buffer-size` và `so-receive-buffer-size` là gì?
- Vì sao length check chỉ phát hiện **một số trường hợp cắt ngắn**, không sửa được mất gói?
- Vì sao payload UTF-8 phải kiểm tra bằng `byte[].length`?
- Điều gì xảy ra nếu receiver dùng `check-length=true` nhưng sender gửi raw UTF-8?
- Khi nào nên từ chối payload lớn, khi nào nên dùng broker hoặc transport khác?
- Vì sao ACK kỹ thuật chưa đủ chứng minh dữ liệu đã được lưu bền trong database?

## 17. Tài liệu tham khảo

- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): length check, framing và ví dụ inbound/outbound.
- [Spring Integration Reference — IP Configuration Attributes](https://docs.spring.io/spring-integration/reference/ip/endpoint-reference.html): `receive-buffer-size`, `so-receive-buffer-size` và các thuộc tính socket.
- [RFC 8085 — UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085): hướng dẫn kích thước thông điệp, PMTU, phân mảnh và hạn chế UDP.
- [RFC 8900 — IP Fragmentation Considered Fragile](https://www.rfc-editor.org/rfc/rfc8900): vì sao phụ thuộc IP fragmentation gây rủi ro và các hướng tránh phân mảnh.

## Kết luận

**Datagram packet size và giới hạn payload** phải được thiết kế ở nhiều tầng: dữ liệu nghiệp vụ **sau encode**, overhead UDP/IP, **Path MTU**, buffer của `DatagramPacket`, socket receive buffer và tốc độ xử lý phía sau. Giới hạn lý thuyết của UDP không thể thay thế việc xác lập ngân sách byte cho từng hợp đồng.

Với Spring Integration, hãy **giới hạn ở sender**, bố trí **receive buffer phù hợp**, **validate `Message<byte[]>` tại receiver** và chỉ dùng `check-length` khi hai phía thống nhất framing. Những cơ chế đó giúp phát hiện và giảm lỗi kích thước nhưng không biến UDP thành truyền tin tin cậy. Khi sự kiện quá lớn hoặc bắt buộc nhận đủ, cần thay đổi kiến trúc giao hàng thông qua quản lý retry/ACK, broker hoặc transport phù hợp, giữ `MessageChannel` làm ranh giới tích hợp giữa các hệ thống.
