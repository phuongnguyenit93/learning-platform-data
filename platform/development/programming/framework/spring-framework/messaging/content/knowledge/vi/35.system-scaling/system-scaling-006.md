# Quản lý số kết nối RSocket và chia tải theo mô hình ứng dụng

RSocket hỗ trợ nhiều request đồng thời trên cùng một connection. Vì vậy, số request không đồng nghĩa với số TCP connection: một RSocketRequester có thể gửi nhiều Request-Response, Request-Stream, Request-Channel và Fire-and-Forget đồng thời qua một kết nối đã thiết lập. Tạo một requester hoặc một TCP connection cho mỗi request thường làm tăng chi phí handshake, socket, keepalive và bộ nhớ mà không tạo thêm năng lực xử lý tương ứng.

Khi hệ thống mở rộng, cần chọn mô hình kết nối theo cách ứng dụng giao tiếp: một client gắn với một backend, nhiều client được phân phối qua load balancer ở tầng mạng, một client phân phối từng request qua nhiều backend, hay một phiên RSocket phải gắn với đúng một instance. Mỗi mô hình có cách quản lý connection, trạng thái và retry khác nhau.

Bài học tập trung vào Spring Framework RSocketRequester và RSocket Java load balancing. Các ví dụ dùng Java 17, Spring Framework 7.0.8 và RSocket Java 1.1.5.

## 1. Connection, request và stream là ba khái niệm khác nhau

Một RSocket connection được tạo trên TCP, WebSocket hoặc transport khác. Sau SETUP, hai phía có thể khởi tạo các interaction trên cùng kết nối. RSocket multiplex nhiều stream trên một transport connection, mỗi stream có stream ID và vòng đời riêng.

- Connection là kênh truyền vật lý/logical giữa hai RSocket endpoint. Nó có handshake, keepalive, trạng thái setup, metadata MIME type và trạng thái đóng.
- Request là một interaction như Request-Response hoặc Fire-and-Forget. Request có thể tạo một stream trên connection.
- Stream là luồng dữ liệu của Request-Stream hoặc Request-Channel. Nhiều stream có thể hoạt động đồng thời trên một connection; backpressure được áp dụng theo từng stream.

Vì thế, nếu một service có 2.000 request đang chờ, không có nghĩa ứng dụng cần 2.000 TCP connections. Một connection RSocket có thể mang nhiều interaction đồng thời. Giới hạn thực tế phụ thuộc CPU, network, số stream đang hoạt động, buffer, kích thước payload, latency và năng lực xử lý của server.

Sơ đồ:

~~~text
Client process
  |
  +-- RSocketRequester (service A)
  |      |
  |      +-- one shared RSocket connection
  |              +-- request-response stream 1
  |              +-- request-response stream 2
  |              +-- request-stream 3
  |              +-- request-channel 4
  |
  +-- RSocketRequester (service B)
         |
         +-- another shared RSocket connection
~~~

Một RSocketRequester là abstraction gửi request. Nó không tương đương một request riêng lẻ và cũng không nên được tạo mới trong mỗi lần gọi API.

## 2. Mặc định: một requester dùng chung một connection

Với một endpoint cố định, Spring cung cấp cách tạo requester đơn giản:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .tcp("orders.internal", 7000);
~~~

Hoặc dùng WebSocket:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .websocket(URI.create("wss://orders.example.com/rsocket"));
~~~

Hai cách này tạo RSocketRequester dùng chung một connection cho các request đồng thời. Kết nối được thiết lập lazy khi có request đầu tiên; khi connection bị mất, các request tiếp theo có thể kích hoạt việc thiết lập lại connection. Điều này không có nghĩa stream đang chạy được chuyển nguyên vẹn sang connection mới. Stream đang hoạt động có thể nhận lỗi khi connection cũ bị đóng.

Trong một ứng dụng Spring Boot, có thể tạo requester một lần rồi inject vào service:

~~~java
@Configuration
class RSocketClientConfig {

    @Bean
    RSocketRequester ordersRequester(RSocketRequester.Builder builder) {
        return builder.tcp("orders.internal", 7000);
    }
}

@Service
class OrdersClient {
    private final RSocketRequester requester;

    OrdersClient(RSocketRequester ordersRequester) {
        this.requester = ordersRequester;
    }

    Mono<OrderReply> find(String orderId) {
        return requester.route("orders.find")
                .data(orderId)
                .retrieveMono(OrderReply.class);
    }
}
~~~

Không tạo requester bên trong mỗi lần gọi find(). Việc tái sử dụng requester giúp nhiều request dùng chung connection và giữ ổn định cấu hình codec, MIME type, setup metadata và connector.

RSocketRequester.Builder là builder có trạng thái. Khi dùng Spring Boot, bean Builder được tạo theo prototype để mỗi nơi inject có một builder riêng. Hãy cấu hình builder rồi tạo requester cho từng remote service hoặc từng chính sách kết nối; không dùng chung một builder rồi thay setup/metadata liên tục giữa các requester khác nhau.

Khi ứng dụng sở hữu requester, cần dispose khi ứng dụng dừng hoặc khi thành phần sở hữu requester bị hủy. Không dispose sau mỗi request vì các request khác có thể vẫn đang dùng connection.

## 3. Khi nào cần nhiều connection?

Nhiều connection hữu ích khi một connection đơn trở thành nút thắt đã được đo đạc, khi cần cách ly workload hoặc khi cần phân phối request tới nhiều backend. Chúng cũng làm tăng chi phí vận hành.

Mỗi connection thường giữ trạng thái ở cả client và server: socket/file descriptor, buffer, keepalive, event-loop registration, protocol state và session context. Nếu dùng TLS hoặc connection-level authentication, còn có chi phí handshake và trạng thái bảo mật. Quá nhiều connection có thể làm tăng memory, CPU, số file descriptor và số heartbeat.

Một số mô hình phổ biến:

| Mô hình ứng dụng | Cách kết nối thường phù hợp | Lý do |
|---|---|---|
| Một service client gọi một backend cố định | Một requester dùng chung một connection | Multiplex nhiều request, ít overhead |
| Nhiều client độc lập gọi một cluster | Mỗi client một connection qua TCP/L4 load balancer | Backend được phân phối lúc connection được tạo; client không phải nối tới mọi node |
| Một client cần phân phối request giữa nhiều instance | Client-side load balancing với nhiều target | Chọn một RSocket trong pool cho từng interaction |
| Client cần giữ session gắn với backend | Một connection có affinity hoặc routing theo session | Tránh gửi request session tới instance khác |
| Workload stream dài và request ngắn cạnh tranh | Tách requester/pool theo workload khi có bằng chứng nghẽn | Cách ly latency và tài nguyên |
| Server cần gửi request ngược về một client đã kết nối | Giữ requester gắn với đúng connection của client đó | Connection là định danh phiên giao tiếp |

Không có một số connection tối ưu chung cho mọi hệ thống. Bắt đầu bằng một connection dùng chung, đo latency, throughput, số stream pending, CPU và network; chỉ tăng connection khi có bằng chứng một connection là giới hạn.

## 4. Ước tính connection count theo topology

Hãy tính số connection từ số process/client và mô hình phân phối:

- Với một requester cố định trên mỗi client process, connection count gần với số client process đang hoạt động, cộng các kết nối quản trị/health riêng nếu có.
- Với client-side load balancing, một requester có pool các RSocket tới nhiều target. Khi số target tăng, số connection được duy trì bởi mỗi client cũng có thể tăng theo số target đang hoạt động.
- Với N client process và M backend target, không nên mặc định rằng mô hình client-side pool chỉ tạo N connection. Hãy lập capacity estimate theo pool thực tế; trường hợp mỗi client giữ connection tới mọi target có thể tiến gần N × M.
- Với L4 load balancer hoặc service VIP, mỗi client có thể chỉ giữ một connection tại một thời điểm; load balancer phân phối các connection khác nhau tới backend khác nhau.

Ví dụ minh họa: 20.000 client, mỗi client một connection qua L4 LB tạo khoảng 20.000 kết nối client-side tới cluster. Nếu mỗi client giữ một connection tới 8 backend trong client-side pool, quy mô có thể tiến gần 160.000 kết nối. Đây là ví dụ tính toán topology, không phải số đo của một triển khai cụ thể.

Spring RSocketRequester.Builder không cung cấp thuộc tính maxConnections kiểu generic pool size. Phương thức transports() dùng LoadbalanceRSocketClient và danh sách LoadbalanceTarget để quản lý các RSocket target. Builder của LoadbalanceRSocketClient cho phép cấu hình connector và strategy; nếu yêu cầu là một số lượng cố định nhiều TCP connections tới cùng một host, cần thiết kế pool/client riêng hoặc nhiều requester có chủ đích, rồi đo và quản lý vòng đời từng kết nối.

## 5. Phân biệt load balancing ở tầng mạng và client-side

### 5.1. Load balancing ở tầng mạng

Một client kết nối tới hostname hoặc VIP của service:

~~~text
Client
  |
  | one TCP/WebSocket connection
  v
L4 load balancer / service VIP
  |
  +---- backend A
  +---- backend B
  +---- backend C
~~~

Load balancer thường chọn backend khi thiết lập TCP connection. Vì RSocket multiplex nhiều request stream trên cùng connection, các request trên connection đó thường tiếp tục đi tới cùng backend. Đây là phân phối theo connection, không phải tự động phân phối từng request.

Mô hình này phù hợp với số lượng client rất lớn, mỗi client duy trì một session hoặc connection ổn định. Load balancer chia số connection giữa các instance. Nếu ứng dụng yêu cầu affinity theo connection, hãy giữ cấu hình stickiness tương ứng.

### 5.2. Client-side load balancing

Spring có API để một RSocketRequester lựa chọn từ nhiều target:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .transports(targetPublisher, new RoundRobinLoadbalanceStrategy());
~~~

targetPublisher phát ra danh sách LoadbalanceTarget. Mỗi target có một key nhận diện duy nhất và một ClientTransport. LoadbalanceRSocketClient duy trì pool RSocket và dùng LoadbalanceStrategy để chọn RSocket phục vụ interaction.

RoundRobinLoadbalanceStrategy chọn lần lượt các RSocket trong pool. WeightedLoadbalanceStrategy chọn dựa trên availability và thống kê sử dụng/độ trễ của RSocket. Chiến lược weighted không đơn giản là đọc CPU của pod; nó dùng trạng thái availability và usage của các connection mà client quan sát được.

Với Request-Response, mỗi interaction được gửi qua RSocket được chọn. Với Request-Stream hoặc Request-Channel, toàn bộ stream đã tạo gắn với RSocket được chọn cho interaction đó; các item trong stream không được phân phối lại giữa các backend.

## 6. Tạo danh sách target tĩnh

Ví dụ có hai backend TCP:

~~~java
List<LoadbalanceTarget> targets = List.of(
        LoadbalanceTarget.from(
                "orders-a",
                TcpClientTransport.create("orders-a.internal", 7000)),
        LoadbalanceTarget.from(
                "orders-b",
                TcpClientTransport.create("orders-b.internal", 7000))
);

RSocketRequester requester = RSocketRequester.builder()
        .transports(Flux.just(targets), new RoundRobinLoadbalanceStrategy());
~~~

Cần có dependency rsocket-transport-netty để sử dụng TcpClientTransport. Key của mỗi LoadbalanceTarget phải xác định duy nhất target. Nếu DNS/IP/port của một instance thay đổi, hãy cập nhật danh sách target theo định danh instance mới phù hợp với service discovery.

Dùng Flux.just(targets) khi topology tĩnh trong suốt vòng đời requester. Với cluster thay đổi theo autoscaling, rolling deployment hoặc discovery, cần một Publisher phát ra các snapshot mới.

## 7. Cập nhật target từ service discovery

RSocketRequester.Builder.transports nhận Publisher<List<LoadbalanceTarget>>; danh sách có thể được cập nhật định kỳ. Đây là điểm nối với Eureka, Consul, Kubernetes hoặc discovery service khác.

Ví dụ minh họa với ReactiveDiscoveryClient và TCP transport:

~~~java
Flux<List<LoadbalanceTarget>> targetUpdates =
        Flux.interval(Duration.ZERO, Duration.ofSeconds(5))
                .concatMap(tick -> discoveryClient.getInstances("orders")
                        .map(instance -> LoadbalanceTarget.from(
                                instance.getHost() + ":" + instance.getPort(),
                                TcpClientTransport.create(
                                        instance.getHost(), instance.getPort())))
                        .collectList()
                        .onErrorResume(error -> {
                            log.warn("Could not refresh RSocket targets", error);
                            return Mono.empty();
                        }));

RSocketRequester requester = builder
        .transports(targetUpdates, WeightedLoadbalanceStrategy.create());
~~~

Đoạn code là mẫu tích hợp; cần có Spring Cloud Discovery và rsocket-transport-netty. Khi discovery thành công nhưng không có instance, collectList() phát danh sách rỗng. Khi discovery lỗi, Mono.empty() giữ cho publisher cập nhật còn sống và không thay thế snapshot hiện tại bằng một danh sách lỗi. Tùy yêu cầu vận hành, có thể chọn chính sách fail fast nếu không còn target nào.

Publisher cho topology động phải tiếp tục sống và phát snapshot mới. Nếu chỉ dùng Flux.just(initialTargets) rồi publisher hoàn tất, client sẽ không nhận được các bản cập nhật sau khi backend biến mất hoặc xuất hiện trở lại. Pool có thể cạn target nếu toàn bộ node bị loại khỏi danh sách và không còn bản cập nhật mới.

Cần phân biệt hai sự kiện:

- Backend tạm thời không phản hồi nhưng vẫn còn trong discovery.
- Backend đã bị loại khỏi discovery và target list mới không còn chứa nó.

Health check, discovery TTL và khoảng polling quyết định thời gian client phát hiện thay đổi. Poll quá thường xuyên tạo tải lên registry; poll quá chậm làm tăng thời gian tồn tại của target cũ. Nếu registry có watch/event stream, có thể dùng sự kiện thay vì polling.

## 8. Chọn Round Robin hay Weighted?

| Strategy | Cách chọn | Phù hợp khi |
|---|---|---|
| RoundRobinLoadbalanceStrategy | Luân phiên các RSocket trong pool | Backend tương đối đồng đều và muốn phân phối đơn giản |
| WeightedLoadbalanceStrategy | Dựa vào availability và usage statistics | Backend có năng lực hoặc độ trễ khác nhau, muốn tránh target đang bận |

Round robin không đảm bảo mỗi backend nhận cùng số byte hoặc cùng thời gian CPU. Một stream kéo dài 10 phút có thể tiêu thụ nhiều tài nguyên hơn hàng trăm request-response ngắn. Round robin chỉ là chiến lược chọn connection cho interaction, không phải thuật toán cân bằng chính xác theo chi phí nghiệp vụ.

Weighted strategy có thể sử dụng availability, số request pending và thống kê latency để chọn RSocket có trọng số phù hợp. Nếu server hỗ trợ leasing, availability có thể phản ánh khả năng tiếp nhận request. Không nên xem weighted strategy là thay thế cho autoscaling, quota hoặc admission control ở tầng nghiệp vụ.

Khi chọn strategy, đo phân phối request, latency p95/p99, số request pending và thời lượng stream theo target. Nếu backend giống nhau và workload đồng nhất, round robin thường dễ dự đoán. Nếu tải và latency khác nhau đáng kể, thử weighted rồi so sánh bằng benchmark.

## 9. Affinity và trạng thái theo connection

RSocket là giao thức hai chiều. Sau SETUP, hai phía có thể gửi request cho nhau. Server có thể giữ state theo connection hoặc dùng @ConnectMapping để xử lý SETUP và tạo session context. Trong trường hợp này, connection có thể đại diện cho một client session.

Nếu client-side load balancer chọn backend A cho request đầu tiên rồi backend B cho request tiếp theo, backend B có thể không có session state đã tạo ở A. Các trường hợp cần đặc biệt chú ý:

- Xác thực hoặc session metadata chỉ được xử lý ở SETUP.
- Server giữ subscription hoặc trạng thái client trong memory theo connection.
- Server gửi request ngược về client qua requester gắn với connection.
- Request cần đọc dữ liệu tạm thời chỉ tồn tại trên một backend.
- Stream dài cần giữ đúng producer/consumer state trong suốt vòng đời.

Nếu request cần affinity, dùng một requester/connection gắn với đúng backend hoặc dùng sticky routing. Nếu muốn load balance từng request, trạng thái nghiệp vụ cần nằm trong shared store hoặc được thiết kế stateless. Không dùng client-side pool nếu việc đổi backend làm mất ngữ cảnh của session.

Session resumption cũng không phải cơ chế load balancing. Resume cần trạng thái session phù hợp ở endpoint tiếp nhận; nó không tự động chuyển một session đang chạy sang bất kỳ backend mới nào trong cluster. Khi cần chuyển node, phải có chiến lược session/state riêng.

## 10. Connection lifecycle, keepalive và cleanup

Một connection có vòng đời gồm tạo transport, SETUP, request/stream, keepalive và close. Hãy xác định rõ component nào sở hữu requester và component nào chịu trách nhiệm dispose.

Các nguyên tắc:

- Tạo requester một lần cho mỗi remote service và chính sách kết nối.
- Không tạo requester mới trong mỗi lần gọi route().
- Không dispose requester khi một request riêng lẻ hoàn tất.
- Dispose requester khi application context hoặc component sở hữu nó dừng.
- Đặt keepalive interval và max lifetime phù hợp với network timeout và server policy.
- Theo dõi connection close và reconnect; stream đang chạy có thể lỗi khi connection bị đóng.
- Nếu dùng target publisher động, dừng publisher và requester cùng lúc khi application shutdown.
- Dùng timeout cho request và stream; không giữ connection hoặc stream vô hạn nếu nghiệp vụ không cần.

Spring cho phép cấu hình RSocketConnector thông qua callback rsocketConnector() trên Builder. Tại đó có thể tùy chỉnh keepalive, session resumption, interceptor và các option mức thấp. Dùng cấu hình nhất quán trên tất cả target trong một pool vì cùng connector template được dùng để kết nối các target.

## 11. Backpressure và Leasing không phải connection pool

Backpressure điều tiết tốc độ phát dữ liệu theo từng stream. Requester yêu cầu số phần tử qua request(n); responder phải tôn trọng demand. Điều này giúp stream consumer chậm không bị producer đẩy dữ liệu vô hạn, nhưng không giới hạn tổng số TCP connections của ứng dụng.

RSocket Leasing là extension cho phép một phía thông báo số request mà phía kia được phép khởi tạo trong một khoảng thời gian. Nó hữu ích cho admission control hoặc bảo vệ server khi quá tải. Leasing điều tiết số request được chấp nhận trên connection; nó không thay thế load balancing giữa các backend và không đặt giới hạn số connection ở client.

Có thể kết hợp:

- Load balancing chọn RSocket target cho interaction.
- Backpressure điều tiết tốc độ dữ liệu của stream.
- Leasing giới hạn request mới theo khả năng tiếp nhận của peer.
- Application-level rate limit/quota kiểm soát theo user, tenant hoặc nghiệp vụ.

Đừng tăng số connection chỉ để né lease hoặc backpressure. Hãy xác định server đang giới hạn vì tài nguyên, quota hay chính sách bảo vệ.

## 12. Retry và failover khi connection lỗi

Nếu connection bị mất, các interaction đang chạy trên connection đó có thể lỗi. Request mới có thể được gửi qua connection mới hoặc target khác tùy requester và pool. Việc một request bị lỗi không chứng minh server chưa xử lý nó: server có thể đã commit side effect nhưng response bị mất.

Retry cần theo hợp đồng nghiệp vụ:

- Request đọc thường có thể retry khi lỗi transient nếu timeout và load cho phép.
- Request ghi cần idempotency key hoặc operation ID để tránh ghi trùng.
- Fire-and-Forget không có business response; send hoàn tất không xác nhận handler đã xử lý xong.
- Stream đang chạy cần chính sách resume/restart rõ ràng; retry toàn stream có thể phát lại dữ liệu hoặc side effect.
- Dùng backoff, jitter, giới hạn số lần retry và circuit breaker phù hợp.
- Không retry lỗi validation, authentication hoặc lỗi nghiệp vụ không transient.

Ví dụ retry cho một thao tác đọc idempotent:

~~~java
Mono<Order> order = requester.route("orders.find")
        .data(orderId)
        .retrieveMono(Order.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
                .filter(this::isTransientTransportFailure));
~~~

Đoạn code chỉ minh họa retry cho một truy vấn đọc. isTransientTransportFailure là chính sách phân loại lỗi của ứng dụng; không retry mọi Throwable. Với thao tác ghi, truyền operation ID ổn định tới server và bảo đảm server xử lý idempotent trước khi bật retry.

## 13. Ví dụ Java 17: phân phối request qua hai target

Ví dụ sau tạo hai RSocket server trong LocalTransport, mỗi server trả về tên node riêng. Một RSocketRequester sử dụng transports() và RoundRobinLoadbalanceStrategy để phân phối 12 request. Test xác nhận cả hai target đều nhận được request.

### 13.1. Maven dependencies

POM tối thiểu để chạy test bằng Java 17:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>rsocket-load-balance-test</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <spring.version>7.0.8</spring.version>
    <rsocket.version>1.1.5</rsocket.version>
    <junit.version>5.12.2</junit.version>
    <reactor.version>3.8.7</reactor.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-messaging</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>io.rsocket</groupId>
      <artifactId>rsocket-core</artifactId>
      <version>${rsocket.version}</version>
    </dependency>
    <dependency>
      <groupId>io.rsocket</groupId>
      <artifactId>rsocket-transport-local</artifactId>
      <version>${rsocket.version}</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <version>${reactor.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>${junit.version}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.3</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 13.2. Test hoàn chỉnh

Lưu thành src/test/java/example/RSocketLoadBalanceTest.java:

~~~java
package example;

import java.time.Duration;
import java.util.List;

import io.rsocket.core.RSocketServer;
import io.rsocket.loadbalance.LoadbalanceTarget;
import io.rsocket.loadbalance.RoundRobinLoadbalanceStrategy;
import io.rsocket.transport.local.LocalClientTransport;
import io.rsocket.transport.local.LocalServerTransport;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RSocketLoadBalanceTest {

    static final class NodeA {
        @MessageMapping("node")
        public String node() {
            return "node-a";
        }
    }

    static final class NodeB {
        @MessageMapping("node")
        public String node() {
            return "node-b";
        }
    }

    private Disposable startServer(String name, Object handler) {
        RSocketStrategies strategies = RSocketStrategies.create();
        RSocketMessageHandler messageHandler = new RSocketMessageHandler();
        messageHandler.setRSocketStrategies(strategies);
        messageHandler.setHandlers(List.of(handler));
        messageHandler.afterPropertiesSet();

        return RSocketServer.create(messageHandler.responder())
                .bind(LocalServerTransport.create(name))
                .block(Duration.ofSeconds(5));
    }

    @Test
    void balancesRequestsAcrossTwoTargets() {
        String targetA = "load-balance-a";
        String targetB = "load-balance-b";
        Disposable serverA = startServer(targetA, new NodeA());
        Disposable serverB = startServer(targetB, new NodeB());

        RSocketRequester requester = RSocketRequester.builder()
                .transports(
                        Flux.just(List.of(
                                LoadbalanceTarget.from(targetA,
                                        LocalClientTransport.create(targetA)),
                                LoadbalanceTarget.from(targetB,
                                        LocalClientTransport.create(targetB)))),
                        new RoundRobinLoadbalanceStrategy());

        try {
            StepVerifier.create(Flux.range(0, 12)
                            .flatMap(index -> requester.route("node")
                                    .retrieveMono(String.class))
                            .collectList())
                    .assertNext(results -> {
                        assertEquals(12, results.size());
                        assertTrue(results.contains("node-a"));
                        assertTrue(results.contains("node-b"));
                    })
                    .expectComplete()
                    .verify(Duration.ofSeconds(10));
        }
        finally {
            requester.dispose();
            serverA.dispose();
            serverB.dispose();
        }
    }
}
~~~

Test sử dụng LocalTransport nên không mở TCP port. Nó vẫn đi qua RSocket protocol, RSocketRequester và RSocketMessageHandler thật. Bài test chứng minh client-side target selection hoạt động; nó không kiểm tra TCP load balancer, TLS hoặc service discovery.

Chạy:

~~~bash
mvn test
~~~

Kết quả Surefire:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
~~~

Trong môi trường thật, thay LocalClientTransport bằng TcpClientTransport hoặc WebsocketClientTransport và dùng danh sách target lấy từ discovery. Nên có thêm integration test cho việc target biến mất, target mới xuất hiện, connection đóng và retry.

## 14. Đo và điều chỉnh connection count

Trước khi tăng số connection, hãy thu thập baseline:

- Số connection đang hoạt động theo client instance và backend.
- Số stream/request pending trên mỗi connection.
- Request rate và bytes/sec theo backend.
- Latency p50/p95/p99 và tỷ lệ timeout/error.
- CPU, memory, direct memory, file descriptor và network throughput.
- Keepalive traffic và số lần reconnect.
- Số target trong pool và số lần target bị loại/được thêm lại.

Một quy trình tuning thực tế:

1. Chạy với một requester và một shared connection.
2. Tăng concurrency request trong khi giữ nguyên connection count.
3. Quan sát CPU, network, latency và số stream pending.
4. Nếu một connection đã bão hòa, thử tách workload hoặc thêm connection có kiểm soát.
5. Nếu cần phân phối qua nhiều backend, so sánh L4 load balancing với client-side transports().
6. Chạy tải có cả request ngắn và stream dài để thấy fairness.
7. Kiểm tra khi backend restart, discovery thay đổi và network chập chờn.
8. Chọn số connection nhỏ nhất đáp ứng throughput và latency mục tiêu với headroom phù hợp.

Không dùng số request đồng thời làm lý do duy nhất để tăng connection. RSocket multiplexing và backpressure có thể xử lý nhiều stream trên một connection; bottleneck thực tế có thể là CPU handler, database, event loop hoặc downstream dependency.

## 15. Lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Tạo RSocketRequester trong mỗi request | Connection/handshake tăng, tốn socket và memory | Tái sử dụng requester theo remote service |
| Nghĩ một requester chỉ phục vụ một request | Tạo quá nhiều connection không cần thiết | Dùng shared connection và multiplexing |
| Dùng một VIP rồi kỳ vọng mỗi request tới backend khác | Nhiều stream trên một connection thường đi cùng backend | Dùng client-side transports() nếu cần phân phối từng interaction |
| Mỗi client nối tới mọi backend dù số client rất lớn | Connection count có thể tăng gần clients × targets | Dùng L4 LB hoặc gateway khi phù hợp |
| Dùng Flux.just() cho discovery động | Không có snapshot mới sau khi publisher hoàn tất | Dùng publisher cập nhật định kỳ hoặc watch stream |
| Target key không ổn định hoặc trùng | Pool khó nhận diện target thay đổi | Dùng instance ID hoặc endpoint key duy nhất |
| Dùng Round Robin cho stream rất dài rồi kỳ vọng byte cân bằng | Một stream lớn có thể giữ tải lâu trên một backend | Đo thời lượng/chi phí stream, cân nhắc weighted hoặc tách workload |
| Load balance request của session có state cục bộ | Request sau có thể tới node không có state | Sticky routing hoặc shared session state |
| Retry mọi request khi connection lỗi | Có thể thực hiện side effect nhiều lần | Idempotency key, retry có chọn lọc và backoff |
| Coi Leasing là connection pool | Nhầm giới hạn request với giới hạn socket | Dùng leasing cho admission control; quản lý connection riêng |
| Không dispose requester | Connection, timer và tài nguyên có thể còn sau shutdown | Quản lý ownership và dispose đúng vòng đời |

## 16. Checklist thiết kế

- Mỗi remote service có requester được tái sử dụng.
- Số connection được tính từ số client process và mô hình target pool.
- Đã xác định load balancing theo connection hay theo từng interaction.
- Nếu dùng client-side pool, target publisher cập nhật đúng khi discovery thay đổi.
- Target key là định danh ổn định và duy nhất.
- Chọn Round Robin hoặc Weighted theo workload và số liệu đo.
- Session/connection affinity được giữ khi ứng dụng phụ thuộc state theo connection.
- Backpressure, leasing và application rate limit được dùng đúng mục đích.
- Retry chỉ áp dụng cho lỗi transient và thao tác an toàn/idempotent.
- Connection count, active streams, pending requests, latency và reconnect được quan sát.
- Requester, pool và target publisher được dispose khi ứng dụng dừng.
- Có integration test cho phân phối target, target removal/addition và connection failure.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework API — RSocketRequester.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
- [RSocket Java API — LoadbalanceRSocketClient](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/LoadbalanceRSocketClient.html)
- [RSocket Java API — LoadbalanceTarget](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/LoadbalanceTarget.html)
- [RSocket Java API — RoundRobinLoadbalanceStrategy](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/RoundRobinLoadbalanceStrategy.html)
- [RSocket Java API — WeightedLoadbalanceStrategy](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/WeightedLoadbalanceStrategy.html)
- [RSocket — Frequently Asked Questions](https://rsocket.io/about/faq/)
