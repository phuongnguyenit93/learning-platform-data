# Connect timeout, response timeout và thời gian chờ lấy kết nối

Khi gọi HTTP bằng **Spring WebClient** trên Reactor Netty, một request có thể phải chờ ở nhiều giai đoạn: chờ một connection rảnh trong pool, thiết lập TCP connection mới, hoàn tất TLS handshake, gửi request, chờ server phản hồi và đọc response body. Mỗi giai đoạn có nguyên nhân chậm và cách cấu hình timeout khác nhau.

Ba timeout thường bị nhầm lẫn là:

- **Connection timeout**: giới hạn thời gian thiết lập kết nối tới remote peer khi cần tạo connection mới.
- **Pending acquire timeout**: giới hạn thời gian chờ lấy một connection từ connection pool khi pool đã bận.
- **Response timeout**: trong Reactor Netty, giới hạn khoảng thời gian tối đa giữa các lần đọc dữ liệu ở tầng mạng khi đang nhận một response.

Ngoài ba timeout này, Reactor cung cấp **timeout theo publisher** để đặt deadline cho một thao tác reactive. Với §Mono.timeout(Duration)§, deadline áp dụng cho toàn bộ Mono từ lúc subscribe đến khi có terminal signal. Với Flux, §timeout(Duration)§ thường giới hạn khoảng im lặng giữa các signal, không tự động giới hạn tổng thời gian của cả stream.

Muốn thiết kế timeout đúng, trước hết phải xác định request đang chậm ở đâu. Tăng connection timeout không giải quyết được pool bị đầy; tăng response timeout không làm queue acquire ngắn lại; còn deadline tổng thể không thay thế các timeout chuyên biệt để chẩn đoán từng giai đoạn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt connect timeout, pending acquire timeout, response timeout và end-to-end timeout.
2. Mô tả vòng đời một request WebClient qua DNS, connection pool, TCP, TLS, request write và response read.
3. Cấu hình §ConnectionProvider§ với giới hạn connection và pending queue.
4. Cấu hình §HttpClient§ với §CONNECT_TIMEOUT_MILLIS§ và §responseTimeout§.
5. Kết nối HttpClient với WebClient bằng §ReactorClientHttpConnector§.
6. Hiểu các timeout TLS, proxy và DNS là các giai đoạn riêng.
7. Đặt deadline tổng thể bằng Reactor timeout operator và xây dựng timeout budget.
8. Phân biệt lỗi pool saturation với lỗi mạng hoặc server phản hồi chậm.
9. Thiết kế retry có giới hạn, có backoff và không nhân đôi thao tác không idempotent.
10. Theo dõi connection pool, latency và timeout bằng metrics.
11. Viết và kiểm thử WebClient trên Java 17 với MockWebServer.

## 2. Vòng đời một request WebClient

Một request đi qua các giai đoạn khái quát sau:

~~~text
WebClient request
      |
      v
DNS hostname resolution
      |
      v
Acquire connection from pool
      |
      +---- pool có connection rảnh --> reuse connection
      |
      +---- pool hết connection ------> pending acquire queue
      |                                  |
      |                                  +--> acquire timeout
      v
Create TCP connection (nếu cần)
      |
      +--> connect timeout
      v
TLS handshake (nếu HTTPS)
      |
      +--> TLS handshake timeout
      v
Write HTTP request
      |
      +--> write/network failure
      v
Wait for and read response
      |
      +--> response/read timeout
      v
Decode response body
      |
      v
Publisher complete
~~~

Không phải request nào cũng chạy qua toàn bộ các bước. Nếu pool đã có connection idle phù hợp, request có thể bỏ qua TCP connect và TLS handshake mới. Nếu DNS đã được cache, hostname resolution có thể nhanh hơn. Nếu request không dùng HTTPS, không có TLS handshake.

Timeout ở từng bước chỉ áp dụng cho giai đoạn mà nó quản lý. Một request có thể không vi phạm bất kỳ timeout riêng lẻ nào nhưng vẫn mất quá lâu tổng cộng; khi đó cần deadline tổng thể ở tầng publisher hoặc service.

## 3. Connection timeout

### 3.1. Connection timeout kiểm soát điều gì?

Connection timeout giới hạn thời gian thiết lập kết nối TCP tới remote peer. Với Reactor Netty, cấu hình phổ biến là Netty channel option:

~~~java
.option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
~~~

Giá trị được tính bằng milliseconds. Nếu quá thời gian mà TCP connection chưa được thiết lập, thao tác connect thất bại.

Connection timeout chỉ có ý nghĩa khi client phải tạo connection mới. Nếu request lấy được một connection đang idle trong pool, không có TCP connect mới để timeout này áp dụng.

Reactor Netty hiện ghi nhận default connect timeout là 30 giây. Tuy nhiên, Spring Boot quản lý phiên bản Reactor Netty thông qua dependency management; hãy kiểm tra tài liệu của phiên bản thực tế và cấu hình rõ timeout theo SLA của ứng dụng thay vì phụ thuộc ngầm vào default.

### 3.2. Cấu hình với WebClient

Spring WebClient không tự định nghĩa một connect timeout độc lập. Khi dùng Reactor Netty, cấu hình HttpClient rồi đưa nó vào connector:

~~~java
HttpClient httpClient = HttpClient.create()
    .option(
        ChannelOption.CONNECT_TIMEOUT_MILLIS,
        2_000
    );

WebClient client = WebClient.builder()
    .clientConnector(
        new ReactorClientHttpConnector(httpClient)
    )
    .build();
~~~

§CONNECT_TIMEOUT_MILLIS§ không phải timeout cho toàn bộ request. Nó không giới hạn thời gian chờ connection pool, thời gian server xử lý hoặc thời gian đọc response body sau khi kết nối đã được thiết lập.

### 3.3. DNS và TLS không phải connect timeout

Hostname resolution có thể xảy ra trước TCP connect. Nếu DNS chậm, request có thể mất thời gian trước khi bước connect bắt đầu. Reactor Netty dùng resolver riêng và có các cấu hình timeout/cache cho DNS; không nên chẩn đoán mọi request chậm trước khi connect là lỗi connect timeout.

Với HTTPS, TLS handshake diễn ra sau khi TCP connection được tạo. Reactor Netty có §handshakeTimeout§ riêng; tài liệu hiện hành ghi default TLS handshake timeout là 10 giây. Một connect timeout ngắn không tự đặt giới hạn TLS handshake tương ứng.

### 3.4. Khi nào cần điều chỉnh?

Cân nhắc điều chỉnh connect timeout khi:

- Remote host nằm ở mạng có latency cao nhưng đã biết và có SLA rõ.
- Một số kết nối mới bị treo lâu do network path hoặc firewall.
- Muốn fail nhanh để service phía trên xử lý fallback.
- Có retry policy phù hợp cho lỗi kết nối tạm thời.

Không tăng connect timeout chỉ vì pool bị đầy hoặc server xử lý chậm. Trước khi đổi, hãy xem DNS latency, connect latency, pool pending và TLS handshake metrics.

## 4. Pending acquire timeout của connection pool

### 4.1. Vì sao phải chờ lấy connection?

Reactor Netty HttpClient thường dùng connection pool. Pool giữ các connection đã tạo để tái sử dụng. Khi request mới đến:

1. Nếu có connection idle phù hợp, pool cấp connection đó.
2. Nếu chưa đạt giới hạn connection, pool có thể tạo connection mới.
3. Nếu đã đạt §maxConnections§, request có thể phải chờ trong pending queue.
4. Nếu chờ quá lâu, §pendingAcquireTimeout§ phát lỗi.
5. Nếu pending queue đã đầy, request mới có thể bị từ chối ngay.

§pendingAcquireTimeout§ không phải thời gian mở TCP connection. Nó là thời gian chờ một connection được trả lại hoặc có thể được cấp từ pool. Khi hết thời gian chờ, Reactor Netty thường phát §PoolAcquireTimeoutException§; exception có thể được wrap bởi lớp connector hoặc error handler của ứng dụng.

### 4.2. Cấu hình ConnectionProvider

Ví dụ giới hạn pool theo remote host:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("catalog-pool")
        .maxConnections(50)
        .pendingAcquireMaxCount(100)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .maxIdleTime(Duration.ofSeconds(20))
        .maxLifeTime(Duration.ofMinutes(5))
        .evictInBackground(Duration.ofSeconds(30))
        .build();
~~~

Ý nghĩa:

| Cấu hình | Vai trò |
| --- | --- |
| §maxConnections§ | Số connection tối đa trong mỗi pool/remote host. |
| §pendingAcquireMaxCount§ | Số request tối đa được giữ trong queue chờ connection. |
| §pendingAcquireTimeout§ | Thời gian tối đa một request được chờ trong pending queue. |
| §maxIdleTime§ | Tuổi idle tối đa trước khi connection đủ điều kiện bị loại bỏ. |
| §maxLifeTime§ | Tuổi tối đa của một connection, kể cả khi được tái sử dụng. |
| §evictInBackground§ | Chu kỳ kiểm tra và loại connection hết hạn ở nền. |

Reactor Netty hiện ghi default pending acquire timeout là 45 giây. Số connection mặc định có thể phụ thuộc cách tạo HttpClient/ConnectionProvider và phiên bản; hãy cấu hình maxConnections, pendingAcquireMaxCount và pendingAcquireTimeout rõ ràng cho workload của mình.

### 4.3. Pool saturation không phải connect timeout

Giả sử pool cho một host chỉ cho phép 20 connection và cả 20 đang bận:

- Request thứ 21 có thể vào pending queue.
- Nếu một connection được trả lại trong 2 giây, request có thể tiếp tục.
- Nếu hết 2 giây mà chưa có connection, request nhận pool acquire timeout.
- Request chưa bắt đầu TCP connect mới, vì thế tăng connect timeout không giúp request này.

Một queue quá dài chỉ làm latency tăng và giữ thêm request trong hệ thống. Pending queue nên hữu hạn; queue không giới hạn có thể biến quá tải tức thời thành độ trễ kéo dài và tiêu thụ memory.

### 4.4. Chọn maxConnections và queue size

Không đặt maxConnections thật lớn chỉ để loại bỏ acquire timeout. Quá nhiều connection đồng thời có thể gây áp lực lên:

- Remote service và database phía sau nó.
- File descriptor và socket.
- Event loop, TLS state và direct memory.
- NAT gateway, firewall và load balancer.
- Thread/queue ở các tầng downstream.

Chọn giới hạn theo năng lực remote service, số request đồng thời thực tế và thời gian một request giữ connection. Đặt pending queue đủ nhỏ để hấp thụ burst ngắn, nhưng không che giấu overload kéo dài.

### 4.5. maxIdleTime và connection stale

Nếu server hoặc load balancer đóng connection idle sau 30 giây, client nên cân nhắc đặt §maxIdleTime§ nhỏ hơn hoặc bằng khoảng idle timeout đó. Điều này giảm khả năng lấy lại một connection mà remote peer đã đóng trong lúc idle.

§maxLifeTime§ giới hạn tuổi tổng thể của connection. Nó không phải request timeout. §evictInBackground§ giúp kiểm tra pool định kỳ thay vì chỉ kiểm tra khi acquire/release.

## 5. Response timeout của Reactor Netty

### 5.1. Response timeout là khoảng cách giữa các lần đọc

Reactor Netty §HttpClient.responseTimeout(Duration)§ xác định khoảng thời gian tối đa được phép giữa các lần đọc ở tầng mạng khi đang nhận response.

~~~java
HttpClient httpClient = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(3));
~~~

Đây là **maximum read-operation interval**, không phải giới hạn tổng thời gian từ lúc gửi request đến lúc body hoàn tất.

Ví dụ:

- Server gửi response headers rồi im lặng 5 giây trước chunk đầu tiên.
- Client đặt responseTimeout 2 giây.
- Client có thể timeout vì khoảng chờ giữa các lần đọc vượt 2 giây.

Với response streaming, nếu server đều đặn gửi chunk mỗi giây, stream có thể chạy lâu hơn 2 giây tổng cộng mà không vi phạm responseTimeout 2 giây. Ngược lại, một stream bị ngừng phát dữ liệu giữa chừng có thể timeout khi khoảng im lặng vượt ngưỡng.

### 5.2. Cấu hình responseTimeout

~~~java
HttpClient httpClient = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
    .clientConnector(
        new ReactorClientHttpConnector(httpClient)
    )
    .build();
~~~

Reactor Netty hiện không đặt responseTimeout mặc định. Tài liệu khuyến nghị nên cấu hình response timeout phù hợp thay vì để một response có thể chờ im lặng vô hạn.

### 5.3. responseTimeout khác ReadTimeoutHandler

Có thể cấu hình Netty §ReadTimeoutHandler§ bằng §doOnConnected§:

~~~java
HttpClient httpClient = HttpClient.create()
    .doOnConnected(connection ->
        connection.addHandlerLast(
            new ReadTimeoutHandler(5)
        )
    );
~~~

Đây là timeout đọc ở cấp channel. Với HTTP client, §responseTimeout§ của Reactor Netty thể hiện rõ hơn mục tiêu giới hạn khoảng cách giữa các lần đọc response và được quản lý theo vòng đời request/response.

Không thêm nhiều read timeout handler chồng lên nhau nếu chưa hiểu thứ tự và lifecycle của chúng. Chọn cơ chế phù hợp, kiểm thử trên loại response thực tế và ghi rõ timeout nào đang phát lỗi.

### 5.4. Response timeout và download/stream dài

Không đặt responseTimeout quá ngắn cho endpoint có thể gửi chunk cách nhau lâu, như export lớn hoặc server-sent events. Với stream, chọn timeout dựa trên khoảng im lặng tối đa hợp lệ, không phải tổng thời gian tải.

Nếu cần giới hạn tổng thời gian stream, thêm deadline riêng ở tầng publisher hoặc service. Cũng cần tính đến tốc độ mạng và client có thể đọc chậm; response timeout là khoảng chờ đọc từ peer, không phải một giới hạn dung lượng body.

## 6. Timeout tổng thể bằng Reactor

### 6.1. Mono.timeout(Duration)

Reactor cung cấp operator:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(Product.class)
    .timeout(Duration.ofSeconds(8));
~~~

Với Mono, timeout giới hạn thời gian từ lúc subscribe đến khi publisher phát giá trị hoặc terminal signal. Nó bao gồm thời gian chờ acquire, DNS/connect, TLS, request, server response và decode body trong cùng publisher chain.

Nếu quá deadline, Reactor phát §java.util.concurrent.TimeoutException§ và hủy upstream subscription. Cancellation được truyền xuống WebClient/transport để dừng công việc nếu có thể.

### 6.2. Flux.timeout(Duration) không phải deadline tổng thể

Với Flux, §timeout(Duration)§ thường giới hạn thời gian chờ signal kế tiếp. Nếu stream tiếp tục phát item trong khoảng thời gian nhỏ hơn timeout, stream có thể chạy rất lâu.

Ví dụ:

~~~java
Flux<Event> events = webClient.get()
    .uri("/events")
    .retrieve()
    .bodyToFlux(Event.class)
    .timeout(Duration.ofSeconds(10));
~~~

Đoạn này phát lỗi khi có khoảng im lặng 10 giây giữa các signal; nó không có nghĩa toàn bộ event stream phải kết thúc trong 10 giây.

Nếu nghiệp vụ cần một deadline wall-clock cho stream, thiết kế deadline/cancellation riêng ở tầng gọi. Không dùng §timeout(Duration)§ trên Flux với giả định nó là giới hạn tổng thời gian.

### 6.3. Timeout chuyên biệt và timeout tổng thể bổ sung cho nhau

Timeout chuyên biệt giúp xác định giai đoạn:

- Pending acquire timeout: pool không cấp connection kịp.
- Connect timeout: không thiết lập được TCP connection kịp.
- Response timeout: response không có dữ liệu đọc tiếp trong khoảng cho phép.
- TLS handshake timeout: bắt tay TLS không hoàn tất kịp.

Timeout tổng thể bảo vệ SLA của thao tác end-to-end. Ví dụ, service đặt deadline 8 giây trong khi acquire tối đa 1 giây, connect tối đa 2 giây và response read gap tối đa 3 giây. Các timeout con cần được thiết kế sao cho không mâu thuẫn với deadline tổng thể.

Nếu deadline tổng thể ngắn hơn một timeout con, timeout tổng thể có thể xảy ra trước. Đây là điều có chủ đích nếu service không thể chờ lâu hơn SLA của nó.

## 7. DNS, TLS và proxy timeout

Không phải mọi giai đoạn đều dùng cùng một cài đặt:

| Giai đoạn | Cơ chế | Ghi chú |
| --- | --- | --- |
| DNS lookup | Resolver timeout/cache | Xảy ra trước TCP connect; phụ thuộc resolver. |
| Chờ connection pool | pendingAcquireTimeout | Chỉ khi pool phải chờ connection. |
| TCP connect | CONNECT_TIMEOUT_MILLIS | Chỉ khi tạo connection mới. |
| TLS handshake | handshakeTimeout | Áp dụng khi kết nối HTTPS/TLS. |
| Proxy connect | ProxyProvider connect timeout | Có cấu hình riêng khi đi qua proxy. |
| Response read | responseTimeout | Giới hạn khoảng cách giữa network read. |
| Publisher deadline | Mono/Flux timeout | Do ứng dụng đặt trên reactive chain. |

TLS handshake timeout hiện có default 10 giây trong Reactor Netty; proxy connect timeout cũng có default riêng. Giá trị mặc định thay đổi theo phiên bản và cấu hình transport. Nếu request dùng proxy hoặc HTTPS, hãy tính các bước đó vào timeout budget.

TCP keepalive là một cơ chế khác: nó gửi probe cho connection idle để phát hiện peer hoặc network path đã mất. Keepalive không thay thế connect timeout, response timeout hay application deadline.

## 8. Cấu hình WebClient hoàn chỉnh với ConnectionProvider

Ví dụ dưới đây dùng Java 17, Spring Boot 3.3.5 và Reactor Netty. Các con số chỉ là baseline minh họa cho một client gọi catalog; hãy thay theo SLA và capacity của remote service.

### 8.1. Cấu hình ConnectionProvider và HttpClient

~~~java
package demo;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.resources.ConnectionProvider;
import reactor.netty.http.client.HttpClient;

@Configuration
class CatalogWebClientConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogConnectionProvider() {
        return ConnectionProvider.builder("catalog-pool")
            .maxConnections(50)
            .pendingAcquireMaxCount(100)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(20))
            .maxLifeTime(Duration.ofMinutes(5))
            .evictInBackground(Duration.ofSeconds(30))
            .build();
    }

    @Bean
    WebClient catalogWebClient(
            ConnectionProvider catalogConnectionProvider) {

        HttpClient httpClient = HttpClient
            .create(catalogConnectionProvider)
            .option(
                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                2_000
            )
            .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
            .baseUrl("https://catalog.example.test")
            .clientConnector(
                new ReactorClientHttpConnector(httpClient)
            )
            .build();
    }
}
~~~

ConnectionProvider là resource có lifecycle. Khi tạo provider riêng, đăng ký thành Spring bean để dispose khi ApplicationContext đóng. Nếu dùng global Reactor Netty resources mặc định, chúng được chia sẻ và thường sống theo vòng đời process; không tạo và dispose một pool mới cho mỗi request.

### 8.2. Service đặt deadline tổng thể

~~~java
package demo;

import java.time.Duration;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

record Product(String id, String name) {}

@Service
class CatalogService {

    private final WebClient client;

    CatalogService(WebClient catalogWebClient) {
        this.client = catalogWebClient;
    }

    Mono<Product> findProduct(String id) {
        return client.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class)
            .timeout(Duration.ofSeconds(8));
    }
}
~~~

HttpClient quản lý connect/response timeout; ConnectionProvider quản lý pool acquire; service quản lý deadline tổng thể. Khi timeout xảy ra, nên ghi nhận giai đoạn/lỗi cụ thể để vận hành có thể phân biệt pool saturation, connect failure, response stall và SLA deadline.

### 8.3. Cấu hình nhiều workload khác nhau

Không nhất thiết dùng một timeout cho mọi endpoint. Ví dụ:

- Catalog lookup: response nhỏ, deadline ngắn.
- Report export: response stream dài, deadline lớn hơn và response read gap phù hợp.
- Upload: request body lớn, write timeout và overall deadline cần được thiết kế theo throughput.
- Long polling/SSE: response có thể kéo dài; response timeout phải lớn hơn khoảng heartbeat tối đa hoặc được thiết kế theo protocol.

Có thể tạo nhiều WebClient/HttpClient cấu hình riêng cho từng remote service hoặc workload. Tránh tạo client/pool cho từng lần gọi vì làm mất lợi ích reuse và tạo quá nhiều connection pool.

## 9. Timeout budget và cách chọn giá trị

### 9.1. Bắt đầu từ SLA end-to-end

Giả sử service cần hoàn thành một request catalog trong tối đa 8 giây. Một budget minh họa có thể là:

| Giai đoạn | Budget minh họa |
| --- | ---: |
| Chờ pool acquire | 1 giây |
| DNS và TCP connect | 2 giây |
| TLS handshake | 1 giây |
| Chờ/đọc response | khoảng im lặng tối đa 3 giây |
| Deadline toàn bộ Mono | 8 giây |

Đây không phải công thức cộng đơn giản để bảo đảm mọi trường hợp; một số giai đoạn chỉ xảy ra khi tạo connection mới, và response timeout là khoảng cách giữa các lần đọc chứ không phải tổng thời gian đọc. Hãy dùng số liệu latency thực tế để đặt ngưỡng.

### 9.2. Chọn timeout theo percentile

Đo latency của từng giai đoạn ở production hoặc staging:

- p50: latency thường gặp.
- p95: mức chậm của phần lớn request.
- p99/p99.9: tail latency.
- Error rate và timeout rate theo remote host.
- Pending acquire time và số request pending.

Timeout thường nên cao hơn latency hợp lệ ở percentile mục tiêu nhưng vẫn đủ ngắn để bảo vệ caller. Nếu đặt quá thấp, request hợp lệ bị hủy và retry có thể làm tải tăng. Nếu đặt quá cao, request lỗi giữ connection và tài nguyên quá lâu.

### 9.3. Timeout không phải giới hạn concurrency

Timeout chỉ giới hạn thời gian chờ. Nó không thay thế:

- maxConnections.
- pendingAcquireMaxCount.
- Rate limiting.
- Bulkhead/semaphore.
- Circuit breaker.
- Giới hạn request body và response body.

Một pool có timeout hợp lý nhưng queue rất lớn vẫn có thể tích tụ quá nhiều request. Hãy giới hạn cả số lượng công việc đồng thời và thời gian tồn tại của chúng.

## 10. Retry và timeout phải được thiết kế cùng nhau

Retry có thể giúp vượt qua lỗi mạng tạm thời, nhưng retry cũng tạo request mới và tiêu thụ thêm connection.

### 10.1. Retry có backoff và giới hạn số lần

~~~java
Mono<Product> load(String id) {
    return client.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
                .maxBackoff(Duration.ofSeconds(1))
        )
        .timeout(Duration.ofSeconds(8));
}
~~~

Ví dụ cho tối đa hai lần retry với exponential backoff và deadline tổng thể 8 giây. Deadline bao trùm toàn bộ chuỗi retry vì operator timeout đặt bên ngoài retryWhen.

Trong ứng dụng thực tế, thêm filter theo loại exception/status; không retry mọi lỗi.

### 10.2. Không retry lỗi không thể khắc phục bằng retry

Thông thường không nên retry mù quáng:

- 400 validation error.
- 401/403 authentication/authorization error.
- 404 khi resource thực sự không tồn tại.
- Pool acquire timeout do hệ thống đang quá tải kéo dài.
- Response decode error do payload sai định dạng.

Một số lỗi connect/reset/503 có thể tạm thời, nhưng cần chính sách cụ thể theo API.

### 10.3. Chú ý thao tác không idempotent

Nếu POST tạo đơn hàng bị timeout sau khi server đã xử lý nhưng trước khi client nhận response, client không biết thao tác đã hoàn tất hay chưa. Retry có thể tạo đơn hàng trùng.

Với thao tác không idempotent:

- Dùng idempotency key hoặc request ID được server lưu và kiểm tra.
- Chỉ retry khi hợp đồng API bảo đảm an toàn.
- Có cơ chế tra cứu kết quả nếu client không biết lần trước đã thành công hay chưa.

### 10.4. Deadline phải tính cả retry

Nếu mỗi lần retry có timeout 8 giây và retry 3 lần, tổng thời gian có thể vượt 24 giây cộng backoff. Đặt deadline tổng thể ở ngoài retry chain để giữ SLA:

~~~java
return oneAttempt()
    .retryWhen(retryPolicy)
    .timeout(Duration.ofSeconds(8));
~~~

Nếu đặt timeout riêng trong mỗi attempt, timeout đó chỉ giới hạn một lần gọi; không giới hạn tổng số lần và thời gian backoff.

## 11. Metrics và chẩn đoán timeout

Khi dùng Reactor Netty, bật metrics cho connection pool/HttpClient nếu ứng dụng có Micrometer phù hợp:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("catalog-pool")
        .maxConnections(50)
        .pendingAcquireMaxCount(100)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .metrics(true)
        .build();
~~~

Các metric quan trọng có thể gồm:

| Metric | Ý nghĩa |
| --- | --- |
| §reactor.netty.connection.provider.active.connections§ | Số connection đang được sử dụng. |
| §reactor.netty.connection.provider.idle.connections§ | Số connection đang idle trong pool. |
| §reactor.netty.connection.provider.pending.connections§ | Số request đang chờ connection. |
| §reactor.netty.connection.provider.max.connections§ | Giới hạn connection của pool. |
| §reactor.netty.connection.provider.pending.connections.time§ | Thời gian chờ acquire connection. |
| §reactor.netty.http.client.connect.time§ | Thời gian thiết lập connection. |
| §reactor.netty.http.client.tls.handshake.time§ | Thời gian TLS handshake. |
| §reactor.netty.http.client.errors§ | Số lỗi của HTTP client. |
| §reactor.netty.http.client.response.time§ | Thời gian request/response theo metric của client. |

Tên metric cụ thể và tag phụ thuộc Reactor Netty version, transport và Micrometer registry. Hãy kiểm tra metric được export thực tế thay vì giả định mọi metric đều có sẵn.

### 11.1. Cách đọc dấu hiệu

| Quan sát | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Pending connections tăng, active chạm max | Pool saturation | maxConnections, request concurrency, body chưa tiêu thụ |
| Pending acquire timeout tăng | Không có connection được trả kịp | Latency downstream, pool limit, connection leak |
| Connect time tăng | DNS/network/TCP path | DNS resolver, firewall, remote reachability |
| TLS handshake time tăng | TLS server/certificate/network | TLS config, handshake latency, proxy |
| Response timeout tăng | Server ngừng gửi hoặc read gap quá dài | Remote latency, slow streaming, network stalls |
| Overall Mono timeout tăng nhưng timeout riêng thấp | Tổng các giai đoạn hoặc retry/backoff vượt SLA | Trace từng phase, deadline và retry count |
| Connection reset/premature close | Peer/proxy đóng connection hoặc network interruption | Idle timeout alignment, stale connection, proxy/load balancer |

Không chẩn đoán chỉ từ exception message. Kết hợp metric, trace, remote host, request ID và phase timing.

## 12. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nhầm pending acquire timeout với connect timeout | Tăng sai timeout nhưng request vẫn chờ pool | Kiểm tra pending queue và cấu hình ConnectionProvider |
| Nghĩ responseTimeout là tổng thời gian request | Stream dài vẫn có thể chạy lâu nếu đều đặn có data | Dùng deadline tổng thể riêng |
| Dùng Mono.timeout như timeout riêng cho TCP | Không biết request chậm ở phase nào | Cấu hình connect/acquire/response timeout chuyên biệt |
| Không đặt response timeout | Response có thể im lặng quá lâu | Đặt responseTimeout theo hợp đồng API |
| Đặt responseTimeout quá ngắn cho SSE | Stream hợp lệ bị timeout khi không có event | Chọn read-gap phù hợp heartbeat |
| Tăng maxConnections để che pool saturation | Gây tải lớn hơn cho remote và network | Đo concurrency/latency, giới hạn queue và bulkhead |
| Pending queue không giới hạn | Request tích tụ, memory và latency tăng | Đặt pendingAcquireMaxCount hữu hạn |
| Retry mọi exception | Tăng tải khi lỗi cố định hoặc overload | Retry có filter, backoff, jitter và giới hạn |
| Retry POST không có idempotency | Tạo dữ liệu trùng | Idempotency key hoặc không retry |
| Đặt timeout mỗi lần thử nhưng không có deadline tổng | Tổng thời gian vượt SLA | Đặt timeout bên ngoài retry chain |
| Bỏ qua DNS/TLS/proxy | Chẩn đoán sai giai đoạn chậm | Theo dõi resolver, handshake và proxy timeout |
| Dùng một timeout cho mọi endpoint | File stream/SSE bị cắt | Cấu hình theo workload/remote service |
| Tạo ConnectionProvider cho từng request | Mất pooling và tạo nhiều socket | Dùng provider dùng chung theo remote/workload |
| Không dispose custom provider | Tài nguyên client còn sống sau khi context đóng | Quản lý lifecycle bằng Spring bean |
| Chỉ nhìn exception, không theo dõi pool metrics | Không phân biệt overload và network failure | Bật metrics và trace theo phase |

## 13. Ví dụ Java 17 chạy được và kiểm thử timeout

Ví dụ dùng Spring Boot 3.3.5, Java 17, WebFlux và MockWebServer. Test sử dụng server local để tạo response chậm và pool contention; không phụ thuộc internet hoặc một địa chỉ IP bên ngoài.

### 13.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 13.2. WebClientTimeoutApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebClientTimeoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebClientTimeoutApplication.class, args);
    }
}
~~~

### 13.3. CatalogClientConfiguration.java

~~~java
package demo;

import java.time.Duration;

import io.netty.channel.ChannelOption;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
class CatalogClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogPool() {
        return ConnectionProvider.builder("catalog")
            .maxConnections(20)
            .pendingAcquireMaxCount(40)
            .pendingAcquireTimeout(Duration.ofSeconds(1))
            .maxIdleTime(Duration.ofSeconds(20))
            .maxLifeTime(Duration.ofMinutes(5))
            .evictInBackground(Duration.ofSeconds(30))
            .metrics(true)
            .build();
    }

    @Bean
    WebClient catalogWebClient(ConnectionProvider catalogPool) {
        HttpClient httpClient = HttpClient.create(catalogPool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
            .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
            .baseUrl("https://catalog.example.test")
            .clientConnector(
                new ReactorClientHttpConnector(httpClient)
            )
            .build();
    }
}
~~~

Actuator đưa Micrometer vào classpath để metrics có thể được export qua registry phù hợp. Cấu hình metrics không tự tạo dashboard; ứng dụng cần registry/exporter và cấu hình endpoint/monitoring tương ứng.

### 13.4. TimeoutClient.java

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

record Item(String id, String name) {}

@Component
class TimeoutClient {

    private final WebClient client;

    TimeoutClient(WebClient catalogWebClient) {
        this.client = catalogWebClient;
    }

    Mono<Item> getItem(String id) {
        return client.get()
            .uri("/items/{id}", id)
            .retrieve()
            .bodyToMono(Item.class)
            .timeout(Duration.ofSeconds(8));
    }

    Mono<Item> getItemWithMappedDeadline(String id) {
        return getItem(id)
            .onErrorMap(
                TimeoutException.class,
                error -> new CatalogDeadlineExceededException(
                    "Catalog call exceeded its deadline"
                )
            );
    }
}

class CatalogDeadlineExceededException extends RuntimeException {
    CatalogDeadlineExceededException(String message) {
        super(message);
    }
}
~~~

### 13.5. TimeoutClientTest.java

~~~java
package demo;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import reactor.core.Disposable;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotNull;

class TimeoutClientTest {

    private MockWebServer server;

    @BeforeEach
    void startServer() throws IOException {
        server = new MockWebServer();
        server.start();
    }

    @AfterEach
    void stopServer() throws IOException {
        server.shutdown();
    }

    private WebClient createClient(
            ConnectionProvider provider,
            Duration responseTimeout) {

        HttpClient httpClient = HttpClient.create(provider)
            .responseTimeout(responseTimeout);

        return WebClient.builder()
            .baseUrl(server.url("/").toString())
            .clientConnector(
                new ReactorClientHttpConnector(httpClient)
            )
            .build();
    }

    @Test
    void responseTimeoutFailsWhenReadGapIsTooLong() {
        ConnectionProvider provider =
            ConnectionProvider.newConnection();

        try {
            WebClient client = createClient(
                provider,
                Duration.ofMillis(150)
            );

            server.enqueue(new MockResponse()
                .setResponseCode(200)
                .setBodyDelay(500, TimeUnit.MILLISECONDS)
                .setBody("{\"id\":\"1\",\"name\":\"slow\"}"));

            StepVerifier.create(
                    client.get()
                        .uri("/slow")
                        .retrieve()
                        .bodyToMono(String.class)
                )
                .expectError()
                .verify(Duration.ofSeconds(3));
        }
        finally {
            provider.disposeLater().block(Duration.ofSeconds(2));
        }
    }

    @Test
    void pendingAcquireTimeoutFailsWhenPoolIsBusy() throws Exception {
        ConnectionProvider provider =
            ConnectionProvider.builder("one-connection-test")
                .maxConnections(1)
                .pendingAcquireMaxCount(1)
                .pendingAcquireTimeout(Duration.ofMillis(100))
                .build();

        try {
            WebClient client = createClient(
                provider,
                Duration.ofSeconds(3)
            );

            server.enqueue(new MockResponse()
                .setResponseCode(200)
                .setBodyDelay(800, TimeUnit.MILLISECONDS)
                .setBody("first"));

            server.enqueue(new MockResponse()
                .setResponseCode(200)
                .setBody("second"));

            Disposable firstRequest = client.get()
                .uri("/first")
                .retrieve()
                .bodyToMono(String.class)
                .subscribe();

            try {
                RecordedRequest received =
                    server.takeRequest(1, TimeUnit.SECONDS);
                assertNotNull(received);

                StepVerifier.create(
                        client.get()
                            .uri("/second")
                            .retrieve()
                            .bodyToMono(String.class)
                    )
                    .expectError()
                    .verify(Duration.ofSeconds(2));
            }
            finally {
                firstRequest.dispose();
            }
        }
        finally {
            provider.disposeLater().block(Duration.ofSeconds(2));
        }
    }

    @Test
    void monoTimeoutIsAnEndToEndDeadline() {
        ConnectionProvider provider =
            ConnectionProvider.newConnection();

        try {
            WebClient client = createClient(
                provider,
                Duration.ofSeconds(2)
            );

            server.enqueue(new MockResponse()
                .setResponseCode(200)
                .setBodyDelay(500, TimeUnit.MILLISECONDS)
                .setBody("{\"id\":\"1\",\"name\":\"slow\"}"));

            StepVerifier.create(
                    client.get()
                        .uri("/slow")
                        .retrieve()
                        .bodyToMono(String.class)
                        .timeout(Duration.ofMillis(100))
                )
                .expectError(TimeoutException.class)
                .verify(Duration.ofSeconds(2));
        }
        finally {
            provider.disposeLater().block(Duration.ofSeconds(2));
        }
    }
}
~~~

Các test có ba mục tiêu khác nhau:

- Response timeout: server ngừng gửi body lâu hơn khoảng đọc cho phép.
- Pending acquire timeout: pool chỉ có một connection đang bận; request thứ hai phải chờ và hết thời gian acquire.
- Mono timeout: response timeout dài hơn, nhưng deadline tổng thể của publisher ngắn hơn nên thao tác vẫn timeout.

Connect timeout khó kiểm thử ổn định bằng một địa chỉ IP công cộng hoặc địa chỉ không thể định tuyến vì kết quả phụ thuộc hệ điều hành, firewall và mạng CI. Trong production, kiểm thử cấu hình connector và có thể dùng một TCP proxy/test harness có khả năng trì hoãn SYN/connect để kiểm chứng riêng phase này.

### 13.6. Chạy test

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Test dùng thời gian ngắn để hoàn thành nhanh trong CI. Khi chạy trên máy tải cao, scheduler và hệ điều hành có thể làm timing dao động; nếu cần kiểm thử ổn định hơn, tăng khoảng cách giữa delay và timeout, đồng thời không assert vào exception class transport quá cụ thể nếu phiên bản connector có thể wrap exception khác nhau.

## 14. Checklist cấu hình timeout trong production

Trước khi đưa WebClient vào production, hãy kiểm tra:

1. **Remote service:** host/port và SLA của remote đã rõ chưa?
2. **Connection pool:** maxConnections có phù hợp năng lực downstream không?
3. **Pending queue:** pendingAcquireMaxCount hữu hạn và đủ nhỏ chưa?
4. **Acquire timeout:** thời gian chờ pool có phù hợp deadline của caller không?
5. **Connect timeout:** TCP connect có fail nhanh khi network không phản hồi không?
6. **DNS/TLS/proxy:** các giai đoạn này có timeout và metrics phù hợp không?
7. **Response timeout:** khoảng im lặng cho phép có phù hợp JSON, download stream, SSE hoặc long polling không?
8. **Overall deadline:** Mono/service có deadline bao trùm các giai đoạn và retry không?
9. **Retry:** chỉ retry lỗi tạm thời, có backoff/jitter và idempotency không?
10. **Cancellation:** khi timeout, upstream request/response có được hủy và tài nguyên được giải phóng không?
11. **Metrics:** active/idle/pending connections, acquire time, connect time, TLS time và response time có được theo dõi không?
12. **Lifecycle:** custom ConnectionProvider có được dispose khi application context đóng không?
13. **Testing:** có test pool saturation, response stall, end-to-end deadline và error mapping không?
14. **Workload:** file stream/SSE có timeout riêng phù hợp với khoảng im lặng hợp lệ không?

**Ghi nhớ:** pending acquire timeout giới hạn thời gian chờ connection trong pool; connect timeout giới hạn TCP connection mới; response timeout giới hạn khoảng cách giữa các lần đọc response; Reactor timeout giới hạn publisher theo semantics của Mono/Flux. Hãy đo đúng phase, đặt timeout budget theo SLA, giới hạn cả connection lẫn pending queue, và thiết kế retry/cancellation để không làm quá tải hệ thống khi downstream chậm.

## Tài liệu tham khảo

- Reactor Netty — HTTP Client, Connection Pool and Timeout Configuration: https://projectreactor.io/docs/netty/release/reference/http-client.html
- Reactor Netty — HttpClientRequest responseTimeout API: https://projectreactor.io/docs/netty/release/api/reactor/netty/http/client/HttpClientRequest.html
- Spring Framework — WebClient Configuration and Reactor Netty Connector: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework — WebClient API and usage: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Spring Boot — Configure the Reactor Netty client used by WebClient: https://docs.spring.io/spring-boot/how-to/http-clients.html
