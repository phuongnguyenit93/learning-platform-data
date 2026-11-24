# Đăng ký MeterFilter hoặc MeterBinder dưới dạng bean

Trong ứng dụng Spring Boot có Actuator, không cần tự tạo `MeterRegistry` hoặc gọi `bindTo(...)` từ service nghiệp vụ. Spring Boot quản lý registry và tự phát hiện các bean Micrometer chuyên dụng: `MeterFilter` để quyết định meter nào được chấp nhận, đổi tên hoặc điều chỉnh; `MeterBinder` để đăng ký các meter phản ánh trạng thái của một thành phần.

Hai loại bean có vai trò khác nhau. `MeterFilter` tác động đến quá trình đăng ký meter trong registry. `MeterBinder` tạo meter và gắn chúng với dữ liệu mà ứng dụng đang quản lý. Khi khai báo đúng trong ApplicationContext, Spring Boot kết nối chúng với registry được cấu hình, giúp mã nghiệp vụ không phải biết chi tiết filter hay cách đăng ký từng meter.

## Thêm Actuator và để Spring Boot quản lý registry

Với Gradle:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
```

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Ví dụ giả định dự án dùng Spring Boot dependency management hoặc BOM tương thích để quản lý phiên bản Micrometer. Actuator tích hợp Micrometer và cấu hình registry dựa trên các registry implementation có trong classpath. Nếu ứng dụng xuất metric đến Prometheus hoặc OTLP, thêm registry tương ứng theo backend đang sử dụng.

Trong service, inject `MeterRegistry` qua constructor để ghi nhận metric. Spring Boot cung cấp registry đã được cấu hình cho ứng dụng; không tự tạo `new SimpleMeterRegistry()` trong bean vận hành, vì registry độc lập đó không nhất thiết được Actuator hoặc exporter sử dụng.

## Đăng ký MeterFilter bằng @Bean

`MeterFilter` được dùng để kiểm soát meter trước khi chúng được đăng ký. Ví dụ, từ chối meter debug và giới hạn số giá trị của tag `uri` trên metric HTTP:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsConfiguration {
    @Bean
    MeterFilter denyDebugMeters() {
        return MeterFilter.denyNameStartsWith("debug.");
    }

    @Bean
    MeterFilter limitHttpUriCardinality() {
        return MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "uri",
                100,
                MeterFilter.deny());
    }
}
```

Spring Boot phát hiện các bean có kiểu `MeterFilter` và áp dụng chúng cho các `MeterRegistry` do ứng dụng quản lý. Filter đầu tiên từ chối tên bắt đầu bằng `debug.`. Filter thứ hai giới hạn tối đa 100 giá trị khác nhau cho tag `uri` của meter `http.server.requests`; khi vượt giới hạn, meter mới có giá trị tag vượt ngưỡng bị từ chối.

Các filter trên không cần được gọi thủ công từ controller hoặc service. Chúng được áp dụng ở tầng registry, vì vậy cả meter do code nghiệp vụ đăng ký lẫn meter được binder hoặc instrumentation tự động tạo đều chịu ảnh hưởng nếu khớp điều kiện.

`MeterFilter` có thể trả về `ACCEPT`, `DENY` hoặc `NEUTRAL`. `NEUTRAL` để filter tiếp theo quyết định; `ACCEPT` hoặc `DENY` kết thúc chuỗi quyết định. Vì vậy, không đặt một filter `accept()` toàn cục trước các filter giới hạn hoặc từ chối cần thực thi. Nếu có nhiều filter phụ thuộc thứ tự, hãy cấu hình và kiểm thử thứ tự rõ ràng.

Filter cần có mặt khi registry được cấu hình, trước khi các meter được đăng ký. Thêm filter sau khi meter đã tồn tại không tự đánh giá lại hoặc xóa những meter cũ. Khi thay đổi cấu hình filter trong ứng dụng, cần kiểm tra thời điểm khởi tạo registry và các binder.

## Dùng MeterRegistryCustomizer cho cấu hình chung

Nếu cần thêm common tags hoặc cấu hình registry theo quy ước của ứng dụng, Spring Boot cung cấp `MeterRegistryCustomizer`:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RegistryCustomization {
    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonMetricTags() {
        return registry -> registry.config().commonTags(
                "application", "checkout",
                "environment", "production");
    }
}
```

Customizer không thay thế `MeterFilter` hoặc `MeterBinder`. Nó cấu hình registry, ví dụ thêm tag chung. Filter quyết định meter có được đăng ký hoặc được biến đổi ra sao; binder đăng ký meter từ các thành phần ứng dụng.

Common tags nên có tập giá trị ổn định. Nếu Prometheus đã tự gắn nhãn target như `job` hoặc `instance`, tránh thêm common tag trùng tên gây xung đột. Không thêm user ID, request ID hoặc dữ liệu nhạy cảm làm common tag.

## Đăng ký MeterBinder dưới dạng bean

`MeterBinder` gom logic đăng ký các meter liên quan đến một thành phần. Ví dụ, một queue có trạng thái độ sâu thay đổi theo số tác vụ được đưa vào và lấy ra. Tạo một bean trạng thái để sở hữu dữ liệu, sau đó tạo binder để đăng ký gauge đọc trạng thái đó.

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class QueueState {
    private final AtomicInteger depth = new AtomicInteger();

    public int depth() {
        return depth.get();
    }

    public void queued() {
        depth.incrementAndGet();
    }

    public void started() {
        depth.updateAndGet(value -> Math.max(0, value - 1));
    }
}
```

`QueueState` là nguồn dữ liệu hiện tại. `AtomicInteger` cho phép nhiều luồng đọc và cập nhật số lượng an toàn. Trong ứng dụng thực tế, nếu queue đã có API đọc độ dài chính xác, nên bind trực tiếp API đó thay vì duy trì thêm một biến đếm có thể lệch với queue thật.

Binder nhận trạng thái qua constructor và đăng ký gauge:

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;

public class QueueMetrics implements MeterBinder {
    private final QueueState queueState;

    public QueueMetrics(QueueState queueState) {
        this.queueState = queueState;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder("worker.queue.depth", queueState, QueueState::depth)
                .description("Số tác vụ đang chờ xử lý")
                .register(registry);
    }
}
```

Khai báo binder dưới dạng bean trong cấu hình:

```java
import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QueueMetricsConfiguration {
    @Bean
    MeterBinder queueMetrics(QueueState queueState) {
        return new QueueMetrics(queueState);
    }
}
```

Spring Boot phát hiện bean triển khai `MeterBinder` và gọi `bindTo(...)` cho registry được quản lý. Service nghiệp vụ chỉ cần inject `QueueState` để cập nhật trạng thái; không cần biết meter được đăng ký ở đâu.

Có thể dùng `@Component` trực tiếp trên class `QueueMetrics` thay cho phương thức `@Bean`, miễn là class nằm trong phạm vi component scan. Chọn một cách đăng ký cho mỗi binder; không vừa khai báo `@Component` vừa tạo thêm bean `QueueMetrics` từ `@Bean`, vì như vậy có thể tạo hai binder cùng đăng ký một meter.

## Kết hợp MeterFilter và MeterBinder

Filter và binder có thể cùng tồn tại trong ApplicationContext. Binder yêu cầu registry đăng ký `worker.queue.depth`; filter có thể chấp nhận hoặc từ chối meter đó theo chính sách tên hoặc tag.

Ví dụ, bổ sung filter từ chối metric thử nghiệm vào ApplicationContext đang có binder cho queue:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ObservabilityConfiguration {
    @Bean
    MeterFilter denyTemporaryMeters() {
        return MeterFilter.denyNameStartsWith("temporary.");
    }
}
```

Giữ bean `queueMetrics` đã khai báo trong `QueueMetricsConfiguration` ở phần trước; `ObservabilityConfiguration` chỉ bổ sung filter. Hai cấu hình cùng nằm trong ApplicationContext. Meter do binder đăng ký cũng đi qua quy tắc filter của registry. Nếu tên meter bị từ chối, thao tác đăng ký có thể trả về meter no-op; gọi các phương thức trên meter đó không tạo dữ liệu trong registry. Vì vậy, khi binder đã được phát hiện nhưng metric không xuất hiện, hãy kiểm tra filter trước khi kết luận binder không chạy.

## Giữ nguồn Gauge sống cùng bean

Gauge thường giữ tham chiếu yếu đến đối tượng nguồn. Trong ví dụ, binder giữ `QueueState` bằng field `final`, còn Spring quản lý vòng đời bean `QueueMetrics` và `QueueState`. Nhờ đó, nguồn trạng thái vẫn có tham chiếu mạnh khi registry đọc gauge.

Không tạo đối tượng trạng thái cục bộ trong `bindTo(...)` rồi chỉ truyền nó cho `Gauge.builder(...)`:

```java
@Override
public void bindTo(MeterRegistry registry) {
    AtomicInteger temporaryDepth = new AtomicInteger();
    Gauge.builder("worker.queue.depth", temporaryDepth, AtomicInteger::get)
            .register(registry);
}
```

Sau khi phương thức kết thúc, đối tượng có thể bị garbage collector thu hồi vì binder không giữ tham chiếu mạnh đến nó. Gauge có thể trả về `NaN` khi nguồn không còn tồn tại. Giữ field `Gauge` cũng không thay thế việc giữ đối tượng nguồn; chính `QueueState` hoặc queue thực tế cần được bean có vòng đời dài sở hữu.

## Binder phải an toàn khi có nhiều registry

Một ứng dụng có thể có nhiều registry, ví dụ Prometheus và OTLP. Spring Boot có thể áp dụng cùng một binder cho các registry được quản lý. Vì vậy, `bindTo(...)` nên chỉ đăng ký meter dựa trên trạng thái hiện có; không thực hiện nghiệp vụ hoặc tăng counter mỗi khi phương thức được gọi.

Các nguyên tắc nên giữ:

1. Tạo nguồn trạng thái trong constructor hoặc inject bean sở hữu trạng thái; không tạo đối tượng tạm trong `bindTo(...)`.
2. Dùng tên và tag ổn định để cùng một binder tạo ra meter có ý nghĩa nhất quán ở các registry.
3. Không gọi `increment()` hoặc `record(...)` trong `bindTo(...)` chỉ để khởi tạo meter; thao tác này sẽ ghi nhận một observation không phải sự kiện nghiệp vụ.
4. Không mở kết nối, tạo thread hoặc khởi chạy job nền trong `bindTo(...)`; binder có thể được gọi cho nhiều registry.
5. Giữ getter của gauge nhanh, không có side effect và an toàn khi được gọi đồng thời.

Nếu cần cấu hình khác nhau cho từng registry, dùng `MeterRegistryCustomizer` có kiểu registry cụ thể hoặc cấu hình riêng theo cơ chế được Spring Boot và registry hỗ trợ. Không giả định mọi registry xuất cùng tên metric, đơn vị hoặc histogram chỉ vì chúng dùng chung một binder.

## Kiểm thử MeterFilter và MeterBinder riêng lẻ

Có thể kiểm thử hành vi filter bằng `SimpleMeterRegistry`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MetricsFilterTest {
    @Test
    void deniesDebugMeters() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        registry.config().meterFilter(MeterFilter.denyNameStartsWith("debug."));

        Counter counter = registry.counter("debug.events");
        counter.increment();

        assertThat(counter.count()).isZero();
        assertThat(registry.find("debug.events").counter()).isNull();

        registry.close();
    }
}
```

Test xác nhận meter bị từ chối không được đăng ký và API trả về hoạt động như no-op. Có thể bổ sung test cho meter hợp lệ để xác nhận filter không chặn nhầm tên ngoài phạm vi.

Kiểm thử binder bằng một nguồn trạng thái được giữ rõ ràng:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class QueueMetricsTest {
    @Test
    void bindsGaugeToTheManagedQueueState() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        QueueState state = new QueueState();
        QueueMetrics binder = new QueueMetrics(state);

        binder.bindTo(registry);
        state.queued();

        Gauge gauge = registry.find("worker.queue.depth").gauge();
        assertThat(gauge).isNotNull();
        assertThat(gauge.value()).isEqualTo(1.0);

        state.started();
        assertThat(gauge.value()).isZero();

        registry.close();
    }
}
```

Test xác nhận gauge đọc giá trị hiện tại từ đúng đối tượng nguồn và phản ánh thay đổi sau khi bind. Không cần gọi `System.gc()` để kiểm thử weak reference vì garbage collector không bảo đảm thu hồi một đối tượng cụ thể theo yêu cầu.

## Kiểm thử Spring phát hiện bean

Unit test trên kiểm tra logic filter và binder, nhưng chưa chứng minh Spring Boot tự phát hiện bean. Có thể dùng `@SpringBootTest` để kiểm tra ApplicationContext:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class MetricsBeanDiscoveryTest {
    @Autowired
    MeterRegistry registry;

    @Test
    void queueBinderRegistersGauge() {
        assertThat(registry.find("worker.queue.depth").gauge()).isNotNull();
    }

    @Test
    void debugMeterIsDeniedByFilterBean() {
        registry.counter("debug.events").increment();
        assertThat(registry.find("debug.events").counter()).isNull();
    }
}
```

Test này giả định `QueueMetricsConfiguration`, `MetricsConfiguration` và `QueueState` nằm trong phạm vi component scan của ứng dụng kiểm thử. Nếu filter hoặc binder được khai báo trong một package ngoài phạm vi scan, hãy import cấu hình tương ứng hoặc điều chỉnh component scan. Với ứng dụng có nhiều registry, nên xác minh từng registry đích thay vì chỉ kiểm tra một bean `MeterRegistry` được inject.

## Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Filter không được áp dụng | Bean không nằm trong ApplicationContext hoặc registry được tạo ngoài Spring | Kiểm tra component scan và nguồn tạo registry |
| Meter do binder đăng ký không xuất hiện | Filter từ chối meter hoặc binder chưa được phát hiện | Kiểm tra bean binder, filter và `registry.find(...)` |
| Binder chạy nhưng gauge thành `NaN` | Đối tượng nguồn chỉ là biến cục bộ và bị GC thu hồi | Giữ nguồn trong field của bean có vòng đời dài |
| Gauge không phản ánh trạng thái mới | Binder và nghiệp vụ dùng hai đối tượng khác nhau | Inject cùng bean trạng thái vào binder và service |
| Metric bị đếm thêm khi ứng dụng khởi động | Có lời gọi `increment()` trong `bindTo(...)` | Chỉ đăng ký meter trong binder; cập nhật tại điểm nghiệp vụ |
| Cùng meter được đăng ký nhiều lần | Vừa dùng `@Component` vừa khai báo `@Bean`, hoặc nhiều binder cùng sở hữu tên/tag | Chọn một bean owner và một nơi đăng ký meter |
| Filter giới hạn không có tác dụng | Filter `ACCEPT` rộng được đánh giá trước filter giới hạn | Kiểm tra thứ tự accept filter và tránh accept toàn cục |
| Common tag bị trùng hoặc xung đột | Ứng dụng thêm tag đã có ở scrape target hoặc registry khác | Thống nhất nguồn sở hữu từng chiều label |

## Checklist triển khai

- [ ] Ứng dụng có `spring-boot-starter-actuator` và registry implementation phù hợp.
- [ ] `MeterFilter` được khai báo thành bean và có phạm vi áp dụng rõ ràng.
- [ ] Thứ tự filter không khiến `ACCEPT` rộng bỏ qua các giới hạn cần thiết.
- [ ] `MeterBinder` được đăng ký duy nhất dưới dạng `@Bean` hoặc `@Component`.
- [ ] Binder chỉ đăng ký meter trong `bindTo(...)`, không chạy nghiệp vụ hoặc ghi observation giả.
- [ ] Nguồn Gauge được giữ bằng tham chiếu mạnh trong bean có vòng đời dài.
- [ ] Binder và service dùng cùng một nguồn trạng thái.
- [ ] Tag và common tags có tập giá trị hữu hạn, không chứa dữ liệu nhạy cảm.
- [ ] Unit test xác nhận filter và binder hoạt động với registry đơn giản.
- [ ] Integration test xác nhận Spring Boot phát hiện bean và áp dụng chúng lên registry.
- [ ] Đã kiểm tra metric tại endpoint hoặc backend thực tế nếu ứng dụng có exporter.

Đăng ký `MeterFilter` và `MeterBinder` dưới dạng bean giúp Spring Boot quản lý chính sách và instrumentation tập trung. Filter kiểm soát meter được chấp nhận; binder đăng ký meter gắn với trạng thái của thành phần. Khi nguồn Gauge có vòng đời rõ ràng, filter được cấu hình trước lúc đăng ký meter và bean chỉ có một chủ sở hữu, metric sẽ ổn định hơn khi ứng dụng mở rộng hoặc sử dụng nhiều registry.
