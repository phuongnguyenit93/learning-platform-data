# SessionRepositoryMessageInterceptor và cập nhật hoạt động khi nhận thông điệp

WebSocket tạo một kết nối hai chiều tồn tại lâu sau HTTP handshake. Trong khi đó, Spring Session quản lý thời hạn HttpSession dựa trên hoạt động của phiên. Nếu người dùng đang trò chuyện qua WebSocket nhưng không gửi HTTP request mới, session có thể hết hạn dù kết nối WebSocket vẫn đang hoạt động.

Spring Session giải quyết khoảng cách này bằng SessionRepositoryMessageInterceptor. Interceptor gắn session ID của HTTP session vào thuộc tính của WebSocket session khi handshake diễn ra. Sau đó, khi nhận các thông điệp STOMP phù hợp trên inbound message channel, interceptor tải session từ SessionRepository, kiểm tra session còn hạn và cập nhật lastAccessedTime. Nếu session đã hết hạn, thông điệp không được tiếp tục xử lý.

Đây là cơ chế đồng bộ hoạt động WebSocket với vòng đời session. Nó không thay thế xác thực, phân quyền thông điệp, kiểm tra CSRF hay quản lý kết nối WebSocket. Ứng dụng vẫn cần cấu hình Spring Security và chính sách vòng đời phù hợp.

## 1. Vì sao WebSocket cần cập nhật hoạt động của HttpSession?

Trong ứng dụng web thông thường, mỗi HTTP request đi qua Spring Session và có thể cập nhật thời điểm truy cập gần nhất của HttpSession. Repository dùng thời điểm này cùng maxInactiveInterval để xác định phiên còn hợp lệ hay đã hết hạn.

WebSocket có vòng đời khác:

1. Trình duyệt gửi HTTP request để thực hiện handshake.
2. Server xác thực handshake và nâng cấp kết nối thành WebSocket.
3. Sau handshake, client và server trao đổi frame trên kết nối lâu dài.
4. Các thông điệp STOMP được chuyển qua message channel của Spring.
5. Không cần gửi một HTTP request mới cho mỗi thông điệp ứng dụng.

Nếu chỉ dựa vào HTTP request, thời điểm truy cập session có thể không được cập nhật trong lúc người dùng gửi và nhận nhiều thông điệp WebSocket. Session repository có thể xem phiên không hoạt động và hết hạn, dù người dùng vẫn đang chat hoặc tương tác realtime.

Ví dụ một ứng dụng có trang email và cửa sổ chat. Người dùng mở trang bằng HTTP rồi trò chuyện liên tục qua WebSocket. Nếu chỉ handshake được tính là hoạt động, sau một khoảng thời gian không có HTTP request, HttpSession có thể hết hạn. Khi đó trạng thái xác thực và các thuộc tính session không còn được duy trì theo mong muốn.

SessionRepositoryMessageInterceptor cho phép các thông điệp inbound phù hợp được tính là hoạt động của session. Điều này giúp timeout phản ánh cả hoạt động WebSocket của người dùng.

## 2. SessionRepositoryMessageInterceptor làm những việc gì?

SessionRepositoryMessageInterceptor nằm trong package org.springframework.session.web.socket.server. Nó triển khai hai giao diện:

- HandshakeInterceptor: chạy quanh quá trình HTTP handshake để liên kết Spring Session ID với WebSocket session attributes.
- ChannelInterceptor: can thiệp vào thông điệp đi qua inbound message channel để kiểm tra và cập nhật session.

Hai vai trò này bổ sung cho nhau:

| Giai đoạn | Vai trò của interceptor | Kết quả |
|---|---|---|
| HTTP handshake | Đọc session ID và gắn vào thuộc tính WebSocket session | Có thể tìm lại Spring Session khi nhận message |
| Inbound STOMP message | Lấy session ID từ thuộc tính, tải session từ repository | Xác minh session tồn tại và chưa hết hạn |
| Cập nhật hoạt động | Cập nhật lastAccessedTime rồi lưu session | Hoạt động WebSocket được tính vào thời gian truy cập |
| Session hết hạn | Ngăn thông điệp tiếp tục qua channel | Handler không xử lý thông điệp bằng session đã hết hạn |

Interceptor không lưu nội dung thông điệp vào HttpSession. Nó cũng không tự động xác thực lại người dùng hoặc quyết định người dùng có quyền gửi đến destination nào. Nhiệm vụ chính là giữ cho lastAccessedTime của Spring Session phản ánh hoạt động nhận thông điệp.

## 3. Liên kết HTTP session với WebSocket session ở handshake

WebSocket handshake bắt đầu bằng HTTP request. Nếu người dùng đã đăng nhập bằng Spring Security và browser gửi cookie session ID, Spring Session có thể khôi phục HttpSession trong quá trình xử lý handshake.

SessionRepositoryMessageInterceptor được đăng ký như một HandshakeInterceptor. Khi handshake thành công, nó liên kết ID của Spring Session với thuộc tính của WebSocket session. Thuộc tính này được giữ trong vòng đời WebSocket connection và được dùng về sau khi có thông điệp inbound.

Luồng khái quát:

    Browser
       |
       | HTTP handshake + SESSION cookie
       v
    Spring Session filter
       |
       v
    Spring Security / WebSocket handshake
       |
       v
    SessionRepositoryMessageInterceptor
       |
       | Gắn Spring Session ID vào WebSocket attributes
       v
    WebSocket connection được thiết lập
       |
       v
    Inbound STOMP message
       |
       | Đọc session ID từ WebSocket attributes
       v
    SessionRepository

Điểm quan trọng là interceptor lưu session ID làm liên kết. Nó không cần sao chép toàn bộ HttpSession vào WebSocket attributes. Khi message đến, repository được dùng để tải trạng thái mới nhất theo ID đó.

Nếu handshake không có HttpSession tương ứng, chẳng hạn client chưa gửi cookie hoặc endpoint không yêu cầu session, interceptor không có một phiên đã liên kết để cập nhật. Nếu endpoint yêu cầu đăng nhập, hãy bảo đảm xác thực được thực hiện trước hoặc trong handshake theo cấu hình Spring Security.

## 4. Cập nhật lastAccessedTime khi nhận thông điệp

Sau handshake, WebSocket connection có thể tồn tại hàng giờ. Khi client gửi STOMP message, Spring chuyển thông điệp qua inbound channel. SessionRepositoryMessageInterceptor hoạt động như ChannelInterceptor và kiểm tra loại thông điệp có thuộc tập cần theo dõi hay không.

Theo mặc định, các SimpMessageType được theo dõi gồm:

- CONNECT
- MESSAGE
- SUBSCRIBE
- UNSUBSCRIBE

Với một thông điệp phù hợp, interceptor lấy session ID đã lưu trong WebSocket session attributes, tìm session trong SessionRepository, kiểm tra thời hạn và cập nhật lastAccessedTime. Nếu session còn hợp lệ, interceptor lưu thay đổi và cho thông điệp tiếp tục. Nếu session đã hết hạn hoặc không còn tồn tại, thông điệp bị chặn.

Luồng xử lý:

    Client gửi STOMP message
             |
             v
    Inbound message channel
             |
             v
    SessionRepositoryMessageInterceptor
             |
             | Loại message có được theo dõi?
             v
       Tìm Spring Session
             |
       +-----+------+
       |            |
     Còn hạn      Hết hạn / không tồn tại
       |            |
       v            v
    Cập nhật      Chặn message
    lastAccessedTime
       |
       v
    Lưu session
       |
       v
    Message tiếp tục đến handler

Nhờ đó, hoạt động nhận thông điệp có thể gia hạn thời gian không hoạt động của HttpSession theo maxInactiveInterval đã cấu hình. Interceptor không tự thay đổi maxInactiveInterval thành một giá trị mới; nó cập nhật thời điểm truy cập gần nhất để repository tính thời điểm hết hạn dựa trên chính sách hiện tại.

## 5. Cấu hình WebSocket theo cách Spring Session hỗ trợ

Với ứng dụng Spring WebSocket dùng STOMP, cách đơn giản là mở rộng AbstractSessionWebSocketMessageBrokerConfigurer. Cấu hình này tích hợp các thành phần Spring Session cần thiết vào WebSocket message broker.

Ví dụ:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig
        extends AbstractSessionWebSocketMessageBrokerConfigurer<Session> {

    @Override
    protected void configureStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/messages");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/queue/", "/topic/");
        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

Trong cấu hình này:

- @EnableWebSocketMessageBroker bật message broker hỗ trợ STOMP.
- configureStompEndpoints đăng ký endpoint WebSocket để client kết nối.
- enableSimpleBroker cấu hình các destination broker xử lý.
- setApplicationDestinationPrefixes định nghĩa prefix cho message gửi đến application handler.
- AbstractSessionWebSocketMessageBrokerConfigurer kết nối WebSocket lifecycle với Spring Session.

Cấu hình trên giả định ứng dụng đã có HttpSession integration của Spring Session hoạt động. Ví dụ có thể dùng Redis hoặc JDBC repository trong Servlet application. Không bật WebSocket support thay cho session repository; hai phần cần được cấu hình cùng nhau.

Một số phiên bản hoặc ứng dụng có thể dùng SockJS fallback:

~~~java
@Override
protected void configureStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/messages").withSockJS();
}
~~~

Dù dùng WebSocket thuần hay SockJS, cần kiểm thử đường đi thực tế của message và session cookie trong môi trường triển khai.

## 6. Những thành phần được đăng ký phía sau cấu hình tích hợp

AbstractSessionWebSocketMessageBrokerConfigurer thực hiện nhiều bước ngoài việc thêm một interceptor đơn lẻ.

| Thành phần | Tác dụng |
|---|---|
| SessionRepositoryMessageInterceptor dạng HandshakeInterceptor | Liên kết Spring Session ID với WebSocket session attributes |
| SessionRepositoryMessageInterceptor dạng ChannelInterceptor | Cập nhật lastAccessedTime khi inbound message phù hợp được nhận |
| WebSocketConnectHandlerDecoratorFactory | Tạo SessionConnectEvent có chứa WebSocketSession |
| WebSocketRegistryListener | Theo dõi quan hệ giữa Spring Session ID và các WebSocket connection |
| Cơ chế đóng kết nối | Đóng WebSocket connection khi Spring Session kết thúc theo sự kiện được xử lý |

WebSocketRegistryListener và decorator factory là các thành phần bổ trợ cho vòng đời kết nối. Chúng giải quyết vấn đề một session đã bị kết thúc nhưng WebSocket connection vẫn đang mở.

SessionRepositoryMessageInterceptor tập trung vào cập nhật hoạt động và chặn message nếu session hết hạn. Listener và registry xử lý việc theo dõi, đóng kết nối. Không nên gộp hai trách nhiệm thành một: cập nhật lastAccessedTime không đồng nghĩa với đóng socket ngay lập tức.

## 7. Đăng ký interceptor thủ công khi cần tùy chỉnh

Nếu không sử dụng AbstractSessionWebSocketMessageBrokerConfigurer, ứng dụng có thể tạo SessionRepositoryMessageInterceptor với repository cụ thể và đăng ký cùng instance ở hai vị trí:

1. Là HandshakeInterceptor trên STOMP endpoint.
2. Là ChannelInterceptor trên inbound channel.

Mẫu cấu hình khái niệm:

~~~java
SessionRepositoryMessageInterceptor<MySession> interceptor =
        new SessionRepositoryMessageInterceptor<>(sessionRepository);

registry.addEndpoint("/messages")
        .addInterceptors(interceptor);

@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(interceptor);
}
~~~

Trong ví dụ, MySession đại diện cho kiểu Session cụ thể do repository của ứng dụng sử dụng; sessionRepository phải có kiểu tương ứng SessionRepository<MySession>. Khi dùng Redis hoặc JDBC, hãy dùng kiểu Session thực tế mà implementation cung cấp.

Đăng ký interceptor chỉ ở inbound channel mà không đăng ký handshake sẽ thiếu thông tin liên kết session ID. Ngược lại, chỉ đăng ký ở handshake thì session ID có thể được lưu trong WebSocket attributes nhưng không có interceptor xử lý các thông điệp để cập nhật lastAccessedTime.

Nếu dùng cấu hình tích hợp của Spring Session, không cần đăng ký lại interceptor thủ công. Đăng ký hai lần có thể làm cùng một thông điệp bị xử lý nhiều lần, tạo thêm truy vấn và cập nhật không cần thiết.

## 8. Tùy chỉnh loại thông điệp được tính là hoạt động

SessionRepositoryMessageInterceptor cung cấp setMatchingMessageTypes(Set<SimpMessageType>) để thay đổi loại STOMP message được theo dõi. Mặc định là CONNECT, MESSAGE, SUBSCRIBE và UNSUBSCRIBE.

Có thể cần tùy chỉnh khi ứng dụng có yêu cầu đặc biệt về hoạt động:

- Chỉ tính các message mang ý nghĩa tương tác người dùng.
- Bổ sung một loại message nếu luồng ứng dụng cần theo dõi.
- Loại một loại message không nên làm mới session theo chính sách sản phẩm.

Ví dụ cấu hình tập loại message cho một interceptor tự đăng ký:

~~~java
interceptor.setMatchingMessageTypes(EnumSet.of(
        SimpMessageType.CONNECT,
        SimpMessageType.MESSAGE,
        SimpMessageType.SUBSCRIBE,
        SimpMessageType.UNSUBSCRIBE
));
~~~

Không nên giảm tập mặc định chỉ để giảm số lần ghi mà chưa kiểm tra trải nghiệm. Nếu chỉ theo dõi CONNECT, một người dùng gửi MESSAGE liên tục vẫn có thể bị timeout vì những message đó không làm mới lastAccessedTime.

Ngược lại, nếu mọi thông điệp kỹ thuật đều được tính là hoạt động, một client có thể giữ session sống bằng cách gửi message tự động dù người dùng không thực sự tương tác. Hãy xác định “hoạt động” theo yêu cầu bảo mật và sản phẩm, rồi chọn loại message phù hợp.

## 9. Inbound message khác outbound message và heartbeat

SessionRepositoryMessageInterceptor được đăng ký trên inbound channel. Vì vậy, nó xử lý thông điệp từ client đi vào server theo các SimpMessageType được cấu hình.

Cần phân biệt:

| Hoạt động | Có được interceptor mặc định theo dõi không? |
|---|---|
| Client gửi STOMP CONNECT | Có |
| Client gửi STOMP MESSAGE | Có |
| Client gửi SUBSCRIBE | Có |
| Client gửi UNSUBSCRIBE | Có |
| Server gửi message đến client | Không, vì đây là outbound |
| Server gửi broadcast trên broker | Không, không phải inbound client message |
| WebSocket transport ping/pong | Không nên mặc định coi là STOMP message được interceptor theo dõi |
| STOMP heartbeat | Không nên giả định heartbeat sẽ cập nhật session nếu không đi qua inbound message channel dưới loại được theo dõi |

Điểm này quan trọng với ứng dụng realtime chủ yếu đẩy dữ liệu từ server xuống client. Nếu server gửi notification liên tục nhưng client không gửi inbound message phù hợp, session có thể không được gia hạn bởi interceptor này.

Nếu yêu cầu session phản ánh sự hiện diện của người dùng, hãy thiết kế heartbeat ứng dụng hoặc thông điệp activity có xác thực và giới hạn tần suất. Không nên coi mọi frame transport là hoạt động người dùng nếu implementation không đưa chúng qua interceptor.

## 10. Điều gì xảy ra khi session đã hết hạn?

Khi inbound message thuộc loại được theo dõi, interceptor tìm session trong repository. Nếu session không tồn tại hoặc đã hết hạn, message không được tiếp tục xử lý.

Điều này tránh tình huống một WebSocket connection cũ tiếp tục gửi lệnh ứng dụng sau khi HttpSession tương ứng đã hết hạn. Tuy nhiên, chặn message không đồng nghĩa mọi WebSocket connection ở mọi node chắc chắn bị đóng ngay tại cùng thời điểm.

Spring Session WebSocket integration có thêm WebSocketRegistryListener để theo dõi connection và đóng các kết nối gắn với session đã kết thúc. Thời điểm nhận event và khả năng đóng kết nối còn phụ thuộc repository, event mechanism và topology triển khai.

Một số điểm cần xử lý trong ứng dụng:

- Client cần nhận biết close/error và chuyển về màn hình đăng nhập.
- Server cần yêu cầu xác thực lại nếu người dùng kết nối lại.
- Message handler không được thực hiện side effect trước khi security/interceptor kiểm tra session.
- Các thao tác nhạy cảm vẫn phải kiểm tra quyền và trạng thái tài khoản.
- Không cho phép client dùng một STOMP connection cũ như credential lâu dài sau khi session đã bị revoke.

Nếu session hết hạn giữa lúc hai message đến gần nhau, repository và interceptor quyết định message nào còn hợp lệ theo trạng thái được quan sát tại thời điểm xử lý. Đối với thao tác nghiệp vụ quan trọng, cần kiểm tra quyền ở tầng service và dùng transaction/locking phù hợp; không dựa vào thời điểm cập nhật session làm cơ chế đồng bộ nghiệp vụ.

## 11. Quan hệ với Spring Security và xác thực WebSocket

SessionRepositoryMessageInterceptor không phải authentication interceptor. Nó không xác minh username/password, không tạo Authentication và không quyết định user có thể SUBSCRIBE vào destination nào.

Trong handshake, Spring Security có thể xác thực HTTP request dựa trên cookie session và khôi phục SecurityContext từ HttpSession. Principal được gắn vào WebSocket session theo cơ chế Spring WebSocket/Spring Security. Sau đó, Spring Security messaging support có thể kiểm tra quyền đối với inbound STOMP message.

Nên tách trách nhiệm:

| Thành phần | Vai trò |
|---|---|
| Spring Session | Khôi phục và lưu HttpSession |
| SessionRepositoryMessageInterceptor | Gắn session ID vào WebSocket attributes, cập nhật hoạt động, chặn message khi session hết hạn |
| Spring Security HTTP | Xác thực và bảo vệ HTTP handshake |
| Spring Security messaging | Phân quyền inbound STOMP message theo destination/principal |
| WebSocketRegistryListener | Theo dõi và đóng kết nối khi Spring Session kết thúc |

Ví dụ cấu hình authorization cho message channel cần được thực hiện riêng theo phiên bản Spring Security, không thể thay bằng SessionRepositoryMessageInterceptor. Hãy giới hạn destination, kiểm tra quyền gửi message và quyền subscribe. Không tin destination do client tự gửi nếu chưa qua authorization.

Nếu session ID được xoay vòng sau đăng nhập, hãy kiểm thử thời điểm WebSocket handshake và quan hệ session ID được lưu trong WebSocket attributes. Một cách triển khai dễ kiểm soát là chỉ cho kết nối WebSocket sau khi xác thực hoàn tất; khi thay đổi danh tính hoặc session ID, yêu cầu client kết nối lại theo chính sách.

## 12. Ảnh hưởng đến timeout và tải repository

Mỗi inbound message được theo dõi có thể dẫn đến thao tác tìm session, cập nhật lastAccessedTime và lưu session. Với ứng dụng chat, cộng tác hoặc dashboard có tần suất message cao, điều này tạo thêm tải lên Redis/JDBC repository.

Cần đo:

- Số inbound message trên mỗi kết nối mỗi giây.
- Số lần load/save session do interceptor tạo ra.
- Độ trễ repository và tỷ lệ lỗi.
- Tỷ lệ session hết hạn trong khi WebSocket vẫn kết nối.
- Số connection bị đóng khi session kết thúc.
- Số lượng WebSocket connection và phân bố theo instance.

Không nên giảm message type tracking mà không đánh giá session timeout. Nếu ứng dụng nhận 100 message/giây, có thể có nhiều thao tác cập nhật lastAccessedTime; nhưng nếu không cập nhật đủ thường xuyên, phiên có thể hết hạn trong khi client còn tương tác.

Có thể thiết kế heartbeat ứng dụng với chu kỳ hợp lý, gộp sự kiện hoặc tùy biến cách theo dõi nếu cần giảm tải. Tuy nhiên, custom interceptor phải bảo đảm session hết hạn vẫn được kiểm tra trước khi message nhạy cảm được xử lý. Không bỏ kiểm tra expiry chỉ để tối ưu hiệu năng.

## 13. Vận hành nhiều instance

Trong triển khai nhiều instance, HTTP handshake có thể được xử lý ở node A và WebSocket connection sau đó được giữ trên node A. Các inbound STOMP message trên connection đó thường tiếp tục đi qua node A. Spring Session repository dùng chung cho phép node A cập nhật session được lưu trong Redis/JDBC; các HTTP request khác ở node B cũng có thể khôi phục cùng session.

Các điều kiện quan trọng:

- Tất cả node dùng cùng Spring Session repository, namespace và serializer tương thích.
- Cấu hình WebSocket endpoint và interceptor nhất quán trên các node.
- Cookie/session resolver và domain/path không khác nhau ngoài chủ đích.
- Session event và cơ chế đóng WebSocket được kiểm thử khi session bị invalidate từ node khác.
- Load balancer giữ một WebSocket connection trên một backend trong suốt vòng đời connection.
- Nếu dùng broker ngoài như RabbitMQ, kiểm thử cả message routing lẫn session lifecycle.

WebSocketRegistryListener duy trì ánh xạ connection trong phạm vi runtime của ứng dụng. Trong hệ thống nhiều node, không mặc định một node có thể đóng socket đang nằm trên node khác chỉ vì nó xóa session trong repository. Cần xác minh event expiration/deletion được phân phối đến mọi node hoặc có cơ chế điều phối đóng kết nối phù hợp.

Redis keyspace notifications, JDBC cleanup và các cơ chế event của repository có semantics khác nhau. Nếu session bị xóa nhưng event không đến node đang giữ WebSocket connection, interceptor vẫn có thể chặn inbound message khi nó kiểm tra session và thấy phiên đã hết hạn/không tồn tại. Tuy nhiên, socket có thể vẫn mở cho đến khi có message hoặc cơ chế đóng kết nối khác được kích hoạt. Hãy kiểm thử tình huống này rõ ràng.

## 14. Logout và kết thúc WebSocket connection

Logout qua HTTP thường invalidate HttpSession. Spring Session phát sự kiện vòng đời theo khả năng repository. WebSocket integration dùng WebSocketRegistryListener và decorator factory để theo dõi WebSocket connection gắn với session đó, sau đó đóng các connection còn mở khi session kết thúc.

Luồng khái quát:

    Người dùng logout
          |
          v
    Spring Security logout handler
          |
          v
    HttpSession invalidate
          |
          v
    Spring Session repository xóa session
          |
          v
    Session destroyed/expired event
          |
          v
    WebSocketRegistryListener
          |
          v
    Đóng WebSocket connection gắn với session

Đóng WebSocket connection là một phần của logout lifecycle, nhưng không thay thế việc xóa SecurityContext hoặc thu hồi session ở repository. Ngược lại, chỉ xóa cookie session ID trong browser mà không invalidate server-side session có thể để lại một WebSocket connection đang mở.

Với ứng dụng có nhiều node, cần xác định event có được phát và nhận ở node giữ socket hay không. Nếu không có bảo đảm phân phối event, cân nhắc một cơ chế application-level revoke/disconnect qua message broker dùng chung. Không dựa vào sticky session để thay thế việc thu hồi session toàn cụm.

## 15. Kiểm thử cập nhật hoạt động khi nhận message

Một bài kiểm thử chỉ xác nhận WebSocket handshake thành công không chứng minh lastAccessedTime được cập nhật. Cần kiểm thử cả inbound channel.

Các tình huống nên có:

1. Tạo HttpSession qua HTTP và ghi một thuộc tính.
2. Thiết lập WebSocket handshake bằng cùng cookie session.
3. Xác nhận interceptor liên kết đúng session ID với WebSocket attributes.
4. Gửi STOMP CONNECT và kiểm tra session còn được tìm thấy.
5. Gửi MESSAGE, SUBSCRIBE và UNSUBSCRIBE, xác nhận lastAccessedTime được cập nhật.
6. Thay đổi tập matching message types và xác nhận loại không được theo dõi không làm mới session.
7. Để session hết hạn rồi gửi message, xác nhận message không đến handler.
8. Invalidate session qua HTTP logout và xác nhận WebSocket connection được đóng theo event integration.
9. Chỉ gửi server-to-client message trong thời gian dài và xác nhận nó không tự động được tính là inbound activity.
10. Kiểm thử heartbeat riêng, không giả định heartbeat refresh session.
11. Gửi message với principal không đủ quyền và xác nhận Spring Security messaging từ chối.
12. Kiểm thử session ID rotation trước và sau handshake.
13. Chạy hai instance và xác nhận repository dùng chung cập nhật hoạt động đúng.
14. Invalidate session từ node khác và kiểm tra event/connection close.
15. Đo tải repository khi tần suất message tăng cao.

Nên dùng Spring WebSocket/STOMP test utilities hoặc WebSocket client thực để xác nhận message channel. Có thể dùng repository thật hoặc môi trường Redis/JDBC tương thích để kiểm tra lastAccessedTime và expiration. Mock ChannelInterceptor đơn lẻ không chứng minh repository đã cập nhật dữ liệu bền vững.

## 16. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| WebSocket đang chat nhưng session vẫn hết hạn | Interceptor chưa đăng ký ở inbound channel hoặc client không gửi message được theo dõi | Kiểm tra channel interceptor và SimpMessageType |
| Handshake thành công nhưng message không cập nhật session | Interceptor không được đăng ký như HandshakeInterceptor hoặc không có session ID | Kiểm tra handshake attributes và cookie |
| Message bị chặn dù user vừa hoạt động | Session ID trong WebSocket attributes cũ, session đã hết hạn hoặc bị revoke | Kiểm tra session ID rotation và repository |
| Server push liên tục nhưng session hết hạn | Outbound message không được tính là inbound activity | Kiểm tra client gửi activity message phù hợp |
| Logout không đóng WebSocket | Event không được phát/nhận hoặc registry không có mapping | Kiểm tra WebSocketRegistryListener và event mechanism |
| Session được cập nhật quá nhiều | Tần suất inbound message cao và tập matching quá rộng | Đo repository writes, cân nhắc activity policy |
| Một node cập nhật session nhưng node khác không thấy | Các node dùng repository/namespace khác nhau hoặc dữ liệu không nhất quán | Kiểm tra cấu hình store và serializer |
| WebSocket message vẫn đến handler sau khi user mất quyền | Chưa cấu hình messaging authorization hoặc chỉ dựa vào interceptor | Kiểm tra Spring Security message security |
| Session hết hạn nhưng socket vẫn mở | Event close trễ hoặc không được phân phối đến node giữ socket | Kiểm tra event delivery và đóng kết nối bổ sung |

Khi điều tra, xác định lần lượt: handshake có session không; session ID có được lưu trong WebSocket attributes không; message có đi qua inbound channel không; loại message có được theo dõi không; repository có tìm thấy session không; và security authorization có cho phép message không.

## 17. Quy trình triển khai đề xuất

Khi tích hợp WebSocket với Spring Session, thực hiện theo thứ tự:

1. Hoàn thiện HttpSession integration bằng Redis hoặc JDBC trước.
2. Bật Spring WebSocket message broker và đăng ký STOMP endpoint.
3. Sử dụng AbstractSessionWebSocketMessageBrokerConfigurer hoặc đăng ký SessionRepositoryMessageInterceptor ở cả handshake và inbound channel.
4. Xác nhận interceptor đang dùng đúng SessionRepository của ứng dụng.
5. Giữ matching message types mặc định trước khi tối ưu.
6. Cấu hình Spring Security HTTP và messaging authorization riêng.
7. Xác định session timeout và tần suất inbound message phù hợp.
8. Kiểm thử hết hạn, logout, session ID rotation và kết nối lâu.
9. Kiểm thử event delivery và đóng WebSocket trên nhiều instance.
10. Đo số lần repository read/write và độ trễ khi tải tăng.
11. Kiểm tra logging không ghi session ID hoặc credential.
12. Ghi rõ giới hạn của repository event và cách xử lý khi node giữ socket không nhận được event.

Nếu ứng dụng không dùng Spring WebSocket message channel, chẳng hạn tích hợp trực tiếp JSR-356, không nên giả định SessionRepositoryMessageInterceptor có thể được gắn vào. Spring Session WebSocket integration dựa vào các điểm mở rộng của Spring WebSocket để chặn handshake và incoming messages; JSR-356 trực tiếp không cung cấp cùng cơ chế interceptor message channel.

## Kết luận

SessionRepositoryMessageInterceptor liên kết Spring Session ID với WebSocket session attributes trong HTTP handshake, rồi theo dõi inbound STOMP message để kiểm tra session và cập nhật lastAccessedTime. Mặc định, CONNECT, MESSAGE, SUBSCRIBE và UNSUBSCRIBE được tính là hoạt động; nếu session đã hết hạn, message bị chặn. Interceptor phải được đăng ký ở cả handshake và inbound channel, thường được cấu hình tự động qua AbstractSessionWebSocketMessageBrokerConfigurer. Nó phối hợp với WebSocketRegistryListener để quản lý connection khi session kết thúc, nhưng không thay thế xác thực hoặc phân quyền thông điệp. Hãy kiểm thử cả inbound/outbound, heartbeat, logout, expiration và event delivery trên nhiều instance trước khi đưa vào production.

## Tài liệu tham khảo

- Spring Session WebSocket Integration: https://docs.spring.io/spring-session/reference/web-socket.html
- SessionRepositoryMessageInterceptor API: https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/socket/server/SessionRepositoryMessageInterceptor.html
- Spring Session WebSocket Guide: https://docs.spring.io/spring-session/reference/guides/boot-websocket.html
- Spring Framework WebSocket/STOMP documentation: https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html
