# Tác động của timeout, cân bằng tải và graceful shutdown tới kết nối dài

## 1. Vấn đề thực tế: kết nối đang mở không có nghĩa nó sẽ sống mãi

Một hệ thống Spring Boot phát sự kiện thời gian thực qua **Server-Sent Events (SSE)** hoặc **WebSocket**. Khi chạy local, client nhận dữ liệu liên tục. Nhưng sau khi triển khai sau NGINX, ingress hay cloud load balancer, kết nối tự ngắt sau một phút im lặng. Khi rolling deployment, một số client mất phiên, sự kiện bị lặp hoặc không được nhận. Khi scale từ hai lên bốn pods, số kết nối vẫn dồn ở các pods cũ. Đội vận hành đã bật `graceful shutdown` nhưng các WebSocket sống lâu vẫn rớt đúng lúc pod kết thúc.

Những hiện tượng đó có thể xảy ra **ngay cả khi Spring controller và business logic đều đúng**. Kết nối dài có nhiều vòng đời cùng lúc:

- Vòng đời TCP/TLS giữa các hop.
- Vòng đời HTTP request/response hoặc HTTP/2 stream.
- Vòng đời WebSocket sau khi HTTP Upgrade.
- Vòng đời proxy/LB backend connection và idle timeout.
- Vòng đời instance/pod cùng readiness, deregistration, draining và SIGTERM.
- Vòng đời subscription, subscriber và nguồn phát sự kiện trong ứng dụng.
- Vòng đời nghiệp vụ: client đã nhận đến event/command nào trước khi bị ngắt?

**Mục tiêu học tập**:
1. Phân biệt **idle timeout, request timeout, read timeout, connection lifetime, TCP keepalive** và heartbeat của ứng dụng.
2. Hiểu ảnh hưởng của NGINX, AWS ALB, ingress và các hop proxy lên SSE, WebSocket và HTTP/2.
3. Giải thích vì sao load balancer không tự phân bổ lại một WebSocket đang sống, và sticky session không thay thế shared state.
4. Hiểu đúng **Spring Boot graceful shutdown**, readiness, preStop, connection draining và giới hạn thời gian của Kubernetes.
5. Viết một demo **Spring Boot WebFlux Java 17+ chạy được**: SSE streaming, trạng thái readiness và chủ động drain kết nối.
6. Thiết kế reconnect có backoff, resume/replay với `Last-Event-ID` hoặc sequence/ack, xử lý duplicate/gap.
7. Kiểm tra bằng `curl`, log/metrics, thử nghiệm timeouts và rollout trước production.

> **Phiên bản:** Phần thực hành dùng Spring Boot **3.5.x**, Java 17+, `spring-boot-starter-webflux`, Reactor Netty và Spring Framework 6.2. Tài liệu Boot 3.5 ghi **graceful shutdown được bật mặc định** cho các embedded web servers được hỗ trợ; YAML vẫn khai báo `server.shutdown: graceful` để ý định dễ quan sát. Ở các phiên bản Boot cũ, mặc định có thể khác; không áp dụng cùng một nhận xét về default cho mọi phiên bản.

## 2. “Kết nối dài” có nhiều loại khác nhau

| Kiểu | Cơ chế | Client/server trao đổi thế nào? | Điểm cần lưu ý |
|---|---|---|---|
| HTTP/1.1 keep-alive | Tái sử dụng TCP connection cho nhiều request | Các request/response riêng biệt qua một connection | Idle keep-alive timeout không phải tuổi thọ của một streaming response |
| HTTP/2 | Nhiều **streams** cùng chia sẻ một connection | Multiplex request/response, có PING và GOAWAY | Một connection đóng có thể ảnh hưởng nhiều streams đồng thời |
| SSE | Một HTTP response `text/event-stream` mở lâu | Server → client, từng event/heartbeat | Proxy buffering/idle timeout; client có thể reconnect |
| WebSocket | Handshake rồi nâng cấp sang giao thức hai chiều | Client ↔ server qua frames, ping/pong/close | Connection gắn với một backend; state cần phục hồi sau reconnect |
| Long polling | Request chờ đến khi có dữ liệu/timeout, sau đó gửi request khác | Chuỗi requests dài có chủ đích | Read/request timeout và request rate; không hẳn một socket tồn tại mãi |
| HTTP streaming/NDJSON | Body phát từng phần | Một response dài, có thể trên HTTP/1.1 hoặc HTTP/2 | Flush/buffering, demand, cancellation, timeout |

Một luồng SSE có thể đi qua HTTP/2 ở phía browser → CDN, nhưng CDN lại dùng HTTP/1.1 tới backend. Vì vậy **loại giao thức ở từng hop có thể khác nhau**. Việc “bật HTTP/2 ở browser” không chứng minh backend cũng đang sử dụng HTTP/2.

**SSE không phải WebSocket.** SSE là one-way server-to-client dùng chuẩn EventSource; browser EventSource có cơ chế tự reconnect. WebSocket hỗ trợ truyền hai chiều, có giao thức ping/pong và close codes riêng. Kết nối dài nào cũng cần xử lý mạng đứt hoặc triển khai lại backend.

## 3. Một kết nối đi qua những tầng nào?

~~~text
Browser / mobile app / CLI
     |
     | TLS / HTTP/2 / WebSocket / SSE
     v
CDN hoặc edge proxy
     |
     | Connection và idle/lifetime riêng
     v
Cloud LB / ingress / reverse proxy
     |
     | Backend keep-alive / Upgrade / HTTP stream
     v
Spring Boot instance A
     |
     +-- Servlet async / WebFlux subscription / WebSocket session
     |
     +-- DB / Redis / event broker / message bus
~~~

Trong mỗi hop có thể có:
- Deadline cho **kết nối mới** như TCP connect/TLS handshake.
- Idle timeout khi **không có bytes** được gửi/nhận một thời gian.
- Read/write timeout giữa các hoạt động I/O.
- Request duration hoặc upstream response timeout.
- Maximum connection lifetime, kể cả khi có traffic.
- Chính sách queue/connection pool/circuit breaker.
- Deregistration/draining timeout khi instance được gỡ khỏi LB.

Kết nối client nhìn thấy thường **không phải một TCP socket xuyên từ browser đến JVM**: proxy kết thúc một socket và mở socket khác. Gửi heartbeat từ ứng dụng chỉ hữu ích nếu bytes được **flush qua tất cả các hop** mà cần giữ hoạt động.

### Quy tắc đơn giản về điểm gây ngắt

Giả sử:
- Client → ALB idle timeout: 60 giây.
- ALB → NGINX hoặc proxy đọc response timeout: 75 giây.
- Backend phát dữ liệu 120 giây một lần.

Đường đi có thể bị ngắt **trước khi backend phát message kế tiếp**. Không có ý nghĩa nếu chỉ tăng một timeout ở Spring mà quên hop có ngưỡng nhỏ nhất.

Đừng coi các con số trên là bộ defaults phổ quát. Chúng là ví dụ có thể kiểm chứng với NGINX và AWS ALB; **cấu hình thực tế của phiên bản LB/proxy đang dùng phải được tra lại**.

## 4. Bảng phân biệt các loại timeout

| Tên/cơ chế | Đo điều gì? | Có phải thời gian tối đa của cả kết nối dài? |
|---|---|---|
| **Connect timeout** | Thời gian thiết lập TCP/TLS hoặc lấy connection tùy client | Không |
| **Read timeout / proxy_read_timeout** | Khoảng thời gian không có dữ liệu đọc được từ upstream giữa các lần đọc | Thường không; stream đều đặn có thể tồn tại rất lâu |
| **Write/send timeout** | Thời gian không gửi được dữ liệu tới peer | Không, nhưng client chậm có thể làm disconnect |
| **Idle timeout** | Khoảng im lặng trên một connection/hop | Không phải absolute lifetime |
| **HTTP request/async timeout** | Thời gian xử lý một request hay async request theo component | Có thể cắt một SSE response dù bytes còn được gửi, tùy stack |
| **Connection max lifetime / keepalive duration** | Tuổi tối đa của connection kể từ khi thiết lập | Có; có thể đóng dù vẫn có hoạt động |
| **LB deregistration delay** | Thời gian đợi target ngừng phục vụ và hoàn tất traffic cũ | Không phải idle timeout |
| **Graceful shutdown timeout** | Ngân sách chờ in-flight work hoàn thành khi dừng ứng dụng | Có giới hạn cho quá trình stop, không tự đảm bảo streams vô hạn |
| **TCP keepalive** | Probe ở tầng TCP/OS sau thời gian không hoạt động | Không thay SSE heartbeat/WebSocket ping hay mọi LB idle timer |
| **Application heartbeat** | Message/comment/ping định kỳ do giao thức/ứng dụng gửi | Có thể giữ idle timer, nhưng không vô hiệu hóa maximum lifetime |

**Quan trọng:** request timeout của Spring MVC async, read timeout của NGINX và client HTTP response timeout **không phải cùng một đồng hồ**. Cấu hình `server.tomcat.connection-timeout` chẳng hạn liên quan hành vi nhận dữ liệu kết nối/HTTP request của Tomcat, không nên coi là “giới hạn SSE response” trong mọi trường hợp.

Đặt tên rõ trong tài liệu vận hành: `client_connect_timeout`, `proxy_upstream_read_timeout`, `lb_idle_timeout`, `sse_heartbeat_interval`, `app_grace_period`. Tên mơ hồ như “timeout=60s” dễ gây hiểu nhầm và tăng rủi ro sửa nhầm tầng.

## 5. Idle timeout và heartbeat: vì sao cứ 60 giây lại đứt?

Giả sử NGINX đang proxy WebSocket. Tài liệu NGINX mô tả `proxy_read_timeout` mặc định là **60 giây** và giới hạn này đo **khoảng cách giữa hai lần đọc từ upstream**, không phải tổng thời gian đọc hết response. Với WebSocket, NGINX cũng lưu ý rằng nếu upstream không phát dữ liệu trong khoảng này, kết nối có thể bị đóng; WebSocket ping frame định kỳ từ server có thể làm sống kết nối.

Tương tự, AWS Application Load Balancer có **connection idle timeout mặc định 60 giây** trong tài liệu hiện tại. Khi không có traffic đáp ứng cơ chế của ALB, kết nối client hoặc target có thể bị đóng. ALB có một cấu hình khác gọi **HTTP client keepalive duration**, mặc định **3600 giây** trong tài liệu, đo tuổi thọ từ lúc kết nối được tạo và **không reset** khi traffic tiếp tục.

### Idle timeout khác maximum connection age

~~~text
Kết nối mở lúc T0
  |
  +-- cứ mỗi 20 giây có heartbeat → reset idle time (nếu hop nhận bytes)
  |
  +-- đến tuổi connection tối đa của LB → có thể bị yêu cầu đóng
~~~

Do đó heartbeat có thể cứu một kết nối khỏi **idle timeout**, nhưng không bảo đảm kết nối bất tử. Client phải sẵn sàng reconnect sau maximum age, pod restart, proxy upgrade, lỗi mạng hoặc server shutdown.

### Chọn heartbeat interval H

Đặt H **nhỏ hơn rõ rệt** so với **idle timeout nhỏ nhất** trong các hop có liên quan, đồng thời chừa khoảng cho jitter, GC pause, scheduler delay, network buffering và thời gian flush.

Ví dụ thiết kế **để thử nghiệm**, không phải con số chuẩn:
- SSE heartbeat hoặc event mỗi **20s**.
- ALB idle timeout **60s**.
- NGINX `proxy_read_timeout: 75s`.

H=20s chừa khoảng so với cả 60s và 75s, **nếu heartbeat thực sự đi qua những hop đó**. Nếu proxy_buffering giữ lại SSE comments, heartbeat từ Java có thể chưa đi đến client/LB như mong đợi; phải kiểm tra bytes ở từng hop.

Đừng đặt H=59s chỉ vì idle=60s: jitter nhỏ đã đủ làm connection rớt. Nhưng cũng không gửi mỗi 100ms cho hàng trăm nghìn clients nếu không có yêu cầu: tốn network, CPU, wakeups và chi phí.

## 6. Heartbeat đúng giao thức: SSE, WebSocket và HTTP/2

### SSE: event hoặc comment heartbeat

SSE sử dụng `Content-Type: text/event-stream`. Một message có thể là:

~~~text
event: price
id: 194
data: {"sku":"SKU-1","price":120}

~~~

Dòng trống kết thúc một SSE event. Một dòng bắt đầu bằng dấu `:` là **comment**; client EventSource không phát callback nghiệp vụ cho comment nhưng bytes của nó có thể giữ hoạt động kết nối khi được flush:

~~~text
: heartbeat

~~~

Trong Spring WebFlux có thể sinh comment qua:

~~~java
// Fragment khi đã có reactive SSE pipeline.
Flux<ServerSentEvent<String>> heartbeats =
    Flux.interval(Duration.ofSeconds(20))
        .map(n -> ServerSentEvent.<String>builder()
            .comment("heartbeat")
            .build());
~~~

Đoạn này chỉ là fragment; imports `Flux`, `ServerSentEvent`, `Duration` cần nằm trong service/controller. Khi merge heartbeat với business events, cần quản lý ordering/cursor và kiểm tra serialization, buffering, cancellation. **Heartbeat comment không nên làm thay đổi `Last-Event-ID` của business event.**

### WebSocket: ping/pong và application-level heartbeat

WebSocket có **protocol PING/PONG control frames** theo RFC 6455. Server/framework có thể gửi ping để nhận pong, kiểm tra peer và giữ một số proxy idle timers. Browser JavaScript `WebSocket` API **không cho ứng dụng tự phát WebSocket protocol PING frames** như một WebSocket server library; nếu cần từ frontend, có thể dùng thông điệp ứng dụng `{"type":"ping"}` và xác nhận `pong` riêng.

Protocol ping/pong và application message heartbeat không hoàn toàn tương đương. Tầng proxy/LB có thể quan sát traffic ở mức bytes; nhưng không nên mặc định mọi L7 gateway hiểu/cộng mọi loại ping vào idle timer giống nhau.

### HTTP/2: PING và GOAWAY

HTTP/2 có **PING frame** để đo round-trip hoặc kiểm tra idle connection và **GOAWAY frame** để ngăn tạo streams mới khi đóng connection. Tuy nhiên **AWS ALB tuyên bố HTTP/2 PING frames không reset ALB connection idle timeout**. Do đó client gửi HTTP/2 PING định kỳ chưa đủ để bảo đảm stream sống qua ALB. Cần dữ liệu thực sự mà LB tính là hoạt động và kiểm tra riêng theo nhà cung cấp.

HTTP/2 GOAWAY là phần của **connection shutdown**, không phải tín hiệu ứng dụng đã lưu hết message nghiệp vụ. Một SSE stream trên HTTP/2 vẫn có thể bị cắt khi underlying connection bị đóng.

## 7. Cấu hình NGINX cho SSE: tránh buffering và idle read timeout

Cấu hình **fragment** dưới đây giả định đã có DNS/backend `spring-runtime:8080` và một `server` NGINX hợp lệ; không phải file NGINX hoàn chỉnh để copy thẳng vào production:

~~~nginx
location /events {
    proxy_pass http://spring-runtime:8080;

    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

    # Không gom SSE chunks vào buffer trước khi đẩy cho client.
    proxy_buffering off;

    # Khoảng chờ GIỮA các lần đọc dữ liệu upstream.
    proxy_read_timeout 75s;
}
~~~

Giải thích:
- `proxy_buffering off` giúp dữ liệu streaming được chuyển tiếp ngay thay vì đợi buffers đầy. NGINX mặc định bật proxy buffering; chỉ thay đổi tại các routes cần streaming để không làm giảm hiệu quả proxy cho toàn bộ ứng dụng.
- `proxy_read_timeout 75s` là khoảng trống giữa các lần đọc từ upstream; không có nghĩa “SSE chỉ được sống tối đa 75s”.
- `proxy_http_version 1.1` minh họa request lên upstream trong nhiều triển khai, đặc biệt hữu ích khi có Upgrade; default thay đổi giữa các phiên bản NGINX nên đọc tài liệu bản đang dùng.
- `X-Forwarded-*` cần được Spring Boot chỉ tin khi request đến từ proxy tin cậy; không blindly trust headers do client trực tiếp gửi.

Nếu response có `X-Accel-Buffering: no`, NGINX có thể tắt response buffering cho response đó khi header không bị cấu hình bỏ qua. Cần **kiểm chứng** cấu hình proxy và không trông đợi một header tự sửa mọi CDN.

**Không thêm `Connection: keep-alive` bừa vào SSE response** và không dùng nó như “heartbeat”. HTTP/1.1 keep-alive tái sử dụng socket, không bảo đảm proxy nhận bytes định kỳ. Với HTTP/2, connection-specific headers như `Connection` có quy tắc riêng và không được dùng kiểu HTTP/1.1.

## 8. NGINX cho WebSocket: phải chuyển Upgrade đúng cách

WebSocket thường bắt đầu bằng HTTP/1.1 Upgrade handshake. Các hop reverse proxy cần chuyển các header hop-by-hop phù hợp. NGINX có mẫu chính thức:

~~~nginx
# Đặt trong context http, ngoài server block.
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

# Bên trong server/location:
location /ws/ {
    proxy_pass http://spring-runtime:8080;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $host;
    proxy_read_timeout 75s;
}
~~~

Đây là **config fragment** gồm hai vị trí đặt cấu hình; phải đặt `map` đúng context `http`, không copy nó vào `location`. Với các phiên bản NGINX khác nhau, defaults thay đổi; đặt explicit ở đây để minh họa cơ chế HTTP/1.1 Upgrade.

Nếu upstream không gửi bất kỳ frame nào quá `proxy_read_timeout`, WebSocket có thể bị NGINX đóng ngay cả khi TCP socket từ phía client tưởng vẫn mở. Dùng ping/pong phù hợp và test end-to-end.

Không dùng `proxy_buffering off` như một giải pháp duy nhất cho WebSocket handshake sai; đây là **hai vấn đề riêng**: chuyển Upgrade đúng và duy trì connection sau upgrade.

## 9. Cloud load balancer: ít nhất ba đồng hồ dễ nhầm

Ví dụ **AWS Application Load Balancer** theo tài liệu:
1. **Connection idle timeout:** mặc định 60s; đóng nếu connection im lặng theo cơ chế của ALB.
2. **HTTP client keepalive duration:** mặc định 3600s; là tuổi thọ client connection, không reset liên tục theo traffic. Khi hết thời gian, ALB có cơ chế đóng phù hợp với HTTP version, có thể dùng `GOAWAY` cho HTTP/2.
3. **Target deregistration delay:** thuộc **target group**, điều khiển connection draining khi target bị loại. Không phải cùng property với idle timeout hoặc client keepalive.

Các defaults là mô tả tài liệu tại thời điểm biên soạn, **không phải phép đo cấu hình tài khoản của bạn**. Trên ALB, các giá trị có thể đã được thay đổi bởi hạ tầng, Terraform/CloudFormation hay console.

### Hai hop có thể có timeout khác nhau

~~~text
Browser --[ALB client connection]--> ALB
                                      |
                                      +--[ALB target connection]--> Pod
~~~

Khi browser reconnect hoặc ALB chuyển target, **socket mới** có thể đến pod khác. Ngay cả khi browser có cookie session, nó không có nghĩa WebSocket cũ được chuyển sang pod mới.

Nếu upstream Boot đóng kết nối đột ngột trong khi ALB vẫn nghĩ nó có thể tái sử dụng, ALB có thể trả lỗi `502 Bad Gateway`. Việc phối hợp idle/keepalive policy và graceful close giúp giảm sự cố nhưng không xóa toàn bộ race condition.

## 10. Load balancing: một WebSocket đã được chọn backend thì không tự chuyển

Giả sử có hai pods:

~~~text
                  +--> Pod A: 8.000 WebSocket connections
Client -> LB -----|
                  +--> Pod B: 2.000 WebSocket connections
~~~

Sau khi scale thêm Pod C, Pod D, **những sockets đang mở trên Pod A/B vẫn gắn với upstream hiện tại**; LB thông thường chỉ chọn backend khi một connection/request mới được tạo. Nó không thể “di chuyển một TCP/WebSocket connection đang sống” theo cách chuyển một HTTP request độc lập.

Hệ quả:
- Round-robin cho **new handshakes** không bảo đảm phân phối đều số **active connections**.
- Một lần scale-out có thể không làm nhẹ các pods đang giữ connection ngay tức khắc.
- Deploy/scale-in Pod A buộc các clients đang ở A reconnect nếu không có protocol migration chuyên biệt.
- Load-balancer weights hoặc CPU-based autoscaling có thể không phản ánh số sockets đang hoạt động.
- Persistent connection khiến rolling update chậm hoặc phải cắt connection sau grace deadline.

Nên quan sát **active connection count per instance**, lưu lượng messages/sec, memory/socket, CPU, event-loop lag và số clients reconnect đồng thời; không chỉ RPS.

### Sticky sessions có phải giải pháp?

**Session affinity** (cookie/hash/source-IP) có thể giúp client mới tiếp tục route tới cùng pod trong một số cấu hình, nhưng:
- Socket đang mở đã gắn với backend, không cần sticky để tiếp tục tồn tại.
- Khi pod bị loại/không còn healthy, sticky không giữ pod sống.
- Client có thể đổi IP, cookie hết hạn, LB ingress có policy riêng.
- Sticky che giấu việc state còn nằm local và làm failover khó khăn.
- Reconnect tới pod khác vẫn cần khôi phục state/cursor.

Nếu WebSocket session chứa subscription list, topic membership hoặc quyền truy cập trong RAM, **hãy thiết kế khôi phục state**. Redis/pub-sub, broker, durable event log, database hoặc external session store có thể phù hợp tùy loại state; không coi sticky session là một message bus.

## 11. Shared state và thứ tự sự kiện sau reconnect

Sự cố phổ biến:

~~~text
T1 Pod A phát event #100
T2 Client nhận #100 rồi mất WebSocket
T3 Event #101 được phát khi client đang offline
T4 Client reconnect và được LB đưa tới Pod B
T5 Pod B bắt đầu từ event #102
=> Client bị mất #101 nếu không có replay/cursor
~~~

Cũng có thể xảy ra:
- Pod B replay lại #100 và client xử lý trùng.
- Hai publishers/consumers có thứ tự khác nhau.
- Client gửi lại command vì không thấy acknowledgement; server áp dụng trùng side effect.
- Khi NGINX/LB timeout, close event không tới kịp client và state chuyển sang “unknown”.

### SSE và Last-Event-ID

SSE cho phép event có trường `id:`:

~~~text
id: 101
event: update
data: {"version":101}

~~~

Browser `EventSource` có thể gửi `Last-Event-ID` khi reconnect. **Nhưng header/cursor này không tự làm Spring Boot replay data**. Server phải:
1. Gắn event IDs bền, có nghĩa trong stream.
2. Lưu event log/offset đủ lâu.
3. Đọc `Last-Event-ID` hoặc cursor theo contract.
4. Replay events sau offset đã xác nhận và sau đó chuyển sang live stream mà không tạo gap giữa hai bước.
5. Có policy khi cursor quá cũ, log bị truncate hoặc access permissions thay đổi.

Nếu stream chỉ dùng `Flux.interval` và mỗi connection đánh số từ 0, **nó không đủ để resume**. Ví dụ thực hành của bài này cố ý **không gắn event ID**, để không tạo cảm giác giả rằng đã có event replay.

### WebSocket cần protocol riêng

WebSocket không có `Last-Event-ID` tự động. Ứng dụng có thể trao đổi:

~~~json
{"type":"subscribe","topic":"orders","afterSequence":101}
~~~

Server xác minh authorization, replay từ `afterSequence` rồi phát live events. Client dedupe theo event ID và xác nhận offset đã xử lý. Cần tránh race giữa “replay đến hiện tại” và “subscribe live”; dùng transactional cursor/broker semantics nếu nghiệp vụ quan trọng.

Khi client gửi lệnh có side effect (ví dụ thanh toán), việc mất WebSocket sau khi gửi **không chứng minh lệnh chưa được xử lý**. Dùng command ID/idempotency key và tra operation status; không auto-resend command không lũy đẳng bằng key mới.

## 12. Graceful shutdown của Spring Boot 3.5 thực sự bảo đảm gì?

Theo tài liệu **Spring Boot 3.5**:
- Graceful shutdown **đã được bật mặc định** với embedded Tomcat, Jetty, Reactor Netty và Undertow được tài liệu đó liệt kê, cho cả Servlet và reactive applications.
- Nó tham gia lúc đóng `ApplicationContext`, trong một phase sớm của `SmartLifecycle` stop.
- Trong grace period, existing requests **được cho cơ hội hoàn tất**, còn requests mới không được nhận theo policy của server.
- Thời gian chờ được cấu hình bằng `spring.lifecycle.timeout-per-shutdown-phase`, ví dụ `30s`.
- Cách từ chối request mới khác theo server: Tomcat/Jetty/Reactor Netty có thể dừng nhận ở network layer; Undertow trong tài liệu Boot 3.5 có thể đáp 503.
- Kết nối persistent có thể làm hành vi dừng nhận request mới khác kỳ vọng trên từng server.

Cấu hình rõ ràng:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

`server.shutdown: graceful` nhấn mạnh chính sách đã là default của Boot 3.5; `immediate` có thể tắt grace nếu muốn, nhưng **không phải lựa chọn tốt cho dịch vụ giữ state/stream dài**.

### Tại sao graceful shutdown chưa đủ với WebSocket/SSE vô hạn?

Một SSE `Flux.interval(...)` không tự hoàn tất khi thời gian đến 30s, trừ khi stream bị cancel hoặc app có logic dừng. WebSocket cũng có thể chờ message mãi. Nếu shutdown chờ in-flight requests hoàn thành nhưng streams không kết thúc trước deadline, quá trình dừng có thể phải đóng chúng sau khi hết grace.

**Graceful shutdown không phải live connection migration**, và **không bảo đảm 100% event đã giao đến client trước khi process tắt**. Nếu nghiệp vụ cần không mất sự kiện, phải có external event store, client cursor/ack và replay/reconciliation.

Không nghĩ rằng tăng grace period từ 30s thành vài giờ là cách duy nhất để giữ socket: rollout có thể bị kẹt, pod bị Kubernetes force kill khi hết termination grace hoặc công cụ triển khai timeout.

## 13. Connection draining phải bắt đầu trước SIGTERM khi cần

Đối với hệ thống có long-lived connections, nên tách hai giai đoạn:

**Giai đoạn A — ứng dụng chủ động drain:**
1. Đánh dấu instance `NOT_READY` trước khi ngừng process.
2. Chờ thời gian cần thiết để thay đổi readiness/endpoint/LB target propagation.
3. Không nhận **new business streams/handshakes**.
4. Gửi tín hiệu application-level “server draining” hoặc close WebSocket code `1001 Going Away` khi thích hợp.
5. Đóng dần SSE/WS streams đã nhận và để clients reconnect qua LB.
6. Persist cursor/checkpoint và hoàn tất những operation đang chạy theo deadline.

**Giai đoạn B — platform stop:**
7. Platform gửi `SIGTERM`.
8. Spring Boot graceful shutdown dừng nhận request mới, chờ in-flight requests trong grace.
9. Sau thời hạn, platform có thể buộc terminate process.
10. Client reconnect tới instance healthy, khôi phục subscription state, event cursor.

Không phải framework tự thực hiện đầy đủ bước 1–6. **Phần drain ứng dụng là trách nhiệm của hệ thống** nếu cần bảo đảm behavior đối với streams vô hạn.

### Không lẫn readiness và liveness

- **Readiness**: instance có nên nhận **new traffic** không?
- **Liveness**: process có ở trạng thái cần bị restart không?
- **Startup probe**: ứng dụng cần thời gian khởi động dài đến đâu?

Khi drain, readiness nên chuyển sang false, trong khi liveness vẫn có thể true cho đến lúc shutdown. Nếu lấy readiness false làm liveness false, Kubernetes có thể restart instance **quá sớm**, cắt những connections đang drain.

Spring Boot Actuator hỗ trợ readiness/liveness health groups qua `ApplicationAvailability`. Trong Kubernetes, các endpoint như `/actuator/health/readiness` và `/actuator/health/liveness` thường được sử dụng khi Actuator và probes được cấu hình. Nếu management chạy port riêng, lưu ý probe có thể không phản ánh hoàn toàn web server port chính; có thể dùng `management.endpoint.health.probes.add-additional-paths=true` theo tài liệu Boot.

## 14. Kubernetes terminationGracePeriodSeconds: ngân sách bao trùm cả preStop

Một ví dụ quy trình pod deletion:

~~~text
Pod nhận yêu cầu terminate
   |
   +-- Kubernetes đánh dấu endpoint terminating, cập nhật LB/endpoints
   +-- preStop hook (nếu khai báo và container còn chạy)
   |     +-- app chuyển readiness/draining
   |     +-- chờ propagation / thông báo clients
   |
   +-- SIGTERM tới process
   |     +-- Spring Boot graceful shutdown
   |
   +-- Pod hết termination grace nếu chưa hoàn tất
         +-- process có thể bị kill cưỡng bức
~~~

Các hoạt động cập nhật endpoints, hooks và routing có thể **chồng lấn theo thời gian**; đây là sơ đồ ý tưởng, không phải thứ tự chính xác được bảo đảm trong mọi cluster/ingress.

**`terminationGracePeriodSeconds` là ngân sách tổng** cho quá trình termination của Pod, không phải “preStop được N giây rồi Spring Boot nhận thêm N giây khác” theo mặc định. Nếu preStop mất 15s, ứng dụng muốn graceful 30s và còn propagation delay, ngân sách 30s tổng cộng rất dễ thiếu. Hãy phối hợp deadlines sao cho platform **không kill** ứng dụng trước khi quá trình draining có cơ hội kết thúc.

### Kubernetes YAML fragment

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: runtime
      image: example/runtime:demo
      ports:
        - containerPort: 8080
      readinessProbe:
        httpGet:
          path: /ready
          port: 8080
        periodSeconds: 2
        failureThreshold: 1
      livenessProbe:
        httpGet:
          path: /live
          port: 8080
~~~

Đây là **PodSpec fragment**, không phải một Deployment hoàn chỉnh. Demo mục 15 có `/ready` nhưng **không có `/live`**; nếu dùng fragment với demo, phải triển khai liveness endpoint riêng hoặc đổi probe sang một endpoint liveness đã có. **Không copy nguyên fragment để deploy** mà chưa bổ sung image thật, security, resources, liveness và termination hooks. Production thường dùng các Actuator probes chính thức.

Nếu có `preStop` gọi drain endpoint, endpoint đó cần được bảo vệ khỏi public traffic hoặc chỉ truy cập từ môi trường control plane phù hợp. **Không mở một endpoint “tắt mọi client” ra Internet**.

## 15. Ví dụ runnable: WebFlux SSE và ứng dụng chủ động drain streams

Ví dụ sau tạo một ứng dụng duy nhất:
- `GET /events` giữ SSE connection lâu, gửi một event `tick` mỗi 2 giây.
- `GET /ready` trả **200 READY** khi có thể nhận stream mới và **503 DRAINING** khi đang drain.
- `GET /status` trả JSON về tình trạng draining và số stream đang theo dõi.
- `POST /demo/drain` bật cờ draining, phát tín hiệu khiến **các SSE streams đang mở hoàn tất**.
- Kể từ đó `GET /events` mới bị từ chối với 503. Muốn thử lại từ trạng thái mới cần **restart app demo**.

Đây là một **minh họa vận hành local**, không phải production WebSocket gateway. Điểm quan trọng là việc **đóng có kiểm soát ứng dụng** thay vì chờ process kill.

### 15.1. Tạo dự án

Trong Spring Initializr, chọn:
- Spring Boot **3.5.x**, Java 17+, Gradle.
- Dependency **Spring Reactive Web** (`spring-boot-starter-webflux`).
- Không thêm starter MVC để tránh Boot chọn Servlet stack.

Trong project Boot 3.5 đã có Gradle plugin và dependency management, phần dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Đây chỉ là fragment, không phải toàn bộ `build.gradle`.

### 15.2. Java source code đầy đủ

Tạo file `src/main/java/demo/streams/StreamLifecycleApplication.java`:

~~~java
package demo.streams;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@SpringBootApplication
@RestController
public class StreamLifecycleApplication {

    private final AtomicBoolean draining = new AtomicBoolean(false);
    private final AtomicInteger activeStreams = new AtomicInteger(0);
    private final Sinks.One<String> drainSignal = Sinks.one();

    public static void main(String[] args) {
        SpringApplication.run(StreamLifecycleApplication.class, args);
    }

    @GetMapping(value = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events(
            ServerHttpResponse response) {

        response.getHeaders().setCacheControl("no-store");

        // Gợi ý NGINX không buffer response SSE, nếu cấu hình cho phép.
        response.getHeaders().set("X-Accel-Buffering", "no");

        return Flux.defer(() -> {
            if (draining.get()) {
                return Flux.<ServerSentEvent<String>>error(
                    new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE, "draining")
                );
            }

            activeStreams.incrementAndGet();

            return Flux.interval(
                    Duration.ZERO, Duration.ofSeconds(2))
                .map(n -> ServerSentEvent.<String>builder()
                    .event("tick")
                    .data("tick-" + n)
                    .build())
                .takeUntilOther(drainSignal.asMono())
                .doFinally(signal -> activeStreams.decrementAndGet());
        });
    }

    @GetMapping("/ready")
    public ResponseEntity<String> ready() {
        if (draining.get()) {
            return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body("DRAINING");
        }
        return ResponseEntity.ok("READY");
    }

    @GetMapping("/status")
    public Map<String, Object> status() {
        return Map.of(
            "draining", draining.get(),
            "activeStreams", activeStreams.get()
        );
    }

    // CHỈ dùng local demo, tuyệt đối không public không auth.
    @PostMapping("/demo/drain")
    public Map<String, String> drain() {
        if (draining.compareAndSet(false, true)) {
            drainSignal.tryEmitValue("drain");
        }
        return Map.of("state", "draining");
    }
}
~~~

#### Vì sao demo này không block event loop?

- `Flux.interval(...)` tạo events định kỳ; handler không gọi `Thread.sleep`.
- `Flux.defer(...)` thực thi kiểm tra draining khi một client **subscribe** thật sự, không quá sớm khi controller đang tạo publisher.
- `Sinks.One<String>` truyền một tín hiệu drain có thể được subscribers quan sát, kể cả các subscriptions bắt đầu sau khi sink đã có kết quả.
- `takeUntilOther(drainSignal.asMono())` làm stream hoàn tất khi nhận tín hiệu drain.
- `doFinally(...)` giảm counter cho cả completion, error hoặc cancellation.
- `AtomicBoolean/AtomicInteger` chỉ giữ trạng thái nhanh trong RAM của demo, không thực hiện network/database I/O đồng bộ.

Còn hai vấn đề **không được demo giải quyết**: authentication cho management/drain endpoint và replay/persistence của events. Production cần thiết kế bổ sung.

#### Tại sao không trả 200 rồi thông báo “tất cả client đã reconnect”?

Sau khi `drain` được gọi, streams hiện tại kết thúc và `activeStreams` dần về 0, nhưng reconnect là trách nhiệm client và LB. Demo không có cách biết tất cả client đã nối sang instance mới; với một JVM duy nhất đang `draining=true`, các kết nối mới tới chính instance này sẽ nhận 503.

`Sinks.One` hoàn tất một lần, không phải signal bật/tắt liên tục. Muốn test lại trạng thái chưa drain, **restart** ứng dụng. Không chuyển lại `draining=false` tùy tiện khi các subscriptions cũ đã kết thúc, vì lifecycle phải nhất quán.

### 15.3. application.yml

Tạo `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Đối với Boot 3.5, dòng `server.shutdown: graceful` là explicit declaration của default, không có nghĩa riêng nó giúp streaming client có automatic replay. `spring.lifecycle.timeout-per-shutdown-phase` là deadline khi context shutdown; nó **không tự kích hoạt** endpoint `/demo/drain`.

### 15.4. Khởi động

Trong thư mục root dự án Spring Initializr:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu port 8080 đang dùng, dừng project khác trước. URL của demo: `http://localhost:8080`.

## 16. Kiểm chứng bằng curl trên hai terminal

### 16.1. Readiness ban đầu

~~~bash
curl -sS -i http://localhost:8080/ready
~~~

Khi chưa drain, **HTTP status 200**, response body:

~~~text
READY
~~~

Đọc trạng thái:

~~~bash
curl -sS http://localhost:8080/status
~~~

Trước khi có SSE subscribers, JSON có thể là:

~~~json
{"draining":false,"activeStreams":0}
~~~

Thứ tự các trường JSON không được bảo đảm bởi `Map.of`, nên test nên đọc theo key thay vì so sánh raw string.

### 16.2. Giữ SSE stream mở

Ở **terminal A** chạy:

~~~bash
curl -N -i -H 'Accept: text/event-stream' \
  http://localhost:8080/events
~~~

`-N`/`--no-buffer` giúp curl xuất dữ liệu ngay thay vì giữ ở output buffer. Server bắt đầu phát events, có thể thấy:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-store

event:tick
data:tick-0

event:tick
data:tick-1

event:tick
data:tick-2

~~~

Đây là **output minh họa cấu trúc SSE**; thứ tự/viết hoa response headers và dấu cách sau dấu `:` tùy HTTP serializer. Nhưng các `data:tick-0`, `tick-1`... theo logic code và khoảng hai giây giữa events là kỳ vọng khi chưa bị mạng/proxy ảnh hưởng.

Ở terminal B, trong khi SSE đang mở:

~~~bash
curl -sS http://localhost:8080/status
~~~

Kỳ vọng `activeStreams` bằng **1** nếu chỉ một client SSE đã subscribe và chưa ngắt. Nếu mở hai SSE connections, số active có thể là 2.

### 16.3. Kích hoạt drain từ terminal B

~~~bash
curl -sS -i -X POST http://localhost:8080/demo/drain
~~~

HTTP body kỳ vọng:

~~~json
{"state":"draining"}
~~~

Terminal A sẽ **kết thúc stream** sau tín hiệu (thời gian cần thiết tùy cancellation/scheduling/network). Đọc readiness:

~~~bash
curl -sS -i http://localhost:8080/ready
~~~

Kỳ vọng:
- Status **503 Service Unavailable**.
- Body `DRAINING`.

Đọc status:

~~~bash
curl -sS http://localhost:8080/status
~~~

Khi luồng SSE đã kết thúc:

~~~json
{"draining":true,"activeStreams":0}
~~~

Giá trị `activeStreams` có thể chưa về 0 đúng ngay thời điểm vừa phát drain, vì cleanup bất đồng bộ. Quan sát sau khi terminal A đóng stream.

### 16.4. Tạo SSE mới sau drain

~~~bash
curl -sS -i http://localhost:8080/events
~~~

Kỳ vọng status **503** do `ResponseStatusException`. Body lỗi chi tiết phụ thuộc Spring Boot error handling và cấu hình. Endpoint `/events` **không mở thêm một stream** khi draining.

### 16.5. Ngắt client chủ động và xem cleanup

Restart demo để bỏ cờ draining. Mở `curl -N` tới `/events`, rồi nhấn Ctrl+C ở **terminal curl**. Trong điều kiện server phát hiện client đã đóng socket và subscription bị cancel, `doFinally` sẽ giảm `activeStreams`. Việc phát hiện disconnect có thể trễ hoặc không đồng bộ; không thiết kế cleanup dựa trên giả định mọi TCP disconnect luôn được phát hiện ngay tức khắc.

**Phân biệt:** `POST /demo/drain` chỉ là **drain logic ứng dụng**, không gửi OS `SIGTERM`. Còn dừng process bằng tool/IDE có thể là SIGINT, SIGTERM hoặc hard kill tùy môi trường. Không dùng một thử nghiệm Ctrl+C rồi kết luận platform graceful shutdown đã phối hợp LB chính xác.

## 17. Thiết kế readiness cho môi trường thực

Demo `GET /ready` trả text thủ công để minh họa, nhưng production thường dùng Spring Boot Actuator:
- `/actuator/health/liveness` cho liveness.
- `/actuator/health/readiness` cho readiness.
- `ApplicationAvailability` và `ReadinessState` cho trạng thái của ứng dụng.

Khi ứng dụng quyết định drain, có thể phát availability change event, ví dụ fragment:

~~~java
// Fragment trong class có ApplicationContext context.
AvailabilityChangeEvent.publish(
    context, ReadinessState.REFUSING_TRAFFIC);
~~~

Imports tương ứng:
- `org.springframework.boot.availability.AvailabilityChangeEvent`
- `org.springframework.boot.availability.ReadinessState`
- `org.springframework.context.ApplicationContext`

Đây **không phải** thay thế toàn bộ shutdown orchestration. Readiness false vẫn cần thời gian LB/ingress nhận thông tin, giảm new traffic và đóng active streams. Nếu HTTP server đã dừng nhận request mới, probe có thể không truy cập được; đừng đợi tới lúc connector đóng rồi mới mong một route readiness phản hồi HTTP 503.

Khi có management port riêng, có thể expose `/readyz` và `/livez` trên **main server port** bằng `management.endpoint.health.probes.add-additional-paths=true` trong cấu hình phù hợp. Tránh liveness phụ thuộc vào database/broker tạm thời lỗi để không gây cascading restart.

## 18. Client reconnect: dùng backoff và jitter, không tạo reconnect storm

Khi pod A drain, hàng nghìn browsers có thể thấy SSE/WebSocket close cùng lúc. Nếu tất cả reconnect ngay, pod B hoặc LB có thể bị **thundering herd**:
- TLS/WebSocket handshakes tăng đột biến.
- Redis/broker subscriptions được tạo cùng lúc.
- CPU, connection pool và memory tăng.
- Client timeout rồi retry nữa, làm vòng lặp xấu.

### SSE EventSource browser

Ví dụ frontend **same-origin**, khi dự án đã cung cấp trang web ở cùng origin API:

~~~javascript
const stream = new EventSource("/events");

stream.addEventListener("tick", event => {
  console.log("event:", event.data);
});

stream.onerror = () => {
  console.warn("SSE disconnected; browser may reconnect");
};

// Khi user rời màn hình, phải đóng chủ động:
window.addEventListener("pagehide", () => stream.close());
~~~

`EventSource` thường tự reconnect theo cơ chế browser và SSE `retry:` field. **Không tạo EventSource mới trong mỗi `onerror`** mà quên đóng instance cũ: sẽ nhân đôi connections. Đối với frontend khác origin, cần CORS phù hợp; `EventSource` credentials/cookie behavior cần thiết kế theo browser `withCredentials` và SameSite/CORS policy.

Ứng dụng có thể gửi trường `retry: 5000` trong SSE stream để gợi ý reconnect delay theo milliseconds, nhưng client implementation có thể có policy riêng. Để tránh reconnect đồng loạt, có thể dùng một client reconnection manager kiểm soát jitter/budget, đặc biệt với WebSocket custom clients.

### WebSocket reconnect fragment

~~~javascript
// Fragment minh họa quản lý retry ở frontend.
let attempts = 0;

function connectSocket() {
  const socket = new WebSocket("wss://api.example.com/ws");

  socket.onopen = () => {
    attempts = 0;
    // Gửi subscription/cursor sau khi xác thực thành công.
  };

  socket.onclose = () => {
    const base = Math.min(30000, 1000 * 2 ** attempts);
    const jitter = Math.floor(Math.random() * 500);
    attempts = Math.min(attempts + 1, 5);
    setTimeout(connectSocket, base + jitter);
  };
}

connectSocket();
~~~

Đoạn này chỉ minh họa **backoff có jitter**, chưa xử lý các trường hợp offline, logout, pagehide, duplicate sockets, authentication expiry và maximum retry budget. Production cần thêm cancellation/cleanup và bảo đảm chỉ một active connection manager cho một logical session.

**Không để mọi client reconnect vào IP của pod cũ.** Client dùng public LB/service hostname, còn LB route tới target healthy. Nếu client được cấp per-instance URL (như sharding), phải có service discovery/redirect strategy cập nhật.

## 19. WebSocket close codes: shutdown khác mạng chết

Theo RFC 6455, server WebSocket có thể phát **Close frame**:
- `1000 Normal Closure`: kết thúc bình thường theo protocol/application.
- `1001 Going Away`: một endpoint đang rời đi, ví dụ server shutdown.
- `1008 Policy Violation`: đóng vì policy, không nên dùng như mã mặc định cho mọi reconnect.
- `1011 Internal Error`: lỗi server không thể hoàn tất yêu cầu.
- `1006 Abnormal Closure`: **không bao giờ được gửi như Close frame code**; phía nhận dùng để biểu thị kết nối biến mất bất thường mà không có close frame hợp lệ.

Một server biết trước mình đang drain có thể:
1. Từ chối **new handshakes**.
2. Phát thông báo ứng dụng sắp chuyển node nếu cần.
3. Gửi WebSocket close `1001` phù hợp.
4. Đóng session sau khoảng chờ hợp lý.
5. Cho client reconnect và khôi phục subscription từ shared state.

Client cần phân biệt `1001` với policy/auth errors: reconnect có thể hữu ích khi server going away, nhưng **403/1008 do thiếu quyền** không nên retry vô hạn. Khi mạng chết, close code trong browser có thể là 1006; cần backoff và kiểm tra network online state.

**Không dựa vào Close frame luôn đến được browser.** Khi process bị kill, LB reset TCP hoặc đường truyền đứt, client có thể không nhận graceful close. Bởi vậy protocol phải có recovery kể cả khi không thấy “server going away” message.

## 20. HTTP/2 GOAWAY và kết nối dài

Trong HTTP/2, **một connection có thể mang nhiều active streams**. Khi một server/LB chuẩn bị dừng, `GOAWAY` giúp báo rằng endpoint sẽ không nhận streams mới trên connection đó, đồng thời có thể cho những streams đã bắt đầu tiếp tục xử lý.

Ví dụ:

~~~text
HTTP/2 connection
  |
  +-- Stream 1: GET /events (SSE vẫn mở)
  +-- Stream 3: GET /catalog (đã hoàn thành)
  +-- Stream 5: POST /orders (đang xử lý)
  |
  +-- GOAWAY (last-stream-id = N)
       |
       +-- Không tạo streams mới trên connection này
       +-- In-flight streams được phép hoàn tất trong giới hạn
       +-- Client mở connection mới khi cần
~~~

Theo **RFC 9113 `6.8`**, `GOAWAY` có trường last-stream-id để xác định những peer-initiated streams mà endpoint có thể đã xử lý. Nó giúp client xác định một số stream IDs lớn hơn giới hạn **chưa được xử lý** và có thể được retry trên connection khác. Với streams có ID thấp hơn hoặc bằng, **không tự động retry request không lũy đẳng** khi kết quả mơ hồ.

Một streaming SSE có thể vẫn đang mở khi GOAWAY được phát; nếu grace period hết, connection/stream có thể bị cắt. GOAWAY **không tự gửi lại những events bị mất**. App cần event IDs + replay như mục 11.

Không giả định mọi proxy gửi đúng chuỗi GOAWAY theo tài liệu hoặc client library sẽ tự retry business requests an toàn. Kiểm thử với HTTP/2 client thực tế và quan sát frames nếu cần.

## 21. Spring MVC SseEmitter và Spring WebFlux khác nhau ở đâu?

Spring MVC/Servlet hỗ trợ `SseEmitter` và Servlet asynchronous request handling. Spring WebFlux hỗ trợ `Flux<ServerSentEvent<T>>` hoặc các publishers streaming.

| Chủ đề | Spring MVC / SseEmitter | Spring WebFlux / Flux SSE |
|---|---|---|
| Vòng đời chính | Servlet async request | Reactive subscription |
| Gửi dữ liệu | `SseEmitter.send(...)` có thể là I/O blocking tùy container | Publisher emission/HTTP writer |
| Timeout | `SseEmitter` timeout + MVC async/container config | HTTP server/proxy/operator timeout tùy pipeline |
| Client ngắt | `onCompletion`/`onTimeout`/`onError` callbacks | `doFinally`/cancellation/error signals |
| Dừng app | Phối hợp emitter completion và Boot shutdown | Phối hợp sink/signal complete và Boot shutdown |
| Scale/replay | Cần external state | Cũng cần external state |
| Backpressure | Phải kiểm soát async executor/sends và slow clients | Reactive demand giúp điều phối, vẫn cần giới hạn queues |

Ví dụ **fragment** cho Spring MVC:

~~~java
@GetMapping(path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter stream() {
    SseEmitter emitter = new SseEmitter(300_000L);
    emitter.onCompletion(() -> removeFromRegistry(emitter));
    emitter.onTimeout(() -> removeFromRegistry(emitter));
    emitter.onError(error -> removeFromRegistry(emitter));

    registerAndScheduleEvents(emitter);
    return emitter;
}
~~~

Đây **không phải class runnable**: `removeFromRegistry`, `registerAndScheduleEvents` và registry/executor là thành phần bạn cần thiết kế trong project MVC. `300_000L` là 300.000 milliseconds (5 phút) và đại diện một async timeout cho emitter ở cấu hình thích hợp; **không tự đồng nghĩa NGINX/LB idle timeout**. Trong ứng dụng thực tế cần xử lý việc `send()` có thể chặn hoặc ném IOException, cleanup khi hoàn tất, timeout, error, và cấu hình executor/capacity.

Nếu đang xây hệ thống mới và muốn hàng nghìn SSE streams, đánh giá WebFlux/Reactor Netty hoặc các giải pháp event streaming phù hợp, nhưng **không khẳng định WebFlux luôn nhanh hơn MVC** mà chưa benchmark theo workload, I/O và deployment.

## 22. Backpressure, slow consumers và tài nguyên connection

Một connection đang mở tiêu thụ tài nguyên:
- Socket/file descriptor và TLS state.
- Bộ nhớ cho buffers, pipeline/sessions và metadata.
- Một số timers, scheduled tasks, heartbeats.
- Subscription/broker topic membership hoặc session registry.
- Outbound queue nếu client nhận chậm.

**Không nên có một unbounded queue trên mỗi client.** Khi một client mất mạng nhưng server chưa phát hiện, events có thể xếp hàng, memory tăng rồi gây OOM. Reactive streams có backpressure ở những điểm phù hợp, nhưng nó **không tự giải quyết** mọi overflow tại WebSocket adapter, broker hoặc application sink.

Các chiến lược:
1. Đặt giới hạn size/buffer/time cho outbound messages.
2. Chọn overflow policy theo nghiệp vụ: drop old non-critical updates, coalesce latest state, disconnect slow client hoặc lưu bền và resume.
3. Không drop silently những events cần exact delivery (ví dụ financial audit).
4. Giới hạn concurrent connections per user/IP/tenant nếu phù hợp; bảo vệ handshake abuse.
5. Cleanup subscription khi disconnect/drain/timeout.
6. Theo dõi active connections, publish-to-send lag, queue depth và JVM memory/GC.

**SSE là one-way**, nên dùng cho trạng thái và notifications server→client; đừng cố sử dụng SSE để truyền client commands hai chiều. Với WebSocket, đặt message size limits, auth và per-message policy.

## 23. Bảo mật của kết nối dài

Kết nối dài thường tồn tại lâu hơn access token/session state. Phải trả lời:
- Auth tại **handshake** có đủ cho toàn bộ lifetime không?
- Khi token hết hạn, người dùng logout, mất role, bị khóa tài khoản thì connection còn được đọc dữ liệu không?
- Có thể yêu cầu client refresh authentication và reconnect có kiểm soát không?
- Subscription vào topic có kiểm tra quyền **mỗi topic** không?
- Có kiểm tra `Origin` cho WebSocket handshake phù hợp không?
- Có dùng `wss://`/`https://` qua TLS ở public edge không?

**WebSocket không tuân chính xác cơ chế browser CORS như fetch/SSE.** Cần kiểm tra origin trong handshake, CSRF/cross-site WebSocket hijacking khi cookie auth, và xác thực/authorization riêng. Với SSE chạy bằng EventSource từ origin khác, cần CORS phù hợp; `EventSource` browser không cho thêm tùy ý mọi custom request header như một generic HTTP client.

Nếu dùng sticky cookie để load balance, nó **không phải authorization token**. Nếu kết nối chuyển sang Pod B sau reconnect, Pod B phải xác minh lại auth và topic permissions, không tin metadata từ pod cũ một cách vô điều kiện.

**Drain endpoint của demo không có xác thực**: tuyệt đối không public trong hệ thống thật. Dùng control plane hooks/secure management endpoints và audit tác động.

## 24. Observability: đo đúng lifecycle, không chỉ đo request rate

Các metric hữu ích:

| Nhóm | Đề xuất theo dõi |
|---|---|
| Connections | Active SSE/WS per instance, connections opened/closed, connection age, idle time |
| Lifecycles | Reason for close: normal, going-away, timeout, error, proxy reset, shutdown |
| Client recovery | Reconnect attempts, backoff, latency to reconnect, clients recovered per minute |
| Data integrity | Last delivered/acked event ID, replay count, duplicate count, gap count |
| Shutdown | Readiness transition time, drained connections, remaining at SIGTERM, forced terminations |
| Load balance | Active connections by backend, new handshakes distribution, target draining age |
| Proxy | 499/502/503/504 (tùy NGINX/vendor), upstream reset, read timeout |
| Runtime | Reactor event-loop lag, CPU, memory, FD count, TLS costs, publish queues |
| SLO | Time connected, event delivery latency, percent of sessions recovered without gap |

**Không gắn user ID, raw JWT, WebSocket session ID, connection ID hoặc full event ID vào high-cardinality Prometheus labels**; dùng route template, protocol, close-reason class, instance/pod và các dimension có giới hạn. Tracing/structured logs có thể chứa safe correlation ID nhưng phải tuân privacy/security rules.

Phân biệt **client-initiated disconnect** với **server-initiated drain** và **proxy timeout**. Nếu chỉ thấy socket `closed`, nguyên nhân vẫn chưa rõ cho đến khi đối chiếu proxy/LB logs, timestamps và close codes.

### Tìm tầng gây đóng kết nối

Thử một request:
- Gọi trực tiếp origin Boot trong test network: streaming vẫn sống?
- Gọi qua NGINX: bị cắt sau 60s im lặng?
- Gọi qua ALB/CDN: bị cắt dù NGINX đã tăng timeout?
- Gửi heartbeat từ app và kiểm tra bytes có ra đến client không?
- Kiểm tra NGINX buffering và ứng dụng flush response?
- So sánh thời điểm bị cắt với rollout/pod deletion và SIGTERM logs?

Nếu vấn đề chỉ xuất hiện ở một hop, chỉnh **đúng tầng**, không bật “infinite timeout” bừa tại mọi nơi.

## 25. Ma trận kiểm thử trước khi rolling deploy

| Kịch bản | Cách kích hoạt | Tiêu chí đạt |
|---|---|---|
| SSE im lặng lâu | Tắt business events, chỉ heartbeat | Không bị LB/proxy cắt trước ngưỡng mong muốn |
| SSE không heartbeat | Dừng mọi bytes trong test | Xác định timeout hop nào cắt, không rớt không rõ nguyên nhân |
| NGINX buffering | So sánh buffering on/off | Event latency/chunks được flush đúng |
| WS idle > 60s | Không gửi data/ping | Quan sát idle timeout; sau đó kiểm tra ping/pong |
| WebSocket disconnect | Restart target/đóng socket | Client reconnect backoff; khôi phục subscription |
| SSE reconnect | Mất mạng ngắn | Last-Event-ID/replay không gây gap khi có durable store |
| 2 instances | Giữ 1.000 connections, scale thêm | Biết rằng sockets cũ không tự migrate; new connections phân phối hợp lý |
| Scale-in | Chuyển readiness false rồi drain | New handshakes không vào target đang drain sau propagation |
| Graceful shutdown | SIGTERM khi SSE/WS đang mở | Application draining phối hợp; không vượt grace budget ngoài dự kiến |
| Hard kill | SIGKILL/process crash | Client recovery còn hoạt động, không phụ thuộc close frame |
| HTTP/2 GOAWAY | Simulate LB/backend draining | Client mở connection mới; in-flight idempotent/non-idempotent xử lý đúng |
| Slow consumer | Giới hạn network receive | Không OOM do queue vô hạn; có overflow policy |
| Auth expired | Token hết hạn khi WS vẫn mở | Không tiếp tục stream dữ liệu bị cấm |
| Gateway error | Force upstream 502/503 | Có observability và client backoff/retry policy phù hợp |

`1.000 connections` trong bảng chỉ là tải thử minh họa, không phải ngưỡng capacity chuẩn. Scale testing phải dựa trên FD/memory/CPU/broker load và mục tiêu SLO thực tế.

## 26. Trình tự triển khai đề xuất

Với kiến trúc **Browser → CDN/ALB → NGINX → Spring Boot** giữ SSE/WebSocket:

1. **Vẽ tất cả các hop** cùng TLS termination, HTTP version và proxy route.
2. Ghi chính xác **idle timeout, absolute lifetime, read timeout, async timeout, deregistration delay** từng hop.
3. Chọn **heartbeat interval** thấp hơn min idle timeout có khoảng an toàn; test bytes đi qua tất cả các hops.
4. Với SSE, cấu hình **non-buffering** ở proxy routes phù hợp; với WS, chuyển Upgrade header đúng.
5. Dùng external store/broker cho **event cursor, subscription state và recovery**, không chỉ RAM + sticky.
6. Khi sắp rollout, **đánh dấu instance unready trước**, chờ propagation.
7. Chủ động thông báo/đóng SSE/WS và giảm số active connections, bảo đảm clients có backoff.
8. Gửi SIGTERM, để Boot graceful shutdown chờ in-flight trong ngân sách đã tính.
9. Đảm bảo Kubernetes termination grace **bao phủ** preStop + Boot grace + overhead.
10. Test cắt kết nối bất thường, not just graceful. Dữ liệu quan trọng phải replay/ack/dedupe được.
11. Quan sát reconnect storm, delivery gaps và forced termination rate.
12. Đánh giá lại mọi defaults sau khi nâng Boot, server, NGINX, ingress hoặc cloud LB.

### Bảng cấu hình ngân sách giả định

| Giá trị thử nghiệm | Ý nghĩa |
|---|---|
| SSE/WS heartbeat: 20s | Tạo hoạt động đều đặn, chừa khoảng trước idle |
| ALB idle timeout: 60s | Một hop có thể cắt khi im lặng |
| NGINX proxy_read_timeout: 75s | Ngưỡng khoảng giữa hai lần upstream đọc |
| Pre-drain propagation window: 10s | Thời gian dành cho LB/endpoint cập nhật, chỉ là ví dụ |
| Boot graceful shutdown phase: 30s | Thời gian chờ in-flight requests hoàn thành |
| Kubernetes terminationGracePeriodSeconds: 60s | Ngân sách tổng cần bao trùm các bước ở trên và dư địa |

Đây là **ví dụ lập kế hoạch**, không phải template production. Một hệ thống không thể bảo đảm propagation đúng 10s ở mọi cluster. Hơn nữa, nếu streams không được đóng chủ động, chỉ chờ grace 30s có thể không đủ dù termination budget 60s. Điều quan trọng là **phối hợp các đồng hồ** dựa trên đo đạc.

## 27. Các lỗi thường gặp và cách giải quyết

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| SSE ngắt đúng ~60s im lặng | ALB/NGINX idle hoặc proxy_read_timeout | Xem đúng hop; heartbeat + buffering off + timeout phù hợp |
| WebSocket 101 thành công rồi 1 phút sau close | Upstream không gửi data/ping, proxy read timeout | Gửi WS ping/pong phù hợp và xem proxy logs |
| NGINX chỉ trả SSE events từng nhóm lớn | Response buffering | `proxy_buffering off` cho route streaming |
| Tăng timeout Spring nhưng vẫn ngắt | Hop nhỏ hơn ở CDN/LB/ingress | Vẽ path và sửa đúng bottleneck |
| HTTP/2 PING đều nhưng ALB vẫn đóng | ALB không reset idle timer bằng HTTP/2 PING | Tạo activity hợp lệ theo LB và kiểm chứng |
| Deploy xong nhiều clients kết nối lại cùng lúc | Draining không stagger, reconnect không jitter | Pre-drain + client backoff/jitter, capacity reserve |
| Scale-out nhưng pod cũ vẫn giữ nhiều sockets | Existing sockets không tự rebalance | Chấp nhận skew, rolling drain hoặc giới hạn connection age |
| Reconnect sang pod mới mất session/topic | State chỉ nằm local; sticky không giúp khi pod chết | Shared state, broker, subscription recovery |
| SSE nhận event trùng sau reconnect | Replay không có dedupe/cursor ổn định | Event ID ổn định, client dedupe/ack |
| SSE mất events giữa disconnect và reconnect | Không có durable replay | Last-Event-ID + event log + catch-up/live atomic design |
| WebSocket close 1006 thay vì 1001 | TCP reset/hard kill/proxy close không có close handshake | Recovery cả khi không nhận graceful close |
| Graceful stop bị treo đến deadline | Long-lived request không tự complete | Application-level drain/close stream trước SIGTERM |
| Pod bị SIGKILL dù Boot graceful=30s | TerminationGracePeriod quá ngắn sau preStop | Tính ngân sách tổng, đo thực tế |
| Readiness false làm pod bị restart ngay | Nhầm liveness với readiness | Tách probes, dùng lifecycle states đúng |
| 503 trên stream mới sau drain | Instance cố ý từ chối | LB chuyển client tới healthy target; retry có backoff |
| Browser CORS error ở EventSource | Cross-origin SSE không được phép | Cấu hình CORS và cookie policy đúng |
| WS handshake có 403 Origin mismatch | Origin/auth policy không cho phép | Xác minh frontend origin, không whitelist tất cả |
| FD/memory tăng sau nhiều disconnects | Subscription không cleanup, buffers không giới hạn | onCancel/doFinally/registry cleanup, limit queues |
| JS tạo nhiều connections sau onerror | Code liên tục tạo EventSource mới | Một connection manager, đóng instance cũ |
| HTTP2 GOAWAY làm POST bị retry trùng | Client retry non-idempotent khi outcome không rõ | Idempotency key và status reconciliation |

## 28. Câu hỏi ôn tập

**1.** `proxy_read_timeout 75s` có nghĩa một SSE connection bắt buộc đóng sau 75 giây không?

**Đáp án:** Không. Với NGINX, nó là timeout giữa các lần đọc upstream; response phát bytes thường xuyên có thể tồn tại lâu hơn.

**2.** Vì sao SSE gửi heartbeat mỗi 20 giây vẫn có thể ngắt sau một khoảng lâu?

**Đáp án:** Heartbeat có thể bị proxy buffer, không qua đúng hop, hoặc bị **absolute connection lifetime/rollout/draining**, không phải idle timeout.

**3.** WebSocket đang kết nối Pod A. Scale thêm Pod C có chuyển socket đó sang C không?

**Đáp án:** Không. LB thường chỉ chọn backend cho connection/handshake mới, không migrate TCP/WebSocket đang sống.

**4.** Sticky session có bảo đảm không mất dữ liệu khi pod A restart không?

**Đáp án:** Không. Nó không giữ pod A sống hoặc chuyển local state sang pod B. Cần shared state và replay/recovery.

**5.** Boot 3.5 cần bắt buộc thêm `server.shutdown: graceful` mới có graceful shutdown không?

**Đáp án:** Theo tài liệu Boot 3.5, graceful shutdown **được bật mặc định**. Có thể khai báo explicit cho rõ; cần `spring.lifecycle.timeout-per-shutdown-phase` phù hợp để điều chỉnh timeout.

**6.** Tăng grace period lên một giờ có bảo đảm WebSocket không ngắt khi deploy không?

**Đáp án:** Không. Streams có thể không tự kết thúc, platform/LB có deadlines riêng và pod có thể bị terminate. Cần drain chủ động và client recovery.

**7.** `terminationGracePeriodSeconds` có cộng thêm vào thời gian `preStop` sau đó mới bắt đầu tính không?

**Đáp án:** Không. Đây là ngân sách termination tổng, phải tính thời gian hooks và stop trong cùng khoảng cùng các chi phí liên quan.

**8.** SSE gửi `id` thì Spring sẽ tự replay events bị mất khi browser reconnect không?

**Đáp án:** Không. EventSource có thể gửi `Last-Event-ID`; server phải có durable event log/cursor và logic replay.

**9.** WebSocket close code 1006 có được server gửi trong Close frame không?

**Đáp án:** Không. 1006 biểu thị kết nối đóng bất thường ở phía nhận, không được gửi trong frame theo RFC 6455.

**10.** HTTP/2 GOAWAY bảo đảm các POST in-flight đã rollback chưa?

**Đáp án:** Không. GOAWAY cho biết khả năng stream đã được xử lý theo last-stream-id; với kết quả mơ hồ và lệnh không lũy đẳng vẫn cần idempotency/reconciliation.

**11.** Nếu ALB idle=60s và app phát sự kiện mỗi 5 phút, tăng chỉ Spring request timeout có đủ không?

**Đáp án:** Không. Cần xử lý idle hop, gửi heartbeat/bytes phù hợp qua proxy hoặc thay policy ALB.

**12.** Lúc drain vì sao nên giữ liveness true trong khi readiness false?

**Đáp án:** Instance vẫn có thể đang hoàn tất kết nối cũ; readiness false ngăn traffic mới, liveness false có thể gây restart/kill quá sớm.

### Thực hành mở rộng

Từ app mục 15:
1. Tăng khoảng `Flux.interval` từ 2s lên 90s trong một môi trường NGINX test, so sánh kết nối có và không heartbeat.
2. Đặt `proxy_read_timeout 10s`, quan sát streaming bị cắt nếu không có bytes 10s. Sau đó thêm SSE heartbeat comment mỗi vài giây và kiểm tra kết nối sống; không cần set mọi timeout “infinite”.
3. Chạy hai instances sau một LB test, kết nối nhiều SSE clients, kiểm tra active connections per instance. Thêm instance thứ ba và quan sát connections cũ không tự chuyển.
4. Gọi `/demo/drain` trên một instance và kiểm tra readiness, SSE completion, reconnect tới instance còn healthy.
5. Thiết kế một durable event sequence và hỗ trợ `Last-Event-ID`; kiểm tra replay không thiếu/trùng qua restart.
6. Trên cluster test, gửi SIGTERM khi stream đang mở, đo chênh lệch giữa thời gian app graceful shutdown và giới hạn pod termination, sau đó điều chỉnh budgets.

## 29. Tài liệu chính thức

- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html)
- [Spring Boot 3.5 — Actuator Kubernetes Liveness/Readiness](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Framework — WebFlux Server-Sent Events](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework — Asynchronous Requests in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework — Reactive WebSockets](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html)
- [NGINX — WebSocket Proxying](https://nginx.org/en/docs/http/websocket.html)
- [NGINX — ngx_http_proxy_module: proxy_read_timeout và proxy_buffering](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [AWS ALB — Connection idle timeout và HTTP client keepalive duration](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/edit-load-balancer-attributes.html)
- [AWS ELB — Target Deregistration Delay](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/edit-target-group-attributes.html)
- [Kubernetes — Pod Lifecycle / Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#termination-of-pods)
- [RFC 9113 — HTTP/2: PING và GOAWAY](https://www.rfc-editor.org/rfc/rfc9113.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html)
- [WHATWG HTML Living Standard — Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html)

**Ghi nhớ cuối cùng:** kết nối dài được quyết định bởi **hop có thời hạn khắt khe nhất**, không phải riêng Spring Boot. Heartbeat cứu idle connection nếu bytes đi qua proxy; load balancer không migrate sockets đang sống; graceful shutdown chỉ chờ in-flight work trong một khoảng hữu hạn. Thiết kế production đúng phải kết hợp **timeouts tương thích, non-buffered streaming, readiness → draining → SIGTERM, reconnect có backoff và khả năng khôi phục state/events độc lập với instance**.
