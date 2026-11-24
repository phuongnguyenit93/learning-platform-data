# Socket timeout và lifecycle của UDP adapter trong Spring Integration

## Mục tiêu học tập

Hoàn thành bài học này, bạn có thể:

- Giải thích **socket timeout** (`SO_TIMEOUT`) ảnh hưởng thế nào đến thao tác nhận datagram UDP, và vì sao hết thời gian chờ **không có nghĩa kết nối bị ngắt**.
- Phân biệt `so-timeout`, `ack-timeout`, `send-timeout` của `MessageChannel`, timeout nghiệp vụ và thời hạn shutdown.
- Cấu hình UDP inbound adapter bằng Java/Java DSL, kiểm tra `isRunning()`, `isListening()` và sự kiện `UdpServerListeningEvent`.
- Mô tả đúng vòng đời **khởi tạo → start → bind socket → nhận datagram → stop → đóng socket** và các điểm có thể phát sinh lỗi.
- Xây dựng kiểm thử có chủ đích: để socket rảnh qua một thời hạn chờ, gửi gói trở lại, dừng adapter, thử gửi trong thời gian dừng rồi khởi động lại.
- Lựa chọn cách điều phối startup, shutdown, retry và quan sát cho một luồng Spring Integration kết nối với hệ thống ngoài.

Bài thuộc chương **Adapter UDP** của module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối hệ thống ngoài vào Spring Integration bằng inbound/outbound adapter, gateway, poller và `MessageChannel`, sau đó xử lý hợp đồng message, lỗi và vòng đời khi tích hợp file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Với UDP, hai vấn đề cần chú ý là **thời gian chờ I/O** và **trạng thái thực sự của listener**, vì UDP không duy trì một kết nối TCP dài hạn.

## 1. Tình huống: collector không nhận datagram trong 30 giây

Một collector Spring Boot nghe tại UDP `12016`. Thiết bị gửi telemetry mỗi 5 giây:

~~~text
v=1;sensor=node-7;seq=105;tempC=26.5
~~~

Ban đầu hệ thống hoạt động. Sau đó thiết bị ngừng gửi trong 30 giây vì mất điện. Người vận hành thấy không còn message vào `MessageChannel`.

Có ba câu hỏi khác nhau:

1. **Socket còn mở và adapter còn nghe không?** Nếu có, receiver vẫn có thể nhận gói tiếp theo.
2. **Đã quá thời gian chờ của một lần `receive()` chưa?** Nếu cấu hình `SO_TIMEOUT=1000 ms`, lời gọi `receive()` có thể hết hạn sau khoảng 1 giây.
3. **Thiết bị có còn hoạt động không?** Không có gói mới chỉ là tín hiệu *thiếu dữ liệu*, không tự chứng minh thiết bị chết, mạng lỗi hay adapter dừng.

~~~mermaid
flowchart LR
    S["Thiết bị / UDP sender"] -->|"Datagram khi có dữ liệu"| U["UnicastReceivingChannelAdapter"]
    U -->|"Message<byte[]>"| C["MessageChannel"]
    C --> H["Handler nghiệp vụ"]
    T["SO_TIMEOUT: thời gian chờ<br/>một lần DatagramSocket.receive()"] -.-> U
    L["SmartLifecycle: start / stop"] -.-> U
~~~

**Kết luận quan trọng:** `SocketTimeoutException` do socket không có gói tới trong khoảng chờ là hiện tượng khác với việc một UDP connection bị ngắt. UDP không có connection handshake hoặc cơ chế báo “peer đã đóng kết nối” như TCP.

## 2. SO_TIMEOUT của DatagramSocket hoạt động ra sao?

Trong Java, một socket UDP nhận datagram qua `DatagramSocket.receive(DatagramPacket)`. Mặc định, nếu timeout bằng **0**, lời gọi nhận có thể **chờ vô thời hạn** cho tới khi có datagram hoặc xảy ra tác động/lỗi khác, chẳng hạn socket bị đóng.

Khi đặt `setSoTimeout(1000)`:

- Mỗi lời gọi `receive()` chỉ đợi datagram tối đa khoảng **1000 ms**.
- Nếu chưa có datagram, lời gọi ném **`SocketTimeoutException`**.
- Socket **vẫn hợp lệ** sau timeout; chương trình có thể gọi `receive()` lần nữa.
- Timeout **không tự tạo `Message` rỗng** để gửi tới Spring Integration.
- Timeout **không kích hoạt retry gửi lại** ở phía client và không làm UDP đáng tin cậy hơn.

Giá trị dương tính bằng **mili giây**; giá trị 0 biểu thị chờ vô hạn. Thời điểm timeout có thể lệch so với con số cấu hình do scheduling và tải hệ thống. Đây là thời gian chờ I/O, **không phải đồng hồ đo nhịp của thiết bị gửi**.

### 2.1. Ví dụ Java thuần để hiểu semantics

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.SocketTimeoutException;
import java.net.SocketException;
import java.io.IOException;

public class UdpReceiveTimeoutDemo {

    public static void main(String[] args) throws IOException {
        try (DatagramSocket socket = new DatagramSocket(12016)) {
            socket.setSoTimeout(1000); // 1 giây cho mỗi lần receive()

            byte[] buffer = new byte[1024];
            for (int attempt = 1; attempt <= 5; attempt++) {
                DatagramPacket packet =
                        new DatagramPacket(buffer, buffer.length);
                try {
                    socket.receive(packet);
                    System.out.println("Received bytes: " +
                            packet.getLength());
                } catch (SocketTimeoutException timeout) {
                    System.out.println("Idle receive timeout #" + attempt);
                    // Socket còn mở; vòng lặp vẫn tiếp tục.
                }
            }
        } // try-with-resources đóng DatagramSocket
    }
}
~~~

Chương trình này độc lập với Spring Integration để minh họa chính xác ý nghĩa của `SO_TIMEOUT`. **Không chạy đồng thời** với UDP inbound adapter đang bind cùng cổng `12016`; hai process có thể xung đột cổng. Trong ứng dụng Spring, adapter tự quản lý vòng nhận và vòng đời socket, không cần tự tạo vòng `for`/ `while` như đoạn minh họa này.

### 2.2. SO_TIMEOUT không phải tín hiệu health của thiết bị

Giả sử `SO_TIMEOUT=1000 ms` trong khi sensor chỉ gửi **mỗi 10 giây**: giữa hai lần gửi sẽ có nhiều lần chờ hết hạn. Đây là hành vi bình thường. Nếu lấy mỗi timeout làm lỗi, dashboard sẽ báo động sai liên tục.

Để phát hiện sensor im lặng, cần lưu **lastSeenAt** theo định danh sensor đã xác minh, so sánh với chu kỳ gửi dự kiến, thêm biên độ cho jitter và quy tắc network loss. Đó là **timeout nghiệp vụ** nằm ở tầng xử lý telemetry, không phải `SO_TIMEOUT` của socket.

## 3. Các loại timeout dễ bị nhầm

| Loại timeout | Cấu hình / cơ chế | Đang chờ điều gì? | Khi hết hạn |
|---|---|---|---|
| **UDP receive socket timeout** | `so-timeout`, `setSoTimeout(ms)` | Một lần `DatagramSocket.receive()` có gói đến | `SocketTimeoutException`; socket có thể tiếp tục nhận |
| **UDP ACK timeout** | `ack-timeout` khi `acknowledge=true` | ACK theo giao thức của Spring Integration UDP | Outbound có thể ném exception vì chưa nhận đủ ACK đúng hạn |
| **MessageChannel send timeout** | Ví dụ `send(message, timeout)` | Channel chấp nhận message khi có khả năng block | Có thể trả `false` hoặc lỗi theo implementation; không liên quan UDP ACK |
| **Gateway reply timeout** | Ví dụ `reply-timeout` của gateway thích hợp | Message trả lời ở tầng integration | Gateway hết hạn đợi reply theo contract |
| **Device inactivity timeout** | Chính sách `lastSeenAt` của ứng dụng | Có telemetry/heartbeat mới của từng thiết bị | Phát cảnh báo hoặc chuyển trạng thái sensor |
| **Shutdown/drain timeout** | Quy trình orchestration, executor, broker | Công việc đang xử lý kết thúc trước khi tắt process | Có thể dừng sau hạn; cần chính sách xử lý các message chưa hoàn tất |

### 3.1. Receive timeout và ACK timeout không thay thế nhau

Một UDP sender thường chỉ giao datagram cho tầng mạng. Nếu bật **application-level ACK** do Spring Integration hỗ trợ, sender cần các thông số như `ack-host`, `ack-port`, `ack-timeout` và receiver phải hiểu đúng framing ACK. Nếu ACK không đến kịp, outbound adapter có thể báo lỗi.

Ví dụ XML *minh họa riêng cho sender có ACK*:

~~~xml
<int-ip:udp-outbound-channel-adapter
    id="telemetryUdpSender"
    channel="toUdp"
    host="collector.example.test"
    port="12016"
    acknowledge="true"
    ack-host="sender.example.test"
    ack-port="12017"
    ack-timeout="3000"/>
~~~

Để dùng thực tế, thay hai host bằng địa chỉ mạng hợp lệ và cấu hình namespace `int-ip` đúng phiên bản; receiver phải hỗ trợ ACK của Spring Integration. **Không cấu hình ACK một phía** khi collector chỉ đọc UDP raw bytes.

Ba điều phải phân biệt:

- Hết `so-timeout` ở **receiver**: lần chờ `receive()` vừa kết thúc vì chưa có gói.
- Hết `ack-timeout` ở **sender**: chưa có ACK phù hợp trong khoảng đợi.
- Chưa có `ACK` **không chứng minh datagram bị mất**; receiver có thể đã nhận nhưng phản hồi thất lạc hoặc xử lý ACK chậm.

Với multicast, `min-acks-for-success` quy định số ACK tối thiểu mong đợi; nó không tự bảo đảm tất cả thành viên multicast đã nhận và xử lý nghiệp vụ.

### 3.2. Tại sao `so-timeout` trên outbound thường khác inbound?

Outbound UDP handler chủ yếu thực hiện **gửi**; với UDP thuần, nó không đợi một bản tin trả lời tương tự TCP request/reply. Tùy chọn socket timeout ở endpoint outbound được mô tả theo socket API, nhưng **không nên diễn giải thành hạn thời gian giao datagram thành công tại receiver**. Nếu cần một thời hạn phản hồi, phải thiết kế cơ chế ACK hoặc giao thức nghiệp vụ riêng, hoặc chọn transport khác.

## 4. Lifecycle của UDP inbound adapter

**`UnicastReceivingChannelAdapter`** là một endpoint do Spring quản lý. Nó có các chức năng lifecycle của Spring Integration, gồm **`start()`**, **`stop()`**, **`isRunning()`** và thuộc tính **`autoStartup`**. Ngoài ra, UDP inbound adapter có **`isListening()`** để phản ánh tình trạng đã bắt đầu lắng nghe thực tế.

~~~mermaid
stateDiagram-v2
    [*] --> Created: Khởi tạo bean
    Created --> Starting: Spring lifecycle / start()
    Starting --> Listening: Bind socket thành công
    Listening --> Listening: Datagram đến / receive timeout
    Listening --> Stopping: stop() / context shutdown
    Stopping --> Stopped: Dừng vòng nhận, giải phóng socket
    Stopped --> Starting: start() lại
~~~

Sơ đồ mô tả luồng mong đợi, không biểu thị mọi chuyển trạng thái khi gặp ngoại lệ. Nếu **không bind được port** hoặc socket lỗi, adapter có thể chưa đạt trạng thái listening và hệ thống cần quan sát lỗi khởi động.

| Giai đoạn | Những gì thường xảy ra | Điều cần kiểm tra |
|---|---|---|
| **Bean được tạo** | Spring dựng adapter và thiết lập output channel, cổng, socket options | Cấu hình có hợp lệ, channel có subscriber |
| **Start** | Lifecycle gọi start theo phase/autoStartup | Chưa suy ra đã bind socket thành công chỉ từ việc ApplicationContext khởi động |
| **Listening** | UDP socket được bind và vòng nhận hoạt động | `isListening()` hoặc `UdpServerListeningEvent` |
| **Nhận gói** | Adapter nhận datagram và phát `Message<byte[]>` | Byte payload, header nguồn, tốc độ nhận, lỗi xử lý |
| **Stop** | Vòng nhận kết thúc, socket không tiếp tục nhận cho endpoint | Datagram gửi trong lúc dừng có thể bị mất |
| **Restart** | Adapter khởi động/bind lại theo cấu hình | Cổng/interface vẫn khả dụng; readiness mới đạt |

**Không đồng nhất `isRunning()` và `isListening()`.** `isRunning()` nói lên trạng thái lifecycle, còn `isListening()` là tín hiệu chuyên biệt hữu ích để biết UDP listener đã bắt đầu hoạt động. Trong thời gian chuyển tiếp hoặc khi bind lỗi, hai trạng thái có thể khác nhau. Đối với readiness/khởi chạy client phụ thuộc UDP, ưu tiên **sự kiện listening** hoặc tín hiệu tương đương đã quan sát.

## 5. Cấu hình Java: SO_TIMEOUT và quản lý endpoint

### 5.1. Dependency

Trong Spring Boot với dependency management:

~~~xml
<!-- Bên trong <dependencies> của pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

### 5.2. Tạo inbound adapter dưới dạng bean

Ví dụ sau minh họa **Spring Integration 7.x**; tên package class inbound đã được tách sang `org.springframework.integration.ip.udp.inbound`. Với **Spring Integration 6.x**, dùng import `org.springframework.integration.ip.udp.UnicastReceivingChannelAdapter` tương ứng.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.ip.udp.inbound.UnicastReceivingChannelAdapter;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class UdpTimeoutConfiguration {

    public static final int PORT = 12016;

    @Bean("udpInput")
    public MessageChannel udpInput() {
        return new DirectChannel();
    }

    @Bean("udpReceiver")
    public UnicastReceivingChannelAdapter udpReceiver(
            @Qualifier("udpInput") MessageChannel input) {

        UnicastReceivingChannelAdapter adapter =
                new UnicastReceivingChannelAdapter(PORT);

        adapter.setOutputChannel(input);
        adapter.setSoTimeout(1000);         // Receive timeout: 1 giây
        adapter.setReceiveBufferSize(2048); // Buffer cho 1 datagram
        adapter.setAutoStartup(true);       // Để Spring tự start
        return adapter;
    }
}
~~~

`setSoTimeout(1000)` cấu hình thời gian chờ nhận ở socket. Khi thời gian chờ trôi qua mà không có gói, **adapter tiếp tục vòng nhận** trong điều kiện hoạt động bình thường. Ứng dụng **không cần tự bắt `SocketTimeoutException` ở service activator**, vì exception đó phát sinh trong lớp đọc socket khi chưa có message để dispatch.

`setReceiveBufferSize(2048)` là bộ đệm dùng cho một datagram; nó khác với `setSoReceiveBufferSize(...)`, là yêu cầu về bộ đệm nhận của **socket kernel**. Đặt kích thước theo payload tối đa và framing giữa hai hệ thống.

### 5.3. Handler xử lý message

~~~java
import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class UdpTelemetryReceiver {

    private static final Logger log =
            LoggerFactory.getLogger(UdpTelemetryReceiver.class);

    @ServiceActivator(inputChannel = "udpInput")
    public void receive(Message<byte[]> message) {
        byte[] payload = message.getPayload();
        if (payload.length == 0 || payload.length > 512) {
            log.warn("UDP payload size rejected: {}", payload.length);
            return;
        }

        // Ví dụ kiểm tra kích thước; production cần validate UTF-8/schema.
        String text = new String(payload, StandardCharsets.UTF_8);
        log.info("UDP telemetry received: {}", text);
    }
}
~~~

**Nếu không có datagram**, hàm `receive(...)` ở service activator **không được gọi**. Kể cả `setSoTimeout(1000)` dẫn đến nhiều lần socket receive timeout, hệ thống không tự tạo message giả. Chỉ có message thực nhận mới đi qua channel.

### 5.4. Cấu hình Java DSL tương đương

Nếu dùng Java DSL, thay *toàn bộ bean `udpReceiver`* ở mục 5.2 bằng một `IntegrationFlow` (giữ channel/handler). **Không đăng ký cả hai listener trên cùng một port**, tránh xung đột socket.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.dsl.Udp;

@Configuration
public class UdpTimeoutFlowConfig {

    @Bean
    public IntegrationFlow udpTimeoutFlow() {
        return IntegrationFlow.from(
                    Udp.inboundAdapter(12016)
                        .soTimeout(1000)
                        .receiveBufferSize(2048))
                .channel("udpInput")
                .get();
    }
}
~~~

Java DSL cấu hình `soTimeout` trên inbound adapter, không có nghĩa message sẽ tự được gửi đều đặn mỗi 1000 ms. Nếu muốn phát heartbeat theo lịch, dùng một flow khác có trigger phù hợp. **Poller** không phải cơ chế đọc gói UDP của adapter.

## 6. Quan sát listener đã sẵn sàng

### 6.1. `UdpServerListeningEvent`

Spring Integration phát **`UdpServerListeningEvent`** khi inbound UDP adapter đã khởi động và bắt đầu lắng nghe. Sự kiện này hữu ích hơn việc chờ mù một khoảng thời gian hoặc suy luận từ log Spring Boot “Started Application”.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.integration.ip.udp.UdpServerListeningEvent;
import org.springframework.stereotype.Component;

@Component
public class UdpListeningObserver {

    private static final Logger log =
            LoggerFactory.getLogger(UdpListeningObserver.class);

    @EventListener
    public void onUdpListening(UdpServerListeningEvent event) {
        log.info("UDP inbound listener ready on port={}", event.getPort());
    }
}
~~~

Sự kiện có `getPort()`. Nếu triển khai **nhiều** UDP listener, cần kiểm tra thêm nguồn/sender của event hoặc định danh adapter để tránh nhầm sự kiện của listener khác. **Không lấy sự kiện listening làm bằng chứng receiver đã nhận được datagram từ mạng bên ngoài**: firewall, DNS, NAT và đường mạng vẫn có thể chặn gói.

### 6.2. `isRunning()` so với `isListening()`

Khi thao tác trên bean adapter trực tiếp:

~~~java
// Ví dụ trong một component đã được inject bean udpReceiver:
boolean lifecycleActive = udpReceiver.isRunning();
boolean socketListening = udpReceiver.isListening();
~~~

Hai giá trị có mục đích riêng:

- `isRunning()`: Spring lifecycle cho biết endpoint đang ở trạng thái hoạt động.
- `isListening()`: receiver đã vào trạng thái nghe UDP, thường là tín hiệu phù hợp hơn cho readiness.
- **Số message đã nhận gần đây**: một metric *khác*, phản ánh lưu lượng và heartbeat nghiệp vụ, không nằm trong hai boolean trên.

Các tín hiệu này phải được đọc trong thời điểm phù hợp; trong lúc stop/start đang chuyển trạng thái, giá trị có thể thay đổi giữa hai lần kiểm tra.

### 6.3. Port 0 trong môi trường test

Với UDP unicast listener, có thể cấu hình **port `0`** để hệ điều hành chọn một cổng trống. Khi adapter thực sự listening, lấy port cụ thể từ `UdpServerListeningEvent.getPort()` hoặc `adapter.getPort()` theo API phiên bản đang dùng.

Đây là cách hữu ích cho integration test chạy song song vì tránh chọn sẵn một số port phổ biến. **Chỉ gửi datagram test sau khi nhận được sự kiện listening hoặc xác nhận trạng thái**; nếu gửi quá sớm, UDP không có hàng đợi mạng chờ ứng dụng mở socket.

## 7. Start, stop và restart có kiểm soát

Theo mặc định, Spring quản lý lifecycle của adapter cùng `ApplicationContext`. Việc gọi thủ công `start()`/`stop()` hữu ích trong test hoặc thao tác bảo trì **có kiểm soát**, nhưng không nên lạm dụng trong request handler thông thường.

Ví dụ component nhận trực tiếp bean adapter đã tạo ở mục 5.2:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.ip.udp.inbound.UnicastReceivingChannelAdapter;
import org.springframework.stereotype.Component;

@Component
public class UdpListenerControl {

    private final UnicastReceivingChannelAdapter receiver;

    public UdpListenerControl(
            @Qualifier("udpReceiver")
            UnicastReceivingChannelAdapter receiver) {
        this.receiver = receiver;
    }

    public boolean isReady() {
        return receiver.isRunning() && receiver.isListening();
    }

    public void pause() {
        receiver.stop();
    }

    public void resume() {
        receiver.start();
        // Đợi UdpServerListeningEvent trước khi báo đã thực sự sẵn sàng.
    }
}
~~~

**Cẩn trọng khi đặt tên “pause”:** `stop()` là dừng endpoint và tài nguyên nhận, **không tạo bộ đệm tạm** cho các datagram đến trong thời gian dừng. Tùy timing và OS, datagram gửi khi chưa có socket nghe có thể bị bỏ. Sau khi `start()`, những gói đã mất **không được replay tự động**.

Khi ứng dụng không cần manual control, có thể dùng `autoStartup` theo cấu hình và để Spring đóng endpoint khi context shutdown. Với nhiều endpoint phụ thuộc nhau, dùng lifecycle phase hoặc điều phối ứng dụng để khởi động consumer/service đúng trình tự; một event listening là tín hiệu chính xác để sender test bắt đầu gửi.

### 7.1. Các lỗi khi khởi động lại

- **Port đang bị chiếm:** một process khác vừa chiếm UDP port trong lúc listener dừng; bind lại có thể thất bại.
- **Network interface biến mất/thay đổi:** bind vào `local-address` cũ hoặc multicast group có thể không còn hợp lệ.
- **Sai thứ tự shutdown/startup:** service upstream gửi trước khi receiver ready, gây mất datagram.
- **External socket ownership:** nếu ứng dụng tự cung cấp `DatagramSocket` hoặc tùy biến sâu, cần hiểu rõ ai có trách nhiệm đóng/mở lại tài nguyên.
- **Thông điệp đang xử lý:** stop listener không đồng nghĩa mọi handler async ở phía sau đã xử lý xong và được lưu bền.

Không dùng `Thread.sleep(...)` trong bài test làm chứng minh listener đã start; event hoặc readiness predicate có giới hạn thời gian sẽ ổn định hơn.

## 8. Graceful shutdown: UDP có giới hạn gì?

Khi Spring Boot dừng vì deploy, scale-down hay SIGTERM, có thể cần:

1. **Ngừng tạo công việc mới** ở upstream nếu có cơ chế điều phối.
2. **Dừng tiếp nhận UDP mới** tại điểm thích hợp của quá trình shutdown.
3. **Cho phép công việc đã nhận** trong hàng đợi nội bộ hoặc broker hoàn thành trong một thời hạn.
4. **Đóng socket, executor và tài nguyên** theo lifecycle quản lý của Spring.
5. **Kiểm tra gói bị mất/trùng** và khôi phục theo hợp đồng nghiệp vụ khi instance mới hoạt động.

~~~mermaid
sequenceDiagram
    participant P as Sender
    participant L as UDP listener cũ
    participant Q as Message pipeline
    participant N as UDP listener mới

    P->>L: Datagram số 101
    L->>Q: Message 101
    Note over L: Bắt đầu shutdown
    L--xP: Stop listening
    P-->>L: Datagram 102 trong khoảng dừng
    Note over P,L: Datagram 102 có thể bị mất
    Note over N: Khởi động / bind / listening
    P->>N: Datagram 103
    N->>Q: Message 103
~~~

Đây là điểm giới hạn **của UDP**: không có session cho phép receiver thông báo backpressure và tự chuyển tiếp gói đang chờ sang instance khác. Một load balancer hỗ trợ UDP có thể phân phối gói tới instance khỏe mạnh, nhưng cần kiểm tra quy tắc session affinity, timeout, route và khả năng chuyển tiếp trong môi trường cụ thể.

Nếu nghiệp vụ yêu cầu không mất sự kiện trong rolling deployment, chỉ sửa `so-timeout` hoặc `terminationGracePeriodSeconds` **không đủ**. Phải có thiết kế lưu bền/ACK/retry/outbox hoặc thay transport thích hợp.

### 8.1. Đồng bộ vòng đời giữa các endpoint

Giả sử một luồng nhận UDP rồi ghi database:

~~~mermaid
flowchart LR
    S["UDP sender"] --> U["UDP inbound adapter"]
    U --> C["MessageChannel"]
    C --> V["Validate / Transform"]
    V --> DB["Database"]
~~~

Với `DirectChannel`, handler xử lý đồng bộ có thể giữ luồng đọc lâu nếu database chậm. Khi stop, có thể có message đang được xử lý. Nếu dùng `ExecutorChannel` hoặc queue, còn thêm công việc pending. Cần quy định rõ:

- Thành phần nào ngừng nhận message mới trước.
- Thời hạn chờ các handler đã nhận và chính sách khi quá hạn.
- Retry tại lớp nghiệp vụ có thể tạo bản ghi trùng hay không.
- Chỉ số nào chứng minh dữ liệu đã được commit, tách khỏi chỉ số datagram nhận được.

Cấu hình `SO_TIMEOUT` không kiểm soát thời gian chạy `ServiceActivator` hoặc thời gian commit database.

## 9. Thử nghiệm vòng đời và socket timeout

### 9.1. Gửi gói thử từ PowerShell

Dùng Spring Boot có `UdpTimeoutConfiguration` và `UdpTelemetryReceiver`. Mở PowerShell trên cùng máy:

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new()
try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes(
        "v=1;sensor=node-7;seq=105;tempC=26.5"
    )
    [void]$client.Send($bytes, $bytes.Length, "127.0.0.1", 12016)
}
finally {
    $client.Dispose()
}
~~~

Nếu listener đã ready, log handler dự kiến có nội dung nhận telemetry. Sender không nhận ACK theo mặc định và không được kết luận gói đã xử lý chỉ từ kết quả `Send`.

### 9.2. Thử “không có gói” qua nhiều khoảng SO_TIMEOUT

- Đặt `soTimeout=1000` ms và **không gửi** gì trong khoảng 5 giây.
- Kiểm tra `receiver.isRunning()` và `receiver.isListening()`; receiver vẫn có thể hoạt động bình thường.
- Xác nhận không xuất hiện 5 message giả trên `udpInput`. Timeout là thao tác I/O nội bộ.
- Sau đó gửi một datagram hợp lệ; handler phải tiếp tục có khả năng nhận gói **mà không cần restart adapter**.

Kết quả kỳ vọng ở điều kiện ổn định:

| Quan sát | Kỳ vọng | Vì sao |
|---|---|---|
| Không có datagram trong 5 giây | Không có message mới | Adapter chỉ phát khi thật sự nhận datagram |
| SO_TIMEOUT = 1000 ms | Không buộc phải restart | Timeout không đóng socket |
| Gửi sau 5 giây im lặng | Có thể nhận bình thường | Vòng nhận tiếp tục |
| Cảm biến không gửi theo lịch | Cần metric `lastSeenAt` riêng | SO_TIMEOUT không đo freshness nghiệp vụ |

### 9.3. Thử stop/start

Trong môi trường test hoặc qua một cơ chế bảo trì nội bộ được bảo vệ:

1. Chờ `UdpServerListeningEvent` hoặc `isListening()` trước khi gửi gói số 1.
2. Gọi `receiver.stop()`; quan sát listener không còn tiếp nhận gói.
3. Gửi datagram số 2 khi listener đang dừng. Không giả định datagram sẽ được giữ lại.
4. Gọi `receiver.start()`; **chờ listening thực tế** chứ không chỉ chờ lời gọi method trả về.
5. Gửi datagram số 3; xác minh handler nhận lại được gói mới.
6. Đối chiếu sequence: nếu gói số 2 bị thiếu, đây là kết quả có thể xảy ra khi receiver tạm dừng.

Vì UDP không bảo đảm giao hàng, bài test xác nhận **khả năng nhận sau restart**, không nên dùng kết quả của một lần gửi để chứng minh tính tin cậy tổng quát.

### 9.4. Thử lỗi bind port

Mở một process khác bind UDP `12016`, rồi thử khởi động adapter trên cổng đó. Tùy hệ điều hành và socket options, thao tác bind có thể thất bại với lỗi tương tự “Address already in use”.

Cách chẩn đoán:

- Kiểm tra port và local address của các process đang dùng UDP.
- Xác minh có vô tình tạo **hai inbound adapter** trong cùng Spring context trên một cổng hay không.
- Không thay đổi ngẫu nhiên `SO_TIMEOUT`; nó không giải quyết xung đột cổng.
- Kiểm tra log lỗi khởi động và sự kiện listening. Nếu không có tín hiệu ready, không gửi dữ liệu test rồi tự kết luận handler sai.

Khi cần chạy test song song, dùng port động `0` với listener unicast và lấy port thực tế từ event listening.

## 10. Lỗi, exception và error channel

| Tình huống | Nơi lỗi xảy ra | Cách quan sát/xử lý |
|---|---|---|
| Không có gói trước SO_TIMEOUT | Socket receive | Timeout bình thường; không đánh dấu xử lý message thất bại |
| Port không bind được | Startup/listener | Log lỗi socket/bind, kiểm tra process và readiness |
| Socket bị đóng trong lúc nhận | Listener lifecycle | Phân biệt stop chủ động với lỗi socket bất thường |
| Datagram bị cắt ngắn | Receive buffer/truyền tải | `check-length` khi hai phía tương thích; buffer đúng kích thước |
| Handler giải mã/validate lỗi | Message processing | Validate, error channel/exception policy, metric invalid |
| Handler DB/broker lỗi | Downstream | Retry có kiểm soát, idempotency, cơ chế lưu bền theo yêu cầu |
| Outbound chờ ACK quá hạn | UDP outbound ACK handling | Lỗi timeout ACK; phân biệt đã nhận hay chưa biết receiver xử lý |
| Không thấy message trong lúc shutdown | Listener đã stop | Theo dõi cửa sổ deploy và hành vi mất gói, thiết kế đảm bảo bổ sung |

Spring Integration UDP inbound endpoint hỗ trợ **`error-channel`** để xử lý lỗi ở downstream theo hợp đồng `ErrorMessage`/`MessagingException`. Điều này **không đồng nghĩa** mỗi lần `SO_TIMEOUT` bình thường ở socket đều phát một `ErrorMessage` đến channel đó.

Ví dụ hướng xử lý trong Spring Integration:

~~~text
UDP adapter -> udpInput -> parse -> validate -> service
                                      |
                                   lỗi xử lý
                                      v
                                 errorChannel
                                      |
                             classify / metric / log
~~~

Cần xác định rõ lỗi nào đi vào error channel và lỗi nào xảy ra **trước khi tạo message**. Gói bị firewall chặn hoặc mất trên đường truyền không thể đưa vào error channel của Spring vì ứng dụng chưa từng nhận chúng.

## 11. Quan sát và health check đúng mục đích

Một dashboard hữu ích nên dùng nhiều tín hiệu độc lập:

| Metric/Signal | Phản ánh |
|---|---|
| `udp_listener_running` | Trạng thái lifecycle của adapter |
| `udp_listener_listening` | Trạng thái sẵn sàng nhận ở socket UDP |
| `udp_receive_total` | Số datagram đến ứng dụng và được mapper/channel tiếp nhận |
| `udp_invalid_total` | Số payload bị từ chối vì định dạng, kích thước, version |
| `udp_handler_error_total` | Số lỗi xử lý downstream |
| `sensor_last_seen_seconds` hoặc `lastSeenAt` | Độ mới dữ liệu theo sensor |
| `udp_ack_timeout_total` | Số lần sender không nhận ACK đúng hạn nếu dùng ACK |
| `udp_sequence_gap_total` | Khoảng sequence bị thiếu theo từng nguồn nghiệp vụ |

**Phân biệt ba trạng thái vận hành:**

- **Liveness**: process còn sống và vòng xử lý chính không bị kẹt.
- **Readiness**: listener đã bind, listening, channel/handler thiết yếu đã sẵn sàng.
- **Freshness**: thiết bị gửi dữ liệu đủ mới theo kỳ vọng và quy tắc nghiệp vụ.

Một endpoint có thể *live + ready* nhưng dữ liệu sensor quá cũ; cũng có thể process live nhưng port UDP chưa bind được. Vì vậy health check chỉ dựa vào “Spring Boot đã khởi động” hoặc chỉ dựa vào datagram gần nhất sẽ gây kết luận sai.

## 12. Cấu hình vận hành với Docker/Kubernetes

Socket UDP trong container thường gắn với network namespace riêng. Khi đưa adapter lên môi trường container:

- **Expose đúng UDP port**, không dùng mapping TCP thay cho UDP. Kiểm tra Service/ingress/network policy hỗ trợ giao thức UDP.
- **Bind đúng địa chỉ interface**, đặc biệt khi cấu hình `local-address`. Không suy ra `127.0.0.1` trong container là IP của host.
- **Bảo đảm readiness** phản ánh listener đã listening, sau đó mới cho network route traffic đến instance theo cơ chế môi trường.
- **Có thời gian drain** cho các message đã nhận ở executor/queue/broker; không kỳ vọng `SO_TIMEOUT` sẽ tự drain.
- **Thiết kế dự phòng mất gói** trong rolling deployment. Các datagram gửi lúc không có receiver khả dụng có thể biến mất mà sender không được báo.
- **Tách timeout mạng và timeout nghiệp vụ**. Heartbeat thiết bị, UDP ACK và việc commit DB nên có chính sách và metric riêng.

Nếu cần giám sát thay đổi trạng thái của listener, nên sử dụng event lifecycle và metric có nhãn instance. Không thu thập quá nhiều nhãn IP:port động vì dễ tăng cardinality và gây quá tải hệ thống quan sát.

## 13. Bảo mật khi bật/tắt listener

Một API cho phép client tùy ý gọi `stop()`/`start()` trên UDP listener có thể trở thành đường gây gián đoạn dịch vụ. Trong production, chỉ cho phép điều khiển lifecycle qua quy trình vận hành có xác thực/phân quyền và audit phù hợp.

Khi tự xây cơ chế phản hồi UDP hoặc ACK, nhớ rằng địa chỉ nguồn UDP có thể bị giả mạo ở một số môi trường. Giới hạn mạng được phép gửi, tốc độ phản hồi và kích thước datagram để giảm nguy cơ UDP reflection/amplification. `SO_TIMEOUT` không phải biện pháp chống DDoS hay giới hạn tốc độ.

Vòng đời socket cũng liên quan đến việc không để lại listener trên port cũ khi thay đổi cấu hình. Nếu ứng dụng tự cấp `DatagramSocket`, cần thống nhất ownership và cleanup; với adapter Spring quản lý, để container/lifecycle xử lý tài nguyên theo contract.

## 14. Bài thực hành tổng hợp

Bạn có collector nhận datagram tại `12016`, sensor gửi mỗi **5 giây**, hệ thống cảnh báo khi không có telemetry **quá 20 giây**.

### Phần A — Phân biệt timeout

1. Cấu hình `soTimeout(1000)`; để socket idle 10 giây. Quan sát lifecycle và xác nhận không có message giả.
2. Gửi một datagram từ PowerShell sau khi chờ; giải thích vì sao adapter vẫn nhận được mà không cần restart.
3. Thêm `lastSeenAt` vào service xử lý và tạo kiểm tra theo lịch: cảnh báo khi `now - lastSeenAt > 20 giây`. Lý giải vì sao giá trị này khác `SO_TIMEOUT`.
4. Tắt sender 25 giây nhưng giữ receiver hoạt động. Xác minh freshness alert, đồng thời `isListening()` vẫn có thể là `true`.
5. Bật lại sender và đo thời gian trở lại trạng thái hoạt động.

### Phần B — Vòng đời và shutdown

1. Chạy receiver với `autoStartup=true`, quan sát `UdpServerListeningEvent` trước khi gửi gói đầu.
2. Gọi stop/start trong môi trường test; gửi sequence trước, trong và sau thời gian stop. Ghi nhận gói thiếu.
3. Cấu hình một inbound UDP listener dùng port 0, lấy port do OS cấp từ event và gửi datagram thử.
4. Cố ý tạo xung đột bind port; xác định thông báo lỗi và trạng thái readiness.
5. Mô phỏng database handler xử lý chậm, thảo luận cách drain in-flight message khi shutdown.
6. Viết chính sách khi rolling deploy: sender nên retry/ACK hay chuyển sang broker nếu không được phép mất sự kiện?

### Phần C — Timeout ACK

Giả sử outbound UDP có `ack-timeout=3000` ms. Receiver được thiết kế gửi ACK kỹ thuật sau khi nhận packet, nhưng nghiệp vụ phải mất 5 giây mới ghi DB.

- ACK đến sau 1 giây có nói rằng dữ liệu đã lưu thành công không?
- Nếu ACK bị mất còn record đã lưu, retry có tạo duplicate không?
- Nếu muốn ACK “đã commit”, contract phải thay đổi như thế nào?

**Câu hỏi tự đánh giá:**

1. `SO_TIMEOUT=0` có nghĩa gì với `DatagramSocket.receive()`?
2. Tại sao không có datagram 5 giây không chứng minh UDP adapter đã chết?
3. Tại sao `ack-timeout` và `so-timeout` cần hai metric khác nhau?
4. Khi nào `isListening()` hữu ích hơn `isRunning()`?
5. `UdpServerListeningEvent` giải quyết vấn đề timing nào trong integration test?
6. Trong cửa sổ giữa `stop()` và `start()`, ai chịu trách nhiệm gói bị mất?
7. Vì sao `MessageChannel` và poller không tự tạo retry cho datagram đã mất ở tầng mạng?
8. Nếu nhận dữ liệu từ SFTP bằng poller rồi gửi UDP outbound, lifecycle của poller liên quan thế nào tới lifecycle của UDP sender?

## 15. Tài liệu tham khảo

- [Spring Integration Reference — IP Configuration Attributes](https://docs.spring.io/spring-integration/reference/ip/endpoint-reference.html): mô tả `so-timeout` trên UDP inbound/outbound, `ack-timeout`, receive buffer và `error-channel`.
- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): Java config/Java DSL, `UdpServerListeningEvent`, `isListening()`, `getPort()`, ACK và vòng đời listener.
- [Spring Integration Javadoc — UnicastReceivingChannelAdapter](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/ip/udp/UnicastReceivingChannelAdapter.html): các method lifecycle và socket options của adapter.
- [Spring Integration Javadoc — UdpInboundChannelAdapterSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/ip/dsl/UdpInboundChannelAdapterSpec.html): phương thức DSL như `soTimeout(int)`.
- [Oracle Java DatagramSocket API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/DatagramSocket.html): semantics `setSoTimeout`, `receive` và `close`.

## Kết luận

**Socket timeout** của UDP inbound adapter là hạn chờ cho một lần đọc datagram, còn **lifecycle** quyết định khi nào endpoint được start, bind, listening, stop và đóng socket. Một lần `receive()` hết hạn **không có nghĩa socket hay thiết bị gửi đã ngắt kết nối**, và Spring Integration không phát message rỗng chỉ vì hết `SO_TIMEOUT`.

Với **SPRING_INTEGRATION_ADAPTERS**, hãy quản lý UDP adapter bằng lifecycle của Spring, dùng `UdpServerListeningEvent`/`isListening()` để quan sát readiness, dùng hợp đồng message/metric để đo freshness và phân biệt timeout nhận, timeout ACK, timeout nghiệp vụ. Khi luồng tích hợp cần bảo đảm giao hàng qua file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu, phải thiết kế chính sách ACK, retry, lưu bền và shutdown phù hợp; riêng `SO_TIMEOUT` không giải quyết mất datagram hay phục hồi sau restart.
