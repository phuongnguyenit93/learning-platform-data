# Cân bằng tải WebSocket, proxy timeout và nhu cầu gắn phiên

## 1. Bài toán khi đưa WebSocket lên production

WebSocket tạo một kênh hai chiều tồn tại lâu giữa client và server. Kết nối bắt đầu bằng HTTP handshake; nếu server chấp nhận yêu cầu Upgrade, kết nối chuyển sang giao thức WebSocket và các frame tiếp theo đi trên cùng TCP connection.

Trong môi trường production, endpoint thường nằm sau reverse proxy hoặc load balancer. Các thành phần này có thể:

- Chọn application instance nhận handshake.
- Kết thúc TLS và chuyển tiếp kết nối tới Spring.
- Áp dụng giới hạn thời gian không có dữ liệu (idle timeout).
- Đóng kết nối khi backend bị unhealthy, deploy hoặc vượt giới hạn tài nguyên.
- Phân phối các request HTTP của SockJS fallback.
- Áp dụng cookie hoặc quy tắc định tuyến để giữ một client ở cùng instance.

Ba vấn đề cần giải quyết riêng:

1. **Load balancing:** phân phối kết nối mới giữa các instance để tận dụng tài nguyên.
2. **Proxy timeout:** giữ kết nối sống đủ lâu, đồng thời phát hiện kết nối thực sự đã chết.
3. **Session affinity (sticky session):** bảo đảm các request thuộc cùng một logical session được chuyển tới đúng instance khi ứng dụng cần state cục bộ.

Không nên coi ba vấn đề này là một cấu hình duy nhất. Một hệ thống có thể cân bằng WebSocket tốt nhưng vẫn mất kết nối sau 60 giây do proxy timeout; hoặc có sticky session nhưng vẫn không gửi được thông báo cho user đang kết nối ở instance khác.

## 2. Một WebSocket connection được gắn với backend như thế nào?

Load balancer chọn backend khi nhận HTTP Upgrade request. Sau khi handshake thành công, proxy chuyển kết nối thành một tunnel hai chiều. Các WebSocket frame tiếp theo đi trên tunnel TCP đó và tiếp tục tới cùng backend đã nhận handshake.

```text
Browser
   |
   | HTTP GET + Upgrade: websocket
   v
Reverse proxy / Load balancer
   |
   | chọn app-2
   | trả 101 Switching Protocols
   v
Spring app-2
   |
   | WebSocket frames trên cùng TCP connection
   |-------------------------------------------->
   |<--------------------------------------------
   |
   +-- session, principal, subscriptions của connection
```

Điều này dẫn đến một điểm quan trọng: **mỗi frame WebSocket không được load balancer chọn backend lại**. Một WebSocket đang mở đã gắn với backend thông qua TCP connection của nó. Không cần cookie-based stickiness chỉ để giữ các frame của một WebSocket native trên cùng instance.

Tuy nhiên, backend vẫn giữ state của session, principal, subscription và các channel nội bộ. Nếu kết nối bị đóng rồi client reconnect, đó là một connection mới. Load balancer có thể chọn instance khác. Session affinity có thể giúp reconnect quay lại instance cũ, nhưng không thể khôi phục một TCP connection đã mất hoặc state đã bị xóa khi instance chết.

Cần phân biệt:

- **Connection affinity:** các frame của một WebSocket native đang hoạt động đi trên cùng tunnel TCP.
- **HTTP session affinity:** các HTTP request tiếp theo có cùng cookie hoặc key định tuyến được gửi tới cùng application instance.
- **Application session continuity:** dữ liệu đăng nhập, subscription hoặc trạng thái nghiệp vụ có thể được khôi phục sau khi client reconnect, kể cả khi instance thay đổi.

Ba khái niệm này có liên quan nhưng không thay thế cho nhau.

## 3. Khi nào cần sticky sessions?

### WebSocket native

Với WebSocket native, một HTTP Upgrade request tạo một kết nối hai chiều lâu dài. Sau khi tunnel được thiết lập, proxy giữ kết nối với backend đã chọn. Sticky cookie không cần thiết cho các frame trên kết nối đó.

Session affinity vẫn có thể hữu ích cho các request HTTP khác của cùng người dùng, chẳng hạn REST API dùng cùng `JSESSIONID`, hoặc khi ứng dụng giữ trạng thái xác thực và dữ liệu phiên chỉ trong bộ nhớ của một node.

### SockJS HTTP streaming và long polling

SockJS có thể dùng WebSocket, HTTP streaming hoặc HTTP long polling tùy khả năng của browser và mạng. Với các transport HTTP fallback, một logical SockJS session có thể được tạo bởi nhiều HTTP request:

- Một request dài để server gửi message xuống client.
- Các HTTP POST riêng để client gửi message lên server.
- Long polling có thể kết thúc request hiện tại và tạo request tiếp theo.

Các request đó phải được xử lý như cùng một SockJS session. Nếu load balancer phân phối chúng sang các instance khác nhau trong khi session state chỉ nằm trong bộ nhớ của một node, instance nhận request sau có thể không tìm thấy session hoặc không có message cache cần thiết.

Vì vậy, với SockJS HTTP fallback, cần một chiến lược định tuyến nhất quán theo cookie, địa chỉ client hoặc `server-id` trong URL. Spring SockJS dùng URL transport có dạng:

```text
/myEndpoint/{server-id}/{session-id}/{transport}
```

Trong đó `session-id` liên kết các request thuộc cùng logical session; `server-id` hữu ích cho việc định tuyến request trong cluster. Load balancer có thể dùng một key ổn định để gửi các request này tới cùng node.

Spring SockJS có thuộc tính `sessionCookieNeeded`, mặc định bật vì nhiều ứng dụng Java dựa vào cookie như `JSESSIONID`. Thuộc tính này giúp SockJS client chọn transport phù hợp khi cookie quan trọng. **Nó không tự cấu hình sticky session cho load balancer.** Hạ tầng vẫn phải thực hiện việc định tuyến nhất quán.

### Reconnect sau khi connection bị ngắt

Khi WebSocket bị mất, client tạo một connection mới. Nếu backend được chọn khác node cũ:

- Principal có thể được xác định lại từ cookie hoặc token.
- HTTP session có thể được tải từ session store dùng chung.
- STOMP subscription phải được đăng ký lại.
- Các dữ liệu đang giữ trong bộ nhớ node cũ có thể không còn.
- Message gửi trong khoảng mất kết nối có thể bị bỏ lỡ nếu ứng dụng không có cơ chế lưu và phát lại.

Sticky session có thể làm reconnect quay lại node cũ khi node đó còn khỏe, nhưng không bảo đảm continuity khi node chết hoặc bị loại khỏi pool. Nếu cần khả năng phục hồi, hãy lưu trạng thái quan trọng ngoài bộ nhớ cục bộ và thiết kế giao thức reconnect/resubscribe rõ ràng.

## 4. Chọn chiến lược cân bằng tải cho kết nối dài

Một WebSocket connection có thể tồn tại nhiều phút hoặc nhiều giờ. Vì vậy, số connection đang mở ảnh hưởng lớn tới việc phân phối tải.

Các chiến lược thường gặp:

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Round robin | Phân phối connection mới lần lượt qua các backend | Các node có năng lực tương đương và tải tương đối đồng đều |
| Least connections | Ưu tiên backend có ít connection đang mở hơn | Connection dài và số connection là chỉ số tải có ích |
| Cookie affinity | Gửi request của cùng cookie tới cùng node | SockJS fallback hoặc HTTP session state cục bộ |
| IP hash | Hash địa chỉ IP nguồn để chọn backend | Môi trường không có cookie affinity, sau khi đánh giá NAT/proxy |
| Consistent hash theo path/key | Dùng `server-id` hoặc key session để chọn node ổn định | SockJS HTTP transports và hệ thống có key định tuyến rõ ràng |

`least_conn` thường là lựa chọn khởi đầu hợp lý cho WebSocket native, nhưng số connection không phản ánh toàn bộ chi phí. Một node có ít connection nhưng mỗi connection gửi hàng nghìn message/giây vẫn có thể bận hơn node có nhiều connection nhàn rỗi.

Cần đo thêm:

- Số WebSocket đang hoạt động theo node.
- Số STOMP session và subscription.
- Message inbound/outbound mỗi giây.
- CPU, heap, direct memory và số file descriptor.
- Queue của inbound/outbound channel.
- Send buffer và số slow client.
- Số connection tới external broker.

`ip_hash` có thể gây lệch tải khi nhiều người dùng đi ra Internet qua cùng NAT hoặc proxy. Nếu có lựa chọn, cookie-based affinity hoặc key định tuyến rõ ràng thường dễ kiểm soát hơn. Nếu dùng IP hash, cần hiểu proxy nào đang được nhìn thấy là địa chỉ nguồn và chỉ tin các header địa chỉ client từ proxy đáng tin cậy.

Scale-out cũng chỉ ảnh hưởng các connection mới. Những WebSocket đang mở vẫn nằm trên node cũ cho tới khi disconnect hoặc được drain.

## 5. Cấu hình Nginx để proxy WebSocket

Với reverse proxy Nginx, `Upgrade` và `Connection` là hop-by-hop headers nên không tự động được chuyển tiếp như header thông thường. Proxy phải đặt lại chúng để backend Spring biết client muốn chuyển giao thức sang WebSocket.

Ví dụ cấu hình hai Spring instance:

```nginx
http {
    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }

    upstream spring_ws_nodes {
        least_conn;
        server app1.internal:8080;
        server app2.internal:8080;
    }

    server {
        listen 443 ssl;
        server_name ws.example.com;

        location /ws {
            proxy_pass http://spring_ws_nodes;

            # Explicit for compatibility with older Nginx versions.
            proxy_http_version 1.1;

            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

            proxy_read_timeout 75s;
            proxy_send_timeout 75s;
        }
    }
}
```

Các điểm cần hiểu:

- `upstream` khai báo các Spring instance mà Nginx có thể chọn.
- `least_conn` phân phối connection mới dựa trên số connection đang mở.
- `proxy_http_version 1.1` hỗ trợ WebSocket Upgrade trên các phiên bản Nginx cũ. Từ Nginx 1.29.7, HTTP/1.1 đã là mặc định cho proxy, nhưng khai báo tường minh giúp cấu hình tương thích rộng hơn.
- `Upgrade` và `Connection` cho phép Nginx thiết lập WebSocket tunnel.
- `Host`, `X-Forwarded-Proto` và `X-Forwarded-For` giúp ứng dụng nhận đúng host, scheme và địa chỉ client qua proxy. Chỉ tin forwarded headers từ proxy do hệ thống kiểm soát.
- `proxy_read_timeout` và `proxy_send_timeout` cần được chọn theo heartbeat và chính sách idle của toàn tuyến.

Nếu endpoint có tên khác, hãy sửa `location` tương ứng. Nếu dùng SockJS, đường dẫn `/ws/info` và các URL transport con cũng phải được chuyển tới Spring. Không chỉ route mỗi request handshake mà bỏ sót các request HTTP fallback.

### SockJS HTTP streaming

Với SockJS XHR streaming, response có thể được giữ mở để truyền message dần dần. Proxy buffering có thể khiến message bị giữ lại thay vì chuyển xuống browser ngay khi Spring gửi.

Có thể tắt buffering cho endpoint SockJS:

```nginx
location /sockjs/ {
    proxy_pass http://spring_ws_nodes;
    proxy_http_version 1.1;

    proxy_buffering off;
    proxy_read_timeout 75s;
    proxy_send_timeout 75s;
}
```

Cấu hình thực tế cần chuyển tiếp đầy đủ các header và thiết lập CORS phù hợp với domain của client. `proxy_buffering off` hỗ trợ luồng HTTP streaming; nó không thay thế sticky routing cho SockJS session.

## 6. Hiểu đúng các loại timeout

Một kết nối WebSocket có thể bị đóng bởi bất kỳ thành phần nào trên đường truyền. Vì thế, chỉ tăng timeout ở Spring không giải quyết được nếu load balancer hoặc reverse proxy có idle timeout thấp hơn.

Các lớp timeout thường gặp:

| Thành phần | Timeout kiểm soát điều gì? | Triệu chứng khi quá thấp |
|---|---|---|
| Browser/client | Thời gian chờ phản hồi, timeout nội bộ hoặc chính sách mạng | Client tự đóng socket hoặc báo lỗi |
| CDN/load balancer | Thời gian idle hoặc tuổi tối đa của connection | Kết nối bị ngắt theo chu kỳ hoặc sau một khoảng im lặng |
| Reverse proxy | Thời gian không đọc/ghi dữ liệu giữa proxy và backend | WebSocket đóng khi không có traffic |
| Servlet container | Thời gian chờ hoặc tài nguyên transport | Session bị đóng ở tầng server |
| Spring WebSocket transport | Giới hạn gửi, buffer và message size | Session bị đóng do slow client hoặc message quá lớn |
| SockJS | Disconnect delay, heartbeat và HTTP cache | Session fallback bị xem là mất kết nối |
| STOMP broker | Heartbeat và thời gian phát hiện client/broker không hoạt động | Broker đóng TCP/STOMP connection |

### Nginx proxy_read_timeout

Nginx mặc định đóng kết nối nếu upstream không gửi dữ liệu trong 60 giây. `proxy_read_timeout` đo khoảng thời gian giữa hai lần đọc liên tiếp từ upstream; nó không phải thời gian tối đa cho toàn bộ response.

Ví dụ, nếu Nginx đang chờ dữ liệu từ Spring và Spring không gửi frame, heartbeat hoặc byte nào trong khoảng 60 giây, Nginx có thể đóng tunnel. Có thể tăng `proxy_read_timeout`, nhưng cách bền vững hơn là cấu hình heartbeat phù hợp và đặt timeout cao hơn khoảng heartbeat với một khoảng dự phòng.

`proxy_send_timeout` áp dụng cho khoảng thời gian giữa hai lần ghi liên tiếp tới upstream. Trong một kết nối hai chiều, hãy kiểm tra cả hai hướng dữ liệu thay vì chỉ tăng một directive.

### Idle timeout của load balancer

Cloud load balancer, ingress controller, firewall và NAT gateway có thể có idle timeout riêng. Mỗi nhà cung cấp có mặc định và cách đo khác nhau. Cần kiểm tra cấu hình thực tế của từng lớp và chọn heartbeat/timeout theo lớp có giới hạn thấp nhất.

Một kết nối có thể sống qua Nginx nhưng vẫn bị cloud load balancer đóng trước đó. Vì vậy, hãy lập bảng timeout toàn tuyến thay vì chỉ xem cấu hình của Spring.

### Timeout không giống giới hạn gửi của Spring

`setSendTimeLimit` và `setSendBufferSizeLimit` của Spring WebSocket transport kiểm soát việc gửi message và buffer cho client chậm. `setMessageSizeLimit` giới hạn kích thước message inbound. Chúng không phải idle timeout của proxy.

Ví dụ cấu hình:

```java
@Override
public void configureWebSocketTransport(
        WebSocketTransportRegistration registration) {

    registration
            .setSendTimeLimit(15_000)
            .setSendBufferSizeLimit(512 * 1024)
            .setMessageSizeLimit(128 * 1024);
}
```

Các giá trị trên chỉ là điểm bắt đầu minh họa. Hãy điều chỉnh theo kích thước message, tốc độ client đọc dữ liệu và bộ nhớ có thể cấp cho mỗi session. Tăng buffer quá lớn có thể khiến nhiều slow client chiếm nhiều bộ nhớ hơn.

## 7. Dùng heartbeat để giữ kết nối và phát hiện disconnect

Heartbeat là dữ liệu định kỳ cho biết connection vẫn còn hoạt động. Trong ứng dụng STOMP, heartbeat có thể được thương lượng giữa client và server khi STOMP CONNECT. Khi không có message nghiệp vụ, heartbeat vẫn tạo traffic để proxy không coi connection là idle và để hai phía phát hiện peer không còn phản hồi.

Cần phân biệt các loại heartbeat:

- **STOMP heartbeat:** frame newline được gửi giữa STOMP client và server/broker theo khoảng thời gian đã thương lượng.
- **SockJS heartbeat:** frame heartbeat riêng của SockJS, mặc định Spring gửi sau 25 giây nếu không có message khác trên connection.
- **WebSocket Ping/Pong:** control frame của giao thức WebSocket, có thể được server hoặc client dùng để kiểm tra transport.
- **TCP keepalive:** cơ chế ở tầng TCP/OS; không phải mọi proxy trung gian đều coi nó là traffic ứng dụng để reset idle timeout.

Khi STOMP heartbeat được thương lượng trên STOMP over SockJS, SockJS heartbeat riêng sẽ bị tắt. Vì vậy, phải xác định chính xác heartbeat nào đang hoạt động trên kết nối thực tế.

### Cấu hình heartbeat cho simple broker

Spring simple broker hỗ trợ STOMP heartbeat khi có `TaskScheduler`. Ví dụ:

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    private TaskScheduler messageBrokerTaskScheduler;

    @Autowired
    public void setMessageBrokerTaskScheduler(
            @Lazy TaskScheduler taskScheduler) {
        this.messageBrokerTaskScheduler = taskScheduler;
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue")
                .setHeartbeatValue(new long[] {20_000, 20_000})
                .setTaskScheduler(this.messageBrokerTaskScheduler);

        registry.setApplicationDestinationPrefixes("/app");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws").withSockJS();
    }
}
```

Đây là cấu hình minh họa cho một application instance dùng simple broker. Khi triển khai nhiều node, thay simple broker bằng external broker relay như phần 9.

Trong heartbeat value:

- Giá trị thứ nhất là khoảng thời gian server gửi heartbeat.
- Giá trị thứ hai là khoảng thời gian server mong client gửi heartbeat.
- Đơn vị là millisecond.
- Giá trị `0` có nghĩa là không dùng heartbeat ở hướng tương ứng.

Client STOMP cũng phải hỗ trợ và thương lượng heartbeat. Với Spring `WebSocketStompClient`, cấu hình `TaskScheduler` để client gửi heartbeat khi không có message khác. Browser STOMP client cần cấu hình heartbeat tương ứng theo thư viện client đang dùng.

### Chọn khoảng heartbeat và proxy timeout

Giả sử server gửi heartbeat mỗi 20 giây và proxy đóng connection nếu upstream không có dữ liệu trong 75 giây. Một khoảng 20 giây cho phép có một vài lần heartbeat bị trễ trước khi proxy timeout, đồng thời không tạo quá nhiều traffic.

Ví dụ tham khảo:

| Tham số | Giá trị minh họa |
|---|---:|
| Server STOMP heartbeat | 20 giây |
| Client STOMP heartbeat | 20 giây |
| Nginx `proxy_read_timeout` | 75 giây |
| Nginx `proxy_send_timeout` | 75 giây |

Không sao chép nguyên các giá trị này cho mọi hệ thống. Hãy tính theo latency, jitter, thời gian pause của JVM, lịch scheduler, timeout của cloud load balancer và mục tiêu phát hiện dead connection.

Một chi tiết quan trọng: `proxy_read_timeout` theo dõi dữ liệu từ upstream về proxy. Heartbeat chỉ đi từ browser lên server không làm mới bộ đếm đọc upstream này. Cần có traffic từ server về client, chẳng hạn STOMP heartbeat server gửi hoặc WebSocket Ping từ server, nếu muốn giữ chiều đọc đó hoạt động.

Heartbeat quá ngắn làm tăng traffic và công việc scheduler. Heartbeat quá dài có thể khiến phát hiện disconnect chậm hoặc không đủ để giữ connection qua proxy. Hãy chọn khoảng thời gian có dự phòng thay vì đặt bằng đúng idle timeout.

## 8. Heartbeat giữa Spring và external STOMP broker là một đường khác

Khi dùng STOMP broker relay, có ít nhất hai tuyến kết nối cần theo dõi:

```text
Browser
   |
   | WebSocket + STOMP
   | heartbeat của client/server
   v
Spring application
   |
   | TCP/STOMP tới broker
   | heartbeat của broker relay
   v
External STOMP broker
```

Heartbeat giữa browser và Spring không thay thế heartbeat giữa Spring và broker. Mỗi tuyến có timeout, firewall và network path riêng.

STOMP broker relay tạo:

- Một system TCP connection dùng cho message phát sinh từ server-side application.
- Một TCP connection riêng cho mỗi WebSocket client được relay tới broker.

Relay có heartbeat cho system connection; mặc định các khoảng gửi và nhận là 10 giây. Khi mất kết nối broker, relay thử kết nối lại định kỳ. Các client connection được tạo thay mặt WebSocket client là các kết nối riêng; cần kiểm tra giới hạn connection và heartbeat theo cấu hình broker.

Nếu có 20.000 WebSocket client và dùng broker relay, broker có thể phải giữ xấp xỉ 20.000 client TCP connection cộng với system connection của từng Spring application instance. Hãy kiểm tra giới hạn connection, file descriptor, memory và throughput của broker trước khi scale số WebSocket lên cao.

`BrokerAvailabilityEvent` cho biết system connection của relay đang khả dụng hay mất kết nối. Service có thể lắng nghe event này để tránh gửi message khi broker không sẵn sàng; khi gửi vẫn cần xử lý `MessageDeliveryException`.

## 9. Scale nhiều Spring instance và user destination

Sticky session chỉ định tuyến request tới một node. Nó không tự đồng bộ subscription hoặc user registry giữa các node.

Spring simple broker giữ subscription trong bộ nhớ của từng application instance và không phù hợp cho clustering. Khi chạy nhiều node, dùng external STOMP broker thông qua broker relay để các instance cùng gửi và nhận message qua một broker dùng chung.

Cấu hình mẫu:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("stomp-broker.internal")
            .setRelayPort(61613)
            .setUserRegistryBroadcast("/topic/simp-user-registry")
            .setUserDestinationBroadcast(
                    "/topic/unresolved-user-destination");
}
```

Hai thiết lập broadcast có vai trò khác nhau:

- `setUserRegistryBroadcast` phát user registry cục bộ và nhận registry từ node khác. Nhờ đó, mỗi node có thể biết user đang kết nối ở instance khác.
- `setUserDestinationBroadcast` phát các user destination chưa được node hiện tại phân giải để node khác có cơ hội xử lý.

Ví dụ Alice kết nối vào node A nhưng một service trên node B gọi `convertAndSendToUser("alice", ...)`. Nếu node B không biết Alice đang kết nối ở A, destination có thể chưa được phân giải. User registry broadcast và unresolved destination broadcast giúp node B phối hợp với node A qua broker dùng chung.

Cần bảo vệ các destination nội bộ như `/topic/simp-user-registry` và `/topic/unresolved-user-destination` khỏi client không đáng tin cậy. Không cho phép client tùy ý publish message vào các kênh điều phối này.

External broker cũng cần chính sách xóa queue/destination không hoạt động. Một số broker hỗ trợ auto-delete queue hoặc purge inactive destination; hãy cấu hình theo tài liệu broker đang sử dụng.

**Sticky session không thay thế external broker.** Nếu hai node mỗi node giữ simple broker riêng, client ở node A vẫn không tự nhận broadcast do service ở node B phát. Ngược lại, external broker không tự chuyển một WebSocket đang mở sang node khác. Broker chia sẻ message; mỗi node vẫn quản lý các WebSocket session kết nối trực tiếp với nó.

## 10. Session affinity, Spring Session và trạng thái đăng nhập

Nếu ứng dụng dùng HTTP session hoặc `JSESSIONID` để xác thực WebSocket handshake, cần đảm bảo quá trình xác thực hoạt động khi request tới bất kỳ instance nào.

Có hai cách phổ biến:

1. **Sticky session:** giữ các request HTTP tiếp theo của client ở cùng node. Cách này đơn giản nhưng node đó vẫn là điểm phụ thuộc trong vòng đời session.
2. **Shared session store:** dùng Spring Session với Redis hoặc kho lưu trữ dùng chung để các node đọc được HTTP session. Cách này giúp request sau khi reconnect có thể xác thực trên node khác, tùy cấu hình ứng dụng.

Spring Session dùng chung HTTP session không di chuyển một WebSocket TCP connection đang mở và không tự khôi phục STOMP subscriptions. Client vẫn phải reconnect và subscribe lại sau khi transport bị mất.

Với ứng dụng stateless dùng access token, mỗi handshake hoặc STOMP CONNECT có thể được xác thực lại theo token. Khi reconnect, client gửi token mới hoặc token còn hiệu lực và được node mới xác thực. Cần đảm bảo quy trình xác thực, CORS và cookie/token hoạt động nhất quán trên toàn cluster.

`sessionCookieNeeded` của SockJS chỉ ảnh hưởng lựa chọn transport khi cookie là cần thiết. Nó không phải cơ chế lưu session dùng chung và cũng không phải thiết lập affinity của load balancer.

## 11. Graceful shutdown và reconnect khi deploy

Một node có thể bị loại khỏi pool vì deploy, scale down hoặc health check thất bại. WebSocket đang mở trên node đó sẽ không tự chuyển sang node khác. Khi node đóng connection, client cần reconnect.

Một quy trình deploy có kiểm soát:

1. Đánh dấu node không còn nhận connection mới bằng readiness/target health.
2. Ngừng nhận handshake mới nhưng cho connection đang hoạt động một khoảng thời gian để hoàn thành.
3. Nếu ứng dụng hỗ trợ, gửi thông báo bảo trì để client chuẩn bị reconnect.
4. Đóng các session còn lại trước khi tiến trình bị terminate.
5. Client reconnect với exponential backoff và jitter để tránh hàng nghìn client cùng kết nối lại một lúc.
6. Client xác thực lại, tạo STOMP session mới và đăng ký lại các subscription.
7. Nếu nghiệp vụ cần message không bị mất, dùng sequence number, cursor hoặc inbox/outbox để client lấy lại dữ liệu bị bỏ lỡ.

Sticky session không thể giữ client trên một node đã chết. Đừng xem reconnect tới cùng server là bảo đảm delivery. WebSocket là transport hai chiều; tính bền vững và phát lại message phải được xây dựng ở tầng ứng dụng hoặc broker.

Với Kubernetes, cần đặt `terminationGracePeriodSeconds` đủ cho thời gian drain dự kiến và phối hợp readiness probe, preStop hook, ingress/load balancer draining. Thời gian cụ thể phụ thuộc thời gian cho phép kết nối tồn tại và chính sách deploy.

## 12. Quan sát và chẩn đoán sự cố

Spring tạo bean `WebSocketMessageBrokerStats` khi bật STOMP message broker. Bean này tổng hợp nhiều thống kê về WebSocket session, STOMP frame, broker relay và channel executor; mặc định log định kỳ ở mức INFO. Có thể xuất thông tin qua JMX hoặc tích hợp với hệ thống monitoring của ứng dụng.

Các chỉ số nên theo dõi:

| Chỉ số | Dấu hiệu cần chú ý |
|---|---|
| Current WebSocket sessions theo node | Một node tăng nhanh hoặc phân phối quá lệch |
| SockJS HTTP streaming/polling sessions | Fallback tăng bất thường, có thể do proxy chặn Upgrade |
| Connect failures và abnormal closes | Tăng đột biến sau deploy hoặc thay đổi proxy |
| Send limit exceeded | Client đọc chậm, send buffer hoặc timeout quá thấp |
| Transport errors | Lỗi đọc/ghi, proxy reset, backend đóng socket |
| STOMP CONNECT/CONNECTED/DISCONNECT | Tỷ lệ disconnect bất thường hoặc thiếu DISCONNECT |
| Broker relay TCP connections | Số connection không khớp số client session và system connections dự kiến |
| Inbound/outbound channel queue | Application xử lý chậm hoặc client không nhận message kịp |
| Broker heartbeat failures | Spring và broker không trao đổi heartbeat đúng hạn |

Khi thấy kết nối đóng sau một khoảng cố định gần 60 giây, kiểm tra Nginx `proxy_read_timeout`, cloud load balancer idle timeout và server heartbeat trước khi thay đổi code.

Khi SockJS lỗi ngẫu nhiên với `session not found`, kiểm tra các request `/info`, streaming và polling có đi tới cùng backend hay không. Kiểm tra cookie affinity hoặc key `server-id` trong URL.

Khi user message chỉ tới client trên cùng node, kiểm tra đang dùng simple broker hay external broker relay. Với multi-node, xác minh shared broker và hai kênh user registry/unresolved destination broadcast.

Khi broker relay báo thiếu connection hoặc heartbeat timeout, so sánh số WebSocket session với số TCP connection tới broker và kiểm tra giới hạn của broker.

## 13. Kiểm thử cấu hình trước khi triển khai

Một bộ kiểm thử deployment nên bao gồm:

1. **Handshake qua proxy:** xác nhận HTTP Upgrade trả về `101 Switching Protocols`, backend nhận đúng path và header cần thiết.
2. **Idle connection:** giữ client không gửi nghiệp vụ trong thời gian dài hơn idle timeout ngắn nhất của proxy; xác minh heartbeat giữ kết nối sống.
3. **Heartbeat bị chặn:** tạm dừng heartbeat hoặc mô phỏng network drop để xác minh disconnect được phát hiện trong khoảng thời gian dự kiến.
4. **SockJS fallback:** ép client dùng XHR streaming và polling; xác minh request của cùng session được chuyển tới cùng node.
5. **Multi-node broadcast:** mở client trên hai node khác nhau, gửi message qua external broker và xác minh cả hai nhận được.
6. **User destination cross-node:** kết nối user vào node A, gửi thông báo từ node B và xác minh user nhận được.
7. **Node drain:** loại một node khỏi pool, đóng connection theo quy trình và xác minh client reconnect tới node còn khỏe.
8. **Slow client:** giảm tốc độ đọc message để kiểm tra send buffer, send timeout và khả năng cô lập client chậm.
9. **Broker restart:** dừng rồi bật lại broker, xác minh system relay connection phục hồi và client có cơ chế reconnect phù hợp.

Không chỉ kiểm tra bằng một client trên localhost. Proxy, load balancer, SockJS fallback và broker relay cần được kiểm thử trong topology gần với production.

## 14. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| WebSocket handshake trả 400/426 hoặc không có 101 | Proxy không chuyển tiếp `Upgrade` và `Connection` header | Cấu hình header Upgrade, Connection và HTTP/1.1 phù hợp |
| Kết nối đóng sau khoảng 60 giây không hoạt động | Nginx hoặc LB idle timeout thấp hơn heartbeat | Kiểm tra timeout từng lớp và tạo server-to-client heartbeat |
| Browser gửi heartbeat nhưng proxy vẫn đóng | `proxy_read_timeout` đang chờ dữ liệu từ upstream | Bảo đảm server gửi heartbeat hoặc Ping frame |
| SockJS lúc chạy lúc lỗi session | HTTP streaming/polling request tới nhiều instance | Bật affinity hoặc định tuyến nhất quán theo session/server-id |
| Client reconnect nhưng không còn subscription | STOMP session mới chưa subscribe lại | Lưu danh sách subscription ở client và đăng ký lại sau CONNECTED |
| User message không tới node khác | Chỉ dùng simple broker hoặc user registry cục bộ | Dùng external broker relay và cấu hình broadcast registry/destination |
| Một node nhận quá nhiều connection | Round robin không phản ánh connection dài hoặc NAT làm lệch IP hash | Dùng least connections/cookie affinity phù hợp và theo dõi tải thực |
| Deploy làm rớt nhiều client cùng lúc | Node bị terminate trước khi drain | Readiness, connection draining và reconnect backoff |
| Broker đóng connection vì heartbeat | Heartbeat giữa Spring và broker không khớp hoặc scheduler bị trễ | Kiểm tra relay/broker heartbeat và tải scheduler |
| Server tốn nhiều bộ nhớ khi có client chậm | Send buffer quá lớn hoặc message gửi nhanh hơn client đọc | Giới hạn buffer/time, giảm tốc độ publish hoặc xử lý slow client |

## 15. Checklist triển khai

- [ ] Reverse proxy chuyển tiếp đúng `Upgrade` và `Connection` header.
- [ ] WebSocket handshake trả về `101 Switching Protocols`.
- [ ] `proxy_read_timeout` và timeout của LB phù hợp với heartbeat server-to-client.
- [ ] Heartbeat được cấu hình ở đúng tầng: browser–Spring, Spring–broker và SockJS khi cần.
- [ ] Client và server thương lượng STOMP heartbeat nếu dùng STOMP.
- [ ] SockJS HTTP streaming/polling được route nhất quán tới cùng logical session.
- [ ] Đã xác định sticky session có cần cho HTTP session/SockJS fallback hay không.
- [ ] Không dựa vào sticky session để khôi phục socket hoặc đồng bộ broker giữa các node.
- [ ] Multi-node dùng external broker relay và user registry/unresolved destination broadcast khi cần.
- [ ] Broker đủ capacity cho connection của tất cả WebSocket client và system connection.
- [ ] HTTP session/authentication state có thể dùng ở node khác sau reconnect nếu cần.
- [ ] Client reconnect có backoff/jitter và subscribe lại.
- [ ] Node có readiness và graceful connection draining khi deploy.
- [ ] Có metrics cho active sessions, abnormal closes, transport errors, send limit và broker connections.
- [ ] Đã kiểm thử idle timeout, SockJS fallback, multi-node broadcast và node failure.

## Tài liệu tham khảo

- [Spring Framework Reference — WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket.html)
- [Spring Framework Reference — SockJS Fallback](https://docs.spring.io/spring-framework/reference/web/websocket/fallback.html)
- [Spring Framework Reference — STOMP External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework Reference — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Spring Framework Reference — STOMP User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework Reference — STOMP Monitoring](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html)
- [Spring Cloud Gateway — WebSocket Routing Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html)
- [Nginx — WebSocket Proxying](https://nginx.org/en/docs/http/websocket.html)
- [Nginx — Proxy Module and Timeout Directives](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [Spring Session — Common Configuration](https://docs.spring.io/spring-session/reference/configuration/common.html)
