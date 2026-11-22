# @MessageMapping, @SendTo, @SendToUser và SimpMessagingTemplate trong Spring WebSocket/STOMP

## 1. Vai trò của từng thành phần

STOMP over WebSocket cho phép trình duyệt và server trao đổi message qua một kết nối WebSocket. Trong Spring Framework, bốn thành phần thường làm việc cùng nhau:

- `@MessageMapping`: ánh xạ STOMP message đến method của một Spring `@Controller` dựa trên destination; tương tự ý tưởng route HTTP nhưng dành cho messaging.
- `@SendTo`: lấy **giá trị trả về** từ message handler, convert thành message và gửi tới destination do broker quản lý; điển hình là topic cho nhiều subscriber.
- `@SendToUser`: lấy **giá trị trả về** và gửi tới logical user destination của người dùng/session đã gửi request; có tùy chọn chỉ gửi cho session nguồn.
- `SimpMessagingTemplate`: chủ động gửi message từ service, scheduler, listener, HTTP controller hoặc bất kỳ Spring bean nào, không phụ thuộc việc method đang xử lý STOMP message.

Chúng giải quyết các vấn đề khác nhau: **nhận command**, **phát kết quả chung**, **trả riêng**, và **chủ động publish**.

Ví dụ nghiệp vụ:

- Chat: client gửi message, tất cả người trong room nhận cập nhật.
- Form tính giá: tab đang gửi request chỉ nhận kết quả của riêng mình.
- Đơn hàng: sau khi admin thay đổi trạng thái bằng HTTP, server phát thông báo tới client đang subscribe.
- Notification cá nhân: service gửi tới các session WebSocket của một authenticated user.

Đừng nhầm STOMP destination với URL HTTP. `SEND /app/chat` là một STOMP frame; `POST /app/chat` là HTTP request và không tự kích hoạt `@MessageMapping("/chat")`.

## 2. Cấu hình STOMP và đường đi của message

Một cấu hình cơ bản:

~~~java
@Configuration
@EnableWebSocketMessageBroker
class BrokerConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}
~~~

Ý nghĩa của các prefix:

| Destination | Ai xử lý? | Mục đích |
| --- | --- | --- |
| `/ws` | HTTP/WebSocket handshake handler | Client mở kết nối WebSocket và thương lượng STOMP. |
| `/app/chat` | Application controller | STOMP `SEND` được route tới `@MessageMapping("/chat")`. |
| `/topic/chat` | Message broker | Client `SUBSCRIBE`; nhận các message broadcast tới topic. |
| `/queue/updates` | Message broker | Broker destination; tên `queue` không tự bảo đảm durability. |
| `/user/queue/replies` | `UserDestinationMessageHandler` | Client subscribe destination riêng theo user/session. |

`/app` thường được bỏ trước khi so khớp với `@MessageMapping`; trong khi `/topic` và `/queue` chuyển message tới broker. `/user` là prefix để Spring **biến đổi user destination** thành destination nội bộ có gắn session; không thêm `/user` vào `enableSimpleBroker` cùng `/topic`/`/queue`.

Luồng phát broadcast:

~~~text
Browser A                         Spring application                  Browser B
    |                                     |                               |
    | -- SUBSCRIBE /topic/chat ---------> | broker lưu subscription       |
    |                                     | <--- SUBSCRIBE /topic/chat -- |
    | -- SEND /app/chat ----------------> |                               |
    |                          clientInboundChannel                      |
    |                             @MessageMapping("/chat")                |
    |                                @SendTo("/topic/chat")                |
    |                          brokerChannel -> simple broker             |
    | <--- MESSAGE /topic/chat ---------- | -------- MESSAGE -----------> |
~~~

Các kênh quan trọng: `clientInboundChannel` nhận STOMP frame, `brokerChannel` chuyển message từ ứng dụng tới broker, `clientOutboundChannel` phân phối ra các WebSocket sessions. Một message được gửi vào broker chưa đồng nghĩa mọi người dùng đã đọc hoặc xác nhận message.

**Simple broker** phù hợp demo và triển khai nhỏ trên một JVM. Khi cần liên thông nhiều server instances, durable delivery hoặc broker ngoài, cần kiến trúc bổ sung, xem phần cuối.

## 3. @MessageMapping: ánh xạ destination và đọc payload

Ví dụ:

~~~java
@Controller
class ChatController {
    @MessageMapping("/chat")
    public void accept(ChatInput input) {
        // Nhận STOMP SEND /app/chat và xử lý input.
    }
}
~~~

Client STOMP gửi:

~~~text
SEND
destination:/app/chat
content-type:application/json

{"text":"hello"}^@
~~~

`^@` trong đoạn minh họa đại diện byte NUL kết thúc STOMP frame. Thư viện STOMP client sẽ xử lý protocol framing; không cần tự nối ký tự đó vào JSON.

`@Controller` messaging hỗ trợ một số tham số hữu ích:

- `ChatInput input` hoặc `@Payload ChatInput input`: deserialize body bằng `MessageConverter` phù hợp, thường JSON; `@Payload` có thể được suy ra.
- `@DestinationVariable String roomId`: lấy biến từ destination template, ví dụ `@MessageMapping("/rooms/{roomId}/post")`.
- `@Header("simpSessionId") String id`, `MessageHeaders`, `StompHeaderAccessor`: truy cập headers/session metadata nếu có.
- `Principal principal`: danh tính được gắn với handshake WebSocket đã xác thực; có thể `null` nếu kết nối anonymous.
- `@Valid Request request`: kiểm tra Bean Validation nếu dependency/cấu hình hỗ trợ, ví dụ `spring-boot-starter-validation` khi dùng Spring Boot.

Ví dụ room động:

~~~java
@MessageMapping("/rooms/{roomId}/post")
public void post(@DestinationVariable String roomId,
                 ChatInput message,
                 Principal principal) {
    // Kiểm tra principal được quyền tham gia roomId.
    // Sau đó mới gọi service và publish tới room tương ứng.
}
~~~

Client gửi `SEND /app/rooms/42/post`. Destination template được ánh xạ theo path; **roomId do client đưa vào không chứng minh quyền truy cập**. Server vẫn phải kiểm tra membership, tenant và authorization.

`@MessageMapping` cũng có thể đặt ở class level để chia sẻ prefix. Các annotation xử lý STOMP không thay thế `@GetMapping`/`@PostMapping` cho REST.

## 4. @SendTo: phát kết quả cho subscriber của destination

Nếu `@MessageMapping` trả về đối tượng, `@SendTo` xác định nơi Spring chuyển đối tượng đó thành message:

~~~java
@Controller
class ChatHandler {
    @MessageMapping("/chat")
    @SendTo("/topic/chat")
    public ChatEvent handle(ChatInput input) {
        return new ChatEvent("message", input.text());
    }
}
~~~

Giả sử cả hai browser A và B subscribe `/topic/chat`. A gửi `SEND /app/chat` với body `{"text":"hi"}`. Server gọi method, convert return value `ChatEvent`, gửi tới `/topic/chat`; broker phát cho các subscriber, bao gồm A nếu A đã subscribe. **@SendTo không mặc định chỉ gửi cho request sender.**

Có thể gửi đến nhiều destination:

~~~java
@MessageMapping("/metrics")
@SendTo({"/topic/metrics", "/topic/dashboard"})
public MetricUpdated publish(MetricRequest request) {
    return new MetricUpdated(request.name(), request.value());
}
~~~

Làm vậy chỉ khi hai nhóm subscriber thực sự cần cùng dữ liệu; với dữ liệu nhạy cảm, broadcast nhầm destination sẽ làm lộ thông tin.

### Nếu bỏ @SendTo thì sao?

Trong cấu hình phổ biến, Spring có thể suy ra default destination cho giá trị trả về của `@MessageMapping("/hello")` là `/topic/hello`. Tuy vậy nên khai báo `@SendTo` khi muốn contract outbound tường minh, nhất là khi inbound `/app/order/submit` nhưng outbound là `/topic/orders`.

Annotation này phát **return value**. Với method trả `void`, không có object để Spring tự động phát. Muốn chủ động gửi trong method `void`, dùng `SimpMessagingTemplate`.

## 5. @SendToUser: reply theo user hoặc theo đúng session

`@SendToUser` dùng khi response không nên được broadcast tới tất cả subscriber của một public topic:

~~~java
@MessageMapping("/quote")
@SendToUser("/queue/quotes")
public QuoteResult quote(QuoteRequest input, Principal principal) {
    return quotationService.calculate(input, principal);
}
~~~

Client subscribe **`/user/queue/quotes`**, còn annotation khai báo `/queue/quotes`. Spring tự resolve prefix `/user` theo user/session; không viết `@SendToUser("/user/queue/quotes")` khi dùng quy ước cấu hình ở phần 2.

### broadcast=true và broadcast=false

Nếu một authenticated user mở nhiều tab:

| Cách dùng | Phạm vi |
| --- | --- |
| `@SendToUser("/queue/quotes")` | Mặc định `broadcast=true`: gửi tới các session của cùng user đã subscribe. |
| `@SendToUser(value="/queue/replies", broadcast=false)` | Chỉ session gửi STOMP message đang được xử lý. |
| `@SendToUser(value="/queue/errors", broadcast=false)` trên error handler | Gửi lỗi riêng cho tab gây lỗi, không báo lỗi sang các tab khác. |

Ví dụ request–reply tại tab nguồn:

~~~java
@MessageMapping("/calculate")
@SendToUser(value = "/queue/replies", broadcast = false)
public CalculationResult calculate(CalculationCommand command) {
    return calculator.execute(command);
}
~~~

Client gửi `SEND /app/calculate` sau khi subscribe `/user/queue/replies`. Nếu user alice có tab A và B cùng kết nối, A gửi command thì chỉ A nhận reply của method này.

**Anonymous sessions:** Spring vẫn có thể hỗ trợ user destination trong session chưa có authenticated principal. Khi đó `@SendToUser` vận hành như `broadcast=false`, chỉ hướng đến session đã gửi message; không có khả năng tự tìm “những tab khác của cùng user” khi hệ thống chưa xác định được user.

### Spring làm gì với /user?

~~~text
Alice, session S1: SUBSCRIBE /user/queue/inbox
    -> Spring resolve thành destination nội bộ duy nhất cho S1

Alice, session S2: SUBSCRIBE /user/queue/inbox
    -> destination nội bộ riêng cho S2

Bob, session S3: SUBSCRIBE /user/queue/inbox
    -> destination nội bộ riêng cho S3

Server chủ động gửi cho username "alice":
    -> Spring có thể resolve tới S1 và S2 nếu đang kết nối/subscribe.
~~~

Định dạng destination nội bộ được Spring quản lý; không phụ thuộc vào hậu tố session cụ thể khi viết code nghiệp vụ. User destination là **routing convenience**, không tự cung cấp xác thực, quyền truy cập, offline message storage hoặc encryption ngoài transport.

### @MessageExceptionHandler phối hợp @SendToUser

~~~java
@MessageExceptionHandler(IllegalArgumentException.class)
@SendToUser(value = "/queue/errors", broadcast = false)
public ErrorEvent invalidCommand(IllegalArgumentException ex) {
    return new ErrorEvent("INVALID_COMMAND", ex.getMessage());
}
~~~

Spring Messaging gọi `@MessageExceptionHandler` khi controller STOMP phát sinh lỗi phù hợp. Client subscribe `/user/queue/errors` để nhận response. Đây là cơ chế của messaging controller, khác `@ExceptionHandler` cho HTTP request. Tránh trả stack trace hoặc thông tin hệ thống nhạy cảm trong error payload.

## 6. SimpMessagingTemplate: phát chủ động từ service và HTTP

`SimpMessagingTemplate` cho phép bất kỳ Spring bean nào gửi message vào hệ thống broker mà không cần một inbound STOMP frame.

### Public broadcast

~~~java
@Service
class StatusPublisher {
    private final SimpMessagingTemplate template;

    StatusPublisher(SimpMessagingTemplate template) {
        this.template = template;
    }

    public void publish(StatusChanged event) {
        template.convertAndSend("/topic/status", event);
    }
}
~~~

`convertAndSend` dùng configured message converter để tạo payload, rồi gửi vào messaging channel. Nó không bảo đảm message đã hiển thị trên UI hoặc đã được lưu bền vững sau khi lời gọi trả về.

Một HTTP endpoint cũng có thể phát sự kiện:

~~~java
@RestController
class UpdateApi {
    private final SimpMessagingTemplate template;

    UpdateApi(SimpMessagingTemplate template) {
        this.template = template;
    }

    @PostMapping("/api/announce")
    ResponseEntity<Void> announce(@RequestBody Announcement request) {
        template.convertAndSend("/topic/announcements", request);
        return ResponseEntity.accepted().build();
    }
}
~~~

`HTTP 202` là kết quả xử lý phía HTTP, không phải xác nhận mọi WebSocket client đã nhận message. Khi nghiệp vụ cần audit/ack/retry đáng tin cậy, thiết kế thêm cơ chế khác.

### Gửi một user từ backend

~~~java
@Service
class InboxService {
    private final SimpMessagingTemplate template;

    InboxService(SimpMessagingTemplate template) {
        this.template = template;
    }

    public void notifyAuthenticatedUser(
            String authenticatedUsername, InboxEvent event) {
        template.convertAndSendToUser(
                authenticatedUsername, "/queue/inbox", event);
    }
}
~~~

Client của authenticated user subscribe `/user/queue/inbox`. `convertAndSendToUser("alice","/queue/inbox", event)` biểu đạt logic tương đương phát đến user destination `/user/alice/queue/inbox` theo prefix mặc định, nhưng API rõ ràng và đỡ nối chuỗi sai.

**Không lấy authenticatedUsername từ một STOMP payload do client tự khai báo rồi gửi dữ liệu riêng tư tới user đó mà chưa xác minh quyền.** Danh tính phải từ `Principal` hoặc nguồn server-side đáng tin, và vẫn phải kiểm tra quyền nghiệp vụ của sender với recipient/resource.

Có thể có nhiều session của cùng user; gửi theo username thông thường nhắm đến các session của user đang subscribe, không nhất thiết đúng một tab. Nếu phải nhắm một session cụ thể ngoài message handler, cần định tuyến dựa trên session ID/header đúng cách và kiểm tra kỹ cơ chế user destination.

### Sau database commit

Nếu phát notification trước khi transaction lưu dữ liệu commit mà transaction bị rollback, client nhận một sự kiện “ảo”. Có thể tách sự kiện sau commit:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void onOrderChanged(OrderChanged event) {
    template.convertAndSend("/topic/orders", event);
}
~~~

Đoạn trên chỉ minh họa cách gắn listener với transaction đang tồn tại; cần listener bean, event publisher và transaction infrastructure. Phát sau commit **không bảo đảm durable delivery** trong trường hợp process sập sau commit nhưng trước lúc gửi; hệ thống đòi hỏi độ tin cậy cao nên xét transactional outbox/event log.

## 7. So sánh API và chọn đúng cách

| Mục tiêu | Lựa chọn | Lưu ý |
| --- | --- | --- |
| Nhận `SEND /app/...` | `@MessageMapping` | Handler nhận và xử lý input; chưa tự broadcast nếu không trả giá trị hoặc gửi message. |
| Return value đến mọi người subscribe một topic | `@SendTo("/topic/...")` | Ai subscribe hợp lệ cũng có thể nhận. |
| Return value đến các session của người gửi | `@SendToUser("/queue/...")` | Theo authenticated user; mặc định broadcast nhiều session. |
| Return value đến đúng session nguồn | `@SendToUser(value="/queue/...",broadcast=false)` | Hữu ích cho reply và error riêng của một tab. |
| Chủ động phát từ business service/HTTP/scheduler | `template.convertAndSend(destination,payload)` | Không cần inbound STOMP message. |
| Gửi thông báo cho user có username đã xác thực | `template.convertAndSendToUser(username,"/queue/...",payload)` | Client subscribe `/user/queue/...`; cần auth và user registry phù hợp. |

Chọn theo **ai khởi tạo sự kiện** và **người nào phải nhận**, không theo kích thước JSON hay tên annotation trông ngắn hơn.

## 8. Demo hoàn chỉnh với Java 17 và Spring Boot 3.x

Demo chạy Spring MVC + STOMP simple broker trên một instance. Ba chức năng:

1. `SEND /app/hello` → `@MessageMapping` → `@SendTo("/topic/news")`: broadcast mọi tab đã subscribe.
2. `SEND /app/echo` → `@SendToUser(..., broadcast=false)`: chỉ tab nguồn nhận.
3. `POST /api/announcements` → `SimpMessagingTemplate.convertAndSend(...)`: broadcast từ HTTP controller.

Để demo tự chạy dễ nhất, chưa thêm Spring Security; `@SendToUser(broadcast=false)` vẫn dùng được theo **session anonymous**. Ví dụ `convertAndSendToUser(username,...)` cho authenticated user đã có riêng ở phần 6.

### 8.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>stomp-routing</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
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

### 8.2. src/main/java/demo/StompRoutingApplication.java

Toàn bộ code Java sau lưu trong **một file**. Chỉ class main là `public`; các class/record khác package-private là hợp lệ trong Java 17.

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.ResponseEntity;
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@SpringBootApplication
public class StompRoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(StompRoutingApplication.class, args);
    }
}

record Input(String text) {}
record Event(String type, String text) {}

@Configuration
@EnableWebSocketMessageBroker
class BrokerConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}

@Controller
class CommandController {
    @MessageMapping("/hello")
    @SendTo("/topic/news")
    Event hello(Input input) {
        return new Event("hello", checked(input));
    }

    @MessageMapping("/echo")
    @SendToUser(value = "/queue/replies", broadcast = false)
    Event echo(Input input) {
        return new Event("reply", "Echo: " + checked(input));
    }

    @MessageExceptionHandler(IllegalArgumentException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    Event invalid(IllegalArgumentException error) {
        return new Event("error", error.getMessage());
    }

    static String checked(Input input) {
        if (input == null || input.text() == null
                || input.text().isBlank() || input.text().length() > 500) {
            throw new IllegalArgumentException(
                    "text must contain 1..500 characters");
        }
        return input.text().trim();
    }
}

@RestController
class AnnouncementController {
    private final SimpMessagingTemplate template;

    AnnouncementController(SimpMessagingTemplate template) {
        this.template = template;
    }

    @PostMapping("/api/announcements")
    ResponseEntity<Void> announce(@RequestBody Input input) {
        if (input == null || input.text() == null
                || input.text().isBlank() || input.text().length() > 500) {
            return ResponseEntity.badRequest().build();
        }

        template.convertAndSend("/topic/news",
                new Event("announcement", input.text().trim()));
        return ResponseEntity.accepted().build();
    }
}
~~~

Trong demo:

- `@SendTo("/topic/news")` phát return value, ngay cả khi method không trực tiếp thao tác template.
- `@SendToUser(... broadcast=false)` chỉ trả lời session đã gửi lệnh `/app/echo`.
- `@MessageExceptionHandler` có thể gửi lỗi riêng vào `/user/queue/errors` khi handler ném `IllegalArgumentException`.
- `@PostMapping` là HTTP endpoint, gọi template để phát một message mà không cần inbound STOMP command.
- `Event` là record Java, Jackson sẽ serialize thành JSON thông qua converters do Spring Boot cung cấp.
- `ResponseEntity.accepted()` ở HTTP chỉ xác nhận server xử lý yêu cầu phát tin; không xác nhận các browser đã nhận.

### 8.3. src/main/resources/static/index.html

HTML sau dùng UMD của `@stomp/stompjs`. Trình duyệt cần Internet để tải script CDN; hoặc tải thư viện bằng npm và phục vụ bản build nội bộ nếu muốn chạy offline.

~~~html
<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <title>Spring STOMP demo</title>
</head>
<body>
    <h1>STOMP demo</h1>
    <input id="text" value="Xin chào">
    <button id="hello">Broadcast</button>
    <button id="echo">Reply to this tab</button>
    <button id="announce">Publish from HTTP</button>
    <pre id="log"></pre>

    <script src="https://cdn.jsdelivr.net/npm/@stomp/stompjs@7.2.0/bundles/stomp.umd.min.js"></script>
    <script>
        const input = document.getElementById("text");
        const logPanel = document.getElementById("log");
        const log = value => {
            logPanel.textContent += value + "\n";
        };

        const protocol = location.protocol === "https:" ? "wss://" : "ws://";
        const client = new StompJs.Client({
            brokerURL: protocol + location.host + "/ws",
            reconnectDelay: 3000,
            onConnect: () => {
                log("CONNECTED");
                client.subscribe("/topic/news", message => {
                    log("TOPIC: " + message.body);
                });
                client.subscribe("/user/queue/replies", message => {
                    log("REPLY: " + message.body);
                });
                client.subscribe("/user/queue/errors", message => {
                    log("ERROR: " + message.body);
                });
            },
            onStompError: frame => {
                log("STOMP ERROR: " + (frame.headers.message || "unknown"));
            }
        });
        client.activate();

        function send(destination) {
            if (!client.connected) {
                log("STOMP not connected yet");
                return;
            }
            client.publish({
                destination: destination,
                body: JSON.stringify({ text: input.value })
            });
        }

        document.getElementById("hello").onclick = () => {
            send("/app/hello");
        };
        document.getElementById("echo").onclick = () => {
            send("/app/echo");
        };
        document.getElementById("announce").onclick = async () => {
            try {
                const response = await fetch("/api/announcements", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ text: input.value })
                });
                log("HTTP status: " + response.status);
            } catch (error) {
                log("HTTP request failed: " + error);
            }
        };

        // Khi rời màn hình: await client.deactivate();
    </script>
</body>
</html>
~~~

Code thêm mọi subscription trong `onConnect`: khi STOMP client reconnect, callback lại chạy và subscribe trên connection mới. Dùng `textContent` giúp không render nội dung không tin cậy dưới dạng HTML.

### 8.4. Khởi chạy và kết quả

Dùng JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Mở `http://localhost:8080/`, chờ trạng thái `CONNECTED` rồi thử nút:

1. **Broadcast:** gửi `/app/hello`, log `TOPIC: {"type":"hello","text":"Xin chào"}`. Mở thêm tab đã subscribe và gửi lại, cả hai tab nhận broadcast.
2. **Reply to this tab:** gửi `/app/echo`, log chỉ trên tab gửi là `REPLY: {"type":"reply","text":"Echo: Xin chào"}`. Tab kia không nhận reply này.
3. **Publish from HTTP:** browser POST `/api/announcements`, nhận `HTTP status: 202`, đồng thời các tab subscribe topic nhận message với `"type":"announcement"`.
4. **Lỗi:** xóa input rồi nhấn **Reply to this tab**. Handler từ chối text rỗng, session nguồn nhận message ở `/user/queue/errors` khi error handler được gọi.

JSON ví dụ thể hiện các trường chính; việc thứ tự field khi serialize không phải contract của transport.

Có thể gọi HTTP trực tiếp bằng một lệnh (dành cho terminal hỗ trợ curl CLI):

~~~bash
curl -i -X POST http://localhost:8080/api/announcements -H "Content-Type: application/json" -d '{"text":"Update from API"}'
~~~

HTTP response có status 202, còn message broadcast được đẩy tới các subscription WebSocket. Với Windows PowerShell, `curl` có thể là alias; dùng `curl.exe` và cách quote JSON phù hợp với shell.

**Chú ý thứ tự:** simple broker không lưu lại event gửi trước khi subscription bắt đầu. Hãy chờ STOMP connect và subscribe hoạt động trước khi test. Ví dụ này minh họa mapping và routing, không phải đảm bảo delivery/ack hoặc benchmark.

## 9. Các lỗi thường gặp

### 9.1. Gửi sai destination

- Client `SEND /topic/chat` rồi chờ method `@MessageMapping("/chat")` chạy: sai nếu app prefix là `/app`.
- Client phải `SEND /app/chat`; server `@SendTo("/topic/chat")`; subscriber nghe `/topic/chat`.
- Với user reply, client nghe `/user/queue/replies`, server `@SendToUser("/queue/replies")`.

### 9.2. Dùng @SendTo để gửi dữ liệu riêng tư

`@SendTo` phát đến broker destination; nếu người không đủ quyền có thể subscribe topic, họ có thể nhận dữ liệu. Chọn user destination và áp dụng Spring Security message authorization/kiểm tra quyền nghiệp vụ trước khi gửi.

### 9.3. Nhầm username với session

`@SendToUser(broadcast=false)` nhắm session đã gọi handler; `convertAndSendToUser(username, ...)` nhắm user theo registry và có thể fan-out nhiều session. Nếu đòi hỏi đúng một tab, phải xác định session rõ ràng.

### 9.4. Nghĩ dùng tên /queue là có durable queue

Simple broker không cung cấp persistence, clustering, offline queue, replay hay đảm bảo exactly once. Với độ tin cậy cao cần broker ngoài và/hoặc lưu nghiệp vụ bằng database/outbox.

### 9.5. Tưởng template gửi thành công nghĩa client đã đọc

`convertAndSend` đi vào hệ thống message channel; không phải browser acknowledgement. Với nghiệp vụ quan trọng cần ứng dụng tự gắn message ID, theo dõi trạng thái, thiết kế retry/deduplication và xử lý offline.

### 9.6. Handler xử lý blocking quá lâu

STOMP message handlers chạy thông qua inbound channels/executors. Gọi I/O hoặc DB nặng trên chúng mà không giới hạn có thể gây queue và tăng latency. Đo độ trễ handler, inbound/outbound queues và memory; điều chỉnh threading và backpressure theo tải thực tế.

### 9.7. Không subscribe lại khi reconnect

WebSocket/STOMP session mới không kế thừa mọi subscription từ connection cũ. StompJS thường cần subscribe trong `onConnect` và thực hiện đồng bộ snapshot/missed events sau reconnect.

## 10. Bảo mật, scale và production

**Authentication/authorization:** Mô hình browser thường kế thừa authenticated user từ HTTP/WebSocket handshake. Không tự tin header `login`/`passcode` trong STOMP `CONNECT` để xác minh danh tính nếu chưa cấu hình cơ chế nhận token riêng. Phải kiểm tra quyền `SEND`/`SUBSCRIBE` theo destination, giới hạn topic, kiểm tra từng room/order/tenant trong business layer, rate limit và payload validation. Nếu dùng Spring Security, xem cấu hình message authorization và CSRF/origin cho WebSocket.

**SimpMessagingTemplate và transaction:** Đối với sự kiện DB, nên phát sau commit hoặc thông qua outbox để tránh event sai nếu transaction rollback. Sự kiện quan trọng cần mô hình persisted state và retry, không chỉ dựa trên socket đang mở.

**Nhiều instance:** `enableSimpleBroker` lưu subscription nội bộ một JVM. Nếu có replica A và B, việc gửi ở A không mặc nhiên đến user đang kết nối ở B. Dùng STOMP broker relay với broker phù hợp hoặc message backplane và user-registry phối hợp; thiết kế scale phụ thuộc tải và durability mong muốn.

**Định tuyến user:** Trong hệ thống nhiều node, việc tìm user/session có thể cần hỗ trợ user destination broadcast hoặc shared user registry; xác định rõ behavior khi user chưa online và khi cùng một user có nhiều sessions.

**Giới hạn tài nguyên:** Theo dõi active WebSocket sessions, message sizes, send queue, latency, reconnect count, lỗi gửi và slow clients. Heartbeat, timeouts, giới hạn outbound buffer, backoff và dọn session là yêu cầu vận hành quan trọng.

## 11. Checklist trước khi tích hợp

- [ ] `/ws` là endpoint handshake, `/app` là prefix controller, `/topic`/`/queue` dành cho broker, `/user` được Spring resolve riêng.
- [ ] Client gửi STOMP `SEND` bằng thư viện tương thích STOMP; không gửi JSON raw tới STOMP handler.
- [ ] `@MessageMapping` có đúng destination và converter/DTO/validation.
- [ ] `@SendTo` chỉ phát dữ liệu phù hợp với tất cả subscribers của topic.
- [ ] `@SendToUser` chọn đúng `broadcast`: cùng user nhiều session hay đúng session đã gửi.
- [ ] `SimpMessagingTemplate` được inject ở service cho thông báo phát sinh từ HTTP, scheduler hoặc nghiệp vụ khác.
- [ ] Auth, authorization theo user/room, input validation, rate limiting và logging an toàn được triển khai.
- [ ] Có chiến lược reconnect, resubscribe, snapshot/replay nếu cần, offline notification và delivery semantics.
- [ ] Đã load test với số lượng session/message thật và topology nhiều replica nếu dùng.

**Quy tắc ghi nhớ:** `@MessageMapping` **nhận**; `@SendTo` **phát cho subscriber**; `@SendToUser` **trả về user/session**; `SimpMessagingTemplate` **chủ động gửi từ ứng dụng**. Những lựa chọn này xác định đường đi của message; độ tin cậy, quyền và bảo mật là các lớp cần thiết kế tiếp.

## 12. Nguồn tham khảo chính thức

- Spring Framework — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html
- Spring Framework — User Destinations: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html
- Spring Framework — Sending Messages: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html
- Spring Framework — Enable STOMP: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html
- Spring Framework — Message Flow: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html
- Spring Framework — Authorization: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html
- StompJS — Browser Client & UMD Bundle: https://stomp-js.github.io/guide/stompjs/using-stompjs-v5.html
