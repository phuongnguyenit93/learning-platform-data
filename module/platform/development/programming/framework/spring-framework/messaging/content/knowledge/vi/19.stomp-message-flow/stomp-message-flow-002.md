# registerStompEndpoints và đường dẫn kết nối của client

## Mục tiêu

Trong Spring STOMP over WebSocket, server phải công bố một endpoint để client thực hiện HTTP handshake và nâng cấp kết nối lên WebSocket. Spring cấu hình endpoint này qua phương thức **registerStompEndpoints(StompEndpointRegistry registry)** của **WebSocketMessageBrokerConfigurer**.

Đường dẫn endpoint là URL kết nối ở tầng transport. Sau khi kết nối thành công, client mới gửi các STOMP frame như **CONNECT**, **SUBSCRIBE** và **SEND**. Đường dẫn endpoint vì vậy khác với các destination mà STOMP dùng để định tuyến message.

Sau bài này, bạn có thể:

- Bật hạ tầng STOMP over WebSocket trong Spring.
- Đăng ký một hoặc nhiều endpoint bằng **registerStompEndpoints**.
- Xác định URL client cần kết nối khi có server port, context path và reverse proxy.
- Phân biệt WebSocket endpoint path với STOMP application/broker destination prefix.
- Kết nối bằng WebSocket trực tiếp hoặc SockJS fallback.
- Cấu hình allowed origins, handshake interceptor và bảo mật kết nối.
- Chẩn đoán lỗi URL, handshake, STOMP CONNECT và subscription.

## 1. WebSocket và STOMP đảm nhiệm hai lớp khác nhau

WebSocket cung cấp một kết nối hai chiều lâu dài giữa client và server. Bản thân WebSocket chỉ định nghĩa cách truyền frame; nó không quy định nội dung message ứng dụng.

STOMP là giao thức messaging chạy bên trên WebSocket. STOMP quy định các frame và header như:

| STOMP frame | Mục đích |
|---|---|
| CONNECT | Client bắt đầu phiên STOMP |
| CONNECTED | Server xác nhận phiên STOMP |
| SUBSCRIBE | Client đăng ký nhận message từ destination |
| SEND | Client gửi message tới destination |
| MESSAGE | Server/broker gửi message cho subscriber |
| UNSUBSCRIBE | Client hủy subscription |
| DISCONNECT | Client kết thúc phiên |

Một phiên kết nối có hai giai đoạn:

~~~text
Client                         Spring server
  |                                  |
  | 1. HTTP GET + Upgrade            |
  |--------------------------------->|
  | 2. HTTP 101 Switching Protocols  |
  |<---------------------------------|
  |                                  |
  | 3. STOMP CONNECT                 |
  |--------------------------------->|
  | 4. STOMP CONNECTED               |
  |<---------------------------------|
  |                                  |
  | 5. SUBSCRIBE / SEND              |
  |<-------------------------------->|
  |                                  |
  | 6. DISCONNECT                    |
  |--------------------------------->|
~~~

**registerStompEndpoints** cấu hình bước 1 và bước 2. Các frame STOMP chỉ được trao đổi sau khi WebSocket hoặc SockJS transport đã được thiết lập.

## 2. Bật hạ tầng STOMP trong Spring

STOMP over WebSocket được cung cấp bởi hai module **spring-messaging** và **spring-websocket**. Ứng dụng cần dependency tương ứng và bật **@EnableWebSocketMessageBroker**.

Ví dụ cấu hình cơ bản:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/stomp");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry config) {
        config.setApplicationDestinationPrefixes("/app");
        config.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Hai phương thức có nhiệm vụ riêng:

- **registerStompEndpoints(...)**: đăng ký URL endpoint để client bắt đầu handshake.
- **configureMessageBroker(...)**: cấu hình cách Spring định tuyến STOMP destination sau khi kết nối đã được thiết lập.

**@EnableWebSocketMessageBroker** nhập hạ tầng cần thiết để Spring phát hiện endpoint, quản lý WebSocket session và chuyển STOMP frame thành Spring Message.

## 3. Đăng ký endpoint bằng registerStompEndpoints

Chữ ký phương thức:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/stomp");
}
~~~

**registry.addEndpoint("/stomp")** đăng ký một endpoint có path **/stomp**. Đây là phần path được dùng cho HTTP handshake. Nếu server chạy ở **http://localhost:8080**, ứng dụng không có context path và không đặt thêm prefix ở reverse proxy, client kết nối bằng:

~~~text
ws://localhost:8080/stomp
~~~

Khi server được truy cập qua HTTPS, client phải dùng WebSocket bảo mật:

~~~text
wss://example.com/stomp
~~~

Endpoint có thể đăng ký nhiều path nếu ứng dụng cần nhiều điểm kết nối:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/stomp");
    registry.addEndpoint("/admin-stomp");
}
~~~

Mỗi path là một URL handshake riêng. Có thể cấu hình allowed origins, handshake handler hoặc interceptor riêng cho từng endpoint.

Không cần tạo endpoint riêng cho từng STOMP destination. Một endpoint **/stomp** có thể phục vụ nhiều destination như **/app/chat.send**, **/topic/public** và **/queue/notifications**.

## 4. Đường dẫn kết nối của client được tạo như thế nào?

URL client cần kết nối phụ thuộc vào nhiều phần:

~~~text
scheme://host:port/context-path/endpoint-path
~~~

| Phần | Ví dụ | Nguồn cấu hình |
|---|---|---|
| Scheme | ws hoặc wss | HTTP/HTTPS bên ngoài và TLS |
| Host | localhost, api.example.com | Domain client truy cập |
| Port | 8080, 443 | Server hoặc reverse proxy |
| Context path | /messaging | Servlet/application context |
| Endpoint path | /stomp | registry.addEndpoint("/stomp") |

Ví dụ:

- Server chạy cổng **8080**.
- Application context path là **/messaging**.
- Endpoint đăng ký là **/stomp**.
- Client truy cập cùng máy trong môi trường local.

URL kết nối là:

~~~text
ws://localhost:8080/messaging/stomp
~~~

Khi triển khai HTTPS ở domain công khai:

~~~text
wss://api.example.com/messaging/stomp
~~~

Context path được thêm vào URL bên ngoài endpoint path. Spring không tự thêm **/app**, **/topic** hoặc **/queue** vào URL handshake.

Nếu frontend và backend cùng origin, nên dùng URL tương đối cho SockJS hoặc tạo URL WebSocket từ location hiện tại để tránh hard-code host giữa các môi trường. Nếu frontend và backend khác origin, cấu hình allowed origins và URL đầy đủ tương ứng.

## 5. Endpoint path không phải STOMP destination prefix

Đây là lỗi nhầm lẫn rất phổ biến.

Giả sử cấu hình:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/stomp");
}

@Override
public void configureMessageBroker(MessageBrokerRegistry config) {
    config.setApplicationDestinationPrefixes("/app");
    config.enableSimpleBroker("/topic", "/queue");
}
~~~

Ý nghĩa:

| Path | Dùng ở đâu? | Ví dụ |
|---|---|---|
| /stomp | URL HTTP/WebSocket handshake | ws://localhost:8080/stomp |
| /app | Prefix của STOMP SEND đi vào controller | /app/chat.send |
| /topic | Prefix destination để subscribe qua simple broker | /topic/public |
| /queue | Prefix destination theo quy ước point-to-point | /queue/notifications |

Luồng xử lý ví dụ:

1. Client kết nối đến **ws://localhost:8080/stomp**.
2. Client gửi STOMP **SUBSCRIBE** tới **/topic/public**.
3. Client gửi STOMP **SEND** tới **/app/chat.send**.
4. Spring bỏ prefix **/app** và tìm method **@MessageMapping("/chat.send")**.
5. Kết quả controller được gửi đến broker destination phù hợp.
6. Broker chuyển message đến các client đã subscribe **/topic/public**.

**/topic** và **/queue** trong simple broker tích hợp của Spring chỉ là quy ước đặt tên để phân biệt pub/sub và point-to-point. Khi dùng external broker relay, hãy kiểm tra destination và prefix mà broker thực sự hỗ trợ.

## 6. Kết nối từ trình duyệt bằng STOMP.js

Spring hướng dẫn dùng thư viện **@stomp/stompjs** cho client JavaScript hiện đại.

Cài package trong frontend:

~~~bash
npm install @stomp/stompjs
~~~

Ví dụ kết nối WebSocket trực tiếp:

~~~javascript
import { Client } from '@stomp/stompjs';

const client = new Client({
    brokerURL: 'ws://localhost:8080/stomp',
    reconnectDelay: 5000,

    onConnect: () => {
        console.log('STOMP connected');

        client.subscribe('/topic/public', (frame) => {
            const message = JSON.parse(frame.body);
            console.log('Received:', message);
        });

        client.publish({
            destination: '/app/chat.send',
            body: JSON.stringify({
                from: 'alice',
                text: 'Hello Spring STOMP'
            })
        });
    },

    onStompError: (frame) => {
        console.error('STOMP broker error:', frame.headers['message']);
        console.error(frame.body);
    },

    onWebSocketError: (event) => {
        console.error('WebSocket transport error:', event);
    }
});

client.activate();
~~~

**brokerURL** là URL transport, ví dụ **ws://localhost:8080/stomp**. Trong production có HTTPS, dùng **wss://**:

~~~javascript
brokerURL: 'wss://api.example.com/messaging/stomp'
~~~

**reconnectDelay** đặt khoảng chờ trước khi STOMP.js thử kết nối lại sau khi mất kết nối. Callback **onConnect** được gọi sau mỗi lần kết nối thành công, vì vậy subscription nên được tạo trong callback này để được đăng ký lại sau reconnect.

Khi component hoặc trang không còn cần kết nối, gọi:

~~~javascript
await client.deactivate();
~~~

Việc đóng STOMP client giúp giải phóng WebSocket session và tránh giữ kết nối không cần thiết.

## 7. Kết nối qua SockJS fallback

Một số proxy hoặc mạng doanh nghiệp chặn WebSocket Upgrade hoặc đóng kết nối lâu không có hoạt động. SockJS cung cấp các transport thay thế dựa trên HTTP như streaming và long polling.

Bật SockJS trên server:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/stomp").withSockJS();
}
~~~

Client dùng **sockjs-client** làm WebSocket factory:

~~~bash
npm install @stomp/stompjs sockjs-client
~~~

~~~javascript
import { Client } from '@stomp/stompjs';
import SockJS from 'sockjs-client';

const client = new Client({
    webSocketFactory: () => new SockJS('/stomp'),
    reconnectDelay: 5000,

    onConnect: () => {
        console.log('STOMP connected through SockJS');

        client.subscribe('/topic/public', (frame) => {
            console.log('Received:', frame.body);
        });
    },

    onStompError: (frame) => {
        console.error('STOMP error:', frame.headers['message']);
    }
});

client.activate();
~~~

Với SockJS, truyền URL gốc của endpoint vào **new SockJS(...)**. Không tự thêm các đoạn **/websocket**, server ID, session ID hoặc transport suffix. SockJS client tự gọi **/info**, chọn transport và xây dựng các URL HTTP cần thiết.

Nếu ứng dụng có context path **/messaging**, client cùng origin dùng:

~~~javascript
webSocketFactory: () => new SockJS('/messaging/stomp')
~~~

Nếu frontend ở domain khác, dùng URL HTTPS đầy đủ và cấu hình allowed origins/CORS phù hợp cho SockJS transports.

SockJS không thay đổi destination STOMP. Sau khi transport kết nối, client vẫn gửi **SUBSCRIBE /topic/public** và **SEND /app/chat.send** như khi dùng WebSocket trực tiếp.

## 8. Ví dụ hoàn chỉnh về endpoint và message destination

Cấu hình server:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/stomp");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry config) {
        config.setApplicationDestinationPrefixes("/app");
        config.enableSimpleBroker("/topic");
    }
}
~~~

DTO:

~~~java
public record ChatMessage(String from, String text) {
}
~~~

Controller:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/public")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}
~~~

Client kết nối transport:

~~~text
ws://localhost:8080/stomp
~~~

Client gửi message:

~~~text
SEND
destination:/app/chat.send

{"from":"alice","text":"Hello"}
~~~

Client đăng ký nhận:

~~~text
SUBSCRIBE
id:public-subscription
destination:/topic/public

~~~

Khi client gửi tới **/app/chat.send**, Spring định tuyến tới **ChatController.send**. Giá trị trả về được publish đến **/topic/public**; mọi client đã subscribe destination đó sẽ nhận message.

Ví dụ này là các thành phần tích hợp trong ứng dụng Spring, cần dependency **spring-messaging**, **spring-websocket**, cấu hình web server và frontend STOMP client. Không thể chạy riêng controller bằng **javac** mà không có Spring application context.

## 9. Allowed origins và handshake

Endpoint WebSocket bắt đầu bằng một HTTP request. Với browser, request thường mang header **Origin**. Spring kiểm tra origin để hạn chế website bên ngoài mở kết nối thay mặt người dùng đang đăng nhập.

Mặc định, Spring chỉ cho phép cùng origin. Nếu frontend và backend chạy ở hai origin khác nhau, thêm origin cụ thể:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/stomp")
            .setAllowedOrigins("https://app.example.com");
}
~~~

Origin gồm scheme, host và port nếu có. Không thêm path như **/dashboard** vào origin.

Không nên cấu hình **\*** cho production nếu không có lý do rõ ràng. Kiểm tra Origin giúp bảo vệ browser session, nhưng không thay thế authentication: một client không phải browser có thể tự gửi header Origin. Server vẫn phải xác thực người dùng và phân quyền message.

Allowed origins cũng khác với cấu hình CORS cho REST API. Khi dùng SockJS, các HTTP streaming/polling transport có thể cần CORS headers; Spring SockJS service có cơ chế hỗ trợ cho các transport đó.

## 10. Handshake interceptor và thông tin phiên

**StompEndpointRegistration** cho phép thêm **HandshakeInterceptor**:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/stomp")
            .addInterceptors(handshakeInterceptor());
}
~~~

Handshake interceptor chạy quanh quá trình bắt đầu WebSocket handshake. Nó có thể:

- Kiểm tra thông tin trong HTTP request.
- Đưa thuộc tính cần thiết vào WebSocket session attributes.
- Ghi nhận dữ liệu phục vụ tracing hoặc audit.
- Từ chối handshake nếu điều kiện của ứng dụng không đạt.

Ví dụ trên giả định **handshakeInterceptor()** là bean hoặc method trả về một implementation **HandshakeInterceptor** do ứng dụng cung cấp.

Không dùng interceptor để thay thế authorization cho từng STOMP message. Người dùng có thể kết nối thành công nhưng vẫn không được phép gửi hoặc subscribe một destination cụ thể.

## 11. Authentication và authorization cho STOMP

Trong Spring WebSocket, **Principal** đã xác thực trên HTTP request handshake được gắn với WebSocket session. Nếu ứng dụng dùng Spring Security, cách thông thường là xác thực HTTP trước khi client mở WebSocket.

Một số điểm quan trọng:

- Header **login** và **passcode** của STOMP **CONNECT** bị Spring bỏ qua hoặc ghi đè theo mặc định đối với STOMP over WebSocket.
- Có thể dùng HTTP session/cookie hoặc cơ chế xác thực HTTP đã có.
- Nếu cần token trong STOMP **CONNECT**, ứng dụng phải cấu hình interceptor ở inbound channel để xác thực header token theo thiết kế riêng.
- Với **@EnableWebSocketSecurity**, Spring Security yêu cầu CSRF token trên inbound **CONNECT** theo mặc định.
- Phải phân quyền riêng cho các frame **SEND** và **SUBSCRIBE**.

Ví dụ về chính sách authorization nên phân biệt:

| Frame | Ví dụ destination | Quyền cần kiểm tra |
|---|---|---|
| SEND | /app/chat.send | Người dùng có được gửi message vào chức năng chat không? |
| SUBSCRIBE | /topic/public | Người dùng có được xem kênh công khai không? |
| SUBSCRIBE | /user/queue/notifications | Người dùng có được nhận message cá nhân của mình không? |
| SEND | /topic/system/notifications | Có nên chặn client tự gửi vào destination chỉ dành cho server không? |

Không tin dữ liệu định danh người gửi do client gửi trong payload. Server nên lấy người dùng từ **Principal** đã xác thực rồi gắn danh tính đó vào message nghiệp vụ.

## 12. Context path, reverse proxy và TLS

URL client có thể đúng trong local nhưng sai khi triển khai vì context path hoặc reverse proxy thay đổi đường dẫn bên ngoài.

Ví dụ:

- Ứng dụng Spring có **server.servlet.context-path=/messaging**.
- Endpoint đăng ký bằng **registry.addEndpoint("/stomp")**.
- Reverse proxy công khai ứng dụng ở **https://example.com/messaging**.

Client phải kết nối tới:

~~~text
wss://example.com/messaging/stomp
~~~

Khi triển khai sau Nginx, Apache hoặc load balancer:

- Proxy phải chuyển tiếp HTTP Upgrade và các header **Upgrade**/**Connection** cho WebSocket.
- Dùng **wss://** khi trang web được phục vụ qua HTTPS.
- Giữ đúng context path hoặc cấu hình rewrite tương ứng.
- Cấu hình timeout cho kết nối lâu dài.
- Nếu chạy nhiều instance, kiểm tra routing/sticky session và cách broker chia sẻ subscription.
- Nếu proxy kết thúc TLS, đảm bảo scheme bên ngoài mà client sử dụng là **wss**.

Với SockJS, proxy còn phải chuyển tiếp các HTTP request của transport streaming/polling tới cùng endpoint.

## 13. Chẩn đoán lỗi kết nối

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| HTTP 404 khi kết nối | Sai endpoint path hoặc thiếu context path | So sánh URL client với addEndpoint và context path |
| HTTP 403 khi handshake | Origin không được phép hoặc Spring Security từ chối | Kiểm tra Origin, authentication, CSRF và security filter |
| HTTP 400/426 hoặc không Upgrade | Proxy/server không chuyển tiếp WebSocket Upgrade | Kiểm tra Upgrade, Connection và cấu hình proxy |
| WebSocket mở nhưng STOMP CONNECT lỗi | Client/server không thống nhất STOMP protocol hoặc auth/CSRF lỗi | Xem frame ERROR, server log và CONNECT headers |
| Kết nối thành công nhưng không nhận message | Subscribe sai destination hoặc broker prefix | Kiểm tra SUBSCRIBE và enableSimpleBroker |
| @MessageMapping không được gọi | Client SEND sai application prefix | Kiểm tra /app và mapping method |
| Hoạt động local, lỗi khi HTTPS | Client dùng ws:// từ trang HTTPS | Chuyển sang wss:// hoặc HTTPS SockJS |
| SockJS /info trả 404 | Client dùng sai base URL hoặc server chưa bật withSockJS | Kiểm tra endpoint path và URL gốc |
| Reconnect được nhưng không nhận message | Subscription chưa được tạo lại sau reconnect | Đăng ký subscription trong onConnect |
| Browser báo CORS/origin | Frontend khác origin hoặc SockJS HTTP transport chưa được cấu hình | Kiểm tra allowed origins và CORS response |

Khi debug, kiểm tra theo thứ tự: HTTP handshake, STOMP CONNECT/CONNECTED, SUBSCRIBE, SEND và MESSAGE. Một kết nối WebSocket thành công chưa chứng minh STOMP session hoặc subscription đã hoạt động.

## 14. Kiểm thử endpoint

Nên kiểm thử cả URL transport và luồng message:

1. Khởi động ứng dụng và xác nhận endpoint handshake trả về thành công.
2. Dùng client STOMP kết nối tới đúng URL có context path.
3. Xác nhận nhận được frame **CONNECTED**.
4. Subscribe một destination như **/topic/public**.
5. Gửi message tới **/app/chat.send**.
6. Xác nhận controller **@MessageMapping** được gọi.
7. Xác nhận subscriber nhận frame **MESSAGE**.
8. Thử kết nối từ origin không được phép và xác nhận bị từ chối.
9. Nếu bật SockJS, thử WebSocket transport và một HTTP fallback transport.
10. Thử mất mạng, reconnect và xác nhận subscription được tạo lại.

Có thể dùng Spring **WebSocketStompClient** trong integration test hoặc **@stomp/stompjs** trong browser. Khi test qua proxy, phải dùng URL bên ngoài mà client production thực sự sử dụng.

## 15. Lỗi thường gặp

- **Dùng /app làm URL WebSocket:** /app thường là application destination prefix của STOMP. URL handshake phải là path đã đăng ký bằng addEndpoint.
- **Dùng /stomp làm destination để gửi message:** /stomp là endpoint transport; SEND cần destination như /app/chat.send.
- **Quên context path:** server chạy dưới /messaging nên URL bên ngoài phải chứa prefix đó.
- **Bật SockJS trên server nhưng client dùng sai loại factory:** SockJS client cần webSocketFactory tạo SockJS từ base endpoint URL.
- **Tự nối /websocket vào SockJS URL:** SockJS client tự xây dựng transport path.
- **Cấu hình allowed origins bằng URL có path:** Origin chỉ gồm scheme, host và port.
- **Cho rằng allowed origins là authentication:** Origin chỉ là một lớp kiểm soát browser; vẫn cần authentication và authorization.
- **Không dùng wss khi trang chạy HTTPS:** browser có thể chặn mixed content.
- **Chỉ subscribe một lần lúc tạo client:** sau reconnect, subscription cần được tạo lại trong onConnect.
- **Dùng prefix /topic hoặc /queue mà không kiểm tra external broker:** các prefix này là quy ước của simple broker; external broker có thể có destination syntax khác.
- **Cho rằng kết nối WebSocket thành công nghĩa là message đã được định tuyến:** cần kiểm tra STOMP frame và broker/controller flow.

## 16. Checklist triển khai

- [ ] Đã thêm spring-messaging và spring-websocket.
- [ ] Đã bật @EnableWebSocketMessageBroker.
- [ ] Đã đăng ký endpoint path bằng registerStompEndpoints.
- [ ] Đã xác định URL đầy đủ gồm scheme, host, port, context path và endpoint path.
- [ ] Đã phân biệt endpoint path với /app, /topic, /queue.
- [ ] Client dùng ws/wss hoặc SockJS factory đúng cấu hình server.
- [ ] Nếu dùng SockJS, server đã gọi withSockJS và client dùng URL gốc.
- [ ] Đã cấu hình allowed origins cho frontend khác origin.
- [ ] Đã bật authentication và authorization cho handshake/STOMP message.
- [ ] Đã xử lý CSRF token nếu Spring Security yêu cầu.
- [ ] Reverse proxy chuyển tiếp WebSocket Upgrade và timeout phù hợp.
- [ ] Client subscribe lại sau reconnect và gọi deactivate khi kết thúc.
- [ ] Đã kiểm thử CONNECT, SUBSCRIBE, SEND, MESSAGE, reconnect và origin bị từ chối.

## 17. Tài liệu tham khảo

- [Spring Framework 7.0.10 — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Spring Framework 7.0.10 — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework 7.0.10 — SockJS Fallback](https://docs.spring.io/spring-framework/reference/web/websocket/fallback.html)
- [Spring Framework 7.0.10 — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)
- [Spring Framework 7.0.10 — STOMP Overview](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Security 7 — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [STOMP.js — JavaScript/TypeScript STOMP client](https://github.com/stomp-js/stompjs)
