# Xử lý yêu cầu đang chạy, tác vụ bất đồng bộ và lời gọi dịch vụ phía sau khi dừng Spring Boot

## 1. Vì sao “dừng có kiểm soát” khó hơn gọi `System.exit()`?

Khi một phiên bản Spring Boot được thay thế lúc deploy, vẫn có thể có:
- Một request HTTP đang đợi query DB hoặc kết quả từ downstream.
- Một HTTP request Servlet đang xử lý bằng `Callable`, `DeferredResult`, `CompletableFuture` hoặc trả stream.
- Một WebFlux `Mono`/`Flux` đang chờ HTTP response từ `WebClient`.
- Một tác vụ `@Async` hoặc `TaskExecutor` đã nhận từ request nhưng **không còn gắn vào HTTP response**.
- Một `@Scheduled` task đang đồng bộ dữ liệu, consumer của message queue đang xử lý event.
- Một upload/download đang stream, WebSocket/SSE connection sống lâu, hoặc job đã ghi một phần vào storage.
- Nhiều connection pool và client HTTP cần còn sống cho đến khi các tác vụ sử dụng chúng hoàn tất.

Nếu dừng JVM ngay, request chưa trả lời có thể mất kết nối; các tác vụ bị dở dang; downstream có thể đã commit một giao dịch dù caller không nhận được response. Nhưng **chỉ đặt `server.shutdown=graceful` cũng không bảo đảm mọi việc trên được hoàn tất**.

Bài thuộc nhóm **Dừng có kiểm soát** của **Spring Boot - web-runtime**. Mục tiêu là hiểu:
1. Graceful shutdown của embedded web server chờ request nào, trong bao lâu.
2. Khác biệt giữa HTTP in-flight, Servlet async, application `@Async` và WebFlux publishers.
3. Lời gọi downstream được xử lý thế nào khi caller đang dừng, đặc biệt timeout/cancel/retry và mất response.
4. Cách chọn thời hạn, drain traffic, executor shutdown, Readiness và Kubernetes termination grace period.
5. Cách tự kiểm thử bằng Java 17+ / Spring Boot 3.3.13; không chỉ nhìn một dòng log “graceful shutdown complete”.

**Bối cảnh phiên bản:** hướng dẫn/cấu hình chính theo **Spring Boot 3.3.13, Spring Framework 6.1, Java 17+**. Boot **3.3 cần bật** `server.shutdown=graceful` một cách tường minh; các nhánh Boot mới có thể khác mặc định. Khi triển khai production, dùng nhánh còn được hỗ trợ bảo mật và đối chiếu API theo phiên bản thực tế.

## 2. Định nghĩa chính xác một lần graceful shutdown

Khi JVM/ứng dụng đóng `ApplicationContext` một cách bình thường, Spring Boot có thể yêu cầu web server:
- Dừng nhận **request mới**.
- Cho phép các **HTTP request đang xử lý** tiếp tục đến khi hoàn tất hoặc hết grace period.
- Sau đó đóng web server và tiếp tục các phase shutdown của Spring context.

Theo tài liệu Spring Boot 3.3, graceful shutdown hoạt động với **Tomcat, Jetty, Undertow, Reactor Netty** và cả **Servlet/MVC, WebFlux**. Nó xảy ra khi context đóng, ở phase dừng `SmartLifecycle` sớm nhất, dùng `spring.lifecycle.timeout-per-shutdown-phase` làm budget **cho từng phase**.

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=10s
```

**Không nhầm 10 giây này với “JVM chắc chắn sống đúng 10 giây”.** Một request kết thúc nhanh thì phase có thể xong sớm. Nếu có nhiều shutdown phases, tổng thời gian context close có thể khác một phase. Nếu container/orchestrator gửi `SIGKILL` trước khi đóng xong, không có Java cleanup callback nào cứu được.

**Cách server từ chối request mới khác nhau:** theo tài liệu Boot 3.3, Tomcat/Jetty/Reactor Netty ngừng nhận tại network layer; Undertow có thể chấp nhận connection nhưng trả **503**. Persistent connections, proxy và load balancer cũng ảnh hưởng kết quả. Đừng viết test đòi “mọi request mới trong lúc drain phải có HTTP 503”; một số client sẽ thấy connection refused/reset/EOF.

### 2.1. Timeline

```text
T0: App RUNNING, đã nhận Request A và B
        │
T1: Orchestrator đánh dấu pod terminating / drain routing
        │
T2: JVM nhận SIGTERM → SpringApplication/ApplicationContext đóng
        │
T3: Embedded web server bắt đầu graceful shutdown
        ├── Không nhận request C mới
        ├── Request A đang chạy → có thể hoàn tất, HTTP 200
        ├── Request B đang chờ downstream → chờ trong grace budget
        └── Readiness → REFUSING_TRAFFIC theo lifecycle Boot
        │
T4: Nếu mọi in-flight xong → phase web server kết thúc sớm
    Nếu quá budget → shutdown tiếp tục, requests còn lại có thể mất
        │
T5: Các bean/executor/resource khác được dừng/đóng theo lifecycle
        │
T6: JVM exit nếu không còn threads/conditions giữ process
        │
   [Nếu Pod grace đã hết: SIGKILL; cleanup Java không chạy]
```

**Lưu ý:** timeline ở trên là mô hình **logic**, không bảo đảm thứ tự chính xác của từng bean khi có custom `SmartLifecycle`/`@PreDestroy`. Không tự suy rằng `@PreDestroy` của một service luôn chạy sau khi mọi HTTP client call hoàn tất. Thứ tự và dependencies của beans cần được kiểm tra.

## 3. Bốn phạm vi công việc phải phân biệt

| Loại công việc | Ai sở hữu lifecycle? | Graceful server chờ mặc định? | Việc bạn phải làm |
|---|---|---|---|
| HTTP MVC đồng bộ (`GET` đang trong controller) | Container request | Có, trong budget của web server | Bound request time + downstream time |
| Servlet MVC async (`Callable`, `DeferredResult`, `WebAsyncTask`) | Servlet async request + executor/source | Có thể vẫn là request đang mở nếu async chưa complete | Async timeout, executor bounds, completion/error handling |
| WebFlux HTTP `Mono`/`Flux` | Reactive subscription của request | Có, trong giới hạn lifecycle server | Không `subscribe()` tách luồng; bound stream |
| `@Async`/`TaskExecutor` fire-and-forget sau khi trả 202 | Application executor/job system | **Không được bảo đảm bởi web graceful** | Executor shutdown policy + persistence/ACK/retry |
| `@Scheduled` task | Scheduler riêng | Không mặc định là HTTP request | Scheduler shutdown policy, lease/lock, idempotency |
| Message consumer | Broker listener container | Listener lifecycle, không phải web server | Stop polling, finish/ack/rollback, re-delivery |
| WebSocket/SSE lâu dài | Connection/subscription | Có thể giữ open rất lâu; server/version-specific | Max age, drain notification, close/reconnect |
| HTTP downstream call từ một request | Client + thread/Publisher + downstream service | Chỉ được gián tiếp chờ khi thuộc in-flight request | Timeouts, cancellation, idempotency và budget |

**Điểm chính:** `server.shutdown=graceful` bảo vệ **web server’s in-flight request handling**, không phải công cụ điều phối mọi task/process/transaction trong JVM.

### 3.1. Vì sao HTTP 202 nguy hiểm nếu hiểu sai?

`POST /jobs` có thể:
1. Đẩy một task vào một in-memory executor.
2. Ngay lập tức trả **202 Accepted**.
3. Client tin rằng công việc đã được chấp nhận.
4. Pod nhận SIGTERM trước khi task chạy xong.
5. Executor bị hủy hoặc JVM bị kill → task mất.

Vì HTTP response **đã hoàn tất**, graceful web server **không còn gì để chờ** cho task đó. Tăng `spring.lifecycle.timeout-per-shutdown-phase` có thể giúp một phần nếu task executor được cấu hình chờ, nhưng **không thể tạo durability khi pod crash**. Với công việc quan trọng, chỉ trả 202 sau khi ghi job bền vững vào DB/queue, trả job ID và hỗ trợ retry/idempotency/status endpoint.

## 4. Bật graceful shutdown và giới hạn thời gian đúng cách

### 4.1. Properties cốt lõi trong Boot 3.3

```properties
# Bắt buộc bật rõ trong Boot 3.3:
server.shutdown=graceful

# Timeout được dùng theo từng shutdown phase của SmartLifecycle:
spring.lifecycle.timeout-per-shutdown-phase=12s
```

Bất kỳ request đang chạy nào vượt budget có thể bị đóng sau khi phase dừng. Nếu có downstream call lâu 30 giây mà grace là 12 giây, không thể hứa chắc client sẽ nhận 200/504: JVM/server có thể đóng trước lúc controller viết response.

**Không đặt grace vô hạn** để “bảo đảm không mất request”. Một connection streaming/websocket có thể tồn tại nhiều giờ. Một pod phải dừng trong thời hạn rollout/orchestrator. Nên giới hạn:
- Thời gian tối đa request HTTP.
- Thời gian gọi từng downstream, retry và queue wait.
- Thời gian còn lại cho DB commit/response flush.
- Số tasks đang chạy và kích thước queue.
- Thời gian chờ executor shutdown.
- Grace toàn Pod với margin an toàn.

### 4.2. Ứng dụng qua container

Với Docker Linux, process Java cần nhận được **SIGTERM**. Mẫu entrypoint tốt:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/graceful-mvc-demo-1.0.0.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java","-jar","/app/app.jar"]
```

Tên jar chỉ khớp khi Gradle artifact được cấu hình/đóng gói như ví dụ. Đoạn Dockerfile minh họa nguyên tắc **exec form** để Java nhận signal, không phải image production hardened hoàn chỉnh (cần non-root, resource limits, base image security, secrets/CA phù hợp).

**Sai lầm:** `ENTRYPOINT sh -c "java -jar app.jar"` mà shell không `exec` và không forward SIGTERM. Orchestrator có thể signal tới PID 1 là shell, Java không nhận đúng signal trong thời hạn; graceful shutdown không xảy ra như mong đợi.

### 4.3. Không dùng Ctrl+C/IDE Stop làm kiểm thử duy nhất

`Ctrl+C` trong terminal thường gửi signal phù hợp. Nút Stop của IDE, Task Manager hoặc kill process tùy platform có thể terminate **không đi qua lifecycle đóng context**. `kill -9` gửi SIGKILL và chắc chắn không chạy graceful Java cleanup. Để test thực, gửi `SIGTERM` tới đúng JVM process trong Linux/container và quan sát client/network/executor.

## 5. Đường request đồng bộ và lời gọi downstream

Giả sử `GET /api/proxy` đang xử lý:

```text
HTTP client             Spring Boot A                  Service B
     │                        │                           │
     ├── GET /api/proxy ─────►│                           │
     │                        ├── GET /remote ───────────►│
     │                        │          chờ B             │
  SIGTERM to A                │                           │
     │                        │ Graceful: chờ A in-flight  │
     │                        │                           │
     │                        │◄────────── HTTP 200 ───────┤
     │◄──── HTTP 200 ─────────┤                           │
     │                        │ request complete          │
```

Ở đây A có thể trả response thành công **nếu**:
- Service B trả kịp timeout và context A vẫn giữ client/connection pool hoạt động.
- Budget graceful web server đủ dài.
- Proxy/network tiếp tục giữ kết nối tới A đang terminating.
- Không có lỗi DB/serialization/response flush.
- Không bị Pod SIGKILL trước khi kết thúc.

Graceful của A **không kéo dài timeout của B**. `RestClient`/`RestTemplate` blocking call có connection/read timeout của chính HTTP client; `WebClient` có response timeout và Reactor timeout operator. Nếu B không trả lời, một request A vẫn có thể bị kẹt dù A đã từ chối requests mới.

### 5.1. Timeout ngân sách theo toàn luồng

Ví dụ định tính:
- Pod termination grace: **30s**.
- preStop/endpoint propagation: **5s**.
- HTTP server graceful phase: **15s**.
- Downstream connect timeout: **1s**.
- Downstream read/response timeout: **4s**.
- Business retry: tối đa **1 lần** với backoff nhỏ và idempotency.
- Mục tiêu request tổng: **< 10s** để còn thời gian serialize/flush và bean shutdown.

Đây là **budget minh họa**, không phải bất đẳng thức tự được Spring bảo đảm. Tổng shutdown có thể gồm nhiều phases và executor waits, còn Kubernetes bắt đầu đếm grace **trước khi chạy preStop**. Phải đo under load và thêm margin.

**Không nối 3 thư viện với timeout 20s rồi kỳ vọng request 10s xong.** Trong một call chain A→B→C, dùng deadline chung hoặc truyền remaining budget và giới hạn retries để tránh mọi tầng dành trọn thời gian riêng.

## 6. Servlet async: `Callable` và `DeferredResult` vẫn là HTTP in-flight

Spring MVC hỗ trợ asynchronous request processing dựa trên Servlet async:
- `Callable<T>`: controller trả một Callable; Spring MVC submit vào AsyncTaskExecutor rồi dispatch response khi kết quả sẵn sàng.
- `WebAsyncTask<T>`: tương tự Callable nhưng có thể cấu hình timeout/executor riêng.
- `DeferredResult<T>`: response được giữ mở tới khi thread/event khác gọi `setResult` hoặc `setErrorResult`.
- `CompletionStage<T>`/`CompletableFuture<T>` hay reactive return type được Spring MVC adapt theo contract.
- `ResponseBodyEmitter`/`SseEmitter`: giữ HTTP response streaming cho nhiều events.

```java
// Mảnh controller MVC minh họa:
@GetMapping("/api/async")
Callable<String> async() {
    return () -> {
        Thread.sleep(400);
        return "completed";
    };
}
```

**Nhìn controller method trả về không đủ để biết request đã xong.** `Callable` được trả ngay, nhưng Servlet async response vẫn đang mở; container sẽ dispatch response sau khi task hoàn tất. Do đó nó có thể được tính là in-flight request trong graceful server.

**Khác hoàn toàn `@Async void`:**

```java
// Mảnh controller minh họa:
@PostMapping("/api/fire-and-forget")
ResponseEntity<Void> start() {
    jobService.runInBackground(); // @Async trong bean khác.
    return ResponseEntity.accepted().build(); // HTTP 202 đã kết thúc.
}
```

Với `@Async`, HTTP request không tự chờ job. Nếu cần controller giữ request cho tới khi job trả kết quả, return `CompletableFuture<T>`/`Callable<T>`/`DeferredResult<T>` phù hợp và không gửi 202 trước khi đảm bảo trách nhiệm.

**Không mặc định MVC async executor thích hợp production load.** Spring Framework docs yêu cầu cấu hình `AsyncTaskExecutor` có giới hạn phù hợp nếu dùng Callable/streaming ở quy mô lớn, cùng timeout/pool/queue. Servlet `asyncTimeout` cũng có thể khác downstream read timeout. Một handler timeout không tự hủy được một blocking SDK call không hỗ trợ interruption.

## 7. Project A: Spring Boot MVC minh họa ba loại việc cùng tồn tại

Project chạy độc lập **Java 17+ + Spring Boot 3.3.13 + Gradle**:
- `GET /api/slow?ms=...`: request MVC đồng bộ đang chạy.
- `GET /api/async?ms=...`: Servlet async `Callable`.
- `GET /api/proxy?ms=...`: gọi downstream HTTP qua `RestClient` có connect/read timeout.
- `POST /api/jobs?ms=...`: tạo `@Async` task và lập tức trả 202; nó **không là HTTP in-flight** sau response.
- `GET /api/jobs/completed`: số jobs đã xong, phục vụ quan sát trong lab.
- Có một JDK HTTP server mini ở process riêng để mô phỏng downstream; app backend không gọi HTTP quay lại chính nó trong lúc shutdown.

### 7.1. Cấu trúc

```text
graceful-mvc-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/graceful/
    │   │   ├── MvcShutdownApplication.java
    │   │   └── DemoPartnerServer.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/graceful/MvcShutdownIntegrationTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

// Chạy downstream giả lập trong tiến trình khác với Spring Boot app.
tasks.register('partnerRun', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.graceful.DemoPartnerServer'
}
```

Thêm Actuator nhằm kiểm tra readiness/metrics; không có Spring Security trong demo để đơn giản hoá bài. **Không đưa endpoint lab và metrics công khai vào production**; protect management port/actuator theo security policy.

**`src/main/resources/application.properties`:**

```properties
server.port=8080
spring.application.name=graceful-mvc-demo

# Spring Boot 3.3: bật rõ ràng.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=10s

# HTTP client gọi một process riêng, không phải chính app này.
demo.downstream.base-url=http://127.0.0.1:9090

# Servlet async request timeout, độc lập downstream read timeout.
spring.mvc.async.request-timeout=5s

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info,metrics
```

### 7.2. Application: controller, RestClient và bounded @Async executor

**`src/main/java/com/example/graceful/MvcShutdownApplication.java`:**

```java
package com.example.graceful;

import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@SpringBootApplication
@EnableAsync
public class MvcShutdownApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcShutdownApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class ClientAndExecutorConfiguration {

    @Bean
    RestClient partnerClient(
            RestClient.Builder builder,
            @Value("${demo.downstream.base-url}") String baseUrl) {

        // Lab only: HTTP URL, production cần HTTPS + auth/TLS policy.
        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(1000);
        factory.setReadTimeout(3000);

        return builder.baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }

    @Bean("jobExecutor")
    ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("demo-job-");

        // Khác HTTP graceful: cấu hình chờ riêng cho background executor.
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }
}

@Component
class WorkSignals {
    final CountDownLatch requestEntered = new CountDownLatch(1);
    final CountDownLatch jobStarted = new CountDownLatch(1);
    final AtomicInteger jobsCompleted = new AtomicInteger();
}

@Service
class AuditJobService {

    private static final Logger log =
            LoggerFactory.getLogger(AuditJobService.class);
    private final WorkSignals signals;

    AuditJobService(WorkSignals signals) {
        this.signals = signals;
    }

    @Async("jobExecutor")
    public CompletableFuture<Void> execute(long ms) {
        signals.jobStarted.countDown();
        try {
            Thread.sleep(Math.max(0, Math.min(ms, 2500)));
            signals.jobsCompleted.incrementAndGet();
            log.info("Background demo job completed");
            return CompletableFuture.completedFuture(null);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(interrupted);
        }
    }
}

@RestController
class WorkController {

    private static final Logger log =
            LoggerFactory.getLogger(WorkController.class);

    private final RestClient partner;
    private final AuditJobService jobs;
    private final WorkSignals signals;

    WorkController(RestClient partner, AuditJobService jobs,
            WorkSignals signals) {
        this.partner = partner;
        this.jobs = jobs;
        this.signals = signals;
    }

    @GetMapping("/api/slow")
    Map<String, String> slow(
            @RequestParam(defaultValue = "400") long ms)
            throws InterruptedException {

        signals.requestEntered.countDown();
        Thread.sleep(Math.max(0, Math.min(ms, 2500)));
        return Map.of("result", "slow-done");
    }

    @GetMapping("/api/async")
    Callable<Map<String, String>> async(
            @RequestParam(defaultValue = "400") long ms) {

        return () -> {
            Thread.sleep(Math.max(0, Math.min(ms, 2500)));
            return Map.of("result", "async-done");
        };
    }

    @GetMapping("/api/proxy")
    String proxy(@RequestParam(defaultValue = "400") long ms) {
        long bounded = Math.max(0, Math.min(ms, 2500));

        // Request hiện tại còn mở, RestClient call là blocking.
        // Graceful web sẽ chỉ chờ trong budget shutdown.
        return partner.get()
                .uri("/remote?ms={ms}", bounded)
                .retrieve()
                .body(String.class);
    }

    @PostMapping("/api/jobs")
    ResponseEntity<Void> enqueue(
            @RequestParam(defaultValue = "400") long ms) {

        jobs.execute(Math.max(0, Math.min(ms, 2500)))
                .whenComplete((unused, failure) -> {
                    if (failure != null) {
                        log.warn("Background job failed: {}",
                                failure.toString());
                    }
                });

        // HTTP kết thúc ở đây, dù task vẫn chạy!
        return ResponseEntity.accepted().build();
    }

    @GetMapping("/api/jobs/completed")
    Map<String, Integer> jobsCompleted() {
        return Map.of("completed", signals.jobsCompleted.get());
    }
}
```

**Tính runnable và phạm vi ví dụ:**
- Một file Java có đúng một top-level `public class` tên `MvcShutdownApplication`; các class khác package-private cùng package nên Boot component scan và bean definitions hợp lệ.
- `@EnableAsync` kích hoạt `@Async`; `AuditJobService` là bean **khác bean controller**, lời gọi qua Spring proxy nên annotation có hiệu lực. Self-invocation `this.execute(...)` trong chính service có thể bỏ qua proxy và chạy đồng bộ.
- `jobExecutor` đặt queue **có hạn** (10) và hai worker threads. Khi quá tải, executor có thể reject; demo không triển khai mapping riêng cho `TaskRejectedException`. Production phải kiểm tra admission/quota và chỉ trả 202 sau khi nhận việc bền vững.
- `setWaitForTasksToCompleteOnShutdown(true)` cùng `setAwaitTerminationSeconds(5)` cho phép chờ các jobs đã được executor nhận khi bean bị destroy, **không biến chúng thành HTTP requests**. Nó cũng không thay Kubernetes termination budget.
- `SimpleClientHttpRequestFactory` cho connect/read timeout theo transport Java 17. Dùng factory này thay vì mặc định nhằm bảo đảm demo có timeout; production cần kiểm tra proxy/TLS/pool/observability của client implementation.
- `Thread.sleep(...)` chỉ dùng để mô phỏng blocking work trong MVC/async worker của lab. Không nên dùng nó trên Netty event-loop ở WebFlux.
- `WorkSignals` là latch/counter **in-memory chỉ phục vụ test**. Nó không cung cấp job status durable; nếu JVM crash, count biến mất.
- Endpoint `/api/jobs` không auth trong demo nên không phù hợp public production.
- `@Async` method trả `CompletableFuture<Void>` để caller có thể quan sát lỗi qua `whenComplete`, khác `void` async có thể chỉ báo lỗi tới AsyncUncaughtExceptionHandler. Tuy nhiên return 202 không kèm durable job record là **rủi ro mất job**, được cố ý minh họa.

### 7.3. Downstream server chạy trong process khác

Để không gọi lại chính server đang shutdown, dùng JDK `com.sun.net.httpserver.HttpServer` làm mock partner. **`src/main/java/com/example/graceful/DemoPartnerServer.java`:**

```java
package com.example.graceful;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import com.sun.net.httpserver.HttpServer;

public final class DemoPartnerServer {

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 9090), 0);
        ExecutorService threads = Executors.newFixedThreadPool(4);
        server.setExecutor(threads);

        server.createContext("/remote", exchange -> {
            try {
                String query = exchange.getRequestURI().getRawQuery();
                long ms = 400;
                if (query != null && query.startsWith("ms=")) {
                    ms = Long.parseLong(query.substring(3));
                }
                Thread.sleep(Math.max(0, Math.min(ms, 2500)));

                byte[] bytes = "partner-ok".getBytes(
                        StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, bytes.length);
                try (var output = exchange.getResponseBody()) {
                    output.write(bytes);
                }
            } catch (Exception error) {
                exchange.close();
                if (error instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }
            }
        });

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            server.stop(0);
            threads.shutdownNow();
        }));

        server.start();
        System.out.println("Partner running on http://127.0.0.1:9090");
    }
}
```

Đây là **process test riêng**, không phải production HTTP backend:
- Không auth, không HTTPS, không request logging/metrics.
- Input delay được clamp tối đa 2500ms; với malformed `ms`, connection có thể bị đóng.
- `threads` có tối đa bốn workers, không phải load generator.
- Spring Boot app vẫn có thể dừng trong khi downstream còn xử lý request; hai process có shutdown lifecycle riêng.

### 7.4. Cách chạy hai tiến trình

Ở terminal 1:

```bash
gradle partnerRun
```

Output dự kiến:

```text
Partner running on http://127.0.0.1:9090
```

Ở terminal 2:

```bash
gradle bootRun
```

Nếu project đã có Gradle wrapper: `./gradlew partnerRun` và `./gradlew bootRun` trên Linux/macOS; PowerShell dùng `.\gradlew.bat`. JDK 17+ và Gradle tương thích Boot 3.3.13 là điều kiện. Boot app tại `localhost:8080`, partner tại `localhost:9090`.

Thử:

```bash
curl -i "http://localhost:8080/api/slow?ms=500"
curl -i "http://localhost:8080/api/async?ms=500"
curl -i "http://localhost:8080/api/proxy?ms=500"
curl -i -X POST "http://localhost:8080/api/jobs?ms=500"
curl -i "http://localhost:8080/api/jobs/completed"
```

Expected responses, **không phải stdout đã chạy xác minh**:

| Request | Trạng thái/body dự kiến |
|---|---|
| `GET /api/slow` | 200 và `{"result":"slow-done"}` |
| `GET /api/async` | 200 và `{"result":"async-done"}` |
| `GET /api/proxy` | 200 và text `partner-ok` |
| `POST /api/jobs` | 202, thường body trống |
| `GET /api/jobs/completed` | `{"completed":0}` hoặc `{"completed":1}` tùy task đã xong chưa |

**Không coi 202 là bằng chứng task hoàn tất**, và không coi `jobCompleted=1` là bằng chứng dữ liệu được durable ở DB; đây chỉ là counter in-memory lab.

## 8. Integration tests cho in-flight HTTP và @Async job khi context đóng

Để chứng minh **graceful khác việc controller chạy bình thường**, ta khởi động một Spring Boot context với cổng ngẫu nhiên, gửi HTTP request qua JDK `HttpClient.sendAsync`, đợi handler thực sự bắt đầu bằng `CountDownLatch`, rồi **gọi `context.close()` khi request đang chạy**. Nếu budget đủ, request có cơ hội trả về 200 trước khi context đóng.

Không thực hiện kiểu test này trên một `@SpringBootTest` context dùng chung nhiều tests khác, vì một test đóng context sẽ gây lỗi cho test khác. Mỗi test dưới đây tự tạo/dừng một context độc lập.

**`src/test/java/com/example/graceful/MvcShutdownIntegrationTest.java`:**

```java
package com.example.graceful;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MvcShutdownIntegrationTest {

    private ConfigurableApplicationContext start() {
        return new SpringApplicationBuilder(MvcShutdownApplication.class)
                .properties(
                        "server.port=0",
                        "server.shutdown=graceful",
                        "spring.lifecycle.timeout-per-shutdown-phase=5s",
                        "demo.downstream.base-url=http://127.0.0.1:9090")
                .run();
    }

    private int port(ConfigurableApplicationContext ctx) {
        return ctx.getBean(
                ServletWebServerApplicationContext.class)
                .getWebServer().getPort();
    }

    private HttpRequest get(int port, String path) {
        return HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .GET()
                .build();
    }

    @Test
    void runningHttpRequestCanFinishDuringGracefulClose()
            throws Exception {
        ConfigurableApplicationContext context = start();
        try {
            int port = port(context);
            WorkSignals signals = context.getBean(WorkSignals.class);
            HttpClient client = HttpClient.newHttpClient();

            CompletableFuture<HttpResponse<String>> request =
                    client.sendAsync(
                            get(port, "/api/slow?ms=450"),
                            HttpResponse.BodyHandlers.ofString());

            // Bảo đảm request thật sự vào controller trước shutdown.
            assertTrue(signals.requestEntered.await(
                    3, TimeUnit.SECONDS));

            context.close(); // Chờ graceful web phase.

            HttpResponse<String> response = request.get(
                    3, TimeUnit.SECONDS);
            assertEquals(200, response.statusCode());
            assertTrue(response.body().contains("slow-done"));
        } finally {
            if (context.isActive()) {
                context.close();
            }
        }
    }

    @Test
    void acceptedBackgroundJobNeedsItsOwnExecutorDrain()
            throws Exception {
        ConfigurableApplicationContext context = start();
        try {
            int port = port(context);
            WorkSignals signals = context.getBean(WorkSignals.class);
            HttpClient client = HttpClient.newHttpClient();

            HttpRequest post = HttpRequest.newBuilder(
                    URI.create(
                            "http://127.0.0.1:" + port
                                    + "/api/jobs?ms=450"))
                    .POST(HttpRequest.BodyPublishers.noBody())
                    .build();

            HttpResponse<String> response = client.send(
                    post, HttpResponse.BodyHandlers.ofString());

            assertEquals(202, response.statusCode());
            assertTrue(signals.jobStarted.await(
                    3, TimeUnit.SECONDS));

            // HTTP 202 đã xong; đây là thời gian CHỜ của jobExecutor.
            context.close();

            assertEquals(1, signals.jobsCompleted.get());
        } finally {
            if (context.isActive()) {
                context.close();
            }
        }
    }
}
```

Chạy:

```bash
gradle test
```

**Kỳ vọng:** hai tests pass với cấu hình đúng và máy test không quá tải. Đây là **kiểm thử được thiết kế và rà soát tĩnh**, **chưa thực thi Gradle**. Các bài test có ý nghĩa vì:
- Gửi request qua network của Tomcat trên cổng ngẫu nhiên, không gọi thẳng method controller.
- Latch bảo đảm request/job **đã bắt đầu trước** khi gọi context.close; giảm race khiến test vô tình kiểm tra request chưa chạy.
- HTTP test chứng minh server grace có thể đợi in-flight request ngắn.
- Background test chứng minh HTTP 202 đã kết thúc nhưng executor **được cấu hình chờ riêng** vẫn có thể hoàn tất job.
- Cả hai không chứng minh liệu process sẽ sống lâu hơn Kubernetes grace budget hay task sẽ sống sau `SIGKILL`. Cần test deployment thực.

**Không kiểm thử cứng nhắc rằng request mới khi draining phải trả đúng 503.** Với Tomcat Boot 3.3, connection mới có thể bị từ chối tại network layer, JDK HttpClient nhận IOException/ConnectException và request không tới controller.

### 8.1. Kiểm thử lời gọi downstream khi đang dừng

Trong một **test riêng**, chạy partner mock HTTP server trên cổng ngẫu nhiên và có latch báo nó đã nhận request, sau đó gọi `GET /api/proxy` của Boot app, đợi partner nhận rồi close app. Khi partner phản hồi trong client timeout và graceful budget, HTTP client ban đầu có thể nhận `partner-ok`.

Một test đầy đủ cần:
1. Khởi động `HttpServer` trên port 0 với riêng `ExecutorService`.
2. Truyền `demo.downstream.base-url=http://127.0.0.1:<actual-port>` cho `SpringApplicationBuilder`.
3. Mock partner countDown latch **sau khi nhận request**, sleep khoảng 350ms và trả `partner-ok`.
4. Gửi HTTP `/api/proxy?ms=350` bằng `sendAsync`.
5. Chờ mock partner latch, sau đó `context.close()`.
6. Assert HTTP 200/body và ngừng partner server/executor trong `finally`.

Không đặt mock downstream ở **cùng Boot web server đang shutdown**, vì khi chính app ngừng nhận request mới, outbound RestClient tới `localhost:8080` có thể bị từ chối ngay dù outer request vẫn in-flight. Mô hình mock **process/server riêng** mới mô phỏng downstream hoạt động độc lập.

## 9. Lỗi thường gặp với @Async và executor lúc shutdown

### 9.1. `@Async` không đồng nghĩa “job được đảm bảo chạy”

`@Async` thực chất chuyển lời gọi method qua proxy và submit task tới một `Executor`. Nó không ghi event/transaction vào broker. Các nguy cơ:
- Queue in-memory biến mất khi JVM crash.
- Một task được nhận trước khi shutdown nhưng chưa chạy có thể bị hủy tùy executor policy.
- Task trong lúc shutdown có thể phụ thuộc DB pool đã đóng.
- Task có thể bị interrupt; blocking I/O không phải lúc nào cũng dừng theo interrupt.
- Task timeout không tự rollback giao dịch đã commit.
- Exception của `@Async void` thường không đi về HTTP caller.
- Self-invocation trong cùng bean có thể không qua proxy, dẫn tới chạy đồng bộ.

Một `@Bean ThreadPoolTaskExecutor` cho chính ứng dụng nên cấu hình:
- `corePoolSize`, `maxPoolSize`, `queueCapacity` hữu hạn.
- Rejection policy và HTTP response khi admission fail.
- `setWaitForTasksToCompleteOnShutdown(true)` **nếu** muốn chờ các tasks đã nhận.
- `setAwaitTerminationSeconds(...)` đủ cho task ngắn nhưng không vượt Pod budget.
- Không nhận job mới khi draining (application admission flag/queue gating).
- Xử lý terminal success/error và kết quả bền vững.

**Lưu ý Spring Framework 6.1:** `setWaitForTasksToCompleteOnShutdown(true)` có semantics là **late shutdown** của executor, làm tasks đang chạy/queue tiếp tục trong khi Spring context đang đóng. Điều này có thể xung đột nếu chúng cần DB/client bean bị destroy cùng lúc. Tùy trường hợp, phối hợp early drain qua `SmartLifecycle` có phase/dependencies rõ ràng hoặc chuyển job sang durable broker là an toàn hơn. Không coi await-termination “fix mọi ordering”.

### 9.2. Boot auto-configured task execution properties

Với builder/executor do Boot 3.3 auto-configure, có các property:

```properties
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=100

spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=8s

spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=8s
```

Những property này **không nhất thiết áp cho bean `jobExecutor` tự khai báo bằng `new ThreadPoolTaskExecutor()`** như ví dụ; vì bean custom có settings riêng. Đừng đặt `spring.task.execution.shutdown.await-termination=true` rồi mặc định mọi `Executors.newSingleThreadExecutor()` trong code được Boot quản lý. Bare JDK executors, `CompletableFuture.supplyAsync(...)` dùng common pool, timers của SDK hoặc threads tự tạo **nằm ngoài shutdown policy** nếu không được lifecycle quản lý.

**Boot 3.3 có thêm Java 21 virtual threads option** khi bật `spring.threads.virtual.enabled=true`; nó thay đổi các yếu tố concurrency/executor, nhưng bài minh họa Java 17, không dựa vào virtual threads. Không dùng “virtual thread” như giải pháp thay mọi timeout/durability.

### 9.3. Nếu tác vụ bắt buộc hoàn tất

Ưu tiên pattern:
1. Request xác thực/validate và tạo **idempotency key / job ID**.
2. Ghi trạng thái `PENDING` trong DB cùng transaction/outbox khi phù hợp.
3. Trả 202 **chỉ sau khi durable commit**.
4. Worker lấy job theo lease, xử lý và ghi `DONE` hoặc `FAILED_RETRYABLE`.
5. Khi shutdown, worker ngừng nhận job mới và cố hoàn tất phần đang chạy trong hạn.
6. Nếu bị kill, lease hết hạn → worker khác retry với idempotent side effect.

Executor wait đơn lẻ chỉ là tối ưu để giảm số job cần retry, không thay thế durability.

## 10. Downstream call: timeout, cancellation, retry và “đã xử lý nhưng mất response”

Một downstream timeout có ít nhất hai khả năng:
- Server B **chưa** xử lý request, caller A timeout.
- Server B **đã commit** thay đổi (ví dụ thanh toán), nhưng response bị mất hoặc A bị shutdown trước khi nhận/ghi response.

Vì vậy:

```text
A POST /payments ─► B
       │              └── DB COMMIT ✓
       │
  A mất connection/timeout
       │
  Caller retry POST?
       └── Nếu không có idempotency key → có thể ghi tiền 2 lần
```

**Graceful shutdown không cung cấp exactly-once** giữa client, A, B và database. Cần:
- Idempotency key cho mọi operation có side effect.
- Unique constraint/transactional dedup hoặc outbox/inbox.
- Retry policy có max attempts, backoff và **remaining deadline**.
- Phân biệt retryable network failure với business 4xx.
- Response reconciliation/status query cho “unknown outcome”.
- Client timeout nhỏ hơn request/grace budget phù hợp.
- Không hủy/đóng downstream client pool trước khi caller in-flight hoàn tất.

### 10.1. Connect timeout và read/response timeout khác nhau

`RestClient` và `RestTemplate` là blocking APIs. Cài `connect timeout` (kết nối) và `read timeout` (đợi đọc). Các HTTP client implementations có semantics khác, và timeout tổng business có thể cần deadline riêng. `WebClient` là reactive, có thể cấu hình Reactor Netty `responseTimeout(...)` và/hoặc `Mono.timeout(...)`. Hai cơ chế không đồng nghĩa “request đã được upstream server hủy thành công”.

Ví dụ ở MVC đã dùng `SimpleClientHttpRequestFactory`:
- Connect timeout 1s.
- Read timeout 3s.
- Graceful server phase 10s.
- Partner demo delay ≤2,5s.

Một kết nối đã được thiết lập có thể vẫn mất nhiều thời gian tổng do nhiều reads, retries hoặc business orchestration; **đừng gọi timeout socket là end-to-end SLA**.

### 10.2. Client disconnect và server-side work

Khi browser đóng tab lúc đang đợi:
- MVC blocking controller có thể **chỉ phát hiện disconnect lúc đọc/ghi socket**, chứ không phải tự động interrupt ngay mọi DB/HTTP call.
- Spring MVC `DeferredResult.onTimeout`, `onError`, `onCompletion` hữu ích cho cleanup, nhưng không đảm bảo hủy được tác vụ blocking nằm ngoài phạm vi.
- Trong WebFlux, connection cancellation có thể lan tới reactive publishers như WebClient, nhưng phụ thuộc subscription topology/operator/driver.
- Một downstream đã nhận request có thể vẫn xử lý dù caller A cancel; **cancellation là best effort**.
- Nếu command có side effect, phải có idempotency/reconciliation, không coi cancel là rollback.

**Không gọi `subscribe()` rồi bỏ kết quả trong một reactive HTTP handler**: làm vậy tách công việc khỏi request, khiến graceful/timeout/cancel không còn quản lý nó.

## 11. WebFlux: publisher còn sống khi request đang chạy

Trong Spring WebFlux, handler trả `Mono<T>`/`Flux<T>`. Subscription được WebFlux server quản lý, và việc stream hoàn tất/error/cancel quyết định lifecycle HTTP response.

```java
// Mảnh code trong WebFlux @RestController:
@GetMapping("/api/slow")
Mono<String> slow() {
    return Mono.delay(Duration.ofMillis(500))
            .map(ignored -> "reactive-done");
}
```

Đây là **mảnh code minh họa**; import `Mono`, `Duration` và WebFlux annotations. Không dùng `Thread.sleep(500)` trên Reactor Netty event-loop: một blocking call có thể làm chậm nhiều requests trên cùng event-loop.

### 11.1. WebClient gắn vào cùng reactive chain

```java
// Mảnh code trong service đã inject WebClient:
Mono<String> reply = client.get()
        .uri("/remote")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(3))
        .doFinally(signal ->
                log.debug("Downstream finished: {}", signal));

return reply;
```

`doFinally` có thể thấy `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL` ở vị trí operator. **Nó không chứng minh bên downstream chưa xử lý request hoặc đã rollback.** Spring WebFlux có thể cancel client I/O/subscription nhưng downstream có thể tiếp tục theo implementation.

### 11.2. Bẫy `Mono.when` với streams không kết thúc

Nếu endpoint SSE/WebSocket trả một `Flux.interval(...)` vô hạn, “in-flight” có thể giữ kết nối hàng giờ. Khi nhận shutdown, server **không thể chờ vô hạn** nếu grace có budget. Đối với stream lâu dài:
- Đặt max connection/session age hoặc heartbeat/idle timeout.
- Có tín hiệu drain/close do app phát để clients reconnect sang instance mới.
- Chọn policy complete stream/close WebSocket với code hợp lý.
- Ưu tiên cho clients reconnect với jitter, resume cursor/sequence khi business cần.
- Không dùng một `Sinks.Many` unbounded cho mỗi client mà không kiểm tra memory.
- Đảm bảo buffer/data resource release khi terminal/cancel.
- Với WebSocket và SSE, xem rõ behavior của embedded server phiên bản cụ thể thay vì mặc định mọi kết nối phải hoàn tất trước grace.

## 12. Project B: WebFlux reactive slow request và downstream WebClient

Project độc lập **Spring Boot 3.3.13, Java 17+**, không thêm `spring-boot-starter-web` để server thật là Reactor Netty. Có:
- `GET /api/slow?ms=...` sử dụng `Mono.delay`, quan sát subscribe/termination/cancel.
- `GET /api/proxy?ms=...` gọi downstream riêng bằng `WebClient`, áp timeout hữu hạn.
- Actuator readiness/metrics để kiểm tra quy trình drain.

**Cấu trúc:**

```text
graceful-webflux-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/reactivegraceful/
    │   │   └── ReactiveShutdownApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/reactivegraceful/
            └── ReactiveShutdownIntegrationTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8081
spring.application.name=graceful-webflux-demo
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=10s
demo.downstream.base-url=http://127.0.0.1:9090

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info,metrics
```

**`src/main/java/com/example/reactivegraceful/ReactiveShutdownApplication.java`:**

```java
package com.example.reactivegraceful;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@SpringBootApplication
public class ReactiveShutdownApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveShutdownApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class ReactiveClientConfiguration {

    @Bean
    WebClient partnerWebClient(
            WebClient.Builder builder,
            @Value("${demo.downstream.base-url}") String baseUrl) {
        return builder.baseUrl(baseUrl).build();
    }
}

@Component
class ReactiveSignals {
    final CountDownLatch requestSubscribed = new CountDownLatch(1);
    final AtomicInteger cancelled = new AtomicInteger();
}

@RestController
class ReactiveWorkController {

    private static final Logger log =
            LoggerFactory.getLogger(ReactiveWorkController.class);

    private final WebClient partner;
    private final ReactiveSignals signals;

    ReactiveWorkController(WebClient partner, ReactiveSignals signals) {
        this.partner = partner;
        this.signals = signals;
    }

    @GetMapping("/api/slow")
    Mono<String> slow(
            @RequestParam(defaultValue = "400") long ms) {
        long bounded = Math.max(0, Math.min(ms, 2500));

        return Mono.delay(Duration.ofMillis(bounded))
                .map(ignored -> "reactive-done")
                .doOnSubscribe(subscription ->
                        signals.requestSubscribed.countDown())
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        signals.cancelled.incrementAndGet();
                    }
                    log.info("Reactive slow finished: {}", signal);
                });
    }

    @GetMapping("/api/proxy")
    Mono<String> proxy(
            @RequestParam(defaultValue = "400") long ms) {
        long bounded = Math.max(0, Math.min(ms, 2500));

        return partner.get()
                .uri("/remote?ms={ms}", bounded)
                .retrieve()
                .bodyToMono(String.class)
                .timeout(Duration.ofSeconds(3))
                .doFinally(signal ->
                        log.info("Reactive downstream finished: {}",
                                signal));
    }
}
```

**Giải thích chính:**
- `Mono.delay` lên lịch timer non-blocking, không giữ một Servlet worker thread trong 400ms.
- `doOnSubscribe` chỉ đếm khi reactive chain được subscribe, thuận tiện kiểm tra in-flight thực.
- `doFinally` có thể ghi `ON_COMPLETE`, `ON_ERROR`, `CANCEL`; không phải một transaction log.
- `WebClient` tạo bằng builder do Boot cung cấp; đối tác HTTP ở process riêng, không tự gọi lại port WebFlux 8081 trong lúc dừng.
- `timeout(Duration.ofSeconds(3))` là deadline của Publisher, **không bảo đảm remote server ngừng xử lý** nếu nó đã nhận request.
- Mã demo chỉ có một top-level `public class` trong file; các bean/config classes package-private và được Boot scan.

### 12.1. Chạy WebFlux

Khởi động `DemoPartnerServer` của project MVC trong terminal riêng (hoặc một mock HTTP server tương đương trên port 9090), rồi từ thư mục project WebFlux:

```bash
gradle bootRun
curl -i "http://localhost:8081/api/slow?ms=400"
curl -i "http://localhost:8081/api/proxy?ms=400"
```

Kỳ vọng `/api/slow` trả HTTP 200 với body `reactive-done`; `/api/proxy` trả `partner-ok` nếu partner đang chạy. Mọi kết quả phụ thuộc network/timeouts, **không phải output đã chạy trong môi trường này**.

### 12.2. Kiểm thử in-flight WebFlux khi context đóng

**`src/test/java/com/example/reactivegraceful/ReactiveShutdownIntegrationTest.java`:**

```java
package com.example.reactivegraceful;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveShutdownIntegrationTest {

    @Test
    void reactiveRequestCanCompleteDuringGracefulClose()
            throws Exception {
        ConfigurableApplicationContext context =
                new SpringApplicationBuilder(
                        ReactiveShutdownApplication.class)
                    .properties(
                            "server.port=0",
                            "server.shutdown=graceful",
                            "spring.lifecycle.timeout-per-shutdown-phase=5s",
                            "demo.downstream.base-url=http://127.0.0.1:9090")
                    .run();

        try {
            int port = context.getBean(
                    ReactiveWebServerApplicationContext.class)
                    .getWebServer().getPort();

            ReactiveSignals signals = context.getBean(
                    ReactiveSignals.class);
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest request = HttpRequest.newBuilder(
                    URI.create(
                            "http://127.0.0.1:" + port
                                    + "/api/slow?ms=450"))
                    .GET()
                    .build();

            CompletableFuture<HttpResponse<String>> inFlight =
                    client.sendAsync(
                            request,
                            HttpResponse.BodyHandlers.ofString());

            assertTrue(signals.requestSubscribed.await(
                    3, TimeUnit.SECONDS));

            context.close();

            HttpResponse<String> response = inFlight.get(
                    3, TimeUnit.SECONDS);
            assertEquals(200, response.statusCode());
            assertEquals("reactive-done", response.body());
            assertEquals(0, signals.cancelled.get());
        } finally {
            if (context.isActive()) {
                context.close();
            }
        }
    }
}
```

**Kỳ vọng:** test pass nếu Reactor Netty/Boot giữ request ngắn đang chạy tới completion. Nó kiểm chứng server có thể drain HTTP request trong 450ms trong budget 5s, không phải bảo đảm tất cả stream vô hạn hay downstream operations hoàn tất. Đây là code **được rà soát tĩnh, chưa chạy Gradle**.

**Lưu ý về shutdown racing:** đôi khi HTTP client nhận response nhưng Netty close event tới trong cùng cửa sổ. Test sử dụng latch để biết subscription đã bắt đầu; không dùng sleep tùy tiện trước context.close. Nếu còn flakiness ở CI, hãy thu thập logs/network events và chỉnh deadline/test synchronisation, không sửa business code theo một lần lỗi mạng.

## 13. Cancellation trong WebFlux và lời gọi tới downstream

Giả sử một WebFlux controller thực hiện:
```java
return webClient.get()
        .uri("/remote")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(2))
        .doFinally(signal -> log.info("Signal: {}", signal));
```

Nếu HTTP client gọi vào Spring Boot đóng connection, phía server **có thể** phát `cancel` vào reactive subscription. Reactor Netty WebClient có thể ngừng đọc response hoặc đóng connection. Nhưng:
- Downstream B có thể đang xử lý và không biết caller không còn muốn kết quả.
- Một DB driver có thể đã commit.
- Một `doOnCancel` chạy không thay cho close file/database transaction.
- Một `onErrorResume` có thể biến timeout thành response fallback, khiến client nhận 200 thay vì 504 theo policy.
- `retryWhen` có thể gửi lại request có side effect, gây duplicate.
- Synchronous adapter hoặc `Mono.fromCallable(...)` trên boundedElastic có thể không cancel thread/SDK tức thì.
- `WebClient` HTTP response streaming cần release `DataBuffer` khi code tự nhận/relay; connection close không thay cho quản lý ownership ngoài pipeline.

**Không suy từ tín hiệu CANCEL rằng downstream đã rollback**. Trong observability, phân loại `ON_COMPLETE`, `ON_ERROR` và `CANCEL` riêng, gắn correlation/tracing IDs với thông tin được phép log.

Nếu phải gọi B rồi ghi DB, cố gắng giữ request trong **một reactive chain** với timeout, retries và transaction boundaries rõ ràng. Không `subscribe()` thủ công ở giữa rồi return `Mono.just("accepted")` trừ khi đó thật sự là job workflow có durable handoff.

## 14. Dừng background jobs trước hay sau HTTP listener?

Một quy trình production thường có hai mục tiêu:
1. **Không nhận việc mới** sau khi bắt đầu drain.
2. **Hoàn tất việc đã nhận** đến một mốc deadline, rồi dừng an toàn/ghi trạng thái retry.

Không phải lúc nào chờ toàn bộ jobs mới đóng HTTP server cũng đúng:
- Jobs có thể tiếp tục tiêu tốn DB/HTTP client resources.
- Nếu executor được destroy **sau** DataSource, task còn chạy có thể gặp `Connection pool is closed`.
- Nếu đóng downstream client quá sớm, HTTP requests đang chờ sẽ bị lỗi.
- Nếu tiếp tục nhận jobs khi service đã unready, queue lại tăng.
- Nếu `@PreDestroy` block vô hạn, deployment sẽ SIGKILL.

Thiết kế tốt:
- **Admission gate**: khi readiness chuyển `REFUSING_TRAFFIC`, từ chối new job requests/queue polling mới.
- **Drain deadline**: ghi thời điểm kết thúc còn lại và cho tasks có thể hoàn tất trong budget chạy nốt.
- **Dependency lifetime**: giữ DB/client connection pool sống tới khi những tasks thật sự cần chúng xong.
- **Final state**: jobs chưa xong được persist/requeue/retry, không mất im lặng.
- **Lifecycle coordination**: dùng `SmartLifecycle` với phase/dependencies hợp lý hoặc job manager riêng. Không copy một thứ tự `@PreDestroy` tuỳ tiện mà tưởng Spring sẽ tự hiểu sự phụ thuộc giữa task và resource.
- **Force stop** sau budget: cancel/interrupt khi được hỗ trợ, log/counter unfinished work và cho hệ thống phục hồi.

### 14.1. SmartLifecycle: dùng khi cần điều phối đặc biệt

`SmartLifecycle` có `isRunning()`, `start()`, `stop(Runnable callback)`, `getPhase()`. Khi shutdown, Spring dừng theo thứ tự phase **từ cao xuống thấp** (cùng phase có thể được stop theo nhóm). Bạn có thể dùng một component để ngừng **job intake** trước, đợi in-flight jobs ngắn, rồi gọi callback; phase/bean dependencies cần được xác định cẩn thận để không vượt tổng shutdown time.

**Đoạn khung minh họa, không phải implementation đầy đủ**:

```java
// Trong class implements SmartLifecycle:
@Override
public void stop(Runnable callback) {
    acceptingNewJobs.set(false);

    // Phải gọi callback sau khi drain hoặc deadline.
    // Không giữ callback vô hạn khi queue có job treo.
    stopListeningAndWaitWithinBudget()
            .whenComplete((unused, error) -> callback.run());
}
```

Các biến/method `acceptingNewJobs`, `stopListeningAndWaitWithinBudget()` phải được triển khai. **Không copy mã giả như bean runnable**. Không gọi callback sớm khi jobs còn phụ thuộc resource cần sống; không bao giờ bỏ callback khiến phase chỉ xong khi timeout.

## 15. Kubernetes: readiness, preStop và SIGTERM phải khớp nhau

Kubernetes Pod termination là **quy trình của orchestrator**, không phải Spring Boot property:

1. Pod được đánh dấu terminating; EndpointSlice updates khiến endpoint ngừng `ready` để dần loại khỏi routing.
2. Kubelet chạy `preStop` hook nếu có (và termination grace không bằng 0).
3. **Grace period đã đếm từ lúc termination bắt đầu**, không chờ preStop xong mới đếm.
4. Sau preStop, runtime gửi SIGTERM tới PID 1 Java.
5. Spring Boot bắt đầu graceful shutdown/đóng context.
6. Nếu vượt `terminationGracePeriodSeconds`, container bị SIGKILL; Java cleanup không chạy.

### 15.1. Cấu hình ví dụ

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: graceful-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: graceful-api
  template:
    metadata:
      labels:
        app: graceful-api
    spec:
      terminationGracePeriodSeconds: 40
      containers:
        - name: api
          image: example.registry/graceful-api:1.0.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 2
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
```

Đây là **ví dụ Kubernetes manifest**, image chỉ là tên minh họa và không đủ production: còn cần namespace, securityContext/non-root, resource requests/limits, liveness/startup probes, secret config, PDB, affinity, actual image, HPA và network policy theo hệ thống. `sleep 5` trong preStop chỉ giúp tạo cửa sổ để endpoint propagation ở một số hạ tầng; không làm Spring Boot graceful bắt đầu sớm hơn vì **SIGTERM đến sau preStop**.

**Đọc budget:**
- 40s total Pod grace.
- preStop 5s sử dụng **ngay 5s của 40s**.
- Spring context close và toàn bộ web/executor phases phải còn trong khoảng còn lại, cộng margin cho vận hành.
- Nếu preStop treo 39s, chỉ còn gần 1s cho Java graceful; không thể chữa bằng `timeout-per-shutdown-phase=30s`.
- Nếu ingress/LB propagation chậm, có thể còn request mới tới backend đang dừng; health check/routing/drain cần thiết kế và đo.

### 15.2. Readiness của Spring Boot

Với Actuator và probes enabled, Boot quản lý `ApplicationAvailability` với:
- `ReadinessState.ACCEPTING_TRAFFIC` khi app đã sẵn sàng.
- `ReadinessState.REFUSING_TRAFFIC` trong quá trình shutdown.
- `LivenessState` dùng để nhận diện process bị broken (không gắn mọi lỗi downstream với liveness).

Các endpoints thường dùng:
- `/actuator/health/liveness`.
- `/actuator/health/readiness`.

**Đừng dùng một health check tới DB chung làm liveness probe.** DB down có thể khiến mọi pods restart tạo cascading failure. Readiness phụ thuộc business dependency cần có policy rõ, không phải checklist cứng.

**Cảnh báo:** nếu Actuator management port tách riêng khỏi application port, readiness probe có thể hoạt động dù main server không nhận requests. Boot docs khuyến nghị cân nhắc `management.endpoint.health.probes.add-additional-paths=true` để có `/readyz` và `/livez` trên main server port. Đừng công khai Actuator endpoints nhạy cảm khi expose probes.

## 16. Worker queue và scheduled tasks trong shutdown

**Không gộp @Async và message listener vào HTTP drain.** Ví dụ consumer Kafka nhận message trước SIGTERM, đang xử lý:
- Nếu auto-commit offset trước khi xử lý xong, job có thể mất.
- Nếu commit sau xử lý và pod bị kill trước commit, message có thể redeliver.
- Nếu side effect đã commit nhưng ACK chưa gửi, retry có thể tạo duplicate.
- Nếu đóng DataSource trước listener, xử lý đang chạy sẽ lỗi.

Giải pháp phụ thuộc broker:
- Stop polling/receiving mới khi drain.
- Finish in-flight handler trong bounded deadline.
- ACK/commit chỉ khi business work durable.
- Thiết kế xử lý **idempotent** để chịu redelivery.
- Lease/visibility timeout đủ cho retry, có dead-letter policy.
- Đo số in-flight jobs/consumer lag và unfinished count.

`spring.task.scheduling.shutdown.await-termination=true` có thể giúp scheduler do Boot quản lý chờ running tasks, nhưng **không nói gì** về Kafka listener, Rabbit listener, Quartz scheduler custom hoặc một `ExecutorService` tự `new`. Mỗi subsystem cần lifecycle policy riêng.

## 17. HTTP request drain không giải quyết giao dịch phân tán

Một request có thể đồng thời:
1. Ghi database A.
2. Gửi lệnh tới downstream B.
3. B commit vào database B.
4. Caller A mất connection vì shutdown.
5. Client retry.

Không có Spring graceful property nào biến ba hệ thống thành một transaction exactly-once. Cần quyết định:
- Synchronous idempotent API với request IDs.
- Outbox (ghi business state và event cùng local transaction).
- Inbox/dedup ở consumer.
- Saga/compensation nếu multi-step.
- Query trạng thái theo business key sau “unknown outcome”.
- Tolerate duplicate/out-of-order event khi retry hoặc reconnect.

### 17.1. Ví dụ sai và đúng ở cấp ý tưởng

**Sai:**

```text
client POST /pay
  → A gọi B
  → B commit
  → A bị kill trước response
  → client retry cùng payment mà không có idempotency
  → B commit lần 2
```

**Hướng thiết kế đúng hơn:**

```text
client POST /pay {idempotencyKey=K}
  → A validate + gửi K tới B
  → B insert unique(K) hoặc trả kết quả đã lưu nếu K tồn tại
  → client timeout/retry cùng K
  → B trả cùng business outcome thay vì double charge
```

Những pseudo flow trên minh họa semantics; production cần transaction/unique constraint/correlation/policy giữ idempotency records đủ lâu, không chỉ chèn header tùy ý rồi cho rằng đã có dedup.

## 18. Biết dừng lúc nào: audit và observability

Không nên chỉ log “Application shutdown complete”. Hãy theo dõi:

| Nhóm | Metrics/logs |
|---|---|
| HTTP in-flight | Active HTTP requests, request duration, p95/p99 latency, 5xx during drain |
| Web server | Server shutdown start/end, time spent in grace phase, rejected new connections |
| Async executors | Pool active count, queued tasks, rejected submissions, task completion/error/cancel |
| Downstream | Connect/read timeout, 4xx/5xx, retry count, in-flight calls, client pool active |
| Reactive | `onComplete` / `onError` / `cancel`, active subscriptions, buffered messages |
| Job durability | Pending/running/retryable jobs, leases not renewed, duplicate handling |
| Kubernetes | Pod termination reason, SIGTERM→exit duration, termination grace hit/SIGKILL |
| External traffic | LB endpoint deregistration delay, ingress 502/503/reset, client retries |
| Data safety | Orphan temp files, incomplete uploads, unknown transaction outcomes |

Đặt trace/correlation ID trên request và downstream call theo instrumentation; đừng log access token, session cookies, raw request bodies hoặc PII. Một request reset/EOF khi pod terminating không nhất thiết là Java bug; phân biệt network drain vs real exception.

Nếu metrics `http.server.requests` chỉ đo completed requests, các requests bị **SIGKILL trước completion** có thể không được ghi đầy đủ. Kết hợp client-side/proxy errors và process termination counters; nếu không, dashboard server có thể trông tốt trong khi client nhận nhiều lỗi.

## 19. Test matrix trước khi rollout production

| Kịch bản | Điều cần xác minh |
|---|---|
| GET 400ms bắt đầu trước SIGTERM, grace 5s | Client nhận response, app thoát trong budget |
| GET 15s, grace 5s | Client có thể lỗi/cancel; process vẫn dừng, không treo vô hạn |
| Servlet `Callable` đang chạy | Async dispatch/response hoàn tất khi trong hạn |
| `DeferredResult` không bao giờ complete | Timeout/cleanup không làm shutdown vượt grace |
| `@Async` HTTP trả 202 sớm | Job có durable record hoặc bounded executor drain |
| Queue executor đầy | Task bị reject có chủ đích; không nói 202 nếu không nhận |
| Downstream B 400ms, A nhận SIGTERM | A chờ B và trả response nếu budget đủ |
| Downstream B treo 30s | A có timeout ngắn, không chờ vượt Pod budget |
| WebFlux `Mono.delay` 450ms | Request có thể hoàn tất lúc graceful |
| WebFlux client ngắt giữa downstream call | Cancel/cleanup được quan sát; không giả rollback B |
| SSE/WebSocket/Flux vô hạn | Có policy close/drain; không đợi vô hạn |
| Multipart upload đang streaming | Temp/staging cleanup nếu cancel, không commit partial artifact |
| Kubernetes preStop 5s + grace 40s | SIGTERM còn đủ thời gian, không bị kill trước |
| Rolling update 2 replicas | Readiness/endpoint propagation, không có downtime bất ngờ |
| Pod kill -9 / node crash | Durable job retry + idempotency, không dựa @PreDestroy |
| HTTP keep-alive + HTTP/2 multiplex | Request rejection/connection drain theo runtime/proxy |
| Request A→B commit rồi A mất response | Client retry không tạo side effect trùng |
| Slow client upload/download | Bound queues/timeouts, không giữ drain vô hạn |
| DB pool đóng sớm | Task/job đang chạy không dùng resource đã bị dispose |
| Actuator readiness tách management port | Probe phản ánh main server, không false healthy |

Test graceful bằng **HTTP client thực** và SIGTERM trong container, không chỉ `MockMvc`. `MockMvc` không thử Servlet container connection drain hoặc PID1/signal. Test WebFlux qua actual Reactor Netty server, không chỉ `WebTestClient.bindToController(...)`.

**Phân biệt kiểm chứng:** integration tests ở mục 8/12 đóng Spring context có kiểm soát, chứng minh Spring lifecycle trong JVM. Chúng **không thay thế** test kubelet/preStop/SIGKILL/ingress ở staging.

## 20. Các lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Khi deploy, request đang chạy bị reset | Chưa bật graceful Boot 3.3, Pod SIGKILL sớm, proxy/LB drain chưa đúng | Kiểm tra `server.shutdown`, grace period, termination logs |
| Shutdown phase 10s nhưng Pod chết sau 5s | Orchestrator grace hoặc preStop dùng hết budget | Đo timeline từ Pod deletion, tăng phù hợp và giảm preStop |
| HTTP 202 trả rồi job mất | Task @Async in-memory không durable | Queue/DB job record trước ACK, idempotency |
| MVC Callable không xong sau drain | Async timeout, executor quá tải, task blocked | Cấu hình bounded executor và timeout |
| @Async method không chạy thật | Self-invocation/bỏ `@EnableAsync` hoặc sai executor | Gọi qua bean proxy, kiểm tra thread names |
| Custom executor không chờ | Chỉ đặt `spring.task.execution.shutdown.*` cho auto executor | Cấu hình trực tiếp bean custom hoặc lifecycle riêng |
| Executor chờ, nhưng DB pool đã đóng | Teardown ordering/dependencies không đúng | SmartLifecycle/phases/bean lifetime, durable handoff |
| Trong lúc shutdown vẫn có new jobs | Admission gate chưa đóng hoặc client vào qua stale LB route | Refuse new work, readiness/endpoint propagation |
| Downstream B trả sau grace | HTTP client timeout và retry budget lớn hơn grace | Bound connect/read/overall deadline và thử failure |
| A mất response sau khi B commit | Network/Pod termination giữa commit và response | Idempotency/reconciliation, không retry blind |
| WebFlux bị chặn khi shutdown | `Thread.sleep`/JDBC blocking trên Netty event-loop | Dùng async I/O hoặc boundedElastic có quota |
| `Mono` dùng `subscribe()` rồi response kết thúc | Task detached khỏi request lifecycle | Return/compose Publisher hoặc durable queue |
| WebSocket/SSE giữ pod mãi | Stream vô hạn, thiếu connection max-age/drain policy | Close/reconnect, giới hạn stream và grace |
| JVM không nhận SIGTERM | Shell wrapper làm PID1 và không forward signal | Docker exec-form ENTRYPOINT |
| Debug trong IDE không test được | IDE terminate process thẳng | Test JVM/container SIGTERM |
| Actuator readiness vẫn 200 trong preStop | Spring chưa nhận SIGTERM, vẫn RUNNING | Endpoint routing drain/preStop admission gate |
| Metrics có 5xx ít nhưng client thấy reset nhiều | Requests bị chết trước server observation completion | Xem proxy/client metrics, termination events |
| Scheduled tasks bị hủy bất ngờ | Scheduler có shutdown policy riêng | `spring.task.scheduling.shutdown.*` và durable jobs |
| Retry HTTP POST gây double effects | Không idempotent, ambiguous outcome | Key + dedup/transaction/broker |
| Jobs đợi mãi khiến rollout kẹt | Unbounded queue/deadline, awaitTermination quá dài | Bounded concurrency và stop budget |
| App không exit dù Tomcat shutdown xong | Non-daemon custom ExecutorService/thread còn sống | Đăng ký bean lifecycle, shutdown/awaitTermination |
| Cleanup không chạy khi node crash | SIGKILL/power loss bỏ qua hooks | Durable lease/reaper/idempotency |

## 21. Checklist thiết kế shutdown có kiểm soát

- [ ] Bật rõ `server.shutdown=graceful` khi dùng Spring Boot 3.3.
- [ ] Đặt `spring.lifecycle.timeout-per-shutdown-phase` dựa vào p99 request duration và total Pod budget.
- [ ] Xác định request đồng bộ, Servlet async, reactive và background tasks **thuộc lifecycle nào**.
- [ ] Không đồng nhất HTTP 202 với job được lưu bền/đã hoàn tất.
- [ ] Dùng bounded `TaskExecutor`, xác định admission/reject và await-termination riêng.
- [ ] Với job quan trọng, persist ID/state trước 202, dùng lease/retry/idempotency.
- [ ] Các downstream calls có connect/read/total deadlines, retries hữu hạn và idempotency.
- [ ] Không coi client cancellation là rollback downstream side effect.
- [ ] MVC Callable/DeferredResult có async timeout và executor thích hợp.
- [ ] WebFlux return/compose Publisher, không gọi `subscribe()`/`block()` vô tội vạ.
- [ ] Streaming SSE/WebSocket có drain, close/reconnect và bounded memory.
- [ ] Quản lý DB/client pool theo lifecycle để còn sống tới khi tasks phụ thuộc xong.
- [ ] Readiness giảm traffic; kiểm tra actual LB/ingress endpoint propagation.
- [ ] Docker Java nhận SIGTERM trực tiếp; tránh shell PID1 không forward.
- [ ] Kubernetes `terminationGracePeriodSeconds` đủ cho preStop + shutdown + margin.
- [ ] Không dùng `@PreDestroy` chờ vô hạn, không dựa cleanup callback khi SIGKILL.
- [ ] Có logs/metrics cho active requests, jobs, downstream, cancellation, shutdown duration và rejected traffic.
- [ ] Test in-flight HTTP thực khi context.close, và test SIGTERM/kill trong staging.
- [ ] Có recovery plan cho crash giữa downstream commit và caller response.
- [ ] Có load/chaos tests cho long-running request, idle connections và concurrent jobs.

## 22. Câu hỏi tự kiểm tra

**1. Graceful shutdown của Boot 3.3 được bật theo mặc định không?**  
Không theo tài liệu Boot 3.3; đặt `server.shutdown=graceful` để bật rõ. Các version mới có thể thay đổi default.

**2. Spring Boot có tự đợi toàn bộ @Async jobs sau HTTP 202 không?**  
Không. HTTP 202 đã kết thúc; background executor cần shutdown policy riêng và job durability nếu quan trọng.

**3. Một MVC controller trả Callable nghĩa là request đã kết thúc ngay không?**  
Không. Nó thường chuyển sang Servlet async processing, response vẫn mở đến khi Callable hoàn tất/timeout/error dispatch.

**4. Vì sao lời gọi RestClient downstream có thể làm graceful thất bại?**  
Vì request A đang chờ B lâu hơn grace; timeout/connect/retry không được đặt đúng có thể làm server đóng trước khi response gửi xong.

**5. Nếu B đã commit nhưng A bị SIGKILL trước khi trả response, retry có an toàn không?**  
Chưa chắc. Cần idempotency key, dedup và reconcile outcome; graceful không có exactly-once.

**6. `setWaitForTasksToCompleteOnShutdown(true)` có thay việc lưu job vào database không?**  
Không. Nó giúp executor chờ trong shutdown bình thường, không bảo vệ khỏi crash/power loss/Kubernetes SIGKILL.

**7. Với WebFlux, cần làm gì để HTTP request gắn cùng downstream call?**  
Return/compose Publisher `WebClient...bodyToMono(...)` từ handler. Không tự `subscribe()` rồi bỏ reference.

**8. `Mono.timeout` có đảm bảo downstream server hủy giao dịch không?**  
Không. Nó báo timeout/cancel ở phía reactive subscriber; downstream có thể đã nhận/commit.

**9. Khi preStop sleep 5s và Pod grace 30s, Java còn đúng 30s không?**  
Không. Countdown bắt đầu **trước preStop**, nên chỉ còn khoảng 25s trừ thời gian khác.

**10. Tại sao không assert mọi request mới lúc graceful đều HTTP 503?**  
Vì Tomcat/Jetty/Reactor Netty có thể ngừng accept tại network layer, client có thể nhận connection refused/reset; Undertow có thể trả 503.

**11. Tại sao metrics server có thể không ghi các request mất lúc SIGKILL?**  
Vì observation thường ghi khi request kết thúc; nếu JVM bị kill giữa chừng, dữ liệu chỉ có ở proxy/client/telemetry đã flush.

**12. Có nên chờ mọi WebSocket/SSE connection vô hạn rồi mới shutdown?**  
Không. Cần bounded grace, drain/close/reconnect policy và durable cursor/replay nếu business yêu cầu.

## 23. Tài liệu tham khảo

1. Spring Boot **3.3 Graceful Shutdown** — bốn embedded servers, `server.shutdown`, `spring.lifecycle.timeout-per-shutdown-phase`, behavior server-specific: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
2. Spring Boot **3.3 Application Properties** — `spring.task.execution.shutdown.await-termination`, scheduling, MVC async request timeout: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
3. Spring Boot **3.3 Actuator Endpoints / Kubernetes Probes** — ApplicationAvailability, Readiness/Liveness, graceful shutdown phases: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
4. Spring Framework — **Asynchronous Requests** (`Callable`, `DeferredResult`, `WebAsyncTask`, Servlet async dispatch): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
5. Spring Framework — **Task Execution and Scheduling**, `@Async`, executor bounds và lifecycle: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
6. Spring Framework — **WebClient retrieve** và response handling: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
7. Spring Framework — **WebFlux Reactive Core** (publisher, cancellation, non-blocking I/O): https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
8. Kubernetes — **Pod Lifecycle / Termination Flow**, preStop, SIGTERM/SIGKILL, EndpointSlice readiness: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
9. Kubernetes — **Container Lifecycle Hooks**, preStop consumes total grace: https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/

**Tổng kết:** Graceful shutdown của Spring Boot giúp **HTTP requests đã được server nhận** có thời gian hoàn tất trước khi đóng web runtime, nhưng không mặc định bảo đảm mọi `@Async` job, scheduler, consumer hoặc downstream side effect. Muốn dừng đáng tin cậy, phải thiết kế đồng thời **traffic drain**, **HTTP grace period**, **bounded async executors**, **downstream deadlines**, **job durability/idempotency**, **resource lifetime** và **Kubernetes termination budget**. Kiểm thử bằng request thật đang chạy khi context đóng, sau đó thử SIGTERM/Pod termination trong môi trường triển khai để xác nhận điều kiện thực tế.