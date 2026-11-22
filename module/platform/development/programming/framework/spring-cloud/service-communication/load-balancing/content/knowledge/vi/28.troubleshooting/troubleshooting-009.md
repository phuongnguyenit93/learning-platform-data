# Pool cạn, event-loop bị chặn và độ trễ tăng cao

Một hệ thống dùng **Spring Cloud LoadBalancer** có thể chọn đúng `ServiceInstance` nhưng request vẫn chậm hàng giây, timeout hoặc thất bại hàng loạt. Ba nguyên nhân thường bị nhầm với nhau là:

1. **HTTP connection pool cạn**: request phải chờ một connection rảnh trước khi được gửi.
2. **Event-loop bị chặn**: một hoặc vài thread phụ trách xử lý I/O/reactive callback bị giữ bởi tác vụ blocking/CPU dài, khiến nhiều request khác cùng chậm.
3. **Độ trễ downstream thực sự tăng**: backend, database, DNS, TLS, mạng hoặc proxy chậm; connection bị giữ lâu hơn và có thể **gây ra** pool saturation.

Cả ba có thể xảy ra đồng thời: downstream chậm làm connection đang dùng lâu hơn; pool bắt đầu có hàng đợi; retry nhân lượng request và đẩy độ trễ lên cao; nếu đồng thời có mã blocking trên event-loop, tình hình còn xấu hơn. **Tăng `maxConnections` không phải phương thuốc chung**.

Bài thuộc chương **Chẩn đoán sự cố** của module Spring Cloud LoadBalancer. Bạn sẽ học cách định vị giai đoạn chậm trên đường gọi từ service ID tới instance thật; kiểm tra `RestClient`/Apache HttpClient 5, `WebClient`/Reactor Netty, OpenFeign; nhận diện blocking trong Spring WebFlux; và thiết kế thí nghiệm tải để chứng minh nguyên nhân trước khi chỉnh cấu hình.

> Các con số pool/timeout/RPS trong bài chỉ là **giá trị lab để tái hiện**, không phải cấu hình production mặc định. API có thể khác giữa các phiên bản Spring Boot, Spring Cloud, Apache HttpClient và Reactor Netty; dùng release train/BOM tương thích.

## 1. Định vị pool và event-loop trên đường gọi

~~~mermaid
flowchart TD
    A["Caller gọi http://catalog-service"]
    B["Spring Cloud LoadBalancer<br/>chọn ServiceInstance"]
    C["Địa chỉ vật lý<br/>catalog-a:8081"]
    D{"Có connection rảnh<br/>hoặc được phép tạo mới?"}
    E["Đợi pool acquisition"]
    F["DNS / TCP / TLS nếu cần"]
    G["Gửi request / chờ response"]
    H["Đọc body / decode"]
    I["Hoàn tất operation"]
    J["Pool pending timeout<br/>hoặc pending queue full"]
    K["Connect / response timeout"]
    A --> B --> C --> D
    D -->|"Không"| E
    E -->|"Quá hạn / đầy"| J
    E -->|"Có slot"| F
    D -->|"Có"| F
    F -->|"Lỗi"| K
    F --> G
    G -->|"Timeout"| K
    G --> H --> I
~~~

**Spring Cloud LoadBalancer thực hiện selection**, không sở hữu toàn bộ cơ chế mượn connection hoặc thực thi I/O. Sau khi chọn instance, client HTTP vẫn phải:

- Lấy connection từ pool hoặc mở connection mới.
- Kết nối tới host/port của instance.
- Gửi request, chờ server xử lý và đọc response.
- Giải mã body theo HTTP/JSON contract.
- Trả connection về pool khi vòng đời response kết thúc phù hợp.

Trong `WebClient` với Reactor Netty, nhiều công đoạn I/O và callback chạy trên **event-loop threads**. Nếu một callback thực hiện `Thread.sleep`, JDBC blocking hoặc xử lý CPU quá lâu trên event-loop, các connection/request khác cùng sử dụng thread đó có thể bị chậm dù pool **chưa** cạn.

### Không gộp ba loại hàng đợi

| Hàng đợi / tài nguyên | Ví dụ | Cần quan sát |
|---|---|---|
| Connection pool | Chờ mượn HTTP connection | `leased`/`pending`, active/idle, acquire duration |
| Thread hoặc event-loop | Task chờ thread xử lý | Thread dumps, event-loop pending tasks/latency, blocked-stack |
| Downstream/backend | Request đã đến server nhưng xử lý lâu | Server latency, DB pool, queue depth, tracing |

Ba nơi này có thể cùng tăng nhưng **cách sửa khác nhau**. Pool không đủ gây queue trước request; backend chậm gây queue sau request; event-loop bị chặn có thể trì hoãn cả việc đọc phản hồi và trả connection.

## 2. Ma trận triệu chứng: bắt đầu từ bằng chứng nào?

| Triệu chứng | Nghi vấn chính | Dữ liệu để xác nhận |
|---|---|---|
| Pool `leased≈max`, `pending` tăng | Pool bão hòa hoặc connection bị giữ lâu | Pool stats **theo route** và tổng |
| Pending acquire timeout, không thấy backend nhận request | Request chờ mượn connection quá hạn | Acquire-time metric, pending queue, leased |
| Pool `leased` thấp nhưng HTTP chậm | Không phải bão hòa pool hiện tại; có thể DNS, backend, event-loop | Phân rã latency, thread dumps, tracing |
| Nhiều request WebClient cùng chậm; thread `reactor-http-nio-*` bận ở `sleep`/JDBC | Event-loop bị blocking | Thread dump nhiều thời điểm, BlockHound/test |
| Error rate tăng khi bật retry | Retry amplification | Operations vs attempts, RPS backend, timeout |
| Chỉ một instance chậm, các instance khác bình thường | Backend hot spot hoặc lỗi route riêng | Breakdown theo `ServiceInstance`, server metrics |
| Cache/discovery trả một instance đã chết | Candidate list stale | Instance selection, health/cache/registry |
| Lỗi `Connection refused` | Không có process nghe ở host/port được chọn | Selected URI, port, container health |
| TLS/`UnknownHost` trước HTTP response | Network/DNS/TLS lỗi | Transport cause, URI vật lý |
| JSON decode lỗi với status 200 | Contract hoặc codec, không phải pool | Content-Type, schema/cause được kiểm soát |

**Không dựa một mình vào HTTP 500, latency p99 hoặc từ “timeout” trong exception.** Hãy xác nhận request đã đi tới backend chưa, đã mượn được connection chưa, và thread nào đang giữ thời gian.

## 3. Hiểu đúng “pool cạn”

Một connection pool có hai nhóm đối tượng cơ bản:

- **Connection đang được sử dụng**: đã được mượn và chưa hoàn thành vòng đời request/response.
- **Connection có thể tái sử dụng**: idle/available, tùy chính sách keep-alive, expiry và trạng thái socket.

Khi tất cả connection đủ điều kiện đều đang bận và pool đã đạt giới hạn, request mới **chờ trong hàng đợi acquire**, bị từ chối nếu pending queue đầy, hoặc timeout nếu chờ quá lâu.

~~~text
Requests -> [HTTP pool acquire queue] -> [Leased connections] -> Backend
                    |                       |
               wait/timeout             active requests
~~~

### Các timeout không tương đương

| Timeout/budget | Tính từ đâu? | Ví dụ nguyên nhân |
|---|---|---|
| **Pool acquisition / connection request timeout** | Chờ pool cấp một connection | Tất cả connection bận, pending queue lớn |
| **Connect timeout** | Mở TCP tới endpoint vật lý | IP/port không reachable, network lỗi |
| **TLS handshake timeout** | Hoàn tất bắt tay TLS theo transport | TLS/network/certificate |
| **Response/read timeout** | Chờ dữ liệu/response theo semantics HTTP client | Backend chậm, network stall |
| **Operation/deadline tổng** | Toàn bộ lời gọi nghiệp vụ qua các giai đoạn và attempts | Chờ pool + connect + response + retry |
| **Timeout ở backend** | Downstream/DB hoặc proxy nội bộ | DB contention, overload |

Ví dụ client có `responseTimeout=2s` không đồng nghĩa toàn bộ operation luôn kết thúc trong 2 giây nếu trước đó đã **chờ pool 1 giây**, hoặc còn nhiều attempts. Thiết lập deadline end-to-end riêng khi ứng dụng yêu cầu giới hạn tổng thời gian.

### Connection leak có thể trông giống pool sizing sai

Nếu response stream không được tiêu thụ/đóng theo hợp đồng HTTP client, connection có thể không quay về pool. Khi `leased` tăng không giảm kể cả lưu lượng đã ngừng, phải nghi response lifecycle/stream leak trước khi tăng `maxConnections`.

Ở Spring `RestClient.retrieve().body(...)` thông thường, framework quản lý quá trình đọc/đóng response. Với API thấp hơn, streaming hoặc Apache/Feign client thủ công, người viết code phải đặc biệt chú ý đóng/consume response đúng cách. Không tự đọc raw response rồi bỏ ngang mà không kiểm soát resource lifecycle.

## 4. Công thức tư duy về độ đồng thời và dung lượng

Một ước lượng hữu ích trong trạng thái ổn định là **Little's Law**:

\[
L \approx \lambda \times W
\]

Trong đó:

- `L`: số request trung bình đồng thời đang ở một giai đoạn.
- `λ`: throughput trung bình, tính bằng request/giây.
- `W`: thời gian trung bình mỗi request ở giai đoạn đó, tính bằng giây.

Nếu 100 request/giây giữ connection khoảng 0,4 giây, số request đang giữ connection **trung bình có thể khoảng 40**. Đây không phải công thức tự động chọn `maxConnections=40`: cần dự phòng burst, phân phối theo instance, HTTP protocol, pool reuse, backend capacity và các giai đoạn không giữ connection.

Quan trọng hơn, **giữ nguyên RPS nhưng response time tăng** sẽ tăng số request đồng thời. Ví dụ từ 0,1 giây lên 0,8 giây có thể làm số connection cần phục vụ cùng lượng công việc tăng gấp nhiều lần, ngay cả khi không có “rò rỉ connection”.

### Tác động của một instance chậm

Giả sử `catalog-service` có hai `ServiceInstance`:

~~~text
catalog-a:8081 -> xử lý trong 80 ms
catalog-b:8081 -> xử lý trong 900 ms
~~~

Round-robin có thể đưa request tới cả hai. Những request trên B giữ connection lâu hơn, làm pool/queue của **route B** bão hòa trước. **Chuyển random sang round-robin hoặc ngược lại không chữa được root cause B chậm**.

Để xử lý đúng cần số liệu **tách theo instance hoặc physical route**, không chỉ một biểu đồ latency toàn service ID.

## 5. Apache HttpClient 5: phân biệt pool tổng và theo route

Với `RestClient` blocking dùng Apache HttpClient 5, `PoolingHttpClientConnectionManager` quản lý connection pool. Hai giới hạn thường quan trọng:

- `maxConnTotal`: giới hạn tổng số connection do **một connection manager** quản lý.
- `maxConnPerRoute`: giới hạn cho từng `HttpRoute`, thường gắn với scheme/host/port, có thể gồm proxy/tunnel tùy cấu hình.

Đường đi:

~~~text
catalog-service
  -> catalog-a:8081  [HttpRoute A]  max per-route: 10
  -> catalog-b:8081  [HttpRoute B]  max per-route: 10

Shared connection manager:
  maxConnTotal: 15
~~~

Ở ví dụ này **không thể** có đồng thời 10 connection tới A và 10 connection tới B trong cùng manager khi tổng giới hạn chỉ 15. Nếu A đang giữ 10, B có thể chỉ lấy được tối đa 5 cho tới khi tài nguyên được trả lại.

Với Spring Cloud LoadBalancer, **service ID không nhất thiết là pool route**. LoadBalancer chọn URI vật lý trước; HTTP manager có thể thấy nhiều route khác nhau tương ứng từng instance. Nếu HTTP proxy được sử dụng, cách xác định route cần được xác minh theo transport thực tế.

### Các chỉ số cơ bản của Apache manager

| Chỉ số | Ý nghĩa | Khi bất thường |
|---|---|---|
| `getLeased()` | Connection đã cấp và còn được sử dụng | Sát `getMax()` kéo dài |
| `getAvailable()` | Connection đang idle có thể tái sử dụng | Thấp trong giai đoạn bận không tự đủ kết luận |
| `getPending()` | Request đang chờ mượn connection | Tăng bền vững là tín hiệu queue |
| `getMax()` | Giới hạn pool tương ứng | Cần đối chiếu total **và** route |

Kết quả `getTotalStats()` là snapshot. Để biết route nào gây nghẽn cần lấy thống kê **theo `HttpRoute`** tương ứng, hoặc dùng metrics của transport/HTTP client, nếu framework/phiên bản hỗ trợ.

## 6. Mẫu RestClient có connection manager quan sát được

Ví dụ sau minh họa **Java 17+, Spring Framework 6.1+ và Apache HttpClient 5** với dependency phù hợp:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    implementation("org.apache.httpcomponents.client5:httpclient5")
}
~~~

Cấu hình sample:

~~~java
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogRestClientConfiguration {

    @Bean("catalogConnectionManager")
    PoolingHttpClientConnectionManager catalogConnectionManager() {
        return PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(12)
                .setMaxConnPerRoute(6)
                .build();
    }

    @Bean(value = "catalogApacheClient", destroyMethod = "close")
    CloseableHttpClient catalogApacheClient(
            @Qualifier("catalogConnectionManager")
            PoolingHttpClientConnectionManager manager) {

        RequestConfig requests = RequestConfig.custom()
                .setConnectionRequestTimeout(
                        Timeout.ofMilliseconds(300))
                .setResponseTimeout(
                        Timeout.ofSeconds(2))
                .build();

        return HttpClients.custom()
                .setConnectionManager(manager)
                .setDefaultRequestConfig(requests)
                .evictExpiredConnections()
                .build();
    }

    @Bean("catalogLbBuilder")
    @LoadBalanced
    RestClient.Builder catalogLbBuilder(
            @Qualifier("catalogApacheClient")
            CloseableHttpClient apache) {

        return RestClient.builder()
                .requestFactory(
                        new HttpComponentsClientHttpRequestFactory(
                                apache));
    }

    @Bean("catalogRestClient")
    RestClient catalogRestClient(
            @Qualifier("catalogLbBuilder")
            RestClient.Builder builder) {

        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

**Phân biệt rõ:**

- `@LoadBalanced` giúp Spring Cloud chọn một instance cho `catalog-service`.
- `PoolingHttpClientConnectionManager` quản lý connection đã chọn, **không chọn instance**.
- `setMaxConnTotal(12)` và `setMaxConnPerRoute(6)` là **ngưỡng lab cố ý thấp** để dễ quan sát pool pending.
- `connectionRequestTimeout=300ms` giới hạn chờ mượn connection; `responseTimeout=2s` phục vụ giai đoạn chờ response theo Apache HttpClient 5.
- **Connect timeout** và TLS/operation deadline phải được cấu hình riêng nếu cần; không gộp vào một thuộc tính duy nhất.
- Connection manager dùng chung cho những HTTP call đi qua `catalogApacheClient`; nếu vô tình tạo HttpClient/manager mới cho từng request, pooling mất tác dụng.

Trong ứng dụng Spring Boot thực, builder được Boot quản lý có thể kèm observation, message converters, SSL và customizers. Khi thay bằng `RestClient.builder()` thô, cần kiểm tra các customizations quan trọng không bị mất. Ví dụ chỉ trình bày pipeline tối thiểu để phân tích pool.

### Lấy thống kê pool an toàn

~~~java
import org.apache.hc.core5.pool.PoolStats;

void reportPool(
        PoolingHttpClientConnectionManager manager) {
    PoolStats stats = manager.getTotalStats();

    // Nên đưa vào metric/Micrometer, không in mỗi request.
    System.out.printf(
            "leased=%d available=%d pending=%d max=%d%n",
            stats.getLeased(),
            stats.getAvailable(),
            stats.getPending(),
            stats.getMax());
}
~~~

Đoạn này là **hàm minh họa**, không phải metric được Spring Cloud tự tạo. Trong production, thu thập snapshot theo chu kỳ và đưa vào hệ thống telemetry; tránh `println` hoặc log theo từng request gây thêm tải/I/O.

## 7. Khi pool Apache cạn: suy luận theo số liệu

Ví dụ hai tình huống:

| Mốc đo | Tổng leased | Tổng pending | Available | Nhận định |
|---|---:|---:|---:|---|
| Baseline | 3 / 12 | 0 | 4 | Chưa thấy bão hòa tổng |
| Giờ cao điểm | 12 / 12 | 35 | 0 | Bão hòa manager, requests phải xếp hàng |
| Sau traffic giảm | 12 / 12 | 30 | 0 | Nghi response/stream bị giữ hoặc downstream chưa giải phóng |
| Sau khi xử lý xong | 0 / 12 | 0 | 12 | Pool có thể tái sử dụng bình thường |

Đây là **số liệu giả lập**. Hãy lấy số liệu thực qua manager/metrics khi chạy lab, **không kết luận “leak” chỉ từ một snapshot**.

### Đặc biệt kiểm tra route

Nếu tổng `leased=6/12`, nhưng `catalog-a` đang `leased=6/6` và pending riêng của A tăng, pool **theo route A** đã cạn dù **pool tổng còn chỗ**. Tăng `maxConnTotal` một mình không giải quyết được cap `maxConnPerRoute` của A.

Một route bị dồn request có thể do:

- Chỉ còn một instance được discovery/health/zone filter giữ lại.
- Instance khác không phù hợp hint/region, khiến tập ứng viên co lại.
- Sticky session hoặc weighted policy dồn tải có chủ đích.
- Một instance trả chậm, khiến connection giữ lâu.
- Cấu hình retry tiếp tục chọn cùng instance.
- Một proxy tạo bottleneck khác với mô hình “mỗi backend một route”.

**Không tự bỏ strict region/tenant filter** chỉ để dùng các instance ngoài vùng được phép; hãy tăng capacity trong tập hợp hợp lệ hoặc trả lỗi có kiểm soát.

## 8. Reactor Netty: ConnectionProvider không phải pool tổng của service ID

Với `WebClient` thường dùng Reactor Netty, `ConnectionProvider` quản lý connection HTTP theo **remote host** (host + port) và chính sách pool. Các tham số quan trọng:

- `maxConnections`: giới hạn connection **cho từng pool**; với mô hình HTTP/1.1 thông dụng, pool thường theo remote host. Đây **không phải một giới hạn tổng toàn JVM cho mọi service ID**.
- `pendingAcquireMaxCount`: giới hạn số yêu cầu đang chờ acquisition trong queue; nếu quá giới hạn có thể bị từ chối.
- `pendingAcquireTimeout`: thời gian tối đa một yêu cầu được phép chờ acquisition.
- `maxIdleTime`, `maxLifeTime`: giới hạn vòng đời connection để giảm tác động socket stale theo môi trường.
- `metrics`: bật thu thập thống kê provider nếu Micrometer có mặt và được tích hợp.

Trong Spring Cloud LoadBalancer:

~~~text
catalog-service -> catalog-a:8081  -> Reactor Netty pool A
               -> catalog-b:8081  -> Reactor Netty pool B
               -> catalog-c:8081  -> Reactor Netty pool C
~~~

Nếu đặt `maxConnections(16)`, trong môi trường có ba remote hosts, các pool có thể cùng có connection, nên tổng số physical connections **không mặc nhiên giới hạn ở 16**. Cần tính cả số host, số caller replicas, HTTP/2 multiplexing, connection sharing, proxy và giới hạn hệ thống.

### Không hardcode giả định phiên bản

Default pool size, hàng đợi và timeout có thể thay đổi theo phiên bản Reactor Netty, system properties và custom builder. Tài liệu Reactor Netty mô tả pool mặc định theo remote host và các thuộc tính ở trên; **luôn đọc giá trị effective của stack đang chạy**, không kết luận chỉ dựa vào một con số từ blog.

## 9. Cấu hình WebClient có giới hạn pool, queue và timeout rõ ràng

Ví dụ Spring WebFlux/Reactor Netty:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class CatalogWebClientConfiguration {

    @Bean(value = "catalogPool", destroyMethod = "dispose")
    ConnectionProvider catalogPool() {
        return ConnectionProvider.builder("catalog-http")
                .maxConnections(8)
                .pendingAcquireMaxCount(16)
                .pendingAcquireTimeout(
                        Duration.ofMillis(300))
                .maxIdleTime(Duration.ofSeconds(20))
                .metrics(true)
                .build();
    }

    @Bean("catalogLbWebClientBuilder")
    @LoadBalanced
    WebClient.Builder catalogLbWebClientBuilder(
            @Qualifier("catalogPool")
            ConnectionProvider pool) {

        HttpClient client = HttpClient.create(pool)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1500)
                .responseTimeout(Duration.ofSeconds(2));

        return WebClient.builder()
                .clientConnector(
                        new ReactorClientHttpConnector(client));
    }

    @Bean("catalogWebClient")
    WebClient catalogWebClient(
            @Qualifier("catalogLbWebClientBuilder")
            WebClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

Các giá trị `maxConnections=8`, pending=16 và 300ms chỉ để **tái hiện saturation trong lab**. `metrics(true)` yêu cầu Micrometer/metric integration phù hợp; nếu ứng dụng không cấu hình telemetry, có thể bỏ lời gọi này khi thử chức năng.

**Không nhầm lẫn:**

- `@LoadBalanced WebClient.Builder` giải quyết **service ID**.
- `ReactorClientHttpConnector` chỉ định HTTP client/connection provider.
- `pendingAcquireTimeout` giới hạn thời gian đợi **connection**, không phải thời gian server trả body.
- `responseTimeout` không tự giới hạn toàn bộ operation qua nhiều retry.
- `ConnectionProvider` có vòng đời và phải được dispose khi application shutdown; Spring sẽ gọi destroy method cho bean trên.

Nếu application sử dụng global Reactor Netty resources hoặc Spring Boot WebClient auto-configurations khác, cần kiểm tra việc khai báo client riêng có làm mất observation/tracing/SSL configuration vốn có. Không tạo một `ConnectionProvider` mới cho mỗi HTTP call.

## 10. Lỗi pending acquire cần được phân loại riêng với lỗi HTTP status

Khi không lấy được connection, request có thể thất bại **trước khi gửi HTTP tới backend**. Vì vậy:

~~~text
HTTP client:
  -> chưa mượn được connection
  -> pool acquisition timeout / pending queue full
  -> không có downstream HTTP 429/503 thật
~~~

Một số exception thường liên quan pooling, nhưng tên cụ thể thay đổi theo phiên bản/transport:

| Hệ client | Nhóm exception/dấu hiệu | Điều không nên suy ra |
|---|---|---|
| Apache HttpClient 5 | Connection request/pool lease timeout hoặc exception trong cause chain | Không mặc định backend đã trả 503 |
| Reactor Netty | Pending acquire timeout hoặc pool pending limit reached | Không kết luận server quá tải chỉ từ lỗi acquire |
| WebClient | Có thể bọc transport error trong `WebClientRequestException` | Không thể phân loại chỉ theo wrapper |
| OpenFeign + HC5 | Feign/HTTP client exception bọc pool lease error | Không mặc định URL/discovery sai |

Nếu chưa có HTTP response, log/metric phải phân biệt `httpStatus=none` với một status do application tự trả cho người dùng cuối. Backend access log **không có request** có thể là bằng chứng hỗ trợ, nhưng cũng cần đối chiếu proxy/gateway và logging coverage.

### Pending queue lớn không tạo thêm throughput

Một queue dài có thể làm người dùng chờ lâu hơn, tăng memory và tail latency. Nó không thể vượt qua giới hạn throughput của backend hoặc số connection đang thực sự xử lý.

Không dùng `pendingAcquireMaxCount(-1)` hay timeout vô hạn để “sửa” saturation. Queue không giới hạn có thể biến overload ngắn thành tồn đọng kéo dài.

## 11. Event-loop của WebFlux là gì và chặn nó nguy hiểm thế nào?

Trong mô hình HTTP reactive dùng Reactor Netty, một số lượng hữu hạn **event-loop threads** phụ trách xử lý network events và callbacks. Chúng hiệu quả khi tác vụ không blocking và hoàn thành nhanh.

Ví dụ callback sai:

~~~java
import reactor.core.publisher.Mono;

Mono<ProductDto> badPipeline(WebClient client) {
    return client.get()
            .uri("/products/42")
            .retrieve()
            .bodyToMono(ProductDto.class)
            .map(dto -> {
                try {
                    Thread.sleep(400); // CHỈ ĐỂ MINH HỌA LỖI
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }

                return dto;
            });
}
~~~

Khi callback `map` được thực thi trên event-loop thread, `Thread.sleep` giữ thread đó 400ms, làm chậm việc xử lý các sự kiện khác. Nếu xuất hiện ở nhiều request cùng lúc, p95/p99 có thể tăng mạnh ngay cả khi backend nhanh.

Những thao tác rủi ro tương tự:

- `Thread.sleep(...)`, `Future.get()`, `CountDownLatch.await()`.
- JDBC/JPA blocking hoặc HTTP client blocking bên trong reactive callback.
- Đọc file/blocking SDK call trực tiếp từ event-loop.
- Xử lý CPU nặng không được tách khỏi I/O scheduler.
- Khóa đồng bộ tranh chấp kéo dài.
- Gọi `block()` trong luồng `reactor-http-nio-*`; Reactor có thể báo lỗi rằng blocking không được hỗ trợ trên thread đó.

**Không phải mọi chậm trên WebClient đều do event-loop bị block.** Một request async chờ backend chậm vẫn có thể tốn hàng giây mà event-loop rảnh. Cần bằng chứng thread/CPU/metrics.

### Dấu hiệu thường thấy

- Nhiều request độc lập cùng tăng tail latency.
- Thread dump có `reactor-http-nio-*`, `reactor-http-epoll-*` hoặc thread tương tự bị giữ lâu trong mã blocking.
- Event-loop task latency/pending tasks tăng, số event được xử lý giảm.
- Backend đã trả response nhưng caller nhận/đọc response chậm.
- `Pool pending` có thể tăng **thứ cấp** vì connection không được giải phóng đúng lúc.

Tên thread và metric chính xác phụ thuộc Reactor Netty, runtime và event-loop implementation.

## 12. Phát hiện event-loop blocking bằng stack và thí nghiệm

Để phân biệt event-loop blocking với backend chậm:

1. Lấy **hai hoặc nhiều thread dumps** cách nhau một khoảng hợp lý khi lỗi đang xảy ra.
2. Xem thread phụ trách Reactor Netty và vị trí stack đang thực thi.
3. Tìm `Thread.sleep`, JDBC socket blocking, file I/O blocking hoặc lock contention trong luồng đó.
4. Đối chiếu timestamps với tracing: backend đã hoàn tất response chưa?
5. So sánh latency của endpoint reactive chỉ trả một giá trị sẵn có; nếu nó cũng tăng mạnh, nghi caller-side scheduling/event-loop.
6. Dùng kiểm thử với BlockHound khi phù hợp để phát hiện một số blocking APIs trên nonblocking threads.

Ví dụ lệnh lấy thread dump ở môi trường **có JDK tools**:

~~~powershell
jcmd 12345 Thread.print
~~~

Thay `12345` bằng PID JVM cần kiểm tra. Nếu container chỉ có JRE tối giản không có `jcmd`, dùng công cụ quan sát JVM, JFR, diagnostic image hoặc sidecar theo quy trình môi trường. Không giả định có quyền vào mọi container production và không log toàn bộ thread dump ra kênh công khai nếu nó chứa dữ liệu nhạy cảm.

### BlockHound không phải bằng chứng duy nhất

BlockHound có thể báo nhiều loại blocking calls khi được cài đúng trong **test runtime** và tương thích JDK/agent; không phải mọi lệnh chặn hoặc CPU loop đều được phát hiện. Test không báo BlockHound violation **không chứng minh** event-loop luôn an toàn.

## 13. Chuyển blocking work khỏi event-loop đúng cách

Nếu phải gọi một repository/SDK blocking từ reactive pipeline, hãy bọc lời gọi thành publisher trì hoãn thực thi rồi chuyển nó sang scheduler phù hợp:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

class ProductLookup {

    private final BlockingProductRepository repository;

    ProductLookup(BlockingProductRepository repository) {
        this.repository = repository;
    }

    Mono<ProductDto> find(long id) {
        return Mono.fromCallable(
                    () -> repository.findById(id))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

`BlockingProductRepository` là interface minh họa của dependency blocking, không phải class sẵn có trong Spring. `fromCallable` giúp lời gọi chỉ chạy khi subscribe; `subscribeOn(Schedulers.boundedElastic())` đưa việc gọi repository sang scheduler được thiết kế cho công việc blocking có giới hạn.

**Sai cách:**

~~~java
Mono<ProductDto> wrong(long id) {
    ProductDto result = repository.findById(id); // blocking NGAY
    return Mono.just(result)
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Ở đoạn sai, việc gọi repository đã xảy ra **trước khi scheduler được áp dụng**.

### boundedElastic không phải tài nguyên vô hạn

- Scheduler có **giới hạn thread/task queue** theo Reactor version và cấu hình.
- Nếu blocking workload lớn hơn capacity lâu dài, queue của boundedElastic cũng có thể bão hòa.
- Dùng `boundedElastic` không thay thế timeout, bulkhead, backpressure, DB pool sizing hoặc nonblocking driver.
- Với workloads dài/CPU-heavy, nên dùng worker pool chuyên biệt hoặc thiết kế tác vụ bất đồng bộ phù hợp, không đẩy toàn bộ lên event-loop.

Nếu dependency có API reactive/nonblocking thực sự, ưu tiên API đó thay vì bọc vô hạn blocking calls.

### Giới hạn concurrency khi fan-out tới downstream

~~~java
Flux<ProductDto> results =
        Flux.fromIterable(productIds)
                .flatMap(id ->
                        catalogWebClient.get()
                                .uri("/products/{id}", id)
                                .retrieve()
                                .bodyToMono(ProductDto.class),
                        8 // Tối đa 8 inner subscriptions cùng lúc ở đây
                );
~~~

Con số 8 là **giới hạn minh họa**, không phải chính sách chung. Nó giúp tránh một request nghiệp vụ phát sinh hàng trăm HTTP calls đồng thời và dồn queue connection pool. Cần thêm tổng deadline, xử lý error/cancellation và quản lý concurrency trên toàn application nếu nhiều request upstream chạy song song.

## 14. Phân biệt Spring MVC threads với WebFlux event-loop

Không phải ứng dụng dùng `RestClient`/`WebClient` nào cũng xử lý request trên Reactor Netty event-loop.

| Mô hình caller | Mối nguy chính |
|---|---|
| Spring MVC + `RestClient` blocking | Servlet worker threads bị chiếm khi chờ HTTP hoặc pool; thread exhaustion |
| Spring MVC + `WebClient.block()` trên servlet thread | Blocking servlet thread; HTTP network I/O vẫn có thể do Reactor Netty thực hiện |
| Spring WebFlux + `WebClient` reactive đúng | Event-loop hiệu quả nếu không blocking và callback ngắn |
| Spring WebFlux + JDBC blocking trong controller/callback | Blocking event-loop hoặc scheduler nếu không offload |
| OpenFeign blocking trong reactive handler | Có thể block event-loop nếu gọi trực tiếp |

**Không gọi `block()` là “event-loop blocking” nếu nó thực sự chạy trên servlet thread**; khi đó nó vẫn có thể gây thiếu servlet threads, nhưng nguyên nhân/tài nguyên khác.

Với Spring MVC, đo `server.tomcat.threads.busy`/thread pool theo server và version, pending HTTP pool, latency của downstream. Với WebFlux, kiểm tra Netty event-loops, reactive operators và thread dumps.

Không nên chuyển toàn bộ ứng dụng sang WebFlux chỉ để tránh cấu hình connection pool trong RestClient. Reactive không loại bỏ giới hạn tài nguyên hay slow downstream.

## 15. LoadBalancer có thể khiến pool hotspot dù discovery vẫn đúng

LoadBalancer chọn một instance trong danh sách ứng viên. Nếu instance list bị thu hẹp, traffic dồn lên ít physical routes hơn:

~~~text
Trước:
catalog-service -> A, B, C, D  (4 physical hosts)

Sau health/zone/filter:
catalog-service -> A          (1 physical host)
~~~

Nếu throughput không đổi, giới hạn `maxConnPerRoute` của A hoặc `maxConnections` của Reactor Netty pool A có thể trở thành bottleneck.

Nguyên nhân của việc tập ứng viên co lại có thể là:

- Zone preference, hint, subset hoặc custom filter.
- Strict residency/tenant policy.
- Discovery registry chỉ còn một instance.
- Health check loại instance chậm/đã chết (với semantics fallback cụ thể).
- Cache stale hoặc registration chưa cập nhật.
- Sticky session/weight dồn traffic.

### Vấn đề nằm ở selected instance chứ không nhất thiết ở algorithm

Cần đồng thời đo:

1. `serviceId` và **candidate count** sau supplier/filter.
2. `selectedInstance` và số lần chọn mỗi instance.
3. Active connections/pending per physical remote host/route.
4. Backend RPS, latency và error rate cho từng replica.
5. Retry attempts và tỷ lệ chuyển instance.

**Không tự nới strict zone/region filter** để giảm pending nếu nó là ràng buộc an toàn. Hãy scale trong vùng hợp lệ, giảm load có kiểm soát hoặc fail-closed.

## 16. Retry và timeout làm nghẽn pool trầm trọng hơn thế nào?

Giả sử 100 logical operations/giây, mỗi operation có tối đa 2 lần retry sau lần thử đầu. Khi backend lỗi hàng loạt, số HTTP attempts có thể lên tới khoảng **300 attempts/giây** trong điều kiện mọi lần thử đều được thực hiện.

~~~mermaid
flowchart TD
    A["Backend bắt đầu chậm"]
    B["Connection held lâu hơn"]
    C["Pool leased đạt max; pending tăng"]
    D["Acquisition/response timeout"]
    E["Retry tăng số attempts"]
    F["Áp lực lên pool/backend tiếp tục tăng"]
    G["Latency p95/p99 và error rate tăng"]
    A --> B --> C --> D --> E --> F --> C
    C --> G
~~~

Đây là mô hình minh họa; số lần thực tế phụ thuộc tầng nào bật retry, exception nào retry được, deadline, backoff và request body replay.

### Kiểm tra nhiều tầng retry

- Spring Cloud LoadBalancer retry (nếu có dependency/cấu hình tương ứng).
- OpenFeign `Retryer` hoặc thư viện resilience khác.
- `retryWhen` trong Reactor.
- Gateway/mesh/client SDK có retry.
- User-facing caller hoặc job runner gọi lại toàn operation.

Nếu hai tầng retry cùng bật, số lần thử có thể **nhân nhau**, không chỉ cộng. Cần thống nhất một ngân sách attempts và **deadline tổng**.

### Timeout hợp lý không có nghĩa càng ngắn càng tốt

Timeout quá dài làm connection/thread bị giữ, queue phình. Timeout quá ngắn gây false failures, retry storm và dao động. Cấu hình dựa trên SLO, latency distribution thực, backend capacity và tính chất nghiệp vụ; cần phân biệt pool acquire, connect, response, tổng operation.

**Không tự retry pool acquisition timeout** nếu chưa kiểm soát tải và idempotency: request có thể chưa được gửi, nhưng retry thêm ngay vẫn tăng áp lực vào queue.

## 17. Phân loại latency theo giai đoạn thay vì nhìn một p99

Một trace hợp lý cần trả lời:

~~~text
logical operation start
    -> load balancer selection
    -> wait for HTTP pool slot
    -> DNS / connect / TLS
    -> request sent
    -> backend handling
    -> first response byte
    -> body read / decode
    -> business continuation
logical operation end
~~~

| Metric / span | Giúp tìm gì? |
|---|---|
| LB selection duration | Discovery/cache/supplier/choose có chậm không |
| Pool acquire wait | Có chờ connection trước request không |
| Connect/TLS time | Kết nối mới tốn bao lâu |
| HTTP request-to-response | Downstream/server/network có chậm không |
| Decode/body read | Payload lớn, streaming, codec/CPU |
| Event-loop task latency | Có scheduling delay/callback blocking không |
| Total operation duration | Người dùng/caller thực sự chờ bao lâu |
| Retry attempts and backoff | Tổng thời gian bị nhân bởi retry như thế nào |

**Không cộng các percentile riêng lẻ** của từng giai đoạn để suy ra p99 toàn operation: các phân phối và tương quan khác nhau. Cần đo total span thực và dùng stage spans để định vị đóng góp.

### Micrometer/Reactor Netty

Khi tích hợp Micrometer, Reactor Netty có thể công bố những nhóm metric như:

~~~text
reactor.netty.connection.provider.active.connections
reactor.netty.connection.provider.idle.connections
reactor.netty.connection.provider.pending.connections
reactor.netty.connection.provider.pending.connections.time
~~~

Tên chính xác, labels và khả năng tồn tại tùy Reactor Netty/Micrometer version và việc bật metrics. **Không giả định các metric xuất hiện chỉ vì có Spring Cloud LoadBalancer starter.**

Đừng để tag `remote.address`, raw URI, user ID hoặc instance ID có cardinality vô hạn. Dùng whitelist/filters phù hợp cho metrics backend.

## 18. Thực hành A: tái hiện pool cạn với backend cố ý chậm

### 18.1. Backend Spring MVC thử nghiệm

Controller lab:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SlowCatalogController {

    @GetMapping("/lab/slow")
    String slow(@RequestParam(defaultValue = "600") long ms)
            throws InterruptedException {

        long capped = Math.max(0, Math.min(ms, 3000));
        Thread.sleep(capped); // CHỈ TRONG LAB, cố ý làm server chậm
        return "ok";
    }
}
~~~

Dùng hai bản sao backend khác port, ví dụ 8081/8082, hoặc chỉ một bản sao để cô lập giới hạn route. Backend này **cố ý dùng Spring MVC worker blocking** để tạo response delay có kiểm soát; không sao chép `Thread.sleep` vào production.

### 18.2. Caller với pool rất nhỏ

Thay các thông số lab của `CatalogRestClientConfiguration` mục 6:

~~~java
.setMaxConnTotal(4)
.setMaxConnPerRoute(2)
~~~

và dùng:

~~~java
.setConnectionRequestTimeout(
        Timeout.ofMilliseconds(200))
.setResponseTimeout(Timeout.ofSeconds(2))
~~~

Điểm cần dự đoán:

- Nếu một instance nhận 20 request đồng thời, tối đa 2 connections tới route đó theo cấu hình.
- Nhiều request phải chờ slot, một số hết hạn ở acquire stage.
- Backend **không nhất thiết nhận đủ 20 request**.
- `PoolStats.pending` có thể tăng, `leased` của route đạt 2.
- Nếu tăng concurrency trong caller nhưng không tăng capacity, p95/p99 và error rate có thể tệ hơn.

### 18.3. API caller

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class PoolProbeController {

    private final RestClient catalog;

    PoolProbeController(
            @Qualifier("catalogRestClient") RestClient catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/lab/probe")
    String probe() {
        return catalog.get()
                .uri("/lab/slow?ms=600")
                .retrieve()
                .body(String.class);
    }
}
~~~

Mỗi request tới `/lab/probe` là một logical operation gọi downstream qua LoadBalancer. Với danh sách một/two instances, hãy kiểm tra **selected route** và pool limits tương ứng.

### 18.4. Tải bằng k6

Ví dụ script tập trung tạo nhiều request tới **caller**, không gọi thẳng backend:

~~~javascript
import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    saturation: {
      executor: "constant-arrival-rate",
      rate: 25,
      timeUnit: "1s",
      duration: "60s",
      preAllocatedVUs: 30,
      maxVUs: 80
    }
  },
  thresholds: {
    dropped_iterations: ["count==0"]
  }
};

export default function () {
  const response = http.get(
    "http://127.0.0.1:8080/lab/probe"
  );

  check(response, {
    "HTTP 200": (r) => r.status === 200
  });
}
~~~

Đây là workload **minh họa, không phải số đo đã chạy**. Nếu generator có `dropped_iterations`, chưa thể tin rằng nó đã cấp đủ RPS mong muốn. Nếu application map lỗi downstream thành HTTP 500, `http_req_failed` cũng sẽ tăng; ghi rõ error categories phía caller và số request backend thực nhận.

**Kịch bản đối chiếu:** giữ nguyên tải nhưng tăng số instance hợp lệ, thay độ chậm server hoặc giới hạn pool. Quan sát leased/pending/acquire duration và độ trễ. Không tự bật retry trong lúc đang tìm nguyên nhân gốc.

## 19. Thực hành B: chứng minh event-loop bị chặn

Đối chiếu hai pipeline `WebClient`:

### Pipeline xấu (chỉ trong lab)

~~~java
@GetMapping("/lab/reactive-bad")
Mono<String> bad() {
    return Mono.just("ok")
            .map(value -> {
                try {
                    Thread.sleep(300); // CHẶN callback thread
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }
                return value;
            });
}
~~~

Nếu được thực thi trong Spring WebFlux/Reactor Netty trên event-loop, callback sẽ giữ event-loop thread. Dưới tải, thử gọi **đồng thời** một endpoint reactive nhanh khác để xem tail latency có tăng dù không gọi backend chậm.

### Pipeline đúng nếu phải chạy tác vụ blocking

~~~java
@GetMapping("/lab/reactive-offloaded")
Mono<String> offloaded() {
    return Mono.fromCallable(() -> {
                Thread.sleep(300); // CHỈ TRONG LAB
                return "ok";
            })
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Đoạn thứ hai vẫn tạo tác vụ blocking nhưng **không giữ event-loop trong thời gian sleep**; việc chờ chuyển sang boundedElastic. Khi lượng tác vụ quá lớn, boundedElastic vẫn có thể bị saturate, nên phải quan sát queue và giới hạn concurrency.

### Ma trận kỳ vọng

| Thí nghiệm | Pool pending | Event-loop | Dấu hiệu |
|---|---|---|---|
| Backend chậm, HTTP pool rất nhỏ | Thường tăng | Có thể bình thường | Requests chờ acquire |
| Callback sleep trên event-loop | Có thể tăng thứ cấp | Thread bị block | Nhiều endpoints reactive cùng chậm |
| Blocking được offload, chưa quá capacity | Có thể ổn | Giảm blocking event-loop | Event-loop phục vụ các callback khác |
| Backend xử lý chậm, pool rộng | Có thể thấp | Có thể bình thường | HTTP span/backend latency cao |
| Retry storm vào backend chậm | Tăng nhanh | Tùy implementation | Attempts/RPS backend tăng |

**Không kết luận từ bảng dự đoán thay cho thực đo.** Dùng cùng workload, thu thập thread dump/metric, ghi timing thật và cách cấu hình test.

## 20. Runbook 10 bước khi p95/p99 tăng đột ngột

1. **Xác định phạm vi:** mọi service hay chỉ `catalog-service`? Một instance hay mọi instance? Bắt đầu từ thời điểm deploy, scale, traffic spike nào?

2. **Kiểm tra có chọn instance không:** nếu `NO_INSTANCE`, xử lý discovery/filter trước. Nếu đã chọn, ghi loại endpoint vật lý theo telemetry được phép.

3. **Xem pool tổng và theo route/host:** Apache leased/available/pending/max; Reactor active/idle/pending/acquire time. Không nhìn một con số global rồi bỏ qua route đang hot.

4. **Kiểm tra error cause:** lỗi chờ pool, connect timeout, TLS, response timeout, HTTP 503, decode error là các nhánh khác nhau.

5. **So sánh với backend:** request đã đến backend chưa? Backend latency, DB pool, CPU/GC, queue depth thế nào?

6. **Kiểm tra event-loop và thread pool:** lấy thread dumps/JFR ở thời điểm lỗi; tìm `block()`, `Thread.sleep`, JDBC/file I/O trên event-loop, hoặc servlet worker saturation.

7. **Đếm logical requests và HTTP attempts:** retry có nhân tải và queue không? Có nhiều tầng retry cùng bật không?

8. **Kiểm tra thay đổi membership:** LoadBalancer chỉ còn một instance do health/zone/strict filter hay discovery stale? Có proxy/gateway nào gom nhiều đích vào cùng bottleneck?

9. **Áp dụng mitigations có kiểm soát:** giảm burst/concurrency/retry, phục hồi backend, rollback thay đổi blocking, giới hạn queue/deadline; chỉ tăng pool sau khi xác minh backend có capacity.

10. **Kiểm thử và giám sát sau sửa:** chạy cùng workload, so sánh p95/p99, pending, active, backend saturation, errors và retry amplification; giữ rollback plan.

### Sơ đồ định vị nhanh

~~~mermaid
flowchart TD
    A["p95/p99 tăng hoặc timeout"]
    B{"Có ServiceInstance?"}
    C["Discovery / filter / cache"]
    D{"Pool pending tăng<br/>và active chạm cap?"}
    E["Pool acquisition / per-route bottleneck"]
    F{"Event-loop thread<br/>bị block?"}
    G["Offload/loại blocking,<br/>giới hạn concurrency"]
    H{"Backend latency /<br/>resource tăng?"}
    I["Khắc phục backend / DB / mạng"]
    J["Xem DNS/TCP/TLS, retry,<br/>decode, lock, GC và tracing"]
    A --> B
    B -->|"Không"| C
    B -->|"Có"| D
    D -->|"Có"| E
    D -->|"Không / chưa đủ"| F
    F -->|"Có"| G
    F -->|"Không"| H
    H -->|"Có"| I
    H -->|"Không"| J
~~~

Đây là **trình tự ưu tiên**, không có nghĩa chỉ một nhánh đúng. Backend chậm có thể là nguyên nhân gốc khiến pool pending tăng, và event-loop bị block có thể tiếp tục trì hoãn việc trả connection.

## 21. Những cách sửa sai phổ biến

### 21.1. “Tăng maxConnections lên thật lớn”

Giới hạn connection lớn có thể làm quá tải backend, tăng file descriptors/sockets, handshake và GC. Nếu backend đang chậm do DB pool nhỏ, nhiều connection từ caller có thể chỉ đưa hàng đợi từ client sang server. **Phải xác định khả năng phục vụ toàn tuyến trước khi tăng**.

### 21.2. “Cho pending queue vô hạn”

Queue vô hạn có thể làm response tới người dùng quá hạn và gây memory pressure. Dùng **bounded queue + timeout + backpressure/bulkhead** theo SLO.

### 21.3. “Bật retry mọi exception”

Retry khi pool đã cạn hoặc backend đang quá tải có thể tạo vòng khuếch đại. Không retry lỗi contract, không replay giao dịch có tác dụng phụ nếu thiếu idempotency, và luôn có ngân sách attempts/deadline.

### 21.4. “Tăng responseTimeout để sửa lỗi chờ pool”

Nếu lỗi nằm ở **connection acquisition**, tăng `responseTimeout` không thay giới hạn hàng đợi/chờ acquire. Phải xem request đã mượn được connection và gửi HTTP hay chưa.

### 21.5. “Dùng WebFlux là không có blocking nữa”

Một JDBC/JPA hoặc SDK blocking đặt trực tiếp vào reactive callback vẫn chặn thread. Ngay cả `boundedElastic` cũng có cap và queue.

### 21.6. “RestClient và WebClient dùng chung pool”

Không tự giả định: Apache HttpClient manager và Reactor Netty ConnectionProvider là hai hạ tầng khác nhau; OpenFeign có thể dùng delegate riêng. Cần xác định **HTTP client thực tế** và số manager/provider trong process.

### 21.7. “Không còn 503 là đã hết nghẽn”

Nếu application tự map pool timeout thành HTTP 200 với fallback rỗng, metric HTTP error có thể giảm nhưng tail latency, data completeness hoặc SLO nghiệp vụ vẫn sai. Theo dõi cả logical outcome và error category.

### 21.8. “Đổ lỗi cho LoadBalancer khi request đã đến server”

LoadBalancer có thể góp phần tạo hotspot do filter/weight/sticky, nhưng server/DB chậm, connection leak và event-loop blocking thuộc các tầng khác. Không thay thuật toán round-robin nếu chưa có bằng chứng về phân phối sai.

### 21.9. “Bật wiretap/FULL logs để tìm lỗi”

Feign `FULL`, Reactor Netty wiretap và HTTP transport debug có thể ghi token, cookie, URL có signed query và response body. Trong production, dùng metric/tracing allowlist và thread dumps qua kênh được bảo vệ.

## 22. Cách chọn giải pháp theo nguyên nhân đã xác nhận

| Nguyên nhân đã có bằng chứng | Biện pháp ưu tiên | Cần xác minh sau thay đổi |
|---|---|---|
| Apache `maxConnPerRoute` quá thấp, backend còn capacity | Điều chỉnh per-route và total hợp lý, reuse pool | Pending giảm, backend không bão hòa |
| Reactor Netty pending acquire quá hạn | Giới hạn fan-out, xử lý slow backend, cân nhắc điều chỉnh pool/queue | p95, pending, max connections per host |
| Backend/DB chậm | Tối ưu DB/lock/cache, scale hoặc bảo vệ capacity | Server latency và caller pool đồng thời cải thiện |
| Event-loop blocked | Loại blocking hoặc offload bounded; tối ưu CPU | Thread dumps không còn event-loop blocking |
| Servlet workers bị chiếm bởi blocking HTTP | Timeout hợp lý, bulkhead, concurrency limits, capacity | Busy threads, request backlog, p95 |
| Retry amplification | Giảm attempts, backoff/jitter, deadline và idempotency | Attempts / operations về mức kiểm soát |
| Response body chưa đóng | Sửa response lifecycle, try-with-resources khi cần | Leased trở lại baseline sau tải |
| Một instance hot do filter/sticky | Kiểm tra chính sách và số replica hợp lệ | Per-instance traffic, pool stats |
| Cache stale chọn instance đã chết | Điều chỉnh discovery/health/cache và graceful shutdown | Invalid selections giảm sau refresh |
| Tăng tải đột ngột vượt SLO | Admission control, backpressure, circuit breaker/bulkhead, scale đúng tầng | Error hữu hạn, hệ thống phục hồi |

**Quy tắc an toàn:** đừng “mở rộng tập instance” trái chính sách vùng dữ liệu/tenant, và đừng tăng pool vượt số connection mà downstream có thể phục vụ. Các thay đổi cần rollout có kiểm soát, so sánh trước/sau và kế hoạch rollback.

## 23. Checklist nghiệm thu bài chẩn đoán

- Đã tách rõ **LB selection**, **pool acquisition**, **TCP/TLS/HTTP**, **body decode** và **event-loop/threads**?
- Có biết client thực tế đang dùng Apache HttpClient 5, Reactor Netty, OpenFeign HTTP delegate hay request factory khác không?
- Có metric **leased/pending/available/max** theo tổng và **per route** cho HC5?
- Có metric **active/idle/pending/acquire time** theo remote host với Reactor Netty?
- Có phân biệt `connectionRequestTimeout`/`pendingAcquireTimeout` với connect và response timeout?
- Có xác nhận request đã thực sự tới backend trước khi kết luận “server trả chậm”?
- Với WebFlux, đã tìm blocking operation trong callback và thread dump event-loop?
- Với Spring MVC, đã kiểm tra servlet thread exhaustion chứ không gộp thành event-loop?
- Có phân biệt backend chậm gây pool saturation với pool quá nhỏ là nguyên nhân đầu tiên?
- Có thống kê retry attempts/operation, deadline tổng và nguy cơ retry storm?
- Có xem LoadBalancer filter/health/zone có khiến số physical routes hợp lệ giảm không?
- Có kiểm tra response/stream lifecycle nếu `leased` không trở lại baseline?
- Có cân nhắc HTTP/2 multiplexing, proxy và pool per host trước khi chuyển số request thành số connection?
- Có load test gửi request **qua caller** và ghi rõ các số liệu chỉ là kết quả thực đo?
- Có áp dụng giới hạn concurrent requests/backpressure/bulkhead đúng vị trí?
- Có tránh log token, cookie, raw URL và body khi bật observability?
- Sau sửa, p95/p99, error rate, pool pending, thread/CPU/GC và backend saturation đều được đo lại?
- Có regression test và rollback plan cho thay đổi cấu hình HTTP client/LoadBalancer?

**Kết luận:** Khi gọi service ID qua Spring Cloud LoadBalancer bị chậm, đừng mặc định lỗi ở thuật toán chọn `ServiceInstance`. Hãy đo đúng **giai đoạn request bị giữ lại**: hàng đợi connection pool, DNS/TCP/TLS, backend, response decode hay event-loop/servlet threads. `RestClient`/Apache HC5 có giới hạn **tổng và theo route**; `WebClient`/Reactor Netty quản lý các pool thường **theo remote host**; code blocking trên event-loop làm tăng độ trễ ở nơi hoàn toàn khác. Tối ưu đúng nguyên nhân, giới hạn queue/retry và xác minh bằng metrics cùng test tải là cách phục hồi giao tiếp giữa dịch vụ ổn định.

**Tài liệu tham khảo chính thức:**

- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Framework – REST Clients và HttpComponents request factory](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Reactor Netty – HTTP Client, Connection Pool và Metrics](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Project Reactor – Schedulers và blocking calls](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Spring Framework – WebFlux, Reactive Core và concurrency model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Apache HttpClient 5 – Connection Management](https://hc.apache.org/httpcomponents-client-5.4.x/current/httpclient5/apidocs/)

