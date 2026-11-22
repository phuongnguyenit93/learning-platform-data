# Đo độ trễ, thông lượng, số luồng và bộ nhớ trong Spring WebFlux

**Module:** Spring Framework - reactive  
**Chủ đề cha:** Hiệu năng và tải  
**Bài học:** Đo độ trễ, thông lượng, số luồng và bộ nhớ

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Thiết kế benchmark có thể lặp lại, phân biệt warm-up, ramp-up, steady state và soak test.
2. Đọc latency trung bình, median, p90, p95, p99 và maximum; hiểu vì sao percentile quan trọng hơn average đơn lẻ.
3. Đo throughput, concurrency và phân biệt offered load với request thực sự hoàn tất.
4. Dùng Little's Law để liên hệ throughput, latency và số request in-flight.
5. Chọn mô hình tải open-loop hoặc closed-loop theo mục tiêu kiểm thử.
6. Đo Java threads, thread states, heap, non-heap, direct memory, process RSS, CPU và GC.
7. Sử dụng Micrometer/Actuator, Prometheus, k6, JFR, jcmd, jstat và JMH.
8. Hiểu event-loop của WebFlux và nhận diện blocking call làm nghẽn worker.
9. Xây dựng ứng dụng Spring Boot 3.3.5 có endpoint fast, delay và CPU-bound.
10. Đọc k6 p95/p99, request rate, VUs và dropped iterations; tránh kết luận sai do load generator hoặc môi trường.

## 1. Hiệu năng là nhiều chiều

Một endpoint có thể trả lời nhanh khi chỉ có một request nhưng chậm khi có hàng trăm request đồng thời. Một hệ thống có thể đạt throughput cao nhưng tail latency xấu; hệ thống khác có p50 thấp nhưng số request hoàn tất mỗi giây lại thấp.

Cần đo đồng thời bốn nhóm:

- **Latency:** thời gian một operation từ góc nhìn caller.
- **Throughput:** số operation hoàn tất trong một đơn vị thời gian.
- **Concurrency và thread:** số operation đang in-flight, số thread và trạng thái thread.
- **Memory và GC:** heap, direct memory, RSS, allocation rate và garbage collection.

Khi tăng concurrency, throughput thường tăng tới một điểm. Sau điểm bão hòa, queue dài hơn, p95/p99 tăng, timeout nhiều hơn nhưng throughput có thể đứng yên. CPU không phải bottleneck duy nhất: connection pool, event-loop, database, lock hoặc upstream cũng có thể nghẽn.

Trước khi đo, xác định rõ: đo thành phần nào; thời gian tính từ lúc gửi request đến headers hay hết body; workload và payload nào; tiêu chí thành công là gì. Nếu không xác định ranh giới đo, hai con số latency có thể không so sánh được.

## 2. Latency: nhìn phân bố, không chỉ average

| Chỉ số | Cách đọc | Ý nghĩa |
| --- | --- | --- |
| **p50 / median** | 50% request hoàn tất trong hoặc trước giá trị này | Trải nghiệm điển hình. |
| **p90** | 90% request không chậm hơn giá trị này | Nhóm request chậm. |
| **p95** | 95% request không chậm hơn giá trị này | Tail latency thường dùng cho SLA. |
| **p99** | 99% request không chậm hơn giá trị này | 1% request chậm nhất. |
| **max** | Request chậm nhất | Nhạy với outlier và sample size. |
| **average** | Tổng latency chia số request | Hữu ích nhưng có thể che tail. |

Ví dụ minh họa, không phải kết quả benchmark: p50 = 20 ms, p95 = 120 ms, p99 = 900 ms. Median tốt nhưng 1% request chậm nhất gần một giây. Với chuỗi service gọi nối tiếp, tail latency của một dependency có thể kéo dài toàn bộ request.

Khi báo cáo, ghi số request mẫu, khoảng thời gian đo, p50/p90/p95/p99, error rate, timeout count và latency được đo tới headers hay hết response body.

### 2.1. Metric HTTP trong k6

- `http_req_duration`: thời gian gửi request, chờ response và nhận response body; không bao gồm blocked, connecting và TLS handshake.
- `http_req_waiting`: thời gian đợi response (time to first byte).
- `http_req_sending` và `http_req_receiving`: thời gian gửi và nhận dữ liệu.
- `http_req_blocked`: thời gian chờ trước khi bắt đầu gửi, có thể gồm chờ connection slot.
- `http_req_connecting`: thời gian thiết lập TCP.
- `http_req_tls_handshaking`: thời gian TLS handshake.

Nếu `http_req_duration` tăng, xem tiếp waiting, receiving và connecting để xác định giai đoạn chậm. Status 200 chưa chứng minh body đã được đọc đầy đủ nếu connection bị ngắt giữa chừng.

## 3. Throughput, concurrency và Little's Law

Throughput là số operation hoàn tất trong một đơn vị thời gian:

\[
\text{throughput} =
\frac{\text{số operation hoàn tất}}{\text{thời gian đo}}
\]

Ví dụ 60.000 request hoàn tất trong 60 giây tương đương 1.000 req/s. Đây chỉ là phép tính minh họa; benchmark thật phải dùng số request thực sự hoàn tất và báo lỗi/drop.

Phân biệt:

- **Offered load:** tốc độ generator cố gửi request.
- **Started requests:** request đã được khởi chạy.
- **Completed throughput:** request hoàn tất mỗi giây.
- **Successful throughput:** request hoàn tất thành công mỗi giây.
- **Error rate:** tỷ lệ request lỗi.

Nếu generator nhắm 1.000 req/s nhưng chỉ 600 req/s hoàn tất, không thể báo hệ thống đạt 1.000 req/s.

### 3.1. Little's Law

Trong một hệ thống ổn định:

\[
L = \lambda W
\]

`L` là số operation trung bình đang in-flight; `λ` là throughput trung bình (operation/second); `W` là thời gian trung bình một operation ở trong hệ thống (giây).

Ví dụ:

\[
L = 200 \times 0.1 = 20
\]

Với throughput 200 req/s và thời gian trung bình 0,1 giây, có khoảng 20 request in-flight trung bình. Nếu thời gian tăng lên 0,5 giây mà throughput giữ nguyên, concurrency trung bình tăng lên khoảng 100.

Little's Law chỉ dùng khi hệ thống ổn định và các đại lượng đo trên cùng một ranh giới.

## 4. Open-loop và closed-loop load

**Closed-loop:** một VU gửi request, chờ response rồi mới gửi tiếp. Nếu server chậm, tốc độ phát tải tự giảm. Mô hình này phù hợp mô phỏng người dùng tương tác, nhưng có thể che khuất queueing khi hệ thống quá tải.

**Open-loop:** generator phát request theo arrival rate định trước, độc lập với thời gian response. Mô hình này phù hợp kiểm tra năng lực xử lý theo tốc độ request đến cố định. Nếu không đủ VU để giữ lịch, metric dropped iterations tăng.

Trong k6, `constant-arrival-rate` là executor open-model. Các kiểu kiểm thử thường gặp:

- Ramp-up: tăng tải dần.
- Steady-state: giữ tải ổn định để đo.
- Spike: tăng arrival rate đột ngột.
- Stress: tăng tải vượt mức dự kiến để tìm điểm gãy.
- Soak: giữ tải lâu để phát hiện leak, memory drift và suy giảm.

Ghi rõ mô hình load. Không so throughput open-loop và closed-loop như cùng một điều kiện.

## 5. Thread và event-loop trong WebFlux

WebFlux với Reactor Netty dùng non-blocking I/O. Request đang chờ I/O không cần giữ một Java thread riêng như mô hình thread-per-request. Nhiều request có thể dùng chung event-loop worker threads.

Điều này không có nghĩa WebFlux không thể nghẽn:

- JDBC/file I/O đồng bộ, `Thread.sleep` hoặc `block()` chặn event-loop.
- CPU-bound work chạy lâu trên event-loop làm request khác chậm.
- `Schedulers.parallel()` và `Schedulers.boundedElastic()` có pool riêng.
- Driver, logging và thư viện native có thể tạo thread bổ sung.

Metric cần quan sát:

| Metric | Ý nghĩa |
| --- | --- |
| `jvm.threads.live` | Số Java thread đang sống. |
| `jvm.threads.peak` | Số Java thread sống cao nhất. |
| `jvm.threads.states` | Số thread theo trạng thái. |
| Thread dump | Stack trace và trạng thái tại thời điểm chụp. |
| OS process threads | Số native threads của process. |

Số thread không tự cho biết hiệu năng tốt hay xấu. Hãy so sánh cùng workload: thread count có tăng liên tục không, có nhiều thread BLOCKED không, stack trace có lặp tại lock hoặc blocking call không?

### 5.1. Không block event-loop

Ví dụ không nên dùng:

```java
@GetMapping("/bad")
public Mono<String> bad() {
    return Mono.just(blockingDatabaseCall());
}
```

`blockingDatabaseCall()` chạy ngay khi method được gọi, trước khi Mono được trả về, nên có thể block event-loop.

Nếu buộc phải gọi API blocking cũ:

```java
@GetMapping("/legacy")
public Mono<String> legacy() {
    return Mono.fromCallable(this::blockingDatabaseCall)
            .subscribeOn(Schedulers.boundedElastic());
}
```

Đây là cách cô lập blocking workload, không biến JDBC thành reactive và không tạo transaction chung với R2DBC. Cần giới hạn concurrency và theo dõi queue/thread của scheduler. Với CPU-bound work, dùng pool CPU phù hợp như `Schedulers.parallel()`.

## 6. Memory: heap, direct buffer và RSS

| Vùng | Nội dung | Metric/công cụ |
| --- | --- | --- |
| Heap | Object Java, collection, DTO, cache | `jvm.memory.used`, `jvm.memory.max` |
| Non-heap | Metaspace, code cache và vùng JVM khác | `jvm.memory.used` theo area |
| Direct buffer | Buffer off-heap dùng cho I/O | `jvm.buffer.memory.used`, `jvm.buffer.count` |
| Native memory | Thread stacks, native library, JVM internals | NMT, OS tools |
| Process RSS/working set | Trang memory resident của process | OS process monitor |
| Container memory | Memory được tính theo cgroup/runtime | Container metrics |

Heap used không phải tổng RAM của process. RSS còn gồm direct buffer, thread stack, metaspace, native library và memory mapping. Heap committed có thể lớn hơn heap used vì JVM giữ vùng đã cấp phát để tái sử dụng.

Theo dõi heap trước/sau GC, GC count/pause, allocation rate, old-generation growth, direct buffer và RSS. Một snapshot không đủ để kết luận memory leak; hãy quan sát xu hướng qua nhiều vòng workload.

### 6.1. JDK tools

Lấy PID của ứng dụng, rồi chạy:

```bash
jcmd <PID> Thread.print
jcmd <PID> GC.heap_info
jstat -gcutil <PID> 1000 10
```

`Thread.print` xuất stack trace; `GC.heap_info` hiển thị heap; `jstat -gcutil` lấy mẫu vùng GC mỗi 1.000 ms, 10 lần.

Ghi Java Flight Recorder trong lúc chạy tải:

```bash
jcmd <PID> JFR.start name=webflux-load settings=profile duration=60s filename=webflux-load.jfr
```

Mở file bằng Java Mission Control để xem CPU, allocation, GC, lock contention, thread và I/O event.

Để xem native memory, phải bật Native Memory Tracking từ lúc khởi động:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
jcmd <PID> VM.native_memory summary
```

NMT có overhead và không thể bật hồi tố cho process đã chạy. Trên Windows PowerShell:

```powershell
Get-Process -Id <PID> |
    Select-Object Id, CPU, WorkingSet64, PrivateMemorySize64, Threads
```

`WorkingSet64` là resident working set; `PrivateMemorySize64` là private memory. Chúng không tương đương trực tiếp với heap used.

## 7. Micrometer và Spring Boot Actuator

Actuator cung cấp endpoint health/metrics; Micrometer thu thập metric JVM, process và HTTP server. Thêm Prometheus registry để scrape.

Các metric hữu ích gồm `http.server.requests`, `jvm.threads.live`, `jvm.threads.peak`, `jvm.threads.states`, `jvm.memory.used`, `jvm.memory.max`, `jvm.buffer.memory.used`, `jvm.gc.pause`, `process.cpu.usage` và `system.cpu.usage`. Không giả định mọi driver/pool xuất cùng tên metric; kiểm tra endpoint thực tế.

### 7.1. application.properties

```properties
spring.application.name=webflux-performance-lab
server.port=8080

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.endpoint.health.show-details=never
management.metrics.tags.application=webflux-performance-lab
management.metrics.distribution.percentiles-histogram.http.server.requests=true
```

Chỉ expose metrics/prometheus trong mạng quản trị nội bộ hoặc bảo vệ bằng security policy phù hợp.

### 7.2. Đọc metric

```bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/actuator/metrics/jvm.threads.live
curl http://localhost:8080/actuator/metrics/jvm.memory.used
curl http://localhost:8080/actuator/metrics/jvm.buffer.memory.used
curl http://localhost:8080/actuator/prometheus
```

Endpoint `metrics/{name}` trả measurement và tags. Tên Prometheus được chuẩn hóa, ví dụ `jvm_threads_live_threads` hoặc `jvm_memory_used_bytes`. Xem endpoint thực tế trước khi viết dashboard.

## 8. Quy trình benchmark có thể lặp lại

1. **Cố định môi trường:** ghi commit, JDK, Spring Boot/Reactor, CPU/RAM, OS, container limits, JVM flags, GC, dependency, pool và máy load generator.
2. **Xác định workload:** route mix, payload/response size, cache nóng/lạnh, arrival rate/VU, error budget, latency SLO và memory ceiling.
3. **Warm-up:** chờ class loading, JIT, connection pool và cache ổn định; đo cold start riêng nếu cần.
4. **Ramp-up:** tăng tải theo bước, quan sát CPU, latency, throughput và queue.
5. **Steady-state:** giữ tải cố định đủ lâu để có sample đại diện.
6. **Soak:** chạy dài (ví dụ 30–60 phút hoặc theo mục tiêu) để tìm memory drift, thread tăng, pending acquire và GC pause.
7. **Lặp lại:** chạy nhiều lần cùng điều kiện, báo độ dao động; không chọn riêng lần đẹp nhất.
8. **Thay một yếu tố mỗi lần:** pool size, scheduler, payload hoặc serialization. Nếu đổi nhiều thứ cùng lúc, không biết yếu tố nào tạo khác biệt.

Không chạy vài giây rồi kết luận p99. Với test dài, xác nhận load generator không trở thành bottleneck.

## 9. k6: đo HTTP latency và throughput

Tạo file `load.js`:

```javascript
import http from "k6/http";
import { check } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8080";
const PATH = __ENV.SCENARIO_PATH || "/bench/delay?ms=20";

export const options = {
  scenarios: {
    steady_arrival: {
      executor: "constant-arrival-rate",
      rate: 100,
      timeUnit: "1s",
      duration: "60s",
      preAllocatedVUs: 50,
      maxVUs: 200
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<250", "p(99)<500"],
    dropped_iterations: ["count==0"],
    checks: ["rate>0.99"]
  }
};

export default function () {
  const response = http.get(BASE_URL + PATH);
  check(response, {
    "HTTP status is 200": (r) => r.status === 200
  });
}
```

Generator cố khởi chạy 100 iteration/giây trong 60 giây; cấp 50 VU ban đầu và có thể tăng tới 200. `dropped_iterations` phải được quan sát; nếu tăng, generator không phát đủ workload theo lịch. Threshold p95/p99 và error rate ở đây là ví dụ, phải thay theo SLO thật.

Chạy app trước rồi chạy:

```bash
k6 run -e BASE_URL=http://localhost:8080 load.js
k6 run -e BASE_URL=http://localhost:8080 -e SCENARIO_PATH=/bench/fast load.js
k6 run -e BASE_URL=http://localhost:8080 -e SCENARIO_PATH=/bench/cpu?iterations=100000 load.js
k6 run --summary-export=summary.json load.js
```

k6 báo `http_reqs`, `http_req_duration`, `http_req_failed`, `vus`, `vus_max`, `iterations`, `dropped_iterations` và data transfer. Đọc request rate thực tế và percentile từ summary; không chép rate mục tiêu thành throughput thực.

Nếu CPU generator đạt 100%, VU phải tăng cao hoặc dropped iterations tăng trong khi server còn rảnh, hãy chạy generator trên máy khác, tăng tài nguyên hoặc phân tán load. Theo dõi CPU, memory và network của cả generator lẫn server.

## 10. Project Spring Boot 3.3.5 đo WebFlux

Demo cung cấp ba workload:

- `/bench/fast`: response nhỏ, không delay có chủ đích.
- `/bench/delay?ms=20`: chờ bất đồng bộ bằng `Mono.delay`; đây là delay logic, không phải network latency.
- `/bench/cpu?iterations=100000`: phép tính CPU có giới hạn trên `Schedulers.parallel()` để không chạy vòng lặp dài trên Netty event-loop.

### 10.1. Cấu trúc

```text
webflux-performance-lab/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── PerformanceLabApplication.java
    │   ├── BenchResult.java
    │   └── BenchController.java
    └── resources/application.properties
load.js
```

### 10.2. pom.xml

```xml
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
    <groupId>demo</groupId>
    <artifactId>webflux-performance-lab</artifactId>
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
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
            <scope>runtime</scope>
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

Spring Boot parent quản lý phiên bản tương thích của Spring Framework, Reactor và Micrometer.

### 10.3. PerformanceLabApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PerformanceLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(PerformanceLabApplication.class, args);
    }
}
```

### 10.4. BenchResult.java

```java
package demo;

public record BenchResult(
        String scenario,
        long value,
        long elapsedNanos,
        String executingThread) {
}
```

`elapsedNanos` chỉ đo operation minh họa trong handler, không phải end-to-end HTTP latency; caller latency do k6 đo.

### 10.5. BenchController.java

```java
package demo;

import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/bench")
public class BenchController {

    @GetMapping("/fast")
    public Mono<BenchResult> fast() {
        long started = System.nanoTime();
        return Mono.fromSupplier(() -> new BenchResult(
                "fast", 1L, System.nanoTime() - started,
                Thread.currentThread().getName()));
    }

    @GetMapping("/delay")
    public Mono<BenchResult> delay(
            @RequestParam(defaultValue = "20") long ms) {
        if (ms < 0 || ms > 5000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "ms must be from 0 to 5000");
        }
        long started = System.nanoTime();
        return Mono.delay(Duration.ofMillis(ms))
                .map(ignored -> new BenchResult(
                        "delay", ms, System.nanoTime() - started,
                        Thread.currentThread().getName()));
    }

    @GetMapping("/cpu")
    public Mono<BenchResult> cpu(
            @RequestParam(defaultValue = "100000") int iterations) {
        if (iterations < 1 || iterations > 2_000_000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "iterations must be from 1 to 2000000");
        }
        return Mono.fromCallable(() -> {
                    long started = System.nanoTime();
                    long value = 0x9E3779B97F4A7C15L;
                    for (int i = 0; i < iterations; i++) {
                        value = Long.rotateLeft(value ^ i, 13)
                                * 0xC2B2AE3D27D4EB4FL;
                    }
                    return new BenchResult(
                            "cpu", value, System.nanoTime() - started,
                            Thread.currentThread().getName());
                })
                .subscribeOn(Schedulers.parallel());
    }
}
```

`Mono.fromSupplier` chạy khi có subscription. `Mono.delay` không block thread trong lúc chờ. `/cpu` dùng parallel scheduler cho workload CPU tổng hợp; nó không đại diện cho thuật toán nghiệp vụ cụ thể. Tham số được giới hạn để tránh một request yêu cầu quá nhiều vòng lặp. Thread name trong response chỉ để chẩn đoán, không dùng làm số đếm thread của process.

### 10.6. application.properties

```properties
spring.application.name=webflux-performance-lab
server.port=8080
management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.endpoint.health.show-details=never
management.metrics.tags.application=webflux-performance-lab
management.metrics.distribution.percentiles-histogram.http.server.requests=true
```

### 10.7. Build, run và smoke test

```bash
mvn clean package
mvn spring-boot:run
```

Ở terminal khác:

```bash
curl -i http://localhost:8080/bench/fast
curl -i "http://localhost:8080/bench/delay?ms=20"
curl -i "http://localhost:8080/bench/cpu?iterations=100000"
curl http://localhost:8080/actuator/metrics/jvm.threads.live
curl http://localhost:8080/actuator/metrics/jvm.memory.used
```

Một response có cấu trúc như sau (các giá trị chỉ minh họa, không phải số đo chuẩn):

```json
{
  "scenario": "delay",
  "value": 20,
  "elapsedNanos": 21000000,
  "executingThread": "parallel-1"
}
```

Không dùng giá trị elapsedNanos hoặc thread name minh họa làm baseline. Kết quả thật phụ thuộc scheduler, JIT, CPU và tải.

## 11. JMH: microbenchmark khác load test

k6 đo HTTP end-to-end; JMH phù hợp so sánh một phép biến đổi Java thuần. JMH xử lý warm-up, fork và measurement iteration tốt hơn vòng `System.nanoTime` tự viết.

Ví dụ benchmark riêng (cần JMH dependency và annotation processor trong một module benchmark; không nằm trong project WebFlux ở mục 10):

```java
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(2)
public class MappingBenchmark {
    @Param({"100", "1000"})
    int size;
    private int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];
        for (int i = 0; i < size; i++) values[i] = i;
    }

    @Benchmark
    public long imperativeSum() {
        long sum = 0;
        for (int value : values) sum += value;
        return sum;
    }

    @Benchmark
    public long streamSum() {
        return Arrays.stream(values).asLongStream().sum();
    }
}
```

Đọc throughput và error margin theo từng fork/iteration; không chọn một iteration tốt nhất. Không benchmark WebFlux bằng cách tạo Mono rồi gọi `block()` trong vòng lặp và gọi đó là throughput server reactive. Với HTTP đầu-cuối dùng k6; với hàm CPU riêng dùng JMH.

## 12. Đọc kết quả và tìm bottleneck

- **Latency tăng, throughput vẫn tăng:** hệ thống có thể đang tiến gần bão hòa; kiểm tra in-flight, queue, CPU, event-loop và downstream.
- **Latency tăng, throughput đứng yên:** có thể CPU, connection pool, database, lock hoặc GC đã đạt giới hạn.
- **CPU thấp nhưng latency cao:** request có thể chờ I/O, pool acquire, lock, scheduler queue hoặc remote service; xem thread dump và tracing.
- **Thread count tăng theo thời gian:** tìm Executor/scheduler tạo theo request, thread-per-task, timer/subscription không hủy hoặc client không tái sử dụng.
- **Heap ổn định nhưng RSS tăng:** kiểm tra direct buffer, native memory, thread stack, memory mapping, NMT và process metrics.
- **p99 xấu nhưng p50 ổn:** kiểm tra GC pause, allocation burst, downstream chậm, retry storm, payload lớn, TLS/connection creation, lock contention.

Không tăng thread hoặc pool size trước khi có bằng chứng về bottleneck; tăng giới hạn có thể chỉ chuyển áp lực sang database hoặc CPU.

## 13. Mẫu báo cáo benchmark

| Thuộc tính | Giá trị ghi nhận |
| --- | --- |
| Commit / build | SHA hoặc version |
| JDK / Spring Boot | Version thực tế |
| CPU / RAM / container limit | Cấu hình máy chạy app |
| Workload | Route, payload, tỷ lệ request |
| Load model | Open-loop hoặc closed-loop |
| Arrival rate mục tiêu | req/s |
| Request hoàn tất | Tổng thực tế |
| Successful throughput | successful req/s |
| p50 / p95 / p99 | ms |
| Error / timeout rate | % và số lượng |
| Dropped iterations | Số iteration bị bỏ |
| VUs / in-flight | Giá trị trong thời gian đo |
| JVM live / peak threads | Số thread |
| Heap / direct buffer / RSS | MB |
| CPU / GC pause | % và ms |
| Warm-up / steady / soak | Thời gian |
| Bottleneck | Bằng chứng và giả thuyết |

Để trống số chưa đo. Một con số p95 không có workload, sample count, environment và error rate gần như không thể so sánh đáng tin.

## 14. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Chỉ báo average latency | Che nhóm request rất chậm | Báo p50/p95/p99 và sample count. |
| Dùng arrival rate mục tiêu làm throughput | Request có thể drop/timeout | Đọc request hoàn tất và error metrics. |
| Test quá ngắn | Chưa warm-up, không thấy leak/GC | Tách warm-up, steady-state và soak. |
| So máy khác cấu hình | Nhiễu CPU/RAM/JDK/limit | Cố định và ghi môi trường. |
| Không theo dõi dropped_iterations | Generator không phát đủ tải | Tăng tài nguyên/VU hoặc phân tán generator. |
| Gọi block/sleep trên event-loop | Chặn I/O worker | Dùng non-blocking API hoặc scheduler đúng loại. |
| Tăng thread ngay khi latency tăng | Có thể tăng contention/context switch | Xem thread dump và metric trước. |
| Chỉ nhìn heap | Bỏ qua native/direct memory và RSS | Theo dõi buffers, NMT và process memory. |
| Dùng Mono.delay kết luận TCP chậm | Delay xảy ra sau khi request tới handler | Dùng network fault proxy cho transport. |
| Dùng System.nanoTime một lần | JIT/GC/scheduler gây nhiễu | Dùng JMH hoặc load test lặp lại. |
| Chạy app và generator trên máy yếu | Hai process tranh CPU/network | Tách máy hoặc xác nhận generator còn headroom. |
| Bật wiretap/log body khi benchmark | Logging làm đổi workload và có thể lộ dữ liệu | Tắt debug log hoặc đo overhead riêng. |
| Thay nhiều tham số cùng lúc | Không biết yếu tố nào cải thiện | Mỗi lần đổi một yếu tố. |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** p95 = 200 ms nghĩa là gì?  
**Đáp án:** Khoảng 95% sample request có latency không lớn hơn 200 ms; 5% còn lại chậm hơn.

**Câu 2.** Throughput 500 req/s có đồng nghĩa generator gửi 500 req/s không?  
**Đáp án:** Không. Throughput là tốc độ hoàn tất; offered arrival rate là tốc độ muốn gửi.

**Câu 3.** Little's Law diễn đạt điều gì?  
**Đáp án:** Trong hệ thống ổn định, concurrency trung bình L bằng throughput λ nhân thời gian trung bình W: L = λW.

**Câu 4.** Open-loop khác closed-loop thế nào?  
**Đáp án:** Open-loop giữ lịch arrival độc lập response latency; closed-loop thường chờ response xong mới gửi tiếp.

**Câu 5.** Vì sao WebFlux không tạo thread cho mỗi request?  
**Đáp án:** Nó dùng non-blocking I/O và event-loop; nhiều request có thể dùng chung worker khi chờ I/O.

**Câu 6.** Vì sao gọi JDBC blocking trên event-loop nguy hiểm?  
**Đáp án:** Nó chiếm thread xử lý I/O và làm request khác trên event-loop bị trễ.

**Câu 7.** Heap used khác RSS thế nào?  
**Đáp án:** Heap used là object trong Java heap; RSS còn có direct buffer, native memory, thread stack và vùng process khác.

**Câu 8.** Metric nào giúp quan sát số thread?  
**Đáp án:** `jvm.threads.live` và `jvm.threads.peak`; thread dump giúp tìm stack trace và trạng thái.

**Câu 9.** Dùng công cụ nào đo HTTP throughput và p95/p99?  
**Đáp án:** k6 hoặc công cụ load test tương đương; đọc completed request rate và latency distribution.

**Câu 10.** Dùng JMH hay k6 để đo hàm chuyển đổi collection Java?  
**Đáp án:** JMH cho microbenchmark hàm; k6 cho HTTP end-to-end.

**Câu 11.** Vì sao cần soak test?  
**Đáp án:** Tìm leak, thread tăng, memory drift, GC và pool degradation chỉ xuất hiện sau thời gian dài.

**Câu 12.** CPU thấp nhưng p99 cao có thể do gì?  
**Đáp án:** Chờ I/O, pool acquire, lock, scheduler queue, remote dependency hoặc GC.

## 16. Ghi nhớ

- Đo đồng thời **latency distribution, throughput thực, concurrency, thread, CPU và memory**.
- p95/p99 cho thấy tail latency mà average hoặc p50 có thể che giấu.
- Little's Law liên hệ concurrency, throughput và latency trong trạng thái ổn định.
- Open-loop giữ arrival rate; closed-loop mô phỏng người dùng chờ response.
- WebFlux dựa vào event-loop và non-blocking I/O; không block event-loop bằng JDBC, Thread.sleep hoặc block().
- Heap không phải toàn bộ memory process; đo cả direct buffer, native memory và RSS.
- Actuator/Micrometer quan sát JVM/HTTP; k6 tạo tải; JFR/jcmd/jstat phân tích runtime; JMH đo microbenchmark.
- Warm-up, steady-state, soak, workload cố định và load generator đủ mạnh là điều kiện để so sánh công bằng.
- Không biến ngưỡng minh họa hoặc một lần chạy thành SLA.

## Tài liệu tham khảo

1. [Spring Boot 3.3 – Actuator Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html): Micrometer, JVM metrics, tags và Prometheus.
2. [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): mô hình non-blocking và event-loop.
3. [Reactor Core – Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): parallel, boundedElastic và chuyển scheduler.
4. [k6 – Constant Arrival Rate Executor](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/): open-model, VUs và dropped iterations.
5. [k6 – Built-in Metrics](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/): http_req_duration, waiting, sending, receiving, VUs và request rate.
6. [k6 – Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/): ngưỡng pass/fail theo percentile và error rate.
7. [Micrometer – JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html): thread, memory, GC và buffer metrics.
8. [OpenJDK JMH](https://github.com/openjdk/jmh): microbenchmark, warmup, forks và measurement.
9. [JDK 17 – jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): thread dump, heap, JFR và NMT.
10. [JDK 17 – jstat](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): thống kê JVM/GC.
11. [Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/): ghi và phân tích runtime events.
