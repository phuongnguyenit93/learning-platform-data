# SockJS và các phương thức truyền dự phòng trong Spring WebSocket

## 1. Vì sao cần SockJS?

WebSocket cung cấp kết nối hai chiều full-duplex trên một TCP connection. Sau HTTP handshake có Upgrade thành công, client và server trao đổi frame trên cùng kết nối với độ trễ thấp.

Tuy nhiên, một số mạng doanh nghiệp, proxy hoặc load balancer không chuyển tiếp header Upgrade, đóng kết nối dài hạn khi tưởng rằng nó đang idle, hoặc áp dụng chính sách chỉ cho phép một số kiểu HTTP request. Trong những môi trường đó, WebSocket thuần có thể không kết nối được dù trình duyệt hỗ trợ giao thức.

SockJS giải quyết vấn đề tương thích bằng cách mô phỏng API WebSocket. Client thử WebSocket trước; nếu transport đó không khả dụng, client tự chọn một kỹ thuật HTTP streaming hoặc HTTP long polling. Ứng dụng vẫn làm việc với cùng một API cấp ứng dụng, nên phần xử lý message thường không cần thay đổi theo transport được chọn.

Spring Framework cung cấp SockJS server và Java client trong module spring-websocket. Ở phía trình duyệt, ứng dụng dùng thư viện sockjs-client. SockJS có thể được dùng với WebSocketHandler thuần hoặc làm transport cho STOMP messaging.

Cần phân biệt ba tầng:

- **WebSocket:** giao thức truyền frame hai chiều.
- **SockJS:** giao thức emulation và bộ lựa chọn transport để duy trì API tương tự WebSocket khi WebSocket không dùng được.
- **STOMP:** messaging protocol chạy bên trên WebSocket hoặc SockJS, cung cấp SEND, SUBSCRIBE, MESSAGE và các command messaging khác.

SockJS không phải message broker, không tự định nghĩa destination nghiệp vụ và không thay thế STOMP.

## 2. SockJS lựa chọn transport như thế nào?

Khi client bắt đầu kết nối, nó gửi một HTTP GET đến endpoint với đường dẫn /info. Server trả về thông tin cần thiết để client quyết định transport, chẳng hạn WebSocket có được bật hay không và ứng dụng có cần cookie session hay không.

Sau đó client lựa chọn theo khả năng của trình duyệt và môi trường mạng:

1. Dùng WebSocket nếu handshake có thể thực hiện.
2. Nếu WebSocket không dùng được, thử một transport HTTP streaming phù hợp.
3. Nếu streaming cũng không khả dụng, chuyển sang HTTP long polling.

Việc lựa chọn diễn ra ở runtime. Cùng một ứng dụng có thể dùng WebSocket trên mạng này và XHR streaming hoặc long polling trên mạng khác.

Các request SockJS thường có cấu trúc:

~~~text
https://host:port/app/endpoint/{server-id}/{session-id}/{transport}
~~~

Trong đó:

- server-id hỗ trợ định tuyến request trong môi trường cluster; ứng dụng có thể dùng nó để hỗ trợ sticky routing.
- session-id liên kết các HTTP request thuộc cùng một SockJS session.
- transport cho biết kỹ thuật đang được sử dụng, ví dụ websocket, xhr-streaming hoặc xhr-polling.

Với WebSocket transport, client chỉ cần một request handshake; các message tiếp theo đi qua socket đó. Với HTTP transports, một SockJS session có thể tạo nhiều request và server cần liên kết chúng bằng session-id.

## 3. Ba nhóm transport chính

Spring chia transport SockJS thành ba nhóm: WebSocket, HTTP Streaming và HTTP Long Polling.

### 3.1. WebSocket transport

Đây là lựa chọn ưu tiên khi môi trường cho phép Upgrade handshake và giữ kết nối lâu dài.

- Một HTTP handshake chuyển kết nối sang WebSocket.
- Client và server gửi frame hai chiều trên cùng socket.
- Không phải mở một HTTP request mới cho mỗi message.
- Độ trễ và overhead thường thấp hơn các fallback HTTP.

Nếu WebSocket hoạt động ổn định qua proxy và load balancer, SockJS client thường chọn transport này.

### 3.2. HTTP Streaming

HTTP streaming giữ một request nhận dữ liệu từ server mở trong thời gian dài. Server ghi thêm dữ liệu vào response khi có message mới. Client gửi dữ liệu lên server bằng các HTTP POST request riêng.

Các transport thường gặp trong nhóm này gồm xhr-streaming, eventsource và một số kỹ thuật iframe dành cho trình duyệt cũ.

Đặc điểm:

- Một request nhận dữ liệu có thể tồn tại trong thời gian dài.
- Client-to-server thường dùng POST riêng.
- Server có thể gửi nhiều message trên cùng response streaming.
- Khi response đạt giới hạn byte hoặc kết nối bị đóng, client tạo request mới để tiếp tục session.

HTTP streaming giảm số lần request nhận so với polling. Tuy nhiên, proxy có thể buffer response hoặc đóng request dài hạn; cần kiểm thử với hạ tầng thật.

### 3.3. HTTP Long Polling

Long polling dùng một chuỗi request nhận dữ liệu:

1. Client gửi GET để chờ server có message.
2. Server giữ request mở cho đến khi có message hoặc hết thời gian chờ.
3. Server trả response và kết thúc request.
4. Client lập tức mở request GET tiếp theo.
5. Client gửi dữ liệu lên server qua HTTP POST riêng.

Long polling tương thích với nhiều proxy và hạ tầng HTTP hơn, nhưng tạo nhiều request, header và lần thiết lập HTTP hơn. Khi không có message, client vẫn phải mở lại request theo chu kỳ.

Transport phổ biến có tên xhr-polling hoặc xhr. Một số trình duyệt cũ dùng iframe-xhr-polling hoặc jsonp-polling.

## 4. Những transport cụ thể thường gặp

Tên transport phụ thuộc trình duyệt và phiên bản sockjs-client. Các tên thường thấy gồm:

| Nhóm | Tên transport | Cách hoạt động |
| --- | --- | --- |
| WebSocket | websocket | Kết nối WebSocket tiêu chuẩn |
| HTTP Streaming | xhr-streaming | XHR giữ response mở để nhận nhiều message |
| HTTP Streaming | eventsource | Dựa trên Server-Sent Events cho chiều server-to-client, kết hợp request gửi riêng |
| HTTP Streaming | htmlfile, iframe-eventsource, iframe-htmlfile | Kỹ thuật dự phòng cho một số trình duyệt cũ |
| HTTP Long Polling | xhr, xhr-polling | GET chờ message rồi kết thúc; client mở request tiếp theo |
| HTTP Long Polling | iframe-xhr-polling | Long polling qua iframe |
| HTTP Long Polling | jsonp-polling | Kỹ thuật polling cũ dựa trên JSONP |
| HTTP Streaming/Polling | xdr-streaming, xdr-polling | Dùng XDomainRequest trên một số trình duyệt IE cũ |

Không phải mọi trình duyệt đều hỗ trợ mọi transport. SockJS client có ma trận tương thích riêng và tự chọn các phương thức khả dụng. Khi điều tra lỗi, hãy xem transport thực tế trong Network tab thay vì giả định mọi client đều dùng WebSocket.

Spring SockJS Java client có tập transport hẹp hơn client trình duyệt: hỗ trợ websocket, xhr-streaming và xhr-polling. Các kỹ thuật iframe và JSONP chủ yếu phục vụ trình duyệt cũ.

## 5. So sánh WebSocket, streaming và long polling

| Tiêu chí | WebSocket | HTTP Streaming | HTTP Long Polling |
| --- | --- | --- | --- |
| Kết nối nhận dữ liệu | Một socket dài hạn | Một HTTP response mở lâu | Nhiều GET request nối tiếp |
| Gửi dữ liệu lên server | Frame trên cùng socket | HTTP POST riêng | HTTP POST riêng |
| Overhead request | Thấp sau handshake | Trung bình | Cao hơn do nhiều request |
| Khả năng qua proxy | Phụ thuộc Upgrade và chính sách socket | Phụ thuộc proxy có cho response streaming hay không | Thường tương thích rộng hơn |
| Độ trễ | Thấp | Thấp đến trung bình | Phụ thuộc chu kỳ request |
| Tài nguyên server | Giữ WebSocket session | Giữ request/response streaming | Liên tục mở và kết thúc request |
| Trường hợp phù hợp | Mạng hỗ trợ WebSocket | WebSocket bị chặn nhưng streaming hoạt động | Streaming bị chặn hoặc môi trường chỉ hỗ trợ request-response |

Fallback tăng khả năng kết nối nhưng thường có chi phí về request, header, buffering, thread hoặc tài nguyên HTTP. Hãy xem transport được chọn là một đặc tính vận hành cần theo dõi.

## 6. SockJS framing

SockJS bổ sung một lớp framing nhỏ để biểu diễn trạng thái session và danh sách message trên các transport khác nhau.

Một số frame tiêu biểu:

| Frame | Ý nghĩa |
| --- | --- |
| o | Mở SockJS session |
| a["message1","message2"] | Một mảng JSON chứa các message ứng dụng |
| h | Heartbeat của SockJS |
| c[code,"reason"] | Đóng session cùng mã và lý do |

Ví dụ server gửi hai message:

~~~text
a["first message","second message"]
~~~

Client SockJS giải mã framing này rồi chuyển message tới callback giống API WebSocket. Ứng dụng thường không cần tự parse các frame o, a, h hoặc c.

Với STOMP over SockJS, bên trong message SockJS còn có STOMP frame. SockJS đảm nhiệm transport emulation; STOMP đảm nhiệm command và destination messaging.

Không gửi raw WebSocket frame trực tiếp vào một endpoint STOMP/SockJS với giả định hai giao thức có cùng framing. Client và server phải dùng đúng thư viện và sub-protocol tương ứng.

## 7. Bật SockJS cho WebSocketHandler thuần

Nếu ứng dụng sử dụng WebSocketHandler thuần, có thể bật SockJS ngay trên mapping handler bằng withSockJS():

~~~java
@Configuration
@EnableWebSocket
public class RawWebSocketConfiguration implements WebSocketConfigurer {

    @Bean
    public WebSocketHandler echoHandler() {
        return new EchoWebSocketHandler();
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler(), "/ws/raw")
                .setAllowedOrigins("https://app.example.com")
                .withSockJS();
    }
}
~~~

Bean echoHandler được đăng ký trong Spring context và được dùng cho endpoint /ws/raw. Endpoint này chấp nhận WebSocket hoặc các transport SockJS mà client có thể lựa chọn.

Handler vẫn nhận callback của WebSocketHandler như afterConnectionEstablished, handleMessage và afterConnectionClosed. Spring SockJS chuyển các transport fallback về cùng mô hình session/handler để ứng dụng xử lý.

Ví dụ giả định EchoWebSocketHandler đã được triển khai. Cần cấu hình component scanning hoặc khai báo bean như trên để Spring có thể sử dụng handler.

## 8. Bật SockJS cho STOMP endpoint

Nếu ứng dụng sử dụng Spring messaging cấp cao, bật SockJS trên STOMP endpoint:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.com")
                .withSockJS();
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Client kết nối đến /ws. SockJS client sẽ chọn WebSocket hoặc HTTP fallback; STOMP client tiếp tục trao đổi CONNECT, SEND, SUBSCRIBE và MESSAGE qua transport đã chọn.

Ví dụ JavaScript với @stomp/stompjs và sockjs-client:

~~~javascript
import { Client } from "@stomp/stompjs";
import SockJS from "sockjs-client";

const client = new Client({
    webSocketFactory: () => new SockJS("/ws"),
    reconnectDelay: 5000,
    onConnect: () => {
        client.subscribe("/topic/updates", frame => {
            console.log(frame.body);
        });
    }
});

client.activate();
~~~

webSocketFactory trả về SockJS object cho STOMP client. Khi kết nối thành công, client đăng ký /topic/updates. Nếu transport hiện tại bị mất, reconnectDelay cho phép STOMP client thử kết nối lại; ứng dụng cần đăng ký lại subscription trong onConnect.

Không tạo SockJS object một lần rồi tái sử dụng cho nhiều lần reconnect. Factory được gọi để tạo một transport instance mới cho mỗi lần kết nối.

## 9. Cấu hình các giới hạn và thời gian trên server

Spring cho phép tùy chỉnh các thuộc tính SockJS thông qua đối tượng trả về từ withSockJS().

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
            .setAllowedOrigins("https://app.example.com")
            .withSockJS()
            .setHeartbeatTime(25_000)
            .setDisconnectDelay(5_000)
            .setStreamBytesLimit(128 * 1024)
            .setHttpMessageCacheSize(100)
            .setSessionCookieNeeded(true);
}
~~~

Các giá trị trong ví dụ tương ứng với mặc định Spring phổ biến:

| Thuộc tính | Mặc định | Vai trò |
| --- | --- | --- |
| heartbeatTime | 25 giây | Khoảng thời gian gửi heartbeat khi không có message khác |
| disconnectDelay | 5 giây | Khoảng chờ để nhận request tiếp theo trước khi coi HTTP-based session đã ngắt |
| streamBytesLimit | 128 KiB | Số byte tối thiểu gửi trên một HTTP streaming response trước khi response được đóng và client mở request mới |
| httpMessageCacheSize | 100 | Số message được cache cho HTTP transport/session |
| sessionCookieNeeded | true | Báo cho client rằng ứng dụng cần cookie session, ví dụ JSESSIONID |

Không tăng streamBytesLimit hoặc httpMessageCacheSize tùy tiện. Streaming giữ response mở và có thể giữ dữ liệu đã gửi trong bộ nhớ phía client; cache lớn hơn cũng làm tăng bộ nhớ server cho session HTTP. Hãy điều chỉnh theo kích thước message, số session đồng thời và giới hạn bộ nhớ.

Nếu cần kiểm soát lịch gửi heartbeat, có thể cấu hình TaskScheduler riêng. Scheduler cần đủ thread cho số session và nhịp heartbeat dự kiến.

## 10. Heartbeat và phát hiện client mất kết nối

Heartbeat giúp proxy và load balancer không xem một kết nối lâu không có dữ liệu là kết nối đã chết.

Spring SockJS mặc định gửi heartbeat sau 25 giây nếu không có message khác được gửi trên connection. Khi có message ứng dụng, heartbeat không cần thiết trong khoảng đó.

Khi dùng STOMP over SockJS:

- Nếu client và server thương lượng STOMP heartbeat, SockJS heartbeat sẽ bị tắt.
- STOMP heartbeat khi đó đảm nhiệm việc kiểm tra luồng trao đổi.
- Nếu STOMP heartbeat không được thương lượng, SockJS heartbeat vẫn được dùng theo cấu hình.

Với HTTP streaming và long polling, Servlet API không luôn thông báo ngay khi client đã rời mạng. Spring có thể phát hiện disconnect khi lần ghi response tiếp theo thất bại; heartbeat giúp phát hiện trường hợp này sớm hơn.

Lỗi ghi response sau khi client ngắt là tình huống vận hành có thể xảy ra. Spring cố gắng nhận diện lỗi network tương ứng và ghi log tối giản. Có thể bật TRACE cho log category SockJS khi cần điều tra sâu.

## 11. CORS, Origin và cookie session

HTTP streaming và long polling dùng HTTP request nên chịu ảnh hưởng của CORS. Spring SockJS tự thêm các CORS header cần thiết khi chưa có header tương ứng từ tầng khác. Nếu ứng dụng đã cấu hình CORS qua Servlet Filter hoặc security layer, SockJS có thể phát hiện và bỏ qua phần header đã có.

Một số điểm cần chú ý:

- Cấu hình allowed origins theo domain frontend thực tế.
- Không dùng CORS như cơ chế xác thực hoặc phân quyền.
- Với request có credentials, cookie và session phải được xử lý nhất quán.
- sessionCookieNeeded mặc định true vì nhiều ứng dụng Java cần JSESSIONID cho HTTP session hoặc sticky session.
- Nếu ứng dụng không cần cookie session, có thể cân nhắc đặt sessionCookieNeeded(false) để client có thêm lựa chọn transport trên một số trình duyệt cũ.

Khi giới hạn allowed origins, một số transport iframe hoặc JSONP không gửi Origin header có thể bị vô hiệu hóa. Điều này có thể làm một số trình duyệt cũ không còn transport phù hợp.

### 11.1. Iframe transport và X-Frame-Options

Một số transport cũ dùng iframe để thực hiện cross-domain communication. Nếu response đặt X-Frame-Options: DENY, trình duyệt sẽ chặn iframe.

Nếu vẫn cần transport iframe cho client cũ, cần cấu hình frame policy phù hợp với kiến trúc và chính sách bảo mật, ví dụ SAMEORIGIN khi iframe cùng origin. Không nới lỏng X-Frame-Options chỉ để làm cho fallback hoạt động nếu không có nhu cầu hỗ trợ transport đó.

Spring SockJS cũng cho phép đặt client library URL cho iframe. Trong môi trường production, nên phục vụ thư viện SockJS client từ cùng origin nếu phù hợp với chính sách CSP và cache của ứng dụng.

## 12. SockJS trong môi trường cluster và load balancer

Một SockJS session có thể gồm nhiều HTTP request, đặc biệt với streaming và long polling. Các request đó phải được liên kết với cùng session-id.

Trong môi trường nhiều instance:

- Dùng server-id trong URL để hỗ trợ routing nếu load balancer cần.
- Cấu hình sticky session để các request của cùng SockJS session đến đúng instance đang giữ session.
- Đảm bảo timeout của proxy/load balancer phù hợp với heartbeat và thời gian giữ request.
- Kiểm tra rằng HTTP POST gửi message và GET nhận message cùng được định tuyến tới instance phù hợp.
- Khi instance restart, client cần reconnect và tạo session mới.

Simple in-memory session state của một instance không tự chia sẻ sang instance khác. Nếu cần nhiều node, phải thiết kế routing, sticky session hoặc hạ tầng messaging/broker phù hợp. Broker relay giải quyết phân phối STOMP message giữa node theo cấu hình broker, nhưng không tự thay thế yêu cầu định tuyến HTTP request thuộc cùng SockJS session.

## 13. SockJsClient phía Java

Spring cung cấp SockJsClient để kết nối đến SockJS server từ một ứng dụng Java mà không cần trình duyệt. Client này hữu ích cho tích hợp server-to-server, kiểm thử hoặc mô phỏng nhiều kết nối.

SockJsClient của Spring hỗ trợ các transport:

- WebSocketTransport, có thể dùng StandardWebSocketClient trong runtime JSR-356 hoặc một Spring WebSocketClient khác.
- XhrTransport, hỗ trợ cả xhr-streaming và xhr-polling.
- RestClientXhrTransport sử dụng Spring RestClient cho HTTP request.
- JettyXhrTransport sử dụng Jetty HttpClient.

Ví dụ tạo client:

~~~java
List<Transport> transports = new ArrayList<>();
transports.add(new WebSocketTransport(new StandardWebSocketClient()));
transports.add(new RestClientXhrTransport());

SockJsClient sockJsClient = new SockJsClient(transports);
sockJsClient.doHandshake(new MyWebSocketHandler(), "ws://example.com:8080/sockjs");
~~~

MyWebSocketHandler là WebSocketHandler của ứng dụng. Để chạy ví dụ cần dependency spring-websocket, thư viện client transport tương ứng và endpoint SockJS đang hoạt động.

Khi mô phỏng nhiều user đồng thời bằng XHR transport, cần cấu hình HTTP client đủ connection và thread. Nếu HTTP client chỉ cho phép một số ít connection đến cùng host, các session mô phỏng có thể xếp hàng hoặc timeout dù server còn khả năng xử lý.

## 14. Giới hạn và chi phí của fallback

SockJS cải thiện khả năng tương thích, nhưng fallback HTTP có một số chi phí:

- Nhiều request và header hơn WebSocket.
- Streaming giữ response mở và có thể bị proxy buffer.
- Long polling tạo request mới sau mỗi lần nhận message.
- Client và server cần quản lý session qua nhiều request.
- CORS, cookie, sticky session và timeout proxy phức tạp hơn.
- Độ trễ và throughput phụ thuộc transport được chọn.
- HTTP fallback không làm mọi môi trường mạng đều hoạt động; firewall hoặc proxy có thể chặn cả các request HTTP cần thiết.

Hãy đo số session theo transport, số request polling, thời gian response streaming, heartbeat, reconnect và lỗi network. Không chỉ theo dõi tổng số WebSocket connection vì các session fallback có thể không tạo WebSocket connection thực sự.

## 15. Cách kiểm tra transport đang được sử dụng

Có thể kiểm tra từ trình duyệt:

1. Mở Developer Tools và chọn Network.
2. Tìm request /info để xem client có lấy được thông tin SockJS hay không.
3. Quan sát URL transport sau đó, ví dụ websocket, xhr_streaming hoặc xhr.
4. Kiểm tra request GET dài hạn và POST gửi message nếu đang dùng HTTP fallback.
5. Theo dõi mã HTTP, thời gian response, CORS header, cookie và các lần reconnect.

Ở phía server, bật TRACE cho package org.springframework.web.socket để xem chi tiết transport và session. Trong môi trường production, chỉ bật log chi tiết trong thời gian điều tra vì log có thể chứa nhiều thông tin kết nối.

Nếu client chọn polling trong khi WebSocket đáng lẽ hoạt động, kiểm tra proxy Upgrade header, TLS termination, load balancer idle timeout và cấu hình endpoint. Nếu client không kết nối được cả fallback, kiểm tra /info, CORS, authentication, cookie và routing của session.

## 16. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| /info trả 404 | Endpoint SockJS chưa được đăng ký hoặc sai context path | Kiểm tra addHandler/addEndpoint và withSockJS |
| WebSocket thất bại nhưng client không fallback | SockJS client chưa được dùng hoặc danh sách transport bị giới hạn | Dùng sockjs-client và kiểm tra cấu hình transport |
| XHR streaming mở nhưng không nhận message | Proxy buffer response hoặc timeout đóng request | Kiểm tra proxy buffering, heartbeat và streamBytesLimit |
| Long polling tạo quá nhiều request | Client liên tục mở request nhận tiếp theo | Đây là đặc tính của polling; đánh giá khả năng dùng streaming/WebSocket |
| Client không gửi được cookie | Transport cũ không hỗ trợ cookie hoặc credentials/CORS sai | Kiểm tra sessionCookieNeeded, credentials và transport tương thích |
| Iframe transport bị chặn | X-Frame-Options hoặc CSP chặn iframe | Chỉ cho phép frame policy phù hợp nếu còn cần transport đó |
| Client ngắt sau khoảng thời gian idle | Proxy hoặc load balancer đóng kết nối lâu không có dữ liệu | Cấu hình heartbeat và idle timeout phù hợp |
| Client liên tục tạo session mới | Request của cùng session bị chuyển sang instance khác hoặc disconnectDelay quá ngắn | Cấu hình sticky session và kiểm tra load balancer |
| Server không phát hiện client đã rời | HTTP streaming không có notification disconnect ngay lập tức | Dùng heartbeat và theo dõi lỗi ghi response |
| STOMP client kết nối nhưng không nhận subscription | Nhầm transport fallback với destination hoặc subscription | Kiểm tra STOMP CONNECT, SUBSCRIBE và broker destination |
| Tăng cache gây thiếu bộ nhớ | httpMessageCacheSize hoặc streamBytesLimit quá lớn | Đo memory/session và đặt giới hạn phù hợp |
| SockJS Java client hết connection | HTTP client không đủ connection/thread cho số session | Tăng giới hạn connection và executor phù hợp |

## 17. Checklist triển khai

- [ ] Xác định có thật sự cần hỗ trợ môi trường không dùng được WebSocket.
- [ ] Bật withSockJS() trên đúng raw handler hoặc STOMP endpoint.
- [ ] Dùng sockjs-client ở trình duyệt khi endpoint yêu cầu SockJS.
- [ ] Kiểm tra request /info và transport thực tế.
- [ ] Kiểm thử WebSocket, HTTP streaming và long polling trong môi trường mạng mục tiêu.
- [ ] Cấu hình heartbeat phù hợp với proxy/load balancer idle timeout.
- [ ] Đặt streamBytesLimit, httpMessageCacheSize và disconnectDelay theo tải thực tế.
- [ ] Cấu hình CORS, allowed origins, cookie và credentials đúng.
- [ ] Nếu dùng cluster, cấu hình sticky routing cho cùng SockJS session.
- [ ] Kiểm tra X-Frame-Options nếu còn hỗ trợ iframe transport.
- [ ] Cấu hình reconnect và resubscribe ở client.
- [ ] Theo dõi số session theo transport, polling rate, reconnect, heartbeat và lỗi network.
- [ ] Giới hạn message size, số session và tốc độ gửi để bảo vệ tài nguyên server.

## 18. Tài liệu tham khảo

- [Spring Framework 7.0.10 — SockJS Fallback](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/fallback.html)
- [Spring Framework 7.0.10 — WebSocket API](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/server.html)
- [Spring Framework 7.0.10 — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp.html)
- [SockJS Protocol](https://github.com/sockjs/sockjs-protocol)
- [SockJS Client — Supported Transports](https://github.com/sockjs/sockjs-client)
- [Spring Framework API — SockJsClient](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/sockjs/client/SockJsClient.html)
- [Spring Framework API — SockJsServiceRegistration](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/config/annotation/SockJsServiceRegistration.html)
