# Không có metric do thiếu registry hoặc auto-configuration

> **Chương:** Chẩn đoán sự cố  
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt lỗi thiếu MeterRegistry, thiếu ObservationRegistry, thiếu observation handler và thiếu exporter/Actuator endpoint.
2. Hiểu vai trò của Spring Boot auto-configuration và điều kiện classpath/bean/property khiến metrics không được tạo.
3. Xác minh Spring AI VectorStore có phát Observation và Observation đó có được chuyển thành meter hay không.
4. Kiểm tra dependencies, active profile, property, bean overrides và cấu hình registry theo đúng phiên bản.
5. Dùng Actuator, Prometheus và một phép đo thử để xác định dữ liệu mất ở tầng nào.
6. Viết kiểm thử để phát hiện hồi quy khi nâng Spring Boot, Spring AI, Micrometer hoặc thay đổi auto-configuration.

## 1. Triệu chứng: ứng dụng chạy nhưng không thấy metric

Một ứng dụng Spring AI gọi VectorStore thành công. Log không có exception, câu trả lời RAG vẫn đúng, nhưng dashboard không xuất hiện metric truy vấn vector. Có thể đang xảy ra một trong nhiều tình huống:

- Code chưa phát Observation.
- Spring AI adapter đang dùng không instrument operation đó hoặc instrumentation bị tắt.
- Observation được tạo nhưng ObservationRegistry không có handler chuyển Observation thành meter.
- Không có MeterRegistry phù hợp để nhận meter.
- Meter đã có trong registry nhưng không có exporter hoặc endpoint scrape.
- Actuator endpoint tồn tại nhưng không được expose, bị security chặn hoặc Prometheus scrape nhầm target.
- Metric có tên/tag khác dự kiến, bị filter hoặc nằm trong profile khác.
- Operation chưa chạy trong cửa sổ quan sát, hoặc dữ liệu bị sampling/aggregation che khuất.

**Không có metric trên dashboard chưa chứng minh rằng VectorStore không phát telemetry.** Cần kiểm tra từng chặng từ code đến backend.

### 1.1. Bản đồ đường đi của metric

~~~mermaid
flowchart TD
  A["VectorStore operation"] --> B["Spring AI Observation"]
  B --> C["ObservationRegistry"]
  C --> D["MeterObservationHandler"]
  D --> E["MeterRegistry"]
  E --> F["Exporter / registry integration"]
  F --> G["Actuator endpoint or scrape"]
  G --> H["Prometheus / metrics backend"]
  H --> I["Dashboard / alert"]
  B -.-> T["Tracing ObservationHandler"]
  T --> X["Tracing exporter"]
  C -.-> N["Custom ObservationRegistry"]
  N -.-> Z["Handlers may be missing"]
  E -.-> M["Meter exists but no exporter"]
  G -.-> P["Endpoint hidden or protected"]
~~~

Mỗi thành phần có trách nhiệm riêng. Một ứng dụng có thể có trace nhưng không có metric, hoặc có metric trong process nhưng chưa export được. Việc cài một tracing exporter không tự động chứng minh rằng MeterRegistry và metrics exporter cũng đã được cấu hình.

### 1.2. Bốn thành phần không thể thay thế cho nhau

| Thành phần | Vai trò | Dấu hiệu khi thiếu |
|---|---|---|
| **ObservationRegistry** | Nhận và điều phối Observation do Spring AI/application phát ra | Observation không được ghi nhận qua registry dự kiến |
| **ObservationHandler** | Xử lý lifecycle Observation; meter handler chuyển Observation thành meter, tracing handler tạo span | Có Observation nhưng không có meter hoặc trace tương ứng |
| **MeterRegistry** | Lưu trữ meter/counter/timer trong process | Không có nơi nhận các phép đo metric |
| **Exporter / Actuator endpoint** | Công bố dữ liệu ra hệ thống bên ngoài hoặc endpoint scrape | Meter có thể tồn tại trong process nhưng dashboard không thấy |

Một ObservationRegistry không phải là MeterRegistry. Tương tự, MeterRegistry không tự động bảo đảm mọi Observation đều được chuyển thành Timer/Counter; cần có handler phù hợp.

## 2. Hiểu cơ chế Spring Boot auto-configuration

Spring Boot cấu hình nhiều thành phần dựa trên classpath, property, environment và các bean đã tồn tại. Auto-configuration thường dùng điều kiện như:

- Có hoặc không có một class trên classpath.
- Có hoặc không có bean cùng kiểu.
- Property có giá trị bật/tắt.
- Ứng dụng đang chạy trong context/profile phù hợp.
- Auto-configuration chưa bị exclude hoặc thay thế.

Vì vậy, cùng một source code nhưng hai deployment có dependency hoặc profile khác nhau có thể tạo ra hệ thống metrics khác nhau.

### 2.1. Dependency cần kiểm tra

Trong một ứng dụng Spring Boot, những nhóm dependency thường liên quan:

| Dependency / nhóm | Mục đích |
|---|---|
| Spring Boot Actuator | Cung cấp management endpoints và tích hợp metrics |
| Micrometer Observation | API ObservationRegistry và Observation |
| Micrometer Core | MeterRegistry, Timer, Counter và các meter primitives |
| Micrometer registry implementation | Export metrics sang Prometheus hoặc backend tương ứng |
| Spring AI VectorStore starter/adapter | Cung cấp VectorStore implementation và tích hợp quan sát theo phiên bản |
| JDBC / datasource instrumentation (nếu dùng) | Quan sát client/database operations ở tầng JDBC |
| Tracing bridge/exporter (nếu cần trace) | Chuyển Observation thành spans và export trace |

Trong Spring Boot starter thông thường, một phần Micrometer dependencies có thể đã được kéo bắc cầu. Không nên thêm nhiều phiên bản Micrometer thủ công để sửa lỗi. Hãy dùng Spring Boot dependency management và Spring AI BOM tương thích, rồi kiểm tra dependency tree khi có xung đột.

### 2.2. Ví dụ Maven

Ví dụ tối giản cho ứng dụng Spring Boot dùng Actuator và Prometheus:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Spring AI VectorStore starter/adapter của dự án -->
</dependencies>
~~~

Đoạn trên chỉ minh họa các dependency liên quan đến Actuator và Prometheus; phải giữ đúng starter VectorStore và dependency management đang dùng trong dự án. Tên starter Spring AI phụ thuộc backend, không có một artifact VectorStore chung cho mọi nhà cung cấp.

### 2.3. Ví dụ Gradle

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")

    // Thêm Spring AI VectorStore starter/adapter của backend đang sử dụng.
}
~~~

Không pin phiên bản micrometer-core, micrometer-observation và registry riêng lẻ nếu Spring Boot BOM đã quản lý chúng, trừ khi có lý do tương thích được xác minh. Một registry version lệch với Micrometer Core có thể gây lỗi khởi tạo, NoSuchMethodError hoặc auto-configuration không hoạt động như mong đợi.

### 2.4. Kiểm tra dependency tree

Với Maven:

~~~bash
mvn dependency:tree
~~~

Có thể lọc theo Micrometer/Actuator bằng plugin hoặc pipe phù hợp với shell đang dùng. Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm tra:

- Có spring-boot-starter-actuator nếu cần management endpoints.
- Có Micrometer Core/Observation tương thích.
- Có registry implementation nếu cần export metrics ra Prometheus hoặc backend cụ thể.
- Có đúng Spring AI VectorStore adapter.
- Không có nhiều phiên bản Micrometer khác nhau bị kéo vào runtime.
- Dependency không chỉ nằm trong test scope khi ứng dụng production cần nó.

## 3. Phân biệt ObservationRegistry với MeterRegistry

Đây là nguyên nhân dễ gây nhầm lẫn nhất.

### 3.1. ObservationRegistry điều phối sự kiện

Spring AI phát Observation quanh một hoạt động như query VectorStore. Observation chứa lifecycle và context, ví dụ:

- Operation name.
- Low-cardinality key values.
- High-cardinality key values.
- Start/stop và error.

Observation chỉ trở thành metric khi có handler phù hợp xử lý nó.

### 3.2. MeterRegistry lưu meter

MeterRegistry giữ các meter như:

- Counter: số lần một sự kiện xảy ra.
- Timer: số phép đo và tổng thời gian, có thể thêm histogram.
- DistributionSummary: phân phối giá trị như số document trả về.
- Gauge: giá trị quan sát tại một thời điểm.

Một custom counter có thể được đăng ký trực tiếp vào MeterRegistry mà không đi qua ObservationRegistry.

### 3.3. MeterObservationHandler nối hai hệ thống

Trong Micrometer, handler cho meter có thể chuyển Observation lifecycle thành meter. Spring Boot auto-configuration thường thiết lập các thành phần này khi điều kiện phù hợp. Nếu ứng dụng tự tạo ObservationRegistry hoặc thay thế cấu hình metrics, cần kiểm tra handler đã được đăng ký chưa.

Một trường hợp dễ mắc:

~~~java
@Bean
ObservationRegistry observationRegistry() {
    return ObservationRegistry.create();
}
~~~

Bean tùy chỉnh có thể khiến auto-configuration mặc định lùi lại theo điều kiện ConditionalOnMissingBean. Registry mới tạo ở đây không tự có toàn bộ handler mà Spring Boot đã cấu hình cho ứng dụng. Kết quả có thể là code vẫn gọi Observation nhưng không có meter handler hoặc tracing handler.

**Trong ứng dụng Spring Boot, ưu tiên dùng ObservationRegistry do Boot cung cấp.** Chỉ tự tạo registry khi thật sự cần một registry độc lập và chủ động cấu hình tất cả handler cần thiết.

### 3.4. Ví dụ standalone có MeterObservationHandler

Nếu chạy Micrometer ngoài Spring Boot, có thể kết nối registry và meter handler tường minh:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class ObservationMeterProbe {
    public static void main(String[] args) {
        var meters = new SimpleMeterRegistry();
        var observations = ObservationRegistry.create();

        observations.observationConfig()
                .observationHandler(
                        new DefaultMeterObservationHandler(meters));

        Observation.createNotStarted(
                        "app.telemetry.observation.probe", observations)
                .lowCardinalityKeyValue("outcome", "success")
                .observe(() -> {
                    // Công việc thử nghiệm.
                });

        var timer = meters.find(
                "app.telemetry.observation.probe").timer();
        if (timer == null || timer.count() != 1) {
            throw new IllegalStateException(
                    "Observation chưa được chuyển thành meter");
        }
    }
}
~~~

Đây là ví dụ standalone để minh họa đường nối Observation → meter. Trong Spring Boot, không tạo thêm một registry riêng như trên chỉ để thay registry đang được auto-configure; dùng bean đã inject hoặc viết test context riêng.

## 4. Xác minh Spring AI VectorStore có phát Observation

Spring AI có observation cho các operation VectorStore, thường có tên:

~~~text
db.vector.client.operation
~~~

Operation name có thể là query, add, delete hoặc operation được adapter hỗ trợ. Các thuộc tính có thể gồm backend system, operation name, collection/namespace và thông tin query tùy implementation/version.

### 4.1. Không phải mọi code path đều tạo cùng một observation

Kiểm tra các điểm sau:

1. Ứng dụng thực sự gọi VectorStore của Spring AI hay gọi trực tiếp SDK của backend?
2. Adapter đang dùng có hỗ trợ Observation trong đúng phiên bản không?
3. Operation cụ thể có được instrument không? Query và batch/indexing có thể đi qua code path khác.
4. Observation có bị tắt bởi property, custom configuration hoặc convention không?
5. Ứng dụng có inject đúng ObservationRegistry do Spring quản lý không?
6. Có meter handler nhận Observation không?

Nếu code gọi trực tiếp SDK của database, Spring AI VectorStore observation sẽ không tự xuất hiện quanh lời gọi đó. Khi đó cần instrumentation của SDK/JDBC hoặc tạo Observation nghiệp vụ tại service boundary.

### 4.2. Thử operation tối thiểu

Thực hiện một thao tác query thực tế trong môi trường thử nghiệm:

~~~java
var request = SearchRequest.builder()
        .query("Câu hỏi fixture không chứa dữ liệu thật")
        .topK(3)
        .build();

var documents = vectorStore.similaritySearch(request);
~~~

Sau khi gọi, kiểm tra meter name và tags được export. Đừng giả định mọi phiên bản đều tạo chính xác cùng một tag set. Dùng endpoint metrics để khám phá meter thực tế.

### 4.3. Tách lỗi quan sát với lỗi VectorStore

| Kết quả | Ý nghĩa |
|---|---|
| Query thành công, không có Observation | Có thể adapter không instrument hoặc Observation bị tắt |
| Có Observation nhưng không có meter | Kiểm tra MeterObservationHandler và MeterRegistry |
| Có meter trong registry nhưng endpoint không thấy | Kiểm tra exporter/Actuator exposure |
| Endpoint thấy meter nhưng Prometheus không có | Kiểm tra scrape target, path, network và scrape errors |
| Prometheus có series nhưng dashboard không thấy | Kiểm tra query, label filter, time range và datasource |
| Query thất bại trước khi vào adapter | Không kỳ vọng có operation query hoàn tất; xem error path và instrumentation behavior |

Một query rỗng nhưng hoàn tất vẫn có thể tạo meter. Số document bằng 0 không đồng nghĩa meter không tồn tại.

## 5. Kiểm tra auto-configuration và bean thực tế

### 5.1. Bật condition evaluation report

Khởi động ứng dụng với debug condition report:

~~~bash
java -jar app.jar --debug
~~~

Tìm các auto-configuration liên quan:

- Metrics/Micrometer.
- Actuator endpoints.
- Prometheus registry exporter.
- Observation.
- Datasource/pool metrics.

Condition evaluation report cho biết auto-configuration nào match hoặc không match và điều kiện nào thất bại. Đây là cách tìm nguyên nhân khi bean không được tạo do thiếu classpath, property hoặc bean khác đã tồn tại.

### 5.2. Kiểm tra endpoint conditions

Nếu Actuator endpoint conditions được expose và quyền truy cập cho phép, có thể xem:

~~~text
/actuator/conditions
~~~

Endpoint này cung cấp thông tin condition report ở runtime. Không expose rộng rãi endpoint diagnostics trên production; giới hạn bằng network policy và Spring Security.

### 5.3. Kiểm tra bean trong ApplicationContext

Một diagnostic runner có thể xác nhận các bean quan trọng đã tồn tại:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class TelemetryBeanDiagnostics {
    @Bean
    ApplicationRunner reportTelemetryBeans(
            ApplicationContext context,
            MeterRegistry meters,
            ObservationRegistry observations) {
        return args -> {
            System.out.println("MeterRegistry: "
                    + meters.getClass().getName());
            System.out.println("ObservationRegistry: "
                    + observations.getClass().getName());
            System.out.println("MeterRegistry bean names: "
                    + String.join(", ",
                    context.getBeanNamesForType(MeterRegistry.class)));
            System.out.println("ObservationRegistry bean names: "
                    + String.join(", ",
                    context.getBeanNamesForType(
                            ObservationRegistry.class)));
        };
    }
}
~~~

Đoạn này chỉ chẩn đoán sự tồn tại và loại bean. Nó chưa chứng minh handler đã được đăng ký hoặc exporter đang hoạt động. Không log toàn bộ bean graph hay cấu hình chứa secret vào log production.

Nếu inject MeterRegistry hoặc ObservationRegistry thất bại ngay khi khởi động, đó là dấu hiệu dependency/auto-configuration/bean definition cần được xử lý trước khi kiểm tra metric name.

## 6. Cấu hình Actuator và Prometheus

Có MeterRegistry trong process không đồng nghĩa endpoint HTTP đã công bố meter.

### 6.1. Expose metrics endpoint

Ví dụ cấu hình Actuator:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - metrics
          - prometheus
~~~

Danh sách endpoint expose phải phù hợp chính sách bảo mật. Không expose tất cả endpoints chỉ để debug. Nếu endpoint bị security filter, reverse proxy hoặc network policy chặn, request scrape có thể nhận 401/403/404 dù MeterRegistry vẫn hoạt động.

### 6.2. Kiểm tra metrics endpoint

Mở:

~~~text
GET /actuator/metrics
~~~

Endpoint thường liệt kê tên meter hiện có. Sau đó truy vấn một meter cụ thể:

~~~text
GET /actuator/metrics/db.vector.client.operation
~~~

Tên thực tế phụ thuộc convention và version. Nếu meter name có ký tự đặc biệt hoặc exporter chuẩn hóa tên, dùng tên được endpoint liệt kê thay vì tự đoán.

Endpoint metrics của Actuator là endpoint chẩn đoán, không phải giao thức scrape Prometheus. Nó có thể trả một snapshot/summary của meter trong process.

### 6.3. Kiểm tra Prometheus endpoint

Khi đã thêm Prometheus registry implementation, kiểm tra:

~~~text
GET /actuator/prometheus
~~~

Tìm metric liên quan đến VectorStore. Tên Micrometer có thể được chuẩn hóa thành dạng underscore trong Prometheus. Ví dụ observation name dạng dot có thể xuất thành một metric name khác theo naming convention/exporter.

Nếu /actuator/metrics có meter nhưng /actuator/prometheus không có, kiểm tra:

- Prometheus registry dependency có trên runtime classpath không?
- Registry có được Spring Boot tạo và gắn vào composite registry không?
- Exporter có bị disable bằng property không?
- Meter có bị MeterFilter deny hoặc rename không?
- Metric có bị lọc bởi cấu hình exporter hoặc naming convention không?

### 6.4. Kiểm tra Prometheus scrape

Trong Prometheus, xem trạng thái target và scrape error. Kiểm tra:

- Target URL/host/port đúng.
- Path là /actuator/prometheus.
- Target đang UP.
- HTTP status của scrape thành công.
- Scrape interval và time range phù hợp.
- Network/security cho phép Prometheus truy cập.
- Không scrape nhầm instance hoặc môi trường.

Nếu endpoint trả metric đúng nhưng target DOWN, vấn đề nằm giữa Prometheus và ứng dụng, không phải Spring AI Observation.

## 7. Phân tích property, profile và cấu hình bị ghi đè

### 7.1. Kiểm tra cấu hình theo môi trường

Ứng dụng có thể có:

- application.yml
- application-dev.yml
- application-staging.yml
- application-prod.yml
- Environment variables.
- Command-line arguments.
- Config server hoặc mounted config.

Giá trị cuối cùng phụ thuộc precedence của Spring Boot configuration property sources. Đừng chỉ đọc file mặc định rồi kết luận property đang có hiệu lực.

Kiểm tra active profiles và giá trị property đã bind theo cách an toàn. Tránh in toàn bộ Environment vì có thể lộ credentials.

### 7.2. Property disable observation

Một số component có property riêng để bật/tắt observations hoặc kiểm soát nội dung capture. Tên property và default có thể thay đổi theo Spring AI version. Hãy:

1. Đọc reference đúng phiên bản Spring AI trong dependency management.
2. Tìm property có prefix của component đang điều tra.
3. Kiểm tra profile/environment có override thành false không.
4. Kiểm tra custom ObservationConvention/Filter có loại bỏ hoặc thay đổi data không.
5. Thực hiện một operation test rồi quan sát span/meter thực tế.

Không sao chép property từ một phiên bản Spring AI khác mà chưa xác minh. Đặc biệt, property tắt ghi nội dung response chỉ kiểm soát capture payload; nó không nhất thiết tắt hoặc bật toàn bộ metric.

### 7.3. Custom bean làm auto-configuration lùi lại

Các tình huống thường gặp:

- Tự khai báo ObservationRegistry nhưng không đăng ký meter/tracing handlers.
- Tự khai báo MeterRegistry nhưng không gắn exporter mong muốn.
- Tự tạo SimpleMeterRegistry trong production khiến metrics chỉ tồn tại trong memory.
- Exclude một auto-configuration class để xử lý lỗi khác.
- Dùng @TestConfiguration hoặc test slice thay thế registry.
- Tạo nhiều ApplicationContext khiến code và endpoint đọc các registry khác nhau.

Nếu có custom bean, kiểm tra condition report để biết auto-configuration nào đã back off. Chỉ xóa override khi đã xác định nó không còn cần thiết; có thể custom bean đang phục vụ một yêu cầu riêng của ứng dụng.

## 8. Chẩn đoán bằng phép đo thử có kiểm soát

Một quy trình ngắn giúp phân biệt MeterRegistry với Observation path.

### 8.1. Probe trực tiếp MeterRegistry

Trong môi trường test/dev, đăng ký một counter và tăng một lần:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MeterRegistryProbe {
    @Bean
    ApplicationRunner meterProbe(MeterRegistry meters) {
        return args -> Counter.builder("app.telemetry.meter.probe")
                .tag("probe", "startup")
                .register(meters)
                .increment();
    }
}
~~~

Nếu meter probe xuất hiện trong /actuator/metrics hoặc exporter, MeterRegistry và đường export cơ bản đang hoạt động. Nếu bean inject được nhưng meter không xuất hiện, kiểm tra registry đang dùng, filter và endpoint.

Chỉ dùng metric probe trong môi trường kiểm thử hoặc bỏ sau khi xác minh; tránh tạo metric rác trong production.

### 8.2. Probe Observation → meter

Với ObservationRegistry được inject:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ObservationProbe {
    @Bean
    ApplicationRunner observationProbe(
            ObservationRegistry observations) {
        return args -> Observation.createNotStarted(
                        "app.telemetry.observation.probe", observations)
                .lowCardinalityKeyValue("probe", "startup")
                .observe(() -> {
                    // Không thực hiện I/O hoặc gọi model tại đây.
                });
    }
}
~~~

Nếu counter probe xuất hiện nhưng Observation probe không tạo meter, tập trung kiểm tra ObservationRegistry và MeterObservationHandler. Nếu cả hai probe đều xuất hiện nhưng metric VectorStore không có, tập trung vào Spring AI adapter, property hoặc code path query.

### 8.3. Không nhầm probe với bằng chứng của adapter

Observation probe chỉ chứng minh registry/handler có thể chuyển một Observation tổng quát thành meter. Nó không chứng minh VectorStore adapter phát observation. Cần chạy một query qua đúng bean VectorStore và kiểm tra kết quả.

## 9. Bảng triệu chứng và nguyên nhân có khả năng

| Triệu chứng | Nguyên nhân cần kiểm tra | Bước xác minh |
|---|---|---|
| Không inject được MeterRegistry | Thiếu Micrometer/Actuator hoặc cấu hình registry | Dependency tree, condition report |
| Không inject được ObservationRegistry | Thiếu Observation integration hoặc custom config | Bean report, classpath, auto-config |
| Có MeterRegistry nhưng không có meter nào | Chưa có operation, filter loại meter hoặc code không đăng ký | Counter probe, meter list |
| Custom Counter có, Observation meter không có | Thiếu meter observation handler hoặc registry tùy chỉnh | Observation probe, handler config |
| Observation probe có, VectorStore metric không có | Adapter không instrument, operation chưa chạy hoặc bị disable | Query thật, adapter/version, properties |
| VectorStore metric có trong Actuator nhưng không có Prometheus | Thiếu registry exporter hoặc exporter config | Runtime dependency, /actuator/prometheus |
| Prometheus endpoint có metric nhưng target DOWN | Scrape URL/network/security lỗi | Target status, HTTP scrape error |
| Prometheus có series nhưng dashboard trống | Query/labels/time range/datasource sai | Explore raw series, label selectors |
| Dev có metric, prod không có | Profile, env var, dependency packaging hoặc security khác | So sánh effective config và runtime classpath |
| Chỉ thấy metric sau khi gọi query | Không có operation trong thời gian quan sát trước đó | Thực hiện fixture query có kiểm soát |
| Timer count tăng nhưng p95 không có | Histogram/bucket chưa bật hoặc query sai tên series | Kiểm tra _bucket, registry config |
| Meter bị mất sau nâng version | Convention, dependency alignment hoặc property thay đổi | Dependency diff, condition report, integration test |

## 10. Kiểm thử trong Spring Boot

### 10.1. Unit test MeterRegistry

Test một service custom có thể dùng SimpleMeterRegistry:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MeterRegistryTest {
    @Test
    void customCounterIsRecorded() {
        try (var registry = new SimpleMeterRegistry()) {
            registry.counter(
                    "app.vector.query.outcomes",
                    "outcome", "success").increment();

            assertThat(registry.get(
                    "app.vector.query.outcomes")
                    .tag("outcome", "success")
                    .counter()
                    .count()).isEqualTo(1.0);
        }
    }
}
~~~

Test này xác minh Micrometer counter hoạt động. Nó không xác minh Spring Boot auto-configuration, exporter hoặc Spring AI instrumentation.

### 10.2. Unit test Observation handler

Test độc lập có thể kết nối handler:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

class ObservationToMeterTest {
    @Test
    void observationIsRecordedByMeterHandler() {
        try (var meters = new SimpleMeterRegistry()) {
            var observations = ObservationRegistry.create();
            observations.observationConfig()
                    .observationHandler(
                            new DefaultMeterObservationHandler(meters));

            Observation.createNotStarted(
                            "app.vector.query.probe", observations)
                    .lowCardinalityKeyValue("outcome", "success")
                    .observe(() -> {
                    });

            assertThat(meters.find(
                    "app.vector.query.probe").timer()).isNotNull();
        }
    }
}
~~~

Test này kiểm tra Micrometer Observation API và handler độc lập. Trong Spring Boot, integration test cần dùng context thực tế và kiểm tra registry/handlers do auto-configuration cung cấp.

### 10.3. Integration test cho Spring AI adapter

Một integration test đáng tin cậy nên:

1. Khởi động ApplicationContext với dependency và properties giống môi trường mục tiêu.
2. Lấy VectorStore, ObservationRegistry và MeterRegistry từ context.
3. Gọi query fixture qua đúng adapter.
4. Xác minh operation hoàn tất hoặc phát lỗi theo fixture.
5. Kiểm tra meter/observation xuất hiện với operation name tương ứng theo version.
6. Kiểm tra tag set và privacy policy.
7. Nếu dùng Prometheus, kiểm tra endpoint exporter có series tương ứng.
8. Đảm bảo test không phụ thuộc dịch vụ ngoài nếu mục tiêu chỉ là kiểm tra auto-configuration; dùng test backend/stub phù hợp.

Không chỉ assert rằng bean tồn tại. Một bean MeterRegistry rỗng không chứng minh observation pipeline đang hoạt động.

## 11. Histogram và percentile: metric có nhưng p95 vẫn trống

Một trường hợp phổ biến là endpoint có timer count/sum nhưng PromQL histogram_quantile không trả kết quả.

Nguyên nhân thường gặp:

- Histogram chưa được bật cho meter.
- Prometheus registry không export bucket.
- Dashboard dùng sai tên metric hoặc label.
- Time window không có đủ samples.
- MeterFilter hoặc exporter đã loại bucket series.

Ví dụ PromQL khi bucket được export:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, db_system) (
    rate(db_vector_client_operation_seconds_bucket{
      db_operation_name="query"
    }[5m])
  )
)
~~~

Nếu chỉ có _count, _sum và _max, chưa thể tính p95 từ các series đó. _max không phải p95. Hãy kiểm tra histogram configuration theo phiên bản Spring Boot/Micrometer và xác minh series _bucket thực tế trước khi sửa dashboard.

## 12. Runbook xử lý sự cố

Thực hiện theo thứ tự để tìm đúng tầng bị đứt:

1. **Xác nhận operation:** gọi một VectorStore query fixture và xác minh code path thực sự được chạy.
2. **Kiểm tra dependency:** xác minh Actuator, Micrometer, registry exporter và Spring AI adapter có mặt ở runtime.
3. **Kiểm tra bean:** xác nhận MeterRegistry và ObservationRegistry được inject từ đúng ApplicationContext.
4. **Kiểm tra handler:** chạy Observation probe; nếu Counter probe có nhưng Observation probe không có meter, điều tra meter handler.
5. **Kiểm tra adapter:** xác minh phiên bản và operation đó có phát Observation; kiểm tra property disable.
6. **Kiểm tra meter list:** mở /actuator/metrics và tìm meter name thực tế.
7. **Kiểm tra exporter:** mở /actuator/prometheus nếu dùng Prometheus registry.
8. **Kiểm tra scrape:** xác minh Prometheus target UP, URL/path và scrape errors.
9. **Kiểm tra dashboard:** dùng Explore/raw series để xác minh tên, labels, time range và datasource.
10. **Kiểm tra privacy/filters:** xác minh MeterFilter, ObservationFilter và exporter không vô tình loại metric cần thiết hoặc làm lộ nội dung.
11. **Ghi lại nguyên nhân:** dependency, auto-config condition, custom bean, profile, adapter, handler, exporter hay scrape.
12. **Thêm regression test:** kiểm tra meter/observation path trong context gần với runtime production.

### 12.1. Mẫu ghi nhận điều tra

| Trường | Giá trị cần ghi |
|---|---|
| Application build/profile | Build ID và profile đang hoạt động |
| Spring Boot / Spring AI | Phiên bản đã pin |
| VectorStore adapter | Artifact và phiên bản |
| MeterRegistry | Bean class và registry implementation |
| ObservationRegistry | Bean được inject từ context nào |
| Observation handlers | Có meter handler/tracing handler cần thiết không |
| Counter probe | PASS/FAIL |
| Observation probe | PASS/FAIL |
| VectorStore query observation | PASS/FAIL |
| Actuator metrics | Endpoint và meter name |
| Prometheus exporter | Có/không có series |
| Scrape target | UP/DOWN và lỗi |
| Root cause | Tầng đã xác minh |

Không đưa credentials, raw query, document content hoặc toàn bộ environment properties vào incident report.

## 13. Những sai lầm thường gặp

1. **Cho rằng có ObservationRegistry là đã có metrics.** Cần handler chuyển Observation thành meter.
2. **Cho rằng có MeterRegistry là Spring AI tự phát mọi meter.** Adapter phải phát Observation và code path phải chạy.
3. **Cài tracing exporter rồi mong Prometheus có metric.** Trace và metric là các tín hiệu khác nhau.
4. **Chỉ thêm Actuator mà quên registry exporter.** Actuator metrics endpoint không thay thế Prometheus registry.
5. **Tạo ObservationRegistry tùy chỉnh nhưng không thêm handlers.** Auto-configuration có thể đã back off.
6. **Dùng SimpleMeterRegistry trong production rồi chờ dữ liệu ở backend.** Registry này chủ yếu lưu meter trong process, không tự export.
7. **Chỉ kiểm tra file application.yml mặc định.** Active profile và environment variables có thể override.
8. **Đoán tên metric.** Observation name và Prometheus series name có thể khác do convention.
9. **Không chạy query fixture.** Không có operation thì không có timer count mới.
10. **Dùng Actuator endpoint bị security chặn làm bằng chứng registry không tồn tại.** Kiểm tra bean và endpoint exposure riêng.
11. **Bỏ qua MeterFilter.** Meter có thể bị deny, rename hoặc giới hạn tag.
12. **Kỳ vọng p95 khi chưa export histogram buckets.** Count/sum/max không đủ để tính percentile.
13. **Thêm phiên bản Micrometer thủ công không đồng bộ.** Có thể gây xung đột binary/runtime.
14. **Chỉ test bean existence.** Bean rỗng không chứng minh Observation → meter → exporter hoạt động.
15. **Expose mọi Actuator endpoint để debug.** Có thể mở rộng bề mặt thông tin vận hành ngoài ý muốn.

## 14. Bài thực hành tự luyện

**Bối cảnh:** Ứng dụng Spring Boot và Spring AI gọi PostgreSQL VectorStore thành công. Nhóm vận hành không thấy metric VectorStore trên Prometheus, dù endpoint health vẫn hoạt động.

Yêu cầu:

1. Kiểm tra runtime dependency tree và xác nhận Actuator, Micrometer, Prometheus registry, Spring AI VectorStore adapter.
2. Xác nhận MeterRegistry và ObservationRegistry được inject từ ApplicationContext.
3. Kiểm tra có custom Bean ObservationRegistry hoặc Bean MeterRegistry làm auto-configuration back off không.
4. Khởi động với condition evaluation report và tìm điều kiện auto-configuration không match.
5. Chạy Counter probe để kiểm tra MeterRegistry.
6. Chạy Observation probe để kiểm tra meter observation handler.
7. Gọi một query fixture qua đúng VectorStore adapter.
8. Kiểm tra /actuator/metrics và tên meter thực tế.
9. Kiểm tra /actuator/prometheus, histogram bucket và naming convention.
10. Kiểm tra Prometheus target, scrape URL/path và scrape errors.
11. So sánh effective properties giữa dev và prod mà không xuất secret.
12. Viết integration test để phát hiện lỗi khi nâng Spring Boot/Spring AI/Micrometer.

**Câu hỏi tự kiểm tra:**

- MeterRegistry và ObservationRegistry khác nhau thế nào?
- ObservationHandler có vai trò gì trong việc tạo meter?
- Vì sao custom ObservationRegistry có thể khiến auto-configuration lùi lại?
- Vì sao có Actuator không có nghĩa Prometheus registry đã tồn tại?
- Nếu custom Counter xuất hiện nhưng VectorStore meter không có, nên kiểm tra gì tiếp?
- Khi /actuator/metrics có meter nhưng Prometheus không có, lỗi nằm ở tầng nào?
- Vì sao tracing exporter không thay thế metrics exporter?
- Tại sao cần kiểm tra active profile và runtime dependency tree?
- Vì sao _max không thể thay cho histogram p95?
- Làm thế nào kiểm chứng adapter thực sự phát Observation?

## 15. Checklist triển khai

- [ ] Có Actuator nếu cần management endpoints.
- [ ] Có Micrometer Core/Observation tương thích với Spring Boot BOM.
- [ ] Có registry implementation nếu cần export sang Prometheus/backend.
- [ ] Có đúng Spring AI VectorStore adapter và version hỗ trợ instrumentation.
- [ ] MeterRegistry được tạo và inject từ ApplicationContext mong muốn.
- [ ] ObservationRegistry được tạo và có MeterObservationHandler phù hợp.
- [ ] Không có custom bean vô tình làm auto-configuration back off.
- [ ] Không có property/profile disable observation hoặc metrics ngoài ý muốn.
- [ ] Đã chạy một VectorStore query fixture qua đúng adapter.
- [ ] Đã kiểm tra meter names thực tế qua Actuator.
- [ ] Đã kiểm tra exporter endpoint và Prometheus scrape target.
- [ ] Đã xác minh histogram buckets nếu dashboard cần p95/p99.
- [ ] Đã kiểm tra MeterFilter, endpoint security và network exposure.
- [ ] Có unit test cho MeterRegistry và Observation handler.
- [ ] Có integration test cho Spring AI VectorStore observation trong context thật.
- [ ] Có regression test sau khi nâng Spring Boot, Spring AI, Micrometer hoặc exporter.

## Tổng kết

Khi không thấy metric VectorStore, hãy tìm điểm đứt trong đường đi **VectorStore operation → Observation → ObservationRegistry → MeterObservationHandler → MeterRegistry → exporter → Actuator/scrape → metrics backend**. MeterRegistry và ObservationRegistry có vai trò khác nhau; có registry chưa đủ nếu handler không chuyển Observation thành meter. Tương tự, có meter trong process chưa đủ nếu thiếu exporter hoặc endpoint scrape không được expose.

Spring Boot auto-configuration phụ thuộc classpath, property, profile và bean hiện có. Một custom registry có thể khiến cấu hình mặc định lùi lại, còn dependency version lệch có thể gây lỗi runtime. Quy trình hiệu quả là kiểm tra dependency tree và condition report, xác nhận bean, chạy Counter probe và Observation probe, gọi query qua adapter thực, rồi lần lượt kiểm tra Actuator, Prometheus endpoint và scrape target. Khi có integration test cho toàn bộ đường đi, lỗi thiếu metrics sẽ dễ phát hiện ngay khi thay đổi cấu hình hoặc dependency.

## Tài liệu tham khảo

- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, registry và metrics auto-configuration.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): expose và bảo vệ management endpoints.
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): điều kiện và condition evaluation report.
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): Observation của ChatClient, ChatModel, EmbeddingModel và VectorStore.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): ObservationRegistry, handlers và context.
- [Micrometer — Meter Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html): MeterRegistry, composite registry và meter lifecycle.
- [Micrometer — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html): Prometheus registry và export.
- [Prometheus — Getting Started](https://prometheus.io/docs/prometheus/latest/getting_started/): scrape targets và metric collection.
