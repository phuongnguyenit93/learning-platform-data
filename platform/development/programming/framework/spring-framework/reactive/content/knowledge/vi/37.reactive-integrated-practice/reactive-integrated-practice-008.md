# Đo tải và giải thích lựa chọn reactive bằng bằng chứng trong Spring WebFlux

## 1. Mục tiêu: chọn kiến trúc bằng số liệu

Spring WebFlux và Reactor cung cấp mô hình bất đồng bộ, non-blocking và backpressure. Nhưng việc ứng dụng dùng `Mono`/`Flux` không tự chứng minh rằng nó nhanh hơn, chịu tải tốt hơn hoặc dùng ít tài nguyên hơn Spring MVC.

Lựa chọn reactive cần gắn với một giả thuyết có thể kiểm tra. Ví dụ:

- Với nhiều request đồng thời và phần lớn thời gian chờ I/O, WebFlux có thể giữ ít thread xử lý hơn vì không cần giữ một thread riêng trong lúc chờ network/database.
- Với workload CPU-bound, reactive không làm giảm số phép tính; giới hạn CPU vẫn là số core, thuật toán và chi phí đồng bộ.
- Khi downstream chậm, reactive có thể truyền demand ngược và giới hạn công việc đang chạy, nhưng queue không giới hạn hoặc `flatMap` concurrency quá lớn vẫn có thể làm cạn bộ nhớ.
- Với tải thấp, ứng dụng đơn giản hoặc thư viện chủ yếu blocking, MVC có thể dễ phát triển và vận hành hơn mà không có bất lợi hiệu năng đáng kể.

Bài thực hành này hướng dẫn đo tải và viết lập luận kỹ thuật dựa trên bằng chứng, thay vì chọn reactive theo cảm tính.

Sau bài học, bạn có thể:

1. Đặt giả thuyết hiệu năng cho workload I/O-bound, CPU-bound và tải hỗn hợp.
2. Thiết kế phép đo có baseline, workload, môi trường và tiêu chí thành công rõ ràng.
3. Phân biệt throughput, latency, concurrency, error rate và saturation.
4. Dùng load generator theo mô hình open workload để phát request theo tốc độ xác định.
5. Đọc p50/p95/p99, dropped iterations, CPU, heap, GC và thread count.
6. Áp dụng Little's Law để kiểm tra quan hệ giữa throughput, latency và số request đang xử lý.
7. Kiểm thử ví dụ WebFlux reactive so với tác vụ blocking được offload sang `boundedElastic`.
8. Hiểu giới hạn benchmark mô phỏng và chuyển sang benchmark với downstream thật.
9. So sánh WebFlux với Spring MVC theo điều kiện công bằng.
10. Viết báo cáo kiến trúc có số liệu, phương pháp, kết quả và giới hạn diễn giải.

Dự án mẫu dùng Java 17, Spring Boot 3.3.5, Spring WebFlux, Actuator, Micrometer Prometheus, Reactor Test và k6. Các con số benchmark trong bài là ví dụ về phương pháp; không phải kết quả chạy trên một máy cụ thể.

## 2. Reactive có lợi trong trường hợp nào?

Reactive thường đáng cân nhắc khi hệ thống có nhiều I/O bất đồng bộ và cần phục vụ nhiều tác vụ đồng thời.

### 2.1. Workload I/O-bound

Một request có thể nhận HTTP request, gọi hai dịch vụ HTTP, chờ database, ghép kết quả rồi trả JSON. Nếu client và driver đều non-blocking, thread xử lý request không phải nằm chờ suốt thời gian network I/O. Reactor có thể tiếp tục xử lý request khác trong khi chờ tín hiệu.

Điều này hữu ích khi:

- Có nhiều kết nối đồng thời.
- Thời gian chờ I/O lớn so với thời gian CPU.
- Có nhiều downstream calls có thể chạy song song.
- Cần streaming/backpressure.
- Hệ thống phải kiểm soát lượng công việc đang chờ.

### 2.2. Workload CPU-bound

Mã hóa ảnh, nén dữ liệu, tính toán thống kê hoặc xử lý thuật toán nặng vẫn tiêu thụ CPU dù được viết bằng `Flux`. Reactive không làm một phép tính 20 ms trở thành 2 ms. Nếu CPU đã bão hòa, tăng số request đồng thời có thể chỉ làm queue và latency tăng.

Với CPU-bound workload, tập trung vào thuật toán, số core, allocation/GC, lock contention, kích thước dữ liệu và concurrency phù hợp.

### 2.3. Workload blocking

Nếu request gọi JDBC blocking, `Thread.sleep`, SDK đồng bộ hoặc file API blocking, thread sẽ bị giữ trong lúc chờ. Có thể offload blocking work khỏi event loop bằng `Schedulers.boundedElastic()`, nhưng vẫn cần thread thực hiện từng tác vụ blocking. Cần giới hạn worker/queue và cân nhắc client/driver reactive nếu lợi ích tổng thể xứng đáng.

### 2.4. Không có lựa chọn mặc định cho mọi service

| Đặc điểm workload | Hướng cân nhắc |
|---|---|
| Nhiều I/O đồng thời, driver non-blocking | WebFlux/reactive có tiềm năng rõ |
| Streaming lớn và cần backpressure | Reactive thường phù hợp |
| Ít request, CRUD đơn giản, thư viện blocking | MVC có thể đơn giản hơn |
| Chủ yếu CPU-bound | Profile thuật toán/CPU trước |
| Phụ thuộc nhiều SDK blocking | Đánh giá chi phí offload hoặc thay SDK |
| Tải thấp, API đồng bộ | MVC có thể là lựa chọn hợp lý |
| Tải hỗn hợp | Đo từng loại endpoint và toàn hệ thống |

Không dùng một benchmark synthetic duy nhất để kết luận toàn bộ kiến trúc sản phẩm.

## 3. Bắt đầu bằng giả thuyết có thể bác bỏ

Ví dụ: với workload chủ yếu chờ I/O 100 ms và tải đến 500 request/giây, xử lý non-blocking có thể giữ thread usage ổn định hơn cách chạy blocking trên pool giới hạn, trong khi vẫn giữ p95 và error rate trong ngưỡng mục tiêu.

Giả thuyết này có thể bị bác bỏ nếu hai cách xử lý có latency/tài nguyên tương đương, reactive bị giới hạn bởi scheduler hoặc downstream, blocking pool đủ lớn để xử lý workload, load generator không phát được tốc độ yêu cầu, hoặc nút thắt nằm ở CPU/serialization thay vì I/O wait.

| Thành phần | Câu hỏi |
|---|---|
| Workload | I/O-bound, CPU-bound hay hỗn hợp? |
| Tải | Bao nhiêu request/giây, bao nhiêu client đồng thời? |
| Payload | Kích thước request/response trung bình và p95? |
| Downstream | Thời gian chờ và error rate ra sao? |
| Baseline | So với cách triển khai nào? |
| Metrics | Đo latency, throughput, CPU, heap, GC, threads nào? |
| SLO | p95/p99 và error rate tối đa là bao nhiêu? |
| Điều kiện dừng | Khi nào xem là đã bão hòa? |

Không chọn trước kết quả mong muốn. Nếu MVC đáp ứng SLO với chi phí thấp hơn và code đơn giản hơn, đó cũng là kết luận hợp lệ.

## 4. Những đại lượng cần đo

### 4.1. Throughput

Throughput là số request hoặc operation hoàn tất trong một đơn vị thời gian, thường là requests/second (RPS).

Phân biệt:

- **Offered load**: tốc độ load generator cố gắng gửi.
- **Accepted/requested rate**: số request thực sự tới server.
- **Completed throughput**: số request hoàn tất.
- **Successful throughput**: số request thành công mỗi giây.

Nếu offered load là 500 RPS nhưng generator dropped iterations hoặc server trả lỗi, không được báo throughput thành công là 500 RPS.

### 4.2. Latency và percentile

Latency là thời gian từ lúc gửi request tới lúc nhận response hoàn tất.

- **p50**: một nửa request có latency không lớn hơn giá trị này.
- **p95**: 95% request có latency không lớn hơn giá trị này.
- **p99**: 99% request có latency không lớn hơn giá trị này.

Average có thể che khuất tail latency. Hai hệ thống cùng average 120 ms nhưng một hệ thống có p99 180 ms và hệ thống còn lại p99 2 giây sẽ đem lại trải nghiệm khác nhau.

### 4.3. Error rate

Đo HTTP 5xx, HTTP 4xx không mong đợi, timeout, connection reset/refused, request bị từ chối do quá tải và iteration không khởi chạy từ load generator. Không gộp tất cả lỗi thành một con số mà bỏ mất loại lỗi và nguyên nhân.

### 4.4. Resource usage

| Chỉ số | Ý nghĩa |
|---|---|
| CPU process/system | Mức sử dụng năng lực tính toán |
| Heap used/committed | Bộ nhớ Java |
| GC pause/count | Chi phí thu gom bộ nhớ |
| Live/peak thread count | Mức sử dụng thread |
| Active connections | Kết nối đang mở |
| In-flight requests | Request đang xử lý |
| Queue depth | Công việc đang chờ |
| Network bytes | Lưu lượng vào/ra |
| Connection pool pending | Số tác vụ chờ connection |
| Scheduler pending tasks | Tác vụ chờ scheduler nếu được instrument |

Một metric riêng lẻ không đủ để kết luận. CPU thấp nhưng latency cao có thể do downstream hoặc queue; CPU cao nhưng throughput tăng cũng có thể là trade-off chấp nhận được.

## 5. Closed workload và open workload

### 5.1. Closed workload

Một số virtual users liên tục gửi request mới sau khi request trước hoàn tất. Khi hệ thống chậm, mỗi user tự động gửi ít request hơn. Mô hình này phù hợp với một số user tương tác, nhưng có thể che giấu việc hệ thống không còn đáp ứng tốc độ đến như kỳ vọng.

### 5.2. Open workload

Load generator phát request theo arrival rate cố định, ví dụ 200 request/giây, bất kể response trước mất bao lâu. Mô hình này hữu ích khi muốn biết nếu hệ thống phải nhận 200 request/giây thì latency/error thay đổi ra sao.

Trong k6 có thể dùng executor `constant-arrival-rate`.

### 5.3. `dropped_iterations` cần được điều tra

Nếu k6 không có đủ VU để khởi chạy iteration đúng lịch, `dropped_iterations` tăng. Nguyên nhân có thể là ứng dụng phản hồi quá chậm, `preAllocatedVUs`/`maxVUs` không đủ, máy k6 thiếu CPU/network hoặc load generator đã bão hòa.

Không tự động quy `dropped_iterations` là lỗi server. Xem CPU và tài nguyên trên máy load generator, đồng thời kiểm tra request có tới server không.

## 6. Thiết kế phép đo công bằng

Muốn so sánh reactive và blocking, giữ các biến khác giống nhau:

- Cùng business logic và response shape.
- Cùng kích thước payload.
- Cùng thời gian downstream hoặc cùng dữ liệu thật.
- Cùng JDK và JVM options.
- Cùng CPU/memory limits.
- Cùng HTTP version, TLS, compression và keep-alive.
- Cùng logging/metrics/tracing overhead.
- Cùng connection pool và timeout policy.
- Cùng load generator và network path.
- Cùng thời gian warm-up và measurement window.

Không chạy hai bài test cùng lúc trên một máy vì chúng tranh CPU, heap, network và scheduler. Chạy từng workload độc lập, lặp lại nhiều lần và giữ cùng cấu hình.

Một quy trình thứ tự cân bằng:

1. Khởi động ứng dụng và đợi ổn định.
2. Chạy warm-up.
3. Đo reactive.
4. Nghỉ hoặc reset trạng thái phù hợp.
5. Đo blocking.
6. Lượt sau đổi thứ tự để giảm ảnh hưởng nhiệt/JIT/cache.
7. Thực hiện ít nhất 3 lượt có cùng cấu hình.
8. Báo median các lượt và giữ từng file kết quả.

Nếu hai endpoint cùng nằm trong một JVM, chúng vẫn chia sẻ HTTP server, event loops, heap và CPU. Điều đó hữu ích cho lab minh họa nhưng không tương đương benchmark hai kiến trúc production độc lập.

Không thay đổi nhiều biến cùng lúc. Nếu tăng `flatMap` concurrency, đổi heap, đổi pool size và đổi payload trong cùng lượt, sẽ khó biết yếu tố nào tạo ra kết quả.

## 7. Quy trình thực nghiệm đề xuất

1. **Build**: dùng cùng commit/build, ghi version JDK, Spring Boot, Reactor và OS.
2. **Deploy**: chạy trong cùng CPU/memory limit, cùng JVM heap và environment.
3. **Warm-up**: gửi tải thấp trong 30–60 giây để JIT và connection pool ổn định.
4. **Baseline**: đo tải rất thấp để biết latency nền.
5. **Load steps**: thử các mức arrival rate tăng dần, ví dụ 50, 100, 200, 400, 600 RPS.
6. **Steady state**: mỗi mức giữ 60–180 giây sau warm-up.
7. **Stress**: tăng tải tới khi SLO vi phạm, queue tăng liên tục hoặc error rate vượt ngưỡng.
8. **Recovery**: giảm tải và quan sát queue/latency có trở về bình thường không.
9. **Repeat**: lặp lại ít nhất 3 lượt.
10. **Analyze**: tổng hợp p50/p95/p99, throughput, errors, CPU, memory, GC, threads và dropped iterations.

Các mức tải chỉ là ví dụ để lập kế hoạch; điều chỉnh theo năng lực máy, thời gian xử lý và SLO thực tế.

## 8. Little's Law: throughput, latency và concurrency

Little's Law:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số request trung bình đang ở trong hệ thống (in-flight).
- \(\lambda\): throughput trung bình, request/giây.
- \(W\): thời gian trung bình trong hệ thống, tính bằng giây.

Ví dụ throughput 300 request/giây và latency trung bình 0,1 giây:

\[
L = 300 \times 0.1 = 30
\]

Số request trung bình đang ở trong hệ thống xấp xỉ 30. Nếu throughput giữ nguyên nhưng latency tăng lên 0,5 giây, in-flight trung bình tăng lên khoảng 150 request.

Hệ thống cần giữ nhiều request đồng thời hơn; nếu mỗi request giữ buffer, object, connection hoặc state, memory pressure cũng có thể tăng.

Little's Law mô tả quan hệ trung bình trong hệ thống ổn định; không dùng một percentile latency thay cho \(W\) trung bình rồi diễn giải như đẳng thức chính xác.

## 9. Xác định saturation point

Saturation point là vùng mà tăng offered load không còn làm successful throughput tăng tương ứng, trong khi latency, queue hoặc error rate tăng nhanh.

Dấu hiệu:

- p95/p99 tăng dốc.
- Successful throughput chững lại.
- Error/timeout tăng.
- `dropped_iterations` tăng.
- CPU tiến gần mức tối đa hoặc một core bão hòa.
- Queue hoặc pending tasks tăng liên tục.
- Heap/GC pause tăng.
- Connection pool cạn hoặc pending acquire tăng.

### 9.1. Throughput plateau

Bảng sau chỉ minh họa hình dạng saturation, không phải số đo thực tế:

| Offered load | Successful throughput | p95 | Error rate |
|---:|---:|---:|---:|
| 100 RPS | 100 RPS | 115 ms | 0% |
| 200 RPS | 200 RPS | 125 ms | 0% |
| 400 RPS | 390 RPS | 210 ms | 0.2% |
| 600 RPS | 420 RPS | 950 ms | 4% |
| 800 RPS | 425 RPS | 2.4 s | 12% |

Ở mức 600–800 RPS, offered load tăng mạnh nhưng successful throughput gần như không tăng. Hệ thống đang quá tải; chỉ tăng VU hoặc timeout không giải quyết được nút thắt.

### 9.2. Tìm nguyên nhân

- CPU cao: profile code, serialization, algorithm, lock hoặc GC.
- CPU thấp nhưng latency cao: kiểm tra downstream, connection pool, queue, network và timeout.
- Thread tăng mạnh: kiểm tra blocking calls và scheduler.
- Queue tăng: giảm producer rate, giới hạn concurrency hoặc chọn overflow policy.
- GC cao: kiểm tra allocation, payload copies và object retention.
- Một core cao trong khi tổng CPU thấp: có thể có event loop hoặc lock contention.

## 10. Dự án lab: WebFlux reactive wait và blocking work được offload

Dự án sau tạo hai endpoint có cùng response shape và cùng thời gian chờ cấu hình:

- `/bench/reactive`: dùng `Mono.delay`, mô phỏng operation chờ bất đồng bộ.
- `/bench/blocking`: dùng `Thread.sleep` trong `Mono.fromCallable`, offload sang `Schedulers.boundedElastic()`.

Mục tiêu là quan sát khác biệt giữa việc giữ thread trong lúc chờ và việc đăng ký timer non-blocking.

**Giới hạn quan trọng:** đây là benchmark mô phỏng thời gian chờ, không phải benchmark hoàn chỉnh giữa Spring MVC và WebFlux, cũng không đại diện cho mọi database/HTTP client. `Mono.delay` không thay thế remote network call thật. Dùng lab để học phương pháp, sau đó thay phần chờ bằng downstream thật khi ra quyết định kiến trúc.

### 10.1. Cấu trúc

```text
reactive-load-evidence/
├── pom.xml
├── load/
│   └── benchmark.js
└── src/
    ├── main/
    │   ├── java/edu/demo/load/
    │   │   ├── LoadApplication.java
    │   │   ├── WorkService.java
    │   │   ├── WorkController.java
    │   │   └── WorkResponse.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/edu/demo/load/
            ├── WorkServiceTests.java
            └── WorkControllerTests.java
```

### 10.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>reactive-load-evidence</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
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
```

Spring Boot dependency management chọn các version tương thích của Reactor và Micrometer. Không thêm version ngẫu nhiên cho `reactor-core` hoặc `micrometer-registry-prometheus` nếu đang dùng Boot BOM.

### 10.3. `LoadApplication.java`

```java
package edu.demo.load;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoadApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoadApplication.class, args);
    }
}
```

### 10.4. `WorkResponse.java`

```java
package edu.demo.load;

public record WorkResponse(
        String mode,
        long delayMs,
        String status) {
}
```

### 10.5. `WorkService.java`

```java
package edu.demo.load;

import java.time.Duration;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class WorkService {

    public Mono<WorkResponse> reactive(long delayMs) {
        return Mono.delay(Duration.ofMillis(delayMs))
                .map(ignored ->
                        new WorkResponse("reactive", delayMs, "ok"));
    }

    public Mono<WorkResponse> blockingOffloaded(long delayMs) {
        return Mono.fromCallable(() -> {
                    try {
                        Thread.sleep(delayMs);
                    }
                    catch (InterruptedException error) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                                "blocking work interrupted", error);
                    }

                    return new WorkResponse(
                            "blocking-offloaded", delayMs, "ok");
                })
                .subscribeOn(Schedulers.boundedElastic());
    }
}
```

Hai method tạo cùng loại response và mô phỏng cùng khoảng chờ. `reactive` đăng ký timer mà không giữ một thread riêng để ngủ. `blockingOffloaded` dùng worker bounded elastic trong lúc `Thread.sleep` đang chặn.

Không gọi `Thread.sleep` trực tiếp trên Netty event loop. Trong ứng dụng thực tế, thay sleep bằng I/O thật hoặc adapter blocking được cô lập và có giới hạn.

### 10.6. `WorkController.java`

```java
package edu.demo.load;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class WorkController {

    private final WorkService workService;

    public WorkController(WorkService workService) {
        this.workService = workService;
    }

    @GetMapping("/bench/reactive")
    public Mono<WorkResponse> reactive(
            @RequestParam(defaultValue = "100") long delayMs) {

        return validate(delayMs)
                .flatMap(workService::reactive);
    }

    @GetMapping("/bench/blocking")
    public Mono<WorkResponse> blocking(
            @RequestParam(defaultValue = "100") long delayMs) {

        return validate(delayMs)
                .flatMap(workService::blockingOffloaded);
    }

    private Mono<Long> validate(long delayMs) {
        if (delayMs < 0 || delayMs > 1000) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "delayMs must be between 0 and 1000"));
        }

        return Mono.just(delayMs);
    }
}
```

Giới hạn delay ngăn client biến endpoint lab thành tác vụ ngủ kéo dài không kiểm soát. Trong production, giới hạn workload phải đến từ cấu hình và policy do service owner quản lý, không tin giá trị tùy ý từ caller.

### 10.7. `application.properties`

```properties
spring.application.name=reactive-load-evidence
server.port=8080

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.endpoint.health.show-details=never
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.tags.application=${spring.application.name}
```

Actuator cung cấp health và metrics. Prometheus endpoint xuất metric khi registry có mặt. Trong production, giới hạn network access hoặc bảo vệ actuator endpoints; không công khai mọi management endpoint ra Internet.

### 10.8. `WorkServiceTests.java`

```java
package edu.demo.load;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class WorkServiceTests {

    private final WorkService service = new WorkService();

    @Test
    void reactiveDelayCanBeTestedWithVirtualTime() {
        StepVerifier.withVirtualTime(
                        () -> service.reactive(500))
                .thenAwait(Duration.ofMillis(500))
                .assertNext(result -> {
                    assertEquals("reactive", result.mode());
                    assertEquals(500, result.delayMs());
                    assertEquals("ok", result.status());
                })
                .verifyComplete();
    }

    @Test
    void blockingWorkIsOffloadedAndCompletes() {
        StepVerifier.create(service.blockingOffloaded(10))
                .assertNext(result -> {
                    assertEquals("blocking-offloaded", result.mode());
                    assertEquals(10, result.delayMs());
                    assertEquals("ok", result.status());
                })
                .verify(Duration.ofSeconds(3));
    }
}
```

Virtual time áp dụng cho Reactor timer được tạo trong supplier của `withVirtualTime`. Nó không làm `Thread.sleep` chạy tức thời; test blocking dùng thời gian thực với timeout hữu hạn.

### 10.9. `WorkControllerTests.java`

```java
package edu.demo.load;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WorkControllerTests {

    @Autowired
    WebTestClient client;

    @Test
    void reactiveEndpointReturnsExpectedPayload() {
        client.get()
                .uri("/bench/reactive?delayMs=5")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.mode").isEqualTo("reactive")
                .jsonPath("$.delayMs").isEqualTo(5)
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void blockingEndpointReturnsExpectedPayload() {
        client.get()
                .uri("/bench/blocking?delayMs=5")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.mode").isEqualTo("blocking-offloaded")
                .jsonPath("$.delayMs").isEqualTo(5)
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void delayOutsideAllowedRangeReturnsBadRequest() {
        client.get()
                .uri("/bench/reactive?delayMs=5000")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

Bộ test Maven gồm hai unit tests và ba integration tests. Chúng xác minh semantics của endpoint, không đo throughput. Load testing được thực hiện riêng bằng k6.

### 10.10. Chạy ứng dụng

Trong thư mục dự án:

```bash
mvn test
mvn spring-boot:run
```

Kiểm tra reactive:

```bash
curl "http://localhost:8080/bench/reactive?delayMs=100"
```

Response mẫu:

```json
{"mode":"reactive","delayMs":100,"status":"ok"}
```

Kiểm tra blocking-offloaded:

```bash
curl "http://localhost:8080/bench/blocking?delayMs=100"
```

Response mẫu:

```json
{"mode":"blocking-offloaded","delayMs":100,"status":"ok"}
```

Các response trên là kết quả logic mong đợi của chương trình. Maven chưa được tuyên bố là đã chạy trong quá trình biên soạn bài.

## 11. Load test bằng k6 theo constant arrival rate

k6 là load generator độc lập. Dùng `constant-arrival-rate` để gửi một số iteration mỗi giây bất kể request trước mất bao lâu.

### 11.1. `load/benchmark.js`

```javascript
import http from 'k6/http';
import { check } from 'k6';

const target = __ENV.TARGET === 'blocking'
    ? 'blocking'
    : 'reactive';

const expectedMode = target === 'blocking'
    ? 'blocking-offloaded'
    : 'reactive';

const rate = Number(__ENV.RATE || 200);
const delayMs = Number(__ENV.DELAY_MS || 100);
const duration = __ENV.DURATION || '90s';
const preAllocatedVUs = Number(__ENV.PREALLOCATED_VUS || 100);
const maxVUs = Number(__ENV.MAX_VUS || 500);

export const options = {
    scenarios: {
        steady: {
            executor: 'constant-arrival-rate',
            rate,
            timeUnit: '1s',
            duration,
            preAllocatedVUs,
            maxVUs,
            gracefulStop: '10s'
        }
    },
    thresholds: {
        http_req_failed: ['rate<0.01']
    }
};

export default function () {
    const url = `http://127.0.0.1:8080/bench/${target}?delayMs=${delayMs}`;
    const response = http.get(url, { timeout: '5s' });

    check(response, {
        'status is 200': result => result.status === 200,
        'response mode matches target': result => {
            try {
                return result.json('mode') === expectedMode;
            }
            catch {
                return false;
            }
        }
    });
}

export function handleSummary(data) {
    const summaryName = `summary-${target}.json`;

    return {
        [summaryName]: JSON.stringify(data, null, 2),
        stdout: JSON.stringify({
            target,
            metrics: data.metrics
        }, null, 2)
    };
}
```

Script dùng open workload. Mỗi iteration gửi một HTTP request. `http_req_failed` threshold 1% là ngưỡng ví dụ; thay theo SLO thật.

### 11.2. Chạy hai phương án riêng biệt

Warm-up reactive:

```bash
k6 run -e TARGET=reactive -e RATE=50 -e DURATION=30s load/benchmark.js
```

Đo reactive:

```bash
k6 run -e TARGET=reactive -e RATE=200 -e DELAY_MS=100 -e DURATION=90s load/benchmark.js
```

Warm-up blocking:

```bash
k6 run -e TARGET=blocking -e RATE=50 -e DURATION=30s load/benchmark.js
```

Đo blocking:

```bash
k6 run -e TARGET=blocking -e RATE=200 -e DELAY_MS=100 -e DURATION=90s load/benchmark.js
```

Kết quả được lưu thành `summary-reactive.json` và `summary-blocking.json`. Chạy trong thư mục dự án để các file summary dễ tìm.

### 11.3. Tăng tải theo từng bước

Sau mức 200 RPS, có thể thử:

```bash
k6 run -e TARGET=reactive -e RATE=400 -e DURATION=90s load/benchmark.js
k6 run -e TARGET=reactive -e RATE=600 -e DURATION=90s load/benchmark.js
```

Lặp lại tương tự cho blocking. Chỉ tăng khi máy load generator còn đủ tài nguyên và không có dropped iterations đáng kể do chính generator bão hòa.

Không coi 200/400/600 RPS là mức mục tiêu chung. Chọn mức dựa trên dự báo tải và SLO thực tế.

## 12. Đọc kết quả k6

Trong summary, tập trung vào:

| Metric | Ý nghĩa |
|---|---|
| `http_reqs` | Tổng request đã gửi |
| `http_req_duration` | Phân phối thời gian HTTP request |
| `http_req_failed` | Tỷ lệ request lỗi |
| `iterations` | Số iteration hoàn tất |
| `iteration_duration` | Thời gian một iteration |
| `vus` | Số virtual users đang chạy |
| `dropped_iterations` | Iteration không khởi chạy đúng lịch |

Với `http_req_duration`, đọc `avg`, `med`, `p(90)`, `p(95)`, `p(99)` và `max`. Không chỉ chụp lại dòng RPS. Ghi cả offered rate, completed requests, lỗi và dropped iterations.

### 12.1. Bảng kết quả cần lưu

| Run | Target | Offered RPS | Completed RPS | p50 | p95 | p99 | Error % | Dropped iterations |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | reactive | ... | ... | ... | ... | ... | ... | ... |
| 2 | blocking | ... | ... | ... | ... | ... | ... | ... |
| 3 | reactive | ... | ... | ... | ... | ... | ... | ... |
| 4 | blocking | ... | ... | ... | ... | ... | ... | ... |

Điền bằng dữ liệu thực từ file summary. Không dùng số giả định hoặc số đo của máy khác làm kết quả môi trường hiện tại.

### 12.2. Kiểm tra load generator

Nếu `dropped_iterations` khác 0:

1. Xem CPU và memory của máy k6.
2. Tăng `preAllocatedVUs` nếu VU thiếu nhưng generator còn tài nguyên.
3. Kiểm tra `maxVUs` có chạm trần không.
4. Kiểm tra network path.
5. Xem request duration có vượt khả năng duy trì arrival rate không.
6. Nếu generator bão hòa, chạy k6 trên máy riêng.

Nếu generator không tạo đủ tải, không thể kết luận server đã đạt đúng offered rate.

## 13. Thu thập metrics từ Spring Boot Actuator

Mở:

```text
http://localhost:8080/actuator/health
http://localhost:8080/actuator/metrics
http://localhost:8080/actuator/prometheus
```

Có thể xem riêng:

```bash
curl http://localhost:8080/actuator/metrics/http.server.requests
curl http://localhost:8080/actuator/metrics/jvm.memory.used
curl http://localhost:8080/actuator/metrics/jvm.threads.live
curl http://localhost:8080/actuator/metrics/process.cpu.usage
curl http://localhost:8080/actuator/metrics/jvm.gc.pause
```

Tên metric và tag phụ thuộc registry, instrumentation và phiên bản. Dùng `/actuator/metrics` để xem metric thực sự được đăng ký.

### 13.1. Prometheus scrape

Prometheus có thể scrape `GET /actuator/prometheus`. Dashboard nên có HTTP request rate theo URI/status, p50/p95/p99 latency, 5xx rate, heap, GC pause, live threads, process CPU, connection pool active/pending nếu client instrument, Reactor Netty metrics nếu bật và queue/concurrency nếu ứng dụng instrument custom.

Không thêm user ID, request ID hoặc raw URL có path parameter làm label cardinality cao. Dùng route template và nhãn có tập giá trị hữu hạn.

### 13.2. Metrics boundedElastic và event loop

Metric scheduler/Netty không phải lúc nào cũng đăng ký mặc định với cùng tên. Nếu cần quan sát pending tasks, active workers hoặc connection pool, bật instrumentation phù hợp với Reactor/Netty version và kiểm tra metric thực tế.

Không khẳng định boundedElastic queue depth có sẵn chỉ vì Actuator được thêm vào. Nếu cần, instrument bằng Micrometer hoặc dùng JFR/thread dump.

## 14. Đo CPU, heap, GC và thread ngoài HTTP metrics

Các lệnh JDK hữu ích:

```bash
jcmd <pid> VM.version
jcmd <pid> GC.heap_info
jcmd <pid> Thread.print
jcmd <pid> JFR.start name=load settings=profile duration=120s filename=load.jfr
jfr summary load.jfr
```

Thay `<pid>` bằng process ID thật. JFR có thể giúp tìm thread bị block, CPU hotspots, allocation hotspots, GC pauses, lock contention và socket events tùy recording configuration.

Không dùng một thread dump duy nhất để kết luận. Chụp nhiều lần trong lúc tải và đối chiếu thread state/stack.

### 14.1. Thread count không phải mục tiêu duy nhất

Reactive server có thể dùng ít thread event-loop hơn hệ thống blocking, nhưng số thread ít hơn không tự chứng minh tốt hơn. Cần xem throughput thành công, p95/p99, CPU, queue, error/timeout, heap/GC và khả năng phục hồi khi tải giảm.

Nếu reactive giữ ít thread nhưng p99 tăng mạnh vì downstream chậm hoặc scheduler nghẽn, lợi thế đó có thể không đem lại kết quả tốt cho người dùng.

## 15. Đọc benchmark qua ví dụ minh họa

Giả sử sau nhiều lượt đo có bảng sau:

| Metric ở 400 offered RPS | Reactive | Blocking-offloaded |
|---|---:|---:|
| Completed RPS | 398 | 360 |
| p50 | 108 ms | 110 ms |
| p95 | 145 ms | 380 ms |
| p99 | 220 ms | 900 ms |
| Error rate | 0.1% | 1.5% |
| CPU process | 45% | 68% |
| Live threads | 28 | 75 |

Đây là **số liệu giả lập để hướng dẫn cách lập luận**, không phải kết quả thực nghiệm.

Một cách diễn giải có trách nhiệm:

- Ở mức offered load này, cả hai có p50 tương tự.
- p95/p99 của blocking-offloaded cao hơn; có thể có queue ở boundedElastic hoặc contention.
- CPU và live thread cao hơn trong phương án blocking-offloaded ở môi trường giả định.
- Cần kiểm tra dropped iterations, queue, CPU của load generator và số lượt lặp trước khi kết luận.
- Nếu khác biệt lặp lại ổn định, workload thực sự có nhiều I/O wait và chi phí vận hành quan trọng, reactive có thể là lựa chọn hợp lý.

Không viết “reactive nhanh gấp 3 lần” chỉ vì một percentile hoặc một lượt đo cho thấy chênh lệch. Phải nêu mức tải, môi trường, số lượt, error rate và giới hạn phép đo.

## 16. Chuyển từ synthetic wait sang downstream thật

`Mono.delay` mô phỏng thời gian chờ nhưng không mô phỏng toàn bộ đặc tính database hoặc HTTP service.

Một benchmark production-like nên có downstream riêng:

```text
k6
 |
 v
Gateway / API under test
 |
 +---- Reactive: WebClient (non-blocking)
 |
 +---- Blocking: RestClient/SDK (offloaded)
 |
 v
Downstream service / database
```

Hai phương án phải gọi cùng downstream, cùng payload, cùng timeout, cùng dữ liệu và cùng network path.

### 16.1. Reactive downstream call

```java
public Mono<Product> loadReactive(String id) {
    return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class);
}
```

`WebClient` là reactive HTTP client. Dùng WebClient không tự làm toàn bộ pipeline non-blocking nếu operator sau đó gọi blocking API.

### 16.2. Blocking downstream call được offload

```java
public Mono<Product> loadBlocking(String id) {
    return Mono.fromCallable(() ->
                    restClient.get()
                            .uri("/products/{id}", id)
                            .retrieve()
                            .body(Product.class))
            .subscribeOn(Schedulers.boundedElastic());
}
```

Đây là ví dụ với `RestClient` đã được cấu hình và inject. Blocking call được đưa sang bounded elastic, không chạy trên Netty event loop.

### 16.3. Kiểm soát downstream

- Dùng cùng downstream instance/dataset.
- Reset hoặc chuẩn hóa cache trước mỗi lượt.
- Đặt cùng timeout và retry policy.
- Giới hạn connection pool hợp lý.
- Ghi downstream latency và error rate.
- Không để downstream trở thành bottleneck không được đo.
- Nếu dùng database, giữ cùng schema/index/connection pool và dữ liệu.

Nếu downstream bị bão hòa, kết quả có thể chủ yếu phản ánh database chứ không phải framework web.

## 17. So sánh WebFlux và Spring MVC công bằng

Không chạy hai stack trong cùng một application context rồi cho rằng đó là benchmark độc lập. Khi cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng có mặt, Spring Boot thường chọn MVC khi MVC stack hiện diện.

Một so sánh nghiêm túc nên tạo hai ứng dụng hoặc hai deployment riêng:

| Điều kiện | Ứng dụng MVC | Ứng dụng WebFlux |
|---|---|---|
| Java/JVM | Cùng version/options | Cùng version/options |
| Business logic | Cùng logic | Cùng logic |
| Data source | Cùng dataset | Cùng dataset |
| Downstream | Cùng service | Cùng service |
| Response | Cùng JSON/size | Cùng JSON/size |
| Security | Cùng policy | Cùng policy |
| Timeout/retry | Cùng semantics | Cùng semantics |
| CPU/memory limit | Cùng giới hạn | Cùng giới hạn |
| Load generator | Cùng máy/config | Cùng máy/config |

Nếu một app dùng JDBC và app kia dùng R2DBC, đang so sánh cả stack truy cập dữ liệu chứ không chỉ MVC với WebFlux. Điều đó vẫn hữu ích nhưng phải ghi rõ biến nào khác nhau.

### 17.1. So sánh theo workload

- **I/O-bound, concurrency cao:** WebFlux có thể giảm số thread phải chờ I/O.
- **CPU-bound:** khác biệt có thể nhỏ; profile CPU và thuật toán quan trọng hơn.
- **Blocking dependencies:** WebFlux phải offload, thêm scheduler và complexity.
- **Streaming/backpressure:** WebFlux có API reactive tự nhiên hơn.
- **Tải thấp:** khác biệt có thể không đáng để đổi kiến trúc.
- **Team experience/operations:** complexity, debugging và hiring cũng là chi phí cần tính.

## 18. Cách viết kết luận kiến trúc dựa trên bằng chứng

Một báo cáo ngắn nhưng đủ review nên có:

### 18.1. Câu hỏi và giả thuyết

Ví dụ:

> Với 400 request/giây, payload 2 KB và downstream I/O 100 ms, WebFlux có giữ p95 dưới 250 ms và error rate dưới 0,5% với CPU/memory trong ngân sách không?

### 18.2. Phương pháp

Ghi commit/build ID, JDK, Spring Boot, Reactor, CPU/RAM/container limits, JVM options, downstream/dataset, k6 version/script, arrival rate/duration/VUs, warm-up và số lần lặp, SLO/thresholds.

### 18.3. Kết quả

Bảng gồm offered/completed RPS, p50/p95/p99, error/timeout rate, dropped iterations, CPU/heap/GC/thread, queue/connections, median và độ biến động qua các lượt.

### 18.4. Giải thích

Trả lời nút thắt ở đâu, khi nào throughput ngừng tăng, p99 tăng do queue/CPU/downstream, có mất dữ liệu hoặc dropped iterations không, tài nguyên nào được tiết kiệm và kết quả có lặp lại không.

### 18.5. Quyết định và giới hạn

Ví dụ:

> Chọn WebFlux cho gateway I/O-bound vì ở mức 400 RPS, ba lượt đo đều giữ p95/p99 trong SLO, error rate dưới ngưỡng và thread/heap thấp hơn. Kết quả chỉ áp dụng cho workload có downstream non-blocking đã thử; tác vụ CPU-bound và batch blocking được đánh giá riêng.

Nếu số liệu không cho thấy lợi ích đáng kể, ghi rõ điều đó. Có thể giữ MVC để giảm complexity.

## 19. Các sai lầm khi benchmark

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Chỉ đo average latency | Che giấu tail latency | Báo p50/p95/p99 |
| Chỉ đo một lượt | JIT, cache, nhiệt độ và noise ảnh hưởng | Lặp nhiều lượt |
| Chạy hai target đồng thời | Tranh CPU/heap/network | Chạy riêng |
| Không warm-up | Đo startup/JIT thay vì steady state | Warm-up trước measurement |
| Dùng closed model cho mục tiêu arrival rate | Server chậm làm offered load tự giảm | Dùng constant-arrival-rate |
| Bỏ qua dropped iterations | Không biết generator có tạo đủ tải | Kiểm tra generator và VU capacity |
| Cho rằng thread ít hơn luôn tốt hơn | Bỏ qua latency, errors và queue | Đo toàn bộ SLO/resources |
| Dùng Mono.delay để tuyên bố WebFlux thắng MVC | Chỉ mô phỏng wait, không phải stack production | Dùng downstream thật và hai deployment |
| Đổi pool size giữa các lượt | Không còn cùng điều kiện | Ghi và giữ cấu hình |
| Đo k6 trên cùng máy bị CPU bão hòa | Generator thành bottleneck | Dùng load generator riêng |
| Không đo downstream | Nhầm DB saturation với framework | Thu metric cả upstream/downstream |
| Retry không giới hạn trong load test | Khuếch đại tải | Giới hạn retry/backoff |
| Không giữ cùng response/payload | So sánh workload khác nhau | Chuẩn hóa request/response |
| Chỉ nhìn CPU tổng | Có thể một core/event loop bão hòa | Profile và xem thread-level |
| Không đo heap/GC | Bỏ sót allocation và queue retention | Thu JVM metrics/JFR |
| Dùng synthetic result làm production claim | Mô hình không đại diện đầy đủ | Nêu giới hạn và xác minh bằng workload thật |
| Không lưu raw summary/config | Không tái lập được | Lưu script, summary, environment và commit |
| Tự chọn SLO sau khi xem kết quả | Confirmation bias | Xác định SLO trước benchmark |

## 20. Checklist trước khi kết luận

### Workload và giả thuyết

- Workload được mô tả là I/O-bound, CPU-bound hay mixed?
- Arrival rate, concurrency, payload và downstream latency đã xác định?
- Có giả thuyết có thể bác bỏ?
- SLO và điều kiện saturation đã định trước?

### Môi trường và tính công bằng

- Cùng JDK, JVM options, CPU/RAM limit?
- Cùng business logic, data, downstream, payload?
- Cùng timeout, retry, connection pool và observability?
- Load generator có đủ năng lực?
- Các target được chạy riêng và lặp lại?

### Metrics

- Offered và completed RPS?
- p50/p95/p99?
- Error/timeout rate?
- Dropped iterations?
- CPU, heap, GC và thread count?
- Queue, pending tasks và connection pool?
- Có raw summary để tái lập?

### Diễn giải

- Đã xác định saturation point?
- Có phân biệt server bottleneck và generator bottleneck?
- Có giải thích vì sao p99 tăng?
- Có nêu giới hạn synthetic benchmark?
- Có tránh khẳng định reactive luôn nhanh hơn?
- Có cân nhắc complexity và chi phí vận hành?

## 21. Bài tập tự kiểm tra

**Bài 1.** Vì sao reactive thường phù hợp với I/O-bound workload có concurrency cao?

**Đáp án:** Non-blocking I/O không cần giữ một thread riêng trong suốt thời gian chờ; thread có thể phục vụ công việc khác trong khi chờ I/O completion.

**Bài 2.** Reactive có tự tăng năng lực CPU cho CPU-bound workload không?

**Đáp án:** Không. CPU, thuật toán, số core và contention vẫn là giới hạn chính.

**Bài 3.** Throughput 300 RPS và latency trung bình 100 ms cho in-flight trung bình xấp xỉ bao nhiêu theo Little's Law?

**Đáp án:** \(L = 300 \times 0.1 = 30\) request.

**Bài 4.** p95 khác average thế nào?

**Đáp án:** p95 là ngưỡng mà 95% request hoàn tất không vượt qua; average là trung bình và có thể bị ảnh hưởng mạnh bởi outliers.

**Bài 5.** `constant-arrival-rate` giúp gì khi load test?

**Đáp án:** Duy trì tốc độ bắt đầu iteration theo lịch, phù hợp kiểm tra hệ thống với offered load cố định.

**Bài 6.** `dropped_iterations` tăng có chứng minh server đã bão hòa không?

**Đáp án:** Không. Load generator cũng có thể thiếu VU/CPU/network. Phải kiểm tra cả generator và server.

**Bài 7.** Vì sao cần warm-up?

**Đáp án:** Để giảm ảnh hưởng của class loading, JIT, connection pool và cache khởi tạo lên cửa sổ đo steady-state.

**Bài 8.** Tại sao `Mono.delay` không phải benchmark production hoàn chỉnh?

**Đáp án:** Nó mô phỏng thời gian chờ nhưng không mô phỏng protocol, network, connection pool, database, serialization hoặc failure behavior của downstream thật.

**Bài 9.** Nếu offered load tăng nhưng successful throughput không tăng, còn p99 và errors tăng, đó là dấu hiệu gì?

**Đáp án:** Hệ thống có thể đã tới saturation point; cần tìm bottleneck thay vì chỉ tăng tải.

**Bài 10.** Khi so sánh MVC và WebFlux, vì sao cần hai deployment riêng?

**Đáp án:** Để mỗi ứng dụng dùng đúng stack và cấu hình độc lập; khi cùng có MVC và WebFlux dependencies, Boot có thể chọn MVC auto-configuration.

**Bài 11.** Một benchmark có thread count thấp nhưng error rate cao có chứng minh reactive tốt hơn không?

**Đáp án:** Không. Cần đánh giá SLO, throughput, latency, error rate và tài nguyên cùng nhau.

**Bài 12.** Cần ghi gì để kết quả benchmark có thể tái lập?

**Đáp án:** Source/build, JDK/JVM, phần cứng/limits, dataset/downstream, load script/config, warm-up, thời gian đo, metrics thô và số lượt lặp.

## 22. Ghi nhớ

- Lựa chọn reactive phải dựa trên workload và bằng chứng; không có quy tắc reactive luôn nhanh hơn MVC.
- Lợi thế chính thường xuất hiện ở I/O-bound workloads có nhiều thao tác chờ đồng thời và client/driver non-blocking.
- CPU-bound workload vẫn bị giới hạn bởi CPU, thuật toán và contention.
- Đo throughput, p50/p95/p99, error rate, CPU, heap, GC, threads, queues và connection pools.
- Open workload với constant arrival rate phù hợp để giữ offered load ổn định.
- `dropped_iterations` có thể phản ánh generator thiếu năng lực, không nhất thiết server lỗi.
- Little's Law \(L=\lambda W\) giúp ước lượng số request đang xử lý trung bình.
- Saturation thể hiện qua throughput plateau cùng latency/queue/errors tăng.
- Benchmark phải có warm-up, nhiều lượt, môi trường cố định và target chạy riêng.
- Synthetic wait là bài lab cô lập, không phải bằng chứng production; hãy xác minh bằng workload thật.
- So sánh MVC/WebFlux cần cùng business logic, data, downstream, payload, JVM và resource limits trong hai deployment độc lập.
- Một quyết định tốt phải ghi rõ phương pháp, số liệu, giới hạn và lý do chọn.

**Quy tắc kết luận:** nêu workload → nêu giả thuyết → đo trong điều kiện công bằng → xác định bottleneck/saturation → đối chiếu SLO và resource budget → giải thích giới hạn → mới chọn reactive hay MVC.

## 23. Tài liệu chính thức

- Spring Framework — WebFlux overview and reactive/non-blocking model: https://docs.spring.io/spring-framework/reference/6.1/web/webflux.html
- Spring Boot 3.3 — Actuator metrics: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot 3.3 — Prometheus endpoint: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.export.prometheus
- Project Reactor — Scheduler and blocking integration: https://projectreactor.io/docs/core/3.6.11/reference/
- Project Reactor — Backpressure: https://projectreactor.io/docs/core/3.6.11/reference/#_on_backpressure
- k6 — Constant arrival rate executor: https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/
- k6 — Built-in metrics: https://grafana.com/docs/k6/latest/using-k6/metrics/reference/
- k6 — Handle summary and export results: https://grafana.com/docs/k6/latest/results-output/end-of-test/custom-summary/
- OpenJDK — Java Flight Recorder: https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api.html
- Spring Boot 3.3 — Managed dependency versions: https://docs.spring.io/spring-boot/3.3/appendix/dependency-versions/coordinates.html