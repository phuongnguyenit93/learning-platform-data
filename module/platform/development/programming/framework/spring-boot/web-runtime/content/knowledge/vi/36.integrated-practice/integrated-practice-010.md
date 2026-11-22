# Đo tải, điều chỉnh giới hạn tài nguyên và kiểm chứng hành vi quá tải trong Spring Boot

## 1. Mục tiêu thực hành

Một ứng dụng Spring Boot có thể trả HTTP 200 trong 20 ms khi một người sử dụng, nhưng mất ổn định khi hàng trăm clients tới đồng thời: queue dài, p99 tăng, Tomcat worker threads chờ DB, heap tăng, CPU bị throttling, reverse proxy trả 502/504 hoặc Pod bị OOMKill. Vì vậy **đo tải** không phải chỉ tìm con số RPS cao nhất, mà phải chứng minh:

1. Ứng dụng đáp ứng **SLO** với một loại workload và lượng traffic cụ thể.
2. Tài nguyên nào là **bottleneck** khi tăng tải: CPU, heap/GC, threads, sockets, DB pool, queue, network, proxy hay bộ phát tải.
3. Các giới hạn được **đo và điều chỉnh có cơ sở**, tránh tăng tất cả properties tùy ý.
4. Khi vượt capacity, ứng dụng có **controlled overload behavior**: giới hạn concurrent work, trả HTTP 429/503 rõ ràng hoặc reject sớm, không giữ hàng đợi vô hạn.
5. Khi tải giảm, health, latency, connection/pool và memory **phục hồi**, không để backlog/leak hay restart storm.
6. Bằng chứng được ghi từ **cả client lẫn server**, không che các request bị từ chối.

Bài học là một thực hành tổng hợp cho **Spring Boot web-runtime**, dùng Java 17, Spring Boot 3.3.x, Spring MVC/embedded Tomcat, Actuator/Micrometer, k6, Docker và Kubernetes. Mọi số timeout/threads/quota/RPS là **giá trị lab** để dễ quan sát; không mặc nhiên là cấu hình an toàn/tối ưu cho production.

**Phạm vi an toàn:** chỉ chạy load generator lên localhost hoặc staging có quyền, giới hạn duration, RPS, VUs, kết nối và tài nguyên. Không áp stress tests vào production hoặc hệ thống bên thứ ba nếu chưa có phê duyệt, cửa sổ bảo trì và phương án dừng.

## 2. Định nghĩa các chỉ số trước khi tạo tải

| Thuật ngữ | Ý nghĩa đúng | Nhầm lẫn cần tránh |
| --- | --- | --- |
| Offered arrival rate | Requests/s mà bộ phát tải **muốn bắt đầu** | Không phải requests/s thực sự tới Spring |
| Achieved request rate | Requests/s thực sự được gửi hoặc hoàn tất, tùy công cụ | Không mặc định bằng target rate |
| Successful throughput | Số operations/s **đáp ứng đúng hợp đồng nghiệp vụ** | HTTP 503/429 không phải successful |
| Concurrency/in-flight | Số requests đang giữ tài nguyên tại một mốc | Không giống RPS |
| Latency | Thời gian request theo ranh giới đo được | Average không phản ánh p99 |
| p50/p95/p99 | Phân vị thời gian; p99 là mức mà ~99% samples không vượt | Không ổn định khi sample quá ít |
| Error rate | Tỉ lệ lỗi theo contract: status, timeout, reset, business failure | 503 có chủ ý vẫn là lỗi phía client |
| Rejection/load shedding | Từ chối yêu cầu mới trước khi quá tải kéo sập hệ thống | Không phải tăng throughput thành công |
| Saturation | Resource gần hết capacity hoặc queues/pending tăng | CPU thấp không có nghĩa dư DB/threads |
| Recovery | Trở về latency, success, pool/heap/queue ổn định sau overload | Không chỉ thấy process vẫn Running |

Ví dụ một **hợp đồng lab**, không phải SLO production:

- **Baseline:** 10 GET requests/s vào endpoint có simulated delay 200ms; HTTP success ≥99%, p95 `<`450ms, p99 `<`700ms, không dropped iterations.
- **Stress:** tăng tới 100–120 attempted GET requests/s; khi hết 8 logical slots, application trả **503 + Retry-After**, accepted latency không tăng vô hạn.
- **Safety:** không OOMKill, không restart bất thường, health/ping vẫn có cơ hội phục vụ, không xuất hiện hàng đợi dài không giới hạn.
- **Recovery:** giảm về 10 req/s, 503 về gần 0, accepted latency trở lại baseline, active work về mức hợp lý.
- **Correctness:** nếu chuyển sang POST/DB, phải đối chiếu durable effects và idempotency; HTTP 200 một mình không chứng minh không mất/nhân đôi nghiệp vụ.

### Little's Law và capacity gần đúng

Với hệ thống ổn định và cùng ranh giới đo:

\[
L = \lambda W
\]

`L` là số requests trung bình trong hệ thống, `λ` là số requests/giây hoàn tất và `W` là thời gian trung bình của một request (giây). Giả sử 8 requests đang xử lý đồng thời và mỗi request giữ slot 0,2 giây, năng lực lý tưởng xấp xỉ:

\[
\mu \approx 8 / 0{,}2 = 40 \text{ requests/s}
\]

Đây chỉ là **ước lượng trong lab** nếu mọi requests mất ~200ms và không có bottleneck khác. Thực tế serialization, thread scheduling, IO, GC, retries và payload sizes tạo biến động. Khi offered rate 120/s nhưng chỉ phục vụ ~40/s, lượng dư phải được **queue giới hạn**, reject hoặc điều tiết, thay vì tích lũy vô hạn.

Một dấu hiệu rất nguy hiểm: successful throughput không tăng nữa, nhưng p99, queue depth và timeouts tiếp tục tăng khi tăng offered load. Đó là **knee point** của đường capacity.

## 3. Các kiểu load test và lựa chọn kịch bản

| Test | Câu hỏi cần trả lời | Thời điểm |
| --- | --- | --- |
| Smoke | Endpoint, script, token, metrics đúng chưa? | Trước mọi phép đo |
| Warm-up | JIT, classloading, pools/cache đã ổn định? | Trước baseline |
| Baseline | SLO ở traffic nhỏ có đạt? | Lấy số đối chứng |
| Load test | Traffic dự kiến (đỉnh thường ngày) có đạt SLO? | Kiểm chứng capacity |
| Stress | Tăng quá target, giới hạn nào chạm trước? | Tìm overload behavior |
| Spike | Burst đến đột ngột có gây meltdown? | Kiểm thử queue/retry |
| Soak | Sau thời gian dài có leak memory/FD/threads? | Kiểm tra ổn định |
| Recovery | Sau khi hạ tải hệ thống có hồi phục? | Sau stress/spike |
| Scalability | Tăng CPU/replicas có tăng successful throughput? | Tuning/architecture |
| Failover | Pod restart/drain/DB latency ảnh hưởng tail thế nào? | Resilience test |

### Closed model và open model

**Closed model (constant VUs)**: mỗi virtual user chỉ bắt đầu iteration tiếp khi iteration trước xong. Khi server chậm, tốc độ request tự giảm, nên load generator có thể **vô tình che những khoảng thời gian tệ**, một dạng *coordinated omission*.

~~~javascript
export const options = {
  scenarios: {
    closed: {
      executor: 'constant-vus',
      vus: 20,
      duration: '30s',
    },
  },
};
~~~

**Open model (arrival rate)**: công cụ cố bắt đầu requests theo rate quy định, độc lập thời gian response, miễn đủ VUs.

~~~javascript
export const options = {
  scenarios: {
    open: {
      executor: 'constant-arrival-rate',
      rate: 20,
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 30,
      maxVUs: 60,
    },
  },
};
~~~

Với arrival-rate, **không thêm `sleep(1)` ở cuối iteration** để điều độ; executor đã tự pace. Nếu `dropped_iterations > 0`, một số scheduled iterations **chưa được bắt đầu** vì load generator không có VU trống. Có thể do `preAllocatedVUs/maxVUs` thấp, hoặc SUT quá chậm làm VUs chiếm lâu, hoặc cả hai. Không được gọi chúng là HTTP 503 do app trả: phải đếm HTTP responses và attempts riêng.

## 4. Những tài nguyên hữu hạn trong Spring Boot

~~~text
Clients -> CDN / Ingress / LB
              |
              v
Tomcat TCP accept / keep-alive connections
              |
              v
Servlet request worker threads
              |
              v
Application concurrency gate
              |
          +---+----+
          |        |
          v        v
       JDBC       HTTP downstream
       pool       client pool
          |        |
          +---+----+
              |
              v
        CPU / heap / direct memory
              |
              v
        Database / broker / disk
~~~

| Resource | Dấu hiệu bão hòa | Điều cần điều chỉnh |
| --- | --- | --- |
| Servlet worker threads | Busy gần max, queue chờ, health cũng chậm | Giảm blocking/timeout, tuning worker hợp lý |
| TCP connections/FD | Refused/timeout, open sockets cao | Connection cap, keep-alive, idle/slow-client policy |
| Executor queue | Wait time tăng, memory queue tăng | Bounded queue, admission/rejection |
| JDBC pool | Hikari active=max, pending tăng | Pool sizing, query/index/transaction time |
| CPU | Utilization/quota cao, throttling, p99 tăng | Optimize CPU work, CPU requests/limits, scale |
| JVM heap/GC | GC pause dài, after-GC heap tăng | Allocation profiling, heap/caches, memory |
| Native/direct memory | RSS cao nhưng Java heap thấp | Netty buffers, thread stacks, cgroup memory |
| Reverse proxy | 502/504, upstream connect/read timeouts | LB upstream pool, limits, route/path |
| Load generator | VUs max, dropped_iterations, CPU cao | Tăng injector capacity, giảm target test |
| DB/broker downstream | Latency, locks, queue lag | Capacity/multi-Pod budget, backpressure |

**Không có một flag chung để “tăng performance”.** CPU 30% vẫn có thể bị nghẽn DB pool. Tăng Tomcat workers từ 16 lên 200 có thể chỉ tạo thêm 184 threads chờ DB. Tăng accept queue có thể làm requests chờ lâu hơn và giảm success ratio do client timeouts.

## 5. Một project runnable: Spring Boot 3.3 / Java 17

Ứng dụng demo cần có:

- `GET /api/ping` trả kết quả nhanh để thử sức khỏe HTTP.
- `GET /api/work?durationMs=200` mô phỏng work bằng `Thread.sleep` với giới hạn duration.
- Một **Semaphore** giới hạn tối đa 8 requests đang xử lý trên mỗi JVM. Khi hết, trả **503 Service Unavailable** và `Retry-After: 1`, không xếp hàng permit vô hạn.
- `GET /api/state` phản ánh active/available slots.
- Micrometer counters/gauges và Spring Actuator Prometheus.
- JUnit integration test cho 200, 400, 503 và phục hồi.
- k6 scripts baseline/stress.

**Giới hạn rõ:** `Thread.sleep` chiếm Servlet worker nhưng ít dùng CPU; số RPS của endpoint này **không dùng để sizing CPU-bound workloads** như nén dữ liệu, mã hóa hay JSON nặng, cũng không đại diện cho database production.

### 5.1. Cấu trúc thư mục

~~~text
load-lab/
├── settings.gradle
├── build.gradle
├── Dockerfile
├── baseline.js
├── stress.js
└── src/
    ├── main/
    │   ├── java/demo/loadlab/LoadLabApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/loadlab/LoadLabHttpTest.java
~~~

### 5.2. settings.gradle

~~~groovy
rootProject.name = 'load-lab'
~~~

### 5.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'load-lab.jar'
}
~~~

`spring-boot-starter-web` kéo embedded Tomcat. Micrometer Prometheus registry cho phép `/actuator/prometheus` phục vụ định dạng scrape; Prometheus server thực để lưu time-series là thành phần **riêng**, không tự xuất hiện khi thêm dependency.

### 5.4. application.properties

~~~properties
spring.application.name=load-lab
server.port=8080

# Bảo vệ Actuator khi chỉ test localhost.
server.address=127.0.0.1

# Tomcat connector limits cố ý nhỏ trong lab.
server.tomcat.threads.max=16
server.tomcat.threads.min-spare=4
server.tomcat.max-connections=100
server.tomcat.accept-count=20
server.tomcat.connection-timeout=10s
server.tomcat.keep-alive-timeout=10s
server.tomcat.mbeanregistry.enabled=true

# Logical work admission budget riêng với Tomcat thread count.
lab.max-concurrent=8

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.endpoint.health.probes.enabled=true
management.metrics.distribution.percentiles-histogram.http.server.requests=true

server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

**Giải thích:**
- `server.tomcat.threads.max=16` giới hạn platform request workers, **không phải** giới hạn RPS hay kết nối TCP. Với Java 21 virtual threads, một số Tomcat thread properties không còn tác dụng kiểu này, nhưng lab dùng Java 17.
- `server.tomcat.max-connections=100` giới hạn số connections, gồm cả idle keep-alive, không đồng nghĩa 100 handlers chạy đồng thời.
- `server.tomcat.accept-count=20` là backlog khi capacity đầy; OS có thể timeout/refuse và không tạo HTTP 503.
- `server.tomcat.connection-timeout` chủ yếu chờ request line sau accept; không phải total handler deadline.
- `server.tomcat.keep-alive-timeout` chờ request **tiếp theo** trên persistent connection.
- `server.tomcat.mbeanregistry.enabled=true` cần cho Tomcat metrics với Boot 3.3.
- `management.metrics.distribution.percentiles-histogram.http.server.requests=true` bật histogram HTTP timer; kiểm tra memory/cardinality trước khi dùng trên production.
- `lab.max-concurrent=8` chỉ áp dụng cho đoạn work của controller; server vẫn có thể hết CPU/threads/sockets trước khi request tới controller.

**Không mở `/actuator/prometheus`, `/actuator/metrics`, `/api/state` ra public vô điều kiện**. Trong Docker/Kubernetes, khi cần bind 0.0.0.0 thì áp firewall/NetworkPolicy/auth ở edge và giữ diagnostics private.

### 5.5. Java source đầy đủ

`src/main/java/demo/loadlab/LoadLabApplication.java`:

~~~java
package demo.loadlab;

import java.util.Map;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoadLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoadLabApplication.class, args);
    }
}

@RestController
class WorkController {
    private final Semaphore permits;
    private final AtomicInteger active = new AtomicInteger();
    private final Counter rejected;
    private final Counter completed;
    private final int limit;

    WorkController(
            @Value("${lab.max-concurrent:8}") int maxConcurrent,
            MeterRegistry registry) {

        if (maxConcurrent < 1) {
            throw new IllegalArgumentException(
                    "lab.max-concurrent must be >= 1");
        }

        this.limit = maxConcurrent;
        this.permits = new Semaphore(maxConcurrent, true);

        Gauge.builder("lab.work.active", active, AtomicInteger::get)
                .description("Current active work requests")
                .register(registry);

        Gauge.builder("lab.work.available", permits,
                        Semaphore::availablePermits)
                .description("Available admission permits")
                .register(registry);

        rejected = Counter.builder("lab.work.rejections")
                .description("Work requests rejected at app gate")
                .register(registry);

        completed = Counter.builder("lab.work.completions")
                .description("Accepted work requests completed")
                .register(registry);
    }

    @GetMapping("/api/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/state")
    Map<String, Integer> state() {
        return Map.of(
                "active", active.get(),
                "available", permits.availablePermits(),
                "limit", limit);
    }

    @GetMapping("/api/work")
    ResponseEntity<?> work(
            @RequestParam(defaultValue = "200") int durationMs) {

        if (durationMs < 0 || durationMs > 2500) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "durationMs must be 0..2500"));
        }

        if (!permits.tryAcquire()) {
            rejected.increment();
            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .header(HttpHeaders.RETRY_AFTER, "1")
                    .body(Map.of(
                            "result", "rejected",
                            "reason", "capacity"));
        }

        active.incrementAndGet();
        try {
            // Chỉ dùng để mô phỏng blocking wait trong lab.
            Thread.sleep(durationMs);
            completed.increment();
            return ResponseEntity.ok(Map.of(
                    "result", "ok",
                    "durationMs", durationMs));
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of("result", "interrupted"));
        } finally {
            active.decrementAndGet();
            permits.release();
        }
    }
}
~~~

### Vì sao code này có thể kiểm chứng overload?

- `Semaphore(maxConcurrent,true)` giữ một số permits hữu hạn **trên một JVM**. `tryAcquire()` thử ngay, không làm request thread thành queue chờ permit.
- Khi hết slot, controller **thực sự trả HTTP 503** với `Retry-After:1`. Đây là **application-layer rejection**, khác TCP refused hoặc NGINX 502.
- `try/finally` release permit cả khi exception/interrupt; tránh giảm capacity vĩnh viễn sau nhiều requests.
- `active` là gauge đang xử lý, `available` là permits còn trống, `rejected` đếm 503 do app gate, `completed` đếm công việc đã kết thúc bình thường.
- `/api/ping` không dùng app permits, nhưng vẫn phải qua Tomcat threads/connections. Nếu toàn HTTP stack bão hòa thì ping cũng có thể timeout; không bảo đảm luôn 200.
- Một Pod có 8 permits, 4 Pods có thể chấp nhận tới **32 work requests đồng thời** nếu phân phối đều, nhưng shared DB có thể chịu ít hơn. Đây không phải distributed/global quota.

### 5.6. Chạy thử

Linux/macOS:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/load-lab.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
java -jar .\build\libs\load-lab.jar
~~~

Nếu project chưa có Gradle wrapper, cần Gradle tương thích để tạo wrapper hoặc chạy `gradle clean test bootJar`.

Ở terminal khác:

~~~bash
curl -i http://127.0.0.1:8080/api/ping
curl -i 'http://127.0.0.1:8080/api/work?durationMs=200'
curl -i http://127.0.0.1:8080/api/state
curl -i http://127.0.0.1:8080/actuator/health
~~~

Khi không có tải, các responses logic dự kiến:

~~~text
GET /api/ping                 -> HTTP 200 {"status":"ok"}
GET /api/work?durationMs=200  -> HTTP 200 {"result":"ok","durationMs":200}
GET /api/state                -> HTTP 200 {"active":0,"available":8,"limit":8}
GET /actuator/health          -> HTTP 200 {"status":"UP"}
~~~

Thứ tự keys JSON/headers, elapsed duration và số active tức thời có thể khác. `durationMs=5000` trả HTTP 400 (validation), không phải overload 503.

## 6. Kiểm thử Java JUnit: 503 xảy ra khi thực sự hết permits

`src/test/java/demo/loadlab/LoadLabHttpTest.java`:

~~~java
package demo.loadlab;

import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "lab.max-concurrent=1")
class LoadLabHttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void normalEndpointsWork() {
        ResponseEntity<String> ping = http.getForEntity(
                "/api/ping", String.class);
        assertThat(ping.getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<String> ok = http.getForEntity(
                "/api/work?durationMs=10", String.class);
        assertThat(ok.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(ok.getBody()).contains("\"result\":\"ok\"");
    }

    @Test
    void invalidDurationReturns400() {
        ResponseEntity<String> r = http.getForEntity(
                "/api/work?durationMs=9000", String.class);
        assertThat(r.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);
    }

    @Test
    void overloadedRequestReturns503AndThenRecovers()
            throws Exception {

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<ResponseEntity<String>> first =
                    executor.submit(() -> http.getForEntity(
                            "/api/work?durationMs=2000",
                            String.class));

            // Đợi request đầu đang giữ permit,
            // không dựa vào Thread.sleep(100) ngẫu nhiên.
            boolean entered = false;
            for (int i = 0; i < 150; i++) {
                Map<?, ?> s = http.getForObject("/api/state", Map.class);
                if (s != null
                        && ((Number) s.get("active")).intValue() == 1) {
                    entered = true;
                    break;
                }
                Thread.sleep(10);
            }

            assertThat(entered).isTrue();

            ResponseEntity<String> denied = http.getForEntity(
                    "/api/work?durationMs=10", String.class);
            assertThat(denied.getStatusCode())
                    .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
            assertThat(denied.getHeaders().getFirst("Retry-After"))
                    .isEqualTo("1");

            assertThat(first.get(5, TimeUnit.SECONDS)
                    .getStatusCode()).isEqualTo(HttpStatus.OK);

            ResponseEntity<String> recovered = http.getForEntity(
                    "/api/work?durationMs=10", String.class);
            assertThat(recovered.getStatusCode())
                    .isEqualTo(HttpStatus.OK);
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.loadlab.LoadLabHttpTest
~~~

Với cap test = 1, method giữ request đầu trong 2 giây, **quan sát active==1**, request thứ hai phải 503 và request sau khi job đầu hoàn tất phải 200. Trình tự này tránh nhầm vài requests tuần tự là concurrent test. Test chỉ chứng minh một JVM/HTTP pipeline trong máy test, không chứng minh toàn cluster/Ingress hay production RPS.

**Lưu ý độ ổn định:** trên CI quá chậm hoặc nhiều test chạy đồng thời, thời gian quan sát/timeout có thể cần điều chỉnh; test phải báo lỗi thật nếu không thấy request đầu đã vào controller, không tự gán 503/QA pass.

## 7. k6 baseline.js: mô hình offered rate độc lập latency

Tạo `baseline.js` trong project root. Yêu cầu cài **k6 CLI** theo tài liệu chính thức; Gradle không tự cung cấp lệnh `k6`.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8080';

export const options = {
  scenarios: {
    baseline: {
      executor: 'constant-arrival-rate',
      rate: 10,
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 20,
      maxVUs: 50,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{route:work}': [
      'p(95)<450',
      'p(99)<700',
    ],
    dropped_iterations: ['count==0'],
  },
};

export default function () {
  const res = http.get(BASE + '/api/work?durationMs=200', {
    timeout: '3s',
    tags: { route: 'work' },
  });

  check(res, {
    'baseline receives HTTP 200': (r) => r.status === 200,
    'baseline returns expected body': (r) =>
      r.status === 200 && r.json('result') === 'ok',
  });
}
~~~

Chạy khi Spring app đã lên:

~~~bash
k6 run -e BASE_URL=http://127.0.0.1:8080 baseline.js
~~~

Trên Windows PowerShell cũng dùng lệnh `k6 run -e ... .\baseline.js`. Mục tiêu là **khoảng 10 iterations/s**; vì mỗi iteration đúng một HTTP GET nên có thể suy attempted request rate gần 10/s nếu `dropped_iterations=0` và không có script errors.

### Giải nghĩa thresholds

- `http_req_failed < 1%`: k6 mặc định coi HTTP 4xx/5xx là failed theo expected-response policy; trong baseline không mong 503.
- `http_req_duration{route:work} p95 < 450ms`, p99 < 700ms: route-tagged response duration của test, không trộn health URL.
- `dropped_iterations == 0`: load generator phải có đủ VUs để bắt đầu scheduled iterations.
- Nếu k6 exit non-zero, xem threshold nào fail. Đừng chỉ thêm VUs hoặc tăng timeout cho qua test mà chưa tìm nguyên nhân.
- Ngưỡng dưới 450/700ms mang tính **lab**, phải thiết kế khác theo SLO thật.

**Trước baseline**, chạy warm-up nhỏ để JIT, connection pools và caches ổn định. Với ứng dụng có cold-start SLO, đo cold start thành một thử nghiệm **riêng** thay vì trộn vào steady-state.

## 8. k6 stress.js: tăng tải có kiểm soát và tách 503

Tạo `stress.js` trong project root:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8080';

const rejected = new Counter('lab_rejected_503');
const unexpected = new Rate('unexpected_response');
const acceptedLatency = new Trend('accepted_latency_ms', true);

export const options = {
  scenarios: {
    stress: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 60,
      maxVUs: 120,
      stages: [
        { target: 20, duration: '15s' },
        { target: 80, duration: '25s' },
        { target: 120, duration: '25s' },
        { target: 10, duration: '20s' },
      ],
    },
  },
  thresholds: {
    unexpected_response: ['rate<0.01'],
    dropped_iterations: ['count==0'],
    accepted_latency_ms: ['p(95)<600'],
  },
};

export default function () {
  const res = http.get(BASE + '/api/work?durationMs=200', {
    timeout: '3s',
    tags: { route: 'work' },
  });

  const ok = res.status === 200;
  const shed = res.status === 503;

  if (ok) {
    acceptedLatency.add(res.timings.duration);
  }
  if (shed) {
    rejected.add(1);
  }

  unexpected.add(!(ok || shed));
  check(res, {
    'response is HTTP 200 or controlled 503': (r) =>
      r.status === 200 || r.status === 503,
  });
}
~~~

Chạy:

~~~bash
k6 run -e BASE_URL=http://127.0.0.1:8080 stress.js
~~~

**Cách đọc kết quả:**

- Ở 10–20 req/s app thường còn dư 8 permits.
- Với 8 slots và handler ~200ms, khi offered rate vượt ~40/s, có thể xuất hiện **503 nhanh** từ app gate.
- `lab_rejected_503` k6 đếm responses 503; app counter `lab.work.rejections` đếm đường gate. Khi hai số khác nhau, xem proxy/network/multi-instance/time windows.
- `accepted_latency_ms` chỉ đo responses status 200. `http_req_duration` tổng cũng gồm 503 nhanh.
- `http_req_failed` của k6 **vẫn tăng** khi có 503 intentional; không giấu thông số đó trong báo cáo.
- `unexpected_response` đếm statuses ngoài 200/503 (và status0/network errors), gợi ý vấn đề vượt quá load shedding contract.
- `dropped_iterations` cần kiểm tra riêng. Khi k6 quá ít VUs, số requests thực sự tới app thấp hơn offered rate.
- Threshold `accepted_latency_ms p95<600ms` là một lab criterion; nếu fail, có thể accepted requests cũng đang queue ở các tầng trước permit.
- Không có bảo đảm một lần chạy nhất định phải có 503: OS/client scheduling, actual duration, nhiều replicas và config khác đều ảnh hưởng. **Đo**, không bịa kết quả.

### Vì sao overall latency đôi khi “đẹp” hơn lúc overload?

Giả sử 40 HTTP 200 mất 250ms và 80 HTTP 503 mất 5ms. Average tất cả 120 requests khoảng 87ms, thấp hơn baseline 250ms, nhưng chỉ **một phần ba requests thành công**. Do đó luôn báo đồng thời:

~~~text
target offered rate
started/completed attempts
dropped_iterations
HTTP 200/s (successful throughput)
HTTP 503/s (intentional shed)
unexpected errors and connection failures
accepted p95/p99
all-response p95/p99
JVM, Tomcat, DB and OS saturation
recovery after reducing load
~~~

Không được lọc bỏ 503 khỏi error rate rồi tuyên bố zero errors; cũng không được coi controlled 503 là crash của Spring.

## 9. Kiểm tra thủ công concurrency gate

Một request đơn:

~~~bash
curl -i 'http://127.0.0.1:8080/api/work?durationMs=200'
~~~

Dự kiến HTTP 200 với body JSON tương đương:

~~~json
{"result":"ok","durationMs":200}
~~~

Khi 8 requests đang trong handler, request thứ 9 có thể trả:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 1
Content-Type: application/json

{"result":"rejected","reason":"capacity"}
~~~

Header order/format phụ thuộc runtime. Để thử burst **localhost** trên Linux/macOS:

~~~bash
seq 1 20 | xargs -P 20 -I {} \
  curl -s -o /dev/null -w '%{http_code}\n' \
  'http://127.0.0.1:8080/api/work?durationMs=1000'
~~~

Kết quả thường có cả 200 lẫn 503 nếu nhiều requests đến thật đồng thời; số lượng cụ thể phụ thuộc scheduling và không cố định. Sau khi tất cả xong:

~~~bash
curl -i 'http://127.0.0.1:8080/api/work?durationMs=10'
curl -i http://127.0.0.1:8080/api/state
~~~

mong trở lại HTTP 200 và state active về 0, available về 8 khi không còn job. Không gửi 9 cURL **tuần tự** rồi gọi đó là concurrency test.

## 10. Metrics: client, HTTP, Tomcat, JVM, OS và downstream

### 10.1. Actuator/Micrometer endpoints

Trong lab:

~~~bash
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/actuator/metrics
curl -i http://127.0.0.1:8080/actuator/metrics/http.server.requests
curl -i http://127.0.0.1:8080/actuator/metrics/lab.work.active
curl -i http://127.0.0.1:8080/actuator/metrics/lab.work.rejections
curl -i http://127.0.0.1:8080/actuator/prometheus
~~~

**Một số metrics chỉ xuất hiện sau request đầu tiên**; `http.server.requests` theo route có thể chưa có nếu chưa tạo traffic. Registry naming có thể đổi dạng: dotted `lab.work.rejections` được Prometheus chuyển thành snake_case, ví dụ `lab_work_rejections_total`; gauges có thể là `lab_work_active`. **Đây là tên minh họa**, kiểm tra output thật trước khi viết dashboard.

Trong Spring Boot 3.3:
- Spring MVC auto-instruments `http.server.requests`.
- JVM metrics thuộc `jvm.*` (heap, GC, threads...), system/process metrics thuộc `system.*` và `process.*`.
- Tomcat metrics có thể cần `server.tomcat.mbeanregistry.enabled=true`.
- Prometheus endpoint cần registry dependency **và** expose qua management endpoints.

### 10.2. Dùng PromQL khi có Prometheus thực

Nếu HTTP histogram đã bật và output có label như ví dụ, successful rate:

~~~promql
sum(rate(http_server_requests_seconds_count{
  uri="/api/work",status="200"
}[1m]))
~~~

App-level 503 rate:

~~~promql
sum(rate(http_server_requests_seconds_count{
  uri="/api/work",status="503"
}[1m]))
~~~

p95 latency của requests HTTP 200:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      uri="/api/work",status="200"
    }[5m])
  )
)
~~~

**Kiểm tra thực tế:** Micrometer/Prometheus versions, histogram config và labels có thể khác. Nếu `_bucket` chưa có, không thể chạy histogram_quantile theo câu query này; cần cấu hình timer histogram đúng và đo chi phí time-series/cardinality. Không thêm raw userId/requestId/query string làm metric tags.

### 10.3. Các nhóm cần quan sát đồng bộ

| Lớp | Tín hiệu |
| --- | --- |
| k6 | http_reqs, iterations, dropped_iterations, http_req_failed, p50/p95/p99 |
| HTTP | http.server.requests theo uri/status/method, 429/503/502/504 |
| App | lab.work.active, available, rejections, completions |
| Tomcat | busy/current threads, connections, accept/backlog symptoms |
| JVM | heap used/after GC, GC pauses, live threads, direct buffers |
| OS/container | CPU usage, CPU throttling, RSS, memory limit/OOM, FD |
| DB | Hikari active/idle/pending, acquisition timeouts, slow queries |
| Upstream | downstream latency/errors, HTTP client pool pending |
| Proxy | upstream response/connect times, 502/504, resets |
| K8s | restarts, OOMKilled, CPU/memory request/limit, Ready endpoints |

**Một con số tổng CPU của cluster thấp có thể che một Pod nóng**. Quan sát theo node/pod/revision và đặt metrics ở cùng time window/timestamps. Không so k6 trên localhost với public ingress rồi kết luận một thay đổi Tomcat duy nhất gây chênh lệch.

## 11. Điều chỉnh Tomcat và app budget đúng nghĩa

Các biến lab:

~~~properties
server.tomcat.threads.max=16
server.tomcat.max-connections=100
server.tomcat.accept-count=20
lab.max-concurrent=8
~~~

**Bốn giới hạn độc lập:**

- `threads.max`: số worker platform threads. Java 21 virtual threads thay đổi semantics một số settings; lab Java17 là platform thread mode.
- `max-connections`: tổng connections được chấp nhận/xử lý, bao gồm idle keep-alive; không phải số request workers.
- `accept-count`: TCP backlog khi connections/threads bị căng; OS có thể refuse/timeout mà không có HTTP response.
- `lab.max-concurrent`: số logical work requests vào controller cùng lúc. Khi không còn permit, controller mới tạo 503 nếu đã được Tomcat dispatch.

### Experiment matrix — chỉ đổi một biến mỗi lần

| Run | Thay đổi | Quan sát có thể có |
| --- | --- | --- |
| A | 16 threads, 100 conns, 8 slots | Baseline tham chiếu |
| B | `lab.max-concurrent=2` | ~10/s lý thuyết, 503 sớm hơn |
| C | `lab.max-concurrent=12` | Accepted rate có thể tăng nếu Tomcat/downstream còn dư |
| D | `server.tomcat.threads.max=4` | Tomcat dispatch bottleneck trước app gate |
| E | `server.tomcat.max-connections=20` | Connections/keep-alive có thể thành bottleneck |
| F | `server.tomcat.accept-count=500` | Backlog dài hơn, không tự tăng service rate |
| G | Giảm CPU limit Docker | Nếu workload CPU-bound thì throttling/p99 có thể tăng |
| H | Tăng replicas | Tổng permits tăng nhưng LB/DB có thể giới hạn |

Để chỉnh trong lúc chạy, **restart với CLI args** và kiểm tra startup config:

~~~bash
java -jar build/libs/load-lab.jar \
  --lab.max-concurrent=2
~~~

Hoặc:

~~~bash
java -jar build/libs/load-lab.jar \
  --server.tomcat.threads.max=4
~~~

Chỉ thực hiện một run một config, warm-up lại và chạy cùng k6 script/host/network/payload/time window. Đo successful throughput **và** accepted p95/p99, 503, dropped iterations, threads/CPU/heap/DB.

### Đừng tăng queue vô hạn

Nếu 8 slots bị chiếm do downstream 5 giây, queue 10.000 requests chỉ tạo một khối lượng chờ lớn. `Semaphore.acquire()` chờ vô hạn trên Servlet thread cũng chính là queue ẩn. `tryAcquire()` với reject nhanh, hoặc bounded wait/queue có deadline, bảo vệ p99 tốt hơn. Các request được từ chối cần client policy: 503 server-wide overload; 429 client/tenant rate/quota; `Retry-After` + bounded retries/backoff/jitter.

## 12. HikariCP, DB và downstream: bottleneck thường nằm ngoài Tomcat

Project này **không dùng database**, do đó không có Hikari pool thật. Trong app Spring JDBC/JPA thực, có thể cấu hình ví dụ:

~~~properties
# Chỉ cho ứng dụng có Spring DataSource/HikariCP.
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.minimum-idle=2
spring.datasource.hikari.connection-timeout=1000
~~~

Hikari `connection-timeout=1000` được hiểu bằng **milliseconds** (1 giây). Cần kiểm tra version/DB driver. Nếu 3 Pods, mỗi Pod Hikari max10, tổng có thể mở tới khoảng 30 connections, chưa kể workers khác; không tăng pool trước khi kiểm tra DB max_connections, locks và query plans.

Quan sát:
- Hikari active / idle / pending, connection acquisition timeout.
- DB query duration p95/p99, locks, CPU, IOPS.
- Outbound HTTP client connect/read/pool acquire deadlines.
- Retries có nhân thêm traffic khi error budget đã cạn không?
- Có DB transaction/connection bị giữ trong response streaming không?

**Tăng Tomcat threads không chữa được DB pool đã đầy**. Thường hiệu quả hơn là giảm thời gian xử lý, tối ưu SQL/index, rút ngắn transaction, caching đúng, bounded concurrency theo downstream và circuit breaker phù hợp.

## 13. Docker: CPU, memory, bind address, benchmark boundary

`Dockerfile` cho JAR đã build:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/load-lab.jar /app/load-lab.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/load-lab.jar"]
~~~

Build và chạy **chỉ publish host localhost**:

~~~bash
./gradlew clean bootJar
docker build -t load-lab:1.0 .

docker run --rm --name load-lab \
  --cpus=1 --memory=512m \
  -e SERVER_ADDRESS=0.0.0.0 \
  -e JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65" \
  -p 127.0.0.1:18080:8080 \
  load-lab:1.0
~~~

Test:

~~~bash
curl -i http://127.0.0.1:18080/api/ping
k6 run -e BASE_URL=http://127.0.0.1:18080 baseline.js
~~~

**Giải thích:**
- `server.address=127.0.0.1` trong properties dành cho local phải override thành `0.0.0.0` **bên trong Docker**. Docker host publish chuyển tới container IP, không phải container loopback.
- `EXPOSE 8080` chỉ metadata; `-p 127.0.0.1:18080:8080` mới publish.
- `--cpus=1` giới hạn CPU quota, có thể gây throttling cho workload thực sự CPU-heavy.
- `--memory=512m` là memory container; heap không chiếm toàn bộ. Thread stacks, metaspace, direct buffers và JIT code cache cũng dùng memory.
- `-XX:MaxRAMPercentage=65` chỉ là lựa chọn lab giúp heap không ăn toàn bộ cgroup memory; cần đo RSS/off-heap và JVM flags thực tế.
- `docker stats` theo dõi mức dùng; `docker inspect` có thể hiển thị env/secrets, không chia sẻ output thô.

**Không kỳ vọng tăng CPU từ 1 lên 2 core sẽ tăng throughput bài `Thread.sleep` gấp đôi**. Workload chỉ chờ 200ms và giới hạn permits8, không đại diện cho hashing/JSON serialization/SQL CPU-bound. Muốn sizing CPU, benchmark endpoints thực với payload/mix/DB như production.

## 14. Kubernetes: requests, limits, probes, HPA và backpressure

Manifest **lab** `k8s-load-lab.yaml` (image phải có trên registry/cluster nodes):

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: load-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: load-lab
  template:
    metadata:
      labels:
        app: load-lab
    spec:
      containers:
        - name: app
          image: load-lab:1.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SERVER_ADDRESS
              value: "0.0.0.0"
            - name: LAB_MAX_CONCURRENT
              value: "8"
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: load-lab
spec:
  selector:
    app: load-lab
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
~~~

**Các lớp cần hiểu:**
- `requests` giúp scheduler chọn node và tính utilization của một số HPA policies.
- `limits.cpu` thường dùng cgroup CPU quota/throttling; một container không nhất thiết có CPU usage 100% mới gặp tail latency do throttling.
- `limits.memory` có thể dẫn tới **OOMKill** nếu cgroup vượt hạn mức; Java heap còn dư không bảo đảm native memory không cạn.
- Liveness không nên fail do transient overload ngắn rồi restart toàn bộ replicas.
- Readiness cho biết instance có nhận traffic hay không; **app gate 8/8 đầy trong một chớp mắt không nhất thiết nên làm Pod NotReady** vì dễ gây flapping và traffic shift.
- HPA không thay admission control: việc scale có độ trễ, DB shared capacity có thể không tăng và requests vượt capacity vẫn cần backpressure/load shedding.
- `imagePullPolicy=IfNotPresent` minh họa local kind/minikube; production ưu tiên immutable digest và kiểm tra nguồn image.

Khi image đã được load/publish:

~~~bash
kubectl apply -f k8s-load-lab.yaml
kubectl get pods -l app=load-lab -o wide
kubectl get svc load-lab
kubectl get endpointslice \
  -l kubernetes.io/service-name=load-lab
kubectl logs deployment/load-lab --tail=100
kubectl top pods
~~~

`kubectl top` cần metrics-server hoạt động. Nếu dùng kind và image local, có thể chạy `kind load docker-image load-lab:1.0`. Kịch bản test Service trong cluster phải dùng một Pod có k6/cURL và đúng namespace hoặc Ingress staging; **kubectl port-forward** chỉ để debug, không đo chính xác LB/Ingress production path.

## 15. Cách chẩn đoán nguyên nhân khi stress thất bại

### A. Application admission gate đang đúng thiết kế

Dấu hiệu:
- `lab.work.active≈8`, `lab.work.available≈0`.
- `lab.work.rejections` tăng và k6 thấy HTTP 503.
- Accepted p95 vẫn hợp lý, CPU/heap/threads không bị runaway.
- Khi tải giảm, 503 giảm và permits phục hồi.

**Kết luận:** overload được chặn **trước công việc tốn tài nguyên**. Nếu muốn nâng capacity, chỉ tăng permits khi downstream/CPU/memory đủ.

### B. Tomcat threads hoặc connection layer full trước app

Dấu hiệu:
- Tomcat busy workers sát max16.
- TCP timeout/refused hoặc gateway 502/504.
- App rejection counter không tăng tương ứng vì requests chưa dispatch đến controller.
- `/api/ping` chậm dù không dùng work permits.

**Kết luận:** phải xử lý connector/worker/thread blocking/keep-alive/TCP backlog, không chỉ tăng app permits.

### C. DB pool full

Dấu hiệu:
- Hikari active=max, pending tăng, threads chờ connections.
- p99 tăng, DB query/locks chậm, pool acquisition timeouts.

**Kết luận:** tối ưu query/transaction và downstream budget; tăng threads không giúp DB throughput nếu DB là bottleneck.

### D. CPU throttling, heap/GC, native memory

Dấu hiệu:
- Cgroup CPU throttled time tăng, p99 tăng khi limit thấp.
- GC pause, heap after-GC tăng hoặc memory usage chạm cgroup limit.
- Có OOMKilled dù heap có vẻ chưa đầy (native/direct/stack memory).

**Kết luận:** phải đo CPU quota/RSS/GC/profiling, không chỉ CPU average hay -Xmx.

### E. Ingress/proxy không vào được app

Dấu hiệu:
- k6 nhận 502/504, app không tăng `http.server.requests`/rejections tương ứng.
- Ingress logs connect refused/upstream timeout/no ready endpoints.

**Kết luận:** lỗi có thể ở network/proxy/Service/rollout, không được đổ cho controller.

### F. Load generator bão hòa

Dấu hiệu:
- `dropped_iterations > 0`, k6 VUs/CPU/sockets chạm ngưỡng.
- Server idle, đạt RPS thấp hơn target.

**Kết luận:** dữ liệu không đủ để khẳng định capacity app; phải tăng injector resources, tách máy load generator hoặc điều chỉnh VUs một cách kiểm soát.

## 16. 429 vs 503, Retry-After và retry storms

- **429 Too Many Requests:** thường phù hợp quota/rate limit theo user, tenant hoặc API key.
- **503 Service Unavailable:** phù hợp khi global/node capacity tạm thời cạn. Lab dùng 503 cho `Semaphore` gate.
- **502/504:** gateway/upstream errors, khác application-layer 503.
- **Retry-After: 1:** server gợi ý client thử lại sau một giây, không đảm bảo client thực thi.

Một client retry an toàn cần **exponential backoff + jitter**, giới hạn tổng số lần, deadline và tránh đồng loạt reconnect. Với POST có side effect (tạo order, charge), phải có **Idempotency-Key**, durable dedup/reconciliation; 504/timeout không chứng minh transaction chưa COMMIT.

**Giới hạn request đồng thời** khác **rate limit**: một request SSE giữ 1 giờ không vượt rate limit, nhưng vẫn chiếm connection; ngược lại 1.000 requests ngắn có thể vượt rate dù concurrency thấp. Cần quota/buffer/timeout theo loại route.

## 17. Soak, spike và recovery: kiểm chứng sau khi hạ tải

Một bài stress tốt không kết thúc ngay lúc HTTP 503 xuất hiện. Cần một **recovery window**:

1. Warm-up; ghi baseline CPU/heap-after-GC/threads/FD/active slots.
2. Chạy steady load 10/s và xác nhận baseline SLO.
3. Tăng từng stage 20→80→120/s trong giới hạn được phép.
4. Thu toàn bộ statuses, accepted latency, unexpected failures, queue depths.
5. Hạ về 10/s hoặc 0; theo dõi active slots/DB pending/Tomcat threads/heap.
6. Sau một khoảng ổn định, xác nhận app phục vụ 200 trở lại, 503 gần 0, không restart/OOM/queue creep.
7. Với soak dài, kiểm tra heap after-GC, native RSS, Netty/Servlet connections, file descriptors và time-series labels không tăng không giới hạn.

Một đường RSS tăng vài phút **không tự chứng minh memory leak**: JVM có thể reserve heap/code cache, warm classes, fill caches. Dùng after-GC retained memory, GC/JFR/heap dump (trong staging bảo vệ vì có thể chứa PII) để kết luận.

Khi có JDK diagnostics và quyền:

~~~bash
jcmd
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info
jcmd 12345 Thread.print
jcmd 12345 JFR.start name=load-lab settings=profile duration=60s
~~~

`12345` chỉ là PID ví dụ; thay bằng PID thật. Commands cần JDK tools và quyền; JFR profiling có overhead và dữ liệu nhạy cảm, tránh bật/trích xuất tùy tiện trên production.

## 18. So sánh Spring MVC/Tomcat với WebFlux/Reactor Netty

Bài lab dùng Spring MVC synchronous `Thread.sleep`:
- mỗi accepted request giữ một platform worker thread trong thời gian chờ;
- Tomcat worker saturation là một tín hiệu quan trọng.

WebFlux/Reactor Netty dùng non-blocking I/O:
- không được chạy `Thread.sleep`/`block()` trên event-loop threads;
- cần bounded demand/queues, slow-subscriber policy, timeouts và cancellation;
- `server.tomcat.threads.max` không có tác dụng cho Netty server;
- một hot publisher `onBackpressureBuffer` không giới hạn có thể gây OOM.

Một snippet **minh họa, không phải project WebFlux độc lập**:

~~~java
// Trong một WebFilter reactive có exchange và chain.
return Mono.defer(() -> {
    if (!semaphore.tryAcquire()) {
        exchange.getResponse().setStatusCode(
                HttpStatus.SERVICE_UNAVAILABLE);
        return exchange.getResponse().setComplete();
    }

    return chain.filter(exchange)
            .doFinally(signal -> semaphore.release());
});
~~~

Vì Reactor publishers là lazy, acquire/release phải gắn với subscription/response lifecycle; không dùng `finally` quanh thao tác **tạo Flux/Mono** rồi giải phóng permits trước khi response hoàn tất.

**Không so sánh trực tiếp** Spring MVC thread-sleep với WebFlux timer-based endpoint rồi tuyên bố một framework nhanh hơn. Workloads phải có cùng nghiệp vụ, database, payload, SLO, network path và resources.

## 19. Quy trình tuning khoa học

~~~text
Business workload + SLO
          |
          v
Warm-up + reproducible baseline
          |
          v
Increase offered load in stages
          |
          v
Measure successful throughput,
accepted p95/p99, rejects, saturation
          |
          v
Find actual bottleneck
  | CPU/GC        -> optimize/scale CPU/memory
  | SQL/DB pool   -> query/pool/transaction budget
  | Tomcat worker -> reduce blocking/bounded concurrency
  | Socket/FD     -> connection cap/keep-alive/timeouts
  | Queue         -> bound/reject/priority
  | k6 injector   -> VUs/CPU/network on load-generator
          |
          v
Change ONE parameter
          |
          v
Repeat same workload/environment
          |
          v
Compare SLO, successful RPS,
rejection/error rates, recovery
~~~

**Anti-pattern:** đổi Tomcat 16→200 threads, DB pool10→100, CPU1→4, heap256→2GB cùng lúc rồi kết luận “tăng threads làm app nhanh hơn”. Không có đối chứng cho biến nào đã tạo hiệu quả.

Đo nhiều lần và ghi cả variance, revision, JVM flags, Pod count, k6 target, warm-up, test duration, time of day, ingress route, dataset, cache state. Chỉ khi cùng điều kiện mới so được trước/sau.

## 20. Ví dụ báo cáo kết quả (số liệu hoàn toàn giả định)

| Config | Offered RPS | Achieved req/s | 200/s | 503/s | Unexpected/s | Accepted p95 | Nhận định |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 8 slots baseline | 10 | 10 | 10 | 0 | 0 | 225ms | SLO lab đạt |
| 8 slots ramp | 30 | 30 | 29 | 1 | 0 | 245ms | Gần ngưỡng |
| 8 slots stress | 120 | 120 | 39 | 81 | 0 | 280ms | Controlled load shedding |
| 2 slots stress | 120 | 120 | 10 | 110 | 0 | 240ms | Gate chặn sớm hơn |
| 8 slots recovery | 10 | 10 | 10 | 0 | 0 | 220ms | Phục hồi sau tải |

**Tất cả con số trong bảng chỉ minh họa cách trình bày**, không phải kết quả chạy thật. Giả định k6 không có dropped_iterations, mỗi iteration gửi một HTTP request, không có retries tự động và một JVM app. Các số thực sẽ khác vì scheduling, CPU, network, JIT, payload, OS và các lớp proxy.

### Kết luận mẫu có trách nhiệm

> Với phiên bản, cấu hình và workload đã ghi, hệ thống phục vụ low load trong ngưỡng p95; ở stress arrival rate cao, app chủ động trả 503 khi hết permits, không có unexpected HTTP/network errors, accepted p95 giữ trong SLO và phục hồi sau khi giảm tải. Điều này chứng minh **controlled overload** cho workload lab, không chứng minh production đạt 120 business transactions/s.

### Kết luận sai

> Load generator báo 120 RPS và overall average latency 60ms, vì vậy server xử lý thành công 120 RPS.

Nếu 81/s là HTTP 503 trả nhanh, successful throughput chỉ 39/s. Average latency tổng có thể bị 503 kéo xuống nên không phản ánh hiệu năng của requests được nhận.

## 21. Bảng lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ nhìn RPS tổng | 503 được tính như requests hoàn tất | Báo successful throughput, 503 và retries |
| Chỉ nhìn average latency | Bỏ p95/p99, timeout tail | Đo phân vị theo route/status |
| Không warm-up | Cold JIT/cache làm sai baseline | Warm-up riêng, đo cold riêng |
| Dùng constant-vus khi cần fixed arrival rate | Server chậm làm RPS tự giảm | Arrival-rate k6 executor |
| Thêm sleep cho arrival-rate | K6 VUs giữ lâu, drops tăng | Để executor tự schedule |
| Bỏ qua dropped_iterations | Load chưa thực sự đạt offered rate | Kiểm tra injector VUs/CPU và app |
| Bắt stress test http_req_failed luôn bằng 0 | 503 có chủ đích làm test fail | Định nghĩa overload contract riêng |
| Giấu 503 khỏi báo cáo | Che tác động thật lên client | Báo status mix và errors minh bạch |
| K6 và app cùng node CPU thấp | Injector tranh CPU app | Tách load-generator, đo cả hai |
| Tăng threads khi Hikari pool full | Tạo thêm threads chờ | Tối ưu SQL/DB và concurrency |
| Tăng accept-count thay vì capacity | Tăng queue/timeout | Bounded admission và đo latency |
| `Semaphore.acquire()` chờ vô hạn | Servlet worker bị chiếm chờ | `tryAcquire()`, reject nhanh |
| Không dùng finally release permit | Mất slot vĩnh viễn | Cleanup trên error/interrupt |
| Nhầm ingress 502 với app 503 | Chỉnh sai tầng | So edge/app counters và upstream logs |
| Chỉ đo heap | Bỏ native/direct/stack memory | Theo dõi RSS/cgroup/FD |
| Chỉ nhìn CPU average | Bỏ throttling và DB waits | CPU quota/throttling, downstream metrics |
| Liveness fail vì tải tạm thời | Restart storm | Liveness theo process, readiness riêng |
| HPA thay load shedding | Autoscaling có delay | Bounded admission vẫn cần |
| Dùng port-forward đo hiệu năng ingress | Không đi qua production path | Test Service/Ingress staging thật |
| Expose Actuator ngoài Internet | Lộ metrics/topology | Private network và auth |
| Retry POST bất kỳ khi 503/504 | Duplicate side effects | Idempotency key, durable reconciliation |

## 22. Checklist nghiệm thu

- [ ] Chỉ tạo tải lên hệ thống được phép, có giới hạn thời gian/rate/VUs và stop condition.
- [ ] Định nghĩa success/error SLO và overload contract rõ ràng.
- [ ] Ghi Java/Boot/JVM flags, code revision, Pod count, CPU/memory/DB configs.
- [ ] Dùng endpoint/payload/dataset và network path đại diện cho workload thật.
- [ ] Có warm-up, baseline và cùng cấu hình giữa các runs.
- [ ] k6 `dropped_iterations` được đo; chưa đạt target thì không tuyên bố server capacity.
- [ ] Báo offered vs achieved vs successful throughput, 200/429/503/502/504/status0.
- [ ] Đo accepted p95/p99 riêng và overall p95/p99.
- [ ] Đo Tomcat worker/connections, app slots, JVM/GC, cgroup CPU/memory, DB pool.
- [ ] Kiểm tra 503 application-level có được trả nhanh khi cạn permits không.
- [ ] Đảm bảo không có queue vô hạn, OOM/restart, FD/heap leak.
- [ ] Hạ tải và chứng minh active slots/queue/latency/health phục hồi.
- [ ] Khi tune chỉ đổi một tham số rồi lặp lại toàn bộ workload.
- [ ] Nếu dùng multi-Pod/Ingress, đối chiếu edge vs app và per-Pod metrics.
- [ ] Nếu test nghiệp vụ POST, có idempotency/durable business invariants.
- [ ] Không expose diagnostic/Actuator endpoints, token, PII vào metrics/logs public.
- [ ] Kết luận gắn với workload/environment, không extrapolate tùy tiện.

## 23. Câu hỏi tự kiểm tra

**1.** 8 permits, mỗi work request chiếm 200ms. Năng lực lý thuyết khoảng bao nhiêu?

**Đáp án:** `8 / 0,2 = 40 requests/s` trong điều kiện lý tưởng, không phải throughput đã đo.

**2.** Server nhận 120 req/s nhưng 80/s trả 503. Có được nói server xử lý thành công 120 req/s không?

**Đáp án:** Không. Successful throughput khoảng 40/s nếu các requests còn lại đều thành công; 503 là deliberate rejection và vẫn ảnh hưởng user.

**3.** Vì sao overall average/p95 có thể giảm khi quá tải?

**Đáp án:** 503 được trả rất nhanh, có thể chiếm nhiều responses, kéo duration tổng xuống dù success ratio xấu hơn. Tách accepted latency.

**4.** k6 `dropped_iterations` có phải do Tomcat trả HTTP 503?

**Đáp án:** Không. Đó là scheduled iterations chưa bắt đầu vì không còn VUs; có thể do load-generator thiếu capacity hoặc server chậm kéo dài iterations.

**5.** `server.tomcat.threads.max=16` và `lab.max-concurrent=8` có giống nhau?

**Đáp án:** Không. Tomcat threads xử lý cả HTTP requests khác, app gate chỉ giới hạn logical work route. Connections/backlog lại khác.

**6.** `server.tomcat.accept-count=1000` có làm DB xử lý nhanh hơn không?

**Đáp án:** Không. Nó liên quan backlog khi connector đầy, không tạo thêm CPU/DB capacity.

**7.** Tăng `-Xmx` bằng container memory limit có an toàn không?

**Đáp án:** Không. JVM dùng non-heap/direct/native memory, thread stacks và hệ điều hành/cgroup cũng có chi phí; có thể OOMKill.

**8.** Tại sao test `Thread.sleep` không dùng để khẳng định scale CPU?

**Đáp án:** Nó chờ/block worker chứ không tiêu thụ CPU tương ứng; CPU-bound workload phải đo riêng.

**9.** Khi nào dùng 429, khi nào dùng 503?

**Đáp án:** 429 thường cho client/tenant quota/rate, 503 cho server/node capacity tạm thời không thể nhận thêm work.

**10.** Vì sao tăng Tomcat threads có thể làm latency tệ hơn nếu Hikari max10?

**Đáp án:** Nhiều worker chờ DB connections hơn, queue/p99 tăng; bottleneck ở DB/pool không giải quyết.

**11.** Khi giảm offered rate từ 120/s về 10/s, cần kiểm tra gì?

**Đáp án:** 503 giảm, 200 phục hồi, accepted p95/p99 về baseline, active slots/queue/FD/heap không leak, Pod không restart.

**12.** Port-forward Service có đủ cho benchmark public Ingress không?

**Đáp án:** Không. Port-forward có network path/overhead khác; phải test actual Service/Ingress/LB khi được phép.

**13.** HTTP 504 trên POST có bảo đảm DB chưa COMMIT không?

**Đáp án:** Không. Gateway timeout không chứng minh business effect chưa hoàn tất; retry cần idempotency/durable reconciliation.

**14.** WebFlux/Netty có thể dùng `server.tomcat.threads.max` để tăng xử lý không?

**Đáp án:** Không. Netty có event loops, reactive backpressure và properties khác; không block event loop.

**15.** Ba nhóm metric tối thiểu khi nghiệm thu overload?

**Đáp án:** Client outcomes (offered/started/200/503/errors/p95), server admission/saturation (active slots, worker/CPU/DB), và recovery/stability (health, restart/OOM, queues/memory).

## 24. Tài liệu chính thức

- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): Tomcat max threads/connections/accept count, keep-alive, MBean Registry.
- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html): Micrometer, http.server.requests, JVM/system/Tomcat metrics, Prometheus registry.
- [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): health/metrics security và exposure.
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): in-flight requests khi dừng.
- [Tomcat 10.1 — HTTP Connector](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html): threads/connections/backlog/timeouts.
- [Grafana k6 — Open vs Closed Models](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/): arrival-rate và coordinated omission.
- [Grafana k6 — Constant Arrival Rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/): rate, preAllocatedVUs/maxVUs.
- [Grafana k6 — Ramping Arrival Rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-arrival-rate/): stress stages.
- [Grafana k6 — Dropped Iterations](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/): unscheduled iterations và nguyên nhân.
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/): pass/fail, tagged submetrics.
- [Grafana k6 — Built-in Metrics](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/): http_req_failed, request duration, iterations, VUs.
- [Micrometer — Reference](https://docs.micrometer.io/micrometer/reference/concepts.html): Counters, Gauges, Timers, tag cardinality.
- [Docker — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/): CPU/memory limits.
- [Docker — Port Publishing](https://docs.docker.com/engine/network/port-publishing/): container/host port distinction.
- [Kubernetes — Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU requests/limits, memory, scheduler.
- [Kubernetes — Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): readiness/liveness/startup.
- [Kubernetes — Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/): HPA behavior/metrics.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): 429/503 và Retry-After.

**Ghi nhớ:** một báo cáo đo tải tốt không chỉ ghi RPS. Nó chỉ rõ **điều kiện test, offered/achieved/successful throughput, p95/p99, 429/503/5xx, trạng thái CPU/heap/threads/DB, giới hạn nào nghẽn và khả năng phục hồi**. Khi vượt capacity, từ chối có kiểm soát và đúng hợp đồng có thể tốt hơn xếp hàng vô hạn, nhưng phải báo rõ **tác động lên client** và kiểm chứng bằng số liệu, không che lỗi.
