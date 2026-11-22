# STOMP broker relay và kết nối tới broker bên ngoài

Tài liệu này giải thích cách Spring Framework chuyển tiếp STOMP message tới một message broker chạy độc lập như RabbitMQ hoặc ActiveMQ. Đây là bước tiếp theo sau khi đã cấu hình WebSocket endpoint và STOMP controller: Spring vẫn nhận kết nối WebSocket và định tuyến message tới ứng dụng, còn broker chuyên dụng đảm nhiệm việc quản lý subscription, queue và phát message.

## 1. Vì sao cần broker bên ngoài?

Spring có một simple broker chạy trong bộ nhớ. Nó hữu ích khi học STOMP hoặc xây dựng ứng dụng nhỏ, nhưng chỉ hỗ trợ một phần giao thức: không hỗ trợ ACK, RECEIPT và một số lệnh STOMP khác; trạng thái subscription nằm trong tiến trình ứng dụng và simple broker không phù hợp cho clustering.

Khi cần khả năng messaging đầy đủ hơn, ứng dụng có thể kết nối tới một broker riêng. Những lựa chọn phổ biến gồm RabbitMQ có bật STOMP plugin và ActiveMQ có STOMP connector. Broker phải thực sự bật và mở cổng cho giao thức STOMP; cổng AMQP hay OpenWire của cùng sản phẩm không tự động là cổng STOMP.

Spring cung cấp **STOMP broker relay** để làm cầu nối giữa WebSocket/STOMP client và broker. Relay nhận message từ Spring, chuyển tiếp qua TCP tới broker, nhận message từ broker và chuyển chúng về các WebSocket session đã subscribe. Các controller, destination prefix và API gửi message của Spring vẫn được dùng trong ứng dụng.

## 2. Kiến trúc và đường đi của message

Trong cấu hình thường gặp, destination được chia thành hai nhóm:

- Destination bắt đầu bằng **/app** được định tuyến tới method **@MessageMapping** trong Spring controller.
- Destination bắt đầu bằng **/topic** hoặc **/queue** được chuyển tiếp tới external broker theo prefix đã đăng ký.

Luồng tổng quát:

~~~mermaid
flowchart LR
    C[Browser / STOMP client] <-->|WebSocket + STOMP| WS[Spring WebSocket endpoint]
    WS --> IN[clientInboundChannel]
    IN --> APP[@MessageMapping controllers]
    IN --> RELAY[STOMP broker relay]
    APP --> BC[brokerChannel]
    BC --> RELAY
    RELAY <-->|TCP + STOMP| B[External broker]
    B --> RELAY
    RELAY --> OUT[clientOutboundChannel]
    OUT --> WS
    WS --> C
~~~

Ví dụ client gửi frame tới **/app/orders.create**. Spring định tuyến message tới method **@MessageMapping("/orders.create")**. Controller xử lý nghiệp vụ, sau đó có thể trả kết quả hoặc gọi **SimpMessagingTemplate** để gửi tới **/topic/orders**. Message đi qua **brokerChannel**, relay chuyển nó tới broker và broker phát message cho những client đã subscribe destination tương ứng.

Nếu client subscribe **/topic/orders**, subscription được chuyển tiếp tới broker. Khi broker phát message, relay nhận message đó và Spring gửi về các WebSocket session phù hợp. Broker chịu trách nhiệm về semantics của queue/topic, routing và các tính năng messaging mà sản phẩm hỗ trợ.

## 3. Khác nhau giữa simple broker và broker relay

| Tiêu chí | Simple broker | STOMP broker relay |
| --- | --- | --- |
| Nơi giữ subscription | Bộ nhớ trong ứng dụng Spring | External broker |
| Phạm vi | Gắn với một tiến trình ứng dụng | Có thể dùng chung broker cho nhiều instance ứng dụng |
| STOMP ACK/RECEIPT | Không hỗ trợ đầy đủ | Phụ thuộc broker STOMP được kết nối |
| Queue, persistence, policy | Hạn chế | Do broker cung cấp và cấu hình |
| Vận hành | Ít thành phần, dễ bắt đầu | Cần vận hành broker, network, credentials và giới hạn kết nối |

Broker relay không biến mọi broker thành một hệ thống giống nhau. STOMP quy định frame và command, nhưng ý nghĩa destination, queue, persistence, ACK mode, quyền truy cập và policy có thể khác nhau giữa RabbitMQ, ActiveMQ và các sản phẩm khác. Luôn kiểm tra tài liệu của broker đang sử dụng.

## 4. Hai loại kết nối TCP mà relay quản lý

Một điểm quan trọng là relay không dùng một kết nối TCP duy nhất cho tất cả hoạt động.

**Kết nối client:** Spring tạo một kết nối TCP riêng tới broker cho mỗi WebSocket client đã kết nối. Kết nối đó mang các frame STOMP của client tương ứng, bao gồm SUBSCRIBE, SEND, ACK và DISCONNECT. Với N WebSocket session đang hoạt động, thường sẽ có khoảng N kết nối TCP client tới broker.

**Kết nối system:** Spring giữ một kết nối TCP dùng chung để gửi message phát sinh từ phía ứng dụng, tức message không gắn với một client session cụ thể. Ví dụ, service gọi **SimpMessagingTemplate.convertAndSend(...)** hoặc một HTTP controller phát thông báo tới topic. Kết nối system mặc định phục vụ việc gửi message từ ứng dụng; nó không phải một kết nối nhận message thay cho các client subscription.

Vì vậy, nếu có 500 WebSocket session trên một instance Spring, relay thường cần khoảng 501 kết nối broker: 500 kết nối client và một kết nối system. Nếu chạy nhiều instance Spring, mỗi instance có các kết nối client riêng cho session của nó và một system connection riêng.

Spring cấu hình hai nhóm credentials riêng:

- **clientLogin / clientPasscode**: thông tin xác thực mà relay dùng cho mọi TCP connection được tạo thay mặt các WebSocket client.
- **systemLogin / systemPasscode**: thông tin xác thực cho system connection dùng để gửi message từ ứng dụng.

Relay đặt login và passcode đã cấu hình vào mọi CONNECT frame gửi tới broker thay mặt client. Header login/passcode do trình duyệt gửi lên bị bỏ qua. Vì thế, tất cả broker connection thay mặt client thường dùng chung một broker identity. Hãy xác thực người dùng ở HTTP/WebSocket handshake bằng Spring Security, để Spring gắn Principal vào session; sau đó kiểm tra quyền truy cập destination và hành động ở tầng Spring. Không coi clientLogin là danh tính riêng của từng người dùng cuối.

## 5. Cấu hình Spring bằng Java

Ví dụ dưới đây dùng Spring Framework 6.2 hoặc 7.0 với Java configuration. Đổi host, port, virtual host và credentials theo broker của môi trường.

~~~java
package com.example.messaging;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Value("${messaging.stomp.relay.host}")
    private String relayHost;

    @Value("${messaging.stomp.relay.port:61613}")
    private int relayPort;

    @Value("${messaging.stomp.relay.virtual-host:/}")
    private String virtualHost;

    @Value("${messaging.stomp.relay.client-login}")
    private String clientLogin;

    @Value("${messaging.stomp.relay.client-passcode}")
    private String clientPasscode;

    @Value("${messaging.stomp.relay.system-login}")
    private String systemLogin;

    @Value("${messaging.stomp.relay.system-passcode}")
    private String systemPasscode;

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");

        registry.enableStompBrokerRelay("/topic", "/queue")
                .setRelayHost(relayHost)
                .setRelayPort(relayPort)
                .setVirtualHost(virtualHost)
                .setClientLogin(clientLogin)
                .setClientPasscode(clientPasscode)
                .setSystemLogin(systemLogin)
                .setSystemPasscode(systemPasscode)
                .setSystemHeartbeatSendInterval(10_000)
                .setSystemHeartbeatReceiveInterval(10_000);
    }
}
~~~

**registerStompEndpoints** đăng ký endpoint WebSocket mà client sẽ kết nối, ví dụ **/ws**. **setApplicationDestinationPrefixes("/app")** dành destination cho controller. **enableStompBrokerRelay("/topic", "/queue")** chuyển các destination có hai prefix đó tới external broker. **setRelayHost** và **setRelayPort** là địa chỉ TCP của STOMP listener trên broker.

**setVirtualHost** thiết lập header **host** trong STOMP CONNECT frame. Với RabbitMQ, header này chọn virtual host của broker. Nó có thể khác hostname/IP dùng để mở TCP connection, ví dụ khi dùng dịch vụ broker trên cloud hoặc proxy.

Hai heartbeat interval trong ví dụ áp dụng cho system connection. Đơn vị là milliseconds. Spring mặc định dùng khoảng 10 giây cho gửi và nhận heartbeat trên kết nối system; có thể giữ mặc định nếu không cần tùy chỉnh.

### 5.1. Đưa cấu hình vào application.yml

Không ghi mật khẩu thật vào source code hoặc commit file cấu hình chứa secret. Ví dụ dùng biến môi trường:

~~~yaml
messaging:
  stomp:
    relay:
      host: ${STOMP_RELAY_HOST:localhost}
      port: ${STOMP_RELAY_PORT:61613}
      virtual-host: ${STOMP_RELAY_VHOST:/}
      client-login: ${STOMP_RELAY_CLIENT_LOGIN}
      client-passcode: ${STOMP_RELAY_CLIENT_PASSCODE}
      system-login: ${STOMP_RELAY_SYSTEM_LOGIN}
      system-passcode: ${STOMP_RELAY_SYSTEM_PASSCODE}
~~~

Cấp các biến môi trường từ secret manager hoặc cấu hình runtime của nền tảng triển khai. Dùng tài khoản riêng cho client relay và system connection để có thể cấp quyền broker theo mục đích. Trong production, chỉ cấp quyền cần thiết trên virtual host và destination mà ứng dụng sử dụng.

### 5.2. Dependency cho TCP relay

Ngoài module WebSocket của Spring, tài liệu Spring Framework yêu cầu các dependency quản lý TCP connection cho broker relay:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-websocket</artifactId>
</dependency>

<dependency>
    <groupId>io.projectreactor.netty</groupId>
    <artifactId>reactor-netty</artifactId>
</dependency>

<dependency>
    <groupId>io.netty</groupId>
    <artifactId>netty-all</artifactId>
</dependency>
~~~

Dùng dependency management/BOM tương thích với phiên bản Spring Boot hoặc Spring Framework của dự án để chọn version Reactor Netty và Netty. Nếu ứng dụng dùng Spring Framework trực tiếp, hãy kiểm tra dependency tree để bảo đảm có các thư viện TCP mà broker relay cần. Spring mặc định dùng Reactor Netty TCP client; có thể cung cấp TCP client tùy chỉnh qua **setTcpClient(...)** khi cần cấu hình nâng cao như TLS hoặc cách chọn địa chỉ broker.

## 6. Ví dụ kết nối RabbitMQ

RabbitMQ hỗ trợ STOMP thông qua plugin **rabbitmq_stomp**. Bật plugin trên node RabbitMQ:

~~~bash
rabbitmq-plugins enable rabbitmq_stomp
~~~

Nếu không đổi cấu hình listener, STOMP adapter mặc định lắng nghe TCP port **61613**. Cổng này là cổng STOMP; cổng AMQP mặc định 5672 không dùng thay thế được.

RabbitMQ có virtual host mặc định là **/**. Ví dụ nếu muốn tạo virtual host riêng tên **/messaging** và hai tài khoản relay:

~~~bash
rabbitmqctl add_vhost /messaging
rabbitmqctl add_user stomp-clients REPLACE_WITH_CLIENT_SECRET
rabbitmqctl add_user stomp-system REPLACE_WITH_SYSTEM_SECRET
rabbitmqctl set_permissions -p /messaging stomp-clients ".*" ".*" ".*"
rabbitmqctl set_permissions -p /messaging stomp-system ".*" ".*" ".*"
~~~

Các lệnh permission trên cấp quyền configure, write và read rộng trong virtual host để minh họa kết nối. Khi triển khai thật, giới hạn các biểu thức quyền theo exchange, queue và routing pattern mà ứng dụng cần. Đặt **STOMP_RELAY_VHOST=/messaging** và hai bộ credentials tương ứng trong môi trường chạy Spring.

Không dùng tài khoản **guest/guest** cho kết nối từ xa trong production. RabbitMQ mặc định chỉ cho user guest kết nối từ localhost; hãy tạo user riêng với mật khẩu sinh ngẫu nhiên và quyền tối thiểu. Bảo đảm firewall chỉ cho phép Spring application host truy cập STOMP listener.

### 6.1. Destination semantics của RabbitMQ

RabbitMQ STOMP adapter hỗ trợ nhiều dạng destination:

- **/topic/name**: publish/subscribe. Message gửi tới topic được định tuyến tới các subscriber phù hợp. Nếu không có subscriber, message thường bị loại bỏ, trừ khi ứng dụng cấu hình durable subscription.
- **/queue/name**: queue chia sẻ. Mỗi message được giao cho tối đa một subscriber đang tiêu thụ queue; message có thể được giữ lại khi chưa có subscriber.
- **/amq/queue/name**: truy cập queue đã được tạo bên ngoài STOMP adapter. SUBSCRIBE sẽ lỗi nếu queue chưa tồn tại.
- **/exchange/name/routing-key**: gửi tới exchange và routing key hoặc subscribe theo binding pattern.

Durable topic subscription của RabbitMQ cần cấu hình header theo tài liệu broker, ví dụ SUBSCRIBE với id, durable:true và auto-delete:false. Chỉ thêm tiền tố **/topic** không tự động làm message được lưu bền vững. Cần thiết kế queue, exchange, persistence và acknowledgement theo yêu cầu giao nhận thực tế.

## 7. Gửi message từ Spring application

Controller vẫn dùng **@MessageMapping** để nhận request của client. Service hoặc controller có thể gửi message tới broker bằng **SimpMessagingTemplate**:

~~~java
package com.example.messaging;

import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderNotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishOrderCreated(OrderCreatedEvent event) {
        messagingTemplate.convertAndSend("/topic/orders", event);
    }
}
~~~

Lệnh **convertAndSend** đưa message vào broker channel của Spring. Vì message không gắn với WebSocket session cụ thể, relay gửi nó qua shared system connection. Broker sau đó phát message tới các subscription khớp với **/topic/orders**.

Nếu muốn gửi cho một người dùng, có thể dùng user destination, chẳng hạn **/user/queue/notifications** cùng với **convertAndSendToUser(...)**. Trong môi trường nhiều instance Spring, cần cấu hình cơ chế broadcast user registry/destination phù hợp để node này có thể tìm session của người dùng đang kết nối ở node khác.

## 8. Broker availability và khôi phục kết nối

External broker có thể restart, mất mạng hoặc từ chối kết nối. Spring broker relay tự thử kết nối lại shared system connection khi broker tạm thời không khả dụng; mặc định các lần thử lại diễn ra mỗi 5 giây. Khi trạng thái system connection thay đổi, Spring phát **BrokerAvailabilityEvent**.

Ứng dụng có thể lắng nghe event này:

~~~java
package com.example.messaging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;
import org.springframework.stereotype.Component;

@Component
public class BrokerAvailabilityListener {

    private static final Logger log =
            LoggerFactory.getLogger(BrokerAvailabilityListener.class);

    @EventListener
    public void onBrokerAvailability(BrokerAvailabilityEvent event) {
        if (event.isBrokerAvailable()) {
            log.info("STOMP broker system connection is available");
        } else {
            log.warn("STOMP broker system connection is unavailable");
        }
    }
}
~~~

Event này phản ánh trạng thái shared system connection. Nó hữu ích cho service gửi message chủ động qua **SimpMessagingTemplate**, nhưng không phải bằng chứng rằng mọi client TCP connection đều đang hoạt động. Khi gửi message, ứng dụng vẫn cần xử lý **MessageDeliveryException** trong trường hợp broker vừa mất kết nối.

Client TCP connection không được Spring tự động khôi phục giống system connection. Client cần có reconnect strategy và subscribe lại sau khi kết nối thành công. Ví dụ với thư viện **@stomp/stompjs** trên trình duyệt:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "ws://localhost:8080/ws",
    reconnectDelay: 5000,
    heartbeatIncoming: 10000,
    heartbeatOutgoing: 10000,

    onConnect: () => {
        // Đăng ký lại subscription sau mỗi lần kết nối thành công.
        client.subscribe("/topic/orders", (frame) => {
            console.log("Order event:", frame.body);
        });
    },

    onStompError: (frame) => {
        console.error("STOMP broker error:", frame.headers["message"]);
    }
});

client.activate();
~~~

Ví dụ trên dùng endpoint WebSocket thuần **/ws**. Nếu server đăng ký SockJS endpoint, cấu hình client bằng SockJS transport tương ứng. Không gửi broker username/password từ trình duyệt: relay sẽ thay thế login/passcode bằng credentials phía server đã cấu hình.

## 9. Heartbeat và kiểm tra kết nối

STOMP heartbeat giúp hai phía phát hiện connection im lặng hoặc mất mạng. Heartbeat được thương lượng qua header CONNECT/CONNECTED của STOMP. Nếu hai phía thống nhất khoảng thời gian gửi/nhận, chúng sẽ gửi heartbeat khi không có frame dữ liệu khác trong khoảng đó.

Spring broker relay hỗ trợ heartbeat trên system connection; mặc định khoảng gửi và nhận là 10 giây. Client cũng nên cấu hình heartbeat phù hợp với broker và proxy/network timeout. Không nên đặt timeout của load balancer thấp hơn chu kỳ heartbeat/idle timeout mà ứng dụng kỳ vọng.

Heartbeat không thay thế reconnect logic. Khi kết nối bị đóng, trình duyệt cần kết nối lại, đợi STOMP CONNECTED, sau đó tạo lại subscription. Với message quan trọng, ứng dụng cần xác định chính sách xử lý trùng, retry, ACK và lưu bền vững ở broker; heartbeat chỉ giúp nhận ra kết nối có vấn đề.

## 10. Giám sát số lượng kết nối và tải

Broker relay giữ một TCP connection cho mỗi WebSocket client cộng thêm một system connection cho mỗi Spring application instance. Khi ước lượng capacity, cần tính số session đồng thời, số instance, connection limit của broker, file descriptor, memory, heartbeat traffic và tốc độ message.

Spring cung cấp bean **WebSocketMessageBrokerStats** để tổng hợp số liệu. Bean này mặc định ghi log ở mức INFO mỗi 30 phút và có thể export qua JMX. Trong phần STOMP Broker Relay, chỉ số TCP Connections thường xấp xỉ số WebSocket session hiện tại cộng một system connection. Nếu số liệu thấp hơn hoặc cao hơn bất thường, kiểm tra session lifecycle, broker chủ động đóng connection, heartbeat và transport error.

Ở phía broker, theo dõi số connection, queue depth, consumer, message rate, disk/memory alarm và log xác thực. Đừng chỉ theo dõi trạng thái Spring application: broker có thể vẫn chạy nhưng từ chối connection do hết giới hạn, sai credentials hoặc thiếu quyền trên virtual host.

## 11. Bảo mật khi kết nối broker từ xa

- Đặt broker trong network riêng và chỉ cho phép các application host cần thiết truy cập STOMP listener.
- Dùng credentials riêng cho client relay và system connection; không dùng guest/guest hoặc secret cố định trong repository.
- Cấp quyền tối thiểu trên virtual host và destination. Nếu client relay có quyền quá rộng, mọi WebSocket client được relay dùng cùng broker identity có thể có phạm vi thao tác rộng tương tự nếu Spring không chặn.
- Xác thực WebSocket handshake bằng cơ chế HTTP/Spring Security và dùng Principal gắn với session để kiểm tra quyền ở tầng ứng dụng.
- Không tin username, user-id hay role do client tự gửi trong STOMP header. Nếu cần dùng token, xác thực token ở handshake hoặc interceptor và tự thiết lập Principal đáng tin cậy.
- Dùng TLS cho kết nối Spring-to-broker qua network không tin cậy. Broker phải bật TLS listener; phía Spring cần TCP client được cấu hình TLS và truyền vào **setTcpClient(...)**. Chỉ thay port không tự bật TLS.
- Không đưa credentials hoặc payload nhạy cảm vào log. Giới hạn kích thước frame và kiểm soát destination client được phép SEND/SUBSCRIBE.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Spring khởi động nhưng broker không kết nối | Sai host/port, broker chưa bật STOMP listener, firewall chặn TCP | Kiểm tra listener và thử kết nối TCP từ chính máy/container chạy Spring |
| Connection bị từ chối | Đang dùng cổng AMQP thay cho STOMP hoặc plugin STOMP chưa bật | Với RabbitMQ, bật rabbitmq_stomp và kiểm tra listener 61613 |
| Authentication failed | Sai client/system credentials, user chưa tồn tại hoặc bị khóa | Kiểm tra log broker và từng tài khoản relay |
| Access refused khi CONNECT | Virtual host không tồn tại hoặc user không có quyền truy cập | Kiểm tra **setVirtualHost**, virtual host và permission |
| Client CONNECTED nhưng không nhận message | Subscribe sai prefix, broker destination không đúng hoặc topic không có subscriber | Kiểm tra destination frame và broker subscription/queue |
| Service gửi message thất bại sau khi broker restart | System connection đang unavailable | Lắng nghe BrokerAvailabilityEvent và xử lý MessageDeliveryException |
| Client bị disconnect khi broker restart | Client-side TCP connection đã mất | Cấu hình reconnect delay và tạo lại subscription sau onConnect |
| Broker có quá nhiều connection | Mỗi WebSocket session tạo một TCP connection; có thể có session cũ chưa đóng | So sánh WebSocketMessageBrokerStats với connection count của broker |

Một lưu ý thường gặp với RabbitMQ: user **guest** mặc định chỉ được phép kết nối từ localhost. Spring chạy trong container hoặc máy chủ khác có thể bị từ chối dù mật khẩu guest đúng. Tạo user riêng cho relay là cách xử lý phù hợp.

## 13. Kiểm thử tích hợp

Một bài kiểm thử tích hợp nên chạy Spring application cùng một broker thật hoặc container broker có bật STOMP plugin. Các trường hợp nên kiểm tra:

1. Client kết nối endpoint WebSocket và nhận STOMP CONNECTED.
2. Client subscribe **/topic/orders**, sau đó service gọi **SimpMessagingTemplate.convertAndSend**; client nhận đúng payload.
3. Client SEND tới **/app/orders.create**; controller xử lý và publish event tới broker destination.
4. Hai client subscribe cùng một topic đều nhận bản sao message publish tới topic.
5. Hai client subscribe cùng một queue được broker phân phối message theo semantics queue, không giả định cả hai đều nhận cùng một message.
6. Sai credentials hoặc virtual host làm connection thất bại; log broker chỉ ra nguyên nhân.
7. Restart broker; Spring phát BrokerAvailabilityEvent, system connection tự kết nối lại, client thực hiện reconnect và subscribe lại.
8. Kiểm tra ACK/RECEIPT, durable subscription hoặc persistence theo tính năng cụ thể của broker được chọn.

Dùng broker thật trong integration test giúp phát hiện những khác biệt mà mock hoặc simple broker không thể mô phỏng, đặc biệt là authentication, virtual host, destination mapping, ACK mode và reconnect.

## 14. Checklist triển khai

- Broker đã cài đặt và bật STOMP protocol listener.
- Spring relay trỏ đúng hostname và STOMP port có thể truy cập từ runtime.
- Prefix **/app**, **/topic**, **/queue** được phân chia đúng mục đích.
- Client credentials và system credentials tồn tại, có quyền trên đúng virtual host.
- Virtual host trong STOMP CONNECT khớp cấu hình broker.
- HTTP/WebSocket authentication và authorization được bật; client không tự quyết định broker credentials.
- Heartbeat, reconnect và resubscribe được cấu hình cho client.
- Ứng dụng xử lý BrokerAvailabilityEvent và MessageDeliveryException.
- Broker connection limit, queue policy, persistence và TLS phù hợp tải và yêu cầu độ tin cậy.
- Metrics của Spring và broker được theo dõi cùng nhau.

## 15. Tài liệu tham khảo

- [Spring Framework — External Broker](https://docs.spring.io/spring/reference/6.2/web/websocket/stomp/handle-broker-relay.html): cấu hình broker relay và dependency TCP.
- [Spring Framework — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html): system/client connection, credentials, heartbeat, reconnect và virtual host.
- [Spring Framework — Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html): BrokerAvailabilityEvent và lifecycle event.
- [Spring Framework — Monitoring](https://docs.spring.io/spring/reference/6.2/web/websocket/stomp/stats.html): WebSocketMessageBrokerStats và số lượng TCP connection của relay.
- [RabbitMQ — STOMP Plugin](https://www.rabbitmq.com/docs/stomp): bật plugin, listener, port, TLS, destination, ACK và durable subscription.
- [RabbitMQ — Access Control](https://www.rabbitmq.com/docs/access-control): user, virtual host, authentication và permission.
