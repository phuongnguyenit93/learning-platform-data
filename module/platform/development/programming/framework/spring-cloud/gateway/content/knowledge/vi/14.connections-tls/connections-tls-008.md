# Keep-alive, thời gian nhàn rỗi và vòng đời kết nối

## 1. Tại sao kết nối lại là một phần của kiến trúc API Gateway?

Trong hệ thống microservices, **Spring Cloud Gateway** thường nhận nhiều request từ ứng dụng web, mobile và các service nội bộ, rồi chuyển tiếp chúng đến backend thông qua route predicate, filter chain, biến đổi URL/header và service discovery. Mỗi request đều cần một kết nối mạng hoặc sử dụng lại kết nối đã có. Nếu Gateway liên tục mở kết nối TCP/TLS mới, chi phí handshake, cấp phát socket và quản lý tài nguyên có thể trở thành nút nghẽn. Ngược lại, nếu giữ kết nối quá lâu, Gateway có thể tái sử dụng socket đã bị load balancer, proxy hoặc backend đóng từ trước.

Ba câu hỏi vận hành cần trả lời:

1. Khi nào một kết nối được **tái sử dụng** thay vì mở mới?
2. Sau bao lâu **không hoạt động**, kết nối được giữ lại hoặc bị đóng?
3. Khi instance backend thay đổi, client ngắt kết nối, TLS lỗi hoặc Gateway shutdown, **vòng đời kết nối** kết thúc như thế nào?

Đây là trọng tâm của bài **“Keep-alive, thời gian nhàn rỗi và vòng đời kết nối”** thuộc chương **Kết nối và TLS**. Bài tập trung vào **Spring Cloud Gateway Server WebFlux** sử dụng Reactor Netty; các ví dụ cấu hình cần được đối chiếu với đúng dòng Spring Cloud Gateway/Spring Boot đang triển khai.

Sau bài học, bạn có thể:

- Phân biệt **HTTP persistent connection**, **TCP SO_KEEPALIVE** và **connection pool**.
- Mô tả hai kết nối độc lập ở hai phía Gateway, bao gồm chi phí TCP/TLS.
- Phân biệt `maxIdleTime`, `maxLifeTime`, thời gian chờ lấy kết nối, connect timeout, response timeout và timeout của proxy bên ngoài.
- Cấu hình pool outbound của Gateway, chọn giới hạn tài nguyên và kiểm chứng kết quả.
- Giải thích rủi ro **stale pooled connection**, SSE/WebSocket dài hạn, service discovery và graceful shutdown.
- Quan sát active/idle/pending connections, lỗi mạng, độ trễ và tình trạng nghẽn pool để vận hành API Gateway an toàn.

## 2. Ba khái niệm “keep-alive” dễ bị nhầm

### 2.1. HTTP keep-alive: tái sử dụng kết nối cho nhiều request

Với **HTTP/1.1**, một kết nối TCP thường là **persistent theo mặc định**: sau khi server trả xong response, hai bên có thể sử dụng lại kết nối nếu giao thức, header, độ dài body và trạng thái socket cho phép. Nếu một bên gửi `Connection: close`, nó thể hiện ý định đóng kết nối sau khi hoàn tất trao đổi phù hợp.

~~~text
HTTP/1.1, cùng một TCP connection:

Client ---- GET /items/1 --------> Server
Client <--- 200 + response ------ Server
Client ---- GET /items/2 --------> Server
Client <--- 200 + response ------ Server
         (kết nối được tái sử dụng)
~~~

Ở **HTTP/2**, nhiều HTTP stream có thể chia sẻ và multiplex trên một kết nối. Không áp dụng cách sử dụng header `Connection: keep-alive` của HTTP/1.1 cho HTTP/2: các connection-specific header như `Connection` bị cấm theo quy tắc HTTP/2. HTTP/2 còn có cơ chế quản lý stream, frame và flow control; việc một stream kết thúc **không đồng nghĩa** kết nối TCP phải đóng.

### 2.2. TCP keepalive: probe phát hiện peer không còn reachable

**TCP keepalive** là tính năng ở tầng socket, thường được điều khiển bằng `SO_KEEPALIVE` cùng các tham số hệ điều hành. Sau khoảng thời gian không có dữ liệu, hệ thống có thể gửi probe để phát hiện kết nối không còn hoạt động. Nó **không phải** điều kiện bảo đảm tái sử dụng HTTP connection, không phải cơ chế pool và cũng không bảo đảm mọi middlebox đều giữ mapping NAT.

Các tham số TCP keepalive có thể có mặc định rất dài hoặc do OS/container chi phối. Nếu cần phát hiện lỗi trong thời gian ngắn cho workload thực tế, phải kiểm tra cấu hình và hỗ trợ của **OS, socket, proxy, giao thức ứng dụng**; bật một cờ keepalive không đồng nghĩa lỗi sẽ được phát hiện trong vài giây.

### 2.3. Connection pooling: quản lý các kết nối outbound đã mở

Reactor Netty HTTP client có thể sử dụng **connection pool** để tái sử dụng TCP/TLS connection đến upstream. Pool quản lý số kết nối đang được sử dụng, các kết nối nhàn rỗi có thể dùng lại và các yêu cầu đang chờ khi chạm giới hạn.

~~~mermaid
flowchart TD
    R[Request cần gọi backend] --> Q{Có kết nối idle phù hợp?}
    Q -->|Có| Reuse[Tái sử dụng kết nối]
    Q -->|Không| Cap{Còn capacity mở mới?}
    Cap -->|Có| New[TCP connect + TLS nếu HTTPS]
    Cap -->|Không| Pending[Chờ lấy connection từ pool]
    Pending -->|Được cấp trước deadline| Reuse
    Pending -->|Hết deadline| Err[Acquire timeout / request failure]
    Reuse --> Work[Gửi request và đọc response]
    New --> Work
    Work --> Done{Connection còn tái dùng được?}
    Done -->|Có| Idle[Trả về pool để chờ reuse]
    Done -->|Không| Close[Đóng / loại connection]
~~~

Ba khái niệm bổ sung cho nhau nhưng **không tương đương**:

| Cơ chế | Tầng xử lý | Mục đích |
| --- | --- | --- |
| HTTP keep-alive/persistence | HTTP/1.1 hoặc lifecycle kết nối của HTTP/2 | Cho phép nhiều HTTP exchange dùng chung kết nối |
| TCP keepalive | TCP/OS | Probe một kết nối có thể đã mất peer |
| Connection pooling | Reactor Netty HTTP client | Tái sử dụng, giới hạn và quản lý vòng đời kết nối tới upstream |

## 3. Gateway có hai phía kết nối độc lập

Gateway là một HTTP server đối với client, nhưng là HTTP client đối với backend. Với route proxy thông thường, đó là **hai chặng mạng khác nhau**:

~~~mermaid
flowchart LR
    Client[Browser / Mobile] -->|TCP/TLS A| Gateway[Spring Cloud Gateway]
    Gateway -->|TCP/TLS B, pooled| Inventory[Inventory service]
    Gateway -->|TCP/TLS C, pooled| Orders[Orders service]
~~~

- **Kết nối inbound (client → Gateway):** do HTTP server, ingress/load balancer phía trước và client điều khiển. Client có thể sử dụng HTTP/1.1 hoặc HTTP/2 tùy hỗ trợ và cấu hình.
- **Kết nối outbound (Gateway → backend):** do HTTP client mà Gateway dùng để proxy, route URI, Reactor Netty connection pool, mạng và backend điều khiển.
- **TLS termination:** TLS ở hop A và TLS ở hop B là các phiên bảo mật riêng. Client dùng HTTPS **không tự động** có nghĩa Gateway dùng HTTPS tới backend.
- **Đóng một hop không đồng nghĩa đóng ngay hop còn lại:** khi client ngắt kết nối, Gateway thường có cơ chế hủy công việc reactive; nhưng tiến trình đóng socket, hoàn tất upstream I/O và trả kết nối về pool phụ thuộc trạng thái protocol và cancellation.

Ví dụ: 1.000 client giữ kết nối tới Gateway **không nhất thiết** tạo 1.000 TCP connection tới Inventory. Gateway có thể sử dụng một số lượng connection outbound nhỏ hơn để phục vụ các request diễn ra theo thời gian. Ngược lại, 100 request upstream kéo dài cùng lúc có thể cần nhiều kết nối HTTP/1.1 đang hoạt động, tùy mức ghép kênh và đặc tính connection pool.

**Quan sát hai phía riêng biệt.** Timeout tại ingress, idle timeout của Netty server, pool outbound, timeout ở service và chính sách keep-alive của sidecar không phải cùng một thông số.

## 4. Vòng đời một kết nối outbound

Một kết nối HTTP(S) phía Gateway có thể đi qua các giai đoạn:

~~~mermaid
stateDiagram-v2
    [*] --> ChuaCoKetNoi
    ChuaCoKetNoi --> DangKetNoi: Acquire không có connection tái dùng
    DangKetNoi --> TLS: TCP connect thành công, HTTPS
    DangKetNoi --> DangDung: TCP connect thành công, HTTP
    TLS --> DangDung: Handshake + certificate validation OK
    DangDung --> NhanRoi: HTTP exchange kết thúc, connection tái dùng được
    NhanRoi --> DangDung: Acquire để tái sử dụng
    NhanRoi --> Dong: Idle/lifetime eviction hoặc peer đóng
    DangDung --> Dong: Lỗi mạng, protocol hoặc không thể reuse
    TLS --> Dong: TLS handshake thất bại
    DangKetNoi --> Dong: Connect timeout / failure
    Dong --> [*]
~~~

Đây là **mô hình khái niệm**, không phải chính xác mọi trạng thái nội bộ của Reactor Netty. HTTP/2 có thể phục vụ nhiều stream trên cùng kết nối; kết thúc một stream không giống việc toàn bộ connection trở về idle.

Trong môi trường có pool:

1. Gateway chuẩn bị URL đích từ route, ví dụ `lb://inventory-service` được giải quyết thành instance cụ thể.
2. HTTP client cần acquire một connection tương thích với endpoint/protocol/TLS configuration.
3. Nếu có connection nhàn rỗi dùng được, client có thể tái sử dụng; nếu không, pool có thể mở mới nếu còn capacity.
4. Kết nối mới có thể phải TCP handshake, rồi TLS handshake nếu backend dùng HTTPS.
5. HTTP request/response chạy trên kết nối.
6. Khi exchange kết thúc, connection **nếu còn sử dụng được** có thể quay lại pool; nếu không thì đóng.
7. Khi idle lâu, đạt giới hạn tuổi thọ hoặc pool bị dispose, connection có thể bị loại.

Không giả định **mỗi request sẽ tạo một kết nối** hoặc **mọi request luôn dùng lại kết nối cũ**. Sự tái sử dụng phụ thuộc phiên bản, pool key, endpoint được chọn, connection state, HTTP protocol, proxy và remote close.

## 5. Những timeout khác nhau trong cùng một request

“Timeout” là tên chung cho nhiều đồng hồ bắt đầu và kết thúc ở các thời điểm khác nhau.

| Thông số/khái niệm | Bắt đầu ở đâu? | Tình huống nó giới hạn |
| --- | --- | --- |
| **Pool acquire timeout** | Khi request cần lấy connection outbound từ pool | Chờ quá lâu do pool đầy hoặc thiếu connection |
| **TCP connect timeout** | Khi mở socket mới tới backend | Không thiết lập được TCP connection đúng hạn |
| **TLS handshake timeout** | Khi bắt đầu TLS handshake trên kết nối bảo mật | Không thương lượng/xác minh TLS đúng thời hạn |
| **HTTP response timeout** | Khi HTTP client chờ response theo semantics của phiên bản API | Backend chậm hoặc không tạo tiến triển như policy cho phép |
| **Read/write timeout** | Trong hoạt động I/O nếu được cấu hình | Đọc hoặc ghi dữ liệu không tiến triển theo điều kiện timeout |
| **Pool max idle time** | Khi connection không được dùng và nằm trong pool | Connection rảnh quá lâu, không nên giữ để reuse |
| **Pool max life time** | Tính từ lúc connection được tạo | Hạn chế tái dùng connection quá cũ |
| **Ingress/LB idle timeout** | Do proxy bên ngoài quản lý | Cắt kết nối không có hoạt động đủ lâu |
| **Client deadline** | Khi client bắt đầu một tác vụ | Giới hạn thời gian end-to-end do client quyết định |

Đặc biệt:

- **max idle time của pool không phải response timeout.** Một backend đang stream dữ liệu có connection *in-use*; thông số idle của pool không nên được coi là cơ chế tự cắt stream sau một khoảng thời gian nhàn rỗi giữa hai sự kiện.
- **max life time không phải deadline cho từng request.** Nó thường chi phối khả năng giữ/tái sử dụng connection trong pool. Khi một exchange dài đang chạy, chính sách disposal và HTTP client cụ thể quyết định cách xử lý, không nên mặc định timer sẽ ngắt exchange đúng ở mốc tuổi thọ.
- **Connect timeout không giới hạn thời gian chờ lấy connection từ pool.** Nếu pool bão hòa, request có thể chờ acquire trước khi có cơ hội connect.
- **Response timeout không bao trùm mọi latency end-to-end.** Tổng thời gian còn gồm route selection, filter, acquire, DNS, connect, TLS, upstream processing, streaming, downstream write và proxy khác.

### Dòng thời gian một request chưa có connection để reuse

~~~text
Request vào Gateway
  |-- Route + GatewayFilter
  |-- Acquire trong pool (có thể chờ)
  |-- DNS / TCP connect (nếu mở mới)
  |-- TLS handshake (nếu HTTPS)
  |-- Ghi HTTP request
  |-- Chờ + nhận HTTP response
  |-- Ghi response tới client
  |-- Hoàn tất, connection có thể được trả vào pool
~~~

Vì có nhiều đồng hồ độc lập, một request có thể thất bại **trước khi gọi backend**, ví dụ acquire timeout, hoặc **sau khi đã gửi request**, ví dụ response timeout. Phân biệt chúng giúp tránh retry sai hoặc tăng timeout mà không giải quyết nguyên nhân.

## 6. Chọn giới hạn pool và thời gian nhàn rỗi theo tải thực

Reactor Netty có cơ chế connection pooling cho HTTP client. Khi cấu hình một pool **fixed/bounded**, ba tham số đáng quan tâm là:

| Tham số | Công dụng | Rủi ro khi đặt sai |
| --- | --- | --- |
| `max-connections` | Giới hạn số connection được cấp cho một pool/destination theo implementation | Quá thấp: chờ acquire; quá cao: tốn socket/CPU/TLS, gây quá tải upstream |
| `acquire-timeout` | Thời gian tối đa chờ connection khả dụng trong trường hợp pool phải xếp hàng | Quá ngắn: lỗi khi burst; quá dài: request bị treo trong hàng đợi |
| `max-idle-time` | Giới hạn idle để không tiếp tục tái sử dụng connection cũ | Quá dài: dễ lấy trúng connection mà peer/NAT đã đóng; quá ngắn: mở connection mới liên tục |
| `max-life-time` | Giới hạn tuổi thọ connection trước khi ngừng reuse | Quá ngắn: chi phí handshake cao; quá dài: giữ state rất cũ |
| `eviction interval` | Chu kỳ chủ động xem xét loại connection không còn đủ điều kiện | Không phải thời điểm tuyệt đối mà mọi connection sẽ bị đóng |
| **Pending acquire limit** | Giới hạn số request chờ connection nếu được cấu hình | Không giới hạn: nguy cơ hàng đợi tăng cùng áp lực bộ nhớ |

### Vì sao không có một kích thước pool đúng cho mọi Gateway?

Giả sử một upstream nhận trung bình **300 request/giây**, mỗi request HTTP/1.1 cần giữ connection khoảng **200 ms**. Với tải ổn định và không có multiplexing, số request đang xử lý đồng thời xấp xỉ:

~~~text
Concurrency trung bình ≈ throughput × latency
                       ≈ 300 request/s × 0,2 s
                       ≈ 60 request đồng thời
~~~

Đây là ứng dụng trực giác từ định luật Little cho hệ thống ổn định; **không phải công thức tự chọn pool = 60**. Khi tải theo burst, latency p95/p99, retry, SSE và nhiều backend endpoint được tính vào, mức cần thiết có thể khác đáng kể. HTTP/2 multiplexing còn khiến quan hệ giữa số request đồng thời và số TCP connection khác HTTP/1.1.

Điều cần đo thực tế: active connections, idle connections, pending acquires, pending wait time, acquire failures, request latency, CPU, file descriptors, TLS handshakes, error rate và giới hạn tài nguyên tại backend.

### Đặt idle timeout trong chuỗi proxy

Nếu backend hoặc network load balancer có chính sách đóng connection idle sau một khoảng ngắn, giữ connection trong pool lâu hơn có thể khiến Gateway tìm thấy **stale connection**. Vì vậy nên xem xét đặt **max idle của pool ngắn hơn ngưỡng idle của peer/middlebox**, để có thời gian dự phòng và giảm rủi ro reuse sau khi remote đã đóng.

Đây là **nguyên tắc kinh nghiệm**, không phải bảo đảm tránh mọi stale socket. Race condition vẫn có thể xảy ra giữa lúc pool kiểm tra connection và khi nó gửi byte đầu tiên. Cần kiểm chứng dưới traffic, load balancer và hạ tầng mạng thật.

## 7. Cấu hình connection pool HTTP client của Gateway Server WebFlux

Ví dụ minh họa dùng namespace cấu hình **Spring Cloud Gateway Server WebFlux** của các dòng mới:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            connect-timeout: 3000
            response-timeout: 10s
            pool:
              type: fixed
              max-connections: 150
              acquire-timeout: 3000
              max-idle-time: 20s
              max-life-time: 5m
              eviction-interval: 30s
~~~

**Ý nghĩa dự kiến của cấu hình:**

- `connect-timeout: 3000` minh họa timeout TCP connect theo **mili giây** ở các dòng Gateway thường gặp.
- `response-timeout: 10s` đặt ngưỡng theo Duration. Semantics timeout response cụ thể cần kiểm tra ở bản Gateway/Reactor Netty.
- `type: fixed` chọn pool có giới hạn số connection.
- `max-connections: 150` là mức pool được khai báo cho ví dụ, **không khẳng định giới hạn kết nối tổng trên mọi service hay mọi Gateway replica**.
- `acquire-timeout: 3000` minh họa thời gian chờ acquire theo mili giây trong các dòng property có quy ước đó.
- `max-idle-time: 20s` giới hạn thời gian connection rảnh có thể tiếp tục được tái sử dụng.
- `max-life-time: 5m` giới hạn tuổi connection dùng cho pool.
- `eviction-interval: 30s` minh họa chu kỳ xem xét eviction chủ động nếu release hỗ trợ.

**Đây là các giá trị học tập, không phải cấu hình mặc định và không phải lời khuyên áp thẳng lên production.** Tên thuộc tính, loại dữ liệu và namespace có thể khác theo phiên bản. Ở một số Spring Cloud Gateway WebFlux trước đây, prefix là `spring.cloud.gateway.httpclient` thay vì `spring.cloud.gateway.server.webflux.httpclient`. Từng property như eviction interval hoặc pool type phải được kiểm tra trong metadata/tài liệu cấu hình của đúng release, đồng thời cần xác minh giá trị **đã thực sự bind**, không chỉ YAML hợp lệ.

Ví dụ route kết hợp load balancing:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: inventory-route
              uri: lb://inventory-service
              predicates:
                - Path=/api/inventory/**
              filters:
                - StripPrefix=2
~~~

Load balancing phân giải `lb://inventory-service` thành URL instance. Pool outbound áp vào quá trình gọi HTTP phù hợp với đích đã chọn, nhưng **không tự thay thế Spring Cloud LoadBalancer, service discovery hoặc readiness**. Nếu một service có nhiều instance, connections có thể phân bố trên nhiều destination; không nên cộng nhầm một `max-connections` thành giới hạn tuyệt đối của mọi backend trong toàn cụm.

**Bảo mật TLS:** khi upstream dùng HTTPS, hãy cấu hình truststore/certificate validation và mTLS nếu cần. Không tắt xác minh chứng chỉ chỉ để xử lý lỗi stale connection hay handshake timeout.

## 8. Reactor Netty ConnectionProvider: hiểu API phía dưới

Spring Cloud Gateway Server WebFlux sử dụng Reactor Netty cho hoạt động proxy HTTP thông thường. **ConnectionProvider** là thành phần quản lý pool trong Reactor Netty HTTP client. Để hiểu ý nghĩa cấu hình, xem ví dụ Java độc lập:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

class ReactorNettyPoolExample {

    static HttpClient createSampleClient() {
        ConnectionProvider provider = ConnectionProvider.builder("sample-upstream")
                .maxConnections(150)
                .maxIdleTime(Duration.ofSeconds(20))
                .maxLifeTime(Duration.ofMinutes(5))
                .pendingAcquireTimeout(Duration.ofSeconds(3))
                .evictInBackground(Duration.ofSeconds(30))
                .build();

        return HttpClient.create(provider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3000)
                .responseTimeout(Duration.ofSeconds(10))
                .keepAlive(true);
    }
}
~~~

Điểm cần hiểu:

- `ConnectionProvider.builder(...).maxConnections(...)` giới hạn capacity của pool theo cách Reactor Netty phân nhóm connection. Đây không phải limit HTTP request/s.
- `maxIdleTime(...)` và `maxLifeTime(...)` kiểm soát điều kiện connection còn phù hợp để tái sử dụng.
- `pendingAcquireTimeout(...)` giới hạn thời gian request chờ connection khi pool không cấp được ngay.
- `evictInBackground(...)` yêu cầu cơ chế xem xét loại bỏ connection theo chu kỳ nếu được API/version hỗ trợ.
- `CONNECT_TIMEOUT_MILLIS` áp dụng cho TCP connect của **connection mới**, không thay thế acquire timeout.
- `responseTimeout(...)` liên quan đến chờ response sau khi request đã đi vào quá trình HTTP; khác pool idle.
- `keepAlive(true)` ở đây liên quan HTTP persistent connection, **không phải** cấu hình hệ điều hành `SO_KEEPALIVE`.

> **Quan trọng:** Phương thức `createSampleClient()` ở trên chỉ tạo **một HttpClient độc lập**; nó **không tự động cấu hình HTTP client của Spring Cloud Gateway**. Muốn dùng custom client trong ứng dụng Gateway phải tích hợp bằng extension point phù hợp với phiên bản thực tế hoặc ưu tiên property cấu hình được Gateway hỗ trợ. Đừng tạo một HttpClient trong filter cho từng request: điều đó dễ phá reuse, tăng tài nguyên và làm rò rỉ pool.

Ngoài ra, khi tự quản lý một `ConnectionProvider` riêng, ứng dụng phải có kế hoạch **dispose resource** trong vòng đời ứng dụng. Đừng dispose sau từng request, và cũng đừng giả định Spring sẽ thu hồi một provider do bạn tự tạo mà không đăng ký lifecycle.

## 9. Idle ở phía inbound không phải idle ở pool outbound

Đường Client → Gateway có các timeout/giới hạn khác với Gateway → backend:

| Vị trí | Thành phần có thể quyết định timeout | Ví dụ ảnh hưởng |
| --- | --- | --- |
| Browser/mobile | Client HTTP stack | Client đóng kết nối khi không còn yêu cầu hoặc hết deadline |
| CDN/WAF | Edge proxy | Đóng keep-alive hoặc cắt luồng không hoạt động |
| Ingress / Load Balancer | Reverse proxy | Idle timeout, read/write timeout, connection draining |
| Gateway HTTP server | Reactor Netty server/Spring Boot config | Idle, header/body receive limits, server keep-alive policy |
| Gateway HTTP client | Reactor Netty pool và HTTP client | Acquire, connect, response và pool idle/lifetime |
| Sidecar / service mesh | Proxy ở hop nội bộ | Keep-alive, connection draining và idle timeout riêng |
| Backend HTTP server | Server/framework của service | Max idle connection, request/read timeout |

Một cách xử lý sai là thấy ingress đóng kết nối sau một phút không có dữ liệu rồi tăng **pool max-idle-time** của Gateway. Tham số đó có thể không ảnh hưởng chút nào đến kết nối **client → ingress** đang bị đóng.

### Keep-alive không bảo đảm một kết nối tồn tại mãi

HTTP keep-alive chỉ cho phép reuse nếu connection còn hợp lệ. Remote peer có quyền đóng connection theo chính sách tài nguyên. Load balancer có thể chủ động đóng connection lâu không hoạt động; server có thể giới hạn số request trên một connection hoặc thực hiện graceful shutdown.

Các header HTTP/1.1 như `Connection: keep-alive` hoặc `Keep-Alive: timeout=...` có thể cung cấp gợi ý nhưng không phải hợp đồng cưỡng chế mọi proxy/backend giữ socket đúng từng giây. Một bên có thể đóng sớm hơn, và HTTP/2 không dùng `Connection` header kiểu HTTP/1.1.

### Đừng xử lý mọi idle timeout như một lỗi

Một connection **idle đã hoàn tất request** được đóng chủ động là hành vi bình thường. Lỗi thực sự là:

- Đóng trong khi request/response vẫn đang truyền trái mong đợi.
- Gateway tái sử dụng connection đã bị đóng và request thất bại.
- Connection mới liên tục được mở khiến CPU/TLS handshake tăng mạnh.
- Pool giữ quá nhiều socket nhàn rỗi làm cạn file descriptors hoặc tài nguyên của service.

Để kết luận, cần gắn sự kiện đóng connection với thời điểm HTTP exchange và metric pool, không chỉ nhìn các dòng debug `channel inactive`.

## 10. Stale connection và cuộc đua với load balancer

**Stale connection** là một connection mà pool vẫn có thể xem là ứng viên tái sử dụng, trong khi peer hoặc middlebox đã đóng hoặc sắp đóng nó. Ví dụ:

~~~mermaid
sequenceDiagram
    participant Gateway as Gateway pool
    participant LB as Network load balancer
    participant S as Backend
    Gateway->>LB: TCP/TLS connection established
    LB->>S: Connection to backend
    Gateway->>LB: GET /items/1
    S-->>Gateway: 200 response
    Note over Gateway,LB: Connection idle
    LB-->>Gateway: Idle connection closed / mapping expired
    Note over Gateway: Pool may not yet observe remote close
    Gateway->>LB: Attempt reuse for GET /items/2
    LB-->>Gateway: Reset / close / I-O failure
~~~

Vấn đề có thể biểu hiện thành `PrematureCloseException`, connection reset, EOF hoặc lỗi I/O khác. **Không phải mọi lỗi 502 hoặc 503 là stale connection**; cần đối chiếu log, timing và hạ tầng thực tế.

Các biện pháp thực tế:

1. **Biết idle timeout ở peer/middlebox.** Nếu mạng đóng ở mốc ngắn, điều chỉnh pool max idle ngắn hơn một cách có dự phòng.
2. **Eviction phù hợp.** Thời gian kiểm tra eviction giúp loại bớt connection lâu không dùng; không thể loại bỏ mọi race.
3. **Theo dõi lỗi reuse.** Phân biệt lỗi trên connection cũ với lỗi TCP connect/TLS trên connection mới nếu telemetry có đủ thông tin.
4. **Retry có điều kiện.** Chỉ retry khi phù hợp hợp đồng idempotency/deadline và hiểu request đã có thể tới backend trước khi connection lỗi.
5. **Readiness/draining.** Khi upstream instance sắp bị thay, dừng đưa traffic mới rồi đóng connection theo lộ trình, hạn chế request gửi tới instance đang tắt.
6. **Không đặt tất cả timeout cực ngắn.** Giá trị quá ngắn tạo connection churn và handshake load; cần đo hiệu quả thực tế.

### Tại sao retry một POST không hẳn an toàn?

Giả sử Gateway gửi `POST /orders`, backend tạo đơn nhưng socket đóng trước khi response tới Gateway. Gateway có thể nghĩ request thất bại, nhưng **tác dụng phụ đã xảy ra**. Tự động retry sang connection/instance khác có nguy cơ tạo đơn thứ hai.

Với thao tác có side effect, hãy dùng **idempotency key**, storage/deduplication ở backend và chính sách retry có giới hạn. Load balancing hoặc keep-alive không giải quyết được vấn đề “đã xử lý nhưng mất phản hồi”.

## 11. TLS handshake, tái sử dụng kết nối và đổi chứng chỉ

Kết nối HTTPS mới cần TCP connect rồi TLS handshake. Khi reuse **cùng một kết nối TLS đang mở**, những HTTP request tiếp theo có thể chạy trên cùng phiên kết nối mà không cần thương lượng TLS lại từ đầu cho mỗi request. Điều này giúp giảm CPU, độ trễ handshake và số lần kiểm tra certificate chain.

~~~text
Kết nối HTTPS mới:
  DNS -> TCP connect -> TLS handshake -> HTTP request/response

Tái sử dụng cùng kết nối HTTPS:
  Dùng TCP/TLS connection còn mở -> HTTP request/response
~~~

Đừng nhầm **connection reuse** với **TLS session resumption**. Resumption là khả năng một **kết nối TLS mới** tái sử dụng thông tin phiên bảo mật trước đó theo điều kiện giao thức/server/client, giúp giảm chi phí handshake; nó không biến kết nối TCP đã đóng thành kết nối còn mở.

### Vòng đời chứng chỉ và connection dài hạn

Chứng chỉ thường được kiểm tra trong quá trình **TLS handshake**. Một connection TLS đã mở từ trước không nhất thiết kiểm tra lại chứng chỉ ở mọi HTTP request trên connection đó. Khi backend xoay vòng chứng chỉ, truststore hoặc cấu hình mTLS:

- **Connection hiện hữu** có thể tiếp tục hoạt động cho tới khi bị đóng theo chính sách/protocol.
- **Connection mới** có thể dùng certificate mới và phải vượt qua quá trình xác minh tương ứng.
- Pool max life/idle và graceful draining có thể ảnh hưởng thời gian connection cũ còn được dùng lại.
- Cần bảo đảm truststore và cấu hình TLS client được làm mới theo cơ chế hệ thống đang hỗ trợ; chỉ đổi file trên đĩa không bảo đảm đối tượng SSL đang chạy sẽ tự reload.

Không dùng `max-life-time` làm cam kết “sau đúng 5 phút tất cả TLS certificate đều được kiểm tra lại”. Đây là policy lifecycle của pool, không phải chính sách vòng đời chứng chỉ độc lập.

### Khi gặp lỗi TLS

Các lỗi như certificate expired, hostname mismatch, unknown CA hoặc lỗi bắt tay TLS xảy ra **trước khi một request HTTP(S) mới truyền được bình thường**. Đừng sửa chúng bằng cách chuyển sang HTTP hoặc tắt xác minh. Kiểm tra scheme backend được chọn, tên host/IP của `ServiceInstance`, chứng chỉ, truststore, cổng TLS, thời hạn chứng chỉ và thời gian hệ thống.

## 12. SSE, NDJSON, streaming và WebSocket: kết nối dài nhưng không “idle” đơn giản

Các API thông thường có request/response ngắn, nên pool có thể nhận lại connection nhanh. Nhưng một số loại traffic **giữ connection hoặc HTTP stream lâu**:

| Traffic | Đặc điểm vòng đời | Điểm dễ sai |
| --- | --- | --- |
| JSON request/response ngắn | Hoàn tất nhanh rồi có thể trả connection về pool | Pool bị thiếu capacity khi burst |
| Download lớn | Response có thể truyền trong thời gian dài | Read/response timeout quá ngắn làm ngắt tải xuống |
| SSE (`text/event-stream`) | Response liên tục; có thể không có sự kiện nghiệp vụ trong một khoảng thời gian | Proxy idle timeout cắt stream |
| NDJSON streaming | Truyền dần nhiều bản ghi | Filter đệm toàn body gây tốn RAM/mất streaming |
| WebSocket | Upgrade và kết nối hai chiều dài hạn | Chính sách ping/pong, timeout và routing khác HTTP request ngắn |
| HTTP/2 nhiều stream | Nhiều luồng cùng dùng một kết nối | Đếm mỗi stream như một TCP connection dẫn tới sizing sai |

### SSE không tự được bảo vệ bởi HTTP keep-alive

Một SSE stream có thể tồn tại nhiều phút nhưng không có **byte dữ liệu** trong khoảng giữa các event. Nếu ingress hoặc proxy có idle/read timeout, nó có thể đóng kết nối dù HTTP response chưa kết thúc. Các cơ chế được cân nhắc:

- **SSE comment heartbeat** định kỳ nếu hợp đồng/client và toàn bộ proxy stack cho phép, ví dụ một comment line mang tính keepalive.
- **Cấu hình timeout thích hợp** cho ingress, Gateway HTTP client và backend đối với endpoint streaming.
- **Khả năng reconnect/resume** với event ID ở cấp ứng dụng nếu cần bảo đảm không mất sự kiện.
- **Không tự thay HTTP keep-alive bằng TCP SO_KEEPALIVE**: probe TCP có thể không thỏa điều kiện idle của proxy ở tầng HTTP.

Một comment heartbeat trong SSE:

~~~text
: keepalive

event: inventory-change
data: {"id":"42","stock":8}

~~~

Một số proxy có thể buffering response hoặc chỉ tính idle dựa trên byte thực được chuyển tiếp; vì vậy hãy kiểm thử heartbeat đến **đúng điểm client nhận**, không chỉ log rằng backend đã tạo event.

**Phân biệt response timeout và idle timeout của stream.** Tùy Reactor Netty/Gateway version, `response-timeout` có thể giới hạn thời gian chờ response hoặc khoảng không nhận dữ liệu theo cách implementation xử lý. Không tự đặt một ngưỡng ngắn cho mọi endpoint rồi kỳ vọng SSE/download dài luôn chạy; hãy kiểm tra semantics trên phiên bản cụ thể và chính sách timeout theo route nếu được hỗ trợ.

### Connection pool đối với traffic dài hạn

Khi nhiều request HTTP/1.1 giữ upstream connection lâu, chúng chiếm capacity pool trong thời gian dài. Pool cho request ngắn có thể phải chờ acquire, dù tổng request/s không lớn. Phân chia chính sách/route hợp lý, giới hạn số stream và tính đến số lượng session lâu dài là quan trọng hơn chỉ tăng max connections vô hạn.

WebSocket thường trải qua cơ chế upgrade và routing riêng; không giả định `max-idle-time` của một HTTP connection pool sẽ đóng WebSocket đang active theo cùng quy tắc.

## 13. Service discovery, instance thay đổi và connection draining

Với URI `lb://inventory-service`, **ReactiveLoadBalancerClientFilter** chọn một `ServiceInstance`, rồi routing filter dùng URL HTTP(S) cụ thể. Khi có nhiều instance, pool outbound có thể có các connection tới từng endpoint.

~~~mermaid
flowchart LR
    LB[LoadBalancer] --> A[Instance A]
    LB --> B[Instance B]
    Pool[Outbound connections] --> A
    Pool --> B
    Registry[Discovery updates] --> LB
~~~

Một instance rời hệ thống không đồng nghĩa mọi TCP connection tới instance đó biến mất ngay:

1. Registry/orchestrator cập nhật trạng thái instance.
2. Gateway có thể nhận cập nhật sau một khoảng cache/TTL.
3. Load balancer ngừng chọn instance nếu chính sách ứng viên đã cập nhật.
4. Connection cũ tới instance đó có thể còn đang phục vụ request/stream, hoặc đang nằm trong pool chờ được dọn.
5. Backend/ingress có thể chủ động drain và close để tránh request mới đến instance đã ngừng.

**Scale-down an toàn cần phối hợp nhiều thành phần**, không chỉ cấu hình `max-idle-time`. Nếu service dừng trước khi hết request đang chạy, client có thể gặp reset hoặc response một phần. Readiness, deregistration, drain timeout và graceful shutdown của backend đều quan trọng.

### DNS và pool không phải bảng ánh xạ giống nhau

Khi route đi qua service discovery, host/port do ServiceInstance cung cấp. Khi route dùng hostname HTTP thông thường, DNS có thể phân giải địa chỉ ở quá trình kết nối mới; connection đã mở không nhất thiết được tạo lại chỉ vì DNS record đổi. Pool giữ connection cũ có thể tiếp tục gọi địa chỉ cũ trong thời gian connection còn sống.

Vì vậy nếu chuyển traffic sang vùng khác hoặc rotate endpoint qua DNS, hãy nghĩ đến **TTL của DNS, tuổi thọ connection, pool disposal và chính sách draining** như những lớp khác nhau.

## 14. Graceful shutdown của Gateway và backend

Trong rolling deployment, mục tiêu không phải “giữ mọi kết nối mãi mãi”, mà là **ngừng nhận việc mới, hoàn thành việc còn xử lý và giải phóng tài nguyên có trật tự**.

~~~mermaid
sequenceDiagram
    participant LB as Ingress/LB
    participant G as Gateway instance
    participant U as Upstream

    Note over G: Bắt đầu shutdown
    G-->>LB: Readiness không còn nhận traffic mới
    LB->>LB: Ngừng chọn Gateway cho request mới
    G->>U: Hoàn tất request đang xử lý nếu còn deadline
    U-->>G: Response
    G->>G: Đóng connection / dispose resources
    Note over G: Hết grace period thì có thể buộc kết thúc
~~~

Một trình tự cần thiết kế:

1. **Ngừng đưa traffic mới** vào instance chuẩn bị dừng (readiness/routing/draining).
2. **Cho phép in-flight requests hoàn thành** trong grace period thực tế.
3. **Xác định cách xử lý connection dài hạn** (SSE, WebSocket, upload/download lớn). Không thể bảo đảm chúng kết thúc trước deadline nếu không có contract reconnect.
4. **Dispose connection pools và HTTP client resources** khi ứng dụng tắt theo lifecycle framework.
5. **Theo dõi lỗi sau shutdown**: connection reset, pending requests, 502/503 và tỷ lệ request chưa hoàn tất.

Spring Boot và Reactor Netty có hỗ trợ graceful shutdown theo phiên bản/cấu hình, nhưng **không nên khẳng định chỉ bật một property là mọi in-flight SSE/WebSocket sẽ được drain vô hạn**. Thời gian của orchestrator, ingress, proxy và ứng dụng phải tương thích.

Đối với backend cũng vậy: nên ngừng đưa instance vào danh sách cân tải trước khi đóng server socket, giúp Gateway giảm khả năng gửi request mới tới instance đang shutdown.

## 15. Giới hạn tài nguyên và bảo vệ Gateway trước quá tải

Connection pooling giúp tái sử dụng tài nguyên, nhưng cũng tạo các hàng đợi và giới hạn cần thiết kế cẩn thận.

Những nguồn áp lực phổ biến:

- **Too many open files / file descriptors:** quá nhiều TCP connections và socket đang giữ.
- **Ephemeral port exhaustion:** quá nhiều kết nối outbound tới một hoặc nhiều đích, đặc biệt khi churn cao.
- **TLS handshake CPU:** pool quá ngắn tuổi khiến liên tục tạo kết nối HTTPS mới.
- **Pending acquire queue:** pool quá nhỏ, request đổ vào hàng chờ thay vì được xử lý.
- **Event-loop blocking:** code Gateway filter dùng `block()` hoặc I/O blocking làm chậm cả kết nối.
- **Slow clients / slow upstream:** kết nối và buffer bị giữ lâu, tăng áp lực bộ nhớ/backpressure.
- **Retry storm:** lỗi kết nối làm tăng số lần gọi backend và số acquire request.

Các biện pháp bảo vệ tương ứng:

1. **Bounded pool và bounded pending queue** theo năng lực backend, thay vì cho phép tăng vô hạn.
2. **Rate limiting** ở Gateway để giới hạn lưu lượng vào theo nguồn tin cậy; nhớ rằng rate limiter đếm request, không thay thế pool capacity.
3. **Connect/acquire/response timeout có chủ đích** cho từng nhóm workload; không có một con số phù hợp với mọi API.
4. **Không chặn event loop**; với công việc bắt buộc blocking phải cách ly tài nguyên thích hợp.
5. **Circuit breaker và retry có giới hạn** để giảm tải khi service suy giảm.
6. **Giới hạn body/header và kết nối dài hạn** theo chính sách WebFlux, ingress và backend.
7. **Kiểm soát TLS và nguồn service discovery**, không để client chỉ định host/port nội bộ tùy ý.

**Không giải quyết pool saturation chỉ bằng tăng `max-connections`.** Nếu backend đã quá tải, việc mở thêm socket có thể làm latency và error rate tệ hơn. Cần xem concurrency, thời gian xử lý, hàng đợi và tài nguyên của cả Gateway lẫn backend.

## 16. Metrics, logs và tracing cho vòng đời kết nối

Để biết pool có đang hoạt động đúng, cần quan sát cả HTTP và TCP/TLS ở **phía Gateway outbound**:

| Nhóm tín hiệu | Mục đích |
| --- | --- |
| Active connections | Bao nhiêu connection đang phục vụ I/O hoặc được acquire |
| Idle connections | Bao nhiêu connection đang rảnh và có thể tái dùng |
| Pending acquires / wait time | Có request đang xếp hàng chờ connection không? |
| Acquire timeout/failure | Pool thiếu capacity hoặc không cấp connection kịp |
| TCP connect duration/failure | Backend host/port có vấn đề mạng không? |
| TLS handshake duration/failure | Chứng chỉ, truststore hoặc cấu hình TLS có lỗi không? |
| Connection churn | Tỷ lệ tạo/đóng connection mới có cao bất thường không? |
| HTTP request latency và status | Backend chậm hay Gateway lỗi trước upstream? |
| Event-loop latency/CPU | Có nghẽn non-blocking runtime không? |
| In-flight streams | Có nhiều SSE/WebSocket/upload/download dài hạn chiếm tài nguyên không? |

Reactor Netty, Spring Boot Actuator, Micrometer và Spring Cloud Gateway có thể xuất metrics/tracing nếu được bật và cấu hình đúng. **Tên metric/label thay đổi theo phiên bản**, vì vậy không ghi cứng một tên metric rồi khẳng định release nào cũng có.

### Một cách đọc sự cố qua metric

| Quan sát | Diễn giải có thể |
| --- | --- |
| Pending acquire tăng, active ở giới hạn | Pool bão hòa hoặc backend xử lý chậm |
| Idle gần 0, TLS handshakes tăng | Tăng connection churn, idle/lifetime quá ngắn hoặc tăng tải |
| Idle rất cao nhưng file descriptors thiếu | Pool/cấu hình giữ nhiều socket không cần thiết |
| Connect error tăng, no-instance không tăng | Đã chọn instance nhưng kết nối mạng tới upstream lỗi |
| No-instance tăng sau rollout | Discovery/readiness/cache chưa cập nhật đúng |
| Client 502 tăng ngay sau một khoảng không traffic | Có thể stale connection khi reuse, cần xác minh bằng log/packet/telemetry |
| SSE đứt sau khoảng thời gian cố định | Có thể ingress read/idle timeout, chưa chắc pool idle timeout |
| p99 latency tăng nhưng request rate ổn định | Backend chậm, acquire queue tăng, hoặc event-loop bị block |

Chỉ số nên được phân nhóm bằng route ID/service ID và các nhãn có số lượng hữu hạn. Không đưa token, raw query, request ID hay user ID làm nhãn metric; cũng không log session key hoặc certificate private key. Instance IP/ID có thể thay đổi liên tục khi autoscale, cần kiểm soát cardinality.

Nếu phải debug connection ID, hãy bật mức log phù hợp trong môi trường kiểm soát, liên kết với trace/request ID an toàn, sau đó tắt bớt để tránh quá tải log và lộ dữ liệu.

## 17. Bảng chẩn đoán những lỗi thường gặp

| Hiện tượng | Nguyên nhân đáng kiểm tra | Hành động phù hợp |
| --- | --- | --- |
| Request đầu tiên chậm, request sau nhanh | DNS/TCP/TLS handshake ở connection mới | Đo connect, handshake và reuse; không mặc định lỗi |
| 502/reset sau khoảng thời gian nhàn rỗi | Stale pooled connection do proxy/peer đã đóng | So sánh idle timeout các tầng; giảm max idle có dự phòng |
| Tải tăng thì 5xx, pending acquires tăng | Pool saturation hoặc backend latency cao | Đo active/pending/CPU, cân đối pool và backend capacity |
| Gateway mở quá nhiều connection | Pool limit, nhiều destination, retry hoặc nhiều replica | Kiểm tra pool key, số service instance và tổng socket |
| Lỗi chỉ khi gọi upstream HTTPS | TLS trust/hostname/cert/port, handshake timeout | Kiểm tra chứng chỉ và mTLS, không tắt verification |
| SSE đứt định kỳ | Proxy/read/response timeout hoặc buffering | Kiểm tra từng hop, heartbeat và contract resume |
| WebSocket disconnect khi idle | Ping/pong và timeout của proxy/tunnel | Kiểm tra WebSocket routing và idle chính xác |
| Instance đã rời cluster vẫn nhận request | Registry/cache hoặc connection cũ còn active | Kiểm tra discovery refresh, readiness và drain |
| Đổi DNS nhưng còn request tới IP cũ | Existing pooled connections hoặc DNS cache | Kiểm tra DNS TTL, connection lifetime và draining |
| CPU cao khi traffic vừa phải | TLS handshake churn, event-loop blocking hoặc retry storm | Đo handshake, reuse, pool stats và blocking |
| 503 khi dùng `lb://` | Không có instance hoặc lỗi khác ở lớp Gateway/backend | Phân biệt no-instance với connect/response failure |
| Gateway shutdown làm rớt upload | Grace period ngắn, đóng socket quá sớm | Thống nhất readiness, drain, shutdown và deadline |

**Quy trình phân tích từ ngoài vào trong:**

1. Client gọi **HTTP/1.1 hay HTTP/2**, qua HTTPS hay HTTP?
2. Có CDN/ingress/WAF/sidecar nào **đóng kết nối trước** Gateway hoặc backend không?
3. Gateway route đến URL nào: `http://`, `https://` hay `lb://`?
4. Nếu `lb://`, load balancer có chọn đúng `ServiceInstance` không?
5. HTTP client có đang **chờ acquire**, tạo TCP connection mới hay reuse connection cũ?
6. Lỗi xảy ra ở TCP connect, TLS handshake, chờ response hay trong lúc stream?
7. `max-idle-time`, `max-life-time`, pending timeout và response timeout có tương thích các tầng?
8. Có ảnh hưởng từ **retry, circuit breaker, rate limiter, event-loop blocking** hoặc rollout instance không?
9. Có bảo toàn status/body khi lỗi sau response commit không?

Không lấy một lỗi ở tầng TCP làm bằng chứng rằng route predicate, header rewrite hoặc authentication sai. Ghi nhận đúng điểm thất bại giúp chọn cách sửa nhỏ nhất và an toàn nhất.

## 18. Thực hành: đo keep-alive và xử lý stale connection

**Bối cảnh:** Gateway có route `GET /api/inventory/**` tới Inventory service. Hai backend chạy trên 9001 và 9002; Gateway sử dụng `lb://inventory-service` hoặc một URI HTTP cố định cho bài thử đơn giản. Yêu cầu là giảm chi phí tạo kết nối nhưng vẫn chịu được backend thay đổi.

### Phần A — Kiểm tra HTTP persistence

1. Khởi chạy Gateway và backend kiểm thử, có log an toàn về connection ID hoặc số lần mở TCP connection.
2. Gửi nhiều request qua cùng một client process:

~~~bash
curl -v --http1.1 \
  'http://localhost:8080/api/inventory/items/42' \
  'http://localhost:8080/api/inventory/items/43'
~~~

3. Quan sát xem **client → Gateway** có reuse connection HTTP/1.1 không. Lưu ý: lệnh curl chỉ giúp quan sát **hop client → Gateway**, không tự chứng minh Gateway → backend tái dùng socket.
4. Dùng log/metric ở Reactor Netty hoặc backend kiểm thử để xác nhận **hop outbound** có tái dùng connection sau request hoàn tất.
5. Nếu hạ tầng hỗ trợ HTTP/2, so sánh cách nhiều stream hoạt động trên một kết nối; không sử dụng `Connection: keep-alive` cho HTTP/2.

### Phần B — Đặt giới hạn pool có cơ sở

1. Bắt đầu bằng cấu hình pool có giới hạn ở phần 7, sau khi xác nhận đúng tên property cho phiên bản Gateway.
2. Tạo burst request GET có kiểm soát từ một công cụ load test được phê duyệt trong môi trường thử nghiệm, không tạo tải trên production.
3. Đo active, idle, pending acquires, acquire time, p95/p99 latency và error rate.
4. Giảm `max-connections` có kiểm soát để quan sát hàng chờ. Sau đó tăng vừa đủ để so sánh; không chọn con số chỉ dựa trên TPS.
5. Thử thay `max-idle-time` và `max-life-time` trong ngưỡng hợp lý; xem số lần connect/TLS handshake thay đổi như thế nào.

### Phần C — Mô phỏng stale connection

1. Đặt một backend hoặc proxy thử nghiệm có idle timeout ngắn hơn thời gian pool định reuse connection.
2. Gửi một request thành công, để connection idle lâu hơn timeout ở peer.
3. Gửi request tiếp theo và ghi nhận có reset/retry/open new connection hay không. Đừng yêu cầu lỗi phải xảy ra trong **mọi lần** vì race và cách Netty phát hiện remote close.
4. Điều chỉnh max idle của pool ngắn hơn peer idle timeout có dự phòng, rồi thử lại cùng điều kiện.
5. Phân biệt kết quả của GET an toàn để retry với một POST có side effect; giải thích vì sao retry tự động không được dùng làm “bảo hiểm” cho mọi method.

### Phần D — Streaming, TLS và rollout

1. Tạo một SSE endpoint gửi event định kỳ; thử dừng gửi event đủ lâu để một proxy thử nghiệm có thể đóng idle stream.
2. Thêm heartbeat ở mức ứng dụng, kiểm tra event đến client và quan sát timeout của **từng hop**, không chỉ pool.
3. Dùng HTTPS tới backend với chứng chỉ hợp lệ; quan sát handshake ở kết nối mới và reuse của connection cũ.
4. Mô phỏng dừng backend instance theo trình tự readiness → ngừng chọn → drain → shutdown; đo request thất bại trong thời gian rollout.
5. Kiểm tra metrics/log không lộ token, query chứa dữ liệu riêng tư hoặc khóa TLS.

### Ma trận kết quả cần ghi

| Trường hợp | Kỳ vọng quan sát |
| --- | --- |
| Hai GET tuần tự cùng client | Hop client có thể reuse connection nếu cả hai bên cho phép |
| Hai GET tuần tự tới cùng upstream | Hop Gateway → backend có thể reuse pool connection phù hợp |
| Pool hết capacity | Pending acquires tăng; có thể timeout khi chờ |
| Proxy đóng idle connection | Một số reuse có thể thất bại hoặc phải mở kết nối mới |
| Max idle ngắn hơn peer idle | Giảm nguy cơ stale reuse nhưng tăng churn nếu đặt quá ngắn |
| HTTPS mở connection mới | Có TCP/TLS handshake và certificate validation |
| HTTPS reuse connection hiện hữu | Không phải thực hiện handshake mới cho từng request |
| SSE lâu không có byte | Có thể bị proxy timeout dù request chưa hoàn tất |
| Rollout/scale-down | Discovery, pool và draining cần phối hợp để giảm reset |

**Tiêu chí đạt:** Bạn xác định đúng nơi xảy ra idle hoặc timeout, phân biệt inbound/outbound, chứng minh việc pool reuse dựa trên connection-level evidence, đo ảnh hưởng của pool limit và xử lý stale connection an toàn. Mọi đề xuất timeout hoặc retry phải dựa trên hợp đồng ứng dụng và số liệu thực tế.

## 19. Ghi nhớ

- **HTTP keep-alive, TCP keepalive và connection pool là ba cơ chế khác nhau.** HTTP cho phép reuse; TCP keepalive probe socket; pool quản lý capacity và vòng đời kết nối outbound.
- **Gateway có hai phía kết nối độc lập**: client → Gateway và Gateway → backend. Timeout của ingress, Netty server, Reactor Netty client, sidecar và backend phải được hiểu theo **đúng hop**.
- **max idle time** giới hạn việc giữ connection rảnh để reuse; **max life time** giới hạn tuổi connection; **acquire timeout** giới hạn thời gian chờ pool. Không nhầm chúng với **connect timeout**, **TLS handshake timeout**, **response timeout** hoặc client deadline.
- **Reuse tiết kiệm TCP/TLS handshake**, nhưng giữ connection quá lâu có thể tăng rủi ro stale socket khi peer hoặc proxy đã đóng. Điều chỉnh dựa trên dữ liệu thực và có thời gian dự phòng.
- **HTTP/2 multiplexing, SSE, NDJSON và WebSocket** có đặc tính kết nối khác request HTTP/1.1 ngắn. Đừng áp một idle/response timeout cho mọi loại traffic mà không kiểm thử end-to-end.
- **Service discovery, load balancing, connection pool và graceful draining** phải phối hợp khi backend instance thay đổi. Tắt backend trước khi ngừng chọn instance có thể làm rớt request đang chạy.
- Để vận hành Spring Cloud Gateway an toàn, hãy đo **active/idle/pending connections, handshake, latency, error rate**, đặt giới hạn tài nguyên, bảo vệ TLS và chỉ retry khi bảo đảm tính đúng đắn nghiệp vụ.
