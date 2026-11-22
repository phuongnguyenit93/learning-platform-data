# Đo lỗi cạn kết nối, kết nối nhàn rỗi và tải của dịch vụ đích trong Spring WebFlux

> **Module:** Spring Framework – reactive · **Chủ đề cha:** Kết nối và thời hạn. Bài học xây dựng cách quan sát và chẩn đoán outbound HTTP của `WebClient` trên Reactor Netty. Trọng tâm là phân biệt pool cạn connection, connection nhàn rỗi hoặc stale, lỗi DNS/connect/TLS, response chậm và dịch vụ đích quá tải; bật đúng Micrometer metrics; đặt giới hạn pool/timeout; và kiểm thử dưới tải để chọn capacity an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích connection pool của Reactor Netty và vòng đời acquire → active → release → idle → eviction.
2. Phân biệt `maxConnections`, pending acquire queue, `pendingAcquireTimeout`, `maxIdleTime` và `maxLifeTime`.
3. Đọc các gauge/timer về total, active, idle, pending connections và thời gian chờ acquire.
4. Đo DNS resolution, TCP connect, TLS handshake, gửi/nhận dữ liệu, response time và lỗi HTTP client.
5. Phân biệt pool exhaustion ở client với dịch vụ đích chậm hoặc quá tải.
6. Xử lý stale idle connections, timeout khác tầng, retry amplification và connection churn.
7. Bật Reactor Netty metrics và Spring Boot `http.client.requests` bằng Micrometer/Actuator.
8. Thiết kế dashboard, alert, load test và giới hạn concurrency phù hợp với capacity của downstream.
9. Tạo một WebClient có pool riêng, timeout có chủ đích và HTTP integration tests bằng Java 17+.

**Nguyên tắc vận hành:** một connection pool lớn hơn không tự động làm hệ thống nhanh hơn. Pool phải đủ cho concurrency dự kiến, queue phải có giới hạn, timeout phải phản ánh SLO, và tổng số kết nối từ mọi replica không được vượt khả năng phục vụ của hệ thống đích.

## 2. Bản đồ request outbound và connection pool

`WebClient` là API reactive của Spring. Khi chạy trên Reactor Netty, HTTP client thường dùng `ConnectionProvider` để quản lý các kết nối tới từng remote host. Một request phải lấy được connection hoặc stream trước khi có thể gửi/nhận dữ liệu.

~~~text
Controller / Service
       |
       v
     WebClient
       |
       v
 ConnectionProvider
       |
       +---- idle connection available
       |          |
       |          v
       |       acquire
       |
       +---- no idle connection
                  |
                  v
        active < maxConnections?
             /           \
           yes            no
            |              |
       open connection   pending queue
            |              |
            +-------+------+
                    |
                    v
             TCP / TLS / HTTP
                    |
                    v
             Target service
                    |
                    v
             response body
                    |
                    v
           consume response fully
                    |
                    v
             release connection
                    |
                    v
              idle / evict
~~~

Các trạng thái cần phân biệt:

- **Total:** tổng connection đang được pool quản lý, gồm active và idle.
- **Active:** connection đã acquire và đang phục vụ request.
- **Idle:** connection đã trả về pool, có thể được tái sử dụng.
- **Pending:** request đang chờ một connection khả dụng.
- **Acquire time:** thời gian request phải chờ để lấy connection.
- **Response time:** thời gian thực hiện request/response; nó có thể bao gồm thời gian chờ, network và xử lý phía đích tùy metric/observation đang xem.

Một connection nhàn rỗi không phải lỗi. Nó là năng lực đã được tạo sẵn để tái sử dụng, tránh TCP/TLS handshake cho request tiếp theo. Chỉ khi idle connection stale hoặc pool giữ quá nhiều tài nguyên mới cần điều chỉnh.

## 3. Hiểu các giới hạn của ConnectionProvider

### 3.1. `maxConnections`

`maxConnections` giới hạn số connection đồng thời trong mỗi pool tới remote host. Khi pool đạt giới hạn, request mới có thể chờ trong pending queue nếu queue còn chỗ.

Ví dụ:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("catalog-pool")
        .maxConnections(32)
        .build();
~~~

Giá trị `32` chỉ là ví dụ cho một instance. Nó không có nghĩa toàn bộ hệ thống chỉ có 32 connection. Nếu có 20 replica, mỗi replica có pool riêng, tổng khả năng mở connection có thể lên tới khoảng 640 connection tới cùng downstream, chưa kể service khác.

### 3.2. Pending acquire queue

Khi không có connection idle và đã chạm `maxConnections`, request mới có thể nằm trong pending queue:

- `pendingAcquireMaxCount` giới hạn số yêu cầu được xếp hàng.
- `pendingAcquireTimeout` giới hạn thời gian một yêu cầu được phép chờ.
- Nếu queue đầy hoặc hết thời gian chờ, acquire thất bại.

Queue hữu hạn giúp hệ thống fail fast khi downstream không đáp ứng được tải. Queue vô hạn có thể giữ request quá lâu, tăng memory, tăng latency và khiến một đợt quá tải kéo dài ngay cả khi traffic đã giảm.

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("catalog-pool")
        .maxConnections(32)
        .pendingAcquireMaxCount(64)
        .pendingAcquireTimeout(Duration.ofMillis(500))
        .build();
~~~

Trong cấu hình này, tối đa 32 connection được quản lý đồng thời; tối đa 64 request khác có thể chờ acquire; một request chờ quá 500 ms sẽ thất bại. Đây là giới hạn minh họa, cần hiệu chỉnh theo latency SLO và capacity thực tế của downstream.

### 3.3. `maxIdleTime`, `maxLifeTime` và eviction

| Cấu hình | Ý nghĩa | Dùng để |
| --- | --- | --- |
| `maxIdleTime` | Thời gian tối đa connection được phép ở trạng thái idle | Tránh tái sử dụng connection đã bị server/load balancer đóng |
| `maxLifeTime` | Tuổi thọ tối đa của connection tính từ lúc tạo | Luân chuyển connection cũ và endpoint/DNS đã thay đổi |
| `maxLifeTimeVariance` | Jitter cho thời điểm hết tuổi thọ | Tránh nhiều connection được tạo cùng lúc rồi hết hạn cùng lúc |
| `evictInBackground` | Chu kỳ kiểm tra và loại connection đủ điều kiện eviction | Dọn connection idle theo lịch nền |

Ví dụ:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("catalog-pool")
        .maxConnections(32)
        .pendingAcquireMaxCount(64)
        .pendingAcquireTimeout(Duration.ofMillis(500))
        .maxIdleTime(Duration.ofSeconds(25))
        .maxLifeTime(Duration.ofMinutes(5))
        .maxLifeTimeVariance(5)
        .evictInBackground(Duration.ofSeconds(30))
        .metrics(true)
        .build();
~~~

`maxIdleTime` nên bằng hoặc thấp hơn idle timeout của target server/load balancer. Ví dụ, nếu load balancer đóng connection sau 60 giây idle, đặt client ở khoảng 45–50 giây có thể giúp pool loại connection trước khi thử dùng lại. Con số cụ thể phải theo timeout thực tế của hạ tầng.

`maxLifeTime` quá ngắn có thể tạo connection churn: nhiều TCP/TLS handshake, tăng CPU và tải lên target. Nếu nhiều connection được tạo gần cùng thời điểm, jitter giúp tránh chúng cùng hết hạn và reconnect trong một đợt.

Reactor Netty kiểm tra các timeout khi acquire/release; `evictInBackground` bổ sung kiểm tra định kỳ. Không cần bật chu kỳ quá ngắn nếu chi phí kiểm tra lớn hơn lợi ích.

### 3.4. HTTP/2 không giống HTTP/1.1

Với HTTP/1.1, một connection thường phục vụ một request đang hoạt động tại một thời điểm trong mô hình client thông thường. Với HTTP/2, một connection có thể multiplex nhiều stream đồng thời.

Do đó:
- `active.connections` không phản ánh đầy đủ concurrency HTTP/2.
- Hãy theo dõi thêm `active.streams` và `pending.streams`.
- Một pool chỉ có vài connection vẫn có thể phục vụ nhiều request song song.
- Giới hạn stream concurrency và capacity phía server vẫn quan trọng.

Không áp dụng công thức pool HTTP/1.1 trực tiếp cho HTTP/2 mà không xét stream limit.

## 4. Đọc các metrics của Reactor Netty

Reactor Netty có hai nhóm metrics quan trọng: pool metrics và HTTP client metrics. Chúng có prefix riêng và phải được bật ở đúng đối tượng.

### 4.1. Pool metrics

Bật bằng:

~~~java
ConnectionProvider.builder("catalog-pool")
    .metrics(true)
    .build();
~~~

Các meter chính:

| Meter | Loại | Ý nghĩa |
| --- | --- | --- |
| `reactor.netty.connection.provider.total.connections` | Gauge | Tổng connection active + idle |
| `reactor.netty.connection.provider.active.connections` | Gauge | Connection đang được acquire |
| `reactor.netty.connection.provider.max.connections` | Gauge | Giới hạn connection active |
| `reactor.netty.connection.provider.idle.connections` | Gauge | Connection đang chờ tái sử dụng |
| `reactor.netty.connection.provider.pending.connections` | Gauge | Request đang chờ acquire |
| `reactor.netty.connection.provider.pending.connections.time` | Timer | Thời gian chờ acquire |
| `reactor.netty.connection.provider.max.pending.connections` | Gauge | Giới hạn pending queue |

Đây là nhóm metrics trực tiếp nhất để nhận biết pool saturation. Nếu `active` chạm `max`, `pending` tăng và `pending.connections.time` tăng, request đang phải đợi pool cấp connection.

### 4.2. HTTP client metrics

Bật trên `HttpClient`:

~~~java
HttpClient httpClient =
    HttpClient.create(provider)
        .metrics(true, uri -> {
            if (uri.startsWith("/items/")) {
                return "/items/{id}";
            }
            return uri;
        });
~~~

Mapper chuẩn hóa URI giúp tránh tạo meter riêng cho từng path có ID khác nhau. Ví dụ `/items/42` và `/items/43` cùng được ghi dưới `/items/{id}`.

Các meter chính:

| Meter | Ý nghĩa |
| --- | --- |
| `reactor.netty.http.client.address.resolver` | Thời gian phân giải hostname/DNS |
| `reactor.netty.http.client.connect.time` | Thời gian thiết lập connection |
| `reactor.netty.http.client.tls.handshake.time` | Thời gian TLS handshake |
| `reactor.netty.http.client.data.sent` | Số byte gửi đi |
| `reactor.netty.http.client.data.sent.time` | Thời gian gửi dữ liệu |
| `reactor.netty.http.client.data.received` | Số byte nhận |
| `reactor.netty.http.client.data.received.time` | Thời gian nhận/tiêu thụ dữ liệu |
| `reactor.netty.http.client.response.time` | Thời gian request/response |
| `reactor.netty.http.client.errors` | Số lỗi HTTP client |

HTTP/2 còn có:

- `reactor.netty.connection.provider.active.streams`
- `reactor.netty.connection.provider.pending.streams`

Khi cần tìm nguyên nhân latency, xem DNS, connect, TLS, pending acquire và response time riêng. Nếu chỉ xem `response.time`, bạn sẽ không biết request đang chờ connection hay remote service xử lý chậm.

### 4.3. Spring Boot `http.client.requests` là lớp observation khác

Spring Boot Actuator có thể tự instrument `WebClient` và tạo meter `http.client.requests`. Để nhận instrumentation này, hãy inject `WebClient.Builder` được Spring Boot auto-configure rồi build client từ builder đó.

Hai nhóm metrics có mục đích khác nhau:

| Nhóm | Đo gì? | Bật ở đâu? |
| --- | --- | --- |
| `http.client.requests` | Observation cho request outbound ở mức Spring | Dùng auto-configured `WebClient.Builder` |
| `reactor.netty.connection.provider.*` | Số lượng/trạng thái pool và pending acquire | `ConnectionProvider.metrics(true)` |
| `reactor.netty.http.client.*` | DNS/connect/TLS/data/response và lỗi ở tầng Reactor Netty | `HttpClient.metrics(true, uriMapper)` |

Có thể bật cả ba. Khi phân tích, không cộng thời gian của các meter lại với nhau vì chúng có thể đo những khoảng thời gian lồng nhau hoặc khác boundary.

## 5. Phân biệt pool exhaustion với target service overload

Đây là bước chẩn đoán quan trọng nhất. Hai tình huống có thể cùng làm `active.connections` tăng, nhưng nguyên nhân và cách xử lý khác nhau.

### 5.1. Dấu hiệu pool exhaustion phía client

Thường thấy:

- `active.connections` tiến sát `max.connections`.
- `pending.connections` tăng và tồn tại liên tục.
- `pending.connections.time` tăng.
- Request lỗi `PoolAcquireTimeoutException` hoặc lỗi acquire tương đương.
- DNS/connect time có thể vẫn bình thường vì request chưa lấy được connection để bắt đầu network I/O.
- Target server có thể vẫn khỏe nếu lượng request thực tế tới target chưa vượt capacity.

Nguyên nhân thường gặp:
- `maxConnections` quá thấp so với concurrency hợp lệ.
- Response body không được consume hết nên connection không được trả pool sớm.
- Request/stream quá dài hoặc downstream response bị treo.
- Có một số operation giữ connection lâu hơn dự kiến.
- Target đang chậm khiến connection active không được release.

### 5.2. Dấu hiệu target service quá tải

Thường thấy:

- `reactor.netty.http.client.response.time` tăng, đặc biệt p95/p99.
- `active.connections` tăng vì request giữ connection lâu.
- Pending acquire có thể tăng thứ phát khi pool hết chỗ.
- Target trả nhiều `429`, `503` hoặc `5xx`.
- Metrics phía target cho thấy queue, worker, event loop, CPU, memory hoặc concurrency chạm giới hạn.
- Latency tăng dù connect/TLS vẫn nhanh.

Trong tình huống này, tăng `maxConnections` có thể đẩy thêm request tới một target đã quá tải và làm tình hình nặng hơn. Cần giới hạn concurrency, giảm tốc độ gửi, shed load hoặc mở rộng capacity phía target.

### 5.3. Bảng chẩn đoán theo tín hiệu

| Quan sát | Khả năng cao | Việc nên kiểm tra |
| --- | --- | --- |
| Active = max, pending > 0, acquire timer tăng | Pool saturation | Request nào giữ connection lâu? Pool max và queue có hợp lý? |
| Pending acquire timeout tăng nhưng target latency thấp | Pool quá nhỏ hoặc nhiều request giữ connection | Body có được consume? Có stream dài hoặc leak không? |
| Response time cao, connect/TLS thấp, target 5xx/429 tăng | Target overload | Server queue, CPU, concurrency, rate limit và Retry-After |
| DNS resolver time tăng | DNS hoặc resolver chậm | DNS server, cache, service discovery và hostname |
| Connect time tăng | TCP connect/network/target accept backlog | Network path, SYN backlog, firewall, target listener |
| TLS handshake time tăng | TLS/certificate/crypto hoặc reconnect quá nhiều | Handshake, certificate, connection churn, TLS termination |
| Request đầu tiên sau idle thất bại, request tiếp theo thành công | Stale idle connection | Target/LB idle timeout và client `maxIdleTime` |
| Total connections tăng nhanh, connect/TLS time và errors tăng | Connection churn | `maxIdleTime`, `maxLifeTime`, pool disposal và traffic burst |
| Idle cao, active thấp, pending bằng 0 | Pool đang có spare capacity | Chưa phải lỗi; đánh giá có đang giữ quá nhiều connection không |
| HTTP/2 active streams cao, pending streams tăng | Stream capacity hoặc target chậm | Server max concurrent streams và H2 allocation strategy |

Không kết luận target overload chỉ từ `active.connections = max`. Cần kết hợp pending acquire, response time, status code và metrics phía target.

## 6. Đo tải của dịch vụ đích

Client metrics cho biết client đang chờ, gửi, nhận và gặp lỗi gì. Chúng không tự tiết lộ đầy đủ queue hoặc CPU của server đích. Muốn biết target có thực sự quá tải, phải quan sát cả hai phía.

### 6.1. Các tín hiệu cần thu thập ở target

| Tín hiệu phía target | Câu hỏi cần trả lời |
| --- | --- |
| Request rate (RPS) | Lượng request vào đang tăng hay ổn định? |
| In-flight requests | Có bao nhiêu request đang xử lý đồng thời? |
| p50/p95/p99 latency | Phần lớn request và tail latency thay đổi thế nào? |
| 4xx/429/5xx | Target đang từ chối, rate-limit hay lỗi xử lý? |
| Queue depth / queue wait | Request đang chờ worker, thread, event loop hay database? |
| CPU và memory | Service có chạm giới hạn tài nguyên? |
| Worker/event-loop utilization | Khả năng xử lý request có bị bão hòa? |
| Database/cache dependency | Request chậm do dependency phía sau? |
| Open connections/streams | Connection hoặc stream có vượt capacity server? |

Dùng cùng distributed trace để nối client span với server span. Ghi nhận service name, operation/route template, status và duration; tránh đưa ID người dùng hoặc URL động vào metric tag.

### 6.2. Little’s Law để ước lượng concurrency

Trong hệ thống ổn định:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số request trung bình đang ở trong hệ thống.
- \(\lambda\): throughput, ví dụ request/giây.
- \(W\): thời gian trung bình một request nằm trong hệ thống, tính bằng giây.

Ví dụ: một instance gửi 200 request/giây tới target; thời gian response trung bình là 150 ms = 0,15 giây.

\[
L = 200 \times 0.15 = 30
\]

Con số 30 là concurrency trung bình gần đúng trong điều kiện ổn định, không phải `maxConnections` bắt buộc. Tail latency, burst, retry, số replica, HTTP/2 stream và capacity target đều ảnh hưởng tới giới hạn thực tế.

Nếu latency tăng gấp đôi mà throughput giữ nguyên, số request đồng thời trong hệ thống cũng tăng gần gấp đôi. Đây là lý do target chậm có thể làm pool cạn dù traffic đầu vào không tăng.

### 6.3. Tổng connection từ nhiều replica

Tính theo từng service/target:

~~~text
Tổng connection tiềm năng
    ≈ số replica client
      × maxConnections mỗi replica
      × số pool/client độc lập cùng gọi target
~~~

Ví dụ:

- 12 replica của checkout.
- Mỗi replica có pool `maxConnections=40`.
- Hai WebClient độc lập cùng trỏ tới cùng target.

Giới hạn tiềm năng có thể lên tới \(12 \times 40 \times 2 = 960\) connection. Nếu hai WebClient dùng chung một `ConnectionProvider` phù hợp, có thể giảm pool trùng lặp. Hãy tính cả worker khác, cron job và service khác gọi cùng target.

Pool capacity phải được đánh giá theo toàn bộ deployment, không chỉ một pod.

## 7. Phân biệt các timeout

Tên timeout gần nhau nhưng đo những giai đoạn khác nhau:

| Timeout | Bắt đầu/kết thúc | Lỗi thường gặp |
| --- | --- | --- |
| DNS query timeout | Chờ hostname được resolve | Resolver timeout |
| Connect timeout | Thiết lập TCP connection | Connect timeout/refused |
| TLS handshake timeout | Thương lượng TLS | SSL handshake timeout |
| Pending acquire timeout | Chờ pool cấp connection | Pool acquire timeout |
| Response timeout | Chờ dữ liệu response theo cấu hình Reactor Netty | Response timeout |
| Overall operation timeout | Bao toàn bộ operation reactive | `TimeoutException` từ `Mono.timeout` |

Một cấu hình ví dụ:

~~~java
HttpClient httpClient =
    HttpClient.create(provider)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
        .responseTimeout(Duration.ofSeconds(2));
~~~

Có thể thêm timeout tổng thể ở service:

~~~java
Mono<String> response = webClient.get()
    .uri("/work")
    .retrieve()
    .bodyToMono(String.class)
    .timeout(Duration.ofSeconds(3));
~~~

`Mono.timeout` bao cả quá trình operation từ lúc subscribe tới khi có terminal signal; nó không thay thế timeout chuyên biệt của pool, DNS, connect hoặc response. Cấu hình timeout theo từng tầng giúp xác định request thất bại ở đâu.

Không đặt `pendingAcquireTimeout` quá dài chỉ để giảm số lỗi. Queue lâu làm tăng tail latency và giữ request không cần thiết. Timeout nên nằm trong budget tổng của request, để service gọi WebClient còn thời gian xử lý fallback hoặc trả lỗi cho caller.

## 8. Xử lý connection nhàn rỗi và stale connection

### 8.1. Idle connection bình thường

Khi response hoàn tất và body được tiêu thụ, connection có thể được trả về pool. Nó ở trạng thái idle cho tới khi request khác dùng lại hoặc eviction loại bỏ.

Idle gauge có thể:
- Tăng sau một burst traffic rồi giảm theo eviction.
- Luôn có vài connection nếu traffic đều.
- Bằng 0 khi pool đang bận hoặc không giữ connection.

Không alert chỉ vì `idle.connections > 0`. Hãy so sánh idle với active, pending, max và chi phí giữ socket.

### 8.2. Stale idle connection

Một số load balancer, proxy hoặc target server đóng connection sau một khoảng idle. Nếu client vẫn giữ connection đó và thử reuse, request kế tiếp có thể gặp reset/close sớm, ví dụ `PrematureCloseException` hoặc connection reset.

Cách xử lý:

1. Xác định idle timeout thật của target, proxy và load balancer.
2. Đặt client `maxIdleTime` nhỏ hơn hoặc bằng timeout ngắn nhất trong đường đi.
3. Cân nhắc `evictInBackground` để loại connection đã đủ điều kiện.
4. Đặt `maxLifeTime` hợp lý nếu cần luân chuyển connection.
5. Quan sát lỗi tập trung ở request đầu sau khoảng nghỉ.
6. Kiểm tra HTTP/2 keepalive/PING nếu đang dùng HTTP/2.

Ví dụ nếu load balancer đóng connection sau 60 giây idle:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("catalog-pool")
        .maxIdleTime(Duration.ofSeconds(45))
        .evictInBackground(Duration.ofSeconds(20))
        .build();
~~~

45 giây là giá trị minh họa; cần có khoảng đệm theo chính sách mạng và timeout của mọi hop.

### 8.3. HTTP/2 keepalive

Với HTTP/2, Reactor Netty hỗ trợ PING frames để kiểm tra connection idle. Cấu hình PING health check phụ thuộc `maxIdleTime`; nếu cần dùng, hãy cấu hình idle timeout cùng `pingAckTimeout` và ngưỡng retry theo tài liệu phiên bản Reactor Netty đang chạy.

PING giúp phát hiện peer không còn phản hồi. Nó không thay thế timeout request, giới hạn stream hoặc health check nghiệp vụ.

## 9. Cấu hình WebClient có pool riêng và metrics

Ví dụ dưới đây sử dụng Spring Boot, WebFlux, Reactor Netty và Micrometer. Dùng một `ConnectionProvider` có tên để phân biệt pool của downstream Catalog.

~~~java
@Configuration(proxyBeanMethods = false)
public class CatalogWebClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogConnectionProvider() {
        return ConnectionProvider.builder("catalog-pool")
            .maxConnections(32)
            .pendingAcquireMaxCount(64)
            .pendingAcquireTimeout(Duration.ofMillis(500))
            .maxIdleTime(Duration.ofSeconds(25))
            .maxLifeTime(Duration.ofMinutes(5))
            .maxLifeTimeVariance(5)
            .evictInBackground(Duration.ofSeconds(30))
            .metrics(true)
            .build();
    }

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            ConnectionProvider catalogConnectionProvider,
            @Value("${catalog.base-url}") String baseUrl) {

        HttpClient httpClient =
            HttpClient.create(catalogConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
                .responseTimeout(Duration.ofSeconds(2))
                .metrics(true, uri -> {
                    if (uri.startsWith("/items/")) {
                        return "/items/{id}";
                    }
                    return uri;
                });

        return builder
            .baseUrl(baseUrl)
            .clientConnector(
                new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
~~~

Các điểm quan trọng:

- `ConnectionProvider.metrics(true)` bật pool metrics.
- `HttpClient.metrics(true, uriMapper)` bật HTTP client metrics và chuẩn hóa URI tag.
- `WebClient.Builder` được inject từ Spring Boot để giữ instrumentation `http.client.requests`.
- `maxConnections` và pending queue được đặt rõ thay vì phụ thuộc giá trị mặc định.
- `destroyMethod="dispose"` giải phóng custom provider khi Spring context dừng.
- Pool name `catalog-pool` giúp phân biệt downstream trong metrics tags.

Nếu có nhiều downstream, cân nhắc một `ConnectionProvider` riêng cho từng trust boundary hoặc workload có timeout/capacity khác nhau. Không tạo một provider mới cho từng request.

### 9.1. Service gọi target

~~~java
@Service
public class CatalogClient {

    private final WebClient catalogWebClient;

    public CatalogClient(WebClient catalogWebClient) {
        this.catalogWebClient = catalogWebClient;
    }

    public Mono<String> fetchWork() {
        return catalogWebClient.get()
            .uri("/work")
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

Response body được consume qua `bodyToMono`. Nếu dùng `exchangeToMono` hoặc `ResponseEntity<Flux<T>>`, caller phải bảo đảm body được consume hoặc release để connection có thể được trả về pool.

### 9.2. Endpoint demo

~~~java
@RestController
@RequestMapping("/api/catalog")
public class CatalogProbeController {

    private final CatalogClient client;

    public CatalogProbeController(CatalogClient client) {
        this.client = client;
    }

    @GetMapping("/probe")
    public Mono<ResponseEntity<String>> probe() {
        return client.fetchWork()
            .map(ResponseEntity::ok)
            .onErrorResume(WebClientException.class, error ->
                Mono.just(ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("Catalog service is temporarily unavailable")));
    }
}
~~~

Controller chuyển lỗi outbound thành response an toàn. Trong production, có thể phân biệt timeout/pool capacity, lỗi kết nối và status 5xx để chọn error code phù hợp; không trả raw exception message cho client.

## 10. Cấu hình Spring Boot Actuator và Prometheus

Thêm các dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Cấu hình `application.properties`:

~~~properties
catalog.base-url=http://localhost:9090

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.distribution.percentiles-histogram.http.client.requests=true
~~~

Khi ứng dụng chạy, có thể xem:

~~~text
GET /actuator/health
GET /actuator/metrics
GET /actuator/metrics/http.client.requests
GET /actuator/metrics/reactor.netty.connection.provider.active.connections
GET /actuator/metrics/reactor.netty.connection.provider.pending.connections
GET /actuator/prometheus
~~~

`/actuator/metrics` là endpoint chẩn đoán theo meter name; `/actuator/prometheus` xuất định dạng scrape nếu Prometheus registry có mặt. Trong production, chỉ expose Actuator theo network/security policy phù hợp; không mở metrics endpoint công khai cho Internet.

### 10.1. Tìm metrics qua Actuator

Ví dụ:

~~~bash
curl -s http://localhost:8080/actuator/metrics/reactor.netty.connection.provider.active.connections
curl -s http://localhost:8080/actuator/metrics/reactor.netty.connection.provider.pending.connections
curl -s http://localhost:8080/actuator/metrics/reactor.netty.connection.provider.pending.connections.time
curl -s http://localhost:8080/actuator/metrics/reactor.netty.http.client.response.time
~~~

Endpoint có thể trả measurements và available tags. Dùng query `tag` để lọc theo pool/service nếu meter đã đăng ký tag tương ứng. Tên tag và cách chuyển đổi sang Prometheus label phụ thuộc meter/registry; kiểm tra output thực tế trước khi viết dashboard.

## 11. Dashboard cần có gì?

Không nên chỉ tạo một biểu đồ “connection count”. Một dashboard tốt cho từng downstream cần nhóm thông tin theo cùng trục thời gian.

### 11.1. Pool saturation

- Active connections.
- Max connections.
- Idle connections.
- Pending connections.
- Pending acquire duration p50/p95/p99.
- Pending queue limit và số lần acquire timeout/rejection.

Có thể tính tỷ lệ sử dụng:

\[
\text{pool utilization} =
\frac{\text{active connections}}{\text{max connections}}
\]

Tỷ lệ cao trong thời gian ngắn không nhất thiết là sự cố. Cần xem cùng pending queue và acquire wait. Active gần max nhưng pending bằng 0 có thể là pool đang sử dụng hiệu quả.

### 11.2. Network và HTTP

- DNS resolution time.
- TCP connect time.
- TLS handshake time.
- Request/response duration.
- Data sent/received.
- HTTP client error rate.
- Status code từ target.
- Timeout và retry count.

### 11.3. Target service

- RPS/in-flight requests.
- p95/p99 latency phía server.
- 429/503/5xx rate.
- Queue depth/worker saturation.
- CPU/memory/event-loop utilization.
- Database/cache latency và connection pool của target.

### 11.4. Application impact

- API latency của caller.
- Request error rate.
- Số request bị shed hoặc rejected.
- Retry amplification.
- In-flight outbound operations.
- Cancellation và timeout.

Dashboard phải cho thấy cùng một đợt tăng tải từ caller tới downstream và quay lại response.

## 12. Alert theo triệu chứng và SLO

Không dùng một ngưỡng `active/max > 80%` làm alert duy nhất. Alert nên kết hợp thời gian kéo dài, pending queue và ảnh hưởng user.

Ví dụ hướng dẫn alert:

| Điều kiện | Ý nghĩa | Hành động |
| --- | --- | --- |
| Pending connections > 0 kéo dài và acquire p95 tăng | Pool bắt đầu queue | Xem concurrency, body consumption và response time |
| Pending acquire timeout tăng | Caller không lấy được connection đúng hạn | Giảm load hoặc điều chỉnh pool sau khi xác định nguyên nhân |
| Target p99 tăng cùng 429/503 | Target bị saturation/rate-limit | Load shed, giảm concurrency, phối hợp mở rộng target |
| Connect/TLS time tăng mạnh | Network hoặc connection churn | Kiểm tra DNS, network, TLS termination và idle eviction |
| Stale connection errors sau idle | Timeout client/server lệch nhau | Điều chỉnh maxIdleTime và kiểm tra load balancer |
| Connection count/FD tăng không giới hạn | Pool leak hoặc nhiều pool được tạo động | Kiểm tra lifecycle provider, host cardinality và bean scope |

Alert nên có:
- `for` duration để tránh cảnh báo từ spike ngắn.
- Threshold dựa trên SLO/traffic baseline.
- Tách warning (pending tăng) và critical (acquire timeout + user-facing errors).
- Runbook chỉ rõ metric, log, trace và dashboard cần mở.

Không alert chỉ vì idle connections > 0 hoặc active connections gần max trong một vài giây.

## 13. Thiết kế pool size và pending queue

### 13.1. Ước lượng từ traffic và latency

Bắt đầu với concurrency trung bình:

\[
C_{\text{avg}} \approx RPS_{\text{per instance}} \times W_{\text{avg}}
\]

Sau đó đo burst, tail latency và mức concurrency an toàn của target. Pool max cần:
- Đủ xử lý peak hợp lệ.
- Không lớn tới mức một replica có thể làm target quá tải.
- Tính đến số replica và client pool khác.
- Có giới hạn pending queue và timeout.
- Có margin cho request chậm, retry và traffic burst đã dự đoán.

### 13.2. Queue không phải capacity

Tăng pending queue chỉ cho phép nhiều request chờ hơn. Nó không làm target xử lý nhanh hơn. Nếu server phục vụ 100 request đồng thời nhưng client xếp 10.000 request vào queue, latency có thể tăng rất lớn và memory bị giữ lâu.

Hãy chọn:
- Queue nhỏ và timeout ngắn khi caller cần phản hồi nhanh.
- Queue vừa phải khi workload có burst ngắn và target có khả năng phục hồi.
- Fast fail/load shed khi downstream đã bão hòa.
- Durable queue/message broker cho công việc nền cần chờ lâu; không dùng connection pending queue làm hàng đợi nghiệp vụ.

### 13.3. Không tăng maxConnections để chữa target chậm

Nếu target latency tăng do database chậm, tăng pool sẽ làm nhiều request cùng chờ database và có thể tạo thêm áp lực. Trước khi tăng max:
1. Kiểm tra target p95/p99 và queue.
2. Kiểm tra request đang giữ connection bao lâu.
3. Kiểm tra response body có được consume.
4. Kiểm tra target safe concurrency.
5. Tính tổng kết nối từ mọi replica.
6. Thử thay đổi nhỏ trong load test và so sánh SLO.

## 14. Giảm tải và bảo vệ downstream

### 14.1. Bulkhead và giới hạn concurrency

Có thể giới hạn số request đồng thời tới một dependency ở tầng ứng dụng, độc lập với pool connection. Ví dụ dùng `flatMap` với concurrency hữu hạn cho batch:

~~~java
Flux<Result> processBatch(Flux<Command> commands) {
    return commands.flatMap(
        command -> catalogClient.fetch(command),
        16
    );
}
~~~

Con số `16` giới hạn concurrency trong pipeline này. Nó không thay thế pool max, nhưng giúp một luồng batch không chiếm toàn bộ năng lực outbound.

### 14.2. Retry có chọn lọc

Retry có thể nhân tải khi target đang lỗi. Chỉ retry:
- Lỗi transient đã xác định.
- Operation idempotent hoặc có idempotency key.
- Số lần nhỏ, backoff và jitter.
- Có timeout tổng thể.
- Tôn trọng `Retry-After` khi phù hợp.

Không retry pool acquire timeout một cách mù quáng; caller đang thiếu capacity local, retry ngay có thể làm queue lớn thêm. Không retry 400/401/403 theo mặc định. Với 429/503, phối hợp rate limit và retry budget.

### 14.3. Circuit breaker và load shedding

Circuit breaker có thể tạm ngừng gửi request khi failure/slow-call rate vượt ngưỡng, rồi thử lại sau thời gian open. Load shedding từ chối công việc ít ưu tiên trước khi hàng đợi phình ra.

Fallback phải có giới hạn và semantics rõ. Không tạo một fallback gọi sang dependency khác cũng đang quá tải.

### 14.4. Response body và connection release

Một response body chưa được tiêu thụ có thể khiến connection không được trả pool như mong đợi. Với `retrieve().bodyToMono(...)` hoặc `bodyToFlux(...)`, hãy consume body trong reactive chain. Với `exchangeToMono`, đảm bảo mọi nhánh xử lý status đều đọc, release hoặc chuyển giao body.

Không gọi `subscribe()` phụ để đọc response rồi trả kết quả sớm. Không `block()` trên WebFlux event-loop.

## 15. Load test để tìm giới hạn an toàn

Một load test hữu ích phải kiểm tra cả pool lẫn target. Chạy trên staging hoặc môi trường có capacity được phê duyệt; tránh tạo tải không giới hạn lên production.

### 15.1. Các pha kiểm thử

1. **Warm-up:** khởi tạo event loop, DNS, TLS và pool; không lấy latency cold-start làm baseline steady-state.
2. **Baseline:** traffic thấp, xác nhận metrics và connection reuse.
3. **Ramp-up:** tăng RPS/concurrency từng bước.
4. **Steady state:** giữ tải ở từng mức đủ lâu để pending/latency ổn định.
5. **Burst:** tạo spike ngắn để xem queue và recovery.
6. **Idle gap:** dừng traffic rồi gửi request đầu tiên để tìm stale idle connection.
7. **Target degradation:** làm target chậm hoặc trả 503 có kiểm soát để kiểm tra timeout/circuit breaker.
8. **Recovery:** giảm tải và quan sát pending queue, active connection và error rate trở về bình thường.

### 15.2. Những gì cần ghi cho mỗi mức tải

| Nhóm | Số liệu |
| --- | --- |
| Load generator | Offered RPS, completed RPS, concurrency, dropped iterations |
| Client pool | Active/max, idle, pending, acquire p95/p99 |
| HTTP client | DNS/connect/TLS/response p95/p99, errors, status |
| Target | RPS, in-flight, queue depth, p95/p99, 429/503/5xx |
| Runtime | CPU, heap/direct memory, event-loop pending tasks, file descriptors |
| Business | API latency và error rate caller nhìn thấy |

Ghi cả offered load và completed throughput. Nếu chỉ nhìn completed RPS, hệ thống có thể trông ổn trong khi load generator đang bỏ rơi hoặc xếp hàng request.

### 15.3. Ví dụ k6 test script

~~~javascript
import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    steady: {
      executor: "constant-arrival-rate",
      rate: 100,
      timeUnit: "1s",
      duration: "3m",
      preAllocatedVUs: 40,
      maxVUs: 160
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500", "p(99)<1000"]
  }
};

export default function () {
  const response = http.get(`${__ENV.BASE_URL}/api/catalog/probe`);
  check(response, {
    "status is 200": (r) => r.status === 200
  });
}
~~~

Chạy:

~~~bash
BASE_URL=http://localhost:8080 k6 run load-test.js
~~~

Trên Windows PowerShell:

~~~powershell
$env:BASE_URL = "http://localhost:8080"
k6 run load-test.js
~~~

Script là baseline minh họa. Hãy tăng tải từ thấp lên cao, đặt ngưỡng phù hợp với SLO thực tế và xác nhận `maxVUs` đủ cho arrival rate. Nếu target trả lỗi, không tăng traffic vô hạn để “thử thêm”.

## 16. Ví dụ project Java 17+ chạy được

Project sau tạo một WebClient riêng tới Catalog, bật pool/HTTP metrics, cấu hình timeout và test request thành công/lỗi bằng MockWebServer.

### 16.1. Cấu trúc

~~~text
webclient-pool-observability/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/pool/
│   ├── PoolObservabilityApplication.java
│   ├── CatalogWebClientConfiguration.java
│   ├── CatalogClient.java
│   └── CatalogProbeController.java
└── src/test/java/com/example/pool/
    └── CatalogClientIntegrationTest.java
~~~

### 16.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webclient-pool-observability</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 16.3. application.properties

~~~properties
catalog.base-url=http://localhost:9090

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.distribution.percentiles-histogram.http.client.requests=true
~~~

Trong production, đặt `catalog.base-url` bằng environment/config management và bảo vệ các Actuator endpoints bằng network policy/authentication.

### 16.4. PoolObservabilityApplication.java

~~~java
package com.example.pool;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PoolObservabilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(PoolObservabilityApplication.class, args);
    }
}
~~~

### 16.5. CatalogWebClientConfiguration.java

~~~java
package com.example.pool;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
public class CatalogWebClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogConnectionProvider() {
        return ConnectionProvider.builder("catalog-pool")
            .maxConnections(32)
            .pendingAcquireMaxCount(64)
            .pendingAcquireTimeout(Duration.ofMillis(500))
            .maxIdleTime(Duration.ofSeconds(25))
            .maxLifeTime(Duration.ofMinutes(5))
            .maxLifeTimeVariance(5)
            .evictInBackground(Duration.ofSeconds(30))
            .metrics(true)
            .build();
    }

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            ConnectionProvider catalogConnectionProvider,
            @Value("${catalog.base-url}") String baseUrl) {

        HttpClient httpClient =
            HttpClient.create(catalogConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
                .responseTimeout(Duration.ofSeconds(2))
                .metrics(true, uri -> {
                    if (uri.startsWith("/items/")) {
                        return "/items/{id}";
                    }
                    return uri;
                });

        return builder
            .baseUrl(baseUrl)
            .clientConnector(
                new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
~~~

### 16.6. CatalogClient.java

~~~java
package com.example.pool;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class CatalogClient {

    private final WebClient catalogWebClient;

    public CatalogClient(WebClient catalogWebClient) {
        this.catalogWebClient = catalogWebClient;
    }

    public Mono<String> fetchWork() {
        return catalogWebClient.get()
            .uri("/work")
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

### 16.7. CatalogProbeController.java

~~~java
package com.example.pool;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClientException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/catalog")
public class CatalogProbeController {

    private final CatalogClient client;

    public CatalogProbeController(CatalogClient client) {
        this.client = client;
    }

    @GetMapping("/probe")
    public Mono<ResponseEntity<String>> probe() {
        return client.fetchWork()
            .map(ResponseEntity::ok)
            .onErrorResume(WebClientException.class, error ->
                Mono.just(ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("Catalog service is temporarily unavailable")));
    }
}
~~~

### 16.8. CatalogClientIntegrationTest.java

~~~java
package com.example.pool;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CatalogClientIntegrationTest {

    private static final MockWebServer SERVER = startServer();

    @Autowired
    CatalogClient catalogClient;

    private static MockWebServer startServer() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        }
        catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "catalog.base-url",
            () -> SERVER.url("/").toString());
    }

    @AfterAll
    static void stopServer() throws IOException {
        SERVER.shutdown();
    }

    @Test
    void successfulRequestUsesTargetAndConsumesBody()
            throws Exception {

        SERVER.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("catalog-ready"));

        String body = catalogClient.fetchWork()
            .block(Duration.ofSeconds(3));

        assertEquals("catalog-ready", body);

        RecordedRequest request =
            SERVER.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/work", request.getPath());
    }

    @Test
    void target503BecomesWebClientResponseException() {
        SERVER.enqueue(new MockResponse()
            .setResponseCode(503)
            .addHeader("Content-Type", "text/plain")
            .setBody("temporarily unavailable"));

        WebClientResponseException error = assertThrows(
            WebClientResponseException.class,
            () -> catalogClient.fetchWork()
                .block(Duration.ofSeconds(3)));

        assertEquals(503, error.getStatusCode().value());
    }
}
~~~

`block()` chỉ xuất hiện trong test để assertion đồng bộ. Trong controller/service production, giữ `Mono` và compose reactive chain.

### 16.9. Chạy và quan sát

Yêu cầu JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Khi target service chạy ở `catalog.base-url`, thử:

~~~bash
curl -i http://localhost:8080/api/catalog/probe
curl -s http://localhost:8080/actuator/metrics/reactor.netty.connection.provider.active.connections
curl -s http://localhost:8080/actuator/metrics/reactor.netty.connection.provider.pending.connections
curl -s http://localhost:8080/actuator/metrics/reactor.netty.http.client.response.time
curl -s http://localhost:8080/actuator/prometheus
~~~

MockWebServer test chứng minh client gửi request và xử lý status. Để kiểm tra pool saturation/idle eviction thực tế, chạy load test riêng với target có latency và concurrency được kiểm soát; test chức năng ngắn không chứng minh sizing đã tối ưu.

## 17. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ nhìn `active.connections` | Không biết request có đang chờ hay không | Xem `max`, `pending` và acquire timer cùng lúc |
| Coi idle connection là lỗi | Scale down pool không cần thiết | Idle là capacity tái sử dụng; đánh giá với traffic và eviction |
| Tăng `maxConnections` khi target chậm | Tăng áp lực lên target | Kiểm tra server queue/latency, giới hạn concurrency |
| Pending queue không giới hạn | Queue và latency phình ra | Đặt `pendingAcquireMaxCount` hữu hạn |
| `pendingAcquireTimeout` quá dài | Request giữ tài nguyên lâu | Gắn timeout với budget tổng |
| Không đặt `maxIdleTime` | Tái sử dụng stale connection sau idle | Chọn theo idle timeout ngắn nhất của target/LB |
| `maxLifeTime` quá ngắn | TCP/TLS churn | Đặt tuổi thọ theo nhu cầu và đo handshake |
| Mỗi service method tạo ConnectionProvider mới | Nhiều pool trùng lặp | Dùng provider singleton theo dependency |
| Không consume response body | Connection bị giữ lâu hoặc không release đúng lúc | Consume/release mọi nhánh response |
| Dùng URI động làm metric tag | Cardinality và memory tăng mạnh | Chuẩn hóa route template và giới hạn tag |
| Chỉ bật Boot HTTP metrics, bỏ pool metrics | Không thấy pending acquire | Bật `ConnectionProvider.metrics(true)` |
| Chỉ bật pool metrics, bỏ HTTP client metrics | Thiếu DNS/connect/TLS/response timing | Bật `HttpClient.metrics(true, uriMapper)` |
| Cộng các timer khác boundary | Latency tổng bị tính trùng | Hiểu semantics từng meter trước khi tính |
| Retry ngay khi acquire timeout | Tự tạo thêm cạnh tranh pool | Fail fast, shed load hoặc giới hạn concurrency |
| Chỉ đo client, không đo target | Không biết queue/CPU server | Ghép metrics client với server và trace |
| Chỉ test local happy path | Không thấy stale/overload behavior | Thêm idle gap, slow target, 429/503 và load test |
| Mở Actuator metrics ra Internet | Lộ thông tin vận hành | Bảo vệ endpoint bằng auth/network policy |

## 18. Quy trình điều tra sự cố cạn kết nối

Khi có cảnh báo pending acquire hoặc timeout:

1. Chọn đúng downstream/pool và khoảng thời gian bắt đầu sự cố.
2. Xem `active`, `max`, `idle`, `pending` và acquire timer.
3. Xem HTTP client DNS, connect, TLS và response time.
4. Xem status 429/503/5xx, request rate và retry count.
5. Đối chiếu target-side in-flight requests, queue, CPU, worker và database.
6. Kiểm tra response body có được consume ở mọi nhánh hay không.
7. Kiểm tra request/stream dài, timeout, cancellation và connection lifecycle.
8. Kiểm tra số replica nhân với pool max và số WebClient/provider độc lập.
9. Nếu lỗi sau idle, so sánh client `maxIdleTime` với timeout của target/load balancer.
10. Chọn một thay đổi nhỏ, load test lại và so SLO trước/sau.

Dùng trace để xác định request mất thời gian ở client pool, network hay server handler. Correlation ID/trace ID giúp nối một request cụ thể; metrics cho thấy xu hướng và mức độ của toàn hệ thống.

## 19. Checklist production

- [ ] Mỗi downstream có pool identity và dashboard riêng.
- [ ] `maxConnections` được tính theo từng replica và tổng deployment.
- [ ] `pendingAcquireMaxCount` hữu hạn.
- [ ] `pendingAcquireTimeout` nằm trong request budget.
- [ ] `maxIdleTime` không lớn hơn idle timeout ngắn nhất của target/LB.
- [ ] `maxLifeTime` và eviction được chọn dựa trên traffic/network.
- [ ] Pool metrics bật bằng `ConnectionProvider.metrics(true)`.
- [ ] HTTP client metrics bật bằng `HttpClient.metrics(true, uriMapper)`.
- [ ] WebClient dùng Boot auto-configured builder để có `http.client.requests`.
- [ ] URI tag được chuẩn hóa; không dùng ID/path động, user ID hoặc correlation ID làm metric tag.
- [ ] Dashboard có active/max/idle/pending/acquire time, DNS/connect/TLS/response và status/error rate.
- [ ] Target-side metrics có RPS, in-flight, p95/p99, queue, CPU, worker và dependency latency.
- [ ] HTTP/2 theo dõi stream metrics, không chỉ connection count.
- [ ] Response body được consume/release trong mọi nhánh.
- [ ] Retry có giới hạn, backoff, jitter và idempotency policy.
- [ ] Bulkhead/load shedding bảo vệ target khi bão hòa.
- [ ] Actuator được expose có kiểm soát.
- [ ] Load test gồm steady, burst, idle gap, target slow/error và recovery.
- [ ] Có runbook tìm theo pool name, service, trace và thời điểm.

## 20. Bài tập thực hành

**Bài 1 – Bật pool metrics.** Tạo `ConnectionProvider` có tên, `maxConnections=8`, pending queue giới hạn và `metrics(true)`. Gửi nhiều request đồng thời rồi quan sát active/idle/pending.

**Bài 2 – Phân biệt acquire với response timeout.** Đặt pool max thấp, làm target chậm có kiểm soát. Quan sát pending acquire timer trước khi request được gửi và response timer sau khi request tới target.

**Bài 3 – Idle connection.** Dừng traffic lâu hơn idle timeout của load balancer rồi gửi request. So sánh lỗi trước/sau khi client `maxIdleTime` được đặt thấp hơn timeout đó.

**Bài 4 – Target overload.** Cho target trả 503 hoặc tăng latency. Theo dõi client response time, active/pending connections và server queue; thử giảm concurrency.

**Bài 5 – Nhiều replica.** Tính tổng connection potential từ replica count, pool count và max connections. Đối chiếu với capacity đã công bố của target.

**Bài 6 – HTTP/2.** Chạy client HTTP/2, quan sát active/pending streams và so sánh với connection metrics.

**Bài 7 – Load test.** Dùng k6/Gatling tăng arrival rate theo từng mức. Ghi p95/p99, error rate, completed throughput và pool saturation.

**Bài 8 – Retry budget.** Tạo target 429/503; thử retry có backoff/jitter và không retry. So sánh tổng request target nhận được để thấy retry amplification.

**Bài 9 – Body consumption.** Tạo một nhánh WebClient không consume response body và một nhánh consume đầy đủ; quan sát connection release/pool reuse và sửa lifecycle.

**Bài 10 – Alert.** Tạo cảnh báo khi pending acquire kéo dài kèm p95 vượt SLO hoặc acquire timeout tăng; xác nhận alert không bắn chỉ vì idle connection > 0.

## 21. Tài liệu tham khảo chính thức

1. Reactor Netty Reference Guide – HTTP Client, Connection Pool, Metrics và Timeout Configuration: https://projectreactor.io/docs/netty/release/reference/http-client.html
2. Spring Boot 4.0 – Actuator Metrics và HTTP Client Metrics: https://docs.spring.io/spring-boot/4.0/reference/actuator/metrics.html
3. Spring Framework – WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
4. Spring Framework – WebClient filters và exchange handling: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html
5. Micrometer – Meters, Timer, Counter, Gauge và Tags: https://docs.micrometer.io/micrometer/reference/concepts/meters.html
6. Micrometer – Histograms and Percentiles: https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html
7. Reactor Core – Backpressure và Reactor reference: https://projectreactor.io/docs/core/release/reference/
8. Spring Boot – System Requirements: https://docs.spring.io/spring-boot/system-requirements.html

**Tự đánh giá cuối:** Khi `active.connections` chạm max và pending tăng, bạn cần kiểm tra gì để biết pool nhỏ hay target chậm? Vì sao idle connection không tự động là lỗi? `pendingAcquireTimeout` khác `responseTimeout` ở đâu? Vì sao tăng pool trên mọi replica có thể làm target quá tải? Nếu dashboard có pool, network, response và server-side saturation metrics, bạn có thể tìm đúng tầng gây nghẽn thay vì chỉ tăng số connection.
