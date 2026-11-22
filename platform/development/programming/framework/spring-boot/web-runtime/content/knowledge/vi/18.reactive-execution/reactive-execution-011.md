# Phát hiện chặn luồng và đánh giá khả năng chịu tải thực tế

> **Ngữ cảnh:** Spring Boot web-runtime, trọng tâm là Spring WebFlux chạy trên Reactor Netty và những hệ quả khi mã blocking hoặc CPU-bound lọt vào event loop. Bài này đưa ra quy trình tìm nguyên nhân, tái hiện bằng ứng dụng Java 17+, thiết kế phép thử tải có thể lặp lại, đọc số liệu và xác định ngưỡng chịu tải theo mục tiêu thực tế.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích tại sao một lời gọi đồng bộ kéo dài trên **event-loop thread** có thể làm chậm nhiều HTTP request, ngay cả khi một request riêng lẻ vẫn trả `200 OK`.
2. Phân biệt **blocking I/O**, **non-blocking I/O**, **CPU-bound**, **chờ lock**, **hàng đợi connection pool** và **stop-the-world GC** khi đánh giá độ trễ.
3. Kết hợp dấu hiệu bên ngoài (RPS, p95/p99, lỗi, timeout) với bằng chứng bên trong (thread dump, JFR, CPU profiler, metrics) để chẩn đoán đúng.
4. Dùng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` khi phải tương tác với API blocking và biết tại sao đây chỉ là giải pháp cách ly.
5. Viết phép thử tải có đầu vào, thời gian, mức tăng tải, ngưỡng chấp nhận và điều kiện dừng rõ ràng; diễn giải đúng điểm bão hòa, không lấy “số request cao nhất từng thấy” làm năng lực bền vững.
6. Lập một báo cáo có thể tái lập: phiên bản ứng dụng, cấu hình môi trường, kịch bản tải, thông số, số liệu, nguyên nhân và giới hạn kết luận.

## 2. Mô hình thực thi: vì sao chặn một thread lại nguy hiểm?

Một server WebFlux + Reactor Netty mặc định tận dụng một nhóm thread event loop tương đối nhỏ để phục vụ rất nhiều kết nối. Event loop nhận sự kiện socket, đọc/ghi non-blocking, gọi callback/tiếp tục reactive pipeline, rồi quay về xử lý sự kiện mới. Nó **không** giữ một worker thread chờ cho mỗi request khi network I/O đang đợi.

```text
       HTTP A        HTTP B        HTTP C        ...
          \            |            /
           +---- Netty event loops ----+
                      |
                callback ngắn
                /           \
     WebClient non-blocking    CPU nhẹ / operator
                \           /
               trả thread về loop
                      |
             sự kiện kết quả tới sau
                      |
                phát tín hiệu tiếp
```

Nếu một callback thực thi `Thread.sleep(500)`, `RestTemplate` đồng bộ, JDBC đồng bộ, đọc file blocking hoặc một vòng tính toán lớn trên event loop, thread này bị giữ đến khi thao tác xong. Những kết nối khác cần chính thread đó có thể phải đợi. Hậu quả dễ thấy dưới tải là **head-of-line blocking ở tầng thực thi**: latency đuôi tăng, event-loop lag tăng, timeout xuất hiện, trong khi tổng CPU đôi khi vẫn khá thấp.

Ngược lại, một `WebClient` gọi HTTP từ xa mất 500 ms theo đồng hồ **không mặc nhiên block** event-loop thread trong 500 ms: network runtime có thể đăng ký callback và làm việc khác. Khi dữ liệu trở về, pipeline tiếp tục.

Điểm cần nhớ: `Mono`/`Flux` là mô tả luồng xử lý. Chúng không tự chuyển code đồng bộ sang thread khác. `map(x -> blockingCall(x))` vẫn block thread phát tín hiệu. `flatMap` cũng không cứu được nếu lambda gọi blocking API **trước khi** trả publisher. Và `Thread.sleep()` không tự ném lỗi chỉ vì đang ở Reactor Netty event loop.

### I/O-bound, CPU-bound và blocking là ba trục khác nhau

| Loại việc | Ví dụ | Đang tiêu tài nguyên gì? | Dấu hiệu dễ nhầm |
|---|---|---|---|
| Non-blocking I/O | `WebClient` với Reactor Netty, R2DBC phù hợp | Kết nối, socket, callback, bộ đệm; không cần một thread đứng chờ suốt độ trễ mạng | Request vẫn chậm vì upstream, nhưng thread dump không nhất thiết có thread đang chờ cùng request |
| Blocking I/O | JDBC đồng bộ, `InputStream.read()`, SDK sync | Một thread bị giữ trong khi đợi I/O; có thêm pool/connection limit | CPU thấp nhưng p99 và số thread/hàng đợi cao |
| CPU-bound | Nén, ký số, serialize dữ liệu lớn, thuật toán nặng | CPU core, cache, memory bandwidth | CPU cao, runnable stacks nóng dù không thấy blocking API |
| Lock contention | `synchronized` quanh tài nguyên chung, lock đồng bộ | Thread tranh nhau lock; độ trễ phụ thuộc contention | `BLOCKED`/monitor enter, CPU không nhất thiết cao |
| Scheduler/connection queue | Tất cả boundedElastic worker đang bận, pool DB/HTTP hết connection | Hàng đợi/chờ tài nguyên | Latency tăng trước khi mã nghiệp vụ thực sự bắt đầu |
| GC pause, resource throttling | Áp lực heap, CPU quota, container limit | JVM/runtime/OS | Cả endpoint đơn giản cũng chậm đột ngột |

**Không kết luận “blocking event loop” chỉ từ CPU thấp, latency cao hoặc có thread đang `WAITING`.** Event-loop thread rảnh có thể đợi sự kiện I/O một cách bình thường. Cần bằng chứng về **đúng thread + đúng stack + khoảng thời gian + sự tương quan với tải**.

## 3. Các triệu chứng điển hình khi event loop bị chặn

Bạn có thể gặp những tình huống sau:

- Endpoint `/fast` vốn trả một chuỗi nhỏ rất nhanh bỗng có p95/p99 tăng khi endpoint khác bắt đầu truy vấn dữ liệu chậm.
- `200 OK` vẫn chiếm đa số nhưng timeout xuất hiện khi tăng RPS, trong khi CPU chưa sử dụng hết các lõi.
- Một số request đến muộn dù upstream của chúng khỏe: chúng chờ lượt chạy callback trên event loop bị bận.
- Thread dump liên tiếp thấy `reactor-http-nio-...` hoặc tên Netty tương ứng đứng ở `Thread.sleep`, `java.io`, JDBC client hoặc cùng một thao tác CPU nặng.
- Sau khi offload blocking call khỏi event loop, endpoint nhẹ cải thiện rõ, nhưng throughput vẫn có thể bị chặn bởi DB pool, số worker boundedElastic hoặc downstream.

Các triệu chứng **không độc quyền** của blocking. Proxy buffering, load balancer, DNS, TCP backlog, socket/connection pool, GC, OS throttling hoặc chính máy tạo tải quá yếu có thể gây hình ảnh tương tự. Chẩn đoán đúng là chuỗi **quan sát → giả thuyết → bằng chứng → thay đổi có kiểm soát → đo lại**.

## 4. Phân tầng bằng chứng để phát hiện blocking

### 4.1. Tầng HTTP: phát hiện vấn đề từ bên ngoài

Ghi ít nhất:

- **Offered load:** số request/iteration **dự kiến khởi tạo mỗi giây** từ công cụ tải.
- **Achieved throughput:** số response/request hoàn tất mỗi giây (RPS) từ góc nhìn client và nếu có từ server.
- **Latency:** trung vị (p50), p95, p99 và max; nếu là streaming thì đo thêm thời gian nhận byte đầu và thời gian hoàn tất.
- **Errors:** timeout, reset, `5xx`, `429`, `503`, kết quả nghiệp vụ sai, canceled requests; đừng chỉ nhìn tỷ lệ `500`.
- **Concurrency:** số request đang xử lý cùng lúc, queue, số kết nối mở/đang chờ.
- **Resource saturation:** CPU, GC, heap, event-loop lag, worker utilization, connection pool, OS limits.

Một trung bình latency tốt có thể che 1% request bị chậm nhiều giây. p99 có thể quan trọng hơn trung bình với API nhạy độ trễ. Với mẫu quá nhỏ, p99 rất nhiễu; cần đủ số request, dữ liệu theo từng giai đoạn và phép thử lặp lại.

### 4.2. Tầng thread: chụp stack trong lúc có tải

Với JDK 17+ và quyền truy cập process Java, có thể dùng:

```bash
jps -l
jcmd <PID> Thread.print -l
```

Thay `<PID>` bằng process ID thực. Chụp nhiều lần **trong lúc test đang chạy**, chẳng hạn ở giai đoạn tải ổn định và giai đoạn vừa bắt đầu suy giảm. Tìm thread thực thi request trên Netty (tên có thể khác giữa runtime), rồi nhìn **stack frame** ở thời điểm đó:

```text
Ví dụ pattern cần điều tra (minh họa, không phải thread dump thực):
reactor-http-nio-3
  -> ... handler/reactive operator ...
  -> ... legacy JDBC / Thread.sleep / InputStream.read ...
```

Cùng một call stack blocking lặp lại trên event-loop thread qua nhiều ảnh chụp là bằng chứng mạnh hơn một stack lẻ. Đối chiếu với các thời điểm tăng latency và với endpoint gây tải. Các trạng thái Java `RUNNABLE`, `WAITING`, `TIMED_WAITING`, `BLOCKED` **không tự giải thích nguyên nhân**: `RUNNABLE` có thể chứa native I/O, `WAITING` có thể chỉ là thread rảnh, `BLOCKED` thường liên quan tranh chấp monitor.

Với Docker/Kubernetes, cần chạy công cụ trong môi trường có JDK/attach permissions hoặc thu thread dump bằng cơ chế chẩn đoán phù hợp. Không giả định image chỉ có JRE đã có `jcmd`.

### 4.3. Java Flight Recorder (JFR) và profiler

JFR là công cụ JVM giúp ghi dấu CPU, allocation, GC và một số blocking/park/lock/I/O event khi được cấu hình phù hợp. Một ví dụ cho ứng dụng thử nghiệm:

```bash
jcmd <PID> JFR.start name=webload settings=profile duration=60s filename=webload.jfr
```

Phát tải trong khoảng ghi, sau đó mở `webload.jfr` bằng JDK Mission Control hoặc công cụ đọc JFR tương thích. Có thể xem sự kiện qua CLI:

```bash
jfr print --events jdk.ExecutionSample,jdk.ThreadPark,jdk.SocketRead,jdk.JavaMonitorEnter webload.jfr
```

Danh sách sự kiện có thể trống nếu profile/cấu hình không bật chúng hoặc không phát sinh. Stack trace và tần suất sampling có giới hạn; **không lấy việc không thấy một event làm bằng chứng chắc chắn rằng không hề có blocking**.

Cách đọc:

- **CPU profile**: xem stack nào thực sự tiêu CPU nhiều; nếu việc CPU nặng chạy trên event loop thì cần tách CPU work chứ không gọi nó là I/O blocking.
- **ThreadPark/JavaMonitorEnter**: xem thread nào đang chờ lock/park, thời lượng và call site.
- **SocketRead/file-related events**: xem có I/O đồng bộ giữ thread hay không; sự hiện diện trên boundedElastic có thể là hành vi đã chủ động cô lập.
- **GC/JVM/OS**: xem pause, allocation rate, CPU throttle và memory pressure có trùng thời điểm p99 tăng không.

JFR/profiler cần chạy với overhead được chấp nhận và cấu hình phù hợp môi trường. Đối với production, phải theo quy trình vận hành và bảo vệ dữ liệu stack/metadata của hệ thống.

### 4.4. BlockHound: phát hiện lời gọi blocking trên thread non-blocking

[BlockHound](https://github.com/reactor/BlockHound) có thể instrument một số lời gọi blocking đã biết (chẳng hạn `Thread.sleep`) khi chúng xảy ra trên thread được đánh dấu non-blocking. Với cấu hình tương thích, nó giúp bắt lỗi sớm trong test hoặc môi trường chẩn đoán.

Ví dụ một lỗi mà cơ chế như BlockHound cần phát hiện:

```java
// Đoạn nguy hiểm nếu pipeline này được subscribe trên event-loop thread.
Mono<String> bad = Mono.fromCallable(() -> {
    Thread.sleep(200);
    return "ok";
});
```

**Không ngộ nhận:**

1. `Mono.block()` trên một số Reactor `NonBlocking` thread có thể bị Reactor từ chối ngay bằng `IllegalStateException`; điều đó **không** nghĩa mọi blocking call đều tự báo lỗi.
2. BlockHound không phát hiện mọi thư viện blocking tùy biến, không bắt CPU-bound loop dài bằng cùng cơ chế và có thể cần tích hợp/allowlist phù hợp.
3. Khả năng instrument phụ thuộc phiên bản JDK, Byte Buddy, Reactor và BlockHound; tài liệu dự án có lưu ý tham số JVM trên JDK 13+. Không coi một snippet `BlockHound.install()` là luôn chạy được ở mọi build/runtime.
4. Không dựa duy nhất vào BlockHound để tuyên bố capacity tốt: nó hỗ trợ **phát hiện loại lỗi**, còn load test và observability mới đo tác động thực tế.

### 4.5. Spring Boot Actuator, Micrometer và Reactor Netty

Khi ứng dụng có `spring-boot-starter-actuator`, bạn có thể quan sát nhiều chỉ số HTTP/JVM/system thông qua Micrometer. Với Reactor Netty, các meter như `reactor.netty.eventloop.pending.tasks` hoặc `reactor.netty.connection.provider.pending.connections` hữu ích **nếu đo đạc Netty tương ứng đã được bật và công cụ xuất metric hỗ trợ**. Tên meter/nhãn có thể khác theo phiên bản, cấu hình và backend.

Trong phòng lab, thêm dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Và cấu hình thử nghiệm trong `src/main/resources/application.properties`:

```properties
management.endpoints.web.exposure.include=health,metrics
```

Sau khi khởi động, xem danh sách meter đã được đăng ký bằng:

```bash
curl http://localhost:8080/actuator/metrics
```

Một meter có thể chưa xuất hiện cho tới khi đường code tương ứng chạy; không giả định mọi `reactor.netty.*` đều bật mặc định. Nếu muốn Prometheus, cần thêm registry và cấu hình endpoint riêng; chỉ mở endpoint quản trị trong mạng/quyền truy cập phù hợp.

**Đọc metric theo quan hệ nguyên nhân:** latency HTTP tăng cùng event-loop pending tasks và blocking stacks là tín hiệu điều tra event loop; latency tăng cùng DB pending connections thì cần xem pool/upstream; CPU cao cùng GC pause hoặc hotspots CPU thì xử lý theo nguyên nhân khác.

## 5. Thực hành WebFlux: ba đường xử lý và một endpoint kiểm soát

Mục tiêu thí nghiệm: thấy sự khác nhau giữa **cố ý chặn event loop**, **đẩy blocking call sang worker phù hợp** và **delay theo timer non-blocking**. Để có điều kiện so sánh rõ, dùng ứng dụng Spring Boot **chỉ có** `spring-boot-starter-webflux`, chạy embedded Reactor Netty. Nếu cùng classpath có cả `spring-boot-starter-web`, Spring Boot có thể chọn Spring MVC, làm thay đổi giả định về server.

Tạo dự án Spring Boot Java 17+ có dependency `org.springframework.boot:spring-boot-starter-webflux`. Trong Gradle (Groovy DSL), phần dependency tối thiểu liên quan là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Đây là phần bổ sung vào **dự án đã cấu hình plugin Spring Boot và repositories**, không phải toàn bộ `build.gradle`. Tạo một lớp application duy nhất ở `src/main/java/example/load/BlockingLoadLabApplication.java`:

```java
package example.load;

import java.time.Duration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class BlockingLoadLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(BlockingLoadLabApplication.class, args);
    }

    @RestController
    public static class LabController {

        @GetMapping("/lab/fast")
        public Mono<String> fast() {
            return Mono.just("fast-ok");
        }

        @GetMapping("/lab/blocked")
        public Mono<String> blocked() {
            // CỐ Ý SAI: một Callable blocking được subscribe
            // trên thread hiện tại, thường là Netty event loop.
            // Chỉ dùng để thử nghiệm cục bộ.
            return Mono.fromCallable(LabController::legacyWait);
        }

        @GetMapping("/lab/offloaded")
        public Mono<String> offloaded() {
            // Cùng công việc blocking, nhưng chạy trên
            // Scheduler phù hợp cho blocking I/O.
            return Mono.fromCallable(LabController::legacyWait)
                    .subscribeOn(Schedulers.boundedElastic());
        }

        @GetMapping("/lab/nonblocking")
        public Mono<String> nonblocking() {
            // Delay theo timer, không giữ thread ngủ 200 ms.
            return Mono.delay(Duration.ofMillis(200))
                    .thenReturn("timer-ok");
        }

        @GetMapping("/lab/cpu")
        public Mono<Long> cpu() {
            return Mono.fromCallable(() -> {
                        long sum = 0L;
                        for (long i = 0; i < 2_000_000L; i++) {
                            sum += i;
                        }
                        return sum;
                    })
                    .subscribeOn(Schedulers.parallel());
        }

        private static String legacyWait()
                throws InterruptedException {
            Thread.sleep(200);
            return "legacy-ok";
        }
    }
}
```

**Vì sao ví dụ này đáng tin?**

- `Mono.fromCallable` trì hoãn lời gọi `legacyWait` tới lúc được subscribe. Ở `/lab/blocked`, không có scheduler chuyển tiếp, nên với WebFlux/Netty thông thường lời gọi có thể chạy trên event-loop thread. Đường này **cố tình sai** nhằm kiểm chứng vấn đề, không mang sang production.
- `/lab/offloaded` gắn `subscribeOn(Schedulers.boundedElastic())` vào chính nguồn blocking; đẩy phần chờ `Thread.sleep` sang thread worker để giảm nguy cơ chiếm event loop. Nó **không làm phương thức `legacyWait` trở thành non-blocking**.
- `/lab/nonblocking` dùng timer `Mono.delay`, không cần một thread nằm ngủ suốt 200 ms. Đó là mô phỏng độ trễ logic, **không phải HTTP I/O thực**.
- `/lab/fast` là probe đơn giản để phát hiện ảnh hưởng lan sang endpoint không có thao tác chậm.
- `/lab/cpu` là công việc tính toán được offload sang `Schedulers.parallel()`. Tác vụ CPU ngắn trong ví dụ chỉ để quan sát operator; compiler/JIT có thể tối ưu và không nên dùng nó làm benchmark CPU.
- `Thread.sleep` được dùng đúng mục đích **mô phỏng blocking**; thư viện I/O thật sẽ có hành vi và thời gian chờ khác. `Mono.delay` có thể dùng scheduler dành cho timer, nên vẫn cần thread để phát callback khi hết hạn; điều quan trọng là **không giữ thread chờ** trong toàn bộ 200 ms.

Chạy dự án:

```bash
./gradlew bootRun
```

Trên Windows, dùng `gradlew.bat bootRun`. Ở terminal khác, kiểm tra từng endpoint (trong Windows PowerShell, ưu tiên `curl.exe` nếu `curl` là alias):

```bash
curl -s http://localhost:8080/lab/fast
curl -s http://localhost:8080/lab/blocked
curl -s http://localhost:8080/lab/offloaded
curl -s http://localhost:8080/lab/nonblocking
curl -s http://localhost:8080/lab/cpu
```

Body trả về dự kiến theo đúng thứ tự là:

```text
fast-ok
legacy-ok
legacy-ok
timer-ok
1999999000000
```

Kết quả `1_999_999_000_000` là tổng các số nguyên từ 0 đến 1.999.999. Thời gian response thực tế **không** cố định: hai endpoint legacy và timer tạo độ trễ logic khoảng 200 ms, còn scheduling, mạng, tải, JIT và máy thử nghiệm ảnh hưởng thêm.

Để quan sát rõ, chạy tải **riêng** trên `/lab/blocked`, rồi lặp lại với `/lab/offloaded` và `/lab/nonblocking`. Khi một nhóm client đang tạo tải, gọi xen kẽ `/lab/fast` và ghi latency; probe này giúp thấy việc một endpoint chậm ảnh hưởng đến request khác cùng event loop. Kết luận phải dựa trên số liệu nhiều lượt, không dựa vào một lần gọi `curl`.

### Các mức tác động dự kiến

| Path | Công việc 200 ms ở đâu? | Điều muốn kiểm tra | Giới hạn |
|---|---|---|---|
| `/lab/blocked` | Blocking trên thread subscribe, thường là event loop trong cấu hình thử nghiệm | Nhiều request chậm có thể khiến `/lab/fast` cũng chậm | Phụ thuộc số event loop, cấu hình runtime và lịch phân phối connection |
| `/lab/offloaded` | Blocking trên boundedElastic worker | Event loop giữ khả năng phản hồi tốt hơn | Worker và queue có giới hạn; không tăng vô hạn throughput |
| `/lab/nonblocking` | Timer không giữ một worker đang ngủ | Delay logic không kéo dài thời gian chiếm event loop | Không đại diện DB/downstream thật |
| `/lab/cpu` | Tính toán ở Reactor parallel worker | Tách CPU khỏi event loop | CPU core có hạn, parallel không phù hợp blocking I/O |
| `/lab/fast` | Gần như không có việc nặng | Endpoint kiểm soát latency | Vẫn chịu ảnh hưởng socket, runtime, proxy và CPU chung |

**Cảnh báo về phép thử:** Endpoint `/lab/blocked` chỉ dành cho máy phát triển/benchmark được kiểm soát. Không triển khai endpoint gây nghẽn có chủ đích lên hệ thống thật hoặc chạy thử tải ngoài phạm vi được phép.

## 6. Thiết kế load test: hỏi đúng câu hỏi trước khi đo

Một phép thử tốt không bắt đầu bằng “bắn càng nhiều request càng tốt”. Cần biết **capacity nào** đang được đo: toàn bộ hệ thống cho một workload có cấu trúc, ở cấu hình phần cứng và mức SLA/SLO cụ thể.

### Ba loại kiểm tra cần phân biệt

| Loại | Mục tiêu | Mức tải và thời gian |
|---|---|---|
| Smoke/baseline | Xác nhận endpoint đúng, tool tạo tải hoạt động, metrics có dữ liệu | Ít request, chạy ngắn; chưa đưa ra kết luận capacity |
| Load/step test | Xác định hành vi ở mức tải mục tiêu và ngưỡng bắt đầu suy giảm | Tăng từng nấc, giữ đủ lâu ở mỗi nấc để quan sát steady state |
| Stress/soak test | Stress: xem hệ thống suy giảm và hồi phục thế nào khi vượt khả năng. Soak: tìm leak/tích lũy tài nguyên dưới tải kéo dài | Stress tăng vượt mục tiêu có kiểm soát; soak giữ tải đại diện trong thời gian dài |

Đo thêm **spike test** nếu cần đánh giá khả năng chịu tăng tải đột ngột. Một thử nghiệm 30 giây không chứng minh hệ thống chịu được traffic hàng giờ; cũng không phân biệt được memory leak, connection leak hoặc sự suy giảm sau nhiều chu kỳ GC.

### Ghi bối cảnh để so sánh công bằng

Trước khi bắt đầu, lưu các yếu tố có thể ảnh hưởng kết quả:

1. Source commit/version, Java version, Spring Boot/Reactor version và flags JVM.
2. Số CPU core/vCPU, CPU quota container, RAM, heap, số replica, event-loop/scheduler/pool config.
3. Máy tạo tải, vị trí mạng, TLS, proxy/ingress, keep-alive, HTTP version, connection limits.
4. Phiên bản cấu hình database, pool, cache, upstream, dữ liệu đầu vào và tình trạng ấm/lạnh của cache.
5. Tỷ lệ các endpoint trong workload, kích thước request/response, tỷ lệ đọc/ghi, user behavior, authentication.
6. Tiêu chí chấp nhận: p95/p99 tính ở đâu, tỷ lệ lỗi, throughput yêu cầu, mức sử dụng tài nguyên, giới hạn timeouts.
7. Giới hạn an toàn và điểm dừng: tránh làm cạn DB, gây tắc nghẽn môi trường shared, hoặc tạo traffic đến dịch vụ bên thứ ba ngoài phạm vi thử nghiệm.

Nếu chỉ thay server từ 2 vCPU sang 8 vCPU mà không ghi vào báo cáo, con số RPS mất ý nghĩa. Cache ấm, keep-alive, loopback và không có authentication cũng có thể khiến kết quả đẹp hơn production rất nhiều.

## 7. Open workload, closed workload và vấn đề coordinated omission

Hai cách mô phỏng client phổ biến:

- **Closed workload:** có N virtual users; mỗi user gửi request tiếp sau khi request trước hoàn tất (và có thể nghỉ theo think time). Nếu server chậm, tốc độ gửi **tự giảm**. Hữu ích khi mô phỏng một số loại hành vi người dùng nhưng dễ che dấu việc không đạt offered arrival rate.
- **Open workload:** công cụ cố khởi tạo request theo tốc độ độc lập với thời gian phản hồi của server, ví dụ 20 → 50 → 100 request/s. Hữu ích khi hỏi “server còn giữ SLO được khi traffic đến với tốc độ X hay không?”. Khi VU/connection không đủ, tool có thể bỏ lỡ lượt dự kiến, nên phải kiểm tra `dropped_iterations`.

**Coordinated omission** xảy ra khi một hệ thống đo vô tình không ghi nhận đầy đủ các yêu cầu đáng lẽ đến trong lúc hệ thống đã chậm, làm tail latency trông tốt hơn. Chọn mô hình tải và cách đo phù hợp với thực tế; không khẳng định fixed VU và fixed arrival rate là hai phép đo tương đương.

### Little's Law để kiểm tra tính hợp lý

Trong hệ ổn định, quan hệ xấp xỉ:

```text
L = λ × W

L: số request trung bình đồng thời trong hệ thống
λ: tốc độ hoàn tất/đến trung bình (request/giây) ở steady state
W: thời gian ở trong hệ thống trung bình (giây)
```

Nếu hệ thống đang xử lý ổn định 50 request/s và trung bình mất 0,2 giây/request, ta kỳ vọng khoảng 10 request đang ở trong hệ. Nếu latency trung bình tăng thành 1 giây trong khi throughput vẫn 50 request/s, số request đang tồn đọng xấp xỉ 50. Đây là quan hệ giữa **giá trị trung bình**, không được cắm p95 vào W rồi gọi kết quả là “đồng thời trung bình”.

Khi offered load lớn hơn khả năng xử lý thực tế, hàng đợi tăng, latency tăng và hệ có thể chưa đạt steady state. Khi đó đừng máy móc dùng `L = λW` để suy ra capacity. Little's Law là kiểm tra tính hợp lý, **không phải bằng chứng chọn scheduler**.

## 8. Một kịch bản k6 chạy được để tăng tải theo từng nấc

Dùng [Grafana k6](https://grafana.com/docs/k6/latest/) đã được cài đặt trên máy thử nghiệm. Tạo file `load-test.js` **ở máy dùng để tạo tải** (không phải source code cần deploy):

```javascript
import http from 'k6/http';
import { check } from 'k6';

const baseUrl = __ENV.BASE_URL || 'http://localhost:8080';
const testPath = __ENV.TEST_PATH || '/lab/offloaded';

export const options = {
    scenarios: {
        stepped_load: {
            executor: 'ramping-arrival-rate',
            startRate: 5,
            timeUnit: '1s',
            preAllocatedVUs: 40,
            maxVUs: 100,
            stages: [
                { target: 5, duration: '20s' },
                { target: 20, duration: '30s' },
                { target: 20, duration: '1m' },
                { target: 50, duration: '30s' },
                { target: 50, duration: '1m' },
                { target: 5, duration: '20s' },
            ],
        },
    },
    thresholds: {
        http_req_failed: ['rate<0.01'],
        http_req_duration: ['p(95)<500', 'p(99)<1000'],
        checks: ['rate>0.99'],
    },
};

export default function () {
    const response = http.get(baseUrl + testPath, {
        timeout: '3s',
    });

    check(response, {
        'HTTP 200': (r) => r.status === 200,
    });
}
```

Chạy theo từng endpoint:

```bash
k6 run -e TEST_PATH=/lab/blocked load-test.js
k6 run -e TEST_PATH=/lab/offloaded load-test.js
k6 run -e TEST_PATH=/lab/nonblocking load-test.js
```

Ví dụ nếu chạy qua máy khác, chỉ rõ `BASE_URL` bằng hostname/IP server đã được phép đo:

```bash
k6 run -e BASE_URL=http://localhost:8080 -e TEST_PATH=/lab/offloaded load-test.js
```

Trong môi trường từ xa, thay `localhost` bằng địa chỉ dịch vụ thuộc môi trường thử nghiệm. Đừng dùng địa chỉ localhost khi load generator nằm ở host khác, vì nó sẽ trỏ đến chính máy tạo tải.

**Tính đúng của script:** `ramping-arrival-rate` cố gắng khởi tạo iteration theo số lần/giây; mỗi iteration ở đây làm đúng một HTTP GET, nên offered iterations/s gần tương ứng offered requests/s nếu không có drop hay retry. `preAllocatedVUs` và `maxVUs` là nguồn lực phía k6. Nếu `dropped_iterations > 0`, công cụ đã không khởi tạo hết lượt dự kiến; không được kết luận server đã chịu đúng tải mục tiêu chỉ từ số `target`.

Hai mốc `p95 < 500 ms`, `p99 < 1.000 ms` và lỗi dưới 1% ở trên là **tiêu chuẩn minh họa cho phòng lab**, không phải SLO của ứng dụng thực. Hãy đặt tiêu chí dựa vào yêu cầu sản phẩm. `checks` là assertion rằng HTTP trả 200; `thresholds` mới quyết định trạng thái pass/fail của lệnh k6. Nếu bạn có endpoint được mong đợi trả `404` hoặc `429` theo chính sách, chỉnh predicate và expected-response tương ứng trước khi áp dụng.

**Không thêm `sleep()` cuối iteration** trong `ramping-arrival-rate`: loại executor này đã điều tiết tốc độ khởi tạo. Một load generator có CPU 100%, thiếu socket/file descriptor, cấu hình TLS quá nặng hoặc thiếu VU cũng có thể là điểm nghẽn; cần theo dõi tài nguyên máy tạo tải song song.

### Thử nghiệm lan truyền ảnh hưởng đến endpoint nhanh

Script trên tạo tải trên đúng một path để dễ so sánh. Để kiểm tra event-loop interference, trong khi tải `/lab/blocked` đang chạy, hãy đo latency của `/lab/fast` từ **một client thứ hai** có traffic rất nhẹ. Lặp lại cùng phép đo khi tải `/lab/offloaded` và `/lab/nonblocking`. Tách traffic probe khỏi chính tải chính giúp phân biệt endpoint mất 200 ms theo thiết kế với **một endpoint không có công việc chậm cũng bị trễ**.

Nếu cần báo cáo p95 của probe, dùng k6 scenario/metric riêng hoặc một công cụ đo có phân phối mẫu, thay vì so vài lần `curl` rồi gọi đó là p95.

## 9. Phân tích số liệu: chỉ số nào trả lời câu hỏi nào?

| Chỉ số | Ý nghĩa | Câu hỏi cần đặt |
|---|---|---|
| Offered rate vs achieved RPS | Công cụ định gửi bao nhiêu và thực hoàn tất bao nhiêu | Có đạt lưu lượng mục tiêu không? Có drop, timeout, retry làm sai phép đo không? |
| p50 / p95 / p99 latency | Phân phối độ trễ trải nghiệm từ client | Đuôi có suy giảm trước khi trung bình thay đổi không? |
| `http_req_failed` / status breakdown | Request thất bại theo cách tool nhận diện | Lỗi xuất hiện ở mức tải nào; là `503`, `5xx`, timeout hay kết quả nghiệp vụ sai? |
| `checks` | Assertion logic của k6 | Server có trả **đúng nội dung/trạng thái** không, ngoài việc trả nhanh? |
| `dropped_iterations` | Lượt gửi dự kiến nhưng k6 không bắt đầu | Thiếu VU, generator yếu hay latency quá cao? Offered load có thật sự đạt? |
| p95/p99 của `/lab/fast` khi endpoint chậm chịu tải | Latency của endpoint kiểm soát | Có dấu hiệu blocking lan sang event loop dùng chung? |
| CPU/GC/heap | Áp lực tính toán, bộ nhớ và GC | Bão hòa CPU, pause GC hay allocation pressure? |
| Netty event-loop pending tasks/lag | Hàng đợi/sự chậm trễ khi xử lý event | Callback có bị trì hoãn dưới tải không? Meter có thật sự được bật không? |
| boundedElastic worker/queue | Tài nguyên dành cho blocking calls | Offload đã tránh event loop, nhưng có tạo hàng đợi mới không? |
| DB/HTTP client connection pool | Kết nối đang dùng/chờ lấy | Downstream có giới hạn thấp hơn server HTTP không? |
| Thread dump/JFR | Stack thực thi, lock, I/O, CPU | Code nào gây vấn đề, trên loại thread nào, thời gian nào? |

Trong k6, `http_req_duration` là thời gian cho phần gửi request, chờ response và nhận response, không phải toàn bộ thời gian iteration hay mọi chi phí thiết lập connection/DNS. Nếu muốn phân tích mạng, đọc thêm `http_req_blocked`, `http_req_connecting`, `http_req_tls_handshaking`, `http_req_waiting`, `http_req_receiving`. Với ứng dụng có streaming, response duration và thời gian tới byte đầu phục vụ hai câu hỏi khác nhau.

**Lưu ý phân biệt số liệu đã được xác nhận và giả thuyết.** Ví dụ: “p99 tăng sau 50 RPS, Netty event loop xuất hiện trong stack của `Thread.sleep`” là dữ kiện có thể điều tra. “Do JDBC chiếm event loop” chỉ đúng khi bằng chứng thread stack cho thấy JDBC đồng bộ trên event-loop thread; một biểu đồ latency không đủ chứng minh.

## 10. Xác định ngưỡng chịu tải bền vững

Một định nghĩa thực dụng:

> **Năng lực chịu tải bền vững của hệ thống cho workload X, tại cấu hình Y, là mức offered rate cao nhất đã được kiểm chứng liên tục trong khoảng đo đại diện mà vẫn đáp ứng SLO về latency, tỷ lệ lỗi và giới hạn tài nguyên, không có hàng đợi tăng vô hạn hoặc tích lũy tài nguyên gây suy giảm.**

Phải ghi **X** và **Y**. Không có “web-runtime này chịu 1.000 RPS” chung cho mọi endpoint hay mọi môi trường.

### Quy trình đo từng nấc

1. **Baseline:** chạy không tải/ít tải, xác nhận API, dataset và monitor hoạt động; ghi CPU, heap, GC, latency nền.
2. **Warm-up:** cho JVM/JIT, connection pool, cache khởi tạo; tách dữ liệu warm-up khỏi dữ liệu dùng quyết định capacity.
3. **Steady-state ở tải mục tiêu:** tăng qua các nấc đã định, giữ đủ lâu để thu mẫu p95/p99 và quan sát queue. Ghi offered vs achieved, error và resource.
4. **Tìm knee point:** ghi mức tải khi p95/p99 bắt đầu tăng nhanh, throughput không còn tăng tương xứng, hàng đợi/phục vụ xấu đi hoặc error xuất hiện.
5. **Xác nhận tính bền vững:** lặp lại ở nấc thấp hơn ngưỡng suy giảm, giữ lâu hơn. Một lượt 30 giây không đủ kết luận không có leak.
6. **Đánh giá phục hồi:** giảm tải và xem queue/latency/CPU/GC quay lại nền không. Tài nguyên không hồi phục có thể cho thấy leak hoặc tác vụ bị kẹt.
7. **So sánh A/B:** chỉ đổi một biến quan trọng (ví dụ `blocked` → `offloaded`) khi phần còn lại giữ như cũ; lặp phép đo, tránh so những ngày máy/proxy/database có tải khác nhau.

### Mẫu kết luận đúng và sai

Không nên viết: “Bài test đã chạy lên 500 RPS, do đó server chịu được 500 RPS.” Có thể 500 chỉ là `target`, 150 iteration bị drop, p99 vượt SLO, hoặc sau một phút pool tăng hàng đợi.

Nên viết: “Ở **đúng kịch bản** và **cấu hình** đã ghi, tải offered 120 request/s được giữ trong 20 phút, achieved 119,6 request/s, p95 dưới SLO, lỗi dưới ngưỡng và queue ổn định; mức 150 request/s không đạt vì p99 vượt SLO và timeout tăng. Đây là ngưỡng quan sát trong phép thử, cần xác nhận thêm với workload sản xuất.”

Các số trong đoạn trên **chỉ minh họa cách diễn đạt**, không phải kết quả đo của ứng dụng lab này.

### Minh họa Little's Law và bottleneck

Giả sử bốn event-loop thread, mỗi thread liên tục bị block 200 ms bởi một callback (giả định cực kỳ đơn giản, không có overhead khác). Một thread chỉ có thể hoàn thành khoảng 5 callback blocking/giây; bốn thread khoảng 20 callback/giây. Đây là **ước lượng trực giác của điểm nghẽn giả định**, không phải throughput đảm bảo của Netty hay benchmark thật: kết quả phụ thuộc scheduling, số worker, cấu hình, pool, socket, request mixing và client. Khi offload, event loop rảnh hơn nhưng capacity vẫn bị giới hạn bởi boundedElastic, connection pool và chính thư viện blocking.

Nếu CPU là điểm nghẽn, thêm thread có thể chỉ tăng context switches. Nếu database có 10 connections và query tốn 200 ms, throughput database trong điều kiện lý tưởng có giới hạn riêng khoảng 50 query/s, không tự tăng khi thêm HTTP worker. Những ước lượng này giúp định hướng **đo đúng bottleneck**, không thay thế số liệu thực nghiệm.

## 11. Phân loại vấn đề theo đồ thị nguyên nhân

```text
           p95/p99 tăng khi tăng offered RPS
                         |
           +-------------+--------------+
           |                            |
      Achieved RPS có             Achieved RPS có
      gần offered?                drop/timeout?
           |                            |
      Xem CPU/GC/queue             Kiểm tra generator,
           |                       network, pool, server
   +-------+---------+
   |                 |
 CPU cao           CPU thấp/vừa
   |                 |
 Profiling CPU     Thread dump/JFR
 serialize/logic   event loop có blocking?
   |                 |
 CPU pool          +------+---------+
 phù hợp           |                |
                Có bằng chứng    Không rõ bằng chứng
                   |                |
             Cách ly source      Xem connection pool,
             blocking, test      proxy, lock, queue,
             lại cùng tải        upstream, GC, timeout
```

Đây là **sơ đồ định hướng**, không phải thuật toán chẩn đoán quyết định. Các bottleneck có thể đồng thời tồn tại; ví dụ JDBC blocking có thể vừa chiếm event loop vừa chờ DB pool. Một thay đổi giảm p99 có thể đẩy giới hạn sang tài nguyên khác.

## 12. Sửa theo nguyên nhân, không theo triệu chứng

### 12.1. Blocking API vô tình chạy trên event loop

Ví dụ lỗi:

```java
// Trong WebFlux service; legacyRepository là API blocking.
Mono<Report> wrong(long id) {
    return Mono.just(legacyRepository.load(id));
}
```

`legacyRepository.load(id)` đã chạy đồng bộ **ngay lúc tạo** `Mono.just` và có thể block thread gọi service. Đổi thành nguồn lazy và tách scheduler:

```java
// Đúng cách cô lập API blocking; Report/legacyRepository do ứng dụng định nghĩa.
Mono<Report> better(long id) {
    return Mono.fromCallable(() -> legacyRepository.load(id))
            .subscribeOn(Schedulers.boundedElastic());
}
```

Đây là **mảnh mã minh họa** của một service có field `legacyRepository` và type `Report`; không phải chương trình biên dịch độc lập. BoundedElastic có giới hạn thread và queue; cần kiểm soát timeout, DB pool, concurrency/bulkhead và xử lý cancellation phù hợp. Khi API hỗ trợ non-blocking thật (WebClient, reactive DB driver phù hợp), ưu tiên giữ đường I/O non-blocking thay vì offload vô ích.

### 12.2. CPU nặng nằm trong `map` trên event loop

```java
// Giả sử transformCpuHeavy đã được định nghĩa.
Mono<Result> transformed =
        sourceMono.publishOn(Schedulers.parallel())
                  .map(this::transformCpuHeavy);
```

`publishOn(parallel())` chuyển đoạn downstream sang worker dành cho CPU, nhưng **không tự chia** phép tính đơn khối thành nhiều core. Muốn khai thác nhiều core cho nhiều phần tử độc lập phải chia việc và giới hạn concurrency thích hợp; có thể dùng `Flux.parallel().runOn(...)` hoặc executor CPU riêng. Chú ý pool `parallel` hữu hạn và có thể bị bão hòa bởi tính toán quá dài.

### 12.3. Downstream/DB pool bão hòa

Nếu event loop khỏe nhưng request xếp hàng đợi connection database, tối ưu event loop có thể không cải thiện throughput. Đo `active/idle/pending`, thời gian acquire, query latency và timeout. Cân nhắc tối ưu query, index, capacity downstream, cache hợp lý, giảm concurrency vượt khả năng; **tăng pool size không phải luôn đúng**, vì database có thể quá tải thêm.

### 12.4. Hàng đợi tác vụ và backpressure

Reactor `Schedulers.boundedElastic()` có giới hạn; gửi quá nhiều callable blocking có thể dẫn đến queue tăng và tail latency. Với `flatMap`, có thể giới hạn số nguồn nội bộ được subscribe đồng thời:

```java
// Mã minh họa: blockingLoad(id) do ứng dụng định nghĩa.
Flux.range(1, 100)
    .flatMap(id -> Mono.fromCallable(() -> blockingLoad(id))
                        .subscribeOn(Schedulers.boundedElastic()), 8);
```

Con số `8` giới hạn concurrent inner subscriptions **trong pipeline này**, không tự giới hạn toàn bộ traffic trên tất cả HTTP request. Với workload production, cần rate limit/admission control, bulkhead toàn cục, capacity của pool, timeout và trả tín hiệu quá tải hợp lý (ví dụ `429` hoặc `503` theo hợp đồng API) thay vì để hàng đợi tăng vô hạn.

### 12.5. Thread local, context và tracing

Khi chuyển scheduler, đừng giả định dữ liệu trong `ThreadLocal` tự theo sang thread mới. Với Reactor, dùng `Context`/cơ chế context propagation được hỗ trợ và tích hợp observability/security thích hợp. Khi đọc thread dump, theo dõi tên request/span nếu có trace ID; đừng trộn correlation giữa các request.

### 12.6. Timeout, retry và cancellation

Timeout cần đặt ở đúng tầng (HTTP client, DB, reactive pipeline, gateway) và phản ánh giới hạn nghiệp vụ. Retry không kiểm soát có thể **khuếch đại tải** vào đúng lúc downstream đang bão hòa. Chỉ retry lỗi phù hợp, có backoff, giới hạn số lần và bảo đảm idempotency khi cần. Client hủy request không bảo đảm API blocking đồng bộ đã được ngắt; phải xử lý cleanup và giới hạn tài nguyên đúng với SDK/driver.

## 13. Những bẫy đo tải thường khiến kết luận sai

| Bẫy | Hậu quả | Cách giảm |
|---|---|---|
| Chỉ chạy một request bằng `curl` | Không phơi bày contention, queue hoặc p99 | Đo có concurrency và phân phối đủ mẫu |
| Chỉ nhìn average latency | Bỏ qua tail latency và timeout | Ghi p95/p99, max và tỷ lệ lỗi |
| Nhìn `target` RPS, quên `dropped_iterations` | Tưởng đã gửi tải mà k6 thực tế không khởi tạo được | Ghi offered, achieved, drop và tài nguyên load generator |
| Test loopback trên một máy | Tranh CPU/network giữa generator và server; khác production network | Tách máy tạo tải khi cần, ghi rõ topology |
| Cache nóng/response giả quá nhỏ | Kết quả nhanh hơn workload thực | Dùng dữ liệu và response size đại diện |
| Chạy test sau restart nhưng không warm-up | JIT, class loading, pool init gây méo p95 | Warm-up rõ ràng; ghi số liệu steady state |
| Tăng VU rồi coi đó là tăng request/s cố định | Closed workload tự giảm arrival rate khi server chậm | Dùng open arrival model khi muốn ép offered rate |
| Không quan sát DB/pool/upstream | Quy kết sai cho event loop hoặc CPU | Đo end-to-end và từng dependency |
| Bật quá nhiều debug logging khi benchmark | Logging gây blocking/I/O, thay đổi kết quả | Chỉ bật profiling/logging được kiểm soát; ghi overhead |
| Tăng thread pool thật lớn khi thấy latency tăng | Oversubscription, queue/memory và context-switch tăng | Xác định bottleneck thực, đặt giới hạn phù hợp |
| Thấy event loop `WAITING` và kết luận nó bị block | Event loop rảnh bình thường cũng chờ event | Xem stack, thời lượng, event-loop lag và correlation |
| Chỉ nhìn test ngắn có `200 OK` | Không phát hiện leak, GC, timeout, backlog kéo dài | Stress/soak có thời gian, lỗi và cleanup |
| Thử trực tiếp trên production không kiểm soát | Có thể gây suy giảm thực tế và làm sai số liệu do traffic thật | Dùng môi trường/cửa sổ kiểm thử được phép và giới hạn tải |

## 14. Mẫu báo cáo kết quả có thể hành động

Một báo cáo kỹ thuật tốt nên gồm:

```text
Mục tiêu/SLO:
  workload, offered RPS mục tiêu, p95/p99, error-rate, thời gian giữ tải

Môi trường:
  commit, Java/Spring/Reactor, vCPU/RAM, CPU quota, heap, replicas,
  proxy/TLS, DB, client, máy tạo tải

Kịch bản:
  endpoint mix, payload, auth, open/closed model,
  warm-up, stages, duration, generator version

Quan sát ở từng nấc:
  offered vs achieved RPS, dropped iterations,
  p50/p95/p99, timeouts/error status,
  CPU, GC, memory, event-loop lag,
  scheduler queue, HTTP/DB connection pool

Bằng chứng chẩn đoán:
  timestamp, thread dump/JFR/profiler,
  stack của event-loop hoặc downstream queue,
  mối liên hệ với thời điểm p99 tăng

Kết luận:
  ngưỡng tải đạt/không đạt SLO trong môi trường nêu trên,
  nghi vấn và bằng chứng, bottleneck hiện tại,
  mức chắc chắn, rủi ro còn mở

Thay đổi và kiểm chứng:
  code/config đã đổi, phép thử lặp cùng điều kiện,
  tác động tới p95/p99/errors/throughput/resource,
  bước thử tiếp theo nếu chưa có đủ bằng chứng
```

Ví dụ diễn giải **không phải số liệu đã đo**: “Trong bước tăng từ 40 lên 80 req/s, p99 của endpoint nhẹ tăng mạnh, trong khi CPU dưới mức bão hòa. Thread dump tại các đỉnh latency cho thấy một event-loop thread đang thực thi `Thread.sleep` từ handler của endpoint chậm. Sau khi chuyển callable sang boundedElastic, p99 của endpoint nhẹ giảm trong phép thử tương đương; mức tải cao tiếp tục bị giới hạn bởi pool của blocking backend.” Đây là chuỗi suy luận từ **số liệu + stack + thí nghiệm đối chứng**, không phải suy đoán chỉ từ biểu đồ.

## 15. Tự kiểm tra

**Câu 1.** WebFlux trả `Mono<String>` thì chắc chắn không có blocking?  
**Đáp:** Không. Nội dung của `Mono.fromCallable`, `map`, `flatMap` hoặc code trước khi tạo `Mono` vẫn có thể gọi blocking API. Cần xác định thread thực thi và API phía dưới.

**Câu 2.** `Thread.sleep(200)` trong handler có tự bị Reactor ném `IllegalStateException` không?  
**Đáp:** Không nên giả định. Reactor kiểm soát một số phương thức như `block()` trên non-blocking thread; để phát hiện `Thread.sleep` và nhiều blocking API khác có thể cần BlockHound/JFR/thread dump, với giới hạn tương thích và độ bao phủ tương ứng.

**Câu 3.** Đưa JDBC blocking vào boundedElastic đã biến database client thành non-blocking chưa?  
**Đáp:** Chưa. Thread boundedElastic vẫn chờ JDBC và chịu giới hạn worker, hàng đợi, connection pool; cách ly này giúp tránh làm nghẽn event loop.

**Câu 4.** Vì sao phải đo p95/p99 của endpoint `/lab/fast` khi endpoint khác bị tải?  
**Đáp:** Để phát hiện tác động lan truyền của event loop/CPU/tài nguyên dùng chung. Nó giúp tách “endpoint này có độ trễ nghiệp vụ 200 ms” khỏi “endpoint khác bị trì hoãn bất thường”.

**Câu 5.** k6 đặt `target: 100` iteration/s, có `dropped_iterations > 0`. Có thể kết luận server đạt 100 RPS không?  
**Đáp:** Không. Một phần lượt yêu cầu không được khởi tạo; cần kiểm tra achieved RPS và công suất máy tạo tải/VU trước khi kết luận.

**Câu 6.** Ở 50 req/s và thời gian trong hệ trung bình 200 ms, trung bình có khoảng bao nhiêu request đang xử lý nếu hệ ở steady state?  
**Đáp:** Theo Little's Law, khoảng `50 × 0,2 = 10` request. Không thay thời gian trung bình bằng p99.

**Câu 7.** CPU thấp, p99 cao thì chắc chắn event loop bị blocking?  
**Đáp:** Không. Có thể chờ downstream, connection pool, lock hoặc proxy/network. Cần stack/metrics và đối chứng.

**Câu 8.** Công cụ tải đạt một đỉnh 500 RPS trong vài giây có phải “sustainable capacity = 500 RPS”?  
**Đáp:** Không. Capacity cần được kiểm chứng ở workload và môi trường cụ thể, giữ đủ lâu, đạt latency/error SLO, queue/tài nguyên ổn định và hồi phục khi giảm tải.

**Câu 9.** Khi phép thử `/lab/offloaded` tốt hơn `/lab/blocked`, có nghĩa boundedElastic là giải pháp cuối cùng cho mọi blocking I/O không?  
**Đáp:** Không. Đó là bằng chứng cần cách ly blocking khỏi event loop; vẫn phải đánh giá pool, timeout, rate limits và khả năng dùng API non-blocking thật.

## Tài liệu tham khảo

- [Spring Framework — WebFlux concurrency model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): giả định non-blocking, thread model và khác biệt với Servlet.
- [Project Reactor — FAQ: wrapping a synchronous blocking call](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking): `fromCallable` và `subscribeOn(Schedulers.boundedElastic())`.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `publishOn`, `subscribeOn`, `parallel` và `boundedElastic`.
- [BlockHound — README](https://github.com/reactor/BlockHound): instrumentation blocking calls và yêu cầu JVM/phiên bản.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): HTTP, JVM và system observability.
- [Reactor Netty — Reference Guide](https://projectreactor.io/docs/netty/release/reference/): event loops, connection provider, metrics.
- [Grafana k6 — Ramping arrival rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-arrival-rate/): kịch bản open arrival theo nấc.
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/): điều kiện pass/fail, latency và error-rate.
- [Grafana k6 — Arrival-rate VU allocation](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/arrival-rate-vu-allocation/): số VU và `dropped_iterations`.
