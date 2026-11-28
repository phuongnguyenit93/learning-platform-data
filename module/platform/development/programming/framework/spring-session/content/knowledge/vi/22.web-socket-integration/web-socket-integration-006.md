# Thông điệp đến, heartbeat, thông điệp gửi đi và cách xác định không hoạt động

Khi kết hợp Spring Session với WebSocket/STOMP, một kết nối có thể tồn tại lâu hơn một HTTP request thông thường. Trình duyệt gửi cookie session khi bắt tay kết nối; sau đó dữ liệu được trao đổi qua WebSocket mà không cần gửi lại cookie trong từng frame. Vì vậy, ứng dụng cần phân biệt hoạt động của kết nối, hoạt động của giao thức STOMP, thông điệp nghiệp vụ và thời gian không hoạt động của HTTP session.

Spring Session có thể theo dõi các WebSocket connection gắn với một HTTP session và cập nhật thời điểm truy cập khi nhận thông điệp từ client thông qua tích hợp WebSocket tương ứng. Điều này giúp session dùng chung trong Redis hoặc JDBC tiếp tục được gia hạn khi client thực sự gửi dữ liệu. Tuy nhiên, thông điệp gửi từ server và heartbeat ở tầng giao thức không nhất thiết được tính là hoạt động nghiệp vụ hoặc làm mới idle timeout của session.

## 1. Phân biệt bốn loại hoạt động

Trong một kết nối WebSocket dùng STOMP, có ít nhất bốn khái niệm cần tách biệt:

1. **Thông điệp đến (inbound message):** frame STOMP hoặc message do client gửi vào ứng dụng, ví dụ gửi tin nhắn, cập nhật trạng thái hoặc yêu cầu đăng ký.
2. **Heartbeat:** tín hiệu định kỳ để hai đầu biết kết nối/giao thức còn hoạt động. WebSocket ping/pong và STOMP heartbeat là hai cơ chế khác nhau.
3. **Thông điệp gửi đi (outbound message):** dữ liệu server đẩy về client, ví dụ tin nhắn mới, thông báo hoặc cập nhật trạng thái.
4. **Không hoạt động (inactivity):** khoảng thời gian không có hoạt động được tính theo một chính sách cụ thể, chẳng hạn idle timeout của HTTP session hoặc thời gian không nhận heartbeat.

Một kết nối có thể vẫn mở ở tầng TCP/WebSocket trong khi HTTP session đã hết hạn. Ngược lại, một người dùng có thể không gửi thông điệp nghiệp vụ nhưng vẫn trả lời heartbeat, khiến kết nối được xem là còn sống. Không dùng một bộ đếm last activity duy nhất để đại diện cho tất cả các khái niệm này.

| Hoạt động | Cho biết điều gì? | Có tự động làm mới Spring Session không? |
| --- | --- | --- |
| Client gửi thông điệp STOMP đến ứng dụng | Client đang gửi dữ liệu qua kênh WebSocket | Tích hợp Spring Session WebSocket có thể cập nhật last accessed time khi nhận inbound message |
| WebSocket ping/pong | Kết nối transport còn phản hồi | Không nên giả định nó cập nhật HTTP session |
| STOMP heartbeat | Đầu bên kia còn hoạt động ở tầng STOMP | Không nên giả định heartbeat được chuyển thành application message hoặc làm mới session |
| Server gửi thông điệp đến client | Server có dữ liệu cần đẩy ra | Không làm mới last accessed time của session chỉ vì server gửi |
| Client đóng kết nối | Kết nối không còn được duy trì | Có thể phát sinh sự kiện disconnect; việc đóng socket và việc hết hạn session là hai vòng đời riêng |

## 2. Luồng WebSocket và HTTP session

Ban đầu, client thực hiện HTTP handshake đến endpoint WebSocket. Cookie session được gửi cùng request handshake và Spring Security có thể xác định principal đã đăng nhập. Sau khi nâng cấp thành WebSocket, các message tiếp theo được gửi trên kết nối đã mở.

Với Spring Session WebSocket integration, session HTTP được liên kết với WebSocket connection. Spring Session có thể lưu dấu các connection này và đóng chúng khi HTTP session bị hủy. SessionRepositoryMessageInterceptor hỗ trợ cập nhật last accessed time của session khi có message đến từ client.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant W as WebSocket/STOMP
    participant I as Spring Session interceptor
    participant R as SessionRepository
    participant A as Application handler

    B->>W: HTTP handshake + session cookie
    W->>R: Tải HTTP session
    W-->>B: Upgrade thành WebSocket
    B->>W: STOMP SEND / SUBSCRIBE
    W->>I: Inbound message
    I->>R: Cập nhật last accessed time
    W->>A: Chuyển message đến handler
    A->>W: Gửi outbound message
    W-->>B: STOMP MESSAGE
    Note over B,W: Heartbeat là tín hiệu giao thức riêng
~~~

Điểm quan trọng là cookie thường được dùng ở handshake để xác định session. Sau khi kết nối đã mở, WebSocket frame không gửi lại HTTP cookie như một request mới. Do đó, nếu session bị invalidate hoặc hết hạn, ứng dụng phải có cơ chế gắn vòng đời WebSocket với vòng đời session; không thể chỉ trông chờ browser ngừng gửi cookie.

## 3. Tích hợp Spring Session với STOMP

Trong ứng dụng Servlet dùng Spring WebSocket/STOMP, Spring Session có extension hỗ trợ liên kết WebSocket với HTTP session. Ở các phiên bản cung cấp AbstractSessionWebSocketMessageBrokerConfigurer, có thể dùng cấu hình chuyên biệt để đăng ký các thành phần cần thiết:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.Session;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;
import org.springframework.session.web.socket.config.annotation.AbstractSessionWebSocketMessageBrokerConfigurer;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;

@Configuration
@EnableRedisHttpSession
class WebSocketSessionConfiguration
        extends AbstractSessionWebSocketMessageBrokerConfigurer<Session> {

    @Override
    protected void configureStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    protected void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

Đây là mẫu tích hợp theo API của các phiên bản Spring Session có abstract configurer nói trên. Tên package, generic session type và trạng thái hỗ trợ thay đổi theo phiên bản. Với phiên bản mới hơn, nếu API này không còn được khuyến nghị hoặc không có trong dependency, hãy dùng các thành phần WebSocket integration được tài liệu của phiên bản đó hướng dẫn; không sao chép nguyên cấu hình cũ vào một dự án có API khác.

Tích hợp chuyên biệt có thể đăng ký SessionRepositoryMessageInterceptor trên inbound channel, lưu liên kết giữa WebSocket connection và HTTP session, đồng thời theo dõi khi session bị hủy để đóng các connection liên quan. Nếu tự cấu hình WebSocketMessageBrokerConfigurer, cần xác minh những thành phần này đã được đăng ký; chỉ bật STOMP broker không tự động bảo đảm session được gia hạn hoặc socket được đóng khi session bị thu hồi.

## 4. Thông điệp đến và cập nhật last accessed time

Khi client gửi một message STOMP vào ứng dụng, Spring Session WebSocket integration có thể dùng SessionRepositoryMessageInterceptor để lấy session ID đã gắn với handshake và cập nhật thời điểm truy cập của session trong repository.

Ví dụ handler nhận thông điệp:

~~~java
import java.security.Principal;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

record ChatMessage(String text) {}
record ChatAck(String status) {}

@Controller
class ChatMessageController {

    @MessageMapping("/chat.send")
    @SendToUser("/queue/ack")
    ChatAck receive(@Payload ChatMessage message, Principal principal) {
        // Xử lý nghiệp vụ; xác thực và phân quyền phải được cấu hình riêng.
        return new ChatAck("accepted");
    }
}
~~~

Client có thể gửi message đến destination /app/chat.send. Inbound message đi qua channel của Spring Messaging rồi được định tuyến đến handler. Với tích hợp Spring Session tương thích, quá trình này cũng có thể cập nhật last accessed time của HTTP session.

Không phải mọi frame đều là message nghiệp vụ. CONNECT, SUBSCRIBE, UNSUBSCRIBE, SEND và các loại message khác có thể đi qua inbound channel theo cách riêng. Heartbeat STOMP thường là frame rỗng/line-feed ở tầng giao thức và không nhất thiết trở thành Message<?> được chuyển qua channel interceptor. Vì vậy, không dựa vào STOMP heartbeat để làm mới session nếu chưa xác minh hành vi của phiên bản và stack đang dùng.

Nếu ứng dụng cần một tín hiệu nghiệp vụ để gia hạn session, hãy thiết kế một message ứng dụng rõ ràng, ví dụ SEND /app/presence với payload nhỏ. Tuy nhiên, không gửi message giả quá thường xuyên chỉ để giữ session sống vô hạn; hãy cân nhắc chính sách bảo mật và idle timeout.

## 5. Heartbeat WebSocket và heartbeat STOMP

WebSocket có control frame ping/pong ở tầng transport. Ping có thể được gửi bởi client, server hoặc hạ tầng; pong xác nhận đầu kia vẫn phản hồi. Các control frame này không phải message STOMP và không được chuyển đến @MessageMapping.

STOMP định nghĩa heartbeat ở tầng giao thức. Khi hai đầu thương lượng heartbeat trong CONNECT/CONNECTED, chúng có thể gửi ký tự line-feed định kỳ nếu không có frame khác được gửi trong khoảng thời gian đó. Heartbeat giúp phát hiện kết nối STOMP không còn hoạt động.

Phân biệt:

- **WebSocket ping/pong:** kiểm tra khả năng phản hồi của kết nối WebSocket.
- **STOMP heartbeat:** kiểm tra hoạt động của phiên giao thức STOMP giữa client và server.
- **Application heartbeat:** message do ứng dụng tự định nghĩa, có thể mang user presence hoặc trạng thái nghiệp vụ.

Không phải client, proxy và broker nào cũng xử lý ba cơ chế giống nhau. Cần chọn cơ chế phù hợp với tầng cần giám sát. Nếu chỉ cần phát hiện socket chết, dùng ping/pong hoặc STOMP heartbeat. Nếu cần cập nhật trạng thái người dùng đang tương tác trong ứng dụng, dùng application message với quy tắc rõ ràng.

## 6. Cấu hình heartbeat cho simple broker

Với simple broker của Spring Messaging, có thể cấu hình heartbeat và TaskScheduler để broker gửi heartbeat và kiểm tra hoạt động của client:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
class BrokerHeartbeatConfiguration implements WebSocketMessageBrokerConfigurer {

    @Bean
    ThreadPoolTaskScheduler stompHeartbeatScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-heartbeat-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue")
            .setHeartbeatValue(new long[] {10_000, 10_000})
            .setTaskScheduler(stompHeartbeatScheduler());
        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

Trong ví dụ, hai giá trị heartbeat được đặt 10 giây theo đơn vị mili giây. Scheduler thực hiện tác vụ định kỳ của broker. Cấu hình cụ thể cần khớp với phiên bản Spring Framework; nếu ứng dụng đã có WebSocketMessageBrokerConfigurer, hãy hợp nhất cấu hình vào một nơi hoặc dùng cơ chế ordering có chủ đích để tránh ghi đè broker registry.

Heartbeat được thương lượng theo STOMP protocol và thời gian thực tế phụ thuộc giá trị hai đầu công bố. Client cũng cần bật heartbeat gửi/nhận tương ứng. Chỉ cấu hình server chưa bảo đảm client sẽ gửi heartbeat nếu client không yêu cầu hoặc thư viện client không hỗ trợ.

Nếu dùng external STOMP broker relay, heartbeat còn phụ thuộc kết nối giữa Spring application và broker bên ngoài, cùng cấu hình heartbeat của broker đó. Không áp dụng cấu hình simple broker một cách máy móc cho broker relay.

## 7. Thông điệp gửi đi không đồng nghĩa với hoạt động của client

Server có thể gửi message đến client qua SimpMessagingTemplate, broker hoặc @SendTo. Ví dụ:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
class NotificationPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    NotificationPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    void publishToUser(String username, String text) {
        messagingTemplate.convertAndSendToUser(
            username,
            "/queue/notifications",
            text
        );
    }
}
~~~

Đây là hoạt động outbound: server đẩy dữ liệu đến người dùng. Nó không chứng minh người dùng đang tương tác và không nên tự động gia hạn idle timeout của HTTP session. Một server có thể gửi hàng nghìn thông báo đến một kết nối mà client không gửi bất kỳ message nào trở lại.

Nếu cần biết client đã nhận hoặc xử lý thông điệp, thiết kế acknowledgement ở tầng ứng dụng. Ví dụ, client gửi ACK cho một notification ID sau khi xử lý. ACK đó là inbound application message và có thể được tính là hoạt động theo chính sách của ứng dụng. Không coi việc server đã gọi convertAndSendToUser là bằng chứng browser đã nhận message.

## 8. Xác định inactivity theo đúng mục đích

Một hệ thống nên định nghĩa ít nhất ba mốc hoạt động:

1. **Transport last seen:** lần cuối ping/pong hoặc heartbeat cho thấy socket còn sống.
2. **Application last activity:** lần cuối client gửi message nghiệp vụ hoặc presence message.
3. **Session last accessed:** lần cuối Spring Session ghi nhận hoạt động làm mới HTTP session.

Các mốc này có thể khác nhau. Ví dụ:

- Client gửi STOMP heartbeat mỗi 10 giây nhưng không gửi message nghiệp vụ trong 30 phút.
- Server gửi notification mỗi phút nhưng client không phản hồi.
- Client gửi message nghiệp vụ thường xuyên, do đó inbound interceptor làm mới HTTP session.
- Socket vẫn mở nhưng session đã bị invalidate ở repository.

Một chính sách thường dùng:

| Mục tiêu | Nguồn tín hiệu | Hành động |
| --- | --- | --- |
| Phát hiện kết nối mạng đã chết | WebSocket ping/pong hoặc STOMP heartbeat | Đóng connection hoặc đánh dấu transport offline |
| Biết người dùng còn tương tác | Application heartbeat/presence hoặc message nghiệp vụ | Cập nhật presence riêng |
| Giữ session đăng nhập hoạt động | Inbound message qua Spring Session integration | Cập nhật last accessed time theo repository |
| Hết phiên xác thực | Session idle timeout/absolute lifetime | Từ chối request và đóng các WebSocket liên quan |

Không gộp socket còn sống thành người dùng còn hoạt động. Một tab có thể gửi heartbeat tự động khi người dùng đã rời máy. Nếu chính sách yêu cầu tự động đăng xuất sau thời gian không tương tác, cần đo application activity hoặc absolute lifetime riêng, không chỉ dựa vào heartbeat transport.

## 9. Session timeout và WebSocket connection có vòng đời riêng

HTTP session có thể hết hạn theo idle timeout hoặc bị invalidate khi logout. WebSocket connection có thể vẫn đang mở ở tầng mạng sau khi session đã hết hạn nếu ứng dụng không liên kết hai vòng đời.

Spring Session WebSocket integration có thể theo dõi các WebSocket connection gắn với HTTP session và đóng chúng khi session bị hủy. Đây là điểm quan trọng khi dùng session chia sẻ trên nhiều instance: thao tác logout hoặc thu hồi từ instance A phải có khả năng kết thúc các socket gắn với session đó, kể cả socket được mở qua instance B, trong phạm vi cơ chế integration và cấu hình cluster hỗ trợ.

Các điểm cần kiểm tra:

- Handshake có mang cookie session hợp lệ không.
- WebSocket connection có được đăng ký với HTTP session không.
- SessionRepositoryMessageInterceptor có được gắn vào inbound channel không.
- Sự kiện session destroyed/expired có được nhận và liên kết với registry WebSocket không.
- Khi logout, session repository có thực sự xóa/vô hiệu hóa session không.
- Các instance có cùng repository và cơ chế thông báo để nhận biết session bị hủy không.

Đóng socket không thay thế việc xóa session. Ngược lại, xóa session mà không đóng socket có thể để lại kết nối đang mở. Cần kiểm thử cả hai trạng thái.

## 10. Heartbeat và proxy/load balancer

Một kết nối WebSocket có thể đi qua reverse proxy, ingress controller hoặc load balancer. Nếu timeout ở hạ tầng ngắn hơn chu kỳ heartbeat, proxy có thể đóng kết nối dù client và server vẫn hoạt động.

Khi cấu hình:

- Chọn heartbeat interval nhỏ hơn idle timeout của proxy/load balancer với khoảng đệm phù hợp.
- Kiểm tra timeout của ingress, reverse proxy và firewall.
- Đảm bảo client và server cùng hỗ trợ STOMP heartbeat hoặc WebSocket ping/pong.
- Theo dõi reconnect để phân biệt lỗi mạng với session timeout.
- Không tăng heartbeat quá dày gây tải không cần thiết trên client, server và broker.

Heartbeat chỉ chứng minh đường truyền còn phản hồi theo cơ chế đã chọn. Nó không bảo đảm request được xác thực lại, không làm mới cookie và không khôi phục session đã bị xóa.

## 11. Bảo mật thông điệp đến và gửi đi

WebSocket thường được xác thực tại HTTP handshake bằng cookie session. Sau đó, các message STOMP cần được kiểm soát quyền riêng. Không mặc định mọi message đến từ một socket đã xác thực đều được phép truy cập mọi destination.

Các nguyên tắc:

- Chỉ cho phép origin cần thiết ở handshake.
- Xác thực người dùng dựa trên session/security context hợp lệ.
- Cấu hình message authorization cho CONNECT, SUBSCRIBE và SEND theo destination.
- Không tin username hoặc principal do client gửi trong payload.
- Với message riêng tư, gửi theo principal đã xác thực thay vì destination công khai.
- Duy trì CSRF protection cho handshake và các luồng HTTP liên quan theo cấu hình Spring Security.
- Khi session bị thu hồi, đóng socket và từ chối message tiếp theo.

Nếu ứng dụng dùng broker relay, cần bảo vệ cả kết nối từ Spring đến broker và phân quyền destination ở broker. Việc xác thực ở HTTP handshake không tự động cấu hình ACL của broker bên ngoài.

## 12. Kiểm thử inbound, heartbeat, outbound và inactivity

Kiểm thử cần phân biệt message nghiệp vụ với heartbeat. Một test chỉ xác nhận socket vẫn kết nối không chứng minh Spring Session đã được gia hạn.

| Kịch bản | Thao tác | Điều cần xác nhận |
| --- | --- | --- |
| Inbound message | Client gửi STOMP SEND | Inbound interceptor nhận message và last accessed time được cập nhật theo integration |
| Outbound message | Server gửi notification nhưng client không gửi lại | Outbound không bị nhầm thành inbound activity |
| STOMP heartbeat | Client và server trao đổi heartbeat | Kết nối được giám sát; không giả định heartbeat làm mới HTTP session |
| WebSocket ping/pong | Gửi control ping và nhận pong | Transport còn phản hồi; không coi là application activity |
| Idle session | Không gửi inbound message vượt timeout | Session hết hạn theo chính sách repository |
| Session active | Gửi inbound message định kỳ | Session được gia hạn nếu integration cập nhật last access |
| Logout | Invalidate HTTP session khi socket đang mở | Connection liên quan bị đóng và message tiếp theo không được xử lý |
| Nhiều instance | Kết nối ở instance A, logout từ B | Repository và registry phối hợp kết thúc session/socket theo cấu hình |
| Proxy timeout | Đặt heartbeat lớn hơn idle timeout proxy | Quan sát disconnect; điều chỉnh interval và timeout cho phù hợp |

Nên dùng integration test với WebSocket/STOMP client và repository Redis/JDBC test thật. Mock SimpMessagingTemplate chỉ kiểm tra code gửi message; nó không kiểm tra heartbeat, session refresh, broker hoặc việc đóng socket.

## 13. Giám sát và xử lý sự cố

Theo dõi riêng từng lớp:

- Số WebSocket connection đang mở, số reconnect và disconnect bất thường.
- STOMP heartbeat timeout và lỗi protocol.
- Số inbound application message theo loại.
- Số outbound message, delivery/ack nếu ứng dụng có cơ chế xác nhận.
- Session last accessed time, số session hết hạn và số session bị invalidate.
- Số socket bị đóng do session destroy/expire.
- Độ trễ xử lý message, queue backlog và lỗi broker.
- Lỗi Redis/JDBC khi cập nhật session từ inbound interceptor.

Khi socket bị đóng, xác định nguyên nhân theo thứ tự:

1. Transport bị ngắt bởi client, proxy hay server?
2. STOMP heartbeat có bị timeout không?
3. HTTP session còn tồn tại và còn hợp lệ không?
4. Inbound message có làm mới last accessed time không?
5. WebSocket registry có nhận biết session destroy/expire không?
6. Message broker hoặc network có lỗi riêng không?

Không ghi session ID, cookie hoặc payload nhạy cảm vào log. Dùng connection correlation ID và principal identifier đã được bảo vệ để điều tra.

## 14. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| WebSocket còn mở nhưng request HTTP bị yêu cầu đăng nhập lại | Socket và HTTP session có vòng đời riêng; session đã hết hạn | Bật/kiểm tra Spring Session WebSocket integration và chính sách timeout |
| Session hết hạn dù client gửi heartbeat | STOMP heartbeat không đi qua inbound message interceptor hoặc không cập nhật session | Dùng inbound application message nếu chính sách cần tính hoạt động đó |
| Session sống mãi dù người dùng không tương tác | Heartbeat tự động bị xem nhầm là hoạt động nghiệp vụ hoặc timeout quá dài | Tách transport liveness khỏi application inactivity |
| Server gửi notification nhưng session vẫn hết hạn | Outbound message không làm mới last accessed time | Để client gửi inbound message khi thực sự hoạt động |
| Client disconnect liên tục | Heartbeat lớn hơn proxy timeout hoặc mạng không ổn định | Điều chỉnh interval và kiểm tra hạ tầng |
| Logout nhưng socket vẫn nhận message | Connection registry không gắn với session hoặc session destroy không đóng socket | Kiểm tra WebSocket integration và registry listener |
| Inbound message gây tải Redis/JDBC cao | Message tần suất quá lớn làm cập nhật last access liên tục | Giảm tần suất application heartbeat và đo tải repository |

## 15. Nguyên tắc triển khai

- Phân biệt WebSocket ping/pong, STOMP heartbeat, inbound application message và outbound message.
- Dùng Spring Session WebSocket integration để liên kết WebSocket connection với HTTP session.
- Xác nhận SessionRepositoryMessageInterceptor hoặc thành phần tương đương được đăng ký trên inbound channel.
- Không giả định heartbeat hay outbound message tự làm mới session idle timeout.
- Dùng application heartbeat khi thật sự cần theo dõi presence nghiệp vụ và đặt tần suất hợp lý.
- Đồng bộ heartbeat interval với timeout của proxy/load balancer.
- Đóng WebSocket connection khi HTTP session bị invalidate/expire theo cơ chế integration.
- Kiểm tra authorization cho inbound SEND và SUBSCRIBE, không chỉ xác thực handshake.
- Kiểm thử riêng transport liveness, session timeout, logout và nhiều instance.

Trong hệ thống Spring Session kết hợp WebSocket, inbound message, heartbeat và outbound message biểu thị các loại hoạt động khác nhau. Inbound message có thể làm mới last accessed time thông qua tích hợp Spring Session; heartbeat chủ yếu kiểm tra kết nối/giao thức; outbound message chỉ cho biết server đang gửi dữ liệu. Để xác định inactivity chính xác, hãy định nghĩa rõ đang đo kết nối, tương tác nghiệp vụ hay thời hạn xác thực, rồi phối hợp interceptor, repository, WebSocket registry và chính sách timeout tương ứng.
