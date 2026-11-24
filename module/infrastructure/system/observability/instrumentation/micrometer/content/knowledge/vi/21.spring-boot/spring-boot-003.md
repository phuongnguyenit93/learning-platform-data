# MeterRegistryCustomizer cho tag dùng chung và cấu hình registry

## Mục tiêu

Trong một ứng dụng Spring Boot, metrics thường được tạo từ nhiều nơi: HTTP server, JVM, database client, cache, message broker và instrumentation nghiệp vụ. Nếu mỗi nơi tự thêm tag application, environment hoặc region, cấu hình dễ bị lặp và không nhất quán.

Spring Boot cung cấp MeterRegistryCustomizer để áp dụng cấu hình chung lên MeterRegistry do ứng dụng quản lý. Customizer có thể thêm common tags, đăng ký MeterFilter hoặc điều chỉnh cấu hình registry trước khi các meter được sử dụng.

Sau bài này, bạn có thể:

- Tạo bean MeterRegistryCustomizer để thêm tag dùng chung.
- Phân biệt common tags với tag riêng của từng meter và resource attributes của OTLP.
- Chọn giá trị tag ổn định, có cardinality thấp.
- Dùng customizer để cấu hình MeterFilter và thống kê phân bố.
- Chọn customizer chung cho mọi registry hoặc customizer theo loại registry.
- Kiểm thử cấu hình bằng SimpleMeterRegistry và Spring application context.

## MeterRegistryCustomizer hoạt động ở đâu?

MeterRegistry là nơi đăng ký và quản lý các meter như Counter, Gauge, Timer và DistributionSummary. Spring Boot auto-configuration tạo registry dựa trên registry implementation có trong classpath và cấu hình ứng dụng.

MeterRegistryCustomizer là một callback được Spring Boot áp dụng cho registry. Interface có một phương thức customize(registry). Khi khai báo bean, Spring Boot gọi customizer trong quá trình cấu hình registry, trước khi các binder và instrumentation sử dụng registry đó.

Sơ đồ khái quát:

~~~text
Spring Application Context
        |
        v
Auto-configured MeterRegistry
        |
        v
MeterRegistryCustomizer beans
        |
        +--> common tags
        |
        +--> MeterFilter
        |
        +--> distribution configuration
        |
        v
MeterBinder và instrumentation đăng ký meter
        |
        v
Registry export metrics đến backend
~~~

Điểm quan trọng là customizer cấu hình registry, còn meter được đăng ký sau đó sẽ nhận cấu hình phù hợp. Đây là nơi tập trung các chính sách áp dụng cho nhiều meter, thay vì lặp lại cùng một tag hoặc filter trong từng component.

## Thêm common tags bằng MeterRegistryCustomizer

### Chọn tag dùng chung

Common tags là những chiều có ý nghĩa với hầu hết hoặc toàn bộ metrics của một registry. Ví dụ:

| Tag | Ví dụ | Đặc điểm |
|---|---|---|
| application | orders-api | Tên ứng dụng ổn định |
| environment | production | Tập giá trị nhỏ như local, staging, production |
| region | ap-southeast-1 | Khu vực triển khai có tập giá trị giới hạn |
| cluster | payments-prod | Tên cluster được quản lý |

Các tag này giúp lọc hoặc nhóm metrics theo môi trường triển khai. Chúng không nên chứa dữ liệu thay đổi theo từng request như request ID, trace ID, user ID, session ID, email, timestamp hoặc URL đầy đủ. Những giá trị đó làm số chuỗi time series tăng nhanh và có thể đưa dữ liệu nhạy cảm vào hệ thống metrics.

### Khai báo customizer trong Spring Boot

Ví dụ cấu hình ba common tags trong application properties:

~~~yaml
spring:
  application:
    name: orders-api

app:
  metrics:
    environment: production
    region: ap-southeast-1
~~~

Bean customizer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.core.env.Environment;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonTags(Environment environment) {
        String application = environment.getProperty(
                "spring.application.name", "application");
        String deploymentEnvironment = environment.getProperty(
                "app.metrics.environment", "local");
        String region = environment.getProperty(
                "app.metrics.region", "unknown");

        return registry -> registry.config().commonTags(
                "application", application,
                "environment", deploymentEnvironment,
                "region", region
        );
    }
}
~~~

Customizer này áp dụng cùng bộ tag cho các meter trên những registry mà Spring Boot quản lý. Ví dụ, một Counter nghiệp vụ được đăng ký sau đó:

~~~java
Counter.builder("business.orders.created")
        .tag("channel", "web")
        .register(registry);
~~~

sẽ có cả ba common tags và tag riêng channel=web. Không cần lặp application, environment và region ở mọi builder.

### Đặt common tags trước khi đăng ký meter

Common tags thuộc cấu hình registry. Hãy áp dụng chúng trong customizer trước khi các meter được tạo. Không nên đợi đến khi ứng dụng đã đăng ký hàng loạt meter rồi mới thay đổi common tags và kỳ vọng những meter cũ được cập nhật ngược.

Trong Spring Boot, customizer bean là extension point phù hợp cho cấu hình này vì Boot gọi chúng trong quá trình chuẩn bị registry. Với registry được tự tạo bên ngoài Spring hoặc đăng ký thủ công, ứng dụng phải tự gọi customizer hoặc áp dụng cùng cấu hình trước khi đăng ký meter.

## Common tags, meter tags và OTLP resource attributes

Ba loại thông tin này có mục đích khác nhau:

| Loại | Gắn ở đâu | Ví dụ | Dùng để |
|---|---|---|---|
| Common tags | Trên mọi meter của registry | environment=production | Lọc hoặc nhóm các metric trong registry |
| Meter-specific tags | Trên một meter cụ thể | method=GET, status=2xx | Phân tích dimension của metric đó |
| Resource attributes | Trên resource của telemetry | service.name=orders-api | Nhận diện service/process tạo telemetry |

Không nên coi common tag application là thay thế cho resource attribute service.name của OTLP. Một backend có thể dùng resource attributes để tách service và dùng metric attributes để phân tích từng meter. Khi xuất OTLP, hãy cấu hình resource attributes qua cấu hình exporter tương ứng của Spring Boot/Micrometer.

Ví dụ, environment và region có thể vừa cần xuất dưới dạng resource attributes vừa cần xuất thành metric tags tùy mô hình truy vấn. Nếu dùng cả hai, hãy thống nhất tên và giá trị để tránh hai nguồn metadata mâu thuẫn.

## Kết hợp common tags với MeterFilter

MeterRegistryCustomizer không chỉ dùng để thêm tag. Nó có thể cấu hình MeterFilter nhằm kiểm soát meter trước khi được đăng ký.

Ví dụ, cùng một cấu hình có thể thêm common tags và giới hạn số giá trị URI của HTTP metrics:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> metricsRegistryCustomizer() {
        return registry -> {
            registry.config().commonTags(
                    "application", "orders-api",
                    "environment", "production"
            );

            registry.config().meterFilter(
                    MeterFilter.maximumAllowableTags(
                            "http.server.requests",
                            "uri",
                            100,
                            MeterFilter.deny()
                    )
            );
        };
    }
}
~~~

Filter giới hạn tối đa 100 giá trị tag uri cho meter có tên bắt đầu bằng http.server.requests. Khi xuất hiện giá trị mới vượt giới hạn, meter mới bị từ chối. Filter không tự chuẩn hóa URI lạ thành một nhóm fallback; route template vẫn cần được chuẩn hóa ở instrumentation.

Hãy cấu hình filter trước khi meter đầu tiên được đăng ký. Cũng cần chú ý thứ tự giữa nhiều MeterFilter: filter trả ACCEPT có thể kết thúc sớm vòng xét accept và khiến filter accept phía sau không được gọi. Đặt các điều kiện DENY và giới hạn cardinality trước filter cho phép rộng.

## Cấu hình histogram hoặc percentile theo loại meter

Có thể dùng MeterRegistryCustomizer để đăng ký một MeterFilter tùy chỉnh, rồi cấu hình phân bố cho những meter cần histogram. Ví dụ:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.distribution.DistributionStatisticConfig;

MeterFilter httpLatencyHistogram = new MeterFilter() {
    @Override
    public DistributionStatisticConfig configure(
            Meter.Id id,
            DistributionStatisticConfig config) {
        if (id.getName().equals("http.server.requests")) {
            return DistributionStatisticConfig.builder()
                    .percentilesHistogram(true)
                    .build()
                    .merge(config);
        }

        return config;
    }
};
~~~

Đăng ký filter trong customizer:

~~~java
@Bean
MeterRegistryCustomizer<MeterRegistry> httpMetricsConfiguration() {
    return registry -> registry.config()
            .meterFilter(httpLatencyHistogram);
}
~~~

Đây là cấu hình minh họa. Trong ứng dụng thực tế, chỉ bật histogram cho metric mà dashboard hoặc alert cần phân tích phân vị. Histogram tạo thêm chuỗi bucket và làm tăng chi phí lưu trữ, vì vậy cần cân nhắc số route, method, status và các tag kết hợp.

Nếu muốn đặt cấu hình phân bố qua application properties, Spring Boot cũng cung cấp nhóm cấu hình management.metrics.distribution.* cho percentile histogram, percentiles, SLA và giới hạn thống kê. Hãy chọn properties cho chính sách cấu hình tĩnh; dùng customizer/filter khi cần logic theo tên meter hoặc loại registry.

## Customizer áp dụng cho mọi registry hay một registry cụ thể?

### Customizer chung

Khai báo generic là MeterRegistry:

~~~java
@Bean
MeterRegistryCustomizer<MeterRegistry> commonTags() {
    return registry -> registry.config()
            .commonTags("environment", "production");
}
~~~

Cách này phù hợp với common tags, filter và chính sách cần áp dụng đồng nhất cho mọi registry mà Spring Boot quản lý.

### Customizer theo loại registry

Nếu cấu hình chỉ dành cho một implementation, dùng generic type cụ thể:

~~~java
@Bean
MeterRegistryCustomizer<PrometheusMeterRegistry> prometheusNamingPolicy() {
    return registry -> {
        // Cấu hình chỉ dành cho PrometheusMeterRegistry.
    };
}
~~~

Ví dụ này yêu cầu dependency Prometheus registry và import PrometheusMeterRegistry tương ứng. Không dùng kiểu cụ thể nếu ứng dụng cần hỗ trợ nhiều backend và chính sách phải giống nhau.

### Nhiều customizer và thứ tự

Spring Boot có thể áp dụng nhiều MeterRegistryCustomizer bean. Khi thứ tự quan trọng, khai báo @Order trên bean hoặc phương thức tạo bean để thể hiện thứ tự mong muốn. Ví dụ, common tags và filter giới hạn nên được cấu hình trước các customizer có quyết định ACCEPT rộng.

Để dễ bảo trì, nên gom các chính sách có liên quan vào một cấu hình rõ ràng hoặc tách thành các customizer có tên và thứ tự được kiểm thử. Tránh tạo nhiều customizer cùng thay đổi một tag key hoặc cùng sửa cấu hình histogram mà không có quy ước.

## Properties hay MeterRegistryCustomizer?

Spring Boot cung cấp properties cho nhiều cấu hình metrics phổ biến:

~~~yaml
management:
  metrics:
    tags:
      environment: production
      region: ap-southeast-1
    distribution:
      percentiles-histogram:
        http.server.requests: true
~~~

Properties thường phù hợp khi cấu hình có thể biểu diễn trực tiếp trong YAML và thay đổi theo profile hoặc môi trường triển khai. MeterRegistryCustomizer phù hợp khi cần:

- Dùng giá trị từ bean hoặc logic Java.
- Áp dụng cấu hình theo loại MeterRegistry.
- Kết hợp common tags với MeterFilter.
- Viết quy tắc configure theo tên meter.
- Tái sử dụng một chính sách cấu hình trong nhiều ứng dụng.

Không cấu hình cùng một chính sách ở nhiều nơi nếu không cần thiết. Nếu common tag environment được khai báo cả trong management.metrics.tags và customizer với giá trị khác nhau, kết quả có thể chứa tag trùng key hoặc gây lỗi khi tạo meter. Hãy chọn một nguồn cấu hình có thẩm quyền.

## Kiểm soát cardinality của common tags

Common tags được gắn vào mọi meter, vì vậy mỗi giá trị mới của common tag có thể nhân số chuỗi metrics trên toàn registry.

Giả sử ứng dụng có:

- 30 tên meter.
- 4 environment.
- 3 region.
- 5 giá trị method cho một số meter HTTP.

Chỉ riêng các chiều common tag đã có thể nhân số chuỗi theo 4 x 3 = 12 cho mỗi meter. Các tag riêng tiếp tục làm số tổ hợp tăng thêm.

Chọn common tag theo các nguyên tắc:

1. Giá trị có tập hữu hạn và được quản lý.
2. Giá trị ổn định trong vòng đời một instance.
3. Cùng một ý nghĩa có cùng key và format ở mọi meter.
4. Không chứa dữ liệu cá nhân hoặc ID của request.
5. Không tạo tag chỉ để phân biệt từng pod nếu backend đã có resource attribute hoặc target label tương ứng.

Không nên dùng hostname ngẫu nhiên, container ID hoặc deployment timestamp làm common tag nếu chúng khiến số series tăng theo mỗi lần rollout. Nếu cần nhận diện instance, ưu tiên resource attribute hoặc metadata scrape do backend quản lý.

## Kiểm thử MeterRegistryCustomizer

### Unit test với SimpleMeterRegistry

Có thể gọi customizer trực tiếp với SimpleMeterRegistry để xác minh common tags được áp dụng:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;

import static org.assertj.core.api.Assertions.assertThat;

class MetricsConfigurationTest {
    @Test
    void addsCommonTagsToRegisteredMeters() {
        MeterRegistryCustomizer<MeterRegistry> customizer =
                registry -> registry.config().commonTags(
                        "application", "orders-api",
                        "environment", "test"
                );

        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            customizer.customize(registry);

            Counter counter = Counter.builder("business.orders.created")
                    .tag("channel", "web")
                    .register(registry);

            assertThat(counter.getId().getTag("application"))
                    .isEqualTo("orders-api");
            assertThat(counter.getId().getTag("environment"))
                    .isEqualTo("test");
            assertThat(counter.getId().getTag("channel"))
                    .isEqualTo("web");
        } finally {
            registry.close();
        }
    }
}
~~~

Test xác minh common tags và tag riêng cùng xuất hiện trên Meter.Id sau khi đăng ký.

### Kiểm thử filter trong customizer

Khi customizer cài MeterFilter, hãy đăng ký meter sau khi gọi customize(), rồi xác minh:

- Meter trong nhóm được phép có thể được đăng ký.
- Meter thuộc nhóm bị từ chối không xuất hiện.
- Meter vượt maximum allowable tags bị từ chối.
- Common tags vẫn được gắn vào các meter được đăng ký.

### Kiểm thử Spring application context

Một test với SpringBootTest có thể inject MeterRegistry do Spring Boot auto-configure, tạo một meter và kiểm tra các tag chung. Cách này xác minh customizer bean thực sự được Spring phát hiện và áp dụng trong context, thay vì chỉ kiểm tra lambda độc lập.

Nếu ứng dụng có nhiều registry, hãy kiểm tra từng registry mong đợi. Với customizer dùng generic type cụ thể, xác nhận nó chỉ tác động đến registry tương ứng.

## Những lỗi thường gặp

**Thêm common tag trong mọi meter builder.** Cách này lặp cấu hình và dễ thiếu tag ở một component. Hãy dùng customizer cho chiều dùng chung.

**Dùng tag có cardinality cao.** Request ID, user ID, session ID và timestamp không phù hợp làm common tags.

**Nhầm common tags với resource attributes.** Common tags là meter dimensions; resource attributes nhận diện nguồn telemetry. Cấu hình OTLP resource riêng khi cần.

**Đăng ký customizer quá muộn.** Meter đã tạo trước khi common tags hoặc filter được cấu hình có thể không nhận chính sách như mong đợi.

**Đặt ACCEPT rộng trước filter giới hạn.** Quyết định ACCEPT sớm có thể ngăn filter accept phía sau được gọi. Đặt deny và cardinality guard trước allow rộng.

**Cấu hình cùng tag ở nhiều nơi.** Tránh khai báo trùng key trong properties, customizer và builder của từng meter.

**Bật histogram cho mọi meter.** Histogram làm tăng số chuỗi. Chỉ bật cho các metric có nhu cầu phân tích phân vị rõ ràng.

**Giả định customizer tự áp dụng cho registry tự tạo bên ngoài Spring.** Nếu registry được tạo thủ công ngoài cơ chế auto-configuration, hãy tự gọi customizer hoặc cấu hình registry trước khi đăng ký meter.

## Checklist triển khai

1. Chọn các common tags có ý nghĩa và cardinality thấp.
2. Lấy giá trị từ application properties hoặc cấu hình triển khai có thẩm quyền.
3. Khai báo MeterRegistryCustomizer<MeterRegistry> cho chính sách chung.
4. Dùng generic type cụ thể chỉ khi cấu hình dành riêng cho một registry.
5. Cấu hình common tags và MeterFilter trước khi meter đầu tiên được đăng ký.
6. Đặt deny và giới hạn cardinality trước filter ACCEPT rộng.
7. Phân biệt meter tags với OTLP resource attributes.
8. Chọn properties cho cấu hình tĩnh và customizer cho logic Java hoặc cấu hình theo registry.
9. Kiểm tra xung đột key giữa common tags và tag riêng.
10. Kiểm thử Meter.Id, filter decision và Spring application context.
11. Xác minh endpoint export có các tag và histogram như mong đợi.

## Kết luận

MeterRegistryCustomizer là extension point của Spring Boot để cấu hình MeterRegistry tập trung. Dùng commonTags() cho những chiều ổn định như application, environment và region; dùng MeterFilter để giới hạn hoặc biến đổi meter; và dùng configure() khi cần điều chỉnh histogram theo loại meter. Hãy giữ common tags có cardinality thấp, phân biệt chúng với resource attributes của OTLP và áp dụng customizer trước khi meter được đăng ký. Kiểm thử cả Meter.Id lẫn registry được Spring auto-configure giúp bảo đảm chính sách chung được áp dụng nhất quán.

## Tài liệu tham khảo

- [Spring Boot - Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): MeterRegistryCustomizer, common tags và cấu hình metrics qua properties.
- [Micrometer - MeterRegistry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html): registry, common tags và cách quản lý meter.
- [Micrometer - Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): accept, map, configure và giới hạn cardinality.
- [Spring Boot - Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): các thuộc tính management.metrics.tags và management.metrics.distribution.
