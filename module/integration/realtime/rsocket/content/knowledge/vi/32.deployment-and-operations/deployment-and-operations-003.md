# Kiểm tra WebSocket Upgrade, giới hạn frame và thời gian chờ nhàn rỗi

RSocket có thể chạy trên WebSocket để client trình duyệt, ứng dụng di động hoặc dịch vụ phía sau reverse proxy giao tiếp realtime với Spring Boot. Khi triển khai, một kết nối không chỉ phụ thuộc vào handler RSocket. HTTP Upgrade phải thành công, proxy phải chuyển tiếp đúng header, WebSocket phải chấp nhận kích thước frame/message, RSocket phải hoàn tất SETUP và các lớp mạng phải giữ kết nối đủ lâu.

Ba nhóm sự cố thường gặp là:

- **Upgrade thất bại**: client nhận 400, 404, 426 hoặc 502 thay vì 101 Switching Protocols.
- **Payload/frame quá lớn**: handshake thành công nhưng interaction bị từ chối, WebSocket đóng hoặc server hết tài nguyên.
- **Kết nối nhàn rỗi bị đóng**: stream đang chờ dữ liệu hoặc client không gửi request mới thì load balancer, proxy, NAT hay RSocket keepalive đóng connection.

Bài học này hướng dẫn kiểm tra handshake HTTP/1.1, cấu hình WebSocket transport cho RSocket, phân biệt giới hạn WebSocket frame với RSocket payload, căn chỉnh idle timeout và keepalive, quan sát close code, cũng như xây dựng kiểm thử triển khai qua proxy.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích HTTP Upgrade handshake và phản hồi 101.
- Phân biệt WebSocket handshake với RSocket SETUP.
- Kiểm tra path, Origin, TLS, proxy headers và subprotocol nếu ứng dụng sử dụng.
- Cấu hình Spring Boot RSocket server chạy trên WebSocket.
- Phân biệt WebSocket frame, WebSocket message, RSocket frame và application payload.
- Đặt giới hạn kích thước ở proxy, WebSocket server và application layer.
- Phân biệt WebSocket Ping/Pong với RSocket KEEPALIVE.
- Căn chỉnh keepalive interval, max lifetime và idle timeout của các intermediary.
- Chẩn đoán close code, handshake failure, frame too large và idle disconnect.
- Kiểm thử cả transport trực tiếp lẫn đường đi qua ingress/load balancer.

## 1. Luồng kết nối RSocket qua WebSocket

Khi client kết nối RSocket qua WebSocket, hai giao thức được thiết lập theo thứ tự:

1. Client gửi HTTP request để nâng cấp kết nối thành WebSocket.
2. Server hoặc reverse proxy trả 101 Switching Protocols nếu handshake hợp lệ.
3. Hai bên trao đổi WebSocket messages.
4. RSocket client gửi frame SETUP bên trong WebSocket connection.
5. Server chấp nhận SETUP và bắt đầu xử lý các interaction RSocket.

~~~mermaid
sequenceDiagram
    participant C as WebSocket / RSocket client
    participant P as Ingress / reverse proxy
    participant S as Spring RSocket server
    C->>P: HTTP GET + Upgrade: websocket
    P->>S: Forward Upgrade headers
    S-->>P: 101 Switching Protocols
    P-->>C: 101 Switching Protocols
    C->>S: WebSocket binary message chứa RSocket SETUP
    Note over C,S: Server accepts SETUP; the RSocket connection is ready
    C->>S: REQUEST_RESPONSE / REQUEST_STREAM
    S-->>C: NEXT / COMPLETE / ERROR
~~~

**HTTP 101 chỉ chứng minh WebSocket handshake đã thành công.** Nó chưa chứng minh RSocket SETUP, authentication metadata, data MIME type hoặc route nghiệp vụ đã hợp lệ. Khi chẩn đoán, cần xác định lỗi xuất hiện ở bước HTTP Upgrade hay sau khi WebSocket đã được thiết lập.

### 1.1. Các lớp giao thức

| Lớp | Chịu trách nhiệm | Ví dụ lỗi |
|---|---|---|
| HTTP handshake | Nâng cấp HTTP connection thành WebSocket | 404 sai path, 426 thiếu Upgrade |
| WebSocket | Binary messages, fragmentation, Ping/Pong, close | 1009 message quá lớn, 1002 protocol error |
| RSocket | SETUP, interaction frames, keepalive, request/cancel | SETUP bị từ chối, stream ERROR |
| Application | Route, codec, validation, authorization | Route không tồn tại, DTO sai |

Không gộp tất cả lỗi thành “WebSocket không kết nối được”. Ghi nhận lớp phát hiện lỗi và thời điểm tương ứng để khoanh vùng nhanh.

## 2. HTTP/1.1 WebSocket Upgrade handshake

WebSocket handshake truyền thống dùng HTTP/1.1. Client gửi GET đến endpoint WebSocket với các header bắt buộc:

~~~http
GET /rsocket HTTP/1.1
Host: api.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: https://app.example.com
~~~

Server trả về:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
~~~

Header Sec-WebSocket-Accept được tính từ Sec-WebSocket-Key và GUID theo RFC 6455. Client xác minh giá trị này để chắc chắn server hiểu handshake WebSocket.

Các header cần kiểm tra:

| Header | Mục đích |
|---|---|
| Upgrade | Yêu cầu chuyển giao thức sang websocket |
| Connection | Chứa token Upgrade |
| Sec-WebSocket-Key | Nonce của handshake |
| Sec-WebSocket-Version | Phiên bản protocol, thông thường là 13 |
| Origin | Nguồn trang web mở kết nối, cần kiểm tra theo chính sách |
| Sec-WebSocket-Protocol | Subprotocol tùy chọn nếu hai phía có thỏa thuận |

Upgrade và Connection là header hop-by-hop. Reverse proxy phải chủ động chuyển tiếp chúng; không thể giả định proxy tự giữ nguyên như header thông thường.

### 2.1. Kiểm tra handshake bằng curl

Có thể kiểm tra endpoint có trả 101 bằng một request HTTP/1.1:

~~~bash
curl --http1.1 -i \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Origin: https://app.example.com" \
  https://api.example.com/rsocket
~~~

Kết quả mong đợi là status 101 cùng các header Upgrade, Connection và Sec-WebSocket-Accept. Công cụ curl chỉ giúp kiểm tra handshake HTTP; nó không tự gửi RSocket SETUP hoặc thực hiện interaction RSocket.

Nếu curl treo sau khi nhận 101, điều đó có thể bình thường vì kết nối đã chuyển sang WebSocket và đang chờ binary message. Dùng WebSocket/RSocket client thật để kiểm tra phần protocol phía sau.

### 2.2. Ý nghĩa các status khi Upgrade thất bại

| Status | Khả năng nguyên nhân | Kiểm tra |
|---|---|---|
| 400 Bad Request | Header handshake thiếu hoặc sai | Upgrade, Connection, key, version |
| 401 Unauthorized | Chính sách xác thực tại gateway | Cookie, token hoặc cơ chế auth handshake |
| 403 Forbidden | Origin hoặc policy bị từ chối | Origin allowlist, authorization |
| 404 Not Found | Sai WebSocket mapping path | Path và ingress rewrite |
| 426 Upgrade Required | Request không được nhận dạng là WebSocket Upgrade | HTTP version và Upgrade headers |
| 502 Bad Gateway | Proxy không kết nối được upstream hoặc upstream đóng sớm | Backend address, TLS upstream, port |
| 504 Gateway Timeout | Proxy chờ upstream quá lâu | Timeout, backend health và routing |

Status thực tế phụ thuộc gateway, proxy và server. Hãy đọc response body và access log của từng hop thay vì suy ra nguyên nhân chỉ từ status code.

## 3. WebSocket Upgrade và HTTP/2

Handshake HTTP/1.1 dùng Upgrade và 101. WebSocket qua HTTP/2 có thể dùng Extended CONNECT theo RFC 8441; đó là cơ chế khác với HTTP/1.1 Upgrade thông thường. Khi Extended CONNECT thành công, server trả response 2xx (thường là 200), không dùng HTTP/1.1 status 101.

Không phải mọi reverse proxy, ingress controller, CDN hoặc client đều hỗ trợ WebSocket Extended CONNECT. Nếu client kết nối HTTP/2 đến edge nhưng edge không hỗ trợ chuyển tiếp WebSocket qua HTTP/2, hệ thống có thể cần terminate ở edge và mở kết nối HTTP/1.1 WebSocket tới upstream.

Khi kiểm tra production, xác minh:

- HTTP version giữa browser và edge.
- HTTP version giữa edge và upstream.
- Proxy có hỗ trợ Extended CONNECT nếu cần hay không.
- TLS termination và ALPN có làm thay đổi đường đi không.
- WebSocket Upgrade headers có được giữ trên hop HTTP/1.1 hay không.

Đừng thêm header Upgrade thủ công vào request HTTP/2; hãy dùng cơ chế WebSocket mà client và proxy hỗ trợ.

## 4. Cấu hình Spring Boot RSocket server trên WebSocket

Với ứng dụng WebFlux chạy trên Reactor Netty, Spring Boot có thể gắn RSocket WebSocket vào HTTP web server hiện tại. Cấu hình transport và mapping path:

~~~yaml
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
~~~

Trong cấu hình này:

- transport chọn WebSocket thay vì TCP.
- mapping-path là HTTP path dùng cho handshake.
- RSocket dùng chung HTTP port của ứng dụng WebFlux, ví dụ server.port.

Client kết nối đến endpoint tương ứng, ví dụ:

~~~text
ws://localhost:8080/rsocket
~~~

Nếu cần một RSocket WebSocket server độc lập, không gắn vào HTTP server WebFlux, cấu hình port riêng:

~~~yaml
spring:
  rsocket:
    server:
      transport: websocket
      port: 7000
~~~

Hai mô hình này khác nhau: mapping-path dùng khi RSocket được gắn vào WebFlux server; port dùng để khởi chạy embedded RSocket server riêng. Với mô hình WebFlux, Spring Boot chỉ hỗ trợ tích hợp này trên Reactor Netty.

Trong production, thường dùng TLS ở edge:

~~~text
wss://api.example.com/rsocket
~~~

Không nhầm route RSocket như devices.lookup với mapping path WebSocket như /rsocket. Mapping path chọn endpoint transport; route được gửi sau khi RSocket connection đã được thiết lập.

### 4.1. Kết nối từ RSocketRequester

Ví dụ client Java:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> connector
                .keepAlive(
                        Duration.ofSeconds(20),
                        Duration.ofSeconds(60)))
        .websocket(URI.create(
                "wss://api.example.com/rsocket"));
~~~

Giá trị 20 giây và 60 giây chỉ là ví dụ. Hãy chọn interval và max lifetime dựa trên idle timeout nhỏ nhất của mạng và chính sách phát hiện connection chết.

Nếu dùng Spring Boot auto-configuration, xác minh transport, mapping path, TLS termination và codec strategy thực tế bằng integration test. Không giả định cấu hình TCP cũ vẫn được áp dụng sau khi chuyển sang WebSocket.

### 4.2. Browser client

Browser có thể mở WebSocket:

~~~javascript
const socket = new WebSocket(
  "wss://api.example.com/rsocket"
);
socket.binaryType = "arraybuffer";
~~~

RSocket client library cho browser sẽ quản lý RSocket frames và SETUP trên WebSocket này. Ứng dụng không nên tự serialize RSocket frame nếu đã dùng thư viện RSocket client.

WebSocket API của browser không cho JavaScript tự đặt tùy ý các header handshake như Authorization hoặc Sec-WebSocket-Key. Với browser client, cân nhắc secure cookie hoặc authentication metadata trong RSocket SETUP theo mô hình bảo mật đã chọn. Không đưa bearer token dài hạn vào query string vì URL thường xuất hiện trong access log và telemetry.

## 5. Cấu hình reverse proxy cho WebSocket

Reverse proxy cần chuyển tiếp HTTP/1.1 Upgrade headers và duy trì kết nối sau handshake. Ví dụ Nginx:

~~~nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

upstream rsocket_backend {
    server 127.0.0.1:7000;
}

server {
    listen 443 ssl;
    server_name api.example.com;

    location /rsocket {
        proxy_pass http://rsocket_backend;
        proxy_http_version 1.1;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 75s;
        proxy_send_timeout 75s;
        proxy_buffering off;
    }
}
~~~

Đoạn cấu hình giả định TLS kết thúc tại Nginx và upstream lắng nghe HTTP/WebSocket không mã hóa trên mạng nội bộ được bảo vệ. Nếu mã hóa cả hop upstream, dùng HTTPS/WSS tới backend và cấu hình trust phù hợp.

Các điểm cần kiểm tra:

- proxy_http_version 1.1 cho đường upstream dùng HTTP/1.1 Upgrade.
- Upgrade và Connection được chuyển tiếp.
- proxy_pass giữ đúng path hoặc rewrite theo mapping path của Spring Boot.
- Timeout đọc/ghi phù hợp với heartbeat.
- Access log không ghi token hoặc query chứa credential.
- Proxy không buffer hoặc biến đổi binary stream theo cách làm hỏng WebSocket.

### 5.1. Path rewrite

Giả sử Spring Boot lắng nghe /rsocket nhưng ingress public expose /realtime. Khi đó proxy phải chuyển request đến đúng path backend. Nếu path bị rewrite thành /, server có thể trả 404 dù Upgrade headers hoàn toàn đúng.

Kiểm tra path ở cả ba nơi:

1. URL client dùng.
2. Path sau rewrite ở ingress/reverse proxy.
3. Mapping path mà RSocket server bind.

Không dùng route RSocket để sửa lỗi mapping path. Route chỉ được xử lý sau khi handshake và SETUP thành công.

## 6. Origin, TLS và subprotocol

Header Origin cho biết trang web khởi tạo WebSocket. Với browser client, server/gateway nên kiểm tra Origin theo allowlist để giảm nguy cơ website không tin cậy mở kết nối bằng cookie của người dùng.

Origin không phải cơ chế authentication. Một client không phải browser có thể tự đặt Origin; hãy xác thực danh tính bằng cookie/session hoặc RSocket authentication metadata đã được xác minh.

Các kiểm tra triển khai:

- Chỉ cho phép Origin của frontend hợp lệ.
- Dùng WSS ở mạng công cộng.
- Kiểm tra certificate chain và hostname.
- Không tin X-Forwarded-Proto từ nguồn bất kỳ; chỉ tin header do proxy tin cậy đặt.
- Nếu sử dụng Sec-WebSocket-Protocol, client và server phải thống nhất giá trị được chọn.
- Không yêu cầu subprotocol tùy chọn nếu RSocket client/server của ứng dụng không sử dụng nó.

RSocket SETUP có thể mang data MIME type, metadata MIME type và setup metadata. Thành công ở HTTP handshake không đồng nghĩa authentication hoặc authorization ở RSocket đã thành công.

## 7. Phân biệt WebSocket frame, message và RSocket payload

Một trong những lỗi cấu hình phổ biến là dùng một giới hạn kích thước cho mọi lớp. Trên đường WebSocket có nhiều đơn vị khác nhau:

| Đơn vị | Ý nghĩa |
|---|---|
| WebSocket frame | Đơn vị truyền trên WebSocket; có thể là text, binary, continuation hoặc control frame |
| WebSocket message | Một message logic; có thể được chia thành nhiều WebSocket frames |
| RSocket frame | Frame protocol mang SETUP, REQUEST, NEXT, ERROR, KEEPALIVE hoặc các loại khác |
| RSocket payload | Phần data và metadata mà interaction mang theo |
| Application object | DTO sau khi codec decode và validation |

Trong WebSocket transport, RSocket frames được vận chuyển bằng binary WebSocket messages. WebSocket có thể fragment một message thành nhiều frames ở tầng wire; WebSocket stack ghép chúng lại trước khi giao message cho tầng trên.

WebSocket fragmentation không đồng nghĩa RSocket payload fragmentation. Mỗi tầng có framing và giới hạn riêng.

Khác với TCP transport dùng length prefix để phân định RSocket frame, WebSocket transport dùng ranh giới WebSocket message. Không tự thêm TCP length prefix vào binary message khi tự viết transport adapter.

### 7.1. Ba nhóm giới hạn kích thước

**Giới hạn WebSocket frame** kiểm soát payload của một WebSocket frame. Server hoặc thư viện WebSocket có thể từ chối frame vượt giới hạn và đóng connection.

**Giới hạn WebSocket message** kiểm soát tổng dữ liệu sau khi ghép các fragment thành một message. Một message lớn có thể vượt giới hạn dù từng fragment nhỏ.

**Giới hạn RSocket/application** kiểm soát frame hoặc payload RSocket mà implementation chấp nhận, cùng kích thước DTO mà ứng dụng cho phép decode.

Không thể kết luận rằng tăng max WebSocket frame size sẽ giải quyết mọi lỗi payload quá lớn. Request có thể vẫn bị giới hạn bởi RSocket decoder, proxy, gateway hoặc business validation.

### 7.2. Giới hạn cần đặt ở nhiều lớp

| Lớp | Điều cần giới hạn |
|---|---|
| CDN / load balancer | Kích thước request, connection và thời gian xử lý |
| Reverse proxy | WebSocket frame/message theo khả năng implementation |
| WebSocket server | Maximum frame payload và tổng message nếu có cấu hình riêng |
| RSocket transport | Kích thước frame/payload inbound theo implementation |
| Codec | Kích thước object, nesting depth, string/collection limits |
| Application | Giới hạn field, file/chunk, số item và business constraints |

Đặt giới hạn ở lớp gần nguồn vào nhất có thể để từ chối sớm. Giới hạn application vẫn cần thiết vì payload hợp lệ về transport có thể chứa JSON rất sâu, collection rất lớn hoặc field không phù hợp với nghiệp vụ.

### 7.3. Cấu hình giới hạn trong Spring Boot

Spring Boot có property riêng cho WebSocket frame payload và RSocket fragmentation:

~~~yaml
spring:
  rsocket:
    server:
      spec:
        max-frame-payload-length: 64KB
      fragment-size: 60KB
~~~

Ý nghĩa:

- spring.rsocket.server.spec.max-frame-payload-length giới hạn payload của một WebSocket frame. Giá trị mặc định được tài liệu Spring Boot công bố là 65536 bytes.
- spring.rsocket.server.fragment-size đặt maximum transmission unit cho RSocket; frame lớn hơn ngưỡng này được chia thành các RSocket fragments.

Chọn RSocket fragment-size nhỏ hơn giới hạn WebSocket frame để chừa chỗ cho RSocket frame header và các overhead khác. Các giá trị 64KB và 60KB chỉ là ví dụ; hãy kiểm tra cách implementation đang dùng tính kích thước và chạy test biên. Nếu tăng fragment-size, cần xem lại max-frame-payload-length tương ứng.

Hai property không giới hạn tổng dung lượng một application message sau khi nhiều fragment được ghép lại. Vẫn cần giới hạn payload inbound, metadata và cấu trúc DTO ở các lớp tương ứng. Property max-frame-payload-length chỉ kiểm soát frame payload của WebSocket, không phải giới hạn tổng data mà business handler được phép xử lý.

Spring Boot cũng có các property spring.rsocket.server.spec.handle-ping và spring.rsocket.server.spec.compress. Chúng điều khiển xử lý WebSocket Ping frames và compression extension; chỉ bật compression khi đã đánh giá memory/CPU cost và giới hạn decompression của phiên bản Reactor Netty đang dùng.

Các property trong mục spec được công bố trong Spring Boot 3.2 trở lên. Với phiên bản cũ hơn, kiểm tra application-properties của đúng phiên bản và API WebSocket upgrade strategy tương ứng; không sao chép cấu hình mới vào bản cũ mà chưa xác minh.

## 8. Chọn kích thước frame và payload

Không có một giá trị tối ưu cho mọi ứng dụng. Hãy xác định:

- Payload lớn nhất của request/response bình thường.
- Kích thước metadata và header.
- Tần suất message và số connection đồng thời.
- Bộ nhớ cần để giữ bytes, decoded object và bản sao trong pipeline.
- Khả năng xử lý của proxy, gateway và client browser.
- Yêu cầu truyền file hoặc binary data.

Một payload 1 MiB không chỉ tiêu tốn 1 MiB RAM. Trong quá trình decode, ứng dụng có thể đồng thời giữ buffer gốc, object đã giải mã, bản sao khi map và buffer trong queue. Với hàng nghìn connection, memory amplification có thể đáng kể.

### 8.1. Ví dụ kiểm tra ngưỡng

Nếu policy cho phép data payload tối đa 256 KiB, hãy test:

| Kích thước | Kết quả mong đợi |
|---|---|
| 256 KiB - 1 byte | Được chấp nhận nếu các giới hạn khác cho phép |
| Đúng 256 KiB | Được chấp nhận theo định nghĩa inclusive |
| 256 KiB + 1 byte | Bị từ chối có kiểm soát |
| Metadata vượt giới hạn riêng | Bị từ chối |
| Nhiều field nhỏ nhưng tổng DTO lớn | Application validation từ chối |

Các con số trong ví dụ chỉ minh họa. Ghi rõ giới hạn áp dụng cho data bytes, metadata bytes hay tổng payload; đừng để tên cấu hình mơ hồ.

### 8.2. Binary transfer và chunking

Nếu cần truyền file lớn, cân nhắc chia thành chunk có ID, sequence number, checksum và giới hạn kích thước mỗi chunk. Không gửi một payload khổng lồ chỉ vì WebSocket stack cho phép.

Chunking giúp:

- Giới hạn memory mỗi interaction.
- Retry từng chunk.
- Theo dõi tiến độ.
- Kiểm tra thứ tự và checksum.
- Hủy transfer mà không phải giữ toàn bộ file trong heap.

Thiết kế chunk protocol cần có timeout, giới hạn số transfer đồng thời, cleanup khi client cancel và chính sách xóa dữ liệu tạm nếu connection mất giữa chừng.

## 9. WebSocket Ping/Pong và RSocket KEEPALIVE

Hai cơ chế heartbeat thường bị nhầm lẫn:

| Cơ chế | Tầng | Mục đích |
|---|---|---|
| WebSocket Ping/Pong | WebSocket control frames | Kiểm tra peer và giữ hoạt động ở tầng WebSocket |
| RSocket KEEPALIVE | RSocket protocol frame | Kiểm tra peer RSocket, phát hiện connection chết và hỗ trợ protocol lifecycle |

WebSocket Ping là control frame; peer WebSocket phải phản hồi Pong theo protocol. Browser WebSocket API không cho JavaScript trực tiếp gửi Ping control frame, nhưng browser stack tự xử lý Pong khi nhận Ping.

RSocket KEEPALIVE là RSocket frame được truyền bên trong WebSocket binary message. RSocket client/server library quản lý frame này. Trong RSocket protocol, KEEPALIVE có thể đặt cờ yêu cầu peer phản hồi; peer trả KEEPALIVE tương ứng khi cần.

WebSocket Pong không thay thế RSocket KEEPALIVE. Một peer có thể trả Pong thành công nhưng RSocket application đã không còn phản hồi; ngược lại RSocket KEEPALIVE vẫn hoạt động dù không dùng WebSocket Ping control frame.

### 9.1. Cấu hình RSocket keepalive

Ví dụ client Java:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(configurer ->
                configurer.keepAlive(
                        Duration.ofSeconds(20),
                        Duration.ofSeconds(60)))
        .websocket(URI.create(
                "wss://api.example.com/rsocket"));
~~~

Builder cấu hình connector mà RSocketRequester sử dụng. Interval là khoảng gửi KEEPALIVE; max lifetime là giới hạn thời gian không nhận KEEPALIVE trước khi connection bị xem là hết hạn.

Không đặt max lifetime bằng interval. Cần có khoảng dung sai cho scheduling delay, GC pause và jitter mạng. Nếu interval quá ngắn, heartbeat tạo tải không cần thiết; nếu quá dài, intermediary có thể đóng connection trước khi heartbeat tiếp theo đến.

### 9.2. KEEPALIVE có cờ RESPOND

Một KEEPALIVE request có thể yêu cầu peer phản hồi. Phản hồi này tạo traffic chiều ngược lại, hữu ích khi proxy có timeout đọc dữ liệu từ upstream server.

Không chỉ kiểm tra rằng client có gửi heartbeat. Hãy xác minh server có trả phản hồi khi protocol yêu cầu và response đi qua toàn bộ reverse proxy/load balancer.

## 10. Căn chỉnh idle timeout giữa các lớp

Một connection WebSocket có thể bị đóng bởi bất kỳ intermediary nào:

- Browser hoặc mobile OS tạm ngưng ứng dụng.
- Wi-Fi, NAT hoặc firewall xóa state của connection nhàn rỗi.
- CDN hoặc load balancer có idle timeout.
- Ingress/reverse proxy có read timeout hoặc send timeout.
- WebSocket server có idle policy.
- RSocket max lifetime phát hiện peer không còn gửi KEEPALIVE.

Hãy lập bảng timeout trước khi chọn keepalive:

| Thành phần | Timeout cần xác định |
|---|---|
| Browser/mobile | Background suspension, network transition |
| NAT/firewall | TCP/WebSocket idle expiration |
| CDN/load balancer | Idle connection timeout |
| Reverse proxy | Upstream read/write inactivity timeout |
| WebSocket server | Idle timeout hoặc ping policy |
| RSocket | Keepalive interval và max lifetime |
| Application | Session idle timeout và business subscription timeout |

### 10.1. Quy tắc căn chỉnh

1. Xác định idle timeout nhỏ nhất trên đường client-server.
2. Đặt heartbeat interval thấp hơn timeout đó với margin đáng kể.
3. Bảo đảm có traffic theo đúng chiều mà proxy đang đo.
4. Đặt RSocket max lifetime đủ lớn để chịu jitter nhưng nhỏ hơn thời gian phát hiện sự cố mà hệ thống chấp nhận.
5. Kiểm thử trong môi trường có cùng CDN, ingress và load balancer như production.

Ví dụ nếu intermediary đóng connection sau 60 giây không có dữ liệu, có thể bắt đầu thử interval khoảng 15 giây và theo dõi heartbeat round-trip. Đây chỉ là điểm xuất phát; cần xác minh timer thực tế và hướng traffic.

### 10.2. Read timeout và send timeout không giống nhau

Với Nginx:

- proxy_read_timeout là khoảng chờ giữa các lần đọc dữ liệu từ upstream server.
- proxy_send_timeout là khoảng chờ giữa các lần ghi dữ liệu đến upstream server.

Client gửi dữ liệu lên server có thể reset timeout theo chiều gửi nhưng không nhất thiết reset proxy_read_timeout. Nếu server không gửi gì về client trong thời gian dài, proxy có thể đóng connection dù client vẫn gửi traffic. RSocket KEEPALIVE response hoặc WebSocket server Ping có thể tạo traffic chiều server-to-client, nhưng phải kiểm tra cấu hình thực tế.

### 10.3. Timeout tuyệt đối và idle timeout

Idle timeout đóng connection sau một khoảng không có traffic. Absolute lifetime đóng connection sau tổng thời gian tồn tại, kể cả khi vẫn có traffic. Một số gateway áp dụng cả hai.

Heartbeat có thể giữ connection sống qua idle timeout nhưng không vượt qua absolute lifetime. Nếu nền tảng có absolute connection lifetime, client cần reconnect có kiểm soát và ứng dụng cần phục hồi subscription theo semantics đã chọn.

## 11. Close code và tín hiệu chẩn đoán

WebSocket close frame có thể mang mã trạng thái và lý do:

| Close code | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| 1000 | Normal closure | Ai chủ động đóng và vì sao |
| 1001 | Going away | Browser rời trang, server shutdown hoặc endpoint ngừng |
| 1002 | Protocol error | Frame hoặc handshake vi phạm protocol |
| 1003 | Unsupported data | Server không chấp nhận data type |
| 1008 | Policy violation | Origin, authorization hoặc policy |
| 1009 | Message too big | Frame/message vượt giới hạn |
| 1011 | Internal server error | Lỗi nội bộ server |
| 1006 | Abnormal closure quan sát cục bộ | Mất mạng hoặc đóng không có close frame |

Code 1006 là giá trị dành cho việc biểu diễn abnormal closure ở local API; không được gửi trong close frame trên wire. Nếu client báo 1006, kiểm tra log proxy/server và TCP reset thay vì tìm một frame 1006 từ peer.

Close reason có thể chứa dữ liệu do peer gửi. Không ghi nguyên văn nếu nó có thể chứa token, payload hoặc chuỗi không tin cậy; sanitize trước khi log.

## 12. Quan sát vận hành

Theo dõi handshake, connection và protocol riêng biệt:

| Metric/log | Dùng để phát hiện |
|---|---|
| WebSocket upgrade attempts | Lưu lượng kết nối |
| Upgrade success / status code | Tỷ lệ handshake thất bại |
| Active WebSocket connections | Connection đang mở |
| Close code và initiator | Nguyên nhân disconnect |
| WebSocket frame/message size | Payload bất thường |
| RSocket SETUP success/failure | Lỗi sau khi HTTP Upgrade |
| RSocket keepalive RTT/missed count | Peer chậm hoặc mất phản hồi |
| Connection age và idle duration | Disconnect theo chu kỳ |
| Request rate và active streams | Tải interaction |
| Payload-too-large count | Giới hạn frame/payload bị chạm |

Không dùng connection ID hoặc session ID làm metric label có cardinality cao. Đặt ID chi tiết trong structured log hoặc trace. Log nên có timestamp, path, upstream, status, close code, thời lượng và correlation ID nếu đã có.

### 12.1. Dấu hiệu theo chu kỳ

Nếu connection thường đóng sau khoảng thời gian gần như cố định, hãy so sánh thời điểm disconnect với:

- Idle timeout của load balancer.
- proxy_read_timeout/proxy_send_timeout.
- NAT/firewall timeout.
- RSocket max lifetime.
- Absolute connection lifetime của gateway.
- Background suspension của browser/mobile.

Một khoảng thời gian lặp lại thường là dấu hiệu của timer ở một lớp trung gian, không nhất thiết là bug trong handler.

## 13. Kiểm thử WebSocket Upgrade và giới hạn frame

Kiểm thử cần đi từ handshake đến interaction:

### 13.1. Handshake test

- Request đúng path trả 101.
- Thiếu Upgrade hoặc Connection header bị từ chối.
- Sec-WebSocket-Version không hỗ trợ trả lỗi phù hợp.
- Sai path trả 404.
- Origin không nằm trong allowlist bị từ chối.
- TLS certificate và hostname hợp lệ với WSS.
- Proxy chuyển tiếp Upgrade headers đúng.
- Subprotocol được thương lượng nếu contract yêu cầu.

### 13.2. RSocket SETUP test

- Sau 101, client gửi SETUP hợp lệ và nhận được connection.
- Data MIME type không được hỗ trợ bị từ chối.
- Authentication metadata sai bị từ chối theo policy.
- Route request-response hoạt động sau SETUP.
- Client/server đóng connection đúng khi SETUP thất bại.

### 13.3. Kích thước và fragmentation

- Message nhỏ hơn giới hạn được chấp nhận.
- Message đúng giới hạn được xử lý theo policy inclusive/exclusive.
- Message lớn hơn giới hạn bị từ chối có kiểm soát.
- Metadata lớn được kiểm tra riêng.
- WebSocket message bị fragment được ghép đúng.
- Binary data không bị biến đổi bởi proxy.
- Payload nhiều item không làm tăng buffer vô hạn.

Không chỉ test frame nhỏ và message lớn. Một message có thể gồm nhiều WebSocket frames; test cần xác minh giới hạn của cả frame và tổng message theo implementation đang chạy.

## 14. Kiểm thử idle timeout và keepalive

Nên có ít nhất các tình huống:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Connection idle nhưng KEEPALIVE hoạt động | Connection duy trì lâu hơn idle timeout |
| Peer trả KEEPALIVE response đúng hạn | Max lifetime không bị vượt |
| Ngừng gửi KEEPALIVE | Connection bị đóng sau ngưỡng max lifetime |
| WebSocket Ping không có Pong | WebSocket stack phát hiện peer không phản hồi |
| Server gửi RSocket KEEPALIVE response | Proxy read timeout được reset nếu response đi qua upstream |
| Browser chuyển background | Hành vi timer và reconnect được quan sát |
| Network đổi Wi-Fi sang mobile | Connection cũ đóng; client reconnect theo policy |
| Proxy idle timeout ngắn hơn client interval | Connection bị đóng; test phải phát hiện cấu hình lệch |
| Absolute lifetime hết hạn dù có heartbeat | Client reconnect có kiểm soát |

Integration test qua proxy hoặc môi trường staging có giá trị hơn chỉ test server trực tiếp, vì idle timeout thường nằm ở hạ tầng.

### 14.1. Không dùng sleep dài trong unit test

Unit test có thể dùng virtual time để kiểm tra logic retry hoặc timer trong application. Tuy nhiên, virtual time của Reactor không điều khiển timer bên trong browser, kernel, Netty event loop hoặc load balancer. Kiểm thử idle timeout của toàn đường mạng cần integration test với thời gian thực và timeout có kiểm soát.

## 15. Runbook chẩn đoán

Khi client không kết nối được:

1. Ghi lại URL, path, scheme ws/wss, HTTP status và response headers.
2. Kiểm tra Upgrade/Connection/Sec-WebSocket-Version ở edge access log.
3. Xác minh path rewrite và mapping path của Spring Boot.
4. Kiểm tra TLS, certificate, Origin và auth tại handshake.
5. Nếu có 101, kiểm tra RSocket SETUP và MIME types.
6. Nếu SETUP thành công, kiểm tra route, codec và application error.
7. Nếu connection đóng sau một khoảng idle, đối chiếu close code với timeout từng intermediary.
8. Nếu chỉ payload lớn thất bại, đo frame/message/payload size ở từng lớp.

Khi connection bị đóng theo chu kỳ:

1. Đo thời gian từ lúc handshake đến disconnect.
2. Đo thời gian từ message cuối cùng theo từng chiều.
3. Kiểm tra client có gửi RSocket KEEPALIVE không.
4. Kiểm tra server có trả KEEPALIVE response không.
5. Kiểm tra WebSocket Ping/Pong nếu đang bật.
6. Đối chiếu proxy read/send timeout và load balancer idle timeout.
7. Kiểm tra absolute connection lifetime.
8. Kiểm thử lại qua đúng đường production.

Khi gặp lỗi payload lớn:

1. Ghi data bytes, metadata bytes và tổng payload.
2. Xác định lỗi đến từ proxy, WebSocket frame/message limit, RSocket decoder hay application validator.
3. Kiểm tra close code 1009 hoặc error frame tương ứng.
4. Điều chỉnh giới hạn đồng bộ giữa client, edge và server.
5. Nếu payload thực sự lớn, thiết kế chunking thay vì chỉ tăng giới hạn.

## 16. Lỗi thường gặp

### Server trả 404 dù port mở

Port TCP reachable không chứng minh mapping path đúng. Kiểm tra path client, rewrite ở proxy và spring.rsocket.server.mapping-path.

### Proxy bỏ mất Upgrade headers

HTTP request đến được backend nhưng không được nâng cấp. Chuyển tiếp Upgrade và Connection trên hop HTTP/1.1.

### Coi 101 là RSocket đã sẵn sàng

WebSocket có thể mở nhưng SETUP thất bại do MIME type, metadata hoặc authentication. Quan sát cả hai giai đoạn.

### Chỉ tăng frame limit ở Netty

Proxy hoặc application vẫn có thể từ chối message lớn. Xác định lớp thực sự áp dụng giới hạn.

### Nhầm WebSocket frame với WebSocket message

Một message có thể được chia thành nhiều frames. Test riêng giới hạn frame và giới hạn message.

### Dùng WebSocket Ping thay cho RSocket KEEPALIVE

Ping/Pong kiểm tra WebSocket peer; KEEPALIVE kiểm tra RSocket peer và semantics protocol. Chọn cơ chế phù hợp hoặc dùng cả hai khi có lý do.

### Chỉ gửi heartbeat một chiều

Một số proxy đo timeout theo chiều đọc upstream. Bảo đảm có response hoặc server-originated traffic đi qua hướng đó.

### Cấu hình keepalive bằng đúng idle timeout

Scheduling delay và network jitter có thể khiến heartbeat đến muộn. Đặt interval thấp hơn đáng kể và kiểm thử.

### Nghĩ heartbeat vượt được absolute lifetime

Absolute timeout đóng connection dù vẫn có traffic. Cần reconnect có chủ đích.

### Dùng browser JavaScript để gửi WebSocket Ping

Browser WebSocket API không expose Ping control frame. Dùng RSocket KEEPALIVE hoặc cơ chế server-side phù hợp.

## 17. Checklist triển khai production

Trước khi đưa RSocket WebSocket vào production, hãy xác nhận:

1. Endpoint trả 101 với handshake HTTP/1.1 hợp lệ.
2. Mapping path khớp giữa client, proxy và Spring Boot.
3. Upgrade và Connection headers được proxy chuyển tiếp.
4. HTTP/2 Extended CONNECT chỉ được dùng khi toàn tuyến hỗ trợ.
5. Origin allowlist và TLS/WSS được cấu hình.
6. Authentication handshake và RSocket SETUP được kiểm thử riêng.
7. WebSocket frame và message limits được xác định.
8. RSocket/application payload limits được cấu hình riêng.
9. Codec và application validation giới hạn object/collection lớn.
10. Payload lớn có chiến lược chunking nếu cần.
11. WebSocket Ping/Pong và RSocket KEEPALIVE không bị nhầm lẫn.
12. Keepalive interval thấp hơn idle timeout nhỏ nhất với margin.
13. KEEPALIVE response đi qua đúng hướng proxy đang đo.
14. RSocket max lifetime và absolute connection lifetime có policy rõ.
15. Close code, handshake status, SETUP failure và payload-too-large được quan sát.
16. Integration tests chạy qua ingress/load balancer thực tế.
17. Browser background, mobile sleep và network transition được kiểm thử.
18. Reconnect không tạo subscription hoặc connection leak.

## 18. Tổng kết

RSocket qua WebSocket cần được vận hành như một chuỗi lớp giao thức. HTTP Upgrade phải trả 101; sau đó RSocket SETUP mới xác lập connection RSocket. Reverse proxy phải chuyển tiếp Upgrade headers và giữ kết nối; WebSocket frame/message limits cần được phân biệt với RSocket payload và application limits.

Idle disconnect cần được chẩn đoán theo từng intermediary. WebSocket Ping/Pong hoạt động ở tầng WebSocket, còn RSocket KEEPALIVE kiểm tra peer ở tầng RSocket. Căn chỉnh heartbeat interval với idle timeout nhỏ nhất, bảo đảm có traffic theo đúng chiều proxy đang đo và xử lý riêng absolute connection lifetime. Kết hợp handshake tests, frame boundary tests, idle integration tests và observability close code sẽ giúp phát hiện sớm lỗi triển khai trước khi chúng ảnh hưởng đến các stream realtime.

## Tài liệu tham khảo

- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Boot Common Application Properties — RSocket server spec](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Reactor Netty API — WebsocketServerSpec](https://projectreactor.io/docs/netty/release/api/reactor/netty/http/server/WebsocketServerSpec.html)
- [Spring Framework API — ReactorNettyRequestUpgradeStrategy](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/server/upgrade/ReactorNettyRequestUpgradeStrategy.html)
- [RSocket Protocol — Keepalive and Frame Format](https://rsocket.io/about/protocol/)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
- [RFC 8441 — Bootstrapping WebSockets with HTTP/2](https://www.rfc-editor.org/rfc/rfc8441)
- [Nginx Documentation — WebSocket proxying](https://nginx.org/en/docs/http/websocket.html)
