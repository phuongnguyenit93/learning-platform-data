# Chẩn đoán cạn luồng, nghẽn kết nối, thiếu bộ nhớ và tác vụ chặn event loop trong Spring Web

## 1. Tại sao bốn vấn đề này dễ bị nhầm lẫn?

Ứng dụng Spring có thể trả HTTP 503, 500, timeout hoặc phản hồi rất chậm dù CPU chưa cao. Nguyên nhân không nhất thiết ở controller vừa xuất hiện trong log. Request đi qua nhiều tài nguyên: luồng tiếp nhận, scheduler, hàng đợi, kết nối HTTP đến dịch vụ khác, JDBC connection, bộ nhớ heap, direct memory và các bước mã hóa/giải mã dữ liệu.

Bốn nhóm sự cố thường tạo ra triệu chứng tương tự:

1. **Cạn luồng (thread starvation):** các luồng cần để làm việc đã bận hoặc chờ quá lâu; request mới xếp hàng, bị từ chối hoặc timeout.
2. **Nghẽn kết nối (connection-pool exhaustion):** hết kết nối HTTP client, JDBC hoặc giới hạn kết nối server; luồng có thể đang chờ lấy connection chứ không thực sự dùng nhiều CPU.
3. **Thiếu bộ nhớ (memory pressure/OOM):** heap, direct buffer, metaspace, native thread stacks hoặc container RSS tiến sát giới hạn, dẫn đến GC liên tục, OOM hoặc container bị kill.
4. **Chặn event loop:** đoạn code blocking chạy trên các thread nhỏ và quan trọng của Reactor Netty/WebFlux, khiến nhiều request không liên quan đều chậm.

Không thể khẳng định nguyên nhân chỉ từ một thông báo `TimeoutException` hay tên thread. Cách làm đúng là **đo triệu chứng → xác định tài nguyên bị giới hạn → lấy bằng chứng độc lập → sửa một nguyên nhân → so sánh lại dưới tải tương tự**.

### 1.1 Hai mô hình chạy phổ biến

| Đặc điểm | Spring MVC + Servlet (thường Tomcat) | Spring WebFlux + Reactor Netty |
| --- | --- | --- |
| Ngữ nghĩa HTTP | Controller thường chạy trên luồng worker Servlet | Handler phản ứng, event-loop non-blocking |
| Số luồng | Thường có pool tương đối lớn để chịu các thao tác blocking | Ít event-loop threads; không được chặn chúng |
| Khi xử lý JDBC blocking | Thường sử dụng worker Servlet, cần giới hạn pool | Cần offload khỏi event loop hoặc dùng driver reactive |
| Khi gọi HTTP outbound | Có thể dùng RestClient/RestTemplate hoặc WebClient | WebClient non-blocking là lựa chọn tự nhiên |
| Điểm nghẽn điển hình | Worker threads, accept queue, HikariCP, outbound HTTP | Event-loop blocking, connection provider, Scheduler, buffer |
| Tín hiệu lỗi | Busy threads, queue tăng, connection wait | Event-loop latency, pool acquire queue, stalled subscribers |

Một ứng dụng MVC **vẫn có thể dùng WebClient** và vì vậy cũng có Reactor Netty event-loop ở phía HTTP client. Không suy luận rằng thấy tên `reactor-http-nio-*` thì toàn bộ ứng dụng chạy WebFlux. Spring Boot có thể chọn MVC khi có cả hai starter, tùy cấu hình triển khai. Cần xem dependency, runtime thực tế và stack trace.

### 1.2 Phân biệt chậm vì CPU và chậm vì chờ tài nguyên

Nếu CPU cao bền vững kèm thread `RUNNABLE` thực hiện tính toán liên tục, tìm hot path, vòng lặp, serialization hoặc GC. Nếu CPU thấp nhưng độ trễ cao, nghi ngờ socket/DB chờ, queue, mutex, pool hoặc thread đợi điều kiện. Cần đo **thời gian chờ và độ sâu hàng đợi** chứ không mặc định “CPU thấp là khỏe”.

Ví dụ một request cần tổng cộng 300 ms, nhưng 240 ms chờ kết nối database, 30 ms chạy SQL, 20 ms business logic và 10 ms chuyển đổi JSON. Tối ưu code Java 20 ms không giải quyết phần lớn độ trễ. Lập timeline của từng pha giúp ưu tiên đúng nguồn lực.

## 2. Quy trình ứng cứu có bằng chứng

Khi tần suất timeout tăng, áp dụng một thứ tự ổn định:

1. **Xác định phạm vi sự cố:** tất cả endpoint hay một route? có xảy ra ở mọi instance/pod? từ khi deploy cấu hình nào? tỷ lệ lỗi, p50/p95/p99, throughput, số request đang chờ và error rate.
2. **Bảo vệ hệ thống đang chạy:** nếu cần, áp dụng giới hạn đầu vào, backpressure, giảm traffic không quan trọng hoặc rollback thay đổi vừa phát hành theo quy trình sự cố. Không tăng tất cả các giới hạn bừa bãi.
3. **Thu thập đồng thời metrics, logs, tracing, JVM evidence:** thời điểm phải đồng bộ. Một ảnh chụp tại lúc hệ thống rảnh có thể không thể hiện nút nghẽn.
4. **So sánh mô hình JVM/HTTP/database:** worker busy, active/pending connections, connection acquire wait, GC pauses, used heap/direct memory, số thread và trạng thái event loop.
5. **Thu nhiều thread dump/JFR có khoảng cách:** phân biệt một thread vô tình đang ngủ với một cụm thread liên tục nghẽn tại cùng lời gọi.
6. **Kiểm tra phụ thuộc bên ngoài:** DB slow query/lock, API upstream latency, DNS, load balancer, proxy, network RTT, CPU limit/GC.
7. **Xây giả thuyết có thể bác bỏ:** nếu connection pool là nút nghẽn, tăng thời gian SQL hoặc giữ response body lâu sẽ làm active=max và pending tăng; nếu sửa code trả connection sớm, pending phải giảm dưới cùng tải.
8. **Thay đổi nhỏ và xác nhận lại:** xem p95/p99, error rate, memory, số pool waiters, resource headroom. Ghi lại quyết định và hệ quả.

Mỗi giả thuyết phải trả lời ba câu: **bằng chứng nào ủng hộ, bằng chứng nào chống lại, quan sát nào thay đổi sau khi sửa?**

### 2.1 Những chỉ số cần chụp ngay

| Nhóm | Chỉ số/chứng cứ nên quan sát | Đọc như thế nào |
| --- | --- | --- |
| HTTP | RPS, in-flight requests, latency p95/p99, 429/503/5xx, timeout theo route | Phân biệt quá tải đầu vào với một downstream bất thường |
| Servlet | Tomcat busy/current/max threads, request queue, connection counts | Busy sát max cùng queue tăng gợi ý starvation ở worker |
| Thread/JVM | thread count, daemon count, thread dump, CPU theo thread, deadlock | Stack cho biết đang block I/O, lock, wait hay chạy CPU |
| JDBC/Hikari | active, idle, pending, acquire timeout, query duration, DB connections | Active sát max + pending tăng là dấu hiệu thiếu connection hoặc giữ connection quá lâu |
| HTTP outbound | Reactor Netty active/idle/pending connections, acquire timeouts, connect/response timeouts | Phân biệt không lấy được connection với remote trả chậm |
| Bộ nhớ | heap used/committed/max, GC pause/rate, direct buffer, RSS/container limit | Phân biệt heap retention với áp lực native/direct |
| Event loop | event-loop responsiveness, thread dump stack, long/blocking tasks, BlockHound | Một blocking call có thể làm chậm nhiều socket dùng cùng loop |
| Phụ thuộc | DB locks, slow SQL, upstream p95, connection resets, DNS | Đừng sửa pool khi nguyên nhân nằm ở server phụ thuộc |

Metrics cần được thu theo thời gian (đường biểu diễn) và theo nhãn hợp lý. Đừng tạo nhãn động như userId, orderId hoặc URL nguyên văn có hàng triệu biến thể; cardinality cao có thể làm hệ giám sát tốn bộ nhớ.

## 3. Thu thập chứng cứ bằng Spring Boot Actuator và JVM

### 3.1 Actuator: biết metric nào đang tồn tại

Spring Boot Actuator và Micrometer cung cấp nhóm HTTP, JVM, datasource, server và một số driver. **Tên metric cụ thể phụ thuộc phiên bản, thư viện, cấu hình**: trước hết gọi `/actuator/metrics` để xem danh sách, rồi truy vấn từng metric có thật.

Ví dụ cấu hình tối thiểu cho môi trường nội bộ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
  metrics:
    tags:
      application: order-api
```

Đây là cấu hình ví dụ cho một ứng dụng Spring Boot có `spring-boot-starter-actuator`; endpoint `prometheus` còn cần registry tương ứng, ví dụ dependency `io.micrometer:micrometer-registry-prometheus`. Mặc định các endpoint metrics không phải lúc nào cũng được expose. Chỉ expose chúng qua mạng quản trị có xác thực/phân quyền và không tiết lộ thông tin runtime cho người dùng công cộng.

Các lệnh kiểm tra ở máy có quyền gọi endpoint quản trị:

```bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/jvm.threads.live
curl -s http://localhost:8080/actuator/metrics/jvm.memory.used
curl -s http://localhost:8080/actuator/metrics/jvm.gc.pause
curl -s http://localhost:8080/actuator/metrics/http.server.requests
```

Không suy diễn kết quả cứng cho các lệnh này: nó phụ thuộc trạng thái runtime. Ví dụ `jvm.memory.used` có thể trả nhiều measurement/tag theo `area` và `id`; muốn phân tách heap, dùng query tag nếu metric hỗ trợ. Với Prometheus, tên metric có thể được đổi sang dấu gạch dưới và hậu tố đơn vị; Actuator `/metrics` dùng **tên meter gốc**.

Các metric hữu ích **nếu được đăng ký**:

- `tomcat.threads.busy`, `tomcat.threads.current`, `tomcat.threads.config.max` cho Tomcat; một số bản/cấu hình cần bật MBean registry.
- `hikaricp.connections.active`, `hikaricp.connections.idle`, `hikaricp.connections.pending` cho HikariCP.
- `jdbc.connections.active` cho một số DataSource được instrument.
- `reactor.netty.connection.provider.active.connections`, `...idle.connections`, `...pending.connections`, `...pending.connections.time` khi metrics của Reactor Netty ConnectionProvider được bật.
- `jvm.memory.used`, `jvm.memory.max`, `jvm.buffer.memory.used`, `jvm.threads.live`, `jvm.gc.pause` và metric HTTP server.

Không nhìn một con số hiện tại rồi kết luận leak: hãy quan sát xu hướng dưới tải, sau GC, khi traffic giảm và so sánh với baseline.

### 3.2 Chụp thread dump bằng jcmd

Dùng JDK 17+/21 có công cụ `jcmd`, chạy bằng tài khoản được phép truy cập process Java tương ứng. Phải biết đúng PID trong VM/container:

```bash
jcmd -l
jcmd <PID> Thread.print -l > thread-1.txt
```

`<PID>` là chỗ điền số process thực; hai dòng trên chỉ là mẫu lệnh, không chạy nguyên placeholder. Tên subcommand được hỗ trợ cần kiểm tra `jcmd <PID> help Thread.print` theo JDK đang sử dụng. Lấy thêm 2–3 bản thread dump cách nhau vài giây **khi sự cố còn xảy ra**; tránh coi stack một thời điểm là bằng chứng nguyên nhân duy nhất.

Đọc thread dump:

- `RUNNABLE` không luôn đồng nghĩa tiêu CPU: thread Java đang trong native socket I/O có thể ở trạng thái RUNNABLE. Kết hợp CPU-per-thread/JFR.
- `WAITING` / `TIMED_WAITING` có thể là chờ bình thường của thread pool; cần xem **đang chờ ở đâu** và có bao nhiêu request bị ảnh hưởng.
- `BLOCKED` thường liên quan monitor/`synchronized`; stack và `locked ownable synchronizers` giúp xem lock.
- Tìm nhiều `http-nio-*-exec-*` mắc ở JDBC, RestTemplate, khóa hoặc gọi remote; tìm `reactor-http-nio-*` mắc ở `Thread.sleep`, `Future.get`, JDBC hoặc blocking client.
- Nếu hàng trăm request chờ một connection pool, thread dump cho thấy nơi **bị chặn**, trong khi metrics pool xác nhận nguyên nhân thiếu tài nguyên.

Trong production, thread dump có thể chứa tên method, đường dẫn tệp và đôi khi dữ liệu nhạy cảm từ stack; lưu bằng quyền hạn chế và dùng quy trình bảo vệ dữ liệu. JFR/thread dump ít xâm lấn hơn heap dump nhưng vẫn có chi phí.

### 3.3 Java Flight Recorder (JFR)

JFR cung cấp timeline về CPU, allocation, GC, locks, socket và nhiều sự kiện Java. Ví dụ ghi ngắn 60 giây trong lúc lỗi tái hiện:

```bash
jcmd <PID> JFR.start name=web-incident settings=profile duration=60s filename=/tmp/web-incident.jfr
jcmd <PID> JFR.check
```

Đường dẫn phải là nơi process có quyền ghi; trên Windows thay `/tmp/...` bằng đường dẫn phù hợp. Với `duration`, bản ghi được hoàn thiện theo lịch cấu hình; có thể dùng `JFR.dump` hoặc `JFR.stop` theo tình huống. Mở kết quả bằng JDK Mission Control (JMC) hoặc công cụ phân tích JFR được phép.

JFR giúp trả lời: thread nào tiêu CPU, socket read nào kéo dài, allocation ở đoạn code nào, GC pause nào trùng p99 spike và có lock contention thực hay không. Dùng `settings=profile` trong thời gian giới hạn vì lượng sự kiện/chi phí lớn hơn `default`; kiểm tra chính sách chẩn đoán của môi trường.

### 3.4 GC, heap và native memory

Những lệnh read-only thường hữu ích (tùy khả năng của JDK và process):

```bash
jcmd <PID> GC.heap_info
jcmd <PID> VM.flags
jcmd <PID> VM.native_memory summary
```

`VM.native_memory summary` chỉ có thông tin đầy đủ nếu **Native Memory Tracking** đã bật khi JVM khởi động, ví dụ `-XX:NativeMemoryTracking=summary`, và có overhead. Không bật tính năng chỉ bằng việc gọi lệnh. Nếu ứng dụng chết bởi OOMKilled từ orchestrator, JVM có thể không kịp ném `OutOfMemoryError` hoặc ghi heap dump; cần xem giới hạn bộ nhớ container và log của nền tảng.

`GC.class_histogram` và `GC.heap_dump` có thể gây tác động đáng kể, dung lượng lớn và chứa dữ liệu nhạy cảm. Chỉ thực hiện theo kế hoạch đã kiểm tra dung lượng, thời điểm và phân quyền. Không kích hoạt heap dump ngay khi máy đang hết đĩa hoặc memory.

## 4. Cạn luồng trên Spring MVC/Servlet

### 4.1 Mô hình cạn luồng

Tomcat giữ một tập worker để chạy HTTP request. Nếu 200 luồng đều chờ DB/HTTP/lock lâu, request mới có thể phải xếp hàng. Độ trễ tăng ngay cả khi CPU thấp.

```text
Incoming requests
        |
        v
Tomcat accept/connection handling
        |
        v
Request workers (busy: 200 / max: 200)
   |      |      |
   v      v      v
 DB wait HTTP wait Lock wait
        |
        v
Pending work accumulates -> high latency/timeouts
```

Một phép ước lượng từ định luật Little cho hệ ổn định:

**Số request đồng thời xấp xỉ = tốc độ đến (request/giây) × thời gian trung bình trong hệ (giây).**

Ví dụ 100 RPS × 0,2 s ≈ 20 request đang xử lý. Nếu dependency chậm lên 2 s nhưng RPS vẫn 100, con số lên xấp xỉ 200. Đây là **ước lượng trung bình**, không phải công thức đặt chính xác thread pool; burst, queue, CPU, xử lý async, nhiều upstream và giới hạn container có thể đổi kết quả.

### 4.2 Bằng chứng cần đối chiếu

- `tomcat.threads.busy` tăng gần giới hạn và request latency/pending queue cùng tăng.
- Thread dumps lặp lại cho thấy nhiều worker đang ở `HikariPool.getConnection`, `SocketInputStream.read`, `HttpURLConnection` hoặc khóa.
- Database metrics có active=max + waiters/pending? Khi đó cạn luồng có thể **là hậu quả của thiếu JDBC connection**.
- CPU gần 100% kèm runnable tính toán liên tục thì không chỉ là I/O starvation.
- Request rate tăng sau deploy/retry storm? Phải đánh giá nguồn tải trước khi tăng thread count.

### 4.3 Cách sửa đúng tầng

**Nếu công việc chỉ chờ HTTP/DB chậm:** tối ưu query, rút ngắn transaction, đặt timeout cho từng dependency, circuit breaker/giới hạn đồng thời, giảm retry đồng loạt. Thêm thread có thể làm số người cùng chờ tăng và đẩy áp lực sang DB.

**Nếu CPU mới là nút nghẽn:** profile hot method, giảm serialize/parse không cần thiết, giới hạn parallelism theo số CPU; tăng worker không làm CPU tạo ra nhiều thời gian tính toán hơn.

**Nếu pool bị queue quá sâu:** đặt giới hạn request và từ chối sớm theo khả năng hệ thống; trả mã phù hợp (ví dụ 429 cho rate limit, 503 cho tạm quá tải) cùng retry-after theo contract nếu có.

**Nếu đang chạy nhiều tác vụ async:** `@Async` và `Callable`/`DeferredResult` cần executor được quản lý, có giới hạn queue, timeout và chính sách rejection rõ ràng. Không dùng pool mặc định vô hạn trong production.

Ví dụ cấu hình `ThreadPoolTaskExecutor` cho công việc bất đồng bộ có kiểm soát:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class WorkerPoolConfig {
    @Bean
    ThreadPoolTaskExecutor blockingWorkExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("blocking-work-");
        return executor;
    }
}
```

Đây là một class cấu hình Spring (đặt trong package đã được component scan), không phải chương trình `main` độc lập. Các số 8/16/100 chỉ để minh họa; capacity cần được xác định bằng profile và limit tài nguyên. Bean này **không tự động đổi Tomcat worker pool** hoặc WebFlux event loop; chỉ được dùng tại nơi ứng dụng inject và gọi executor, hoặc được cấu hình vào thành phần async cụ thể.

## 5. Nghẽn kết nối: phải xác định pool nào

Ứng dụng có thể đồng thời sử dụng nhiều loại kết nối:

- **Inbound server connection/worker:** Tomcat/Netty chấp nhận request từ client.
- **JDBC/HikariCP:** lấy connection từ pool để chạy SQL/transaction.
- **Outbound HTTP pool của Reactor Netty:** `WebClient` dùng `ConnectionProvider` để tái sử dụng HTTP connections.
- **Broker, Redis hoặc client khác:** mỗi driver có giới hạn và metrics riêng.

Một thông báo “connection timeout” có thể xảy ra ở bước DNS, TCP connect, chờ lấy connection từ pool, đợi response, hoặc cơ sở dữ liệu. Không gộp tất cả thành một timeout duy nhất.

### 5.1 HikariCP bị giữ kết nối quá lâu

Dấu hiệu điển hình: active gần maximum, idle bằng 0, pending threads tăng, `SQLTransientConnectionException` hoặc log “Connection is not available, request timed out”. Nguyên nhân có thể là:

- Mỗi transaction kéo dài vì query chậm, row lock hoặc chờ remote HTTP trong khi vẫn giữ DB connection.
- Code mở connection/ResultSet nhưng không đóng đúng cách, hoặc response streaming gắn với transaction kéo dài.
- DB đã đạt giới hạn connection hoặc không cho thêm session.
- Pool quá nhỏ so với số transaction đồng thời **thực sự có nhu cầu**, hoặc tải vượt năng lực DB.
- Retry storm khiến nhiều transaction mới xuất hiện trước khi transaction cũ kết thúc.

`@Transactional` không nhất thiết chiếm connection từ đầu tới cuối trong mọi driver/transaction, nhưng thường có thể **giữ connection khi transaction đang dùng DB**. Tránh gọi API remote nhiều giây bên trong một transaction DB nếu không có lý do rõ.

### 5.2 Connection pool của Reactor Netty

`WebClient` dùng Reactor Netty `HttpClient` có thể hoạt động với pool giữ kết nối theo remote host. Khi các connection đang hoạt động đạt `maxConnections`, yêu cầu tiếp theo có thể chờ trong hàng `pending acquire`. Nếu hết giới hạn thời gian hoặc pending queue đầy, client báo lỗi acquisition trước khi request đến server.

Cần phân biệt:

- `pendingAcquireTimeout`: thời gian chờ lấy connection từ pool.
- `CONNECT_TIMEOUT_MILLIS`: thời hạn thiết lập kết nối TCP.
- `responseTimeout`: thời gian chờ liên quan response theo cấu hình HTTP client.
- `Mono.timeout(...)`: deadline của publisher ở tầng Reactor; có thể cancel upstream.
- `maxIdleTime` / `maxLifeTime`: chính sách lưu/reuse connection, không phải thời gian chờ server xử lý.

Không dựa vào một con số “mặc định pool bao nhiêu” vì thay đổi theo Reactor Netty version, cấu hình global, CPU và cách tạo `ConnectionProvider`. Luôn xem metrics và version runtime.

### 5.3 Ví dụ cấu hình outbound HTTP pool có giới hạn

Đây là cấu hình Spring Boot có `spring-webflux` và Reactor Netty connector, dùng cho `WebClient` outbound kể cả trong ứng dụng MVC:

```java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
class OutboundHttpClientConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider inventoryConnectionProvider() {
        return ConnectionProvider.builder("inventory-api")
                .maxConnections(50)
                .pendingAcquireMaxCount(100)
                .pendingAcquireTimeout(Duration.ofSeconds(2))
                .metrics(true)
                .build();
    }

    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder,
                                 ConnectionProvider inventoryConnectionProvider) {
        HttpClient http = HttpClient.create(inventoryConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
                .responseTimeout(Duration.ofSeconds(3));

        return builder.clone()
                .baseUrl("https://inventory.example")
                .clientConnector(new ReactorClientHttpConnector(http))
                .build();
    }
}
```

Spring quản lý `ConnectionProvider` bean và gọi `dispose` khi context đóng. Phải thay domain bằng địa chỉ cấu hình thật và bổ sung TLS/authn nếu endpoint yêu cầu. `metrics(true)` cần các dependency Micrometer phù hợp. Không chia sẻ connection provider chỉ để “giải quyết” pool cạn khi nhiều đối tác có đặc tính hoàn toàn khác nhau; quản trị tài nguyên theo nhu cầu và xác định owner của pool.

**Các giới hạn 50/100/2s/3s chỉ là ví dụ.** Nếu upstream không trả response trong 3 giây, timeout có thể xảy ra dù còn connection; khi đó tăng `maxConnections` có thể làm upstream quá tải thêm. Cần đo connection active/pending, duration, error code, TLS/connect time và throughput.

### 5.4 Trả connection về pool đúng vòng đời

Một connection HTTP cần body của response được tiêu thụ hoặc giải phóng phù hợp để tái sử dụng. Với `WebClient.retrieve().bodyToMono(...)`, Spring thường quản lý quá trình giải mã và vòng đời body. Với các API cấp thấp `exchangeToMono` / `exchangeToFlux`, phải xử lý body trong function tương ứng; không trả `ClientResponse` để xử lý ngoài vòng đời chức năng mà không hiểu API. Nếu tự làm việc với `DataBuffer` pooled, cần giải phóng dữ liệu không còn sử dụng theo quy tắc của Spring.

**Dấu hiệu leak/giữ connection:** active sát max dai dẳng ngay khi request đã “xong” ở tầng nghiệp vụ, pending liên tục tăng và thread dumps hoặc leak detector chỉ ra response body không được hoàn tất. Nhưng cũng có thể endpoint stream đang cố ý giữ connection; cần tách lưu lượng streaming lâu dài khỏi request ngắn khi thiết kế capacity.

## 6. Thiếu bộ nhớ: heap, direct memory, metaspace và container

### 6.1 Memory của JVM không chỉ là -Xmx

RSS của process Java có thể bao gồm:

```text
Container memory budget / process RSS
       |
       +-- Java heap (-Xmx) / object graph
       +-- JVM metaspace / class metadata
       +-- Code cache / JIT
       +-- Thread stack của platform threads
       +-- Direct / off-heap buffers (NIO/Netty)
       +-- JNI/native libraries & allocator overhead
       +-- JVM runtime structures và vùng native khác
```

Nếu đặt `-Xmx` quá sát memory limit của container, phần native/direct/thread stack không còn chỗ; container có thể bị OOMKilled ngay cả khi Java heap chưa đầy. `jvm.memory.used` không đo toàn bộ RSS. Ngược lại, heap used tăng đến một mức và ổn định sau GC có thể là bình thường, **không tự chứng minh memory leak**.

### 6.2 Phân biệt các loại lỗi

| Triệu chứng | Giả thuyết cần kiểm chứng | Bằng chứng |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | Heap thật thiếu hoặc object bị giữ quá lâu | Heap/GC, allocation rate, histogram và dominator tree khi có heap dump |
| `OutOfMemoryError: Direct buffer memory` | Direct buffer quá nhiều/không giải phóng/giới hạn direct memory | Direct buffer metrics, allocation stack, Netty leak detector, RSS |
| `Metaspace` OOM | Nạp class/classloader quá nhiều hoặc leak classloader | Classloader stats, metaspace metrics, JFR |
| `unable to create native thread` | Quá nhiều thread hoặc giới hạn native memory/PID | Thread count, OS process/thread limit, stack size, RSS |
| Container `OOMKilled` không có Java OOME | RSS/container limit vượt ngưỡng | Orchestrator event, container memory working set, JVM memory breakdown |
| GC pause nhiều, CPU cao | Allocation churn hoặc heap pressure | JFR GC, allocation profile, heap occupancy sau GC |

### 6.3 Spring WebFlux/DataBuffer thường gặp

- `bodyToMono(String.class)` gom toàn body thành một String: nếu response lớn, allocation lớn và heap pressure. Với payload lớn nên parse/stream theo phần, có kích thước tối đa cho từng request.
- `DataBufferLimitException` là ngoại lệ **vượt giới hạn lượng dữ liệu được gom/giải mã**, không nhất thiết có memory leak; đừng tự tăng `maxInMemorySize` lên mức vô hạn để che lỗi dữ liệu quá lớn.
- Với `DataBuffer` kiểu pooled, tự giữ, chuyển, loại bỏ hoặc đọc thủ công mà không release đúng lúc có thể làm tăng direct memory.
- `Flux.cache()`/`collectList()`/`buffer()` trên luồng vô hạn hoặc stream lớn có thể giữ hàng triệu object; `onBackpressureBuffer` không có giới hạn có thể biến nghẽn downstream thành OOM.
- Các kết nối SSE/WebSocket nhiều và tồn tại lâu cần quota, lifetime, giới hạn message size, timeout và cleanup.
- Ghi log body HTTP không giới hạn hoặc giữ exception stack/body lớn cũng tạo áp lực bộ nhớ.

Ví dụ xử lý upload/download phải có giới hạn, chuyển tiếp theo stream khi phù hợp, không gom toàn bộ vào `byte[]` nếu không cần. Chỉ điều chỉnh codec limit sau khi biết payload hợp lệ tối đa và budget memory theo concurrency.

### 6.4 Chẩn đoán leak thật, không nhầm với cache hợp lệ

Một memory leak thường có **live set** tăng dần sau các lần GC và không hồi phục sau khi tải giảm. Điều tra gồm: histogram nhiều lần, JFR allocation, heap dump tại một thời điểm có đủ dung lượng và so sánh dominator graph. Đặt giả thuyết về ai giữ reference (static map, cache không TTL, subscriber/connection chưa dọn, ThreadLocal, classloader, scheduled job).

Với Netty direct memory, heap dump có thể không chứa toàn bộ nội dung native buffer; cần kết hợp direct buffer metrics, Netty leak detection trong môi trường kiểm soát, NMT (nếu bật) và native allocation profile. Không tự động kết luận “không thấy heap leak nên không có leak”.

## 7. Chặn event loop trong Spring WebFlux

### 7.1 Event loop vì sao đặc biệt nhạy cảm?

Reactor Netty thường dùng một số lượng nhỏ thread I/O (ví dụ tên `reactor-http-nio-*`) để xử lý rất nhiều socket. Nếu một callback chạy `Thread.sleep`, gọi JDBC blocking, `Future.get`, `RestTemplate` hoặc I/O file đồng bộ trên event loop, nó giữ thread đó trong lúc chờ. Các kết nối khác cùng event loop không được xử lý kịp, làm p99 tăng mạnh ngay cả khi CPU rất thấp.

```text
Event-loop thread #1:
  socket A -> callback -> Thread.sleep(1000)  [BLOCKED 1 second]
  socket B -> cannot progress
  socket C -> cannot progress

Event-loop thread #2:
  sockets D, E ... continue normally
```

Điểm quan trọng: **“code trả Mono” không tự làm cho mọi thao tác bên trong không chặn**. Nếu gọi JDBC trước khi tạo Mono hoặc gọi blocking method trong `map` đang chạy trên event loop, vẫn có vấn đề.

### 7.2 Ví dụ sai: blocking trước khi tạo publisher

```java
@GetMapping("/customers/{id}")
Mono<Customer> customer(@PathVariable long id) {
    Customer value = legacyJdbcService.loadCustomer(id); // Chặn ngay.
    return Mono.just(value);
}
```

Đây là fragment bên trong WebFlux controller có `legacyJdbcService` (API blocking). Blocking xảy ra ngay khi controller method chạy. `Mono.just` không chuyển công việc sang thread khác; chỉ bọc giá trị đã được tính.

Ngay cả đoạn sau vẫn block nếu subscriber chạy trên event loop:

```java
return Mono.fromCallable(() -> legacyJdbcService.loadCustomer(id));
```

`fromCallable` trì hoãn tính toán đến subscription, nhưng **không tự đổi scheduler**.

### 7.3 Cách bọc một blocking API khi chưa thể chuyển sang reactive driver

```java
@GetMapping("/customers/{id}")
Mono<Customer> customer(@PathVariable long id) {
    return Mono.fromCallable(
                    () -> legacyJdbcService.loadCustomer(id))
            .subscribeOn(Schedulers.boundedElastic());
}
```

Đây là fragment trong một `@RestController` có `legacyJdbcService` và imports `Mono`, `Schedulers`, `GetMapping`, `PathVariable`, `Customer`. `subscribeOn(boundedElastic())` khiến blocking call chạy trên pool dành cho việc có thể chặn, giúp event loop không bị giữ trong lúc đợi.

Đổi scheduler **không làm JDBC trở thành non-blocking**. BoundedElastic vẫn có giới hạn thread/queue; nếu query chậm và lưu lượng quá lớn, queue của boundedElastic lại đầy. Cần giải quyết cả giới hạn DB, query duration, timeout, số việc đồng thời và ngừng phát tác vụ không có nhu cầu.

Nếu dùng `publishOn`, nó chuyển execution downstream từ vị trí tương ứng; `subscribeOn` trên publisher bọc blocking source thường dễ dự đoán hơn cho cách này. Không dùng `Schedulers.parallel()` để chạy I/O blocking lâu vì scheduler đó hướng tới công việc CPU giới hạn thread.

### 7.4 Không chữa bằng block() hoặc subscribe() thủ công

- `.block()` trong WebFlux handler là dấu hiệu sai mô hình; trên Reactor thread được đánh dấu non-blocking, có thể ném `IllegalStateException`. Ở nơi khác nó vẫn có thể làm tắc worker.
- `.subscribe()` thủ công trong controller tách vòng đời lỗi/cancellation khỏi HTTP response; thường nên trả publisher để framework subscribe.
- `CompletableFuture.join()`, `Thread.sleep()`, `LockSupport.parkNanos()`, driver JDBC/Redis đồng bộ hoặc DNS synchronous trong callback cũng đáng kiểm tra.
- `Flux.parallel()` hoặc tăng số scheduler không thay thế limit tài nguyên bên ngoài.

### 7.5 Phát hiện blocking call

Tìm stack như sau trong thread dumps/JFR: `reactor-http-nio-*` đang ở `Thread.sleep`, `SocketInputStream.read`, `java.sql.*`, `Future.get`, `FileInputStream.read` hoặc thư viện đồng bộ. Kết hợp sự gia tăng latency của **nhiều endpoint độc lập** chạy chung event loop.

Trong test, **BlockHound** có thể instrument code để phát hiện blocking call trên thread được đánh dấu non-blocking. Ví dụ ý tưởng:

```java
BlockHound.install();

Mono.delay(Duration.ofMillis(1))
        .doOnNext(ignored -> {
            try {
                Thread.sleep(10); // Chỉ là lỗi chủ động trong test.
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new RuntimeException(error);
            }
        })
        .block();
```

Đây là fragment test có `io.projectreactor.tools:blockhound` (phiên bản tương thích) và `reactor-core`, không phải code đưa vào production. Với JDK 13+ và các phiên bản BlockHound nhất định, công cụ có thể cần JVM flag `-XX:+AllowRedefinitionToAddDeleteMethods`; kiểm tra tài liệu và tương thích JDK đang chạy. BlockHound không phát hiện **mọi** blocking operation, và một test không có lỗi chưa chứng minh toàn ứng dụng không block.

Nếu cần kiểm tra chính sách an toàn trong dự án, dùng JFR + test về độ trễ event loop/CPU, kiểm soát thread names và một test BlockHound độc lập ở môi trường phù hợp; đừng cài agent vô điều kiện trong production.

## 8. Bài thực hành Java 17+: hiểu tác động của thời gian chờ lên độ đồng thời

Trước khi tối ưu pool, cần hiểu quan hệ cơ bản giữa thời gian xử lý và lượng công việc đang trong hệ. Ví dụ này dùng **Java thuần**, chạy được mà không có Spring/Gradle, để ước lượng tải trung bình theo định luật Little. Nó **không mô phỏng scheduler thật** và không đề xuất thông số production.

**Tệp `CapacityEstimateDemo.java`:**

```java
public class CapacityEstimateDemo {

    static double averageInFlight(double requestsPerSecond,
                                  double averageSeconds) {
        if (requestsPerSecond < 0 || averageSeconds < 0) {
            throw new IllegalArgumentException("Non-negative only");
        }
        return requestsPerSecond * averageSeconds;
    }

    public static void main(String[] args) {
        double rps = 100;

        System.out.printf("fast dependency: %.0f requests%n",
                averageInFlight(rps, 0.2));

        System.out.printf("slow dependency: %.0f requests%n",
                averageInFlight(rps, 2.0));

        System.out.printf("after timeout cap: %.0f requests%n",
                averageInFlight(rps, 0.8));
    }
}
```

Lệnh:

```bash
javac CapacityEstimateDemo.java
java CapacityEstimateDemo
```

**Stdout chính xác** (trên môi trường dùng định dạng số dấu chấm cho ví dụ):

```text
fast dependency: 20 requests
slow dependency: 200 requests
after timeout cap: 80 requests
```

Giải thích: ở tốc độ 100 RPS ổn định, tăng thời gian trong hệ từ 0,2 giây lên 2 giây làm số lượng trung bình từ 20 lên 200. Giá trị “after timeout cap” là kịch bản minh họa thời gian trung bình giảm còn 0,8 giây; thực tế áp timeout có thể làm tăng lỗi, retry hoặc hàng đợi. Không nên đặt timeout chỉ để ép phép tính.

**Thực hành tiếp:** chọn một API nội bộ có số liệu test. Đo throughput, p95/p99, pool active/pending, thread dump. Làm chậm dependency có kiểm soát trên môi trường test, quan sát loại tài nguyên bị bão hòa, sau đó khôi phục tốc độ dependency hoặc thêm concurrency limit và đo lại. Không tạo tải bất thường lên hệ thống production.

## 9. Chẩn đoán qua bốn ca điển hình

### 9.1 Case A: Tomcat threads 200/200, CPU 20%

**Hiện tượng:** p99 tăng, HTTP 503/timeout, JVM CPU chỉ khoảng 20%, worker busy gần tối đa. Thread dumps cho thấy nhiều `http-nio-*` gọi `HikariPool.getConnection`. Metrics Hikari active=max và pending tăng.

**Giả thuyết hợp lý:** thiếu JDBC connection do query/transaction giữ connection, worker Servlet chờ nối. **Không** kết luận “Tomcat cần 500 threads”: nhiều threads hơn có thể cùng đợi DB lâu hơn.

**Kiểm chứng:** xem slow query/DB lock, transaction duration, đối chiếu active vs max của Hikari, số pending và DB-side connection/lock; tìm SQL chậm theo traceId.

**Khắc phục:** tối ưu SQL/index, rút ngắn transaction, tránh network call giữa transaction; điều chỉnh concurrency/timeout có hạn; chỉ đổi kích thước pool nếu DB có năng lực phục vụ. Sau sửa, pending giảm và p99 phục hồi.

### 9.2 Case B: WebClient pending connections tăng, HTTP upstream vẫn khỏe

**Hiện tượng:** request outbound fail với pool acquire timeout; metrics Reactor Netty active sát max, pending tăng; cùng lúc server phía xa có latency ổn.

**Khả năng:** giữ connection vì response body chưa được tiêu thụ/đóng, stream sống lâu, max pool quá nhỏ so với concurrency hoặc request fan-out tạo nhiều kết nối đồng thời.

**Kiểm chứng:** số active/pending sau khi traffic giảm, loại endpoint streaming, trace span duration, body consumption path và Reactor Netty metrics. Thử với workload cố định có/không có response body release đúng.

**Khắc phục:** tiêu thụ/release body đúng vòng đời, giới hạn fan-out, tách pool cho stream dài, đặt pending timeout và limit hợp lý, áp dụng backpressure; tăng maxConnections nếu server/upstream có headroom thực sự.

### 9.3 Case C: JVM heap ổn nhưng pod OOMKilled

**Hiện tượng:** heap used ~60% Xmx, GC bình thường, nhưng container RSS sát limit và bị OOMKilled; ứng dụng không ghi `Java heap space`.

**Khả năng:** direct/off-heap buffers, nhiều native thread stacks, metaspace, JVM native allocator hoặc giới hạn container chưa tính memory ngoài heap.

**Kiểm chứng:** JVM heap, `jvm.buffer.memory.used`, số thread, `VM.native_memory summary` (nếu NMT bật), RSS và cgroup limit. Nhìn trend trước khi chết; heap dump **có thể không chứa nguyên nhân** nếu leak ở direct memory.

**Khắc phục:** giảm retention và kích thước buffer, release pooled DataBuffer, giới hạn số connection/stream/thread, chọn budget Xmx và native phù hợp với container, giảm cache/queue không giới hạn.

### 9.4 Case D: WebFlux latency spike nhưng CPU vẫn thấp

**Hiện tượng:** đồng loạt nhiều endpoint phản hồi trễ đúng từng đợt ~1 giây; thread dump cho thấy `reactor-http-nio-*` đang `Thread.sleep(1000)` hoặc gọi JDBC blocking.

**Khả năng:** callback trên event loop bị chặn. Khác với một downstream đơn lẻ chậm, ảnh hưởng lan tới nhiều request trên cùng event loop.

**Kiểm chứng:** thread dumps liên tiếp, JFR hoặc BlockHound trong test; tái hiện khi bật/tắt đoạn blocking trong môi trường kiểm soát.

**Khắc phục:** thay bằng I/O non-blocking thực sự; trong giai đoạn chuyển đổi, dùng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`; áp concurrency limit và timeout cho dependency blocking. Xác minh event-loop latency/p99 phục hồi, đồng thời không đẩy nghẽn sang boundedElastic/DB.

## 10. Phân loại lỗi thường gặp: đừng đoán từ exception

| Lỗi/tín hiệu | Có thể là gì | Cần kiểm chứng thêm |
| --- | --- | --- |
| `TimeoutException` từ `Mono.timeout` | Publisher chưa phát tín hiệu đúng hạn | Nguồn chậm, acquire wait, event-loop block, timeout đặt quá thấp |
| `PoolAcquireTimeoutException` | Chờ connection từ Reactor Netty pool quá hạn | Active/pending/max, response body retention, upstream concurrency |
| `ConnectTimeoutException` | Kết nối TCP chưa thiết lập kịp | DNS, routing, firewall, backlog server, network và remote readiness |
| `ReadTimeoutException` / response timeout | Không nhận response/dữ liệu trong thời hạn | Remote server/stream, network, proxy hoặc timeout config |
| `SQLTransientConnectionException` | JDBC pool không cấp connection kịp | Hikari active/pending, DB locks, transaction duration |
| `DataBufferLimitException` | Vượt ngưỡng aggregate/codec | Payload size/shape, codec limit, streaming design; không đồng nghĩa leak |
| `OutOfMemoryError: Java heap space` | Thiếu heap khả dụng | GC, live set, allocation, cache, heap dominators |
| `OutOfMemoryError: Direct buffer memory` | Direct memory không đủ | Buffers, connection count, release, limit direct memory |
| `IllegalStateException: block() ... non-blocking thread` | Blocking Reactor API trên thread non-blocking | Vị trí `block()`/`blockFirst()` và pipeline |
| Pod `OOMKilled` | Container vượt memory limit | RSS/cgroup/native memory, JVM heap chỉ là một phần |
| 503 tăng cùng thread/queue saturation | Server không đủ năng lực phục vụ tức thời | Pool, backlog, downstream, rate, retries, admission control |

Không dựa hoàn toàn vào tên exception; đọc root cause và toàn stack (loại bỏ dữ liệu nhạy cảm trước chia sẻ). Cùng một HTTP 503 có thể đến từ application, reverse proxy, load balancer hoặc upstream. Cần correlation/trace ID để xác định tầng phát sinh lỗi.

## 11. Những thay đổi dễ làm tình hình xấu hơn

- **Tăng Tomcat maxThreads vô giới hạn:** nhiều request giữ JDBC/socket lâu hơn, native thread stacks tăng, DB chịu tải nặng hơn.
- **Tăng Hikari maximumPoolSize ngay lập tức:** DB có thể hết session, memory và tăng lock contention; pool phải phù hợp giới hạn DB và latency SQL.
- **Tăng Reactor Netty maxConnections rất lớn:** mở nhiều kết nối có thể gây connect timeout hoặc làm upstream quá tải; giải quyết response lifecycle và fan-out trước.
- **Dùng queue không giới hạn:** chuyển overload thành tăng heap, thời gian chờ và OOM thay vì từ chối sớm có kiểm soát.
- **Tắt timeout vô thời hạn:** giữ threads/connections/subscriptions mãi khi dependency chết.
- **Tăng `maxInMemorySize` không có phân tích:** có thể tránh một `DataBufferLimitException` nhưng đổi thành heap OOM khi nhiều request đồng thời.
- **Đưa mọi blocking call vào boundedElastic mà không giới hạn:** không block event loop nhưng vẫn có thể cạn boundedElastic threads/queue hoặc connection pool.
- **Dùng retry đồng loạt không backoff/jitter/idempotency:** khuếch đại traffic trong lúc hệ thống yếu nhất.
- **Tắt logging/metrics toàn bộ để giảm overhead:** mất bằng chứng nguyên nhân; chỉ giảm logging dư thừa, bật observability phù hợp.
- **Chỉ nhìn heap dump khi pod chết:** có thể bỏ qua native memory, socket hoặc thread stack.

Bất kỳ thay đổi pool/timeout/retry nào cũng cần kèm mục tiêu về p95/p99, lỗi, throughput và giới hạn tài nguyên, sau đó đo lại.

## 12. Kiểm thử và diễn tập ở môi trường kiểm soát

### 12.1 Kịch bản 1: DB trì hoãn

Dùng test database hoặc stub repository gây trễ có kiểm soát. Phát một lượng request vừa đủ, ghi lại Hikari active/pending, Tomcat busy và p95. Thử cùng tải với transaction được rút ngắn; xác minh pending giảm. Không tăng traffic vào hệ thống production để tự tạo sự cố.

### 12.2 Kịch bản 2: WebClient pool nhỏ

Tạo một HTTP test server phản hồi trễ (ví dụ WireMock/MockWebServer) và `WebClient` có maxConnections nhỏ, pending queue giới hạn. Gửi request song song, xác nhận metrics pending/acquire timeout khớp lý thuyết; sau đó thực hiện body consumption đúng, giới hạn concurrency và so sánh.

### 12.3 Kịch bản 3: Event-loop blocking

Trong môi trường test, tạo hai endpoint WebFlux, một endpoint có callback cố ý `Thread.sleep`. Gửi đồng thời request vào endpoint nhanh; đo đuôi latency. Sửa endpoint chặn sang `boundedElastic` và kiểm tra request nhanh không còn bị chậm tương tự. Dùng test thời gian có ngưỡng rộng, không assert chính xác từng mili giây.

### 12.4 Kịch bản 4: Memory retention

Mô phỏng cache không TTL hoặc `Flux.cache()` trên luồng tăng mãi với quota test nhỏ; theo dõi heap/live set sau các chu kỳ GC. Loại bỏ giữ tham chiếu, đặt giới hạn/TTL và so sánh. Test direct buffer phải bảo đảm buffer release và cleanup; không tạo leak cố ý trên máy dùng chung/production.

### 12.5 Các assertion nên có

- Khi quá tải, hệ thống từ chối/timeout **trong giới hạn thời gian có chủ đích**, không treo vô thời hạn.
- Khi dependency phục hồi, queue/pending và error rate trở về gần baseline, không còn tích tụ.
- Phát hiện leak bằng dữ liệu qua thời gian, không bằng một snapshot may rủi.
- Tránh tác dụng phụ lặp do retry: idempotency key và trạng thái xử lý nhất quán.
- Không còn blocking call trên event loop trong những luồng đã kiểm soát.
- Sau dừng hoặc hủy stream, connection/allocated buffers được giải phóng.

## 13. Checklist nhanh theo thứ tự kiểm tra

**Khi HTTP response chậm và CPU thấp:**

1. Endpoint nào, instance nào, từ khi nào? Kiểm tra error rate và dependency latency.
2. Tomcat workers busy hay WebFlux event-loop stalls? Spring MVC có đang dùng WebClient phía client không?
3. DB connections hoặc outbound HTTP connections có `active=max`, `pending>0` không?
4. Thread dumps/JFR chứng minh thread chờ cái gì? Có thread đang chặn event loop không?
5. Heap, native RSS và GC có cùng tăng không? Có container OOMKill không?
6. Có một thay đổi cấu hình, retry, fan-out hay cache mới vừa được triển khai?
7. Can thiệp tối thiểu: giới hạn đầu vào, sửa query/response lifecycle/offload blocking, cấu hình timeout thực tế.
8. Đo lại p95/p99, saturation, memory và các chỉ số người dùng quan trọng dưới tải tương đương.

**Khi nghi ngờ memory leak:** xem live set sau GC, heap dump khi đủ an toàn, direct memory, thread count, classloader và object retention. **Khi nghi ngờ event loop:** tìm stack blocking trên `reactor-http-nio-*`, kiểm tra phản hồi của endpoint độc lập và tái hiện có kiểm soát. **Khi nghi ngờ thiếu connection:** chứng minh pending acquire/connection wait và xác định **pool nào** trước khi đổi kích thước.

## 14. Tài liệu chính thức để tra cứu

- [Spring Framework — WebFlux concurrency model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): Servlet blocking model và event-loop, xử lý thư viện blocking.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metrics JVM/HTTP/connection và Actuator metrics endpoint.
- [Reactor Netty — HTTP client connection pool và timeouts](https://projectreactor.io/docs/netty/release/reference/http-client.html): `ConnectionProvider`, queue, timeout và Micrometer metrics.
- [Oracle JDK 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): `jcmd`, thread dumps, JFR, native memory và các công cụ JVM.
- [Oracle JDK 21 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder.html): thu thập và phân tích sự kiện JFR.
- [Spring Framework — DataBufferUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): vòng đời và release của pooled buffers.
- [Spring Framework — DataBufferLimitException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferLimitException.html): nguyên nhân vượt giới hạn aggregate.
- [Project Reactor — FAQ: blocking calls on boundedElastic](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking): bọc nguồn blocking bằng `fromCallable` và `subscribeOn`.
- [Reactor BlockHound](https://github.com/reactor/BlockHound): phát hiện blocking calls trong các thread non-blocking.
