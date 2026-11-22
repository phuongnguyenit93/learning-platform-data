# Tiền tố ứng dụng, tiền tố broker và tiền tố người dùng

Spring STOMP over WebSocket dùng destination trong STOMP frame để quyết định message đi vào controller nghiệp vụ, tới message broker hay tới một user/session cụ thể. Ba nhóm tiền tố thường gặp:

- **/app**: message hướng vào ứng dụng, thường được định tuyến tới phương thức @MessageMapping.
- **/topic và /queue**: destination do broker quản lý để phân phối message.
- **/user/**: destination logic dành cho user/session; Spring phân giải nó thành destination nội bộ riêng cho từng phiên kết nối.

Các tiền tố này thuộc tầng STOMP destination. Chúng khác URL endpoint WebSocket như /ws, là địa chỉ HTTP dùng để bắt đầu handshake. Client có thể kết nối đúng WebSocket endpoint nhưng gửi message sai destination nếu nhầm hai khái niệm này.

## 1. WebSocket endpoint và STOMP destination

WebSocket endpoint là URL client dùng để mở kết nối:

~~~java
registry.addEndpoint("/ws");
~~~

Trình duyệt kết nối tới ws://localhost:8080/ws hoặc wss://app.example.com/ws.

Sau khi kết nối, client gửi STOMP frame có header destination, ví dụ:

~~~text
/app/chat.send
/topic/chat
/user/queue/reply
~~~

Spring phân loại destination sau khi handshake hoàn tất. Chúng không phải URL HTTP và không cần đăng ký như endpoint riêng.

Cấu hình tổng quát:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Client kết nối /ws, gửi command tới /app/..., subscribe destination broker như /topic/... hoặc /queue/..., và có thể dùng /user/ để nhận message riêng. Không thêm /app vào URL handshake.

## 2. Tiền tố ứng dụng: setApplicationDestinationPrefixes

Tiền tố ứng dụng xác định STOMP message được chuyển tới phương thức @MessageMapping trong controller.

~~~java
registry.setApplicationDestinationPrefixes("/app");
~~~

Ví dụ controller:

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}
~~~

Client gửi STOMP SEND tới /app/chat.send:

~~~text
SEND
destination:/app/chat.send
content-type:application/json

{"sender":"alice","content":"Hello"}
^@
~~~

Spring nhận thấy destination bắt đầu bằng /app, loại bỏ tiền tố này rồi dùng phần còn lại /chat.send để tìm @MessageMapping("/chat.send").

Vì prefix đã được loại bỏ trước khi tra cứu, annotation chỉ ghi phần path còn lại:

~~~java
@MessageMapping("/chat.send")
~~~

Không viết @MessageMapping("/app/chat.send"), vì như vậy mapping sẽ lặp lại prefix mà Spring đã loại bỏ.

Có thể khai báo nhiều application prefix:

~~~java
registry.setApplicationDestinationPrefixes("/app", "/api");
~~~

Spring loại bỏ prefix phù hợp trước khi tra cứu mapping. Prefix nên có quy ước rõ ràng và không chồng lấn với broker prefix. Spring tự thêm dấu / cuối nếu application prefix chưa có dấu này.

Application prefix chỉ là quy tắc routing, không phải cơ chế authentication hoặc authorization. Controller vẫn phải kiểm tra payload, danh tính, quyền và trạng thái nghiệp vụ. Spring Security có thể giới hạn client chỉ được SEND tới /app/** và kiểm soát SUBSCRIBE tới destination được phép.

Nếu client được quyền SEND trực tiếp tới /topic/..., nó có thể bỏ qua validation trong @MessageMapping. Chỉ mở những destination client thực sự cần.

## 3. Tiền tố broker: simple broker và broker relay

Broker prefix xác định destination do broker quản lý. Client thường SUBSCRIBE vào các destination này; server cũng có thể gửi message tới chúng.

Spring hỗ trợ hai cách cấu hình:

- enableSimpleBroker(...): broker đơn giản chạy trong bộ nhớ của ứng dụng.
- enableStompBrokerRelay(...): relay chuyển tiếp message tới STOMP broker bên ngoài.

### Simple broker

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

Client subscribe:

~~~text
SUBSCRIBE
id:chat-subscription
destination:/topic/chat
ack:auto
^@
~~~

Khi server gửi message tới /topic/chat, simple broker tìm subscription khớp destination và phân phối message tới client tương ứng.

Trong simple broker, /topic và /queue không có ngữ nghĩa đặc biệt do Spring áp đặt. Đây là quy ước tên để phân biệt publish-subscribe với luồng thường được hiểu là point-to-point. Vì vậy, /queue/orders trên simple broker không tự động là durable queue có competing consumers như queue của broker chuyên dụng.

Simple broker phù hợp cho ứng dụng nhỏ hoặc thử nghiệm. Nó chỉ hỗ trợ một tập con STOMP command, không có đầy đủ ACK/RECEIPT và không phù hợp cho clustering.

### STOMP broker relay

Khi cần broker chuyên dụng, cấu hình relay:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("localhost")
            .setRelayPort(61613)
            .setClientLogin("stomp-client")
            .setClientPasscode("CLIENT_PASSWORD")
            .setSystemLogin("stomp-system")
            .setSystemPasscode("SYSTEM_PASSWORD");
}
~~~

Relay là MessageHandler trong Spring. Nó mở kết nối TCP tới STOMP broker bên ngoài, chuyển message từ ứng dụng lên broker và chuyển message broker gửi về xuống WebSocket client.

- enableStompBrokerRelay chọn destination được chuyển tới broker.
- setRelayHost và setRelayPort đặt địa chỉ TCP của broker.
- setClientLogin và setClientPasscode đặt thông tin xác thực cho kết nối client được relay.
- setSystemLogin và setSystemPasscode đặt thông tin xác thực cho kết nối hệ thống của Spring.

Lấy credentials từ secret manager hoặc biến môi trường; không commit password vào source code. Cú pháp và semantics của /topic, /queue hay prefix khác phụ thuộc broker. Kiểm tra tài liệu STOMP của RabbitMQ, ActiveMQ Artemis hoặc broker đang dùng.

| Destination | Simple broker | External STOMP broker |
|---|---|---|
| /topic/news | Quy ước broadcast tới subscriber khớp | Thường là pub-sub destination |
| /queue/orders | Destination trong bộ nhớ, không phải durable queue thật | Thường là point-to-point queue |
| /app/orders.create | Được route tới controller | Được Spring xử lý trước relay |
| /user/queue/alerts | Spring phân giải user destination trước broker | Spring phân giải rồi relay tới broker |

## 4. Tiền tố người dùng: /user/

Tiền tố user destination mặc định của Spring là /user/. Nó cho phép các client subscribe cùng một tên logic nhưng nhận message ở destination nội bộ riêng cho từng user hoặc session.

Ví dụ Alice và Bob đều subscribe:

~~~text
/user/queue/notifications
~~~

Spring dùng UserDestinationMessageHandler để chuyển destination logic thành tên nội bộ riêng. Tên vật lý có thể trông như sau:

~~~text
Alice: /queue/notifications-userA-session1
Bob:   /queue/notifications-userB-session1
~~~

Đây chỉ là ví dụ minh họa. Ứng dụng không nên tự tạo hoặc phụ thuộc vào cách Spring đặt tên nội bộ. Client chỉ cần subscribe /user/queue/notifications.

Frame SUBSCRIBE:

~~~text
SUBSCRIBE
id:private-notifications
destination:/user/queue/notifications
^@
~~~

Spring xử lý /user/, tìm user/session phù hợp rồi chuyển subscription tới destination riêng. Khi server gửi message tới user, Spring phân giải sang destination tương ứng để broker phân phối đúng phiên.

 /user/ không phải broker prefix thông thường. Nó được xử lý bởi UserDestinationMessageHandler; destination nội bộ sau khi phân giải mới được chuyển tới broker. Tránh cấu hình broker prefix quá rộng như / khiến broker bắt cả /user/... trước khi Spring xử lý.

Có thể thay prefix mặc định:

~~~java
registry.setUserDestinationPrefix("/private/");
~~~

Nếu thay đổi, client và server phải dùng prefix mới thống nhất. Nếu không gọi setter, Spring mặc định dùng /user/.

## 5. Gửi message tới user bằng SimpMessagingTemplate

Một service có thể gửi message tới user cụ thể bằng SimpMessagingTemplate.convertAndSendToUser():

~~~java
@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(String username, Notification notification) {
        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                notification
        );
    }
}
~~~

Tham số đầu tiên là tên user, thường lấy từ Principal.getName(). Tham số thứ hai là phần destination phía sau user prefix; không thêm /user/ vào tham số này.

Principal phản ánh user đã được xác thực cho WebSocket session. Trong ứng dụng Spring Security, danh tính thường được thiết lập qua HTTP handshake và security context. Không lấy username do client tự gửi trong JSON làm danh tính đáng tin cậy.

Một user có thể đăng nhập từ nhiều tab hoặc thiết bị. Mặc định, user destination có thể gửi tới tất cả session của user đang subscribe destination đó. Nếu chỉ muốn trả lời session đã gửi message, dùng @SendToUser với broadcast=false:

~~~java
@MessageMapping("/orders.validate")
@SendToUser(value = "/queue/validation", broadcast = false)
public ValidationResult validate(OrderRequest request) {
    return validationService.validate(request);
}
~~~

Với session không gắn user đã xác thực, @SendToUser cũng có ngữ nghĩa chỉ gửi về session đã gửi message.

## 6. @SendTo, @SendToUser và @SubscribeMapping

@SendTo định tuyến giá trị trả về tới broker destination:

~~~java
@MessageMapping("/chat.send")
@SendTo("/topic/chat")
public ChatMessage send(ChatMessage message) {
    return message;
}
~~~

Client gửi /app/chat.send; Spring loại bỏ /app, gọi method và gửi kết quả tới /topic/chat. Broker phát message cho các subscriber phù hợp.

Có thể chỉ định nhiều destination:

~~~java
@MessageMapping("/orders.created")
@SendTo({"/topic/orders", "/topic/audit"})
public OrderEvent publish(OrderEvent event) {
    return event;
}
~~~

Nếu không khai báo @SendTo, Spring dùng destination phản hồi mặc định dựa trên destination đầu vào và prefix broadcast mặc định. Dùng @SendTo tường minh giúp client/server thống nhất hợp đồng.

@SendToUser định tuyến kết quả tới user/session:

~~~java
@MessageMapping("/profile.refresh")
@SendToUser("/queue/profile")
public ProfileView refreshProfile(Principal principal) {
    return profileService.load(principal.getName());
}
~~~

Client subscribe /user/queue/profile. Method-level annotation có thể ghi đè cấu hình mặc định ở class-level.

@SubscribeMapping xử lý STOMP SUBSCRIBE thay vì SEND. Nó hữu ích khi client cần lấy trạng thái ban đầu lúc đăng ký:

~~~java
@Controller
public class DashboardController {

    @SubscribeMapping("/dashboard")
    public DashboardSnapshot initialSnapshot(Principal principal) {
        return dashboardService.load(principal.getName());
    }
}
~~~

Client subscribe /app/dashboard. Spring gọi method và mặc định gửi kết quả trực tiếp về client khởi tạo subscription, không broadcast qua broker. Nếu muốn kết quả đi qua broker, thêm @SendTo hoặc @SendToUser.

| Annotation | STOMP frame | Mục đích |
|---|---|---|
| @MessageMapping | SEND | Xử lý command/message gửi vào ứng dụng |
| @SubscribeMapping | SUBSCRIBE | Trả dữ liệu khởi tạo cho client subscribe |
| @SendTo | Return routing | Gửi kết quả tới broker destination |
| @SendToUser | Return routing | Gửi kết quả tới user/session destination |

## 7. Luồng routing đầy đủ trong Spring

Khi cấu hình /app, /topic, /queue và /user/, message đi qua các channel chính:

~~~text
Client
  |
  | SEND /app/chat.send
  v
clientInboundChannel
  |
  | match /app, remove application prefix
  v
@MessageMapping("/chat.send")
  |
  | @SendTo("/topic/chat")
  v
brokerChannel
  |
  v
Message Broker
  |
  | find matching subscriptions
  v
clientOutboundChannel
  |
  v
WebSocket clients
~~~

Các channel có vai trò:

- clientInboundChannel: nhận message từ WebSocket client sau khi STOMP frame được giải mã.
- brokerChannel: chuyển message từ code phía server tới broker.
- clientOutboundChannel: chuyển message từ server/broker tới WebSocket client.

Với user destination, UserDestinationMessageHandler xử lý subscription rồi đăng ký destination riêng ở broker. Khi server gọi convertAndSendToUser, Spring phân giải user/session rồi gửi qua broker và clientOutboundChannel.

## 8. Cấu hình ba loại prefix cùng nhau

Một cấu hình dễ hiểu dùng các prefix không chồng lấn:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user/");
    }
}
~~~

| Prefix | Nơi xử lý | Ví dụ |
|---|---|---|
| /app | Spring annotated controller | SEND /app/chat.send |
| /topic | Simple broker hoặc external relay | SUBSCRIBE /topic/chat |
| /queue | Simple broker hoặc external relay | SUBSCRIBE /queue/jobs |
| /user/ | UserDestinationMessageHandler rồi tới broker | SUBSCRIBE /user/queue/notifications |

setUserDestinationPrefix("/user/") có thể gọi để ghi rõ quy ước hoặc thay đổi giá trị mặc định. Không đặt cùng một prefix cho application và broker. Ví dụ /app vừa là application prefix vừa là broker prefix sẽ làm luồng routing khó hiểu.

## 9. External broker và nhiều instance

Khi dùng enableStompBrokerRelay, Spring vẫn xử lý /app và /user/; các destination broker được chuyển tiếp tới external broker.

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.setUserDestinationPrefix("/user/");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.internal")
            .setRelayPort(61613)
            .setClientLogin(System.getenv("STOMP_CLIENT_LOGIN"))
            .setClientPasscode(System.getenv("STOMP_CLIENT_PASSWORD"))
            .setSystemLogin(System.getenv("STOMP_SYSTEM_LOGIN"))
            .setSystemPasscode(System.getenv("STOMP_SYSTEM_PASSWORD"));
}
~~~

Kiểm tra broker đã bật STOMP listener, tài khoản relay có quyền SEND/SUBSCRIBE, TLS cho kết nối broker nếu cần, và destination semantics của provider. Destination tạm do user destination tạo ra cần được broker dọn khi session kết thúc.

Trong ứng dụng nhiều Spring node, user có thể kết nối ở node A trong khi event được xử lý ở node B. Node B có thể không biết session của user đang ở A. MessageBrokerRegistry có các tùy chọn setUserDestinationBroadcast(...) và setUserRegistryBroadcast(...) để hỗ trợ chia sẻ thông tin user destination/registry giữa các node.

Khi triển khai nhiều node, cần broker ngoài phù hợp, cấu hình broadcast unresolved user destination khi cần, đồng bộ prefix và user identity giữa các node, kiểm thử reconnect và theo dõi message không phân giải được. Simple broker trong bộ nhớ không tự chia sẻ subscription giữa các instance.

## 10. Bảo mật theo destination prefix

Destination prefix chỉ quyết định routing, không thay thế authentication hoặc authorization.

Một chính sách thường gặp:

- Client đã xác thực được SEND tới /app/**.
- Client được SUBSCRIBE tới topic công khai hoặc topic theo quyền.
- Client chỉ SUBSCRIBE tới /user/queue/** dành cho chính user/session.
- Client không được tự SEND vào destination quản trị hoặc destination nội bộ.
- Server dùng SimpMessagingTemplate để gửi notification tới user theo Principal đã xác thực.

Không cho phép client tùy ý chọn username trong /user/{username}/... rồi coi đó là quyền gửi tới người khác. Server phải xác định user đích từ dữ liệu nghiệp vụ đã kiểm tra và dùng API gửi tới user ở phía server.

Nếu dùng Spring Security, cấu hình message authorization trên STOMP inbound channel. Có thể cho phép SEND /app/** và giới hạn SUBSCRIBE /topic/**, /user/** theo role hoặc ownership. Quy tắc cụ thể phụ thuộc mô hình quyền của ứng dụng.

Cần kiểm tra payload, giới hạn kích thước message, rate limit và quyền trên từng đối tượng nghiệp vụ. Một client có quyền kết nối WebSocket không mặc nhiên được đọc mọi topic.

## 11. Ví dụ hoàn chỉnh: chat broadcast và user reply

Ví dụ dùng Java 17, Spring Boot 3.4.4 và spring-boot-starter-websocket. Ứng dụng có endpoint /ws, application prefix /app, broker prefixes /topic và /queue, user prefix /user/. /app/chat.send broadcast tới /topic/chat; /app/chat.echo trả lời riêng session gửi tới /user/queue/reply.

Simple broker chạy trong bộ nhớ nên không cần cài broker bên ngoài.

Cấu trúc:

~~~text
stomp-prefix-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── StompApplication.java
        │       ├── WebSocketConfiguration.java
        │       ├── ChatMessage.java
        │       └── ChatController.java
        └── resources/
            └── static/
                └── index.html
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>stomp-prefix-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.4</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/StompApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StompApplication {

    public static void main(String[] args) {
        SpringApplication.run(StompApplication.class, args);
    }
}
~~~

### src/main/java/demo/WebSocketConfiguration.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user/");
    }
}
~~~

### src/main/java/demo/ChatMessage.java

~~~java
package demo;

public record ChatMessage(String sender, String content) {
}
~~~

### src/main/java/demo/ChatController.java

~~~java
package demo;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage broadcast(ChatMessage message) {
        return message;
    }

    @MessageMapping("/chat.echo")
    @SendToUser(value = "/queue/reply", broadcast = false)
    public ChatMessage echo(ChatMessage message) {
        return new ChatMessage(
                "server",
                "Private reply: " + message.content()
        );
    }
}
~~~

Lưu ý import: @SendTo thuộc package org.springframework.messaging.handler.annotation; @SendToUser thuộc org.springframework.messaging.simp.annotation.

Method broadcast nhận message qua /app/chat.send, rồi trả kết quả tới /topic/chat. Tất cả client subscribe /topic/chat nhận được message.

Method echo nhận message qua /app/chat.echo, rồi trả kết quả tới /user/queue/reply. broadcast=false giới hạn phản hồi vào session gửi message. Ví dụ không cần đăng nhập để minh họa session-specific reply; ứng dụng thật thường kết hợp user destination riêng tư với authentication và authorization.

### src/main/resources/static/index.html

~~~html
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Spring STOMP Prefix Demo</title>
</head>
<body>
    <h1>Spring STOMP Prefix Demo</h1>
    <button id="send">Send test messages</button>
    <pre id="log"></pre>

    <script type="module">
        import { Client } from "https://cdn.jsdelivr.net/npm/@stomp/stompjs@7.1.1/esm6/index.js";

        const logElement = document.getElementById("log");

        function log(value) {
            logElement.textContent += value + "\n";
        }

        const scheme = location.protocol === "https:" ? "wss" : "ws";
        const client = new Client({
            brokerURL: scheme + "://" + location.host + "/ws",
            reconnectDelay: 5000
        });

        client.onConnect = () => {
            log("STOMP connected");

            client.subscribe("/topic/chat", (frame) => {
                log("broadcast: " + frame.body);
            });

            client.subscribe("/user/queue/reply", (frame) => {
                log("private: " + frame.body);
            });

            document.getElementById("send").disabled = false;
        };

        client.onStompError = (frame) => {
            log("STOMP error: " + frame.headers.message);
        };

        document.getElementById("send").disabled = true;
        document.getElementById("send").addEventListener("click", () => {
            const message = {
                sender: "browser",
                content: "Hello from STOMP"
            };

            client.publish({
                destination: "/app/chat.send",
                body: JSON.stringify(message)
            });

            client.publish({
                destination: "/app/chat.echo",
                body: JSON.stringify(message)
            });
        });

        client.activate();
    </script>
</body>
</html>
~~~

Chạy tại thư mục chứa pom.xml:

~~~shell
mvn spring-boot:run
~~~

Mở http://localhost:8080 trong hai cửa sổ trình duyệt. Nhấn Send test messages ở một cửa sổ.

Cả hai cửa sổ nhận broadcast trên /topic/chat. Chỉ cửa sổ gửi nhận private reply trên /user/queue/reply.

Output dự kiến trong cửa sổ gửi:

~~~text
STOMP connected
broadcast: {"sender":"browser","content":"Hello from STOMP"}
private: {"sender":"server","content":"Private reply: Hello from STOMP"}
~~~

Output dự kiến trong cửa sổ còn lại:

~~~text
STOMP connected
broadcast: {"sender":"browser","content":"Hello from STOMP"}
~~~

Ví dụ kiểm tra ba nhóm destination:

1. /app/chat.send và /app/chat.echo đi vào @MessageMapping.
2. /topic/chat được simple broker quản lý và broadcast tới subscriber.
3. /user/queue/reply được Spring phân giải thành destination riêng của session gửi.

Nếu dùng HTTPS, client tự chọn wss:// dựa trên location.protocol. Trong production, cần cấu hình allowed origins, TLS, authentication và message authorization.

## 12. Những lỗi thường gặp

**Đưa application prefix vào @MessageMapping:** client gửi /app/chat.send, Spring loại bỏ /app trước khi tìm mapping. Annotation phải là /chat.send.

**Dùng WebSocket endpoint làm STOMP destination:** /ws là URL handshake. /app, /topic, /queue và /user/ là destination trong STOMP frame.

**Quên cấu hình application prefix:** nếu controller được thiết kế để nhận /app/** nhưng registry không khai báo application prefix, message có thể đi tới broker thay vì controller.

**Dùng cùng prefix cho application và broker:** các prefix chồng lấn làm luồng routing khó kiểm soát và dễ chuyển message tới sai handler.

**Đăng ký /user/ như broker prefix thông thường:** user destination cần được UserDestinationMessageHandler phân giải trước. Để broker prefix không bắt nhầm /user/.

**Cho rằng /queue của simple broker là queue thật:** simple broker dùng destination name và subscription matching trong bộ nhớ. Nó không cung cấp toàn bộ semantics của queue broker chuyên dụng.

**Cho rằng /topic và /queue có ý nghĩa giống nhau ở mọi broker:** destination semantics phụ thuộc broker. Kiểm tra tài liệu STOMP của broker khi dùng relay.

**Subscribe /user/{username}/queue/... ở client:** client thông thường subscribe /user/queue/.... Username được dùng ở phía server khi gửi tới user cụ thể.

**Truyền /user/ vào convertAndSendToUser:** tham số destination của convertAndSendToUser là phần phía sau user prefix, ví dụ /queue/notifications.

**Lấy username từ payload để gửi message riêng:** danh tính user cần đến từ Principal đã xác thực hoặc dữ liệu server đã kiểm chứng. Client có thể giả mạo username trong JSON.

**Nghĩ user destination tự động xác thực user:** /user/ chỉ định tuyến message theo user/session. Nó không đăng nhập người dùng hoặc cấp quyền truy cập.

**Không xử lý nhiều session của cùng user:** mặc định một user destination có thể gửi tới nhiều session đang đăng ký. Dùng broadcast=false nếu chỉ cần phản hồi session nguồn.

**Dùng simple broker cho hệ thống nhiều node:** simple broker trong bộ nhớ không chia sẻ subscription giữa các instance. Dùng broker relay và cấu hình user registry/broadcast phù hợp khi cần mở rộng.

**Không kiểm soát quyền SEND/SUBSCRIBE:** prefix không phải authorization. Cấu hình Spring Security để giới hạn client được gửi và đăng ký destination nào.

## 13. Checklist thiết kế destination

- URL handshake WebSocket được tách riêng khỏi STOMP destination.
- Application prefix chỉ dành cho message cần xử lý bởi @MessageMapping.
- Các annotation @MessageMapping không lặp lại application prefix.
- Broker prefixes chỉ gồm destination broker thực sự quản lý.
- User prefix mặc định /user/ được giữ riêng để Spring phân giải.
- Không để application và broker prefixes chồng lấn.
- @SendTo trỏ tới destination thuộc broker prefix.
- Client subscribe /user/queue/... để nhận message riêng.
- Server dùng convertAndSendToUser(username, "/queue/...", payload) khi gửi tới user cụ thể.
- Principal đến từ cơ chế authentication đã cấu hình.
- Đã quyết định cách xử lý nhiều session của cùng user.
- Đã chọn simple broker hay external broker relay theo yêu cầu về clustering, ACK, RECEIPT và durability.
- Đã kiểm tra semantics destination của broker cụ thể.
- Spring Security giới hạn SEND và SUBSCRIBE theo quyền.
- Có integration test cho broadcast, private reply, reconnect và nhiều session.

## 14. Ghi nhớ

- /app là application destination prefix; Spring loại bỏ prefix rồi route phần còn lại tới @MessageMapping.
- /topic và /queue là broker destination prefixes; chúng được cấu hình bằng enableSimpleBroker hoặc enableStompBrokerRelay.
- Trong simple broker, /topic và /queue là quy ước tên, không tự tạo semantics queue/topic bền vững như broker chuyên dụng.
- /user/ là user destination prefix mặc định; UserDestinationMessageHandler chuyển destination logic thành destination riêng theo user/session.
- Client thường gửi SEND tới /app/..., SUBSCRIBE tới /topic/... hoặc /user/queue/....
- Server có thể gửi tới user bằng convertAndSendToUser(username, "/queue/...", payload).
- @SendTo định tuyến kết quả tới broker destination; @SendToUser định tuyến kết quả tới user/session.
- /ws là URL handshake, không phải STOMP destination prefix.
- Prefix chỉ quyết định routing; authentication và authorization vẫn cần được cấu hình riêng.
- Khi dùng nhiều instance, cần broker chia sẻ và cơ chế user destination phù hợp để message tới đúng session.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Enable STOMP](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/enable.html)
- [Spring Framework 6.2 — Flow of Messages](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/message-flow.html)
- [Spring Framework 6.2 — User Destinations](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/user-destination.html)
- [Spring Framework 6.2 — External Broker and Broker Relay](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/handle-broker-relay.html)
- [MessageBrokerRegistry Javadoc — Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/simp/config/MessageBrokerRegistry.html)
- [MessageMapping Javadoc — Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/handler/annotation/MessageMapping.html)
- [SendTo Javadoc — Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/handler/annotation/SendTo.html)
