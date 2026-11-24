# Kiểm tra điều kiện của thư viện hoặc framework để biết phép đo thực sự được tạo

Micrometer và Spring Boot có thể tự đăng ký nhiều phép đo từ JVM, HTTP server, datasource, cache, executor và các thư viện tích hợp. Tuy nhiên, việc thêm một dependency hoặc bật Actuator không có nghĩa mọi meter đều xuất hiện. Mỗi nhóm built-in metrics thường chỉ được tạo khi các điều kiện về classpath, bean, cấu hình và loại ứng dụng được đáp ứng.

Muốn biết một phép đo có thực sự được tạo, cần kiểm tra cả điều kiện kích hoạt lẫn registry đang chạy. Condition report giải thích vì sao một auto-configuration hoặc binder được bật/tắt; MeterRegistry và endpoint Actuator cho biết meter có được đăng ký thực tế hay không. Hai loại bằng chứng này bổ sung cho nhau.

## 1. Built-in metrics được tạo qua những lớp nào?

Một phép đo có sẵn thường đi qua chuỗi sau:

~~~mermaid
flowchart TD
    A["Dependency có trên classpath"] --> B{"Auto-configuration phù hợp?"}
    B -- "Không" --> X["Không tạo binder / instrumentation"]
    B -- "Có" --> C{"Bean và property cần thiết có mặt?"}
    C -- "Không" --> X
    C -- "Có" --> D["Binder hoặc instrumentation được cấu hình"]
    D --> E["Meter được đăng ký vào MeterRegistry"]
    E --> F{"Có dữ liệu hoặc thao tác được đo?"}
    F -- "Chưa" --> G["Meter có thể chưa xuất hiện hoặc chưa có mẫu"]
    F -- "Có" --> H["Actuator / exporter đọc và xuất metric"]
~~~

Có thể chia thành bốn câu hỏi:

1. **Có đúng thư viện không?** Class cần thiết và integration module phải nằm trên runtime classpath.
2. **Framework có kích hoạt integration không?** Auto-configuration phải thỏa các điều kiện class, bean, property và application type.
3. **Meter có được đăng ký không?** Binder hoặc instrumentation phải chạy với MeterRegistry thực tế.
4. **Có dữ liệu được ghi nhận và endpoint được truy cập không?** Một số meter chỉ xuất hiện sau khi thao tác tương ứng xảy ra; endpoint cũng phải được expose và cho phép truy cập.

Không nên gộp bốn bước thành một kết luận duy nhất. Ví dụ, một dependency có thể đã có nhưng auto-configuration không match vì thiếu bean. Ngược lại, binder có thể đã được đăng ký nhưng HTTP request chưa từng chạy nên meter request chưa xuất hiện.

## 2. Điều kiện classpath: thư viện có thực sự hiện diện?

Nhiều integration được bảo vệ bằng điều kiện tương tự ConditionalOnClass. Spring Boot chỉ áp dụng cấu hình khi class được yêu cầu có thể nạp từ runtime classpath.

Ví dụ:

- JVM metrics cần Micrometer binder và các API JVM phù hợp.
- HTTP server metrics cần web server stack được hỗ trợ và instrumentation tương ứng.
- Datasource metrics cần datasource và metadata hoặc integration cho pool được sử dụng.
- Cache metrics cần cache abstraction/provider hoặc cache manager mà binder hỗ trợ.
- Metrics cho thư viện bên thứ ba cần module Micrometer integration tương ứng nếu module đó được tách riêng.

Có dependency trong file build chưa chắc đã có class ở runtime. Dependency có thể nằm ở scope test, bị exclude, bị conflict version hoặc không được đóng gói vào artifact triển khai.

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
./mvnw dependency:tree -Dincludes=io.micrometer,org.springframework.boot
~~~

Hãy kiểm tra runtime classpath của đúng module chạy ứng dụng, không chỉ module chứa mã instrumentation. Nếu class có trong compile classpath nhưng không có trong runtime classpath, auto-configuration có thể không được kích hoạt khi khởi động.

## 3. Điều kiện bean: framework có đối tượng để đo không?

Một số auto-configuration chỉ tạo binder khi một bean phù hợp đã tồn tại. Đây là cách Spring Boot tránh tạo metrics cho thành phần mà ứng dụng không sử dụng.

Ví dụ:

| Thành phần cần đo | Điều kiện thường gặp |
| --- | --- |
| Datasource | Có bean DataSource và pool/provider được hỗ trợ |
| Cache | Có CacheManager hoặc cache implementation phù hợp |
| HTTP server | Ứng dụng chạy web stack được hỗ trợ |
| Executor | Có executor bean thuộc loại có thể instrument |
| Client HTTP | Có client hoặc builder được framework instrument |

Tên bean và loại bean quan trọng. Một thư viện có thể được thêm vào classpath nhưng ứng dụng không tạo đối tượng tương ứng, do đó binder không có nguồn trạng thái để đọc.

Các điều kiện bean phổ biến gồm:

- ConditionalOnBean: chỉ cấu hình khi bean yêu cầu đã có.
- ConditionalOnMissingBean: chỉ tạo bean mặc định nếu ứng dụng chưa cung cấp bean thay thế.
- ConditionalOnSingleCandidate: chỉ chọn khi có một ứng viên phù hợp hoặc một ứng viên primary.

Ví dụ minh họa một auto-configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(DataSource.class)
class ExampleDataSourceMetricsConfiguration {

    @Bean
    @ConditionalOnBean(DataSource.class)
    @ConditionalOnMissingBean(DataSourcePoolMetrics.class)
    DataSourcePoolMetrics dataSourcePoolMetrics(DataSource dataSource) {
        return new DataSourcePoolMetrics(dataSource);
    }
}
~~~

Đây là ví dụ minh họa cách điều kiện được kết hợp; tên class và cách triển khai thực tế phụ thuộc Spring Boot/Micrometer version. Khi điều tra một binder cụ thể, hãy đọc condition report của chính auto-configuration đang chạy.

### Bean thay thế có thể làm cấu hình mặc định không match

Nếu ứng dụng tự khai báo bean thay thế, điều kiện ConditionalOnMissingBean có thể khiến bean mặc định không được tạo. Điều này thường là hành vi có chủ ý để tránh hai thành phần cùng quản lý một nguồn trạng thái.

Ví dụ, ứng dụng tự cung cấp một MeterBinder hoặc một datasource metrics binder có thể khiến auto-configuration mặc định lùi lại. Khi đó cần xác định bean nào đang sở hữu việc đăng ký meter và nó có thực sự đăng ký đúng các phép đo mong muốn không.

## 4. Điều kiện property: cấu hình có cho phép instrumentation không?

Auto-configuration có thể phụ thuộc vào property. Các điều kiện thường gặp:

- ConditionalOnProperty: chỉ bật khi property có giá trị phù hợp.
- Property có thể bật/tắt một nhóm metrics hoặc exporter.
- Cấu hình quản lý có thể giới hạn việc export, distribution hoặc một loại instrumentation.

Ví dụ về một cấu hình tùy chỉnh:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "app.metrics.queue",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
class QueueMetricsConfiguration {
    // Khai báo binder cho queue khi app.metrics.queue.enabled=true.
}
~~~

Property ví dụ này thuộc ứng dụng, không phải property chuẩn của Spring Boot. Khi kiểm tra built-in metrics, phải tra đúng property của phiên bản Spring Boot và integration đang dùng; không đoán tên property từ tên meter.

Một điểm cần phân biệt:

- **Không tạo binder:** điều kiện auto-configuration không match, nên instrumentation có thể chưa được đăng ký.
- **Tạo binder nhưng lọc meter:** binder đã chạy, nhưng MeterFilter hoặc cấu hình enable/deny có thể chặn meter.
- **Không export:** meter tồn tại trong registry nhưng registry/exporter hoặc endpoint chưa được cấu hình để đưa dữ liệu ra ngoài.

Ba trạng thái này có biểu hiện khác nhau và cần được kiểm tra riêng.

## 5. Điều kiện application type và web stack

Không phải mọi ứng dụng Spring Boot đều có cùng tập metrics. Một ứng dụng command-line, servlet web application và reactive web application có các thành phần runtime khác nhau.

Ví dụ:

- HTTP server metrics chỉ có ý nghĩa khi có server nhận request.
- Servlet instrumentation và reactive instrumentation có thể dùng integration khác nhau.
- Client metrics phụ thuộc loại client và cách nó được tạo.
- Một ứng dụng không có datasource thì không có connection pool metrics.

Nếu ứng dụng dùng WebClient hoặc RestTemplate, việc tạo client theo builder do Spring Boot quản lý thường là yếu tố quan trọng để instrumentation được áp dụng. Tự tạo client bằng constructor hoặc factory riêng có thể bỏ qua customizer mà framework cung cấp.

Ví dụ minh họa:

~~~java
@Configuration
class ClientConfiguration {

    @Bean
    RestTemplate partnerRestTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
~~~

Khi dùng builder được Spring Boot tùy biến, client có thể nhận observation/customizer tích hợp sẵn. Nếu tạo RestTemplate độc lập, không nên giả định nó tự có cùng instrumentation. Cần xác minh cấu hình client thực tế và meter sau khi gửi request.

## 6. Các nhóm built-in metrics thường gặp và điều kiện tạo

Tên meter và điều kiện chính xác có thể thay đổi theo Spring Boot, Micrometer, web stack và thư viện pool. Bảng dưới đây là định hướng để biết cần kiểm tra thành phần nào.

| Nhóm | Ví dụ tên meter thường gặp | Điều kiện cần kiểm tra |
| --- | --- | --- |
| JVM | jvm.memory.used, jvm.threads.live, jvm.gc.pause | JVM binder được bind vào registry |
| Process/system | process.uptime, system.cpu.usage | Binder hệ thống tương ứng và quyền đọc thông tin runtime |
| HTTP server | http.server.requests | Web server được hỗ trợ, observation/metrics auto-configuration và request đi qua server |
| Datasource | jdbc.connections.active, jdbc.connections.idle | DataSource bean, pool metadata và binder phù hợp |
| Cache | cache.gets, cache.puts | CacheManager/provider và cache được instrument |
| Executor | executor.active, executor.queued, executor.pool.size | Executor bean thuộc loại hỗ trợ và được bind |
| HTTP client | http.client.requests | Client được tạo qua integration/builder được instrument |

Đừng coi bảng này là danh sách meter luôn xuất hiện ở mọi dự án. Một meter có thể không tồn tại vì ứng dụng không dùng thành phần đó, vì binder không được cấu hình, hoặc vì tên/semantics đã thay đổi giữa các phiên bản.

## 7. JVM metrics: kiểm tra binder và registry

JVM metrics thường được cung cấp bởi binder của Micrometer. Các meter phổ biến gồm:

- jvm.memory.used và jvm.memory.max: bộ nhớ theo memory area.
- jvm.threads.live: số thread hiện tại.
- jvm.classes.loaded: số class đã nạp.
- jvm.gc.pause: thời gian hoặc sự kiện liên quan đến garbage collection.

Nếu không thấy nhóm JVM:

1. Kiểm tra Micrometer core có trên runtime classpath.
2. Kiểm tra JVM binder được Spring Boot/Micrometer bind vào registry nào.
3. Kiểm tra có MeterFilter chặn prefix jvm hay không.
4. Kiểm tra đang xem đúng application context và đúng MeterRegistry.
5. Tra cứu tên canonical qua Actuator Metrics.

JVM binder không cần request HTTP để ghi nhận các giá trị trạng thái cơ bản, nhưng endpoint export vẫn phải truy cập được. Một số phép đo chỉ cập nhật khi JVM có hoạt động tương ứng, ví dụ garbage collection.

## 8. HTTP server metrics: cần request đi qua server

HTTP server metrics thường được ghi nhận khi request đi qua instrumentation của server. Việc ứng dụng khởi động thành công và endpoint metrics đã được expose chưa đủ để bảo đảm meter request xuất hiện.

Quy trình xác minh:

1. Xác nhận ứng dụng là web application và dùng server được hỗ trợ.
2. Xác nhận Actuator/Micrometer observation integration có mặt.
3. Gửi một request đến endpoint ứng dụng.
4. Kiểm tra meter http.server.requests trong Actuator Metrics.
5. Nếu dùng Prometheus, kiểm tra tên đã chuẩn hóa trong exposition.

Ví dụ:

~~~bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/actuator/metrics/http.server.requests
~~~

Tên meter có thể chỉ xuất hiện sau request đầu tiên. Nếu request được gửi qua proxy, gateway hoặc một đường xử lý không đi qua server instrumentation mong đợi, nó có thể không được tính trong meter đó.

Tags như method, status, outcome và uri giúp phân tích request. URI thường được chuẩn hóa thành route template; tránh tag bằng URL thô có ID động vì sẽ tạo cardinality rất cao.

## 9. Datasource metrics: kiểm tra loại connection pool

Datasource metrics thường phụ thuộc DataSource và pool implementation. Spring Boot/Micrometer có thể lấy metadata từ các pool được hỗ trợ để tạo các phép đo như active, idle, max và min connections.

Điều cần xác minh:

- DataSource có thực sự được tạo thành bean trong ApplicationContext không?
- DataSource đang dùng HikariCP, Tomcat JDBC Pool, DBCP2 hay pool khác?
- Module hỗ trợ pool tương ứng có trên runtime classpath không?
- Pool có cung cấp metadata/getter mà binder cần không?
- MeterFilter có chặn các meter jdbc hoặc tên prefix liên quan không?

Ví dụ kiểm tra meter sau khi ứng dụng khởi động:

~~~java
Gauge active = registry.find("jdbc.connections.active")
    .tag("name", "dataSource")
    .gauge();
~~~

Tag thực tế phụ thuộc cấu hình và phiên bản. Khi test, không hardcode tag chưa được xác nhận; trước tiên xem availableTags ở Actuator hoặc liệt kê Meter.Id trong registry.

Nếu ứng dụng tự tạo DataSource ngoài ApplicationContext hoặc tạo nhiều pool theo cách động, auto-configuration mặc định có thể không nhìn thấy đầy đủ các pool. Khi đó cần đăng ký binder riêng hoặc điều chỉnh cách tạo bean.

## 10. Cache và executor metrics: bean có tồn tại chưa đủ

Cache metrics có thể phụ thuộc cache manager, provider và cách binder truy cập từng cache. Một cache manager tồn tại nhưng không có cache được instrument hoặc cache chưa được tạo có thể làm số meter khác với kỳ vọng.

Executor metrics phụ thuộc loại executor. Một executor được tạo bằng Executors.newFixedThreadPool() và giữ trong field không nhất thiết tự động được bind như một bean executor mà Spring Boot nhận diện. Nếu muốn built-in metrics, hãy dùng loại bean/integration được hỗ trợ hoặc tạo MeterBinder riêng.

Với executor, các chỉ số thường có ý nghĩa:

- active: số thread đang thực thi.
- queued: số task đang chờ.
- pool size: số thread hiện có.
- completed: tổng task đã hoàn tất, nếu implementation cung cấp.

Khi kiểm tra, xác nhận đúng executor mà ứng dụng thực sự submit task. Nếu có nhiều executor, meter có thể được phân biệt bằng tag name hoặc executor name.

## 11. Condition Evaluation Report cho biết vì sao cấu hình match hoặc không match

Spring Boot có thể hiển thị báo cáo đánh giá điều kiện auto-configuration. Chạy ứng dụng với debug:

~~~bash
./gradlew bootRun --args='--debug'
~~~

Hoặc chạy jar:

~~~bash
java -jar app.jar --debug
~~~

Trong log, tìm phần CONDITIONS EVALUATION REPORT. Báo cáo phân nhóm:

- Positive matches: điều kiện đã match.
- Negative matches: điều kiện không match.
- Exclusions: auto-configuration bị loại trừ.
- Unconditional classes: cấu hình không phụ thuộc điều kiện thông thường.

Khi một built-in metrics không xuất hiện, tìm tên auto-configuration hoặc class binder tương ứng. Negative match thường cung cấp lý do như thiếu class, thiếu bean, property không bật hoặc ứng dụng không thuộc loại cần thiết.

Condition report chỉ giải thích quyết định cấu hình. Nó không chứng minh meter đã được đăng ký hoặc exporter đã gửi được dữ liệu. Sau khi condition match, vẫn phải kiểm tra bean/binder và MeterRegistry.

## 12. Kiểm tra điều kiện qua Actuator Conditions endpoint

Nếu ứng dụng có Actuator và Conditions endpoint được bật, có thể truy cập:

~~~text
/actuator/conditions
~~~

Endpoint này hiển thị kết quả condition evaluation trong ApplicationContext. Để expose:

~~~properties
management.endpoints.web.exposure.include=health,metrics,conditions
~~~

Endpoint conditions là công cụ chẩn đoán nhạy cảm vì có thể tiết lộ tên class, bean và cấu trúc nội bộ ứng dụng. Chỉ expose trong môi trường quản trị được bảo vệ; không công khai cho người dùng bên ngoài.

Nếu endpoint không xuất hiện, kiểm tra Actuator dependency, exposure configuration, management port/path và security rules. Không nhầm việc endpoint bị ẩn với việc auto-configuration không match.

## 13. Xác minh meter thực sự đã được đăng ký

Sau khi condition report cho thấy auto-configuration match, kiểm tra registry:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetricsDiagnostics {

    @Bean
    ApplicationRunner listMeters(MeterRegistry registry) {
        return args -> registry.getMeters().stream()
            .map(Meter::getId)
            .sorted(java.util.Comparator.comparing(Meter.Id::getName))
            .forEach(id -> System.out.println(
                id.getName() + " " + id.getTags()
            ));
    }
}
~~~

Đoạn code chỉ nên dùng tạm trong môi trường phát triển hoặc test; tránh in toàn bộ danh sách meter ở production nếu số lượng lớn hoặc tags chứa thông tin không phù hợp để log.

Có thể tra cứu một meter cụ thể:

~~~java
Meter meter = registry.find("jvm.memory.used").meter();
if (meter == null) {
    // Meter chưa được đăng ký trong registry này.
}
~~~

Nếu meter chưa có, cần quay lại kiểm tra binder, điều kiện và filter. Nếu meter có trong registry nhưng không thấy ở endpoint Prometheus, kiểm tra registry exporter, endpoint exposure và quy tắc naming.

## 14. Endpoint Actuator Metrics là bằng chứng ở lớp ứng dụng

Endpoint generic:

~~~text
GET /actuator/metrics
~~~

Liệt kê tên meter đã được registry quản lý và có thể được Actuator quan sát. Tra cứu một meter:

~~~text
GET /actuator/metrics/jvm.memory.used
~~~

Lọc tag:

~~~text
GET /actuator/metrics/http.server.requests?tag=method:GET
~~~

Phản hồi gồm measurements và availableTags tùy meter. Nếu tên không có trong danh sách, có thể meter chưa được đăng ký hoặc không thuộc registry mà endpoint đang đọc.

Một số meter chỉ được đăng ký khi có thao tác đầu tiên. Vì vậy, khi kiểm tra HTTP, cache hoặc client metrics, hãy thực hiện thao tác đại diện trước khi kết luận rằng binder không hoạt động.

## 15. Phân biệt meter chưa được tạo, meter bị lọc và meter không được export

| Trạng thái | Condition report | Registry | Endpoint/export |
| --- | --- | --- | --- |
| Auto-configuration không match | Có negative match | Không có meter từ binder đó | Không có dữ liệu |
| Binder không được tạo do thiếu bean/property | Điều kiện liên quan không match | Không có meter tương ứng | Không có dữ liệu |
| Meter bị MeterFilter từ chối | Auto-configuration có thể vẫn match | Meter không được đăng ký hoặc bị từ chối | Không có dữ liệu |
| Meter đã đăng ký nhưng chưa có thao tác | Condition có thể match | Meter có thể có giá trị ban đầu hoặc chưa được tạo tùy instrumentation | Có thể chưa thấy sample hoặc count bằng 0 |
| Meter có trong registry nhưng exporter không có | Condition và binder có thể đều match | Có meter | Kiểm tra registry type, naming, filter và endpoint |
| Endpoint không truy cập được | Không nói lên condition | Meter có thể vẫn tồn tại | Kiểm tra exposure, port, path và security |

Bảng này giúp chọn đúng bước điều tra. Đừng sửa dependency nếu vấn đề chỉ là endpoint chưa được expose; cũng đừng chỉ mở endpoint nếu binder chưa từng được tạo.

## 16. Kiểm tra MeterFilter và cấu hình enable/deny

MeterFilter có thể từ chối, đổi tên, thêm tags hoặc giới hạn meter. Vì vậy, auto-configuration có thể match nhưng meter vẫn không xuất hiện trong registry.

Ví dụ từ chối một prefix:

~~~java
registry.config().meterFilter(
    MeterFilter.denyNameStartsWith("jvm.")
);
~~~

Khi đó JVM binder vẫn có thể được tạo, nhưng meter có tên bắt đầu bằng jvm. bị từ chối khi đăng ký. Condition report không nhất thiết báo auto-configuration thất bại vì bộ lọc hoạt động ở lớp MeterRegistry.

Spring Boot cũng cung cấp các property để cấu hình metrics enable/disable và distribution. Cú pháp, mức ưu tiên và phạm vi áp dụng phụ thuộc phiên bản. Hãy xem configuration metadata của đúng dependency; tránh suy ra rằng một property enable/disable meter cũng bật/tắt auto-configuration hoặc binder.

## 17. Kiểm thử điều kiện auto-configuration

Với Spring Boot, ApplicationContextRunner giúp kiểm tra điều kiện mà không cần khởi động toàn bộ ứng dụng:

~~~java
import io.micrometer.core.instrument.binder.MeterBinder;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class QueueMetricsAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withUserConfiguration(QueueMetricsConfiguration.class);

    @Test
    void createsBinderWhenEnabled() {
        contextRunner
            .withPropertyValues("app.metrics.queue.enabled=true")
            .withBean(JobQueue.class, JobQueue::new)
            .run(context -> {
                assertThat(context).hasSingleBean(MeterBinder.class);
            });
    }

    @Test
    void doesNotCreateBinderWhenDisabled() {
        contextRunner
            .withPropertyValues("app.metrics.queue.enabled=false")
            .withBean(JobQueue.class, JobQueue::new)
            .run(context -> {
                assertThat(context).doesNotHaveBean(MeterBinder.class);
            });
    }
}
~~~

Đây là ví dụ minh họa cho auto-configuration của ứng dụng. Với auto-configuration của Spring Boot, cần đưa đúng configuration class vào runner và cung cấp hoặc loại bỏ bean/property để kiểm tra từng nhánh điều kiện.

Nên kiểm tra ít nhất:

- Classpath có/không có integration module.
- Bean nguồn có/không có.
- Property bật/tắt.
- Bean tùy chỉnh có làm điều kiện MissingBean không match.
- Binder thực sự đăng ký meter vào registry.
- MeterFilter có chặn meter như dự kiến.

## 18. Integration test xác nhận built-in metric

Unit test điều kiện không thay thế kiểm thử với ApplicationContext thực tế. Có thể dùng SpringBootTest để xác nhận binder và meter:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class BuiltInMetricsIntegrationTest {

    @Autowired
    MeterRegistry registry;

    @Test
    void registersJvmMemoryMetric() {
        assertThat(registry.find("jvm.memory.used").gauge())
            .isNotNull();
    }
}
~~~

Test cụ thể phải dùng dependency và auto-configuration thực tế của dự án. Với HTTP metrics, hãy gửi request trước rồi mới kiểm tra meter. Với datasource/cache/executor metrics, cần tạo đúng bean và thực hiện thao tác tương ứng nếu meter được đăng ký lười.

Nếu cần xác nhận Prometheus export, dùng PrometheusMeterRegistry hoặc kiểm thử HTTP endpoint /actuator/prometheus. SimpleMeterRegistry chỉ xác minh logic meter trong bộ nhớ, không chứng minh naming convention hay exporter hoạt động.

## 19. Quy trình điều tra khi một built-in metric không xuất hiện

Thực hiện theo thứ tự:

1. Xác định tên canonical dự kiến và nhóm instrumentation tương ứng.
2. Kiểm tra dependency và runtime classpath của ứng dụng.
3. Xác nhận application type và web/client stack phù hợp.
4. Kiểm tra bean nguồn như DataSource, CacheManager, Executor hoặc HTTP client.
5. Bật debug condition report hoặc truy cập Conditions endpoint trong môi trường an toàn.
6. Tìm positive/negative match của auto-configuration liên quan.
7. Kiểm tra binder bean có tồn tại và đã được bind vào registry cần xem không.
8. Kiểm tra MeterFilter và các property enable/deny.
9. Thực hiện thao tác nghiệp vụ để tạo mẫu nếu instrumentation đăng ký lười.
10. Tra cứu tên canonical qua /actuator/metrics.
11. Kiểm tra exposition qua /actuator/prometheus hoặc exporter tương ứng.
12. Xác minh endpoint exposure, management port/path và security.

Thu thập bằng chứng ở từng lớp giúp xác định chính xác nguyên nhân thay vì thêm dependency hoặc bật mọi cấu hình một cách thử-sai.

## 20. Checklist trước khi kết luận metrics đã được tạo

- [ ] Dependency integration có trong runtime classpath.
- [ ] Auto-configuration class phù hợp được import và không bị exclude.
- [ ] Điều kiện classpath, bean, property và application type đã match.
- [ ] Binder hoặc instrumentation bean đã được tạo.
- [ ] Binder đã bind vào đúng MeterRegistry.
- [ ] Không có MeterFilter hoặc cấu hình enable/deny chặn meter.
- [ ] Đã thực hiện thao tác cần thiết nếu meter được đăng ký lười.
- [ ] Meter xuất hiện trong registry.getMeters() hoặc Actuator Metrics.
- [ ] Tên và tags đúng như kỳ vọng.
- [ ] Exporter và endpoint đã được cấu hình, expose và truy cập được.
- [ ] Integration test xác nhận đường export nếu cần kiểm chứng backend.

Built-in metrics chỉ xuất hiện khi điều kiện của thư viện hoặc framework được đáp ứng và instrumentation thực sự đăng ký meter vào registry. Condition report giải thích vì sao auto-configuration được bật hoặc bỏ qua; kiểm tra MeterRegistry và endpoint xác nhận kết quả cuối cùng. Khi tách riêng dependency, điều kiện, binder, filter và export, việc chẩn đoán một phép đo bị thiếu sẽ rõ ràng và có thể lặp lại.
