# Connection pool, giới hạn kết nối và hàng đợi chờ trong Spring WebClient

WebClient thường chạy trên Reactor Netty và tái sử dụng các kết nối HTTP thông qua connection pool. Khi một request cần gửi đi, client mượn một kết nối đang rảnh từ pool. Nếu chưa có kết nối rảnh và pool đã đạt giới hạn, request phải chờ một kết nối được trả lại hoặc thất bại khi hàng đợi chờ đầy hay hết thời gian.

Cấu hình pool ảnh hưởng trực tiếp đến độ trễ, thông lượng và khả năng bảo vệ hệ thống khi tải tăng. Pool quá nhỏ có thể khiến nhiều request chờ và timeout. Pool quá lớn có thể tạo quá nhiều kết nối tới upstream, làm tăng socket, file descriptor, TLS handshake và tải lên dịch vụ từ xa. Hàng đợi không giới hạn có thể biến quá tải tức thời thành độ trễ kéo dài và tiêu thụ bộ nhớ.

Bài học thuộc nhóm **Kết nối và thời hạn**, tập trung vào ConnectionProvider của Reactor Netty, giới hạn số kết nối, pending acquire queue, các loại timeout, vòng đời kết nối, metrics và cách chọn cấu hình phù hợp cho WebClient.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích connection pool giúp tái sử dụng TCP connection như thế nào.
- Phân biệt WebClient, ReactorClientHttpConnector, HttpClient và ConnectionProvider.
- Cấu hình maxConnections cho pool.
- Giới hạn số request chờ bằng pendingAcquireMaxCount.
- Đặt pendingAcquireTimeout để giới hạn thời gian chờ lấy connection.
- Phân biệt acquire timeout, connect timeout, response timeout và timeout tổng.
- Dùng maxIdleTime, maxLifeTime và eviction để quản lý kết nối cũ.
- Hiểu sự khác nhau giữa HTTP/1.1 và HTTP/2 khi tính concurrency.
- Theo dõi active, idle, pending và tổng số connection bằng metrics.
- Ước lượng kích thước pool dựa trên tốc độ request và thời gian xử lý.
- Quản lý lifecycle của ConnectionProvider và tài nguyên dùng chung.
- Kiểm thử giới hạn connection và pending queue bằng MockWebServer.

## 2. Connection pool giải quyết vấn đề gì?

Thiết lập TCP connection có chi phí: DNS lookup, TCP handshake, TLS handshake nếu dùng HTTPS, thương lượng giao thức và các bước khởi tạo khác. Nếu mỗi HTTP request tạo một connection mới, ứng dụng phải trả chi phí này lặp lại và tạo nhiều socket ngắn hạn.

Connection pool giữ lại các connection có thể tái sử dụng. Khi một request hoàn tất, connection thường được trả về pool để request khác dùng tiếp, miễn là connection còn hợp lệ và giao thức cho phép.

~~~text
Request A ----+
Request B ----+----> Connection pool ----> HTTP upstream
Request C ----+         |
                         +-- active connection
                         +-- idle connection
                         +-- pending acquire queue
~~~

Các trạng thái cần phân biệt:

- **Active connection:** đang được sử dụng cho một hoặc nhiều exchange/stream.
- **Idle connection:** đã được trả về pool và có thể được cấp cho request khác.
- **Pending acquire:** request đang chờ được cấp một connection.
- **Total connection:** tổng connection đang được quản lý bởi pool, thường gồm active và idle.
- **Maximum connection:** giới hạn connection mà pool được phép tạo cho một remote destination.

Với HTTP/1.1 thông thường, một connection thường phục vụ một request-response exchange tại một thời điểm. Với HTTP/2, một connection có thể multiplex nhiều stream đồng thời, nên số connection không bằng số request đang chạy.

## 3. Các thành phần trong WebClient connection stack

Trong ứng dụng WebFlux dùng Reactor Netty, các thành phần thường được kết nối như sau:

~~~text
Application service
       |
       v
WebClient
       |
       v
ReactorClientHttpConnector
       |
       v
Reactor Netty HttpClient
       |
       v
ConnectionProvider
       |
       v
TCP / TLS connection pool
       |
       v
Remote HTTP service
~~~

Vai trò từng thành phần:

- **WebClient:** API cấp cao để tạo request, khai báo headers/body và giải mã response.
- **ReactorClientHttpConnector:** adapter nối WebClient với một HTTP client cụ thể.
- **HttpClient:** cấu hình transport của Reactor Netty, như connect timeout, response timeout, proxy và các tùy chọn TCP.
- **ConnectionProvider:** quản lý pool, số connection tối đa, pending queue, thời gian chờ lấy connection, idle/lifetime và metrics.
- **Remote service:** upstream mà client gọi tới.

Không phải mọi WebClient đều bắt buộc dùng Reactor Netty. WebClient có thể dùng connector khác. Các cấu hình ConnectionProvider trong bài này áp dụng cho Reactor Netty; nếu ứng dụng dùng Jetty hoặc connector khác, hãy dùng cơ chế pool tương ứng.

## 4. maxConnections: giới hạn số connection

Với Reactor Netty, tạo ConnectionProvider bằng builder:

~~~java
ConnectionProvider provider = ConnectionProvider.builder("catalog-pool")
    .maxConnections(50)
    .build();
~~~

maxConnections đặt giới hạn số connection trong pool cho một remote destination. Pool được quản lý theo địa chỉ remote; khi một WebClient gọi nhiều host khác nhau, mỗi destination có thể có pool riêng theo cách ConnectionProvider quản lý.

Ví dụ:

- maxConnections = 1: tối đa một connection cho destination.
- maxConnections = 20: tối đa hai mươi connection cho destination.
- maxConnections = 100: có thể duy trì tối đa một trăm connection cho destination, nếu tải và pool cần đến mức đó.

Đừng chọn con số lớn chỉ để loại bỏ pending queue. Số connection phải phù hợp với năng lực của upstream, giới hạn socket của máy, số instance ứng dụng và số request thực sự đồng thời.

### maxConnections không phải giới hạn request toàn ứng dụng

Nếu một ứng dụng có ba WebClient dùng ba ConnectionProvider khác nhau, mỗi pool có thể có giới hạn riêng. Nếu chúng cùng dùng một provider và cùng destination, chúng có thể chia sẻ pool tương ứng.

Một service có nhiều instance cũng cần tính tổng tải:

~~~text
Số instance ứng dụng × maxConnections mỗi instance
    = giới hạn connection tiềm năng tới upstream
~~~

Ví dụ 8 instance, mỗi instance có pool tối đa 40 connection, có thể tạo ra tới 320 connection tới cùng upstream. Upstream phải đủ khả năng phục vụ tổng số này.

## 5. pendingAcquireMaxCount: giới hạn hàng đợi chờ

Khi tất cả connection đã bận, request mới có thể được đưa vào hàng đợi chờ cấp connection. Reactor Netty cho phép giới hạn số request đang chờ bằng pendingAcquireMaxCount.

~~~java
ConnectionProvider provider = ConnectionProvider.builder("catalog-pool")
    .maxConnections(50)
    .pendingAcquireMaxCount(100)
    .build();
~~~

Ý nghĩa:

- **0:** không cho request xếp hàng chờ khi không có connection khả dụng; request không thể lấy connection sẽ bị từ chối.
- **Số dương:** tối đa số request đó được chờ cấp connection.
- **-1:** hàng đợi không giới hạn; cần thận trọng vì tải tăng có thể tạo queue rất dài.

Ví dụ maxConnections = 2 và pendingAcquireMaxCount = 3:

~~~text
Connection #1: Request A đang dùng
Connection #2: Request B đang dùng

Pending queue:
  1. Request C
  2. Request D
  3. Request E

Request F:
  Bị từ chối vì hàng đợi đã đầy
~~~

Pending queue là nơi request chờ được cấp connection, không phải nơi lưu body hoặc response. Request vẫn chịu timeout và cancellation. Nếu queue đầy, Reactor Netty có thể phát lỗi kiểu PoolAcquirePendingLimitException.

### Vì sao không nên dùng queue vô hạn?

Một queue dài có thể che giấu việc upstream không đủ năng lực. Request vẫn nằm trong bộ nhớ, thời gian phản hồi tăng và nhiều request có thể hết hạn trước khi được xử lý.

Queue vô hạn thường làm tình trạng quá tải kéo dài hơn:

1. Tải tăng vượt năng lực upstream.
2. Request chờ tích lũy trong pending queue.
3. Thời gian chờ tăng.
4. Client timeout và retry.
5. Retry tạo thêm request mới.
6. Hệ thống chịu thêm tải khi đang quá tải.

Hãy chọn queue hữu hạn, timeout rõ ràng và chính sách backpressure/rejection phù hợp. Queue chỉ hấp thụ burst ngắn, không thể sửa một hệ thống có tải trung bình vượt công suất.

## 6. pendingAcquireTimeout: thời gian chờ lấy connection

pendingAcquireTimeout giới hạn thời gian một request có thể chờ trong pending queue để được cấp connection.

~~~java
ConnectionProvider provider = ConnectionProvider.builder("catalog-pool")
    .maxConnections(50)
    .pendingAcquireMaxCount(100)
    .pendingAcquireTimeout(Duration.ofSeconds(2))
    .build();
~~~

Trong ví dụ, request chờ tối đa hai giây để lấy connection. Nếu không có connection khả dụng trong thời gian đó, publisher phát lỗi acquire timeout, thường là PoolAcquireTimeoutException.

Hai giới hạn này giải quyết hai vấn đề khác nhau:

| Cấu hình | Giới hạn |
| --- | --- |
| maxConnections | Số connection được tạo/giữ trong pool |
| pendingAcquireMaxCount | Số request đang chờ cấp connection |
| pendingAcquireTimeout | Thời gian mỗi request được phép chờ cấp connection |

Một request có thể thất bại ngay vì queue đầy, hoặc chờ một thời gian rồi thất bại vì hết pendingAcquireTimeout.

### Queue không phải một timeout tổng

pendingAcquireTimeout chỉ đo thời gian chờ lấy connection. Sau khi đã có connection, request còn có thể mất thời gian kết nối, gửi request, chờ response và đọc body. Vì thế cần cấu hình riêng các timeout khác.

## 7. Phân biệt các loại timeout

WebClient/Reactor Netty có nhiều timeout ở các giai đoạn khác nhau. Dùng nhầm timeout có thể khiến ứng dụng vẫn treo lâu hơn dự kiến hoặc hủy request quá sớm.

| Timeout | Bắt đầu áp dụng ở đâu? | Cấu hình thường dùng |
| --- | --- | --- |
| Pending acquire timeout | Chờ lấy connection từ pool | ConnectionProvider.pendingAcquireTimeout |
| Connect timeout | Thiết lập TCP connection mới | ChannelOption.CONNECT_TIMEOUT_MILLIS |
| TLS handshake timeout | Thương lượng TLS khi dùng HTTPS | HttpClient secure configuration |
| Response timeout | Khoảng thời gian chờ giữa các lần đọc dữ liệu network | HttpClient.responseTimeout |
| Read/write timeout | Đọc hoặc ghi network theo handler | Netty ReadTimeoutHandler/WriteTimeoutHandler |
| Overall operation timeout | Toàn bộ publisher của thao tác | Reactor Mono/Flux.timeout |

### Connect timeout

Connect timeout giới hạn thời gian thiết lập TCP connection mới. Nó không phải thời gian chờ lấy connection từ pool. Nếu pool có connection idle, request có thể không cần tạo TCP connection mới.

~~~java
HttpClient httpClient = HttpClient.create(provider)
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000);
~~~

Giá trị trong ví dụ là hai giây.

### Response timeout

responseTimeout của Reactor Netty đặt giới hạn thời gian giữa các lần đọc dữ liệu network. Nó hữu ích để phát hiện upstream ngừng gửi dữ liệu quá lâu. Nó không phải timeout tổng cho toàn bộ request.

~~~java
HttpClient httpClient = HttpClient.create(provider)
    .responseTimeout(Duration.ofSeconds(5));
~~~

Một stream dài có thể hoạt động lâu hơn năm giây nếu vẫn nhận dữ liệu đều đặn; ngược lại, một stream không phát dữ liệu trong khoảng thời gian cấu hình có thể timeout.

### Overall timeout

Nếu muốn giới hạn toàn bộ thao tác, có thể đặt timeout trên publisher:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(Product.class)
    .timeout(Duration.ofSeconds(8));
~~~

Timeout này áp dụng cho toàn bộ publisher từ lúc subscribe, gồm thời gian chờ pool, kết nối, response và decode theo pipeline. Hãy cân nhắc cách nó tương tác với các timeout ở tầng transport.

### Đừng đặt mọi timeout bằng cùng một con số một cách máy móc

Một cấu hình hợp lý thường có thứ tự ngân sách:

- Acquire timeout ngắn để không xếp hàng quá lâu.
- Connect timeout đủ cho network/TCP.
- Response timeout phù hợp với khoảng im lặng tối đa của upstream.
- Overall timeout lớn hơn tổng ngân sách các bước cần thiết, nhưng vẫn nằm trong deadline của request gọi.

Đối với stream dài, overall timeout có thể không phù hợp; hãy dùng idle timeout hoặc chính sách lifetime riêng theo giao thức.

## 8. maxIdleTime, maxLifeTime và eviction

Connection pool không nên tái sử dụng một connection mãi mãi. Connection có thể bị upstream đóng sau một thời gian idle, mạng thay đổi hoặc server áp dụng giới hạn tuổi thọ.

### maxIdleTime

Giới hạn thời gian một connection được phép nằm idle trong pool trước khi bị loại bỏ.

~~~java
.maxIdleTime(Duration.ofSeconds(20))
~~~

Đặt maxIdleTime nhỏ hơn hoặc bằng idle timeout của upstream/load balancer thường giúp giảm khả năng lấy phải connection đã bị peer đóng. Ví dụ, nếu upstream đóng connection idle sau 30 giây, pool có thể đặt maxIdleTime khoảng 20 giây để loại connection trước đó.

Đây là lựa chọn theo môi trường; cần kiểm tra timeout thực tế của upstream và proxy.

### maxLifeTime

Giới hạn tuổi thọ tối đa của một connection, kể cả khi connection vẫn hoạt động tốt.

~~~java
.maxLifeTime(Duration.ofMinutes(5))
~~~

maxLifeTime giúp luân chuyển connection để tránh giữ một connection quá lâu, đồng thời có thể giúp cân bằng lại giữa các node upstream khi DNS/load balancer thay đổi. Connection đang được sử dụng thường được xử lý theo lifecycle của pool; không nên giả định thay đổi này cắt ngang một response đang truyền.

### Eviction định kỳ

Có thể yêu cầu pool quét connection cũ theo chu kỳ:

~~~java
.evictInBackground(Duration.ofSeconds(30))
~~~

Eviction giúp dọn connection idle/expired theo lịch, thay vì chỉ kiểm tra khi request mới cần connection. Chọn chu kỳ phù hợp với quy mô pool và yêu cầu vận hành.

### Kết hợp các chính sách

~~~java
ConnectionProvider provider = ConnectionProvider.builder("catalog-pool")
    .maxConnections(50)
    .pendingAcquireMaxCount(100)
    .pendingAcquireTimeout(Duration.ofSeconds(2))
    .maxIdleTime(Duration.ofSeconds(20))
    .maxLifeTime(Duration.ofMinutes(5))
    .evictInBackground(Duration.ofSeconds(30))
    .build();
~~~

Đây là cấu hình minh họa. Các con số phải được đo và điều chỉnh theo latency, traffic, upstream keep-alive và giới hạn tài nguyên.

## 9. HTTP/1.1 và HTTP/2 ảnh hưởng đến pool như thế nào?

Với HTTP/1.1, một connection thông thường phục vụ một exchange tại một thời điểm. Khi request hoàn tất và connection được trả về pool, request khác mới có thể dùng lại connection đó.

Với HTTP/2, một TCP connection có thể mang nhiều stream đồng thời nhờ multiplexing. Do đó:

- Một connection HTTP/2 có thể phục vụ nhiều request đồng thời.
- maxConnections không còn tương đương số request đồng thời.
- Số stream đồng thời trên mỗi connection còn phụ thuộc giới hạn được thương lượng với peer và cấu hình client/server.
- Tăng số connection không nhất thiết tăng throughput nếu một connection HTTP/2 đã đủ stream capacity.

Hãy đo protocol đang được sử dụng. Không áp dụng công thức HTTP/1.1 một connection cho mỗi request vào HTTP/2.

## 10. Ước lượng kích thước pool bằng tải thực tế

Một cách ước lượng cơ bản là dùng định luật Little:

\[
L = \lambda \times W
\]

Trong đó:

- L là số request trung bình đang ở trong hệ thống.
- λ là tốc độ request đến, tính theo request/giây.
- W là thời gian xử lý trung bình, tính bằng giây.

Ví dụ:

- Upstream nhận 100 request/giây.
- Thời gian xử lý trung bình 0,2 giây.
- Số request đồng thời trung bình 100 × 0,2 = 20.

Con số 20 là mức concurrency trung bình theo giả định đơn giản, không phải maxConnections bắt buộc. Thực tế còn có burst, p95/p99 latency, HTTP/2 multiplexing, retry, thời gian giữ connection và giới hạn upstream.

### Quy trình chọn pool

1. Đo request rate và latency theo từng upstream.
2. Ước lượng concurrency trung bình bằng Little's Law.
3. Xem p95/p99 và burst để xác định headroom.
4. Kiểm tra giới hạn connection và request đồng thời mà upstream cho phép.
5. Tính tổng pool của tất cả instance ứng dụng.
6. Chọn maxConnections phù hợp với năng lực upstream.
7. Chọn pendingAcquireMaxCount nhỏ và hữu hạn để hấp thụ burst ngắn.
8. Chọn pendingAcquireTimeout theo deadline của request.
9. Đo active/pending/idle và error rate khi tải tăng.
10. Điều chỉnh dựa trên kết quả load test, không chỉ dựa trên một công thức.

### Ví dụ định hướng

Giả sử 4 instance, mỗi instance dự kiến có 25 request đồng thời trung bình tới upstream. Nếu mỗi instance đặt maxConnections = 40, tổng giới hạn connection tiềm năng là 160. Trước khi triển khai, phải xác nhận upstream có thể chấp nhận số connection này và có đủ năng lực xử lý request tương ứng.

Không nên đặt maxConnections cao hơn năng lực upstream chỉ để pending queue ít xuất hiện. Khi upstream quá tải, cần backpressure, rate limiting, circuit breaker hoặc từ chối sớm.

## 11. Theo dõi pool metrics

Reactor Netty có thể xuất metrics của connection provider. Bật metrics trên provider:

~~~java
ConnectionProvider provider = ConnectionProvider.builder("catalog-pool")
    .maxConnections(50)
    .pendingAcquireMaxCount(100)
    .metrics(true)
    .build();
~~~

Để tích hợp metrics với Micrometer trong Spring Boot, thêm dependency Spring Boot Actuator hoặc cấu hình registry phù hợp.

Các metric quan trọng thường có prefix reactor.netty.connection.provider:

| Metric | Ý nghĩa |
| --- | --- |
| total.connections | Tổng connection hiện có trong pool |
| active.connections | Connection đang hoạt động |
| idle.connections | Connection đang rảnh |
| pending.connections | Request đang chờ connection |
| pending.connections.time | Thời gian chờ cấp connection |
| max.connections | Giới hạn connection cấu hình |
| max.pending.connections | Giới hạn pending queue |

Tên metric có thể được gắn tag theo tên provider và remote address. Hãy kiểm tra tags khi truy vấn qua Micrometer/Actuator.

### Cách đọc dấu hiệu vận hành

- **active gần max liên tục, pending tăng:** pool có thể quá nhỏ so với tải hoặc upstream xử lý chậm.
- **pending tăng rồi giảm nhanh:** có thể là burst ngắn; kiểm tra latency và acquire wait.
- **pending tăng cùng acquire timeout:** request đang chờ lâu hơn ngân sách cho phép.
- **idle cao và active thấp:** pool có thể đang giữ nhiều connection hơn nhu cầu; xem xét maxIdleTime/maxConnections.
- **total connection liên tục tạo/đóng:** có thể có churn do idle/lifetime quá ngắn, upstream đóng connection hoặc cấu hình pool không phù hợp.
- **pool rejection tăng:** pending queue đã đầy hoặc không thể cấp connection; cần kiểm tra tải và upstream capacity.

Metrics nên được theo dõi theo từng upstream. Gộp tất cả host vào một biểu đồ có thể che giấu một dependency đang quá tải.

## 12. Quản lý lifecycle và chia sẻ ConnectionProvider

ConnectionProvider là tài nguyên có lifecycle. Trong ứng dụng Spring, nên tạo provider như một bean dùng chung cho WebClient tương ứng, thay vì tạo mới cho mỗi request.

Ví dụ:

~~~java
@Bean(destroyMethod = "dispose")
ConnectionProvider catalogConnectionProvider() {
    return ConnectionProvider.builder("catalog-pool")
        .maxConnections(50)
        .pendingAcquireMaxCount(100)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .build();
}
~~~

Spring gọi dispose khi application context đóng. Điều này giúp giải phóng pool trong quá trình shutdown.

### Không tạo pool cho mỗi request

Không làm như sau:

~~~java
public Mono<Product> getProduct(String id) {
    ConnectionProvider provider =
        ConnectionProvider.builder("temporary").build();

    HttpClient httpClient = HttpClient.create(provider);
    WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();

    return client.get()
        .uri("https://catalog.example/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class);
}
~~~

Đoạn code này tạo provider và client lặp lại cho mỗi lần gọi, làm mất lợi ích tái sử dụng connection, gây churn và khiến việc dispose khó kiểm soát.

Hãy tạo WebClient/ConnectionProvider ở cấu hình ứng dụng, rồi inject vào service.

### Tài nguyên global của Reactor Netty

Reactor Netty có thể dùng tài nguyên global dùng chung. Spring Boot thường tích hợp các resource dùng chung này để giảm chi phí tạo event loop và pool. Nếu tạo provider tùy chỉnh, phải quản lý lifecycle của chính provider đó; không tùy tiện dispose tài nguyên global mà client khác vẫn đang dùng.

## 13. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ dưới đây cấu hình một WebClient gọi Catalog API bằng Reactor Netty:

- maxConnections = 20.
- pendingAcquireMaxCount = 40.
- pendingAcquireTimeout = 1 giây.
- maxIdleTime = 20 giây.
- maxLifeTime = 5 phút.
- connect timeout = 2 giây.
- response timeout = 5 giây.
- metrics được bật.
- ConnectionProvider được dispose khi Spring context đóng.

### Cấu trúc project

~~~text
webclient-pool-demo/
├── pom.xml
└── src
    ├── main/java/com/example/pool
    │   ├── PoolDemoApplication.java
    │   ├── WebClientPoolConfiguration.java
    │   ├── Product.java
    │   └── CatalogClient.java
    └── test/java/com/example/pool
        └── ConnectionPoolTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>webclient-pool-demo</artifactId>
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
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
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

Spring Boot 3.3.5 quản lý các phiên bản Spring Framework, Reactor Netty và Micrometer tương thích. Actuator cung cấp tích hợp metrics; MockWebServer chỉ dùng trong test.

### PoolDemoApplication.java

~~~java
package com.example.pool;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PoolDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PoolDemoApplication.class, args);
    }
}
~~~

### Product.java

~~~java
package com.example.pool;

public record Product(String id, String name) {
}
~~~

### WebClientPoolConfiguration.java

~~~java
package com.example.pool;

import java.time.Duration;

import io.netty.channel.ChannelOption;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class WebClientPoolConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogConnectionProvider() {
        return ConnectionProvider.builder("catalog-pool")
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
    WebClient catalogWebClient(
            WebClient.Builder builder,
            ConnectionProvider catalogConnectionProvider) {

        HttpClient httpClient = HttpClient
            .create(catalogConnectionProvider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
            .responseTimeout(Duration.ofSeconds(5));

        String baseUrl = System.getProperty(
            "catalog.base-url", "http://localhost:8081");

        return builder
            .baseUrl(baseUrl)
            .clientConnector(
                new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
~~~

Các điểm cần chú ý:

1. ConnectionProvider được tạo một lần và quản lý như Spring bean.
2. maxConnections giới hạn connection; pendingAcquireMaxCount giới hạn request đang chờ.
3. pendingAcquireTimeout giới hạn thời gian chờ lấy connection, không phải timeout TCP.
4. CONNECT_TIMEOUT_MILLIS giới hạn thiết lập TCP connection mới.
5. responseTimeout giới hạn khoảng chờ giữa các lần đọc dữ liệu network.
6. metrics(true) bật metrics của pool; Actuator/Micrometer giúp xuất và quan sát các metric.
7. destroyMethod=dispose giải phóng provider khi application context đóng.

### CatalogClient.java

~~~java
package com.example.pool;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient catalogWebClient) {
        this.webClient = catalogWebClient;
    }

    public Mono<Product> findById(String id) {
        return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class);
    }
}
~~~

CatalogClient nhận WebClient đã được cấu hình pool. Không tạo connection provider trong từng method.

## 14. Kiểm thử giới hạn connection và pending queue bằng MockWebServer

Có thể mô phỏng upstream chậm để kiểm tra request thứ hai phải chờ hoặc request tiếp theo bị từ chối khi queue đầy.

### ConnectionPoolTests.java

~~~java
package com.example.pool;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.Exceptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;
import reactor.test.StepVerifier;

class ConnectionPoolTests {

    private MockWebServer server;
    private ConnectionProvider provider;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();
    }

    @AfterEach
    void tearDown() throws IOException {
        if (provider != null) {
            provider.dispose();
        }
        server.shutdown();
    }

    private WebClient client(
            int maxConnections,
            int pendingAcquireMaxCount,
            Duration pendingAcquireTimeout) {

        provider = ConnectionProvider.builder(
                "test-pool-" + System.nanoTime())
            .maxConnections(maxConnections)
            .pendingAcquireMaxCount(pendingAcquireMaxCount)
            .pendingAcquireTimeout(pendingAcquireTimeout)
            .build();

        HttpClient httpClient = HttpClient.create(provider)
            .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
            .baseUrl(server.url("/").toString())
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .build();
    }

    private Mono<String> get(WebClient client, String path) {
        return client.get()
            .uri(path)
            .retrieve()
            .bodyToMono(String.class);
    }

    @Test
    void requestSucceedsThroughConfiguredPool() {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("catalog-ok"));

        WebClient client = client(
            2, 2, Duration.ofSeconds(1));

        StepVerifier.create(get(client, "/health"))
            .expectNext("catalog-ok")
            .verifyComplete();
    }

    @Test
    void onePendingRequestCanWaitForTheOnlyConnection() {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("first")
            .setBodyDelay(150, TimeUnit.MILLISECONDS));

        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("second"));

        WebClient client = client(
            1, 1, Duration.ofSeconds(2));

        Mono<String> first = get(client, "/first");
        Mono<String> second = get(client, "/second");

        StepVerifier.create(Flux.merge(first, second))
            .expectNextCount(2)
            .expectComplete()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void requestIsRejectedWhenPendingQueueIsDisabled() {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("slow")
            .setBodyDelay(700, TimeUnit.MILLISECONDS));

        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("second"));

        WebClient client = client(
            1, 0, Duration.ofSeconds(1));

        Mono<String> first = get(client, "/first");
        Mono<String> second = get(client, "/second");

        StepVerifier.create(Flux.merge(first, second))
            .expectErrorMatches(error -> {
                Throwable cause = Exceptions.unwrap(error);
                String name = cause.getClass().getSimpleName();
                String message = String.valueOf(cause.getMessage())
                    .toLowerCase(Locale.ROOT);

                return name.contains("PoolAcquirePendingLimit")
                    || message.contains("pending acquire queue");
            })
            .verify(Duration.ofSeconds(3));
    }
}
~~~

Test thứ nhất xác nhận WebClient gửi request qua pool và đọc response bình thường.

Test thứ hai đặt maxConnections=1 và pendingAcquireMaxCount=1. Request thứ nhất giữ connection trong lúc body bị trì hoãn; request thứ hai được xếp hàng rồi tiếp tục khi connection được trả về.

Test thứ ba đặt pendingAcquireMaxCount=0. Khi connection duy nhất đang bận, request tiếp theo không được xếp hàng và phải nhận lỗi pool acquire. Chi tiết exception có thể khác theo phiên bản Reactor Netty được Spring Boot quản lý.

Chạy test:

~~~bash
mvn -q test
~~~

Nếu ba test pass, Maven kết thúc với exit code 0. Test không đo throughput production; nó chỉ xác minh semantics của pool và hàng đợi với một upstream được điều khiển.

## 15. Cấu hình pool trong ứng dụng thực tế

Một cấu hình pool nên được quyết định theo từng dependency. Một API tìm kiếm nhanh, một dịch vụ báo cáo chậm và một message gateway có thể cần pool/timeout khác nhau.

Ví dụ:

~~~java
@Bean(destroyMethod = "dispose")
ConnectionProvider reportingConnectionProvider() {
    return ConnectionProvider.builder("reporting-pool")
        .maxConnections(10)
        .pendingAcquireMaxCount(20)
        .pendingAcquireTimeout(Duration.ofSeconds(3))
        .maxIdleTime(Duration.ofSeconds(30))
        .maxLifeTime(Duration.ofMinutes(10))
        .build();
}
~~~

Một catalog API latency thấp có thể dùng maxConnections lớn hơn nhưng pendingAcquireTimeout ngắn hơn.

### Một WebClient cho mỗi upstream có chính sách khác nhau

Không nhất thiết phải dùng một pool chung cho mọi dịch vụ. Có thể tạo provider và WebClient riêng:

- catalog-pool: phục vụ truy vấn sản phẩm.
- reporting-pool: phục vụ báo cáo có thời gian xử lý dài.
- payment-pool: giới hạn chặt số connection và timeout ngắn.

Tách pool giúp một upstream chậm không chiếm hết connection dành cho upstream khác. Tuy nhiên, mỗi pool tăng tổng tài nguyên và phải được tính trong ngân sách connection của ứng dụng.

### Giới hạn connection không thay thế rate limiting

maxConnections giới hạn connection đồng thời. Nó không giới hạn trực tiếp số request mỗi giây. Một pool nhỏ có thể tái sử dụng connection nhanh và vẫn gửi nhiều request mỗi giây.

Nếu upstream yêu cầu giới hạn request rate, hãy dùng rate limiter/token bucket hoặc cơ chế quota phù hợp. Không dùng maxConnections như một cách thay thế rate limiting.

## 16. Backpressure, queueing và overload protection

Connection pool và pending queue là một phần của cơ chế bảo vệ tải, nhưng chúng không tự giải quyết toàn bộ overload.

Một thiết kế an toàn thường kết hợp:

- **Bounded pending queue:** giới hạn số request được phép chờ.
- **Acquire timeout:** giới hạn thời gian chờ connection.
- **Overall deadline:** giới hạn tổng thời gian của request.
- **Rate limiting:** giới hạn tốc độ gửi tới upstream.
- **Circuit breaker:** tạm ngừng gọi upstream khi lỗi liên tục vượt ngưỡng.
- **Bulkhead:** tách tài nguyên giữa các dependency.
- **Retry policy:** retry có giới hạn, có backoff và chỉ với thao tác phù hợp.
- **Backpressure:** không tạo hàng đợi downstream vô hạn.

Khi pool đầy, cần quyết định tầng nào chuyển lỗi acquire thành response phù hợp. Một API gateway có thể trả 503 hoặc 429 tùy nguyên nhân và hợp đồng. Không nên trả 200 với body rỗng chỉ để che lỗi pool.

## 17. Các lỗi thường gặp và cách khắc phục

1. **Tạo WebClient mới cho mỗi request.** Điều này tạo churn và làm mất lợi ích reuse. Tạo WebClient/provider dùng chung theo lifecycle ứng dụng.
2. **Đặt maxConnections quá cao.** Upstream có thể bị quá tải và máy client dùng quá nhiều socket. Tính tổng connection của mọi instance.
3. **Đặt maxConnections quá thấp.** Request xếp hàng và acquire timeout dù upstream còn khả năng xử lý. Đo concurrency và latency để điều chỉnh.
4. **Dùng pendingAcquireMaxCount=-1 mà không có lý do.** Queue vô hạn có thể tích lũy request và làm tăng memory/latency. Ưu tiên queue hữu hạn.
5. **Không đặt pendingAcquireTimeout.** Request có thể chờ lâu hơn deadline của caller. Đặt timeout theo ngân sách request.
6. **Nhầm pendingAcquireTimeout với connect timeout.** Một cái chờ connection từ pool; một cái thiết lập TCP connection mới. Cấu hình riêng.
7. **Nhầm responseTimeout với timeout tổng.** responseTimeout giới hạn khoảng chờ giữa các lần đọc network, không phải toàn bộ thời gian xử lý.
8. **Đặt timeout quá ngắn cho stream hợp lệ.** Một stream có khoảng im lặng dài có thể bị đóng dù vẫn đúng nghiệp vụ. Chọn timeout theo idle semantics.
9. **Đặt maxIdleTime lớn hơn idle timeout upstream.** Pool có thể cấp connection đã bị peer đóng. Đặt giá trị phù hợp với keep-alive của server/proxy.
10. **Không cấu hình maxLifeTime khi upstream yêu cầu luân chuyển connection.** Connection lâu năm có thể giữ route/node cũ. Chọn lifetime theo môi trường.
11. **Không bật hoặc không đọc metrics.** Pool exhaustion chỉ được phát hiện qua lỗi người dùng. Theo dõi active, idle, pending và acquire time.
12. **Dùng chung một pool cho mọi upstream không cùng đặc tính.** Dependency chậm có thể chiếm tài nguyên của dependency nhanh. Cân nhắc tách pool theo upstream.
13. **Tạo ConnectionProvider nhưng không dispose.** Có thể giữ tài nguyên sau shutdown/test. Quản lý lifecycle bằng bean destroy method.
14. **Dispose global resources khi ứng dụng vẫn còn WebClient khác sử dụng.** Có thể làm hỏng client khác. Chỉ dispose provider do ứng dụng sở hữu.
15. **Cho rằng maxConnections là số request đồng thời với HTTP/2.** HTTP/2 multiplex nhiều stream trên một connection; phải xét giới hạn stream.
16. **Retry ngay khi pool acquire thất bại.** Retry có thể làm queue đầy hơn. Retry phải có backoff, giới hạn và deadline.
17. **Dùng connection pool để giới hạn request/giây.** Pool giới hạn connection đồng thời, không phải rate. Dùng rate limiter nếu cần quota.
18. **Không kiểm tra tổng connection từ nhiều instance.** Mỗi instance có pool riêng; upstream thấy tổng của tất cả instance.
19. **Không phân biệt pool exhaustion với upstream response 503.** Một lỗi xảy ra trước khi có response; lỗi kia là status từ upstream. Ghi nhận và ánh xạ riêng.
20. **Không load test burst traffic.** Cấu hình tốt ở tải thấp có thể tạo pending queue lớn khi burst. Kiểm thử concurrency, latency và failure rate.

## 18. Checklist cấu hình connection pool

Trước khi phát hành WebClient client, hãy xác định:

- **Connector:** đang dùng Reactor Netty hay connector khác?
- **Destination:** pool áp dụng cho host/port nào?
- **maxConnections:** upstream có thể phục vụ bao nhiêu connection từ tất cả instance?
- **pendingAcquireMaxCount:** queue có hữu hạn và phù hợp burst không?
- **pendingAcquireTimeout:** request được chờ bao lâu trước khi thất bại?
- **Connect timeout:** TCP connection mới có giới hạn thời gian không?
- **Response timeout:** khoảng im lặng giữa các lần đọc có giới hạn phù hợp không?
- **Overall deadline:** toàn bộ request có nằm trong deadline của caller không?
- **Idle policy:** maxIdleTime có phù hợp với keep-alive của upstream/proxy không?
- **Lifetime:** có cần maxLifeTime và background eviction không?
- **Protocol:** HTTP/1.1 hay HTTP/2? Có multiplexing không?
- **Metrics:** active, idle, total, pending và acquire time có được quan sát không?
- **Lifecycle:** provider có được chia sẻ và dispose đúng lúc không?
- **Overload:** queue full/acquire timeout được ánh xạ thành lỗi ứng dụng nào?
- **Retry:** retry có giới hạn, backoff và không làm khuếch đại tải không?
- **Testing:** có test pool bình thường, pending queue và queue rejection không?

## 19. Bài tập tự kiểm tra

**Bài 1.** maxConnections giới hạn điều gì?  
**Đáp án:** Số connection mà pool có thể tạo/giữ cho remote destination theo cấu hình.

**Bài 2.** pendingAcquireMaxCount giới hạn điều gì?  
**Đáp án:** Số request đang chờ được cấp connection khi không có connection khả dụng.

**Bài 3.** pendingAcquireMaxCount=0 có ý nghĩa gì?  
**Đáp án:** Không cho request xếp hàng chờ; nếu không lấy được connection ngay thì request bị từ chối.

**Bài 4.** pendingAcquireTimeout khác connect timeout thế nào?  
**Đáp án:** Acquire timeout là thời gian chờ connection trong pool; connect timeout là thời gian thiết lập TCP connection mới.

**Bài 5.** responseTimeout có phải timeout tổng của request không?  
**Đáp án:** Không. Nó giới hạn khoảng thời gian giữa các lần đọc dữ liệu network. Dùng Reactor timeout nếu cần deadline tổng.

**Bài 6.** maxIdleTime dùng để làm gì?  
**Đáp án:** Loại connection nằm idle trong pool quá thời gian cho phép, giảm nguy cơ tái sử dụng connection đã cũ.

**Bài 7.** maxLifeTime khác maxIdleTime thế nào?  
**Đáp án:** maxLifeTime giới hạn tuổi thọ connection; maxIdleTime giới hạn thời gian connection nằm không hoạt động.

**Bài 8.** Vì sao pending queue vô hạn nguy hiểm?  
**Đáp án:** Nó có thể tích lũy request, tăng memory và latency, che giấu quá tải upstream.

**Bài 9.** HTTP/2 có một connection phục vụ nhiều request đồng thời không?  
**Đáp án:** Có. HTTP/2 multiplex nhiều stream trên cùng connection, theo giới hạn stream được thương lượng.

**Bài 10.** Vì sao cần tính tổng pool của tất cả instance?  
**Đáp án:** Mỗi instance có pool riêng; upstream nhận tổng connection từ toàn bộ instance.

**Bài 11.** Pool metrics nào cho thấy request đang chờ connection?  
**Đáp án:** pending.connections; cần xem cùng active.connections và pending.connections.time.

**Bài 12.** Vì sao không tạo ConnectionProvider trong mỗi method gọi API?  
**Đáp án:** Điều đó gây churn, mất reuse và làm lifecycle tài nguyên khó quản lý.

## 20. Ghi nhớ

ConnectionProvider quản lý connection pool của Reactor Netty. maxConnections giới hạn số connection; pendingAcquireMaxCount giới hạn số request chờ; pendingAcquireTimeout giới hạn thời gian chờ được cấp connection. Queue hữu hạn giúp ứng dụng từ chối sớm khi quá tải thay vì tích lũy request vô hạn.

Acquire timeout, connect timeout, response timeout và overall timeout bảo vệ các giai đoạn khác nhau. maxIdleTime, maxLifeTime và eviction quản lý connection cũ. HTTP/2 multiplex nhiều stream nên số connection không tương đương số request đồng thời.

Hãy cấu hình một provider dùng chung theo lifecycle ứng dụng, theo dõi active/idle/pending metrics và tính tổng connection của tất cả instance. Chọn pool dựa trên request rate, latency, năng lực upstream và load test. Connection pool là một phần của overload protection; nó cần phối hợp với bounded queue, deadline, rate limiting, circuit breaker, bulkhead và retry có kiểm soát.

### Tài liệu tham khảo

- Spring Framework, [WebClient – Client Connector and Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html).
- Spring Framework, [WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).
- Reactor Netty, [HTTP Client – Connection Pool](https://projectreactor.io/docs/netty/release/reference/http-client.html#_connection_pool).
- Reactor Netty, [HTTP Client – Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html#_timeout_configuration).
- Reactor Netty, [Metrics](https://projectreactor.io/docs/netty/release/reference/metrics.html).
- Reactor Netty Javadoc, [ConnectionProvider](https://projectreactor.io/docs/netty/release/api/reactor/netty/resources/ConnectionProvider.html).
- Reactor Netty Javadoc, [HttpClient](https://projectreactor.io/docs/netty/release/api/reactor/netty/http/client/HttpClient.html).
- Project Reactor, [Reactor Core Reference](https://projectreactor.io/docs/core/release/reference/).
- Spring Boot, [Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- OkHttp, [MockWebServer](https://square.github.io/okhttp/4.x/mockwebserver/).
