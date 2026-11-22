# Mối liên hệ giữa runner và mốc sẵn sàng nhận công việc trong Spring Boot

## 1. Vấn đề: “ứng dụng đã chạy” chưa chắc “đã sẵn sàng nhận việc”

Khi một ứng dụng Spring Boot khởi động, có ít nhất ba mốc cần phân biệt:

1. **ApplicationContext đã refresh**: các thành phần nền tảng, bean thông thường và hạ tầng web có thể đã được dựng. Spring Boot công bố **ApplicationStartedEvent**.
2. **Công việc startup bắt buộc đã hoàn thành**: SpringApplication gọi các **ApplicationRunner** và **CommandLineRunner**. Các runner có thể warm up cache, xác minh dữ liệu, khởi tạo trạng thái cần thiết và từ chối startup nếu không đáp ứng điều kiện.
3. **Ứng dụng sẵn sàng phục vụ**: khi các runner hoàn tất bình thường, Spring Boot phát **ApplicationReadyEvent**, sau đó công bố **ReadinessState.ACCEPTING_TRAFFIC**.

Đây là lý do tài liệu Spring Boot mô tả runner là cơ chế dành cho công việc thực hiện sau khi context khởi động nhưng **trước khi ứng dụng bắt đầu nhận lưu lượng** theo hợp đồng readiness.

Tuy nhiên cần diễn đạt thật chính xác: **readiness là trạng thái/khả năng được công bố cho bên điều phối**, không phải một ổ khóa JVM tự động chặn mọi request, message, scheduler hoặc thread. Web server có thể đã bind cổng trước khi runner hoàn tất; những thành phần không phối hợp với readiness vẫn có thể xử lý việc sớm. Vì thế phải phân biệt **mốc Boot tuyên bố ready** với **cơ chế thực tế ngăn hoặc cho phép từng nguồn công việc**.

Mục tiêu bài học:

- Hiểu vị trí của runner trong chuỗi sự kiện và trạng thái **ApplicationAvailability**.
- Dùng runner làm **startup barrier** cho những điều kiện bắt buộc trước khi ready.
- Phân biệt **liveness**, **readiness**, **HTTP probe** và **khả năng thực sự xử lý công việc**.
- Nhận diện các trường hợp **async**, **listener container**, **scheduler** hoặc lời gọi trực tiếp phá vỡ kỳ vọng “chưa ready thì chưa nhận việc”.
- Thiết kế xử lý lỗi, timeout, thứ tự runner, readiness probe và kiểm thử đúng.
- Thực hành Java 17+ với Spring Boot 3.x, web endpoint, actuator và nhánh startup failure.

## 2. Vòng đời chính xác: runner nằm giữa Started và Ready

Trong một lần **SpringApplication.run(args)** thành công, chuỗi mốc chính là:

| Thứ tự | Mốc trong Spring Boot | Điều đã/đang xảy ra |
| --- | --- | --- |
| 1 | Chuẩn bị Environment và ApplicationContext | Đọc cấu hình, chuẩn bị các nguồn ứng dụng |
| 2 | Refresh ApplicationContext | Tạo bean không lazy, khởi tạo hạ tầng và web server phù hợp |
| 3 | **ApplicationStartedEvent** | Context đã refresh thành công; runner chưa được SpringApplication gọi |
| 4 | **AvailabilityChangeEvent(LivenessState.CORRECT)** | Spring Boot công bố ứng dụng có trạng thái live |
| 5 | **ApplicationRunner/CommandLineRunner** | Các công việc startup được thực thi theo thứ tự áp dụng |
| 6 | **ApplicationReadyEvent** | Toàn bộ runner đã trả về bình thường; nhánh startup thành công tiến tới ready |
| 7 | **AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)** | Spring Boot công bố instance sẵn sàng nhận lưu lượng |
| 8 | SpringApplication.run(...) trả về | Caller nhận context; ứng dụng web thông thường tiếp tục chạy |

Sơ đồ gọn:

~~~text
SPRINGAPPLICATION.RUN
         |
    Create/Refresh
    ApplicationContext
         |
   ApplicationStartedEvent
         |
    LivenessState.CORRECT
         |
         v
   +------------------------+
   | ApplicationRunner      |
   | CommandLineRunner      |  <- Startup barrier
   | (may throw exception)  |
   +------------------------+
         |
         | All runners returned successfully
         v
   ApplicationReadyEvent
         |
   ReadinessState.ACCEPTING_TRAFFIC
         |
   SpringApplication.run returns
~~~

**Từ khóa là “trả về thành công”.** Spring Boot không kiểm tra xem một Future đã xong hoặc một background thread đã warm up xong nếu runner chỉ kích hoạt task bất đồng bộ rồi trả về ngay. Runner là một **barrier đồng bộ theo method run(...)**; nó chỉ bảo vệ những việc mà method thực sự đợi/kiểm tra.

**Started khác Ready:** nhìn thấy ApplicationStartedEvent, log “Started ...”, cổng TCP mở hay health check liveness thành công **không có nghĩa các startup runner đã chạy xong**.

## 3. Liveness và readiness phản ánh hai câu hỏi khác nhau

**LivenessState** trả lời đại ý: tiến trình còn ở trạng thái nội bộ đủ lành mạnh để tiếp tục hoạt động hoặc tự phục hồi? Spring Boot thường công bố **LivenessState.CORRECT** sau context refresh.

**ReadinessState** trả lời: instance đã có thể nhận lưu lượng/công việc theo hợp đồng readiness chưa? Trong quá trình runner thực thi, trạng thái mặc định còn là **ReadinessState.REFUSING_TRAFFIC**. Khi startup thành công qua các runner, Boot công bố **ReadinessState.ACCEPTING_TRAFFIC**.

| Giai đoạn | Liveness | Readiness | Ý nghĩa vận hành |
| --- | --- | --- | --- |
| Bootstrap sớm | Chưa live/BROKEN theo vòng đời ứng dụng | REFUSING_TRAFFIC | Chưa hoàn thành context; probe HTTP có thể chưa truy cập được |
| Refresh xong, runner đang chạy | CORRECT | REFUSING_TRAFFIC | JVM/context hoạt động; chưa xong điều kiện startup |
| Sau runner và Ready | CORRECT | ACCEPTING_TRAFFIC | Instance công bố có thể phục vụ lưu lượng |
| Ứng dụng chủ động giảm khả năng phục vụ | Có thể vẫn CORRECT | Có thể REFUSING_TRAFFIC | Không nhận thêm traffic nhưng không cần restart ngay |
| Đang graceful shutdown | Thường vẫn CORRECT trong giai đoạn đầu | REFUSING_TRAFFIC | Ngừng nhận traffic mới, xử lý tác vụ đang chạy theo chính sách |

Không nên đưa mọi dependency ngoài hệ thống vào **liveness**. Ví dụ nếu database chung gặp sự cố, đánh dấu toàn bộ Pod là BROKEN có thể gây vòng restart hàng loạt và làm sự cố nặng hơn. Tùy tính chất nghiệp vụ, cân nhắc readiness, circuit breaker hoặc chính sách degrade phù hợp.

**Readiness cũng không phải cam kết mọi nghiệp vụ luôn thành công:** sau khi ready, một request vẫn có thể lỗi do dữ liệu đầu vào, hết quota, timeout hoặc một dependency tạm thời không có sẵn. Readiness là tín hiệu điều phối khả năng phục vụ, không phải lời hứa về từng giao dịch.

## 4. Runner là startup barrier, không phải “nút bật server”

Khi web server được tạo trong quá trình refresh, cổng HTTP có thể được bind **trước khi runner chạy xong**. Vì vậy:

- Kết nối trực tiếp tới instance có thể tới được web server từ sớm; việc ứng dụng có phục vụ hay từ chối request phụ thuộc web stack, trạng thái readiness và code xử lý.
- Bên điều phối như Kubernetes nên đọc **readiness probe** để chỉ đưa một instance vào tập nhận traffic khi nó đã sẵn sàng.
- Một client bypass load balancer, gọi thẳng Pod IP hoặc dùng một endpoint không tuân thủ readiness có thể vẫn tạo việc trước mốc ready.
- Một consumer của Kafka/RabbitMQ hoặc scheduler có thể bắt đầu công việc từ **lifecycle riêng**; HTTP readiness probe không tự dừng chúng.

Vì vậy, cấu hình runner chỉ là một phần trong thiết kế. **Phải đảm bảo từng nguồn công việc tôn trọng ranh giới startup cần thiết.**

Ví dụ: service cần preload bảng quy tắc định giá. Runner nạp cache và kiểm tra thành công. Nếu ném exception, instance không đạt ready theo đường thành công. HTTP ingress theo readiness sẽ không định tuyến tới instance đó. Nhưng nếu một message listener container tự start trong context refresh, nó có thể nhận message **trước khi runner nạp xong cache**. Đối với consumer, phải dùng cơ chế start/stop hoặc gating riêng.

## 5. Khi nào chọn ApplicationRunner hoặc CommandLineRunner?

Spring Boot có hai interface:

~~~java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

~~~java
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

Đây là **chữ ký rút gọn để học**, không phải file source tự chạy vì đã bỏ package và phần khai báo phụ. Cả hai chạy ở **cùng giai đoạn sau ApplicationStartedEvent và trước ApplicationReadyEvent**; khác nhau chính ở đối số:

- **ApplicationRunner** nhận **ApplicationArguments** để kiểm tra **containsOption()**, **getOptionValues()** và **getNonOptionArgs()**.
- **CommandLineRunner** nhận String[] arguments thô.
- Cả hai được đăng ký như Spring bean qua @Component hoặc @Bean.
- Nếu có nhiều runner, dùng **@Order/Ordered** để chỉ ra thứ tự trong **cùng ApplicationContext**.

**Nên dùng runner cho:**

1. Warm up cache **phải hoàn thành trước khi service nhận traffic**.
2. Kiểm tra một cấu hình hoặc dữ liệu ứng dụng bắt buộc dựa trên nhiều bean đã khởi tạo.
3. Xác nhận sự sẵn sàng của hệ thống phụ thuộc quan trọng, với timeout và chính sách fail-fast.
4. Khởi tạo dữ liệu nhẹ, idempotent và được điều phối phù hợp trước khi ready.
5. Công việc CLI/batch được gọi trong startup, có ý nghĩa hoàn tất trước khi run trả về.

**Không nên dùng runner để:**

- Chạy tác vụ định kỳ suốt vòng đời ứng dụng; sử dụng scheduler/job framework.
- Giữ một vòng lặp vô hạn nhận message, khiến run(...) không bao giờ trả về và instance mãi chưa ready.
- Tự quản lý thread hoặc socket dài hạn mà không có stop/shutdown; chọn lifecycle bean hoặc consumer container phù hợp.
- Thay thế schema migration được quản lý bằng Flyway/Liquibase.
- Chạy một nhiệm vụ **đúng một lần toàn cluster** chỉ bằng cách đặt trong runner: mỗi replica/restart có runner riêng, cần unique key, transaction, idempotency hoặc job orchestrator dùng chung.

## 6. Công việc runner phải chờ kết quả thật

Một lỗi phổ biến:

~~~java
@Component
class WrongRunner implements ApplicationRunner {
    private final WarmupService service;

    WrongRunner(WarmupService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        service.startWarmupAsync();
        // Method returns immediately: startup may progress to Ready.
    }
}
~~~

Đây là **đoạn minh họa**, cần định nghĩa WarmupService và các import khi dùng thực tế. Runner đã **gọi** method, nhưng không biết warm up đã xong hay thất bại. SpringApplication chỉ thấy **run(...) trả về bình thường**; vì vậy nó có thể phát ApplicationReadyEvent và ACCEPTING_TRAFFIC trong khi dữ liệu vẫn chưa chuẩn bị xong.

Với tác vụ async thực sự cần hoàn tất trước readiness, phải chờ có giới hạn và làm lỗi lan lên startup:

~~~java
@Override
public void run(ApplicationArguments args) throws Exception {
    CompletableFuture<Void> completion = service.startWarmupAsync();
    completion.get(10, TimeUnit.SECONDS);
}
~~~

Đây là **đoạn minh họa trong runner**, không phải chương trình độc lập. Service giả định trả CompletableFuture<Void>; cần import **java.util.concurrent.CompletableFuture** và **TimeUnit**. **get(...)** có timeout và ném exception khi không hoàn thành. Cần thiết kế hủy task, cleanup, retry hữu hạn và xử lý exception gốc phù hợp. Nếu dùng **@Async**, bảo đảm executor được cấu hình và lời gọi đi qua Spring proxy; tự gọi method trong cùng bean có thể làm mất hiệu lực @Async.

**Không dùng Thread.sleep vô hạn** để “đợi sẵn sàng”: chờ bằng trạng thái hoàn thành xác thực, timeout và logging có ý nghĩa. Sleep ngắn trong ví dụ thực hành phía dưới chỉ để tạo khoảng thời gian quan sát.

## 7. Ví dụ Spring Boot 3.x/Java 17+: runner quyết định readiness

Ví dụ sau cho thấy:

- ApplicationStartedEvent đã xảy ra nhưng runner chưa hoàn thành.
- Runner quan sát được trạng thái **REFUSING_TRAFFIC** trong lúc warm up.
- Một endpoint nhận công việc kiểm tra **ApplicationAvailability** và điều kiện cache, từ chối với **HTTP 503** nếu chưa đủ điều kiện.
- Khi mọi runner hoàn tất, ứng dụng phát ApplicationReadyEvent rồi **ReadinessState.ACCEPTING_TRAFFIC**.
- Actuator cung cấp readiness health probe để bên điều phối có tín hiệu.
- Nếu runner ném exception, ứng dụng không đi qua nhánh ready thành công.

### 7.1. Cấu trúc dự án

~~~text
runner-readiness-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          ReadinessRunnerDemo.java
      resources/
        application.properties
~~~

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'runner-readiness-demo'
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
}
~~~

Cần **JDK 17+**, Gradle tương thích và dependencies có thể tải từ repository hoặc đã có trong cache. Bản 3.3.13 được cố định để ví dụ tái lập theo Spring Boot 3.3.x; với phiên bản khác cần đối chiếu API tương ứng.

Tệp **src/main/resources/application.properties**:

~~~properties
spring.application.name=runner-readiness-demo
server.port=8080

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info
~~~

**management.endpoint.health.probes.enabled=true** bật các health probe group **liveness/readiness** cho cả môi trường thử nghiệm local. Trên Kubernetes, Spring Boot có thể tự phát hiện và bật probe khi cấu hình tương ứng; ở đây ghi rõ để dễ thử trên máy.

### 7.2. Source Java hoàn chỉnh

Tạo **src/main/java/demo/ReadinessRunnerDemo.java**:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReadinessRunnerDemo {
    public static void main(String[] args) {
        SpringApplication.run(ReadinessRunnerDemo.class, args);
        System.out.println("MAIN_AFTER_RUN");
    }
}

@Component
class StartupCache {
    private final AtomicBoolean warmed = new AtomicBoolean(false);

    void markWarmed() {
        warmed.set(true);
    }

    boolean isWarmed() {
        return warmed.get();
    }
}

@Component
class StartupEvents {

    @EventListener(ApplicationStartedEvent.class)
    public void started() {
        System.out.println("EVENT_STARTED");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void ready() {
        System.out.println("EVENT_READY");
    }

    @EventListener
    public void readinessChanged(
            AvailabilityChangeEvent<ReadinessState> event) {
        if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
            System.out.println("READINESS_ACCEPTING");
        }
    }
}

@Component
@Order(10)
class WarmupRunner implements ApplicationRunner {
    private final ApplicationAvailability availability;
    private final StartupCache cache;

    WarmupRunner(ApplicationAvailability availability, StartupCache cache) {
        this.availability = availability;
        this.cache = cache;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("RUNNER_WARMUP_START");
        System.out.println(
                "RUNNER_READINESS_" + availability.getReadinessState());

        if (args.containsOption("fail-warmup")) {
            throw new IllegalStateException("Demo warmup failed");
        }

        try {
            Thread.sleep(2500); // Chi de de quan sat startup barrier.
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Warmup interrupted", exception);
        }

        cache.markWarmed();
        System.out.println("RUNNER_WARMUP_DONE");
    }
}

@Component
@Order(20)
class VerifyRunner implements CommandLineRunner {
    private final StartupCache cache;

    VerifyRunner(StartupCache cache) {
        this.cache = cache;
    }

    @Override
    public void run(String... args) {
        if (!cache.isWarmed()) {
            throw new IllegalStateException("Cache has not been warmed");
        }
        System.out.println("RUNNER_VERIFIED");
    }
}

@RestController
class WorkEndpoint {
    private final ApplicationAvailability availability;
    private final StartupCache cache;

    WorkEndpoint(ApplicationAvailability availability, StartupCache cache) {
        this.availability = availability;
        this.cache = cache;
    }

    @PostMapping("/work")
    ResponseEntity<String> acceptWork() {
        if (availability.getReadinessState()
                != ReadinessState.ACCEPTING_TRAFFIC
                || !cache.isWarmed()) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("NOT_READY");
        }
        return ResponseEntity.ok("WORK_ACCEPTED");
    }
}
~~~

**Giải thích chi tiết:**

1. **StartupCache** sử dụng AtomicBoolean nhằm minh họa một điều kiện đã khởi tạo. Nó không thay thế cơ chế lưu dữ liệu nghiệp vụ hoặc distributed readiness cho nhiều replica.
2. **WarmupRunner** được gọi sau ApplicationStartedEvent; nó in trạng thái readiness hiện tại, rồi giả lập warm up bằng Thread.sleep(2500). Trong sản phẩm thật phải thay bằng thao tác chuẩn bị cụ thể, có timeout, xử lý lỗi và khả năng thử lại an toàn.
3. **VerifyRunner** dùng @Order(20) chạy sau WarmupRunner @Order(10); nếu cache chưa được đánh dấu hợp lệ, ném exception để từ chối startup.
4. **StartupEvents** lắng nghe Started/Ready và chỉ in thông báo **READINESS_ACCEPTING** khi thấy AvailabilityChangeEvent mang ReadinessState.ACCEPTING_TRAFFIC.
5. **WorkEndpoint** kiểm tra cả readiness state và điều kiện cache; **POST /work** nhận công việc khi đã ready, trả **503** nếu chưa ready. Demo dùng một endpoint đơn giản để minh họa; code sản phẩm cần xác thực, authorization, input validation, idempotency và quản lý công việc riêng.
6. **ApplicationAvailability** là API nội bộ Spring Boot để truy cập trạng thái hiện hành; nó không phải một cơ chế khóa phân tán hoặc hàng đợi bền vững.

### 7.3. Chạy dự án

Nếu project đã có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu không có wrapper nhưng đã cài một Gradle tương thích, có thể dùng **gradle bootRun**.

Trong lần chạy bình thường, **thứ tự các dòng do chính mã ví dụ in ra** là:

~~~text
EVENT_STARTED
RUNNER_WARMUP_START
RUNNER_READINESS_REFUSING_TRAFFIC
RUNNER_WARMUP_DONE
RUNNER_VERIFIED
EVENT_READY
READINESS_ACCEPTING
MAIN_AFTER_RUN
~~~

Log từ Spring Boot, Tomcat, Actuator và Gradle có thể xen giữa; đây **không phải toàn bộ stdout**. Thời gian thực tế phụ thuộc khởi tạo context và scheduler, nhưng trật tự các mốc là hợp đồng startup của ví dụ.

**Chú ý:** READINESS_ACCEPTING được in từ một listener đồng bộ nhận **AvailabilityChangeEvent**; nó xuất hiện sau EVENT_READY vì Boot công bố readiness sau ApplicationReadyEvent. Nếu bạn thay cấu hình listener bằng bất đồng bộ hoặc phát trạng thái availability tùy biến ở những nơi khác, không được dựa vào dòng log này để suy ra thời điểm hoàn thành một task async.

### 7.4. Kiểm tra trạng thái bằng curl

Sau khi ứng dụng chạy thành công:

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
curl -i -X POST http://localhost:8080/work
~~~

Với health probe đã bật, readiness endpoint ở trạng thái chấp nhận traffic thường trả **HTTP 200**, body có **"status":"UP"**. Endpoint demo **POST /work** trả **HTTP 200** với nội dung **WORK_ACCEPTED**.

Trong khoảng thời gian warm up, nếu HTTP server đã có thể trả lời request, readiness probe có thể báo **HTTP 503/OUT_OF_SERVICE**, còn endpoint demo **POST /work** trả **503 NOT_READY** theo code. Nếu thử quá sớm khi web server chưa mở cổng thì có thể gặp **connection refused**: không thể ép HTTP probe có response trước khi server bắt đầu lắng nghe.

Với runner ngủ 2,5 giây, có thể thử gửi curl trong cửa sổ này từ terminal khác. Kết quả thời gian không tuyệt đối cố định giữa các máy; hãy dựa trên trạng thái được báo và log tương ứng, không phụ thuộc vào thao tác tay phải “bắt kịp” đúng một khoảnh khắc.

### 7.5. Thử nhánh startup thất bại

~~~bash
./gradlew bootRun --args="--fail-warmup"
~~~

Các dòng do mã ví dụ in ra trước khi lỗi được ném:

~~~text
EVENT_STARTED
RUNNER_WARMUP_START
RUNNER_READINESS_REFUSING_TRAFFIC
~~~

Sau đó runner ném **IllegalStateException("Demo warmup failed")**. **RUNNER_WARMUP_DONE**, **RUNNER_VERIFIED**, **EVENT_READY**, **READINESS_ACCEPTING** và **MAIN_AFTER_RUN** không xuất hiện theo nhánh startup thành công. Spring Boot xử lý lỗi và đóng context khi phù hợp; Gradle có thể báo task thất bại và in stack trace.

Vì process startup fail, **không đòi hỏi readiness endpoint phải tiếp tục sống để trả 503 mãi**. Cổng HTTP có thể bị đóng khi context shutdown. Bên điều phối cần hiểu cả tín hiệu probe và việc process/container thoát.

## 8. Mối liên hệ với Actuator và Kubernetes readiness probe

Spring Boot Actuator có thể công bố các health group:

- **/actuator/health/liveness**: phản ánh trạng thái liveness của instance.
- **/actuator/health/readiness**: phản ánh trạng thái readiness của instance.

Với cấu hình probes hợp lệ, readiness group mặc định dựa vào **readinessState**. Lúc REFUSING_TRAFFIC, chỉ báo readiness có thể là **OUT_OF_SERVICE** và HTTP status thường là **503**; khi ACCEPTING_TRAFFIC, status thường **UP/200**. Actual HTTP response phụ thuộc trạng thái server đã mở, cấu hình health group, security và HTTP status mapping.

Trong Kubernetes, ví dụ một readinessProbe:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Đây là **đoạn YAML minh họa bên trong cấu hình container**, không phải toàn bộ Deployment runnable độc lập. Các tham số cần điều chỉnh theo ứng dụng, latency startup, port, Spring Security và hệ thống triển khai. Nếu application dùng management port khác, phải lựa chọn đường probe phù hợp; probe trên một cổng quản trị riêng **không tự chứng minh** cổng ứng dụng chính đang phục vụ request. Spring Boot còn hỗ trợ các đường probe bổ sung trên server port chính trong cấu hình phù hợp.

**Vai trò của readinessProbe** là để Kubernetes **không chọn instance chưa ready làm endpoint nhận traffic**. Điều này hữu ích với HTTP ingress/Service traffic được Kubernetes điều phối. Nó **không ngăn** một client truy cập trực tiếp địa chỉ Pod, không chặn thread tự tạo và không dừng message listener chỉ vì readiness còn REFUSING_TRAFFIC.

### Startup probe và liveness probe không thay readiness probe

- **Startup probe** (nếu có) cho phép ứng dụng khởi động chậm hơn trước khi các phép kiểm tra liveness/readiness khác có hiệu lực theo lịch của kubelet.
- **Liveness probe** dùng để quyết định khởi động lại container khi ứng dụng không còn có thể tự phục hồi.
- **Readiness probe** quyết định có nên đưa instance vào luồng phục vụ traffic hay không.

Nếu runner phải tải một tài nguyên quan trọng mất vài chục giây, cân nhắc startup probe/budget và readinessProbe hợp lý; **đừng đánh dấu liveness BROKEN chỉ vì cache đang được preload**. Nếu runner không thể hoàn thành do dependency bắt buộc hỏng, hãy đặt timeout/fail-fast hợp lý để orchestrator thấy startup failure đúng bản chất.

## 9. Trường hợp HTTP readiness không kiểm soát được việc nhận message

Đây là một điểm dễ bị bỏ sót trong ứng dụng event-driven.

**SmartLifecycle** và nhiều listener container có thể tự start trong quá trình ApplicationContext refresh. Ví dụ một consumer có **autoStartup=true** có thể bắt đầu poll message trước khi Spring Boot gọi các ApplicationRunner. Một scheduler cũng có thể bắt đầu xử lý task theo lifecycle riêng khi context đã sẵn sàng phần scheduler. Thời gian cụ thể còn tùy framework và cấu hình.

Vì vậy:

~~~text
Context refresh
   |
   +-- Kafka/RabbitMQ listener container co the start
   +-- Scheduler co the duoc kich hoat
   |
ApplicationStartedEvent
   |
Runner preload cache
   |
ApplicationReadyEvent
   |
ReadinessState.ACCEPTING_TRAFFIC
~~~

**HTTP readiness probe không phải bộ điều khiển consumer group.** Nếu consumer có thể nhận message trước khi cache sẵn sàng, cần một chiến lược riêng:

1. **Không tự start consumer** trong refresh: cấu hình autoStartup=false trên container/listener phù hợp.
2. Khởi động consumer sau khi warm up đã hoàn thành, bằng lifecycle API chuyên biệt, từ một thành phần điều phối có kiểm soát.
3. Nếu bắt đầu theo ApplicationReadyEvent, nhớ rằng event này xảy ra **ngay trước** trạng thái ACCEPTING_TRAFFIC; nếu yêu cầu đồng bộ chính xác với trạng thái, lắng nghe **AvailabilityChangeEvent<ReadinessState>** hoặc dùng gate dựa vào ApplicationAvailability.
4. Nếu đã nhận message, nhưng chưa thể xử lý, áp dụng pause/resume, nack/requeue hoặc backpressure theo đúng semantics của broker. Không đơn giản bỏ qua message đã nhận.
5. Đặt timeout và shutdown path; bảo đảm không chặn thread startup bằng một vòng loop polling vô hạn.

Đoạn minh họa về readiness gate độc lập:

~~~java
@Component
class ReadinessGate {
    private final AtomicBoolean accepting = new AtomicBoolean(false);

    @EventListener
    public void onAvailability(AvailabilityChangeEvent<ReadinessState> event) {
        accepting.set(event.getState() == ReadinessState.ACCEPTING_TRAFFIC);
    }

    public boolean canProcess() {
        return accepting.get();
    }
}
~~~

Đây là **đoạn mã minh họa**, không tự chạy độc lập: cần import Component, AtomicBoolean, EventListener, AvailabilityChangeEvent và ReadinessState. Trong consumer thực, phải gắn gate vào **cơ chế lấy/ack/nack/pause message phù hợp**, không đơn giản check rồi tự drop. Nếu không cần sao chép trạng thái, consumer cũng có thể inject **ApplicationAvailability** để đọc readiness hiện tại.

**Điểm quan trọng về message processing:** “Ready để HTTP nhận request” và “ready để consume message” đôi khi là hai điều kiện khác nhau. Một ứng dụng có thể cố ý không mở HTTP ingress nhưng vẫn nhận message, hoặc ngược lại. Khi đó cần định nghĩa readiness theo **từng loại công việc** và kiểm soát các consumer tương ứng; không dùng một boolean chung nếu các workstream có điều kiện phục vụ khác nhau.

## 10. Lỗi sau runner hoặc async task còn chạy

### 10.1. Một runner kết thúc không có nghĩa toàn bộ hệ thống đã xử lý xong

Runner có thể gọi:

~~~java
backgroundExecutor.submit(() -> preloadBigCache());
return;
~~~

Đây là **pseudocode Java bên trong method**, vì backgroundExecutor và preloadBigCache chưa được khai báo. Khi method trả về, SpringApplication có thể tiếp tục sang runner sau và ApplicationReadyEvent. Nếu background task sau đó thất bại, lỗi không tự làm SpringApplication.run(...) thất bại, trừ khi bạn đợi và chuyển lỗi về đường startup.

Nên chọn một trong hai hợp đồng rõ ràng:

- **Bắt buộc trước ready:** chờ task hoàn tất có timeout, propagate lỗi, hoặc chạy đồng bộ trong runner.
- **Được phép hoàn tất sau ready:** tách thành background task có health/metric riêng; chỉ cho phép các chức năng tương ứng khi dependency của chúng đã sẵn sàng.

Không được dùng câu “đã submit task” để báo “đã hoàn thành task”.

### 10.2. Runner kết thúc thành công nhưng công việc bắt buộc bị nuốt lỗi

Ví dụ sai:

~~~java
try {
    validateCriticalDependency();
} catch (Exception error) {
    logger.warn("Startup check failed", error);
}
// run(...) returns successfully => Boot may proceed to ready
~~~

Đây là **pseudocode** vì validateCriticalDependency và logger phải do ứng dụng định nghĩa. Nếu dependency này là điều kiện bắt buộc, catch rồi chỉ log làm ứng dụng có thể tự công bố ready trong trạng thái thiếu khả năng phục vụ. Hãy ném lại exception có cause thích hợp hoặc chuyển sang chế độ degraded rõ ràng, có readiness phản ánh đúng loại công việc.

### 10.3. Một runner thất bại làm gì với mốc ready?

Nếu một runner ném exception trước khi trở về:

- **ApplicationReadyEvent** không được phát trên đường startup thành công.
- **ReadinessState.ACCEPTING_TRAFFIC** không được Spring Boot công bố theo đường thành công đó.
- **ApplicationFailedEvent** thường được phát trong failure handling của SpringApplication.
- ApplicationContext đã được tạo có thể được đóng; destroy callback của bean thuộc phạm vi container được gọi theo lifecycle phù hợp.
- Những tác dụng phụ bên ngoài transaction (gửi email, ghi file, HTTP API) **không tự hoàn tác** khi context đóng.

Vì hệ thống điều phối có thể restart instance sau lỗi, runner phải an toàn khi **được gọi lại**. Với việc ghi dữ liệu hoặc gửi message, cần idempotency key, transaction boundary và đối soát.

## 11. Thứ tự nhiều runner và tác động tới readiness

Spring Boot cho phép nhiều runner trong cùng ApplicationContext. Nếu công việc có dependency, dùng **@Order/Ordered** để diễn đạt thứ tự:

~~~java
@Component
@Order(10)
class LoadCacheRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Load cache.
    }
}

@Component
@Order(20)
class VerifyCacheRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        // Verify cache.
    }
}
~~~

Đây là **mã minh họa**, cần các import của Spring Boot/Spring và logic thực. Nếu hai runner cùng order, không nên dựa vào thứ tự classpath scanning hoặc tên class như một hợp đồng nghiệp vụ.

Theo đường thành công:

~~~text
ApplicationStartedEvent
      |
LoadCacheRunner  (order 10)
      |
VerifyCacheRunner (order 20)
      |
ApplicationReadyEvent
      |
ReadinessState.ACCEPTING_TRAFFIC
~~~

Nếu VerifyCacheRunner ném exception, không đến ready. Nếu LoadCacheRunner tự khởi chạy async rồi trả về, VerifyCacheRunner vẫn có thể chạy khi cache chưa xong. **@Order kiểm soát thứ tự các lời gọi run(...), không tạo một barrier cho mọi background task.**

Nếu nhiều bước phụ thuộc chặt chẽ, một runner điều phối service theo thứ tự tường minh còn dễ bảo trì hơn một chuỗi lớn các runner lệ thuộc order khó theo dõi.

## 12. Vì sao @PostConstruct và ApplicationStartedEvent không thay runner?

**@PostConstruct** là callback khởi tạo của **một bean**. Nó thường chạy khi context đang refresh, lúc những bean khác chưa chắc đã khởi tạo hoàn chỉnh. Tác vụ nặng trong @PostConstruct có thể làm chậm quá trình tạo bean hoặc gây vòng phụ thuộc. Nó phù hợp để xác thực cấu hình cục bộ và chuẩn bị state nhỏ của chính bean.

**ApplicationStartedEvent** xảy ra sau refresh nhưng trước runner, phù hợp với logging/metric hoặc xử lý nhẹ cần biết context đã refresh. Listener mặc định chạy **đồng bộ trong publisher thread**, nên một listener Started dài có thể trì hoãn runner và readiness. Đừng dùng nó làm nơi thực thi toàn bộ warm up nếu mục tiêu là một bước startup bắt buộc được điều phối rõ.

**ApplicationReadyEvent** xảy ra sau runner nhưng trước trạng thái ACCEPTING_TRAFFIC. Listener Ready chạy đồng bộ dài có thể làm chậm việc chuyển readiness. Nếu listener Ready được đánh dấu @Async, Boot có thể công bố ACCEPTING_TRAFFIC **trước khi listener async thực sự hoàn thành**, làm sai kỳ vọng của người đọc nếu công việc đó là điều kiện bắt buộc.

| Hook | Mốc chính | Dùng tốt cho | Rủi ro khi dùng sai |
| --- | --- | --- | --- |
| @PostConstruct/initMethod | Khi bean khởi tạo | Invariant cục bộ | Phụ thuộc bean khác chưa hoàn chỉnh, khởi tạo lâu |
| ApplicationStartedEvent | Sau refresh, trước runner | Log, trace, metric nhẹ | Listener dài chặn startup; async listener không làm barrier |
| ApplicationRunner/CommandLineRunner | Sau Started, trước Ready | Startup task bắt buộc | Chạy lâu, lỗi không propagate, async trả về sớm |
| ApplicationReadyEvent | Sau runner, trước công bố readiness | Tín hiệu hoàn tất startup, telemetry | Công việc nặng trì hoãn/đi sau readiness |
| SmartLifecycle | Lifecycle start/stop của bean | Consumer, background service dài hạn | Có thể bắt đầu nhận việc trước runner hoàn tất |
| @Scheduled | Theo lịch sau khi scheduler hoạt động | Công việc định kỳ | Không được giả định scheduler chờ runner |

## 13. Tự quản lý readiness sau khi startup thành công

Readiness không nhất thiết chỉ thay đổi một lần. Sau khi ứng dụng đã sẵn sàng, nếu một thành phần quan trọng không thể tiếp tục nhận việc hoặc bị quá tải, ứng dụng có thể chủ động công bố **ReadinessState.REFUSING_TRAFFIC**.

Spring Boot hỗ trợ **AvailabilityChangeEvent.publish(...)**:

~~~java
AvailabilityChangeEvent.publish(
        applicationEventPublisher,
        this,
        ReadinessState.REFUSING_TRAFFIC);
~~~

Đây là **đoạn minh họa bên trong một Spring bean** đã inject ApplicationEventPublisher. Khi đã phục hồi và ứng dụng thực sự sẵn sàng, có thể công bố **ACCEPTING_TRAFFIC** theo chính sách. Cần bảo đảm state machine minh bạch và không chuyển ready chỉ vì một phép thử đơn lẻ quá lạc quan.

**Phải cân nhắc các điểm sau:**

- Refusing traffic là tín hiệu cho hệ thống điều phối; **không tự hủy những request đang chạy** và không tự pause Kafka/RabbitMQ listener.
- Nếu chỉ một chức năng không dùng được, có thể không nên từ chối toàn bộ traffic. Cần xác định hợp đồng chức năng/degraded mode.
- Với lỗi dependency ngoài hệ thống dùng chung, mọi Pod đều có thể trở thành unready. Điều này tránh phục vụ sai nhưng cũng có thể gây ngắt dịch vụ toàn bộ; cần chính sách dự phòng và phục hồi.
- Trong shutdown, Spring Boot có thể chuyển readiness về REFUSING_TRAFFIC để ngừng nhận lưu lượng mới; graceful shutdown vẫn cần cấu hình riêng khi phù hợp.
- Không dùng liveness để tái khởi động hàng loạt container chỉ vì dependency ngoài tạm mất.

## 14. Readiness probe không nhất thiết bao gồm mọi dependency

Khi Actuator readiness probe được bật, trạng thái mặc định phản ánh khả năng phục vụ theo **readinessState** của Spring Boot. Không nên tự suy luận rằng nó đã kiểm tra database, broker, remote API hoặc chất lượng cache nghiệp vụ.

Nếu một dependency là điều kiện **bắt buộc để nhận traffic**, bạn có thể:

1. Kiểm tra trong runner trước khi SpringApplication ready, với timeout hữu hạn.
2. Xây dựng health indicator cho readiness group phù hợp và định nghĩa điều kiện khi nào trả OUT_OF_SERVICE.
3. Chủ động chuyển ReadinessState.REFUSING_TRAFFIC khi ứng dụng phát hiện không còn đủ khả năng phục vụ.
4. Kiểm soát endpoint/consumer cụ thể để không nhận việc vượt quá trạng thái thực tế.

Không thêm mọi health check của dependency dùng chung vào readiness một cách máy móc; khi dependency đó hỏng, tất cả instance có thể unready cùng lúc, khiến bên điều phối không còn endpoint. Quyết định đúng dựa vào việc **service có thể xử lý công việc hữu ích theo degrade mode không**.

## 15. Từ “sẵn sàng nhận traffic” đến “sẵn sàng nhận mọi loại công việc”

Hệ thống thường có nhiều đường vào:

| Nguồn công việc | Có tự tôn trọng HTTP readiness probe? | Cách phối hợp đúng |
| --- | --- | --- |
| HTTP qua Kubernetes Service/Ingress đã cấu hình probe | Thông thường có, theo routing/endpoint của nền tảng | Readiness probe và timeout phù hợp |
| HTTP gọi trực tiếp instance | Không bảo đảm | Gate ở endpoint/middleware nếu cần |
| Kafka listener | Không tự động vì HTTP probe | autoStartup, pause/resume, lifecycle API, kiểm soát ack |
| RabbitMQ consumer | Không tự động vì HTTP probe | Listener container lifecycle và requeue/nack có kiểm soát |
| Scheduler @Scheduled | Không tự động | Guard trạng thái, bật/tắt scheduler hoặc điều phối job |
| Tác vụ @Async | Không tự động | Chờ kết quả hoặc quản lý readiness theo task |
| Thread tự tạo, cron bên ngoài | Không tự động | Protocol trạng thái, lease/queue, gate tại điểm nhận |
| ApplicationRunner | Chính là một phần startup barrier | Chờ công việc bắt buộc kết thúc, propagate lỗi |

Có thể một ứng dụng chỉ cần ready cho HTTP, còn batch consumer có điều kiện sẵn sàng khác. Khi ấy nên **thiết kế readiness theo từng workstream** hoặc tách service/job để hợp đồng vận hành nhất quán. Không dựa vào một boolean duy nhất nếu các loại công việc có thời điểm khởi tạo khác nhau.

## 16. Timeout, retry và thiết kế startup không bị kẹt

Một runner chờ dependency vô hạn khiến instance mãi không có ApplicationReadyEvent. Đối với service chạy nhiều replica, điều này có thể kéo dài rollout, làm giảm số instance phục vụ và tạo áp lực lên dependency.

Thiết kế thực tế nên:

- Đặt **timeout** cho I/O, JDBC, HTTP, file/object storage và mọi Future được chờ.
- Dùng retry có **số lần tối đa, backoff, jitter** khi lỗi có thể tạm thời.
- Không retry vô hạn trong runner nếu platform có cơ chế restart hợp lý hơn.
- Báo lỗi có cause chính xác để logs/metrics chỉ ra dependency không đáp ứng.
- Khi startup task gây tác dụng phụ DB/broker, đặt **transaction/idempotency/compensation** để an toàn khi Pod restart.
- Quan sát thời gian từng runner bằng timer/trace; **ApplicationStartedEvent.getTimeTaken()** chưa gồm toàn bộ runner, trong khi thời gian đến ready phản ánh tiến trình muộn hơn.
- Nếu công việc mất hàng phút và không cần hoàn tất trước mỗi Pod phục vụ, xem xét tách thành Job/migration/workflow riêng thay vì block startup.
- Khi có nhiều replica, tránh mỗi runner cùng lúc chạy một migration/global job không được điều phối.

**Mục đích không phải làm runner càng ngắn càng tốt bằng cách âm thầm đẩy việc ra background**, mà là giữ chính xác hợp đồng: *đã ready thì điều kiện bắt buộc được đáp ứng*.

## 17. Kịch bản chẩn đoán thực tế

### Tình huống A — Cổng 8080 đã mở nhưng ứng dụng chưa nhận traffic

Khả năng: web server đã khởi tạo trong refresh, nhưng runner preload cache chưa hoàn tất. Kiểm tra log EVENT_STARTED, mốc runner, readiness group và cách Kubernetes chọn endpoint. Không coi “TCP port open” là “startup ready”.

### Tình huống B — ApplicationReadyEvent xuất hiện nhưng cache vẫn rỗng

Kiểm tra runner có **chỉ submit async task rồi trả về**, hoặc catch exception mà không ném lại, hoặc dữ liệu chỉ được nạp ở bean lazy/consumer sau ready. Sửa bằng việc chờ công việc bắt buộc trong runner với timeout và propagate lỗi.

### Tình huống C — HTTP đã ready nhưng Kafka consumer xử lý lỗi ngay lúc startup

Có thể consumer container auto-start trong refresh, trước runner. Cấu hình deferred startup hoặc gate nhận message, kiểm tra ack/nack/backpressure và trách nhiệm của listener container. HTTP readiness không áp đặt trật tự cho consumer.

### Tình huống D — Runner ném lỗi, Pod restart liên tục

Tìm exception gốc, timeout/dependency, idempotency của tác vụ đã làm dở, startupProbe và chính sách restart của workload. Không sửa bằng cách nuốt lỗi rồi báo ready nếu điều kiện đó thật sự bắt buộc.

### Tình huống E — Không thể gọi readiness endpoint trong vài giây đầu

Chưa chắc là lỗi readiness state. HTTP server/Actuator có thể chưa khởi tạo hoặc bind port. Phân biệt **connection refused**, **503 OUT_OF_SERVICE** và **200 UP**; các tín hiệu này thuộc các giai đoạn khác nhau.

### Tình huống F — Một listener ApplicationReadyEvent chạy 40 giây

Listener mặc định đồng bộ, nên có thể trì hoãn việc phát hoàn tất event và readiness state tiếp theo. Nếu đó là tác vụ bắt buộc, chuyển sang runner. Nếu không bắt buộc, dùng task nền/queue với observability, bảo đảm không lấy việc background chưa xong làm điều kiện sẵn sàng giả.

## 18. Bài kiểm tra và chiến lược QA

### Kiểm thử thứ tự lifecycle

Với code mục 7, xác minh:

1. EVENT_STARTED xuất hiện trước RUNNER_WARMUP_START.
2. RUNNER_READINESS_REFUSING_TRAFFIC xuất hiện khi runner thực thi.
3. RUNNER_WARMUP_DONE và RUNNER_VERIFIED xuất hiện trước EVENT_READY.
4. READINESS_ACCEPTING xuất hiện sau EVENT_READY.
5. MAIN_AFTER_RUN xuất hiện sau khi SpringApplication.run(...) trả về.

Không assert toàn bộ stdout vì log của framework và thời gian chạy có thể biến động; chỉ đối chiếu các thông điệp do ví dụ chủ động in.

### Kiểm thử lỗi startup

Với --fail-warmup, kiểm tra runner ném exception, ApplicationReadyEvent và READINESS_ACCEPTING không xuất hiện trên đường thành công; process fail/đóng context theo khả năng của Spring. Nếu runner thực hiện ghi dữ liệu, kiểm tra transaction rollback và idempotency khi restart.

### Kiểm thử HTTP readiness

- Thử **/actuator/health/readiness** sau khi ứng dụng ready: dự kiến UP/200 nếu không có indicator bổ sung làm fail group.
- Nếu có thể bắt khoảng thời gian warm up khi server lắng nghe, kiểm tra 503/OUT_OF_SERVICE; nếu cổng chưa mở, connection refused là kết quả hợp lý.
- Thử **POST /work** khi chưa ready: đoạn code gate trả 503 NOT_READY.
- Sau ready, **POST /work** trả 200 WORK_ACCEPTED theo demo.

### Kiểm thử background consumers

Kích hoạt một message khi runner còn warm up và kiểm tra rằng consumer chưa thực thi nghiệp vụ trước khi dependency sẵn sàng; nếu chưa có gating, thử nghiệm này có thể phát hiện bug dù HTTP readiness hoạt động đúng.

### Kiểm thử async

Cho runner submit CompletableFuture với thời gian xử lý dài hơn; nếu runner không đợi, chứng minh ApplicationReadyEvent có thể xảy ra trước completion. Sau đó sửa runner chờ completion.get(timeout) và kiểm chứng ready chỉ xuất hiện sau completion hoặc startup fail khi timeout.

### Kiểm thử tải và shutdown

Thử rolling update, scale-out, shutdown khi còn request/message, health probes, readiness refusal, xử lý in-flight, retry và giới hạn tài nguyên. Readiness chỉ là tín hiệu; cần xác nhận **hành vi thực tế của từng consumer/endpoint**.

## 19. Những hiểu nhầm phổ biến

**“ApplicationStartedEvent nghĩa là đã sẵn sàng nhận request.”** Sai. Nó đến trước runner; readiness còn có thể REFUSING_TRAFFIC.

**“Runner chạy xong là mọi task background đã xong.”** Sai nếu runner chỉ khởi chạy bất đồng bộ rồi trả về.

**“Spring Boot tự chặn tất cả HTTP request khi chưa ready.”** Không nên giả định. Nền tảng và endpoint cần tuân thủ readiness; truy cập trực tiếp có thể khác.

**“Readiness probe cũng tự pause Kafka consumer.”** Sai. Consumer có lifecycle, polling và ack riêng.

**“Liveness UP nghĩa là cache đã warm.”** Không. Liveness và readiness có mục đích khác nhau.

**“@Order(1) cho runner làm nó chạy trước ApplicationStartedEvent.”** Sai. @Order chỉ sắp thứ tự giữa các runner, không thay đổi chuỗi sự kiện SpringApplication.

**“Một runner fail thì Boot vẫn công bố ACCEPTING_TRAFFIC.”** Không trên đường startup thành công thông thường. Lỗi runner chặn ApplicationReadyEvent và xử lý như startup failure.

**“Listener ApplicationReadyEvent dài luôn an toàn vì app đã ready.”** Event đến ngay trước trạng thái readiness ACCEPTING_TRAFFIC; listener đồng bộ dài có thể trì hoãn transition đó.

**“Không cần timeout vì Kubernetes sẽ restart nếu runner lâu.”** Không đủ. Startup/probe budget, graceful shutdown, ngoại lệ, cancellation và giới hạn tải cần được thiết kế chủ động.

**“Runner chỉ thực hiện đúng một lần cho toàn cluster.”** Sai. Runner là hook mỗi lần SpringApplication khởi động; nhiều Pod và restart có thể chạy lại.

**“Readiness luôn bao gồm mọi health indicator và mọi dependency.”** Không. Health group mặc định và các custom indicators cần được cấu hình rõ theo hợp đồng.

**“Trả 503 khi chưa ready là toàn bộ giải pháp.”** Chưa đủ với gRPC, messaging, scheduled jobs, direct callers, background threads hoặc những HTTP path không thực hiện gate.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Spring Boot gọi ApplicationRunner trước hay sau ApplicationStartedEvent?  
**Đáp án:** Sau ApplicationStartedEvent và sau LivenessState.CORRECT theo chuỗi mặc định.

**Câu 2.** ReadinessState.ACCEPTING_TRAFFIC được công bố trước hay sau runner?  
**Đáp án:** Sau khi các runner hoàn tất thành công và sau ApplicationReadyEvent.

**Câu 3.** Vì sao liveness CORRECT không đủ chứng minh service sẵn sàng nhận traffic?  
**Đáp án:** Context có thể đã refresh nhưng runner vẫn đang warm up và readiness còn REFUSING_TRAFFIC.

**Câu 4.** Nếu runner gọi asyncService.start() rồi trả về ngay, SpringApplication biết task hoàn tất không?  
**Đáp án:** Không. Cần chờ/có trạng thái hoàn thành thực nếu task là điều kiện ready.

**Câu 5.** Nên dùng gì cho cache preload bắt buộc trước traffic?  
**Đáp án:** ApplicationRunner/CommandLineRunner với timeout, fail-fast và kiểm chứng kết quả; không chỉ log “đã bắt đầu tải”.

**Câu 6.** HTTP readiness probe có tự ngăn KafkaListener nhận message không?  
**Đáp án:** Không. Cần cấu hình listener container/lifecycle/gate riêng.

**Câu 7.** Nếu runner ném exception, ApplicationReadyEvent có xuất hiện theo nhánh thành công không?  
**Đáp án:** Không.

**Câu 8.** Lệnh curl nhận connection refused khi ứng dụng vừa startup; có phải readiness 503 không?  
**Đáp án:** Không. Connection refused nghĩa là chưa có server đáp ứng ở địa chỉ/cổng, khác với HTTP 503 do probe trả.

**Câu 9.** Cổng web đã mở trước runner, nên hệ thống có thể nhận request trực tiếp không?  
**Đáp án:** Tùy web stack và cách truy cập, có thể. Bên điều phối cần theo readiness; endpoint quan trọng có thể cần gate rõ ràng.

**Câu 10.** Một listener ApplicationReadyEvent dùng Thread.sleep(5000) có thể làm gì?  
**Đáp án:** Nếu chạy đồng bộ, nó có thể trì hoãn thời điểm Spring Boot công bố ACCEPTING_TRAFFIC.

**Câu 11.** Có nên đưa remote database health vào liveness luôn không?  
**Đáp án:** Không máy móc; dependency chung lỗi có thể khiến mọi instance restart cùng lúc. Cân nhắc readiness và degrade policy.

**Câu 12.** Sau khi ready, cache quan trọng hỏng thì runner có tự chạy lại không?  
**Đáp án:** Không. Runner là bước startup; cần cơ chế runtime health, sửa chữa, thay đổi readiness hoặc restart theo chính sách.

**Kết luận:** **ApplicationRunner/CommandLineRunner là ranh giới thực thi công việc khởi động bắt buộc trước readiness**, không phải công tắc điều khiển tất cả luồng nhận việc. Spring Boot công bố **ApplicationStartedEvent → runners → ApplicationReadyEvent → ReadinessState.ACCEPTING_TRAFFIC**. Muốn “ready nghĩa là có thể xử lý đúng công việc”, hãy đợi công việc bắt buộc thực sự hoàn thành trong runner, báo lỗi trung thực, cấu hình readiness probe, đồng thời kiểm soát riêng HTTP direct calls, consumer, scheduler và tác vụ bất đồng bộ theo hợp đồng của chúng.

### Tài liệu tham khảo

- [Spring Boot — SpringApplication: Application Events, Runners, Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot — Actuator Endpoints: Kubernetes Probes and Application Lifecycle](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot 3.3 — ApplicationAvailability API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html)
- [Spring Boot 3.3 — ReadinessState API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ReadinessState.html)
- [Spring Boot 3.3 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html)
