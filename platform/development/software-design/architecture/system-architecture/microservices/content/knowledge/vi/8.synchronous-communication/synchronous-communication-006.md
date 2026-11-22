# Quản lý kết nối, connection pool và tái sử dụng client trong Microservices

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Giao tiếp đồng bộ.
>
> **Mục tiêu:** hiểu vòng đời kết nối HTTP/gRPC, tránh tạo client mới liên tục, biết thiết kế connection pool với giới hạn phù hợp, kết hợp deadline và concurrency control, xử lý sự cố kết nối, quan sát và kiểm thử hiệu năng ở mức toàn hệ thống.

## 1. Vì sao cần quan tâm đến kết nối?

Trong hệ thống microservices, lời gọi REST hoặc gRPC từ Order sang Inventory nhìn giống một lời gọi hàm, nhưng thực chất cần đi qua mạng, proxy/load balancer và các tài nguyên có giới hạn.

~~~text
Client
  |
  v
API Gateway
  |
  v
Order Service
  |
  +-- HTTP/gRPC client ---> connection pool ---> Inventory Service
                                                        |
                                                        v
                                                  Inventory DB
~~~

Mỗi kết nối mới có thể cần DNS resolution, mở socket, TCP handshake, TLS handshake và phân bổ bộ nhớ. Khi tạo mới quá thường xuyên, chi phí này được trả lại trên từng request. Dù downstream xử lý nghiệp vụ rất nhanh, caller vẫn có thể chịu latency cao vì transport.

Tuy nhiên, một pool quá lớn không làm downstream có thêm năng lực xử lý. Khi Order gửi quá nhiều request đồng thời, Inventory có thể cạn worker threads hoặc database connections; các request chậm thêm, tạo timeout và retry storm.

**Nguyên tắc cốt lõi:** tái sử dụng kết nối để giảm chi phí thiết lập nhưng giới hạn lưu lượng đồng thời, hàng chờ và thời gian xử lý để bảo vệ cả hai phía.

### 1.1. Những mục tiêu cần cùng đạt

- **Hiệu năng:** giảm chi phí socket/TCP/TLS và latency kết nối mới.
- **Quản lý tài nguyên:** giới hạn connections, in-flight calls, pending requests, buffers và threads.
- **Chịu lỗi:** khi downstream chậm, request bị giới hạn hoặc từ chối có kiểm soát thay vì làm toàn cụm cạn tài nguyên.
- **Quan sát:** có metrics về active, idle, pending, acquire latency, retry, timeout và kết nối bị đóng.
- **Độc lập vận hành:** từng upstream có deadline, retry policy và ngân sách concurrency phù hợp.

## 2. Phân biệt HTTP client, connection, pool và request

| Khái niệm | Vai trò | Điều không được nhầm |
| --- | --- | --- |
| HTTP client | Đối tượng quản lý transport, TLS, proxy, codec, policy và pooling | Một client không bằng một TCP connection |
| Connection | Đường truyền TCP/TLS tới một endpoint/hop | Có thể đóng hoặc thay đổi ngoài ý muốn client |
| Keep-alive | Giữ connection để phục vụ request sau | Không đảm bảo socket tồn tại mãi |
| Connection pool | Cấp phát và tái sử dụng connection trong giới hạn | Không phải mọi pool đều có cùng semantics |
| Active connection | Connection đang được sử dụng tại thời điểm đo | Với HTTP/2, một connection có thể có nhiều streams |
| Idle connection | Connection rảnh, còn hợp lệ theo nhận định của client | Có thể đã bị LB/NAT đóng khi idle |
| Pending acquire | Request chờ resource của pool | Chờ có thể tiêu tốn gần hết deadline |
| In-flight request | Request đã bắt đầu và chưa hoàn tất | Có thể nhiều hơn số connections khi multiplex |
| gRPC channel | Đối tượng quản lý kết nối và transport cho nhiều RPC | Không cần channel mới cho mỗi call |
| Concurrency limiter | Giới hạn thao tác được thực thi đồng thời | Bổ sung chứ không thay cho connection pool |

Điểm khác biệt lớn nhất khi tính capacity là: **số connection không nhất thiết bằng số request đồng thời**, đặc biệt khi dùng HTTP/2 hoặc gRPC. Pool là giới hạn transport; bulkhead/concurrency limiter là giới hạn công việc nghiệp vụ có thể gây tải.

## 3. Vòng đời một request đồng bộ

~~~text
Order nhận yêu cầu
     |
     v
Kiểm tra deadline còn lại
     |
     v
Nhận permit từ concurrency limiter
     |
     v
Chờ pool acquire, nếu cần
     |
     +-- Connection cũ còn phù hợp -> reuse
     |
     +-- Chưa có connection -> DNS/connect/TLS
     |
     v
Gửi request tới Inventory
     |
     v
Nhận response headers và body
     |
     v
Deserialize hoặc stream nội dung
     |
     v
Giải phóng stream/response resource
     |
     v
Trả connection về pool nếu được tái sử dụng
     |
     v
Release permit và hoàn thành lời gọi
~~~

Các thư viện có thể thay đổi thứ tự chi tiết, và không phải mọi request đều cần mở connection mới. Cũng cần chú ý resource có thể nằm ở nhiều hop: client → sidecar, sidecar → upstream proxy, proxy → Inventory. Khi điều tra nghẽn, phải biết pool nào đang hoạt động.

### 3.1. Chi phí thiết lập mới

Một kết nối HTTPS mới có thể cần:

1. Lấy địa chỉ đích từ DNS/service discovery.
2. Mở TCP socket và thiết lập TCP.
3. Thực hiện TLS handshake và xác minh chứng chỉ.
4. Thương lượng HTTP version nếu có.
5. Được reverse proxy/server chấp nhận và cấp resource.
6. Gửi request và chờ application response.

Connection reuse giảm số lần trả chi phí thiết lập này; HTTP/2 còn cho phép multiplex nhiều request lên một TCP connection. Tuy nhiên server hoặc proxy có thể chủ động đóng kết nối do idle timeout, max age hoặc rollout. Không được giả định kết nối trong pool luôn còn sống.

## 4. Keep-alive và thời gian sống của connection

Keep-alive cho phép client giữ một kết nối sẵn sàng sử dụng lại sau khi request hoàn tất, thay vì đóng ngay. Với HTTP/1.1, persistent connections giúp giảm TCP/TLS handshakes giữa nhiều request tuần tự. Với HTTP/2, connection còn có thể phục vụ các streams đồng thời.

### 4.1. Vì sao socket idle có thể bị lỗi?

- Server đóng idle connection để tiết kiệm tài nguyên.
- Load balancer hoặc NAT xóa state sau thời gian không có dữ liệu.
- Pod/backend được thay thế, kết nối cũ đến endpoint sắp shutdown.
- Network reset hoặc timeout khiến trạng thái hai phía không còn đồng bộ.
- TLS/certificate rotation hoặc proxy reconfiguration yêu cầu kết nối mới.

Một stale connection có thể chỉ bị phát hiện khi request tiếp theo bắt đầu ghi dữ liệu. Client cần chính sách max idle/max lifetime và handling lỗi transport.

### 4.2. Max idle time khác max life time

**Max idle time** là khoảng kết nối không được sử dụng trước khi bị loại theo policy của pool. Nếu quá ngắn, tạo nhiều handshake mới; nếu quá dài so với LB idle timeout, client có thể reuse socket cũ đã bị đóng.

**Max life time** là tuổi tối đa từ khi kết nối được tạo. Dù đang được sử dụng thường xuyên, connection có thể phải được thay thế khi đạt điều kiện tuổi. Nó hỗ trợ việc luân chuyển endpoint, tránh bám quá lâu vào backend cũ và giảm số connection quá già. Tuy nhiên quá ngắn sẽ tạo churn.

Chính sách thu hồi thường phụ thuộc implementation: pool có thể đóng connection khi nó được trả về hoặc ở một vòng quét nền, chứ không nhất thiết ngắt một request đang chạy đúng lúc chạm ngưỡng.

## 5. HTTP/1.1 pooling và HTTP/2 multiplexing

### 5.1. HTTP/1.1

Trong cách sử dụng HTTP/1.1 thông dụng không pipelining, một connection phục vụ một chuỗi request/response tại một thời điểm. Muốn nhiều request đồng thời tới cùng upstream, thường cần nhiều connections:

~~~text
Order HTTP/1.1 pool
  Connection 1 -> request A
  Connection 2 -> request B
  Connection 3 -> request C
  Connection 4 -> idle, có thể reuse
~~~

Nếu số request vượt số connection khả dụng, request có thể chờ acquire, được mở thêm connection tới giới hạn, hoặc bị từ chối khi hết ngân sách.

### 5.2. HTTP/2

HTTP/2 multiplex nhiều streams trên một TCP connection:

~~~text
One HTTP/2 connection
  stream 1 -> GET /products/A
  stream 3 -> GET /products/B
  stream 5 -> POST /reservations
  stream 7 -> GET /products/C
~~~

Nhờ đó số TCP connections có thể ít hơn đáng kể, nhưng concurrency không vô hạn. Stream limits, HTTP/2 flow control, connection congestion, tốc độ đọc body và công suất server vẫn tồn tại.

Một TCP connection mang nhiều streams cũng có thể trở thành điểm nóng. Khi mất connection hoặc xảy ra reset, nhiều request cùng bị ảnh hưởng. Khi dùng L4 load balancer, long-lived connection có thể bám một backend và làm phân phối tải không đều. Vì thế phải đo cả **active streams, in-flight calls và backend utilization**, không chỉ socket count.

### 5.3. Hậu quả cho pool sizing

Một cấu hình maxConnections=100 không có ý nghĩa tương đương ở mọi protocol. Với HTTP/1.1, đó thường là giới hạn gần với số request đang giữ socket. Với HTTP/2, nhiều request có thể đi trên một connection; stream limits và bulkhead mới trở thành tham số rất quan trọng.

Kiểm tra transport thực tế từng hop: một client có thể thương lượng HTTP/2 với gateway nhưng gateway tiếp tục dùng HTTP/1.1 tới backend.

## 6. gRPC và tái sử dụng ManagedChannel

gRPC Java thường sử dụng HTTP/2. ManagedChannel quản lý transport cho nhiều RPC. Client stub có thể được tạo từ channel đã tồn tại. Không nên tạo channel mới cho mỗi lời gọi nếu không có lý do cách ly đặc biệt.

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.concurrent.TimeUnit;

public final class InventoryGrpcGateway implements AutoCloseable {

    private final ManagedChannel channel;
    private final InventoryGrpc.InventoryBlockingStub stub;

    public InventoryGrpcGateway(String target) {
        channel = ManagedChannelBuilder
            .forTarget(target)
            .useTransportSecurity()
            .build();

        stub = InventoryGrpc.newBlockingStub(channel);
    }

    public ReserveReply reserve(ReserveRequest request) {
        return stub
            .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
            .reserve(request);
    }

    @Override
    public void close() throws InterruptedException {
        channel.shutdown();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    }
}
~~~

Các lớp InventoryGrpc, ReserveReply và ReserveRequest minh họa một contract Protobuf đã được generate. Trong ứng dụng, quản lý channel bằng dependency injection/lifecycle của ứng dụng và gắn deadline phù hợp cho mỗi RPC.

Channel reuse không tự giải quyết overload; gRPC cũng có giới hạn HTTP/2 streams, backpressure và deadline. Tăng số channel có thể phù hợp trong một số trường hợp đã đo được bottleneck nhưng không nên mặc định thêm channel mỗi RPC.

## 7. Anti-pattern: khởi tạo client cho mỗi request

Ví dụ minh họa không nên áp dụng khi có nhiều request:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public String getStock(String sku) throws Exception {
    HttpClient client = HttpClient.newHttpClient();

    HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://inventory.internal/items/" + sku))
        .GET()
        .build();

    return client.send(
        request, HttpResponse.BodyHandlers.ofString()
    ).body();
}
~~~

Lỗi thiết kế là mỗi lần tạo một phạm vi quản lý transport mới. Các kết nối không được chia sẻ giữa những lần gọi như mong muốn, dễ gây handshake churn và khó quản trị TLS, timeout, logging, tracing và shutdown.

Không nhất thiết việc tạo đối tượng lập tức mở TCP; chi phí lớn thường xuất hiện khi request thực sự cần kết nối. Tuy nhiên việc khởi tạo lặp lại làm giảm khả năng pooling có chủ đích.

## 8. Pattern: client có vòng đời dài trong Java

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class InventoryGateway {

    private final HttpClient client;

    public InventoryGateway() {
        client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(1))
            .version(HttpClient.Version.HTTP_2)
            .build();
    }

    public String getStock(String sku) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://inventory.internal/items/" + sku))
            .timeout(Duration.ofSeconds(2))
            .GET()
            .build();

        return client.send(
            request, HttpResponse.BodyHandlers.ofString()
        ).body();
    }
}
~~~

InventoryGateway có thể được cung cấp dưới dạng singleton qua DI container. Mỗi request tạo request object riêng nhưng dùng chung HttpClient đã cấu hình. JDK HTTP client quản lý connection reuse nội bộ; API chuẩn không cung cấp mọi tùy chọn pool sizing như Apache HttpClient hoặc Reactor Netty.

Nếu cần giới hạn in-flight calls, dùng semaphore/bulkhead hoặc thư viện có hỗ trợ. Không nên giả định chỉ đặt HTTP/2 hoặc connectTimeout là đủ để bảo vệ backend.

### 8.1. Request-scoped context phải tách khỏi singleton

Không để mutable token, correlation ID, tenant ID hoặc các headers theo người dùng trong field của shared client/gateway. Client dùng chung nên chứa transport configuration tương đối bất biến; authentication, deadline, tracing context và request body thuộc từng lời gọi.

## 9. Giới hạn concurrency bằng semaphore

Ví dụ Java có concurrency limit độc lập với số connection:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class BoundedInventoryGateway {
    private final HttpClient client = HttpClient.newHttpClient();
    private final Semaphore permits = new Semaphore(50);

    public String get(String sku) throws Exception {
        if (!permits.tryAcquire(100, TimeUnit.MILLISECONDS)) {
            throw new IllegalStateException("Inventory capacity exhausted");
        }

        try {
            HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://inventory.internal/items/" + sku))
                .timeout(Duration.ofSeconds(2))
                .GET()
                .build();

            return client.send(
                request, HttpResponse.BodyHandlers.ofString()
            ).body();
        } finally {
            permits.release();
        }
    }
}
~~~

Ví dụ chỉ minh họa cách dùng permit và finally, chưa bao gồm chuẩn hóa lỗi, metrics, URI encoding, retry, cancellation hay overall deadline. Những phần đó cần được bổ sung theo thực tế. Khi permit không được cấp trong thời gian hữu hạn, có thể trả lỗi bận hoặc chuyển sang trạng thái chờ theo contract.

**Giới hạn này đặc biệt quan trọng với HTTP/2**: một connection có thể chở nhiều streams, nên chỉ đếm socket không đủ để bảo vệ backend.

## 10. Spring WebClient và Reactor Netty ConnectionProvider

Một ứng dụng Spring có thể tạo connection pool và WebClient một lần bằng bean:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class InventoryClientConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider inventoryProvider() {
        return ConnectionProvider.builder("inventory-pool")
            .maxConnections(100)
            .pendingAcquireMaxCount(120)
            .pendingAcquireTimeout(Duration.ofMillis(250))
            .maxIdleTime(Duration.ofSeconds(30))
            .maxLifeTime(Duration.ofMinutes(5))
            .evictInBackground(Duration.ofSeconds(30))
            .build();
    }

    @Bean
    WebClient inventoryWebClient(
        ConnectionProvider inventoryProvider
    ) {
        HttpClient netty = HttpClient.create(inventoryProvider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1000)
            .responseTimeout(Duration.ofSeconds(2))
            .keepAlive(true);

        return WebClient.builder()
            .baseUrl("https://inventory.internal")
            .clientConnector(
                new ReactorClientHttpConnector(netty)
            )
            .build();
    }
}
~~~

Các giá trị trên là **ví dụ**. Không nên chép nguyên vào production mà chưa đo tải và xác nhận semantics trong phiên bản Reactor Netty thực tế. Đặc biệt cần xác minh scope maxConnections theo pool key/route, đặc tính HTTP/1.1 hay HTTP/2 và những connection resources thực sự được quản lý.

Một gateway sử dụng bean đã được inject:

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public final class InventoryWebGateway {
    private final WebClient client;

    public InventoryWebGateway(WebClient client) {
        this.client = client;
    }

    public Mono<InventoryDto> getInventory(String sku) {
        return client.get()
            .uri("/items/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryDto.class)
            .timeout(Duration.ofSeconds(3));
    }
}
~~~

InventoryDto là kiểu DTO giả định của contract Inventory. Operator timeout trên Publisher không thay thế toàn bộ các policy connect/acquire/response và deadline của workflow; nó là thêm một lớp bảo vệ.

### 10.1. Không block event loop

Reactive Netty dùng event loops; nếu chạy Thread.sleep, JDBC blocking hoặc các lời gọi blocking kéo dài trên event loop, một số ít threads có thể khiến nhiều connections bị treo. Dùng scheduler/executor phù hợp cho blocking operations hoặc chọn mô hình request-thread/virtual-thread phù hợp với ứng dụng, vẫn phải giữ concurrency limits.

### 10.2. Đóng provider khi shutdown

Không dispose provider sau mỗi request; dùng vòng đời của application context. Khi ứng dụng dừng, ngừng nhận traffic mới, chờ các request đang xử lý trong thời gian cho phép rồi dispose connection provider/channel/client theo API tương ứng.

## 11. Apache HttpClient: max total và max per route

Với Apache HttpClient 5, connection manager có thể cung cấp giới hạn tổng và từng route:

~~~java
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;

public final class ApacheClientFactory {

    public static CloseableHttpClient create() {
        PoolingHttpClientConnectionManager manager =
            PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(200)
                .setMaxConnPerRoute(40)
                .build();

        return HttpClients.custom()
            .setConnectionManager(manager)
            .evictExpiredConnections()
            .build();
    }
}
~~~

Ví dụ cho thấy giới hạn tổng 200 connections và tối đa 40 cho mỗi route, nhưng chưa cấu hình đầy đủ TLS, request/response timeout và instrumentation. Trong hệ thống thực tế, giữ CloseableHttpClient có vòng đời dài, quản lý close ở shutdown và xác minh đúng API của phiên bản được dùng.

Nếu có 100 connections tổng mà max per route chỉ 20, một upstream có thể chờ connection dù vẫn còn capacity tổng. Không nên hiểu max total và max per route là hai giá trị thay thế nhau.

## 12. Pool sizing dựa trên tải và Little's Law

Một ước lượng hữu ích trong hệ ổn định là:

\[
L = \lambda W
\]

Với L là số công việc đồng thời trung bình, lambda là throughput request/giây và W là mean time trong hệ, đơn vị giây.

Ví dụ:

- Inventory nhận từ Order trung bình 500 requests/giây.
- Thời gian trung bình của một lời gọi là 120 ms = 0,12 giây.
- Số in-flight trung bình ước lượng là 500 × 0,12 = 60.

Con số 60 **không tự động là cấu hình maxConnections phù hợp**, vì HTTP version, burst, số pods, proxy, thời gian chờ pool và công suất downstream còn ảnh hưởng. Cũng không thể lấy p95 latency nhân RPS rồi khẳng định đó là p95 concurrency; Little's Law mô tả trung bình khi điều kiện áp dụng phù hợp.

Nếu response latency tăng từ 120 ms lên 2 giây và arrival rate vẫn 500/s, số yêu cầu cần giữ trong hệ để duy trì tốc độ tương ứng có thể tăng lên khoảng 1000. Đây là lý do cần giới hạn in-flight và backpressure, không chỉ tăng pool đến 1000.

### 12.1. Số pods làm thay đổi tải toàn cụm

Giả sử mỗi Order pod cho phép 100 in-flight calls tới Inventory, và có 30 pods. Tổng offered concurrent calls có thể lên tới khoảng 3000, chưa tính các caller khác. Autoscaling thêm Order pods có thể tăng áp lực xuống Inventory thay vì tự giải quyết sự cố của Inventory.

Cần thiết kế giới hạn theo số replicas và sức chứa toàn cụm, có server-side rate/concurrency limiter làm lớp bảo vệ cuối cùng khi cần.

### 12.2. Quy trình chọn ngưỡng

1. Đo RPS, mean/p95/p99 latency và concurrency thật.
2. Đo công suất downstream trước khi CPU, DB pool hoặc queue bị bão hòa.
3. Chọn max in-flight/pool limits có headroom cho burst nhưng không vượt downstream budget.
4. Đặt pending queue hữu hạn và acquire timeout ngắn hơn deadline còn lại.
5. Chạy load test với steady load, burst, timeout, backend chậm và rolling deployment.
6. Quan sát reject rate, retries và thời gian phục hồi.
7. Điều chỉnh từ kết quả đo thay vì sao chép một giá trị của hệ khác.

## 13. Pending queue, backpressure và fail fast

Ví dụ pool HTTP/1.1 cho phép 40 connections, pending queue tối đa 80. Khi 200 requests đến gần đồng thời:

~~~text
200 incoming calls
    |
    +-- 40 active calls
    |
    +-- 80 waiting for pool acquire
    |
    +-- 80 rejected / failed early
~~~

Trên thực tế, các queue có thể nằm ở application executor, Reactor subscriber, connection pool, Envoy sidecar, load balancer hoặc server. Một queue ở mỗi tầng có thể làm tổng thời gian chờ cao hơn nhiều so với dự đoán.

**Backpressure** là kiểm soát lượng công việc được tiếp nhận khi không còn đủ công suất. Với API cần phản hồi nhanh, chờ rất lâu thường vô nghĩa. Tùy contract có thể trả 429/503 hoặc trạng thái PENDING nếu nghiệp vụ cho phép.

Tăng pendingAcquireMaxCount vô hạn để “không mất request” có thể khiến request hết deadline ngay trong hàng đợi, làm tăng RAM và tăng retry khi các caller không nhận được phản hồi kịp thời.

## 14. Timeout cần tách rõ theo giai đoạn

Một lời gọi có thể tốn thời gian cho:

~~~text
Acquire limiter permit
  -> Acquire pool slot
  -> DNS (nếu cần)
  -> TCP connect (nếu tạo kết nối mới)
  -> TLS handshake
  -> Send request
  -> Wait response headers
  -> Read response body
  -> Deserialize / business processing
~~~

Các thư viện khác nhau có cách định nghĩa connect timeout, read timeout và response timeout khác nhau. Không nên giả định chỉ một tham số readTimeout bảo vệ toàn bộ đường đi.

### 14.1. Pool acquisition timeout

Giới hạn thời gian chờ connection hoặc resource pool. Nếu thường xuyên vượt ngưỡng, cần điều tra pool quá nhỏ, connection leak hoặc downstream chậm. Chỉ tăng pool nếu backend thực sự có headroom.

### 14.2. Connect timeout

Giới hạn thời gian mở TCP connection mới theo semantics của client. Nếu đã có socket, connect timeout không xử lý phần chờ response; cũng không nhất thiết bao gồm DNS/TLS/pool wait.

### 14.3. TLS handshake timeout

Một số thư viện cho phép cấu hình riêng. Lỗi chứng chỉ/identity không được xử lý bằng cách tắt hostname verification hay bỏ kiểm tra certificate.

### 14.4. Response/read timeout

Có thể giới hạn chờ response hoặc khoảng im lặng giữa các lần đọc, tùy thư viện. Với streaming endpoint, “không có byte trong 10 giây” khác “toàn bộ body phải tải xong trong 10 giây”.

### 14.5. End-to-end deadline

Ngân sách của cả request từ caller đến khi trả kết quả. Nếu Gateway có deadline 1500 ms nhưng Order đã dùng 900 ms, một lần gọi Payment tiếp theo không được tự tạo ba retries mỗi lần 2 giây. Cần biết thời gian còn lại và giới hạn các bước cho phù hợp.

Ví dụ ngân sách minh họa:

| Bước | Ngân sách |
| --- | ---: |
| Gateway/auth/routing | 100 ms |
| Order local logic | 100 ms |
| Inventory | 350 ms |
| Payment | 600 ms |
| Serialize/response | 100 ms |
| Safety margin | 250 ms |
| **Tổng** | **1500 ms** |

Những giá trị là giả định để giải thích budget, không phải SLO cho mọi hệ thống. Phần thời gian thực có thể khác nhau; điểm mấu chốt là các hop không tự tiêu hết nhiều lần ngân sách.

## 15. Timeout không chứng minh thao tác chưa thực thi

Một request có side effect có thể bị ngắt:

1. Trước khi server nhận được request.
2. Trong khi truyền body.
3. Sau khi server đã commit, trước khi trả response.
4. Sau khi server trả response nhưng kết nối mất trên đường về.

Client chỉ thấy timeout hoặc reset, không luôn biết thao tác đã hoàn tất chưa. Ví dụ Payment đã trừ tiền nhưng Order mất response:

~~~text
Order                              Payment
  | POST /charge                    |
  | Idempotency-Key: order-731-pay  |
  |-------------------------------->|
  |                                 | commit thành công
  |             [mất response]      |
  X                                 |
  | retry cùng idempotency key      |
  |-------------------------------->|
  |                                 | trả kết quả đã ghi nhận
  |<--------------------------------|
~~~

Idempotency key phải đại diện cho cùng một ý định nghiệp vụ và được lưu theo contract đủ bền. Một key mới khi retry có thể tạo giao dịch thứ hai. Khi không chắc chắn, phải có API tra cứu trạng thái hoặc reconciliation.

## 16. Retry và retry storm

Một downstream chậm khiến caller retry; nhiều tầng cùng retry làm traffic phình ra. Nếu Gateway, Order và Inventory client đều có retry policy độc lập, một yêu cầu gốc có thể tạo nhiều lời gọi xuống tầng cuối.

Cần:

- Chọn tầng nào được retry và loại lỗi nào được retry.
- Giới hạn attempts và tổng thời gian trong overall deadline.
- Dùng exponential backoff và jitter khi phù hợp.
- Có retry budget hoặc giới hạn tỷ lệ requests được thử lại.
- Tôn trọng Retry-After nếu server công bố và còn ngân sách.
- Chỉ retry thao tác có semantics idempotent hoặc idempotency key hợp lệ.
- Phân biệt error response do nghiệp vụ từ chối với lỗi hệ thống có khả năng phục hồi.
- Theo dõi số retry requests trên mỗi original request.

Pool size không tự ngăn retry storm. Ngược lại, pool lớn làm retry có thể được đẩy xuống backend nhanh hơn và làm backend càng quá tải.

## 17. DNS, load balancer và service mesh

Connection reuse có lợi nhưng làm client có thể giữ socket tới backend cũ sau khi DNS hoặc endpoint discovery thay đổi. Rolling deployment, failover hoặc thay đổi backend cần một chính sách kết nối phù hợp.

### 17.1. L4 và L7 khác nhau

L4 balancer có thể phân phối theo TCP connection. Một connection HTTP/2 dài hạn chở nhiều streams có thể bám một backend và gây traffic skew. L7 proxy có thể cân bằng theo HTTP request/stream, nhưng cần xác minh cấu hình thực tế.

### 17.2. Service mesh tạo thêm pool

~~~text
Order application
    |
    v
Local sidecar pool
    |
    v
Mesh / network proxy
    |
    v
Inventory sidecar pool
    |
    v
Inventory application
~~~

Khi dùng Envoy hoặc mesh khác, application pool không phải pool duy nhất. Có thể có connection limits và retries ở proxy, khác timeout của ứng dụng. Phải kiểm tra tổng retry amplification giữa các tầng và tránh hai nơi đồng thời retry cùng một thao tác non-idempotent.

### 17.3. Graceful connection draining

Khi backend được thay thế, readiness/draining cần cho các yêu cầu đang chạy hoàn tất trong giới hạn. HTTP/2 có GOAWAY báo không nhận streams mới. Client phải xử lý reconnect, reset và request có kết quả không chắc chắn. Kiểm thử rolling deployment là cần thiết, vì một hệ chỉ test khi backend khỏe thường không thấy lỗi lifecycle.

## 18. Connection leak và phản hồi streaming

Một response có body lớn/streaming có thể giữ connection trong suốt quá trình đọc. Nếu consumer không đóng stream khi gặp exception hoặc sau khi không cần body, active connections có thể duy trì ở max và pending acquire tăng dần.

Dấu hiệu:

- Active connections không giảm về baseline sau burst.
- Idle connections gần bằng 0 dù throughput đã thấp.
- Pending acquire tăng dần, acquire timeout xảy ra thường xuyên.
- Số file descriptors hoặc socket sống lâu không hợp lý.
- Server latency bình thường nhưng caller chờ pool lâu.

Phòng tránh:

- Consume hoặc close response body theo API của client.
- Dùng try-with-resources khi phù hợp.
- Hủy streaming subscription và giải phóng resource khi caller cancel.
- Thiết lập deadline cho các hoạt động không phải streaming dài hạn.
- Tracing và metrics để biết connection được giữ bởi loại request nào.
- Test khi deserialize lỗi, client cancel và server đóng stream bất thường.

Không phải mọi connection active dài là leak: một stream hợp lệ có thể chạy lâu. Cần đối chiếu loại request và vòng đời mong đợi.

## 19. Security và quản lý credentials

Singleton client tạo điều kiện reuse nhưng phải tránh lưu trạng thái bảo mật từng request trong đối tượng dùng chung.

- Token có expiry phải được lấy/refresh theo scope đúng, không cache vô hạn.
- Không chia sẻ Authorization header mutable giữa các users/tenants.
- Client certificate khi mTLS rotate có thể yêu cầu kết nối mới; cần chính sách lifecycle.
- Không tắt TLS verification để làm reconnect thành công.
- Thư viện logging/interceptor dùng chung phải che token, PII và dữ liệu thanh toán.
- Nếu những nhóm traffic có TLS identities khác nhau, cần cách ly transport phù hợp và giới hạn số pool.

Trace ID, correlation ID và auth identity cần được truyền theo từng request, không gán vào global mutable field của shared client.

## 20. Bulkhead, circuit breaker và rate limiting

Connection pool quản lý transport nhưng không thay thế chính sách chịu lỗi.

**Bulkhead:** giới hạn một dependency không chiếm hết tài nguyên của service. Ví dụ Order có 80 permits cho Inventory, 30 cho Payment và 20 cho Recommendation; các giá trị phải được đo, không sao chép.

**Circuit breaker:** sau nhiều lỗi đủ điều kiện, có thể ngưng gửi requests tạm thời để tránh làm downstream tệ hơn. Lỗi validation 400 không nên được xem giống lỗi service unavailable. Khi circuit breaker mở, UI/API phải phản ánh trạng thái chính xác.

**Rate limit:** giới hạn requests/giây. **Concurrency limit:** giới hạn số requests đang xử lý. Một service nhận 100 RPS với mean latency 10 ms chỉ có khoảng 1 in-flight; nếu latency tăng 2 giây, có thể cần ~200 in-flight để duy trì tốc độ. Vì vậy rate limiting không thay thế concurrency limit.

**Load shedding:** từ chối công việc không thể phục vụ an toàn khi overload, thay vì cố đưa mọi request vào pending queue dài. Nếu một tác vụ có thể xử lý nền thì nhận dưới trạng thái PENDING/ACCEPTED có ngữ nghĩa rõ, không tuyên bố giao dịch đã CONFIRMED.

## 21. Không giữ transaction/lock trong lúc gọi network

Ví dụ không nên mặc định:

~~~text
BEGIN ORDER_DB_TRANSACTION
  lock Order row
  call Inventory HTTP, wait...
  call Payment HTTP, wait...
  call Notification HTTP, wait...
COMMIT
~~~

Cách này giữ database connection/lock qua những khoảng chờ mạng không đoán trước, gây áp lực lên DB pool, kéo dài transaction và gia tăng cascading failures. Với workflow nhiều service, thường nên dùng transactions cục bộ ngắn, state machine, idempotent commands, outbox và reconciliation. Nếu một invariant thật sự cần transaction nguyên tử, xem lại ownership/boundary trước khi thêm distributed transaction phức tạp.

## 22. Metrics và tracing cần có

| Nhóm | Chỉ số nên có | Ý nghĩa |
| --- | --- | --- |
| Pool | active, idle, max, pending | Đo pressure/underutilization |
| Acquire | wait duration, timeout count | Request nghẽn trước khi gửi |
| Connection | created/closed rate, age, reset | Phát hiện churn và stale socket |
| Latency | p50, p95, p99 end-to-end và dependency | Đo trải nghiệm thực |
| Transport | connect errors, TLS errors, GOAWAY | Phân biệt lỗi mạng/protocol |
| Concurrency | current in-flight, rejected count | Xem limiter có thực sự bảo vệ |
| Retry | attempts/original request | Phát hiện khuếch đại traffic |
| Downstream | CPU, DB pool, queue, saturation | Không tăng pool khi backend quá tải |
| Network | backend skew, DNS changes, LB drains | Phát hiện route bất thường |

Mỗi thư viện có cách xuất metrics khác nhau. Reactor Netty, Apache HttpClient, gRPC và service mesh có điểm đo riêng. Không giả định mọi client có sẵn mọi chỉ số. Tránh nhãn metrics có cardinality cao như requestId, sku động, full URL, token hoặc user ID.

### 22.1. Diễn giải triệu chứng

- Active đạt max, pending tăng, server response nhanh: kiểm tra pool sizing, response leak hoặc traffic burst.
- Active cao, server p99/CPU/DB pool cũng cao: downstream đang quá tải; tăng pool có thể làm tệ hơn.
- Connection created/closed rate tăng cao: kiểm tra client lifecycle, idle timeout hoặc proxy reset.
- Reset chủ yếu sau idle lâu: kiểm tra stale connection và LB/NAT idle timeouts.
- Socket count thấp nhưng HTTP/2 stream queue tăng: kiểm tra stream/concurrency limits.
- Retry requests tăng nhanh hơn original RPS: kiểm tra retry storm và retry ở nhiều tầng.
- Chỉ một vài pods bị lỗi: kiểm tra DNS, backend skew, network local và rollout.

## 23. Kiểm thử và fault injection

### 23.1. Kiểm tra client reuse

Gửi nhiều request tuần tự và đồng thời bằng một client, đo connection creation và reuse. Kiểm tra cả request đầu tiên, request sau idle, lúc backend restart và lúc rolling deploy.

### 23.2. Kiểm tra saturation

Tạo burst vượt max active và pending queue. Xác minh limiter không vượt ngưỡng đã cấu hình, pending không vô hạn, acquire timeout xảy ra đúng và hệ phục hồi khi tải giảm. Thử thay đổi số pods để kiểm tra giới hạn cấp cụm.

### 23.3. Kiểm tra leaks

Mô phỏng streaming body, cancel giữa chừng, deserialization lỗi và exception trong callback. Đo active/idle/pending, file descriptors và connection age. Xác minh cleanup sau khi có lỗi.

### 23.4. Kiểm tra deadline

Mô phỏng connect chậm, TLS handshake chậm, server không trả headers, body đọc chậm, pool acquisition bị nghẽn. Xác minh overall deadline được tôn trọng và retry không tiếp tục sau khi hết ngân sách.

### 23.5. Kiểm tra side effects

Mô phỏng server đã commit reservation hoặc payment nhưng response bị mất. Client retry cùng idempotency key không được tạo giao dịch thứ hai. Kiểm tra trạng thái UNKNOWN/PENDING và reconciliation.

### 23.6. Bằng chứng

Lưu topology thử nghiệm, mức tải, số instances, số connections, p95/p99 latency, pool pending, error/retry count, downstream saturation và thời gian phục hồi. Fault injection phải thực hiện trong môi trường được phép và bảo vệ dữ liệu nghiệp vụ.

## 24. Tình huống mẫu: Inventory chậm trong flash sale

Giả sử Order có 20 pods, mỗi pod sử dụng pool tới Inventory, bình thường xử lý 500 RPS toàn cụm. Khi flash sale, requests tăng nhanh và Inventory database chậm từ 100 ms lên 1,5 giây.

**Cách phản ứng nguy hiểm:** tăng max connections gấp mười lần, pending queue vô hạn và retry mọi timeout. Kết quả có thể là Inventory nhận nhiều calls hơn công suất, Order cạn bộ nhớ/threads và hệ khó phục hồi.

**Cách phản ứng được kiểm soát:**

1. Giới hạn in-flight theo capacity Inventory và số Order pods.
2. Pending queue và acquire timeout hữu hạn.
3. Deadline từ Gateway tới các hop; không retry vượt ngân sách.
4. Phân biệt thao tác GET có thể chịu degraded read và lệnh reserve phải giữ invariant.
5. Reservation retry theo idempotency key, trạng thái chưa rõ được truy vấn/đối soát.
6. Bulkhead riêng cho Payment để lỗi Inventory không chiếm mọi resource.
7. Dashboard hiển thị active/idle/pending, retry budget và thời gian phục hồi.
8. Có load shedding khi không đủ công suất; trả lỗi/đang chờ chính xác theo contract.

Mục tiêu không phải biến mọi request thành thành công giả khi quá tải, mà là bảo vệ tính đúng đắn và giúp hệ thống suy giảm, phục hồi có kiểm soát.

## 25. Sai lầm thường gặp

### Sai lầm 1 — Khởi tạo client/channel cho mỗi request

Làm giảm reuse và tăng connection churn. Tạo transport ở scope ứng dụng hoặc scope dài phù hợp.

### Sai lầm 2 — Mở pool không giới hạn

Không tăng công suất backend; có thể làm cạn socket, file descriptors và CPU ở cả hai phía.

### Sai lầm 3 — Chỉ đặt connect timeout

Không bảo vệ pool acquisition, chờ response, đọc body hay retry. Cần deadline tổng.

### Sai lầm 4 — Không đóng response body/stream

Giữ connection và gây pool exhaustion. Dùng resource cleanup đúng theo client API.

### Sai lầm 5 — Một shared pool cho mọi upstream nhưng không có bulkhead

Một dependency chậm có thể chiếm hết concurrency, khiến dependency quan trọng khác bị ảnh hưởng.

### Sai lầm 6 — Tăng connection count vì thấy HTTP/2 chỉ dùng một socket

Một connection có thể multiplex nhiều streams. Phải quan sát stream limits và in-flight, không chỉ socket.

### Sai lầm 7 — Bỏ qua LB, DNS và rollout

Long-lived connections có thể bám backend cũ; cần idle/max age và draining phù hợp.

### Sai lầm 8 — Retry mọi POST sau timeout

Server có thể đã commit; yêu cầu phải có idempotency key hoặc trạng thái chưa chắc chắn.

### Sai lầm 9 — Mỗi tenant một pool không giới hạn

Số pool và connections có thể tăng theo tenant count. Nếu cần cách ly, phải có capacity và eviction policy.

### Sai lầm 10 — Chỉ test khi backend khỏe

Sự cố pool thường xuất hiện khi downstream chậm, mạng reset hoặc lúc deploy. Cần thử các trường hợp này.

## 26. Checklist thiết kế

1. Client/channel được tạo ở đâu và đóng lúc nào?
2. Protocol thực tế từng hop là HTTP/1.1, HTTP/2 hay gRPC?
3. Pool max là theo host, route hay toàn manager?
4. Có concurrency limiter độc lập với connection count không?
5. Pending queue và acquire timeout có giới hạn không?
6. Connect, TLS, response timeout và overall deadline đã được phân biệt chưa?
7. Retry policy có idempotency, attempts và total budget rõ không?
8. Có xét số pods, autoscaling và năng lực backend không?
9. Response body và streaming resource được close/cancel đúng chưa?
10. LB/NAT idle timeout, DNS refresh và graceful draining được kiểm thử chưa?
11. TLS/mTLS và per-request identity có được xử lý an toàn không?
12. Metrics active/idle/pending, acquire latency và retries có sẵn không?
13. Có test burst, backend chậm và response mất sau commit không?
14. Khi không phục vụ được, API trả trạng thái nào cho người dùng?
15. Có kế hoạch phục hồi/rollback khi thay cấu hình pool không?

## 27. Câu hỏi tự kiểm tra

1. Tại sao tái sử dụng HttpClient giúp giảm connection churn?
2. Connection pool và concurrency limiter khác nhau thế nào?
3. Khi dùng HTTP/2, một connection có thể phục vụ bao nhiêu request, và giới hạn ở đâu?
4. Vì sao gRPC ManagedChannel nên có vòng đời dài?
5. Active connections đạt max, pending tăng: ba nguyên nhân khả dĩ là gì?
6. Response stream không được close ảnh hưởng pool thế nào?
7. Với 400 RPS và mean duration 150 ms, in-flight trung bình xấp xỉ bao nhiêu?
8. Nếu mỗi pod max 100 calls và có 30 pods, tải tối đa theo lý thuyết tới downstream là bao nhiêu?
9. Vì sao connect timeout không thể thay thế end-to-end deadline?
10. Vì sao timeout của payment không chứng minh thanh toán thất bại?
11. Khi dùng L4 LB, một HTTP/2 connection dài hạn có thể gây lệch tải ra sao?
12. Connection idle và connection maximum lifetime giải quyết những vấn đề nào?
13. Virtual threads có loại bỏ nhu cầu giới hạn connections và downstream load không?
14. Nếu Inventory chậm gấp mười lần, tăng maxConnections có thể phản tác dụng như thế nào?
15. Những metrics nào giúp phân biệt connection leak với backend thật sự quá tải?

## 28. Tóm tắt

- **Tái sử dụng client/channel có vòng đời dài**, không tạo transport mới cho từng request.
- **Connection reuse giúp giảm TCP/TLS overhead**, nhưng kết nối có thể bị đóng bởi LB, NAT, server hoặc rollout.
- **HTTP/1.1 và HTTP/2 có cách sử dụng connections khác nhau**; giới hạn sockets không đồng nghĩa giới hạn requests.
- **Pool và concurrency phải được giới hạn có căn cứ**, dựa trên throughput, latency, số pods và công suất downstream.
- **Pending acquisition phải hữu hạn** và không chờ quá deadline còn lại.
- **Timeout được đặt theo giai đoạn và overall deadline**, không mở ngân sách mới cho mỗi retry.
- **Retry phải an toàn theo ngữ nghĩa**, dùng idempotency key và reconciliation cho side effects.
- **Theo dõi active/idle/pending, churn, retry và downstream saturation** để tìm đúng bottleneck.
- **Kiểm thử khi lỗi mạng, backend chậm và trong deployment**, không chỉ lúc đường truyền khỏe.
- **Không dùng connection pool để che một chuỗi gọi đồng bộ quá dài** hoặc để giữ transaction trong khi đợi mạng.

Câu hỏi cuối cùng: **khi Inventory đột ngột chậm gấp mười lần, Order có giới hạn số lời gọi, biết hết deadline, giải phóng kết nối đúng và tự phục hồi mà không khuếch đại lỗi thành retry storm hay không?** Một thiết kế tốt trả lời bằng cấu hình, số đo và bài test cụ thể.
