# Giới hạn kết nối, hàng đợi chờ và số yêu cầu đồng thời

Trong ứng dụng Spring Boot chạy trên **Servlet web stack** với máy chủ nhúng Tomcat, ba khái niệm dễ nhầm là **kết nối đồng thời**, **hàng đợi kết nối** và **yêu cầu HTTP đang được xử lý đồng thời**. Chúng có liên quan nhưng không phải cùng một số đo. Đặt `server.tomcat.max-connections=1000` không có nghĩa ứng dụng xử lý được 1.000 request nghiệp vụ cùng một lúc; đặt `server.tomcat.threads.max=200` cũng không có nghĩa chỉ 200 socket TCP có thể tồn tại.

Khi lưu lượng tăng, request có thể bị chờ ở nhiều chỗ: trình duyệt và reverse proxy, hàng đợi chờ kết nối của hệ điều hành, connector của Tomcat, executor xử lý request, bộ cấp phát kết nối database, hoặc hàng đợi trong các dịch vụ phụ thuộc. Muốn cấu hình đúng, cần biết giới hạn đang tác động ở tầng nào và đo được nút thắt thực tế.

Bài này tập trung vào Spring Boot 3.3.x, Tomcat NIO trên Servlet stack và Java 21. Những giá trị mặc định dưới đây là của **Spring Boot 3.3.x** trong cấu hình thông thường, không phải gợi ý cấu hình tối ưu cho mọi hệ thống. Với Jetty, Undertow, Reactor Netty, external Servlet container hoặc custom Executor, cần kiểm tra cơ chế và thuộc tính riêng.

## 1. Phân biệt các loại giới hạn

| Khái niệm | Đại diện cho | Ví dụ | Điểm cần nhớ |
| --- | --- | --- | --- |
| **TCP connection đang mở** | Kết nối mạng từ client/proxy đến server | 100 socket keep-alive đang mở | Kết nối có thể đang rảnh, không có request nào chạy |
| **Accepted connections** | Kết nối đã được connector tiếp nhận và quản lý | `maxConnections` của Tomcat | Không phải số request đang thực thi trong controller |
| **Listen/accept backlog** | Kết nối mới đang chờ tại socket/OS khi server chưa thể tiếp nhận tiếp | `acceptCount` | Là hàng đợi **kết nối**, không phải hàng đợi business task |
| **Request processing threads** | Thread đang hoặc có khả năng xử lý request synchronous | `maxThreads` / `server.tomcat.threads.max` | Với request blocking, thread bị chiếm trong thời gian xử lý |
| **Executor task queue** | Công việc đã được đưa tới executor nhưng chưa có worker xử lý | `server.tomcat.threads.max-queue-capacity` ở cấu hình được hỗ trợ | Khác OS listen backlog; ngữ nghĩa thực tế tùy executor |
| **In-flight HTTP requests** | Request đã tới hệ thống và chưa hoàn tất | 120 request đang đợi/được xử lý | Có thể lớn hơn số worker thread nếu có async/HTTP/2 |
| **Downstream pool capacity** | Khả năng dùng kết nối tới database, HTTP client hoặc hệ thống khác | HikariCP maximumPoolSize=20 | Có thể là nút thắt dù Tomcat còn thread trống |

Ví dụ, Tomcat nhận 300 kết nối HTTP keep-alive nhưng chỉ có 12 request đồng thời. Khi request dùng HTTP/1.1 tuần tự trên các connection đang mở, nhiều connection hoàn toàn không chiếm thread trong lúc chờ request tiếp theo. Ngược lại, HTTP/2 cho phép nhiều stream/request trên một connection, vì vậy số request đang hoạt động có thể lớn hơn số kết nối.

**Không được dùng các từ connection, request, thread và queue thay thế cho nhau** khi thiết kế giới hạn hoặc quan sát production.

## 2. Request đi qua những tầng nào khi hệ thống chịu tải?

~~~text
HTTP client / load generator
          |
          v
DNS / network / load balancer / API gateway
          |
          v
Tomcat listening socket
          |
          +--> OS connection backlog (acceptCount: mức yêu cầu)
          |
          v
Tomcat Connector (accepted sockets <= maxConnections, theo cơ chế connector)
          |
          +--> I/O poller, keep-alive, parser
          |
          +--> Tomcat executor / worker threads
          |       +--> runnable task queue (nếu executor có queue)
          |       +--> xử lý Servlet Filter
          |       +--> DispatcherServlet / Controller
          |
          v
Service / transaction / database pool / HTTP client pool
          |
          v
Database / remote API
          |
          v
HTTP response -> client
~~~

Sơ đồ khái quát những vị trí có thể chờ, không phải thứ tự nội bộ bất biến của tất cả connector và executor Tomcat. Tomcat NIO, cấu hình executor dùng chung, virtual threads và request async có thể thay đổi cách tài nguyên được sử dụng.

Khi server bận, có thể xảy ra các tình huống khác nhau:

1. **Còn chỗ nhận kết nối nhưng hết worker:** Tomcat có thể giữ thêm connection và công việc chờ xử lý, khiến latency tăng.
2. **Đã đạt maxConnections:** kết nối mới có thể chờ ở listen backlog của OS; khi backlog quá tải, client có thể bị timeout hoặc lỗi kết nối.
3. **Worker còn nhưng database pool hết connection:** request vẫn được nhận, nhưng thread mắc kẹt chờ lấy JDBC connection.
4. **Gateway hết hạn chờ trước backend:** client thấy 502/504 hoặc timeout dù server chưa kịp trả response.
5. **Một request làm việc async:** số request in-flight và số worker đang chạy có thể rất khác nhau.

Mục tiêu của capacity planning không phải chỉ làm cho hệ thống “nhận được nhiều socket”, mà là duy trì throughput, độ trễ và tỷ lệ lỗi trong giới hạn tài nguyên.

## 3. Các thuộc tính quan trọng của Spring Boot 3.3 + Tomcat

| Thuộc tính Spring Boot | Mặc định Spring Boot 3.3.x | Ý nghĩa chính |
| --- | ---: | --- |
| `server.tomcat.threads.max` | `200` | Số worker threads tối đa của Tomcat khi dùng mô hình platform threads thông thường |
| `server.tomcat.threads.min-spare` | `10` | Mức worker threads tối thiểu được duy trì |
| `server.tomcat.max-connections` | `8192` | Giới hạn kết nối được connector chấp nhận và xử lý đồng thời |
| `server.tomcat.accept-count` | `100` | Kích thước listen backlog mong muốn của OS khi không tiếp nhận thêm kết nối được |
| `server.tomcat.threads.max-queue-capacity` | `2147483647` | Giới hạn hàng đợi runnable tasks của executor ở trường hợp được hỗ trợ; chỉ có hiệu lực khi cấu hình > 0 |
| `server.tomcat.connection-timeout` | Tùy giá trị hiệu lực của connector | Khoảng chờ để nhận request line sau khi chấp nhận kết nối |
| `server.tomcat.keep-alive-timeout` | Nếu không cấu hình, dùng connection timeout | Khoảng chờ HTTP request tiếp theo trên connection keep-alive |
| `server.tomcat.max-keep-alive-requests` | `100` | Số request tối đa trên một kết nối keep-alive trước khi đóng theo cấu hình connector |

Nguồn đối chiếu: Spring Boot 3.3 Common Application Properties và Apache Tomcat 10.1 HTTP Connector Configuration (liên kết ở cuối bài). Giá trị **mặc định** có thể bị thay đổi bởi profile, biến môi trường, command-line argument, cấu hình factory và các điều chỉnh trong ứng dụng.

Ba giới hạn đầu cần ghi nhớ nhất:

- `threads.max`: năng lực cấp worker thread của server cho xử lý request synchronous.
- `max-connections`: số connection Tomcat đang nhận và quản lý; bao gồm cả connection chờ/keep-alive.
- `accept-count`: kích thước hàng đợi chờ kết nối tại socket/OS khi connector đạt tình trạng không thể nhận thêm connection.

**Chú ý:** tài liệu Spring Boot mô tả accept-count qua tình huống hết request-processing threads, còn tài liệu Tomcat Connector nêu rõ listen backlog khi `maxConnections` đạt giới hạn. Ở tầng vận hành hãy dùng nghĩa connector/OS cụ thể và kiểm chứng thực tế; đừng biến accept-count thành “số request được xếp sau maxThreads”.

## 4. `server.tomcat.threads.max`: giới hạn worker threads

Với Spring MVC xử lý đồng bộ thông thường, Tomcat cấp worker thread để thực hiện chuỗi Servlet Filter, DispatcherServlet, controller và service. Khi controller gọi JDBC, remote HTTP client blocking, `Thread.sleep` hoặc file I/O blocking, worker có thể bị chiếm trong lúc chờ.

~~~text
maxThreads = 8
8 worker threads đều đang xử lý request chậm
            |
Request mới đến
            |
Không có worker trống ngay lúc đó
            |
Chờ / được đưa vào cơ chế phân phối của connector-executor
            |
Worker rảnh -> tiếp tục xử lý
~~~

Giá trị `threads.max=8` thường giới hạn số thread xử lý của executor nội bộ; nó không đồng nghĩa “chỉ 8 client có thể kết nối”. Số accepted connections vẫn chịu `max-connections` và cơ chế NIO.

Trường hợp nên xem lại `threads.max`:

- `tomcat.threads.busy` thường xuyên sát ngưỡng tối đa trong khi CPU, GC và downstream còn khả năng xử lý.
- Latency tăng mạnh khi số request concurrent tăng.
- Thread dump cho thấy nhiều worker bị giữ bởi JDBC, socket read hoặc lock.
- Số thread hiện hành, thread đang bận và độ trễ thực tế có dấu hiệu cho thấy worker là bottleneck.

Tuy nhiên, **tăng threads.max không nhất thiết tăng throughput**. Nếu database pool chỉ có 20 connection và các request đều cần database, tăng worker từ 100 lên 500 có thể tạo thêm 400 request đang đợi, làm tăng memory, context switching và p99 latency.

### 4.1. min-spare khác max

`server.tomcat.threads.min-spare` là số worker thread tối thiểu mà Tomcat duy trì, không phải mức concurrency tối thiểu hay thread dành riêng cho một endpoint. Thread pool có thể tăng dần tới `threads.max` khi cần. Không nên nâng min-spare lên sát max nếu chỉ vì muốn “có sẵn nhiều thread”, vì thread cũng tiêu tốn tài nguyên.

### 4.2. Shared executor và virtual threads

Nếu connector được cấu hình dùng một `Executor` ngoài hoặc dùng chung, thuộc tính `maxThreads` nội bộ có thể bị bỏ qua; giới hạn phải xem tại executor thực tế.

Trong Spring Boot 3.3 trên Java 21, khi bật `spring.threads.virtual.enabled=true`, các thuộc tính `server.tomcat.threads.max` và `min-spare` **không còn chi phối request workers theo cùng cách**. Virtual threads làm mô hình sử dụng thread khác đi nhưng không tạo ra CPU, database connection, RAM hoặc downstream capacity vô hạn. Muốn giới hạn request đồng thời theo nghiệp vụ, có thể cần semaphore/bulkhead/rate limit riêng.

## 5. `server.tomcat.max-connections`: giới hạn kết nối đồng thời

Tomcat NIO có thể quản lý nhiều HTTP connection trong khi chỉ có một tập worker nhỏ hơn. Một connection có thể:

- Đang gửi/nhận request.
- Đang ở trạng thái keep-alive chờ request tiếp theo.
- Đang dùng HTTP/2 với nhiều request streams.
- Đang chờ socket event, timeout hoặc response.

Giá trị `maxConnections=8192` trong mặc định Boot 3.3 có nghĩa connector có thể nhận và quản lý lượng connection tới giới hạn đó theo cơ chế của Tomcat. Nó **không phải bảo đảm xử lý 8192 request nghiệp vụ đồng thời**, cũng không đồng nghĩa throughput 8192 request/giây.

Ví dụ:

~~~text
maxConnections = 1000
maxThreads     = 80

Có 750 HTTP keep-alive connections, phần lớn đang rảnh
Có 35 synchronous requests đang thực thi

=> Connector vẫn có nhiều connection đang mở,
   còn worker threads đang bận chỉ là khoảng 35.
~~~

Ngược lại, HTTP/2 có thể khiến một connection mang nhiều request streams. Do đó đừng suy số request đồng thời từ số socket với phép tính cố định “1 connection = 1 request”.

Giới hạn số connection bị ảnh hưởng bởi open file descriptors, socket buffers, kernel TCP settings, reverse proxy connection pooling, số instance, TLS, phiên bản connector và client traffic pattern.

Đừng đặt `max-connections` quá cao chỉ để nhận nhiều client hơn. Nếu downstream không chịu được tải và worker đã hết, kết nối dư có thể biến thành backlog và hàng đợi kéo dài thời gian chờ.

## 6. `server.tomcat.accept-count`: listen backlog, không phải business queue

Hệ điều hành hỗ trợ một hàng đợi cho những kết nối đang chờ được ứng dụng accept từ listening socket. Tomcat dùng tham số `acceptCount` để yêu cầu kích thước backlog khi đã đạt mức chấp nhận connection của connector; OS có thể điều chỉnh hoặc không tuân theo chính xác giá trị.

Ví dụ minh họa:

~~~text
TCP connections đến nhanh hơn khả năng accept
            |
            +--> Tomcat đang giữ maxConnections connections
            |
            +--> OS listen backlog (acceptCount)
            |
            +--> Backlog đầy
                      |
                      +--> Client connect timeout
                      +--> Connection refused / reset tùy OS/network
~~~

Không được diễn giải `accept-count=100` thành “100 request được lưu trong queue sau 200 worker threads” hoặc “100 request chắc chắn hoàn thành”. Listen backlog chứa **kết nối đang chờ**, chịu hành vi OS, network và handshake.

Các điểm quan trọng:

1. Backlog là tham số của listening socket, không phải collection trong Java controller.
2. Kernel có thể giới hạn kích thước hiệu dụng bằng những cấu hình của OS.
3. Một load balancer hoặc reverse proxy có thể có hàng đợi riêng trước khi request tới Tomcat.
4. Tăng backlog có thể giảm lỗi kết nối trong các đợt burst ngắn, nhưng nếu server xử lý chậm kéo dài, backlog lớn có thể chỉ làm request đợi lâu hơn.
5. Dấu hiệu quá tải có thể là client connection timeout hoặc refused connection; **không nhất thiết** là HTTP 503/429 từ application.

## 7. Hàng đợi executor khác hàng đợi OS

Trong tài liệu Spring Boot 3.3 có thuộc tính `server.tomcat.threads.max-queue-capacity` cho hàng đợi tác vụ của thread pool. Tomcat có khái niệm `maxQueueSize` cho runnable tasks chờ executor xử lý. Đây là queue ở tầng **Java executor**, khác `acceptCount` của listening socket.

| Queue | Đơn vị thường chờ | Có thuộc tính tương ứng | Nơi tồn tại |
| --- | --- | --- | --- |
| **OS listen backlog** | Kết nối TCP đang chờ accept | `server.tomcat.accept-count` | Kernel/socket |
| **Tomcat executor queue** | Runnable task chờ worker | `server.tomcat.threads.max-queue-capacity`, trong trường hợp supported | Executor |
| **Database connection wait queue** | Thread/task chờ nhận DB connection | HikariCP timeout và cấu hình pool | Application/DataSource |
| **Gateway / load balancer queue** | HTTP request chưa chuyển tiếp tới backend | Tùy gateway/proxy | Hạ tầng ngoài JVM |
| **Business job queue** | Công việc cần thực hiện bất đồng bộ | Kafka/RabbitMQ/queue nội bộ, nếu thiết kế | Tầng nghiệp vụ |

Không thể dùng một con số `accept-count` để mô tả toàn bộ thời gian queueing. Một request có thể chờ ở nhiều hàng đợi khác nhau trong hành trình của nó.

Cấu hình `threads.max-queue-capacity` trong Spring Boot 3.3 chỉ có hiệu lực khi giá trị lớn hơn 0 và theo implementation executor tương ứng. Nếu connector dùng custom Executor hoặc virtual threads, cần kiểm tra hành vi thực tế. Đừng đặt một con số nhỏ rồi giả định mọi request vượt ngưỡng sẽ nhận đúng HTTP 429; lỗi có thể xuất hiện ở tầng mạng, executor hoặc gateway.

Khi quyết định giới hạn queue, cần cân nhắc thời gian chờ tối đa chấp nhận được. Hàng đợi dài làm tail latency tăng ngay cả khi throughput không cải thiện.

## 8. Số yêu cầu đồng thời phụ thuộc giao thức và cách xử lý

### 8.1. HTTP/1.1 và keep-alive

HTTP/1.1 có thể tái sử dụng một TCP connection cho nhiều HTTP requests. Trong lúc không có request đang thực thi, connection có thể chờ request tiếp theo mà không chiếm worker xử lý trong toàn bộ thời gian chờ.

`server.tomcat.keep-alive-timeout` ảnh hưởng thời gian Tomcat chờ request tiếp theo trên connection. Nó khác với thời gian tối đa service được phép xử lý một request nghiệp vụ.

Ví dụ, 300 keep-alive connections đang mở không có nghĩa 300 worker threads đang bận.

### 8.2. HTTP/2

HTTP/2 multiplex nhiều streams trong một TCP connection. Vì vậy có thể có 1 connection nhưng nhiều request cùng tồn tại. Việc phân phối xử lý still phụ thuộc connector, executor và ứng dụng.

Không áp dụng phép suy luận `maxConnections ≈ maximum concurrent requests` cho HTTP/2; cũng phải xem những giới hạn stream/concurrency ở các tầng liên quan.

### 8.3. Async Servlet

Spring MVC hỗ trợ cơ chế như `Callable`, `DeferredResult`, `WebAsyncTask` hoặc streaming. Khi request bước vào pha async và giải phóng worker, request vẫn in-flight nhưng có thể không giữ Tomcat request-processing thread suốt thời gian chờ.

Nếu dùng async, phải xem executor dùng cho phần việc thực tế và giới hạn của nó. Đưa blocking I/O sang một executor không giới hạn chỉ di chuyển điểm quá tải sang chỗ khác.

### 8.4. Virtual threads

Virtual threads của Java 21 có thể giúp mô hình request blocking sử dụng thread hiệu quả hơn, nhưng tổng số request hoàn thành mỗi giây vẫn bị ràng buộc bởi CPU, database, external API, memory và cấu hình khác. Bật virtual threads không làm `max-connections` hay tài nguyên OS trở thành vô hạn.

## 9. Timeout và connection reuse ảnh hưởng capacity

Ngoài ba giới hạn cơ bản, thời gian duy trì connection quyết định lượng tài nguyên bị giữ:

- `server.tomcat.connection-timeout`: khoảng chờ sau khi nhận connection để đọc request URI line. Đây không phải “tổng timeout của service/controller”.
- `server.tomcat.keep-alive-timeout`: khoảng chờ request tiếp theo trên một connection; nếu không đặt, giá trị connection timeout thường được dùng.
- `server.tomcat.max-keep-alive-requests`: số request được phép dùng một kết nối trước khi đóng theo chính sách connector.
- Timeout của reverse proxy, load balancer, client, database và outbound HTTP client: những timeout độc lập cần được phối hợp.

Ví dụ, rút keep-alive timeout có thể giảm số connection idle chiếm slot nhưng đồng thời tăng số lần TCP/TLS handshake. Giảm connection-timeout có thể hạn chế client gửi dữ liệu quá chậm, nhưng cũng có thể gây lỗi cho client hợp lệ trên mạng có độ trễ cao.

**Không dùng connection-timeout để giải quyết truy vấn SQL mất 30 giây.** Điều đó thường cần timeout ở JDBC/query, transaction, downstream HTTP client và giới hạn nghiệp vụ; còn timeout tổng request từ góc nhìn client/gateway cần được thiết kế riêng.

## 10. Throughput, latency và in-flight requests: định lượng bằng Little's Law

Một cách ước lượng lượng công việc đồng thời trong trạng thái ổn định là:

~~~text
L = λ × W

L = số request in-flight trung bình
λ = throughput trung bình (requests/second)
W = thời gian request ở trong hệ thống (seconds)
~~~

Nếu hệ thống hoàn thành trung bình 300 request/giây với thời gian xử lý từ đầu tới cuối trung bình 0,20 giây:

~~~text
L = 300 × 0,20 = 60 request in-flight trung bình
~~~

Đây là **giá trị trung bình**, không phải p99 concurrency, số worker threads cần thiết hay số lượng connection phải cấu hình. Nếu có queueing, thời gian W tăng và L cũng có thể tăng trong khi throughput không tăng.

Ví dụ Java độc lập chạy trên JDK 17+:

**CapacityMath.java**

~~~java
import java.util.Locale;

public class CapacityMath {
    public static void main(String[] args) {
        double throughputPerSecond = 300.0;
        double averageLatencySeconds = 0.20;
        double averageInFlight = throughputPerSecond * averageLatencySeconds;

        System.out.printf(Locale.ROOT,
            "Average in-flight requests: %.0f%n", averageInFlight);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CapacityMath.java
java CapacityMath
~~~

Stdout chính xác:

~~~text
Average in-flight requests: 60
~~~

Nếu cùng throughput 300 request/giây nhưng latency trung bình tăng lên 2 giây do queueing, số in-flight trung bình có thể thành 600, không có nghĩa server đã xử lý hiệu quả gấp 10.

**Không dùng Little's Law để lấy trực tiếp `threads.max=60`**. Thread occupancy phụ thuộc phần thời gian synchronous giữ thread; còn timeout, burst, percentiles, CPU và DB contention cần được đo thêm.

## 11. Ví dụ cấu hình thử nghiệm Tomcat trong Spring Boot

Đoạn cấu hình dưới đây dành cho **thử nghiệm trên máy local**. Nó cố ý đặt giới hạn thấp để quan sát sự khác biệt; không áp dụng nguyên xi cho production.

**src/main/resources/application.yml**

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
  tomcat:
    threads:
      max: 8
      min-spare: 2
    max-connections: 64
    accept-count: 20
    connection-timeout: 5s
    keep-alive-timeout: 3s
~~~

Ý nghĩa:

- Tomcat giới hạn tối đa 8 platform worker threads cho request handling synchronous.
- Connector được cấu hình với giới hạn 64 accepted connections.
- Listen backlog được yêu cầu là 20; giá trị hiệu lực thực tế còn phụ thuộc OS.
- Thời gian chờ request line và HTTP keep-alive được cấu hình riêng.
- `server.address=127.0.0.1` giữ demo chỉ lắng nghe loopback IPv4, phù hợp thực hành cá nhân.

Nếu muốn kiểm nghiệm hàng đợi executor, có thể thử thêm `server.tomcat.threads.max-queue-capacity` với giá trị dương ở môi trường kiểm thử, nhưng cần hiểu cách executor được tạo và đo đúng tín hiệu; tránh tưởng rằng thay đổi queue capacity đảm bảo một status code HTTP cố định.

### 11.1. Project Gradle tối thiểu chạy được

Cấu trúc:

~~~text
tomcat-capacity-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/capacity/
    │   ├── CapacityDemoApplication.java
    │   └── CapacityController.java
    └── resources/
        └── application.yml
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'tomcat-capacity-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**src/main/java/com/example/capacity/CapacityDemoApplication.java**

~~~java
package com.example.capacity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CapacityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CapacityDemoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/capacity/CapacityController.java**

~~~java
package com.example.capacity;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/demo")
public class CapacityController {

    private final AtomicInteger inFlight = new AtomicInteger();
    private final AtomicInteger peak = new AtomicInteger();

    @GetMapping("/work")
    public Map<String, Integer> work(
            @RequestParam(defaultValue = "200") int delayMs)
            throws InterruptedException {

        if (delayMs < 0 || delayMs > 2000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "delayMs must be 0..2000");
        }

        int active = inFlight.incrementAndGet();
        peak.accumulateAndGet(active, Math::max);

        try {
            // Cố ý chiếm worker thread để quan sát giới hạn.
            // Không dùng Thread.sleep để giả lập nghiệp vụ production.
            Thread.sleep(delayMs);
            return Map.of(
                "activeAtEntry", active,
                "peakObserved", peak.get());
        } finally {
            inFlight.decrementAndGet();
        }
    }

    @GetMapping("/stats")
    public Map<String, Integer> stats() {
        return Map.of(
            "inFlight", inFlight.get(),
            "peakObserved", peak.get());
    }
}
~~~

Các biến `AtomicInteger` đảm bảo cập nhật số đếm thread-safe trong demo. Giá trị `inFlight` chỉ đếm số lần thực thi method `work()` trong một instance, **không** đếm tất cả socket, tất cả Servlet requests, connection đang chờ accept hoặc request của instance khác.

### 11.2. Chạy chương trình

Trong thư mục chứa `build.gradle` với JDK 21 và Gradle tương thích:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

Nếu đã có Gradle wrapper, chỉ cần `./gradlew bootRun`. Trên Windows PowerShell, sử dụng `.\gradlew.bat bootRun`.

Khi Boot khởi động thành công, embedded Tomcat lắng nghe trên 127.0.0.1:8080. Không cần cài Tomcat độc lập.

Kiểm tra một request:

~~~bash
curl -i "http://127.0.0.1:8080/demo/work?delayMs=200"
~~~

Kết quả kỳ vọng là HTTP 200 và một JSON response có hai trường, ví dụ khi chỉ có một request từng chạy:

~~~json
{"activeAtEntry":1,"peakObserved":1}
~~~

Giá trị trong response thay đổi theo concurrency và lịch sử request, vì vậy không nên coi đây là stdout/JSON cố định cho mọi lần thử.

Xem số đo của demo:

~~~bash
curl -s "http://127.0.0.1:8080/demo/stats"
~~~

Nếu không còn request `work` đang thực thi, `inFlight` thường là 0. `peakObserved` giữ giá trị cao nhất quan sát được kể từ lúc ứng dụng chạy; khởi động lại sẽ reset.

### 11.3. Thử chạy đồng thời trên máy local

Ví dụ Bash/Linux/macOS phát 20 request gần như cùng lúc:

~~~bash
for i in $(seq 1 20); do
  curl -s -o /dev/null "http://127.0.0.1:8080/demo/work?delayMs=1000" &
done
wait
curl -s "http://127.0.0.1:8080/demo/stats"
~~~

Với `threads.max=8`, không dùng async và controller cố ý blocking, peak synchronous `work` đang thực thi thường không vượt quá số worker xử lý request tương ứng. Tuy nhiên, số peak chính xác và thời gian hoàn thành phụ thuộc scheduling, keep-alive, kết nối của client, JVM, OS và cấu hình thực tế.

**Không chạy bài thử tải trên hệ thống production hoặc địa chỉ server người khác.** Demo chỉ bind loopback; những con số 8/64/20 được chọn để dễ quan sát khác biệt giữa thread, connection và backlog.

Thử lần lượt thay `threads.max`, `max-connections`, `accept-count` trong một môi trường kiểm thử, đo lại latency và lỗi, sau đó giải thích tại sao kết quả thay đổi. Chỉ thay một nhóm biến tại một thời điểm để tránh kết luận sai.

## 12. Đo và quan sát bằng Actuator, Micrometer, hệ điều hành

Ví dụ controller ở trên cho thấy số request thực thi trong một method, chưa phải metrics cấp connector. Khi quan sát ứng dụng thật cần cả server metrics và downstream metrics.

Nếu thêm Spring Boot Actuator:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Trong môi trường local, có thể bật endpoint metrics:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
server:
  tomcat:
    mbeanregistry:
      enabled: true
~~~

Đây là phần **mở rộng** ngoài cấu hình demo ban đầu; nếu ghép vào cùng file YAML cần hợp nhất các key `server`, tránh khai báo trùng block ở root. Việc bật Tomcat MBean Registry giúp thu thập đầy đủ metrics Tomcat trong những cấu hình Spring Boot có Micrometer binder phù hợp.

Các metric name phổ biến để tìm trong Spring Boot/Micrometer Tomcat gồm:

- `tomcat.threads.busy`: worker threads đang bận.
- `tomcat.threads.current`: số worker hiện có.
- `tomcat.threads.config.max`: cấu hình giới hạn worker threads.
- `tomcat.connections.current`: số connection theo metric server đang xuất.
- HTTP server request metrics `http.server.requests`: số request, thời lượng, phân loại status/method/URI tùy tag và instrumentation.

Tên metric khả dụng và tag phụ thuộc version/instrumentation. Hãy gọi `/actuator/metrics` để liệt kê trước, rồi truy cập metric cụ thể, ví dụ:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
~~~

**Không công khai metrics không có bảo vệ trên Internet.** Production cần phân quyền truy cập, giới hạn network hoặc xuất metrics an toàn sang hệ quan sát.

Khi điều tra nhiều instance, quan sát metric theo **instance/pod** và aggregate từ load balancer. Tổng request toàn hệ thống không cho biết một pod riêng lẻ có bị quá tải hay không.

Nên kết hợp thêm:

| Tín hiệu | Cho biết điều gì |
| --- | --- |
| RPS/throughput | Số request hoàn thành trong khoảng thời gian |
| p50/p95/p99 latency | Thời gian đáp ứng trung vị và phần đuôi phân phối |
| HTTP 4xx/5xx, timeout, connection refused | Lỗi tầng ứng dụng, gateway hoặc mạng |
| Tomcat busy/current/max threads | Khả năng saturation ở worker pool |
| Tomcat current/allowed connections | Connection occupancy, có thể bao gồm keep-alive idle |
| JVM CPU, heap, GC pauses, thread dumps | Nút thắt CPU/memory/lock |
| Hikari active/idle/pending/timeout | Có đang chờ database connections hay không |
| Client pool pending, remote API latency | Có chờ outbound HTTP hay không |
| OS TCP backlog drops, open files | Socket/OS đang là nút thắt |
| Gateway upstream connect/read timeout | Request chậm hoặc lỗi trước/sau khi tới app |

Nếu `tomcat.threads.busy` luôn thấp nhưng p99 cao, không nên kết luận Tomcat đã khỏe hoàn toàn: có thể app sử dụng async, lỗi network ở gateway, truy vấn chậm, hoặc số request bị chặn từ trước khi vào connector.

## 13. Kết hợp giới hạn Tomcat với database pool và downstream

Giả sử:

~~~text
Tomcat threads.max    = 200
Tomcat max-connections = 1000
Hikari maximumPoolSize = 20
Mỗi request cần 1 JDBC connection trong 300 ms
~~~

Nếu toàn bộ 200 worker đồng thời tới database, nhiều request có thể đợi lấy connection. Tăng `threads.max` lên 500 không làm database có thêm khả năng xử lý; hàng đợi có thể dài hơn và nhiều request hết hạn chờ.

Bảng định hướng:

| Nút thắt đo được | Hướng điều tra |
| --- | --- |
| Worker threads luôn bận, CPU còn thấp | Xem blocking calls và khả năng của downstream trước khi tăng threads |
| Hikari pending tăng, connection active sát max | Tối ưu query/transaction, giảm thời gian giữ connection, cân nhắc pool theo sức chịu của DB |
| CPU gần 100%, p99 tăng | Giảm overhead, tối ưu code, scale out; tăng threads nhiều có thể làm tệ hơn |
| Accepted connections sát max nhưng ít request | Kiểm tra idle keep-alive, connection leaks, proxy pooling, timeouts |
| Client connect timeouts khi burst | Kiểm tra maxConnections, OS listen backlog, load balancer, network và khả năng xử lý |
| Queue tăng nhưng throughput không tăng | Ưu tiên giảm thời gian xử lý, giới hạn chờ, load shedding hoặc scale thích hợp |
| Gateway 504 nhưng app trả muộn | Đồng bộ timeout và giảm latency của backend/downstream |

Một hệ thống có thể cần **bulkhead** giới hạn số request được gọi tới dependency đắt đỏ, queue hữu hạn và từ chối sớm khi quá tải. Những chính sách này là thiết kế ở ứng dụng/gateway, không tự xuất hiện chỉ nhờ `threads.max` hoặc `accept-count`.

### 13.1. Rate limit và concurrency limit không giống nhau

- **Rate limit** kiểm soát tốc độ yêu cầu theo thời gian, ví dụ 100 request/giây cho một API key.
- **Concurrency limit** kiểm soát số yêu cầu cùng tồn tại tại một thời điểm, ví dụ tối đa 20 giao dịch nặng đang xử lý.
- **Connection limit** kiểm soát số socket tới server, không gắn trực tiếp với user hoặc quyền nghiệp vụ.
- **Queue limit** kiểm soát số đơn vị đang chờ tại một tầng cụ thể.

API cần chống lạm dụng có thể dùng 429 Too Many Requests khi vượt rate limit đã được thiết kế; 503 Service Unavailable có thể phù hợp khi chủ động từ chối vì quá tải. **Spring Boot/Tomcat không tự đảm bảo rằng vượt accept-count hoặc threads.max sẽ trả 429 hoặc 503**: request có thể chỉ bị chờ, time out hoặc thất bại kết nối trước khi có HTTP response.

## 14. Cách thiết kế và hiệu chỉnh giới hạn

Một quy trình có cơ sở thực nghiệm:

1. **Xác định SLO:** ví dụ 95% request hoàn tất dưới 300 ms ở 200 RPS và lỗi dưới ngưỡng được cho phép.
2. **Xác định workload:** GET nhẹ, POST ghi database, upload file, streaming, long polling và batch có đặc điểm tài nguyên khác nhau.
3. **Đo baseline:** throughput, p50/p95/p99, CPU, memory, Tomcat threads/connections và database pool.
4. **Kiểm tra client/proxy:** số TCP connection, HTTP/1.1 hay HTTP/2, keep-alive, upstream pool và timeout.
5. **Tìm giới hạn nhỏ nhất trên đường đi:** worker threads, JDBC pool, CPU, outbound HTTP client, gateway hoặc OS.
6. **Thiết lập concurrency và queue hợp lý:** giới hạn tài nguyên theo khả năng phục vụ, tránh hàng đợi dài vô hạn; xem xét reject sớm.
7. **Load test tăng dần:** steady load, burst, soak test và failure test trong môi trường được phép.
8. **Thay từng tham số:** ví dụ worker max, max connections, keep-alive timeout, database pool; so sánh trước/sau theo p99 và lỗi.
9. **Kiểm thử thoát tải:** khi burst kết thúc, queue có giảm và latency phục hồi nhanh không?
10. **Ghi nhận giả định và rollback:** lưu version Boot/Tomcat, hạ tầng, số instance, profile và bộ cấu hình được kiểm chứng.

Ví dụ quyết định:

~~~text
p99 tăng + tomcat.threads.busy sát max?
    |
    +-- Có -> worker bị kẹt ở đâu?
    |          +-- CPU cao -> tối ưu CPU / scale
    |          +-- JDBC pending cao -> tối ưu DB / pool / giới hạn workload
    |          +-- External API chậm -> timeout / bulkhead / caching
    |
    +-- Không -> xem connection occupancy,
                 proxy/network, async executor và downstream
~~~

Không chọn `threads.max` bằng cách nhân tùy ý với số CPU core. Với request rất I/O-bound, số worker lớn hơn số core có thể hợp lý; với CPU-bound, nhiều threads có thể chỉ tăng context switching. Cần đo mức thời gian bị blocking, tài nguyên per-thread và khả năng của downstream.

## 15. Những lỗi hiểu nhầm phổ biến

1. **“max-connections là max requests.”** Sai khi có keep-alive, HTTP/2, requests đang chờ và xử lý async.
2. **“threads.max=200 thì chỉ có 200 client kết nối được.”** Sai; Tomcat NIO có thể quản lý số connection lớn hơn.
3. **“accept-count là queue gồm 100 request sau worker pool.”** Sai; đây là backlog kết nối ở tầng listening socket/OS.
4. **“Tăng queue sẽ tăng throughput.”** Không chắc; queue thường chỉ giữ thêm công việc, làm tăng thời gian chờ và tail latency.
5. **“Tăng threads.max sẽ sửa database chậm.”** Có thể làm tình trạng tệ hơn do thêm request chờ DB.
6. **“connection-timeout kiểm soát tổng thời gian controller chạy.”** Sai; property này gắn với đọc request line sau khi accept.
7. **“Mỗi connection HTTP/2 chỉ mang một request.”** Sai vì multiplexed streams.
8. **“Mọi request in-flight đều chiếm worker thread liên tục.”** Sai với asynchronous Servlet và các mô hình I/O khác.
9. **“Đặt min-spare cao sẽ tăng số request xử lý tối đa.”** Không phải; đó là số worker được duy trì, không phải ngưỡng tối đa.
10. **“Bật virtual threads là không cần concurrency limit.”** Sai; CPU, database, remote API và memory vẫn hữu hạn.
11. **“Có 502/504 là chắc chắn Tomcat trả lỗi.”** Không chắc; status có thể do reverse proxy phát sinh.
12. **“Vượt threads.max sẽ nhận HTTP 429.”** Sai; 429 cần chính sách rate limiting phù hợp, không tự tạo từ worker pool.
13. **“Chỉ cần xem một metric threads.busy.”** Chưa đủ để biết hàng đợi OS, pool database, gateway hoặc socket idle.
14. **“Dùng thông số của Jetty/Undertow giống Tomcat.”** Sai; mỗi runtime có mô hình thread, connection và cấu hình khác.
15. **“Thử tải tại production rồi tăng dần đến khi lỗi.”** Nguy hiểm và khó tái lập; dùng môi trường được kiểm soát, workload và giới hạn đã thống nhất.

## 16. Checklist vận hành

Trước khi chốt cấu hình máy chủ nhúng, hãy trả lời:

- Web stack thực tế là Spring MVC/Servlet, WebFlux hay ứng dụng không mở web server?
- Server thực tế là Tomcat, Jetty, Undertow, Reactor Netty hay external container?
- Có dùng default Tomcat Executor, custom Executor hoặc Java virtual threads không?
- `threads.max`, `min-spare`, `max-connections` và `accept-count` được thiết lập ở nguồn cấu hình nào và giá trị hiệu lực là bao nhiêu?
- HTTP client dùng keep-alive, HTTP/2 hoặc reverse proxy pooling như thế nào?
- Connection/request/queue saturation đã có metric và cảnh báo chưa?
- Database pool, HTTP client pool, CPU, memory và file descriptors có đủ khả năng phục vụ workload không?
- Timeout tầng client/gateway, Servlet connector, database và remote API có nhất quán với SLO không?
- Hệ thống có cơ chế admission control, rate limit, bulkhead hoặc reject sớm phù hợp không?
- Đã thử nghiệm steady-state, burst, p95/p99, errors và recovery sau quá tải chưa?
- Thay đổi cấu hình đã được ghi nhận, review và có phương án rollback chưa?

**Điểm cốt lõi:** `threads.max`, `max-connections` và `accept-count` giới hạn **ba nguồn tài nguyên khác nhau**. Chúng tương tác với HTTP keep-alive, HTTP/2, executor queue, timeout và năng lực downstream. Một server “chấp nhận được nhiều connection” chưa chắc “xử lý được nhiều request”; cấu hình đúng phải bắt đầu từ workload, đo đạc và yêu cầu độ trễ, sau đó mới chọn giới hạn phù hợp.

## Tài liệu đối chiếu

- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): tra cứu `server.tomcat.threads.max`, `max-connections`, `accept-count` và timeout.
- [Apache Tomcat 10.1 — HTTP Connector](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html): tham số `maxThreads`, `maxConnections`, `acceptCount`, `maxQueueSize`, keepAlive và executor.
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): cách cấu hình server nhúng.
- [Spring Boot 3.3 — Actuator Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html): quan sát request/JVM/server qua Micrometer.
