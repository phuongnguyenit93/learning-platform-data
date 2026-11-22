# So sánh cùng một tác vụ trên MVC dùng luồng nền tảng, luồng ảo và WebFlux

**Phạm vi:** Spring Boot → web-runtime → **Thực hành tổng hợp**.

Bài thực hành đặt **cùng một nhiệm vụ HTTP có độ trễ I/O** lên ba mô hình phục vụ request:

1. **Spring MVC + Tomcat + platform threads**: mỗi request đồng bộ thường chiếm một servlet worker thread của pool trong lúc chờ backend.
2. **Chính Spring MVC/Tomcat đó + virtual threads**: vẫn viết code đồng bộ và gọi HTTP blocking như cũ, nhưng Java 21+ cho phép nhiều virtual threads tạm dừng khi chờ I/O mà không giữ carrier thread trong những trường hợp I/O được JVM hỗ trợ.
3. **Spring WebFlux + Reactor Netty + WebClient**: mô tả tác vụ bằng `Mono`, thực hiện HTTP non-blocking, tiếp tục pipeline khi response tới; không block event-loop thread trong khoảng chờ.

Điểm học chính **không phải tuyên bố một mô hình luôn nhanh hơn**, mà là hiểu vì sao **cùng một công việc** có cách dùng threads, giới hạn đồng thời, error propagation và backpressure khác nhau. Bài đưa một Maven multi-module project **chạy được trên JDK 21**, ba HTTP services trong bốn process, unit/integration smoke tests, công cụ benchmark dùng Python standard library, cách đo p50/p95/p99, RPS, CPU, threads, tài nguyên backend, lỗi tải cao và tiêu chí chọn kiến trúc.

**Yêu cầu phiên bản:** Spring Boot 3.5.16 (Spring Framework 6.2), Java **21** dùng chung để so sánh công bằng. Spring Boot 3.5 có minimum Java **17**, nên hai mô hình **MVC platform/WebFlux** có thể chạy từ Java 17 với code tương ứng; riêng **virtual threads cần Java 21+** và `Thread.currentThread().isVirtual()` cũng cần Java 21. Boot 3.5.16 là bản OSS cuối của dòng 3.5 (6/2026); với sản phẩm đang vận hành hãy chọn bản đang được hỗ trợ/bảo trì. Không trộn API của Boot 4.x vào project 3.5.

> **Một phép so sánh hợp lệ:** cả ba gateway gọi **cùng backend** `GET /delay?ms=300` qua localhost HTTP thật, nhận cùng JSON `{"result":"ok","waitMs":300}`, và chỉ khác execution model ở gateway. Backend dùng `Mono.delay` để tạo độ trễ **chờ không chiếm event loop**, giống một downstream HTTP service có response chậm; nó **không** mô phỏng chi tiết database/remote API production. Đây là **latency workload mô phỏng**, không phải chứng nhận throughput của công nghệ.

## 1. Bài toán: request chờ downstream 300 ms

Một client gọi `GET /task?ms=300`. Gateway phải gọi downstream `GET /delay?ms=300`, đợi JSON, rồi trả response với thông tin:
- `mode`: mô hình gateway đang chạy (`mvc` hoặc `webflux`);
- `waitMs`: độ trễ downstream được yêu cầu;
- `backendResult`: giá trị downstream trả về (`ok`);
- `virtualThread`: `Thread.currentThread().isVirtual()` ở vị trí code ghi nhận;
- `threadName`: tên Java thread tại cùng vị trí.

~~~text
                       HTTP GET /task?ms=300
                               │
                               ▼
                       Client / Load Tool
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
    MVC platform          MVC virtual            WebFlux
    Tomcat :8080          Tomcat :8082            Netty :8083
    synchronous           synchronous            reactive Mono
    RestClient            RestClient             WebClient
          │                    │                    │
          └────────────────────┼────────────────────┘
                               │
                    HTTP GET /delay?ms=300
                               ▼
                      WebFlux backend :8081
                 Mono.delay(Duration.ofMillis(ms))
                               │
                      JSON {"result":"ok",...}
                               ▼
                    Gateway returns same schema
~~~

Cùng **tác vụ chức năng** nghĩa là cả ba chấp nhận cùng query parameter, validate cùng giới hạn, gọi backend thực qua socket và kiểm tra cùng nội dung. Chúng **không** nhất thiết trả cùng `threadName`, vì thread model là thứ đang đo.

**Không chọn ba workload khác nhau** (MVC `Thread.sleep(300)`, WebFlux `Mono.delay(300)` và virtual thread gọi SQL) rồi so RPS; như vậy backend CPU, sockets, network, validation và latency semantics đã khác. Ở lab này backend chung dùng `Mono.delay`, còn hai gateway dùng blocking RestClient hoặc non-blocking WebClient để đi đến backend ấy.

## 2. Định nghĩa đúng: concurrency, parallelism, throughput và latency

- **Concurrency (đồng thời):** nhiều requests ở trạng thái đang tiến triển trong cùng khoảng thời gian; có thể đa số chờ I/O.
- **Parallelism (song song thực sự):** nhiều CPU cores cùng chạy instructions một lúc. Threads nhiều không tự tăng số cores.
- **Latency:** thời gian một request từ client tới response; quan tâm p50, p95, p99 hơn chỉ mean.
- **Throughput:** số requests hoàn tất trên một giây (RPS).
- **In-flight:** số requests đang nhận xử lý mà chưa kết thúc.
- **Saturation:** giới hạn nào đang cạn: servlet worker pool, TCP connections, DB pool, downstream, CPU, heap, file descriptors hay event-loop capacity.
- **Backpressure:** downstream/consumer có cơ chế điều tiết lượng công việc upstream phát để tránh cấp phát vô hạn; Reactive Streams có demand signals, **không có nghĩa toàn bộ hệ thống HTTP tự được bảo vệ khỏi overload**.
- **Queueing:** requests không được thực thi ngay vì thread/connection/semaphore/worker limit; tail latency tăng dù service time backend vẫn ~300 ms.

Một quan hệ ước lượng hữu ích ở trạng thái ổn định là **Little’s Law**:

\[
L \approx \lambda W
\]

với `L` là requests trung bình in-flight, `λ` là RPS và `W` là response time trung bình (giây). Ví dụ độ trễ 0,3 giây khiến nhu cầu đồng thời tăng theo RPS. Đây là **hệ quả toán học dưới giả định steady state**, không phải lời hứa một app sẽ đạt một RPS cố định.

### 2.1. Vì sao workload I/O-bound khác CPU-bound?

Khi gateway chờ 300 ms downstream:
- CPU của gateway phần lớn **không cần tính toán**; thời gian mất đi vì chờ network/timer.
- Với platform threads, thread xử lý request thường bị giữ trong trạng thái chờ.
- Với virtual threads, JVM có thể unmount một virtual thread đang chờ I/O được hỗ trợ, trả carrier platform thread cho work khác.
- Với WebFlux, Reactor đăng ký async continuation; khi response đến, event-loop tiếp tục processing pipeline.

Khi nhiệm vụ là mã hóa video hoặc SHA hashing chiếm CPU liên tục, virtual threads không tạo thêm CPU cores, còn WebFlux không tự biến blocking CPU loop thành async. Cần kiểm soát CPU parallelism/work stealing/worker scheduling và benchmark riêng.

### 2.2. Ba mô hình không đồng nhất ở mọi lớp

| Trục | MVC platform | MVC virtual | WebFlux non-blocking |
| --- | --- | --- | --- |
| Server trong lab | Embedded Tomcat | **Cùng embedded Tomcat** | Reactor Netty |
| Controller style | Trả DTO trực tiếp | **Cùng code MVC** | Trả `Mono<DTO>` |
| Downstream client | `RestClient` blocking | **Cùng RestClient` blocking** | `WebClient` reactive |
| Thread chờ downstream | Servlet worker platform thread thường block | Virtual thread chờ; carrier thường được giải phóng | Không cần giữ event-loop worker trong lúc chờ |
| Request processing | Thread-per-request (Servlet) | Thread-per-request conceptually, virtual threads rẻ hơn | Event-loop + callbacks/operators |
| Lỗi programming model | Exceptions đồng bộ | Exceptions đồng bộ | Error signal trong Reactor pipeline |
| Context | ThreadLocal/MDC theo Servlet scope | ThreadLocal vẫn có nhưng nhiều virtual threads | Reactor Context, context propagation |
| Concurrency limit tự nhiên | Worker pool / queue | Backend pools / network / semaphore và resource budgets | Event loop, connection pool, operator concurrency / queues |
| I/O blocking tương thích | Có, nhưng tốn worker | Có, thường hợp với virtual threads | **Không block event loop**; offload khi không tránh được |
| Java minimum | Boot3.5: Java17 | Java21+ | Boot3.5: Java17 |
| Độ phức tạp | Dễ viết/debug imperative | Gần MVC cũ, thêm VT-specific operations | Cần hiểu Mono/Flux, cancellation, scheduling và context |

**Quan trọng:** “MVC + virtual” không phải Reactor WebFlux trá hình. Nó vẫn dùng `DispatcherServlet` và Servlet API, vẫn có synchronized business flow và blocking request/response calls. “WebFlux non-blocking” không tự có virtual threads. Bật `spring.threads.virtual.enabled=true` trong WebFlux không biến Reactor Netty event loop thành một virtual-thread-per-request server.

## 3. MVC dùng platform threads: request bị giữ bởi worker

Mô hình với request đồng bộ:

~~~text
Tomcat acceptor
     └─ HTTP request assigned to http-nio-8080-exec-N (platform)
           ├─ controller method
           ├─ RestClient GET /delay?ms=300
           │    └─ thread waits for network response
           ├─ JSON deserialize
           └─ response to client → thread reused
~~~

**Thread pool hữu hạn** hấp thụ blocking. Khi số in-flight requests tăng vượt số threads có thể chạy đồng thời, requests khác phải chờ từ accept queue/connector hoặc bị reject/timeout. Nếu pool gồm 32 workers và mỗi request đợi downstream khoảng 300 ms, chỉ có ~32 request threads **cùng chờ** theo mô hình đơn giản (không kể các thread pools khác); ứng dụng có thể bị giới hạn bởi thread ceiling trước khi CPU saturate.

Cấu hình ví dụ:

~~~properties
server.tomcat.threads.max=32
spring.threads.virtual.enabled=false
~~~

Đây là setting **cho phần lab MVC platform**. Nó không giới hạn tất cả sources of concurrency (async tasks, connection pools, downstream capacity, socket accept queue). Trong một ứng dụng thật, chỉnh thread max và request timeouts theo load/test, không mặc định càng nhiều threads càng tốt.

### 3.1. Những gì platform threads vẫn làm rất tốt

- Code Java imperative dễ đọc, stack trace theo request.
- Hệ sinh thái Spring MVC/JDBC/servlet filters/channels phong phú.
- Với traffic vừa phải và blocking wait không quá lớn, thread pool thông thường đã đủ.
- Ít code Reactor, không cần thay repository từ JDBC sang R2DBC.
- Nếu CPU/DB/external service mới là bottleneck, đổi threading model chưa chắc giúp gì.

**Không đánh đồng nhiều platform threads với “sai kiến trúc”.** WebFlux và virtual threads không phải yêu cầu bắt buộc cho Spring Boot web runtime.

## 4. MVC dùng virtual threads: code blocking cũ, thread thực thi khác

**Java virtual thread** là `java.lang.Thread`, nhưng được JVM scheduling lên các carrier platform threads. Khi một virtual thread thực hiện **blocking I/O** được JVM hỗ trợ, nó có thể được unmount, carrier trở lại xử lý việc khác. Điều đó giúp mô hình “một thread logic cho một task/request” mở rộng tốt hơn với workload chờ I/O.

Bật trong Spring Boot 3.5:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Điều kiện quan trọng:
1. **Chạy trên JDK 21+**; một JVM Java 17 không thể cung cấp virtual threads dù property có được khai báo.
2. Với **Tomcat/Jetty embedded servlet servers** do Boot quản lý, Boot 3.5 có tích hợp dùng virtual threads cho request processing khi flag enabled. Đây là lý do có thể chạy **cùng `mvc/target/mvc-1.0.0.jar`** hai lần, một lần false, một lần true.
3. Với virtual-thread executor, các property cấu hình kiểu platform pool, ví dụ `spring.task.execution.pool.*`, không còn tác động cùng cách. `server.tomcat.threads.max` cũng **không còn là trần concurrency của virtual request executor** như platform pool; phải giới hạn backend/network/DB một cách riêng.
4. Các threads ảo là **daemon threads**, nên những ứng dụng chỉ còn virtual daemon threads có thể kết thúc JVM dù đang có scheduled tasks; `spring.main.keep-alive=true` giúp JVM tiếp tục sống theo Boot guidance khi đó là yêu cầu.
5. Nếu tự tạo `Executor`/task executor bean, bạn có thể **vô hiệu một phần Boot auto-config mặc định**; kiểm tra executor thực sự, `applicationTaskExecutor` và integrations.
6. Virtual threads không làm cho mọi blocking syscall/library trở nên “tự nhiên non-blocking”. Native/foreign operations, contention, thread-local caches và resource pools vẫn có chi phí.

Trong cùng MVC controller:

~~~java
public Result task(long ms) {
    // Dòng này GIỐNG ở cả hai lần chạy MVC:
    DelayReply remote = client.get()
            .uri("/delay?ms={ms}", ms)
            .retrieve()
            .body(DelayReply.class);

    return new Result("mvc", ms, remote.result(),
            Thread.currentThread().isVirtual(),
            Thread.currentThread().getName());
}
~~~

Đây là **mảnh code**; project đầy đủ ở mục 8. Cùng một blocking RestClient call vẫn diễn ra. Khác biệt nằm ở **thread executor của Tomcat**, không phải chuyển code sang Reactor.

### 4.1. Virtual threads khác thread pool kích thước lớn

Một platform thread thường gắn với một OS thread và stack/OS resources; tạo quá nhiều làm tăng context switching/memory. Virtual thread có stack được JVM quản lý, có thể tạm dừng/cất stack khi chờ và chạy qua các carrier pool threads.

**Đừng pool virtual threads** như platform threads. Nếu cần thực thi nhiều công việc có thể tạo virtual thread per task, ví dụ `Executors.newVirtualThreadPerTaskExecutor()`. Nhưng mục tiêu giới hạn traffic không phải một “pool 50 virtual threads” mà nên dùng **Semaphore/rate limiter/DB pool/connection limits** phù hợp để ngăn downstream quá tải.

~~~java
private final Semaphore slots = new Semaphore(20);

void callLimitedBackend() throws InterruptedException {
    slots.acquire();
    try {
        // Gọi downstream với timeout hữu hạn tại đây.
    } finally {
        slots.release();
    }
}
~~~

Đây là **mảnh minh họa**; import `java.util.concurrent.Semaphore`. Trong API thực, trả 429/503 hoặc queue có deadline thay vì chờ vô thời hạn tại semaphore. Giới hạn `HikariCP maximumPoolSize`/max HTTP connections vẫn có thể là bottleneck **sau khi** giải tỏa giới hạn servlet worker threads.

### 4.2. Pinned virtual threads phải xét theo JDK version

**JDK 21–23:** blocking khi giữ monitor `synchronized` hoặc native/foreign method có thể **pin** carrier thread, làm mất lợi ích về scale nếu thao tác kéo dài/lặp thường xuyên. **JDK 24+** có **JEP 491** cải thiện/loại bỏ loại pinning do Java `synchronized`; native/foreign cases và resource saturation vẫn cần theo dõi. Không áp những chẩn đoán JDK21 nguyên xi cho JDK24+.

Ví dụ **anti-pattern trên JDK 21**:

~~~java
synchronized (lock) {
    callSlowRemoteApi(); // Có thể pin carrier nếu blocking lâu.
}
~~~

Không sửa mọi synchronized chỉ vì có virtual threads; ưu tiên phát hiện bằng profile/JFR, xem chỗ blocking dài thực, rồi chuyển những critical sections cần thiết sang lock strategy phù hợp hoặc thu hẹp scope. Với JDK 21:

~~~bash
java -Djdk.tracePinnedThreads=full -jar mvc/target/mvc-1.0.0.jar \
  --spring.threads.virtual.enabled=true \
  --server.port=8082
~~~

Property diagnostic trên dành cho **JDK 21–23**, có thể bị loại khỏi các JDK mới hơn. Trên JDK24+ sử dụng **JFR `jdk.VirtualThreadPinned`** và thread dump, tránh copy flag cũ bất chấp phiên bản.

### 4.3. ThreadLocal không biến thành Reactor Context

Virtual threads **vẫn hỗ trợ ThreadLocal/MDC** như platform threads. Nhưng nếu tạo một virtual thread mới cho mỗi task, cache expensive objects trong `ThreadLocal` có thể được khởi tạo **rất nhiều lần**; không giống dùng một số ít pooled platform threads. MDC phải được set/cleanup có scope để không giữ dữ liệu nhạy cảm. Với cross-thread `@Async`, vẫn cần propagation của trace/security/request context khi thích hợp.

## 5. WebFlux và event loop: không giữ worker lúc chờ downstream

Spring WebFlux sử dụng Reactor `Mono/Flux` và có thể chạy trên Reactor Netty. Code:

~~~java
return webClient.get()
        .uri("/delay?ms={ms}", ms)
        .retrieve()
        .bodyToMono(DelayReply.class)
        .map(reply -> new Result(...));
~~~

**Không có `.block()`**. WebClient đăng ký network I/O bất đồng bộ và trả một `Mono<Result>`. Reactor Netty xử lý socket events; khi downstream response đến, phần `map` mới thực thi. Trong thời gian chờ ~300 ms, event-loop thread có thể phục vụ nhiều connections khác.

~~~text
reactor-http-nio-* event loop
       ├─ parse request A → subscribe to WebClient A → return
       ├─ parse request B → subscribe to WebClient B → return
       ├─ request C ...
       ├─ backend response B available → map/serialize B
       └─ backend response A available → map/serialize A
~~~

Đây là sơ đồ ý tưởng, không phải lịch scheduler cố định. **`Mono` không có nghĩa mỗi request lập tức tạo thread mới.** Thông thường các operators chạy trên thread đang phát tín hiệu trừ khi có `publishOn`/`subscribeOn`/library scheduling khác.

### 5.1. Nguyên tắc tuyệt đối: không block event loop

Sai khi dùng WebFlux:

~~~java
@GetMapping("/task")
public Mono<String> broken() {
    Thread.sleep(300);              // Blocking request thread!
    return Mono.just("done");
}
~~~

Đây là **phản ví dụ** (Java method trên cần xử lý `InterruptedException` để compile; không copy chạy). Nó giữ thread dùng cho event-loop/handler trong khoảng delay. Cũng nguy hiểm:

~~~java
return webClient.get().uri("/delay")
        .retrieve().bodyToMono(String.class)
        .map(text -> jdbcBlockingRepository.load(text)); // Blocking!
~~~

Nếu JDBC/API blocking không thể thay, offload **cục bộ**:

~~~java
return Mono.fromCallable(() -> blockingRepository.load())
           .subscribeOn(Schedulers.boundedElastic());
~~~

**Đây là mảnh minh họa**, cần `reactor.core.publisher.Mono`, `reactor.core.scheduler.Schedulers`, biến `blockingRepository` và error handling; không tự biến JDBC thành reactive driver. `boundedElastic` có thread/queue caps, không vô hạn. `Schedulers.parallel()` chủ yếu dành cho nonblocking/CPU tasks, không đẩy JDBC/`Thread.sleep` lên đó.

### 5.2. Reactive backpressure không phải nút chống DDoS

Reactor supports **Reactive Streams demand** trong chuỗi xử lý Publisher/Subscriber. Với một HTTP request `Mono` chỉ có một item, backpressure ở tầng signal có ý nghĩa khác pipeline `Flux` hàng triệu events. Dù dùng WebFlux, hệ thống vẫn có:
- Incoming requests không giới hạn nếu ingress không throttle;
- Connection pool max/pending acquire queue;
- Memory pressure từ request bodies và pending subscribers;
- Downstream API rate limits;
- Database pool/transactions/authorization;
- Timeout/retry storms.

Giới hạn fan-out/calls có chủ đích:

~~~java
return Flux.fromIterable(ids)
        .flatMap(id -> webClient.get()
                .uri("/data/{id}", id)
                .retrieve()
                .bodyToMono(Data.class),
                16) // Giới hạn concurrent inner subscriptions.
        .collectList();
~~~

Mảnh minh họa cần `Flux`, `webClient`, `ids` và record `Data`; không nằm trong project lab. `flatMap(..., 16)` **giới hạn đồng thời trong pipeline này**, không tự giới hạn tổng yêu cầu từ mọi clients. Khi có nhiều requests, cần global concurrency/rate limit hoặc bounded server resources.

### 5.3. Có cùng hai web starters thì sao?

Trong Spring Boot 3.5, nếu cùng classpath có `spring-boot-starter-web` và `spring-boot-starter-webflux`, **Spring MVC được chọn mặc định**, vì nhiều MVC apps chỉ thêm WebFlux để dùng `WebClient` outbound. Thử “chuyển sang WebFlux” bằng cách thêm starter nhưng vẫn giữ MVC có thể làm benchmark **chạy lại MVC**.

Bài dùng **hai Maven modules tách biệt**:
- `mvc` chỉ có `spring-boot-starter-web`.
- `webflux` chỉ có `spring-boot-starter-webflux`.
- `backend` cũng WebFlux để tạo delayed async response.

Kiểm tra logs thực: MVC dùng Tomcat, WebFlux mặc định Netty. Đừng đoán chỉ từ response type `Mono` trong một controller.

## 6. Thiết kế thí nghiệm công bằng

### 6.1. Điều giữ nguyên

| Thành phần | Giá trị trong lab |
| --- | --- |
| JDK | **Cùng JDK 21** cho cả ba gateway |
| Boot version | **3.5.16** theo parent Maven BOM |
| Gateway endpoint | `GET /task?ms=300` |
| Backend | **Cùng process** `127.0.0.1:8081` |
| Backend contract | `GET /delay?ms=300` → JSON `{"result":"ok","waitMs":300}` |
| Data volume | Một JSON object nhỏ ở mọi request |
| Authentication | Không có, **localhost-only lab** |
| Timeout | Cần điều chỉnh tương đương khi benchmark thực tế |
| Hardware | Cùng CPU/RAM/JDK/GC limits và tải nền |
| Client concurrency | Cùng một tập mức 1, 10, 50, 100, 200... |
| Measurement | Success count, error count, RPS, p50/p95/p99, CPU/threads/memory |

### 6.2. Điều cố ý thay đổi

- Gateway MVC platform: Tomcat platform worker pool hữu hạn.
- Gateway MVC virtual: same MVC JAR với `spring.threads.virtual.enabled=true`.
- Gateway WebFlux: Reactor Netty + WebClient non-blocking.
- Concurrency behavior / scheduler; đây chính là biến độc lập được nghiên cứu.

**Thận trọng:** MVC dùng blocking `RestClient` và WebFlux dùng non-blocking `WebClient`. Vì thế phép đo tổng thể so sánh **ba execution stacks của một tác vụ** chứ **không cô lập tác động virtual threads đến mức microbenchmark**. Muốn đo riêng tác động virtualization, so **MVC platform vs MVC virtual trên cùng code/JDK/dependencies** là cặp kiểm soát mạnh nhất. MVC vs WebFlux còn khác HTTP client implementation, connection pools, server, JSON/filters; cần ghi rõ khi kết luận.

## 7. Cấu trúc Maven multi-module project runnable

Tạo cấu trúc:

~~~text
same-task-lab/
├── pom.xml
├── backend/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/com/example/backend/
│       │   │   ├── BackendApplication.java
│       │   │   └── DelayController.java
│       │   └── resources/application.properties
│       └── test/java/com/example/backend/
│           └── BackendHttpTest.java
├── mvc/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/com/example/mvc/
│       │   │   ├── MvcApplication.java
│       │   │   └── MvcGatewayController.java
│       │   └── resources/application.properties
│       └── test/java/com/example/mvc/
│           └── MvcContractTest.java
├── webflux/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/com/example/webflux/
│       │   │   ├── WebFluxApplication.java
│       │   │   └── FluxGatewayController.java
│       │   └── resources/application.properties
│       └── test/java/com/example/webflux/
│           └── FluxContractTest.java
└── scripts/
    └── load.py
~~~

**Tại sao ba Maven modules?** Một executable JAR có cả web starters có thể khiến Boot chọn MVC thay vì WebFlux; tách modules giúp rõ classpath và thuận tiện chạy cùng lúc để quan sát. MVC platform/virtual dùng **cùng đúng một module/JAR**, chỉ khác runtime flags. Backend WebFlux chia sẻ bởi tất cả, không dùng riêng một database cho MVC.

**Cấu hình bảo mật lab:** mọi server đều bind `127.0.0.1`; không có login/TLS/circuit breaker, nên **không expose lên Internet**. Thử nghiệm load quá cao phải giới hạn concurrency/total requests để không làm cạn tài nguyên máy cá nhân.

### 7.1. Parent `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>same-task-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>backend</module>
        <module>mvc</module>
        <module>webflux</module>
    </modules>
    <properties>
        <java.version>21</java.version>
    </properties>
</project>
~~~

`<java.version>21</java.version>` bảo đảm code dùng Java21 API `Thread.isVirtual()` compile đúng và cả ba module chạy một runtime Java. **JDK 17 không build được project này** vì cố ý sử dụng Java21 methods; muốn chạy MVC platform/WebFlux trên Java17 cần thay chỗ `isVirtual()` và Maven Java version, rồi không bật virtual threads.

### 7.2. `backend/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>same-task-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>backend</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

Module backend được giữ giống nhau cho mọi gateway. `spring-boot-starter-webflux` mang Netty và Reactor; không thêm servlet starter.

### 7.3. `mvc/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>same-task-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>mvc</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

MVC module sử dụng **RestClient** từ Spring Framework 6.2 qua `spring-web`. Không khai báo Reactor Netty/WebFlux để tránh thay đổi HTTP client selection so với baseline.

### 7.4. `webflux/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>same-task-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>webflux</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

Khi xây dựng bằng parent Maven POM, Spring Boot BOM quản lý các phiên bản Micrometer/Reactor/Tomcat/Netty đồng bộ. Không tự pin Reactor Netty một version xa lạ hoặc vừa add `spring-boot-starter-web` vào WebFlux module vừa tin Netty vẫn là server mặc định.

## 8. Backend WebFlux: một nguồn delay chung

### 8.1. `backend/src/main/java/com/example/backend/BackendApplication.java`

~~~java
package com.example.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BackendApplication {
    public static void main(String[] args) {
        SpringApplication.run(BackendApplication.class, args);
    }
}
~~~

### 8.2. `backend/src/main/java/com/example/backend/DelayController.java`

~~~java
package com.example.backend;

import java.time.Duration;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class DelayController {

    @GetMapping("/delay")
    public Mono<DelayReply> delay(
            @RequestParam(defaultValue = "300") long ms) {

        if (ms < 0 || ms > 3000) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "ms must be 0..3000"));
        }

        return Mono.delay(Duration.ofMillis(ms))
                .map(ignored -> new DelayReply("ok", ms));
    }

    public record DelayReply(String result, long waitMs) {
    }
}
~~~

**Tại sao backend dùng `Mono.delay`?** Nó phát signal sau khoảng thời gian yêu cầu mà **không gọi `Thread.sleep` trên Netty event loop**. Do đó backend có thể xử lý nhiều delayed responses mà không cần mỗi request một platform thread đang ngủ. Nó mô phỏng time-to-first-response của một service chậm và giúp phần gateway là đối tượng chính được so sánh.

**Lưu ý:** `Mono.delay` dùng Reactor Scheduler timer, không phải một HTTP DB query thật. Benchmark này khảo sát overhead và concurrency của **HTTP wait** chứ không chứng minh hiệu năng JDBC/R2DBC. Với `ms=0`, task vẫn qua asynchronous scheduling, nên thời gian phản hồi không thể bằng 0 tuyệt đối.

### 8.3. `backend/src/main/resources/application.properties`

~~~properties
spring.application.name=lab-backend
server.address=127.0.0.1
server.port=8081
~~~

Cấu hình backend giống nhau bất kể gateway mode. Không thay backend implementation khi so sánh ba variants, và không chạy nhiều backend ở các ports khác nhau rồi tưởng tính năng tương đương là đủ để so tài nguyên.

### 8.4. `backend/src/test/java/com/example/backend/BackendHttpTest.java`

~~~java
package com.example.backend;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class BackendHttpTest {

    @LocalServerPort int port;

    @Test
    void delayReturnsExpectedJsonOverRealHttp() {
        String body = RestClient.create().get()
                .uri("http://127.0.0.1:" + port
                     + "/delay?ms=10")
                .retrieve()
                .body(String.class);

        assertTrue(body != null
                && body.contains("\"result\":\"ok\""));
        assertTrue(body.contains("\"waitMs\":10"));
    }

    @Test
    void negativeDelayReturns400() {
        int status = RestClient.create().get()
                .uri("http://127.0.0.1:" + port
                     + "/delay?ms=-1")
                .exchange((request, response) ->
                        response.getStatusCode().value());

        assertEquals(400, status);
    }
}
~~~

Đây là **real socket HTTP test** vì `RANDOM_PORT` khởi động Netty server thật. Không cần một process backend ngoài để chạy JUnit; test context tự có instance backend của nó. `contains(...)` kiểm tra contract JSON tối thiểu, không phụ thuộc thứ tự fields hoặc timestamp không ổn định.

## 9. MVC gateway: một codebase chạy platform hoặc virtual

### 9.1. `mvc/src/main/java/com/example/mvc/MvcApplication.java`

~~~java
package com.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcApplication.class, args);
    }
}
~~~

### 9.2. `mvc/src/main/java/com/example/mvc/MvcGatewayController.java`

~~~java
package com.example.mvc;

import java.util.Objects;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class MvcGatewayController {
    private final RestClient client;

    public MvcGatewayController(
            RestClient.Builder builder,
            @Value("${lab.backend-url:http://127.0.0.1:8081}")
            String backendUrl) {

        // Boot-injected RestClient.Builder giữ customizers/observability.
        this.client = builder.baseUrl(backendUrl).build();
    }

    @GetMapping("/task")
    public TaskResult task(
            @RequestParam(defaultValue = "300") long ms) {

        if (ms < 0 || ms > 3000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "ms must be 0..3000");
        }

        // Gọi HTTP blocking: current MVC request thread chờ JSON.
        DelayReply remote = Objects.requireNonNull(
                client.get()
                        .uri("/delay?ms={ms}", ms)
                        .retrieve()
                        .body(DelayReply.class),
                "backend returned an empty body");

        Thread handlingThread = Thread.currentThread();

        return new TaskResult(
                "mvc",
                ms,
                remote.result(),
                handlingThread.isVirtual(),
                handlingThread.getName());
    }

    public record DelayReply(String result, long waitMs) {
    }

    public record TaskResult(String mode, long waitMs,
                             String backendResult,
                             boolean virtualThread,
                             String threadName) {
    }
}
~~~

**Mấu chốt của thử nghiệm:** **không viết một controller cho platform và một controller khác cho virtual**. Cùng class `MvcGatewayController`, cùng blocking RestClient call và JSON contract. Chỉ runtime flag quyết định Tomcat dùng request handling virtual threads hay platform threads.

`RestClient.Builder` là builder do Spring Boot inject, thay vì `RestClient.create()` trong runtime app; nó giữ các Boot customizers cần thiết cho observability/tracing trong ứng dụng thật. Trong JUnit test client dùng `RestClient.create()` vẫn đúng vì chỉ cần gửi HTTP tới localhost.

**Chú ý production:** default HTTP client connect/read timeouts phụ thuộc request factory/JDK; cần cấu hình timeouts và maximum connections/connection pooling một cách tường minh khi benchmark nghiêm túc. Demo tránh viết custom client factory phức tạp để tập trung so threading; vì thế kết quả **không phải** benchmark so tối ưu client transports.

### 9.3. `mvc/src/main/resources/application.properties`

~~~properties
spring.application.name=lab-mvc
server.address=127.0.0.1
server.port=8080

lab.backend-url=http://127.0.0.1:8081

# Baseline platform mode; CLI virtual instance sẽ override.
spring.threads.virtual.enabled=false

# Dùng worker pool giới hạn để quan sát platform saturation.
server.tomcat.threads.max=32
~~~

Ở virtual mode, `server.tomcat.threads.max` **không có ý nghĩa là “chỉ cho 32 virtual request threads”**. Tomcat virtual executor không hoạt động như fixed platform worker pool đó. Số connections/downstream/CPU vẫn hữu hạn; muốn giới hạn đồng thời thật phải đặt resource bounds khác.

### 9.4. `mvc/src/test/java/com/example/mvc/MvcContractTest.java`

~~~java
package com.example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class MvcContractTest {

    @LocalServerPort int port;

    @Test
    void invalidDelayIsRejectedBeforeDownstreamCall() {
        int status = RestClient.create().get()
                .uri("http://127.0.0.1:" + port
                     + "/task?ms=5000")
                .exchange((request, response) ->
                        response.getStatusCode().value());

        assertEquals(400, status);
    }
}
~~~

Trong test này không khởi động backend; request bị từ chối tại controller do `ms>3000` nên **không gọi RestClient outbound**, chạy độc lập. Positive functional test xuyên hai processes sẽ được kiểm tra bằng `curl` ở mục 12.

### 9.5. Khởi chạy hai MVC instances

Một ứng dụng, hai tiến trình độc lập:
- platform `8080`: `spring.threads.virtual.enabled=false`.
- virtual `8082`: `spring.threads.virtual.enabled=true`, JDK 21.

Không bật hai phiên bản vào cùng process bằng cách toggle property trong một request; thread factory/executor được tạo trong startup, không thay qua query param. Tên `mode= "mvc"` giống nhau vì application stack đều là MVC; **trường `virtualThread` mới chỉ ra execution mode ở vị trí controller**.

## 10. WebFlux gateway: cùng lời gọi backend, không block event loop

### 10.1. `webflux/src/main/java/com/example/webflux/WebFluxApplication.java`

~~~java
package com.example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxApplication.class, args);
    }
}
~~~

### 10.2. `webflux/src/main/java/com/example/webflux/FluxGatewayController.java`

~~~java
package com.example.webflux;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class FluxGatewayController {
    private final WebClient client;

    public FluxGatewayController(
            WebClient.Builder builder,
            @Value("${lab.backend-url:http://127.0.0.1:8081}")
            String backendUrl) {

        this.client = builder.baseUrl(backendUrl).build();
    }

    @GetMapping("/task")
    public Mono<TaskResult> task(
            @RequestParam(defaultValue = "300") long ms) {

        if (ms < 0 || ms > 3000) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "ms must be 0..3000"));
        }

        // Không .block(): event loop không giữ thread khi đợi network.
        return client.get()
                .uri("/delay?ms={ms}", ms)
                .retrieve()
                .bodyToMono(DelayReply.class)
                .map(remote -> {
                    Thread callbackThread = Thread.currentThread();
                    return new TaskResult(
                            "webflux",
                            ms,
                            remote.result(),
                            callbackThread.isVirtual(),
                            callbackThread.getName());
                })
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.BAD_GATEWAY,
                                "backend returned empty response")));
    }

    public record DelayReply(String result, long waitMs) {
    }

    public record TaskResult(String mode, long waitMs,
                             String backendResult,
                             boolean virtualThread,
                             String threadName) {
    }
}
~~~

**So sánh đúng:** cả MVC và WebFlux dùng cùng path, query, validation range, backend JSON và output schema. Nhưng `TaskResult.virtualThread` của WebFlux ghi tại **`map` khi backend signal đến**, không phải một “request owner thread” như Servlet. Một request reactive có thể đổi thread giữa các operators; không suy luận toàn bộ request chạy trên một thread chỉ từ giá trị này.

**Vì sao không gọi `subscribe()` thủ công trong controller?** Spring WebFlux framework **subscribe** vào `Mono` bạn return để điều phối response/error/cancellation. Nếu tự `subscribe()` rồi return ngay, response lifecycle không còn gắn rõ với downstream result, dễ leak và swallow errors. Nếu gọi `block()` trong controller Netty, có thể bị Reactor phát `IllegalStateException` hoặc làm nghẽn event loop.

### 10.3. `webflux/src/main/resources/application.properties`

~~~properties
spring.application.name=lab-webflux
server.address=127.0.0.1
server.port=8083

lab.backend-url=http://127.0.0.1:8081
spring.threads.virtual.enabled=false
~~~

Không đặt `server.tomcat.threads.max` vào WebFlux/Netty để giả định điều khiển Netty: đó là setting Tomcat, không phù hợp Netty event loop. Dùng Reactor Netty client/server pool settings riêng nếu cần tuning sau profiling. Không bật virtual flag ở đây để so **WebFlux nonblocking baseline** rõ ràng.

### 10.4. `webflux/src/test/java/com/example/webflux/FluxContractTest.java`

~~~java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class FluxContractTest {

    @LocalServerPort int port;

    @Test
    void invalidDelayIsRejectedBeforeNetworkRequest() {
        int status = RestClient.create().get()
                .uri("http://127.0.0.1:" + port
                     + "/task?ms=5000")
                .exchange((request, response) ->
                        response.getStatusCode().value());

        assertEquals(400, status);
    }
}
~~~

JUnit gọi **HTTP thật tới Netty RANDOM_PORT**, nhưng với input không hợp lệ nên không cần backend process. Nó giúp xác nhận reactive web server được tạo từ module WebFlux, không phải MockMvc. Những tests đã xây dựng không tự đo throughput hay prove WebFlux tốt hơn; việc đo tải thực hiện riêng bằng script sau.

### 10.5. Tổng hợp mã code path

| MVC platform/virtual | WebFlux |
| --- | --- |
| `TaskResult task(long ms)` | `Mono<TaskResult> task(long ms)` |
| `RestClient.get().retrieve().body(...)` | `WebClient.get().retrieve().bodyToMono(...)` |
| Block current Servlet request thread | No wait-block on event-loop while downstream processes |
| Response dựng sau blocking call trả về | Response dựng trong `map` khi signal tới |
| `throw new ResponseStatusException(...)` | `return Mono.error(new ResponseStatusException(...))` |
| Same path/payload/schema | Same path/payload/schema |
| Run same MVC jar with virtual false/true | Different module with reactive starter |

**Không cần** dùng `CompletableFuture`, `@Async` hay một manual thread pool trong MVC để có virtual request threading; Boot/Tomcat tự điều phối theo flag. Khi muốn làm fan-out nhiều downstream calls trong một request, virtual threads + structured concurrency (JDK API support tùy version) là **một bài toán khác**, không phải yêu cầu của lab.

## 11. Build và chạy đủ bốn processes

Từ thư mục `same-task-lab`:

~~~bash
java -version
mvn --version
mvn clean verify
~~~

**Yêu cầu:** `java -version` và Java mà Maven sử dụng đều trỏ tới **JDK 21+**; `mvn clean verify` sẽ biên dịch cả ba modules, chạy JUnit tests (1 backend class với 2 tests, 1 MVC test, 1 WebFlux test) và build executable JARs. Chạy lệnh thật mới xác nhận kết quả; các outcomes trong bài là **expected** từ source đã liệt kê.

Bốn terminals (Linux/macOS Bash, các lệnh đặt trên một dòng nếu dùng PowerShell):

**Terminal A — backend luôn chạy trên cổng 8081:**

~~~bash
java -jar backend/target/backend-1.0.0.jar
~~~

**Terminal B — MVC platform (8080):**

~~~bash
java -jar mvc/target/mvc-1.0.0.jar \
  --server.port=8080 \
  --spring.threads.virtual.enabled=false
~~~

**Terminal C — cùng MVC JAR nhưng virtual threads (8082):**

~~~bash
java -jar mvc/target/mvc-1.0.0.jar \
  --server.port=8082 \
  --spring.threads.virtual.enabled=true \
  --spring.main.keep-alive=true
~~~

**Terminal D — WebFlux/Netty (8083):**

~~~bash
java -jar webflux/target/webflux-1.0.0.jar
~~~

Chạy **backend trước**, kiểm tra nó ready, rồi khởi động gateways. Nếu cổng đã bận, tìm đúng process với `ss`/`lsof` hoặc dùng các overrides/ports tương ứng và sửa benchmark URLs. Đừng kill ngẫu nhiên process của người khác. Trong Docker, `127.0.0.1` là loopback **riêng của container**; nếu mỗi module chạy một container, cần đặt backend URL thành hostname trong network, mở binding đúng, bảo vệ network bằng policy. Lệnh hiện tại thiết kế cho **cùng máy host**.

### 11.1. Kiểm thử backend trước

~~~bash
curl -i 'http://127.0.0.1:8081/delay?ms=300'
~~~

Expected JSON body (không phụ thuộc key order):

~~~json
{"result":"ok","waitMs":300}
~~~

Có khoảng 300 ms timer delay + HTTP/JVM overhead. Response có thể có HTTP headers khác giữa Java versions. Nếu backend không trả 200, **không** chạy benchmark ngay: khi backend fail, mọi gateway RPS/error metrics đều không phản ánh đúng execution model.

### 11.2. Kiểm thử platform MVC

~~~bash
curl -sS 'http://127.0.0.1:8080/task?ms=300'
~~~

Expected shape, thread name chỉ minh họa:

~~~json
{
  "mode": "mvc",
  "waitMs": 300,
  "backendResult": "ok",
  "virtualThread": false,
  "threadName": "http-nio-8080-exec-1"
}
~~~

`virtualThread:false` cho biết `Thread.currentThread().isVirtual()` trong handler của MVC platform là false. Thread names/sequence không cố định, và một JVM có thể dùng nhiều threads khác cho internal work.

### 11.3. Kiểm thử virtual MVC

~~~bash
curl -sS 'http://127.0.0.1:8082/task?ms=300'
~~~

Expected shape:

~~~json
{
  "mode": "mvc",
  "waitMs": 300,
  "backendResult": "ok",
  "virtualThread": true,
  "threadName": "tomcat-handler-virtual-example"
}
~~~

**Tên thread này là minh họa, không phải guarantee của Spring Boot/Tomcat**. Virtual threads có thể có tên trống hoặc format khác tùy executor. Điều cần assert là **`virtualThread:true`**, chứng minh handler code được thực thi trong virtual thread trên Boot/Tomcat/JDK đang dùng. Nếu false, xem Java version, property flag, server type, custom Executor và auto-config thay vì chỉ tin app log startup thành công.

### 11.4. Kiểm thử WebFlux

~~~bash
curl -sS 'http://127.0.0.1:8083/task?ms=300'
~~~

Expected shape, thread name minh họa:

~~~json
{
  "mode": "webflux",
  "waitMs": 300,
  "backendResult": "ok",
  "virtualThread": false,
  "threadName": "reactor-http-nio-3"
}
~~~

`virtualThread:false` ở đây là **thread chạy operator `map`**, không phải lời tuyên bố rằng WebFlux xử lý mỗi request bằng đúng một platform thread. Một request có thể đi qua nhiều event loops/callback contexts; nếu WebFlux có `publishOn`, tên thread trong `map` sẽ khác.

### 11.5. Smoke-test bằng jq (tùy máy)

Nếu đã có `jq`:

~~~bash
for port in 8080 8082 8083; do
  curl -fsS "http://127.0.0.1:$port/task?ms=300" |
    jq '{mode,waitMs,backendResult,virtualThread,threadName}'
done
~~~

**Kỳ vọng:** cả ba responses có `waitMs=300` và `backendResult="ok"`, nhưng mode/virtualThread/threadName khác. Dấu `$port` trong code sẽ trở thành shell `$port` khi lưu bài; đây là Bash variable, không dùng trực tiếp trong PowerShell.

### 11.6. Kiểm thử input validation

~~~bash
curl -i 'http://127.0.0.1:8080/task?ms=-1'
curl -i 'http://127.0.0.1:8082/task?ms=5000'
curl -i 'http://127.0.0.1:8083/task?ms=5000'
curl -i 'http://127.0.0.1:8081/delay?ms=5000'
~~~

Expected **400 Bad Request** ở cả các endpoints. Error body mặc định của MVC và WebFlux có thể **khác**; bài chỉ bảo đảm status chung cho invalid input, không so exact JSON error details của các framework. Một bài chuyên sâu hơn cần chuẩn hóa error contract và security filters để cross-stack test chặt chẽ.

## 12. Script đo tải dùng Python standard library

Mục tiêu đo **một gateway tại một thời điểm**, không cần cài thư viện benchmark. File `scripts/load.py`:

~~~python
#!/usr/bin/env python3
import argparse
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

parser = argparse.ArgumentParser()
parser.add_argument("--base", required=True)
parser.add_argument("--total", type=int, default=300)
parser.add_argument("--concurrency", type=int, default=30)
parser.add_argument("--ms", type=int, default=300)
args = parser.parse_args()

if args.total < 1 or args.concurrency < 1:
    parser.error("--total and --concurrency must be >= 1")
if not 0 <= args.ms <= 3000:
    parser.error("--ms must be between 0 and 3000")

url = args.base.rstrip("/") + "/task?ms=" + str(args.ms)

def send_one(index):
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.load(response)
            ok = (response.status == 200
                  and data.get("waitMs") == args.ms
                  and data.get("backendResult") == "ok")
            status = response.status
    except urllib.error.HTTPError as exc:
        ok, status = False, exc.code
    except Exception as exc:
        ok, status = False, type(exc).__name__
    elapsed_ms = 1000 * (time.perf_counter() - started)
    return (ok, status, elapsed_ms)

begin = time.perf_counter()
with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
    results = list(executor.map(send_one, range(args.total)))
wall_seconds = time.perf_counter() - begin

latencies = sorted(row[2] for row in results)
success = sum(1 for row in results if row[0])
errors = len(results) - success

def pct(p):
    idx = max(0, math.ceil(p / 100 * len(latencies)) - 1)
    return latencies[idx]

print("url:", url)
print("requests:", len(results))
print("success:", success, "errors:", errors)
print("duration_s:", round(wall_seconds, 3))
print("rps:", round(len(results) / wall_seconds, 2))
print("latency_ms_p50:", round(pct(50), 2))
print("latency_ms_p95:", round(pct(95), 2))
print("latency_ms_p99:", round(pct(99), 2))
print("latency_ms_avg:", round(statistics.mean(latencies), 2))
if errors:
    from collections import Counter
    print("failed_statuses:",
          dict(Counter(str(row[1]) for row in results if not row[0])))
~~~

**Lý do script dùng `ThreadPoolExecutor` phía load client:** đó là **load generator**, không phải gateway execution model. Nó phát đồng thời nhiều HTTP requests qua sockets thật. Không suy ra gateway WebFlux hay virtual thread chỉ vì client Python có threads. Python client có giới hạn GIL/socket creation/CPU nên có thể là **bottleneck của benchmark**; với kết luận production, dùng `wrk`, `hey`, `k6`, Gatling hay load generators đã được hiệu chuẩn/đặt trên máy riêng.

**Lưu ý độ chính xác:** `rps` ở đây là `total requests / wall duration`, bao gồm errors; nếu errors nhiều, luôn báo song song `success` và `errors`, không dùng RPS cao với HTTP 500/timeout làm “thắng”. `p50/p95/p99` đo client-observed latency gồm queueing, HTTP transfer và backend delay, không phải chỉ server processing time. `statistics.mean` chỉ để tham khảo; phân vị tail quan trọng hơn dưới tải.

### 12.1. Chạy baseline nhẹ trước

~~~bash
python3 scripts/load.py --base http://127.0.0.1:8080 \
  --total 60 --concurrency 10 --ms 300

python3 scripts/load.py --base http://127.0.0.1:8082 \
  --total 60 --concurrency 10 --ms 300

python3 scripts/load.py --base http://127.0.0.1:8083 \
  --total 60 --concurrency 10 --ms 300
~~~

Chỉ khi **success=60, errors=0** ở cả ba thì tăng dần. Test nhỏ thường không làm lộ thread-pool saturation, nên sự khác biệt có thể không đáng kể. Đừng bịa số liệu “đạt 10.000 RPS” nếu chưa chạy trên hardware thật.

### 12.2. Các mức load lặp lại

~~~bash
# Mức 1 — low concurrency:
python3 scripts/load.py --base http://127.0.0.1:8080 \
  --total 300 --concurrency 10 --ms 300

# Mức 2 — nhiều requests chờ I/O:
python3 scripts/load.py --base http://127.0.0.1:8082 \
  --total 600 --concurrency 100 --ms 300

# Mức 3 — reactive:
python3 scripts/load.py --base http://127.0.0.1:8083 \
  --total 600 --concurrency 100 --ms 300
~~~

Các dòng trên **minh họa cú pháp**, **chưa phải** ma trận benchmark đối chứng công bằng (chúng khác cả concurrency/total). Muốn so chính thức phải chạy **cả ba variants với cùng `--total`, `--concurrency`, `--ms` ở cùng mỗi mức**, rồi lặp nhiều lần và ghi median/variation. **Đừng kết luận hơn-kém từ ba lệnh có tải khác nhau.**

Ma trận đề xuất:
- `ms=0`: xem baseline overhead ít chờ.
- `ms=50`: wait nhỏ.
- `ms=300`: medium I/O latency.
- `ms=1000`: tail latency lớn.
- Concurrency `1, 10, 32, 50, 100, 200` tùy sức máy.
- Mỗi combination chạy ít nhất vài lần sau warm-up, thứ tự runs luân phiên để hạn chế JVM/JIT/cache bias.

### 12.3. Vì sao có thể thấy platform MVC chạm trần?

Ở platform MVC, `server.tomcat.threads.max=32` khiến một số requests phải chờ worker khi đồng thời 100–200 outbound blocking calls. Khi queueing tăng, p95/p99 tăng dù backend vẫn cố định `ms=300`. Virtual MVC có thể vượt worker ceiling đó, nhưng tiếp theo có thể chạm **HTTP connection pool**, file descriptors, backend throughput, memory hoặc CPU. WebFlux có thể giữ ít event-loop threads trong lúc chờ, nhưng vẫn chịu giới hạn network/client pool/backpressure. **Không dự đoán số RPS cụ thể từ code**; phải đo.

## 13. Cách đọc benchmark đúng: throughput vs latency vs resources

Một bảng ghi số liệu sau khi tự chạy (các ô để điền, **không phải kết quả đo**):

| Mô hình | C | wait(ms) | Thành công | Lỗi | RPS | p50/p95/p99 (ms) | CPU (%) | Threads/RSS |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |
| MVC platform | 100 | 300 | đo | đo | đo | đo | đo | đo |
| MVC virtual | 100 | 300 | đo | đo | đo | đo | đo | đo |
| WebFlux | 100 | 300 | đo | đo | đo | đo | đo | đo |

Khi phân tích:
1. So **success RPS** (không chỉ total RPS).
2. So **p95/p99** tại cùng offered load, không chỉ server’s best throughput.
3. So **CPU % trên cùng core limit**; RPS cao nhưng CPU vượt budget vẫn là trade-off.
4. So **RSS, heap, GC pauses**, thread count và socket/file descriptors.
5. Kiểm tra backend p95/CPU/active requests. Nếu backend đã bão hòa, gateway differences có thể bị che.
6. Kiểm tra client load-generator không cạn CPU/socket hoặc tạo queue nội tại.
7. So **SLO**: ví dụ p95 < target, error rate dưới mục tiêu, memory budget phù hợp.
8. Test **overload recovery** sau khi hạ traffic; một mô hình đẩy được nhiều requests vào downstream nhưng gây timeout storms không phải “thắng”.
9. Cân nhắc developer complexity, debugger/profiling, security/instrumentation, library compatibility và vận hành.
10. Lặp trên JDK version khác trước khi suy luận JDK21 pinning là định luật vĩnh viễn.

### 13.1. Load không phải constant-arrival-rate trong script này

`ThreadPoolExecutor(max_workers=C)` duy trì tối đa C tasks đang chạy. Khi một request chậm, worker Python đợi lâu rồi mới phát request tiếp: đây gần với **closed-loop fixed concurrency**. Nó có thể **che latency collapse** (coordinated omission) so với traffic arrival rate không phụ thuộc thời gian trả response.

Để thử SLO khi spike/request arrivals độc lập, dùng công cụ hỗ trợ **constant arrival rate/open-loop** và theo dõi server queuing. Trình bày kết quả phải ghi load model, không so RPS closed-loop với open-loop như cùng một thống kê.

### 13.2. Chạy trên cùng một máy có tạo nhiễu không?

Có. Nếu cả bốn JVMs luôn chạy trên cùng laptop:
- Backend phải phục vụ tất cả tests nhưng nên chạy **một gateway load tại một thời điểm**.
- Các JVM idle vẫn có GC/JIT/background tasks tiêu thụ tài nguyên.
- OS scheduler, turbo boost, laptop thermal throttling, CPU topology ảnh hưởng số liệu.
- Với virtual threads, carrier parallelism phụ thuộc available processors và JVM/CPU constraints.
- WebFlux Netty event-loop count cũng thường phụ thuộc processor count.
- Thay đổi container CPU quota cần đồng thời ghi JVM `availableProcessors`/thread configs.

Để benchmark nghiêm túc, deploy từng gateway cùng resource limits trên host/pod riêng, backend ổn định riêng, client load-generator độc lập, warm up và lặp có randomization order.

## 14. Quan sát runtime: thread dumps, JFR và metrics

### 14.1. Xác nhận thread model thay vì đoán từ response

Với response JSON của MVC:
- `virtualThread=false` ở port8080;
- `virtualThread=true` ở port8082 khi Java21+ và Boot/Tomcat auto-config đúng;
- response `threadName` chỉ minh họa thread cụ thể.

Với WebFlux:
- field `virtualThread=false` trong `map` có thể hợp lý;
- event-loop threads thường tên gần `reactor-http-nio-*`, nhưng code không nên assert tên exact;
- một request reactive không gắn một thread riêng suốt 300 ms.

Trong production, dùng tracing (HTTP server span, client span) thay vì tự đưa thread names vào public response. Lab trả thread name để học; **không expose runtime implementation hoặc diagnostic endpoints không auth trên Internet**.

### 14.2. JDK 21 thread dumps

~~~bash
jcmd <JAVA_PID> Thread.dump_to_file -format=json threads.json
~~~

Đây là **lệnh mẫu**, phải thay `<JAVA_PID>` bằng process ID đúng. JSON thread dump hữu ích khi có nhiều virtual threads mà `jstack`/truyền thống hiển thị không đủ. Không thu dumps chứa stack/SQL/token secrets rồi chia sẻ public. Trong containers cần JDK tools/attach permissions và target PID đúng namespace.

### 14.3. Java Flight Recorder

~~~bash
jcmd <JAVA_PID> JFR.start name=compare \
  settings=profile duration=30s filename=compare.jfr
~~~

Đo thread activity, CPU samples, allocation, socket I/O và (trên JDK hỗ trợ) `jdk.VirtualThreadPinned`. Chú ý overhead của recorder, kích thước file, security, GC và sampling configuration. JDK21 pinning diagnostics khác JDK24 JEP491; ghi **exact JDK runtime version** trong benchmark.

### 14.4. Spring Boot Actuator và Micrometer

Có thể bổ sung `spring-boot-starter-actuator` trong từng module và metrics export đúng chuẩn. Theo dõi:
- `http.server.requests` timer và exception/status tags (tên meter tùy Boot/config);
- JVM memory/GC/threads;
- Tomcat busy/current threads (platform instance);
- Reactor Netty connection pool/pending-acquire/event-loop utilization (khi bật instrumentation);
- HTTP downstream client metrics, timeouts và retries;
- process CPU, heap allocation và RSS ngoài JVM.

Không dùng `traceId`/`requestId` làm high-cardinality metrics labels; không expose `/actuator/metrics` public. Một request mất ~300 ms trong backend chưa có nghĩa tất cả latency do gateway thread scheduling.

## 15. Lỗi phổ biến và cách tự kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| MVC virtual trả `virtualThread=false` | JDK chưa phải 21+, flag không enabled, Tomcat không dùng executor Boot, custom config | Check `java -version`, startup args, thread executor/server |
| Bật `spring.threads.virtual.enabled=true` nhưng Java17 | Virtual threads không khả dụng | Dùng JDK21+ hoặc giữ MVC platform |
| WebFlux log vẫn hiện Tomcat | Cả MVC và WebFlux starters cùng classpath | Tách modules, bỏ servlet starter khỏi reactive app |
| WebFlux trả `Mono` nhưng RPS rất thấp | Dùng `block()`/Thread.sleep/JDBC trên event loop | Dùng nonblocking APIs hoặc offload boundedElastic |
| MVC platform RPS thấp khi C lớn | 32 Tomcat workers bão hòa vì blocking | Kiểm tra busy threads, queues, downstream latency |
| MVC virtual tăng RPS nhưng DB timeout | JDBC/Hikari pool là bottleneck | Giới hạn concurrency, tune pool và timeouts |
| WebFlux timeout nhiều dưới tải | WebClient connection pool/downstream quá tải | Pool size, pending acquire, backpressure, rate limits |
| Virtual threads quá nhiều, heap tăng | ThreadLocal objects, request objects, unbounded inflight | Tránh per-thread caches, giới hạn admission |
| Virtual JDK21 có carrier pinning | Blocking trong synchronized/native | JFR/profile, refactor hot spots, consider JDK24+ |
| Cấu hình `spring.task.execution.pool.max-size` không có tác dụng | Boot virtual executor không phải platform pool | Dùng admission/semaphore/resource limits |
| WebFlux `map` đọc ThreadLocal thiếu trace | Reactor context không truyền ThreadLocal mặc định qua all operators | Tracing/context-propagation integration |
| Bật VT nhưng WebFlux event loop vẫn platform | WebFlux reactive pipeline không đổi thành VT per request | Đây là expected, không phải bug |
| `curl` trả 502/500 khi backend tắt | Gateway không connect được backend | Chạy backend trước, cấu hình URL đúng |
| Port 8080/8081/8082/8083 đã dùng | Multiple instances/collision | Xác định PID hoặc đổi port chính xác |
| Python load generator reports slow | Client CPU/connection creation bottleneck | Dùng external calibrated load tool |
| p99 tăng ở concurrency cao | Queueing, GC, backend saturation, pool limits | Phân rã spans/metrics/profiling |
| CPU 100%, VT không nhanh hơn | CPU-bound bottleneck | Optimize CPU/processes, không kỳ vọng VT |
| Các client tests trả 400 | Query `ms` vượt 0..3000 | Test trong giới hạn; 400 là hợp đồng |
| WebFlux body rỗng và không lỗi | Upstream body không emit `onNext` | `switchIfEmpty` và error contract |
| Stream bị memory pressure | Fan-out quá lớn, eager buffers | `flatMap` concurrency caps, bounded queues |
| Browser CORS không cho gọi | CORS/Origin policy chưa thiết kế | Không disable security bừa để benchmark |
| Spring MVC WebClient trả Mono, tưởng đã dùng Netty | MVC ưu tiên khi cả starters | Kiểm tra context/server thực |
| Benchmark “WebFlux thắng” sau 1 run | JIT/GC/temp/cache/client noise | Warmup, nhiều runs, error/SLO budgets |
| Side effect tạo trùng do retry khi overload | Không có idempotency | Idempotency-Key/transactional design |
| Java21 virtual vs Java25 WebFlux benchmark | JVM version là confounder | Dùng cùng JDK runtime trước kết luận |

### 15.1. Sự cố `block()/blockFirst()` trong WebFlux

Nếu gọi:

~~~java
String value = someMono.block();
~~~

trên Reactor nonblocking threads, Reactor có thể phát lỗi kiểu “block()/blockFirst()/blockLast() are blocking, which is not supported in thread reactor-http-nio...” hoặc làm giảm throughput. **Không chữa bằng cách tăng event-loop threads thật lớn**. Hãy trả về `Mono` hoặc dùng asynchronous composition `flatMap`/`zip`. Nếu phải dùng legacy blocking JDBC, chỉ cô lập blocking segment trên `Schedulers.boundedElastic()` với giới hạn và timeouts.

### 15.2. Semantics của `Mono.delay` không phải HTTP deadline

Backend `Mono.delay(Duration.ofMillis(ms))` chỉ đợi trước khi emit data; nó không mô phỏng:
- TCP slow-start/retransmission;
- database locks/connection pool waits;
- TLS certificate negotiation;
- network bandwidth;
- read timeout ở HTTP client;
- response streaming nhiều chunks;
- request cancellation/error rate;
- service-side CPU spikes.

Để tăng độ thực tế, thay backend bằng một server có instrumentation, network latency injection, error rate và controlled concurrency; giữ nguyên backend đó qua cả ba gateway variants khi đo.

## 16. Bài tập nâng cao với cùng tác vụ

### 16.1. Thay độ trễ giả lập bằng một API thật

Hướng cải tiến:
1. Backend trả 200 hoặc 503 có xác suất điều khiển được (seed random deterministic để so).
2. Gateway có connect timeout/read/response timeout giống mục tiêu, cùng retry policy.
3. Thêm request ID/traceparent, lấy HTTP client span ở MVC và WebFlux.
4. Đo client connection pool saturation (max connections/pending acquire), not only threads.
5. Thử disconnect client giữa khi backend đang delay; quan sát WebFlux cancellation và MVC blocking call handling khác nhau.
6. Thử large JSON payload/serialization CPU để xem hiệu ứng CPU-bound xen I/O.
7. Thêm TLS trên backend và đo handshake/connection reuse — nhưng giữ cấu hình giống nhau cho mỗi variant.
8. Tạo fault injection 1% backend 500 để xem retry storm và tail latency.

Cần test **service contract**/security/idempotency trước khi coi các kết quả performance là production-ready.

### 16.2. Fan-out hai calls: MVC vs WebFlux

Đây là **bài tiếp theo**, không phải thay đổi code gốc:

**MVC blocking tuần tự:**

~~~java
var a = restClient.get().uri("/delay?ms=300")
        .retrieve().body(DelayReply.class);
var b = restClient.get().uri("/delay?ms=300")
        .retrieve().body(DelayReply.class);
return combine(a, b);
~~~

Hai calls nối tiếp thường cộng độ trễ. Với virtual threads, có thể dùng `Executors.newVirtualThreadPerTaskExecutor()`/`Future` để fan-out đồng thời, nhưng phải manage lifecycle/cancellation/timeouts và downstream rate limits. Java21 structured concurrency vẫn là preview nên không dựa vào nó cho project lab.

**WebFlux nonblocking song song:**

~~~java
Mono<DelayReply> a = webClient.get()
        .uri("/delay?ms=300")
        .retrieve().bodyToMono(DelayReply.class);
Mono<DelayReply> b = webClient.get()
        .uri("/delay?ms=300")
        .retrieve().bodyToMono(DelayReply.class);

return Mono.zip(a, b)
        .map(tuple -> combine(tuple.getT1(), tuple.getT2()));
~~~

Hai mảnh code minh họa, cần `restClient`/`webClient`/`DelayReply`/`combine` được khai báo; không copy vào source chạy ngay. Giữ concurrency limits vì 100 clients × 2 outbound calls tạo nhiều hơn 100 requests backend. Đây là cách phân biệt **cách đồng thời hóa lời gọi** với **cách một HTTP request được phục vụ**.

### 16.3. CPU-bound control

Thay backend delay bằng một endpoint tính toán nặng cùng CPU budget, chạy lại benchmark. **Kỳ vọng định tính:** tăng thread count có thể tăng contention/GC và không tăng giới hạn CPU, WebFlux cũng cần tránh CPU loop dài chiếm event loop; có thể offload bounded CPU executor. Tuy nhiên kết quả thực phụ thuộc payload/cores/JIT, nên không ghi trước số phần trăm.

### 16.4. JDBC/Hikari comparison

Thay backend bằng một DB query blocking:
- MVC platform: JDBC/Hikari bình thường, platform threads có thể chờ pool.
- MVC virtual: JDBC còn blocking ở API level nhưng virtual threads thường chờ thuận lợi hơn; `maximumPoolSize` của Hikari vẫn giới hạn số connections.
- WebFlux: JDBC trên Netty event loop sai; dùng R2DBC reactive driver hoặc isolate JDBC call trong boundedElastic (phải giới hạn pool/queues).
- DB locking/transactions làm biến đổi workload, nên mọi modes cần cùng SQL, indexes, connection pool capacity, DB host và data fixtures.

Đừng gọi JDBC trở thành “nonblocking” chỉ vì mã được wrap trong `Mono.fromCallable`.

## 17. Hướng dẫn lựa chọn thực tế

| Dự án / điều kiện | Lựa chọn thường đáng cân nhắc | Vì sao |
| --- | --- | --- |
| CRUD API Spring MVC + JDBC truyền thống, moderate concurrency | **MVC platform** | Ổn định, đơn giản, đủ hiệu năng khi pool và DB phù hợp |
| MVC + nhiều outbound blocking HTTP/SQL, JDK21+ và cần scale request concurrency | **MVC virtual threads** | Giữ imperative code, giảm chi phí chờ trên request workers |
| Nonblocking end-to-end HTTP/R2DBC/streaming, rất nhiều connections | **WebFlux** | Reactive pipeline, event loops và backpressure composition |
| Legacy blocking libraries xen trong WebFlux | **Xem lại WebFlux hoặc offload boundedElastic** | Không block event loops |
| CPU-intensive processing | **Bất kỳ stack + bounded CPU design** | Tối ưu CPU cores/queue/batching trước |
| Team chưa quen Reactor nhưng có blocking domain code | **MVC virtual/platform** | Giảm lỗi compositional/cancellation context |
| Server-Sent Events, high fan-out reactive flows | **WebFlux có thể phù hợp** | Nonblocking streaming với Reactor operators |
| Strict memory/thread budget | **Đo ba modes** | Thread count thấp không đồng nghĩa RSS thấp hơn |
| TLS/HTTP2/proxy/metrics/security complex | **Chọn stack có tooling phù hợp** | Benchmark đơn giản không bao phủ production constraints |

**Cách quyết định theo bằng chứng:** dựng cùng workload, benchmark các mức concurrency thật, đo p99/error/CPU/DB pool, đánh giá regression và operational complexity. Không rewrite toàn bộ Spring MVC/JPA chỉ vì một biểu đồ của `Thread.sleep`; cũng không mặc định virtual threads đã giải quyết rate limiting và circuit breaker.

### 17.1. Checklist trước khi bật virtual threads production

- [ ] JDK21+ (ưu tiên JDK LTS đã vá) và Spring Boot version được hỗ trợ.
- [ ] Xác nhận servlet request handler thực sự là virtual bằng instrumentation/`Thread.isVirtual()`.
- [ ] Benchmark p95/p99/RPS/CPU/heap với cùng workload như platform baseline.
- [ ] Kiểm tra HTTP connection pools, HikariCP, downstream quotas, file descriptors.
- [ ] Theo dõi pinning nếu JDK21–23; JDK24+ có JEP491 nhưng vẫn monitor native cases.
- [ ] Kiểm tra ThreadLocal/MDC/security context và per-thread caches.
- [ ] Thiết lập admission/rate limits thay vì “virtual threads không giới hạn”.
- [ ] Timeout, cancellation/retry/idempotency rõ ràng.
- [ ] Kiểm tra `@Async`/custom executors và scheduler keep-alive property.
- [ ] Test graceful shutdown với in-flight requests và resource cleanup.
- [ ] Không dựa vào `spring.task.execution.pool.*` như giới hạn virtual threads.

### 17.2. Checklist trước khi chuyển WebFlux

- [ ] Controller thực sự chạy trên **WebFlux**, không phải MVC có thêm dependency WebFlux.
- [ ] Mọi outbound I/O chính dùng client nonblocking, không `block()` ở event loop.
- [ ] Database driver R2DBC hoặc offload blocking cùng limits rõ.
- [ ] Biết dùng `map`, `flatMap`, `zip`, `onErrorResume`, `timeout`, cancellation.
- [ ] Quản lý Reactor Context/trace/security context thay vì giả định ThreadLocal tự lan truyền.
- [ ] Bound concurrency/fan-out, connection pools/pending acquisitions, body buffering.
- [ ] Test WebFilter/SecurityWebFilterChain khác với Servlet Filter/SecurityFilterChain.
- [ ] Có integration tests với Netty và proxy/streaming thực.
- [ ] Benchmark dưới traffic/service time giống production, không chỉ microbenchmark delay.
- [ ] Team có khả năng debug Reactor stack traces và operator assembly.

## 18. Câu hỏi tự kiểm tra và đáp án

1. Tại sao 3 giải pháp phải gọi cùng backend HTTP để so sánh?
2. Spring Boot 3.5 minimum Java bao nhiêu; virtual threads cần Java nào?
3. Ở MVC platform, một blocking RestClient call giữ loại thread gì?
4. Ở MVC virtual, RestClient có tự trở thành API nonblocking không?
5. Virtual thread khi chờ I/O được hỗ trợ có thể trả lại tài nguyên nào?
6. Tại sao virtual threads không tự tăng hiệu năng CPU-bound?
7. Bật property nào trong Boot 3.5 để dùng virtual threads?
8. Vì sao nên cân nhắc `spring.main.keep-alive`?
9. Trong Boot MVC virtual, `server.tomcat.threads.max=32` có còn là trần 32 virtual threads không?
10. Vì sao không nên pool virtual threads như platform threads?
11. Bên cạnh virtual threads, phải giới hạn tài nguyên nào để bảo vệ DB?
12. JDK21–23 pinning khác JDK24+ ở synchronized như thế nào?
13. WebFlux xử lý chờ HTTP response mà không giữ event loop ra sao?
14. Vì sao `Mono.just(blockingCall())` không làm blockingCall nonblocking?
15. `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` giúp gì?
16. BoundedElastic có bảo đảm vô hạn threads và memory không?
17. Khi cả MVC và WebFlux starters đều trên classpath Boot3.5 chọn gì?
18. Tại sao WebFlux response thread name không chứng minh toàn bộ request chạy trên một thread?
19. Vì sao `.block()` không nên nằm trong WebFlux request handler?
20. Tác dụng của `flatMap(publisher, 16)` là gì, và điều nó **không** giới hạn?
21. Vì sao benchmark lỗi HTTP 500 vẫn có RPS cao là kết luận nguy hiểm?
22. p95/p99 quan trọng hơn mean ở traffic queueing như thế nào?
23. Vì sao tăng concurrency của load generator có thể làm client thành bottleneck?
24. Little’s Law mô tả quan hệ nào?
25. Script Python `ThreadPoolExecutor` phía load client có nghĩa gateway dùng platform threads không?
26. Khi MVC virtual RPS cao nhưng DB timeout, nguyên nhân có thể nằm ở đâu?
27. Vì sao `Mono.delay(300ms)` không đại diện đầy đủ JDBC?
28. Ba mô hình có cùng error response body mặc định không?
29. `RestClient.Builder` và `WebClient.Builder` do Spring Boot inject có lợi gì?
30. Vì sao bật VT trên WebFlux không tự chuyển Reactor Netty event loop thành virtual-thread-per-request?
31. Khi MVC platform/virtual so sánh bằng cùng JAR, biến khác biệt chính là gì?
32. Khi so MVC với WebFlux, những library/server changes nào là confounders?
33. Khác nhau giữa closed-loop fixed-concurrency và open-loop arrival-rate là gì?
34. Trong production, chọn stack dựa trên RPS lớn nhất hay p99/SLO/error/resource budget?
35. Nếu một API cần retry một POST sau overload, vì sao cần idempotency?
36. Tại sao `@WebMvcTest` không đủ để chứng minh thread model runtime?
37. Nếu muốn biết pinning/virtual thread count thực, dùng công cụ JVM nào?
38. CPU-bound WebFlux operator kéo dài nên chạy trên event loop không?
39. Dùng JDBC trong virtual MVC có loại bỏ giới hạn connection pool không?
40. Khi benchmark có WebFlux/virtual nhưng client đếm nhiều errors, có phải hệ thống scale tốt hơn không?

**Đáp án trọng tâm:** (1) Cô lập tác vụ/latency downstream. (2) Boot Java17, VT Java21+. (3) Platform servlet worker. (4) Không, vẫn blocking API trên virtual thread. (5) Carrier OS/platform thread. (6) Số cores không tăng. (7) `spring.threads.virtual.enabled=true`. (8) Virtual threads là daemon. (9) Không phải trần virtual executor. (10) Tạo per-task, giới hạn downstream bằng semaphore/pools. (11) Connection pool, rate limiter, quota. (12) JDK24/JEP491 cải thiện pinning monitor. (13) Event loop tiếp tục khi asynchronous network pending. (14) Blocking đã xảy ra trước Mono assembly. (15) Offload blocking khỏi event loop. (16) Không, có caps. (17) MVC/SERVLET. (18) Reactive có callbacks/schedulers. (19) Chặn event loop/IllegalStateException. (20) Concurrent inner subscriptions trong pipeline đó, không phải global admission. (21) Errors có thể hoàn tất nhanh gây RPS giả. (22) Phản ánh tail under queue. (23) Python/socket/CPU resource hạn chế. (24) Inflight ≈ throughput × latency. (25) Không, chỉ test client. (26) Hikari/downstream saturation. (27) Chỉ timer wait, không DB/lock. (28) Không. (29) Giữ Boot instrumentation/customizers. (30) Reactor event loops vẫn nonblocking. (31) Flag + request executor. (32) Tomcat vs Netty, RestClient vs WebClient, pools. (33) Completion-driven vs arrivals độc lập. (34) SLO/error/cost. (35) Side effect có thể đã commit trước timeout. (36) MockMvc không mở HTTP server thật. (37) JFR, jcmd thread dump. (38) Không, offload CPU bounded. (39) Không, DB pool vẫn giới hạn. (40) Không.

## 19. Tài liệu chính thức

- Spring Boot 3.5 — **Virtual Threads** (`spring.threads.virtual.enabled`, `spring.main.keep-alive`, JDK21+): https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 — **Task Execution and Scheduling**, MVC async/`applicationTaskExecutor` và executor auto-config: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.5 — **Reactive Web Applications**, WebFlux/Netty, MVC priority when both starters: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5 — **Servlet Web Applications**, Tomcat/MVC: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — **Embedded Web Servers**, different Servlet/Reactive HTTP servers: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5 — **System Requirements**, Boot 3.5.16 Java17 minimum: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Framework — **Spring WebFlux Concurrency Model and Blocking I/O**: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- Project Reactor — **Threading and Schedulers**, boundedElastic/parallel/event-loop caveats: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Oracle Java 21 — **Virtual Threads Developer Guide**, carriers, I/O blocking, semaphore, ThreadLocal: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- OpenJDK — **JEP 444: Virtual Threads**: https://openjdk.org/jeps/444
- OpenJDK — **JEP 491: Synchronize Virtual Threads without Pinning (JDK24)**: https://openjdk.org/jeps/491
- Spring Boot 3.5.16 release, **End of OSS Support**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
