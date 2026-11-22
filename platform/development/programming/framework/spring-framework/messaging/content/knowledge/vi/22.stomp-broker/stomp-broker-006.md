# Virtual host, TLS và cấu hình kết nối TCP tới STOMP broker trong Spring Framework

## Mục tiêu và phạm vi

Khi ứng dụng Spring dùng STOMP broker relay, Spring đóng vai trò cầu nối giữa các WebSocket/STOMP client và một message broker bên ngoài như RabbitMQ hoặc ActiveMQ. Relay chuyển các STOMP frame qua kết nối TCP tới broker, rồi chuyển message broker gửi về các client đang subscribe.

Có ba cấu hình dễ bị nhầm lẫn nhưng giải quyết ba việc khác nhau:

- **TCP host và port** xác định địa chỉ mạng mà tiến trình Spring kết nối đến.
- **Virtual host** là giá trị header **host** trong STOMP frame **CONNECT**, dùng để chọn không gian tài nguyên hoặc virtual host ở broker.
- **TLS** mã hóa và xác thực peer trên kết nối TCP giữa ứng dụng Spring và broker.

Ví dụ, ứng dụng có thể mở TCP/TLS đến **rabbitmq.internal:61614**, đồng thời gửi STOMP CONNECT header **host: /orders** để chọn RabbitMQ virtual host tên **/orders**. Tên DNS, port và virtual host không nhất thiết giống nhau.

Phần này tập trung vào kết nối từ **Spring broker relay đến broker bằng TCP**. Kết nối từ trình duyệt đến ứng dụng Spring qua WebSocket hoặc **wss://** là một chặng riêng, có cấu hình TLS riêng.

## 1. STOMP broker relay và luồng kết nối

### 1.1. Simple broker và broker relay

Spring có thể bật simple broker tích hợp bằng **enableSimpleBroker(...)**. Đây là broker đơn giản chạy trong ứng dụng, phù hợp với nhu cầu cơ bản nhưng không cung cấp đầy đủ tính năng của một broker độc lập.

Khi cần broker chuyên dụng, có thể dùng **enableStompBrokerRelay(...)**. Relay chuyển các frame đến một broker bên ngoài qua TCP. Broker bên ngoài quản lý subscription, queue/topic và việc phân phối message theo khả năng của chính nó.

### 1.2. Mô hình kết nối

Một broker relay duy trì:

1. Một kết nối TCP **system** dùng cho message phát sinh từ mã phía server, chẳng hạn service hoặc REST controller gửi qua **SimpMessagingTemplate**. Kết nối này không phải kết nối nhận message cho các subscription của WebSocket client.
2. Một kết nối TCP riêng cho mỗi WebSocket client đang kết nối. Các frame STOMP của client được relay qua kết nối tương ứng.

Vì vậy, với một instance ứng dụng có N WebSocket client đang kết nối, broker thường thấy N kết nối client cộng thêm một kết nối system dùng chung. Mỗi instance ứng dụng được triển khai thêm cũng có kết nối system riêng.

~~~mermaid
flowchart LR
    C1[WebSocket client 1] -->|STOMP frames| S[Spring application]
    C2[WebSocket client 2] -->|STOMP frames| S
    S -->|TCP connection per client| B[External STOMP broker]
    S -->|Shared system TCP connection| B
    B -->|Messages for subscriptions| S
    S -->|WebSocket frames| C1
    S -->|WebSocket frames| C2
~~~

Relay vừa nhận frame từ client để gửi tới broker, vừa nhận message từ broker để chuyển về đúng WebSocket session. TCP host/port là địa chỉ mạng của broker; destination như **/topic/orders** hay **/queue/orders** là địa chỉ message bên trong STOMP.

## 2. Phân biệt TCP endpoint và virtual host

### 2.1. TCP host và port

**TCP host** là tên DNS hoặc IP mà ứng dụng Spring có thể phân giải và truy cập. **TCP port** là port broker mở cho STOMP qua TCP. Port phải là STOMP listener, không phải port HTTP management, AMQP hoặc cổng WebSocket của ứng dụng Spring.

Ví dụ với cấu hình RabbitMQ phổ biến:

| Kiểu listener STOMP | Port ví dụ | Ý nghĩa |
|---|---:|---|
| TCP không mã hóa | 61613 | STOMP qua TCP thuần |
| TLS | 61614 | STOMP qua TCP được mã hóa TLS |

Port thực tế phụ thuộc broker và cấu hình triển khai. Không mặc định mọi broker đều dùng các port này.

### 2.2. Virtual host trong STOMP

Trong STOMP 1.1, frame **CONNECT** có header **host** để chỉ định virtual host mà client muốn sử dụng. Spring cung cấp **setVirtualHost(String)** trên **StompBrokerRelayRegistration** để đặt giá trị header đó.

Ví dụ:

~~~java
relay.setVirtualHost("/orders");
~~~

Giá trị này được gửi trong STOMP CONNECT header:

~~~text
CONNECT
accept-version:1.2
host:/orders
login:service-user
passcode:...
heart-beat:10000,10000

^@
~~~

Ví dụ frame trên chỉ minh họa các header; giá trị passcode không nên ghi vào log hoặc tài liệu thật.

Với RabbitMQ, header **host** chọn RabbitMQ virtual host. Virtual host phải tồn tại trên broker và tài khoản dùng để kết nối phải có quyền phù hợp trên virtual host đó. RabbitMQ thường dùng **/** làm virtual host mặc định nếu STOMP CONNECT không chỉ định host và broker được cấu hình theo mặc định đó.

### 2.3. Ba giá trị cần cấu hình độc lập

| Thuộc tính | Ví dụ | Dùng ở đâu |
|---|---|---|
| TCP host | rabbitmq.internal | DNS/IP cho socket TCP |
| TCP port | 61614 | Port STOMP TLS listener |
| STOMP virtual host | /orders | Header host của STOMP CONNECT |
| TLS server name/SNI | rabbitmq.internal | Tên server dùng khi kiểm tra chứng thư TLS |

Không đặt virtual host vào **setRelayHost**. Không đặt port vào **setVirtualHost**. Khi broker dùng virtual host **/orders** nhưng TCP endpoint là **rabbitmq.internal:61614**, hai giá trị phải được cấu hình đúng vai trò như ví dụ.

## 3. Cấu hình broker relay qua TCP thuần

Nếu broker chỉ mở listener STOMP TCP không mã hóa trong mạng nội bộ được kiểm soát, có thể cấu hình trực tiếp relay host và port. Đây là ví dụ cấu hình kết nối, không phải lựa chọn phù hợp cho mọi môi trường triển khai.

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        StompBrokerRelayRegistration relay =
                registry.enableStompBrokerRelay("/topic", "/queue");

        relay.setRelayHost("rabbitmq.internal");
        relay.setRelayPort(61613);
        relay.setVirtualHost("/orders");

        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

Trong ví dụ:

- Client gửi message đến destination có prefix **/app** để Spring controller xử lý.
- **/topic** và **/queue** được chuyển đến broker bên ngoài.
- Ứng dụng mở TCP đến **rabbitmq.internal:61613**.
- STOMP CONNECT gửi header **host: /orders**.

Khi dùng cấu hình này, Spring dùng TCP client mặc định của broker relay. Để bật TLS hoặc tùy chỉnh sâu hơn TCP client, cần cấu hình **setTcpClient(...)**.

## 4. Cấu hình STOMP broker relay dùng TLS

### 4.1. TLS trên chặng Spring-to-broker

TLS trên kết nối relay bảo vệ frame STOMP khi di chuyển giữa ứng dụng Spring và broker. Cấu hình TLS ở đây không tự động bật TLS cho WebSocket endpoint của ứng dụng.

Spring cho phép cung cấp một **TcpOperations<byte[]>** tùy chỉnh thông qua **setTcpClient(...)**. Một cách triển khai là dùng **ReactorNettyTcpClient** với **StompReactorNettyCodec**. Reactor Netty **TcpClient.secure()** bật TLS cho TCP client.

Khi dùng TCP client tùy chỉnh, phải đặt host và port ngay trong cấu hình **TcpClient**. Các giá trị **setRelayHost** và **setRelayPort** trên relay registration sẽ bị bỏ qua khi đã gọi **setTcpClient**.

### 4.2. Cấu hình TLS với trust store mặc định

Ví dụ sau dùng trust configuration mặc định của JVM/Reactor Netty. Chứng thư máy chủ broker phải được tin cậy bởi trust store đang dùng và hostname phải khớp với chứng thư.

~~~java
package com.example.messaging;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.messaging.simp.config.StompBrokerRelayRegistration;
import org.springframework.messaging.simp.stomp.StompReactorNettyCodec;
import org.springframework.messaging.tcp.reactor.ReactorNettyTcpClient;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration implements WebSocketMessageBrokerConfigurer {

    @Value("${messaging.broker.tcp-host}")
    private String brokerHost;

    @Value("${messaging.broker.tcp-port}")
    private int brokerPort;

    @Value("${messaging.broker.virtual-host}")
    private String virtualHost;

    @Value("${messaging.broker.client-login}")
    private String clientLogin;

    @Value("${messaging.broker.client-passcode}")
    private String clientPasscode;

    @Value("${messaging.broker.system-login}")
    private String systemLogin;

    @Value("${messaging.broker.system-passcode}")
    private String systemPasscode;

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        StompBrokerRelayRegistration relay =
                registry.enableStompBrokerRelay("/topic", "/queue");

        relay.setVirtualHost(virtualHost);
        relay.setClientLogin(clientLogin);
        relay.setClientPasscode(clientPasscode);
        relay.setSystemLogin(systemLogin);
        relay.setSystemPasscode(systemPasscode);

        relay.setSystemHeartbeatSendInterval(10_000);
        relay.setSystemHeartbeatReceiveInterval(10_000);

        relay.setTcpClient(new ReactorNettyTcpClient<>(
                tcpClient -> tcpClient
                        .host(brokerHost)
                        .port(brokerPort)
                        .secure(),
                new StompReactorNettyCodec()
        ));

        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

Các giá trị cấu hình có thể được đưa vào **application.yml**:

~~~yaml
messaging:
  broker:
    tcp-host: ${STOMP_BROKER_HOST:rabbitmq.internal}
    tcp-port: ${STOMP_BROKER_PORT:61614}
    virtual-host: ${STOMP_VIRTUAL_HOST:/}
    client-login: ${STOMP_CLIENT_LOGIN}
    client-passcode: ${STOMP_CLIENT_PASSCODE}
    system-login: ${STOMP_SYSTEM_LOGIN}
    system-passcode: ${STOMP_SYSTEM_PASSCODE}
~~~

Các biến môi trường chứa thông tin đăng nhập cần được cấp từ secret manager hoặc cơ chế quản lý bí mật của nền tảng triển khai. Không commit passcode thật vào source control.

### 4.3. Dùng CA riêng cho broker nội bộ

Nếu broker dùng chứng thư được ký bởi CA nội bộ chưa nằm trong trust store mặc định, cần thêm CA đó vào trust store hoặc cấu hình trust manager riêng. Ví dụ dưới đây dùng file PEM của CA:

~~~java
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import java.io.File;
import javax.net.ssl.SSLException;

private ReactorNettyTcpClient<byte[]> createTcpClientWithPrivateCa() {
    try {
        SslContext sslContext = SslContextBuilder.forClient()
                .trustManager(new File("/run/secrets/broker-ca.pem"))
                .build();

        return new ReactorNettyTcpClient<>(
                tcpClient -> tcpClient
                        .host(brokerHost)
                        .port(brokerPort)
                        .secure(ssl -> ssl.sslContext(sslContext)),
                new StompReactorNettyCodec()
        );
    }
    catch (SSLException ex) {
        throw new IllegalStateException(
                "Cannot initialize TLS trust for the STOMP broker", ex
        );
    }
}
~~~

Trong **configureMessageBroker**, dùng:

~~~java
relay.setTcpClient(createTcpClientWithPrivateCa());
~~~

Không đồng thời gọi **setRelayHost** hoặc **setRelayPort** để mong chúng thay đổi địa chỉ của TCP client tùy chỉnh; host và port đã được đặt bên trong lambda.

### 4.4. Mutual TLS (mTLS)

TLS thông thường xác thực chứng thư máy chủ để ứng dụng biết mình đang kết nối đúng broker. Với mutual TLS, broker còn yêu cầu ứng dụng trình chứng thư client để xác thực chiều ngược lại.

Khi broker yêu cầu client certificate, có thể bổ sung **keyManager** vào **SslContextBuilder**:

~~~java
SslContext sslContext = SslContextBuilder.forClient()
        .trustManager(new File("/run/secrets/broker-ca.pem"))
        .keyManager(
                new File("/run/secrets/client-chain.pem"),
                new File("/run/secrets/client-private-key.pem")
        )
        .build();
~~~

Đoạn này thay phần tạo **SslContext** trong ví dụ CA riêng. Private key phải được bảo vệ như một secret. Broker cũng phải được cấu hình yêu cầu và xác thực client certificate; chỉ thêm certificate phía Spring không tự bật mTLS ở broker.

Không tắt xác minh chứng thư để khắc phục lỗi handshake. Cần kiểm tra CA chain, thời hạn chứng thư, SAN/hostname, SNI và cấu hình client certificate nếu broker yêu cầu.

## 5. Cấu hình TLS listener ở broker

TLS phải được bật ở cả hai đầu: Spring TCP client và STOMP listener của broker. Chỉ gọi **secure()** ở Spring sẽ không biến listener TCP thuần thành TLS listener.

### 5.1. Ví dụ RabbitMQ STOMP plugin

RabbitMQ cần bật STOMP plugin và cấu hình TLS listener. Ví dụ cấu hình rút gọn:

~~~ini
ssl_options.cacertfile = /etc/rabbitmq/tls/ca.pem
ssl_options.certfile = /etc/rabbitmq/tls/server.pem
ssl_options.keyfile = /etc/rabbitmq/tls/server-key.pem

stomp.listeners.tcp = none
stomp.listeners.ssl.1 = 61614
~~~

Ví dụ này tắt STOMP listener TCP thuần và mở STOMP TLS listener trên port **61614**. Tên file, đường dẫn và port cần khớp môi trường thực tế.

Nếu triển khai mTLS, broker cần yêu cầu client certificate và xác minh CA, ví dụ với các tùy chọn RabbitMQ tương ứng:

~~~ini
ssl_options.verify = verify_peer
ssl_options.fail_if_no_peer_cert = true
~~~

Khi bật các tùy chọn này, client phải gửi certificate được broker tin cậy. Cấu hình TLS của broker và cấu hình trust/key manager phía Spring phải thống nhất.

### 5.2. RabbitMQ virtual host

Với RabbitMQ, STOMP CONNECT header **host** chọn virtual host. Ví dụ:

~~~java
relay.setVirtualHost("/orders");
~~~

Virtual host **/orders** phải được tạo trước trên RabbitMQ, và tài khoản STOMP được cấu hình trong relay phải có quyền phù hợp đối với virtual host đó. Nếu dùng virtual host mặc định **/**, có thể cấu hình rõ **setVirtualHost("/")** để tránh phụ thuộc vào mặc định ở broker.

## 6. Phân biệt thông tin đăng nhập client và system

Broker relay dùng hai nhóm thông tin STOMP credentials:

| Cấu hình | Kết nối nào sử dụng | Mục đích |
|---|---|---|
| **clientLogin / clientPasscode** | Mỗi TCP connection được tạo thay mặt WebSocket client | Xác thực các kết nối client qua relay |
| **systemLogin / systemPasscode** | Một TCP system connection dùng chung | Xác thực message do mã phía server gửi đến broker |

Spring relay luôn đặt lại **login** và **passcode** trên CONNECT frame chuyển tiếp thay mặt client. Vì vậy, credentials do trình duyệt tự gửi trong STOMP CONNECT không được dùng như thông tin xác thực broker. Client nên xác thực với ứng dụng qua HTTP/WebSocket handshake và để Spring Security xác định **Principal** của session.

Một điểm kiến trúc quan trọng: các kết nối client qua relay thường dùng cùng một cặp **clientLogin/clientPasscode**. Broker vì thế có thể nhìn thấy cùng một broker account cho nhiều WebSocket user. Nếu cần phân quyền riêng theo người dùng, cần thiết kế lớp xác thực/ủy quyền và ánh xạ identity phù hợp; không giả định relay tự chuyển credentials tùy ý từ trình duyệt đến broker.

Nên dùng tài khoản broker có quyền tối thiểu cần thiết. Có thể tách tài khoản system và client để giới hạn quyền của message do server phát ra và message từ client.

## 7. Heartbeat, reconnect và trạng thái broker

### 7.1. Heartbeat của system connection

Relay gửi và nhận STOMP heartbeat qua system TCP connection. Mặc định Spring dùng khoảng thời gian 10 giây cho chiều gửi và nhận. Có thể điều chỉnh bằng:

~~~java
relay.setSystemHeartbeatSendInterval(10_000);
relay.setSystemHeartbeatReceiveInterval(10_000);
~~~

Giá trị được tính bằng milliseconds. Đặt bằng 0 sẽ tắt heartbeat tương ứng. Cần phối hợp giá trị với khả năng heartbeat của broker và timeout của hạ tầng mạng; không giảm interval tùy tiện vì sẽ làm tăng traffic và hoạt động kiểm tra.

### 7.2. Broker mất kết nối

Nếu system connection bị mất, relay tự thử kết nối lại theo chu kỳ mặc định 5 giây cho đến khi kết nối thành công. Spring phát **BrokerAvailabilityEvent** khi trạng thái system connection thay đổi. Service có thể lắng nghe sự kiện này để biết broker đang sẵn sàng hay không và tránh gửi message khi relay không khả dụng.

Khi gửi qua **SimpMessagingTemplate**, ứng dụng vẫn cần xử lý trường hợp gửi thất bại, chẳng hạn **MessageDeliveryException**. BrokerAvailabilityEvent phản ánh trạng thái system connection; nó không thay thế việc theo dõi từng WebSocket client session.

Các kết nối TCP thay mặt WebSocket client không tự động được khôi phục chỉ vì system connection đã reconnect. Client cần phát hiện mất kết nối và thực hiện reconnect STOMP/WebSocket theo chính sách retry phù hợp.

## 8. Kiểm tra kết nối và xử lý lỗi

### 8.1. Kiểm tra theo từng lớp

1. **DNS và route:** container/VM chạy Spring có phân giải được broker host không?
2. **TCP port:** firewall, security group, Kubernetes NetworkPolicy hoặc routing có cho phép outbound từ ứng dụng tới STOMP listener không?
3. **TLS handshake:** broker có mở TLS listener ở đúng port không? Certificate chain có được trust không? SAN có khớp hostname không?
4. **STOMP CONNECT:** credentials có đúng không? Header **host** có chọn đúng virtual host không?
5. **Broker authorization:** user có quyền connect, send, subscribe và truy cập destination cần dùng không?
6. **Message flow:** client có kết nối STOMP tới Spring, subscribe đúng destination và nhận được message qua broker relay không?

### 8.2. Lệnh chẩn đoán mạng

Kiểm tra TCP port từ máy/container có môi trường công cụ tương ứng:

~~~bash
nc -vz rabbitmq.internal 61614
~~~

Lệnh này chỉ xác nhận TCP port có thể mở kết nối; nó không xác nhận TLS hoặc STOMP authentication.

Kiểm tra TLS certificate và hostname:

~~~bash
openssl s_client -connect rabbitmq.internal:61614 -servername rabbitmq.internal -CAfile /run/secrets/broker-ca.pem -verify_return_error
~~~

Nếu TLS handshake thất bại, kiểm tra certificate chain, CA, thời hạn, hostname/SNI, port và yêu cầu mTLS. Nếu TLS thành công nhưng Spring vẫn không kết nối được, kiểm tra tiếp STOMP CONNECT headers, credentials và virtual host trong log broker.

### 8.3. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Connection refused | Sai host/port hoặc broker chưa mở listener | Kiểm tra TCP host, port và trạng thái STOMP listener |
| Connection timeout | Firewall, route hoặc DNS | Kiểm tra DNS, network policy, security group và outbound rule |
| SSL handshake failure | Kết nối TLS vào port TCP thuần, CA không được trust hoặc certificate sai hostname | Kiểm tra listener TLS, trust store, SAN và SNI |
| Broker báo sai virtual host | Header host không khớp virtual host | Kiểm tra setVirtualHost và virtual host tồn tại trên broker |
| ACCESS_REFUSED / authentication failure | Sai credentials hoặc user không được phép | Kiểm tra client/system credentials và quyền broker |
| Kết nối client mất khi broker restart | Client-side TCP/STOMP connection cần reconnect | Thực hiện reconnect ở client và kiểm tra sự kiện broker availability |
| Server gửi message thất bại khi broker down | System connection chưa sẵn sàng | Lắng nghe BrokerAvailabilityEvent và xử lý MessageDeliveryException |

## 9. Theo dõi số lượng kết nối và vận hành

Với N WebSocket client đang kết nối đến một instance Spring, số TCP connection relay thường xấp xỉ **N + 1**: một connection cho mỗi client và một system connection dùng chung. Khi triển khai nhiều instance Spring, mỗi instance có system connection riêng và số client connection phụ thuộc client được phân phối đến instance nào.

Spring cung cấp **WebSocketMessageBrokerStats** để theo dõi số session, STOMP frame và thông tin broker relay. Chỉ số TCP Connections của broker relay giúp đối chiếu số kết nối TCP theo mô hình trên. Khi số kết nối cao hơn dự kiến, kiểm tra session disconnect, reconnect loop, nhiều instance hoặc client không đóng session đúng cách.

Trước khi triển khai production, cần xác nhận:

- Broker đã bật STOMP listener đúng giao thức và port.
- Ứng dụng Spring truy cập được TCP endpoint từ network runtime thực tế.
- Virtual host tồn tại và broker user có quyền phù hợp.
- TLS trust chain, hostname/SNI và mTLS (nếu có) hoạt động.
- Client và system credentials được cấp từ secret manager.
- Heartbeat và reconnect phù hợp timeout của broker, load balancer và network.
- Broker connection limit đủ cho tổng WebSocket client trên tất cả instance cộng các system connection.

## 10. Nguyên tắc thiết kế

1. **Tách đúng ba lớp cấu hình.** TCP host/port là địa chỉ socket; virtual host là header STOMP; TLS là lớp bảo mật của transport.
2. **Dùng STOMP TLS listener khi bật secure TCP client.** Không gửi TLS handshake vào port chỉ nhận TCP thuần.
3. **Xác minh certificate.** Tin cậy CA hợp lệ và kiểm tra hostname/SNI; không tắt xác minh để bỏ qua lỗi.
4. **Giới hạn quyền broker.** Dùng credentials riêng cho system/client khi phù hợp và chỉ cấp quyền cần thiết.
5. **Quản lý secrets an toàn.** Không ghi passcode, private key hoặc token vào source control hay log.
6. **Thiết kế reconnect ở cả hai phía.** Relay tự reconnect system connection; WebSocket client vẫn cần chính sách reconnect riêng.
7. **Tính trước số connection.** Mỗi WebSocket client tạo một TCP connection tới broker, ngoài system connection dùng chung trên mỗi instance Spring.

## 11. Tài liệu tham khảo

- [Spring Framework – External STOMP Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework – Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [StompBrokerRelayRegistration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html)
- [Reactor Netty – TCP Client, SSL and TLS](https://projectreactor.io/docs/netty/release/reference/tcp-client.html)
- [ReactorNettyTcpClient Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/tcp/reactor/ReactorNettyTcpClient.html)
- [Spring Framework – Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [RabbitMQ – STOMP Plugin, TLS and Virtual Hosts](https://www.rabbitmq.com/docs/stomp)
