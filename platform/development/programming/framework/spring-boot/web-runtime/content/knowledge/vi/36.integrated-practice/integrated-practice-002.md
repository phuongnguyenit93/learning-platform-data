# Xây dựng API Spring WebFlux có dữ liệu theo luồng và kiểm soát mã chặn luồng

## 1. Mục tiêu của bài thực hành tổng hợp

Spring WebFlux là web stack hỗ trợ **non-blocking I/O** và mô hình lập trình dựa trên Reactive Streams. Tuy nhiên, một controller trả về `Flux<T>` không tự động làm mọi công việc thành non-blocking: `Thread.sleep`, JDBC đồng bộ, `RestTemplate`, `Future.get`, `Files.readAllBytes`, `Mono.block()` hoặc thư viện client đồng bộ vẫn có thể chiếm thread đang xử lý request. Nếu mã đó chạy trên một **Reactor Netty event-loop**, một request chậm có thể gây chậm hàng loạt kết nối dùng cùng event loop.

Bài học thuộc **Thực hành tổng hợp** trong module **Spring Boot - web-runtime**. Ta xây dựng một API có **hai cách phát dữ liệu theo luồng** và một endpoint làm cầu nối tới thư viện đồng bộ cũ, có **giới hạn tài nguyên**:

1. `GET /api/readings/sse` phát sự kiện cảm biến bằng **Server-Sent Events** (`text/event-stream`).
2. `GET /api/readings/ndjson` phát từng object JSON theo dòng bằng **NDJSON** (`application/x-ndjson`).
3. `GET /api/legacy/{sku}` mô phỏng đọc kho hàng từ một API đồng bộ, bao `Mono.fromCallable(...)` và `subscribeOn(...)` với **custom boundedElastic Scheduler**; tuyệt đối không sleep/block trên Netty event loop.
4. `GET /api/readings/stats` quan sát **active/cancelled subscriptions** trong demo.
5. Bộ **unit tests với StepVerifier**, **slice tests với @WebFluxTest** và **HTTP integration tests @SpringBootTest(RANDOM_PORT)** kiểm stream, validation, cancellation và offloading.

Dự án mẫu dùng **Java 17+, Spring Boot 3.5.16, Reactor Netty, reactor-test, JUnit Jupiter, Mockito**. Phiên bản 3.5.16 được cố định để giữ import/API nhất quán với Boot 3.5, nhưng đây là **bản OSS cuối của dòng 3.5.x** theo thông báo Spring (25/06/2026). Với sản phẩm mới đưa vào production, chọn dòng Boot còn hỗ trợ và bản vá mới phù hợp; khi nâng lên Boot 4.x hãy kiểm tra thay đổi test modules/packages.

Sau khi học, bạn phải trả lời được:

- Dữ liệu được đưa ra client **dần dần** hay bị `collectList()` gom hết trước khi trả?
- Source là **cold** (mỗi subscriber nhận stream riêng) hay **hot** (chia sẻ producer)?
- Có gì xảy ra khi client ngắt kết nối hoặc subscriber `cancel()`?
- Thread nào thực sự chạy một lời gọi chặn? `subscribeOn` khác `publishOn` thế nào?
- Vì sao một bounded scheduler vẫn có thể queue đầy, và khi timeout có chắc underlying blocking I/O đã dừng chưa?
- Trường hợp nào dùng SSE, NDJSON, WebSocket, `Mono` một giá trị, hoặc MVC thay vì WebFlux?
- Một test xanh bằng mock exchange có chứng minh Netty thực sự phát chunks và giải phóng tài nguyên không?

**Quy tắc quan trọng:** trả về `Flux` chỉ là **API shape**. Tính reactive/non-blocking phụ thuộc mọi thao tác thực thi bên trong pipeline, từ request handler, persistence, HTTP client, codec, scheduler đến downstream service.

## 2. Kiến trúc của bài thực hành

```text
HTTP Client / curl -N / WebTestClient
                  |
                  v
          Reactor Netty server
            WebFlux WebHandler
                  |
          StreamingController
         /        |         \
        /         |          \
GET SSE       GET NDJSON      GET /legacy/{sku}
text/event-   x-ndjson              |
stream            |                LegacyBridge
        \         /                  |
        ReadingStreamService         Mono.fromCallable
        Flux.interval + take         .subscribeOn(custom boundedElastic)
        map -> SensorReading          |
        defer + doFinally            LegacyInventoryClient
         |         |                  (Thread.sleep demo ONLY)
    active gauge  cancel counter
```

WebFlux có thể multiplex nhiều request I/O-bound với số ít event-loop threads. Nhưng chương trình không thể tạo thêm CPU cores hay capacity database chỉ bằng cách dùng `Mono`/`Flux`.

### 2.1. SSE so với NDJSON và JSON array

| Hình thức | Media type | Cách dữ liệu tới client | Trường hợp phù hợp |
| --- | --- | --- | --- |
| JSON array | `application/json` | Thường encode theo một document JSON hoàn chỉnh; người đọc body có thể đợi kết thúc | Danh sách nhỏ, finite |
| SSE | `text/event-stream` | Nhiều event `id`/`event`/`data` theo luồng HTTP một chiều server→client | Progress, notifications, logs, live dashboard |
| NDJSON | `application/x-ndjson` | Mỗi dòng là **một JSON value độc lập**; nhiều dòng liên tiếp | Stream records/analytics/events tới máy khách |
| WebSocket | WebSocket protocol | Full-duplex messages hai chiều | Chat, interactive bidirectional updates |

SSE thường dùng browser `EventSource`, có reconnect semantics và hỗ trợ `Last-Event-ID` ở giao thức; **demo này chỉ đánh số id**, không lưu/replay lịch sử sau reconnect. Nếu nghiệp vụ cần resume chính xác, server phải có event log bền vững và logic nhận `Last-Event-ID`, không thể chỉ thêm `.id(...)`.

NDJSON không phải một JSON array: body có thể như sau, mỗi object kết thúc bằng newline:

```text
{"sequence":1,"celsius":20.0,"source":"sensor-demo"}
{"sequence":2,"celsius":20.5,"source":"sensor-demo"}
{"sequence":3,"celsius":21.0,"source":"sensor-demo"}
```

Nếu client dùng `JSON.parse` trên toàn body như **một** JSON document, nó có thể thất bại. Client NDJSON phải đọc từng line hoặc dùng streaming decoder phù hợp. Tương tự, SSE body không thể xử lý như JSON array thông thường.

### 2.2. Streaming không đồng nghĩa “mỗi dòng lập tức hiện ở màn hình”

Thời điểm client thấy từng event còn bị ảnh hưởng bởi TCP buffers, kernel scheduling, codecs, compression, reverse proxy buffering, HTTP/2 flow control, mobile network và behavior của client library. `curl -N` giảm buffering phía curl, **không vô hiệu hóa buffering ở mọi proxy**. Vì vậy cần kiểm real HTTP stream, chứ không chỉ test publisher phát nhiều values.

## 3. Nền tảng Reactive Streams đủ để viết mã đúng

Các tín hiệu cơ bản của một `Flux<T>`:

```text
subscribe
  |
  +-- request(n) từ downstream (backpressure demand)
  |
  +-- onNext(value) 0..N lần
  |
  +-- onComplete() HOẶC onError(error)
  |
  +-- cancel() từ subscriber (không phải onComplete)
```

Một `Mono<T>` phát tối đa một value, hoặc complete rỗng, hoặc error. `Flux<T>` có nhiều values. Publisher có thể **cold** (mỗi subscription tạo luồng riêng) hoặc **hot** (nhiều subscribers chia sẻ nguồn đang hoạt động).

Một controller trả `Flux<SensorReading>` **không nên tự gọi** `subscribe()`. WebFlux chịu trách nhiệm subscribe theo response lifecycle. Nếu tự `subscribe()` để “bắt đầu xử lý” rồi trả `Mono.empty()`, lỗi bất đồng bộ có thể không truyền tới HTTP response, dữ liệu không gắn cancellation, và bạn có thể vô tình tạo duplicate side effects.

Các phép toán quan trọng:

- `map`: biến đổi value trong pipeline, không dùng cho blocking I/O.
- `flatMap`: phối hợp asynchronous publishers; dùng `flatMap(mapper, concurrency)` để giới hạn concurrency **trong pipeline** khi có nhiều remote calls.
- `concatMap`: giữ thứ tự khi cần xử lý publishers nối tiếp.
- `take(n)`: giới hạn stream hữu hạn; downstream hủy upstream sau khi đủ n.
- `onErrorResume`: fallback có **điều kiện**, không nuốt mọi lỗi; với lỗi nghiệp vụ quan trọng phải giữ error semantics.
- `timeout`: giới hạn thời gian chờ trên reactive pipeline nhưng **không bảo đảm** blocking client/native I/O luôn kết thúc khi timeout.
- `doFinally`: chạy khi complete, error hoặc cancel; dùng cleanup/metrics, **không** làm business side effects quyết định consistency.
- `retryWhen`: retry có backoff/jitter với operation idempotent; không retry POST tạo giao dịch bừa bãi.

### 3.1. Vì sao `Flux.interval` được dùng trong demo?

`Flux.interval(initialDelay, period)` tạo emissions bằng Scheduler và không gọi `Thread.sleep` ở controller. Trong demo, mỗi subscription tạo timer stream riêng (cold publisher). Đây là nguồn giả lập data mới theo thời gian, **không phải realtime sensor thật**. Với production, thay nó bằng WebClient/R2DBC/reliable message feed có giải pháp buffering/backpressure rõ ràng.

`Flux.interval` không phải hàng đợi bền vững; khi subscriber không theo kịp demand nó có thể phát lỗi overflow, không đảm bảo giữ mọi event. Dữ liệu không được lưu lại cho khách reconnect. Tạo streams vô hạn với hàng nghìn subscribers có chi phí timers, network connections và memory; cần quota, cancellation, heartbeat và monitoring.

## 4. Chặn luồng trên event loop: sai ở đâu?

### 4.1. Ví dụ **sai** — chỉ để nhận diện anti-pattern

**Không thêm đoạn sau vào dự án chạy**:

```java
@GetMapping("/wrong")
public Mono<String> wrong() {
    // SAI: đây là mã đồng bộ chặn thread gọi controller.
    Thread.sleep(1000);  // Java sẽ yêu cầu xử lý InterruptedException.
    return Mono.just("done");
}
```

Đoạn trên cố ý là **pseudocode không biên dịch độc lập** để minh họa lỗi thiết kế; `Thread.sleep` còn cần xử lý checked exception. Trong thực tế, nếu code sửa thành hợp lệ rồi chạy ngay trong WebFlux handler, nó có thể giữ Netty event-loop trong 1 giây, ảnh hưởng nhiều requests khác. Không sao chép vào production.

Một biến thể **cũng sai**:

```java
@GetMapping("/wrong-again")
public Mono<String> wrongAgain() {
    String value = blockingClient.fetch(); // gọi blocking ngay
    return Mono.just(value);               // bọc SAU khi đã block
}
```

Đây là snippet khái niệm, `blockingClient` không nằm trong project mẫu. `Mono.just` không biến một lời gọi đồng bộ đã thực thi thành không chặn; nó chỉ gói giá trị đã có.

### 4.2. Mẫu đúng cho một lời gọi legacy blocking

Reactor hướng dẫn:

```java
Mono<InventorySnapshot> result =
    Mono.fromCallable(() -> legacyClient.fetch(sku))
        .subscribeOn(Schedulers.boundedElastic());
```

`Mono.fromCallable` **hoãn** lời gọi đến lúc subscribe; `subscribeOn` quyết định scheduler chạy subscribe/source call. `Schedulers.boundedElastic()` cho phép offload blocking I/O khỏi event loop và có **giới hạn threads/tasks queued**. Nó không tăng throughput một DB đã bão hòa; cần timeouts và kiểm soát concurrency.

**Vì sao không dùng `publishOn(Schedulers.boundedElastic())` ở cuối để sửa lỗi?**

```java
Mono.fromCallable(() -> blockingClient.fetch(sku))
    .publishOn(Schedulers.boundedElastic());
```

Đoạn là snippet khái niệm. `publishOn` thay execution context cho **các toán tử phía sau** điểm publishOn; nó không bảo đảm source callable phía **trước** được offload. Với một nguồn blocking hãy đặt `subscribeOn` sát nguồn `Mono.fromCallable`.

**Không gọi `Mono.block()` trong WebFlux handler.** Reactor cảnh báo blocking APIs như `block()/blockFirst()/blockLast()` trên non-blocking schedulers có thể ném `IllegalStateException`, ngoài tác hại với throughput.

### 4.3. Một bounded scheduler là một vùng chứa, không phải phép màu

Trong dự án, ta dùng một scheduler chuyên biệt:

```java
Schedulers.newBoundedElastic(
    4,               // thread cap của scheduler
    16,              // queue bound cho mỗi backing thread theo Reactor API
    "legacy-bridge"  // tên dễ nhận diện trong thread dumps
);
```

Đây là một **giới hạn demo**; không phải cấu hình khuyến nghị production. Reactor có thể từ chối scheduling khi quota queue đầy, phát `RejectedExecutionException`. Queue bound **không phải** quota kết nối database và không thay thế admission control/global bulkhead theo người dùng.

Các giới hạn còn tồn tại:

- Mọi concurrent HTTP request có thể vào pipeline; đến scheduler queue mới bị chờ/từ chối.
- Timeout ở Reactor có thể cancel subscription, nhưng legacy call đang chặn có thể phớt lờ interrupt và vẫn chạy.
- Nếu thư viện đồng bộ không có native connect/read/query timeouts, một worker có thể bị giữ quá lâu.
- Scheduler không tự khống chế global load ở **nhiều JVM replicas**.
- Blocking calls dài tạo pressure lên memory/queue; rejected requests và p95/p99 cần metric/alert riêng.
- BoundedElastic hữu ích như **cầu nối tạm thời**; giải pháp lâu dài nên dùng reactive/non-blocking client nếu có và hợp lý.

## 5. Dự án thực hành Java 17+ hoàn chỉnh

### 5.1. Cây thư mục

```text
webflux-streaming-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/streamlab/
    │   │   ├── StreamLabApplication.java
    │   │   ├── SensorReading.java
    │   │   ├── InventorySnapshot.java
    │   │   ├── ReadingStreamService.java
    │   │   ├── LegacyInventoryClient.java
    │   │   ├── LegacyBridge.java
    │   │   └── StreamingController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/streamlab/
            ├── StreamingApiIntegrationTest.java
            ├── StreamingControllerSliceTest.java
            ├── ReadingStreamServiceTest.java
            └── LegacyBridgeTest.java
```

Mỗi `public` top-level Java class hoặc record được đặt trong file cùng tên. Không cần database, Kafka hoặc external HTTP service cho demo; dữ liệu đến từ `Flux.interval` và một client đồng bộ giả có sleep ngắn. Nhờ đó người học có thể chạy bằng Maven/JDK mà không cần network ngoài để phục vụ requests.

### 5.2. `pom.xml` — Maven hợp lệ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-streaming-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
```

**Vì sao những dependencies này?**

- `spring-boot-starter-webflux`: Spring WebFlux, Reactor, Reactor Netty server mặc định và Jackson codecs.
- `spring-boot-starter-actuator`: `health/metrics` khi có cấu hình exposure; dùng quan sát trong local lab, không public production.
- `spring-boot-starter-test`: JUnit Jupiter, Mockito, Spring Test.
- `reactor-test`: `StepVerifier` để test tín hiệu, cancellation, virtual time.
- **Không** thêm `spring-boot-starter-web` vì khi cả MVC và WebFlux trên classpath, Spring Boot thông thường ưu tiên MVC; lúc đó bài học về Netty event loop không còn đúng runtime như dự kiến.

### 5.3. Application properties

**`src/main/resources/application.properties`**

```properties
spring.application.name=webflux-streaming-lab
server.port=8080

# Chỉ phục vụ local demo; khi chạy container thực tế,
# cấu hình lại listen address/network theo deployment.
server.address=127.0.0.1
spring.main.web-application-type=reactive

# Chỉ expose health và metrics trong môi trường local.
management.endpoints.web.exposure.include=health,metrics

# Giới hạn buffer khi decode một payload vào memory
# (không phải giới hạn tổng số SSE clients hoặc outbound bytes).
spring.codec.max-in-memory-size=256KB
```

`spring.codec.max-in-memory-size` hạn chế một số hoạt động buffering của codecs và có thể phát `DataBufferLimitException` khi payload quá lớn; nó **không** giới hạn toàn bộ lượng dữ liệu phát qua streaming response. Trong production, thêm body-size rules, connection quotas, upstream timeouts, authentication/authorization và monitoring cgroup resources.

### 5.4. Main class

**`src/main/java/com/example/streamlab/StreamLabApplication.java`**

```java
package com.example.streamlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamLabApplication.class, args);
    }
}
```

### 5.5. DTO cho streaming và inventory

**`src/main/java/com/example/streamlab/SensorReading.java`**

```java
package com.example.streamlab;

public record SensorReading(
        long sequence,
        double celsius,
        String source
) {}
```

**`src/main/java/com/example/streamlab/InventorySnapshot.java`**

```java
package com.example.streamlab;

public record InventorySnapshot(
        String sku,
        int available
) {}
```

Java 17 record phù hợp làm immutable DTO và được Jackson mã hóa thành object JSON. Các ví dụ dùng giá trị xác định để test không phải assert ngẫu nhiên. Không đưa internal thread name, exception stack trace hoặc token vào DTO production.

### 5.6. Stream service: cold Flux, giới hạn sự kiện và cleanup

**`src/main/java/com/example/streamlab/ReadingStreamService.java`**

```java
package com.example.streamlab;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

@Service
public class ReadingStreamService {

    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger cancelled = new AtomicInteger();

    public Flux<SensorReading> readings(
            int count,
            long periodMs) {

        // Mỗi subscription có timer và lifecycle riêng.
        return Flux.defer(() -> {
            active.incrementAndGet();

            return Flux.interval(
                    Duration.ZERO,
                    Duration.ofMillis(periodMs))
                .take(count)
                .map(tick -> new SensorReading(
                    tick + 1,
                    20.0 + (tick % 5) * 0.5,
                    "sensor-demo"
                ))
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        cancelled.incrementAndGet();
                    }
                    active.decrementAndGet();
                });
        });
    }

    public int active() {
        return active.get();
    }

    public int cancelled() {
        return cancelled.get();
    }
}
```

Giải thích thiết kế:

1. `Flux.defer` tạo luồng **khi subscribe**, không tăng `active` ngay lúc controller trả object Flux. Nếu hai subscribers độc lập cùng gọi endpoint, mỗi người có timer và sequence riêng.
2. `Flux.interval(Duration.ZERO, Duration.ofMillis(periodMs))` phát số `0,1,2,...` theo lịch, từ đó tạo `SensorReading(sequence = tick+1,...)`.
3. `take(count)` giới hạn số events và kết thúc pipeline; tránh stream vô hạn trong demo HTTP.
4. `doFinally` xử lý **complete, error và cancel**; decrement `active` ở một nơi duy nhất. `SignalType.CANCEL` được ghi vào counter để quan sát behavior subscriber hủy.
5. `AtomicInteger` không biến counter thành database; đây là metrics **trong một JVM**. Ở nhiều replicas, muốn tổng toàn cluster phải dùng monitoring backend.
6. Counter có thể về `0` trước/lúc client đọc `/stats`; sample stats **không** chứng minh từng event đã tới browser.
7. Với `Flux.interval`, nếu downstream không yêu cầu dữ liệu kịp, có thể phát lỗi về demand; demo không cam kết at-least-once delivery hay replay.
8. `doFinally` phù hợp để release resources/local gauges; không dùng nó làm nơi commit tài chính hoặc exactly-once side effect.

**Giới hạn:** do `periodMs` được validate ở controller, nếu gọi service trực tiếp với `periodMs <= 0` có thể nhận lỗi tạo timer. Vì vậy khi tái sử dụng service ở nơi khác, thêm domain validation/test ở service boundary nếu cần contract độc lập.

### 5.7. Mô phỏng thư viện synchronous legacy

**`src/main/java/com/example/streamlab/LegacyInventoryClient.java`**

```java
package com.example.streamlab;

import org.springframework.stereotype.Component;

@Component
public class LegacyInventoryClient {

    public InventorySnapshot fetch(String sku) {
        // Chỉ để mô phỏng một API JDBC/HTTP đồng bộ cũ.
        // KHÔNG dùng sleep để xử lý request trong production.
        try {
            Thread.sleep(60);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Legacy lookup interrupted", ex
            );
        }

        return new InventorySnapshot(sku, 17);
    }
}
```

`Thread.sleep(60)` **chặn thread**. Đây là mô phỏng có chủ đích để kiểm offloading, không phải cách thực thi I/O thật. Nếu thay bằng một synchronous JDBC/HTTP client, hãy cấu hình **timeouts ở chính thư viện đó** (connect/read/query) và pool limits. Không để một task blocking tồn tại vô hạn.

### 5.8. Cầu nối có scheduler chuyên biệt và timeout

**`src/main/java/com/example/streamlab/LegacyBridge.java`**

```java
package com.example.streamlab;

import java.time.Duration;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeoutException;

import jakarta.annotation.PreDestroy;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Service
public class LegacyBridge {

    private final LegacyInventoryClient client;

    // Các giới hạn demo: 4 backing threads, queue bound 16/thread.
    // Production sizing phải dựa trên workload và downstream capacity.
    private final Scheduler scheduler =
        Schedulers.newBoundedElastic(4, 16, "legacy-bridge");

    public LegacyBridge(LegacyInventoryClient client) {
        this.client = client;
    }

    public Mono<InventorySnapshot> lookup(String sku) {
        return Mono.fromCallable(() -> client.fetch(sku))
            .subscribeOn(scheduler)
            .timeout(Duration.ofSeconds(2))
            .onErrorMap(
                TimeoutException.class,
                ex -> new ResponseStatusException(
                    HttpStatus.GATEWAY_TIMEOUT,
                    "Legacy lookup timed out",
                    ex
                ))
            .onErrorMap(
                RejectedExecutionException.class,
                ex -> new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Legacy executor saturated",
                    ex
                ));
    }

    @PreDestroy
    public void dispose() {
        scheduler.dispose();
    }
}
```

Điểm then chốt:

- `Mono.fromCallable` bao **cả** lời gọi chặn và trì hoãn việc gọi cho tới subscription.
- `subscribeOn(scheduler)` chuyển source callable khỏi event loop sang pool bounded dành riêng cho legacy workload.
- `newBoundedElastic(4,16,...)` ngăn scheduler tăng backing threads vô hạn; khi queue đầy nó có thể phát rejection, được map thành 503 tại HTTP layer của demo. Con số `16` là queue bound **theo backing thread** trong Reactor API, không phải 16 request toàn cluster.
- `timeout(2s)` chuyển chờ quá lâu thành timeout error, map 504. Timeout ở pipeline **không bảo đảm** đã dừng được thư viện JDBC/socket đang chặn; cần timeout native driver và resource cleanup.
- `@PreDestroy` dispose scheduler khi bean/context kết thúc. Một scheduler tạo **theo bean singleton**, không phải mỗi HTTP request. Tạo scheduler mới ở mỗi request dẫn đến resource/thread leak.
- `RejectedExecutionException` cũng có thể từ executor nội bộ khác nếu logic mở rộng; mapping này hợp lý cho demo nhưng production phải phân biệt error source khi đưa ra HTTP 503.
- Dùng HTTP status 503/504 không thay cho metrics/alerting. Bổ sung throughput, queue depth, rejected count và error rate ở hệ thống thật.

**Không dùng `Schedulers.parallel()` để chạy blocking I/O.** Nó phù hợp CPU/non-blocking work, không phù hợp sleep/JDBC. `boundedElastic` cũng không làm CPU-bound loop nhanh hơn; CPU-intensive tasks cần thiết kế riêng với số cores/quota và concurrency phù hợp.

### 5.9. Controller: SSE, NDJSON, stats và bridge

**`src/main/java/com/example/streamlab/StreamingController.java`**

```java
package com.example.streamlab;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class StreamingController {

    private final ReadingStreamService readings;
    private final LegacyBridge legacy;

    public StreamingController(
            ReadingStreamService readings,
            LegacyBridge legacy) {
        this.readings = readings;
        this.legacy = legacy;
    }

    @GetMapping(
        path = "/readings/sse",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<SensorReading>> sse(
            @RequestParam(defaultValue = "3") int count,
            @RequestParam(defaultValue = "50") long periodMs) {

        validateStreamParameters(count, periodMs);

        return readings.readings(count, periodMs)
            .map(item ->
                ServerSentEvent.<SensorReading>builder()
                    .id(Long.toString(item.sequence()))
                    .event("reading")
                    .data(item)
                    .build());
    }

    @GetMapping(
        path = "/readings/ndjson",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<SensorReading> ndjson(
            @RequestParam(defaultValue = "3") int count,
            @RequestParam(defaultValue = "50") long periodMs) {

        validateStreamParameters(count, periodMs);
        return readings.readings(count, periodMs);
    }

    @GetMapping("/readings/stats")
    public Map<String, Integer> stats() {
        return Map.of(
            "active", readings.active(),
            "cancelled", readings.cancelled()
        );
    }

    @GetMapping("/legacy/{sku}")
    public Mono<InventorySnapshot> legacy(
            @PathVariable String sku) {

        if (!sku.matches("[A-Za-z0-9_-]{1,32}")) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid SKU"
            );
        }

        return legacy.lookup(sku);
    }

    private static void validateStreamParameters(
            int count,
            long periodMs) {
        if (count < 1 || count > 20 ||
                periodMs < 25 || periodMs > 1000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "count must be 1..20 and periodMs 25..1000"
            );
        }
    }
}
```

**Vì sao validation trước khi trả Flux?**

Nếu không kiểm và một lỗi xảy ra sau khi SSE/NDJSON đã bắt đầu ghi bytes, HTTP headers có thể đã được commit. Lúc đó server thường **không thể** đổi status từ 200 sang 400/500 theo cách bình thường. Kiểm `count`/`periodMs`/`sku` ngay ở request boundary để trả 400 rõ ràng.

**Vì sao count giới hạn 20, periodMs 25..1000?** Đây là guardrail demo ngăn một client yêu cầu stream quá dài hoặc timer dày đặc. **Không phải rate limiting đủ cho production**: kẻ tấn công vẫn có thể mở nhiều connections đồng thời. Production cần authentication, per-tenant connection limits, admission control, idle timeout và monitoring.

## 6. Chạy thử API trong terminal

Dùng JDK 17+, Maven, tại thư mục `webflux-streaming-lab`:

```bash
java -version
mvn spring-boot:run
```

Nếu có Maven Wrapper đã sinh sẵn, dùng `./mvnw spring-boot:run` hoặc Windows `mvnw.cmd spring-boot:run`. Không giả định project có wrapper nếu chưa tạo.

### 6.1. SSE — xem event-by-event

```bash
curl -N -i \
  -H "Accept: text/event-stream" \
  "http://127.0.0.1:8080/api/readings/sse?count=3&periodMs=300"
```

Body có dạng (JSON field order có thể khác):

```text
id:1
event:reading
data:{"sequence":1,"celsius":20.0,"source":"sensor-demo"}

id:2
event:reading
data:{"sequence":2,"celsius":20.5,"source":"sensor-demo"}

id:3
event:reading
data:{"sequence":3,"celsius":21.0,"source":"sensor-demo"}

```

Từng event có dòng trống phân cách; đây là representation minh họa theo SSE encoder, không phải đảm bảo các TCP packets tương ứng 1:1 từng event. `id` cho phép client nhận biết event, nhưng demo không có durable replay/resume.

### 6.2. NDJSON — từng dòng là một object

```bash
curl -N -i \
  -H "Accept: application/x-ndjson" \
  "http://127.0.0.1:8080/api/readings/ndjson?count=3&periodMs=300"
```

Body minh họa:

```text
{"sequence":1,"celsius":20.0,"source":"sensor-demo"}
{"sequence":2,"celsius":20.5,"source":"sensor-demo"}
{"sequence":3,"celsius":21.0,"source":"sensor-demo"}
```

Không có dấu `[`/`]` bao quanh body như JSON array. Một client dùng JSON decoder cho array hoặc browser JSON.parse toàn body có thể hiểu sai; client cần line parser/NDJSON decoder.

### 6.3. Legacy blocking endpoint đã offload

```bash
curl -i "http://127.0.0.1:8080/api/legacy/SKU-123"
```

Kỳ vọng:

```json
{"sku":"SKU-123","available":17}
```

Endpoint vẫn tiêu tốn ~60ms sleep trong **legacy scheduler thread**, nhưng Netty event loop không bị block bởi lời gọi đó. Client có thể quan sát latency lớn hơn 60ms do queue/network/JVM scheduling. Không tuyên bố response luôn chính xác 60ms hoặc máy chủ có throughput tối đa nào từ một request.

### 6.4. Invalid input và stats

```bash
curl -i "http://127.0.0.1:8080/api/readings/sse?count=0&periodMs=50"
curl -i "http://127.0.0.1:8080/api/readings/ndjson?count=3&periodMs=1"
curl -i "http://127.0.0.1:8080/api/legacy/bad%20sku"
curl -sS "http://127.0.0.1:8080/api/readings/stats"
```

Ba request invalid ở trên kỳ vọng 400, nhưng bản thân proxy/path decoding có thể từ chối encoded URI trước handler tùy deployment; status của URL chứa khoảng trắng mã hóa không phải bằng chứng duy nhất cho validation. Để xác minh SKU validation ổn định, dùng unit/controller test kiểm trực tiếp input `"bad sku"` hoặc dùng path param không hợp lệ nhưng được container chấp nhận, ví dụ `bad!sku`. `stats` trả JSON có `active`/`cancelled`; giá trị thay đổi theo số streams và cancellation thực tế.

PowerShell có alias `curl` trong một số môi trường; dùng `curl.exe` để áp dụng flags như `-N`.

## 7. Kiểm thử bằng Spring WebTestClient và Reactor StepVerifier

Phân biệt ba mức:

1. **Unit test** `ReadingStreamService`/`LegacyBridge` trực tiếp: không cần mở HTTP server, dùng StepVerifier, chứng minh emission/cancel và thread offloading của blocking callable.
2. **`@WebFluxTest` slice**: nạp controller và WebFlux codecs/validation, dùng `@MockitoBean` cho service/bridge; kiểm HTTP mapping/status/body, không kiểm Netty TCP hoặc real business implementation.
3. **`@SpringBootTest(RANDOM_PORT)`**: khởi động **Reactor Netty HTTP server thật**, WebTestClient gửi HTTP tới random port và consume SSE/NDJSON. Không tự chứng minh proxy/CDN/TLS production hay mọi thứ dưới tải.

### 7.1. Unit test service: values, complete và cancel

**`src/test/java/com/example/streamlab/ReadingStreamServiceTest.java`**

```java
package com.example.streamlab;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReadingStreamServiceTest {

    @Test
    void finiteStreamEmitsValuesInOrder() {
        ReadingStreamService service = new ReadingStreamService();

        StepVerifier.create(service.readings(3, 25))
            .assertNext(r -> {
                assertEquals(1L, r.sequence());
                assertEquals(20.0, r.celsius());
            })
            .assertNext(r -> assertEquals(2L, r.sequence()))
            .assertNext(r -> assertEquals(3L, r.sequence()))
            .expectComplete()
            .verify(Duration.ofSeconds(5));

        assertEquals(0, service.active());
        assertEquals(0, service.cancelled());
    }

    @Test
    void cancellationTriggersCleanup() {
        ReadingStreamService service = new ReadingStreamService();

        StepVerifier.create(service.readings(20, 1000))
            .assertNext(r -> assertEquals(1L, r.sequence()))
            .thenCancel()
            .verify(Duration.ofSeconds(5));

        assertEquals(0, service.active());
        assertEquals(1, service.cancelled());
    }
}
```

`StepVerifier` subscribe và request signals; với `Flux.interval` emissions thực theo scheduler, thời gian test có thể thay đổi nhưng không assert milliseconds cụ thể. `verify(Duration)` bảo vệ CI khỏi đợi vô hạn. `thenCancel()` là một **cancellation từ subscriber**. `doFinally(CANCEL)` cập nhật counter khi upstream thực sự nhận hủy.

Test này kiểm implementation của stream trong một JVM. Nó không kiểm Netty, JSON encoder hay client TCP disconnect. Trường hợp SSE qua proxy, cancellation end-to-end cần integration test và quan sát tài nguyên thật.

### 7.2. Unit test cầu nối: callable không chạy trên test thread

**`src/test/java/com/example/streamlab/LegacyBridgeTest.java`**

```java
package com.example.streamlab;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class LegacyBridgeTest {

    @Test
    void blockingCallableRunsOnDedicatedScheduler() {
        AtomicReference<String> observedThread =
            new AtomicReference<>();

        LegacyInventoryClient fake = new LegacyInventoryClient() {
            @Override
            public InventorySnapshot fetch(String sku) {
                observedThread.set(
                    Thread.currentThread().getName());
                return new InventorySnapshot(sku, 7);
            }
        };

        LegacyBridge bridge = new LegacyBridge(fake);
        try {
            StepVerifier.create(bridge.lookup("SKU-1"))
                .expectNext(new InventorySnapshot("SKU-1", 7))
                .expectComplete()
                .verify(Duration.ofSeconds(5));

            assertNotNull(observedThread.get());
            assertNotEquals(
                Thread.currentThread().getName(),
                observedThread.get()
            );
        } finally {
            bridge.dispose();
        }
    }
}
```

Test này không khẳng định toàn bộ HTTP handler non-blocking, nhưng xác minh **nguồn blocking callable được chạy ngoài JUnit calling thread**, theo `subscribeOn` của bridge. Muốn chứng minh không block **Netty event-loop** thực tế, cần thêm tracing/profiling/BlockHound/integration test trong runtime có instrumentation tương thích.

### 7.3. Web slice test: media type, body và 400

**`src/test/java/com/example/streamlab/StreamingControllerSliceTest.java`**

```java
package com.example.streamlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;

@WebFluxTest(controllers = StreamingController.class)
class StreamingControllerSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    ReadingStreamService readings;

    @MockitoBean
    LegacyBridge legacy;

    @Test
    void ndjsonUsesExpectedMediaTypeAndBody() {
        given(readings.readings(2, 25)).willReturn(Flux.just(
            new SensorReading(1, 20.0, "sensor-demo"),
            new SensorReading(2, 20.5, "sensor-demo")
        ));

        client.get()
            .uri("/api/readings/ndjson?count=2&periodMs=25")
            .accept(MediaType.APPLICATION_NDJSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_NDJSON)
            .expectBodyList(SensorReading.class)
            .hasSize(2)
            .contains(
                new SensorReading(1, 20.0, "sensor-demo"),
                new SensorReading(2, 20.5, "sensor-demo")
            );
    }

    @Test
    void invalidStreamSettingsReturn400BeforeService() {
        client.get()
            .uri("/api/readings/sse?count=0&periodMs=20")
            .exchange()
            .expectStatus().isBadRequest();

        verify(readings, never()).readings(
            anyInt(), anyLong());
    }

    @Test
    void legacyRouteReturnsJson() {
        given(legacy.lookup("SKU1")).willReturn(
            Mono.just(new InventorySnapshot("SKU1", 17))
        );

        client.get().uri("/api/legacy/SKU1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.sku").isEqualTo("SKU1")
            .jsonPath("$.available").isEqualTo(17);
    }
}
```

`@WebFluxTest` auto-configures WebTestClient không cần HTTP port; với các `@Service` thông thường bị loại khỏi slice nên dùng `@MockitoBean`. `Mockito.verify(..., never())` xác nhận invalid input bị chặn **trước khi gọi** stream service. Test không chứng minh scheduler thật, vì `LegacyBridge` ở đây là mock.

### 7.4. HTTP integration: real Netty server, NDJSON và SSE

**`src/test/java/com/example/streamlab/StreamingApiIntegrationTest.java`**

```java
package com.example.streamlab;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class StreamingApiIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void ndjsonStreamsThreeObjectsOverHttp() {
        FluxExchangeResult<SensorReading> result =
            client.get()
                .uri("/api/readings/ndjson?count=3&periodMs=25")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                    MediaType.APPLICATION_NDJSON)
                .returnResult(SensorReading.class);

        StepVerifier.create(result.getResponseBody())
            .assertNext(r -> assertEquals(1L, r.sequence()))
            .assertNext(r -> assertEquals(2L, r.sequence()))
            .assertNext(r -> assertEquals(3L, r.sequence()))
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void sseStreamsThreeEventsOverHttp() {
        FluxExchangeResult<ServerSentEvent<SensorReading>> result =
            client.get()
                .uri("/api/readings/sse?count=3&periodMs=25")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                    MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<SensorReading>>() {}
                );

        StepVerifier.create(result.getResponseBody())
            .assertNext(e -> {
                assertEquals("reading", e.event());
                assertEquals("1", e.id());
                assertNotNull(e.data());
                assertEquals(1L, e.data().sequence());
            })
            .assertNext(e -> assertEquals("2", e.id()))
            .assertNext(e -> assertEquals("3", e.id()))
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void badCountIsRejectedWith400() {
        client.get()
            .uri("/api/readings/ndjson?count=21&periodMs=25")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void legacyLookupReturnsExpectedDtoOverHttp() {
        client.get().uri("/api/legacy/SKU-1")
            .exchange()
            .expectStatus().isOk()
            .expectBody(InventorySnapshot.class)
            .isEqualTo(new InventorySnapshot("SKU-1", 17));
    }

    @Test
    void clientCanCancelLongSseSubscription() {
        FluxExchangeResult<ServerSentEvent<SensorReading>> result =
            client.get()
                .uri("/api/readings/sse?count=20&periodMs=1000")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<SensorReading>>() {}
                );

        StepVerifier.create(result.getResponseBody())
            .assertNext(e -> assertEquals("1", e.id()))
            .thenCancel()
            .verify(Duration.ofSeconds(5));
    }
}
```

**Phạm vi thực sự được kiểm:**

- `@SpringBootTest(RANDOM_PORT)` khởi động full application context và embedded Reactor Netty HTTP server. WebTestClient gửi request qua loopback network, rồi decode body streaming.
- `FluxExchangeResult` cho phép tiêu thụ body **từng event/object**; không chờ toàn stream bằng `expectBodyList` khi stream dài.
- `thenCancel()` hủy subscription ở test client. Nó chứng minh client có thể cancel một HTTP stream, nhưng nếu muốn chứng minh **server-side listener đã cleanup** qua TCP trong mọi trường hợp cần thêm instrumentation/async observation. Không assert ngay `stats.active==0` mà không chờ eventual completion vì network cancellation có độ trễ.
- Tất cả tests dùng URL tương đối vào random port mà Spring Boot cấu hình; không phụ thuộc server 8080 của process khác.
- Test 200 JSON từ `LegacyBridge` thực sự chạy scheduler, nhưng một request đơn lẻ **không** chứng minh scheduler vẫn có latency tốt dưới overload.

### 7.5. Chạy bộ tests và kỳ vọng

```bash
mvn test
```

Hoặc nếu đã tạo Maven Wrapper:

```bash
./mvnw test
```

Có thể chạy riêng:

```bash
mvn -Dtest=ReadingStreamServiceTest test
mvn -Dtest=LegacyBridgeTest test
mvn -Dtest=StreamingControllerSliceTest test
mvn -Dtest=StreamingApiIntegrationTest test
```

Dự án mẫu gồm **2 + 1 + 3 + 5 = 11 phương thức test**. Chúng được **thiết kế** để pass với JDK/Maven/dependencies phù hợp; phần README không khẳng định đã chạy Maven trên máy của người đọc. Độ trễ của `Flux.interval` phụ thuộc scheduler/CI; tests dùng `verify(Duration)` thay vì assert thời gian mỗi event chính xác vài ms.

## 8. Kiểm soát blocking trong một dự án thực tế

### 8.1. Audit theo từng lời gọi

Dò từ controller xuống service/repository:

| Loại công việc | Ví dụ | Hành động |
| --- | --- | --- |
| Non-blocking reactive source | `WebClient`, R2DBC, reactive Redis driver | Giữ pipeline reactive; giới hạn connection/request timeout |
| Synchronous HTTP client | `RestTemplate`, Apache sync client, `java.net.http.HttpClient.send` | Ưu tiên WebClient hoặc offload bằng fromCallable+boundedElastic |
| JDBC/JPA | `JdbcTemplate`, `JpaRepository` | Synchronous, offload nếu chưa thể migration; không gọi trên event loop |
| File sync I/O | `Files.readAllBytes`, `FileInputStream` | Dùng async-capable APIs khi có hoặc offload/streaming có giới hạn |
| Waiting | `Thread.sleep`, `Future.get`, `CountDownLatch.await` | Không thực thi trên event loop; thay bằng async composition hoặc offload |
| Reactive blocking bridge | `Mono.block()`, `Flux.blockFirst()` | Không gọi từ handler/event loop; compose bằng map/flatMap |
| CPU-intensive task | lớn vòng lặp, ảnh/video encoding | Thiết kế executor/scheduler/worker riêng, giới hạn song song theo CPU |
| Logging | sync appenders hoặc logging body lớn | Kiểm I/O/logging overhead và dữ liệu nhạy cảm |
| Database pool | chờ acquire connection | Đo pool wait/busy/rejection, tối ưu downstream |

**Không được kết luận `@Async` tự động biến một dependency synchronous thành non-blocking I/O.** Nó chuyển execution sang executor, có thread/queue giới hạn và failure mode riêng. Đặt `@Async` rồi bỏ qua timeouts/bulkhead cũng có thể quá tải.

### 8.2. WebClient non-blocking thay cho synchronous HTTP

Ví dụ **snippet**, không thuộc các class cần biên dịch ở dự án mẫu:

```java
private final WebClient webClient;

public Mono<RemoteStatus> getStatus(String id) {
    return webClient.get()
        .uri(uriBuilder ->
            uriBuilder.path("/status/{id}").build(id))
        .retrieve()
        .bodyToMono(RemoteStatus.class)
        .timeout(Duration.ofSeconds(2));
}
```

Snippet này giả định đã inject `WebClient` và có record/class `RemoteStatus` cùng endpoint upstream được phép gọi. Không gọi `.block()` ở cuối. Tuy nhiên `WebClient` vẫn có connection pool, codec buffers, DNS/TLS và upstream quotas; cấu hình connect/response/read timeouts tại Reactor Netty client phù hợp thay vì chỉ dựa vào reactive `timeout`.

Khi gọi nhiều nguồn:

```java
Flux.fromIterable(ids)
    .flatMap(id -> webClient.get()
        .uri("/items/{id}", id)
        .retrieve()
        .bodyToMono(ItemDto.class),
        4);
```

Đây là snippet giả định `ids`, `webClient` và `ItemDto` có sẵn. `flatMap(...,4)` giới hạn **bốn inner subscriptions đồng thời trong pipeline này**, không phải global concurrency across all requests/replicas. Với operations cần thứ tự dùng `concatMap` hoặc tái sắp xếp có chủ đích.

### 8.3. BoundedElastic: shared và dedicated

`Schedulers.boundedElastic()` là shared global scheduler với default bounds và policy của Reactor version/runtime. Nó phù hợp cho các lời gọi blocking được cô lập ngắn hạn nhưng shared với các nơi khác dùng cùng scheduler. `Schedulers.newBoundedElastic(...)` tạo một scheduler riêng như trong demo, giúp phân vùng workloads và dispose đúng lifecycle.

Tránh hai sai lầm:

1. Tạo `newBoundedElastic` **bên trong mỗi HTTP request** rồi không dispose → thread/resource leak.
2. Dùng một scheduler dedicated cho mọi library blocking không liên quan nhưng không có separate admission quotas → một dependency chậm có thể làm nghẽn tất cả tasks khác.

Cần chọn concurrency, queue, native timeouts và fallback phù hợp với connection pool/downstream SLA, cân bằng throughput và resource budgets. Nếu queue đầy, trả 429/503 có chủ đích và metrics; không nuốt lỗi hoặc retry vô hạn.

### 8.4. Backpressure không giống tốc độ producer hay retry

Reactive Streams `request(n)` cho downstream quyền yêu cầu dữ liệu, nhưng khả năng chống overload **phụ thuộc nguồn**:

- `Flux.range` có thể phát đúng demand.
- `Flux.interval` dựa trên thời gian; khi consumer chậm, nó không mặc nhiên lưu mọi tick để phát sau.
- Hot external sensor/Kafka/WebSocket callbacks có thể vượt demand; cần backpressure strategy, bounded buffer, drop/latest policies hoặc flow control ở nguồn.
- `onBackpressureBuffer` không có giới hạn có thể tạo OOM; bounded buffer mới là cơ chế an toàn nếu ứng dụng chấp nhận policy đó.
- `retryWhen` có thể nhân lưu lượng khi downstream đang quá tải; nên có backoff+jitter, giới hạn attempts và deadline.

Một HTTP client chậm khiến response stream bị network backpressure, nhưng **không bảo đảm** upstream provider tự giảm tốc theo cùng tín hiệu, đặc biệt với hot sources. Đặt queue length, discarded count, slow-consumer metrics và cancellation cleanup vào design.

### 8.5. Cancellation và tài nguyên

Khi subscriber cancel:

- Reactor gọi cancel upstream, nhưng nguồn có thể không hỗ trợ hủy tác vụ ở OS/driver.
- `doFinally(SignalType.CANCEL)` chạy khi subscription của pipeline này kết thúc do cancel.
- Đối với SSE/NDJSON, client disconnect thường dẫn đến cleanup, nhưng thời điểm detection phụ thuộc network/heartbeat.
- Long-lived connections có thể chỉ phát hiện disconnect khi server cố ghi thêm dữ liệu; framework docs khuyến nghị heartbeat periodic (SSE comment-only/no-op event) để nhận biết disconnect sớm hơn.
- Nếu dùng pooled Netty `DataBuffer` trực tiếp, phải release buffers theo đúng contract. Với DTO→Jackson codec trong demo, framework quản lý buffers; không tự gọi `DataBufferUtils.release` cho những objects không sở hữu.

**Đừng dựa vào cancellation như một transactional rollback**. Nếu một blocking call đã ghi database trước khi request bị hủy, side effect có thể vẫn tồn tại. Business idempotency/transactions cần thiết kế riêng.

## 9. Tránh BlockHound và profiling bị hiểu sai

### 9.1. BlockHound dùng để phát hiện một số blocking calls

**BlockHound** là tùy chọn instrumentation cho Reactor, có thể phát hiện những blocking operations đã biết được gọi trên thread được đánh dấu non-blocking, nhất là event loops. Nó không tự có mặt khi thêm `spring-boot-starter-webflux` hoặc `reactor-test`.

Nếu đội chọn dùng BlockHound:

- Thêm dependency/version **tương thích JDK/Reactor/agent** và cấu hình installation riêng trong test/test JVM, không bật tùy tiện production.
- Trên JDK 13+ có yêu cầu JVM instrumentation flags trong một số bản BlockHound (ví dụ `-XX:+AllowRedefinitionToAddDeleteMethods`); xác minh theo docs/version thay vì copy một lệnh từ blog cũ.
- Chạy trên **real reactive execution path**, không chỉ tạo mock `Mono.just(...)`; chú ý test framework và instrumentation agents.
- Tránh allowlist toàn package hoặc nới quá rộng rồi tưởng không còn blocking.
- Không coi không có report từ BlockHound là chứng minh **mọi JDBC/native call non-blocking**. Nó chỉ phát hiện những trường hợp mà instrumentation có thể nhận diện.

### 9.2. Thread dumps, Micrometer và event-loop latency

Các dấu hiệu chặn event loop:

- Netty event-loop threads có stack `Thread.sleep`, synchronous JDBC, socket read hoặc `Future.get`.
- p95/p99 latency tăng khi số request concurrency tăng, dù CPU chưa bão hòa.
- Health endpoint phản hồi chậm nếu cùng event-loop bị block.
- Queues/outbound pools và timeout/rejection tăng khi downstream quá tải.

Micrometer/Actuator có `http.server.requests`, JVM threads/memory/GC/process metrics tùy registry. `/actuator/metrics` là diagnostic endpoint, **không** là time-series DB đầy đủ cho p99 nhiều pods. Với Prometheus/OpenTelemetry, kết hợp HTTP latency histograms, errors, Reactor Netty connection metrics, boundedElastic queue utilization và downstream latency.

Đừng gắn request path chứa user ID, session ID, access token hoặc raw query vào metric labels; dùng low-cardinality route templates như `/api/legacy/{sku}`. Actuator `metrics/env/threaddump/heapdump` cần bảo vệ, không expose công khai.

## 10. Timeout, HTTP errors và đã commit stream

Có ba mốc khác nhau:

1. Request chưa xử lý/headers chưa gửi.
2. Server bắt đầu gửi SSE/NDJSON data, **headers đã committed**.
3. Client đã nhận được một số events nhưng Flux error hoặc downstream mất kết nối.

Ở mốc 1, exception handler có thể trả status 400/503/504. Ở mốc 2/3, không thể đảm bảo server sẽ đổi status 200 thành 500 vì HTTP response đã được commit. Client streaming phải phân biệt unexpected stream termination, heartbeat timeout, explicit application-level error event và network failures.

Trong demo:

- `GET /api/readings/sse?count=0` → 400 do validation trước khi tạo Flux.
- `GET /api/legacy/sku` timeout → 504 nếu source chưa có response committed.
- Scheduler reject → 503.
- Một Flux đã gửi 2 events rồi `onError` → có thể kết thúc response với network/protocol error; **không** chắc status đổi từ 200.
- Nếu client cancel → `doFinally(CANCEL)` cập nhật counter, nhưng không hứa legacy blocking task chắc chắn dừng.

**Không áp `onErrorResume(ex -> Flux.empty())` tràn lan**. Điều đó có thể che mất partial failure, khiến client tưởng stream hoàn tất bình thường. Khi cần business fallback, phải giới hạn exception classes, ghi metrics và phát tín hiệu/format mà client hiểu.

## 11. Thiết kế streaming API production

### 11.1. Authentication, authorization và dữ liệu nhạy cảm

- SSE thường giữ HTTP connection lâu; xác thực lúc mở connection và đánh giá token expiration/reauth policy cho stream dài.
- Browser `EventSource` không cho đặt custom Authorization headers theo cùng cách như fetch; dùng architecture phù hợp (same-origin cookie/cors với CSRF/threat model, hoặc fetch streaming dùng bearer), không đưa token lên URL query.
- Kiểm object/tenant authorization cho từng stream subscription. Không dựa vào việc client đã truy cập homepage.
- Không đưa email/user IDs/session IDs vào SSE `id` hoặc metric labels. `Last-Event-ID` từ client là input không đáng tin và cần validate/bounds khi có replay.
- CORS và cache headers cần cấu hình theo origin/data sensitivity, không `Access-Control-Allow-Origin: *` tùy tiện với dữ liệu riêng tư.
- Tránh log nguyên body/PII trên mỗi event vì làm tăng I/O và rủi ro lộ dữ liệu.

### 11.2. Giới hạn tài nguyên và overload

- Giới hạn **active streams per user/tenant**, tổng connections, max stream duration và idle timeout.
- Với hot source, xác định buffer/drop/replay policy và metrics của slow consumers.
- Giới hạn `count`/`periodMs` như demo **không đủ** chống DDoS hoặc multi-connection overload.
- Với blocking bridge, ngoài bounded scheduler cần native DB/HTTP timeouts, connection pool limits, request deadlines và global admission controls.
- Nếu overload, 429/503 với retry guidance hợp lý tốt hơn nhận vô hạn rồi kéo p99 lên nhiều giây.
- Không chạy load tests vào production/third-party endpoint nếu chưa được phép; dùng staging với test data và guardrails rõ.

### 11.3. Gateway/proxy ảnh hưởng streaming

Cần kiểm:

- Nginx/Ingress buffering response hoặc caching làm SSE đến thành “một cục” thay vì từng event.
- Gateway idle timeout có ngắn hơn heartbeat interval không?
- HTTP/1.1/HTTP/2 keep-alive, compression và proxy limits.
- App base path `spring.webflux.base-path`, route annotations và reverse proxy rewrite có nhất quán không?
- DNS/load balancer reconnect dẫn subscriber sang một replica khác; local memory `Flux.interval` không có replay across replicas.
- Client có reconnect exponential backoff và xử lý duplicated/gap events nếu business yêu cầu.

**Ghi chú:** `X-Accel-Buffering: no` là một gợi ý riêng của Nginx trong những setup có hỗ trợ; nó không tự tắt mọi proxy buffering. Đừng gán một header rồi mặc định mọi CDN/ingress sẽ phát chunks theo lịch.

### 11.4. Khác biệt giữa API streaming và infinite storage

`Flux` theo luồng làm giảm nhu cầu materialize một list lớn nhưng không chứng minh bounded memory trong mọi pipeline. Các operators như `collectList()`, `buffer()` không giới hạn, `cache()` và `replay()` có thể giữ rất nhiều items. Pooled `DataBuffer` hoặc JSON object allocations vẫn tiêu thụ heap/direct memory.

Nếu client cần replay/historical data, dùng durable message log/database cursor, pagination và checkpoint. SSE/NDJSON chỉ là transport representation, không thay persistent event store.

## 12. Ma trận lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách chẩn đoán/sửa |
| --- | --- | --- |
| Controller trả Flux nhưng request khác chậm | Blocking code chạy trên Netty event-loop | Thread dump, audit sleep/JDBC/`block()`; offload nguồn |
| `Mono.just(blockingCall())` vẫn chặn | Blocking call đã chạy trước khi tạo Mono | `Mono.fromCallable(...).subscribeOn(boundedElastic)` |
| `publishOn` đặt cuối không giải quyết | Nó không đổi scheduler của source phía trước | `subscribeOn` nguồn blocking |
| Scheduler threads tăng nhiều | Tạo scheduler mới trên từng request | Dùng singleton scheduler, dispose bean lifecycle |
| Latency legacy tăng dù Netty không block | Queue của boundedElastic/upstream saturation | Metrics queue/timeout, native client timeouts và load shedding |
| `RejectedExecutionException` khi tải lớn | Scheduler queue/task cap đã chạm | Trả 503 có kiểm soát, giảm load hoặc scale có căn cứ |
| Client nhận 504 nhưng DB vẫn xử lý | Timeout không dừng blocking call | Driver timeouts, cancellation support, idempotency |
| SSE nhận toàn events cùng lúc | Client/proxy buffering, compression hoặc nguồn emit cùng lúc | `curl -N`, kiểm proxy buffering, thời điểm phát |
| NDJSON parse lỗi | Client coi nhiều dòng như một JSON object/array | Parse line-by-line hoặc streaming decoder |
| SSE endpoint 406 | `Accept`/`produces` không khớp | Dùng `text/event-stream` |
| NDJSON endpoint 406 | Client chỉ chấp nhận `application/json` | Dùng `application/x-ndjson` |
| Service returns Mono.empty nhưng vẫn 200 empty | HTTP contract chưa map empty→404 | Domain handler/advice có chủ đích |
| `DataBufferLimitException` | Codec buffering payload quá lớn | Giới hạn input, stream thay collect, chỉnh memory setting có cân nhắc |
| Heap/direct memory tăng | Buffer/`cache` không bounded, DataBuffer không release | Profiling và release theo ownership |
| SSE active không về 0 ngay khi đóng tab | Disconnect detection/network async | Heartbeat, logs, eventual cleanup tests |
| Counter cancel khác số requests | Multiple subscriptions, disconnect timing, finalize | Định nghĩa metric boundary, tracing |
| `StepVerifier` pass nhưng network fail | Unit test không chạy Netty/proxy | `RANDOM_PORT` hoặc deployment-level test |
| `@WebFluxTest` thiếu service bean | Slice không scan `@Service` | `@MockitoBean`/import đúng |
| App chạy Spring MVC thay vì WebFlux | Có cả MVC và WebFlux starter | Kiểm dependencies, web-application-type |
| 200 đã gửi rồi source error | Headers committed | Test stream termination/error protocol |
| BlockHound không báo lỗi | Không cài, agent/runtime không tương thích hoặc test path không đúng | Cấu hình đúng instrumentation và thử trên real event loop |
| `Thread.sleep` trên boundedElastic được xem là “không block” | Nó vẫn block một worker, chỉ được offload | Giới hạn workers/queue; ưu tiên non-blocking library |

## 13. Checklist tự đánh giá

- [ ] App thực sự chạy **Spring WebFlux + Reactor Netty**, không vô tình chạy Servlet MVC.
- [ ] SSE trả `text/event-stream` với `ServerSentEvent<T>`; NDJSON trả `application/x-ndjson`.
- [ ] Mỗi event/object được phát qua Flux và codec, không `collectList()` toàn stream.
- [ ] `Flux.defer` giúp metrics/subscription lifecycle đúng thời điểm; `doFinally` xử lý complete/error/cancel.
- [ ] Không có `Thread.sleep`/synchronous JDBC/`RestTemplate`/`Future.get` hoặc `Mono.block()` trực tiếp trên event loop.
- [ ] Nếu cần legacy blocking, dùng `Mono.fromCallable(...).subscribeOn(boundedElastic)`, timeout driver và resource bounds.
- [ ] Scheduler chuyên biệt tạo một lần, dispose đúng lifecycle; không tạo pool mới cho mỗi request.
- [ ] Có giới hạn số events/interval, connections và admission control khi triển khai thật.
- [ ] Đã phân biệt cold streams và hot external data; có buffer/drop/replay policy rõ.
- [ ] HTTP errors trước khi commit và errors sau khi stream bắt đầu được thiết kế riêng.
- [ ] Đã kiểm WebTestClient real HTTP SSE/NDJSON, không chỉ mock publisher.
- [ ] Đã có StepVerifier tests onNext/onComplete/cancel và offloading test.
- [ ] Không dùng `expectBodyList` với infinite stream; test dùng `returnResult` và `thenCancel()`.
- [ ] Có SLO latency, error rate, upstream pool queue, memory/direct buffers, event-loop utilization và active streams metrics.
- [ ] CORS/auth/tenant/data sensitivity cho SSE đã kiểm; không ghi tokens/PII vào URLs/logs.
- [ ] Proxy buffering/heartbeat/reconnect và Last-Event-ID replay được kiểm khi nghiệp vụ yêu cầu.
- [ ] Load test chỉ chạy trong môi trường đã được cho phép; không dùng 11 functional tests để chứng minh capacity production.

## 14. Câu hỏi tự kiểm tra

**1. Trả về `Flux<T>` có chắc WebFlux không block không?**  
Không. Mã bên trong stream có thể gọi JDBC/HTTP synchronous, `Thread.sleep` hoặc `block()`.

**2. Tại sao `Mono.just(legacy.fetch())` chưa đúng?**  
Vì `legacy.fetch()` đã thực thi và có thể block **trước** khi Mono được tạo. Dùng `Mono.fromCallable`.

**3. `subscribeOn` và `publishOn` khác gì với nguồn blocking?**  
`subscribeOn` đặt execution của subscription/source; `publishOn` chuyển downstream operators, không cứu lời gọi blocking đã diễn ra trước đó.

**4. Vì sao dùng `newBoundedElastic` thay vì `parallel`?**  
`boundedElastic` phù hợp cô lập blocking calls có giới hạn threads/queue; `parallel` không dành cho blocking I/O.

**5. Timeout 504 có chắc task JDBC đồng bộ đã dừng không?**  
Không. Driver có thể phớt lờ cancellation/interrupt; cần native timeout và resource controls.

**6. SSE và NDJSON khác JSON array thế nào?**  
SSE có event frames `id/event/data`; NDJSON mỗi dòng là một JSON object; cả hai phù hợp truyền từng phần.

**7. `Flux.interval` có tự lưu lại events khi client reconnect không?**  
Không. Demo là cold publisher tạo dữ liệu mới theo subscription, không có event log/replay.

**8. Vì sao không dùng `expectBodyList` cho infinite SSE?**  
Nó có thể chờ stream complete mãi; dùng `returnResult`/StepVerifier và cancel sau số events cần kiểm.

**9. `doFinally(CANCEL)` có chứng minh browser đã nhận tất cả events không?**  
Không. Nó phản ánh lifecycle subscription tại boundary được đo, không bảo đảm delivery end-to-end.

**10. Khi SSE đã trả 200 rồi pipeline phát lỗi, HTTP status có đổi thành 500 không?**  
Không bảo đảm. Headers có thể đã commit; client phải xử lý stream termination.

**11. `@WebFluxTest` có khởi động Netty TCP server thật không?**  
Không. Dùng `@SpringBootTest(RANDOM_PORT)` để kiểm real HTTP connector.

**12. Tại sao `periodMs` tối thiểu 25 vẫn chưa đủ bảo vệ production?**  
Vì client có thể mở rất nhiều connections; cần quotas/rate limiting, auth và monitoring.

**13. WebClient có làm downstream API nhanh hơn không?**  
Không. Nó tránh chặn event loop trong lúc I/O, nhưng chịu network/upstream latency, pool limits và server quotas.

**14. Nếu streaming client chậm, `onBackpressureBuffer()` mặc định là an toàn tuyệt đối?**  
Không. Buffer không giới hạn có thể gây OOM; cần strategy bounded và policy khi tràn.

**15. BlockHound có phải một dependency mặc định của WebFlux?**  
Không. Đây là instrumentation tùy chọn, có yêu cầu tương thích JDK/Reactor và cấu hình test.

## 15. Tài liệu chính thức

- Spring Boot 3.5 — **Reactive Web Applications**, WebFlux/Netty và application setup: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Framework 6.2 — **WebFlux Reactive Core**, streaming SSE/NDJSON và DataBuffer: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework — **Annotated WebFlux Controllers**, response streaming: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html
- Project Reactor — **FAQ: How Do I Wrap a Synchronous, Blocking Call?**: https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking
- Project Reactor — **Schedulers and Threading**: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Project Reactor — **Testing with StepVerifier**: https://projectreactor.io/docs/core/release/reference/testing.html
- Spring Framework — **WebTestClient (streaming returnResult)**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Boot 3.5 — **Testing Spring Boot Applications**: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — **Actuator Metrics**: https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html
- Spring Boot 3.5.16 — **Release and last OSS release notice (25/06/2026)**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
- Reactor BlockHound repository/docs (optional instrumentation): https://github.com/reactor/BlockHound

**Kết luận:** Spring WebFlux streaming đòi hỏi **cả transport phù hợp (SSE/NDJSON)** lẫn **pipeline thực sự không chặn event loop**. Hãy truyền dữ liệu qua `Flux` với lifecycle/cancellation rõ ràng, không gom vô hạn vào memory; offload đúng những synchronous legacy operations bằng `Mono.fromCallable.subscribeOn(boundedElastic)` với scheduler có giới hạn; giám sát queue/timeouts, và kiểm cả publisher signals lẫn HTTP streaming thật. Không đánh đồng “có Flux” với “hệ thống đã non-blocking từ đầu đến cuối”.