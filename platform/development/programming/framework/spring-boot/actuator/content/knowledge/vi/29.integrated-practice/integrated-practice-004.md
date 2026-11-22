# Thêm metrics nghiệp vụ với tag được giới hạn

## 1. Bài thực hành giải quyết vấn đề gì?

Metrics hạ tầng cho biết CPU, bộ nhớ hoặc HTTP request đang hoạt động ra sao. Metrics nghiệp vụ trả lời những câu hỏi gần với hoạt động của hệ thống hơn:

- Có bao nhiêu đơn hàng được tạo thành công?
- Có bao nhiêu lần checkout bị từ chối hoặc gặp lỗi?
- Thời gian xử lý checkout khác nhau thế nào giữa các kênh?
- Bao nhiêu đầu vào không thuộc các kênh mà hệ thống đã chuẩn hóa?

Trong Micrometer, **tag** là cặp khóa–giá trị gắn vào meter, chẳng hạn `channel=web` hoặc `outcome=success`. Khi xuất sang Prometheus, chúng trở thành label.

Tag hữu ích để chia nhỏ dữ liệu, nhưng mỗi tổ hợp giá trị có thể tạo thêm chuỗi thời gian. Nếu đưa `orderId`, `userId` hoặc chuỗi tự do từ request vào tag, số tổ hợp có thể tăng theo dữ liệu nghiệp vụ và không có giới hạn hợp lý.

Mục tiêu của bài là tạo metrics có ý nghĩa, đồng thời kiểm soát **độ đa dạng giá trị tag (cardinality)** ngay từ thiết kế và tại điểm nhận dữ liệu.

Ví dụ dùng Spring Boot 3.3.x, Java 17+ và Micrometer do Spring Boot quản lý phiên bản. Ứng dụng thử nghiệm chỉ chạy cục bộ, dùng Servlet stack và xuất Prometheus qua Actuator.

## 2. Chốt ngữ nghĩa trước khi viết code

Bài thực hành mô phỏng một thao tác checkout:

- `success`: thao tác tạo đơn được coi là thành công.
- `rejected`: nghiệp vụ chủ động từ chối.
- `error`: phát sinh exception trong xử lý.

Ta thiết kế hai meter:

| Tên Micrometer | Loại | Ý nghĩa | Tag |
| --- | --- | --- | --- |
| `business.orders.created` | Counter | Số đơn được tạo thành công tại điểm ghi nhận của ví dụ | channel |
| `business.checkout.duration` | Timer | Thời gian và số lần hoàn tất xử lý checkout, gồm cả từ chối/lỗi | channel, outcome |

Counter chỉ đếm sự kiện tạo đơn thành công. Timer vừa đo thời gian vừa có số lần ghi nhận, nên không cần tạo thêm một counter tổng số lần checkout chỉ để sao chép đúng count của timer.

Đây là mô phỏng không ghi database và không thanh toán thật. Khi áp dụng vào hệ thống có transaction, phải chọn lại điểm ghi nhận thành công sao cho phù hợp với commit nghiệp vụ.

### 2.1. Bộ giá trị được phép

| Tag | Giá trị cố định | Xử lý đầu vào ngoài tập |
| --- | --- | --- |
| channel | web, mobile, batch, other | Chuẩn hóa về other |
| outcome | success, rejected, error | Suy ra từ luồng xử lý, không lấy nguyên từ client |

Ta giữ nguyên tên tag cho mọi meter cùng một họ. Không lúc dùng `channel`, lúc đổi thành `source` cho cùng tên metric; cũng không đăng ký cùng họ timer với các bộ khóa tag khác nhau.

Chữ hoa/thường và khoảng trắng quanh channel được chuẩn hóa. `WEB`, `web` và ` web ` đều là `web`. Giá trị rỗng, thiếu hoặc không được nhận diện đều là `other`.

Outcome là kết quả mà service quan sát được. Trong bài thử nghiệm, client chọn một kịch bản để kích hoạt từng nhánh; trong hệ thống thật, client không được tự tuyên bố outcome để làm sai số liệu.

### 2.2. Giới hạn số meter có thể tạo

Với cách đăng ký trước mọi tổ hợp:

```text
Counter: 4 channel                         =  4 meter
Timer:   4 channel × 3 outcome             = 12 meter
Tổng meter nghiệp vụ của bộ ghi nhận này   = 16 meter
```

Đây là số định danh meter trong một registry, không phải tổng số series Prometheus. Một timer có thể xuất nhiều series như count, sum, các bucket hoặc thông tin khác tùy cấu hình/exporter.

Trong ứng dụng Spring Boot đang chạy, registry còn có meter JVM, HTTP và các thành phần khác. Vì vậy không kỳ vọng tổng toàn bộ registry của ứng dụng bằng 16; con số này chỉ áp dụng cho tập meter nghiệp vụ đã thiết kế.

## 3. Chuẩn bị dependency và cấu hình

Dùng dự án Spring Boot đã có Gradle wrapper, Boot plugin và cơ chế quản lý dependency phù hợp. Phần cấu hình cần bổ sung:

```groovy
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
    archiveFileName = 'bounded-business-metrics.jar'
}
```

Đây không phải toàn bộ build file. Trong repository có build orchestration, dùng cơ chế của repository để tránh cấu hình trùng.

Tệp `src/main/resources/application.yml` của bài cục bộ:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Bài tối giản không thêm Spring Security hoặc proxy. Nếu chạy trong môi trường đã có chúng, phải sử dụng quyền truy cập tương ứng; không bỏ bảo mật của một ứng dụng thật để làm theo bài thử nghiệm.

Không expose toàn bộ Actuator để đọc một bản xuất Prometheus. Các endpoint khác không cần cho mục tiêu thực hành này.

## 4. Tạo bộ ghi nhận với bộ tag cố định

### 4.1. Lớp khởi động

Tệp `src/main/java/demo/businessmetrics/BusinessMetricsApplication.java`:

```java
package demo.businessmetrics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BusinessMetricsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BusinessMetricsApplication.class, args);
    }
}
```

### 4.2. Chuẩn hóa channel và đăng ký meter một lần

Tệp `src/main/java/demo/businessmetrics/CheckoutMetrics.java`:

```java
package demo.businessmetrics;

import java.util.EnumMap;
import java.util.Locale;
import java.util.Map;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class CheckoutMetrics {

    public enum Channel {
        WEB("web"),
        MOBILE("mobile"),
        BATCH("batch"),
        OTHER("other");

        private final String tag;

        Channel(String tag) {
            this.tag = tag;
        }

        public String tag() {
            return tag;
        }

        public static Channel fromRaw(String raw) {
            if (raw == null) {
                return OTHER;
            }

            return switch (raw.trim().toLowerCase(Locale.ROOT)) {
                case "web" -> WEB;
                case "mobile" -> MOBILE;
                case "batch" -> BATCH;
                default -> OTHER;
            };
        }
    }

    public enum Outcome {
        SUCCESS("success"),
        REJECTED("rejected"),
        ERROR("error");

        private final String tag;

        Outcome(String tag) {
            this.tag = tag;
        }

        public String tag() {
            return tag;
        }
    }

    private final MeterRegistry registry;

    private final Map<Channel, Counter> created =
            new EnumMap<>(Channel.class);

    private final Map<Channel, Map<Outcome, Timer>> durations =
            new EnumMap<>(Channel.class);

    public CheckoutMetrics(MeterRegistry registry) {
        this.registry = registry;

        for (Channel channel : Channel.values()) {
            created.put(channel,
                    Counter.builder("business.orders.created")
                            .description("Successfully created orders")
                            .tag("channel", channel.tag())
                            .register(registry));

            Map<Outcome, Timer> byOutcome = new EnumMap<>(Outcome.class);

            for (Outcome outcome : Outcome.values()) {
                Timer timer = Timer.builder("business.checkout.duration")
                        .description("Completed checkout processing duration")
                        .tags("channel", channel.tag(),
                                "outcome", outcome.tag())
                        .register(registry);

                byOutcome.put(outcome, timer);
            }

            durations.put(channel, byOutcome);
        }
    }

    public Timer.Sample start() {
        return Timer.start(registry);
    }

    public void orderCreated(Channel channel) {
        created.get(channel).increment();
    }

    public void stop(
            Timer.Sample sample,
            Channel channel,
            Outcome outcome) {
        sample.stop(durations.get(channel).get(outcome));
    }
}
```

Các map được xây dựng trong constructor rồi chỉ dùng để tra cứu. Bộ đếm và timer của Micrometer hỗ trợ các thao tác ghi nhận đồng thời; ta không thêm phần tử vào map ở mỗi request.

Có ba quyết định thiết kế ở đây:

1. Enum giữ tập giá trị xuất ra hữu hạn.
2. Chuỗi raw được chuẩn hóa trước khi dùng để chọn meter.
3. Mọi meter được đăng ký một lần, không tạo cache theo chuỗi đầu vào không giới hạn.

Không thay map enum bằng `ConcurrentHashMap<String, Timer>` rồi dùng channel raw làm key. Một map an toàn khi truy cập đồng thời vẫn có thể tăng bộ nhớ không giới hạn.

Đăng ký trước 16 meter là lựa chọn nhỏ, có chủ đích của bài này. Nếu tập tổ hợp hợp lệ rất lớn, chính việc đăng ký trước cũng có thể tốn tài nguyên; cần giảm số chiều thay vì chỉ đổi từ đăng ký động sang đăng ký toàn bộ.

## 5. Ghi nhận đúng một lần cho mỗi nhánh nghiệp vụ

Tệp `src/main/java/demo/businessmetrics/CheckoutService.java`:

```java
package demo.businessmetrics;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    public enum Scenario {
        SUCCESS,
        REJECTED,
        ERROR
    }

    private final CheckoutMetrics metrics;

    public CheckoutService(CheckoutMetrics metrics) {
        this.metrics = metrics;
    }

    public boolean checkout(String rawChannel, Scenario scenario) {
        CheckoutMetrics.Channel channel =
                CheckoutMetrics.Channel.fromRaw(rawChannel);

        var sample = metrics.start();
        CheckoutMetrics.Outcome outcome = CheckoutMetrics.Outcome.ERROR;

        try {
            if (scenario == Scenario.REJECTED) {
                outcome = CheckoutMetrics.Outcome.REJECTED;
                return false;
            }

            if (scenario == Scenario.ERROR) {
                throw new IllegalStateException("simulated checkout failure");
            }

            metrics.orderCreated(channel);
            outcome = CheckoutMetrics.Outcome.SUCCESS;
            return true;
        } finally {
            metrics.stop(sample, channel, outcome);
        }
    }
}
```

Giải thích thứ tự:

- Channel đã được đưa về tập cho phép trước khi chọn meter.
- `Timer.Sample` bắt đầu khi service nhận xử lý.
- Outcome mặc định là error, để exception trong nhánh xử lý không bị ghi thành success.
- Counter chỉ tăng ở nhánh tạo đơn thành công.
- Khối `finally` ghi timer khi return hoặc khi exception thoát khỏi try.
- Mỗi lần gọi trong các kịch bản hợp lệ của bài chỉ có một lần stop sample.

Timer của service không phải thời gian HTTP end-to-end. Nó không bao gồm toàn bộ thời gian lọc bảo mật, chuyển đổi tham số hoặc gửi response. Nếu cần hai loại thời gian này, đặt tên/ngữ nghĩa riêng để tránh so sánh nhầm.

Một tham số HTTP không chuyển đổi được thành Scenario có thể bị framework trả 400 trước khi vào service. Request đó không được timer nghiệp vụ này đếm. Đây là ranh giới phép đo, không phải tự động là thiếu dữ liệu.

### Độ tin cậy của số liệu

Metrics trong bộ nhớ không phải sổ cái giao dịch. Tiến trình dừng đột ngột có thể làm mất dữ liệu chưa được scrape. Retry có thể tạo thêm lần xử lý; increment trước khi transaction commit có thể đếm một giao dịch sau đó rollback.

Khi triển khai thật, định nghĩa rõ đang đếm lần thử, kết quả service hay sự kiện đã commit. Nếu cần số liệu kế toán chính xác hoặc xử lý đúng một lần theo sự kiện nghiệp vụ, phải có nguồn dữ liệu bền vững phù hợp; không lấy một counter trong RAM thay thế.

## 6. Tạo API để kích hoạt các nhánh

Tệp `src/main/java/demo/businessmetrics/CheckoutController.java`:

```java
package demo.businessmetrics;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CheckoutController {
    private final CheckoutService service;

    public CheckoutController(CheckoutService service) {
        this.service = service;
    }

    @PostMapping("/lab/checkout")
    public ResponseEntity<String> checkout(
            @RequestParam(name = "channel", defaultValue = "") String channel,
            @RequestParam(name = "scenario", defaultValue = "SUCCESS")
            CheckoutService.Scenario scenario) {
        try {
            boolean created = service.checkout(channel, scenario);

            if (created) {
                return ResponseEntity.status(HttpStatus.CREATED)
                        .body("created");
            }

            return ResponseEntity.status(422).body("rejected");
        } catch (IllegalStateException exception) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("failed");
        }
    }
}
```

API này dùng POST vì nó kích hoạt một thao tác mô phỏng nghiệp vụ. Tham số scenario chỉ là công cụ của bài thực hành để tái hiện kết quả; không phải thiết kế cho phép client điều khiển kết quả nghiệp vụ trong hệ thống thật.

Trong ví dụ, enum HTTP dùng giá trị `SUCCESS`, `REJECTED`, `ERROR`. Tag outcome xuất ra là chữ thường và được chọn trong service. Hai tập giá trị có vai trò khác nhau.

Phần bắt `IllegalStateException` ở controller phục vụ lỗi mô phỏng cụ thể. Không coi đây là chính sách xử lý mọi exception cho một ứng dụng sản xuất.

## 7. Thêm giới hạn tại MeterRegistry

Chuẩn hóa bằng enum là cơ chế chính. Thêm `MeterFilter` để chặn việc một đường instrumentation khác vô tình đăng ký thêm giá trị tag.

Tệp `src/main/java/demo/businessmetrics/MetricGuardConfiguration.java`:

```java
package demo.businessmetrics;

import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricGuardConfiguration {

    @Bean
    MeterFilter businessChannelGuard() {
        return MeterFilter.maximumAllowableTags(
                "business.",
                "channel",
                4,
                MeterFilter.deny());
    }

    @Bean
    MeterFilter checkoutOutcomeGuard() {
        return MeterFilter.maximumAllowableTags(
                "business.checkout.duration",
                "outcome",
                3,
                MeterFilter.deny());
    }
}
```

Spring Boot áp dụng các bean MeterFilter cho registry do cơ chế Boot quản lý. Một registry tự tạo bằng `new SimpleMeterRegistry()` ở nơi khác không tự nhận các bean này; khi kiểm thử trực tiếp phải gắn filter vào registry thử nghiệm.

Ý nghĩa và giới hạn:

- Tiền tố tên được kiểm tra theo tên meter Micrometer, không phải tên đã đổi sang dấu gạch dưới trong Prometheus.
- Bộ giới hạn channel áp dụng cho các meter bắt đầu bằng `business.`.
- Giới hạn là số giá trị tag phân biệt mà filter theo dõi trong phạm vi đó.
- Vượt giới hạn thì từ chối đăng ký meter theo filter được truyền vào; không tự đổi giá trị về other.
- Đây không phải danh sách cho phép chính xác. Nếu bốn giá trị sai được đăng ký trước, chỉ đặt max=4 không biến chúng thành web/mobile/batch/other.
- Filter không tự xóa meter đã tồn tại hoặc tự thu hồi những giá trị cũ để nhận giá trị mới.
- Meter bị từ chối có thể trở thành phép ghi nhận không có dữ liệu xuất ra; không coi việc lời gọi Java không ném exception là bằng chứng phép đo đã được lưu.

Vì vậy, không dùng filter như một thuật toán lấy “bốn channel xuất hiện đầu tiên”. Tập giá trị cho phép phải nằm trong thiết kế và được chuẩn hóa trước đăng ký.

Giới hạn từng tag cũng chưa giới hạn tổng số meter nếu tên metric hoặc các tag khác còn tăng tự do. Không tạo tên như `business.orders.customer.12345` để né giới hạn tag; vấn đề cardinality chỉ chuyển sang tên metric.

## 8. Kiểm thử giới hạn tag và các nhánh kết quả

Các kiểm thử dưới đây dùng `SimpleMeterRegistry` riêng, không khởi động web server. Vì registry này chỉ chứa bộ meter của ví dụ, có thể kiểm tra chính xác tổng là 16.

Tệp `src/test/java/demo/businessmetrics/CheckoutMetricsTest.java`:

```java
package demo.businessmetrics;

import java.time.Duration;
import java.util.Set;
import java.util.stream.Collectors;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CheckoutMetricsTest {

    private static SimpleMeterRegistry registryWithGuards() {
        var registry = new SimpleMeterRegistry();
        var guards = new MetricGuardConfiguration();

        registry.config()
                .meterFilter(guards.businessChannelGuard())
                .meterFilter(guards.checkoutOutcomeGuard());

        return registry;
    }

    @Test
    void rawChannelsDoNotCreateUnboundedMeters() {
        try (var registry = registryWithGuards()) {
            var metrics = new CheckoutMetrics(registry);
            var service = new CheckoutService(metrics);

            service.checkout(" WEB ", CheckoutService.Scenario.SUCCESS);
            service.checkout("Web", CheckoutService.Scenario.SUCCESS);
            service.checkout(null, CheckoutService.Scenario.SUCCESS);

            for (int index = 0; index < 1_000; index++) {
                service.checkout("partner-" + index,
                        CheckoutService.Scenario.SUCCESS);
            }

            assertEquals(16, registry.getMeters().size());

            assertEquals(2.0, registry.get("business.orders.created")
                    .tag("channel", "web").counter().count(), 0.0);

            assertEquals(1_001.0, registry.get("business.orders.created")
                    .tag("channel", "other").counter().count(), 0.0);

            assertEquals(1_001L,
                    registry.get("business.checkout.duration")
                            .tags("channel", "other",
                                    "outcome", "success")
                            .timer().count());

            Set<String> channels = registry.getMeters().stream()
                    .map(meter -> meter.getId().getTag("channel"))
                    .collect(Collectors.toSet());

            assertEquals(Set.of("web", "mobile", "batch", "other"),
                    channels);
        }
    }

    @Test
    void rejectedAndErrorAreTimedWithoutCreatedOrders() {
        try (var registry = registryWithGuards()) {
            var metrics = new CheckoutMetrics(registry);
            var service = new CheckoutService(metrics);

            assertFalse(service.checkout("mobile",
                    CheckoutService.Scenario.REJECTED));

            assertThrows(IllegalStateException.class,
                    () -> service.checkout("batch",
                            CheckoutService.Scenario.ERROR));

            assertEquals(1L,
                    registry.get("business.checkout.duration")
                            .tags("channel", "mobile",
                                    "outcome", "rejected")
                            .timer().count());

            assertEquals(1L,
                    registry.get("business.checkout.duration")
                            .tags("channel", "batch",
                                    "outcome", "error")
                            .timer().count());

            assertEquals(0.0, registry.get("business.orders.created")
                    .tag("channel", "mobile").counter().count(), 0.0);

            assertEquals(0.0, registry.get("business.orders.created")
                    .tag("channel", "batch").counter().count(), 0.0);
        }
    }

    @Test
    void guardsDenyAdditionalTagValues() {
        try (var registry = registryWithGuards()) {
            new CheckoutMetrics(registry);

            registry.counter("business.orders.created",
                    "channel", "unexpected-channel").increment();

            registry.timer("business.checkout.duration",
                    "channel", "web",
                    "outcome", "unexpected-outcome")
                    .record(Duration.ofMillis(1));

            assertNull(registry.find("business.orders.created")
                    .tag("channel", "unexpected-channel").counter());

            assertNull(registry.find("business.checkout.duration")
                    .tags("channel", "web",
                            "outcome", "unexpected-outcome")
                    .timer());

            assertEquals(16, registry.getMeters().size());
        }
    }
}
```

Chạy:

```bash
./gradlew test
```

Trên Windows dùng `gradlew.bat test`. Nếu dùng multi-project build, chọn task path của đúng module.

Những kiểm thử này chứng minh ba điều khác nhau:

| Kiểm thử | Điều được xác minh |
| --- | --- |
| 1.000 chuỗi đầu vào lạ | Không làm tăng số meter, vẫn ghi nhận đủ vào other |
| Nhánh rejected/error | Timer vẫn ghi một lần khi return từ chối hoặc exception; counter thành công không tăng |
| Đăng ký tag vượt giới hạn | Filter chặn meter mới có giá trị ngoài số lượng đã được đăng ký |

Bài kiểm tra đầu không chỉ xác nhận số meter không tăng. Nó còn xác nhận số sự kiện vẫn được cộng vào other, tránh trường hợp “giới hạn thành công” bằng cách làm mất mọi phép đo.

Không assert thời gian xử lý bằng một con số cố định. Thời gian thực thi phụ thuộc máy và lịch chạy; điều cần kiểm tra trong ví dụ là timer count và đúng bộ tag.

Kết quả cần đạt là ba test thành công. Dạng console/report cụ thể phụ thuộc Gradle và cấu hình logging, nên không coi một dòng log Gradle dự đoán là stdout cố định.

## 9. Chạy API và kiểm tra bản xuất Prometheus

### 9.1. Khởi động một tiến trình mới

```bash
./gradlew bootJar
java -jar build/libs/bounded-business-metrics.jar
```

Với Windows, dùng `gradlew.bat bootJar`.

Các tệp Java ứng dụng cần dependency của Spring Boot/Micrometer. Lệnh `java -jar` chạy executable JAR đã đóng gói; không chạy riêng các class ứng dụng bằng `javac` khi chưa thiết lập classpath.

Giữ tiến trình đang chạy và mở terminal khác. Trên Windows, dùng `curl.exe` nếu `curl` đang bị một alias PowerShell thay thế.

### 9.2. Gửi bốn request có chủ đích

Trên một tiến trình vừa khởi động, chưa có request checkout nào khác:

```bash
curl -i -X POST "http://127.0.0.1:8080/lab/checkout?channel=web&scenario=SUCCESS"
curl -i -X POST "http://127.0.0.1:8080/lab/checkout?channel=mobile&scenario=REJECTED"
curl -i -X POST "http://127.0.0.1:8080/lab/checkout?channel=batch&scenario=ERROR"
curl -i -X POST "http://127.0.0.1:8080/lab/checkout?channel=partner-42&scenario=SUCCESS"
```

Kỳ vọng:

| Request | HTTP status | Body |
| --- | --- | --- |
| web / SUCCESS | 201 | created |
| mobile / REJECTED | 422 | rejected |
| batch / ERROR | 500 | failed |
| partner-42 / SUCCESS | 201 | created |

Trong các lệnh này không dùng `--fail`, để có thể đọc status và body của cả nhánh 422/500. curl không tự coi mọi HTTP status lỗi là lỗi kết nối.

Các body trên do controller trả về, không được code thêm ký tự xuống dòng. Header có thể chứa thông tin động; không coi toàn bộ response HTTP là một chuỗi stdout cố định.

### 9.3. Kiểm tra giá trị logic sau bốn request

| Meter | Tag | Giá trị cần có |
| --- | --- | --- |
| business.orders.created | channel=web | count=1 |
| business.orders.created | channel=other | count=1 |
| business.orders.created | channel=mobile | count=0 |
| business.orders.created | channel=batch | count=0 |
| business.checkout.duration | channel=web, outcome=success | count=1 |
| business.checkout.duration | channel=mobile, outcome=rejected | count=1 |
| business.checkout.duration | channel=batch, outcome=error | count=1 |
| business.checkout.duration | channel=other, outcome=success | count=1 |

Các timer còn lại có count=0. Tổng số lần được timer ghi nhận là 4; tổng đơn thành công là 2.

Lần lỗi được đo ở outcome=error chứ không tạo một tag chứa exception message. Channel `partner-42` không được xuất nguyên văn; nó được cộng vào other.

Đọc bản xuất:

```bash
curl -i http://127.0.0.1:8080/actuator/prometheus
```

Tìm các tên xuất tương ứng:

```text
business_orders_created_total
business_checkout_duration_seconds_count
business_checkout_duration_seconds_sum
```

Tên metric trong bản xuất khác tên Micrometer. Timer được xuất theo đơn vị phù hợp của exporter; các tên trên thể hiện giây. Cách biểu diễn số, thứ tự dòng và nhãn bổ sung có thể khác theo exporter/cấu hình.

Không dự đoán một giá trị cố định cho duration sum. Các request trong mô phỏng không cố tình sleep và thời gian xử lý phụ thuộc môi trường.

Kiểm tra thêm rằng không có giá trị tag `partner-42`, ID đơn hàng hay chuỗi lỗi thô trong họ metric này. Việc gọi endpoint scrape không làm counter tạo đơn tăng, vì nó không gọi handler checkout.

### 9.4. Kiểm tra chuẩn hóa và ranh giới phép đo

Thử thêm channel có chữ hoa và khoảng trắng:

```bash
curl -i -X POST --data-urlencode "channel= WEB " --data-urlencode "scenario=SUCCESS" http://127.0.0.1:8080/lab/checkout
```

Request này phải tăng series channel=web đang có, không tạo series channel=WEB hoặc channel có khoảng trắng.

Thử không truyền channel:

```bash
curl -i -X POST "http://127.0.0.1:8080/lab/checkout?scenario=SUCCESS"
```

Giá trị mặc định rỗng được đưa về other.

Nếu truyền scenario không hợp lệ:

```bash
curl -i -X POST "http://127.0.0.1:8080/lab/checkout?channel=web&scenario=UNKNOWN"
```

Framework trả lỗi chuyển đổi tham số, thông thường là 400 trong cấu hình tối giản của bài, trước khi vào service. Timer nghiệp vụ không tăng cho request đó. Metrics HTTP tự động có thể vẫn ghi request; đó là một phép đo khác.

Sau các request bổ sung, số liệu không còn bằng bảng của đúng bốn request ban đầu. Ghi lại số lần gọi thực tế hoặc khởi động lại tiến trình trước khi lặp một kịch bản cần số đếm chính xác.

## 10. Truy vấn theo đúng ngữ nghĩa và đơn vị

Các ví dụ sau giả định Prometheus đã scrape được ứng dụng. Tên job/instance và các nhãn hạ tầng phải phù hợp với hệ thống đang dùng.

### 10.1. Tốc độ tạo đơn thành công theo channel

```promql
sum by (channel) (
  rate(business_orders_created_total[5m])
)
```

Kết quả là số sự kiện thành công mỗi giây. Đây không phải tổng số lần thử checkout, vì counter không tăng ở rejected hoặc error.

Dùng `rate()` trên từng chuỗi rồi tổng hợp để xử lý counter reset theo từng instance. Không cộng các counter của nhiều instance trước rồi mặc định coi kết quả như một counter đơn không reset.

### 10.2. Số lần xử lý checkout theo channel và outcome

```promql
sum by (channel, outcome) (
  rate(business_checkout_duration_seconds_count[5m])
)
```

Timer count bao gồm các kết quả được service ghi nhận. Nó không bao gồm request bị từ chối trước service hoặc hoạt động chưa hoàn tất.

### 10.3. Thời gian trung bình theo channel

```promql
sum by (channel) (
  rate(business_checkout_duration_seconds_sum[5m])
)
/
sum by (channel) (
  rate(business_checkout_duration_seconds_count[5m])
)
```

Kết quả tính bằng giây. Muốn biểu diễn mili giây thì nhân kết quả với 1000 ở lớp truy vấn/hiển thị.

Khi không có lưu lượng, mẫu số có thể bằng 0 và kết quả có thể là NaN. Không tự diễn giải thành “thời gian xử lý bằng 0” hoặc “exporter hỏng”.

### 10.4. Tỷ lệ lỗi trong các lần xử lý

```promql
sum(
  rate(business_checkout_duration_seconds_count{outcome="error"}[5m])
)
/
sum(
  rate(business_checkout_duration_seconds_count[5m])
)
```

Nếu nghiệp vụ coi cả rejected là kết quả cần theo dõi riêng, tạo tỷ lệ riêng cho rejected. Không âm thầm gộp từ chối nghiệp vụ với lỗi kỹ thuật nếu định nghĩa vận hành phân biệt chúng.

### 10.5. Tỷ lệ channel chưa được nhận diện

```promql
sum(
  rate(business_checkout_duration_seconds_count{channel="other"}[5m])
)
/
sum(
  rate(business_checkout_duration_seconds_count[5m])
)
```

Other giúp giữ giới hạn cardinality nhưng có đánh đổi: mất phân biệt giữa các giá trị lạ. Tỷ lệ other tăng là lý do kiểm tra dữ liệu đầu vào và taxonomy, không phải lý do tự động xuất mọi chuỗi lạ thành tag.

Các cửa sổ `5m` chỉ là ví dụ. `rate()` cần đủ mẫu theo scrape interval; một request vừa chạy và một lần scrape chưa đủ để mọi truy vấn tốc độ có kết quả ổn định.

### 10.6. Percentile cần có dữ liệu phân phối phù hợp

Timer count và sum không đủ để khôi phục p95. Với classic histogram đã được bật phù hợp, có thể dùng:

```promql
histogram_quantile(
  0.95,
  sum by (le, channel) (
    rate(business_checkout_duration_seconds_bucket[5m])
  )
)
```

Bài cấu hình cơ bản chưa bật histogram cho timer này, nên không kỳ vọng query bucket tự có dữ liệu. Cần quyết định riêng về histogram, khoảng giá trị, bucket và ngân sách series trước khi bật.

Không lấy trung bình các p95 của từng instance để coi là p95 toàn hệ thống. Không thể biến một average duration thành percentile chỉ bằng đổi tên biểu đồ.

## 11. Tính ngân sách cardinality khi mở rộng

Nếu thêm một chiều tag có N giá trị độc lập, số tổ hợp có thể tăng theo N. Ví dụ thêm `payment_method` với 5 giá trị vào timer 12 tổ hợp có thể làm nó thành 60 tổ hợp.

Đây là mức tối đa theo tập giá trị và các tổ hợp được phép; không phải mọi mô hình dữ liệu đều thực sự tạo toàn bộ tích Descartes. Riêng cách đăng ký trước trong bài tạo đủ mọi tổ hợp đã thiết kế.

Ngân sách cần tính cả:

- Số bộ tag cho mỗi họ metric.
- Số series mà loại meter/exporter sinh ra.
- Số target/replica được scrape.
- Nhãn hạ tầng hoặc common tags được thêm vào.
- Số bộ nhãn khác nhau được tích lũy trong khoảng lưu trữ dữ liệu.

Với classic histogram, nếu mỗi tổ hợp xuất B bucket, trong đó B đã tính bucket +Inf, thì riêng bucket cộng count và sum có B+2 series cho mỗi tổ hợp. Một số exporter còn có series khác; không dùng B+2 như công thức đầy đủ cho mọi cấu hình.

Không áp dụng nguyên công thức bucket này cho mọi cách triển khai native histogram hoặc summary. Cần biết loại dữ liệu thực tế đã chọn.

Những tag nên tránh trong metrics nghiệp vụ tổng hợp:

| Giá trị | Vì sao không phù hợp? | Nơi phù hợp hơn khi cần điều tra |
| --- | --- | --- |
| orderId, requestId, traceId | Gần như tăng theo từng sự kiện | Log hoặc trace có chính sách truy cập/lưu trữ phù hợp |
| userId, email | Cardinality cao và có thể chứa dữ liệu cá nhân | Nguồn điều tra có kiểm soát |
| URL đầy đủ hoặc query string | Có ID/tham số thay đổi liên tục | Route template hoặc log được xử lý phù hợp |
| Exception message | Không ổn định, có thể chứa dữ liệu đầu vào | Log có cấu trúc; tag lỗi chỉ dùng phân loại hữu hạn |
| Tên đối tác nhập tự do | Tập giá trị có thể mở rộng ngoài dự kiến | Danh mục hữu hạn đã duyệt hoặc other |

Băm userId/email không làm số lượng giá trị phân biệt giảm đi. Nó cũng không tự là biện pháp ẩn danh đủ cho mọi mục đích; không dùng hash như cách chữa cardinality.

Giới hạn số ký tự của tag không tương đương giới hạn số giá trị. Một triệu chuỗi ngắn vẫn là một triệu giá trị khác nhau.

Nếu hệ thống có common tags như region/service, cần kiểm tra chúng cũng có tập giá trị được kiểm soát và không xung đột với tên tag của nghiệp vụ. Filter của ví dụ chỉ bảo vệ các chiều đã cấu hình; nó không kiểm soát mọi chiều khác trong toàn hệ thống.

## 12. Các lỗi triển khai dễ gặp

### Gắn tag raw rồi hy vọng exporter tự giới hạn

Micrometer/Prometheus không tự hiểu một chuỗi là “ID không nên dùng”. Chuẩn hóa phải xảy ra trước đăng ký meter. Giới hạn bổ sung tại registry không thay thế được quyết định ngữ nghĩa.

### Đăng ký cùng tên với bộ khóa tag khác nhau

Một họ metric lúc có channel, lúc có channel+userId có thể gây xung đột hoặc tạo mô hình dữ liệu không nhất quán. Giữ schema ổn định và kiểm tra cảnh báo đăng ký của registry.

### Nhầm meter bị từ chối với sự kiện được gom vào other

Deny filter chặn meter mới; nó không chuyển sự kiện sang một meter khác. Muốn giữ tổng số sự kiện theo nhóm other phải thực hiện chuẩn hóa trong bộ ghi nhận, như kiểm thử đã xác nhận.

### Ghi timer hai lần hoặc bỏ nhánh exception

Nếu vừa stop trong catch vừa stop trong finally, có thể ghi một lần xử lý nhiều lần. Nếu chỉ stop trên đường success, số liệu sẽ bỏ sót lỗi và thời gian trung bình có thể bị thiên lệch.

### Đếm thành công trước khi có thành công thực sự

Trong mô phỏng, điểm thành công rất đơn giản. Trong service thật, cần đối chiếu transaction, tác vụ bất đồng bộ, retry và callback sau commit. Đừng đặt increment chỉ vì “đã nhận request”.

### Tạo metric name động để tránh tag

Tên như `business.checkout.partner_123` vẫn tạo tập meter tăng theo dữ liệu. Ngân sách phải kiểm soát cả tên metric lẫn tag.

### Chỉ kiểm tra số meter, không kiểm tra tổng sự kiện

Một bộ lọc deny mọi thứ có thể làm số meter không tăng nhưng mất toàn bộ dữ liệu cần quan sát. Kiểm thử phải xác minh số đếm đúng ở các nhóm hợp lệ.

### Gom về other nhưng không quan sát tỷ lệ other

Một nhóm other quá lớn có thể che mất thay đổi đầu vào hoặc sai mapping. Theo dõi tỷ lệ và điều tra bằng log/trace phù hợp; chỉ thêm giá trị vào danh mục khi có nhu cầu nghiệp vụ và ngân sách rõ ràng.

### Coi giới hạn tag là giới hạn đầu vào HTTP

Chuẩn hóa cardinality không thay thế validation về độ dài request, định dạng hoặc quy tắc nghiệp vụ. Một chuỗi raw cực lớn vẫn có thể tốn CPU/bộ nhớ khi nhận và chuẩn hóa, dù kết quả cuối cùng chỉ là other.

## 13. Tiêu chí hoàn thành

Bài thực hành đạt yêu cầu khi có đủ bằng chứng:

1. Hai họ metric có định nghĩa rõ: counter đếm thành công, timer đếm và đo mọi kết quả đã xử lý trong service.
2. Channel chỉ xuất web/mobile/batch/other; outcome chỉ xuất success/rejected/error.
3. Chữ hoa, khoảng trắng và đầu vào lạ được chuẩn hóa đúng.
4. Kiểm thử 1.000 giá trị raw không tạo thêm meter và vẫn cộng đủ sự kiện vào other.
5. Nhánh từ chối/lỗi được timer ghi đúng một lần, không làm counter thành công tăng.
6. Filter chặn đăng ký bổ sung vượt ngân sách như đã thiết kế.
7. Bốn request thực hành tạo đúng số đếm theo bảng; thời gian không bị so sánh với một giá trị giả định.
8. Bản xuất không chứa ID, exception message hoặc channel raw ngoài danh mục.
9. Truy vấn sử dụng đúng tên xuất, đơn vị và cửa sổ đủ mẫu.
10. Khi thêm chiều tag/histogram/replica, ngân sách được tính lại và giới hạn của từng lớp được giữ rõ.

Sau khi thử nghiệm, dừng tiến trình cục bộ. Khi chuyển ý tưởng vào ứng dụng thật, bỏ cơ chế chọn scenario của bài mô phỏng và nối instrumentation vào các kết quả nghiệp vụ thực tế.

Tập tag hữu hạn là một hợp đồng dữ liệu: nó giữ metrics có thể tổng hợp, so sánh và vận hành được trong thời gian dài. Bộ ghi nhận, giới hạn registry và kiểm thử số đếm cần cùng bảo vệ hợp đồng đó.
