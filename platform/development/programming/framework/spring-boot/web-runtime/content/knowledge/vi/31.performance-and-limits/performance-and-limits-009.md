# Kiểm soát tải từ máy khách chậm hoặc kết nối giữ lâu trong Spring Boot

## 1. Vấn đề: request ít nhưng vẫn có thể làm cạn hệ thống

Thông thường người học nghĩ tải server bằng **requests/second** (RPS). Thực tế một client không gửi nhiều request vẫn có thể giữ tài nguyên lâu: mở TCP connection mà không gửi đủ HTTP headers, upload body rất chậm, đọc response nhỏ giọt, hoặc duy trì SSE/WebSocket/long-poll hàng giờ.

Ví dụ:

~~~text
Client A: 1 request, trả lời xong sau 20 ms
Client B: mở TCP, gửi headers từng đoạn rất chậm
Client C: POST 50 MB nhưng chỉ gửi ~100 byte/giây
Client D: GET /download nhưng đọc 1 KB/giây
Client E: mở /events SSE trong 1 giờ
                      |
                      v
         Reverse proxy / HTTP server
              | sockets, buffers
              | workers, event loops
              | request/response state
              v
           Spring Boot
              | executor + database connections
              | queued tasks + publisher subscriptions
              | heap/direct memory + file handles
~~~

Dù mỗi client chỉ tạo một request, **số kết nối đồng thời, thời gian tồn tại và lượng tài nguyên giữ trên mỗi request** có thể làm server không còn phục vụ được client khỏe. Một kiểu khai thác nổi tiếng là **Slowloris**: gửi HTTP request headers quá chậm để chiếm connections. Biến thể khác là slow upload, slow read hoặc kết nối “hợp lệ nhưng ở mãi”.

**Mục tiêu không phải đóng mọi kết nối dài.** SSE, video/file streaming, upload lớn qua mạng di động và WebSocket có nhu cầu hợp lệ. Cần đặt hạn mức *theo giai đoạn*, tổng ngân sách tài nguyên và policy riêng cho từng loại route.

Trong bài này dùng Spring Boot 3.3.x, Java 17+, Servlet stack (Tomcat/Jetty/Undertow) và reactive stack (Reactor Netty/WebFlux). Các giá trị timeout/limit dưới đây đều là **ví dụ lab để học**, không phải cấu hình production mặc định an toàn cho mọi tải.

## 2. Phân loại slow client và lý do mỗi loại khác nhau

| Loại | Hành vi | Tài nguyên/triệu chứng | Lớp kiểm soát chính |
| --- | --- | --- | --- |
| **Idle connection** | TCP đã mở nhưng chưa gửi request hoặc chờ request keep-alive tiếp theo | Socket, file descriptor, protocol state | Listener/connector idle/keep-alive timeout, connection cap |
| **Slow request headers** | Gửi request line/headers rất chậm, nhỏ giọt | HTTP parser, connection slots, bộ nhớ header | Edge client-header timeout, header size, connector timeout |
| **Slow request body** | POST/PUT upload từng ít bytes trong thời gian dài | Socket, body buffer, parser, temp disk, worker | Body-read timeout/absolute deadline, max body, proxy buffering |
| **Slow response reader** | Server tạo response nhanh nhưng client đọc chậm | TCP send buffers, blocked writes, queued data, memory | Write timeout, bounded response buffers, proxy buffering hoặc fail closed |
| **Long-running handler** | Business logic/DB/downstream chạy lâu | Worker thread, DB connections, futures | Business deadline, cancellation, concurrency gate, DB/client timeout |
| **Long-lived stream** | SSE/WebSocket/long-poll đúng nghiệp vụ | Socket, subscription, publisher, per-client queue | Quota active streams, heartbeat, TTL/re-auth, slow-consumer policy |
| **Reconnect storm** | Hàng nghìn clients nối lại sau deploy/mạng lỗi | Handshakes, authentication, CPU, allocation | Connection/rate limits, jitter, backoff, draining |
| **HTTP/2 multiplexing** | Nhiều streams/requests trên một TCP connection | Concurrent streams + per-stream state | H2 stream limits, route concurrency, memory budgets |

**Không đánh đồng** connection idle với request đang xử lý: `keepAliveTimeout` cho HTTP/1.1 thường đo thời gian đợi request **tiếp theo** trên kết nối đã hoàn thành request cũ; nó không phải deadline cho một download đang gửi, và không thay timeout đọc toàn bộ body.

**Không đánh đồng** request timeout với read idle timeout: một client có thể gửi một byte trước khi idle timeout hết hạn, rồi tiếp tục giữ request kéo dài. Muốn chống body trickle cần xem **absolute deadline, tối thiểu tốc độ đọc, tổng kích thước** hoặc giới hạn tài nguyên ở gateway. Một “idle timeout” đơn lẻ không bảo đảm giới hạn tổng thời gian.

## 3. Những tài nguyên có thể hết trước khi CPU đạt 100%

~~~text
OPEN SOCKETS ------> File descriptors / kernel memory
REQUEST PARSERS ---> Header buffers / memory
HTTP/1 worker -----> Servlet threads / executor queue
SLOW RESPONSE -----> Socket send buffer / blocked write
UPLOAD BODY -------> Heap, direct memory, temp files, disk
DB WORK -----------> JDBC pool / transactions / row locks
STREAMS -----------> Subscribers, scheduler, buffers, topic slots
METRICS/LOGS ------> Label cardinality, queues, file I/O
~~~

Điều đó lý giải vì sao một hệ thống có CPU thấp nhưng mọi request mới đều timeout. Ví dụ 200 platform threads đang kẹt gửi dữ liệu cho client chậm, DB pool 30 connections bị giữ trong giao dịch dài, hoặc file descriptors đạt ulimit. **Giải pháp không đơn giản là tăng max threads lên 2.000.** Có thể chỉ chuyển điểm nghẽn sang memory/DB/pod, làm tail latency tệ hơn.

### Một mô hình công suất gần đúng

Theo quan hệ Little's Law cho hệ thống ổn định:

\[
L = \lambda W
\]

Trong đó:

- `L`: số request đang ở trong hệ thống trung bình.
- `λ`: requests/second.
- `W`: thời gian trung bình một request chiếm hệ thống, tính bằng giây.

Ví dụ 100 requests/second hoàn tất trong trung bình 0,1 s → khoảng 10 requests đang hoạt động. Nếu cùng tốc độ nhưng mỗi request giữ tài nguyên 10 s → khoảng **1.000** concurrent requests. Đây là ví dụ toán học, **không phải** dự báo chắc chắn cho burst/queues/slow clients; tail behavior còn nguy hiểm hơn.

Với SSE 10.000 kết nối, mỗi kết nối chỉ gửi 1 message/30 s, RPS tính theo request mở mới có thể rất nhỏ, nhưng server vẫn cần đủ sockets, TLS state, subscriptions, memory và network.

## 4. Năm lớp bảo vệ hợp tác với nhau

~~~text
Internet
   |
   | 1. Edge/CDN/WAF:
   |    TLS, header/body timeouts, client rate, concurrent connections
   v
Reverse proxy / load balancer
   |
   | 2. Proxy:
   |    request buffering, response buffering, upstream timeouts
   v
Spring embedded server
   |
   | 3. Connector:
   |    max connections, keep-alive, parser/header/body limits
   v
Spring Security + Controller
   |
   | 4. Application:
   |    per-user quotas, concurrency limits, 429/503, deadlines
   v
Service / DB / brokers
      5. Downstream:
         pool limits, timeout/circuit breaker, bounded queues,
         cancellation, telemetry, graceful shutdown
~~~

Một tầng không thay mọi tầng khác:

- Proxy giới hạn client requests nhưng **không biết** đơn hàng nào thuộc tenant nào.
- Connector có thể giới hạn sockets nhưng không biết route nào cần stream 1 giờ.
- Application có thể hạn chế active SSE nhưng **không thấy** client gửi một phần header nếu request chưa parse xong.
- DB pool giới hạn số SQL connections nhưng không ngăn socket bị chiếm.
- Circuit breaker cho downstream không chống được slow reader khi trả một file đã nằm trong RAM.

Thiết kế theo nguyên tắc **bounded resources + timeout theo giai đoạn + overload response rõ ràng + observability**.

## 5. Các loại timeout và phạm vi hiệu lực

| Timeout/deadline | Bắt đầu từ | Khi hết thời gian | Không nhất thiết kiểm soát |
| --- | --- | --- | --- |
| TLS handshake | Kết nối TLS được khởi tạo | Đóng handshake/socket | Thời gian app xử lý request |
| Request-line/header timeout | TCP accepted/đang đọc header | Đóng kết nối không hoàn tất header | Tổng response duration |
| Request-body read idle timeout | Đọc bytes request body | Đóng khi không nhận thêm bytes đủ lâu | Client gửi 1 byte đều đặn mãi mãi |
| Absolute body deadline | Bắt đầu nhận body | Hủy dù bytes vẫn tới từng ít | Response streaming sau khi nhận body |
| HTTP keep-alive timeout | Đợi HTTP request kế tiếp | Đóng idle persistent connection | HTTP request hiện đang xử lý |
| App work deadline | Bắt đầu tác vụ nghiệp vụ | Fail/cancel theo policy | Network/TCP receive timeout tự động |
| Downstream client timeout | Gọi DB/HTTP/broker | Hủy hoặc timeout ở dependency | Client đọc response chậm |
| Response write idle timeout | Server gửi response ra client | Đóng khi client không nhận/không tiến triển | Total lifetime của SSE đang phát heartbeat |
| Stream absolute TTL | Connection/subscribe bắt đầu | Đóng stream theo policy, buộc reauth/resume | Số connections hiện hoạt nếu không có quota |
| Proxy upstream read timeout | Đọc response từ Spring | Gateway đóng nếu Spring không gửi dữ liệu giữa reads | Client gửi header chậm về edge |
| Queue wait timeout | Bắt đầu xếp hàng ở executor | Reject/fail nếu không có slot | Socket connection cap |

**Lưu ý riêng NGINX:** `proxy_read_timeout` là thời gian **giữa hai lần đọc dữ liệu từ upstream**, không phải deadline xử lý request toàn phần; `send_timeout` là thời gian giữa các lần ghi response tới client. Vì vậy một stream SSE phát heartbeat có thể tồn tại rất lâu dù proxy_read_timeout là 60 giây, nếu heartbeat hợp lệ đến đều hơn.

## 6. Tomcat: giới hạn kết nối, worker threads và keep-alive

Spring Boot `spring-boot-starter-web` mặc định dùng embedded Tomcat. Spring Boot 3.3 có các properties:

~~~properties
server.port=8080

# Các số dưới đây CHỈ để thử tải trong môi trường lab.
server.tomcat.max-connections=100
server.tomcat.accept-count=20
server.tomcat.threads.max=20
server.tomcat.threads.min-spare=4

# 10s chờ request line sau accept; không phải tổng request deadline.
server.tomcat.connection-timeout=10s

# Chỉ đợi request HTTP kế tiếp sau khi request trước đã hoàn tất.
server.tomcat.keep-alive-timeout=10s
server.tomcat.max-keep-alive-requests=50

# Giới hạn HTTP headers và body multipart tùy use case.
server.max-http-request-header-size=8KB
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
~~~

**Cần đọc từng property theo đúng nghĩa:**

- `server.tomcat.max-connections`: giới hạn connections được connector nhận/xử lý đồng thời; Tomcat NIO có cơ chế tiếp nhận/queue ở socket layer. **Không phải** limit số requests/second.
- `server.tomcat.accept-count`: độ dài backlog khi capacity đã hết; OS có thể không thực thi đúng mọi giá trị. Khi queue đầy, clients có thể bị từ chối TCP connection hoặc timeout, không chắc nhận HTTP 503.
- `server.tomcat.threads.max`: giới hạn worker platform threads trong cấu hình thread-pool kiểu truyền thống; **không đồng nghĩa maxConnections**. Một socket keep-alive đang chờ request có thể vẫn chiếm connection nhưng không giữ worker request thread liên tục.
- `server.tomcat.connection-timeout`: thời gian chờ sau khi nhận connection để request URI line đến; Tomcat còn có socket/read behavior riêng. **Không tự tạo total response deadline**.
- `server.tomcat.keep-alive-timeout`: thời gian chờ request tiếp theo. Đặt `-1` nghĩa không timeout theo thuộc tính này và dễ bị dùng sai.
- `server.tomcat.max-keep-alive-requests`: số HTTP requests được xử lý trên một persistent connection trước khi đóng, không phải số connections hoặc tổng lifetime stream.
- `server.max-http-request-header-size`: ngăn headers quá lớn gây chi phí parser/buffer; không chống body gửi chậm.
- Multipart limits: kiểm soát bytes của multipart, không thay upload duration/rate limit; request khác multipart phải có giới hạn riêng ở edge/app.

**Quan trọng về virtual threads:** nếu dùng Java 21+ và bật Spring Boot virtual threads, một số `server.tomcat.threads.*` properties có thể không còn tác động như với platform threads. Java 17 của lab không bật virtual threads. Virtual threads cũng **không giới hạn số socket/DB connections**, nên capacity quotas vẫn cần thiết.

### 6.1. Tomcat timeout cho upload body

Tomcat connector có thêm các tùy chọn nâng cao `disableUploadTimeout` và `connectionUploadTimeout`. Theo Tomcat 10.1, mặc định `disableUploadTimeout=true` nên timeout upload đặc thù không được dùng và regular timeout áp theo connector behavior. Nếu chủ động bật upload timeout riêng, cần cấu hình connector phù hợp và test; đừng tuyên bố một `server.tomcat.connection-timeout=10s` là “upload luôn tối đa 10 giây”.

Trên mạng chậm, chọn upload timeouts quá ngắn có thể làm gián đoạn người dùng thật; quá dài làm tăng bề mặt DoS. Đặt **body size**, **minimum rate/absolute deadline** ở reverse proxy khi cần chống trickle; hạn chế số upload đồng thời vào backend.

### 6.2. Thread và queue không phải chính sách overload hoàn chỉnh

Nếu 20 worker threads đều bận, tăng `accept-count` từ 20 lên 5.000 chỉ làm nhiều clients chờ hơn: latency p99 tăng, retries trùng, memory/connection pressure lớn. Ở app cần thêm **admission control** trước DB-intensive work và trả nhanh 429 hoặc 503 khi quá tải.

**Đừng mặc định `max-connections=100` sẽ cho mỗi client bị từ chối HTTP 503.** TCP backlog và socket acceptance là cơ chế ở transport; status HTTP có thể không được tạo khi request còn chưa được đọc/dispatch.

## 7. Jetty: connection idle, max connections và thread pool

Khi thay starter Tomcat bằng `spring-boot-starter-jetty` (và exclude starter-tomcat), Spring Boot 3.3 cung cấp:

~~~properties
# CHỈ cho ứng dụng thực sự chạy embedded Jetty.
server.jetty.connection-idle-timeout=20s
server.jetty.max-connections=100
server.jetty.threads.max=40
server.jetty.threads.min=4
server.jetty.threads.idle-timeout=60s
server.jetty.threads.max-queue-capacity=100
server.max-http-request-header-size=8KB
~~~

- `server.jetty.connection-idle-timeout`: idle timeout của connection; **không phải** total deadline cho một business task.
- `server.jetty.max-connections`: giới hạn số connections Jetty chấp nhận và xử lý cùng lúc. Trong Boot 3.3 giá trị mặc định là `-1` theo property list (không áp dụng Jetty cap cụ thể); cần cân đối với proxy/OS/worker budget.
- `server.jetty.threads.max`: số threads trong Jetty thread pool cấu hình thông thường, không phải số TCP clients và không phải tác vụ vĩnh viễn miễn phí.
- `server.jetty.threads.max-queue-capacity`: hạn mức queue của thread pool, tránh xếp hàng không giới hạn ở worker layer nhưng không thay admission control theo route.
- `server.jetty.threads.idle-timeout`: **thread idle** timeout, khác `connection-idle-timeout`. Thread idle timeout thường điều khiển việc thu hồi idle threads, không ép một client rời khỏi connection.

Jetty còn có selectors/acceptors, HTTP/2 và connection factories; tùy chỉnh sâu cần đo và dùng phiên bản Jetty tương thích Boot. Không copy trực tiếp Tomcat `server.tomcat.max-connections` sang app Jetty rồi nghĩ có hiệu lực.

**Cảnh báo:** cấu hình queue quá ngắn trong lab có thể làm Jetty bị thiếu worker phục vụ các tác vụ nội bộ; kiểm tra health/liveness/error logs và dùng capacity model của Jetty thay vì đoán.

## 8. Undertow: I/O threads, worker threads và no-request-timeout

Với `spring-boot-starter-undertow` (đã exclude Tomcat), Spring Boot 3.3 có:

~~~properties
# CHỈ cho embedded Undertow.
server.undertow.no-request-timeout=20s
server.undertow.threads.io=2
server.undertow.threads.worker=16
server.max-http-request-header-size=8KB
server.undertow.max-http-post-size=6MB
~~~

Phân biệt:

- `server.undertow.no-request-timeout` là thời gian **connection ngồi idle mà không xử lý request** trước khi server đóng. Không đồng nghĩa toàn bộ request đang upload/download phải hoàn thành trong 20 giây.
- `server.undertow.threads.io` chạy I/O/selector công việc nhạy latency; **không được block** bằng DB/JDBC hoặc CPU-heavy task.
- `server.undertow.threads.worker` là số worker threads Undertow dành cho blocking work được dispatch; không phải quota kết nối socket.
- `server.undertow.max-http-post-size` giới hạn body POST theo Undertow semantics; mặc định Boot 3.3 là `-1B` (không có limit theo property đó), nên production cần xem yêu cầu upload và proxy size caps.
- Các `server.undertow.options.server.*` và `server.undertow.options.socket.*` liên kết Undertow/XNIO options nâng cao. Chỉ thêm các keys được tài liệu implementation xác nhận, tránh đoán một property `server.undertow.read-timeout` không có trong Boot 3.3 list.

Undertow dùng event-driven I/O. Một servlet handler làm việc blocking có thể được dispatch vào workers; điều đó không có nghĩa I/O threads vô hạn hoặc việc chạy N×Long-Poll không tốn memory/threads. Khi tuning, quan sát I/O loop latency, worker queue và connections thực.

## 9. Reactor Netty: channel idle và read/response timeouts

Nếu ứng dụng chỉ có `spring-boot-starter-webflux`, Spring Boot 3.3 thường dùng Reactor Netty. Những properties trong Boot 3.3:

~~~properties
server.port=8082

# Chỉ áp nếu HTTP server thật đang là Reactor Netty.
server.netty.idle-timeout=30s
server.netty.connection-timeout=10s
server.netty.max-keep-alive-requests=100
server.netty.max-initial-line-length=4KB
server.max-http-request-header-size=8KB
~~~

Ý nghĩa:

- `server.netty.idle-timeout`: idle timeout của **Netty channel**; nếu không cấu hình thì Boot nêu giá trị mặc định là **infinite**. Đây không phải total request deadline hay minimum byte rate.
- `server.netty.connection-timeout`: timeout liên quan Netty channel/connection; **không được dùng như một lời hứa rằng body upload hay response phải hoàn tất trong 10 giây**.
- `server.netty.max-keep-alive-requests`: giới hạn requests trên một connection; mặc định không giới hạn.
- `server.netty.max-initial-line-length` và `server.max-http-request-header-size`: hạn chế parser allocation/headers. Boot lưu ý semantics header cap khác giữa servers, nhất là Netty có thể áp theo từng header thay vì tổng request line+headers như Tomcat.

**Quan trọng:** response SSE phát heartbeat đều đặn có thể tồn tại rất lâu dù server.netty.idle-timeout đã đặt. Muốn **stream lifetime tối đa**, phải tự đặt deadline ở route/broker hoặc lifecycle app; channel idle timeout không tự làm business TTL.

### 9.1. Programmatic Netty server tuning

Ví dụ class config cho **WebFlux + Netty**:

~~~java
package demo.reactive;

import java.time.Duration;
import org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class NettyIdleConfig {
    @Bean
    WebServerFactoryCustomizer<NettyReactiveWebServerFactory>
            nettyServerCustomizer() {
        return factory -> factory.addServerCustomizers(
                server -> server.idleTimeout(Duration.ofSeconds(30)));
    }
}
~~~

`NettyReactiveWebServerFactory` cho phép custom Reactor Netty `HttpServer`. Đoạn trên cấu hình idle timeout qua API `HttpServer.idleTimeout`. **Không bật cả property và programmatic config với giá trị trái nhau** rồi giả định chúng cùng được áp; test final runtime. Đây chỉ là idle/channel policy, không giới hạn số streams, bytes/s hoặc thời gian nghiệp vụ.

### 9.2. Reactor Netty không tự chữa hot publisher không giới hạn

WebFlux dùng non-blocking I/O và Reactive Streams backpressure, nhưng nếu source phát nhanh hơn client (ví dụ 10.000 events/s vào SSE cho thiết bị di động), phải kiểm soát:

- `Flux` source là cold hay hot? Một hot `Sinks.Many`/broker có thể cần overflow policy.
- Buffer per-client có bounded không? `onBackpressureBuffer` không giới hạn có thể làm OOM.
- Có thể **drop/replace latest state** hay event bắt buộc phải được lưu bền?
- Khi downstream cancel, subscription có giải phóng DB/broker consumer/connection không?
- CPU-heavy/legacy blocking I/O có đang chạy trên Reactor event loop không? Dùng reactive driver hoặc offload blocking đúng cách.
- Có quotas số concurrent streams theo tenant/user/node và memory budget không?

**Reactive backpressure không phải bảo đảm exactly-once delivery, không thay bandwidth budget và không tự giới hạn memory cho mọi publisher.**

## 10. Reverse proxy NGINX: nơi nên chặn slow client sớm

Một kiến trúc thường gặp:

~~~text
Internet clients
      |
      v
NGINX / ingress / CDN
      | client_header_timeout
      | client_body_timeout
      | send_timeout
      | keepalive_timeout
      | limit_conn / limit_req
      |
      | proxy_request_buffering
      | proxy_buffering
      | proxy_connect/read/send_timeout
      v
Spring Boot
~~~

Lợi ích: proxy có thể nhận/đọc request từ client chậm và lọc giới hạn **trước khi tiêu tốn toàn bộ application resources**. Nhưng proxy cũng có socket, temp disk, worker connections và cache memory giới hạn; không thể biến nó thành hàng đợi vô hạn.

### 10.1. Snippet NGINX có giới hạn theo phase

Đây là **snippet trong nginx.conf** với upstream Spring đang nghe `127.0.0.1:8080`. Không thay đổi production nếu chưa xác minh mạng/CDN/ingress và người dùng hợp lệ:

~~~nginx
http {
    # Giới hạn theo IP: trong thực tế cần trusted real-ip setup.
    limit_conn_zone $binary_remote_addr zone=conn_per_ip:10m;
    limit_req_zone $binary_remote_addr zone=req_per_ip:10m rate=10r/s;

    # Header chậm được xử lý trước khi định tuyến app.
    client_header_timeout 10s;
    client_body_timeout 15s;
    keepalive_timeout 20s;
    send_timeout 20s;

    server {
        listen 8088;

        location /api/ {
            proxy_pass http://127.0.0.1:8080;
            proxy_connect_timeout 5s;
            proxy_send_timeout 20s;
            proxy_read_timeout 30s;

            # Đọc client body tại proxy rồi mới gửi upstream.
            proxy_request_buffering on;
            # Buffer response bình thường, giúp cách ly slow reader phần nào.
            proxy_buffering on;

            limit_conn conn_per_ip 4;
            limit_conn_status 429;
            limit_req zone=req_per_ip burst=15 nodelay;
            limit_req_status 429;
        }

        location /events {
            proxy_pass http://127.0.0.1:8080;
            proxy_read_timeout 75s;
            proxy_buffering off;

            # Long-lived streams có ngân sách riêng.
            limit_conn conn_per_ip 2;
            limit_conn_status 429;
        }
    }
}
~~~

**Ý nghĩa rất quan trọng:**

- `client_header_timeout`: ràng buộc việc đọc request headers. Nó khác thời gian chờ upload body và khác keep-alive.
- `client_body_timeout`: đo khoảng chờ **giữa hai lần đọc body**, không phải total body deadline. Client gửi dữ liệu đều nhưng cực chậm vẫn có thể vượt qua một idle-based limit.
- `send_timeout`: thời gian giữa các lần ghi response tới client; nhằm tránh client không đọc, không phải tổng thời gian truyền response.
- `proxy_connect_timeout`: thời gian thiết lập connection tới Spring upstream.
- `proxy_send_timeout`: thời gian giữa các lần gửi request tới upstream.
- `proxy_read_timeout`: thời gian **giữa các lần đọc từ upstream** (mặc định NGINX có giá trị 60s), không phải total handler deadline.
- `proxy_request_buffering on`: proxy nhận toàn bộ request body trước khi gửi Spring, giúp cô lập upload chậm khỏi application **nhưng chuyển áp lực temp disk/edge memory sang proxy**. Nếu tắt, Spring sẽ thấy upload nhỏ giọt trực tiếp, cần hạn mức riêng.
- `proxy_buffering on`: proxy có thể đọc response upstream nhanh hơn client và chứa trong buffers/temp files; giảm giữ app writer trong một số trường hợp nhưng có chi phí/bộ nhớ/disk.
- `proxy_buffering off` cho SSE để events được gửi dần, không bị gom chờ đầy buffer; đồng thời làm backend chịu ảnh hưởng trực tiếp hơn bởi client chậm.
- `limit_conn` giới hạn request/connection theo key khi **đã đọc xong headers**, không chặn giai đoạn gửi headers lửng từng byte. Dùng kết hợp client_header_timeout.
- `limit_req` giới hạn **tốc độ request bắt đầu**, không giới hạn số streams sống lâu; `limit_conn` và app per-user quotas mới kiểm soát active streams.

**NGINX HTTP/2/3 nuance:** với `limit_conn`, mỗi concurrent HTTP/2/HTTP/3 request được coi như một connection trong cách đếm của module, dù cùng underlying TCP/QUIC connection. Không dùng công thức “một socket = một stream”.

### 10.2. Chọn proxy buffering theo loại route

| Route | Request buffering | Response buffering | Giải thích |
| --- | --- | --- | --- |
| JSON API ngắn | Thường bật | Thường bật | Cách ly slow clients khỏi upstream; tránh queuing vô hạn |
| Upload lớn | Cân nhắc buffered + disk quotas hoặc streaming có kiểm soát | Thường không trọng tâm | Giới hạn file size, content length, disk, upload slots/timeouts |
| Download file | Không liên quan nhiều | Bật hoặc streaming tùy size/latency/memory | Cần chống slow reader và tránh temp disk đầy |
| SSE | Body GET nhỏ | **Tắt** buffering response | Gửi events/heartbeats kịp thời |
| WebSocket | Không giống response buffering thông thường | Upgrade/tunnel configuration riêng | Ping/pong, idle/reconnect, quotas, handshake |

Ngắt quá mạnh làm client mạng yếu không dùng được hệ thống; để timeout quá dài làm resource starvation. Cần SLO riêng cho người dùng hợp lệ, đo p95/p99 upload/read latency và giới hạn theo endpoint.

### 10.3. Giới hạn IP không đồng nghĩa giới hạn người dùng

NAT/corporate proxy có thể làm hàng nghìn người dùng chia một IP. Nếu chỉ dùng `limit_conn perip 2`, nhiều user hợp lệ bị từ chối. Ngược lại attacker có thể phân tán IP hoặc gửi header `X-Forwarded-For` giả.

Nên:
1. Ở edge: dùng IP/ASN/bot/rate controls theo trust boundary, và cấu hình real-ip dựa trên **trusted proxies**.
2. Ở Spring sau authentication: thêm quota **user/tenant/API key/route**.
3. Ở hạ tầng: limit connections/streams per pod và cluster; tránh một node thành hotspot.
4. Khi bị chặn: chọn status/Retry-After hợp lệ, đo số lần reject, không log bí mật credentials.

## 11. Admission control: chặn sớm hơn là xếp hàng vô tận

Có ba quyết định độc lập:

1. **Rate limiting:** cho phép bao nhiêu requests trong một khoảng thời gian? Thích hợp chống burst/abuse.
2. **Concurrency limiting:** cho phép bao nhiêu requests/streams **đang chạy** cùng lúc? Thích hợp tác vụ giữ tài nguyên lâu.
3. **Resource/budget limiting:** một request được dùng bao nhiêu bytes, time, CPU, DB connections, queue slots?

Một client gọi 1 SSE mỗi 60 phút **không vượt rate limit** nhưng một triệu clients tương tự vẫn có thể làm cạn sockets. Một download 5GB với 1 request không vượt RPS limit nhưng cần bytes/duration/concurrency budget. Vì vậy không chỉ đặt `@RateLimiter` trên controller là xong.

### 11.1. 429 hay 503?

- **429 Too Many Requests**: phù hợp khi **quota/rate của client hoặc tenant** bị vượt.
- **503 Service Unavailable**: phù hợp khi **server đang hết capacity**, tạm thời không tiếp nhận thêm.
- **413 Content Too Large**: khi payload vượt kích thước cho phép.
- **408 Request Timeout**: có thể xảy ra khi server không nhận request hoàn chỉnh trong thời gian yêu cầu; nhưng nhiều proxy/server chỉ đóng TCP hoặc trả mã khác, không phải mọi timeout đều đảm bảo 408.
- **504 Gateway Timeout**: thường do reverse proxy/gateway chờ upstream quá lâu.

`Retry-After` có thể dùng cùng 429/503 để gợi ý thời gian thử lại, nhưng phải kết hợp **exponential backoff + jitter** và client retry policy; không tự động retry POST không idempotent nếu chưa có idempotency key/business contract. Với stream bị reject, client cũng nên backoff trước khi mở lại.

### 11.2. Queue bounded

Một hàng đợi không giới hạn làm overload chuyển thành đợi vô hạn. Với ThreadPoolExecutor hoặc async tasks:

~~~text
Max active = 20
Queue = 40
Beyond capacity --> Reject fast
~~~

Chọn kích thước dựa trên mục tiêu latency. `ThreadPoolExecutor` nên có bounded queue + rejection strategy quan sát được; nếu dùng Spring `ThreadPoolTaskExecutor`, đảm bảo `queueCapacity` và `maxPoolSize` có semantics như mong đợi: **khi queue chưa đầy, pool có thể không tăng tới max ngay**.

**Không dùng request thread để chờ vô hạn acquire() từ semaphore**: điều đó biến concurrency gate thành một hàng đợi thread bị chiếm. Dùng `tryAcquire()` hoặc `tryAcquire(timeout rất ngắn)` theo SLO, trả HTTP khi không còn slot.

## 12. Dự án A: Servlet MVC + giới hạn active SSE bằng Semaphore

Ví dụ này cung cấp **một dự án Spring Boot Java 17+ runnable**:

- `GET /health` trả ngay.
- `GET /work` mô phỏng công việc 200ms, tối đa 2 requests cùng xử lý. Vượt cap sẽ **503**.
- `GET /events` phát SSE 5 tick rồi `done`, tối đa 2 concurrent streams. Stream kết thúc/timeout/disconnect phải **release permit đúng một lần**.
- Dùng thread pool chung nhỏ để mô phỏng chi phí thực; không khuyên dùng scheduler với blocking `send` cho số lượng stream rất lớn.

### 12.1. Cấu trúc

~~~text
slow-client-mvc/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/slowmvc/SlowMvcApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/slowmvc/SlowMvcTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'slow-client-mvc'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
server.tomcat.max-connections=100
server.tomcat.accept-count=20
server.tomcat.threads.max=20
server.tomcat.connection-timeout=10s
server.tomcat.keep-alive-timeout=10s
spring.mvc.async.request-timeout=20s
server.max-http-request-header-size=8KB
~~~

Cấu hình kết nối chỉ minh họa; SSE có timeout riêng 15 giây, nên stream 5 giây có đủ thời gian hoàn tất. Tomcat max-connections không phải app-SSE permit count.

### 12.2. Toàn bộ Java source

`src/main/java/demo/slowmvc/SlowMvcApplication.java`:

~~~java
package demo.slowmvc;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@SpringBootApplication
public class SlowMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(SlowMvcApplication.class, args);
    }

    @Bean(destroyMethod = "shutdown")
    ScheduledExecutorService streamScheduler() {
        return Executors.newScheduledThreadPool(2);
    }
}

@RestController
class SlowMvcController {
    private final ScheduledExecutorService scheduler;

    // Hai budgets riêng: CPU/business work vs long-lived streams.
    private final Semaphore workSlots = new Semaphore(2, true);
    private final Semaphore streamSlots = new Semaphore(2, true);

    SlowMvcController(ScheduledExecutorService scheduler) {
        this.scheduler = scheduler;
    }

    @GetMapping("/health")
    Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/work")
    Map<String, String> work() throws InterruptedException {
        if (!workSlots.tryAcquire()) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE, "work is busy");
        }
        try {
            Thread.sleep(200); // Chỉ để mô phỏng trong lab.
            return Map.of("status", "done");
        } finally {
            workSlots.release();
        }
    }

    @GetMapping(path = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    SseEmitter events() {
        if (!streamSlots.tryAcquire()) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "too many active SSE streams");
        }

        SseEmitter emitter = new SseEmitter(15_000L);
        AtomicInteger counter = new AtomicInteger();
        AtomicBoolean cleaned = new AtomicBoolean(false);
        AtomicReference<ScheduledFuture<?>> taskRef =
                new AtomicReference<>();

        Runnable cleanup = () -> {
            if (cleaned.compareAndSet(false, true)) {
                ScheduledFuture<?> task = taskRef.get();
                if (task != null) {
                    task.cancel(false);
                }
                streamSlots.release();
            }
        };

        emitter.onCompletion(cleanup);
        emitter.onTimeout(cleanup);
        emitter.onError(error -> cleanup.run());

        Runnable publish = () -> {
            int n = counter.incrementAndGet();
            try {
                emitter.send(SseEmitter.event()
                        .id("mvc-" + n)
                        .name("tick")
                        .data(Map.of("sequence", n)));

                if (n >= 5) {
                    emitter.send(SseEmitter.event()
                            .name("done").data("finished"));
                    emitter.complete();
                    cleanup.run();
                }
            } catch (IOException disconnected) {
                // Servlet container/Spring xử lý async write error.
                // Dừng publisher; không cố completeWithError cho IOException.
                cleanup.run();
            } catch (RuntimeException unexpected) {
                cleanup.run();
                emitter.completeWithError(unexpected);
            }
        };

        try {
            ScheduledFuture<?> task = scheduler.scheduleAtFixedRate(
                    publish, 1, 1, TimeUnit.SECONDS);
            taskRef.set(task);
        } catch (RuntimeException schedulingFailed) {
            cleanup.run();
            throw schedulingFailed;
        }

        return emitter;
    }
}
~~~

### 12.3. Tại sao ví dụ này giới hạn đúng hai loại tải?

- `workSlots.tryAcquire()` là **non-blocking admission** cho công việc đồng bộ. Khi không có slot, HTTP 503 được tạo sớm. `finally` release dù code có lỗi/InterruptedException, tránh permit leak. Vì `/work` hoàn toàn synchronous, phạm vi `try/finally` tương ứng với lifetime business work.
- `streamSlots.tryAcquire()` giới hạn số **SSE subscriptions** trên node. Nó độc lập với connector maxConnections=100, vì server còn cần slots cho requests bình thường.
- `SseEmitter(15_000L)` là **Servlet async timeout**. Nếu client giữ request quá lâu, callback `onTimeout` dọn producer/permit, nhưng timeout có thể chỉ phát khi container xử lý async lifecycle.
- `onCompletion`, `onTimeout` và `onError` có thể chạy trên các luồng khác nhau; `AtomicBoolean` bảo đảm **release một lần**, không trả semaphore quá số permit gốc.
- `onError`/write `IOException` không có nghĩa phải tự đóng một lần nữa bằng `completeWithError`. Spring docs hướng dẫn container quản lý async error notification cho lỗi ghi khi client disconnect.
- `ScheduledExecutorService` là bean chia sẻ và đóng khi application context shutdown; **không tạo executor mới cho mỗi client**.
- `emitter.send` trong MVC có thể **block** nếu receiver chậm. Bài lab chỉ cho 2 streams; production phải quản lý bounded write workers, per-client slow-write budget và event queue, không dùng một scheduler bé với số stream khổng lồ.
- Khi stream phát `done`, server `complete()`. Browser `EventSource` cần gọi `close()` khi nghe done; nếu không nó có thể reconnect sau khi response kết thúc.
- Trong ví dụ, mọi stream là dữ liệu giả/không cá nhân hóa. Production phải xác thực user/tenant trước khi cấp permit và trước khi phát event, đồng thời re-evaluate quyền khi lifetime dài.

**Giới hạn có chủ đích của lab:** đây là semaphore per-process; nếu có 4 Spring nodes thì tổng capacity SSE có thể là 8, chưa có global quota. Nó không trực tiếp bảo vệ giai đoạn TCP accept/partial HTTP headers, và không phát hiện slow body upload: việc đó phải do connector/proxy chịu trách nhiệm.

### 12.4. Khởi động và quan sát

Nếu project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Không có wrapper thì dùng Gradle tương thích để tạo wrapper hoặc gọi `gradle bootRun`. Khi server đã chạy:

~~~bash
curl -i http://localhost:8080/health
~~~

Dự kiến HTTP 200 và body:

~~~json
{"status":"ok"}
~~~

~~~bash
curl -i http://localhost:8080/work
~~~

Nếu có slot, HTTP 200:

~~~json
{"status":"done"}
~~~

Khi có hơn 2 requests `/work` thực sự xử lý đồng thời, request vượt capacity nhận **503**. Thứ tự các status trong thử nghiệm concurrent phụ thuộc scheduler/network; không cam kết con số chính xác nếu không đồng bộ thời điểm bắt đầu.

### 12.5. SSE và giới hạn active stream

Mở **ba terminals** liên tiếp trong vòng vài giây:

Terminal 1:

~~~bash
curl -N -i http://localhost:8080/events
~~~

Terminal 2:

~~~bash
curl -N -i http://localhost:8080/events
~~~

Terminal 3 (ngay khi hai stream đầu còn sống):

~~~bash
curl -N -i http://localhost:8080/events
~~~

Hai streams đầu có thể trả HTTP 200 `text/event-stream` và mỗi giây một event:

~~~text
id:mvc-1
event:tick
data:{"sequence":1}

id:mvc-2
event:tick
data:{"sequence":2}

...
event:done
data:finished

~~~

Formatting whitespace quanh dấu hai chấm/serialization phụ thuộc codec/framework; event **logic** là 5 ticks và 1 done. Request thứ ba sẽ nhận **503** nếu vẫn còn đúng 2 permits đang bị giữ. Sau khoảng 5 giây, hai stream bình thường hoàn tất và một request mới lại có slot.

Dùng Ctrl+C đóng stream sớm. Lúc đó server có thể chưa ngay lập tức phát hiện disconnect vì Servlet streaming phát hiện chủ yếu qua một lần ghi sau đó; khi IOException/callback đến, cleanup sẽ giải phóng permit. **Đừng đo từ khi Ctrl+C tới khi permit release như cam kết tức thì trên mọi OS/proxy.**

### 12.6. Chậm đọc response

Để mô phỏng slow reader, có thể dùng cURL:

~~~bash
curl --limit-rate 512 --max-time 5 -o /dev/null \
  http://localhost:8080/events
~~~

`--limit-rate 512` giới hạn truyền theo cURL để tạo tải nhận chậm; `--max-time 5` tự cắt ở khoảng 5s. Nhưng SSE payload của lab rất nhỏ nên **chưa chắc** đủ để làm đầy TCP send buffer hoặc khiến `send` block; với tải thật cần stream body lớn và đo blocked write/queue size.

Không mô phỏng Slowloris bằng nhiều kết nối tấn công lên địa chỉ ngoài quyền quản lý. Tất cả kiểm thử dạng trickle phải giới hạn **localhost hoặc staging do bạn sở hữu**, có số client và thời lượng nhỏ.

## 13. Test MVC: HTTP 200, asyncStarted và lỗi quá quota

Trong project MVC tạo `src/test/java/demo/slowmvc/SlowMvcTest.java`:

~~~java
package demo.slowmvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SlowMvcTest {
    @Autowired
    MockMvc mvc;

    @Test
    void healthIsResponsive() throws Exception {
        mvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"status\":\"ok\"}"));
    }

    @Test
    void eventsBeginAsyncProcessing() throws Exception {
        mvc.perform(get("/events").accept(MediaType.TEXT_EVENT_STREAM))
                .andExpect(status().isOk())
                .andExpect(request().asyncStarted());
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.slowmvc.SlowMvcTest
~~~

Kiểm tra cơ bản này không đo throughput/slow receiver thật. Muốn test quota 2 một cách ổn định, dùng HTTP integration test tạo **hai SSE streams còn mở có subscription thực**, rồi request thứ ba ngay khi server xác nhận cả hai đã đăng ký; sau đó cancel và xác minh capacity được phục hồi. Test đơn giản kiểu gửi 3 requests nối đuôi nhau có thể cho kết quả khác nhau nếu hai stream đầu đã hoàn tất trước request thứ ba.

**MockMvc không thay network test:** preflight/body trickle, proxy buffering, TCP flow control, client disconnect và keep-alive timeout cần chạy qua HTTP server thật.

## 14. Dự án B: WebFlux Reactor Netty với WebFilter giới hạn active responses

WebFlux hỗ trợ **non-blocking I/O**, nhưng một request SSE vẫn giữ một HTTP response/stream đang hoạt động và cần quota.

Ví dụ này dùng **WebFilter** để giới hạn cùng lúc **2 responses SSE**. Điểm cần học là permit được release bằng `Mono<Void>.doFinally(...)` sau khi response **complete, error hoặc cancel**, không release ngay sau khi controller trả `Flux`. Đây là lỗi phổ biến khi port code Servlet `try/finally` sang reactive stack.

### 14.1. Cấu trúc

~~~text
slow-client-reactive/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/reactive/SlowReactiveApplication.java
    │   ├── java/demo/reactive/StreamLimitWebFilter.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/reactive/SlowReactiveTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'slow-client-reactive'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8082
server.netty.idle-timeout=30s
server.netty.max-keep-alive-requests=100
server.max-http-request-header-size=8KB
~~~

### 14.2. Reactive HTTP controller

`src/main/java/demo/reactive/SlowReactiveApplication.java`:

~~~java
package demo.reactive;

import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class SlowReactiveApplication {
    public static void main(String[] args) {
        SpringApplication.run(SlowReactiveApplication.class, args);
    }
}

record Tick(long sequence, String state) { }

@RestController
class ReactiveStreamController {

    @GetMapping("/health")
    Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping(path = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<Tick>> events() {
        Flux<ServerSentEvent<Tick>> ticks =
                Flux.interval(Duration.ofSeconds(1))
                        .take(5)
                        .map(index -> {
                            long n = index + 1;
                            return ServerSentEvent
                                    .<Tick>builder(
                                            new Tick(n, "running"))
                                    .id("flux-" + n)
                                    .event("tick")
                                    .build();
                        });

        return ticks.concatWith(Mono.just(
                ServerSentEvent.<Tick>builder(
                        new Tick(0, "finished"))
                        .event("done")
                        .build()));
    }
}
~~~

`Flux.interval` tạo publisher theo từng subscription, không gọi `Thread.sleep`/`block()` trên Netty event loop. `take(5)` giới hạn số events và `done` kết thúc response hữu hạn. Điều này chỉ minh họa, không tự cung cấp replay/Last-Event-ID cho client reconnect.

### 14.3. WebFilter thực thi active-stream quota

`src/main/java/demo/reactive/StreamLimitWebFilter.java`:

~~~java
package demo.reactive;

import java.util.concurrent.Semaphore;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
public class StreamLimitWebFilter implements WebFilter {

    private final Semaphore permits = new Semaphore(2, true);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String path = exchange.getRequest()
                .getPath().pathWithinApplication().value();

        if (!"/events".equals(path)) {
            return chain.filter(exchange);
        }

        return Mono.defer(() -> {
            if (!permits.tryAcquire()) {
                exchange.getResponse()
                        .setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
                exchange.getResponse().getHeaders()
                        .set(HttpHeaders.RETRY_AFTER, "3");
                return exchange.getResponse().setComplete();
            }

            return chain.filter(exchange)
                    .doFinally(signal -> permits.release());
        });
    }
}
~~~

Giải thích:

1. `WebFilter` là reactive filter, khác Servlet `OncePerRequestFilter`.
2. Đường `/health` đi qua bình thường, không chiếm stream permit.
3. `Mono.defer` chỉ thử acquire **khi HTTP chain được subscribe**, tránh side effects eager khi lập một publisher chưa được thực thi.
4. Nếu hết 2 permits, server trả HTTP **503** và `Retry-After: 3`, không bắt đầu stream.
5. Nếu được cấp permit, `chain.filter(exchange)` hoàn tất khi **response pipeline** hoàn tất; `doFinally` được gọi cả khi complete/error/cancel để trả permit.
6. `Semaphore` là quota **trên một application instance**; nhiều pods cần thêm gateway/global user quotas.
7. Trong pipeline, chưa có quota byte/s, memory/event backlog hoặc tenant permissions. Chúng phải được thiết kế thêm.

**Cảnh báo về WebFilter:** ở ứng dụng thật có authentication filters và nhiều streams, quota thường nên đặt **sau khi biết principal đáng tin**, hoặc tách edge anonymous quotas và per-user quotas. Không dựa vào raw `X-User-Id` do client cung cấp. Filter theo path demo chỉ để minh họa.

### 14.4. Chạy thử

~~~bash
./gradlew bootRun
~~~

Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Mở hai connections:

~~~bash
curl -N -i http://localhost:8082/events
~~~

Nếu mở request thứ ba trước khi hai stream hoàn tất, sẽ trả 503 và `Retry-After: 3`. Khi một client đóng hoặc stream kết thúc, `doFinally` release capacity.

**Một lần Ctrl+C không đảm bảo server phát hiện ngay trong cùng mili giây**: cancellation truyền theo TCP/HTTP lifecycle. Test trong khoảng thời gian nhỏ và theo dõi số active streams/memory thay vì suy từ thời điểm người dùng bấm Ctrl+C.

### 14.5. WebFlux stream có backpressure nhưng vẫn cần bounded source

`Flux.interval` là một publisher có nhịp cố định. Trong production, khi downstream không theo kịp, các yếu tố khác có thể gây backpressure/cancellation; việc event source thuộc hot broker hoặc tick scheduler có thể có overflow semantics khác. Không giả định WebFlux tự giữ hàng triệu events trong memory an toàn.

Với thông báo chỉ quan tâm trạng thái mới nhất, có thể dùng policy **coalescing/latest**. Với giao dịch không được mất, ghi event vào durable store và resync/replay theo ID; không thả `onBackpressureDrop` một cách vô tư làm mất dữ liệu nghiệp vụ.

## 15. Test WebFlux: đảm bảo endpoint và lifecycle

Tạo `src/test/java/demo/reactive/SlowReactiveTest.java`:

~~~java
package demo.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SlowReactiveTest {
    @Autowired
    WebTestClient client;

    @Test
    void healthWorks() {
        client.get().uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void streamingProducesNamedEvents() {
        var response = client.get()
                .uri("/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(new ParameterizedTypeReference<
                        ServerSentEvent<Tick>>() { });

        StepVerifier.create(response.getResponseBody().take(1))
                .expectNextMatches(event ->
                        "tick".equals(event.event())
                        && "flux-1".equals(event.id())
                        && event.data() != null
                        && event.data().sequence() == 1)
                .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.reactive.SlowReactiveTest
~~~

`take(1)` giúp test không chờ toàn bộ stream và truyền cancellation upstream. Đây là test HTTP pipeline của WebFlux; **nó không chứng minh mọi case chậm đọc/slow header/slow body đã được bảo vệ**. Trường hợp đó cần proxy/network tests và test quota thực sự bằng hai active streams đồng thời.

## 16. Vì sao không dùng một filter try/finally cho mọi async request?

Với synchronous endpoint:

~~~java
try {
    return doWork();
} finally {
    permits.release();
}
~~~

phạm vi xử lý và lifetime resource có thể trùng nhau.

Với Servlet async:

~~~java
SseEmitter emitter = new SseEmitter();
return emitter;
~~~

Controller **trả về ngay**, nhưng response còn sống. Nếu release permit trong `finally` của controller thì kết nối vẫn giữ socket/subscription mà capacity counter đã giảm. Attacker có thể mở nhiều streams dù code “có semaphore”.

Với reactive:

~~~java
Flux<String> stream = createStream();
return stream;
~~~

Việc tạo `Flux` chỉ mô tả pipeline. Nó **không đồng nghĩa đã subscribe** hoặc response hoàn tất. Nên gắn acquire/release với subscription/response lifecycle bằng `Mono.defer`, `Flux.using`, `doFinally` hoặc Spring WebFilter đúng vị trí, tùy case.

Với Servlet `SseEmitter`, dùng `onCompletion`, `onTimeout`, `onError` và cleanup idempotent. Với MVC reactive return type, Spring docs nhấn mạnh **blocking response writes vẫn chạy trên async executor**, dù dữ liệu nguồn là `Flux`; không bê nguyên sự kỳ vọng WebFlux non-blocking sang MVC.

## 17. Khi response chậm: producer, queue và write path

### 17.1. Bài toán slow reader

~~~text
Producer: 1000 messages/s
        |
        v
Bounded/unbounded queue?
        |
        v
HTTP response writer
        |
        v
TCP send buffer
        |
        v
Client đọc 10 messages/s
~~~

Nếu producer không có cơ chế giảm tốc, sau vài phút có thể có hàng trăm nghìn items chờ. Dù socket không “bận CPU”, heap/direct buffers hoặc blocked worker threads tăng. Giải pháp phụ thuộc semantics:

- **Latest-state feed:** coalesce, throttle, sampling hoặc bỏ intermediate snapshots có kiểm soát.
- **Important events:** durable event store + cursor, client reconnect/replay, idempotent handler; không lặng lẽ drop.
- **Large download:** stream file bằng công cụ hỗ trợ zero-copy/backpressure khi phù hợp, kiểm soát file handles và response buffer.
- **Uploads:** body size + read deadlines + temp-disk quotas + checksums/cleanup on abort.
- **Stuck client:** close connection có logging/metrics lý do; không tạo unbounded retry queue.

### 17.2. Blocking writes trong Spring MVC

`SseEmitter.send`/`ResponseBodyEmitter.send` có thể chặn worker đang gửi khi client chậm. Servlet async giải phóng initial controller thread, **không làm mỗi lần write trở thành non-blocking**. Cần scheduler/executor có capacity, giới hạn concurrent streams, tránh giữ lock chung khi gửi cho nhiều subscribers và đóng emitter khi send lỗi.

### 17.3. Reactive source và cancellation

WebFlux/Netty hỗ trợ non-blocking I/O và Reactor demand/cancellation. Tuy nhiên:
- Một producer hot không hỗ trợ demand có thể phải buffer/drop/fail.
- `Flux.onBackpressureBuffer` nếu không giới hạn có thể OOM.
- `Flux.onBackpressureLatest` có thể mất intermediate events; chỉ dùng khi policy cho phép.
- Đóng HTTP connection không luôn hủy lập tức broker message processing nếu custom subscription không xử lý dispose/cancel.
- Không gọi `Thread.sleep`/`block()` trong reactive event loop.
- `DataBuffer` có thể wrap pooled Netty ByteBuf; custom discard/error paths phải release đúng khi chịu trách nhiệm quản lý buffer, tránh direct memory leak.

Backpressure là **cơ chế phối hợp trong pipeline**, không phải SLA của từng client và không thay limits.

## 18. HTTP/2, HTTP/3, WebSocket, SSE và long-poll cần quota riêng

### HTTP/1.1 keep-alive

Một TCP connection có thể phục vụ nhiều requests tuần tự. `max-keep-alive-requests` không hạn chế một request SSE kéo dài, và `keep-alive-timeout` thường chỉ đếm khi đợi request sau.

### HTTP/2 multiplexing

Một TCP connection mang nhiều concurrent streams. **Giới hạn TCP connection không đủ** để chặn client chiếm nhiều HTTP/2 streams, request headers và per-stream buffers. Cần HTTP/2 max-concurrent-streams/protocol limits của server/proxy và app per-route quotas; test theo thực tế deployment. Không giả định mọi property HTTP/1.1 có ngữ nghĩa y hệt HTTP/2.

### HTTP/3/QUIC

Dùng UDP/QUIC và stream-level control khác TCP. Một NGINX/CDN có thể termination HTTP/3 rồi proxy HTTP/1.1 vào Spring. Giới hạn cần áp theo **client-facing protocol và upstream protocol** riêng, cùng with quotas ở Spring.

### SSE

Browser thường reconnect theo `retry`/Last-Event-ID; không tạo durable replay tự động. Server cần:
- Connection quotas theo user/tenant.
- Heartbeat ít hơn proxy idle timeout để giữ đường truyền và phát hiện client đã rời.
- Absolute stream lifetime hoặc reauthorization khi session bị thu hồi.
- Bounded event queue, cancellation cleanup.
- Jittered reconnect và replay/idempotency nếu cần continuity.

**Heartbeat không thay absolute TTL:** nếu stream phát comment mỗi 20s, nhiều idle timeouts sẽ được reset; muốn đóng sau 1h phải đặt deadline theo ứng dụng.

### WebSocket

Kết nối thường sống rất lâu; dùng ping/pong, số sessions, message size, inbound/outbound queue, send-time limit, heartbeat và policy khi client không đọc. Sau HTTP upgrade, các timeout request thông thường không nhất thiết còn phù hợp; phải quản lý session/messaging stack.

### Long-polling

Một request có thể chờ event 20–60s rồi trả response và client mở request mới. Cần giới hạn số waiting requests, promise cleanup khi disconnect và jittered retry, không nghĩ rate limiter RPS một mình đủ.

## 19. Business deadlines và downstream resource limits

Một client có thể đọc response bình thường nhưng gọi endpoint làm DB query 60 giây. Đây là long-running server work, không phải slow reader, nhưng vẫn chiếm capacity.

Phân tách:
- **HTTP request deadline**: tổng thời gian app nhận và xử lý request theo contract.
- **DB query timeout**: không để SQL chạy vô hạn.
- **HTTP client timeout**: connect/read/response/pool acquire, khác timeout của inbound HTTP server.
- **Thread/worker concurrency**: giới hạn số công việc đồng thời.
- **Cancellation propagation**: khi client disconnect, cố hủy các tác vụ có thể hủy; nhưng không mặc định DB transaction sẽ tự rollback chỉ vì browser tab đóng.
- **Idempotency**: nếu client timeout mà server vẫn hoàn thành POST, retry phải có idempotency key hoặc business de-duplication.

Ví dụ `CompletableFuture.orTimeout` có thể làm future hoàn tất exceptional nhưng **không bảo đảm đã dừng thread/DB call thực sự**. Reactor `timeout(Duration)` có thể cancel subscription, song nguồn blocking/non-cancellable vẫn chạy. Deadline phải được chuyển xuống các downstream client drivers và kiểm tra thực tế.

Một HTTP response 504 từ gateway **không chứng minh** Spring đã ngừng xử lý transaction. Phải thiết kế cancellation, transaction boundaries và idempotent retries.

## 20. Connection quotas theo user/tenant thay vì IP giả

Một app cho phép người dùng xem dashboard SSE. Giới hạn kiểu “2 streams mỗi client IP” có thể làm nhân viên chung NAT bị chặn oan. Ngược lại, API key bị lạm dụng có thể mở streams từ nhiều IP.

Sau authentication, key quota có thể là:

~~~text
tenantId + userId + streamType

Example:
  tenant-42:user-7:notifications → max 2
  tenant-42:user-7:reports       → max 1
  tenant-42:*:all-streams        → max 500
  node:*:all-streams             → max 2000
~~~

Đây là **policy minh họa**, không phải số production khuyên dùng. Cần cân nhắc:

1. Route nào thực sự long-lived.
2. User có mở nhiều tabs/devices không?
3. Có reconnect trùng trong lúc old connection chưa release không?
4. Một tenant lớn có cần quota riêng hoặc weighted fairness không?
5. Có global limiter qua Redis/gateway/broker hay quota per node là đủ?
6. Node chết khi đang giữ distributed permits thì token/lease có TTL để auto-release không?
7. Client có thể giả userId hay quota key đến từ principal đã xác thực?
8. Khi người dùng mất quyền, stream bị đóng/reauth kịp thời không?
9. 429/503 được đo và client có backoff jitter không?

**Không giữ distributed lock vĩnh viễn theo TCP connection** mà không có lease/TTL recovery; node crash có thể làm quota không bao giờ trở về trạng thái đúng. Trong nhiều hệ thống, per-node capacity + gateway rate limit + distributed user quota là đủ, nhưng cần mô hình dữ liệu và fault tests.

## 21. Observability: đo nghẽn thay vì chỉ đọc p95 latency

Những tín hiệu nên có:

| Tín hiệu | Dùng để phát hiện |
| --- | --- |
| Open/active HTTP connections | Socket/file descriptor pressure |
| Active requests, concurrent streams | Long-lived request occupancy |
| Worker busy/queued tasks/rejections | Servlet/JDBC/async pool saturation |
| Event-loop latency | Netty/Undertow I/O thread bị block |
| Heap/direct memory, GC, pooled buffers | Per-client buffer backlog, leak |
| HTTP duration p50/p95/p99 | Tail latency (phân tách short API vs stream) |
| Read/write timeout count | Slow body, stalled response |
| Client disconnect/cancel count | Slow readers, mobile network, deploy |
| 429/503/408/413/502/504 by route/layer | Which limit/timeout đang tác động |
| DB pool active/idle/pending | Downstream resource contention |
| SSE subscription active/backlog/replay | Hot publisher pressure và reconnect storm |
| Load balancer pending/current requests | Edge queue/capacity overload |
| Per-tenant quota rejects | Fairness và policy phù hợp |

Spring Boot Actuator/Micrometer có `http.server.requests` và runtime metrics tùy enabled binders. Với Tomcat, nhiều `tomcat.*` metrics yêu cầu bật:

~~~properties
server.tomcat.mbeanregistry.enabled=true
~~~

và cấu hình Actuator/micrometer phù hợp. `http.server.requests` không phải meter số TCP connections và cũng không tự có per-user labels. **Không thêm userId, sessionId, raw URL vào metric tags** vì tăng cardinality và lộ PII. Dùng route template, status, server instance, outcome và bucket/aggregate hợp lý.

### SLO riêng cho streaming

Một request SSE sống 1 giờ sẽ có duration lớn **theo thiết kế**. Nếu gộp nó vào latency p99 của GET JSON, dashboard báo “API chậm” không có nghĩa controller bị nghẽn. Tạo SLO riêng:
- HTTP short requests: p95/p99 latency và errors.
- SSE/WebSocket: active connections, time-to-first-event, reconnect rate, canceled streams, delivered event lag.
- Upload: bytes/s, time to first byte, completion/abort, oversized rejection.
- Download: throughput, stalled write, canceled transfers.

Access logs thường ghi khi request kết thúc, nên stream đang mở có thể chưa có access entry; theo dõi live gauges.

## 22. Test slow clients: an toàn, có kiểm soát và có mục tiêu

Các bài thử chỉ chạy trên **localhost hoặc staging được phép**, số clients nhỏ và thời lượng ngắn. Không phát kiểu Slowloris với hàng nghìn sockets ra hệ thống của người khác.

### 22.1. Trình tự test

1. Baseline: cURL `/health` latency và HTTP status khi không có tải.
2. Mở hai SSE streams; request thứ ba nhận 503 khi quota đầy; health vẫn 200.
3. Đóng một SSE sớm, xác nhận quota được giải phóng và request tiếp theo có thể nhận stream.
4. Giữ SSE một lúc rồi chờ hết timeout; kiểm tra cleanup, thread/connection counts.
5. Đặt cURL `--limit-rate` cho response và `--max-time` để mô phỏng client đọc chậm; đo blocked writer/buffer nếu có.
6. Thử upload body lớn **hợp lệ** từ client chậm vào staging route có size cap; verify 413/408/close behavior theo proxy/server, không kỳ vọng status nào cũng giống nhau.
7. Test qua public NGINX/ingress route, không chỉ port Spring.
8. Kill một pod/instance trong lúc streams mở; client reconnect với jitter; quan sát backlog/CPU.
9. Đo p95 short API vẫn đạt SLO khi có một số streams hợp lệ.
10. Xem logs/metrics có phân biệt quota reject, timeout và client abort mà không log secrets.

### 22.2. cURL slow-reader demo

~~~bash
curl -N -i --limit-rate 512 --max-time 5 \
  http://localhost:8080/events
~~~

Đây là test **nhẹ**, không chắc làm TCP send buffer đầy vì SSE sample rất nhỏ. Nó chứng minh client có thể đọc chậm, không tự chứng minh server chống Slowloris. Để test slow response rõ, cần endpoint xuất nhiều bytes, đồng thời monitor memory/threads và giới hạn thời gian/phạm vi test.

### 22.3. cURL concurrent requests (minh họa)

Trên Linux/macOS, nếu có `xargs`:

~~~bash
seq 1 12 | xargs -P 12 -I {} \
  curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/work
~~~

Vì `/work` mỗi request mất ~200ms khi được nhận và chỉ có hai slots, dưới tải concurrent có thể quan sát cả 200 và 503. **Số lượng từng status không cố định** do scheduling, network và cách `xargs` khởi tạo processes. Không dùng kết quả một lần để tuyên bố policy đã chống được tấn công slow headers.

### 22.4. Phân biệt tầng tạo lỗi

| Kết quả | Nguồn có thể tạo |
| --- | --- |
| HTTP 429 | App per-user quota hoặc NGINX limit_conn/limit_req được cấu hình 429 |
| HTTP 503 | Application semaphore không còn permits; NGINX mặc định có thể trả 503 khi giới hạn connections |
| HTTP 408 | HTTP server/proxy request timeout, nếu nó chọn trả HTTP response |
| HTTP 413 | Body/request size exceeded |
| HTTP 502/504 | Gateway không connect/đợi upstream, có thể Spring không ghi response tương ứng |
| TCP reset / EOF | Connection bị đóng trước khi HTTP response hình thành; không luôn có status |
| HTTP 200 nhưng stream dừng | Mid-response disconnect/timeout; không thể đổi HTTP status sau khi headers đã commit |

Đừng “sửa” mọi lỗi bằng cách tăng timeouts. Điều đó có thể làm những clients thật dùng được hơn, nhưng cũng làm attacker giữ tài nguyên lâu hơn. Cần đối chiếu reason, backend capacity và route semantics.

## 23. Những anti-pattern phổ biến

| Anti-pattern | Hệ quả | Thay bằng |
| --- | --- | --- |
| Chỉ đặt `keepAliveTimeout=10s` rồi nghĩ chống slow upload | Request active có thể vẫn bị giữ | Body-read/deadline/size/rate limits tại edge |
| Tăng `maxConnections` vô hạn | Socket/heap/FD pressure | Capacity model + quotas + monitoring |
| Tăng `threads.max` mà DB pool vẫn 10 | Threads xếp hàng chờ DB | Bounded concurrency và downstream budgets |
| `Semaphore.acquire()` chờ vô hạn trên request thread | Giữ threads, overload lớn hơn | `tryAcquire` + fast reject |
| Release permit trong controller finally khi trả SSE/Flux | Stream vẫn mở nhưng quota “rỗng” | Lifecycle callbacks hoặc reactive `doFinally` |
| Tạo một thread mới cho mỗi SSE user | Cạn threads khi scale | Shared bounded executor/reactive stream |
| `Flux.onBackpressureBuffer()` không cap | OOM khi slow readers | Bounded queue + overflow policy |
| Drop event nghiệp vụ mà không replay | Mất thông tin, sai state | Durable log/cursor và resync |
| Tắt mọi timeout để “SSE không đứt” | Resource held vô hạn | Heartbeat + quota + absolute TTL + reconnect |
| Dùng IP-only quota khi nhiều user sau NAT | False positives | Edge IP + authenticated user/tenant quotas |
| Tin raw `X-Forwarded-For` để quyết định quota | Attacker giả IP | Trusted gateway strip/overwrite |
| Thiếu jitter sau disconnect đồng loạt | Reconnect storm | Exponential backoff + jitter |
| Response buffer vô hạn cho slow reader | Memory/disk pressure | Bounded buffers/temp disk + close slow clients |
| Tưởng 504 đã hủy DB transaction | Duplicate effects khi retry | Propagate deadline/cancellation, idempotency |
| Gom SSE duration vào HTTP JSON p99 | Dashboard báo latency sai | Stream-specific SLOs |
| Test bằng MockMvc rồi tuyên bố chặn slowloris | Không test TCP parser/proxy/slow reader | Staging network test hợp pháp |

## 24. Checklist áp dụng cho môi trường production

1. Embedded server thực tế là Tomcat, Jetty, Undertow hay Reactor Netty? Có đúng dependency không?
2. Edge/proxy có header/body timeouts, connection caps và chống slow readers không?
3. Timeout nào là *idle giữa operations*, timeout nào là *absolute duration*? Có hiểu rõ?
4. `keep-alive-timeout` có đang bị nhầm với app/request timeout không?
5. Tomcat maxConnections/acceptCount/threads hoặc Jetty/Undertow/Netty config đã được test cùng workload?
6. Có giới hạn request header/body sizes, multipart size và temp disk không?
7. Request queues, executor queues, outbound connection pools có bounded không?
8. Tác vụ tốn CPU/DB có admission control, timeout, cancel và 429/503 policy?
9. SSE/WebSocket/long-poll có active quota per node/user/tenant và cleanup khi disconnect?
10. Producer streaming có bounded buffer/backpressure/replay semantics rõ?
11. Reconnect có backoff+jitter và có thể resume/resync nếu mất events không?
12. TLS/HTTP2/H3 limits và proxy-hop timeouts có được cấu hình nhất quán không?
13. CORS/authentication/authorization có áp dụng đúng cho long-lived streams và khi user bị revoke?
14. Có theo dõi open sockets, FD, busy threads, Netty event-loop, direct memory và DB pool?
15. Có test slow body/slow read/long streams ở staging qua **public route**, không chỉ localhost?
16. Có phân biệt gateway timeout vs origin timeout trong logs/metrics không?
17. Có chống leak credentials/PII trong logs, X-Forwarded-* trust và metric cardinality không?
18. Có kế hoạch rolling deploy/draining, idle stream cleanup và load-shedding không?
19. Có capacity plan tính đến burst/p99, không chỉ average RPS?
20. Mọi số timeout/capacity có theo SLO sản phẩm và dữ liệu đo thật, không copy lab mặc định?

## 25. Bài tập tự kiểm tra

**1.** Một client mở kết nối keep-alive nhưng không gửi request mới. `keepAliveTimeout` dùng để làm gì?

**Đáp án:** Đặt thời gian chờ HTTP request **kế tiếp** trên persistent connection, sau đó có thể đóng connection. Nó không tự tạo deadline cho download đang chạy.

**2.** Vì sao Slowloris có thể làm server gặp vấn đề dù mỗi IP có RPS rất thấp?

**Đáp án:** Nó giữ nhiều connections/HTTP parser states bằng cách gửi headers rất chậm, không cần tạo nhiều completed HTTP requests.

**3.** `client_body_timeout=10s` ở NGINX có đảm bảo upload tối đa 10 giây không?

**Đáp án:** Không. Nó liên quan khoảng chờ giữa operations đọc body. Một client gửi liên tục với tốc độ rất nhỏ có thể vượt qua; cần thêm total deadline/size/minimum rate nếu phù hợp.

**4.** Tomcat `max-connections=100` có đồng nghĩa server sẽ luôn trả HTTP 503 cho request thứ 101 không?

**Đáp án:** Không. Socket backlog/OS behavior có thể timeout/refuse; HTTP status chỉ hình thành khi request được xử lý đủ để tạo response.

**5.** `server.undertow.no-request-timeout` có giới hạn tổng thời gian một file download đang gửi không?

**Đáp án:** Không. Nó nhằm connection idle **không xử lý request**; cần response write policy/stream lifetime riêng.

**6.** Spring MVC `SseEmitter` trả từ controller rồi, có thể release stream semaphore ngay không?

**Đáp án:** Không. HTTP response vẫn đang mở; release trên completion/timeout/error/disconnect cleanup idempotent.

**7.** Spring WebFlux `Flux` có bảo đảm producer hot không bao giờ OOM khi browser đọc chậm không?

**Đáp án:** Không. Backpressure cần producer cooperates; hot sources/buffers có thể overflow. Cần bounded strategy và event semantics.

**8.** NGINX `limit_req` có đủ chặn một user mở hàng trăm SSE streams không?

**Đáp án:** Không. `limit_req` quản lý rate requests, còn streams giữ lâu cần `limit_conn`/per-user active quotas và HTTP2 stream budgets.

**9.** Một stream SSE gửi heartbeat mỗi 20 giây, proxy_read_timeout=60s. Stream có tự đóng sau 60 giây không?

**Đáp án:** Không nhất thiết. Proxy đọc bytes liên tục trước idle threshold nên timeout có thể reset. Muốn lifetime tối đa, đặt stream absolute TTL và reconnect/re-auth policy.

**10.** Gateway trả 504 sau 30s. SQL transaction trên Spring chắc chắn đã dừng chưa?

**Đáp án:** Không. Gateway timeout không mặc nhiên cancel DB transaction. Cần phối hợp deadlines/cancellation/idempotency.

**11.** Bật Java 21 virtual threads có loại bỏ rủi ro socket/DB pool starvation không?

**Đáp án:** Không. Virtual threads thay concurrency execution model, không tăng số FD/DB connections vô hạn; app quotas vẫn quan trọng.

**12.** Vì sao cần tách HTTP latency metrics khỏi SSE stream duration?

**Đáp án:** Stream dài là đúng design; trộn vào JSON API p99 tạo tín hiệu sai. Đo active streams/event lag/reconnect riêng.

## 26. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): Tomcat maxConnections, threads, acceptCount, connection/keepAlive timeouts; Jetty idle/connection limits; Undertow no-request-timeout, worker; Netty idle/keepAlive.
- [Spring Boot 3.3 – Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): async executor, bounded queues, virtual threads và MVC async integration.
- [Apache Tomcat 10.1 – HTTP Connector](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html): connectionTimeout, keepAliveTimeout, maxConnections, acceptCount, maxKeepAliveRequests, upload timeouts.
- [Spring Framework – MVC Asynchronous Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): SseEmitter, blocking writes, lifecycle callbacks, disconnect handling, async executor.
- [Spring Framework – WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): nonblocking I/O, Reactive Streams backpressure, DataBuffer/codec behavior.
- [Reactor Netty – HTTP Server](https://projectreactor.io/docs/netty/release/reference/http-server.html): idle timeout và server-side read/request timeouts theo Reactor Netty version.
- [NGINX – HTTP Proxy Module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): proxy_request_buffering, proxy_buffering, proxy_read/send/connect_timeout.
- [NGINX – HTTP Core Module](https://nginx.org/en/docs/http/ngx_http_core_module.html): client_header_timeout, client_body_timeout, send_timeout, keepalive_timeout.
- [NGINX – Connection Limiting](https://nginx.org/en/docs/http/ngx_http_limit_conn_module.html): limit_conn_zone, limit_conn, giới hạn với HTTP/2/3 và điều kiện request headers đã đọc.
- [Spring Boot 3.3 – Actuator Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html): http.server.requests, Tomcat metrics và monitoring.
- [Reactor Core – Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): lifecycle/cancellation/backpressure operators.
- [RFC 9112 – HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): HTTP framing, connections và message processing.
- [RFC 9113 – HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): multiplexing, concurrent streams, flow control.

**Ghi nhớ:** đừng cố “chặn client chậm” chỉ bằng một timeout hoặc tăng threads. Cần **timeout theo từng giai đoạn, giới hạn socket/streams/worker/queue, streaming backpressure, quota theo identity, bảo vệ ở proxy và đo lường cả request đang mở**. Client bình thường phải được phục vụ trong ngân sách đã định; client chậm quá mức được từ chối hoặc đóng có chủ đích mà không kéo sập cả hệ thống.
