# SockJsClient khi cần transport dự phòng trong Spring STOMP

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vấn đề mạng mà SockJS giải quyết và phân biệt SockJS với WebSocket thuần.
- Cấu hình endpoint SockJS ở phía Spring server.
- Tạo SockJsClient với WebSocket và HTTP transport dự phòng.
- Kết hợp SockJsClient với WebSocketStompClient để dùng STOMP mà không thay đổi mô hình xử lý message của ứng dụng.
- Phân biệt WebSocket, XHR streaming và XHR long polling về cách truyền dữ liệu và chi phí kết nối.
- Nhận biết các giới hạn của Java SockJS client, các khác biệt API giữa các phiên bản Spring và những yêu cầu về bảo mật, proxy, tài nguyên.
- Thiết kế reconnect, kiểm thử và giám sát phù hợp khi transport bị gián đoạn.

## 1. Vì sao cần SockJS?

WebSocket tạo một kết nối hai chiều lâu dài giữa client và server. Sau khi HTTP Upgrade thành công, hai phía có thể gửi dữ liệu trên cùng một kết nối. Cách này hiệu quả cho ứng dụng realtime, nhưng một số môi trường mạng không cho phép WebSocket hoạt động ổn định.

Các tình huống thường gặp:

- Proxy hoặc firewall không chuyển tiếp header HTTP Upgrade.
- Hạ tầng mạng chỉ cho phép một số loại HTTP request.
- Proxy đóng kết nối lâu dài khi cho rằng kết nối đang nhàn rỗi.
- Môi trường client cũ hoặc bị giới hạn không có triển khai WebSocket phù hợp.
- Hai server cần giao tiếp qua mạng công cộng có proxy trung gian.

SockJS cung cấp cơ chế mô phỏng WebSocket bằng nhiều transport. Client ưu tiên WebSocket khi có thể; nếu transport đó không dùng được, client có thể thử một phương thức HTTP tương thích. Nhờ vậy, ứng dụng vẫn dùng mô hình giao tiếp message hai chiều ở tầng ứng dụng.

SockJS không thay thế STOMP. Hai giao thức giải quyết hai lớp khác nhau:

- **SockJS** cung cấp cách vận chuyển dữ liệu và fallback khi WebSocket không khả dụng.
- **STOMP** định nghĩa frame, command, destination, subscription và message ở tầng ứng dụng.

Khi dùng STOMP trên SockJS, STOMP frame vẫn được gửi và nhận như trước; SockJS quyết định cách các byte/message đi qua mạng.

## 2. Phân biệt WebSocket thuần và SockJS

| Tiêu chí | WebSocket thuần | SockJS |
|---|---|---|
| Transport | WebSocket | WebSocket hoặc HTTP transport dự phòng |
| Bắt đầu kết nối | HTTP Upgrade | Yêu cầu thông tin endpoint, sau đó chọn transport |
| Mạng chỉ cho phép HTTP | Có thể không kết nối được | Có thể dùng XHR streaming hoặc long polling |
| API ứng dụng | WebSocket API | API mô phỏng WebSocket |
| Giao thức STOMP | Có thể chạy trên WebSocket | Có thể chạy trên SockJS transport |
| Chi phí truyền tải | Thường thấp hơn khi WebSocket hoạt động tốt | HTTP fallback có thêm request, framing và overhead |
| Lưu message khi offline | Không tự cung cấp | Không tự cung cấp |

SockJS không biến một kết nối mạng không ổn định thành kết nối có bảo đảm giao nhận nghiệp vụ. Nó cung cấp lựa chọn transport để tăng khả năng kết nối. Nếu cần lưu message, phát lại hoặc xác nhận xử lý, ứng dụng vẫn phải dùng cơ chế persistence và delivery phù hợp.

## 3. Phải bật SockJS ở phía server

Java SockJsClient cần kết nối tới một endpoint đã bật SockJS. Với Spring STOMP, gọi `withSockJS()` khi đăng ký STOMP endpoint:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOriginPatterns("https://app.example.com")
                .withSockJS();
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Trong ví dụ:

- `/ws` là base endpoint cho SockJS.
- `withSockJS()` bật các URL và transport theo giao thức SockJS.
- `/app` là application destination prefix cho các message gửi tới controller.
- `/topic` và `/queue` là broker destination prefix trong cấu hình minh họa.

Thay origin mẫu bằng origin thật của client. Nếu ứng dụng có Spring Security hoặc một lớp CORS riêng, cần bảo đảm các request SockJS được phép đi qua đúng quy tắc bảo mật. HTTP fallback tạo các request HTTP ngoài request bắt tay WebSocket, vì vậy không thể chỉ kiểm tra cấu hình Upgrade rồi kết luận mọi transport đều hoạt động.

**Quan trọng:** Nếu server chỉ đăng ký endpoint WebSocket thuần bằng `addEndpoint("/ws")` mà không gọi `withSockJS()`, SockJsClient không thể tự biến endpoint đó thành SockJS server. Hai phía phải thống nhất giao thức SockJS.

## 4. Các transport mà Java SockJsClient hỗ trợ

Java SockJS client của Spring hỗ trợ ba loại transport:

| Transport | Cách hoạt động | Khi phù hợp |
|---|---|---|
| `websocket` | Một request HTTP Upgrade tạo kết nối WebSocket; message tiếp tục đi trên socket đó | Lựa chọn ưu tiên khi mạng hỗ trợ |
| `xhr-streaming` | Duy trì một request HTTP dài để nhận dữ liệu từ server; client gửi dữ liệu bằng các HTTP POST riêng | Khi WebSocket không dùng được nhưng HTTP streaming hoạt động |
| `xhr-polling` | Client giữ request nhận dữ liệu; sau mỗi lần server trả dữ liệu, request kết thúc và client mở request mới | Phương án dự phòng khi streaming không khả dụng |

Một điểm cần nhớ: Java SockJsClient không hỗ trợ mọi transport dành cho trình duyệt. Các transport như iframe, htmlfile hoặc kỹ thuật dành riêng cho browser không nằm trong ba loại transport được Java client hỗ trợ.

### 4.1 WebSocket transport

`WebSocketTransport` sử dụng một implementation của Spring `WebSocketClient`. Có thể dùng:

- `StandardWebSocketClient` trong runtime có hỗ trợ Jakarta WebSocket (JSR-356).
- `JettyWebSocketClient` nếu ứng dụng dùng WebSocket API của Jetty.
- Một implementation `WebSocketClient` khác tương thích với Spring.

Khi WebSocket kết nối thành công, message đi qua kết nối hai chiều lâu dài. Đây thường là transport hiệu quả nhất trong ba lựa chọn.

### 4.2 XHR transport

`XhrTransport` dùng HTTP request để mô phỏng kết nối WebSocket. Từ góc nhìn client Java, một implementation XHR có thể hỗ trợ cả `xhr-streaming` và `xhr-polling`; sự khác biệt nằm ở URL transport và cách phiên HTTP được duy trì.

Các implementation phụ thuộc phiên bản Spring có thể gồm:

- `RestTemplateXhrTransport`: dùng Spring `RestTemplate` cho HTTP request.
- `RestClientXhrTransport`: dùng Spring `RestClient`, được dùng trong tài liệu Spring Framework mới hơn.
- `JettyXhrTransport`: dùng Jetty `HttpClient`.

Không sao chép tên class từ một phiên bản tài liệu sang dự án khác mà chưa kiểm tra dependency thực tế. Một số class được giữ lại để tương thích hoặc thay đổi theo phiên bản; hãy dùng Javadoc đúng phiên bản Spring đang chạy.

## 5. SockJsClient chọn transport như thế nào?

Khi bắt đầu một SockJS session, client trước hết gửi request tới đường dẫn `/info` của endpoint. Thông tin trả về cho biết các khả năng của server, ví dụ server có cho phép WebSocket hay không và các thông tin cần thiết để lựa chọn transport.

Sau đó client chọn transport dựa trên khả năng của server và danh sách transport được cấu hình. Với danh sách thường dùng, WebSocket được đặt trước và XHR được dùng làm phương án dự phòng.

Ví dụ danh sách:

~~~java
List<Transport> transports = new ArrayList<>(2);
transports.add(new WebSocketTransport(new StandardWebSocketClient()));
transports.add(new RestTemplateXhrTransport());

SockJsClient sockJsClient = new SockJsClient(transports);
~~~

Thứ tự trong danh sách thể hiện thứ tự ưu tiên mà client có thể thử. Nếu chỉ khai báo WebSocket transport, ứng dụng không có XHR fallback. Nếu chỉ khai báo XHR transport, ứng dụng không thử WebSocket.

### URL transport của SockJS

Các request SockJS có cấu trúc khái quát:

~~~text
https://host:port/app/ws/{server-id}/{session-id}/{transport}
~~~

Trong đó:

- `server-id` hỗ trợ định tuyến request trong môi trường cluster; ngoài mục đích định tuyến, nó không mang ý nghĩa nghiệp vụ.
- `session-id` liên kết các request HTTP thuộc cùng một SockJS session.
- `transport` xác định transport đang được dùng, ví dụ `websocket`, `xhr_streaming` hoặc `xhr`.

Đây là URL nội bộ của giao thức SockJS. Ứng dụng thông thường chỉ cần cung cấp base endpoint như `ws://host:port/app/ws`; SockJsClient tự tạo các URL liên quan.

## 6. Kết hợp SockJsClient với WebSocketStompClient

`SockJsClient` triển khai interface `WebSocketClient` của Spring. Vì vậy, có thể truyền nó trực tiếp vào constructor của `WebSocketStompClient`.

Ví dụ dưới đây dùng `RestTemplateXhrTransport`, phù hợp với các ví dụ Spring Framework 6.2:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.messaging.converter.StringMessageConverter;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;
import org.springframework.messaging.simp.stomp.WebSocketStompClient;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.sockjs.client.RestTemplateXhrTransport;
import org.springframework.web.socket.sockjs.client.SockJsClient;
import org.springframework.web.socket.sockjs.client.Transport;
import org.springframework.web.socket.sockjs.client.WebSocketTransport;

public class StompClientFactory {

    public WebSocketStompClient createClient() {
        List<Transport> transports = new ArrayList<>(2);

        transports.add(
                new WebSocketTransport(new StandardWebSocketClient()));

        transports.add(new RestTemplateXhrTransport());

        SockJsClient sockJsClient = new SockJsClient(transports);

        WebSocketStompClient stompClient =
                new WebSocketStompClient(sockJsClient);

        stompClient.setMessageConverter(new StringMessageConverter());

        return stompClient;
    }

    public void connect(WebSocketStompClient stompClient) {
        String url = "ws://localhost:8080/ws";

        stompClient.connect(url, new StompSessionHandlerAdapter() {
            @Override
            public void afterConnected(
                    StompSession session,
                    org.springframework.messaging.simp.stomp.StompHeaders headers) {

                // Session STOMP đã sẵn sàng.
                // Có thể subscribe hoặc gửi message tại đây.
            }
        });
    }
}
~~~

Với Spring Framework mới hơn có `RestClientXhrTransport`, thay import và constructor của `RestTemplateXhrTransport` bằng class đó:

~~~java
import org.springframework.web.socket.sockjs.client.RestClientXhrTransport;

// ...
transports.add(new RestClientXhrTransport());
~~~

Không khai báo đồng thời hai XHR transport chỉ để tăng số lượng fallback. Hãy chọn implementation phù hợp với HTTP client, dependency và phiên bản Spring của dự án.

### 6.1 Gửi và nhận STOMP message

Sau khi callback `afterConnected` được gọi, có thể đăng ký destination và gửi message:

~~~java
session.subscribe("/topic/updates", new StompFrameHandler() {

    @Override
    public Type getPayloadType(StompHeaders headers) {
        return String.class;
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        System.out.println("Received: " + payload);
    }
});

session.send("/app/updates", "refresh");
~~~

Ví dụ này giả định server có controller xử lý `/app/updates` và phát dữ liệu tới `/topic/updates`. Nếu dùng payload JSON dạng object, hãy cấu hình message converter phù hợp như `MappingJackson2MessageConverter` và khai báo đúng kiểu payload trong `getPayloadType`.

Có hai lớp chuyển đổi cần phân biệt:

- `SockJsMessageCodec` xử lý framing/message encoding của giao thức SockJS.
- `MessageConverter` của `WebSocketStompClient` xử lý payload STOMP của ứng dụng.

Theo mặc định, SockJS Java client dùng Jackson 2 cho định dạng message của SockJS. Nếu classpath không có Jackson 2 hoặc ứng dụng cần codec khác, cấu hình một `SockJsMessageCodec` phù hợp trên SockJsClient. Điều đó không thay thế message converter STOMP.

## 7. Khác biệt giữa XHR streaming và long polling

Cả hai đều dùng HTTP, nhưng cách giữ request khác nhau.

### XHR streaming

- Client mở một request HTTP dài để nhận dữ liệu từ server.
- Server ghi nhiều message vào cùng response theo framing của SockJS.
- Client gửi dữ liệu lên server qua các HTTP POST request riêng.
- Request nhận dữ liệu có thể được giữ mở trong thời gian dài.

Ưu điểm là không phải mở lại request nhận dữ liệu sau mỗi message. Nhược điểm là proxy hoặc gateway có thể giới hạn thời gian sống của response, buffer dữ liệu hoặc đóng request lâu dài.

### XHR long polling

- Client gửi request để chờ server có dữ liệu.
- Khi server gửi message, response được hoàn tất.
- Client mở một request nhận dữ liệu mới.
- Client-to-server vẫn dùng HTTP request riêng.

Long polling thường tương thích với nhiều hạ tầng HTTP hơn nhưng tạo thêm request và chi phí thiết lập request. Khi tần suất message cao, overhead có thể lớn hơn streaming hoặc WebSocket.

### So sánh tổng quát

| Thuộc tính | WebSocket | XHR streaming | XHR polling |
|---|---|---|---|
| Kết nối nhận dữ liệu | Socket lâu dài | HTTP response dài | Request kết thúc sau mỗi lần trả dữ liệu |
| Gửi dữ liệu client lên server | Trên socket | HTTP POST | HTTP POST |
| Số request | Ít | Một request nhận dài và các POST gửi | Nhiều request nhận và POST gửi |
| Độ trễ | Thường thấp | Phụ thuộc response streaming và proxy | Có thể tăng do chu kỳ polling |
| Overhead | Thường thấp nhất | Cao hơn WebSocket | Thường cao hơn khi message liên tục |
| Hạ tầng cần hỗ trợ | WebSocket Upgrade | HTTP streaming | HTTP request/response thông thường |

Không có một transport tối ưu cho mọi mạng. Cần đo trong môi trường thực tế, đặc biệt khi có reverse proxy, API gateway, firewall hoặc thiết bị mạng doanh nghiệp.

## 8. SockJS fallback không phải message retry hoặc durable delivery

Fallback chỉ thay đổi cách tạo và duy trì kết nối. Nó không cung cấp các bảo đảm nghiệp vụ như:

- Lưu message khi client offline.
- Phát lại message sau khi client reconnect.
- Xác nhận message đã được ứng dụng client xử lý.
- Chống xử lý trùng.
- Đồng bộ lịch sử message bị bỏ lỡ.
- Lưu subscription qua lần restart server.

Nếu một SockJS session bị đóng, client cần xử lý việc tạo session mới và đăng ký STOMP subscription lại. Ứng dụng nên có API đồng bộ trạng thái hoặc cơ chế event ID/version nếu việc bỏ lỡ thông báo ảnh hưởng đến dữ liệu hiển thị.

Ví dụ, dashboard nhận notification rằng đơn hàng thay đổi. Khi kết nối lại, client nên gọi API đọc trạng thái đơn hàng mới nhất. Không nên giả định notification đã gửi trong thời gian offline sẽ được SockJS phát lại.

Đối với nghiệp vụ quan trọng, lưu trạng thái ở database hoặc event store. Có thể dùng transactional outbox để phát sự kiện sau khi transaction nghiệp vụ commit. SockJS/WebSocket chỉ là kênh thông báo cho client.

## 9. Heartbeat của SockJS và heartbeat của STOMP

Một ứng dụng có thể đồng thời có heartbeat ở nhiều lớp:

1. **SockJS heartbeat:** frame của giao thức SockJS giúp giữ phiên HTTP fallback và phát hiện hoạt động của transport. Spring SockJS server mặc định gửi heartbeat khi không có message trong một khoảng thời gian (25 giây theo cấu hình mặc định được tài liệu mô tả).
2. **STOMP heartbeat:** được thương lượng qua header CONNECT và CONNECTED. Nó theo dõi hoạt động của phiên STOMP.
3. **TCP/WebSocket ping-pong:** nếu implementation và hạ tầng hỗ trợ, đây là cơ chế ở tầng kết nối.

Các cơ chế này không thay thế lẫn nhau. SockJS heartbeat không chứng minh STOMP handler đã xử lý message. STOMP heartbeat không bảo đảm message được lưu bền vững. TCP ping-pong không thay thế ACK hoặc xác nhận nghiệp vụ.

Khi dùng `WebSocketStompClient`, có thể cấu hình `TaskScheduler` để gửi STOMP heartbeat:

~~~java
stompClient.setTaskScheduler(taskScheduler);
~~~

Nếu mô phỏng hàng nghìn client trên cùng một máy để kiểm thử tải, cần lưu ý mỗi STOMP session có thể tạo các tác vụ heartbeat riêng. Scheduler và HTTP client phải được cấu hình đủ tài nguyên. Với bài kiểm thử chỉ tập trung vào thông lượng, có thể tắt heartbeat nếu điều đó phù hợp với mục tiêu test; không được áp dụng kết quả đó như cấu hình production khi production cần heartbeat.

## 10. CORS, authentication và proxy

HTTP fallback đi qua các request HTTP thông thường. Vì vậy, cần kiểm tra các yếu tố sau:

- **CORS:** XHR streaming và polling cần các CORS response header phù hợp nếu client ở origin khác.
- **Cookie:** Nếu xác thực dựa trên session cookie, hãy bảo đảm cookie được gửi trong các HTTP request của fallback và cấu hình SockJS server phù hợp.
- **Authentication header:** Nếu dùng bearer token hoặc header tùy chỉnh, kiểm tra header có được truyền qua các request SockJS liên quan hay không.
- **CSRF:** Các request HTTP gửi dữ liệu phải tuân theo chính sách bảo mật của ứng dụng và Spring Security.
- **Reverse proxy:** Cần cấu hình timeout và buffering phù hợp cho response streaming; timeout quá ngắn có thể làm request bị đóng liên tục.
- **Load balancer:** Các request thuộc cùng SockJS session cần được định tuyến tới server xử lý session đó. Có thể dùng sticky session hoặc định tuyến dựa trên server-id theo kiến trúc triển khai.

SockJS server của Spring có thể tự thêm CORS header cho XHR transport nếu response chưa có CORS header. Nếu ứng dụng đã có filter hoặc gateway xử lý CORS, hãy kiểm tra cấu hình để tránh header bị thêm trùng hoặc mâu thuẫn.

Trong Java SockJsClient, `setHttpHeaderNames` cho phép chọn những handshake header được sao chép sang các HTTP request khác của SockJS, chẳng hạn request /info hoặc XHR send/receive. Theo mặc định của API, các handshake header được sử dụng cho các request liên quan nếu không cấu hình danh sách riêng. Chỉ truyền những header thực sự cần thiết và phù hợp với chính sách bảo mật.

Không ghi access token, cookie hoặc nội dung nhạy cảm vào log debug/TRACE khi điều tra transport.

## 11. Tải, thread và connection pool

HTTP fallback thường cần nhiều tài nguyên hơn WebSocket:

- XHR streaming giữ request nhận dữ liệu trong thời gian dài.
- Long polling thường xuyên tạo request mới.
- Mỗi session có thể cần thêm request gửi dữ liệu và request nhận dữ liệu.
- HTTP client phải có đủ connection, thread và timeout phù hợp.

Tài liệu Spring lưu ý rằng khi dùng SockJsClient để mô phỏng nhiều concurrent user, cần cấu hình HTTP client bên dưới để cho phép đủ connection và thread. Nếu dùng `RestTemplateXhrTransport` hoặc `RestClientXhrTransport`, cần xem cấu hình request factory và connection pool tương ứng. Nếu dùng `JettyXhrTransport`, cần cấu hình Jetty HttpClient.

Khi kiểm thử, đo ít nhất:

- Số session kết nối thành công theo từng transport.
- Tỷ lệ fallback từ WebSocket sang XHR.
- Thời gian tạo session và thời gian reconnect.
- Độ trễ từ server publish đến client nhận.
- Số HTTP request và số connection đang hoạt động.
- CPU, heap, GC, thread pool và connection pool.
- Timeout, lỗi CORS, lỗi handshake và số session bị đóng.

Đừng chỉ đo tổng số WebSocket thành công. Mục tiêu của SockJS là hoạt động khi WebSocket không khả dụng, vì vậy cần chủ động kiểm thử cả các tình huống fallback.

## 12. Xử lý lỗi và reconnect

Một số nhóm lỗi thường gặp:

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Request /info trả 404 | Server chưa bật SockJS hoặc base URL sai | Kiểm tra `withSockJS()` và endpoint |
| WebSocket handshake thất bại | Proxy chặn Upgrade, sai scheme hoặc server không cho phép WebSocket | Kiểm tra request Upgrade, TLS, proxy và log server |
| XHR streaming bị đóng sớm | Proxy timeout, buffering hoặc giới hạn response | Kiểm tra timeout, buffering và log gateway |
| XHR polling liên tục lỗi | CORS, authentication, CSRF hoặc endpoint sai | Kiểm tra request OPTIONS/GET/POST và response header |
| Không có fallback | Danh sách transport không có XhrTransport hoặc cấu hình sai | Kiểm tra danh sách Transport theo thứ tự |
| STOMP CONNECT lỗi sau khi transport đã mở | Header STOMP, xác thực hoặc cấu hình broker sai | Đọc ERROR frame và log message broker |
| Kết nối lại nhưng không nhận message | Session mới chưa subscribe lại | Đăng ký lại subscription sau khi STOMP session mới kết nối |
| Nhiều request tới sai node | Load balancer không giữ routing cho SockJS session | Kiểm tra sticky session hoặc server-id routing |

SockJS hỗ trợ fallback trong quá trình lựa chọn transport để tạo session. Khi một session đã được thiết lập rồi bị ngắt, ứng dụng vẫn cần quy trình reconnect. Đừng giả định một session STOMP cũ hoặc subscription cũ tự tồn tại sau khi client mở một SockJS session mới.

Mẫu xử lý ở phía ứng dụng:

1. Nhận lỗi transport hoặc thông báo session bị đóng.
2. Chờ theo backoff có giới hạn và thêm jitter để nhiều client không reconnect đồng thời.
3. Tạo lại kết nối STOMP qua SockJsClient.
4. Đăng ký lại các destination cần thiết.
5. Đồng bộ dữ liệu hiện tại qua API hoặc event cursor.
6. Tiếp tục nhận notification mới.

Khi dùng `StompSessionHandler`, có thể xử lý `afterConnected`, `handleTransportError` và các callback phù hợp để quản lý vòng đời session.

## 13. Quan sát và debug

Trong quá trình phát triển, kiểm tra request thực tế của SockJS:

- Request đầu tiên tới `/info`.
- URL transport đã được chọn.
- Các request HTTP streaming hoặc polling.
- Header Origin, Cookie, Authorization và CORS.
- Response status và thời gian sống của request.
- Frame SockJS open, message, heartbeat và close.

Ở phía server, có thể bật TRACE logging cho package `org.springframework.web.socket` trong môi trường kiểm thử để xem chi tiết quá trình transport. Chỉ bật log chi tiết trong phạm vi cần thiết và tránh ghi thông tin xác thực.

Trong browser, SockJS JavaScript client có debug option riêng. Tùy chọn đó thuộc thư viện JavaScript và không phải cấu hình cho Java `SockJsClient`.

Để kiểm tra từng fallback riêng lẻ, có thể tạm thời giới hạn transport được cấu hình trong test. Ví dụ, chạy một lượt chỉ với WebSocket, một lượt chỉ với XHR streaming/polling, sau đó chạy lại với danh sách đầy đủ để kiểm tra quá trình lựa chọn.

## 14. Khi nào nên dùng SockJsClient?

SockJsClient phù hợp khi:

- Một Java service cần kết nối tới Spring SockJS endpoint từ xa.
- Hai server cần giao tiếp hai chiều qua mạng có proxy hạn chế WebSocket.
- Cần viết integration test cho STOMP endpoint có SockJS.
- Cần mô phỏng nhiều concurrent client để kiểm tra khả năng kết nối và fallback.
- Hệ thống cần giữ cùng API STOMP client trong khi transport có thể thay đổi theo khả năng mạng.

Không cần SockJS nếu mọi client và hạ tầng đều hỗ trợ WebSocket ổn định, không có yêu cầu tương thích HTTP fallback và không cần giao thức SockJS. Trong trường hợp đó, `StandardWebSocketClient` kết hợp với `WebSocketStompClient` thường đơn giản hơn.

Không chọn SockJS chỉ để giải quyết việc lưu message hoặc xử lý offline. Các yêu cầu đó thuộc persistence, message broker, queue, event store hoặc API đồng bộ trạng thái.

## 15. Bài tập tự kiểm tra

### Bài 1

Server đăng ký endpoint:

~~~java
registry.addEndpoint("/ws");
~~~

Client tạo `SockJsClient` và kết nối tới `ws://localhost:8080/ws`. Vì sao kết nối SockJS có thể thất bại?

**Đáp án:** Endpoint chưa bật SockJS. Cần đăng ký `registry.addEndpoint("/ws").withSockJS()` để server hỗ trợ giao thức SockJS.

### Bài 2

Danh sách transport chỉ có:

~~~java
List<Transport> transports = List.of(
        new WebSocketTransport(new StandardWebSocketClient())
);
~~~

Nếu proxy chặn WebSocket, Java SockJsClient có HTTP fallback không?

**Đáp án:** Không. Danh sách không có `XhrTransport`, vì vậy client không có transport HTTP để chuyển sang.

### Bài 3

`xhr-streaming` và `xhr-polling` khác nhau ở điểm nào?

**Đáp án:** Streaming giữ một HTTP response dài để nhận nhiều message. Polling kết thúc response sau khi trả dữ liệu rồi client mở request nhận dữ liệu mới. Cả hai đều dùng HTTP request riêng để gửi dữ liệu từ client lên server.

### Bài 4

Sau khi mạng bị ngắt và client tạo STOMP session mới, có cần subscribe lại không?

**Đáp án:** Có. Session mới không tự kế thừa subscription của session trước. Client cần đăng ký lại các destination cần thiết và đồng bộ dữ liệu có thể đã bỏ lỡ.

### Bài 5

SockJS fallback có bảo đảm message gửi trong thời gian client offline sẽ được phát lại không?

**Đáp án:** Không. Fallback chỉ thay đổi transport. Muốn lưu và phát lại message, ứng dụng cần broker hoặc kho lưu trữ có hỗ trợ persistence/durable subscription, hoặc API lịch sử riêng.

## 16. Checklist trước khi đưa vào production

- [ ] Server endpoint đã bật `withSockJS()`.
- [ ] Danh sách client có WebSocket transport và ít nhất một XHR fallback khi yêu cầu fallback.
- [ ] XHR implementation tương thích với phiên bản Spring và HTTP client của dự án.
- [ ] URL, TLS, CORS, cookie, authentication và CSRF đã được kiểm thử cho cả WebSocket lẫn HTTP.
- [ ] Reverse proxy có timeout và buffering phù hợp cho streaming.
- [ ] Load balancer định tuyến đúng các request cùng SockJS session.
- [ ] HTTP connection pool và thread pool chịu được số session dự kiến.
- [ ] Client có reconnect, resubscribe và đồng bộ trạng thái.
- [ ] Log không để lộ cookie, token hoặc payload nhạy cảm.
- [ ] Đã kiểm thử WebSocket thành công, XHR streaming, polling, proxy timeout và restart server.

## Tài liệu tham khảo

- [Spring Framework — SockJS Fallback](https://docs.spring.io/spring-framework/reference/web/websocket/fallback.html)
- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)
- [Spring Framework 6.2 — SockJS Fallback](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/fallback.html)
- [Spring Framework Javadoc — SockJsClient](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/sockjs/client/SockJsClient.html)
- [Spring Framework Javadoc — XhrTransport](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/sockjs/client/XhrTransport.html)
- [Spring Framework Javadoc — WebSocketTransport](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/sockjs/client/WebSocketTransport.html)
