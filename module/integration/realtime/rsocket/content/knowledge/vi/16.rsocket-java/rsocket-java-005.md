# TcpClientTransport, TcpServerTransport và truyền tải WebSocket

RSocket Java tách giao thức RSocket khỏi transport bên dưới. Cùng một ứng dụng có thể trao đổi Request-Response, Fire-and-Forget, Request-Stream hoặc Request-Channel qua TCP hoặc WebSocket; phần xử lý payload và route không cần viết lại chỉ vì thay đổi cách kết nối.

Trong module `INTEGRATION_REALTIME_RSOCKET`, việc chọn transport ảnh hưởng tới cách client kết nối, cách server bind cổng, khả năng đi qua proxy/firewall và loại client có thể sử dụng. RSocket Java cung cấp `TcpClientTransport` và `TcpServerTransport` cho TCP, cùng `WebsocketClientTransport` và `WebsocketServerTransport` cho WebSocket. Bài viết này trình bày cách khởi tạo hai phía, quản lý vòng đời kết nối và chọn transport phù hợp.

## 1. Transport nằm ở đâu trong kiến trúc RSocket?

Một kết nối RSocket có thể nhìn theo ba phần:

- **Application handler:** xử lý request, route, metadata và payload nghiệp vụ.
- **RSocket protocol:** quản lý stream, frame, demand/backpressure, cancellation, keepalive và các mô hình tương tác.
- **Transport:** chuyển frame qua mạng. Trong bài này, transport là TCP hoặc WebSocket.

```text
Ứng dụng Java
  RSocketRequester / RSocket API
             |
             v
       RSocket protocol
             |
       +-----+------+
       |            |
       v            v
   TCP transport  WebSocket transport
       |            |
       +-----+------+
             |
          Network
             |
       +-----+------+
       |            |
       v            v
   TCP server   WebSocket server
       |            |
       +-----+------+
             |
       RSocket protocol
             |
       Application handler
```

Transport không quyết định mô hình tương tác. Ví dụ, Request-Channel vẫn là một stream hai chiều dù frame được truyền qua TCP hay được đóng gói trong WebSocket message.

## 2. Kết nối TCP bằng RSocket Java

TCP là lựa chọn trực tiếp cho giao tiếp giữa các dịch vụ Java hoặc các ứng dụng có thể mở kết nối socket tới nhau. RSocket Java dùng Netty transport để mở kết nối TCP và truyền các frame RSocket qua kết nối đó.

### 2.1. Server với TcpServerTransport

`TcpServerTransport` bind địa chỉ và cổng mà server lắng nghe. Server cần cung cấp `SocketAcceptor`, tức logic tạo responder cho mỗi kết nối mới.

```java
import io.rsocket.AbstractRSocket;
import io.rsocket.Payload;
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.TcpServerTransport;
import io.rsocket.util.DefaultPayload;
import reactor.core.publisher.Mono;

var server = RSocketServer
    .create((setup, sendingSocket) -> Mono.just(new AbstractRSocket() {
        @Override
        public Mono<Payload> requestResponse(Payload request) {
            String message;
            try {
                message = request.getDataUtf8();
            } finally {
                request.release();
            }

            return Mono.just(DefaultPayload.create("echo: " + message));
        }
    }))
    .bind(TcpServerTransport.create("0.0.0.0", 7000))
    .block();

server.onClose().block();
```

Trong ví dụ, server lắng nghe trên cổng `7000`. `0.0.0.0` cho phép bind trên các interface IPv4 của máy; trong môi trường production cần chọn interface và quy tắc firewall theo kiến trúc mạng. Nếu chỉ thử nghiệm trên máy cá nhân, có thể bind `localhost` để chỉ nhận kết nối loopback.

`SocketAcceptor` tạo một responder cho kết nối. `AbstractRSocket` cho phép override mô hình tương tác cần dùng; ví dụ này chỉ cài đặt Request-Response để minh họa. Payload là tài nguyên có thể reference-count, vì vậy handler giải phóng request sau khi đọc data. Trong ứng dụng thật, cần triển khai các phương thức tương ứng với mô hình tương tác của API.

`bind(...).block()` trả về `CloseableChannel`. `onClose().block()` giữ server chạy cho đến khi channel đóng. Trong ứng dụng Spring Boot hoặc container có lifecycle riêng, nên gắn channel vào lifecycle của ứng dụng để shutdown có kiểm soát.

### 2.2. Client với TcpClientTransport

Client tạo transport tới host và port của server, rồi đưa transport cho `RSocketConnector`:

```java
import io.rsocket.RSocket;
import io.rsocket.core.RSocketConnector;
import io.rsocket.transport.netty.client.TcpClientTransport;
import io.rsocket.util.DefaultPayload;

RSocket socket = RSocketConnector.create()
    .connect(TcpClientTransport.create("localhost", 7000))
    .block();

String reply = socket
    .requestResponse(DefaultPayload.create("hello"))
    .map(response -> {
        try {
            return response.getDataUtf8();
        } finally {
            response.release();
        }
    })
    .block();

socket.dispose();
```

`TcpClientTransport.create("localhost", 7000)` chỉ mô tả địa chỉ remote mà client cần kết nối. `RSocketConnector` thực hiện handshake SETUP và trả về `RSocket` khi kết nối thành công. Khi không còn sử dụng socket, ứng dụng cần dispose/đóng nó để giải phóng transport và tài nguyên liên quan.

Trong service reactive, tránh gọi `.block()` trên event-loop thread. Ví dụ trên minh họa chương trình console hoặc đoạn khởi tạo đồng bộ; ứng dụng reactive nên giữ `Mono<RSocket>` và kết hợp nó vào pipeline thay vì chặn thread.

## 3. Kết nối WebSocket bằng RSocket Java

WebSocket chạy trên HTTP Upgrade rồi sử dụng WebSocket frames để vận chuyển dữ liệu. RSocket Java đóng gói frame RSocket trong WebSocket message. Transport này hữu ích khi client chạy trong trình duyệt, khi hạ tầng chỉ cho phép đi qua HTTP/HTTPS ingress hoặc khi cần định tuyến qua reverse proxy hỗ trợ WebSocket.

WebSocket không biến RSocket thành REST. Sau khi handshake WebSocket hoàn tất, hai bên vẫn trao đổi các frame RSocket và sử dụng cùng các mô hình tương tác, metadata, demand và cancellation.

### 3.1. Server với WebsocketServerTransport

Server dùng cùng `SocketAcceptor` như TCP; chỉ thay transport khi bind:

```java
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.WebsocketServerTransport;

var server = RSocketServer
    .create(socketAcceptor)
    .bind(WebsocketServerTransport.create("0.0.0.0", 8080))
    .block();

server.onClose().block();
```

`socketAcceptor` là handler đã được định nghĩa cho ứng dụng. Ví dụ này bind WebSocket server trên cổng `8080`. Client phải dùng URI WebSocket tương ứng với endpoint mà server công bố. Khi dùng Spring Boot, mapping path có thể được cấu hình riêng; khi dùng transport Netty trực tiếp, cần xác nhận path mặc định hoặc path được cấu hình trong phiên bản thư viện đang dùng.

### 3.2. Client với WebsocketClientTransport

Client tạo transport từ URI `ws://` hoặc `wss://`:

```java
import io.rsocket.RSocket;
import io.rsocket.core.RSocketConnector;
import io.rsocket.transport.netty.client.WebsocketClientTransport;
import java.net.URI;

URI endpoint = URI.create("ws://localhost:8080/");

RSocket socket = RSocketConnector.create()
    .connect(WebsocketClientTransport.create(endpoint))
    .block();
```

`ws://` là WebSocket không mã hóa ở tầng transport; `wss://` sử dụng TLS. Địa chỉ, port, path và cấu hình TLS của client phải khớp với WebSocket endpoint phía server hoặc reverse proxy. Nếu proxy công bố path `/rsocket`, client phải kết nối đúng URI có path đó.

## 4. So sánh TCP và WebSocket

| Tiêu chí | TCP | WebSocket |
|---|---|---|
| Kết nối | Socket TCP trực tiếp | HTTP Upgrade rồi chuyển sang WebSocket |
| URI/địa chỉ | Host và port | `ws://` hoặc `wss://` cùng path |
| Trình duyệt | Không thể mở TCP socket tùy ý từ JavaScript browser | Được hỗ trợ bởi WebSocket API của trình duyệt |
| Hạ tầng mạng | Cần mở và định tuyến cổng TCP riêng | Có thể đi qua HTTP ingress/proxy hỗ trợ Upgrade |
| Overhead | Framing trực tiếp, thường ít lớp đóng gói hơn | Có thêm WebSocket framing và chi phí handshake |
| Định tuyến | Thường theo địa chỉ và port | Có thể theo host/path qua reverse proxy |
| Trường hợp phù hợp | Service-to-service, mạng nội bộ, client Java/native | Browser client, môi trường chỉ công khai HTTP/HTTPS, proxy/ingress |

Không có transport tốt nhất cho mọi tình huống. Nếu cả client và server đều là service Java trong mạng được kiểm soát, TCP thường đơn giản và trực tiếp. Nếu cần giao tiếp với browser hoặc phải đi qua hạ tầng HTTP, WebSocket thường thuận tiện hơn. Hãy đo latency và throughput trên đường mạng thực tế trước khi quyết định.

## 5. Dùng Spring Boot với TCP hoặc WebSocket

Spring Boot có thể tự cấu hình RSocket server từ các thuộc tính `spring.rsocket.server`. Ví dụ server TCP:

```yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
```

Để chạy server qua WebSocket, đổi transport và cấu hình mapping path:

```yaml
spring:
  rsocket:
    server:
      transport: websocket
      port: 8080
      mapping-path: /rsocket
```

Client Spring có thể tạo `RSocketRequester` bằng transport tương ứng:

```java
import java.net.URI;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester tcpRequester = RSocketRequester.builder()
    .connectTcp("localhost", 7000)
    .block();

RSocketRequester websocketRequester = RSocketRequester.builder()
    .connectWebSocket(URI.create("ws://localhost:8080/rsocket"))
    .block();
```

Các đoạn `block()` trên phù hợp với ví dụ khởi tạo đồng bộ. Trong ứng dụng Spring reactive, nên tạo requester ở lifecycle phù hợp và không block event loop. Nếu cần tùy chỉnh connector, có thể dùng callback `rsocketConnector(...)` trên builder để cấu hình keepalive, Resume hoặc các thiết lập của RSocket Java.

`mapping-path` áp dụng cho WebSocket endpoint; TCP dùng địa chỉ và port để kết nối. Khi triển khai client và server ở hai môi trường khác nhau, hãy quản lý host, port, path và scheme bằng cấu hình theo môi trường thay vì hardcode vào code nghiệp vụ.

## 6. TLS, xác thực và metadata

Chọn TCP hay WebSocket không thay thế thiết kế bảo mật. Cần xác định cách bảo vệ transport, xác thực peer và phân quyền từng route:

- Với TCP, dùng cấu hình TLS của transport/server khi dữ liệu đi qua mạng không tin cậy hoặc chính sách hạ tầng yêu cầu mã hóa.
- Với WebSocket, dùng `wss://` để bảo vệ handshake và dữ liệu bằng TLS. Reverse proxy cần chuyển tiếp đúng header Upgrade và bảo toàn kết nối hai chiều.
- Xác thực danh tính client bằng cơ chế đã thống nhất, chẳng hạn authentication metadata được bảo vệ hoặc cơ chế xác thực ở tầng kết nối.
- Phân quyền theo route và hành động. Có kết nối hợp lệ không đồng nghĩa client được phép gọi mọi handler.
- Không đưa token hoặc dữ liệu nhạy cảm vào URL query string hay log của proxy. Bảo vệ metadata theo cơ chế xác thực và mã hóa phù hợp.
- Giới hạn kích thước payload, số stream, thời gian xử lý và tốc độ gửi để giảm nguy cơ lạm dụng tài nguyên.

Với WebSocket qua proxy, kiểm tra idle timeout, giới hạn thời gian kết nối và chính sách đóng socket của load balancer. Với TCP, kiểm tra firewall, NAT timeout và cổng được phép. RSocket KEEPALIVE là frame ở tầng RSocket; nó khác với TCP keepalive và WebSocket Ping/Pong ở tầng transport.

## 7. Vòng đời kết nối và graceful shutdown

Transport là tài nguyên có vòng đời. Ứng dụng cần đóng kết nối client và server khi dừng, xử lý lỗi connect và đặt timeout hợp lý.

Đối với client:

- Chỉ tạo một kết nối dùng chung khi nhiều request có thể chia sẻ cùng RSocket session theo thiết kế ứng dụng.
- Theo dõi `onClose`/availability và xử lý lỗi kết nối.
- Dispose socket khi ứng dụng hoặc component sở hữu nó dừng.
- Nếu cần reconnect hoặc Resume, định nghĩa retry/backoff và giữ session state theo khả năng của implementation.

Đối với server:

- Bind trên interface và port đúng với môi trường triển khai.
- Quản lý `CloseableChannel` trong lifecycle của ứng dụng.
- Khi shutdown, ngừng nhận kết nối mới, cho các request đang chạy thời gian kết thúc phù hợp rồi đóng channel.
- Theo dõi số kết nối, số stream, lỗi handshake và lỗi transport.

Không tạo một RSocket connection mới cho từng payload nếu có thể tái sử dụng session. Việc tái sử dụng giúp giảm handshake và chi phí socket, nhưng cần giới hạn số kết nối, quản lý concurrency và xử lý lỗi ở cấp session.

## 8. Những lỗi cấu hình thường gặp

- **Client và server dùng transport khác nhau:** TCP client không thể kết nối trực tiếp tới WebSocket endpoint và ngược lại.
- **Sai host/port:** server chỉ bind `localhost` nhưng client ở container hoặc máy khác cần truy cập qua network interface.
- **Sai WebSocket path:** reverse proxy hoặc Spring Boot dùng `/rsocket` nhưng client lại kết nối `/`.
- **Dùng `ws://` khi endpoint yêu cầu TLS:** handshake thất bại; cần `wss://` và trust chain phù hợp.
- **Proxy không hỗ trợ WebSocket Upgrade:** HTTP request có thể tới được ingress nhưng kết nối hai chiều không được thiết lập.
- **Timeout của proxy ngắn hơn thời gian nhàn rỗi:** kết nối bị đóng dù ứng dụng nghĩ rằng session còn hoạt động; cần phối hợp KEEPALIVE và idle timeout.
- **Không đóng socket/channel:** tài nguyên Netty, event loop và file descriptor có thể tồn tại lâu hơn vòng đời ứng dụng.
- **Block trên event loop:** `.block()` trong luồng reactive có thể làm tắc các kết nối và stream khác.

## 9. Kiểm thử TCP và WebSocket

Nên chạy cùng một bộ kiểm thử handler trên cả hai transport để xác nhận logic nghiệp vụ không phụ thuộc vào cách truyền frame:

1. Khởi động server TCP và kết nối bằng `TcpClientTransport`.
2. Khởi động server WebSocket và kết nối bằng `WebsocketClientTransport` tới đúng URI/path.
3. Kiểm tra Request-Response, Fire-and-Forget, Request-Stream và Request-Channel.
4. Kiểm tra metadata/route, payload lớn, fragmentation và backpressure.
5. Đóng client đột ngột; xác nhận stream bị hủy và tài nguyên được giải phóng.
6. Kiểm tra timeout, KEEPALIVE và reconnect/Resume nếu ứng dụng bật các tính năng đó.
7. Kiểm tra TLS với chứng thư hợp lệ, chứng thư không tin cậy và hostname không khớp.
8. Với WebSocket, kiểm thử qua reverse proxy/ingress thực tế, bao gồm Upgrade header, path, idle timeout và giới hạn kết nối.
9. Với TCP, kiểm thử firewall, port mapping, NAT và trường hợp server restart.

Trong production, theo dõi số kết nối theo transport, handshake latency, connect failure, thời gian sống socket, số stream hoạt động, throughput, lỗi protocol và số lần reconnect. Đừng chỉ kiểm thử localhost; đường mạng thật có proxy, TLS termination và timeout có thể tạo ra hành vi khác.

## 10. Kết luận

`TcpClientTransport` và `TcpServerTransport` cung cấp kết nối TCP trực tiếp cho các ứng dụng Java; `WebsocketClientTransport` và `WebsocketServerTransport` đưa frame RSocket qua WebSocket, thuận tiện cho browser và hạ tầng HTTP. Cả hai dùng cùng RSocket protocol và application handler. Hãy chọn transport theo môi trường mạng và loại client, cấu hình host/port/path/TLS nhất quán, quản lý lifecycle của socket/channel và kiểm thử qua đúng proxy hoặc network path sẽ dùng khi triển khai.
