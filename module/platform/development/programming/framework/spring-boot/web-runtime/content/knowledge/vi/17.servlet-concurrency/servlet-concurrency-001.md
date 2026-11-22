# Mô hình luồng tiếp nhận kết nối và luồng xử lý yêu cầu trong Servlet

## 1. Bài toán: một request HTTP đi qua những luồng nào?

Khi triển khai Spring Boot chạy **Spring MVC trên Servlet container**, chẳng hạn Tomcat nhúng, dễ có ba cách hiểu sai:

1. “Mỗi kết nối TCP luôn sở hữu một thread Java riêng.”
2. “Thread nhận kết nối cũng chính là thread chạy controller.”
3. “Cứ tăng `server.tomcat.threads.max` thì server sẽ phục vụ được vô hạn request đồng thời.”

Trong mô hình **Tomcat NIO thông thường**, connector có các công việc khác nhau: **accept** kết nối, theo dõi **socket readiness** và **thực thi request processing**. Các công việc ấy thường được thực hiện bằng những loại thread khác nhau. Một kết nối keep-alive có thể nằm chờ mà không chiếm một Servlet request worker liên tục; nhưng một controller Servlet **đồng bộ**, nếu đang chờ JDBC, HTTP client, ổ đĩa hoặc `Thread.sleep`, thường giữ request worker suốt khoảng chờ.

Bài này giải thích các lớp đồng thời từ TCP socket tới Spring MVC handler, nêu rõ giới hạn của connector, cách cấu hình/quan sát Tomcat, cơ chế Servlet asynchronous processing, sự khác nhau giữa `Callable`, `DeferredResult`, `@Async`, và Virtual Threads. Có ví dụ Spring Boot 3.5.x / Java 17+ chạy được và các test minh họa chính xác sự chuyển luồng.

**Mục tiêu học tập**

- Nhận diện vai trò của **acceptor**, **poller/selector**, **request worker/executor**, **application executor** và **async dispatch**.
- Phân biệt số **TCP connections**, số **HTTP requests**, số **active workers**, số **queued tasks** và số **async requests còn mở**.
- Giải thích xử lý blocking vs. non-blocking I/O ở hai tầng: connector có thể NIO nhưng Servlet controller vẫn blocking.
- Đọc đúng `maxConnections`, `acceptCount`, `maxThreads`, `minSpareThreads`, `keepAliveTimeout` và các thread-pool settings.
- Tính mức đồng thời cần thiết qua Little's Law và hiểu giới hạn do CPU, I/O, DB pool, memory, timeouts.
- Thấy được tại sao `Callable` giải phóng Servlet container worker nhưng tác vụ vẫn cần một executor khác.
- Kiểm thử theo runtime thật thay vì suy luận chỉ từ thread name hoặc test MockMvc.

**Phạm vi:** Servlet stack của Spring Boot 3.x với Apache Tomcat 10.1 (NIO là cấu hình thường gặp). Jetty, Undertow, Tomcat NIO2 và virtual-thread executor có chi tiết khác; sơ đồ dưới đây không được áp dụng máy móc cho mọi connector.

## 2. Bốn khái niệm không được nhập làm một

| Khái niệm | Nghĩa | Có luôn bằng số worker threads? |
|---|---|---|
| **TCP connection** | Socket giữa peer và server/proxy, có thể tồn tại qua nhiều HTTP requests | Không |
| **HTTP request** | Một lần trao đổi HTTP: request line/headers/body và response tương ứng | Không |
| **In-flight request** | Request đã bắt đầu nhưng chưa hoàn tất, kể cả async đang đợi | Không |
| **Busy request worker** | Thread hiện đang chạy công việc xử lý request trong container executor | Không |

Một HTTP/1.1 keep-alive connection có thể xử lý nhiều request **liên tiếp**. Trong thời gian idle giữa hai request, Tomcat NIO có thể tiếp tục quản lý socket bằng poller thay vì giữ worker chạy controller. HTTP/2 còn có thể multiplex nhiều streams trên một kết nối; không dùng giả định 1 connection = 1 request để thiết kế capacity.

Ví dụ giả định: 1.000 kết nối keep-alive đang mở, nhưng chỉ 20 request tại một thời điểm đang được xử lý trong các controller blocking. Khi ấy số connection có thể lớn hơn rất nhiều số busy workers. Ngược lại, 100 request async đang chờ sự kiện từ hệ thống khác không nhất thiết cần 100 Servlet workers giữ CPU liên tục, nhưng vẫn tiêu tốn connection, request state, memory và các tài nguyên khác.

**Điểm cốt lõi:** capacity phải được đánh giá trên nhiều trục: socket, worker, queue, database connections, upstream concurrency, memory và latency.

## 3. Mô hình Tomcat NIO: Acceptor → Poller → Worker

Sơ đồ khái niệm cho một embedded Tomcat NIO connector:

~~~text
Client / Load balancer
        |
    TCP handshake
        |
Operating-system accept backlog (có giới hạn, phụ thuộc OS)
        |
     Acceptor thread(s)
        | accept socket / đăng ký endpoint
        v
    Socket wrapper / NIO channel
        |
   Poller / Selector thread(s)
        | theo dõi readiness của socket
        | chuyển socket event tới executor
        v
  Container Executor / request worker threads
        |
  Coyote HTTP processor: parse HTTP request
        |
  Servlet Filter chain -> DispatcherServlet
        |
  HandlerMapping -> argument bind/validate
        |
  Spring MVC controller -> service -> DB/HTTP/file
        |
  HttpMessageConverter / view / response write
        |
 Socket keep-alive quay lại theo dõi / hoặc đóng kết nối
~~~

Sơ đồ giản lược, **không** khẳng định mọi byte được đọc/ghi trên cùng một poller hay một worker, không mô tả chi tiết SSL handshake, sendfile, asynchronous Servlet I/O hay HTTP/2 streams.

### 3.1. Acceptor — tiếp nhận kết nối, không chạy nghiệp vụ

Acceptor nhận những socket mới mà hệ điều hành cho phép accept. Công việc chính liên quan tới TCP socket/connector registration; thông thường **không chạy Spring MVC controller**, không mở giao dịch DB và không xử lý JSON nghiệp vụ.

Khi giới hạn concurrent connections của connector đã bị chạm, hành vi accept/backlog thay đổi. Một số connection có thể chờ trong queue của hệ điều hành, timeout hoặc bị từ chối theo tải và chính sách hệ điều hành. Không có công thức “acceptCount đúng bằng số request được xếp hàng trong Spring MVC”: nó mô tả một cấp backlog **kết nối**, không phải hàng đợi của handler tasks.

### 3.2. Poller / Selector — nhận tín hiệu readiness

Poller theo dõi nhiều socket qua NIO selector, phát hiện khi có dữ liệu để đọc hoặc socket đã sẵn sàng cho công việc tiếp theo. Poller không có nghĩa “một thread liên tục đọc một socket”. Đây là một ưu điểm của NIO ở **tầng kết nối**: nhiều kết nối idle có thể được quản lý mà không yêu cầu một blocking Java thread cho từng socket.

NIO ở connector **không tự biến JDBC blocking**, `Thread.sleep()` hoặc một controller Spring MVC đồng bộ thành non-blocking application code. Phần gọi Servlet/controller vẫn thường được dispatch tới worker/executor.

### 3.3. Worker / Executor — xử lý HTTP và gọi Servlet

Khi Tomcat có socket event/request cần xử lý, một worker của container executor có thể:
- Parse request line/headers và xử lý HTTP protocol state.
- Thực thi Servlet filters và security filters.
- Gọi `DispatcherServlet`, controller, service và các thư viện đồng bộ.
- Chờ kết quả blocking I/O nếu application dùng JDBC/client đồng bộ.
- Serialize response bằng `HttpMessageConverter`, render template hoặc ghi bytes.
- Kết thúc hoặc chuyển trạng thái socket để chờ request tiếp theo.

Một worker được **tái sử dụng** cho các requests khác nhau. Không suy luận “cùng user/session/connection thì luôn cùng tên thread”. Dữ liệu request-scoped không được giữ trong field mutable của singleton bean hay dựa vào thread name để định danh client.

### 3.4. Container executor không đồng nghĩa mọi executor trong Spring

Tomcat có worker/executor phục vụ Servlet dispatch. Ngoài ra ứng dụng có thể có:
- `applicationTaskExecutor` do Boot auto-configure.
- `ThreadPoolTaskExecutor` riêng cho Spring MVC `Callable`.
- `@Async` executor cho application methods.
- Scheduler cho `@Scheduled`.
- Executor của HTTP client, Kafka listener, messaging, background jobs.

Những pool này có thể khác nhau cả về số thread, queue và lifecycle. Tăng `spring.task.execution.pool.max-size` không nhất thiết tăng `server.tomcat.threads.max`; tăng Tomcat workers cũng không tự tăng DB connection pool hoặc MVC async executor.

## 4. Timeline của một request đồng bộ

Giả sử `GET /api/report` có bước truy vấn database bằng JDBC blocking:

~~~text
T0  Acceptor nhận connection.
T1  Poller nhận ra socket có request/event.
T2  Tomcat worker W1 được điều phối để xử lý request.
T3  W1 chạy Filter -> DispatcherServlet -> controller.
T4  W1 gọi JDBC và CHỜ 250 ms.
T5  JDBC trả kết quả. W1 serialize DTO, ghi response.
T6  W1 kết thúc phần việc và quay về pool.
T7  Socket được giữ keep-alive hoặc đóng theo protocol/config.
~~~

Trong khoảng T4, **W1 bị chiếm** dù CPU có thể không bận. Điều này giải thích vì sao workload nhiều blocking I/O có thể hết busy worker trước khi CPU đạt 100%.

Một worker không tự động chạy controller khác trong lúc `Thread.sleep`, `ResultSet.next()` đang chờ hoặc `RestTemplate`/synchronous HTTP client block. NIO connector vẫn quản lý các socket khác, nhưng controller synchronously blocking cần worker để tiến hành.

### 4.1. Throughput lý thuyết và giới hạn thật

Theo Little's Law tại trạng thái ổn định:

[
L = lambda 	imes W
]

Trong đó:
- `L`: số request đang đồng thời trong một giai đoạn/hệ.
- `λ`: throughput (requests/second) của giai đoạn đó.
- `W`: thời gian trung bình request ở trong giai đoạn (seconds).

Ví dụ 100 requests/second, mỗi request chiếm worker trung bình 0,2 giây sẽ cần xấp xỉ **20 busy workers** chỉ để duy trì mức tải ấy. Đây là phép ước lượng, không phải đề xuất `maxThreads=20` cho production: CPU, latency tail, garbage collection, bursts, retries, downstream và queueing đều làm cần headroom hoặc giảm thời gian chiếm worker.

Cần phân biệt **end-to-end response latency** với **worker occupancy time**. Với Servlet async, request có thể chờ 1 giây nhưng container worker chỉ bận một phần nhỏ của thời gian ấy; `L=λW` với W toàn request không được dùng trực tiếp để suy ra số worker đang bận.

## 5. Keep-alive, HTTP/2 và sự độc lập của connections/requests

### 5.1. HTTP/1.1 keep-alive

Connection có thể duy trì sau khi một response hoàn tất để xử lý request tiếp theo. Trong lúc không có request, socket idle không nhất thiết chiếm request worker. Cấu hình `keepAliveTimeout` quyết định thời gian chờ request tiếp theo trên một connection trước khi đóng; nó **không** giống business timeout hoặc timeout toàn bộ controller.

Tomcat còn có `maxKeepAliveRequests` — giới hạn số requests có thể được xử lý qua connection trước khi đóng (tùy protocol). Đóng connection không đồng nghĩa controller gặp exception.

### 5.2. HTTP/2 multiplexing

HTTP/2 có nhiều streams/request trên một TCP connection. Một connection có thể phát sinh nhiều tác vụ HTTP đang xử lý đồng thời, chịu các giới hạn HTTP/2 stream/flow control của server và client. Không dùng `maxConnections` làm giới hạn “số requests cùng chạy” cho HTTP/2.

### 5.3. Reverse proxy và load balancer

Tomcat có thể chỉ nhìn thấy connections từ Nginx/Ingress/Load Balancer, không phải từ end users. Proxy có connection pools, keep-alive, buffer, timeout và limits riêng. Một đợt latency tăng có thể bắt nguồn ở proxy queue hoặc upstream connection pool dù Tomcat workers còn rảnh.

Khi debug, phải đặt metrics tại đúng lớp (edge/proxy, Tomcat socket/worker, Spring request, DB/client) để không đổ lỗi cho acceptor khi nút thắt thật nằm trong database.

## 6. Các giới hạn Tomcat cần đọc riêng từng dòng

Spring Boot với embedded Tomcat cho phép cấu hình nhiều thuộc tính connector qua `server.tomcat.*`. Ví dụ **môi trường thử nghiệm**, không phải sizing recommendation cho mọi hệ thống:

~~~properties
server.port=8080
server.tomcat.threads.max=24
server.tomcat.threads.min-spare=4
server.tomcat.max-connections=512
server.tomcat.accept-count=64
server.tomcat.keep-alive-timeout=20s
~~~

| Thuộc tính | Ý nghĩa | Không được nhầm với |
|---|---|---|
| `server.tomcat.threads.max` | Số worker threads tối đa của pool Tomcat nội bộ khi dùng platform-thread executor phù hợp | Số socket connections hoặc tổng số threads JVM |
| `server.tomcat.threads.min-spare` | Số worker threads dự trữ tối thiểu của executor nội bộ | Số acceptors hoặc kết nối phải luôn hoạt động |
| `server.tomcat.max-connections` | Số connections có thể được connector nhận và xử lý đồng thời theo giới hạn | Số controllers đang thực thi hoặc queue tasks |
| `server.tomcat.accept-count` | Backlog kết nối chờ khi maxConnections đạt, có thể chịu giới hạn/điều chỉnh của OS | Số HTTP requests chờ trong Spring `TaskExecutor` |
| `server.tomcat.keep-alive-timeout` | Thời gian chờ request tiếp theo trên connection idle | Timeout của JDBC, service hoặc `Callable` |
| `server.tomcat.connection-timeout` | Thời gian chờ request line sau khi connection được chấp nhận, theo connector settings | Business operation timeout |
| `spring.task.execution.*` | Cấu hình task executor của Spring Boot trong những điều kiện auto-configuration cụ thể | Tomcat acceptor/poller/worker pool |
| `spring.mvc.async.request-timeout` | Timeout mặc định cho một số async request processing paths trong Spring MVC | Network keep-alive timeout |

**Lưu ý:** nếu connector được cấu hình dùng một shared `Executor` thay vì pool nội bộ, một số thuộc tính threads của connector có thể bị bỏ qua. Khi bật Java virtual threads, cách thực thi request và hiệu lực các thread-pool properties cũng thay đổi. Luôn xác minh cấu hình đang hoạt động bằng runtime metrics/JMX và logs.

### 6.1. Tại sao maxConnections không bằng maxThreads?

Với Tomcat NIO, nhiều connections có thể idle/keep-alive mà không giữ busy worker liên tục. `maxConnections` vì vậy thường có thể lớn hơn `maxThreads`. Tuy nhiên mỗi connection vẫn giữ socket/file descriptor, buffers, state, TLS metadata và overhead. Đặt maxConnections rất lớn có thể làm cạn OS file descriptors hoặc memory.

### 6.2. acceptCount không đảm bảo “không bao giờ rớt request”

Backlog là hàng đợi **chờ accept/connect** phía TCP/OS, không phải request queue của ứng dụng. Khi backlog đầy, client có thể gặp timeout hoặc connection refused, tùy kernel và network. Hệ điều hành có thể áp dụng giới hạn hoặc diễn giải giá trị backlog khác với số cấu hình. Đừng coi `accept-count=1000` là “buffer an toàn cho 1000 request trong controller”.

### 6.3. Khi maxThreads đạt giới hạn

Worker pool đã bận hết thì các socket processing tasks có thể xếp hàng trong executor hoặc bị từ chối tùy giới hạn/implementation; request latency tăng. NIO poller không biến CPU-bound/business work thành miễn phí. Đồng thời các lớp upstream có thể tiếp tục giữ sockets và chờ.

Điều quan trọng là đo **busy threads**, **executor queue**, **response time percentiles**, **timeouts/rejections** và **downstream pool saturation**. Chỉ tăng maxThreads khi biết bottleneck và có tài nguyên CPU/memory/DB tương ứng.

## 7. Servlet blocking vs. Tomcat NIO: hai tầng khác nhau

“NIO connector” không đồng nghĩa “Servlet controller hoàn toàn non-blocking”. Tomcat NIO tối ưu I/O ở tầng mạng, nhất là việc quản lý nhiều sockets. Nhưng đồng bộ Servlet programming model vẫn có thể chặn worker trong các hoạt động:
- JDBC query hoặc transaction blocking.
- Synchronous HTTP client `RestTemplate` / `RestClient`.
- File system blocking.
- `Thread.sleep` hoặc lock contention.
- JSON serialization lớn gây CPU load.
- Lấy connection từ pool đã cạn.

Tương tự, “CPU idle” không chứng minh server còn throughput. Một thread dump có thể cho thấy hàng chục `http-nio-*-exec-*` threads đang chờ socket/DB/locks, trong khi các request mới vẫn phải queue.

### 7.1. Servlet 3.x+ asynchronous processing

Servlet API hỗ trợ async mode, cho phép request **tạm rời** filter/Servlet call stack mà giữ response mở. Spring MVC tích hợp qua `Callable`, `WebAsyncTask`, `DeferredResult`, `ResponseBodyEmitter`, `SseEmitter` và streaming/reactive return values.

Nhưng “asynchronous” có nhiều nghĩa:
- **Giải phóng Servlet request worker:** thread của container không bị giữ liên tục trong thời gian đợi.
- **Dùng một application executor khác:** với `Callable`, tác vụ có thể vẫn block trên một thread khác.
- **Thật sự non-blocking end-to-end:** chỉ đạt khi I/O libraries và pipeline cũng non-blocking; `Callable` không tự biến JDBC blocking thành reactive.

Không suy luận rằng đổi `String` thành `Callable<String>` giúp giảm CPU hoặc giảm tổng thread count. Nó thường chỉ **chuyển nơi chờ** từ Tomcat worker sang MVC async worker, tạo không gian cho container tiếp nhận những request khác.

## 8. Timeline Callable: trả container worker rồi async dispatch

~~~text
Client sends GET /demo/callable
    |
Tomcat worker W1
    |
DispatcherServlet -> controller tạo Callable
    |
Spring MVC startAsync() và submit Callable tới AsyncTaskExecutor
    |
W1 rời Servlet/filter chain và quay về Tomcat pool
    |             Response vẫn mở
    |                      |
    |               MVC async worker A1
    |                      | chạy Callable / chờ I/O
    |                      | return kết quả
    |                      v
    +----------- Async dispatch trở lại container
                           |
                      Tomcat worker W2
                           |
                   DispatcherServlet xử lý async result
                   Converter ghi JSON, hoàn tất response
~~~

W1 và W2 **có thể** tình cờ là cùng một thread nếu pool tái sử dụng, nhưng không có đảm bảo. Đừng gắn logic nghiệp vụ vào giả định “controller entry/exit luôn cùng thread” khi đã có async dispatch. `ThreadLocal`, MDC logging và security context cần cơ chế propagation phù hợp với executor/framework.

### 8.1. Callable vs. DeferredResult

| Cơ chế | Ai tạo kết quả cuối | Có tự tạo một worker để chạy công việc? |
|---|---|---|
| Method trả `String` / DTO đồng bộ | Controller trên Tomcat worker | Không cần pool phụ |
| `Callable<T>` | Callable được Spring chạy trên `AsyncTaskExecutor` | Có, executor thực thi Callable |
| `WebAsyncTask<T>` | Callable với cấu hình timeout/executor tùy request | Có, giống Callable |
| `DeferredResult<T>` | Nguồn bên ngoài quyết định khi nào gọi `setResult`/`setErrorResult` | Không tự đòi một thread chuyên ngồi chờ mỗi request; phụ thuộc nguồn sự kiện |
| `ResponseBodyEmitter` / `SseEmitter` | Event producer phát nhiều chunks/events | Phụ thuộc async producer và writer; kết nối/response còn mở |
| `@Async` method | Method chạy trên executor do `@EnableAsync` cấu hình | Có nếu được gọi qua Spring proxy; không tự kích hoạt Servlet async response |

**Đặc biệt:** gọi một method có `@Async` từ controller rồi dùng `future.get()` ngay trên Tomcat worker vẫn làm controller block, trừ khi trả một async result được MVC nhận biết và quản lý. `@Async` cũng có các caveat về proxy/self-invocation.

### 8.2. Async timeout và cancellation

Async request có timeout riêng; nó **không** là keep-alive timeout của socket. Timeout có thể dẫn đến error/dispatch, nhưng không nên tin rằng thread chạy một tác vụ blocking sẽ tự động dừng ngay. Nếu gọi JDBC/upstream, vẫn cần timeout, cancellation và resource cleanup cụ thể của thư viện.

Khi thiết kế `DeferredResult`, có thể đăng ký `onTimeout` và `onCompletion`, nhưng callback có thể chạy trên thread khác. Kết quả có thể đến sau khi client disconnect; phải xử lý late completion idempotently.

## 9. Ví dụ thực hành: một project Spring Boot Java 17+

Dự án này cho bạn quan sát hai đường đi:
- `/demo/thread`: controller synchronous chạy trên Tomcat worker.
- `/demo/blocking`: worker bị giữ trong 300 ms bởi `Thread.sleep` (chỉ để demo).
- `/demo/callable`: controller tạo `Callable` trên Tomcat worker, còn Callable thực thi ở pool có tiền tố `mvc-async-`.
- Một `OncePerRequestFilter` in tên thread ở lần dispatch đầu, giúp thấy filter/container boundary.

**Không sử dụng `Thread.sleep` trong request handler production** như giải pháp chờ. Đó chỉ là cách tạo một workload blocking có thể đo được, không phụ thuộc DB bên ngoài.

### 9.1. Maven project

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>servlet-threads-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Chỉ khai báo `spring-boot-starter-web` vì đây là chương trình Servlet MVC. Đừng suy luận runtime reactive chỉ từ việc project khác có `WebClient` dependency.

File `src/main/resources/application.properties` (các mức này để thực nghiệm trên local):

~~~properties
server.port=8080
server.tomcat.threads.max=24
server.tomcat.threads.min-spare=4
server.tomcat.max-connections=512
server.tomcat.accept-count=64
management.endpoints.web.exposure.include=health,metrics
~~~

**An toàn:** Actuator metrics có thể làm lộ thông tin vận hành. Đừng expose công khai trên production; bảo vệ endpoint bằng security/network policy. Các giới hạn Tomcat trên đây là cấu hình của môi trường thử, không phải lựa chọn tối ưu có thể copy vào hệ thống production không cần benchmark.

### 9.2. Java source độc lập

Tạo `src/main/java/example/threads/ServletThreadsApplication.java`:

~~~java
package example.threads;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.Callable;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;
import org.springframework.http.MediaType;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class ServletThreadsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServletThreadsApplication.class, args);
    }

    @Bean("mvcAsyncExecutor")
    ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("mvc-async-");
        // Spring quản lý vòng đời, khởi tạo executor qua bean lifecycle.
        return executor;
    }

    @Bean
    WebMvcConfigurer asyncMvcConfigurer(
            @Qualifier("mvcAsyncExecutor")
            ThreadPoolTaskExecutor executor) {

        return new WebMvcConfigurer() {
            @Override
            public void configureAsyncSupport(AsyncSupportConfigurer config) {
                config.setTaskExecutor(executor);
                config.setDefaultTimeout(5000);
            }
        };
    }
}

@RestController
@RequestMapping("/demo")
class ThreadDemoController {

    @GetMapping(path = "/thread",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Map<String, String> thread() {
        return Map.of(
                "mode", "sync",
                "requestThread", Thread.currentThread().getName());
    }

    @GetMapping(path = "/blocking",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Map<String, String> blocking() throws InterruptedException {
        String before = Thread.currentThread().getName();
        Thread.sleep(300);
        return Map.of(
                "mode", "blocking",
                "threadBefore", before,
                "threadAfter", Thread.currentThread().getName());
    }

    @GetMapping(path = "/callable",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Callable<Map<String, String>> callable() {

        String entryThread = Thread.currentThread().getName();

        return () -> {
            Thread.sleep(300);
            return Map.of(
                    "mode", "callable",
                    "entryThread", entryThread,
                    "taskThread", Thread.currentThread().getName());
        };
    }
}

@Component
class RequestThreadFilter extends OncePerRequestFilter {

    private static final Logger LOG =
            LoggerFactory.getLogger(RequestThreadFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws IOException, ServletException {

        String entry = Thread.currentThread().getName();
        LOG.info("begin uri={} dispatch={} thread={}",
                request.getRequestURI(), request.getDispatcherType(), entry);

        try {
            chain.doFilter(request, response);
        } finally {
            LOG.info("end uri={} asyncStarted={} thread={}",
                    request.getRequestURI(), request.isAsyncStarted(),
                    Thread.currentThread().getName());
        }
    }
}
~~~

Mã có một `public class` trùng tên file và các type package-private trong cùng `example.threads`, tất cả được scan bởi `@SpringBootApplication`. Không cần `@EnableAsync` cho ví dụ `Callable` vì Spring MVC có hỗ trợ async request riêng.

`RequestThreadFilter` kế thừa `OncePerRequestFilter`. Mặc định nó có thể bỏ qua async redispatch, nên **không** lấy việc filter log một lần làm bằng chứng HTTP request kết thúc ở lần log đó. Sau controller trả `Callable`, filter chain của initial dispatch có thể kết thúc với `asyncStarted=true`, nhưng response vẫn đang mở cho kết quả async.

Một số imports không được sử dụng có thể bỏ, chẳng hạn `org.springframework.core.task.TaskExecutor`; trình biên dịch Java không coi import không sử dụng là lỗi. Nếu bật checkstyle nghiêm ngặt, xóa imports thừa.

### 9.3. Chạy và đọc output

Yêu cầu JDK 17+, Maven, cổng 8080 còn trống:

~~~bash
mvn spring-boot:run
~~~

Trong terminal khác:

~~~bash
curl -s http://localhost:8080/demo/thread
curl -s http://localhost:8080/demo/blocking
curl -s http://localhost:8080/demo/callable
~~~

Ví dụ **hình dạng** kết quả, không ràng buộc số thứ tự thread:

~~~json
{"mode":"sync","requestThread":"http-nio-8080-exec-1"}
~~~

~~~json
{"mode":"blocking","threadBefore":"http-nio-8080-exec-2","threadAfter":"http-nio-8080-exec-2"}
~~~

~~~json
{"mode":"callable","entryThread":"http-nio-8080-exec-3","taskThread":"mvc-async-1"}
~~~

Kết quả thực có thể dùng tên `http-nio-8080-exec-X` khác, tùy connector, số request trước đó và Tomcat version. Với synchronous blocking method, code trước/sau `Thread.sleep` nằm trong một invocation nên cùng thread. Với Callable, `entryThread` và `taskThread` thuộc hai executor khác nhau theo cấu hình demo; async response còn được dispatch lại tới container worker để serialize, nhưng JSON trả về chỉ chứa tên thread tại hai điểm được đo.

Đừng khẳng định từ output rằng Tomcat chỉ có ba threads hoặc rằng mỗi HTTP connection gắn chặt với một thread. Đây chỉ là ba request độc lập quan sát ở những thời điểm cụ thể.

## 10. Kiểm thử với MockMvc đúng phạm vi

Thêm file `src/test/java/example/threads/ServletThreadsApplicationTests.java`:

~~~java
package example.threads;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ServletThreadsApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void synchronousControllerReturnsThreadInformation() throws Exception {
        mvc.perform(get("/demo/thread"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mode").value("sync"))
                .andExpect(jsonPath("$.requestThread").isNotEmpty());
    }

    @Test
    void blockingControllerUsesOneThreadWithinInvocation()
            throws Exception {

        mvc.perform(get("/demo/blocking"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mode").value("blocking"));
    }

    @Test
    void callableStartsAsyncAndUsesConfiguredTaskExecutor()
            throws Exception {

        MvcResult initial = mvc.perform(get("/demo/callable"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(initial))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mode").value("callable"))
                .andExpect(jsonPath("$.taskThread").isNotEmpty());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Lưu ý về ý nghĩa test:** `MockMvc` không chạy Tomcat connector thật nên initial request thread trong bài test có thể là test runner thread (ví dụ `main`), không nhất thiết mang tên `http-nio-...`. Test chỉ xác nhận MVC async handling, HTTP result và executor đã được cấu hình. Muốn kiểm tra acceptor/poller/worker thực tế thì phải chạy ứng dụng nhúng và quan sát thread dump/JMX/metrics, không lấy MockMvc làm bằng chứng kiến trúc socket.

## 11. Khi nào chuyển từ synchronous sang asynchronous?

### 11.1. Workload chờ lâu, ít CPU

Nếu request cần chờ event/message hoặc một upstream async API, `DeferredResult` hoặc asynchronous return value có thể giúp tránh giữ container worker trong suốt thời gian chờ. Nhưng cần timeout, completion/cancellation, giới hạn số request đang mở và chính sách backpressure.

### 11.2. JDBC hoặc HTTP client vẫn blocking

Chuyển việc đó sang `Callable` giúp Tomcat worker quay về pool, nhưng một MVC async worker vẫn bị giữ trong thời gian block. Nếu DB connection pool chỉ có 10 connections, tạo 500 async workers **không** giúp DB xử lý 500 truy vấn song song hữu ích; chỉ gây queue ở tầng khác.

Khi đã dùng `Callable`, chọn một executor có số workers và queue phù hợp với downstream capacity; đừng dùng unbounded threads/queue để che latency. Một hàng đợi quá dài làm request timeout và tích tụ memory.

### 11.3. CPU-intensive handler

Đưa CPU-heavy task sang async executor không làm tổng CPU work giảm. Trên cùng một máy, quá nhiều threads có thể gây context switching và làm tail latency xấu hơn. Cần tối ưu thuật toán, caching, precomputation hoặc tách worker service nếu thích hợp.

### 11.4. Streaming/SSE

SSE mở kết nối lâu; Servlet async có thể tránh giữ worker suốt thời gian **không có event**, nhưng response/socket vẫn mở, cần timeout/heartbeat, cleanup khi disconnect và giới hạn stream clients. Việc viết dữ liệu có thể cần worker trong Servlet MVC, không đồng nghĩa non-blocking WebFlux.

## 12. Phân biệt @Async và MVC asynchronous processing

`@Async` thuộc Spring task execution: khi được bật với `@EnableAsync` và method đi qua Spring proxy, công việc có thể chạy trên một executor. Nó không tự khởi động `HttpServletRequest.startAsync()` và không thay đổi contract HTTP nếu controller vẫn chờ kết quả.

Ví dụ anti-pattern minh họa (fragment):

~~~java
@GetMapping("/bad")
String bad() throws Exception {
    Future<String> future = asyncService.fetch();
    return future.get(); // Tomcat worker vẫn BLOCK ở đây
}
~~~

Cần phân biệt điều này với:

~~~java
@GetMapping("/callable")
Callable<String> good() {
    return () -> blockingService.fetch();
}
~~~

Trong ví dụ thứ hai, Spring MVC có thể `startAsync()` rồi chạy Callable trên executor khác. Tác vụ `blockingService.fetch()` vẫn block thread của executor đó, nhưng không giữ Servlet worker ban đầu. Trường hợp tốt hơn nữa là dùng I/O bất đồng bộ thực sự nếu client và business API hỗ trợ, nhưng không nên đổi framework chỉ để sửa một endpoint mà chưa đo bottleneck.

**Khi service trả `CompletableFuture`** và Spring MVC xử lý nó như async return value, cũng cần test timeout/error/cancellation và executor thực sự được sử dụng. Không đặt giả định rằng có `CompletableFuture` ở bất kỳ vị trí nào đều làm request bất đồng bộ.

## 13. Virtual threads: lựa chọn khác trong Java 21+

Ví dụ chạy ở mục 9 dùng Java 17 và **platform threads**. Với **Java 21+**, Spring Boot 3.5 hỗ trợ lựa chọn virtual threads:

~~~properties
spring.threads.virtual.enabled=true
~~~

Khi bật đúng điều kiện Java/runtime, nhiều công việc blocking-style có thể được thực hiện bằng virtual threads được JVM scheduling trên carrier platform threads, giúp giảm chi phí giữ một platform thread cho mỗi tác vụ chờ. Tuy nhiên:

- Virtual threads không biến CPU-intensive work thành nhanh hơn; vẫn cần CPU cores.
- Không giải quyết giới hạn DB pool, remote API rate limits, socket/file handles hoặc memory.
- Một số blocking operations/pinning situations có thể ảnh hưởng throughput; cần đo với workload thật.
- Các thông số `server.tomcat.threads.max`/`min-spare` dành cho platform-worker pool có thể không còn hiệu lực theo cấu hình virtual threads của Boot.
- Không suy luận rằng acceptor/poller của Tomcat biến mất hoặc tất cả framework executors dùng virtual threads giống nhau.
- Nên dùng JDK Flight Recorder hoặc công cụ chẩn đoán JDK thích hợp để tìm pinned virtual threads/bottlenecks.

**Đừng** bật `spring.threads.virtual.enabled=true` trên Java 17 rồi tuyên bố thí nghiệm đang chạy virtual threads. Java 21+ là điều kiện cần. Nếu dự án dùng Java 17, giữ cách platform thread ở demo chính để kết quả có thể tái lập.

## 14. Quan sát thực tế: logs, Actuator, thread dumps, JMX

### 14.1. Logs theo từng giai đoạn

Để hiểu một request:
1. Log request ID, route, method tại điểm vào filter.
2. Log `Thread.currentThread().getName()` ở controller entry.
3. Khi có Callable, log thread ở trong Callable và nhận biết async completion.
4. Log thời gian chiếm worker, tổng request latency và downstream wait.
5. Không đặt request-specific mutable state vào singleton bean field.
6. Với MDC/`ThreadLocal`, có cơ chế propagate và cleanup khi chuyển executor; request thread có thể được tái sử dụng cho client khác.

Không log cookies, Authorization tokens hoặc full request body chứa PII. Thread name chỉ là tín hiệu debug, không phải identity của user.

### 14.2. Actuator metrics

Nếu project có `spring-boot-starter-actuator` và bật exposure phù hợp:

~~~bash
curl -s http://localhost:8080/actuator/metrics
~~~

Danh sách cho biết các metric names thực tế đã được đăng ký. Tùy version/connector/config, có thể thấy các metrics liên quan tới:
- Tomcat busy/current threads.
- Current/keep-alive connections.
- HTTP server requests/observations.
- JVM threads, CPU, memory, garbage collection.
- Application task executor active/pool/queue (nếu được instrument).

Không hardcode một metric name chỉ từ suy luận. Hãy liệt kê `/actuator/metrics`, sau đó truy vấn các names xuất hiện. Một số Tomcat-specific metrics cần connector JMX MBean registry hoặc binder phù hợp được bật. **Không expose** Actuator metrics, `/actuator/env` hay `/actuator/beans` rộng rãi trên Internet.

### 14.3. Thread dump

Từ JDK:

~~~bash
jcmd <PID> Thread.print
~~~

`<PID>` là placeholder hiển thị cú pháp; khi thực thi cần thay bằng PID thật của Java process. Trong thread dump, phân loại:
- Acceptor/poller threads: thường đang chờ socket/readiness.
- `http-nio-...-exec-...` hoặc worker threads tương đương: có đang block trên DB/socket/lock hay chạy controller?
- `mvc-async-...`: có đang thực thi Callable hoặc queue đầy?
- GC, scheduler, background, client HTTP workers: phân biệt khỏi Servlet worker.

Đừng tính tất cả `Thread.State.WAITING` là “thread deadlock”. Poller, idle executor và scheduler thường chờ hợp lệ. Một deadlock cần quan hệ lock cycle hoặc bằng chứng cụ thể từ dump.

### 14.4. JMX và connection pool

JMX/Tomcat MBeans có thể cung cấp executor/connector metrics, bao gồm busy threads và connections. Đồng thời theo dõi HikariCP active/idle/pending nếu dùng JDBC, vì 50 Tomcat workers chạy vào DB pool 10 connections có thể khiến 40 workers chờ pool, làm request queue tăng mà CPU vẫn thấp.

Cần ghi lại:
- Request rate, average/p95/p99 response latency.
- Tomcat busy/current threads, connection utilization và queue/rejections.
- Async executor active/core/max/queue, timeout/rejection count.
- DB pool active/pending, SQL latency và slow queries.
- Upstream client pool saturation, retries, timeouts.
- CPU, heap/native memory, file descriptors và GC pauses.

## 15. Dấu hiệu nghẽn và quyết định xử lý

| Triệu chứng | Giả thuyết | Điều tra trước khi tăng threads |
|---|---|---|
| CPU thấp, p99 latency cao, Tomcat busy threads gần max | Workers đang block | Thread dump, DB/client timeouts, locks |
| CPU gần 100%, high runnable threads | CPU bottleneck | Profile CPU, GC, algorithm và oversubscription |
| Tomcat connections cao nhưng busy workers thấp | Keep-alive/idle sockets hoặc async waits | Connection timeout, proxy pools, FD/memory |
| 503/timeouts ở phía proxy nhưng Tomcat CPU thấp | Queue/connection limits hoặc proxy routing | Backlog, maxConnections, proxy queues, network |
| Async timeout tăng, Tomcat workers không bận | MVC async executor/remote event quá chậm | Async pool active/queue, timeout, upstream |
| Hikari pending cao | DB pool/SQL bị nghẽn | DB query plan, pool sizing, transaction duration |
| Queue task executor tăng lâu | Năng lực xử lý thấp hơn arrival rate | Giới hạn queue, reject policy, backpressure |
| Thread count tăng không kiểm soát | Pools mới/unbounded tasks/threads | Thread dump, bean executors, lifecycle |
| Client thấy response dở dang | Disconnect/stream write error | Connection lifecycle, response committed và logs |

**Không nâng đồng thời** maxThreads, maxConnections, acceptCount và DB pool đến các giá trị rất lớn mà không có thí nghiệm. Thay từng biến, giữ traffic profile và quan sát throughput/p95/p99, errors, queue và resource saturation.

## 16. Quy trình benchmark và capacity planning tối thiểu

1. **Chọn workload:** 90% GET nhẹ, 10% I/O blocking, hoặc phân bố phản ánh production.
2. **Đo baseline:** request rate, p50/p95/p99, busy workers, connections, DB pool và CPU.
3. **Tăng concurrency theo bậc:** giữ server và dữ liệu test ổn định, không burst thẳng vào production.
4. **Xác định điểm bẻ cong:** throughput không tăng nhưng latency/errors/queue tăng.
5. **Chụp thread dumps ở điểm nghẽn:** thread nào block, ở driver/API/lock nào?
6. **Thay một giả thuyết:** tối ưu SQL, giảm remote latency, cấu hình async, giới hạn queue hoặc tăng worker hợp lý.
7. **Chạy lại cùng workload:** so sánh percentile và failure rate, không chỉ requests/sec.
8. **Kiểm tra shutdown/cancellation:** tasks và async responses có timeout, executor có dọn dẹp không.

Một request sync chờ 200 ms và request async chờ 200 ms có thể có **end-to-end latency tương đương** trong tải thấp. Sự khác biệt là worker occupancy và năng lực tiếp nhận tải khi nhiều request chờ. Muốn chứng minh lợi ích, phải đo dưới concurrency thích hợp, không chỉ gọi một request bằng curl.

### 16.1. Queueing không phải biện pháp tăng throughput

Hệ thống xử lý được 100 requests/second mà nhận liên tục 150 requests/second sẽ tạo backlog tăng theo thời gian, trừ khi có admission control, backpressure, giảm tải hoặc scale capacity. Tăng queue chỉ trì hoãn lỗi và tăng latency; không làm server xử lý nhanh hơn về mặt vật lý.

Thiết kế có thể cần:
- Kích thước pool phù hợp workload.
- Bounded queues và reject policy rõ.
- Rate limiting/concurrency limits ở edge.
- Timeouts và circuit breakers cho downstream.
- Async I/O phù hợp, tối ưu đường critical path hoặc scale out.

## 17. Spring MVC Servlet khác Spring WebFlux ở đâu?

| Tiêu chí | Spring MVC trên Tomcat Servlet | Spring WebFlux trên Reactor Netty |
|---|---|---|
| Hợp đồng controller chính | Servlet request/response, thường đồng bộ; hỗ trợ async return | Reactive publishers và non-blocking APIs |
| Container | Tomcat/Jetty/Undertow Servlet | Reactor Netty hoặc reactive runtime khác |
| Đọc/ghi request HTTP | Servlet API; NIO ở connector nhưng application I/O có thể blocking | Reactive HTTP codecs và event-loop model |
| Blocking service calls | Thường chiếm Servlet worker; `Callable` chuyển block sang pool phụ | Không được block event-loop; cần isolate blocking library |
| Đợi idle keep-alive connection | NIO socket management, không nhất thiết giữ request worker | Event-loop quản lý nhiều sockets |
| Async request lifecycle | Servlet async start, task executor, ASYNC redispatch | Async là phần tự nhiên của reactive pipeline |
| Tài nguyên cần đo | Workers, connections, queues, DB/client pools | Event-loop latency, blocking tasks, scheduler pools, connections |

**Không nhầm connector NIO của Tomcat với WebFlux event-loop architecture.** Cả hai tận dụng non-blocking network I/O ở một mức độ nào đó, nhưng contract application và cách quản lý blocking work khác nhau.

Ứng dụng Spring Boot có cả `spring-boot-starter-web` và `spring-boot-starter-webflux` thường chọn MVC server theo mặc định; có `WebClient` trong classpath không chứng minh request controller chạy trên Reactor Netty event-loop.

## 18. Lỗi phổ biến cần tránh

1. **Một kết nối = một worker thread:** sai trong NIO keep-alive, đặc biệt HTTP/2.
2. **Một request luôn nằm trên một thread từ đầu đến cuối:** sai với Servlet async/redispatch.
3. **Acceptor/poller chạy Spring controller:** không đúng với kiến trúc Tomcat NIO thông thường.
4. **Connector NIO nghĩa là JDBC không block:** sai; application code vẫn có thể blocking.
5. **maxThreads = maxConnections:** hai đại lượng khác, phục vụ giới hạn khác nhau.
6. **acceptCount là số request trong Spring queue:** backlog TCP connection, chịu ảnh hưởng OS.
7. **Tăng maxThreads giải quyết hết lỗi 503:** còn DB pool, CPU, network, proxy, memory.
8. **Số threads JVM là số HTTP requests đồng thời:** còn acceptors, pollers, schedulers, clients, GC.
9. **Giữ ThreadLocal state qua async call mà không propagate:** dễ mất context hoặc rò data giữa requests.
10. **Tin rằng Callable chạy non-blocking:** Callable có thể block ở executor phụ.
11. **@Async method cộng Future.get() vẫn giải phóng Tomcat worker:** `get()` vẫn block.
12. **DeferredResult tự tạo một thread ngủ để đợi mỗi request:** kết quả thường đến từ external event; không cần một thread riêng cho mỗi request idle.
13. **Một lần filter log “end” nghĩa là response hoàn tất:** sai khi `request.isAsyncStarted()` là true.
14. **MockMvc trả thread name main nên Tomcat không có worker:** MockMvc không chạy connector thật.
15. **Tăng unbounded queue để tránh reject:** latency/tài nguyên có thể phình đến lúc timeout.
16. **Virtual threads làm CPU tasks nhanh hơn:** không đảm bảo, còn giới hạn downstream.
17. **Bật virtual threads trên Java 17:** Java 21+ mới hỗ trợ.
18. **Đo average latency mà bỏ qua p99:** tail latency và queue dễ báo động sớm hơn.
19. **Giả định test curl một request đo được concurrency capacity:** cần controlled load test.
20. **Quên bảo vệ Actuator:** metrics/bean/env endpoints có thể tiết lộ thông tin hạ tầng.

## 19. Checklist trước khi triển khai hoặc tuning

- [ ] Xác nhận đang chạy Servlet web stack, container và connector implementation cụ thể.
- [ ] Vẽ đường đi acceptor → poller → container worker → Filter/DispatcherServlet/controller.
- [ ] Tách số connections, in-flight requests, busy workers và async tasks.
- [ ] Kiểm tra keep-alive và HTTP/2 thay vì giả định 1:1 connection-request.
- [ ] Đánh giá `maxThreads`, `maxConnections`, `acceptCount` cùng giới hạn OS.
- [ ] Đánh giá blocking time của JDBC, outbound HTTP, disk, locks và JSON serialization.
- [ ] Phân biệt Tomcat executor, MVC async executor, `@Async` và scheduler.
- [ ] Nếu dùng `Callable`/`DeferredResult`, đã có timeout, bounded executor/queue và cancellation cleanup.
- [ ] Không kỳ vọng `@Async` kèm `Future.get()` làm servlet request non-blocking.
- [ ] Có logs/request IDs, thread dumps, Actuator/JMX metrics có bảo vệ.
- [ ] Có load test xác định saturation thay vì chỉ dựa vào defaults.
- [ ] Kiểm DB pool, connection pool, CPU và memory trước khi tăng worker threads.
- [ ] Nếu dùng Java 21 virtual threads, đo pinning và nhớ thread pool settings có thể bị bỏ qua.
- [ ] Kiểm tra cùng workload trước/sau tuning, quan sát p95/p99 và error rate.
- [ ] Không tự ý áp dụng thông số thí nghiệm từ bài này vào production.

## 20. Kết luận

Mô hình đồng thời Servlet với Tomcat NIO cần được hiểu theo **ba nhiệm vụ tách biệt**: acceptor nhận kết nối, poller theo dõi socket readiness và worker/executor thực thi HTTP request cùng Spring MVC controller. Nhiều connections có thể idle mà không chiếm worker, nhưng một controller blocking vẫn giữ worker trong thời gian chờ. `Callable`/`DeferredResult` cho phép Servlet request bước vào async lifecycle, giải phóng worker ban đầu; điều đó không tự làm downstream blocking trở thành non-blocking hay miễn phí CPU. Các giới hạn `maxConnections`, `acceptCount`, `maxThreads`, async executor, DB pool và resource budget phải được đánh giá độc lập. Thiết kế đúng bắt đầu bằng việc đo request timeline, worker occupancy, queue và latency dưới tải thực.

## Tài liệu tham khảo

- Apache Tomcat 10.1 — HTTP Connector (NIO, threads, connections, accept backlog): https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
- Spring Boot 3.5 — Common Application Properties (Tomcat thread/connectors): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Framework — MVC Asynchronous Requests (Callable/DeferredResult/ASYNC dispatch): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Boot 3.5 — Task Execution and Scheduling (applicationTaskExecutor): https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.5 — Virtual Threads and SpringApplication: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Jakarta Servlet 6.0 — Specification: https://jakarta.ee/specifications/servlet/6.0/
