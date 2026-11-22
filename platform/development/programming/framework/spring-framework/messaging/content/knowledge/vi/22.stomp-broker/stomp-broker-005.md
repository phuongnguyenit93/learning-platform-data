# Kết nối hệ thống, kết nối client và thông tin đăng nhập relay

## 1. Vai trò của STOMP broker relay

Spring Messaging hỗ trợ hai cách xử lý message broker phổ biến trong WebSocket/STOMP:

- **Simple broker** chạy trong tiến trình ứng dụng Spring. Nó phù hợp với nhu cầu cơ bản, nhưng không có đầy đủ khả năng của một message broker chuyên dụng.
- **STOMP broker relay** chuyển tiếp STOMP frame giữa ứng dụng Spring và một broker STOMP bên ngoài, chẳng hạn RabbitMQ hoặc ActiveMQ. Broker bên ngoài đảm nhiệm quản lý subscription và phân phối message; Spring duy trì kết nối WebSocket với client và kết nối TCP tới broker.

Khi dùng relay, trình duyệt vẫn kết nối WebSocket tới endpoint của ứng dụng Spring. Trình duyệt không cần kết nối trực tiếp tới cổng TCP STOMP của broker. Spring nhận STOMP frame từ client, chuyển tiếp frame qua TCP tới broker, rồi đưa frame broker trả về đúng WebSocket session.

Broker relay có hai loại kết nối TCP quan trọng:

1. **System connection**: một kết nối dùng chung từ mỗi relay instance tới broker, phục vụ message do chính ứng dụng server phát ra, chẳng hạn message được gửi từ REST controller, service hoặc scheduled task.
2. **Client connection**: một kết nối TCP riêng cho từng WebSocket client đang kết nối. Relay chuyển tiếp STOMP frame của client tới broker và chuyển frame phản hồi từ broker về WebSocket session tương ứng.

Phân biệt hai kết nối này giúp cấu hình đúng thông tin đăng nhập, quyền broker, heartbeat và cách theo dõi trạng thái.

## 2. Luồng kết nối tổng thể

Một ứng dụng có thể cấu hình endpoint WebSocket /ws, application prefix /app và broker prefix /topic, /queue.

- Client thực hiện HTTP handshake tới ứng dụng Spring rồi nâng cấp thành WebSocket.
- Client gửi STOMP CONNECT qua WebSocket.
- Spring thiết lập danh tính người dùng từ cơ chế xác thực HTTP/WebSocket.
- Broker relay mở hoặc sử dụng TCP connection tương ứng tới broker.
- Các frame tới destination /app/... được Spring định tuyến tới controller có @MessageMapping.
- Các frame tới destination broker như /topic/... hoặc /queue/... được relay chuyển tới broker ngoài.
- Frame broker phát tới subscription được chuyển qua client TCP connection và WebSocket session tới client.

Sơ đồ luồng message:

~~~mermaid
flowchart LR
    C["Browser / STOMP client"] <-->|"WebSocket + STOMP"| S["Spring WebSocket endpoint"]
    S <-->|"Client TCP connection riêng"| R["STOMP broker relay"]
    R <-->|"STOMP TCP"| B["External STOMP broker"]
    A["REST / Service / Scheduler"] -->|"SimpMessagingTemplate"| S
    S <-->|"System TCP connection dùng chung"| B
    S -->|"/app/..."| H["@MessageMapping controller"]
~~~

Sơ đồ thể hiện các đường đi chính. Trong triển khai thực tế, broker relay là message handler trong Spring; các channel nội bộ của Spring định tuyến message giữa controller, broker handler và WebSocket session.

## 3. System connection và client connection khác nhau thế nào?

| Thuộc tính | System connection | Client connection |
|---|---|---|
| Số lượng | Một kết nối dùng chung cho mỗi relay instance. | Một kết nối cho mỗi WebSocket client đang kết nối tới instance đó. |
| Mục đích | Gửi message từ server-side application tới broker, không gắn với một client session cụ thể. | Chuyển tiếp message của một client tới broker và chuyển frame broker trả về client đó. |
| Credentials | systemLogin, systemPasscode. | clientLogin, clientPasscode. |
| Vòng đời | Được relay tạo khi khởi động và tự kết nối lại khi mất kết nối. | Được tạo khi client kết nối; được đóng khi session client kết thúc hoặc connection lỗi. |
| Ví dụ | REST request gọi SimpMessagingTemplate.convertAndSend(...). | Client subscribe /topic/prices hoặc gửi STOMP SEND. |

Ví dụ, nếu một relay instance phục vụ 500 WebSocket session đang hoạt động, broker thường thấy khoảng 500 client TCP connections cùng system connection của instance đó. Khi chạy nhiều Spring instance, mỗi instance có system connection riêng và quản lý các client connection của các session đang kết nối vào instance đó. Hãy tính cả số lượng connection này khi đặt giới hạn kết nối, quota và tài nguyên cho broker.

System connection không phải là một kết nối WebSocket của người dùng. Nó cũng không thay thế các client connection dùng để nhận message broker trả về cho từng client.

## 4. Cấu hình STOMP broker relay trong Java

Dùng enableStompBrokerRelay để chuyển các destination broker tới một STOMP broker bên ngoài:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.messaging.simp.config.StompBrokerRelayRegistration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    private final String relayHost;
    private final int relayPort;
    private final String clientLogin;
    private final String clientPasscode;
    private final String systemLogin;
    private final String systemPasscode;
    private final String virtualHost;

    public WebSocketConfig(
            @Value("${app.stomp.relay.host${") String relayHost,
            @Value("${app.stomp.relay.port:61613${") int relayPort,
            @Value("${app.stomp.relay.client-login${") String clientLogin,
            @Value("${app.stomp.relay.client-passcode${") String clientPasscode,
            @Value("${app.stomp.relay.system-login${") String systemLogin,
            @Value("${app.stomp.relay.system-passcode${") String systemPasscode,
            @Value("${app.stomp.relay.virtual-host:${") String virtualHost) {
        this.relayHost = relayHost;
        this.relayPort = relayPort;
        this.clientLogin = clientLogin;
        this.clientPasscode = clientPasscode;
        this.systemLogin = systemLogin;
        this.systemPasscode = systemPasscode;
        this.virtualHost = virtualHost;
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        StompBrokerRelayRegistration relay =
                registry.enableStompBrokerRelay("/topic", "/queue")
                        .setRelayHost(relayHost)
                        .setRelayPort(relayPort)
                        .setClientLogin(clientLogin)
                        .setClientPasscode(clientPasscode)
                        .setSystemLogin(systemLogin)
                        .setSystemPasscode(systemPasscode)
                        .setSystemHeartbeatSendInterval(10_000)
                        .setSystemHeartbeatReceiveInterval(10_000);

        if (!virtualHost.isBlank()) {
            relay.setVirtualHost(virtualHost);
        }
    }
}
~~~

Ý nghĩa các cấu hình:

- **setRelayHost** và **setRelayPort**: địa chỉ mạng và cổng TCP STOMP của broker ngoài.
- **setClientLogin** và **setClientPasscode**: credentials relay sử dụng khi tạo các broker connection thay mặt cho WebSocket client.
- **setSystemLogin** và **setSystemPasscode**: credentials cho system connection dùng chung.
- **setVirtualHost**: giá trị header STOMP host gửi trong frame CONNECT, nếu broker yêu cầu.
- **setSystemHeartbeatSendInterval** và **setSystemHeartbeatReceiveInterval**: chu kỳ gửi và khoảng chờ heartbeat của system connection, tính bằng mili giây.

Đoạn cấu hình là ví dụ cho ứng dụng có Spring Messaging và cơ chế tiêm cấu hình của Spring. Các giá trị thực tế phải lấy từ môi trường triển khai và cấu hình broker đang sử dụng.

## 5. Địa chỉ broker, cổng TCP và virtual host

Có ba khái niệm dễ bị nhầm:

| Cấu hình | Ý nghĩa |
|---|---|
| WebSocket endpoint, ví dụ /ws | Địa chỉ client dùng để kết nối tới ứng dụng Spring. |
| Relay host/port | Địa chỉ IP hoặc hostname và cổng TCP mà Spring dùng để kết nối tới STOMP broker. |
| Virtual host | Giá trị header host trong STOMP CONNECT, có thể dùng để chọn virtual host hoặc tenant ở broker. |

Ví dụ, trình duyệt có thể kết nối wss://app.example.com/ws, trong khi Spring relay kết nối tới broker.internal:61613. Đây là hai kết nối khác nhau với hai endpoint khác nhau.

Cổng 61613 thường được dùng làm cổng STOMP TCP trong một số cấu hình broker, chẳng hạn RabbitMQ khi STOMP plugin được bật. Đây không phải cổng mặc định chung cho mọi broker. Cần kiểm tra listener STOMP TCP, plugin, port mapping, firewall và tài liệu của broker đang dùng. Không lấy cổng AMQP hoặc cổng WebSocket của broker thay cho cổng TCP STOMP.

setVirtualHost("example-vhost") không thay đổi địa chỉ TCP mà relay kết nối tới. Nó đặt header host trong frame STOMP CONNECT. Thuộc tính này hữu ích khi địa chỉ dịch vụ STOMP logic khác hostname thực tế mà TCP socket kết nối tới, hoặc broker yêu cầu một virtual host cụ thể.

## 6. Phân biệt client credentials và system credentials

Spring cung cấp hai cặp credentials độc lập.

### Client credentials

- Cấu hình qua setClientLogin(...) và setClientPasscode(...).
- Được dùng khi relay tạo TCP connection tới broker thay mặt cho các WebSocket client.
- Một cặp cấu hình được áp dụng cho các client connection do relay quản lý.
- Theo mặc định, hai giá trị là guest và guest.

### System credentials

- Cấu hình qua setSystemLogin(...) và setSystemPasscode(...).
- Được dùng cho system TCP connection dùng chung.
- Phục vụ message do server-side application gửi tới broker mà không gắn với một client session, ví dụ từ REST controller, service hoặc scheduled task.
- Theo mặc định, hai giá trị là guest và guest.

Hai cặp credentials không nên bị nhầm lẫn. Client credentials phục vụ các connection đại diện cho WebSocket client; system credentials phục vụ message do ứng dụng server phát ra.

**Điểm quan trọng về CONNECT của client:** broker relay luôn đặt header login và passcode trên mọi frame STOMP CONNECT mà relay chuyển tới broker thay mặt cho client. Vì vậy, login và passcode do trình duyệt gửi trong STOMP CONNECT sẽ bị bỏ qua. Client WebSocket không cần gửi broker credentials trong JavaScript.

Điều này cũng có nghĩa là clientLogin/clientPasscode là credentials broker dùng chung cho các client connection do relay tạo ra, không phải username/password riêng của từng tài khoản ứng dụng. Spring xác định người dùng ứng dụng qua danh tính HTTP/WebSocket và Principal; broker authentication và application authentication là hai lớp khác nhau.

## 7. Xác thực người dùng ở HTTP/WebSocket

Một phiên STOMP over WebSocket bắt đầu bằng HTTP request: WebSocket handshake hoặc các HTTP request của SockJS. Trong ứng dụng web thông thường, Spring Security xác thực HTTP request và lưu danh tính vào HTTP session. Spring liên kết principal đó với WebSocket/SockJS session và các STOMP message tiếp theo.

Luồng xác thực điển hình:

1. Người dùng đăng nhập qua cơ chế HTTP authentication của ứng dụng.
2. Trình duyệt mở WebSocket handshake tới endpoint Spring, gửi cookie/session phù hợp.
3. Spring lấy principal từ HTTP request đã xác thực và gắn với WebSocket session.
4. Các STOMP message trên session mang danh tính người dùng do Spring quản lý.
5. Spring Security có thể dùng principal và destination để kiểm tra quyền SEND/SUBSCRIBE.

Với STOMP over WebSocket, header login và passcode của giao thức không phải cơ chế xác thực người dùng mặc định của Spring. Không dùng broker credentials làm thông tin đăng nhập tài khoản ứng dụng.

Nếu ứng dụng dùng token thay vì cookie-based HTTP session, cần thiết kế bước xác thực token và gắn Principal vào message/session, thường bằng cơ chế xác thực ở inbound channel. Không chuyển token người dùng thành clientPasscode của relay.

## 8. Client kết nối tới Spring bằng STOMP.js

Ví dụ với STOMP.js, brokerURL là WebSocket endpoint của ứng dụng Spring:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "ws://localhost:8080/ws",
    reconnectDelay: 5000,
    heartbeatIncoming: 10000,
    heartbeatOutgoing: 10000,

    onConnect: () => {
        client.subscribe("/topic/updates", (frame) => {
            console.log("Update:", frame.body);
        });
    },

    onStompError: (frame) => {
        console.error("Broker error:", frame.headers["message"]);
    }
});

client.activate();
~~~

Trong môi trường HTTPS, WebSocket endpoint thường dùng wss://. Với SockJS, client dùng webSocketFactory tạo SockJS connection thay cho brokerURL.

Client chỉ biết endpoint Spring, chẳng hạn /ws. Nó không cần biết hostname nội bộ, cổng TCP STOMP, username hoặc passcode của broker. Không đặt login/passcode broker trong cấu hình JavaScript; relay sẽ sử dụng clientLogin/clientPasscode đã cấu hình ở server.

## 9. Server gửi message qua system connection

Các message do ứng dụng server tạo ra và gửi qua broker relay không gắn với một WebSocket client cụ thể sẽ sử dụng system connection. Một ví dụ là REST request cập nhật trạng thái đơn hàng rồi phát thông báo tới topic:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderEventPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishOrderUpdate(String orderId, String status) {
        OrderUpdate event = new OrderUpdate(orderId, status);
        messagingTemplate.convertAndSend("/topic/order-updates", event);
    }
}
~~~

Ví dụ payload:

~~~java
public record OrderUpdate(String orderId, String status) {
}
~~~

Vì lệnh gửi xuất phát từ server và không gắn với session cụ thể, relay sử dụng system connection và systemLogin/systemPasscode. Broker user của system connection cần có quyền phù hợp với các destination mà ứng dụng server sẽ publish hoặc subscribe theo cấu hình hệ thống.

Ngược lại, nếu client gửi STOMP SEND tới một broker destination, frame được chuyển qua client connection của session đó. Không phải mọi message đi qua relay đều dùng system connection.

## 10. Heartbeat, reconnect và trạng thái broker

Broker relay trao đổi heartbeat với broker qua system connection. Trong Spring Framework, khoảng gửi và nhận heartbeat của system connection mặc định là 10 giây. Có thể điều chỉnh bằng:

- **setSystemHeartbeatSendInterval(milliseconds)**: khoảng thời gian gửi heartbeat khi không có dữ liệu khác để gửi.
- **setSystemHeartbeatReceiveInterval(milliseconds)**: khoảng thời gian tối đa chờ heartbeat từ broker khi không có dữ liệu khác.
- Giá trị 0 có thể dùng để tắt heartbeat gửi hoặc không yêu cầu heartbeat nhận ở hướng tương ứng.

Nếu mất kết nối tới broker, relay tiếp tục thử kết nối lại; mặc định việc thử lại diễn ra sau mỗi 5 giây cho đến khi thành công. Cần phân biệt trạng thái WebSocket client và trạng thái system connection: client có thể vẫn kết nối tới ứng dụng trong khi relay đang mất kết nối với broker.

Spring phát BrokerAvailabilityEvent khi system connection mất hoặc được thiết lập lại. Service cần biết broker đang khả dụng có thể lắng nghe event:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;
import org.springframework.stereotype.Component;

@Component
public class BrokerAvailabilityListener {

    @EventListener
    public void onBrokerAvailability(BrokerAvailabilityEvent event) {
        if (event.isBrokerAvailable()) {
            System.out.println("STOMP broker is available");
        } else {
            System.out.println("STOMP broker is unavailable");
        }
    }
}
~~~

Ứng dụng có thể dùng trạng thái này để tạm dừng tác vụ publish không cần thiết, hiển thị trạng thái vận hành hoặc retry ở tầng nghiệp vụ theo chính sách riêng. Không nên giả định rằng một lệnh publish sẽ thành công chỉ vì WebSocket handshake của client đã thành công.

## 11. Quản lý credentials và quyền broker

Trong môi trường thật, tránh ghi username/password trực tiếp trong mã nguồn, file cấu hình được commit hoặc log. Có thể đưa giá trị qua biến môi trường, secret manager hoặc hệ thống quản lý cấu hình bảo mật.

Ví dụ application.properties:

~~~properties
app.stomp.relay.host=${STOMP_RELAY_HOST:localhost${
app.stomp.relay.port=${STOMP_RELAY_PORT:61613${

app.stomp.relay.client-login=${STOMP_RELAY_CLIENT_LOGIN${
app.stomp.relay.client-passcode=${STOMP_RELAY_CLIENT_PASSCODE${

app.stomp.relay.system-login=${STOMP_RELAY_SYSTEM_LOGIN${
app.stomp.relay.system-passcode=${STOMP_RELAY_SYSTEM_PASSCODE${

app.stomp.relay.virtual-host=${STOMP_RELAY_VIRTUAL_HOST:${
~~~

Các biến môi trường chứa passcode cần được cấp trong môi trường chạy ứng dụng. Ví dụ trên cố ý không đặt giá trị mặc định cho passcode để tránh vô tình chạy production với tài khoản mẫu.

Một số nguyên tắc vận hành:

1. **Không giữ guest/guest ở production.** Đây là giá trị mặc định của Spring relay, không phải credentials an toàn cho triển khai thật.
2. **Dùng quyền tối thiểu.** Broker account dành cho client connection chỉ nên có quyền cần thiết trên các exchange, queue hoặc destination mà client cần truy cập. System account chỉ nên có quyền cần thiết cho luồng message do server phát.
3. **Hiểu phạm vi client account.** Vì relay dùng cùng clientLogin/clientPasscode cho các connection thay mặt client, broker có thể nhìn các client connection dưới cùng broker identity. Phân quyền từng người dùng ứng dụng cần được thực hiện ở Spring Security và tầng nghiệp vụ, hoặc qua thiết kế broker authentication/authorization riêng nếu cần phân tách sâu hơn.
4. **Không ghi passcode vào log.** Tránh log toàn bộ STOMP CONNECT frame, cấu hình hoặc exception chứa credential.
5. **Bảo vệ đường truyền.** Dùng mạng riêng và TLS phù hợp giữa Spring và broker; bảo vệ WebSocket bằng HTTPS/WSS khi triển khai qua mạng không tin cậy.
6. **Luân chuyển bí mật.** Khi thay credentials, cập nhật secret và kế hoạch restart/reconnect để relay tạo các broker connection bằng thông tin mới.
7. **Tách môi trường.** Dùng broker account và secret riêng cho local, staging và production.

## 12. Phân quyền ở Spring và broker

Có hai lớp kiểm soát khác nhau:

- **Broker authorization** quyết định broker account được CONNECT, SEND hoặc SUBSCRIBE vào destination nào.
- **Spring Security authorization** quyết định principal ứng dụng nào được gửi hoặc đăng ký subscription trên destination nào trong ứng dụng Spring.

Ví dụ, tất cả client TCP connection có thể dùng một broker account được giới hạn trong nhóm destination mà ứng dụng cho phép. Spring Security tiếp tục kiểm tra từng Principal trước khi cho phép SUBSCRIBE vào /user/** hoặc SEND tới /app/**. Việc client không biết broker password không có nghĩa là ứng dụng đã tự động an toàn; endpoint WebSocket, origin, authentication và message authorization vẫn phải được cấu hình.

Không dùng destination prefix như một ranh giới bảo mật duy nhất. Phải kiểm tra quyền theo principal và quy tắc nghiệp vụ, đặc biệt với message riêng tư, dữ liệu tenant và thao tác có tác động tới tài khoản khác.

## 13. Lỗi thường gặp và cách chẩn đoán

### Connection refused hoặc timeout

Nguyên nhân thường gặp:

- Sai relayHost hoặc relayPort.
- Broker chưa bật STOMP TCP listener hoặc plugin tương ứng.
- Spring chạy trong container nhưng dùng localhost trỏ về chính container Spring thay vì broker.
- Firewall, network policy, DNS hoặc port mapping chặn kết nối.

Cách kiểm tra: kiểm tra hostname từ môi trường chạy Spring, listener TCP của broker, port mapping và log khởi động của broker. Kiểm tra kết nối từ chính container/host của ứng dụng, không chỉ từ máy developer.

### Broker từ chối CONNECT

Nguyên nhân thường gặp:

- clientLogin/clientPasscode không hợp lệ cho client connection.
- systemLogin/systemPasscode không hợp lệ cho system connection.
- Account bị khóa, password hết hạn hoặc broker không cho phép account dùng STOMP.
- virtualHost không đúng hoặc account không có quyền trên virtual host đó.

Cách kiểm tra: xác định lỗi xuất hiện khi system connection khởi tạo hay khi client connection mới được tạo; kiểm tra credentials tương ứng và log broker. Không thử gửi password broker từ trình duyệt để khắc phục lỗi relay.

### Client WebSocket kết nối được nhưng không nhận message

Kiểm tra:

1. Client subscribe đúng destination broker, chẳng hạn /topic/updates.
2. Destination prefix đã khai báo trong enableStompBrokerRelay có khớp destination cần relay.
3. Client broker account có quyền SUBSCRIBE.
4. Broker có publish message tới destination đó hay không.
5. Relay còn giữ client TCP connection và WebSocket session hay không.

### Server publish thất bại nhưng client vẫn kết nối

Kiểm tra system connection, systemLogin/systemPasscode, quyền SEND của system account và trạng thái BrokerAvailabilityEvent. WebSocket session của client không chứng minh system connection đang hoạt động.

### /app/... không được relay chuyển tới broker

Đây thường là nhầm lẫn giữa application destination và broker destination. Destination bắt đầu bằng /app được định tuyến tới method @MessageMapping của Spring sau khi bỏ application prefix. Chỉ các destination khớp broker prefix như /topic hoặc /queue mới được relay theo cấu hình ví dụ.

### Lỗi heartbeat hoặc connection bị đóng định kỳ

Kiểm tra heartbeat hai chiều, thời gian idle timeout của load balancer/proxy, khả năng xử lý heartbeat của broker và log TCP. Nếu thay đổi interval, phải bảo đảm cấu hình tương thích giữa các thành phần; không đặt timeout proxy ngắn hơn khoảng heartbeat dự kiến.

### Chỉ một số instance gửi được message

Trong triển khai cluster, kiểm tra broker endpoint, credentials, virtual host, network policy và trạng thái system connection của từng Spring instance. Mỗi relay instance có system connection riêng; một instance khỏe không chứng minh các instance khác cũng đã kết nối thành công.

## 14. Checklist triển khai

- [ ] Broker ngoài đã bật STOMP TCP listener và cho phép Spring kết nối.
- [ ] relayHost/relayPort trỏ tới đúng địa chỉ từ môi trường chạy Spring.
- [ ] Broker account cho client connection được cấu hình bằng clientLogin/clientPasscode.
- [ ] Broker account cho system connection được cấu hình bằng systemLogin/systemPasscode.
- [ ] Các account có quyền SEND/SUBSCRIBE đúng phạm vi destination.
- [ ] virtualHost được cấu hình khi broker yêu cầu STOMP host header.
- [ ] WebSocket endpoint và HTTP authentication hoạt động độc lập với broker credentials.
- [ ] Client không gửi broker login/passcode trong STOMP CONNECT.
- [ ] Heartbeat, reconnect và BrokerAvailabilityEvent được kiểm tra.
- [ ] Secret không nằm trong source control hoặc log.
- [ ] Giới hạn connection của broker đáp ứng số lượng client session và số Spring instance.

## 15. Ghi nhớ

STOMP broker relay duy trì một system TCP connection dùng chung cho message do server phát và một client TCP connection riêng cho mỗi WebSocket client. systemLogin/systemPasscode xác thực system connection; clientLogin/clientPasscode xác thực các connection thay mặt cho client. Relay tự ghi login/passcode vào STOMP CONNECT gửi tới broker, vì vậy client WebSocket không cần biết broker credentials. Người dùng ứng dụng được xác thực qua HTTP/WebSocket và Principal; quyền truy cập được kiểm tra ở Spring Security cùng broker ACL. Hiểu rõ các lớp kết nối và xác thực này giúp cấu hình relay đúng, giới hạn quyền hợp lý và chẩn đoán sự cố theo đúng connection bị lỗi.

## Tài liệu tham khảo

- [Spring Framework Reference — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Spring Framework Reference — Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [StompBrokerRelayRegistration API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html)