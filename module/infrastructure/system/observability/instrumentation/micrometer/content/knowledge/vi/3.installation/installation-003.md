# Phân biệt micrometer-core, micrometer-observation và các mô-đun registry

Micrometer được chia thành nhiều mô-đun để ứng dụng có thể sử dụng API đo lường, mô tả hoạt động cần quan sát và xuất dữ liệu đến hệ thống giám sát theo những nhu cầu riêng. Khi cài đặt, cần hiểu mỗi mô-đun đảm nhiệm phần nào để chọn dependency vừa đủ, tránh trộn lẫn API instrumentation với adapter của backend.

Ba nhóm quan trọng nhất là:

- **micrometer-core** cung cấp mô hình metrics và API để tạo, đăng ký, cập nhật meter.
- **micrometer-observation** cung cấp API mô tả vòng đời của một hoạt động cần quan sát, chẳng hạn một request hoặc một lần gọi dịch vụ.
- **Các mô-đun registry** kết nối meter của Micrometer với định dạng và giao thức của một hệ thống giám sát cụ thể, chẳng hạn Prometheus, OTLP, StatsD hoặc Datadog.

Các mô-đun này phối hợp với nhau. Trong ứng dụng Spring Boot, Spring Boot Actuator và cơ chế tự cấu hình có thể kết nối chúng để ứng dụng vừa ghi nhận số đo vừa công bố dữ liệu cho hệ thống giám sát.

## 1. Bản đồ các mô-đun Micrometer

| Nhóm | Thành phần tiêu biểu | Trách nhiệm |
| --- | --- | --- |
| Metrics API | micrometer-core | Định nghĩa Meter, MeterRegistry, Counter, Gauge, Timer, DistributionSummary, filter và các tiện ích đo lường. |
| Observation API | micrometer-observation | Mô tả một hoạt động bằng Observation, ObservationRegistry, context, convention, filter và handler. |
| Metrics registry | micrometer-registry-prometheus, micrometer-registry-otlp, micrometer-registry-statsd, micrometer-registry-datadog | Chuyển meter thành dữ liệu mà backend tương ứng có thể nhận hoặc scrape. |
| Tracing tích hợp | micrometer-tracing và các bridge tương ứng | Kết nối API tracing với thư viện hoặc hệ thống tracing cụ thể. Đây là nhóm riêng, có thể phối hợp với Observation. |

Không phải ứng dụng nào cũng cần khai báo trực tiếp tất cả các artifact. Một ứng dụng Spring Boot thường nhận phần lớn dependency nền tảng thông qua starter và chỉ cần bổ sung registry cho backend đã chọn. Ứng dụng Java độc lập có thể khai báo trực tiếp các mô-đun mà mã nguồn thực sự sử dụng.

## 2. micrometer-core: mô hình và API metrics

### Vai trò

micrometer-core là nền tảng đo lường của Micrometer. Nó cung cấp API trung lập với backend để mã ứng dụng ghi nhận số liệu. Mã nghiệp vụ làm việc với các khái niệm như meter và registry thay vì gọi API riêng của Prometheus, Datadog hoặc một nhà cung cấp khác.

Các kiểu meter phổ biến:

| Kiểu meter | Dùng khi nào | Ví dụ |
| --- | --- | --- |
| Counter | Đếm số lần một sự kiện xảy ra; giá trị tăng dần. | Số giao dịch được chấp nhận, số lần xử lý lỗi. |
| Gauge | Quan sát một giá trị có thể tăng hoặc giảm tại thời điểm lấy mẫu. | Độ dài hàng đợi, số kết nối đang hoạt động. |
| Timer | Đo thời lượng và số lần một thao tác được thực hiện. | Thời gian xử lý request, thời gian truy vấn cơ sở dữ liệu. |
| DistributionSummary | Ghi nhận phân bố của một đại lượng số không nhất thiết là thời gian. | Kích thước request, số byte được xử lý. |

Meter được đăng ký trong MeterRegistry. Registry quản lý meter, tên, đơn vị, tag và cách cung cấp dữ liệu cho hệ thống đích. Core cũng cung cấp các thành phần như SimpleMeterRegistry để kiểm thử hoặc sử dụng trong trường hợp không cần xuất dữ liệu ra backend, CompositeMeterRegistry để phối hợp nhiều registry, cùng các cơ chế lọc và tùy biến meter.

### Ví dụ tạo meter

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class CheckoutMetrics {

    private final Counter completedCheckouts;

    public CheckoutMetrics(MeterRegistry registry) {
        this.completedCheckouts = Counter.builder("checkout.completed")
                .description("Number of completed checkouts")
                .tag("channel", "web")
                .register(registry);
    }

    public void markCompleted() {
        completedCheckouts.increment();
    }
}
~~~

Trong ví dụ, mã ứng dụng chỉ phụ thuộc vào API của core. Nó không cần biết registry đang ghi dữ liệu vào Prometheus hay một backend khác. Registry được Spring Boot hoặc cấu hình ứng dụng cung cấp thông qua MeterRegistry.

Nên đăng ký meter một lần và tái sử dụng, ví dụ trong constructor của bean. Tránh tạo meter với tên hoặc tag-value mới cho mỗi request. Mỗi tổ hợp tên meter và tag-value có thể tạo một chuỗi thời gian riêng ở backend; tạo meter liên tục với tag có giá trị biến thiên sẽ làm cardinality tăng nhanh.

## 3. micrometer-observation: mô tả hoạt động cần quan sát

### Vì sao có Observation API?

Metrics API phù hợp khi lập trình viên đã biết rõ cần ghi nhận meter nào và cách cập nhật nó. Tuy nhiên, một hoạt động như xử lý thanh toán thường có nhiều khía cạnh cần quan sát: thời gian bắt đầu và kết thúc, trạng thái thành công hoặc lỗi, thông tin ngữ cảnh, metric tổng hợp và trace liên quan.

Observation API cung cấp một mô hình chung để mô tả vòng đời của hoạt động đó. Mã nghiệp vụ tạo một Observation, bổ sung thông tin ngữ cảnh và thực thi thao tác trong phạm vi Observation. Các ObservationHandler đã đăng ký sẽ nhận sự kiện bắt đầu, lỗi và kết thúc để chuyển thông tin sang hệ thống tương ứng.

Các khái niệm chính:

- **Observation** đại diện cho một hoạt động cần quan sát, có tên và vòng đời.
- **ObservationRegistry** quản lý cấu hình và các handler được áp dụng khi tạo Observation.
- **Observation.Context** giữ dữ liệu ngữ cảnh trong suốt vòng đời hoạt động.
- **ObservationConvention** chuẩn hóa tên và các key-value của một loại Observation.
- **ObservationFilter** cho phép điều chỉnh context trước khi handler xử lý.
- **ObservationHandler** nhận các sự kiện vòng đời và chuyển chúng thành đầu ra, ví dụ metrics hoặc tracing.

Observation không phải một registry metrics và bản thân việc tạo Observation không có nghĩa dữ liệu đã được gửi đến Prometheus. Cần có handler phù hợp để chuyển Observation sang metrics, tracing hoặc đầu ra khác.

### Ví dụ quan sát một thao tác

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final ObservationRegistry observationRegistry;
    private final PaymentGateway paymentGateway;

    public PaymentService(
            ObservationRegistry observationRegistry,
            PaymentGateway paymentGateway) {
        this.observationRegistry = observationRegistry;
        this.paymentGateway = paymentGateway;
    }

    public PaymentResult pay(String paymentMethod, PaymentCommand command) {
        return Observation.createNotStarted("payment.process", observationRegistry)
                .lowCardinalityKeyValue("payment.method", paymentMethod)
                .observe(() -> paymentGateway.charge(command));
    }
}
~~~

Đoạn mã tạo một Observation tên payment.process, gắn thông tin payment.method và thực thi lời gọi cổng thanh toán trong phạm vi quan sát. Phương thức observe quản lý vòng đời bắt đầu và kết thúc, kể cả khi thao tác phát sinh lỗi.

Trong ứng dụng Spring Boot có hỗ trợ Observation, ObservationRegistry thường được tự cấu hình và có thể được inject vào bean. Các handler tương ứng có thể được Spring Boot cấu hình dựa trên những dependency đã có. Với ứng dụng độc lập, lập trình viên cần tạo ObservationRegistry và đăng ký các handler mong muốn.

### Low-cardinality và high-cardinality key-value

Observation phân biệt hai nhóm key-value:

- **Low-cardinality** dành cho các giá trị có tập hợp hữu hạn và ổn định, phù hợp để chuyển thành label của metrics. Ví dụ: phương thức HTTP, loại thao tác hoặc kết quả thành công/thất bại.
- **High-cardinality** dành cho giá trị có thể biến thiên rất nhiều, thường hữu ích với trace. Ví dụ: mã request hoặc định danh tài nguyên.

Không nên đưa user ID, order ID, email, token hoặc URL chứa định danh vào low-cardinality key-value. Nếu handler metrics chuyển những giá trị này thành label, số lượng time series có thể tăng rất lớn. High-cardinality cũng cần được cân nhắc về quyền riêng tư và chi phí lưu trữ ở hệ thống tracing.

## 4. Các mô-đun registry: kết nối với backend metrics

### Registry giải quyết vấn đề gì?

Core định nghĩa cách ứng dụng tạo và cập nhật meter, nhưng mỗi hệ thống giám sát có định dạng dữ liệu, giao thức và cơ chế thu thập riêng. Registry là adapter thực hiện phần chuyển đổi đó.

Ví dụ:

| Artifact | Hệ thống đích hoặc giao thức | Đặc điểm tích hợp |
| --- | --- | --- |
| micrometer-registry-prometheus | Prometheus | Cung cấp endpoint exposition để Prometheus scrape theo mô hình pull. |
| micrometer-registry-otlp | OpenTelemetry Protocol (OTLP) | Xuất metrics theo giao thức OTLP đến collector hoặc backend tương thích. |
| micrometer-registry-statsd | StatsD | Gửi số đo theo giao thức StatsD đến agent hoặc dịch vụ nhận dữ liệu. |
| micrometer-registry-datadog | Datadog | Xuất metrics theo cơ chế tích hợp của Datadog. |
| micrometer-registry-influx | InfluxDB | Xuất dữ liệu theo định dạng mà InfluxDB tiếp nhận. |
| micrometer-registry-graphite | Graphite | Chuyển meter thành chuỗi metric theo quy ước Graphite. |
| micrometer-registry-jmx | JMX | Cho phép quan sát meter qua JMX trong môi trường Java. |

Đây là các ví dụ phổ biến, không phải danh sách đầy đủ. Tên artifact, giao thức và khả năng cụ thể có thể thay đổi theo phiên bản Micrometer. Cần chọn registry theo backend thực tế và tài liệu của phiên bản đang sử dụng.

### Ví dụ registry Prometheus

Trong Spring Boot, khi có Actuator và registry Prometheus tương thích trên classpath, Spring Boot có thể tự cấu hình PrometheusMeterRegistry và endpoint /actuator/prometheus. Prometheus sẽ chủ động truy cập endpoint này theo chu kỳ scrape.

Một ứng dụng Java không dùng Spring Boot có thể tạo registry trực tiếp:

~~~java
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import io.micrometer.prometheusmetrics.PrometheusConfig;

PrometheusMeterRegistry registry =
        new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);

String exposition = registry.scrape();
System.out.println(exposition);
~~~

API và package của Prometheus registry phụ thuộc thế hệ artifact và phiên bản Micrometer. Ví dụ trên minh họa cách tạo registry ở các phiên bản dùng Prometheus client mới; nếu dự án đang dùng phiên bản cũ, hãy dùng API được tài liệu của phiên bản đó công bố. Trong ứng dụng Spring Boot, thông thường không cần tự khởi tạo registry vì auto-configuration đảm nhiệm việc này.

### Một hay nhiều registry?

Một ứng dụng có thể cần xuất metrics đến nhiều backend. CompositeMeterRegistry cho phép một meter được ghi nhận qua nhiều registry thành phần. Tuy nhiên, mỗi đích xuất làm tăng số kết nối, cấu hình và chi phí vận hành. Chỉ thêm registry khi có nhu cầu giám sát cụ thể và đã xác định nơi tiếp nhận dữ liệu.

Không cần khai báo mọi registry chỉ để giữ mã ứng dụng độc lập với backend. Chọn registry tại lớp triển khai hoặc cấu hình runtime, trong khi mã nghiệp vụ tiếp tục dùng API của core.

## 5. Cách ba nhóm phối hợp

~~~mermaid
flowchart LR
    A[Code nghiệp vụ] --> B[Micrometer Observation]
    A --> C[Micrometer Core API]
    B --> D[ObservationRegistry]
    D --> E[ObservationHandler]
    E --> C
    C --> F[MeterRegistry]
    F --> G[Registry adapter]
    G --> H[Prometheus / OTLP / StatsD / Backend]
~~~

Có thể đọc luồng này theo hai cách:

1. Khi mã cần ghi một số đo cụ thể, nó gọi trực tiếp API của micrometer-core, ví dụ tăng Counter hoặc ghi nhận Timer.
2. Khi mã cần bao quanh một hoạt động có vòng đời và ngữ cảnh, nó tạo Observation. Các handler nhận sự kiện từ Observation và có thể chuyển hoạt động đó thành metrics thông qua core, thành trace thông qua tracing integration hoặc thành đầu ra khác.

Sau đó, MeterRegistry và registry adapter xử lý việc cung cấp metrics cho backend. Observation và core có thể được sử dụng cùng nhau; Observation không thay thế metrics API và registry cũng không thay thế Observation.

## 6. Chọn dependency theo loại ứng dụng

### Ứng dụng Spring Boot

Với dự án Gradle đã dùng Spring Boot dependency management, ví dụ tích hợp Prometheus:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Starter Actuator tích hợp hệ sinh thái metrics và quản trị của Spring Boot. Registry Prometheus cung cấp adapter cần thiết để xuất metrics theo định dạng Prometheus. Spring Boot dependency management nên quản lý phiên bản tương thích của các dependency Micrometer.

Nếu mã nguồn trực tiếp import API của Observation hoặc Metrics, các artifact tương ứng thường đã được đưa vào qua dependency của starter. Hãy kiểm tra dependency tree trước khi khai báo trùng lặp. Nếu dự án không dùng starter hoặc muốn khai báo rõ API mà module của mình phụ thuộc, có thể thêm trực tiếp micrometer-core hoặc micrometer-observation.

Ví dụ khi dùng registry khác, thay artifact Prometheus bằng registry tương ứng, chẳng hạn micrometer-registry-otlp hoặc micrometer-registry-statsd. Không thêm nhiều registry nếu ứng dụng chỉ gửi metrics đến một backend.

### Ứng dụng Java độc lập

Một ứng dụng không dùng Spring Boot có thể khai báo rõ các mô-đun cần thiết. Ví dụ Gradle với BOM của Micrometer:

~~~groovy
dependencies {
    implementation(platform("io.micrometer:micrometer-bom:$micrometerVersion"))

    implementation("io.micrometer:micrometer-core")
    implementation("io.micrometer:micrometer-observation")
    implementation("io.micrometer:micrometer-registry-prometheus")
}
~~~

Trong ví dụ, micrometerVersion là phiên bản BOM được dự án quản lý ở nơi khác. BOM giúp các artifact Micrometer sử dụng phiên bản tương thích với nhau. Nếu mã nguồn trực tiếp khởi tạo lớp của một registry, dependency đó cần nằm trên compile classpath; khi registry chỉ được phát hiện và cấu hình lúc chạy, runtimeOnly có thể phù hợp.

Với Maven, có thể import BOM và khai báo các artifact tương tự:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-bom</artifactId>
            <version>${micrometer.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-core</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-observation</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Nếu dự án đã dùng Spring Boot parent hoặc BOM, hãy để dependency management của Spring Boot kiểm soát phiên bản Micrometer thay vì import thêm một BOM Micrometer khác mà không có lý do. Trộn các phiên bản không tương thích có thể gây lỗi runtime hoặc lỗi liên kết class.

### Khi nào cần micrometer-tracing?

Observation API có thể là điểm tích hợp chung cho metrics và tracing, nhưng micrometer-observation không phải toàn bộ hệ thống tracing. Khi cần tạo và xuất distributed trace, ứng dụng còn cần các thành phần tracing phù hợp, chẳng hạn API micrometer-tracing, bridge tương ứng với Brave hoặc OpenTelemetry, và exporter hoặc agent để chuyển trace đến backend.

Chọn các dependency tracing theo hệ thống đích và phiên bản Spring Boot/Micrometer. Không thêm bridge tracing nếu mục tiêu hiện tại chỉ là xuất metrics.

## 7. Chọn mô-đun nào cho từng nhu cầu?

| Nhu cầu | Thành phần nên dùng | Lý do |
| --- | --- | --- |
| Đếm số đơn hàng thành công | micrometer-core | Counter thể hiện số lần sự kiện xảy ra. |
| Đo thời gian xử lý một phương thức | micrometer-core hoặc Observation với metrics handler | Timer ghi nhận thời lượng; Observation phù hợp khi cần quản lý vòng đời thao tác chung. |
| Theo dõi một request xuyên qua nhiều lớp | micrometer-observation | Observation mang context và vòng đời xuyên suốt thao tác. |
| Xuất metrics cho Prometheus | micrometer-registry-prometheus | Adapter chuyển meter thành định dạng Prometheus. |
| Gửi metrics theo OTLP | micrometer-registry-otlp | Adapter xuất theo giao thức OTLP. |
| Gửi metrics đến StatsD | micrometer-registry-statsd | Adapter giao tiếp theo giao thức StatsD. |
| Tạo distributed trace | Observation kết hợp micrometer-tracing và bridge phù hợp | Observation cung cấp điểm tích hợp; tracing bridge và exporter đảm nhiệm phần tracing cụ thể. |

Một quy tắc lựa chọn thực tế: xác định trước loại tín hiệu cần thu thập, API phù hợp để ghi nhận tín hiệu đó, rồi mới chọn adapter hoặc backend cần nhận dữ liệu.

## 8. Kiểm tra dependency và xác minh cài đặt

Sau khi khai báo dependency, hãy kiểm tra dependency graph để xác định phiên bản thực tế và phát hiện artifact bị kéo vào nhiều phiên bản.

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-observation --configuration runtimeClasspath
~~~

Trên Windows PowerShell có thể dùng:

~~~powershell
.\gradlew dependencies --configuration runtimeClasspath
.\gradlew dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
.\gradlew dependencyInsight --dependency micrometer-observation --configuration runtimeClasspath
~~~

Một số kiểm tra cơ bản:

1. Xác nhận ứng dụng biên dịch được khi import các API Micrometer cần dùng.
2. Kiểm tra runtime classpath có registry adapter đã chọn.
3. Khởi động ứng dụng và xác nhận Spring Boot tạo được MeterRegistry tương ứng.
4. Với Prometheus, gọi endpoint /actuator/prometheus và xác nhận có nội dung exposition.
5. Ghi một meter thử nghiệm hoặc thực hiện thao tác nghiệp vụ để xác nhận số đo thay đổi như dự kiến.
6. Nếu dùng Observation, xác nhận ObservationRegistry tồn tại và handler cần thiết đã được cấu hình.

Trong kiểm thử đơn vị, SimpleMeterRegistry hữu ích để xác minh Counter, Gauge hoặc Timer mà không cần chạy một backend giám sát thực tế. Với kiểm thử tích hợp, có thể khởi động ứng dụng và kiểm tra endpoint hoặc dữ liệu do registry xuất ra.

## 9. Lỗi cài đặt thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy lớp MeterRegistry hoặc Counter khi biên dịch | Thiếu micrometer-core hoặc dependency quản lý chưa đưa core vào compile classpath. | Kiểm tra dependency tree và khai báo core nếu module trực tiếp sử dụng API này. |
| Không tìm thấy lớp Observation hoặc ObservationRegistry | Thiếu micrometer-observation trên compile classpath hoặc phiên bản Micrometer không cung cấp API tương ứng. | Kiểm tra phiên bản và khai báo dependency trực tiếp khi cần. |
| Ứng dụng không tạo được PrometheusMeterRegistry | Thiếu registry Prometheus, phiên bản không tương thích hoặc đang import API khác thế hệ. | Kiểm tra artifact, BOM và dependency insight. |
| Endpoint /actuator/prometheus trả về 404 | Chưa có registry Prometheus, endpoint chưa được expose hoặc base path đã thay đổi. | Kiểm tra dependency, cấu hình Actuator và đường dẫn. |
| Có meter trong ứng dụng nhưng backend không nhận dữ liệu | Registry chưa được cấu hình, endpoint không truy cập được hoặc backend chưa scrape/nhận dữ liệu. | Kiểm tra cấu hình registry, network và trạng thái thu thập ở backend. |
| Lỗi NoSuchMethodError hoặc NoClassDefFoundError | Các artifact Micrometer hoặc thư viện backend dùng phiên bản không tương thích. | Dùng BOM hoặc dependency management thống nhất; kiểm tra dependency tree. |
| Có nhiều time series ngoài dự kiến | Tag hoặc low-cardinality key-value nhận quá nhiều giá trị khác nhau. | Chuẩn hóa tập giá trị, tránh đưa định danh biến thiên vào label metrics. |

## 10. Những nhầm lẫn cần tránh

- **Core không phải registry backend.** Core định nghĩa API và meter; registry adapter quyết định cách xuất dữ liệu đến hệ thống đích.
- **Observation không tự động đồng nghĩa với metrics.** Observation mô tả hoạt động và phát sự kiện vòng đời; handler mới chuyển dữ liệu sang metrics, tracing hoặc đầu ra khác.
- **Registry không thay thế instrumentation.** Registry không tự biết nghiệp vụ cần đo gì; ứng dụng hoặc instrumentation tích hợp phải tạo meter hay Observation.
- **Actuator không phải một registry.** Actuator là phần tích hợp quản trị của Spring Boot, cung cấp endpoint và kết nối với registry được cấu hình.
- **Không nên tự ghim phiên bản rời rạc cho từng artifact.** Hãy dùng Spring Boot dependency management hoặc Micrometer BOM để đồng bộ các mô-đun.
- **Không cần thêm mọi registry vào classpath.** Mỗi registry bổ sung một adapter và cấu hình vận hành; chỉ cài những backend thực sự được sử dụng.

Khi phân định đúng vai trò, mã nghiệp vụ có thể tiếp tục sử dụng API ổn định của Micrometer, trong khi lớp triển khai quyết định registry và backend phù hợp. Cách tổ chức này giúp thay đổi hệ thống giám sát mà không phải viết lại toàn bộ instrumentation trong ứng dụng.
