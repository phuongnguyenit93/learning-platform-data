# So sánh reactive với MVC hoặc luồng ảo trên cùng tải thực tế

## 1. Mục tiêu và câu hỏi cần trả lời

Spring MVC, Spring MVC chạy với virtual threads và Spring WebFlux đều có thể phục vụ HTTP API trong Java. Mỗi mô hình tổ chức việc chờ I/O, sử dụng thread, điều phối công việc và truyền dữ liệu theo cách khác nhau. Không có kết luận chung rằng reactive luôn nhanh hơn MVC, virtual threads luôn thay thế WebFlux, hoặc một framework có throughput cao nhất cho mọi workload.

Bài học này xây dựng cách so sánh có thể lặp lại và giải thích được:
- So sánh ba phương án trên cùng một workload và cùng giới hạn tài nguyên.
- Phân biệt I/O-bound, CPU-bound và workload hỗn hợp.
- Giữ nguyên dependency, dữ liệu, payload, timeout, connection pool và tải gửi vào.
- Đo throughput, p50/p95/p99 latency, error rate, CPU, heap/direct memory, GC, thread, connection và queue.
- Dùng load generator theo offered arrival rate thay vì chỉ gửi request theo vòng lặp phụ thuộc response.
- Phân tích kết quả ở điểm bão hòa và xác định bottleneck thật.
- Viết project mẫu Spring Boot có ba ứng dụng riêng: MVC với platform threads, MVC với virtual threads và WebFlux.
- Biết khi nào nên chọn từng mô hình, khi nào cần benchmark bổ sung và khi nào số liệu chưa đủ để ra quyết định.

**Ba mô hình được so sánh:**

| Mô hình | Cách xử lý request | Khi chờ I/O |
| --- | --- | --- |
| Spring MVC + platform threads | Servlet request được xử lý trên platform thread của server | Thread request thường bị giữ trong lúc chờ blocking I/O |
| Spring MVC + virtual threads | MVC/Servlet programming model, dùng virtual threads theo cấu hình/runtime hỗ trợ | Virtual thread có thể unmount khi blocking I/O phù hợp, giải phóng carrier |
| Spring WebFlux + Reactor Netty | Non-blocking handler và Reactive Streams | Event-loop không bị block; pipeline tiếp tục khi I/O có signal |

Virtual threads là mô hình threading, không phải web framework riêng. WebFlux là reactive web stack. Hai lựa chọn giải quyết các vấn đề khác nhau và có thể cùng xuất hiện trong một hệ thống ở những ranh giới phù hợp.

## 2. Hiểu đúng ba mô hình

### 2.1. Spring MVC với platform threads

Spring MVC dựa trên Servlet API. Trong mô hình request-per-thread truyền thống, một request thường chiếm một server worker thread trong lúc controller thực hiện công việc. Nếu controller gọi JDBC đồng bộ, đọc file hoặc gọi HTTP blocking, thread đó sẽ chờ I/O hoàn tất.

Ưu điểm:
- Lập trình tuần tự, dễ đọc, dễ debug bằng stack trace.
- Hệ sinh thái Servlet, filter, security, transaction, JDBC và thư viện đồng bộ phong phú.
- Dễ tích hợp với dependency blocking sẵn có.
- Với tải vừa phải hoặc CPU-bound, mô hình này có thể đạt hiệu năng rất tốt và đơn giản.

Giới hạn:
- Platform threads có chi phí stack/native resources cao hơn virtual threads.
- Thread pool có giới hạn; khi request chờ I/O lâu, worker bị giữ và request mới có thể xếp hàng.
- Tăng thread count vô hạn không phải giải pháp vì hệ điều hành, memory và scheduler có giới hạn.
- Một dependency chậm có thể giữ thread lâu hơn thời gian CPU thực sự cần.

### 2.2. Spring MVC với virtual threads

Virtual thread là một đối tượng Thread do JVM quản lý, được schedule trên một số lượng platform carrier threads nhỏ hơn. Khi virtual thread thực hiện một số thao tác blocking I/O được JDK hỗ trợ, nó có thể unmount khỏi carrier trong lúc chờ; carrier có thể chạy virtual thread khác.

Mô hình này giữ code đồng bộ:

```java
String result = restClient.get()
        .uri("/remote")
        .retrieve()
        .body(String.class);
```

Thread request có thể chờ I/O mà không giữ một platform thread trong nhiều tình huống. Điều này hữu ích cho ứng dụng thread-per-request với nhiều request đồng thời và phần lớn thời gian chờ I/O.

Điều virtual threads không làm:
- Không làm một phép tính CPU chạy nhanh hơn.
- Không tăng số CPU cores.
- Không làm database, downstream API hoặc connection pool có thêm capacity.
- Không tự giới hạn số request đồng thời tới dependency.
- Không loại bỏ nhu cầu timeout, bulkhead, rate limit, backpressure hoặc giới hạn queue.
- Không biến một API blocking thành non-blocking; code vẫn có semantics đồng bộ.

Java 21+ mới có virtual threads; Spring Boot 3.5 bật hỗ trợ bằng:

```properties
spring.threads.virtual.enabled=true
```

Spring Boot 3.5 khuyến nghị Java 24+ để có trải nghiệm tốt hơn, nhưng Java 21+ là điều kiện tối thiểu. Dùng cùng JDK, cùng bản cập nhật và cùng cấu hình JVM cho cả ba ứng dụng trong benchmark.

Virtual threads là daemon threads. Với ứng dụng cần bảo đảm JVM tiếp tục chạy khi chỉ còn virtual threads, Spring Boot khuyến nghị:

```properties
spring.main.keep-alive=true
```

Với embedded Tomcat hoặc Jetty được hỗ trợ, Spring Boot có thể cấu hình virtual threads cho xử lý request. Xác minh server implementation và thread runtime thực tế; không suy ra chỉ từ property. Property này không biến Reactor Netty event-loop của WebFlux thành virtual threads.

### 2.3. Spring WebFlux với Reactor

WebFlux hỗ trợ non-blocking I/O và Reactive Streams backpressure. Trên Reactor Netty, một số event-loop threads phục vụ nhiều connection; khi I/O chưa sẵn sàng, event loop có thể xử lý công việc khác thay vì giữ một thread riêng cho mỗi request đang chờ.

Controller có thể compose kết quả bất đồng bộ:

```java
@GetMapping("/work")
public Mono<String> work() {
    return webClient.get()
            .uri("/remote")
            .retrieve()
            .bodyToMono(String.class);
}
```

Điều kiện để mô hình này có lợi:
- Phần lớn đường đi request phải non-blocking.
- Dùng reactive HTTP client, R2DBC hoặc driver reactive phù hợp.
- Không block event-loop bằng JDBC, Thread.sleep, I/O blocking hoặc CPU task kéo dài.
- Quản lý demand, prefetch, concurrency và buffer.
- Xử lý cancellation, timeout, error và resource cleanup đúng lifecycle.

Nếu gọi block() hoặc chạy JDBC trực tiếp trên event-loop, một thread có thể bị giữ và ảnh hưởng nhiều request khác. Với legacy blocking API, có thể cô lập trên Schedulers.boundedElastic() hoặc một executor được giới hạn, nhưng đó là giải pháp tích hợp blocking chứ không phải đường đi fully non-blocking.

### 2.4. WebFlux không bắt buộc dùng Netty

WebFlux có thể chạy trên Reactor Netty và một số Servlet containers. Spring MVC và WebFlux có thể cùng tồn tại, nhưng Spring Boot chọn MVC nếu cả spring-boot-starter-web và spring-boot-starter-webflux cùng có mặt trên classpath theo cơ chế auto-detection thông thường.

Vì vậy, một benchmark có MVC/Tomcat và WebFlux/Netty thực chất đang so sánh hai stack triển khai hoàn chỉnh, gồm framework, server connector và cấu hình runtime. Nếu muốn cô lập riêng ảnh hưởng của programming model, cần kiểm soát hoặc thay đổi server connector có chủ đích, và báo cáo rõ setup.

## 3. Workload quyết định kết quả

Không nên chạy một benchmark rồi tuyên bố mô hình đó tốt hơn cho mọi ứng dụng. Ít nhất cần phân biệt ba workload.

### 3.1. I/O-bound: chờ downstream

Ví dụ request:
1. Nhận HTTP request.
2. Gọi một downstream API có latency 50–200 ms.
3. Chờ response.
4. Serialize payload nhỏ và trả kết quả.

Đây là trường hợp platform thread có thể bị giữ trong thời gian chờ; virtual threads có thể tăng số tác vụ chờ đồng thời; WebFlux có thể dùng ít event-loop threads hơn nếu toàn bộ chuỗi non-blocking.

Đây là workload phù hợp để so sánh khả năng mở rộng khi nhiều request đang chờ I/O.

### 3.2. CPU-bound: tính toán

Ví dụ:
- Hash/encode.
- Tính toán dữ liệu.
- Nén ảnh.
- Chạy thuật toán thuần CPU.
- Chuyển đổi object lớn.

CPU-bound bị giới hạn chủ yếu bởi CPU cores, thuật toán, allocation và memory bandwidth. Virtual threads không tạo thêm CPU. Reactive operator cũng không làm phép tính CPU tự nhanh hơn.

Khi đo CPU-bound, dùng cùng hàm tính toán, cùng input, cùng số iteration và cùng số core. Với WebFlux, tránh chạy một phép tính dài trực tiếp trên event-loop; có thể dùng scheduler CPU phù hợp, nhưng cần ghi rõ scheduler overhead và số worker.

### 3.3. Mixed workload

Ứng dụng thực tế thường vừa chờ DB/HTTP vừa serialize, validate, authorize và tính toán. Đây là workload quan trọng nhất để ra quyết định production.

Hãy đo riêng:
- Thời gian chờ dependency.
- Thời gian CPU của ứng dụng.
- Connection pool wait.
- Queue wait.
- Serialization/deserialization.
- Thời gian response body được tiêu thụ.

Nếu chỉ đo tổng latency, có thể nhầm database bottleneck với thread model.

## 4. Nguyên tắc so sánh công bằng

### 4.1. Cố định các biến đầu vào

| Biến | Cần giữ giống nhau |
| --- | --- |
| Hardware | Cùng CPU model/core, RAM, NUMA/host nếu có thể |
| Container | Cùng CPU quota, memory limit và container runtime |
| JDK | Cùng vendor, major/minor/update và JVM flags |
| Framework | Cùng Spring Boot/Spring Framework version |
| Payload | Cùng request size, response size, schema và compression |
| Workload | Cùng endpoint semantics, business logic và input distribution |
| Dependency | Cùng downstream/database, dữ liệu và latency |
| Connection | Ghi rõ max connection, pool, keep-alive và protocol |
| Security | Cùng authentication/authorization hoặc tắt có chủ đích cho tất cả |
| Logging | Cùng mức log; tránh debug/trace trong một variant |
| Metrics | Cùng instrumentation và cardinality |
| Timeouts | Cùng connect/read/overall deadline |
| Load generator | Cùng host, script, arrival rate và duration |

Không benchmark ba server trên cùng một máy trong cùng thời điểm nếu chúng cạnh tranh CPU/memory. Chạy từng variant riêng biệt trên cùng môi trường và lặp lại nhiều lượt.

### 4.2. Tách hai câu hỏi benchmark

**Câu hỏi A — So sánh end-to-end stack:** MVC/Tomcat/platform, MVC/Tomcat/virtual, WebFlux/Netty. Đây là câu hỏi thực tế khi chọn stack triển khai. Kết quả bao gồm cả khác biệt connector và framework.

**Câu hỏi B — So sánh programming model:** cố gắng giữ server, protocol, dependency và workload giống nhau; chỉ thay cách xử lý request/threads. Câu hỏi này khó hơn và có thể cần nhiều cấu hình server. Không trộn kết quả của A và B thành một kết luận.

### 4.3. Cùng dependency, không chỉ cùng thời gian giả lập

Nếu mục tiêu là I/O-bound, ưu tiên một downstream service chung:
- Cùng endpoint.
- Cùng payload.
- Cùng latency distribution.
- Cùng connection reuse.
- Cùng HTTP version.
- Cùng timeout.
- Cùng số connection hoặc ghi rõ khác biệt client connector.

Một Thread.sleep(100) trong MVC và Mono.delay(100ms) trong WebFlux chỉ mô phỏng thời gian chờ; nó không kiểm tra network, connection pool, HTTP client, DNS, TLS hoặc database. Dùng synthetic wait cho một bài test scheduling riêng, không thay cho benchmark end-to-end.

## 5. Thiết kế benchmark I/O-bound dùng chung downstream

Mẫu dưới đây dùng ba ứng dụng riêng. Cả ba expose GET /work; mỗi request gọi một WebFlux stub ở cổng 9090, stub trả cùng payload sau một khoảng delay. Hai ứng dụng MVC gọi cùng WebClient rồi block trong request thread; ứng dụng WebFlux trả Mono mà không block.

Thiết kế này giữ outbound client library/connector giống nhau, đồng thời thay đổi cách inbound request được xử lý. Nó đo end-to-end request handling của ba biến thể trong workload I/O-bound, không phải một benchmark thuần túy chỉ đo event loop.

### 5.1. Cấu trúc project

```text
web-stack-benchmark/
  settings.gradle
  build.gradle
  stub/
    build.gradle
    src/main/java/demo/stub/StubApplication.java
    src/main/java/demo/stub/DelayController.java
  mvc-platform/
    build.gradle
    src/main/resources/application.properties
    src/main/java/demo/mvcplatform/MvcPlatformApplication.java
    src/main/java/demo/mvcplatform/WorkController.java
  mvc-virtual/
    build.gradle
    src/main/resources/application.properties
    src/main/java/demo/mvcvirtual/MvcVirtualApplication.java
    src/main/java/demo/mvcvirtual/WorkController.java
  webflux/
    build.gradle
    src/main/resources/application.properties
    src/main/java/demo/webflux/WebFluxApplication.java
    src/main/java/demo/webflux/WorkController.java
  load/
    k6-work.js
```

### 5.2. settings.gradle

```groovy
rootProject.name = 'web-stack-benchmark'

include 'stub'
include 'mvc-platform'
include 'mvc-virtual'
include 'webflux'
```

### 5.3. build.gradle ở thư mục gốc

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.6' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}

allprojects {
    group = 'demo'
    version = '1.0.0'

    repositories {
        mavenCentral()
    }
}

subprojects {
    apply plugin: 'java'
    apply plugin: 'org.springframework.boot'
    apply plugin: 'io.spring.dependency-management'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    dependencies {
        testImplementation 'org.springframework.boot:spring-boot-starter-test'
    }

    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }
}
```

Mỗi module thêm dependency riêng trong build.gradle của nó:

| Module | Dependency bổ sung |
| --- | --- |
| stub | spring-boot-starter-webflux, spring-boot-starter-actuator |
| mvc-platform | spring-boot-starter-web, spring-boot-starter-webflux, spring-boot-starter-actuator |
| mvc-virtual | spring-boot-starter-web, spring-boot-starter-webflux, spring-boot-starter-actuator |
| webflux | spring-boot-starter-webflux, spring-boot-starter-actuator |

Trong hai MVC module, starter-webflux chỉ cung cấp WebClient; do có starter-web, Spring Boot chọn MVC application type theo auto-detection thông thường. Không dùng cùng classpath đó để kỳ vọng profile tự chuyển sang Netty/WebFlux server.

Ví dụ build.gradle cho module stub:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Với mvc-platform và mvc-virtual:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Với webflux:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

### 5.4. Stub dùng chung

Tệp stub/src/main/resources/application.properties:

```properties
server.port=9090
spring.application.name=benchmark-stub
management.endpoints.web.exposure.include=health,metrics
```

Tệp DelayController.java:

```java
package demo.stub;

import java.time.Duration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DelayController {

    @GetMapping("/delay")
    public Mono<String> delay(
            @RequestParam(defaultValue = "100") long ms) {
        if (ms < 0 || ms > 2000) {
            return Mono.error(
                    new IllegalArgumentException("ms out of range"));
        }
        return Mono.delay(Duration.ofMillis(ms))
                .thenReturn("OK");
    }
}
```

StubApplication.java:

```java
package demo.stub;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StubApplication {

    public static void main(String[] args) {
        SpringApplication.run(StubApplication.class, args);
    }
}
```

Stub dùng chung trả body OK sau 100 ms mặc định. Nó là một dependency giả lập có network thật giữa process, nhưng không phải database hoặc hệ thống downstream production. Cần đo CPU, connections và latency của stub để chắc chắn stub không trở thành bottleneck.

### 5.5. MVC với platform threads

Tệp mvc-platform/src/main/resources/application.properties:

```properties
spring.application.name=mvc-platform
server.port=8080
spring.threads.virtual.enabled=false
benchmark.stub.base-url=http://127.0.0.1:9090
management.endpoints.web.exposure.include=health,metrics
```

MvcPlatformApplication.java:

```java
package demo.mvcplatform;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcPlatformApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MvcPlatformApplication.class, args);
    }
}
```

WorkController.java:

```java
package demo.mvcplatform;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ClientConfiguration {

    @Bean
    WebClient benchmarkClient() {
        return WebClient.builder()
                .baseUrl("http://127.0.0.1:9090")
                .build();
    }
}

@RestController
class WorkController {

    private final WebClient client;

    WorkController(WebClient client) {
        this.client = client;
    }

    @GetMapping("/work")
    String work() {
        return client.get()
                .uri("/delay?ms=100")
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(2));
    }
}
```

Controller dùng MVC request thread và block tối đa hai giây để lấy response từ cùng WebClient. Đây là cách cố ý tạo workload blocking ở request thread để đo platform-thread behavior.

### 5.6. MVC với virtual threads

Tệp mvc-virtual/src/main/resources/application.properties:

```properties
spring.application.name=mvc-virtual
server.port=8080
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
benchmark.stub.base-url=http://127.0.0.1:9090
management.endpoints.web.exposure.include=health,metrics
```

MvcVirtualApplication.java:

```java
package demo.mvcvirtual;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcVirtualApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MvcVirtualApplication.class, args);
    }
}
```

WorkController.java có cùng logic với module mvc-platform, đổi package thành demo.mvcvirtual:

```java
package demo.mvcvirtual;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ClientConfiguration {

    @Bean
    WebClient benchmarkClient() {
        return WebClient.builder()
                .baseUrl("http://127.0.0.1:9090")
                .build();
    }
}

@RestController
class WorkController {

    private final WebClient client;

    WorkController(WebClient client) {
        this.client = client;
    }

    @GetMapping("/work")
    String work() {
        return client.get()
                .uri("/delay?ms=100")
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(2));
    }
}
```

Điểm khác của module này là runtime/server executor được cấu hình để dùng virtual threads qua Spring Boot. Controller vẫn là synchronous MVC; outbound WebClient vẫn là cùng client/connector và request thread chờ bằng block.

**Kiểm tra trước benchmark:** xác nhận server thực tế đang sử dụng virtual threads trong môi trường đang chạy; không chỉ dựa vào property file. Ghi lại JDK, Spring Boot, embedded server version và thread names/JFR. Nếu server/connector hoặc custom executor không hỗ trợ virtual thread integration như kỳ vọng, kết quả không phải benchmark MVC virtual threads.

### 5.7. WebFlux

Tệp webflux/src/main/resources/application.properties:

```properties
spring.application.name=webflux
server.port=8080
benchmark.stub.base-url=http://127.0.0.1:9090
management.endpoints.web.exposure.include=health,metrics
```

WebFluxApplication.java:

```java
package demo.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                WebFluxApplication.class, args);
    }
}
```

WorkController.java:

```java
package demo.webflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Configuration
class ClientConfiguration {

    @Bean
    WebClient benchmarkClient() {
        return WebClient.builder()
                .baseUrl("http://127.0.0.1:9090")
                .build();
    }
}

@RestController
class WorkController {

    private final WebClient client;

    WorkController(WebClient client) {
        this.client = client;
    }

    @GetMapping("/work")
    Mono<String> work() {
        return client.get()
                .uri("/delay?ms=100")
                .retrieve()
                .bodyToMono(String.class)
                .timeout(java.time.Duration.ofSeconds(2));
    }
}
```

WebFlux trả Mono<String> và không block event-loop. Deadline hai giây được đặt ở publisher. Hai module MVC dùng block(Duration.ofSeconds(2)); cả ba có cùng ngân sách thời gian ở tầng ứng dụng, nhưng exception mapping của blocking timeout và reactive timeout có thể khác. Trong benchmark cần ghi nhận error/status mapping nhất quán.

### 5.8. Chạy từng biến thể

Khởi động stub một lần:

```bash
./gradlew :stub:bootRun
```

Trong terminal riêng, chỉ chạy một ứng dụng benchmark tại một thời điểm:

```bash
./gradlew :mvc-platform:bootRun
```

Hoặc:

```bash
./gradlew :mvc-virtual:bootRun
```

Hoặc:

```bash
./gradlew :webflux:bootRun
```

Các ứng dụng dùng cùng port 8080 nên phải dừng variant trước khi chạy variant kế tiếp. Stub tiếp tục lắng nghe tại 9090.

Kiểm tra readiness trước khi load:

```bash
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/work
```

Response body mong đợi của /work là:

```text
OK
```

Không chạy k6 trước khi ứng dụng và stub đã sẵn sàng. Không tính thời gian startup/JIT warmup vào steady-state measurement.

## 6. Load generator theo offered arrival rate

### 6.1. Vì sao nên dùng constant-arrival-rate?

Một test closed-loop gửi request mới sau khi response trước hoàn tất sẽ tự giảm offered load khi server chậm. Khi hệ thống bão hòa, generator có thể gửi ít request hơn và làm latency nhìn có vẻ thấp hơn so với tải người dùng thực sự muốn tạo.

Một arrival-rate scenario cố định cho phép đặt số request bắt đầu mỗi giây. Theo dõi dropped_iterations: nếu load generator không tạo đủ iteration, bài test không đạt offered rate đã định và kết quả không thể so sánh như dự kiến.

### 6.2. k6 script

Tệp load/k6-work.js:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady_load: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 200,
      maxVUs: 1000
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500']
  }
};

export default function () {
  const response = http.get(__ENV.BASE_URL + '/work');

  check(response, {
    'HTTP 200': r => r.status === 200,
    'body is OK': r => r.body === 'OK'
  });
}
```

Rate 200 request/second và threshold p95 500 ms chỉ là giá trị khởi đầu minh họa, không phải kết quả hay SLO phổ quát. Điều chỉnh rate theo capacity dự kiến, latency của dependency và khả năng của load generator.

Chạy:

```bash
k6 run -e BASE_URL=http://127.0.0.1:8080 load/k6-work.js
```

Để tìm điểm bão hòa, tăng arrival rate theo các stage riêng, ví dụ 50, 100, 200, 400, 800 request/second. Mỗi stage cần đủ thời gian ổn định và measurement. Dừng khi error rate/latency vượt ngưỡng hoặc tài nguyên chạm giới hạn an toàn.

### 6.3. Load generator phải đủ mạnh

- Chạy load generator trên máy/container khác với server nếu có thể.
- Theo dõi CPU, memory và network của máy chạy k6.
- Theo dõi dropped_iterations và số VU thực tế.
- Không tăng maxVUs vô hạn để che việc generator không đủ capacity.
- Cố định version k6, script, seed/input và test duration.
- Không chạy ba server benchmark đồng thời trên cùng host trừ khi mục tiêu là đo cạnh tranh tài nguyên.

## 7. Những metric phải ghi lại

### 7.1. Chất lượng phục vụ

| Metric | Trả lời câu hỏi |
| --- | --- |
| Throughput (completed req/s) | Hệ thống hoàn tất bao nhiêu request mỗi giây? |
| Offered arrival rate | Load generator cố gắng gửi bao nhiêu request mỗi giây? |
| p50 latency | Request điển hình mất bao lâu? |
| p95/p99 latency | Tail latency có xấu khi tải cao không? |
| Error rate | Có bao nhiêu request lỗi/timeout? |
| Dropped iterations | Generator có gửi đủ tải yêu cầu không? |
| Active requests | Có bao nhiêu request đang xử lý? |

Không chỉ nhìn throughput. Một server đạt nhiều request/second nhưng p99 tăng mạnh và error rate cao có thể không đáp ứng SLA.

### 7.2. CPU và memory

- CPU utilization theo process/container.
- Heap used/committed và allocation rate.
- Direct/native memory, đặc biệt với Netty.
- GC count, pause time, allocation pressure và promotion.
- RSS/container memory.
- Context switch và runnable thread.
- JFR allocation/lock/I/O profile.

WebFlux có thể dùng ít request threads hơn nhưng vẫn có heap/direct buffer, event-loop và queue. Virtual threads giảm chi phí platform thread khi chờ I/O nhưng mỗi virtual thread vẫn có stack/state và có thể tiêu thụ memory nếu số lượng đồng thời rất lớn.

### 7.3. Thread và queue

Với MVC platform:
- Tomcat busy/current/max threads.
- Request queue/accept count.
- Executor queue và rejected tasks.

Với MVC virtual:
- Số virtual threads đang tồn tại.
- Carrier/platform thread utilization.
- JFR pinned virtual threads.
- Queue chờ DB/HTTP connection.
- Semaphore/resource wait.

Với WebFlux:
- Reactor Netty active connections/event loops.
- Event-loop pending tasks.
- Scheduler worker/queue.
- Pending connection pool acquisitions.
- Operator prefetch/buffer và cancellation.

Không so sánh số thread thô mà bỏ qua vai trò của thread. 1.000 virtual threads đang chờ I/O không tương đương 1.000 platform threads đang bị giữ.

### 7.4. Dependency

Nếu workload gọi database hoặc HTTP service, ghi:
- Active/idle connection count.
- Pending acquire count và acquire latency.
- Downstream request rate và latency.
- Database CPU, lock waits, query plan và connection count.
- Stub/downstream error rate.
- Timeout/retry count.

Nếu DB connection pool đạt giới hạn, tăng số virtual threads hoặc event loops không làm DB nhanh hơn.

## 8. Phân tích theo workload

### 8.1. I/O-bound với latency ổn định

Khi phần lớn request chờ một dependency, platform-thread MVC có thể đạt giới hạn ở worker thread hoặc queue. MVC virtual có thể giữ nhiều request chờ hơn mà không cần cùng số platform threads. WebFlux có thể phục vụ nhiều connection với ít event-loop threads nếu toàn bộ chuỗi non-blocking.

Kết quả phụ thuộc:
- Downstream connection pool.
- Số connection cho phép.
- HTTP client connector.
- Timeout.
- Payload encode/decode.
- CPU và memory.
- Cấu hình server.

Nếu tất cả biến thể đều bị giới hạn bởi cùng một database pool 50 connections, tăng concurrency có thể chỉ làm tăng queue wait chứ không tăng throughput.

### 8.2. CPU-bound

Với CPU-bound, cả ba mô hình bị giới hạn bởi số cores và hiệu quả thuật toán. Virtual threads không tăng số core; WebFlux không tự tăng tốc CPU work. Sự khác biệt có thể đến từ:
- Scheduler/executor overhead.
- Context switching.
- Allocation và GC.
- Serialization.
- JIT compilation.
- Lock contention.

Không dùng Thread.sleep() để đại diện CPU-bound. Dùng cùng một hàm CPU có input và iteration cố định; đo CPU time, throughput và tail latency.

Ví dụ hàm deterministic:

```java
public final class CpuWork {

    private CpuWork() {
    }

    public static long calculate(int iterations) {
        long value = 0x1234ABCDL;

        for (int i = 0; i < iterations; i++) {
            value ^= (value << 7);
            value ^= (value >>> 9);
            value *= 0x9E3779B97F4A7C15L;
        }

        return value;
    }
}
```

MVC có thể gọi trực tiếp hàm này. WebFlux có thể chạy một tác vụ CPU kéo dài trên scheduler phù hợp:

```java
@GetMapping("/cpu")
Mono<Long> cpu(@RequestParam(defaultValue = "1000000")
               int iterations) {
    return Mono.fromSupplier(
            () -> CpuWork.calculate(iterations))
            .subscribeOn(Schedulers.parallel());
}
```

Đây là snippet cần import Reactor Mono và Schedulers. Số worker của Schedulers.parallel() phụ thuộc cấu hình/CPU; hãy ghi nhận và không tùy tiện tăng worker vượt cores. Nếu tác vụ rất ngắn, scheduler handoff có thể tốn hơn phần tính toán; benchmark cả cách inline và offload với mục tiêu được xác định rõ.

### 8.3. Mixed workload

Một request có thể chờ HTTP 80 ms rồi tính toán 3 ms và serialize 1 ms. Trong trường hợp này:
- Mô hình threading ảnh hưởng thời gian chờ.
- CPU work ảnh hưởng event loop/carrier/worker.
- Pool size giới hạn số request đồng thời tới dependency.
- Queue và buffer ảnh hưởng tail latency.

Thay đổi một biến mỗi lượt. Ví dụ tăng concurrency pool và arrival rate cùng lúc sẽ làm khó xác định nguyên nhân throughput thay đổi.

## 9. Virtual threads: các điều kiện và bẫy riêng

### 9.1. Không pool virtual threads như platform threads

Virtual threads được thiết kế theo hướng một thread cho một task. Không cần tạo fixed thread pool để tái sử dụng virtual threads. Nếu cần giới hạn số request tới dependency, dùng cơ chế giới hạn concurrency phù hợp như Semaphore, bulkhead hoặc connection pool.

Ví dụ:

```java
Semaphore permits = new Semaphore(20);

String callDependency() throws InterruptedException {
    permits.acquire();
    try {
        return blockingClientCall();
    } finally {
        permits.release();
    }
}
```

Snippet này minh họa giới hạn 20 call đồng thời. Trong production cần xử lý interruption, timeout khi chờ permit và bảo đảm permit luôn được release. Nếu dùng database connection pool, pool vốn đã là một giới hạn tài nguyên; không thêm semaphore trùng lặp nếu không có lý do.

### 9.2. Pinning

Trên một số phiên bản JDK, virtual thread có thể bị pinned vào carrier khi thực hiện blocking operation trong synchronized hoặc native/foreign call. Pinning kéo dài và thường xuyên có thể làm giảm scalability.

Kiểm tra bằng:
- JFR event jdk.VirtualThreadPinned.
- Thread dump/JFR.
- Profiling trên đúng JDK production.

Hành vi pinning thay đổi giữa các JDK; không lấy một kết quả Java 21 để suy ra Java 24+ mà không đo lại.

### 9.3. ThreadLocal

Virtual threads hỗ trợ ThreadLocal, nhưng số lượng virtual threads có thể rất lớn. Không nên cache object nặng trong ThreadLocal như cách thường làm với một pool nhỏ platform threads. ThreadLocal context cho mỗi virtual thread có thể tăng allocation/memory.

### 9.4. Blocking vẫn phải có giới hạn

Virtual threads làm blocking dễ scale hơn, nhưng không khiến dependency vô hạn. Cần:
- Timeout cho từng downstream call.
- Overall request deadline.
- Connection pool giới hạn.
- Bulkhead/concurrency limit.
- Rate limit theo tenant/service.
- Retry có điều kiện và idempotency.
- Cancellation và cleanup.

## 10. WebFlux: các điều kiện và bẫy riêng

### 10.1. Không block event-loop

Không gọi JDBC/JPA đồng bộ, Thread.sleep, block() hoặc file/network I/O blocking trực tiếp trên event-loop. Một blocking operation có thể ngăn event-loop xử lý nhiều connection khác.

Nếu phải gọi legacy blocking code:

```java
Mono<Result> result = Mono.fromCallable(
        () -> legacyBlockingService.load(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là giải pháp cô lập blocking work, không phải biến thư viện blocking thành reactive. Bounded elastic có giới hạn worker/queue; đo và cấu hình theo dependency, tránh dùng như một queue vô hạn.

### 10.2. Backpressure không phải giới hạn bộ nhớ tự động

Reactive Streams demand giúp điều tiết phần tử giữa Publisher/Subscriber, nhưng operator prefetch, flatMap concurrency, buffer, codec, connection pool và network stack vẫn có queue. Cần xác định từng buffer và giới hạn của nó.

### 10.3. Không benchmark bằng Flux.just rồi kết luận về I/O

Một endpoint chỉ trả Flux.range hoặc Mono.just không đo được khả năng scale khi chờ database/network. Nó chủ yếu đo routing, serialization, scheduler và overhead của framework.

### 10.4. Đừng chuyển toàn bộ ứng dụng sang WebFlux nếu dependency vẫn blocking

Nếu phần lớn workload dùng JDBC/JPA blocking và thư viện đồng bộ, WebFlux có thể cần offload liên tục sang boundedElastic. MVC + virtual threads có thể cho mô hình code đơn giản hơn. So sánh bằng workload thật, không dựa vào chữ reactive trong return type.

## 11. Benchmark database: JDBC, virtual threads và R2DBC

Đây là một bài toán riêng với outbound HTTP stub.

Một benchmark DB cần giữ:
- Cùng database engine/version.
- Cùng schema, index, dữ liệu và query plan.
- Cùng transaction isolation.
- Cùng read/write ratio.
- Cùng pool max connections và timeout.
- Cùng cache warm/cold state.
- Cùng số lượng database nodes và CPU/memory.

Các biến thể thường là:
- MVC + JDBC trên platform threads.
- MVC + JDBC trên virtual threads.
- WebFlux + R2DBC.

**Giới hạn:** JDBC và R2DBC là hai driver/API khác nhau. Dù cùng query và database, serialization, protocol handling, pool và driver implementation có thể khác. Kết quả là so sánh end-to-end giữa hai data access stacks, không phải một phép đo cô lập chỉ riêng thread model.

Không gọi JDBC blocking trực tiếp trên WebFlux event-loop. Nếu cần benchmark legacy JDBC trong WebFlux, phải offload sang boundedElastic và báo cáo rõ đó là variant blocking adapter.

Pool connection database là resource cap thực. Nếu pool có 40 connections, 4.000 virtual threads hoặc 4.000 reactive subscribers không biến nó thành 4.000 query đồng thời.

## 12. Phương pháp chạy benchmark đáng tin cậy

### 12.1. Warm-up

JVM cần thời gian:
- Class loading.
- JIT compilation.
- Connection pool initialization.
- DNS/TLS/session setup.
- Cache population.
- Spring initialization.

Warm-up không được tính vào steady-state measurement. Dùng cùng thời gian warm-up cho mọi variant; ví dụ 3–5 phút hoặc đến khi throughput/CPU/latency ổn định.

### 12.2. Measurement và repetition

Một protocol thực tế:
1. Deploy một variant trên môi trường sạch.
2. Chờ health/readiness.
3. Warm-up với tải cố định.
4. Chạy stage arrival rate thấp.
5. Tăng từng stage cho tới khi đạt saturation hoặc SLO fail.
6. Thu metrics/log/JFR.
7. Dừng ứng dụng, khởi động lại sạch.
8. Lặp lại ít nhất ba lần.
9. Hoán đổi thứ tự variant để giảm bias do cache/host thermal/load.
10. Tổng hợp median và độ phân tán giữa các lần chạy.

Không dùng một lần chạy đơn lẻ làm kết luận kiến trúc.

### 12.3. Đo ở mức ổn định

Không tính vài giây đầu startup hoặc lúc test đang tăng tải vào steady state. Với mỗi stage, xác định:
- Offered rate.
- Achieved throughput.
- Latency distribution.
- Error/timeout.
- CPU/memory.
- Connection/queue.
- Dropped iterations.

Nếu generator không đủ sức tạo offered rate, stage đó không hợp lệ để so sánh.

### 12.4. Coordinated omission

Closed-loop generator chỉ gửi request tiếp theo sau response trước có thể bỏ qua thời gian mà người dùng thực tế vẫn tiếp tục tạo request. Khi server chậm, generator tự giảm tải và có thể làm tail latency thấp giả tạo.

Arrival-rate model giúp đặt offered load rõ ràng. Vẫn cần theo dõi generator có bị thiếu VU hoặc dropped iterations không.

## 13. Cách đọc kết quả và xác định điểm bão hòa

Ví dụ bảng minh họa (số liệu giả lập để giải thích cách đọc, **không phải benchmark thực tế**):

| Variant | Offered req/s | Completed req/s | p95 | Error rate | CPU |
| --- | ---: | ---: | ---: | ---: | ---: |
| MVC platform | 500 | 470 | 420 ms | 1.0% | 75% |
| MVC virtual | 500 | 498 | 210 ms | 0.1% | 73% |
| WebFlux | 500 | 500 | 180 ms | 0.0% | 71% |

Không nên đọc bảng này là WebFlux luôn tốt nhất. Trong ví dụ, WebFlux có p95 thấp hơn ở một mức tải cụ thể; phải kiểm tra nhiều stage, p99, memory, error rate, downstream pool và nhiều lần lặp trước khi kết luận.

### 13.1. Tìm dấu hiệu bottleneck

- CPU 100%, throughput không tăng: CPU-bound hoặc allocation/serialization; thêm concurrency có thể làm latency tăng.
- CPU thấp, latency cao, nhiều pending connection acquire: dependency pool hoặc downstream chậm.
- MVC platform busy threads chạm max và queue tăng: request thread capacity hoặc blocking wait.
- MVC virtual có nhiều virtual threads nhưng throughput không tăng: dependency/database cap, CPU hoặc semaphore/connection pool.
- WebFlux event-loop pending tasks tăng: có thể blocking event-loop hoặc CPU work quá dài.
- Heap/direct memory tăng liên tục: buffer/queue/retained objects hoặc leak; không phải cứ reactive là memory bounded.
- Error/timeout tăng theo arrival rate: hệ thống vượt capacity hoặc deadline không phù hợp.
- Dropped iterations tăng: load generator không đạt offered load; kết quả stage cần điều tra.

### 13.2. So sánh throughput ở cùng SLO

Một phương pháp tốt là tìm throughput tối đa vẫn đáp ứng SLO:
- Error rate dưới ngưỡng.
- p95/p99 dưới ngưỡng.
- Memory không tăng vô hạn.
- Dependency vẫn ở capacity cho phép.
- Không có queue kéo dài.

Đây là metric có ý nghĩa vận hành hơn “RPS cao nhất trước khi process chết”.

## 14. Công cụ quan sát

### 14.1. Spring Boot Actuator và Micrometer

Expose các endpoint cần thiết ở mạng nội bộ/test environment:

```properties
management.endpoints.web.exposure.include=health,metrics,prometheus
```

Nếu dùng Prometheus, thêm registry dependency tương ứng và bảo vệ endpoint metrics. Không public /actuator/prometheus vô hạn ra Internet.

Metrics nên có tag cardinality giới hạn; không gắn user ID, order ID hoặc URL chứa ID động vào tag.

### 14.2. Java Flight Recorder

JFR hữu ích để xem:
- CPU hot methods.
- Allocation và GC.
- Thread park/block/monitor contention.
- Socket read/write.
- Virtual thread pinning.
- Class loading và runtime events.

Bắt đầu recording:

```bash
java -XX:StartFlightRecording=filename=benchmark.jfr,duration=10m -jar app.jar
```

Phân tích file bằng JDK Mission Control hoặc công cụ JFR phù hợp. Dùng cùng recording policy cho mọi variant vì profiling có overhead.

### 14.3. Thread dump

Đối với virtual threads, có thể dùng jcmd để tạo thread dump dạng JSON trên JDK hỗ trợ:

```bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
```

Đây là lệnh minh họa; thay <pid> bằng process ID thực. So sánh thread dump để hiểu task đang chờ ở đâu, nhưng không chỉ đếm thread để kết luận performance.

## 15. Những lỗi benchmark thường gặp

| Sai lầm | Vì sao kết quả sai lệch | Cách khắc phục |
| --- | --- | --- |
| Chỉ benchmark Flux.just | Không có I/O hoặc concurrency thực | Dùng workload production-like |
| Dùng Thread.sleep trong WebFlux event-loop | Block event-loop, tạo benchmark sai | Dùng dependency thật hoặc Mono.delay cho synthetic test |
| So MVC JDBC với WebFlux JDBC trên event-loop | Một variant vi phạm mô hình WebFlux | Dùng R2DBC hoặc offload blocking rõ ràng |
| Chạy ba variant đồng thời trên cùng máy | Cạnh tranh CPU/memory/cache | Chạy tuần tự, môi trường giống nhau |
| Dùng JDK khác nhau | Khác JIT/GC/virtual thread implementation | Pin cùng JDK |
| Chỉ đo RPS | Bỏ qua tail latency và errors | Đo p50/p95/p99, error và SLO |
| Closed-loop load generator | Tải giảm khi server chậm | Dùng arrival-rate model |
| Không theo dõi dropped iterations | Không biết generator có gửi đủ tải | Ghi offered và achieved rate |
| Downstream stub quá yếu | Benchmark đo stub chứ không đo ứng dụng | Theo dõi stub, tăng capacity hoặc kiểm soát tải |
| Connection pool khác nhau | Một variant được nhiều connection hơn | Cố định hoặc báo cáo rõ pool |
| Warm-up không đồng đều | JIT/cache bias | Warm-up cùng protocol |
| Chỉ chạy một lần | Kết quả chịu ảnh hưởng nhiễu | Lặp lại và hoán đổi thứ tự |
| Không đo GC/direct memory | Bỏ qua bottleneck memory | Thu JFR, GC và RSS/direct metrics |
| Virtual thread được bật nhưng không xác minh | Variant thực tế vẫn chạy platform threads | Kiểm tra thread/JFR/runtime |
| Tăng virtual threads để vượt DB pool | Queue wait tăng, DB vẫn giới hạn | Giới hạn concurrency theo dependency |
| Chỉ test CPU-bound rồi chọn framework | Không đại diện I/O-bound | Tách nhiều workload |
| Chỉ test localhost rồi kết luận production | Bỏ qua proxy/TLS/network | Test staging với hạ tầng thật |

## 16. Ma trận quyết định kiến trúc

| Đặc điểm hệ thống | Lựa chọn đáng thử đầu tiên | Lý do |
| --- | --- | --- |
| Ứng dụng MVC/JDBC hiện hữu, nhiều request chờ I/O | MVC + virtual threads | Có thể tăng concurrency mà giữ code blocking |
| API reactive từ đầu, WebClient/R2DBC và streaming | WebFlux | Non-blocking end-to-end, backpressure |
| CPU-bound là chủ đạo | Đo cả ba; chọn theo độ đơn giản/overhead | Thread model không tạo thêm CPU |
| Thư viện blocking chiếm đa số | MVC platform hoặc MVC virtual | Tránh offload blocking liên tục trong WebFlux |
| Nhiều streaming request/response | WebFlux | Reactive Streams và non-blocking streaming |
| Downstream connection pool rất nhỏ | Bất kỳ mô hình nào nhưng giới hạn concurrency | Dependency là bottleneck |
| Cần tích hợp Servlet filters/container và ecosystem | Spring MVC | Tương thích Servlet stack |
| Nhiều tác vụ chờ I/O với code đồng bộ dễ đọc | MVC + virtual threads | Thread-per-request vẫn dễ phát triển |
| Team đã có năng lực Reactor và toàn bộ dependency reactive | WebFlux | Tận dụng non-blocking và cancellation/backpressure |
| Hệ thống có mixed workload và legacy | Benchmark theo service boundary | Có thể chọn stack khác nhau cho từng service |

Không bắt buộc toàn tổ chức dùng một mô hình. Có thể giữ MVC cho CRUD/JDBC, dùng WebFlux cho gateway/streaming service, và bật virtual threads ở một số ứng dụng MVC phù hợp.

## 17. Kết luận kỹ thuật cần ghi vào báo cáo benchmark

Một báo cáo có thể tái lập nên chứa:

1. Mục tiêu: throughput ở cùng SLO, latency, memory hoặc concurrency.
2. Mô hình: MVC platform, MVC virtual, WebFlux; server connector và client connector.
3. Version: JDK, Spring Boot, Spring Framework, Reactor, server, OS/container.
4. Hardware/resource: CPU, RAM, cgroup quota, heap, GC.
5. Workload: I/O/CPU/mixed, payload, dependency latency, data distribution.
6. Pool: HTTP, DB, executor, connection, concurrency limit.
7. Load: generator version, arrival-rate stages, duration, VUs và dropped iterations.
8. Warm-up/measurement: protocol, số lần lặp, thứ tự chạy.
9. Results: offered/achieved RPS, p50/p95/p99, errors, CPU, memory, GC, queue.
10. Bottleneck: CPU, event loop, worker threads, pool, database hay network.
11. Trade-offs: code complexity, observability, operational cost và migration.
12. Giới hạn: phần nào chưa được benchmark, giả định nào chưa kiểm chứng.

Không viết “WebFlux nhanh hơn 30%” nếu chỉ đo một endpoint trên localhost. Hãy nói rõ benchmark cụ thể, tải cụ thể, môi trường và độ biến thiên giữa các lượt.

## 18. Checklist trước khi chọn MVC, virtual threads hoặc WebFlux

- [ ] Đã phân loại workload là I/O-bound, CPU-bound hay mixed.
- [ ] Đã xác định dependency nào chiếm phần lớn latency.
- [ ] Đã dùng cùng JDK và framework version.
- [ ] Đã giữ nguyên payload, business logic và security.
- [ ] Đã cố định hoặc ghi rõ connection pool/executor.
- [ ] Đã xác minh MVC virtual variant thật sự dùng virtual threads.
- [ ] WebFlux không block event-loop.
- [ ] Load generator chạy ngoài máy server và đủ capacity.
- [ ] Đã dùng arrival-rate test và theo dõi dropped iterations.
- [ ] Đã warm-up trước khi đo.
- [ ] Đã chạy nhiều stage tải và nhiều lần lặp.
- [ ] Đã đo p50/p95/p99, errors, CPU, memory và GC.
- [ ] Đã theo dõi queue, active connections và downstream pool.
- [ ] Đã xác định throughput tối đa trong cùng SLO.
- [ ] Đã ghi lại giới hạn của benchmark và không khái quát vượt dữ liệu.

## 19. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 – Virtual Threads](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): Java 21+, spring.threads.virtual.enabled, lưu ý daemon threads và pinning.
- [Spring Boot 3.5 – Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): auto-configured AsyncTaskExecutor và virtual-thread integration.
- [Spring Framework – Spring WebFlux](https://docs.spring.io/spring/reference/web/webflux.html): reactive stack, non-blocking I/O, Reactive Streams backpressure, khả năng cùng tồn tại với MVC.
- [Oracle Java 21 – Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual thread scheduling, use cases I/O-bound, CPU-bound limits và pinning.
- [Oracle Java – JEP 444](https://openjdk.org/jeps/444): mục tiêu và semantics của virtual threads.
- [Spring Boot – Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer và quan sát runtime.
- [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client.
- [k6 – Constant Arrival Rate Executor](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/): mô hình offered arrival rate và cấu hình VUs.
- [JDK Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder.html): ghi và phân tích sự kiện JVM.

## 20. Ghi nhớ

**Không có mô hình thắng trong mọi workload.** MVC platform threads dễ tích hợp và phù hợp tải vừa phải; MVC với virtual threads có thể mở rộng tốt cho code đồng bộ chờ I/O trên Java 21+; WebFlux phù hợp với chuỗi non-blocking, streaming và backpressure khi dependency cũng reactive.

So sánh công bằng cần giữ cùng workload, dependency, payload, JDK, tài nguyên, timeout và offered load. Đo throughput cùng p95/p99, error rate, CPU, memory, GC, connection pool và queue; chạy nhiều lượt sau warm-up. Đặc biệt, virtual threads tăng khả năng mở rộng của tác vụ chờ I/O chứ không làm CPU chạy nhanh hơn, còn WebFlux chỉ phát huy lợi ích khi event-loop không bị blocking. Chọn stack dựa trên điểm bão hòa trong cùng SLO, độ phức tạp vận hành và khả năng của dependency thực tế.
