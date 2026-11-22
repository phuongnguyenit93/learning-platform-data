# CONNECT, CONNECTED và thương lượng phiên

> Mục tiêu: hiểu hai frame mở đầu một STOMP session; biết client và server thương lượng phiên bản giao thức, virtual host và heartbeat như thế nào; phân biệt STOMP session với HTTP/WebSocket connection; cấu hình và theo dõi kết nối STOMP trong Spring.

## 1. STOMP session bắt đầu sau WebSocket handshake

STOMP (Simple Text Oriented Messaging Protocol) là giao thức messaging dạng frame. Nó có thể chạy trên TCP hoặc trên WebSocket. Khi chạy trên WebSocket, quá trình tạo kết nối gồm hai lớp:

1. **HTTP/WebSocket handshake:** client gửi HTTP Upgrade request; server trả `101 Switching Protocols` nếu chấp nhận. Hai bên có thể chọn subprotocol STOMP qua header HTTP `Sec-WebSocket-Protocol`.
2. **STOMP connection negotiation:** sau khi WebSocket đã mở, client gửi frame `CONNECT` (hoặc `STOMP`); server trả `CONNECTED` nếu chấp nhận phiên STOMP.

Hai bước này giải quyết hai vấn đề khác nhau. HTTP handshake thiết lập transport WebSocket và chọn subprotocol; `CONNECT`/`CONNECTED` thương lượng phiên STOMP chạy trên transport đó. WebSocket mở thành công chưa có nghĩa STOMP session đã sẵn sàng.

Luồng tổng quát:

```text
Client                         Spring / STOMP server
  |                                      |
  |--- HTTP Upgrade -------------------> |
  |<-- 101 Switching Protocols --------- |
  |                                      |
  |--- CONNECT ------------------------> |
  |    accept-version                   |
  |    host                             |
  |    heart-beat                       |
  |                                      |
  |<-- CONNECTED ----------------------- |
  |    version                          |
  |    heart-beat                       |
  |    session (optional)               |
  |                                      |
  |<====== SEND / SUBSCRIBE / MESSAGE ==>|
  |                                      |
```

Spring phát `SessionConnectEvent` khi nhận frame `CONNECT`. Sau đó, khi broker trả frame `CONNECTED`, Spring phát `SessionConnectedEvent`; từ thời điểm này STOMP session mới được xem là thiết lập đầy đủ. Hai event hữu ích khi ghi nhận thời điểm client bắt đầu kết nối và thời điểm broker xác nhận kết nối.

## 2. Cấu trúc frame STOMP

Một STOMP frame gồm command, các header, một dòng trống phân cách header/body và ký tự NULL kết thúc frame:

```text
COMMAND
header-name:header-value
another-header:value

body (nếu command cho phép)
^@
```

`^@` trong ví dụ là cách tài liệu STOMP biểu diễn octet NULL (`0x00`); khi truyền thực tế, client gửi đúng byte NULL, không gửi hai ký tự `^` và `@`. Dòng kết thúc header dùng LF hoặc CRLF. Tên command và header phân biệt chữ hoa/chữ thường.

`CONNECT` và `CONNECTED` chỉ mang header, không có body. Body chỉ được dùng cho một số frame như `SEND`, `MESSAGE` và `ERROR`. STOMP mặc định dùng UTF-8; payload có thể là text hoặc binary tùy `content-type` và `content-length`.

## 3. Client gửi CONNECT

`CONNECT` là frame đầu tiên của STOMP client sau khi transport đã sẵn sàng. Trong STOMP 1.2, hai header bắt buộc là:

- `accept-version`: danh sách phiên bản STOMP client hỗ trợ.
- `host`: virtual host mà client muốn kết nối trên server.

Các header tùy chọn:

- `login`: tên người dùng để xác thực với STOMP server.
- `passcode`: mật khẩu hoặc credential theo cơ chế của server.
- `heart-beat`: khả năng gửi heartbeat và khoảng heartbeat client mong muốn nhận.

Ví dụ frame CONNECT theo STOMP 1.2:

```text
CONNECT
accept-version:1.0,1.1,1.2
host:broker.example.net
heart-beat:10000,10000

^@
```

Ví dụ trên cho biết client hỗ trợ STOMP 1.0, 1.1 và 1.2; muốn kết nối virtual host `broker.example.net`; có thể gửi heartbeat ít nhất mỗi 10 giây và mong nhận dữ liệu từ server ít nhất mỗi 10 giây.

Với STOMP 1.2, client phải gửi `accept-version` và `host`. Nếu không có `accept-version`, theo đặc tả server hiểu rằng client chỉ hỗ trợ STOMP 1.0. Vì vậy, client mới nên khai báo rõ các phiên bản mình thực sự hỗ trợ.

### CONNECT và STOMP khác nhau thế nào?

STOMP 1.2 định nghĩa cả command `CONNECT` và `STOMP`; server STOMP 1.2 phải xử lý `STOMP` tương tự `CONNECT`. Client thường tiếp tục dùng `CONNECT` để tương thích với server STOMP 1.0 cũ. `STOMP` có lợi khi hệ thống cần phân biệt rõ STOMP protocol với giao thức khác ở tầng TCP.

## 4. Server trả CONNECTED

Nếu chấp nhận kết nối, server trả frame `CONNECTED`. Trong STOMP 1.2, header bắt buộc là `version`, cho biết phiên bản STOMP được chọn cho toàn bộ session.

Các header tùy chọn:

- `heart-beat`: heartbeat server có thể gửi và mong nhận.
- `session`: định danh session do server cấp.
- `server`: thông tin tên và phiên bản server.

Ví dụ:

```text
CONNECTED
version:1.2
heart-beat:5000,8000
session:sess-7f31a9
server:ExampleBroker/3.4

^@
```

`version:1.2` xác nhận hai bên sẽ dùng STOMP 1.2. `session` và `server` là header tùy chọn; client phải hoạt động đúng ngay cả khi server không gửi chúng. Session ID là định danh kỹ thuật do server cấp, không phải username, access token hay business ID.

Nếu server không chấp nhận kết nối, server thường trả `ERROR` giải thích nguyên nhân rồi đóng kết nối. Ví dụ lỗi có thể do không có phiên bản chung, sai virtual host, credential không hợp lệ hoặc chính sách server từ chối client.

## 5. Thương lượng phiên bản STOMP

Từ STOMP 1.1, client dùng `accept-version` để công bố danh sách phiên bản hỗ trợ. Danh sách thường viết theo thứ tự tăng dần, phân cách bằng dấu phẩy. Server chọn phiên bản cao nhất mà cả client và server cùng hỗ trợ.

Ví dụ:

```text
CONNECT
accept-version:1.0,1.1,1.2
host:broker.example.net

^@

CONNECTED
version:1.2

^@
```

Nếu server hỗ trợ 1.1 và 1.2, phiên bản được chọn là 1.2. Sau frame `CONNECTED`, client và server phải tuân theo semantics của phiên bản đã chọn trong phần còn lại của session.

Nếu hai bên không có phiên bản chung, server trả `ERROR` (thường kèm header `version` liệt kê phiên bản được hỗ trợ) rồi đóng kết nối. Client không nên tiếp tục gửi `SEND` hoặc `SUBSCRIBE` sau lỗi này.

Ví dụ server chỉ hỗ trợ 1.2 nhưng client chỉ gửi `accept-version:1.0,1.1`: không có phiên bản chung, do đó session không được thiết lập.

### Phiên bản STOMP và WebSocket subprotocol

Khi chạy trên WebSocket, header HTTP `Sec-WebSocket-Protocol` có thể chứa các giá trị như `v10.stomp`, `v11.stomp` hoặc `v12.stomp`. Đây là thương lượng subprotocol của WebSocket handshake. Header `accept-version` và response `CONNECTED.version` là thương lượng phiên bản ở tầng STOMP.

Hai cơ chế có liên quan nhưng không thay thế nhau. Một kết nối có thể nâng cấp WebSocket thành công rồi vẫn thất bại ở STOMP `CONNECT` vì phiên bản không tương thích hoặc server từ chối session.

## 6. Ý nghĩa của host, login và passcode

### Header host

`host` trong STOMP `CONNECT` biểu diễn virtual host mà client muốn sử dụng trên messaging server. Nó có thể trùng với hostname của TCP endpoint, nhưng không bắt buộc. Một broker có thể phục vụ nhiều virtual host trên cùng địa chỉ mạng.

Với Spring broker relay, thuộc tính `virtualHost` được dùng làm giá trị header `host` trong các frame `CONNECT` mà relay chuyển đến broker. Điều này hữu ích khi hostname dùng để mở TCP connection khác với virtual host mà broker yêu cầu.

Không nhầm `host` của STOMP với HTTP `Host` header trong WebSocket handshake. HTTP `Host` định tuyến request đến web server; STOMP `host` chọn virtual host ở messaging broker.

### Header login và passcode

Theo STOMP protocol, `login` và `passcode` có thể dùng để xác thực client với STOMP server, đặc biệt trong mô hình STOMP over TCP. Cách xác thực và quyền của tài khoản phụ thuộc broker.

Với STOMP over WebSocket trong Spring, mặc định Spring bỏ qua `login` và `passcode` trên frame `CONNECT`, vì danh tính người dùng được xác thực ở HTTP handshake (ví dụ qua Spring Security và cookie/session). Khi dùng broker relay, Spring relay tự gắn credential cấu hình cho các kết nối client đến broker; browser client không cần tự gửi credential broker.

Nếu ứng dụng cần token authentication trong STOMP CONNECT, phải triển khai cơ chế xác thực riêng bằng `ChannelInterceptor` và gắn `Principal` vào message/session theo hướng dẫn Spring. Không coi việc gửi một header `login` hoặc `passcode` tùy ý là đã xác thực thành công.

## 7. Thương lượng heartbeat

Heartbeat giúp hai bên phát hiện kết nối TCP/WebSocket đã chết hoặc không còn hoạt động. Nó được thương lượng ngay trong `CONNECT` và `CONNECTED` bằng header `heart-beat` có hai số nguyên không âm, phân cách bằng dấu phẩy:

```text
heart-beat:<send>,<receive>
```

Ý nghĩa của hai giá trị đối với bên gửi frame:

- Giá trị thứ nhất là khoảng thời gian tối thiểu (mili giây) bên đó có thể gửi heartbeat ra ngoài.
- Giá trị thứ hai là khoảng thời gian bên đó mong muốn nhận dữ liệu/heartbeat từ phía đối diện.
- Giá trị `0` ở vị trí thứ nhất nghĩa là không thể gửi heartbeat.
- Giá trị `0` ở vị trí thứ hai nghĩa là không yêu cầu nhận heartbeat.
- Nếu không gửi header `heart-beat`, đặc tả xem tương đương `heart-beat:0,0`.

Giả sử client khai báo `heart-beat:cx,cy`, server trả `heart-beat:sx,sy`. Khoảng heartbeat thực tế được tính riêng cho từng chiều:

| Chiều truyền | Điều kiện để heartbeat hoạt động | Khoảng gửi tối thiểu |
|---|---|---|
| Client → Server | `cx > 0` và `sy > 0` | `max(cx, sy)` mili giây |
| Server → Client | `sx > 0` và `cy > 0` | `max(sx, cy)` mili giây |

Nếu một trong hai giá trị của chiều đó bằng 0, chiều đó không có heartbeat theo thỏa thuận.

### Ví dụ tính heartbeat

Client gửi:

```text
CONNECT
accept-version:1.2
host:broker.example.net
heart-beat:10000,10000

^@
```

Server trả:

```text
CONNECTED
version:1.2
heart-beat:5000,8000

^@
```

Ta có:

- Client → Server: `max(10000, 8000) = 10000` ms, tức tối thiểu mỗi 10 giây.
- Server → Client: `max(5000, 10000) = 10000` ms, tức tối thiểu mỗi 10 giây.

Nếu trong khoảng cần gửi không có STOMP frame nghiệp vụ nào, bên gửi heartbeat phải gửi một dòng kết thúc frame (EOL, thường là LF). Nếu đã có frame dữ liệu được truyền trong khoảng đó, dữ liệu này cũng chứng minh kết nối vẫn hoạt động và không cần gửi heartbeat rỗng.

Bên nhận có thể xem kết nối đã chết nếu không nhận được dữ liệu trong cửa sổ thời gian yêu cầu. Tuy nhiên, cần có sai số cho scheduler, network jitter, GC pause và tải máy; không nên đóng kết nối chỉ vì trễ một vài mili giây.

Heartbeat chỉ kiểm tra liveness của đường truyền. Nó không xác nhận một message nghiệp vụ đã được xử lý, không thay thế `ACK`, `RECEIPT` hay trạng thái hoàn tất trong database.

## 8. CONNECTED, RECEIPT và ERROR khác nhau

| Frame | Ý nghĩa |
|---|---|
| `CONNECTED` | Server chấp nhận `CONNECT` và xác nhận STOMP session đã được thiết lập với phiên bản được chọn |
| `RECEIPT` | Server xác nhận đã xử lý một frame client có yêu cầu receipt; không có nghĩa mọi công việc downstream đã hoàn tất |
| `ERROR` | Server báo lỗi protocol hoặc lỗi xử lý; theo STOMP 1.2 server đóng kết nối sau khi gửi ERROR |

Client có thể dùng `receipt` header trên các frame như `SEND`, `SUBSCRIBE` hoặc `DISCONNECT` để yêu cầu `RECEIPT`. Đặc tả không cho phép client yêu cầu receipt trên `CONNECT`; `CONNECTED` chính là phản hồi thành công cho quá trình kết nối STOMP.

Một `RECEIPT` cho biết server đã xử lý frame tương ứng và là xác nhận cộng dồn rằng các frame trước đó đã được nhận qua stream. Tuy nhiên, các frame đó có thể chưa được xử lý xong ở tầng nghiệp vụ.

## 9. Cấu hình STOMP trong Spring

Spring cung cấp hỗ trợ STOMP over WebSocket trong hai module `spring-messaging` và `spring-websocket`. Cấu hình cơ bản dùng `@EnableWebSocketMessageBroker`, đăng ký endpoint và chọn message broker:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class StompWebSocketConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

Ở đây `/ws` là URL HTTP dùng để thực hiện WebSocket handshake. Các STOMP frame được gửi sau khi transport đã mở. Destination bắt đầu bằng `/app` được chuyển đến các method `@MessageMapping`; destination `/topic` và `/queue` được xử lý bởi simple broker.

Các prefix `/topic` và `/queue` trong simple broker của Spring là quy ước đặt tên. Khi dùng broker ngoài, destination syntax và semantics phụ thuộc broker thực tế.

### Bật heartbeat cho simple broker

Simple broker có thể gửi và nhận STOMP heartbeat khi được cấu hình `TaskScheduler`. Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Bean
ThreadPoolTaskScheduler stompHeartbeatScheduler() {
    var scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(1);
    scheduler.setThreadNamePrefix("stomp-heartbeat-");
    return scheduler;
}
```

Sau đó gắn scheduler và khoảng heartbeat vào simple broker:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue")
            .setHeartbeatValue(new long[] {10000, 10000})
            .setTaskScheduler(stompHeartbeatScheduler());
}
```

Mảng heartbeat gồm hai giá trị theo thứ tự server gửi và server muốn nhận, tính bằng mili giây. Cần bảo đảm scheduler được Spring quản lý và không tạo scheduler mới cho từng lần cấu hình. Khi không có `TaskScheduler`, simple broker không thể thực hiện heartbeat theo cách cấu hình này.

Simple broker phù hợp cho ứng dụng đơn giản và lưu subscription trong bộ nhớ. Khi cần tính năng broker đầy đủ, khả năng clustering hoặc semantics ACK/receipt theo broker, hãy cân nhắc STOMP broker relay và kiểm tra tính năng cụ thể của broker.

## 10. Broker relay, virtual host và CONNECT credentials

Khi dùng external STOMP broker như RabbitMQ hoặc ActiveMQ, Spring có thể hoạt động như một relay:

- Một system TCP connection được dùng cho message phát sinh từ server-side application.
- Mỗi WebSocket client có một TCP connection riêng do relay tạo đến broker.
- Relay có thể cấu hình `systemLogin`/`systemPasscode` cho system connection và `clientLogin`/`clientPasscode` cho các connection đại diện client.
- `virtualHost` của relay được đặt vào header `host` trong frame `CONNECT` gửi tới broker.
- Relay quản lý heartbeat trên system connection và tự thử kết nối lại khi mất kết nối broker.

Ví dụ cấu hình broker relay (các biến credential phải lấy từ cấu hình bảo mật của môi trường):

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.internal")
            .setRelayPort(61613)
            .setClientLogin(clientLogin)
            .setClientPasscode(clientPasscode)
            .setSystemLogin(systemLogin)
            .setSystemPasscode(systemPasscode)
            .setVirtualHost("orders-vhost");
}
```

Trong ví dụ, `clientLogin`, `clientPasscode`, `systemLogin` và `systemPasscode` là giá trị cấu hình được inject từ secret/configuration management. Không hardcode mật khẩu broker trong source code. Spring relay tự gắn credential cấu hình vào CONNECT gửi đến broker; browser client không cần tự gửi credential broker.

## 11. Theo dõi vòng đời session trong Spring

Spring phát một số application event giúp quan sát quá trình kết nối:

| Event | Thời điểm | Ý nghĩa |
|---|---|---|
| `SessionConnectEvent` | Khi Spring nhận frame STOMP `CONNECT` | Client bắt đầu yêu cầu mở STOMP session |
| `SessionConnectedEvent` | Sau khi broker trả frame `CONNECTED` | STOMP session đã được thiết lập |
| `SessionDisconnectEvent` | Khi STOMP session kết thúc | Client gửi DISCONNECT hoặc WebSocket session bị đóng |

Có thể dùng `SessionConnectEvent` để ghi nhận yêu cầu kết nối, còn `SessionConnectedEvent` để đo thời gian thương lượng đến khi session sẵn sàng. `SessionDisconnectEvent` có thể được phát nhiều hơn một lần trong một số tình huống; handler cleanup cần idempotent.

Không coi session ID là định danh người dùng. Dùng `Principal` để nhận diện user đã xác thực; dùng session ID để truy vết một kết nối cụ thể. Khi reconnect, client có thể nhận session ID mới.

## 12. Client Spring và heartbeat

Spring cung cấp `WebSocketStompClient` cho STOMP over WebSocket và STOMP over TCP. Để bật heartbeat phía client, cấu hình `TaskScheduler` cho client:

```java
import org.springframework.scheduling.TaskScheduler;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

WebSocketStompClient stompClient = new WebSocketStompClient(
        new StandardWebSocketClient()
);
stompClient.setTaskScheduler(taskScheduler);
```

Khi có scheduler, client có thể gửi heartbeat khi không có dữ liệu khác và theo dõi read inactivity. Khoảng mặc định trong tài liệu Spring hiện hành là 10 giây cho write inactivity và 10 giây cho read inactivity; ứng dụng có thể tùy chỉnh theo mạng, broker và SLA.

Khi session được thiết lập, `StompSessionHandler.afterConnected(...)` nhận `StompSession` và các header của frame `CONNECTED`. Đây là nơi phù hợp để đăng ký subscription và bắt đầu gửi message sau khi kết nối đã thành công.

## 13. Lỗi thường gặp khi CONNECT và CONNECTED

- **Nhầm WebSocket 101 với STOMP CONNECTED:** transport đã mở nhưng STOMP session có thể vẫn chưa được chấp nhận.
- **Thiếu `accept-version` trên client mới:** server hiểu client chỉ hỗ trợ STOMP 1.0 theo đặc tả.
- **Không có phiên bản chung:** server trả ERROR và đóng kết nối; client cần báo lỗi tương thích rõ ràng.
- **Nhầm `host` STOMP với HTTP Host:** một giá trị chọn virtual host broker, giá trị kia định tuyến HTTP request.
- **Coi `session` là header bắt buộc:** server được phép không gửi session ID trong `CONNECTED`.
- **Dùng session ID làm user ID:** session ID chỉ nhận diện kết nối, không chứng minh danh tính hoặc quyền.
- **Nhầm `login`/`passcode` với xác thực HTTP của Spring:** Spring STOMP over WebSocket mặc định bỏ qua các header này.
- **Heartbeat tính sai chiều:** chiều client gửi dùng `max(client-send, server-receive)`; chiều server gửi dùng `max(server-send, client-receive)`.
- **Đặt heartbeat bằng 0 nhưng kỳ vọng phát hiện idle connection:** giá trị 0 tắt heartbeat ở chiều tương ứng.
- **Dùng heartbeat như ACK nghiệp vụ:** heartbeat chỉ cho biết đường truyền còn hoạt động.
- **Bật heartbeat nhưng không cấu hình scheduler:** simple broker hoặc STOMP client không có scheduler để phát heartbeat định kỳ.
- **Không xử lý ERROR frame:** server có thể đóng socket ngay sau khi gửi ERROR.
- **Đăng ký subscription trước CONNECTED:** session chưa sẵn sàng; hãy chờ callback/event xác nhận kết nối.
- **Giả định CONNECTED liệt kê toàn bộ khả năng broker:** phiên bản giao thức được chọn không mô tả mọi extension hay delivery semantics riêng của broker.

## 14. Kiểm thử thương lượng phiên

Nên kiểm thử các tình huống sau với broker/client version thực tế:

1. Client và server cùng hỗ trợ STOMP 1.2: CONNECTED trả `version:1.2`.
2. Client hỗ trợ 1.0/1.1/1.2, server hỗ trợ 1.1/1.2: server chọn phiên bản chung cao nhất là 1.2.
3. Client không gửi `accept-version`: xác nhận server áp dụng semantics 1.0 theo đặc tả.
4. Hai bên không có phiên bản chung: server trả ERROR và đóng kết nối.
5. Client/server tắt heartbeat ở một chiều bằng giá trị 0: chiều đó không gửi heartbeat.
6. Hai bên bật heartbeat: xác nhận khoảng thời gian thực tế theo phép tính max cho từng chiều.
7. Không có message nghiệp vụ trong thời gian dài: heartbeat EOL vẫn giữ kết nối hoạt động.
8. Broker mất kết nối: client nhận lỗi transport/heartbeat timeout và thực hiện reconnect theo chính sách.
9. Virtual host sai: broker từ chối CONNECT với lỗi phù hợp.
10. Credential sai: xác nhận HTTP authentication hoặc broker authentication hoạt động đúng với topology đang dùng.
11. Spring nhận CONNECT nhưng broker chưa trả CONNECTED: chỉ đánh dấu session sẵn sàng sau `SessionConnectedEvent`.
12. Session disconnect hoặc reconnect: session ID mới được xử lý như một kết nối mới và cleanup không bị lặp side effect.

Khi điều tra, ghi lại phiên bản STOMP client đề xuất, phiên bản server chọn, heartbeat hai phía, thời điểm CONNECT/CONNECTED/ERROR, WebSocket close status và nguyên nhân broker trả về. Không ghi `passcode`, token hoặc dữ liệu xác thực vào log.

## 15. Quy trình xử lý kết nối STOMP

1. Mở WebSocket đến đúng endpoint và thương lượng subprotocol STOMP ở HTTP handshake.
2. Gửi `CONNECT` với `accept-version` và `host` đúng; thêm heartbeat nếu client hỗ trợ.
3. Chờ `CONNECTED`; đọc `version` được chọn và heartbeat server trả về.
4. Tính khoảng heartbeat riêng cho client→server và server→client; bật scheduler tương ứng.
5. Chỉ sau khi session được xác nhận, mới gửi `SUBSCRIBE` hoặc `SEND`.
6. Xử lý `ERROR`, transport close và heartbeat timeout bằng trạng thái kết nối rõ ràng.
7. Khi reconnect, thương lượng session mới và đăng ký lại các subscription cần thiết.
8. Dùng `Principal`/authentication context để xác định user; dùng session ID để truy vết connection.
9. Kiểm thử phiên bản, virtual host, credentials, heartbeat, broker restart và disconnect.

## 16. Kết luận

`CONNECT` là lời đề nghị mở STOMP session của client; `CONNECTED` xác nhận server chấp nhận session và công bố phiên bản giao thức được chọn. `accept-version` cho phép hai bên chọn phiên bản chung cao nhất; `host` chọn virtual host; `session` và `server` là metadata tùy chọn.

Heartbeat được thương lượng theo hai chiều độc lập. Client gửi theo `max(client-send, server-receive)` và server gửi theo `max(server-send, client-receive)` khi cả hai phía đều bật chiều tương ứng. Trong Spring, cần phân biệt HTTP/WebSocket handshake với STOMP CONNECT, dùng `SessionConnectedEvent` để xác định session đã sẵn sàng, cấu hình scheduler cho heartbeat và hiểu cách Spring xử lý credential khi dùng WebSocket hoặc broker relay.

## Tài liệu tham khảo

- [STOMP Protocol Specification 1.2 — Connecting, Protocol Negotiation and Heart-beating](https://stomp.github.io/stomp-specification-1.2.html)
- [Spring Framework Reference — STOMP Overview](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html)
- [Spring Framework Reference — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Spring Framework Reference — Simple Broker and Heartbeats](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework Reference — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Spring Framework Reference — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)
- [Spring Framework Reference — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Framework Reference — Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)