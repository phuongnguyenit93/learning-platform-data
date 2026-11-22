# spring.lifecycle.timeout-per-shutdown-phase và thời gian chờ hoàn tất

## 1. Khi hệ thống nhận SIGTERM: vì sao 30 giây vẫn chưa đủ?

Ứng dụng Spring Boot đang xử lý request HTTP, ghi bản ghi database và có các consumer/worker background. Khi Kubernetes rolling deploy, request cũ bị ngắt, job đang chạy dở hoặc Pod bị `SIGKILL` trước khi kịp flush dữ liệu. Người vận hành đã thêm:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

nhưng ứng dụng đôi khi **dừng lâu hơn 30 giây**, đôi khi bị cắt **trước khi đủ 30 giây**. Đây không phải mâu thuẫn: property này **không phải hard timeout cho toàn bộ JVM**. Trong Spring Boot, nó điều khiển **thời gian Spring LifecycleProcessor chờ các SmartLifecycle beans trong mỗi nhóm phase hoàn tất việc stop**. Thời gian của HTTP graceful shutdown là một phần trong cơ chế đó, còn platform termination deadline, executor shutdown, preStop, destroy callbacks và các network timeouts là những đồng hồ riêng.

Bài học thuộc mục **Dừng có kiểm soát**, hướng tới kỹ năng:
- Hiểu `spring.lifecycle.timeout-per-shutdown-phase` chính xác theo **phase**, không nhầm với HTTP request timeout hoặc tổng thời gian shutdown.
- Phân biệt `server.shutdown=graceful`, `ApplicationContext.close()`, `SmartLifecycle.stop(Runnable)`, `@PreDestroy`, SIGTERM/SIGKILL, readiness và draining.
- Xác định thứ tự các phases, callbacks bất đồng bộ, dependency ordering và trường hợp phase bị timeout.
- Phối hợp với `terminationGracePeriodSeconds` và `preStop` trong Kubernetes, deregistration của load balancer và các task executors.
- Chạy một demo Java 17+/Spring Boot 3.5 có request chậm và hai SmartLifecycle beans ở phase 200, 100; đo kết quả khi gửi SIGTERM.
- Thiết kế deadline/recovery cho request dài, SSE/WebSocket, jobs và các side effects không lũy đẳng.
- Có checklist kiểm thử deployment thật và cách quan sát logs/metrics.

> **Phiên bản:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, Java **17+**, Spring MVC/Tomcat cho demo. Theo tài liệu Boot 3.5, **graceful HTTP shutdown đã bật mặc định** với embedded Jetty, Reactor Netty, Tomcat và Undertow, cho cả reactive lẫn Servlet. `spring.lifecycle.timeout-per-shutdown-phase` có default **30s**. Các phiên bản cũ có thể mặc định HTTP shutdown là immediate; luôn đối chiếu tài liệu đúng phiên bản.

## 2. Định nghĩa của property

Cấu hình trong `application.yml`:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Tương đương:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

`20s` là một `Duration`. Khi cần, có thể dùng giá trị có đơn vị `500ms`, `1m`. Nên luôn viết đơn vị để tránh nhầm giây/milliseconds.

**Spring Boot 3.5 mô tả property**: timeout cho quá trình dừng **bất kỳ phase nào** (nhóm `SmartLifecycle` beans cùng giá trị `phase`). Một phase có thể chứa nhiều bean. Trong mỗi phase, lifecycle processor chờ các callback hoặc đến hết timeout. Nếu app có nhiều phase, tổng thời gian chờ có thể vượt một giá trị `timeout-per-shutdown-phase`, **không phải framework bỏ qua property**.

### So sánh khái niệm

| Đối tượng | Điều nó giới hạn | Không giới hạn |
|---|---|---|
| `spring.lifecycle.timeout-per-shutdown-phase` | Thời gian chờ **một nhóm SmartLifecycle stop** | Tổng thời gian JVM, toàn bộ @PreDestroy, mọi worker task |
| `server.shutdown=graceful` | Chọn cách dừng HTTP server cho in-flight requests | Không đặt duration riêng nếu không có lifecycle timeout |
| `server.shutdown=immediate` | Chọn shutdown không graceful cho HTTP | Không vô hiệu mọi SmartLifecycle phase khác |
| HTTP read/request timeout | Thời gian xử lý/giao tiếp một request theo stack | Không tự chờ context close |
| `terminationGracePeriodSeconds` | Ngân sách termination tổng do Kubernetes áp đặt | Không tự sửa Spring lifecycle property |
| `preStop` | Một lifecycle hook của container | Không cấp thêm độc lập một ngân sách Spring |
| `@PreDestroy` | Bean destruction callback | Không tự timebox bằng property lifecycle |
| `spring.task.execution.shutdown.await-termination-period` | Thời gian chờ executor do Boot quản lý tương ứng | Không chờ mọi executor custom không được tích hợp |

**Hệ quả:** bạn cần thiết kế nhiều timeout **phối hợp**, thay vì trông chờ một config trên thay thế các cơ chế còn lại.

## 3. SmartLifecycle phase là gì?

Spring Framework định nghĩa `Lifecycle` với `start()`, `stop()`, `isRunning()`; `SmartLifecycle` bổ sung startup tự động, phase và callback stop:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
}
~~~

Đây là **mô hình rút gọn** của interface, không phải source code hoàn chỉnh của Spring. Cách dùng:
- Mỗi bean định nghĩa `getPhase()`.
- **Khởi động** theo thứ tự phase thấp → cao.
- **Shutdown** theo thứ tự ngược lại: phase cao → thấp.
- Beans **cùng phase** được nhóm trong một đợt stop.
- `stop(Runnable callback)` có thể hoàn tất bất đồng bộ; lifecycle processor chờ **callback**.
- Callback phải được gọi sau khi bean hoàn tất quá trình stop, **đúng một lần**, kể cả khi phải báo failure có kiểm soát.
- Quan hệ phụ thuộc explicit `depends-on` có thể ảnh hưởng thứ tự, nên không dùng phase như một cách thay thế hiểu dependencies.

### Trong cùng phase có nhiều beans

Giả sử phase 200 có ba beans:
- Bean A dừng sau 1s.
- Bean B dừng sau 5s.
- Bean C dừng sau 12s.

Khi `timeout-per-shutdown-phase=10s`, nhóm phase 200 **không được 10s riêng cho A, B, C**. Processor có thể chờ nhóm tối đa gần 10s. A và B đã callback, C chưa hoàn tất thì phase có thể timeout, sau đó processor chuyển tiếp các phases khác.

Nếu tất cả stop async trong cùng group và không có phụ thuộc đặc biệt, tổng phase thường bị chi phối bởi **bean lâu nhất**, không cộng tuần tự thời gian của mọi bean trong nhóm. Tuy nhiên nếu một bean làm việc **đồng bộ và chặn trong method stop**, processor có thể không thể áp đặt hạn chờ như một bộ ngắt thread từ bên ngoài.

### Nhiều phase khác nhau

Ví dụ:
- Phase 300 dừng mất 4s.
- Phase 200 dừng mất 6s.
- Phase 100 dừng mất 3s.

Với timeout **10s mỗi phase**, tổng riêng ba phases đã gần **13s**, dù từng phase đều hoàn tất trước 10s. Nếu custom phases stop chậm và có web server phase trước chúng, thời gian JVM shutdown có thể còn dài hơn.

**Công thức tư duy:** thời gian stop ≈ tổng thời gian thực tế của các phases được xử lý tuần tự + thời gian các callbacks/destruction khác + overhead; không phải `max(phase durations)` và không phải một lần timeout chung.

## 4. Web server graceful shutdown diễn ra lúc nào?

Một flow khái niệm:

~~~text
Process nhận SIGTERM / ApplicationContext.close
             |
             v
       Spring Context closing
             |
             v
    DefaultLifecycleProcessor
             |
             +-- HTTP server graceful stop (phase sớm)
             |     +-- không nhận new HTTP requests
             |     +-- chờ requests đang xử lý hoàn tất
             |     +-- dừng chờ khi phase timeout
             |
             +-- SmartLifecycle custom phase cao
             |     +-- stop(Runnable callback)
             |
             +-- SmartLifecycle custom phase thấp
             |     +-- stop(Runnable callback)
             |
             +-- destroy callbacks / resource close
             |
             v
        JVM process exits
~~~

Spring Boot 3.5 nói HTTP graceful shutdown xảy ra trong **phase đầu tiên của SmartLifecycle stop sequence**. Server cho phép in-flight requests có cơ hội kết thúc, nhưng không cho requests mới bắt đầu.

Các embedded servers khác nhau về cách từ chối:
- Tomcat, Jetty và Reactor Netty có thể dừng nhận new requests ở network layer.
- Undertow theo tài liệu Boot 3.5 có thể còn nhận nhưng trả **503 Service Unavailable**.
- HTTP keep-alive/persistent connections có thể làm hành vi khác với kỳ vọng từ một client đơn giản.

**Đừng khẳng định** rằng sau SIGTERM mọi client mới nhận 503, hoặc mọi client cũ nhận 200. Có thể có connection refused, reset, incomplete response, proxy 502/503/504 hay timeout. Tình huống phụ thuộc server, LB, request lifecycle, connection pool và platform.

### Điểm giới hạn

Nếu request `/api/export` cần 60s nhưng còn 10s tới khi phase timeout, graceful shutdown không tự:
- Chuyển request đang chạy sang pod khác.
- Tăng thời gian Pod termination.
- Đảm bảo 60s công việc được rollback.
- Trả một HTTP status cố định khi timeout.
- Chạy lại request một cách exactly-once.

Nếu công việc dài hoặc side effect quan trọng, cần **durable queue/operation ID, idempotency, status reconciliation hoặc checkpoint** riêng.

## 5. Khi nào callback đã thực sự được hoàn tất?

Cách viết fragment sai:

~~~java
// SAI: làm async stop nhưng không báo completion.
@Override
public void stop(Runnable callback) {
    executor.execute(() -> {
        flushPendingWrites();
        // callback.run() bị quên!
    });
}
~~~

Nếu bean này nằm trong phase 100, processor có thể đợi **hết phase timeout** ngay cả khi `flushPendingWrites()` đã xong.

Một fragment minh họa hợp đồng đúng:

~~~java
@Override
public void stop(Runnable callback) {
    executor.execute(() -> {
        try {
            flushPendingWrites();
        } catch (Exception failure) {
            recordShutdownFailure(failure);
        } finally {
            callback.run();
        }
    });
}
~~~

Các tên `executor`, `flushPendingWrites` và `recordShutdownFailure` là API do dự án tự định nghĩa; đoạn code là **fragment**, không chạy độc lập. Khi vận dụng:
1. Đừng dùng một executor **đã bị dừng** trước khi bean gọi `stop`.
2. Nếu `executor.execute(...)` ném `RejectedExecutionException` ngay lúc submit, cần có policy fallback và không để lifecycle processor chờ mãi.
3. Callback chỉ báo completion của **component stop procedure**, không chứng minh side effect từ đối tác đã commit.
4. Không gọi callback trước khi việc bắt buộc đã flush xong chỉ để “shutdown nhanh”.
5. Nếu có failure, ghi nhận điều gì chưa hoàn tất để recovery sau restart.
6. Khi cần timeout cho network flush, thiết lập deadline ngay trong operation; không đợi lifecycle processor tự interrupt.
7. Ngăn nhận **công việc mới** trước khi đo outstanding work, tránh backlog kéo dài vô tận.

### Stop đồng bộ và bất đồng bộ

`stop()` không có callback thuộc `Lifecycle`; nó dùng được cho stop synchronous. Với `SmartLifecycle`, phương thức `stop(Runnable)` cho phép hoàn thành async. Không nên nhầm:
- “Bean đã bắt đầu ngừng” với “bean đã ngừng hoàn toàn”.
- “Processor hết chờ” với “mọi cleanup tasks đã bị hủy”.
- “Callback được gọi” với “dữ liệu nghiệp vụ đã được commit end-to-end”.

## 6. Per-phase timeout không phải hard interrupter

Đây là điểm kỹ thuật quan trọng. Nếu `stop(Runnable)` lập tức tạo task khác rồi return, Spring có thể áp dụng timeout khi **chờ callback**. Nhưng nếu phương thức `stop(Runnable)` tự gọi một network I/O blocking lâu trước khi return:

~~~java
// RỦI RO: fragment chặn ngay trong lời gọi stop.
@Override
public void stop(Runnable callback) {
    blockingSdk.flushWithoutTimeout();
    callback.run();
}
~~~

Thì default processor không nhất thiết có cách cắt thread này đúng ở mốc phase deadline. Một `Duration` property **không tương đương** `Thread.interrupt()`, HTTP cancellation, transaction rollback hoặc `SIGKILL`.

Đối với các thao tác stop I/O, dùng:
- SDK có **connect/read/operation timeout**.
- Future/async completion với bounded timeout, nếu cancellation thực sự có ý nghĩa.
- Đồng hồ deadline chung cho component (không để mỗi I/O attempt dùng hết cả grace).
- Durable outbox/checkpoint khi deadline hết.
- Logging nguyên nhân chưa hoàn thành.

Không dùng `System.gc()`, `Thread.stop()`, hay vòng lặp chờ vô hạn để “bảo đảm an toàn”.

## 7. @PreDestroy là giai đoạn khác

`@PreDestroy` và `DisposableBean.destroy()` được Spring gọi trong bean destruction. Chúng không tự động chịu giới hạn `spring.lifecycle.timeout-per-shutdown-phase` như các stop callbacks của `SmartLifecycle`.

Phản ví dụ:

~~~java
// Chỉ minh họa; không nên làm trong production.
@PreDestroy
void destroy() throws InterruptedException {
    Thread.sleep(60_000);
}
~~~

Nếu phase timeout là 10s, không có hợp đồng nào bảo đảm đoạn `@PreDestroy` trên sẽ bị cắt sau 10s. Nó có thể trì hoãn context close đến khi hoàn thành hoặc bị platform kill. Vì vậy:
- `@PreDestroy` phù hợp cho cleanup nhỏ, nhanh và có giới hạn.
- Dừng consumer/background loop có nhiều giai đoạn nên xem xét `SmartLifecycle`.
- Lấy runtime measurements thực tế thay vì mặc định bean destroy luôn rất nhanh.
- Đừng đặt toàn bộ persistence flush quan trọng vào một destroy callback chờ vô hạn.

### Bean dependency ordering

Một consumer cần database client để commit offset cuối. Nếu DB pool đóng **trước** consumer, callback consumer có thể fail. Phải thiết kế thứ tự:
1. Chặn công việc mới.
2. Stop/finish workers đang xử lý.
3. Commit/checkpoint.
4. Đóng downstream clients, data sources và caches khi không còn ai dùng.
5. Kết thúc observability/logging theo cơ chế framework.

Thứ tự cụ thể phụ thuộc service architecture. Spring `depends-on` và phases là công cụ hỗ trợ, không thay thế việc hiểu quan hệ tài nguyên.

## 8. Thực hành runnable: Spring Boot Java 17 với hai SmartLifecycle phases

Mục tiêu: tạo một dự án có:
- `GET /api/fast` trả ngay HTTP 200.
- `GET /api/slow?ms=6000` chạy 6 giây trên Servlet thread.
- `SmartLifecycle` bean `cache-flush` phase **200**, stop mất ~1.2s.
- `SmartLifecycle` bean `consumer-stop` phase **100**, stop mất ~1.2s.
- Khi shutdown, web server graceful phase được chờ trước, rồi **phase 200 → phase 100**.
- Dễ thay cleanup delay bằng JVM system property và phase timeout bằng Boot CLI flag.

**Chỉ là demo local**. `Thread.sleep` dùng để tạo thời gian quan sát, không đại diện cho durable business cleanup.

### 8.1. Dependencies

Tạo project từ Spring Initializr:
- Artifact ID: `shutdown-phase-demo`.
- Spring Boot **3.5.x**, Java **17+**, Gradle.
- Dependency **Spring Web**; thêm **Spring Boot Starter Test** cho tests.

Trong project đã có Gradle plugin/dependency management, `dependencies` tương đương:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là **fragment Gradle**, không phải toàn bộ file `build.gradle`. Gradle wrapper đã được Initializr tạo.

### 8.2. File Java đầy đủ

Tạo `src/main/java/demo/shutdown/ShutdownPhaseDemoApplication.java`:

~~~java
package demo.shutdown;

import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ShutdownPhaseDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShutdownPhaseDemoApplication.class, args);
    }

    @Bean
    SmartLifecycle cacheFlusher() {
        return new DelayedStopBean(
            "cache-flush", 200, Long.getLong("demo.cleanup.ms", 1200L));
    }

    @Bean
    SmartLifecycle messageConsumer() {
        return new DelayedStopBean(
            "consumer-stop", 100, Long.getLong("demo.cleanup.ms", 1200L));
    }

    private static final class DelayedStopBean implements SmartLifecycle {
        private final String name;
        private final int phase;
        private final long delayMs;
        private final AtomicBoolean running = new AtomicBoolean();

        private DelayedStopBean(String name, int phase, long delayMs) {
            this.name = name;
            this.phase = phase;
            this.delayMs = delayMs;
        }

        @Override
        public void start() {
            running.set(true);
            System.out.println(name + " START phase=" + phase);
        }

        @Override
        public void stop(Runnable callback) {
            System.out.println(name + " STOP_BEGIN phase=" + phase);

            Thread cleanupThread = new Thread(() -> {
                try {
                    Thread.sleep(delayMs);
                    System.out.println(
                        name + " STOP_COMPLETE phase=" + phase);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    System.out.println(
                        name + " STOP_INTERRUPTED phase=" + phase);
                } finally {
                    running.set(false);
                    callback.run();
                }
            }, name + "-cleanup");

            // Chỉ dùng daemon thread để học timeout behavior.
            cleanupThread.setDaemon(true);
            cleanupThread.start();
        }

        @Override
        public void stop() {
            running.set(false);
        }

        @Override
        public boolean isRunning() {
            return running.get();
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return phase;
        }
    }
}

@RestController
class DemoHttpController {

    @GetMapping("/api/fast")
    public Map<String, String> fast() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/slow")
    public Map<String, Object> slow(
            @RequestParam(defaultValue = "6000") long ms)
            throws InterruptedException {

        if (ms < 0 || ms > 15000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "ms must be between 0 and 15000"
            );
        }

        System.out.println("HTTP_WORK_BEGIN ms=" + ms);
        // Mô phỏng I/O đồng bộ trên Servlet worker thread.
        Thread.sleep(ms);
        System.out.println("HTTP_WORK_COMPLETE ms=" + ms);

        return Map.of("status", "done", "sleptMs", ms);
    }
}
~~~

**Kiểm tra khả năng chạy:**
- Một Java source duy nhất có một `public class` cùng tên file; `DemoHttpController` là package-private top-level class được Spring Boot component scan trong `demo.shutdown`.
- `@Bean` trả hai `SmartLifecycle` instances, `getPhase()` lần lượt 200 và 100.
- `Long.getLong("demo.cleanup.ms", 1200L)` đọc **JVM system property** có kiểu long, không phải một Spring `@ConfigurationProperties`. Đổi delay khi chạy bằng `-Ddemo.cleanup.ms=3500`.
- `running` dùng `AtomicBoolean` bảo đảm visibility khi start/stop callback chạy ở các threads khác nhau.
- `stop(Runnable)` gọi callback trong `finally`, nên không bỏ quên completion khi thread bị interrupt. Trong production cần xử lý failure và bảo toàn state mạnh hơn.
- Dùng `System.out.println` để học; log thực tế nên có structured timestamps và phase name.
- `Thread.sleep` nằm trên Servlet thread của MVC. Không chuyển nguyên method này sang WebFlux event loop.

### 8.3. Cấu hình application.yml

Tạo `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 8s
~~~

`server.shutdown: graceful` trong Boot 3.5 chỉ là **ghi rõ default**. `8s` là tham số phục vụ bài thực hành, không phải recommendation cho mọi server.

### 8.4. Build/Run

Ở root project:

~~~bash
./gradlew bootJar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootJar
~~~

Khi artifact ID là `shutdown-phase-demo` và version mặc định của Initializr, jar thường có tên:

~~~text
build/libs/shutdown-phase-demo-0.0.1-SNAPSHOT.jar
~~~

**Kiểm tra tên file thực tế trước khi chạy**, vì nó phụ thuộc build config. Trên Linux/macOS/WSL:

~~~bash
java -jar build/libs/shutdown-phase-demo-0.0.1-SNAPSHOT.jar
~~~

Chạy Java process trực tiếp thuận tiện hơn `bootRun` khi muốn gửi SIGTERM đến đúng **JVM PID**, không nhầm Gradle wrapper/daemon.

## 9. Thử HTTP graceful shutdown có một request đang chạy

Mở ba terminals trong Linux/WSL/container environment:

**Terminal A:** chạy Java process ở mục 8.4; quan sát startup logs.

**Terminal B:** bắt đầu một request 6s:

~~~bash
curl -sS -i \
  "http://localhost:8080/api/slow?ms=6000"
~~~

**Khi Terminal B vẫn đang chờ**, dùng Terminal C tìm đúng PID Java:

~~~bash
jps -lv
~~~

Gửi signal:

~~~bash
kill -TERM 12345
~~~

`12345` là **PID minh họa**, thay bằng PID JVM thực tế. Không gửi signal đến tất cả Java processes trên máy.

### Khi grace 8s đủ

Nếu SIGTERM đến ngay sau khi request bắt đầu và không có bottleneck lớn, HTTP request có cơ hội hoàn tất:

~~~json
{"status":"done","sleptMs":6000}
~~~

Thứ tự JSON field không cố định; status HTTP kỳ vọng **200** khi request thực sự được hoàn tất. Logs liên quan có thể là:

~~~text
HTTP_WORK_BEGIN ms=6000
... embedded web server graceful shutdown begins ...
HTTP_WORK_COMPLETE ms=6000
cache-flush STOP_BEGIN phase=200
cache-flush STOP_COMPLETE phase=200
consumer-stop STOP_BEGIN phase=100
consumer-stop STOP_COMPLETE phase=100
... application stops ...
~~~

Các dòng Boot do framework phát có format và text thay đổi theo server/logging config. Hai custom phases có thứ tự **200 → 100** khi shutdown; startup ngược lại **100 → 200**. Nếu client bị disconnect, proxy timeout hoặc signal đến gần cuối grace, response có thể khác. Một lần demo thành công không bảo đảm cùng behavior dưới load rất lớn.

### Request mới trong thời gian dừng

Một request mới gửi ngay khi graceful stop bắt đầu có thể nhận connection refused/reset hoặc lỗi của proxy. **Không viết test chỉ assert 503**. Boot 3.5 với Tomcat/Jetty/Reactor Netty dừng nhận ở network layer; Undertow có thể trả 503. Client retry phải tuân semantics HTTP và idempotency, không tự động retry POST quan trọng khi kết quả lần đầu chưa rõ.

### Nếu dùng Windows

PowerShell `Stop-Process` thường dùng đường termination khác POSIX SIGTERM; không dựa vào nó để xác nhận graceful semantics. Hãy dùng WSL/Linux hoặc một container rồi gửi SIGTERM. Trên Docker, `docker stop` gửi stop signal tới PID 1 rồi chờ theo timeout; Java phải nhận signal đúng, nếu shell wrapper nuốt signal thì graceful hook có thể không chạy.

## 10. Thử riêng per-phase vs toàn thời gian shutdown

Để phân biệt timeout per phase với total:
1. Khởi động lại app sau mỗi lần thử.
2. **Không** gửi request slow, để web graceful phase không phải chờ lâu.
3. Đặt phase timeout **2s** và mỗi custom cleanup **1.2s**:

~~~bash
java -jar build/libs/shutdown-phase-demo-0.0.1-SNAPSHOT.jar \
  --spring.lifecycle.timeout-per-shutdown-phase=2s
~~~

Gửi SIGTERM. Logs custom liên quan:

~~~text
cache-flush STOP_BEGIN phase=200
cache-flush STOP_COMPLETE phase=200
consumer-stop STOP_BEGIN phase=100
consumer-stop STOP_COMPLETE phase=100
~~~

Hai custom phases dùng khoảng **1.2s + 1.2s = 2.4s**, đã lớn hơn **2s** nhưng không vi phạm property vì mỗi phase có budget 2s riêng.

**Không so sánh process wall-clock với đúng 2.400ms**: còn phases/framework, scheduling, IO flush, JVM overhead và biến động runtime. Hãy quan sát phase ordering và callback completion.

### Một cleanup cố ý chạy lâu hơn phase timeout

Khởi động lại với:

~~~bash
java -Ddemo.cleanup.ms=3500 \
  -jar build/libs/shutdown-phase-demo-0.0.1-SNAPSHOT.jar \
  --spring.lifecycle.timeout-per-shutdown-phase=2s
~~~

Sau SIGTERM, mỗi custom cleanup dự kiến mất **3.5s**, nhưng processor chỉ đợi gần **2s cho một phase**. Có thể thấy:
- Processor báo phase timeout và chuyển sang phase kế tiếp.
- `STOP_BEGIN phase=100` xuất hiện khi phase 200 chưa in `STOP_COMPLETE`.
- Vì threads cleanup trong demo là **daemon**, process có thể kết thúc trước khi chúng kịp in hoàn tất.
- Không có bằng chứng Spring đã `Thread.interrupt()` tất cả threads đúng ở giây thứ hai.

**Điểm bài học:** phase timeout giới hạn **thời gian chờ**, không đảm bảo completion, cancellation hay durability. Không mô phỏng kiểu “chấp nhận mất dữ liệu” trên production.

## 11. Một phase có hai beans: cùng chia deadline

Để kiểm chứng, thêm bean phase 200 thứ hai với cleanup 800ms (fragment đặt trong class demo):

~~~java
@Bean
SmartLifecycle secondCacheFlusher() {
    return new DelayedStopBean("another-flush", 200, 800L);
}
~~~

Fragment này nằm trong **class đã chứa DelayedStopBean**, không phải file Java riêng. Khi stop phase 200, lifecycle processor gọi stop cho beans cùng phase và chờ callbacks trong **một time budget**. Với phase timeout 2s, `another-flush` xong 0.8s và `cache-flush` xong 1.2s, phase có thể hoàn tất khoảng 1.2s, **không phải cộng từng bean 0.8+1.2=2s** theo mặc định.

Nếu một bean không gọi callback, phase có thể phải đợi đến 2s ngay cả khi bean còn lại rất nhanh. Khi có dependencies hoặc thực hiện stop đồng bộ dài, phải quan sát behavior thực tế, không dựa vào phép max đơn giản như bảo đảm tuyệt đối.

### Không tự “sửa” bằng cách đổi mọi phase thành 0

Đặt tất cả custom SmartLifecycle beans cùng phase khiến chúng stop gần như đồng thời, có thể:
- Resource bị đóng trước dependent worker.
- Consumer chưa ngừng nhưng publisher đã đóng.
- Trace/log exporter dừng khi jobs vẫn cố ghi logs.
- DB pool đóng trước transaction flush.

Chọn phase dựa trên dependency ownership và stop sequence. Khi có thể, dùng framework-managed lifecycle cho integration components; không override phases bừa.

## 12. Spring Boot task execution/scheduling có shutdown config riêng

Bên cạnh phase timeout, Boot có:

~~~yaml
spring:
  task:
    execution:
      shutdown:
        await-termination: true
        await-termination-period: 10s
    scheduling:
      shutdown:
        await-termination: true
        await-termination-period: 10s
~~~

Các properties trên điều khiển behavior của **auto-configured task execution/scheduling components phù hợp**, không phải mọi `ExecutorService` do bạn tự `new`. Giá trị là minh họa; các defaults/behavior phụ thuộc loại executor, phiên bản, virtual threads và cách tạo bean.

Một service có nhiều queued tasks cần tách:
- Ngừng submit jobs mới.
- Đợi jobs nhỏ có thể hoàn tất trước deadline.
- Checkpoint jobs không đủ thời gian.
- Đưa work trở lại durable queue/outbox để chạy lại.
- Đảm bảo retries và redelivery không nhân đôi side effect.

**Không tính “đã gửi task vào Executor” là đã hoàn tất công việc nghiệp vụ**. Nếu JVM bị kill, in-memory queue thường không bền. Shutdown timeout chỉ đặt ngân sách chờ, không tự cung cấp exactly-once delivery.

### Custom executor

Nếu app viết:

~~~java
// Fragment: executor tạo bằng tay, không được Boot tự quản lý đầy đủ.
ExecutorService executor = Executors.newFixedThreadPool(4);
~~~

thì cần explicit lifecycle/bean destroy behavior hoặc dùng Boot-managed Executor. Việc chỉ set `spring.task.execution.shutdown.await-termination-period` không tự shutdown/await mọi executor được tạo ở bất kỳ chỗ nào.

## 13. Request dài và long-lived HTTP responses

HTTP graceful stop cho các requests đang xử lý một cơ hội hoàn tất, nhưng phải phân loại request:

| Workload | Rủi ro khi SIGTERM | Phương án |
|---|---|---|
| JSON GET 100ms | Thường hoàn thành trong grace | Đo latency, giới hạn request timeout |
| POST payment/order 5s | Client có thể mất response sau DB commit | Idempotency key + lookup operation status |
| HTTP export 60s | Dài hơn phase budget | Async job + 202/operation ID/download sau |
| File upload lớn | Đang nhận body khi connector ngừng | Bounded upload/resumable protocol nếu cần |
| SSE vô hạn | Request không hoàn tất tự nhiên | App drain/complete stream + event replay |
| WebSocket hàng giờ | Session gắn vào một pod | Close 1001 khi có thể, reconnect/backoff/shared state |
| Long polling | Request đang đợi sự kiện | Kết thúc có kiểm soát, client gửi lại theo cursor |
| HTTP/2 stream | Có thể chia connection với nhiều streams | GOAWAY/connection draining và per-stream semantics |

**Không đặt grace period hàng giờ để giữ WebSocket sống trong rolling deploy**. Cần application-level drain và client reconnect. Với SSE, `Last-Event-ID` chỉ giúp khi server có **event IDs bền và replay implementation**; không tự động biến RAM `Flux.interval` thành message log.

Khi downstream side effect được áp dụng nhưng client chưa thấy response, kết quả **mơ hồ**. Với POST không lũy đẳng, đừng retry bằng operation ID mới sau shutdown; dùng cùng idempotency key hoặc reconcile status.

## 14. Kubernetes deadline: một ngân sách tổng, không phải per-phase

Khi Pod bị xóa/scale-in:

~~~text
Kubernetes marks Pod terminating
        |
        +-- Endpoint slices / LB routing dần cập nhật
        +-- preStop hook (nếu được khai báo)
        |       |
        |       +-- có thể dùng vài giây trong tổng grace
        |
        +-- SIGTERM đến process PID 1
        |       |
        |       +-- Boot graceful web phase
        |       +-- other SmartLifecycle phases
        |       +-- destroy callbacks
        |
        +-- JVM exits normally
        |
        +-- Nếu hết terminationGracePeriodSeconds
                -> SIGKILL/force termination theo runtime
~~~

**Các events propagation và hooks có thể chồng lấn**, không có cam kết hoàn toàn tuần tự mọi network edge. Theo tài liệu Kubernetes, default `terminationGracePeriodSeconds` thường **30s**. Nó tính cho **toàn** quá trình termination; `preStop` tiêu tốn phần trong đó. Nếu app có:
- preStop = 10s;
- phase web chờ 20s;
- consumer phase 10s;
- destroy overhead 5s;
- Pod grace = 30s;

thì cấu hình **mâu thuẫn về ngân sách**. Java có thể bị kill trước cleanup, bất kể property Spring là 20s/30s. Tránh nghĩ “preStop 10s, sau đó Kubernetes cho Spring thêm 30s” nếu tổng budget chỉ là 30s.

### Đề xuất budget có margin

Ví dụ để lập kế hoạch (không phải production defaults):

| Khoản | Budget dự kiến |
|---|---:|
| pre-drain/LB propagation | 5s |
| HTTP graceful phase | 12s |
| Consumer phase | 8s |
| Flush phase | 6s |
| Destroy/executor overhead | 4s |
| Safety margin | 5s |
| **Tổng** | **40s** |

Giả sử Pod grace 45s sẽ có một chút đệm nếu các giả định đúng. Nhưng nếu system có thêm phases/GC pauses, thời gian vẫn có thể dài hơn. Tính `terminationGracePeriodSeconds` dựa vào **measured maximum shutdown durations**, request latency SLO, background queue drain rate và infrastructure behavior.

**Không hardcode per-phase=45s chỉ vì Pod grace=45s**: nếu preStop hoặc nhiều phases dùng gần 45s mỗi cái thì platform vẫn kill.

## 15. Readiness, liveness và pre-drain

Spring Boot có `ApplicationAvailability` và `ReadinessState`:
- `ACCEPTING_TRAFFIC`: app sẵn sàng nhận workload mới.
- `REFUSING_TRAFFIC`: app không nên được routing new requests.
- Liveness cho biết tiến trình vẫn khỏe hay cần restart, **không phải tín hiệu “đừng gửi request mới”**.

Khi graceful shutdown bắt đầu, Boot có thể chuyển readiness sang REFUSING_TRAFFIC và dừng HTTP connector nhận new requests. Nhưng readiness probe có thể **không đọc được HTTP 503** vì connector đã ngừng accept. Với hệ thống có LB propagation delay, nên thiết kế **pre-drain trước SIGTERM** khi cần:
1. Chuyển app sang state draining/readiness false.
2. Từ chối new business intake, đặc biệt background jobs/handshakes.
3. Đợi LB/ingress endpoint propagation trong window có đo.
4. Chủ động kết thúc long-lived streams/reject new subscriptions.
5. Gửi SIGTERM và để HTTP graceful + SmartLifecycle cleanup.
6. Client reconnect hoặc job runner khôi phục từ durable state.

Có thể phát availability event từ control plane (fragment):

~~~java
// Fragment trong bean có ApplicationContext context:
AvailabilityChangeEvent.publish(
    context, ReadinessState.REFUSING_TRAFFIC);
~~~

Imports:
- `org.springframework.boot.availability.AvailabilityChangeEvent`
- `org.springframework.boot.availability.ReadinessState`
- `org.springframework.context.ApplicationContext`

**Không mở endpoint public để người ngoài bật draining tùy ý.** Nếu có admin endpoint, yêu cầu authentication/authorization/mTLS hoặc internal-only access. Chỉ thay readiness false không đảm bảo mọi Load Balancer lập tức ngừng gửi traffic; cần test propagation.

### Kubernetes PodSpec minh họa

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: spring-api
      image: example/shutdown-demo:local
      ports:
        - containerPort: 8080
      readinessProbe:
        httpGet:
          path: /actuator/health/readiness
          port: 8080
        periodSeconds: 2
        failureThreshold: 1
      livenessProbe:
        httpGet:
          path: /actuator/health/liveness
          port: 8080
        periodSeconds: 5
        failureThreshold: 3
~~~

Đây là **fragment PodSpec**, không phải Deployment đầy đủ và `example/shutdown-demo:local` không phải image production. Phải thêm `spring-boot-starter-actuator`, bật probes phù hợp nếu environment không tự bật, bảo vệ management endpoints và triển khai readiness/liveness đúng server port.

### preStop sleep: làm gì và không làm gì?

~~~yaml
lifecycle:
  preStop:
    exec:
      command: ["/bin/sh", "-c", "sleep 5"]
~~~

Đây chỉ là một fragment container. Nó **trì hoãn** tín hiệu dừng, có thể tạo window cho endpoint propagation, nhưng:
- Không tự phát `REFUSING_TRAFFIC`.
- Không tự stop consumer, websocket, scheduler.
- Không bảo đảm mọi ingress đã cập nhật trong 5s.
- Trừ 5s khỏi termination grace.
- Có thể khiến rollout chậm nếu quá nhiều pods cùng chờ.

Một preStop tốt cần gắn với rollout/capacity strategy và đo đạc, không đơn thuần copy con số từ ví dụ mạng.

## 16. Docker PID 1 và tín hiệu đến JVM

Một container Docker có thể dùng:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Exec-form giúp Java làm PID 1. Nếu dùng shell wrapper, nên dùng `exec java -jar ...` để shell chuyển giao process; không chạy Java là child của shell không forward signal.

Khi runtime gửi `SIGTERM`:
- JVM có cơ hội chạy shutdown hook/context close.
- Nếu wrapper nuốt signal, Spring không nhận được đúng yêu cầu dừng.
- Khi platform grace hết, runtime có thể dùng SIGKILL, bỏ qua cleanup.

**Không dùng** `kill -9` hoặc Windows `Stop-Process` như test chính của graceful shutdown. Chúng có semantics khác và có thể kết thúc process mà không chạy Spring cleanup.

## 17. Background workers: cần bảo đảm durability trước deadline

Một consumer:
1. Nhận message “charge order 123”.
2. Bắt đầu remote request.
3. JVM nhận SIGTERM.
4. Remote API mất lâu hơn remaining grace.
5. Process bị kill.

Nếu message đã ACK **trước commit**, message có thể mất dù payment chưa hoàn tất. Nếu chưa ACK, broker có thể redeliver sau restart, làm duplicate nếu thiếu idempotency. Vì vậy:
- Stop intake trước khi close dependencies.
- Đánh dấu in-flight operations.
- Có processing deadline và bounded remote timeout.
- Commit/ACK theo durable outcome, không ngay khi nhận message.
- Dùng stable business operation ID/idempotency key.
- Dùng outbox/queue/leases/checkpoints khi job dài hơn shutdown grace.
- Có status reconciliation cho remote operations có outcome mơ hồ.
- Test crash/hard kill, không chỉ graceful stop thành công.

`SmartLifecycle` stop callback phản ánh component đã hoàn tất protocol dừng **theo implementation**, không phải chứng chỉ exactly-once cho distributed transaction.

## 18. Quan sát hiệu quả của per-phase timeout

Một dashboard/logs hữu ích có thể trả lời:
- Thời gian bắt đầu drain/readiness false.
- Thời gian JVM nhận SIGTERM.
- HTTP requests đang chạy lúc stop, duration và route template.
- Thời điểm HTTP graceful phase bắt đầu/hoàn tất/hết timeout.
- Mỗi SmartLifecycle bean/phase `STOP_BEGIN`, callback complete, timeout.
- In-flight Kafka/Rabbit messages, executor queue depth, DB active transactions.
- Tổng shutdown duration và process exit code.
- Pod forced kill events, 502/503 của ingress, client reconnect spikes.

Nên dùng **structured logs** với fields có cardinality thấp như `phase`, `component`, `outcome`, `durationMs`, `instance`. Không đưa JWT, cookies, raw personal IDs hay sensitive payload vào metrics labels.

Một số log text của embedded server được tự động phát tùy version/level. Không khẳng định một chuỗi log cụ thể phải có ở mọi bản Boot. Dùng timestamp và các marker riêng để đo.

### Dấu hiệu thiếu ngân sách

- Phase stop callback không thấy `STOP_COMPLETE` trước khi process biến mất.
- Log phase timeout xuất hiện hoặc server graceful timeout.
- Kubernetes report exit code 137/SIGKILL (cần đối chiếu OOMKill vs platform force-kill).
- HTTP clients bị reset/partial response trong rollout.
- Số queue jobs sau restart tăng, active tasks chưa được ACK.
- Replica mới bị reconnect storm do hàng nghìn clients dừng đồng thời.

Không đồng nhất exit code 137 với đúng một nguyên nhân; cần xem `kubectl describe pod`, Events, `lastState.terminated.reason`, node/container memory và termination timeline.

## 19. Kiểm thử tự động: controller test và signal integration test khác nhau

Trong project có `spring-boot-starter-test`, tạo `src/test/java/demo/shutdown/ShutdownPhaseDemoApplicationTests.java`:

~~~java
package demo.shutdown;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ShutdownPhaseDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void fastRequestReturnsOk() throws Exception {
        mvc.perform(get("/api/fast"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void slowRequestCanFinish() throws Exception {
        mvc.perform(get("/api/slow").param("ms", "10"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sleptMs").value(10));
    }

    @Test
    void invalidSlowDurationIsRejected() throws Exception {
        mvc.perform(get("/api/slow").param("ms", "15001"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Đây là **test file Java 17/JUnit5 đầy đủ**, nhưng các `@SpringBootTest`/MockMvc tests chủ yếu kiểm tra HTTP handler behavior. Nó **không chứng minh** real process SIGTERM, network connector shutdown hoặc Kubernetes Pod termination.

Chạy:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

Không khẳng định `BUILD SUCCESSFUL` khi chưa thực sự chạy trên project; người học cần build và kiểm tra trong môi trường của mình.

### Signal/termination integration test cần gì?

Dùng process thật trong Linux/WSL/container:
1. Start jar và chờ /api/fast healthy.
2. Gửi HTTP slow request.
3. Khi handler đã vào, gửi `SIGTERM` tới đúng JVM.
4. Với 8s grace và 6s work, kỳ vọng có cơ hội hoàn tất 200.
5. Đổi grace 2s; quan sát incomplete request/failure, không assert một HTTP status cố định.
6. Thêm hai beans cùng phase, kiểm tra chung phase deadline.
7. Cho một bean không callback trong test cô lập, xem phase timeout và logs.
8. Thử `preStop`/`terminationGracePeriodSeconds` trên Kubernetes test cluster.
9. Chạy dưới CPU throttling/GC/downstream slow conditions.
10. Thử `SIGKILL` riêng để chứng minh recovery khi shutdown hooks không chạy.

**Không đo chỉ bằng mock server**, vì MockMvc không thể tái tạo đầy đủ signal-to-JVM, LB deregistration, container grace và socket closure.

## 20. FAQ: các ngộ nhận chính

| Ngộ nhận | Sự thật |
|---|---|
| “Property 30s = toàn JVM chỉ dừng tối đa 30s” | Không; mỗi SmartLifecycle phase có 30s wait budget |
| “Có 3 beans cùng phase, mỗi bean được 30s riêng” | Không; cùng chung phase timeout |
| “Phase 100 sẽ stop trước phase 200” | Ngược lại, shutdown phase cao → thấp |
| “Không gọi callback vẫn ổn, thread xong rồi” | Processor có thể đợi đến timeout vì không được báo completion |
| “Hết phase timeout chắc chắn interrupt thread” | Timeout chỉ giới hạn chờ, không hard cancel toàn bộ I/O/threads |
| “@PreDestroy bị timeout property này cắt” | Không tự động, đó là giai đoạn bean destruction khác |
| “Boot 3.5 phải bật server.shutdown mới graceful” | Graceful đã là default ở Boot 3.5; khai báo explicit được |
| “Mọi new request sau SIGTERM nhận 503” | Server/proxy có thể từ chối ở network layer, không có status cố định |
| “Client thấy reset => server đã rollback POST” | Không, outcome có thể đã commit; cần idempotency/status lookup |
| “TaskExecutor queue chờ chung HTTP grace” | Có cấu hình/cơ chế executor shutdown riêng |
| “PreStop xong rồi Pod mới bắt đầu đếm 30s” | PreStop tiêu trong tổng terminationGracePeriodSeconds |
| “Tăng Spring grace thành 5 phút thì Kubernetes đợi 5 phút” | Pod grace độc lập, có thể kill trước |
| “Graceful shutdown chuyển WebSocket tới pod mới” | Không; client reconnect và restore state |
| “SIGKILL dùng để test graceful” | SIGKILL bypass cleanup; dùng để test crash recovery |
| “Một lần shutdown local thành công là production safe” | Cần load/proxy/rollout tests, metrics và durable recovery |

## 21. Checklist khi đưa vào production

- [ ] Đã kiểm tra đúng **Spring Boot version** và default HTTP graceful behavior.
- [ ] Cấu hình `server.shutdown` và `spring.lifecycle.timeout-per-shutdown-phase` tường minh khi cần.
- [ ] Mỗi `SmartLifecycle` bean có phase/dependency rõ; startup và stop ordering hợp lý.
- [ ] `stop(Runnable)` gọi callback **sau** khi thật sự hoàn tất, xử lý error/rejection paths.
- [ ] Không có I/O blocking vô hạn trong `stop()`, `@PreDestroy` hay network cleanup.
- [ ] HTTP new requests bị chặn ở đúng thời điểm; requests cũ được chờ trong budget đo được.
- [ ] Readiness/drain propagation được phối hợp với LB/ingress.
- [ ] Pod `terminationGracePeriodSeconds` bao preStop + phases + destructors + margin.
- [ ] Container PID 1 hoặc shell wrapper forward SIGTERM đến JVM.
- [ ] Background executors/schedulers có shutdown policy riêng.
- [ ] Message consumers stop intake rồi ACK/commit/retry theo durable state.
- [ ] Jobs vượt grace có checkpoint/outbox/lease và idempotency.
- [ ] SSE/WebSocket có close/reconnect/backoff/replay; không kỳ vọng socket migration.
- [ ] Có dashboards/logs cho phase durations, HTTP active, queue lag, forced kills.
- [ ] Đã test 2s/8s/long request/long cleanup trong môi trường an toàn.
- [ ] Đã test cả graceful SIGTERM và hard-crash recovery riêng.
- [ ] Không tăng per-phase timeout quá lớn khiến rolling deploy kẹt.
- [ ] Không suy rằng HTTP completed 200 đồng nghĩa mọi background work đã durable.

## 22. Câu hỏi ôn tập

**1.** `spring.lifecycle.timeout-per-shutdown-phase=20s` có giới hạn cả JVM shutdown 20s không?

**Đáp án:** Không. Đây là giới hạn chờ **mỗi SmartLifecycle phase**, không phải hard global deadline.

**2.** Hai beans cùng phase 200 cần 1s và 7s, per-phase timeout 10s. Spring chờ tổng 8s?

**Đáp án:** Không nhất thiết. Nếu stop async chạy song song, thường nhóm xong sau bean lâu nhất (~7s) và có một deadline 10s chung.

**3.** Khi shutdown, phase 100 hay 200 chạy trước?

**Đáp án:** Phase **200** stop trước, phase **100** stop sau (startup theo chiều ngược lại).

**4.** Một bean quên `callback.run()` thì sao?

**Đáp án:** Processor có thể chờ hết timeout phase và báo không hoàn tất, dù thao tác stop thực tế xong.

**5.** `@PreDestroy` chạy 60s thì timeout-per-shutdown-phase=10s tự ngắt không?

**Đáp án:** Không mặc nhiên. Phạm vi timeout này thuộc SmartLifecycle phase waits.

**6.** Vì sao Pod grace=30s nhưng Spring phase timeout=60s vẫn bị SIGKILL?

**Đáp án:** Kubernetes có deadline tổng riêng; hết Pod grace có thể force kill JVM trước khi Spring chờ đủ.

**7.** Boot 3.5 có cần bật graceful HTTP server không?

**Đáp án:** Graceful là default theo tài liệu Boot 3.5 với embedded server hỗ trợ; có thể ghi `server.shutdown=graceful` cho rõ.

**8.** New request trong graceful phase chắc chắn có HTTP 503?

**Đáp án:** Không. Tomcat/Jetty/Reactor Netty có thể từ chối ở network layer; Undertow có thể trả 503; proxy có thể khác.

**9.** Nếu request POST mất response khi Pod dừng, retry với key mới có an toàn không?

**Đáp án:** Không. Server có thể đã commit. Cần stable idempotency key và status reconciliation.

**10.** Cleanup thread vẫn chạy sau phase timeout nghĩa là property không có tác dụng?

**Đáp án:** Không. Property giới hạn **thời gian processor chờ**; không bắt buộc interrupt thread.

**11.** Vì sao nên giữ readiness false nhưng liveness vẫn true khi drain?

**Đáp án:** Để không nhận traffic mới trong khi process còn khỏe và cần thời gian hoàn tất work; liveness false dễ dẫn tới restart quá sớm.

**12.** Có nên tăng timeout lên 10 phút chỉ vì SSE stream có thể sống 1 giờ?

**Đáp án:** Không. Streaming cần deliberate close/reconnect và replay, không bắt Pod chờ kết nối vô hạn.

**13.** Property `spring.task.execution.shutdown.await-termination-period` có thay thế lifecycle phase timeout không?

**Đáp án:** Không. Nó giới hạn việc chờ task executor tương ứng, là một thành phần trong toàn bộ shutdown design.

**14.** Test MockMvc chạy pass chứng minh graceful shutdown hoạt động qua ALB?

**Đáp án:** Không. Cần signal test ở process thật và route qua LB/ingress thực tế.

**15.** Nếu cần bảo đảm đơn hàng không mất khi bị hard kill, phần nào quan trọng nhất?

**Đáp án:** Durable transaction/queue/outbox, idempotency và recovery. Graceful timeout giúp giảm disruption nhưng không bảo vệ khi không chạy được cleanup.

### Bài tập mở rộng

Từ demo:
1. Chạy request slow 6s và gửi SIGTERM với per-phase=8s, ghi timeline response/stop.
2. Đổi per-phase=2s, chạy request slow 6s và quan sát failure path, không assert 503.
3. Cho delay của custom phases=1.2s với phase limit=2s, chứng minh tổng phase work có thể >2s.
4. Đặt system property `-Ddemo.cleanup.ms=3500` khi phase=2s, xem callback nào đến muộn.
5. Thêm bean phase 200 thứ hai, đo cùng-group deadline và lifecycle ordering.
6. Thêm một `@PreDestroy` có sleep trong **test cô lập**, quan sát vì sao không bị phase timeout ngắt.
7. Đo preStop, readiness transition và Pod termination trên cluster test; tính headroom.
8. Thêm queue consumer giả lập có pending operation ID, kiểm tra recovery sau SIGKILL.

## 23. Tài liệu chính thức

- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Framework 6.2 — Bean Lifecycle và SmartLifecycle](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html)
- [Spring Framework — DefaultLifecycleProcessor API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html)
- [Spring Framework — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Spring Boot 3.5 — Application Availability](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html)
- [Spring Boot 3.5 — Actuator Kubernetes Liveness/Readiness](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html)
- [Kubernetes — Pod Lifecycle and Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#termination-of-pods)
- [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)
- [Dockerfile ENTRYPOINT exec form](https://docs.docker.com/reference/dockerfile/#entrypoint)
- [RFC 9110 — Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html#name-idempotent-methods)

**Kết luận:** `spring.lifecycle.timeout-per-shutdown-phase` là ngân sách chờ **từng nhóm SmartLifecycle phase**, không phải tổng thời gian process hoặc universal cancellation. Dừng an toàn cần đồng bộ **readiness → traffic drain → HTTP graceful phase → worker/consumer phase callbacks → destroy/executor cleanup → Pod termination deadline**, đồng thời có durable recovery cho mọi công việc không thể hoàn tất đúng hạn.
