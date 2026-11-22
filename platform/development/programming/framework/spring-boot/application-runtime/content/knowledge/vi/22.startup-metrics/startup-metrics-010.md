# Đánh giá khởi động nguội, khởi động lại và lần sử dụng đầu tiên trong Spring Boot

Một ứng dụng Spring Boot có thể in dòng `Started ... in ... seconds` rất nhanh nhưng request đầu tiên lại chậm. Ngược lại, lần đầu mở JVM có thể mất nhiều giây, còn các lần request sau nhanh vì class đã được nạp, JIT đã biên dịch mã nóng, connection pool đã có kết nối và cache đã được tạo. Nếu chỉ đo một con số “startup time”, bạn dễ tối ưu nhầm chỗ hoặc chuyển độ trễ từ giai đoạn khởi động sang người dùng đầu tiên.

Cần phân biệt **ba kịch bản**, đo bằng các mốc thời gian và điều kiện thử nghiệm rõ ràng:

1. **Khởi động nguội (cold start):** khởi chạy **một JVM/process mới**, tạo Spring ApplicationContext mới, khởi tạo web server, beans và dependency. Có thể mở rộng thành cold start của container/Pod, nhưng phải tách thời gian image pull/scheduling khỏi thời gian Java.
2. **Khởi động lại (restart):** phải nói rõ là **restart JVM hoàn toàn**, **restart container/Pod**, hay **DevTools restart chỉ thay ApplicationContext/classloader trong cùng JVM**. Chúng có chi phí và bộ nhớ đệm còn lại khác nhau.
3. **Lần sử dụng đầu tiên (first use):** sau khi ứng dụng được báo Ready, request hoặc tác vụ đầu tiên chạm vào đường code, bean `@Lazy`, serializer, DNS, TLS, JPA query, template hay cache chưa được làm nóng. Đây là **độ trễ thực tế của lần sử dụng đầu**, không nhất thiết nằm trong thời gian `ApplicationReadyEvent`.

**Nguyên tắc:** một ứng dụng “Ready nhanh hơn” chưa chắc có trải nghiệm tốt hơn nếu chỉ trì hoãn công việc sang request đầu tiên. Cần đo cả **time-to-ready** và **first useful response**, kèm tài nguyên CPU/bộ nhớ và tính đúng đắn của readiness.

Ví dụ dùng **Java 17+ và Spring Boot 3.3.x**. Nội dung nói tới DevTools chỉ để đo và phát triển, không khuyến nghị mang DevTools vào production.

## 1. Định nghĩa ba loại khởi động trước khi so sánh

| Kịch bản | JVM/process | Spring ApplicationContext | Thứ có thể được giữ lại | Mục đích phép đo |
|---|---|---|---|---|
| **Process cold start** | Tạo JVM mới | Tạo mới | OS page cache, image layers, DNS/caches ngoài process có thể vẫn ấm | Mất bao lâu từ launch JVM đến ready? |
| **Process restart** (stop rồi chạy JAR lại) | **JVM mới** | Tạo mới | OS page cache hoặc external service cache; **không giữ heap/JIT của JVM cũ** | Startup lần hai có nhanh hơn nhờ môi trường đã ấm? |
| **Container restart** | Thường tiến trình JVM mới | Tạo mới | Image có thể sẵn trên node, volume/cache ngoài process tùy cấu hình | Time-to-ready của restart dưới orchestrator |
| **DevTools restart** | **Cùng JVM** | Đóng context cũ, tạo context mới | Base classloader/dependencies và một số trạng thái JVM còn tồn tại | Vòng phản hồi nhanh khi phát triển |
| **First use sau Ready** | JVM đã chạy | Context đang active | JIT/class/cache/pool được làm nóng dần sau từng request | Độ trễ request/job đầu tiên so với những lần sau |

**Cold start không nhất thiết đồng nghĩa cold OS cache.** Chạy `java -jar app.jar` lần đầu sau reboot có thể khác lần đầu của **một JVM mới** trên máy vốn đã chạy ứng dụng trước đó. Nếu không kiểm soát cache hệ điều hành, hãy gọi chính xác phép đo là **fresh-process startup**, thay vì khẳng định “máy nguội hoàn toàn”.

Tương tự, **restart JVM** và **DevTools restart** không phải phép đo tương đương. DevTools cố tình giữ lại base classloader của các thư viện ít thay đổi, do đó restart thường nhanh hơn khởi chạy JVM mới.

## 2. Các đồng hồ và mốc đo cần phân biệt

Một timeline thực tế có thể như sau:

~~~text
t0   Launcher bắt đầu tạo tiến trình
 |
 | JVM bootstrap: tải runtime, đọc classpath/JAR, class loading đầu tiên
 |
t1   SpringApplication bắt đầu chuỗi startup
 |
 | ApplicationContext tạo/refresh beans
 |
t2   ApplicationStartedEvent
 |    -> Context đã refresh, trước ApplicationRunner/CommandLineRunner
 |
 | ApplicationRunner/CommandLineRunner thực thi
 |
t3   ApplicationReadyEvent
 |    -> Mốc Boot cho biết ứng dụng sắp hoàn tất startup bình thường
 |
 | Spring Boot chuyển trạng thái availability/readiness theo lifecycle
 |
t4   Readiness probe của ứng dụng thực sự thành công
 |
 | Traffic được chuyển đến instance (có thể có độ trễ router/Service)
 |
t5   Request nghiệp vụ đầu tiên đến
 |    -> Có thể lazy-init bean, tạo pool connection, nạp cache, JIT...
 |
t6   Response nghiệp vụ đầu tiên hoàn tất
 |
t7   Một request tương đương về sau hoàn tất
~~~

**Đừng mặc định tất cả các mốc trùng nhau.**

- `ApplicationStartedEvent` được phát sau khi context refresh, **trước** runners.
- `ApplicationReadyEvent` được phát rất muộn trong chuỗi startup, **sau** runners; thời gian của event có thể lấy từ `getTimeTaken()`.
- `ApplicationReadyEvent` không tự đo thời gian tạo Pod, download image hay DNS/network routing.
- Probe readiness là **một phép HTTP/exec kiểm tra** có lịch và ngưỡng riêng. Thời điểm kubelet thấy thành công có thể **muộn hơn** mốc ready event.
- Response đầu tiên có thể kéo dài thêm vì công việc được trì hoãn. Một health endpoint nhẹ thành công không bảo đảm đường nghiệp vụ nặng cũng đã warm.
- Nếu app có `ApplicationRunner` thực hiện đồng bộ một công việc dài, khoảng từ `ApplicationStartedEvent` tới `ApplicationReadyEvent` sẽ phản ánh thêm thời gian runner đó.

### Các metric nên báo cáo tách biệt

| Tên đo | Công thức khái niệm | Công dụng |
|---|---|---|
| `JVM-to-Ready` | Process launch → readiness probe thành công | Góc nhìn orchestrator/launcher |
| `Spring started time` | Timer nội bộ SpringApplication → `ApplicationStartedEvent` | Spring context + lifecycle trước runner |
| `Spring ready time` | Timer nội bộ SpringApplication → `ApplicationReadyEvent` | Bao gồm runner trước Ready |
| `Ready-to-first-response` | Sau Ready → hoàn tất request nghiệp vụ đầu | Gắn startup với trải nghiệm |
| `First-request latency` | Request đầu tới → response đầu trả về | Cold path của request |
| `Steady-request latency` | Một request tương đương sau khi warm | Giá trị đối chứng |
| `First-use penalty` | First-request latency − latency baseline đã warm | Độ trễ tăng thêm ước lượng |

Khoảng `First-use penalty` phải được đo bằng những request **tương đương**; nếu lần đầu đọc tập dữ liệu lớn, lần sau chỉ đọc cache, cần nói rõ chính cache là biến số mà bạn đang đánh giá.

## 3. Dùng ApplicationStartedEvent và ApplicationReadyEvent

Spring Boot 3.3 cung cấp `Duration getTimeTaken()` trên cả hai event:

- `ApplicationStartedEvent.getTimeTaken()`: thời gian Spring Boot ghi nhận để ứng dụng **start** (sau refresh, trước runners).
- `ApplicationReadyEvent.getTimeTaken()`: thời gian để ứng dụng **ready** theo lifecycle Spring Boot.

Dữ liệu có thể là `null` nếu không xác định được; code quan sát nên xử lý trường hợp này thay vì mặc định gọi `toMillis()` không điều kiện.

Ví dụ minh họa trong một Spring bean:

~~~java
@Component
class StartupEventReporter {

    @EventListener
    void started(ApplicationStartedEvent event) {
        Duration duration = event.getTimeTaken();
        System.out.println(
                "started_ms=" + (duration == null
                        ? "unknown" : duration.toMillis()));
    }

    @EventListener
    void ready(ApplicationReadyEvent event) {
        Duration duration = event.getTimeTaken();
        System.out.println(
                "ready_ms=" + (duration == null
                        ? "unknown" : duration.toMillis()));
    }
}
~~~

Đây là **đoạn minh họa**, cần import `Component`, `EventListener`, `Duration`, `ApplicationStartedEvent` và `ApplicationReadyEvent`. Chương trình chạy đầy đủ nằm ở mục 7.

**Không tính một cách tùy tiện:** `ready_ms - started_ms` có thể giúp ước lượng thời gian giữa hai mốc nội bộ của cùng lần chạy khi cả hai Duration hợp lệ, nhưng không chứng minh toàn bộ khoảng đó chỉ thuộc `ApplicationRunner`. Những sự kiện, listener và công việc khác cũng có thể góp phần vào chuỗi startup.

### Dòng log “Started in...” có đo hết JVM không?

Spring Boot thường in một dòng như:

~~~text
Started DemoApplication in 3.218 seconds (process running for 3.741)
~~~

Đây là **ví dụ định dạng**, không phải kết quả đã đo trong môi trường của bạn. Con số “in ... seconds” phản ánh startup theo cách Boot tính, còn “process running for ...” liên quan uptime của process JVM. Hai mốc có thể khác nhau và đều chưa bao gồm thời gian scheduler tải image, chờ cấp Pod, hoặc latency mạng tới ứng dụng.

Khi so sánh nhiều lần chạy, **không lấy timestamp giữa hai dòng log từ những process khác nhau** để suy ra chính xác độ trễ. Đồng hồ wall clock, đồng bộ log, buffer và start point có thể khác nhau.

## 4. ApplicationStartup và startup endpoint giúp nhìn vào pha nào?

Spring Framework có `ApplicationStartup` để ghi lại các `StartupStep` ở quá trình khởi động: đăng ký/khởi tạo beans, xử lý lifecycle và những bước được Spring instrument. Spring Boot cung cấp implementation `BufferingApplicationStartup`.

Cấu hình trong `main`:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(2048));
app.run(args);
~~~

Đây là đoạn minh họa cần class `DemoApplication` cùng import `SpringApplication` và `org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup`. Việc cấu hình phải diễn ra **trước `run(args)`** để ghi được những bước khởi động ban đầu.

Nếu có `spring-boot-starter-actuator` và endpoint `startup` được expose qua HTTP, bạn có thể gọi:

~~~bash
curl -s http://localhost:8080/actuator/startup
~~~

Đối với Spring Boot 3.3, endpoint hỗ trợ:

- **`GET /actuator/startup`**: snapshot những steps còn trong buffer.
- **`POST /actuator/startup`**: lấy và **drain** các steps từ buffer. Những lần GET sau không còn trả lại chính các steps đã bị drain như trước.

Dữ liệu là JSON, với các trường như `timeline.startTime`, `timeline.events[].duration` và `startupStep.name`, `startupStep.id`, `startupStep.parentId`, `startupStep.tags`. Không nhầm mỗi step duration là một phần tuần tự không chồng lấn: các bước có quan hệ cha-con và có thể nested; **không cộng tất cả duration để suy ra startup time**.

### Startup endpoint không tự xuất hiện chỉ vì có Actuator

Cần cấu hình **SpringApplication có BufferingApplicationStartup**, đồng thời expose endpoint:

~~~properties
management.endpoints.web.exposure.include=health,metrics,startup
~~~

Nếu không cấu hình buffer, chỉ bật `management.endpoints.web.exposure.include=startup` sẽ **không đủ** để có dữ liệu phù hợp. Nếu endpoint đã bị disable bằng cấu hình khác, phải kiểm tra lại enablement. Trong production, **bảo vệ endpoint này** và không công khai toàn bộ startup/bean metadata ra Internet.

Buffer có **dung lượng hữu hạn**. Chọn size đủ lớn cho mức độ chi tiết cần đo, theo dõi việc mất step nếu quá nhỏ và cân nhắc overhead. Khi đo performance, bật/tắt instrumentation nhất quán giữa các lần chạy để tránh làm kết quả không so sánh được.

## 5. FlightRecorderApplicationStartup và JFR: tìm nguyên nhân sâu hơn

Khi timeline cho thấy startup chậm nhưng bạn chưa biết vì đâu, Java Flight Recorder (JFR) giúp tương quan Spring startup steps với JVM events như class loading, allocation, GC, CPU hay những tác vụ I/O có thể quan sát.

Spring Framework cung cấp `FlightRecorderApplicationStartup`:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setApplicationStartup(new FlightRecorderApplicationStartup());
app.run(args);
~~~

Đây là **phương án thay thế** `BufferingApplicationStartup` trong `main`, không phải cấu hình cần dùng đồng thời trong chương trình ví dụ. Cần import `org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup`.

Khởi chạy JFR **từ đầu JVM** để không bỏ lỡ pha startup:

~~~bash
java -XX:StartFlightRecording=filename=startup.jfr,duration=30s \
     -jar build/libs/startup-measurement.jar
~~~

Lệnh minh họa cho HotSpot/JDK hỗ trợ JFR, chạy trong môi trường lab. Dấu `\` ở cuối dòng chỉ là nối dòng của shell Unix; trên Windows hãy đặt thành một dòng phù hợp hoặc dùng cú pháp PowerShell.

Lưu ý:

- Nếu chỉ chạy `jcmd <PID> JFR.start` **sau khi app đã Ready**, những sự kiện khởi động đầu tiên đã trôi qua; recording đó không thể “đo ngược thời gian”.
- JFR có overhead và tệp có thể chứa dữ liệu vận hành nhạy cảm. Dùng recording được phép, có retention và bảo mật phù hợp.
- `FlightRecorderApplicationStartup` thêm sự kiện startup vào JFR; nó **không thay thế** việc đo external time-to-ready hoặc request đầu tiên.
- Dùng JDK Mission Control hoặc công cụ tương thích để xem flame/stack/timeline, và đối chiếu cùng một workload có cấu hình JVM tương đương.

## 6. Thế nào là “first-use latency”?

Sau khi Spring Boot Ready, vẫn có nhiều công việc chỉ thực sự phát sinh khi **một đường xử lý được gọi lần đầu**:

- **Lazy bean:** `@Lazy` hoặc `spring.main.lazy-initialization=true` trì hoãn bean instantiation.
- **Spring MVC/Jackson:** khởi tạo một số cấu trúc liên quan tới dispatch, serialization hay serializer caching khi request đầu tới.
- **JPA/Hibernate:** chuẩn bị query/metadata và tạo connection lần đầu dùng datasource.
- **Network:** DNS lookup, TLS handshake, connection establishment/pool warm-up.
- **CPU/JIT:** class loading và JIT compilation của nhánh code mới được thực thi.
- **Cache:** query đầu tiên phải tải dữ liệu, tiếp theo có thể đọc cache.
- **Template/regex/codec:** compile hoặc khởi tạo internal cache trong lần sử dụng đầu.
- **External dependency:** dịch vụ đang chậm/timeout có thể làm cold request lâu nhưng không phải lỗi của Spring context.

Vì vậy một service có thể có:

~~~text
Spring ready time        = 1.2s   (ví dụ giả định)
HTTP request đầu        = 750ms  (ví dụ giả định)
HTTP request sau warm   = 35ms   (ví dụ giả định)
~~~

Các số này là **minh họa phương pháp đọc**, không phải benchmark Spring Boot. Không suy ra ứng dụng thực tế cũng có chênh lệch tương tự.

### Lazy initialization: tối ưu hay chuyển chi phí?

Spring Boot cho phép:

~~~properties
spring.main.lazy-initialization=true
~~~

Điều này có thể rút ngắn thời gian khởi động bằng cách tạo beans **khi cần**, thay vì tất cả trong pha startup. Nhưng có hai đánh đổi quan trọng:

1. **Chuyển độ trễ** sang request/tác vụ đầu tiên.
2. **Trì hoãn phát hiện lỗi:** bean cấu hình sai có thể chỉ gây lỗi khi người dùng chạm đến lần đầu, thay vì fail-fast lúc startup.

Nếu muốn kiểm chứng tác động, hãy đo đủ bộ: `started_ms`, `ready_ms`, ready probe, first-request latency và warm-request latency. Đừng chỉ so sánh một log startup.

## 7. Ví dụ Java 17+ Spring Boot 3.3: đo Ready và first-use độc lập

Ví dụ sau có:

- `ApplicationStartedEvent` và `ApplicationReadyEvent` ghi Duration nội bộ.
- `BufferingApplicationStartup` để đọc startup steps.
- Endpoint `/readyz` phục vụ thí nghiệm time-to-ready trên main port.
- Endpoint `/demo/use` sử dụng một bean `@Lazy` thông qua `ObjectProvider`.
- Bean lazy **cố tình ngủ 300ms trong constructor** để mô phỏng chi phí khởi tạo; vì vậy request đầu tiên thường có chi phí khác biệt rõ, còn request sau không tạo bean nữa.

**Mã sleep 300ms chỉ là cơ chế học tập**, tuyệt đối không xem nó là cách tối ưu production.

### 7.1 Cấu trúc dự án

~~~text
startup-measurement/
├── build.gradle
└── src/
    └── main/
        ├── java/com/example/startup/StartupMeasurementApplication.java
        └── resources/application.properties
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
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
}

springBoot {
    mainClass = 'com.example.startup.StartupMeasurementApplication'
}

tasks.named('bootJar') {
    archiveFileName = 'startup-measurement.jar'
}
~~~

Tệp `src/main/resources/application.properties`:

~~~properties
spring.application.name=startup-measurement
server.port=8080
management.endpoints.web.exposure.include=health,metrics,startup
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
management.endpoint.health.show-details=never
logging.level.root=INFO
~~~

`management.endpoint.health.probes.enabled=true` bật các health groups của Kubernetes probes cả khi chạy ngoài Kubernetes. `management.endpoint.health.probes.add-additional-paths=true` tạo `/livez` và `/readyz` trên **cổng HTTP chính**, để phép đo không dựa vào một management port tách biệt.

### 7.2 File Java đầy đủ

Tệp `src/main/java/com/example/startup/StartupMeasurementApplication.java`:

~~~java
package com.example.startup;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class StartupMeasurementApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(StartupMeasurementApplication.class);

        // Bắt đầu ghi Spring startup steps TRƯỚC run(args).
        app.setApplicationStartup(new BufferingApplicationStartup(2048));
        app.run(args);
    }

    @Component
    public static class StartupMarkers {

        @EventListener
        public void started(ApplicationStartedEvent event) {
            System.out.println("EVENT_STARTED "
                    + formatDuration(event.getTimeTaken()));
        }

        @EventListener
        public void ready(ApplicationReadyEvent event) {
            System.out.println("EVENT_READY "
                    + formatDuration(event.getTimeTaken()));
        }

        private static String formatDuration(Duration duration) {
            return duration == null
                    ? "duration=unknown"
                    : "durationMs=" + duration.toMillis();
        }
    }

    @Lazy
    @Component
    public static class SlowCatalog {

        public SlowCatalog() {
            try {
                // Chi phí cố ý cho thí nghiệm first use.
                Thread.sleep(300);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "catalog initialization interrupted", exception);
            }
            System.out.println("CATALOG_INITIALIZED");
        }

        public String read() {
            return "catalog-ready";
        }
    }

    @RestController
    public static class DemoController {

        private final ObjectProvider<SlowCatalog> catalogProvider;
        private final AtomicInteger requestCount = new AtomicInteger();

        public DemoController(
                ObjectProvider<SlowCatalog> catalogProvider) {
            this.catalogProvider = catalogProvider;
        }

        @GetMapping("/demo/use")
        public Map<String, Object> use() {
            long began = System.nanoTime();

            // ObjectProvider chưa yêu cầu tạo bean ở constructor.
            String result = catalogProvider.getObject().read();

            long handlerMillis = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - began);

            return Map.of(
                    "result", result,
                    "requestSequence", requestCount.incrementAndGet(),
                    "handlerMillis", handlerMillis);
        }
    }
}
~~~

### 7.3 Tại sao ví dụ phân biệt được hai pha?

- `StartupMarkers` là Spring bean được khởi tạo trong startup bình thường, bắt hai event và ghi thời gian mà Boot đo.
- `SlowCatalog` được đánh dấu `@Lazy`, nên container **không cần khởi tạo trước** khi có code yêu cầu bean.
- `DemoController` chỉ inject `ObjectProvider<SlowCatalog>`; provider **không buộc SlowCatalog được tạo** ở lúc controller constructor chạy.
- Request đầu tiên đi qua `getObject()` sẽ trigger tạo singleton `SlowCatalog`, sleep 300ms và in `CATALOG_INITIALIZED`.
- Những request tiếp theo nhận cùng singleton, không sleep lần nữa vì constructor không chạy lại.
- `System.nanoTime()` đo **thời gian trong handler** từ khi vào method tới khi trả kết quả, thích hợp cho khoảng đo trong một process; nó **không bao gồm** toàn bộ HTTP network/serialization/client latency.

Đừng xem `handlerMillis` của request đầu như chính xác bằng 300. Nó còn gồm công việc khác trong handler, scheduling, contention hoặc GC pause. Ngược lại, client-reported total request time thường lớn hơn vì bao gồm các pha trước và sau handler.

**Concurrency:** Spring singleton initialization được quản lý bởi container. Nếu hai request đầu cùng tới, cả hai có thể bị ảnh hưởng bởi thời gian chờ bean init, dù constructor chỉ thực hiện một lần. Vì vậy hãy làm thí nghiệm đơn luồng trước khi thử tải song song.

### 7.4 Build và chạy

Với Gradle wrapper và JDK 17+:

~~~bash
./gradlew bootJar
java -jar build/libs/startup-measurement.jar
~~~

Trên Windows PowerShell, thay bước build bằng `.\gradlew.bat bootJar`. Nếu chưa có Gradle wrapper, cần chuẩn bị bản Gradle tương thích trước. Vì đây là code Spring Boot, không thể biên dịch bằng `javac StartupMeasurementApplication.java` độc lập mà không có Spring libraries trên classpath.

Trong log startup, bạn sẽ thấy các dòng có dạng:

~~~text
EVENT_STARTED durationMs=<so_mili_giay_thuc_te>
EVENT_READY durationMs=<so_mili_giay_thuc_te>
~~~

`<so_mili_giay_thuc_te>` là **ký hiệu thay thế trong mô tả**, không phải chuỗi literal chương trình in. Kết quả thật tùy môi trường, và `EVENT_READY` thường xuất hiện sau `EVENT_STARTED` theo lifecycle bình thường.

**Không mong thấy `CATALOG_INITIALIZED` ngay trong startup** nếu không có component khác gọi `SlowCatalog`. Trong chương trình này, bean được truy cập tại endpoint `/demo/use` để tạo ví dụ first-use.

### 7.5 Đọc startup timeline và kiểm chứng first use

Sau khi ứng dụng Ready:

~~~bash
curl -s http://localhost:8080/actuator/health
curl -s http://localhost:8080/actuator/startup
curl -s http://localhost:8080/demo/use
curl -s http://localhost:8080/demo/use
~~~

Kết quả `/demo/use` có **các trường**:

~~~json
{"result":"catalog-ready","requestSequence":1,"handlerMillis":315}
~~~

và lần sau, chẳng hạn:

~~~json
{"result":"catalog-ready","requestSequence":2,"handlerMillis":0}
~~~

**315 và 0 chỉ là giá trị minh họa**, không phải kỳ vọng bắt buộc; JSON object key order cũng không được bảo đảm. Trường `requestSequence` sẽ là 1 và 2 nếu không có request nào khác gọi endpoint; `CATALOG_INITIALIZED` sẽ được in một lần trong log khi singleton được tạo.

Điểm kiểm chứng: request thứ nhất còn chi phí tạo bean chậm; request thứ hai không tạo lại bean đó. Cả hai đều diễn ra **sau khi application đã Ready**. Nếu đo chỉ `ApplicationReadyEvent.getTimeTaken()`, bạn sẽ **không thấy trọn vẹn chi phí** đó.

### 7.6 Phân biệt GET và POST startup endpoint

~~~bash
curl -s -X GET http://localhost:8080/actuator/startup
curl -s -X POST http://localhost:8080/actuator/startup
~~~

`GET` lấy snapshot; `POST` **drain buffer**, tức đọc và lấy các steps khỏi bộ đệm hiện tại. Khi làm benchmark nhiều lần, đừng gọi POST ở một bước mà sau đó còn kỳ vọng GET vẫn trả nguyên timeline cũ.

Cẩn thận: `ApplicationStartup` chỉ ghi **các bước được Spring instrument**. Nó không tự có đủ mọi kết nối mạng/từng bean của third-party, và timeline có thể hữu hạn do buffer. Để quan sát first-use request, cần thêm metrics/tracing của chính endpoint.

## 8. Đo time-to-ready từ góc nhìn process bên ngoài

Bên cạnh event nội bộ, nên đo **từ lúc launcher bắt đầu tạo JVM tới khi HTTP readiness thực sự thành công**.

Ví dụ Bash trên Linux có **GNU date** (hỗ trợ `date +%s%3N`). Chỉ chạy trong môi trường lab và bảo đảm port 8080 chưa bị process khác chiếm:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

jar="build/libs/startup-measurement.jar"

start_ms=$(date +%s%3N)
java -jar "$jar" > startup-run.log 2>&1 &
pid=$!

trap 'kill -TERM "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true' EXIT

ready=0
for attempt in $(seq 1 300); do
    if curl --silent --fail --max-time 1 \
         http://127.0.0.1:8080/readyz >/dev/null 2>&1; then
        ready=1
        break
    fi

    if ! kill -0 "$pid" 2>/dev/null; then
        echo "JVM exited before readiness"
        exit 1
    fi

    sleep 0.1
done

if [ "$ready" -ne 1 ]; then
    echo "Readiness timeout"
    exit 1
fi

ready_ms=$(( $(date +%s%3N) - start_ms ))
echo "external_ready_ms=$ready_ms"

curl --silent --output /dev/null \
     --write-out 'first_http_total_s=%{time_total}\n' \
     http://127.0.0.1:8080/demo/use

curl --silent --output /dev/null \
     --write-out 'second_http_total_s=%{time_total}\n' \
     http://127.0.0.1:8080/demo/use
~~~

Lưu ví dụ trên thành một script nếu muốn chạy nhiều lần trong lab. Kết quả dạng:

~~~text
external_ready_ms=...
first_http_total_s=...
second_http_total_s=...
~~~

Dấu `...` ở đây là **giá trị thời gian biến thiên**, không phải số benchmark được bịa. Script giữ JVM tới khi thu xong hai kết quả rồi gửi TERM ở trap.

### Giới hạn của script

- `start_ms` được lấy trong shell trước lệnh `java`, nên nó đo **launch-to-readiness từ ngoài process**, không hoàn toàn trùng đồng hồ Spring Boot.
- Poll interval `0.1s`, thời gian chạy `curl` và lịch OS tạo sai số: readiness có thể đã thành công **trước thời điểm lần probe trả về**.
- `date +%s%3N` dùng wall clock trên GNU date, có thể chịu điều chỉnh đồng hồ; phép đo lab đơn giản không phải timing harness chuẩn chuyên nghiệp. Để benchmark chính xác hơn, dùng clock monotonic và API `ProcessBuilder` trong một harness chuyên dụng.
- Nếu HTTP server trên port 8080 đã tồn tại, probe có thể đọc nhầm process. Cần dùng port riêng/kiểm tra PID và cô lập môi trường.
- Client `curl` có thể trả total time bao gồm TCP setup, network, response serialization và thread scheduling; đó là **điểm đo bên ngoài** có giá trị khác với `handlerMillis`.
- Script không tự đặt giới hạn tổng thời gian chuẩn cho OS scheduler lớn hay host quá tải; tối ưu cho minh họa kiểm soát, không phải harness benchmark hàng nghìn lần.
- Không xóa OS caches hoặc thay đổi cấu hình kernel để “tạo cold start thật” trên máy dùng chung nếu chưa có quyền và phương án an toàn.

## 9. Ba thí nghiệm riêng, không trộn kết quả

### Thí nghiệm A — Fresh-process cold startup

1. Build **một bản JAR duy nhất** rồi giữ nguyên SHA/version.
2. Đảm bảo không có bản app nào khác chiếm port.
3. Chạy JAR trong một JVM mới.
4. Đo `ApplicationStartedEvent`, `ApplicationReadyEvent`, external readiness và request đầu tiên.
5. Dừng process, xác nhận nó thoát.
6. Lặp nhiều lần, ghi mỗi run là một mẫu.

Với cùng JAR mà lần đầu chậm, lần sau nhanh, có thể do OS file cache, dependency warm state hoặc nền tảng phần cứng, **không phải JVM cũ giữ lại JIT/heap** vì mỗi run là process mới.

Nếu cần “cold machine/container image” thật, hãy tạo môi trường test riêng và đo image pull + container scheduling thành chỉ số riêng, không gộp chúng vào số Boot đo.

### Thí nghiệm B — Restart

Phải ghi rõ **kiểu restart**:

**B1. Restart JVM hoàn toàn:** gửi TERM, đợi exit, chạy lại `java -jar`. JVM mới, heap/JIT/compiler state từ JVM cũ **không được giữ**. OS cache và external cache có thể còn ấm.

**B2. DevTools restart:** trong môi trường development có `spring-boot-devtools`, thay đổi classpath và để DevTools tạo restart classloader/context mới **trong cùng JVM**. Base classloader có thể được giữ, do đó thời gian thường ngắn hơn process cold startup.

**B3. Restart Pod/container:** Kubernetes/container runtime tạo process/container theo chính sách, có thể reuse image layers; còn thời gian scheduling, probes, volume mounts, DNS và network routing. Không suy ra thời gian từ DevTools restart có đại diện cho production rolling restart.

### Thí nghiệm C — Lần sử dụng đầu tiên

1. Chạy app tới khi readiness success.
2. **Không gọi `/demo/use` trước phép đo.**
3. Gọi endpoint một lần, đo client total và server handler.
4. Gọi cùng endpoint thêm 10–30 lần, ghi latency từng lần.
5. So sánh request đầu với phân phối warm requests.
6. Tạo JVM mới và lặp lại để lấy **nhiều mẫu first-use**, thay vì chỉ có một mẫu duy nhất.

Cần tránh “warming” lén trong bước kiểm tra: một synthetic monitor, readiness check tùy chỉnh hoặc browser tab có thể đã gọi đường nghiệp vụ trước bạn. Nếu như vậy “request đầu tiên” trong log không phải first use của bean nữa.

## 10. DevTools restart: hai classloader và nguy cơ so sánh sai

Trong môi trường phát triển, Spring Boot DevTools dùng:

- **Base classloader:** nạp nhiều thư viện/dependencies ít thay đổi.
- **Restart classloader:** nạp code ứng dụng đang phát triển và được thay thế khi DevTools restart.

Quá trình restart thường:

~~~text
JVM đang tồn tại
    |
    +-- Base classloader vẫn còn
    |
    +-- Context và restart classloader cũ được đóng/bỏ
    |
    +-- Tạo restart classloader mới
    +-- Tạo Spring ApplicationContext mới
    +-- Startup callbacks chạy lại
~~~

Điều này thường nhanh hơn cold start vì một số class không cần nạp lại. Nhưng nó không đại diện cho **JVM bootstrap**, OS image pull hay latency deployment thật. Ngoài ra, DevTools áp dụng một số development-time defaults (ví dụ caching) có thể khác production.

Khi thiết kế benchmark startup:

- **Không dùng DevTools restart time** để cam kết thời gian khởi động container production.
- Nếu đang đo DevTools, đo riêng **IDE change-to-ready** và **classloader/context restart**, không gọi là JVM cold start.
- DevTools thường không có trong repackaged production JAR; không cố bật DevTools production để đo.
- Nếu DevTools hoạt động sai do giữ reference tới classloader cũ, đó là một vấn đề lifecycle/resource ownership khác; có thể khiến các lần restart sau ngày càng chậm hoặc làm heap/metaspace tăng.

Một kết quả hợp lệ có thể là DevTools restart 0,8 giây và JVM fresh-process startup 3,5 giây. Hai số ở đây chỉ **minh họa**, và sự chênh lệch không chứng minh performance bug.

## 11. Readiness, startupProbe và khả năng phục vụ thực tế

Trong Kubernetes, **readiness** điều phối việc Pod có nên nhận traffic từ Service hay không; **startup probe** dành riêng khoảng thời gian startup để tránh liveness/readiness can thiệp quá sớm.

Các đường đo có thể khác nhau:

- `/actuator/health/readiness`: health group readiness.
- `/readyz`: đường bổ sung trên **main HTTP port** nếu cấu hình `management.endpoint.health.probes.add-additional-paths=true`.
- Endpoint nghiệp vụ: dùng để đánh giá thật sự “request đầu đã chạy được với latency phù hợp”.

**Một Pod Ready không đảm bảo mọi chức năng đã được warm.** Readiness có thể đúng về hợp đồng phục vụ nhưng request đầu vẫn chậm do lazy initialization. Nếu nghiệp vụ có yêu cầu latency rất chặt, cân nhắc một bước warm-up **có kiểm soát**, nhưng phải cân nhắc dependency, timeout, nguồn lực và liệu warm-up có cần chạy trước readiness hay không.

Ví dụ đoạn probe cấu hình trong một Pod/container:

~~~yaml
startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 5
  failureThreshold: 24

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  periodSeconds: 5
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 10
  failureThreshold: 3
~~~

Đây chỉ là **đoạn YAML của container**, không phải manifest Deployment đầy đủ. Ngưỡng là ví dụ, không phải thông số chuẩn. Khi startup probe chưa thành công, kubelet trì hoãn các kiểm tra liveness/readiness theo cơ chế Kubernetes. Sau khi startup đã qua, readiness mới quyết định Pod có nhận traffic; không gắn dịch vụ bên ngoài vào liveness chỉ để kéo dài thời gian startup.

## 12. Tại sao lazy initialization có thể khiến báo cáo đẹp hơn nhưng SLA xấu hơn?

Xét hai cấu hình:

~~~properties
# A: eager initialization theo cơ chế thông thường
spring.main.lazy-initialization=false
~~~

~~~properties
# B: lazy initialization toàn cục
spring.main.lazy-initialization=true
~~~

Phép đo giả định:

| Phương án | Ready time | Request đầu | Request sau warm |
|---|---:|---:|---:|
| A: Eager | 4,0 giây | 90 ms | 65 ms |
| B: Lazy | 2,2 giây | 1.900 ms | 65 ms |

**Đây là bảng giả lập để minh họa trade-off, không phải benchmark thực tế.** Nếu công việc thuộc first request là quan trọng, phương án B có thể “thắng” ở biểu đồ startup nhưng làm người dùng đầu tiên nhận phản hồi kém.

Các tiêu chí đánh giá nên gồm:

1. Time-to-first-ready và thời gian Pod vào EndpointSlice.
2. First business request latency p50/p95/p99.
3. Warm steady-state throughput và latency.
4. Bộ nhớ heap/RSS trước và sau first-use.
5. CPU spike, GC/classloading/JIT impact.
6. Lỗi phát hiện muộn vì bean không được tạo trong startup.
7. Số request có thể chịu được ngay sau Ready.
8. Khả năng auto-scaling trong đợt tăng traffic đầu tiên.

**Không nên đánh đổi fail-fast validation chỉ để có số startup đẹp.** Bean quan trọng như credential provider, bắt buộc cấu hình dữ liệu hoặc hệ thống authorization có thể cần được validate trước khi instance nhận traffic.

## 13. Phân tích “warm-up” theo lớp, không coi mọi cache là giống nhau

| Lớp được làm nóng | Ví dụ | Có sống qua JVM restart? |
|---|---|---|
| Class loading và Java heap objects | Bean singleton, cache nội bộ | **Không**, nếu là JVM mới |
| JIT compilation và profile data trong JVM | Hot methods sau nhiều lần gọi | **Không theo mặc định giữa hai JVM riêng** |
| Spring DevTools base classloader | Dependency classes đã load | Có thể giữ lại **trong cùng JVM** khi DevTools restart |
| OS page cache | JAR/classes đọc từ filesystem | Có thể sống qua process restart |
| Container image layer/cache | Image đã có trên node | Có thể sống qua container restart/Pod mới cùng node |
| DNS caches | JVM/OS/service resolver | Phụ thuộc layer và TTL |
| Database connection pool nội bộ | HikariCP connections | Pool của JVM cũ mất khi process kết thúc |
| Database buffer cache bên ngoài | DB server đã đọc page dữ liệu | Có thể sống qua restart của ứng dụng |
| CDN/distributed cache | Dữ liệu cache ngoài JVM | Có thể tiếp tục tồn tại, tùy TTL/policy |

Nhờ bảng này ta giải thích được vì sao **JVM mới chạy lần hai nhanh hơn**, dù không có “JVM warm restart” nào thực sự xảy ra: phần OS hoặc dịch vụ bên ngoài có thể đã được làm nóng.

Ngược lại, DevTools restart không có nghĩa mọi bean singleton của ứng dụng được giữ; nhiều bean thuộc ApplicationContext cũ đã bị destroy và sẽ được tạo lại trong context mới.

## 14. Cách tổ chức benchmark đáng tin cậy

Một benchmark startup không cần cực kỳ phức tạp, nhưng phải đủ kiểm soát:

**Giữ các biến cố định**

- Cùng JDK vendor/version, JVM flags (heap, GC, CDS, JIT), Java architecture.
- Cùng Spring Boot version, dependency graph, profile và `application.properties`.
- Cùng JAR checksum, host/container resources và số CPU quota thực.
- Cùng trạng thái network/dependency, database schema, connection pool config.
- Cùng cách khởi chạy: `java -jar`, không trộn số từ IDE, Gradle wrapper, native image.
- Cùng trạng thái instrumentation: không bật JFR cho một phương án rồi tắt ở phương án kia.

**Lặp và phân tích**

- Mỗi cold-start cần **JVM mới**; mỗi first-use sample cần first request thật sự của một process mới hoặc reset trạng thái đúng.
- Có warm-up để đo steady state, nhưng không warm trước kịch bản bạn muốn gọi “cold”.
- Lấy nhiều mẫu, báo p50/p95, min/max, standard deviation nếu có ý nghĩa. Không dựa vào một run đẹp nhất.
- Loại những lần lỗi hoặc timeout phải có quy tắc báo cáo; đừng tự xóa số xấu để cải thiện đồ thị.
- Ghi raw timestamps và method đo, để người khác tái lập.
- Nếu thay đổi mã, chỉ so sánh khi chạy cùng điều kiện và thứ tự thử nghiệm được cân bằng để giảm bias OS caches.

### Ví dụ bảng kết quả cần điền bằng số đo thật

| Run | Loại run | JVM ready (ms) | Spring Started (ms) | Spring Ready (ms) | First HTTP (ms) | Warm HTTP p50 (ms) |
|---|---|---:|---:|---:|---:|---:|
| 1 | Fresh JVM | ... | ... | ... | ... | ... |
| 2 | Fresh JVM | ... | ... | ... | ... | ... |
| 3 | DevTools restart | N/A theo cùng định nghĩa | ... | ... | ... | ... |

Dấu `...` là **ô mẫu chưa có dữ liệu**, không phải một benchmark thực tế. Khi đo DevTools restart trong cùng JVM, cột “JVM ready” theo định nghĩa *launcher tạo JVM mới* không có cùng ý nghĩa; không điền một số để so sánh giả.

### Biểu đồ và quyết định

Đừng tối ưu mỗi một metric. Ví dụ nếu startup giảm 20% nhưng first-use tăng gấp 5 và readiness vẫn cho traffic vào ngay, bạn cần cân nhắc yêu cầu latency của khách hàng. Nếu deployment rollout nhanh hơn nhưng vẫn có burst lỗi ở giây đầu, hãy đo cả **time-to-capacity**: mất bao lâu để Pod phục vụ lượng request mục tiêu với error rate phù hợp.

## 15. Định vị nguyên nhân khi cold start chậm

Sau khi đo timeline, tìm pha chiếm thời gian và đặt giả thuyết:

| Dấu hiệu | Khả năng nguyên nhân | Cách xác minh |
|---|---|---|
| JVM launch → SpringStarted dài | Classpath scanning, bean creation, config binding, web server startup | BufferingApplicationStartup, JFR, heap/CPU |
| Started → Ready dài | ApplicationRunner, CommandLineRunner, ready listeners | Event durations và log từng runner |
| Ready event nhanh nhưng readiness probe muộn | Probe period, platform scheduling, server reachability, readiness group | Timestamp của Pod/probe/HTTP và kubelet |
| Ready nhanh nhưng request đầu chậm | Lazy bean, servlet init, serialization, DNS/TLS, DB pool/cache | Trace request đầu, compare với warm request |
| DevTools restart chậm dần sau mỗi lần | Classloader leak, unmanaged threads, cache accumulation | Classloader stats, heap dump, thread count |
| JVM restart nhanh lần hai | OS page cache hoặc external dependency warm | Reset môi trường lab, kiểm tra I/O và các caches |
| Container “start” kéo dài trước khi Java có log | Image pull, scheduling, volume mount, initContainers | Kubernetes Pod events và node/container metrics |
| First request đầu bị timeout nhưng request sau ổn | Init work bị đẩy sang request, slow dependency hoặc resource contention | Trace CPU/GC/DB, timeout, startup warming |

Nên thay đổi **một giả thuyết mỗi lần** và kiểm tra kết quả trước/sau. Việc tắt tùy tiện toàn bộ auto-configuration, lazy hóa tất cả beans hoặc tăng CPU mà chưa đo nguyên nhân thường khiến application dễ lỗi hơn, không chắc tối ưu được trải nghiệm thực.

## 16. Thời gian khởi động Spring Boot khác với khởi động Pod

Trong Kubernetes, một Pod có thể mất thời gian ở nhiều tầng:

~~~text
Deployment tạo Pod spec
  |
  +-- scheduling chờ node/resources
  +-- download image nếu node chưa có
  +-- tạo sandbox/network/mount/initContainers
  +-- container JVM bắt đầu
  +-- SpringApplication startup
  +-- readiness probe thành công
  +-- EndpointSlice / routing cập nhật
  +-- request nghiệp vụ đến
  +-- lần sử dụng đầu tiên có thể cần warm-up
~~~

Nếu SLA yêu cầu “từ lúc yêu cầu scale-out đến lúc có thêm capacity”, chỉ đo `ApplicationReadyEvent.getTimeTaken()` là chưa đủ. Nó bỏ qua scheduling/image/network và cả thời gian router tiếp nhận Pod mới.

Dữ liệu cần kết hợp:

- Kubernetes Pod scheduling/conditions/events và image pull.
- Container start timestamp.
- Spring `ApplicationStartedEvent`/`ApplicationReadyEvent`.
- Readiness probe status và thời điểm Service/gateway có thể route.
- Kết quả first useful request (thành công, latency, error rate).
- Load test khi nhiều Pod cùng cold start làm tăng tải database/secret manager.

Đặc biệt, một Pod Ready sau 2 giây nhưng không chịu được burst traffic tới sau 20 giây chưa chắc thực sự đạt **time-to-capacity 2 giây**.

## 17. Sai lầm thường gặp

**Lỗi 1 — “Mọi lần chạy JAR từ đầu đều là cold machine start”.** Không. JVM mới có thể dùng OS page cache đã ấm.

**Lỗi 2 — “DevTools restart bằng việc tạo JVM mới”.** Không. DevTools dùng classloader/context restart trong cùng JVM.

**Lỗi 3 — “ApplicationStartedEvent nghĩa là runners đã chạy xong”.** Sai. Started được phát **trước** ApplicationRunner/CommandLineRunner.

**Lỗi 4 — “ApplicationReadyEvent có nghĩa request đầu tiên đã hoàn tất”.** Sai. Ready là mốc startup, first-use có thể chưa xảy ra.

**Lỗi 5 — “Bật spring.main.lazy-initialization=true luôn làm performance tốt hơn”.** Không. Nó có thể chuyển thời gian bean init sang request đầu và trì hoãn lỗi cấu hình.

**Lỗi 6 — “Chỉ cần expose /actuator/startup là có timeline”.** Không. Cần `BufferingApplicationStartup` phù hợp trước `run(args)`.

**Lỗi 7 — “POST /actuator/startup giống GET”.** Không. POST drain buffer; GET là snapshot.

**Lỗi 8 — “Cộng duration của mọi StartupStep là startup time”.** Sai. Các bước nested/overlap, phải phân tích quan hệ thay vì cộng mù quáng.

**Lỗi 9 — “Chạy JFR sau Ready sẽ cho toàn bộ CPU/GC của startup”.** Không. Những sự kiện trước lúc bắt đầu recording đã không được thu thập.

**Lỗi 10 — “Lần gọi health thành công đồng nghĩa mọi bean và database đã warm”.** Không. Readiness health group không phải bài thử mọi đường nghiệp vụ.

**Lỗi 11 — “Lần đầu curl nhanh hơn ở máy mình nên mọi client đều nhanh”.** Không. Khác nhau ở DNS, TLS, network, CPU quota, caches và chính workload.

**Lỗi 12 — “Thời gian Spring startup cũng bằng thời gian image pull + scheduler”.** Không. Các tầng có clock và scope riêng.

**Lỗi 13 — “Một mẫu đo là đủ để quyết định thay đổi production”.** Không. Có nhiễu từ GC/JIT/OS/page cache/network và scheduling.

**Lỗi 14 — “Warm-up bằng request thật là luôn vô hại”.** Không. Nếu route có side effect, warm-up có thể ghi dữ liệu, gửi message hoặc thu phí. Chỉ warm bằng thao tác an toàn/idempotent, có giới hạn.

**Lỗi 15 — “First-use luôn xảy ra đúng một lần trong cluster”.** Không. Mỗi JVM/instance có thể cold path riêng; khi scale-out, nhiều Pod có thể warm song song.

## 18. Bài tập thực hành

1. Chạy project mục 7, ghi `EVENT_STARTED` và `EVENT_READY` cùng các Duration.
2. Kiểm tra `GET /actuator/startup` có timeline; xác định ít nhất ba `StartupStep` có tên/tags và quan hệ parent-child.
3. Gọi `/readyz` thành công rồi mới gọi `/demo/use`. Quan sát `CATALOG_INITIALIZED` xuất hiện khi request đầu tiên thực hiện.
4. Gọi `/demo/use` 10 lần, so `handlerMillis` của lần đầu và những lần sau. Giải thích vì sao hai lần không chắc chênh đúng 300ms.
5. Khởi chạy **JVM mới** với cùng JAR, lặp lại. Lần gọi đầu của **process mới** có trigger lazy bean again không?
6. Chạy script đo bên ngoài, so `external_ready_ms` với `ApplicationReadyEvent.getTimeTaken()`. Nêu các phần thời gian mỗi số bao gồm/không bao gồm.
7. Bật `spring.main.lazy-initialization=true` và đo lại. Phần nào nhanh hơn, phần nào có thể chậm hơn?
8. Thay `@Lazy` trên `SlowCatalog` bằng eager init, giữ nguyên các điều kiện khác. Quan sát log `CATALOG_INITIALIZED` chuyển sang startup hay không.
9. Trong một project development riêng, cài DevTools, sửa classpath và đo thời gian restart; giải thích khác với JVM restart.
10. Ghi JFR từ trước khi Java main startup, xem class loading/GC/events, rồi so với timeline Spring.
11. Thử một monitor gọi `/demo/use` trước bạn và giải thích tại sao phép đo “first request” sau đó không còn hợp lệ.
12. Lập bảng 10–20 mẫu fresh JVM, báo median và p95, kèm JDK/CPU/JAR/version; không điền số đo giả.

## 19. Checklist trước khi tối ưu thời gian khởi động

- **Tên kịch bản:** fresh JVM, cold container/node, JVM restart, DevTools restart hay first-use?
- **Mốc đo:** launch, started event, ready event, readiness probe, first useful response?
- **Clock:** System.nanoTime trong JVM hay external monotonic clock, polling uncertainty bao nhiêu?
- **Tài nguyên:** CPU quota, heap, GC, I/O, network, DB warm state, host cache có cố định không?
- **Bản build:** cùng JAR, JDK, profiles, dependency versions và JVM flags?
- **Công cụ:** BufferingApplicationStartup/JFR/Actuator có được bật nhất quán?
- **Readiness:** phản ánh khả năng phục vụ thật, không chỉ một health endpoint quá nhẹ?
- **First-use:** có lazy beans, serializer, TLS, JIT, connection pool hay cache khởi tạo muộn?
- **Độ tin cậy:** nhiều lần chạy, p50/p95, raw samples, không cherry-pick?
- **Đánh đổi:** startup nhanh hơn có làm first request chậm/timeout hoặc lỗi cấu hình phát hiện muộn?
- **Vận hành:** khi auto-scaling/rolling deploy, time-to-capacity và tải dependency có cải thiện thật không?
- **Bảo mật:** không expose public startup details/JFR/Actuator nhạy cảm; giữ tệp profiling an toàn?

### Tài liệu chính thức

- Spring Boot 3.3 — SpringApplication, *Application Startup Tracking* và *Lazy Initialization*: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Application Startup REST endpoint (GET snapshot / POST drain): https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html
- Spring Boot 3.3 — Actuator endpoints/exposure/security: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Developer Tools, *Restart vs Reload*: https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html
- Spring Boot 3.3 — ApplicationReadyEvent Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Boot 3.3 — ApplicationStartedEvent Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html
- Spring Framework 6.1 — ApplicationStartup / StartupStep: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Kubernetes — Pod Lifecycle and probes: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Oracle JDK 17 — Java Flight Recorder: https://docs.oracle.com/en/java/javase/17/jfapi/

**Kết luận:** Đo startup hiệu quả phải tách **JVM/process cold start**, **kiểu restart thực sự**, và **first-use sau Ready**. Dùng `ApplicationStartedEvent`/`ApplicationReadyEvent` cho mốc Boot, `BufferingApplicationStartup`/Actuator và JFR để tìm pha chậm, đo readiness từ ngoài process và đo **request nghiệp vụ đầu** như một metric riêng. Chỉ xem tối ưu thành công khi nó cải thiện cả **time-to-ready, time-to-useful-response và khả năng phục vụ dưới tải**, chứ không chỉ làm log “Started in ... seconds” nhỏ hơn.
