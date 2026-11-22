# Bật hoặc tắt từng registry và cơ chế xuất mặc định

## 1. Chọn nơi nhận số liệu trước khi cấu hình cách xuất

Một ứng dụng có thể đo số đơn hàng, thời gian xử lý hoặc mức sử dụng bộ nhớ, rồi chuyển cùng số liệu đến nhiều hệ thống giám sát. Trong Micrometer, `MeterRegistry` quản lý các đối tượng đo như `Counter`, `Timer`, `Gauge`. Mỗi hệ thống nhận số liệu có một cách triển khai registry phù hợp; registry ghép (`CompositeMeterRegistry`) có thể phân phối phép đo đến nhiều registry con. `SimpleMeterRegistry` giữ số liệu trong bộ nhớ, không gửi đến dịch vụ bên ngoài. Đây là các khái niệm nền để hiểu vì sao tắt một nơi xuất chưa chắc đã tắt việc đo. [Nguồn: Micrometer — Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html).

Bài này tập trung vào Spring Boot 3.3.x: quyết định registry nào được tự cấu hình, quan hệ giữa cờ riêng và mặc định chung, và điều gì xảy ra khi không còn registry nhận dữ liệu. Không cần dựng máy chủ giám sát để chạy thí nghiệm cuối bài.

Ví dụ tình huống: bản chạy trên máy cá nhân chỉ cần xem số liệu trong bộ nhớ; môi trường triển khai dùng Prometheus; thư viện Datadog vẫn có trên classpath nhưng môi trường này không dùng. Mục tiêu là cấu hình rõ nơi nhận thay vì sửa mã đếm ở từng chức năng.

Ba câu hỏi nên trả lời theo thứ tự:

1. Thư viện registry cần dùng có nằm trên classpath và có được đưa vào cấu hình tự động không?
2. Cờ bật/tắt có cho phép cấu hình tự động đó chạy không?
3. Registry được tạo có thực sự nhận được phép đo, và hệ thống bên ngoài có đường lấy dữ liệu không?

## 2. Hai cấp cấu hình bật/tắt

### 2.1. Cờ riêng của từng registry

Trong Spring Boot 3.3, mẫu tên thuộc tính là `management.<system>.metrics.export.enabled`. Ví dụ:

```properties
management.datadog.metrics.export.enabled=false
management.prometheus.metrics.export.enabled=true
management.simple.metrics.export.enabled=false
```

`<system>` là tên hệ thống được Spring Boot hỗ trợ, chẳng hạn `datadog`, `prometheus`, `simple`, `otlp`, `jmx`. Không tự thay bằng tên bean hay tên lớp Java. Cờ `true` cho phép nhánh tự cấu hình được xét tiếp; các điều kiện về thư viện và bean vẫn phải đạt. Cờ `false` ngăn nhánh tự cấu hình registry tương ứng. Cách đặt tên thuộc tính được xác nhận trong [danh mục thuộc tính Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

Ví dụ tắt Datadog khi thư viện của nó vẫn được đóng gói:

```yaml
management:
  datadog:
    metrics:
      export:
        enabled: false
```

Đây là cấu hình trong `application.yml` của ứng dụng Spring Boot, không phải một chương trình Java độc lập. Những ví dụ YAML tiếp theo là các lựa chọn cấu hình riêng; không ghép bằng cách lặp lại nhiều khóa `management:` trong cùng một tài liệu YAML.

### 2.2. Mặc định chung cho những registry chưa có cờ riêng

```yaml
management:
  defaults:
    metrics:
      export:
        enabled: false
```

Cấu hình này đặt mặc định của các registry chưa khai báo cờ riêng thành tắt. Có thể mở lại từng registry cần dùng. Tài liệu Spring Boot mô tả việc bật/tắt theo hệ thống và mặc định chung tại [Metrics — Getting Started](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#getting-started).

Điểm cần phân biệt: `defaults` là giá trị dự phòng khi không có cờ riêng. Nó không phải một công tắc tổng luôn thắng mọi cờ khác.

### 2.3. Thứ tự quyết định

Với một registry `X`, Spring Boot kiểm tra cờ riêng trước. Nếu không có cờ riêng, nó dùng mặc định chung; nếu cả hai không có, điều kiện bật xuất mặc định khớp. [Nguồn: OnMetricsExportEnabledCondition, Spring Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/export/OnMetricsExportEnabledCondition.java).

| Cờ riêng của X | Cờ mặc định chung | Kết quả của điều kiện bật xuất cho X |
| --- | --- | --- |
| Không khai báo | Không khai báo | Bật |
| Không khai báo | `true` | Bật |
| Không khai báo | `false` | Tắt |
| `true` | Không khai báo | Bật |
| `true` | `true` | Bật |
| `true` | `false` | Bật |
| `false` | Không khai báo | Tắt |
| `false` | `true` | Tắt |
| `false` | `false` | Tắt |

Bảng nói về **điều kiện bật xuất**, không bảo đảm bean sẽ được tạo. Chẳng hạn `management.prometheus.metrics.export.enabled=true` không tải thêm dependency. Nhánh Prometheus còn kiểm tra lớp `PrometheusMeterRegistry`, bean `Clock` và điều kiện bean chưa được người dùng cung cấp. [Nguồn: PrometheusMetricsExportAutoConfiguration](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/export/prometheus/PrometheusMetricsExportAutoConfiguration.java).

Một ví dụ dễ hiểu sai:

```properties
management.defaults.metrics.export.enabled=false
management.prometheus.metrics.export.enabled=true
```

Cờ Prometheus riêng vẫn có hiệu lực. Muốn tắt mọi registry do Spring Boot tự cấu hình, cần kiểm tra cả các cờ riêng đang bật trong cấu hình hiệu lực, không chỉ nhìn dòng `defaults=false`.

## 3. Cấu hình theo nhu cầu thực tế

### 3.1. Chỉ cho phép Prometheus

Giả sử ứng dụng web đã có Actuator và dependency `io.micrometer:micrometer-registry-prometheus` theo bộ phiên bản do Spring Boot quản lý:

```yaml
management:
  defaults:
    metrics:
      export:
        enabled: false
  prometheus:
    metrics:
      export:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Đọc theo hai phần: `defaults=false` cùng `prometheus=true` chọn registry; `exposure.include` chọn endpoint được đưa ra HTTP. Không cần bật Simple làm bước trung gian. Cần bảo đảm không có cấu hình khác mở lại một registry thứ hai.

Prometheus thông thường chủ động lấy số liệu từ ứng dụng (pull/scrape); bật registry không có nghĩa ứng dụng tự gửi yêu cầu HTTP định kỳ đến máy chủ Prometheus. Phần cấu hình máy chủ lấy số liệu là bước riêng. [Nguồn: Spring Boot — Prometheus](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#supported-monitoring-systems.prometheus).

### 3.2. Chỉ đo trong bộ nhớ ở máy cá nhân

```yaml
management:
  defaults:
    metrics:
      export:
        enabled: false
  simple:
    metrics:
      export:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Với ứng dụng web chỉ dùng cấu hình tự động và không có registry do người dùng khai báo, đây là cách chọn Simple trong khi các registry khác mặc định tắt. Dữ liệu trong bộ nhớ mất khi tiến trình kết thúc; nó không tạo kho lưu lịch sử.

Nếu chưa thêm thư viện registry bên ngoài và cũng không thay đổi mặc định, thường không cần cấu hình `simple=true`: Simple có thể được tạo làm dự phòng. Khai báo tường minh trong ví dụ giúp thể hiện lựa chọn môi trường.

### 3.3. Tạm tắt một hệ thống nhưng giữ các hệ thống khác

```properties
management.datadog.metrics.export.enabled=false
```

Dòng này chỉ tác động nhánh Datadog; các registry còn lại tiếp tục xét điều kiện của chính chúng. Khi muốn dừng xuất đến một nhà cung cấp nhưng vẫn giữ Prometheus, không cần thay toàn bộ mặc định chung.

Ngược lại, nếu mục tiêu là chỉ cho phép một danh sách nhỏ, đặt mặc định chung thành `false` rồi mở từng hệ thống sẽ thể hiện ý định rõ hơn. Trong cả hai cách, vẫn phải xem cấu hình hiệu lực của từng môi trường.

### 3.4. Tách cấu hình môi trường và hiểu ghi đè

Ví dụ hai tệp cấu hình theo profile, lựa chọn riêng `local` hoặc `prod`:

```properties
# application-local.properties
management.defaults.metrics.export.enabled=false
management.simple.metrics.export.enabled=true
```

```properties
# application-prod.properties
management.defaults.metrics.export.enabled=false
management.prometheus.metrics.export.enabled=true
```

Trong ví dụ này, không đặt cờ `simple=true` tại tệp chung rồi kỳ vọng `defaults=false` của prod tự vô hiệu hóa nó. Hai thuộc tính có tên khác nhau, nên cờ riêng vẫn tồn tại. Nếu bật nhiều profile đồng thời, phải kiểm tra kết quả hợp nhất.

Có hai kiểu ưu tiên khác nhau: Spring giải quyết giá trị hiệu lực của **cùng một khóa** giữa tệp, biến môi trường, tham số dòng lệnh; sau đó điều kiện registry xét **hai khóa khác nhau**, riêng trước chung sau. Với SpringApplication thông thường, tham số dòng lệnh có thể ghi đè giá trị trong tệp. [Nguồn: Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Ví dụ biến môi trường của hai khóa bật/tắt:

```text
MANAGEMENT_DEFAULTS_METRICS_EXPORT_ENABLED=false
MANAGEMENT_PROMETHEUS_METRICS_EXPORT_ENABLED=true
```

Các điều kiện tạo bean được đánh giá khi khởi tạo context. Không mặc định rằng sửa tệp hoặc biến môi trường của một tiến trình đang chạy sẽ hủy hay tạo registry tức thì; với ứng dụng thông thường, áp dụng cấu hình mới bằng khởi động lại.

## 4. Simple là registry dự phòng có điều kiện

### 4.1. Điều kiện tạo Simple

Simple được xét sau các registry khác. Nó chỉ được tự tạo khi chưa có bean `MeterRegistry` và điều kiện bật xuất cho `simple` cho phép. Vì thế `management.simple.metrics.export.enabled=true` cũng không ép tạo thêm Simple nếu đã có registry khác. [Nguồn: SimpleMetricsExportAutoConfiguration](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/export/simple/SimpleMetricsExportAutoConfiguration.java).

Các tình huống dưới đây giả định có Micrometer và Actuator, không có registry tự khai báo:

| Tình huống | Kết quả cần dự đoán |
| --- | --- |
| Không có registry bên ngoài, giữ mặc định | Simple làm nơi giữ số liệu dự phòng |
| Prometheus đủ dependency và được tự cấu hình thành công | Simple lùi lại vì đã có registry khác |
| Prometheus bị tắt riêng, mặc định chung vẫn bật, không còn registry khác | Simple có thể được tạo |
| Mặc định chung tắt, không mở riêng Simple hay hệ thống nào | Simple cũng không được tự tạo |
| Mặc định chung tắt, Simple bật riêng, không có registry khác | Simple được phép làm dự phòng |
| Simple bật riêng nhưng đã có registry khác | Cờ bật không vượt qua điều kiện thiếu bean |

Dự phòng không phải cơ chế tự chuyển nơi xuất khi lỗi mạng. Nếu một registry đã được tạo rồi dịch vụ giám sát bên ngoài ngừng phản hồi, điều đó không khiến Spring Boot tự thay registry đang tồn tại bằng Simple. Điều kiện thiếu bean nói về context, không nói về khả năng kết nối máy chủ.

### 4.2. Không còn nơi nhận thì sao?

Trong cấu hình tự động chuẩn của Boot 3.3, nếu có `Clock` nhưng không có bất kỳ bean `MeterRegistry` nào, nhánh no-op tạo một `CompositeMeterRegistry` rỗng. [Nguồn: NoOpMeterRegistryConfiguration](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/NoOpMeterRegistryConfiguration.java).

Như vậy, tắt tất cả exporter tự động không nhất thiết làm `MeterRegistry` biến mất hoặc khiến việc tiêm phụ thuộc thất bại. Chương trình có thể vẫn gọi `counter.increment()`, nhưng composite không có registry con thì phép tăng không được lưu tại nơi nhận nào; thí nghiệm bên dưới quan sát giá trị `0.0`.

Không dùng sự tồn tại của bean registry hoặc việc ứng dụng khởi động thành công làm bằng chứng rằng metrics đang được lưu hay xuất. Hãy kiểm tra loại registry, registry con và giá trị đo.

Khi có nhiều registry phù hợp, Boot có thể cung cấp một composite chính để tiêm phụ thuộc; với một registry có thể tiêm duy nhất, không cần luôn có lớp bọc composite. Không nên viết mã nghiệp vụ ép kiểu mọi `MeterRegistry` thành `CompositeMeterRegistry`. [Nguồn: CompositeMeterRegistryConfiguration](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/CompositeMeterRegistryConfiguration.java).

## 5. Phân biệt bốn loại công tắc

| Cấu hình | Điều nó điều khiển | Điều không thể suy ra từ cấu hình đó |
| --- | --- | --- |
| `management.prometheus.metrics.export.enabled=false` | Nhánh tự cấu hình registry Prometheus | Các registry khác cũng bị tắt |
| `management.endpoints.web.exposure.exclude=prometheus` | Đưa endpoint Prometheus ra HTTP | Bean registry đã bị hủy |
| `management.metrics.enable.jvm=false` | Bộ lọc chấp nhận các meter thuộc nhóm tên `jvm` | Mọi exporter bị tắt |
| `management.metrics.use-global-registry=false` | Việc liên kết registry với registry tĩnh toàn cục của Micrometer | Registry trong Spring context ngừng nhận số liệu |

Endpoint còn có cờ `management.endpoint.prometheus.enabled`; endpoint phải thỏa điều kiện và được đưa ra giao thức tương ứng mới truy cập được. Một phản hồi HTTP 404 có thể liên quan exposure, đường dẫn hoặc thiếu endpoint; 401/403 có thể liên quan quyền truy cập. Không dùng riêng mã HTTP để kết luận cờ registry đang bật hay tắt. [Nguồn: Spring Boot — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

`management.metrics.enable.*` được áp dụng qua bộ lọc meter; đó là quyết định nhận nhóm phép đo theo tên. Registry vẫn có thể tồn tại để nhận các meter khác. [Nguồn: PropertiesMeterFilter](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/PropertiesMeterFilter.java).

Trong mã ứng dụng, tiêm `MeterRegistry` giúp làm rõ registry đang dùng. Nếu dùng các hàm tĩnh `Metrics.counter(...)` và đồng thời tắt liên kết global, cần kiểm tra riêng các registry đã được thêm vào `Metrics.globalRegistry`; đường ghi tĩnh có thể khác đường ghi qua bean của Spring. Thuộc tính liên kết global được mô tả trong [Spring Boot — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#getting-started).

## 6. Registry do ứng dụng tự khai báo là trách nhiệm riêng

Một bean `MeterRegistry` do mã ứng dụng tạo không tự biến mất chỉ vì `management.defaults.metrics.export.enabled=false` hay cờ riêng tương ứng bằng `false`. Những cờ đang học là điều kiện cho cấu hình tự động của Boot; chúng không phải bộ quét đóng mọi đối tượng registry tùy ý.

Nếu tự khai báo registry, cần tự quy định vòng đời bean, profile hoặc điều kiện bật/tắt phù hợp, đồng thời tránh tạo hai registry xuất cùng mục đích ngoài ý muốn. Trường hợp `MANUAL_BEAN` trong thí nghiệm cho phép quan sát trực tiếp: cả mặc định chung và cờ Simple đều tắt, nhưng bean Simple tự cung cấp vẫn đếm được.

## 7. Thí nghiệm Java: quan sát registry và giá trị đếm

### 7.1. Phạm vi của thí nghiệm

Đây là chương trình độc lập dùng `ApplicationContextRunner` để tạo và đóng một Spring context cho từng tình huống, không mở HTTP và không kết nối hệ thống giám sát. Chương trình chỉ nạp ba cấu hình tự động về metrics cơ bản, Simple và composite; nó không nạp cấu hình Prometheus.

`PROMETHEUS_FLAG_ONLY` minh họa rằng đặt một cờ không tự nạp cấu hình hoặc thêm thư viện. Không dùng kết quả này để kết luận Prometheus bị hỏng trong một ứng dụng đã có đầy đủ dependency và auto-configuration.

Dùng JDK 17 trở lên, Maven và kết nối mạng cho lần tải dependency đầu. Ví dụ cố định Spring Boot 3.3.0 để tái lập kết quả; tên thuộc tính và cơ chế đã đối chiếu theo dòng 3.3. Đây là bộ phụ thuộc phục vụ thí nghiệm, không phải yêu cầu thêm thư viện kiểm thử vào mã nghiệp vụ của mọi ứng dụng.

Tạo một thư mục thực hành riêng, đặt hai tệp `pom.xml` và `RegistrySwitchDemo.java` cạnh nhau.

### 7.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.0</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>registry-switch-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-test</artifactId>
    </dependency>
    <dependency>
      <groupId>org.assertj</groupId>
      <artifactId>assertj-core</artifactId>
    </dependency>
  </dependencies>
</project>
```

`spring-boot-test` cung cấp `ApplicationContextRunner`; AssertJ đáp ứng các kiểu mà API context runner sử dụng. Các phiên bản phụ thuộc được parent quản lý.

### 7.3. Tệp RegistrySwitchDemo.java

```java
import java.util.Locale;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.composite.CompositeMeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.actuate.autoconfigure.metrics.MetricsAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.metrics.CompositeMeterRegistryAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.metrics.export.simple.SimpleMetricsExportAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

public class RegistrySwitchDemo {
    private static ApplicationContextRunner runner() {
        return new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                MetricsAutoConfiguration.class,
                SimpleMetricsExportAutoConfiguration.class,
                CompositeMeterRegistryAutoConfiguration.class))
            .withPropertyValues("management.metrics.use-global-registry=false");
    }

    private static void show(String label, ApplicationContextRunner runner) {
        runner.run(context -> {
            if (context.getStartupFailure() != null) {
                throw new IllegalStateException(context.getStartupFailure());
            }
            MeterRegistry registry = context.getBean(MeterRegistry.class);
            Counter counter = registry.counter("demo.switch");
            counter.increment();
            int children = registry instanceof CompositeMeterRegistry composite
                ? composite.getRegistries().size() : -1;
            System.out.printf(Locale.ROOT, "%s: %s, children=%d, count=%.1f%n",
                label, registry.getClass().getSimpleName(), children, counter.count());
        });
    }

    public static void main(String[] args) {
        show("DEFAULT", runner());
        show("DEFAULTS_OFF", runner().withPropertyValues(
            "management.defaults.metrics.export.enabled=false"));
        show("SIMPLE_ON", runner().withPropertyValues(
            "management.defaults.metrics.export.enabled=false",
            "management.simple.metrics.export.enabled=true"));
        show("SIMPLE_OFF", runner().withPropertyValues(
            "management.defaults.metrics.export.enabled=true",
            "management.simple.metrics.export.enabled=false"));
        show("PROMETHEUS_FLAG_ONLY", runner().withPropertyValues(
            "management.defaults.metrics.export.enabled=false",
            "management.prometheus.metrics.export.enabled=true"));
        show("MANUAL_BEAN", runner()
            .withPropertyValues(
                "management.defaults.metrics.export.enabled=false",
                "management.simple.metrics.export.enabled=false")
            .withBean("manualRegistry", MeterRegistry.class, SimpleMeterRegistry::new));
    }
}
```

### 7.4. Biên dịch và chạy

Chạy các lệnh sau trong PowerShell, tại thư mục chứa hai tệp:

```powershell
mvn dependency:copy-dependencies -DincludeScope=runtime
New-Item -ItemType Directory -Force -Path target/classes | Out-Null
javac --release 17 -encoding UTF-8 -cp "target/dependency/*" -d target/classes RegistrySwitchDemo.java
java -cp "target/classes;target/dependency/*" RegistrySwitchDemo
```

Trên Linux/macOS, tạo thư mục bằng `mkdir -p target/classes` và dùng dấu `:` thay dấu `;` trong classpath khi chạy `java`.

Phần stdout do chương trình in ra:

```text
DEFAULT: SimpleMeterRegistry, children=-1, count=1.0
DEFAULTS_OFF: CompositeMeterRegistry, children=0, count=0.0
SIMPLE_ON: SimpleMeterRegistry, children=-1, count=1.0
SIMPLE_OFF: CompositeMeterRegistry, children=0, count=0.0
PROMETHEUS_FLAG_ONLY: CompositeMeterRegistry, children=0, count=0.0
MANUAL_BEAN: SimpleMeterRegistry, children=-1, count=1.0
```

`children=-1` là ký hiệu do ví dụ tự chọn cho registry không phải composite, không phải số lượng registry âm trong Micrometer. Mỗi tình huống tạo context mới nên bộ đếm không cộng dồn từ dòng trước.

Giải thích từng dòng:

- `DEFAULT`: không có cờ, không có registry khác, Simple được tạo và lưu phép tăng.
- `DEFAULTS_OFF`: Simple không được mở lại riêng; composite rỗng không giữ phép tăng ở registry con nào.
- `SIMPLE_ON`: cờ riêng `true` thắng mặc định chung `false`.
- `SIMPLE_OFF`: cờ riêng `false` thắng mặc định chung `true`.
- `PROMETHEUS_FLAG_ONLY`: cờ không tự đưa cấu hình Prometheus vào runner.
- `MANUAL_BEAN`: bean được cung cấp trực tiếp vẫn tồn tại dù hai cờ tự cấu hình liên quan đều tắt; Simple tự động lùi lại.

Thuộc tính `management.metrics.use-global-registry=false` trong runner giúp thí nghiệm ghi qua bean của từng context, không cần liên kết với trạng thái global tĩnh. Nó không ngăn Simple nhận phép tăng.

## 8. Chẩn đoán khi kết quả khác dự đoán

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Đã đặt `defaults=false` nhưng vẫn có registry bên ngoài | Tìm cờ riêng `true` trong cấu hình hiệu lực và các bean do ứng dụng cung cấp |
| Bật Prometheus nhưng không thấy registry | Kiểm tra dependency lúc chạy và điều kiện tự cấu hình; cờ không thay thế classpath |
| Tắt một registry nhưng vẫn xem được metrics | Xem có registry khác hoặc Simple dự phòng không; không mặc định dữ liệu cũ là bằng chứng exporter đó còn chạy |
| Có bean registry nhưng số đếm luôn bằng 0 | Kiểm tra composite rỗng, bộ lọc meter và đường ghi qua bean/global |
| Bật Simple nhưng không có bean Simple tự động | Kiểm tra đã có bean `MeterRegistry` khác khiến điều kiện dự phòng không đạt |
| Không truy cập được `/actuator/prometheus` | Kiểm tra registry, endpoint, exposure, cổng/đường dẫn và quyền truy cập theo từng lớp |
| Đổi cấu hình mà tiến trình vẫn giữ registry cũ | Kiểm tra ứng dụng đã tạo lại context/khởi động lại chưa |

Với ứng dụng Spring Boot chạy thông thường, dùng báo cáo điều kiện khi khởi động với `--debug` để xem nhánh tự cấu hình nào khớp. Nếu xem qua endpoint `conditions`, endpoint đó phải được cho phép truy cập phù hợp. Bắt đầu từ cấu hình hiệu lực và bean thực tế, rồi mới kiểm tra dữ liệu ở nơi nhận.

## 9. Tự kiểm tra

1. Chung `false`, riêng Prometheus `true`, đủ thư viện và điều kiện: Prometheus có được phép tự cấu hình không?
2. Chung `true`, riêng Datadog `false`: Datadog theo giá trị nào?
3. Chưa có registry khác, cả hai cờ của Simple và chung đều không khai báo: nơi giữ số liệu dự phòng là gì?
4. Chung `false`, không có cờ riêng bật và không có registry tự khai báo: có thể vẫn tiêm được `MeterRegistry` không? Nó có giữ được phép đếm trong thí nghiệm không?
5. Vì sao `simple=true` không bảo đảm Simple cùng tồn tại với Prometheus?
6. Vì sao tắt HTTP exposure không đủ để dừng một registry gửi dữ liệu ra dịch vụ ngoài?

Đáp án: (1) Có, cờ riêng thắng mặc định chung, các điều kiện còn lại vẫn cần đạt. (2) `false`. (3) Simple. (4) Có thể có composite rỗng nhờ cấu hình no-op; phép đếm trong thí nghiệm vẫn là `0.0`. (5) Simple còn yêu cầu chưa có bean registry khác. (6) Exposure điều khiển đường truy cập endpoint; nơi nhận và vòng đời registry là lớp cấu hình khác.
