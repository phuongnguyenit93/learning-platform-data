# Tự động cấu hình MeterRegistry từ các phụ thuộc có trên classpath

Spring Boot Actuator tự động cấu hình Micrometer để ứng dụng có thể ghi nhận và xuất metrics mà không phải tự khởi tạo từng MeterRegistry. Khi một registry implementation được đặt trên runtime classpath, Spring Boot nhận diện nó qua auto-configuration và thêm registry tương ứng vào CompositeMeterRegistry. Ứng dụng chỉ cần inject MeterRegistry để đăng ký Counter, Gauge, Timer hoặc DistributionSummary; composite sẽ chuyển các phép ghi nhận đến những registry thành viên đã được cấu hình.

Cơ chế này dựa trên dependency, điều kiện auto-configuration và các thuộc tính cấu hình. Vì vậy, có dependency trên classpath là điều kiện quan trọng nhưng chưa phải bằng chứng rằng dữ liệu đã đến backend. Registry có thể bị tắt bằng property, thiếu thông tin kết nối, hoặc được thay thế bởi cấu hình tùy chỉnh. Cần hiểu toàn bộ quá trình từ dependency đến registry bean và exporter để kiểm soát hành vi thực tế.

Bài học thuộc module OBSERVABILITY_INSTRUMENTATION_MICROMETER. Module này hướng dẫn sử dụng Micrometer để đo lường ứng dụng Java bằng counter, gauge, timer, distribution summary và nhãn có kiểm soát; tích hợp Spring Boot, xuất metrics đến hệ giám sát, kiểm soát cardinality, kiểm thử instrumentation và diễn giải số đo vận hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của Spring Boot Actuator trong auto-configuration của Micrometer.
- Nhận biết cách registry implementation trên runtime classpath được phát hiện.
- Mô tả vai trò của CompositeMeterRegistry và registry thành viên.
- Chọn dependency phù hợp với hệ thống giám sát cần xuất metrics.
- Điều khiển registry bằng các property `management.*.metrics.export`.
- Phân biệt registry backend với MeterRegistry mà component nghiệp vụ inject.
- Dùng MeterRegistryCustomizer và MeterFilter để áp dụng chính sách trước khi meter được tạo.
- Kiểm tra registry auto-configured trong Spring context và chẩn đoán khi thiếu registry.

## 1. Spring Boot tự cấu hình MeterRegistry như thế nào?

Spring Boot Actuator tích hợp Micrometer và cung cấp auto-configuration cho các registry implementation được hỗ trợ. Khi ứng dụng khởi động, Spring Boot kiểm tra classpath, các điều kiện cấu hình và bean hiện có. Những registry phù hợp sẽ được tạo và thêm vào CompositeMeterRegistry.

Có thể hình dung luồng khởi động như sau:

~~~mermaid
flowchart TD
    A["Runtime classpath"] --> B["Spring Boot auto-configuration"]
    B --> C{"Có registry implementation?"}
    C -->|"Có"| D["Tạo registry theo implementation"]
    C -->|"Không có backend khác"| E["Simple in-memory fallback"]
    D --> F["CompositeMeterRegistry"]
    E --> F
    F --> G["MeterRegistry được inject"]
    G --> H["Counter / Gauge / Timer / Summary"]
    H --> I["Các registry thành viên"]
    I --> J["Backend hoặc endpoint giám sát"]
~~~

Ví dụ, khi có dependency Prometheus registry, Spring Boot có thể tạo PrometheusMeterRegistry. Khi có thêm OTLP registry, ứng dụng có thể có cả PrometheusMeterRegistry và OtlpMeterRegistry cùng tham gia CompositeMeterRegistry.

Mã nghiệp vụ không cần biết mỗi lần ghi nhận sẽ được gửi đến bao nhiêu backend:

~~~java
@Component
public class CheckoutMetrics {

    private final Counter completed;

    public CheckoutMetrics(MeterRegistry registry) {
        this.completed = Counter.builder("checkout.completed")
                .description("Số lượt checkout hoàn tất")
                .tag("channel", "web")
                .register(registry);
    }

    public void checkoutCompleted() {
        completed.increment();
    }
}
~~~

Component inject abstraction MeterRegistry. Spring Boot cung cấp registry composite phù hợp trong context, nhờ đó instrumentation không bị gắn chặt vào một hệ thống giám sát cụ thể.

## 2. Vai trò của từng thành phần

Auto-configuration có nhiều lớp. Hiểu đúng trách nhiệm giúp chẩn đoán lỗi và tránh tạo registry trùng lặp.

| Thành phần | Vai trò |
| --- | --- |
| Spring Boot Actuator | Cung cấp dependency management và auto-configuration cho metrics |
| Micrometer core | Cung cấp API MeterRegistry, Counter, Gauge, Timer, DistributionSummary và các khái niệm meter |
| Registry implementation | Chuyển meter sang định dạng hoặc giao thức của backend |
| CompositeMeterRegistry | Phân phối phép ghi nhận đến các registry thành viên |
| MeterRegistryCustomizer | Cấu hình registry trước khi các meter được đăng ký |
| MeterFilter | Chấp nhận, từ chối, ánh xạ hoặc cấu hình meter khi đăng ký |
| Exporter hoặc endpoint | Gửi metrics đến backend hoặc cho backend scrape |

Micrometer core không tự quyết định gửi dữ liệu đến Prometheus, OTLP, Datadog hay Graphite. Registry implementation đảm nhiệm phần tích hợp đó.

Spring Boot Actuator cũng không phải một backend metrics. Nó cung cấp cơ chế cấu hình và quản lý endpoint; registry implementation mới xác định cách metrics được xuất.

## 3. Dependency trên classpath quyết định registry được phát hiện

Với ứng dụng Spring Boot dùng Gradle, dependency nền tảng thường là:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
~~~

Starter Actuator đưa Micrometer và các thành phần quản lý metrics phù hợp vào ứng dụng. Để xuất đến một hệ thống cụ thể, thêm registry implementation tương ứng.

Ví dụ với Prometheus:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Ví dụ với OTLP:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-otlp")
}
~~~

Nếu ứng dụng dùng nhiều backend, có thể thêm nhiều registry implementation:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
    runtimeOnly("io.micrometer:micrometer-registry-otlp")
}
~~~

Spring Boot sẽ nhận diện các registry được hỗ trợ trên runtime classpath và thêm chúng vào composite theo điều kiện auto-configuration.

### Vì sao có thể dùng runtimeOnly?

Khi mã nguồn chỉ inject kiểu chung `MeterRegistry` và không import lớp cụ thể của registry, implementation chỉ cần có mặt lúc chạy. Vì vậy, `runtimeOnly` thường phù hợp với Prometheus hoặc OTLP registry.

Nếu mã nguồn trực tiếp tạo `PrometheusMeterRegistry`, gọi API riêng của registry hoặc khai báo bean có kiểu cụ thể, dependency phải có trên compile classpath, chẳng hạn dùng `implementation`.

### Để Spring Boot quản lý phiên bản

Nên dùng Spring Boot dependency management hoặc BOM để chọn phiên bản Micrometer tương thích:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Không tự nâng riêng `micrometer-core` hoặc registry artifact lên phiên bản không tương thích với Spring Boot đang dùng. Registry có thể phụ thuộc API của Micrometer core và client library cụ thể; lệch phiên bản có thể gây lỗi liên kết lớp hoặc thay đổi hành vi export.

## 4. CompositeMeterRegistry phân phối dữ liệu như thế nào?

CompositeMeterRegistry là một MeterRegistry tổng hợp. Khi component đăng ký meter thông qua composite, meter có thể được đại diện và phân phối đến các registry thành viên.

Giả sử ứng dụng có:

- Prometheus registry để Prometheus scrape.
- OTLP registry để gửi metrics đến OpenTelemetry Collector.

Cả hai registry có thể nhận cùng các phép ghi nhận:

~~~mermaid
flowchart TD
    A["CheckoutMetrics"] --> B["CompositeMeterRegistry"]
    B --> C["PrometheusMeterRegistry"]
    B --> D["OtlpMeterRegistry"]
    C --> E["Prometheus scrape endpoint"]
    D --> F["OTLP Collector"]
~~~

Điều này giúp component nghiệp vụ không cần gọi riêng từng registry:

~~~java
public final class CheckoutMetrics {

    private final Counter completed;

    public CheckoutMetrics(MeterRegistry registry) {
        this.completed = registry.counter(
                "checkout.completed",
                "channel", "web"
        );
    }

    public void complete() {
        completed.increment();
    }
}
~~~

Khi composite có nhiều registry thành viên, mỗi lần increment được phân phối theo cơ chế của composite đến các thành viên. Registry dạng pull như Prometheus sẽ cung cấp dữ liệu qua endpoint scrape; registry dạng push như OTLP hoặc Datadog sẽ xuất theo chu kỳ hoặc cơ chế riêng.

### Nhiều registry không có nghĩa là nhiều lần instrument

Chỉ đăng ký một meter thông qua MeterRegistry được inject rồi để composite phân phối. Nếu component tự tạo nhiều registry và đăng ký cùng một sự kiện vào từng registry, có thể gây ghi trùng hoặc tạo thêm chi phí không cần thiết.

Cũng cần lưu ý rằng thêm một registry dependency sẽ làm tăng số đích nhận metrics. Điều này có thể tăng network traffic, chi phí ingest và số bản sao dữ liệu. Chỉ thêm registry mà hệ thống thực sự sử dụng.

## 5. SimpleMeterRegistry là fallback trong bộ nhớ

Khi không có backend registry khác được cấu hình, Spring Boot có thể sử dụng SimpleMeterRegistry làm backend in-memory fallback. Cách này hữu ích trong phát triển và kiểm thử vì metrics được lưu trong bộ nhớ của process.

Simple registry không tự gửi metrics đến Prometheus, OTLP hoặc dịch vụ giám sát bên ngoài. Dữ liệu biến mất khi process kết thúc. Khi một backend registry khác được cấu hình, Simple fallback tự tắt theo cơ chế mặc định.

Có thể tắt fallback rõ ràng:

~~~properties
management.simple.metrics.export.enabled=false
~~~

Không nhầm SimpleMeterRegistry với một exporter production. Nếu ứng dụng khởi động thành công và meter vẫn tăng nhưng backend không nhận dữ liệu, hãy kiểm tra xem registry thực tế có phải Simple in-memory hay không.

## 6. Điều khiển registry bằng application properties

Các registry thường có property riêng theo dạng:

`management.<registry>.metrics.export.*`

Ví dụ với Prometheus, có thể điều khiển trạng thái exporter:

~~~properties
management.prometheus.metrics.export.enabled=true
~~~

Với OTLP:

~~~properties
management.otlp.metrics.export.enabled=true
management.otlp.metrics.export.url=http://otel-collector:4318/v1/metrics
management.otlp.metrics.export.step=30s
~~~

Với Datadog, cần cung cấp thông tin xác thực và endpoint theo cấu hình tương ứng:

~~~properties
management.datadog.metrics.export.enabled=true
management.datadog.metrics.export.api-key=YOUR_API_KEY
~~~

Không đặt API key thật trong file cấu hình được commit vào source control. Dùng biến môi trường, secret manager hoặc cơ chế quản lý bí mật của nền tảng.

Từ Spring Boot 3, schema property của metrics export được chuyển từ dạng cũ `management.metrics.export.<registry>` sang `management.<registry>.metrics.export`. Ví dụ, cấu hình Prometheus cũ `management.metrics.export.prometheus.enabled` được thay bằng `management.prometheus.metrics.export.enabled`. Khi nâng cấp ứng dụng, hãy kiểm tra property metadata của đúng phiên bản và chuyển các khóa cũ sang namespace mới.

### Tắt một registry cụ thể

Nếu registry implementation vẫn nằm trên classpath nhưng môi trường hiện tại không cần xuất đến backend đó, có thể tắt bằng property:

~~~properties
management.datadog.metrics.export.enabled=false
~~~

Dependency vẫn có thể được resolve, nhưng auto-configuration sẽ không kích hoạt exporter tương ứng theo property.

### Tắt mặc định tất cả registry

Có thể tắt mặc định các registry:

~~~properties
management.defaults.metrics.export.enabled=false
~~~

Sau đó bật riêng registry cần thiết bằng property cụ thể:

~~~properties
management.defaults.metrics.export.enabled=false
management.prometheus.metrics.export.enabled=true
~~~

Cách này giúp môi trường có chính sách rõ ràng về backend được phép xuất metrics. Hãy kiểm tra property của registry cụ thể nếu implementation có quy tắc enablement riêng.

### Tắt global static registry

Spring Boot thường thêm các registry auto-configured vào global static composite registry của Micrometer. Có thể tắt hành vi này:

~~~properties
management.metrics.use-global-registry=false
~~~

Khi tắt global registry, các component vẫn có thể inject MeterRegistry do Spring quản lý. Property này chỉ điều khiển việc liên kết với global static registry, không có nghĩa là vô hiệu hóa toàn bộ metrics.

Việc tắt global registry thường hữu ích trong test để tránh dữ liệu từ context hoặc test trước ảnh hưởng đến test sau.

## 7. Cấu hình chung bằng MeterRegistryCustomizer

MeterRegistryCustomizer cho phép áp dụng cấu hình cho registry trước khi các meter được đăng ký. Một trường hợp thường gặp là thêm common tags cho tất cả meter.

Ví dụ:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonTags() {
        return registry -> registry.config().commonTags(
                "region", "ap-southeast-1",
                "application", "checkout-api"
        );
    }
}
~~~

Với Spring Boot 3.x, import `MeterRegistryCustomizer` thường nằm trong package `org.springframework.boot.actuate.autoconfigure.metrics`. Từ Spring Boot 4, package được tổ chức lại dưới `org.springframework.boot.micrometer.metrics.autoconfigure`. Hãy dùng package tương ứng với phiên bản dependency đang chạy.

Customizer có kiểu tổng quát `MeterRegistry` sẽ áp dụng cho các registry tương thích. Có thể chỉ cấu hình một implementation bằng cách dùng kiểu cụ thể:

~~~java
@Bean
MeterRegistryCustomizer<PrometheusMeterRegistry> prometheusNaming() {
    return registry -> registry.config()
            .commonTags("exporter", "prometheus");
}
~~~

Ví dụ trên yêu cầu Prometheus registry có trên compile classpath. Nếu không muốn mã nguồn phụ thuộc trực tiếp vào implementation, giữ kiểu tổng quát `MeterRegistry`.

### Common tags cần có cardinality thấp

Common tags được gắn lên mọi meter. Vì vậy, mỗi tag chung có thể nhân số tổ hợp series của toàn bộ registry. Chỉ dùng các giá trị ổn định như region, environment hoặc service group đã được chuẩn hóa.

Không dùng request ID, user ID, session ID hoặc raw URL làm common tag. Nếu một tag không có ích cho truy vấn, không nên thêm nó chỉ để tăng metadata.

## 8. MeterFilter bổ sung chính sách cho từng meter

MeterRegistryCustomizer cấu hình registry nói chung. MeterFilter cho phép áp dụng chính sách khi từng meter được đăng ký.

Ví dụ từ chối nhóm meter debug và giới hạn số route:

~~~java
@Bean
MeterFilter denyDebugMetrics() {
    return MeterFilter.denyNameStartsWith("internal.debug");
}

@Bean
MeterFilter limitHttpRoutes() {
    return MeterFilter.maximumAllowableTags(
            "http.server.requests",
            "uri",
            100,
            MeterFilter.deny()
    );
}
~~~

Hai cơ chế có vai trò khác nhau:

| Cơ chế | Phạm vi | Công việc |
| --- | --- | --- |
| MeterRegistryCustomizer | Registry | Common tags, naming convention và cấu hình registry |
| MeterFilter | Từng meter lúc đăng ký | Accept, deny, map và configure meter |
| Registry-specific properties | Registry implementation | Endpoint, credential, step, batch size và enablement |

Filter phải được đăng ký trước khi meter cần kiểm soát được tạo. Nó không tự sửa lại các meter đã tồn tại.

## 9. Tự tạo registry khi cần tùy biến sâu

Trong phần lớn ứng dụng Spring Boot, nên dùng registry do auto-configuration cung cấp. Tuy nhiên, có trường hợp cần constructor riêng, custom name mapper hoặc cấu hình client đặc thù.

Khi đó có thể khai báo bean registry thủ công và cung cấp các dependency cấu hình mà implementation yêu cầu. Ví dụ, Graphite cho phép cung cấp GraphiteConfig, Clock và HierarchicalNameMapper để kiểm soát cách Meter.Id được ánh xạ thành hierarchical name. Hãy dùng constructor và API của đúng phiên bản Micrometer đang có trong dự án.

Khi tự khai báo registry bean, cần kiểm tra điều kiện auto-configuration của registry đó và tránh tạo hai registry cùng loại ngoài ý muốn. Một custom registry bean có thể khiến auto-configuration tương ứng lùi lại theo điều kiện missing-bean. Hãy xác minh context thực tế thay vì giả định cả registry tự tạo và registry tự động đều cùng hoạt động.

Không tạo registry mới trong mỗi service hoặc mỗi request. Registry có vòng đời gắn với ứng dụng; nên được quản lý như một bean dùng chung.

## 10. Kiểm tra auto-configuration trong Spring context

Có thể viết một test khởi động Spring context để xác nhận MeterRegistry được tạo và meter hoạt động.

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class MeterRegistryAutoConfigurationTest {

    @Autowired
    MeterRegistry registry;

    @Test
    void registersAndUpdatesCounter() {
        Counter counter = registry.counter(
                "test.checkout.completed",
                "channel", "web"
        );

        counter.increment();

        assertThat(registry.find("test.checkout.completed")
                .tag("channel", "web")
                .counter()
                .count())
                .isEqualTo(1.0);
    }
}
~~~

Test xác nhận Spring context cung cấp MeterRegistry và registry có thể lưu phép ghi nhận. Nó chưa chứng minh backend nhận dữ liệu qua mạng.

Nếu cần xác minh một implementation cụ thể, có thể inject registry tương ứng trong test:

~~~java
@Autowired
PrometheusMeterRegistry prometheusRegistry;
~~~

Sau đó đăng ký meter vào registry và kiểm tra nội dung scrape:

~~~java
String exposition = prometheusRegistry.scrape();

assertThat(exposition)
        .contains("test_checkout_completed");
~~~

Tên xuất ra phụ thuộc NamingConvention và phiên bản Prometheus client. Hãy kiểm tra đúng tên thực tế của metric trong dự án.

### Kiểm tra dependency và điều kiện auto-configuration

Nếu registry không xuất hiện, hãy kiểm tra:

1. Registry artifact có trên runtime classpath không?
2. Dependency version có tương thích với Spring Boot và Micrometer không?
3. Property `management.<registry>.metrics.export.enabled` có đang tắt không?
4. Có custom registry bean khiến auto-configuration tương ứng back off không?
5. Có cấu hình exclude auto-configuration không?
6. Registry có cần credential hoặc endpoint bắt buộc không?
7. CompositeMeterRegistry có registry thành viên như mong đợi không?

Có thể khởi động ứng dụng với tùy chọn `--debug` để xem condition evaluation report. Report giúp nhận biết auto-configuration nào được áp dụng hoặc bị bỏ qua và điều kiện nào chưa thỏa mãn.

Trong môi trường phát triển, Actuator Conditions endpoint cũng có thể hỗ trợ kiểm tra điều kiện auto-configuration. Không expose endpoint chẩn đoán này công khai trong production nếu chưa có chính sách bảo vệ phù hợp.

## 11. Phân biệt auto-configuration registry và auto-instrumentation

Việc Spring Boot tạo MeterRegistry không có nghĩa mọi thư viện trong ứng dụng đều tự động được instrument.

Có hai hoạt động riêng:

- Registry auto-configuration tạo nơi tiếp nhận và xuất metrics.
- Instrumentation auto-configuration đăng ký meter cho các thành phần được Spring Boot hỗ trợ khi dependency và bean tương ứng hiện diện.

Ví dụ, Spring Boot có thể tự đăng ký JVM metrics, system metrics, HTTP server metrics, DataSource metrics, cache metrics hoặc executor metrics khi điều kiện phù hợp.

| Thành phần | Ví dụ meter | Điều kiện thường gặp |
| --- | --- | --- |
| JVM | `jvm.memory.used`, `jvm.gc.pause` | JVM binder được auto-configure |
| Process và system | `process.cpu.usage`, `system.cpu.usage` | Hệ điều hành và binder hỗ trợ |
| Spring MVC / WebFlux | `http.server.requests` | Web stack tương ứng có trên classpath |
| DataSource | `jdbc.connections.*` | DataSource bean được quản lý |
| Cache | `cache.*` | CacheManager và cache được cấu hình |
| Task executor | `executor.*` | ThreadPoolTaskExecutor hoặc scheduler phù hợp |

Nếu chỉ thêm Prometheus registry dependency, Spring Boot có thể xuất các meter đã tồn tại, nhưng điều đó không tự tạo instrumentation cho một thư viện không được hỗ trợ. Với thư viện riêng, cần dùng binder hoặc instrumentation Micrometer phù hợp.

## 12. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ thêm micrometer-core và chờ metrics xuất đến backend | Không có exporter cụ thể | Thêm registry implementation phù hợp |
| Thêm registry dependency nhưng property export bị tắt | Registry không được kích hoạt như mong muốn | Kiểm tra registry-specific enabled property |
| Có nhiều registry dependency nhưng nghĩ chỉ một registry hoạt động | Metrics có thể được gửi đến nhiều backend | Kiểm tra thành viên của composite |
| Dùng SimpleMeterRegistry như backend production | Dữ liệu chỉ nằm trong bộ nhớ process | Cấu hình exporter production |
| Tạo registry thủ công trong mỗi component | Phân mảnh dữ liệu và tăng tài nguyên | Inject MeterRegistry dùng chung |
| Import lớp registry nhưng khai báo dependency runtimeOnly | Compile không tìm thấy class | Dùng implementation nếu source code tham chiếu trực tiếp |
| Trộn phiên bản Micrometer và registry | Lỗi runtime hoặc API không tương thích | Dùng Spring Boot dependency management |
| Cấu hình common tags sau khi meter đã được tạo | Meter cũ không có tag mới như dự kiến | Dùng MeterRegistryCustomizer trước khi meter đăng ký |
| Nhầm MeterRegistryCustomizer với MeterFilter | Đặt chính sách sai tầng | Dùng customizer cho registry, filter cho meter |
| Nghĩ registry auto-config nghĩa là backend đã nhận dữ liệu | Bỏ sót lỗi endpoint, credential hoặc network | Kiểm tra exporter và backend độc lập |

## 13. Checklist triển khai

Trước khi đưa auto-configuration vào môi trường thật, hãy xác nhận:

1. Ứng dụng có Spring Boot Actuator và Micrometer phù hợp không?
2. Registry implementation cần dùng đã có trên runtime classpath chưa?
3. Phiên bản registry có được Spring Boot dependency management quản lý không?
4. CompositeMeterRegistry có chứa đúng các registry cần thiết không?
5. Registry không mong muốn đã được disable chưa?
6. Simple fallback có đang được dùng ngoài ý muốn không?
7. Endpoint, credential, network và export step đã được cấu hình chưa?
8. Common tags và MeterFilter đã được áp dụng trước khi meter đăng ký chưa?
9. Các component có inject MeterRegistry dùng chung không?
10. Test context và kiểm tra exporter đã xác nhận dữ liệu đi đúng đường chưa?

## Kết luận

Spring Boot Actuator tự động cấu hình CompositeMeterRegistry và thêm các registry implementation được hỗ trợ mà ứng dụng đưa lên runtime classpath. Component nghiệp vụ chỉ cần inject MeterRegistry để ghi nhận Counter, Gauge, Timer hoặc DistributionSummary; composite phân phối các phép đo đến registry thành viên.

Hãy chọn dependency theo backend cần dùng, quản lý phiên bản bằng Spring Boot dependency management và điều khiển exporter bằng property phù hợp. Dùng MeterRegistryCustomizer cho cấu hình chung, MeterFilter cho chính sách từng meter và kiểm tra context để xác nhận auto-configuration thực sự hoạt động. Registry được tạo thành công là bước đầu; cần kiểm tra tiếp endpoint, credential và dữ liệu ở backend để xác nhận metrics đã được xuất đúng.

## Tài liệu tham khảo

- [Spring Boot: Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — auto-configure CompositeMeterRegistry, registry trên classpath, Simple fallback, MeterRegistryCustomizer và các registry properties.
- [Spring Boot: Actuator Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html) — điều kiện và cách chẩn đoán auto-configuration.
- [Micrometer: Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html) — MeterRegistry, CompositeMeterRegistry và cách sử dụng registry.
- [Spring Boot: MeterRegistryCustomizer API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/micrometer/metrics/autoconfigure/MeterRegistryCustomizer.html) — API tùy biến registry trong Spring Boot hiện hành.
