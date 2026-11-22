# Khởi tạo lười: request đầu tiên, warm-up và readiness trong Spring Boot

## 1. Vấn đề cốt lõi

**Lazy initialization** là cách trì hoãn việc tạo một số Spring bean cho đến khi chúng thật sự được yêu cầu. Nhờ đó, thời gian khởi động được Spring Boot báo có thể ngắn hơn. Đổi lại, **request đầu tiên** đụng đến một bean chưa được tạo phải chịu chi phí khởi tạo, có thể tăng latency hoặc bộc lộ lỗi cấu hình mà startup chưa phát hiện.

Cần tách ba câu hỏi:

1. **Startup time:** ứng dụng mất bao lâu để đi đến mốc kết thúc startup?
2. **Cold-path latency:** người dùng đầu tiên của một chức năng phải đợi khởi tạo bao nhiêu thành phần chưa sẵn sàng?
3. **Readiness:** instance đã đủ điều kiện để load balancer/Kubernetes gửi traffic vào chưa?

Spring Boot **không tự tạo mọi bean lazy** trước khi chuyển `ReadinessState` sang `ACCEPTING_TRAFFIC`. Một probe readiness trả `UP` có thể xảy ra khi một endpoint nghiệp vụ chưa từng được sử dụng và các bean của nó vẫn lazy.

Ngữ cảnh của bài: **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**. Ví dụ thực hành kết hợp `@Lazy`, `ObjectProvider`, `ApplicationRunner` và Actuator để làm rõ hai cách chạy: cold request và warm-up trước ready.

## 2. Vòng đời eager so với lazy

Thông thường, `ApplicationContext` tạo singleton không lazy ở pha `refresh()`. Khi bean definition có thuộc tính lazy, Spring trì hoãn việc instantiate tới khi BeanFactory thật sự cần nó.

```text
EAGER SINGLETON
---------------------
SpringApplication.run()
    |
ApplicationContext.refresh()
    +-- tạo các singleton không lazy
    +-- gọi callback init / @PostConstruct
    |
ApplicationStartedEvent
ApplicationRunner / CommandLineRunner
ApplicationReadyEvent
Readiness = ACCEPTING_TRAFFIC
    |
request đầu tiên -> dùng bean đã được tạo

LAZY SINGLETON
---------------------
SpringApplication.run()
    |
ApplicationContext.refresh()
    +-- đăng ký bean definition
    +-- chưa nhất thiết tạo bean lazy X
    |
ApplicationStartedEvent
ApplicationRunner / CommandLineRunner
ApplicationReadyEvent
Readiness = ACCEPTING_TRAFFIC
    |
request đầu tiên cần X
    +-- BeanFactory tạo X
    +-- tạo dependencies của X nếu chưa có
    +-- chạy callback init / @PostConstruct
    +-- xử lý request
    |
request tiếp theo -> thường dùng lại singleton X
```

Đây là mô hình khái niệm. Bean lazy **vẫn có thể tạo ở startup** khi một bean eager cần nó làm dependency, khi runner gọi lấy bean hoặc khi framework chủ động khởi tạo. Không phải toàn bộ web infrastructure đều bị trì hoãn như nhau.

### 2.1. @Lazy không thay scope

- `@Lazy` trên singleton: trì hoãn **lần tạo đầu tiên**, rồi giữ cùng instance singleton trong BeanFactory.
- `@Scope("prototype")`: mỗi lần yêu cầu bean có thể tạo instance mới; khác với singleton lazy.
- Request/session scopes trong web app có lifecycle riêng; đừng đồng nhất chúng với lazy singleton.
- Sau khi singleton lazy được tạo, request kế tiếp thường không phải trả lại chi phí constructor của chính bean đó, nhưng có thể vẫn gặp JIT/cache/network cold cost.

### 2.2. Lazy là trì hoãn *nhu cầu*, không nhất thiết chờ HTTP

Một bean lazy có thể được yêu cầu bởi:

- Một singleton eager inject trực tiếp.
- `ObjectProvider.getObject()` trong một `ApplicationRunner`.
- Một scheduler hoặc message listener.
- Một integration test gọi `getBean(...)`.
- Một request REST chạm đến service.
- Một warm-up task tạo bean có chủ đích.

“Lazy” không có nghĩa chỉ HTTP request đầu tiên mới tạo được bean.

## 3. Cấu hình Spring Boot 3.3

Bật global lazy tại `src/main/resources/application.properties`:

```properties
spring.main.lazy-initialization=true
```

Hoặc `application.yml`:

```yaml
spring:
  main:
    lazy-initialization: true
```

Tùy chọn mặc định là `false`. Khi bật, nhiều beans chuyển sang tạo theo nhu cầu, có thể giảm startup time; nhưng một số infrastructure và những bean được chỉ định eager vẫn cần tạo sớm.

Bằng Java, trước `run`:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setLazyInitialization(true);
app.run(args);
```

Đây là snippet trong `main`, `MyApplication` là class khởi động do dự án định nghĩa.

### 3.1. Lazy từng bean

```java
@Bean
@Lazy
ExpensiveCatalog expensiveCatalog() {
    return new ExpensiveCatalog();
}
```

Đây là method minh họa trong `@Configuration` hoặc `@SpringBootApplication`, cần import `@Bean` và `@Lazy`, cũng như class `ExpensiveCatalog`. Bean này sẽ không bị eager pre-instantiation chỉ vì method `@Bean` tồn tại.

Một component có thể dùng:

```java
@Service
@Lazy
public class ReportService {
    public ReportService() {
        // Khởi tạo tài nguyên của service.
    }
}
```

Đây là class minh họa, cần imports Spring stereotypes.

### 3.2. Bắt buộc eager trong ứng dụng global lazy

`@Lazy(false)` đánh dấu một bean cần được khởi tạo sớm, ví dụ runner quan trọng:

```java
@Bean
@Lazy(false)
ApplicationRunner mandatoryInitializer() {
    return args -> System.out.println("Startup initialization hook");
}
```

Đoạn này nằm trong class cấu hình. Có thể dùng `@Lazy(false)` trên component/controller cần được tạo ở startup.

**Không nên bật global lazy rồi đánh dấu eager toàn bộ bean theo cảm tính.** Xác định tập critical path cần tạo sớm và đo kết quả.

## 4. Điểm rất dễ nhầm: lazy bean nhưng eager dependency

Spring Framework lưu ý một bean lazy có thể bị tạo lúc startup nếu một singleton không lazy cần dependency đó.

```text
EagerController
    |
    +-- constructor(CatalogService)
                       |
                       +-- CatalogService @Lazy
                       +-- vẫn có thể bị tạo ngay lúc khởi động
```

Lý do: Spring không thể tạo `EagerController` nếu constructor bắt buộc cần một instance `CatalogService` mà không có cơ chế trì hoãn dependency.

**@Lazy trên bean definition:**

```java
@Bean
@Lazy
CatalogService catalogService() {
    return new CatalogService();
}
```

**@Lazy tại injection point:**

```java
public CatalogController(@Lazy CatalogService service) {
    this.service = service;
}
```

Đoạn thứ hai là constructor minh họa: Spring có thể inject proxy và resolve service khi proxy được dùng. Hình thức proxy có giới hạn theo type, final class, cơ chế AOP và injection point.

**ObjectProvider:**

```java
public CatalogController(ObjectProvider<CatalogService> provider) {
    this.provider = provider;
}

public String lookup() {
    return provider.getObject().find("item");
}
```

Đây là snippet trong controller đã định nghĩa field `ObjectProvider<CatalogService> provider`. Việc nhận `ObjectProvider` không cần tạo ngay CatalogService; `getObject()` là điểm resolve tường minh. Bài demo dùng cách này để tách biệt thời điểm tạo controller khỏi tạo service.

### 4.1. Cảnh báo @PostConstruct

`@PostConstruct` trên bean lazy **không tự chạy trong startup** nếu bean chưa được khởi tạo. Nó chạy **khi bean được tạo**. Nếu callback nạp cache hoặc kết nối backend chậm, chi phí đó có thể chuyển tới request đầu.

Với một thành phần bắt buộc phải khởi tạo trước nhận traffic, dùng bean eager hoặc một runner warm-up thay vì giả định annotation `@PostConstruct` sẽ chạy sớm.

## 5. Vì sao request đầu tiên có thể chậm?

| Loại chi phí | Nguyên nhân | Có thể xuất hiện muộn? |
| --- | --- | --- |
| Bean creation | Constructor, dependency graph, factory method | Có |
| Bean post-processing | Proxy, validation, post-processor | Có |
| Initialization callbacks | `@PostConstruct` và init method | Có, khi bean tạo muộn |
| Servlet/MVC/WebFlux infrastructure | Handler, serializer, codec, mapping | Có thể tùy mode/config |
| JIT/class loading | JVM biên dịch và tải class | Có |
| DB connection/pool | Mở kết nối lần đầu, xác thực | Có thể |
| ORM/query | Query compilation, metadata, mapping | Có thể |
| Cache | Tải dữ liệu/index đầu tiên | Có thể |
| Remote API | DNS/TLS/authentication | Có thể |
| File/model resource | Đọc schema/template/dictionary | Có thể |

Bật lazy chủ yếu dịch chi phí **bean creation** và các khởi tạo phụ thuộc sang thời điểm sử dụng. Nó không xóa chi phí của JVM, mạng hay nghiệp vụ. Một service đã eager vẫn có thể có **cold path** vì HTTP route, cache hoặc connection còn lạnh.

### 5.1. Request đầu tới route A khác route B

Giả sử `GET /ping` không cần `ReportService` còn `GET /reports` cần nó. Khi app đã ready:

```text
GET /readyz   -> UP (theo readiness group hiện hành)
GET /ping     -> có thể trả nhanh
GET /reports  -> BeanFactory tạo ReportService lazy ở lần đầu
GET /reports  -> thường dùng lại singleton
```

Không nên coi health probe thành một request “làm nóng toàn ứng dụng”. Nó không mặc nhiên chạm đến mọi bean nghiệp vụ.

### 5.2. Request đồng thời và singleton cold start

Nếu 50 request đồng thời cùng cần một singleton lazy chưa tồn tại, các request có thể phải chờ quá trình tạo bean dưới synchronization của BeanFactory. Điều đó có thể làm p95/p99 tăng mạnh ngay sau rollout.

Một phép thử đơn lẻ `curl /reports` không mô phỏng đủ mức tải đồng thời. Hãy đo nhiều instances và các burst đầu sau deploy.

## 6. Đổi startup nhanh lấy lỗi phát hiện muộn và memory tăng muộn

Spring Boot 3.3 nêu rõ hai mặt trái của lazy:

- **Phát hiện lỗi muộn:** bean cấu hình sai có thể không được tạo trong startup. Sau đó, request đầu vào tính năng liên quan mới ném `BeanCreationException` hoặc lỗi init.
- **Heap footprint thay đổi:** startup ban đầu có thể dùng ít heap hơn nhưng nhiều bean sẽ được tạo khi traffic lan sang các tính năng khác. Nếu chỉ cấp memory limit theo số đo ngay sau startup, ứng dụng có nguy cơ không đủ heap.

Ví dụ lỗi muộn: một service lazy yêu cầu property bắt buộc `reports.endpoint`; property không có; Boot không tạo service trong startup nên vẫn đạt ready. Chỉ khi một controller hoặc runner lấy service thì cấu hình thiếu mới bị phát hiện.

Không dùng “startup thành công” như chứng chỉ mọi bean đều được cấu hình đúng. Với critical path, cần fail-fast, integration test hoặc warm-up trước readiness.

## 7. Warm-up (làm nóng) là gì?

Warm-up là chủ động chuẩn bị thành phần trước khi traffic thật cần dùng đến. Có thể phân ba tầng:

1. **Bean warm-up:** yêu cầu tạo một số singleton lazy; chạy constructor, dependency injection, init callbacks.
2. **Service warm-up:** gọi những thao tác an toàn chuẩn bị cache, mapper, query plan, connection hoặc index.
3. **Request-path warm-up:** thực thi một đường request đại diện để chạm handler/serialization/security. Cần đặc biệt cẩn thận với side effects.

Chỉ gọi `getBean(Service.class)` không nhất thiết làm nóng cơ sở dữ liệu, JSON serializer, JVM JIT hoặc toàn bộ request path.

### 7.1. Warm-up tốt nên có những tính chất nào?

- **Idempotent** nếu ứng dụng/test/pod khởi động nhiều lần.
- **Không gây tác dụng phụ nghiệp vụ** (không đặt hàng thật, chuyển tiền, gửi email).
- Có **timeout/budget** và chính sách failure rõ.
- Không làm lộ secrets trong logs.
- Được đo thời gian và kết quả.
- Không tạo quá nhiều kết nối đồng thời khi rollout nhiều pods.
- Chỉ làm những việc cần thiết cho **critical paths**.
- Không giữ lock/thread startup bằng retry vô hạn.

Một service có thể cung cấp method `warmUp()` chỉ đọc hoặc tạo state tại chỗ, được gọi từ `ApplicationRunner`.

### 7.2. Không phải làm nóng mọi bean đều tốt

Nếu có hàng trăm tính năng hiếm dùng, ép tạo mọi bean ở startup làm mất mục tiêu lazy, tăng CPU và memory ngay lúc deploy. Lựa chọn thường hiệu quả: **eager/runner warm-up** cho các đường cốt lõi; để lazy cho chức năng ít dùng có cold latency chấp nhận được; thêm integration test cho tính năng lazy để tránh lỗi config xuất hiện trước người dùng thật.

## 8. Readiness của Spring Boot và vị trí tốt để warm-up

Spring Boot 3.3 thông thường phát các mốc chính:

```text
ApplicationContext.refresh()
    |
ContextRefreshedEvent
    |
ApplicationStartedEvent
    |
LivenessState.CORRECT
    |
ApplicationRunner / CommandLineRunner  <--- warm-up bắt buộc
    |
ApplicationReadyEvent
    |
ReadinessState.ACCEPTING_TRAFFIC
    |
SpringApplication.run() returns
```

Trước khi các runners hoàn thành, readiness mặc định của Boot thường là `REFUSING_TRAFFIC`. Vì vậy một `ApplicationRunner` **đồng bộ** là nơi hợp lý cho warm-up phải thành công **trước** khi instance chấp nhận traffic.

**Điểm quan trọng:** Boot không mặc định quét toàn bộ bean lazy để đánh dấu READY. Runner chỉ làm những gì code của nó yêu cầu. Một runner khởi tạo một service không bảo đảm một route khác đã ấm.

### 8.1. Nếu runner bị lỗi?

Nếu runner ném exception không được xử lý, startup thất bại và `ApplicationReadyEvent` thông thường không được phát. Đây có thể là hành vi đúng nếu không có dependency bắt buộc thì instance không được nhận request.

Nếu một tính năng tùy chọn không warm được, có thể chấp nhận fallback mà vẫn ready, nhưng policy phải được mô tả rõ ràng và đo được. Tránh `catch (Exception ignored)` rồi in “WARMUP_SUCCESS” khi chưa hoàn tất.

### 8.2. @Async không tương đương runner đồng bộ

Nếu runner chỉ gọi `CompletableFuture.runAsync(...)` rồi return, Boot có thể phát `ApplicationReadyEvent` và đánh dấu accepting **trong khi warm-up còn chạy**. Muốn bắt buộc hoàn tất trước ready, runner phải chờ kết quả hữu hạn hoặc dùng một state machine readiness có owner rõ ràng.

## 9. Demo Java 17+: so sánh cold request với warm-up trước READY

Đây là ví dụ **Spring Boot 3.3.x + Spring MVC + Actuator**, có:

- `GET /demo/ping`: không cần catalog.
- `GET /demo/catalog`: lấy `CatalogService` lazy qua `ObjectProvider`.
- `ApplicationRunner` có thể làm nóng catalog trước khi Boot hoàn tất ready.
- `/livez` và `/readyz` để quan sát health groups trên port chính.

Constructor catalog có `Thread.sleep(500)` **chỉ để mô phỏng chi phí khởi tạo**; không dùng sleep này trong production.

### 9.1. Cấu trúc

```text
lazy-readiness-demo/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/com/example/lazy/
    LazyReadinessApplication.java
    CatalogService.java
    CatalogController.java
```

### 9.2. settings.gradle

```groovy
rootProject.name = 'lazy-readiness-demo'
```

### 9.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
}
```

Ví dụ này khóa Spring Boot 3.3.13 để thống nhất với bài học. Dự án cần Gradle và Java 17+, và các lệnh chạy dưới đây giả định có Gradle Wrapper. Không tự trộn dependency của Spring Boot 4 vào project 3.3.

### 9.4. application.properties

```properties
server.port=8080

# Dùng lazy cho bean đủ điều kiện, trừ khi đánh dấu eager.
spring.main.lazy-initialization=true

# Cho phép bật warm-up qua command-line property.
demo.warmup.enabled=false

# Bật health groups kể cả ngoài Kubernetes.
management.endpoint.health.probes.enabled=true

# Đặt /livez và /readyz trên cổng HTTP chính.
management.endpoint.health.probes.add-additional-paths=true
```

### 9.5. LazyReadinessApplication.java

```java
package com.example.lazy;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class LazyReadinessApplication {

    public static void main(String[] args) {
        SpringApplication.run(LazyReadinessApplication.class, args);
        System.out.println("BOOT_COMPLETED");
    }

    @Bean
    @Lazy
    CatalogService catalogService() {
        return new CatalogService();
    }

    @Bean
    @Lazy(false)
    ApplicationRunner optionalWarmup(
            ObjectProvider<CatalogService> catalogProvider,
            Environment environment) {

        return args -> {
            boolean enabled = environment.getProperty(
                    "demo.warmup.enabled", Boolean.class, false);

            if (enabled) {
                System.out.println("WARMUP_START");
                CatalogService catalog = catalogProvider.getObject();
                catalog.lookup("startup");
                System.out.println("WARMUP_DONE");
            }
        };
    }
}
```

Giải thích:

1. `@Bean @Lazy` đăng ký bean definition của CatalogService nhưng không yêu cầu tạo nó ngay.
2. `@Bean @Lazy(false)` buộc runner tham gia giai đoạn startup ngay cả khi bật global lazy.
3. `ObjectProvider<CatalogService>` được inject vào runner mà không instantiate CatalogService.
4. Với cờ warmup false, runner không gọi `getObject()` và catalog vẫn có thể chưa tồn tại.
5. Với cờ warmup true, runner gọi `getObject()`, constructor chạy **trước** khi runner kết thúc và trước mốc accepting mặc định của Boot.
6. `BOOT_COMPLETED` được in sau khi `SpringApplication.run(...)` trả về, giúp quan sát mốc Boot startup hoàn tất.

### 9.6. CatalogService.java

```java
package com.example.lazy;

public final class CatalogService {

    public CatalogService() {
        System.out.println("CATALOG_CREATED");

        try {
            Thread.sleep(500); // Chỉ mô phỏng khởi tạo tốn thời gian.
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Demo initialization interrupted", ex);
        }
    }

    public String lookup(String key) {
        return "catalog:" + key;
    }
}
```

Đây là class Java thuần, **không cần `@Service`** vì đã có `@Bean` tạo nó. `Thread.sleep` chỉ để người học thấy độ trễ một cách dễ quan sát, không phải kỹ thuật tối ưu.

### 9.7. CatalogController.java

```java
package com.example.lazy;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Lazy;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Lazy(false)
public class CatalogController {

    private final ObjectProvider<CatalogService> catalogProvider;

    public CatalogController(
            ObjectProvider<CatalogService> catalogProvider) {
        this.catalogProvider = catalogProvider;
    }

    @GetMapping("/demo/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/demo/catalog")
    public String catalog() {
        return catalogProvider.getObject().lookup("request");
    }
}
```

Controller được đánh dấu eager để giữ riêng biến số **CatalogService lazy** trong demo. `ObjectProvider` bảo đảm constructor controller không tự yêu cầu tạo CatalogService. Một số framework components vẫn có thể khởi tạo muộn do cấu hình global lazy; vì thế khi đo tổng latency, cần xem cả log `CATALOG_CREATED`.

## 10. Thí nghiệm A: không làm nóng

Chạy từ thư mục có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD: `gradlew.bat bootRun`. PowerShell: `.\gradlew.bat bootRun`.

Với `demo.warmup.enabled=false`, chương trình sẽ in dòng từ main:

```text
BOOT_COMPLETED
```

Ở thời điểm này, `CATALOG_CREATED` **chưa in** nếu không thành phần nào khác yêu cầu bean catalog.

Dùng terminal thứ hai:

```bash
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/demo/ping
curl -i http://localhost:8080/demo/catalog
curl -i http://localhost:8080/demo/catalog
```

Body do demo định nghĩa:

```text
GET /demo/ping        -> pong
GET /demo/catalog     -> catalog:request
GET /demo/catalog     -> catalog:request
```

Khi request đầu thực sự yêu cầu catalog, console server in:

```text
CATALOG_CREATED
```

Request này có thể chịu khoảng chờ mô phỏng 500 ms cộng với các chi phí framework/JVM khác. Request tiếp theo dùng lại singleton CatalogService nên không in lại constructor log. **Không cam kết thời gian HTTP chính xác là 500 ms** vì scheduler, JIT, máy chủ HTTP và network còn ảnh hưởng.

### 10.1. /readyz xanh trước /demo/catalog vẫn là kết quả hợp lệ

`/readyz` phản ánh Spring Boot readiness/health group hiện được cấu hình, **không phải phép thử instantiate CatalogService**. Nó có thể trả `UP` trong khi bean catalog chưa được tạo. Đó không phải bug của Actuator; đó là phạm vi contract của readiness mặc định.

Thêm health indicator hoặc kiểm tra catalog chỉ khi nó thực sự là một **điều kiện bắt buộc cho việc nhận traffic**, tránh để health check biến thành công việc nặng trong mỗi lần probe.

### 10.2. Vì sao ping có thể chậm dù catalog chưa tạo?

Global lazy có thể để một số MVC/servlet/serialization infrastructure khởi tạo ở request đầu tiên. `/demo/ping` có thể chịu cold cost không liên quan đến catalog. Hãy dùng marker `CATALOG_CREATED` để biết thời điểm tạo bean catalog; đừng suy luận từ tổng latency của một request duy nhất.

## 11. Thí nghiệm B: runner làm nóng trước ready

Dừng tiến trình cũ và chạy lại bằng argument:

```bash
./gradlew bootRun --args="--demo.warmup.enabled=true"
```

`--args` là cách Gradle `bootRun` truyền tham số cho Spring Boot. Nếu có nhiều main class, cấu hình `springBoot.mainClass` trong build script, không dùng một tùy chọn `--main-class` không được xác nhận của `bootRun`.

Các dòng từ code demo theo thứ tự:

```text
WARMUP_START
CATALOG_CREATED
WARMUP_DONE
BOOT_COMPLETED
```

Diễn giải:

- Runner chạy sau refresh nhưng trước `ApplicationReadyEvent`.
- `ObjectProvider.getObject()` tạo CatalogService khi chạy warm-up.
- Constructor chạy đúng một lần.
- Runner gọi `lookup("startup")` và kết thúc.
- Boot mới hoàn tất startup/readiness mặc định, rồi `run(...)` trả về cho main.

Gọi:

```bash
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/demo/catalog
curl -i http://localhost:8080/demo/catalog
```

Không có dòng `CATALOG_CREATED` thứ hai vì singleton đã tồn tại. **Chỉ riêng bean CatalogService và method đã gọi được làm nóng**; các chi phí của route khác, JSON serializer, JIT, DB hay TLS vẫn có thể cold.

### 11.1. Bảng so sánh

| Tiêu chí | Lazy, không warm-up | Lazy + runner warm-up |
| --- | --- | --- |
| Startup-to-ready | Thường ngắn hơn | Trả thêm thời gian warm-up |
| First use CatalogService | Tạo bean ở request đầu | Bean đã tạo trước ready |
| Phát hiện lỗi CatalogService | Có thể muộn | Có cơ hội fail trước ready |
| Memory ngay sau ready | Có thể thấp hơn | Cao hơn do catalog đã tạo |
| Route khác có sẵn sàng không? | Không thể suy ra | Vẫn không thể suy ra |
| Tổng chi phí tạo singleton | Không biến mất | Chỉ đổi thời điểm |

## 12. Làm nóng đúng đường xử lý quan trọng

Một service thực tế có graph:

```text
POST /orders
  -> Security / validation / tracing
  -> OrderController
  -> OrderService
      -> PricingEngine
      -> InventoryClient
      -> OrderRepository
          -> DataSource
          -> TransactionManager
  -> JSON serialization
```

Chỉ gọi `getBean(OrderService.class)` có thể chưa chạm đến query, connection, mapper/serialization hoặc remote dependency thực sự.

Thiết kế warm-up nên trả lời:

1. Route nào có SLO first-request chặt?
2. Bean nào đang gây cold latency?
3. Những init callbacks nào phải hoàn tất trước traffic?
4. Có cache/index/query/connection nào cần làm nóng?
5. Warm-up có gây side effect không?
6. Có thể fail-fast nếu thiếu dependency bắt buộc không?
7. Warm-up nhiều pod cùng lúc ảnh hưởng database/API thế nào?
8. Đo sau warm-up bằng traffic thật có chứng minh cải thiện không?

### 12.1. Tránh self-HTTP mặc định

Một số ứng dụng tự gọi HTTP vào localhost để làm nóng route. Cách này dễ gặp vấn đề:

- Tạo đơn hàng/giao dịch hoặc side effect thật.
- Sai authentication/authorization context.
- Phụ thuộc HTTP server đã bắt đầu phục vụ.
- Deadlock nếu startup đang chờ một self-request không thể chạy.
- Tạo các log/traces khó phân biệt warm-up với traffic thật.

Ưu tiên **method service chuyên warm-up** được gọi từ runner nếu có thể. Nếu yêu cầu warm-up toàn bộ HTTP path, dùng request không side effect và **điều phối readiness** thật sự để không lẫn với traffic khách hàng.

### 12.2. Thundering herd khi rollout

Nếu 30 pod cùng startup và mỗi pod warm 100.000 record từ DB, có thể quá tải nguồn chung. Cân nhắc giới hạn concurrency, time budget, rolling deployment, chia sẻ cache, batch size và backoff. Không để warm-up bắt buộc retry vô hạn rồi khiến mọi pod kẹt ở unready mãi mãi.

## 13. Actuator readiness/liveness và lazy

Trong ứng dụng web có `spring-boot-starter-actuator`, Spring Boot có hai health groups dựa trên `ApplicationAvailability`:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

Với `management.endpoint.health.probes.add-additional-paths=true`, nhóm đó có thêm đường trên main port:

- `/livez`
- `/readyz`

Readiness trả lời **có nên route traffic vào instance không**, không phải “mọi bean lazy đã được instantiate chưa”.

### 13.1. Mốc availability và runner

```text
STARTING: Liveness BROKEN; Readiness REFUSING_TRAFFIC
    |
Context refreshed / ApplicationStartedEvent
    |
Liveness CORRECT; Readiness REFUSING_TRAFFIC
    |
ApplicationRunner warm-up
    |
ApplicationReadyEvent
    |
Readiness ACCEPTING_TRAFFIC
```

Trạng thái ban đầu `BROKEN` là cách Boot chưa công bố instance live trong startup, không có nghĩa ứng dụng đã gặp một lỗi internal corruption. HTTP server cũng có thể chưa mở nên probe chưa truy cập được.

### 13.2. Readiness không nên lẫn với liveness

- **Liveness:** tín hiệu restart instance nếu trạng thái nội bộ không thể tự hồi phục.
- **Readiness:** tín hiệu ngừng route traffic trong khi startup, quá tải, mất dependency bắt buộc hoặc warm-up.
- **Global health:** có thể tổng hợp database/cache/những indicator khác.

Không đưa kiểm tra external dependency vào liveness một cách tùy tiện: khi DB chung mất kết nối, tất cả pods có thể restart đồng loạt, khuếch đại sự cố.

### 13.3. Probe trên port chính

Một Actuator chạy management port riêng có thể báo xanh dù port chính của web app gặp sự cố. Khi được cấu hình thêm `/livez` và `/readyz` trên server port chính, probe đi qua cùng cổng ứng dụng. Tuy nhiên **nó vẫn không tự gọi mọi endpoint nghiệp vụ**, nên không phải full route warm-up.

## 14. Nếu warm-up chỉ có thể làm sau ApplicationReadyEvent?

Đây là một mô hình phức tạp hơn. Nếu bạn bắt đầu warm-up bất đồng bộ **sau** mốc ready, Boot có thể chuyển readiness sang `ACCEPTING_TRAFFIC` trước khi task hoàn tất.

Khi đó cần state machine có owner:

1. Đưa `ReadinessState` về `REFUSING_TRAFFIC` nếu ứng dụng chưa có quyền nhận công việc.
2. Chạy warm-up có timeout và kết quả.
3. Chỉ publish `ACCEPTING_TRAFFIC` khi xong điều kiện bắt buộc.
4. Kiểm soát race với availability events mặc định, shutdown và những listener khác.
5. Không đơn giản trông chờ `@Async` sẽ giữ Boot chờ.

API biểu diễn việc chuyển state:

```java
AvailabilityChangeEvent.publish(
        applicationContext, ReadinessState.REFUSING_TRAFFIC);

// Chạy warm-up đã thiết kế: có timeout và failure handling.

AvailabilityChangeEvent.publish(
        applicationContext, ReadinessState.ACCEPTING_TRAFFIC);
```

Đây là snippet **chỉ minh họa API**; `applicationContext` phải là một context hợp lệ, import `AvailabilityChangeEvent` và `ReadinessState`. Không đặt nguyên đoạn ở một `@EventListener(ApplicationReadyEvent.class)` rồi giả định mọi race được giải quyết tự động. Nếu warm-up **phải** xong trước khi nhận traffic, **runner đồng bộ** thường dễ đảm bảo thứ tự hơn nhiều.

## 15. Lỗi cấu hình ở request đầu: nguyên nhân và khắc phục

```text
Startup:
  Bean ReportService @Lazy
  -> chưa được tạo
  -> Boot đạt readiness ACCEPTING_TRAFFIC

GET /reports:
  -> BeanFactory tạo ReportService
  -> thiếu property / dependency / init lỗi
  -> BeanCreationException / root cause
  -> request thất bại
  -> readiness có thể vẫn ACCEPTING_TRAFFIC
```

HTTP status thực tế phụ thuộc exception handling và web stack; không cam kết mọi trường hợp đều cùng một status code.

Cách giảm rủi ro:

- Bean cốt lõi được đánh dấu eager.
- Runner lấy những bean cần thiết và gọi validation/warm-up trước ready.
- Dùng config validation phù hợp.
- Integration test đi qua critical routes và dependency.
- Timeout/fallback được thiết kế rõ với external service.
- Không chỉ tăng health-probe timeout để che lỗi nghiệp vụ.

Một bean lazy ít dùng có thể được chấp nhận phát hiện lỗi khi truy cập trong một số thiết kế plugin/tùy chọn, nhưng phải có policy lỗi phù hợp. Với nghiệp vụ cốt lõi, **fail before traffic** thường đáng tin hơn.

## 16. Đo first-request latency đúng cách

Đừng chỉ nhìn log `Started Application in X seconds`.

| Metric | Câu hỏi |
| --- | --- |
| Process-to-ready | Mất bao lâu trước khi readiness accepting? |
| First-hit latency mỗi route | Người dùng đầu tiên phải đợi bao lâu? |
| p50/p95/p99 sau deploy | Có spike ở traffic đầu không? |
| Bean creation duration | Constructor/init callback nào chậm? |
| Error rate request đầu | Có lỗi init bị giấu tới request không? |
| Startup CPU | Warm-up làm CPU peak ra sao? |
| Heap ngay sau ready | Lợi ích lazy về memory ban đầu thế nào? |
| Heap sau full critical workload | Memory có tăng về mức dự tính không? |
| Database/remote load | Nhiều pods warm cùng lúc có gây bão request không? |

Ví dụ POSIX shell đo hai lượt:

```bash
curl -s -o /dev/null -w 'first=%{time_total}\n' \
  http://localhost:8080/demo/catalog

curl -s -o /dev/null -w 'next=%{time_total}\n' \
  http://localhost:8080/demo/catalog
```

Đây là command dành cho shell có `/dev/null`; trên Windows cần điều chỉnh cách bỏ body và quoting, có thể dùng `curl.exe`. Mỗi phép thử “first” phải dùng **instance mới**; sau khi singleton được tạo, gọi lại trong cùng process không còn tái hiện cold bean creation.

Dùng nhiều lần deploy/multiple instances để có phân phối latency, không kết luận từ một lần chạy trên laptop. Đồng thời so sánh với tỉ lệ lỗi, JIT/GC, CPU và network.

## 17. Tình huống ứng dụng thực tế

**A — dịch vụ thanh toán:** đường chính có SLO chặt. Nên eager/warm các component bắt buộc, validate cấu hình và chỉ công bố ready khi có thể xử lý request an toàn.

**B — cổng báo cáo nhiều module hiếm dùng:** giữ lazy cho report ít truy cập, warm các route phổ biến. Chấp nhận cold latency lần đầu một số module nhưng có test và timeout.

**C — serverless / scale-to-zero:** lazy giúp log startup nhanh nhưng request đầu vẫn phải chịu chi phí nếu instance sống ngắn. Đo toàn bộ thời gian *first invocation*, không chỉ thời gian container boot.

**D — startup cache tốn 60 giây:** nếu cache bắt buộc trước traffic, runner warm-up nên kết thúc trước readiness và phối hợp startup probe/deployment timeout. Nếu cache có thể nạp dần, cân nhắc fallback/partial service và readiness rõ.

**E — dependency ngoài mất kết nối:** lỗi API/DB tạm thời không tự biến liveness thành BROKEN. Quyết định retry/circuit breaker/readiness theo khả năng phục vụ; không khởi động lại mọi pod chỉ vì dịch vụ ngoài đang lỗi.

**F — nhiều request đầu cùng vào một singleton:** có thể gây p99 spike do các request đợi khởi tạo. Warm trong runner hoặc dùng eager cho đường critical.

**G — @Lazy được gắn nhưng startup không thay đổi:** kiểm tra eager graph; bean eager có thể đang inject trực tiếp bean lazy, ép nó tạo sớm.

## 18. Các anti-pattern cần tránh

| Sai lầm | Vì sao sai | Cách thay |
| --- | --- | --- |
| Bật global lazy chỉ để log startup nhanh | Dồn chi phí/lỗi vào traffic thật | Đo startup + first-request + errors |
| Coi /readyz UP là mọi lazy bean đã sẵn sàng | Probe không duyệt toàn bộ BeanFactory | Warm/test critical paths |
| @Lazy bean có @PostConstruct nên chắc chắn đã warm | Callback chỉ chạy khi bean tạo | Eager hoặc runner |
| Eager controller inject trực tiếp lazy service | Service có thể bị tạo sớm | ObjectProvider/lazy injection |
| Đặt @Async vào warm-up và coi Boot đang đợi | Task có thể còn chạy sau ready | Runner đồng bộ hoặc readiness gating |
| Self-HTTP POST để warm-up | Có thể tạo side effect nghiệp vụ | Method warm-up riêng |
| Warm mọi bean | Mất lợi ích lazy, tăng CPU/memory | Chọn critical set |
| Bỏ qua bean init failures tới production | Request đầu tiên gánh lỗi | Startup validation và integration test |
| Dùng liveness để check database | Restart storm khi DB chung lỗi | Phân biệt availability groups |
| Giảm heap dựa trên memory ngay sau startup | Bean lazy tạo về sau | Đo memory sau traffic |
| Chỉ test một request tuần tự | Không thấy burst/p99 | Test concurrency và rollout |
| Để runner warm-up retry vô hạn | Instance không bao giờ ready | Timeout + failure policy |
| Dùng health probe gọi endpoint nghiệp vụ nặng | Probe tự gây tải/side effect | Health indicator nhẹ theo contract |
| Cho readiness accepting ngay khi context created | Runners chưa hoàn tất | Dựa vào Boot ready state hoặc policy |
| Không kiểm soát warm-up nhiều pods | Thundering herd tới DB/remote | Bounded concurrency/rollout |

## 19. Bảng chọn chiến lược

| Mục tiêu | Chiến lược | Giá phải trả |
| --- | --- | --- |
| Phát hiện cấu hình lỗi sớm, startup ổn định | Để mặc định eager | Startup tạo nhiều singleton |
| Tính năng ít dùng, khởi tạo nặng | @Lazy chọn lọc | Cold latency khi dùng lần đầu |
| Startup rất gắt, nhiều bean hiếm dùng | Global lazy + kiểm thử | Quản trị first-hit/error/memory |
| Route critical không được có spike | Eager hoặc runner warm-up | Time-to-ready dài hơn |
| Cần kiểm tra backend trước traffic | Runner fail-fast và readiness đúng | Có thể làm deployment fail nếu backend bắt buộc unavailable |
| Background warm-up sau Boot ready | Điều phối readiness và state machine | Có race và độ phức tạp vận hành |
| Nhiều pods warm dữ liệu chung | Rolling/limit concurrency/cache | Tổng thời gian rollout có thể tăng |
| Service optional có fallback | Lazy + timeout/circuit breaker | Request đầu của feature có thể chậm |

## 20. Câu hỏi tự kiểm tra

**1. Bật global lazy có nghĩa mọi singleton chỉ tạo khi HTTP request đến không?**

Không. Eager dependencies, framework components và runners có thể tạo bean từ trước; bean cũng có thể được yêu cầu bởi scheduler, tests hoặc logic không phải HTTP.

**2. Vì sao @Lazy không luôn giảm startup?**

Một bean eager inject trực tiếp lazy dependency có thể buộc Spring tạo dependency ở startup.

**3. @Lazy ở injection point khác gì @Lazy trên bean?**

Trên bean definition điều khiển eager instantiation; ở injection point có thể dùng proxy để trì hoãn việc resolve.

**4. ApplicationReadyEvent có chờ toàn bộ lazy beans không?**

Không. Boot chờ các bước startup bắt buộc, không chủ động instantiate mọi bean lazy.

**5. Readiness 200 có đảm bảo request đầu không chậm?**

Không. Probe không warm mọi route; JIT, cache, network, serializer và lazy bean vẫn có thể cold.

**6. ApplicationRunner warm-up chạy trước hay sau ready?**

Trước `ApplicationReadyEvent` và trước `ReadinessState.ACCEPTING_TRAFFIC` trong chuỗi Boot 3.3 tiêu chuẩn.

**7. Có thể giảm latency request đầu mà không bật global lazy không?**

Có. Tối ưu bean initialization, cache, connection pool, JVM/JIT hoặc warm request path an toàn tùy bottleneck.

**8. Tại sao không dùng @Async rồi coi warm-up đã xong?**

Task async có thể tiếp tục sau khi method runner return và Boot accepting traffic.

**9. Có nên add DB health vào liveness để biết app phục vụ được chưa?**

Thông thường không: lỗi DB chung có thể khiến mọi pods restart đồng loạt.

**10. Khi nào nên dùng @Lazy(false) dù global lazy bật?**

Với runner/bean critical cần được tạo ở startup hoặc muốn phát hiện cấu hình lỗi trước traffic.

**11. Một singleton lazy có được tạo lại với mỗi request không?**

Không. Nó thường chỉ tạo một lần cho BeanFactory; scope request/prototype là cơ chế khác.

**12. Chỉ đo heap ngay sau startup đủ để chọn memory limit không?**

Không. Bean lazy có thể làm memory tăng đáng kể sau khi nhiều chức năng được gọi.

## 21. Checklist triển khai

1. Xác định mục tiêu: startup, memory, first-request SLO hay reliability.
2. Lấy baseline của time-to-ready và first-hit latency trước khi đổi lazy.
3. Chọn global lazy hoặc từng bean có lý do rõ.
4. Rà dependency graph: có eager singleton nào đang kéo lazy bean không?
5. Xác định critical routes và beans liên quan.
6. Làm eager hoặc warm-up những dependency bắt buộc trước ready.
7. Dùng ObjectProvider/lazy injection khi cần trì hoãn thật.
8. Với warm-up runner trong app global lazy, đánh dấu runner eager nếu cần.
9. Warm-up phải idempotent và không tạo side effect nghiệp vụ.
10. Đặt timeout, retry policy và hành vi fail-fast/fallback.
11. Không đồng nhất @PostConstruct với eager startup trên lazy bean.
12. Kiểm thử property/config sai, init exception và request đầu.
13. Quan sát /readyz cùng request nghiệp vụ thật, không chỉ /ping.
14. Đo cold request p95/p99 sau nhiều rollout với concurrency.
15. Theo dõi memory/CPU sau khi lazy beans đã được tạo.
16. Giới hạn warm-up concurrency khi nhiều pod startup cùng lúc.
17. Cấu hình startupProbe phù hợp nếu warm-up kéo dài.
18. Không đưa external health checks vào liveness tùy tiện.
19. Phân biệt bean warm-up, service warm-up và full HTTP path warm-up.
20. Giữ khả năng rollback cấu hình nếu lazy tăng error/latency.
21. Không lộ secrets trong logs/Actuator.
22. Chọn chiến lược rõ cho các tính năng optional.

## 22. Tóm tắt

```text
SPRING BOOT LAZY INITIALIZATION
        |
        +-- Startup có thể ngắn hơn
        |
        +-- Có thể còn bean chưa tạo sau ApplicationReadyEvent
                    |
                    +-- Request đầu: trả cold cost / gặp init failure
                    |
                    +-- HOẶC ApplicationRunner khởi tạo critical beans
                             trước readiness ACCEPTING_TRAFFIC

READY != mọi bean lazy đã được khởi tạo
READY != mọi đường request đã warm
READY != mọi dependency ngoài khỏe
```

**Nguyên tắc cốt lõi:** lazy **dịch chi phí và thời điểm phát hiện lỗi**, không làm chúng biến mất. Đối với các đường xử lý quan trọng, hãy làm nóng hoặc tạo bean **trước khi nhận traffic** và xác minh bằng các phép đo first-request thực tế. `ApplicationRunner` đồng bộ là lựa chọn đơn giản khi warm-up là điều kiện bắt buộc trước readiness; còn liveness, readiness và health indicators cần giữ đúng mục đích của từng loại.

## Tài liệu chính thức

- [Spring Boot 3.3 — SpringApplication: Lazy Initialization, Application Events, Runners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — Actuator Endpoints và Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3 — SpringApplication.setLazyInitialization API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Framework 6.1 — @Lazy annotation API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/annotation/Lazy.html)
- [Spring Framework — Lazy-initialized Beans và eager dependencies](https://docs.spring.io/spring-framework/reference/6.1/core/beans/dependencies/factory-lazy-init.html)
- [Spring Framework 6.1 — ObjectProvider API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/beans/factory/ObjectProvider.html)
