# Đo và kiểm thử trước khi áp dụng khởi tạo lười trong vận hành

**Khởi tạo lười (lazy initialization)** trong Spring Boot là việc trì hoãn tạo một số bean tới khi chúng được yêu cầu, thay vì tạo chúng ngay lúc `ApplicationContext` được làm mới. Có thể bật toàn cục bằng:

~~~properties
spring.main.lazy-initialization=true
~~~

Cách này có thể **rút ngắn thời gian khởi động**, nhưng không làm chi phí khởi tạo bean biến mất. Chi phí có thể chuyển vào request đầu tiên, lần chạy một job đầu tiên hoặc một nhánh tính năng hiếm dùng. Lỗi cấu hình trước đây phát hiện trong startup cũng có thể bị dời tới khi người dùng thật chạm chức năng.

Bài học thuộc chủ đề **Spring Boot Application Runtime**, phần **Khởi tạo lười**, dùng API Spring Boot **3.3.x / Spring Framework 6.1 / Java 17+**. Mục tiêu là thiết lập thí nghiệm có đối chứng và tiêu chí chấp nhận **trước khi bật lazy ở môi trường vận hành**, không kết luận từ một dòng log `Started`.

## 1. Hiểu điều gì được thay đổi

~~~text
EAGER, mặc định:
SpringApplication.run
  -> tạo bean definitions
  -> tạo/khởi tạo nhiều singleton non-lazy
  -> ApplicationReadyEvent
  -> request đầu: thường dùng bean đã khởi tạo

GLOBAL LAZY:
SpringApplication.run
  -> tạo bean definitions
  -> chỉ tạo những bean bắt buộc phải tạo sớm
  -> ApplicationReadyEvent
  -> request đầu: có thể tạo thêm bean lazy
  -> xử lý request
~~~

**Các giới hạn quan trọng:**

- Mặc định `spring.main.lazy-initialization=false`.
- Bật `true` không có nghĩa **mọi** bean đều lazy. Một bean lazy vẫn có thể được tạo sớm nếu singleton eager cần inject nó, hoặc hạ tầng framework yêu cầu.
- `@Lazy` áp dụng khởi tạo lười cho một bean/component. `@Lazy(false)` có thể giữ bean quan trọng khởi tạo sớm khi toàn ứng dụng đang bật lazy.
- `ApplicationReadyEvent` và readiness phản ánh mốc vòng đời Spring Boot, **không chứng minh tất cả lazy bean đã được tạo, kiểm tra và làm nóng**.
- Có thể xuất hiện cold latency, CPU spike, tăng RAM sau warm-up và lỗi `BeanCreationException` ở first-use.

| Hành vi | Eager | Lazy |
| --- | --- | --- |
| Startup | Tốn chi phí khởi tạo nhiều bean | Có thể nhanh hơn |
| HTTP request đầu | Nhiều bean đã có | Có thể phải khởi tạo thêm |
| Phát hiện lỗi bean | Nhiều lỗi lộ khi startup | Một số lỗi lộ khi first-use |
| RAM lúc ready | Có thể cao hơn | Có thể thấp tạm thời |
| RAM dưới tải thật | Phụ thuộc hoạt động | Có thể tăng khi bean được tạo |
| Scale-out | Độ trễ khi instance startup | Độ trễ có thể chuyển tới traffic mới |

Lazy **dịch thời điểm phải trả chi phí**, không tự tối ưu hóa code tạo bean, query DB, kết nối hay logic nghiệp vụ.

## 2. Đặt giả thuyết đo lường

Ví dụ giả thuyết tốt:

> Trên cùng artifact, JDK và tài nguyên, bật global lazy giúp giảm thời gian tới `ApplicationReadyEvent` mà không làm cold request, p95/p99, tỷ lệ lỗi, memory, readiness và shutdown vượt tiêu chí chấp nhận.

Trước khi chạy benchmark, xác định:

1. **Mốc tối ưu:** muốn rút ngắn startup của JVM, mốc Spring Boot ready, hay thời gian từ tạo Pod đến khi nhận traffic?
2. **SLO:** latency request đầu tiên, p95/p99, error rate và tỉ lệ readiness thành công cho phép bao nhiêu?
3. **Đường quan trọng:** login, checkout, API chính, report, batch job, queue consumer và feature hiếm dùng nào bắt buộc hoạt động?
4. **Tài nguyên:** RAM, heap, CPU, GC, memory limit trong container và tải tối đa.
5. **Chính sách fail fast:** bean nào phải báo lỗi cấu hình trước khi instance nhận traffic?
6. **Điều kiện rollout/rollback:** khi nào bật cho canary, khi nào dừng và hoàn nguyên?

Không có một phần trăm startup “đạt chuẩn” dùng chung mọi dịch vụ. Hãy dựa vào SLO vận hành và kiểm thử thật.

## 3. Phân biệt các mốc thời gian

~~~text
OS/container khởi chạy JVM
  |
  v
SpringApplication.run
  |
  +-- refresh ApplicationContext
  |
  +-- ApplicationStartedEvent
  |
  +-- ApplicationRunner / CommandLineRunner
  |
  +-- ApplicationReadyEvent
  |
  +-- AvailabilityChangeEvent(ACCEPTING_TRAFFIC)
  |
  +-- readiness probe bên ngoài thành công
  |
  v
Request đầu tiên gọi nhánh chưa warm
  |
  +-- bean lazy được tạo
  |
  v
HTTP response
~~~

| Metric | Ý nghĩa |
| --- | --- |
| `T_started` | Thời gian tới `ApplicationStartedEvent`, trước runners |
| `T_ready` | Thời gian tới `ApplicationReadyEvent`, sau runners |
| `T_probe_ready` | Thời gian từ khi hạ tầng tạo instance tới lúc probe nhận trạng thái sẵn sàng |
| `T_cold_http` | Latency request đầu tiên kích hoạt một nhánh còn lạnh |
| `T_warm_http` | Latency sau warm-up, đo phân bố p50/p95/p99 |
| `T_scale_out` | Từ yêu cầu thêm instance đến lúc nhận traffic hữu ích |

Spring Boot 3.3 có `ApplicationReadyEvent.getTimeTaken()` trả về `Duration`, **hoặc `null` nếu không xác định**. Mẫu listener:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners((ApplicationListener<ApplicationReadyEvent>) event -> {
    Duration taken = event.getTimeTaken();
    System.out.println("READY_MS="
            + (taken == null ? "unknown" : taken.toMillis()));
});
app.run(args);
~~~

Đây là đoạn minh họa, cần lớp cấu hình `MyApplication` và các import tương ứng. Code hoàn chỉnh ở phần 7. Thời gian event **không bao gồm toàn bộ image pull, scheduling, readiness probe và network**.

**Không so sánh `Started` của bản A với `Ready` của bản B.** Nếu mốc đo khác nhau, kết quả không có giá trị đối chứng.

## 4. Thiết kế A/B công bằng

Hai biến thể chỉ khác một cấu hình:

- **A — Baseline:** `spring.main.lazy-initialization=false`.
- **B — Candidate:** `spring.main.lazy-initialization=true`.

Các biến bắt buộc kiểm soát:

| Biến | Cần giữ |
| --- | --- |
| Source code, commit, JAR/image, phiên bản Spring Boot | Giống hệt |
| JDK, JVM args, `-Xms`/`-Xmx`, collector | Giống hệt |
| CPU, RAM limit, storage, OS/container image | Giống hệt |
| Profile và các property ngoài cờ lazy | Giống hệt |
| Cấu hình DB, Redis, HTTP dependencies, dữ liệu thử | Tương đương |
| Tình trạng cache cold/warm, đường traffic | Có mô tả, kiểm soát |
| Công cụ đo, client location và network | Cố định |
| Các endpoint và thứ tự warm-up | Như nhau |

Mỗi **cold run phải dùng JVM mới**. Chạy lặp nhiều vòng, ví dụ 10–20 lần để khảo sát ban đầu nếu phù hợp chi phí, rồi lấy median/độ phân tán và tăng số mẫu khi kết quả còn nhiều nhiễu. Có thể thay đổi thứ tự chạy A/B giữa các vòng để giảm sai lệch thời điểm.

Không xem request thứ hai trên cùng JVM là “cold run thứ hai”: bean singleton đã có thể được tạo.

## 5. Bảng số liệu cần thu

| Metric | Eager | Lazy | Quyết định |
| --- | --- | --- | --- |
| Median `T_ready_ms` | Đo thực tế | Đo thực tế | Lợi ích startup ổn định? |
| `T_probe_ready_ms` | Đo bên ngoài | Đo bên ngoài | Instance vào traffic sớm hơn? |
| First HTTP latency theo endpoint | Đo thực tế | Đo thực tế | Cold penalty có vượt SLO? |
| Warm p50/p95/p99 | Load test | Load test | Tail latency và throughput thay đổi? |
| Concurrent first requests | Tập tải lạnh | Tập tải lạnh | Có chờ bean khởi tạo cùng lúc? |
| RSS lúc ready | OS/container | OS/container | Footprint ban đầu |
| RSS sau warm-up và peak | OS/container | OS/container | Đủ memory limit? |
| Heap, CPU, GC pause | JVM/JFR | JVM/JFR | Có spike tạo object/GC? |
| Startup errors | Log/test | Log/test | Có che giấu lỗi? |
| Lỗi khi đi qua nhánh hiếm | Smoke/soak | Smoke/soak | Có lỗi first-use? |
| Readiness/shutdown | Test | Test | Vận hành an toàn? |

Công thức tính tỷ lệ giảm `T_ready`:

~~~text
100 * (T_ready_eager - T_ready_lazy) / T_ready_eager
~~~

Chỉ áp dụng khi baseline lớn hơn 0 và cùng mốc đo. **Không gọi thời gian một lần `curl` là p99**: p99 là phân vị được tính từ nhiều mẫu request.

## 6. Công cụ đo startup và first-use

### `ApplicationReadyEvent`

Dùng `getTimeTaken()` để đo thời gian Spring Boot tới ready; log theo một key rõ ràng để thu về dashboard. Đừng đồng nhất nó với thời gian Kubernetes cho phép traffic.

### `BufferingApplicationStartup` và Actuator

Để xem Spring startup steps, có thể tạo application bằng:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(2048));
app.run(args);
~~~

Đây là phương án minh họa thay thế đoạn tạo `SpringApplication`, cần import `org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup`.

Nếu có `spring-boot-starter-actuator`, bật endpoint ở môi trường đo:

~~~properties
management.endpoints.web.exposure.include=health,info,startup
~~~

Khi endpoint đã sẵn sàng:

~~~bash
curl -sS http://localhost:8080/actuator/startup
~~~

Trong Spring Boot 3.3, `GET` trả snapshot timeline; `POST` có thể drain buffer. Dung lượng `2048` chỉ là ví dụ và có thể thiếu nếu ứng dụng có nhiều bước startup. Không expose endpoint chẩn đoán công khai trên production.

### JFR, heap và RSS

Java Flight Recorder hỗ trợ phân tích allocation, GC và class loading:

~~~bash
java -XX:StartFlightRecording=filename=trial.jfr,duration=60s \
     -jar build/libs/lazy-measure-demo-1.0.0.jar \
     --spring.main.lazy-initialization=true
~~~

Chạy cùng chế độ profiling trên cả hai biến thể. Có thể kiểm tra thông tin heap JVM bằng:

~~~bash
jcmd <PID> GC.heap_info
~~~

Thay `<PID>` bằng PID thật. Heap **không phải** RSS; cần metrics OS/container để theo dõi tổng bộ nhớ. Đo cả **lúc mới ready, sau warm-up đầy đủ và dưới tải cao** trước khi quyết định giảm memory limit.

### HTTP latency

~~~bash
curl -sS -o /dev/null \
     -w 'HTTP=%{http_code} total=%{time_total}s\n' \
     http://localhost:8080/work
~~~

Dùng `curl` cho một quan sát, còn phân bố p95/p99, concurrency, throughput cần công cụ load test như k6, Gatling hoặc JMeter với kịch bản được chuẩn hóa.

## 7. Dự án chạy được: quan sát bean được tạo ở first-use

Ví dụ **Spring Boot 3.3.13 / Java 17 / Gradle** có bean `SlowService` mô phỏng chi phí tạo khoảng 300 ms. Controller inject `ObjectProvider<SlowService>` để bean chỉ được yêu cầu lúc xử lý `GET /work`.

`Thread.sleep(300)` ở đây là **chi phí nhân tạo phục vụ học tập**, không phải cách tối ưu thật; kết quả benchmark production phải lấy từ service thật.

### Cấu trúc

~~~text
lazy-measure-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/lazymeasure/
│   ├── LazyMeasureApplication.java
│   ├── SlowService.java
│   └── WorkController.java
└── src/test/java/com/example/lazymeasure/
    ├── EagerModeTest.java
    └── LazyModeTest.java
~~~

### `settings.gradle`

~~~groovy
rootProject.name = 'lazy-measure-demo'
~~~

### `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

BOM được khai báo cho cả implementation và testImplementation để dependency không cần tự chỉ định version. Cần Gradle tương thích với plugin Spring Boot 3.3.

### `LazyMeasureApplication.java`

~~~java
package com.example.lazymeasure;

import java.time.Duration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LazyMeasureApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(LazyMeasureApplication.class);

        ApplicationListener<ApplicationReadyEvent> listener = event -> {
            Duration elapsed = event.getTimeTaken();
            System.out.println("MEASURE ready_ms="
                    + (elapsed == null ? "unknown" : elapsed.toMillis()));
        };

        app.addListeners(listener);
        app.run(args);
    }

    @Bean
    SlowService slowService() {
        return new SlowService();
    }
}
~~~

Listener được đăng ký trực tiếp trước `run`, không phụ thuộc vào bean listener có được tạo sớm hay không.

### `SlowService.java`

~~~java
package com.example.lazymeasure;

public final class SlowService {

    public SlowService() {
        System.out.println("MEASURE slow_service_constructor");
        try {
            Thread.sleep(300);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted during demo init", e);
        }
    }

    public String work() {
        return "OK";
    }
}
~~~

### `WorkController.java`

~~~java
package com.example.lazymeasure;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkController {

    private final ObjectProvider<SlowService> provider;

    public WorkController(ObjectProvider<SlowService> provider) {
        this.provider = provider;
    }

    @GetMapping("/work")
    public String work() {
        return provider.getObject().work();
    }
}
~~~

`ObjectProvider` chỉ yêu cầu `SlowService` khi `getObject()` được gọi. Nếu inject `SlowService` trực tiếp vào một controller eager, bean phụ thuộc có thể bị tạo ngay lúc controller được tạo, làm sai lệch tình huống muốn thử.

### Build

~~~bash
./gradlew clean test bootJar
~~~

Trong PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
~~~

Với tên project và version như trên, executable JAR thường là `build/libs/lazy-measure-demo-1.0.0.jar`; kiểm tra file thực nếu dự án có tùy chỉnh.

### Chạy baseline eager

Terminal 1:

~~~bash
java -Xms256m -Xmx512m \
     -jar build/libs/lazy-measure-demo-1.0.0.jar \
     --server.port=8080 \
     --spring.main.lazy-initialization=false
~~~

Sau khi ready, terminal 2:

~~~bash
curl -sS -o /dev/null -w 'A_FIRST=%{time_total}s HTTP=%{http_code}\n' \
     http://localhost:8080/work

curl -sS -o /dev/null -w 'A_WARM=%{time_total}s HTTP=%{http_code}\n' \
     http://localhost:8080/work
~~~

Với eager, marker `MEASURE slow_service_constructor` thường xuất hiện **trước** `MEASURE ready_ms=...`.

### Chạy biến thể lazy

Dừng JVM A hoàn toàn, rồi mở **một JVM mới** cùng artifact, JVM args và cổng:

~~~bash
java -Xms256m -Xmx512m \
     -jar build/libs/lazy-measure-demo-1.0.0.jar \
     --server.port=8080 \
     --spring.main.lazy-initialization=true
~~~

Sau ready:

~~~bash
curl -sS -o /dev/null -w 'B_FIRST=%{time_total}s HTTP=%{http_code}\n' \
     http://localhost:8080/work

curl -sS -o /dev/null -w 'B_WARM=%{time_total}s HTTP=%{http_code}\n' \
     http://localhost:8080/work
~~~

Với lazy, marker constructor thường xuất hiện **sau** ready, khi request đầu gọi `getObject()`. Cả hai mode, khi thành công, endpoint trả HTTP 200 với body:

~~~text
OK
~~~

Không có con số `ready_ms` hoặc latency cố định: JVM, hạ tầng, tài nguyên và overhead ảnh hưởng thời gian thật. Đừng lấy mức sleep 300 ms làm kết quả thực nghiệm production.

**Windows PowerShell 5.1:** `curl` có thể là alias; dùng `curl.exe`. Không trộn cách escape của shell khi viết script thu thập metric chính thức.

## 8. Kiểm thử tự động cả eager và lazy

`@SpringBootTest` giúp xác minh chức năng, nhưng không phải benchmark cold startup JAR. Hai test sau dùng JUnit 5 và `spring-boot-starter-test` đã có trong build.

### `EagerModeTest.java`

~~~java
package com.example.lazymeasure;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.main.lazy-initialization=false")
class EagerModeTest {
    @Autowired
    TestRestTemplate rest;

    @Test
    void firstAndWarmRequestsWork() {
        assertEquals("OK", rest.getForObject("/work", String.class));
        assertEquals("OK", rest.getForObject("/work", String.class));
    }
}
~~~

### `LazyModeTest.java`

~~~java
package com.example.lazymeasure;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.main.lazy-initialization=true")
class LazyModeTest {
    @Autowired
    TestRestTemplate rest;

    @Test
    void firstAndWarmRequestsWork() {
        assertEquals("OK", rest.getForObject("/work", String.class));
        assertEquals("OK", rest.getForObject("/work", String.class));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Các test xác nhận endpoint trả đúng kết quả ở hai mode. Chúng **không chứng minh startup nhanh hay p99 đạt chuẩn**, vì test context caching, Gradle/JUnit và JVM test khác môi trường chạy JAR thật. Tránh inject trực tiếp `SlowService` vào test nếu muốn quan sát bean chưa khởi tạo trước request, vì chính test có thể buộc nó tạo sớm.

## 9. Lỗi cấu hình có thể chỉ xuất hiện ở first-use

Một bean critical bị thiếu property, dependency hoặc cấu hình có thể fail khi eager khởi động, nhưng bị hoãn khi lazy. Ví dụ khái niệm:

~~~text
Bean required partner API credentials
  Eager: bean được tạo lúc refresh -> phát hiện thiếu config -> startup FAIL
  Lazy: context READY -> request đầu cần bean -> phát hiện thiếu config -> request FAIL
~~~

Không phải mọi lỗi đều bị hoãn: lỗi trong `Environment`, initializer, migration hoặc hạ tầng bắt buộc khởi tạo sớm vẫn có thể làm startup fail ngay.

### Kịch bản thử có kiểm soát

1. Trong staging, cố ý bỏ một thuộc tính bắt buộc của bean có đường truy cập rõ ràng.
2. Khởi động eager và ghi nhận lúc lỗi xuất hiện.
3. Khởi động lazy; nếu app ready, chủ động **gọi đúng nhánh dùng bean đó**.
4. Kiểm tra exception, HTTP status, log có lộ secret không, readiness có bảo vệ traffic chưa.
5. Khôi phục cấu hình đúng và lặp lại hai mode.

Nếu bean **bắt buộc phải đúng trước khi nhận traffic**, cân nhắc `@Lazy(false)` cho bean đó hoặc kiểm tra trước readiness bằng một bước khởi động có chủ đích.

Ví dụ bean giữ eager khi global lazy:

~~~java
@Component
@Lazy(false)
public class CriticalConfigValidator {
    public CriticalConfigValidator() {
        // Kiểm tra cấu hình cục bộ bắt buộc.
    }
}
~~~

Đây là mã minh họa cần import `org.springframework.stereotype.Component` và `org.springframework.context.annotation.Lazy`. Tránh I/O dài trong constructor; dùng runner hoặc readiness check phù hợp nếu cần kiểm tra phụ thuộc ngoài.

## 10. Readiness và auto-scaling

Spring Boot phát `ApplicationReadyEvent` sau các runner, rồi công bố `ReadinessState.ACCEPTING_TRAFFIC`. Nhưng với lazy, instance có thể báo ready khi một số bean quan trọng **chưa được tạo hoặc chưa được thử**.

~~~text
Kubernetes/Autoscaler thêm instance
  -> app đạt ready nhanh
  -> instance nhận traffic
  -> nhiều request đầu kích hoạt bean lazy
  -> CPU/GC spike, latency cao hoặc lỗi init
  -> request sau mới warm
~~~

Thử **một instance mới dưới tải thật**, không chỉ test startup trên máy nhàn rỗi. Đo concurrent cold requests và p95/p99 trong giai đoạn scale-out. Một singleton lazy tạo một lần nhưng nhiều request có thể cùng chờ tạo bean, khiến tail latency tăng.

Actuator readiness probe, nếu được cấu hình:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

không tự khởi tạo tất cả bean nghiệp vụ. Nếu dùng warm-up, thực hiện trước khi cho traffic đến và tránh side effect không idempotent (thanh toán, xóa dữ liệu, gửi email thật). Hoặc giữ đường critical eager để sẵn sàng trước readiness.

## 11. Bộ nhớ phải đo sau warm-up

Lazy có thể giảm RAM lúc vừa ready do còn nhiều bean chưa tạo, nhưng RAM sau khi đủ các đường được dùng có thể quay lại gần mức eager. Thu ba mốc:

1. Ngay sau ready, khi chưa gọi traffic nghiệp vụ.
2. Sau khi đi qua toàn bộ nhánh quan trọng để warm-up.
3. Dưới tải ổn định và đỉnh tải.

Đo heap used/committed, RSS, allocation và GC pause. Heap không bằng tổng RSS. Không giảm `-Xmx` hoặc container memory limit dựa trên một ảnh chụp lúc ready. Khi một đợt traffic tạo đồng loạt nhiều lazy bean, allocation/GC có thể tăng nhanh.

## 12. Checklist kiểm thử trước production

| Tầng | Cần làm | Điều kiện |
| --- | --- | --- |
| Unit/integration | Test ở cả hai mode, dependency/config/profile | Đúng chức năng |
| Startup smoke | Chạy JAR/image thật, đo ready/probe | Không lỗi |
| First-use paths | Gọi endpoint, job, consumer hiếm dùng | Không lỗi init/cold SLO |
| Failure injection | Thiếu/sai config của bean critical | Lỗi được phát hiện phù hợp |
| Load/soak | Cold concurrency, p95/p99, memory/GC | Trong giới hạn |
| Staging | JDK/image/probes giống production | Kết quả lặp lại |
| Canary | Tỉ lệ instance/traffic nhỏ có nhãn riêng | Alerts/metrics đạt |
| Rollback drill | Trở về eager, kiểm tra kết quả | Không gián đoạn bất thường |

Những đường cần kiểm thử thường bị bỏ sót: login, persistence/transaction, Redis, HTTP client, scheduled job, queue listener, serializer, feature flag, report export và shutdown. Một endpoint hoạt động không chứng minh mọi bean lazy của ứng dụng hoạt động.

## 13. Quy tắc triển khai và rollback

**Chấp nhận** khi startup cải thiện có ý nghĩa trong phép đo lặp, không lỗi cấu hình bị che, cold/warm latency và resource đạt SLO, readiness và shutdown hoạt động trong load test và canary.

**Điều chỉnh** khi startup tốt nhưng một số đường cold quá chậm: dùng `@Lazy(false)` cho bean critical, warm-up an toàn trước readiness hoặc lazy chọn lọc, rồi đo lại.

**Từ chối hoặc rollback** nếu phát sinh lỗi first-use, p99/5xx tăng, vượt memory limit, autoscaling gây nghẽn, hoặc readiness cho traffic khi chức năng bắt buộc chưa hoạt động.

Rollback cấu hình:

~~~properties
spring.main.lazy-initialization=false
~~~

rồi triển khai/khởi động lại JVM. Thay property trong tiến trình đang chạy **không làm các bean đã khởi tạo trở về trạng thái chưa tạo**. Chuẩn bị dashboard tách eager/canary lazy, ngưỡng rollback và cách drain traffic trước khi đưa canary vào production.

## 14. Sai lầm phổ biến

- **Chỉ đo startup một lần:** nhiễu CPU/cache/JIT/network/GC làm kết quả không ổn định.
- **So sánh sai mốc:** `ApplicationStartedEvent` không phải `ApplicationReadyEvent`.
- **Gọi vài request warm rồi tưởng đã đo cold:** cần JVM mới cho mỗi cold sample.
- **Dùng một `curl` làm p99:** cần phân bố mẫu và load generator.
- **Chỉ kiểm tra health xanh:** bean lazy nghiệp vụ có thể vẫn chưa tạo.
- **Bỏ qua lỗi bean tạo muộn:** startup pass nhưng request đầu fail.
- **Không test concurrent cold:** nhiều request có thể cùng chờ bean creation.
- **Không chạy job/queue trong test:** bean chỉ bị yêu cầu nhiều giờ sau startup.
- **Hạ memory limit quá sớm:** RAM tăng sau warm-up.
- **Cho rằng mọi bean đều lazy:** singleton eager phụ thuộc và hạ tầng có thể ép tạo sớm.
- **Dùng thời gian `gradle test` để so startup JAR:** môi trường test khác production.
- **Không có rollback:** phát hiện lỗi khi đã nhận traffic nhưng khó khôi phục.
- **Expose endpoint startup diagnostic công khai:** dữ liệu khởi động có thể tiết lộ cấu trúc nội bộ.

## 15. Tự kiểm tra

1. **Mặc định `spring.main.lazy-initialization` là gì?** `false`.
2. **Lazy có loại bỏ chi phí tạo bean không?** Không, chủ yếu dời sang lần yêu cầu.
3. **Bean đánh dấu lazy có thể vẫn tạo lúc startup không?** Có nếu bean eager khác hoặc framework cần nó.
4. **`ApplicationReadyEvent` chứng minh tất cả bean đã sẵn sàng chưa?** Không.
5. **Ngoài `T_ready` cần đo gì?** Cold/warm latency, p95/p99, errors, memory/GC, readiness và concurrency.
6. **Vì sao đo cold cần JVM mới?** Singleton có thể đã được tạo sau lần dùng đầu.
7. **Có thể lấy một request làm p99 không?** Không.
8. **Nếu lỗi config của bean lazy xuất hiện ở first-use, làm sao phòng vệ?** Test nhánh đó, warm-up trước readiness hoặc giữ bean critical eager.
9. **RSS lúc ready thấp có nghĩa đủ RAM production?** Không; đo sau warm và peak.
10. **`/actuator/startup` cần gì?** `BufferingApplicationStartup` và Actuator được bật/expose phù hợp.
11. **Lazy luôn tốt cho autoscaling?** Không; cold instance có thể chậm khi nhận traffic.
12. **Rollback cờ lazy thế nào?** Khởi động mới với `spring.main.lazy-initialization=false`.
13. **Tại sao kiểm thử scheduled jobs?** Bean lazy có thể chỉ được tạo khi job đầu chạy.
14. **Vì sao phải giữ điều kiện A/B giống nhau?** Để chênh lệch có thể quy cho lazy thay vì CPU/JDK/cấu hình.

**Kết luận:** Quyết định bật lazy initialization phải dựa trên **phép đo A/B cùng điều kiện**, **request lạnh trên JVM mới**, **kiểm thử first-use mọi nhánh quan trọng**, **RAM sau warm-up**, **readiness dưới tải** và **canary có rollback**. Chỉ rút ngắn startup mà đẩy lỗi hoặc tail latency sang người dùng không phải là tối ưu vận hành thành công.

### Tài liệu tham khảo

- Spring Boot 3.3 — `SpringApplication` (Lazy Initialization, Application Events, Application Startup tracking): https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — `ApplicationReadyEvent.getTimeTaken()` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Boot 3.3.13 — Actuator startup endpoint: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html
- Spring Boot 3.3 — Actuator endpoints/probes: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Framework 6.1 — `@Lazy` API: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/annotation/Lazy.html
- Spring Framework 6.1 — Lazy Beans: https://docs.spring.io/spring-framework/reference/6.1/core/beans/dependencies/factory-lazy-init.html
- Spring Boot 3.3 — Gradle managing dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
