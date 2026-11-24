# Chọn hỗ trợ Micrometer của Reactor theo phiên bản đang dùng

Project Reactor có tích hợp metrics cho Flux, Mono và Scheduler. Cách tích hợp đã thay đổi từ Reactor 3.5.0: các API cũ nằm trong reactor-core được đánh dấu deprecated và module riêng reactor-core-micrometer cung cấp API mới dựa trên tap, registry truyền tường minh và Micrometer Observation.

Vì vậy, trước khi thêm dependency hoặc sao chép ví dụ, cần xác định phiên bản reactor-core thực tế mà ứng dụng đang chạy. Chọn sai API có thể khiến code không biên dịch, tiếp tục dùng API deprecated hoặc tạo hai lớp instrumentation cùng đo một pipeline.

## 1. Xác định phiên bản Reactor trước tiên

Phiên bản được khai báo trực tiếp trong pom.xml hoặc build.gradle chưa chắc là phiên bản cuối cùng trên runtime classpath. Spring Boot, Reactor BOM hoặc một dependency khác có thể quản lý và ghi đè phiên bản.

Hãy kiểm tra dependency đã được resolve:

~~~bash
mvn dependency:tree -Dincludes=io.projectreactor:reactor-core,io.projectreactor:reactor-core-micrometer,io.micrometer
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency reactor-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-core-micrometer --configuration runtimeClasspath
~~~

Trên Windows PowerShell, dùng .\gradlew thay cho ./gradlew nếu cần. Kiểm tra runtimeClasspath vì compile classpath có thể khác cấu hình đóng gói hoặc chạy ứng dụng.

Không chỉ nhìn phiên bản Spring Boot rồi suy ra Reactor. Hãy đọc kết quả dependency resolution để biết chính xác reactor-core và reactor-core-micrometer nào được đưa vào ứng dụng.

## 2. Bảng chọn API theo phiên bản

| Phiên bản Reactor Core | Hướng tích hợp | API chính | Khuyến nghị |
| --- | --- | --- | --- |
| 3.4.x và cũ hơn | Tích hợp cũ nằm trong reactor-core. | Flux.metrics(), Mono.metrics(), Schedulers.enableMetrics(), Metrics.MicrometerConfiguration. | Dùng để duy trì ứng dụng cũ; Micrometer phải có trên classpath. |
| 3.5.0 | Module reactor-core-micrometer được giới thiệu. | tap(Micrometer.metrics(registry)), tap(Micrometer.observation(observationRegistry)), Micrometer.timedScheduler(...). | Chọn module mới cho instrumentation mới; API cũ đã deprecated. |
| 3.6.x trở lên | Tiếp tục dùng module reactor-core-micrometer. | Micrometer.metrics, Micrometer.observation và Micrometer.timedScheduler. | Không thiết kế code mới dựa trên API cũ; kiểm tra Javadoc đúng phiên bản. |
| Các bản Reactor hiện hành | Module mới vẫn là hướng tích hợp được tài liệu khuyến nghị. | API trong reactor-core-micrometer tương ứng release train. | Dùng BOM và kiểm tra API thực tế khi nâng cấp. |

Module reactor-core-micrometer được giới thiệu cùng release train 2022.0 và Reactor 3.5.0. Từ mốc này, Flux.metrics(), Mono.metrics(), Schedulers.enableMetrics() và reactor.util.Metrics được đánh dấu deprecated để chuyển sang API mới.

Một số Javadoc vẫn liệt kê API cũ ở các phiên bản mới hơn dù đã ghi chú dự kiến loại bỏ từ sớm nhất ở 3.6.0. Vì vậy, không nên khẳng định các phương thức đó chắc chắn đã bị xóa trong mọi phiên bản 3.6 trở lên. Hãy kiểm tra Javadoc và compile với đúng phiên bản ứng dụng đang dùng; dù còn tồn tại, API deprecated vẫn không phải lựa chọn cho code mới.

## 3. Reactor 3.4.x: tích hợp cũ trong reactor-core

Ở các phiên bản trước 3.5.0, Reactor cung cấp operator metrics trực tiếp trên Flux và Mono. Ví dụ:

~~~java
import reactor.core.publisher.Flux;

public class LegacyReactorMetrics {

    public void run() {
        Flux.range(1, 10)
                .name("legacy.range")
                .metrics()
                .blockLast();
    }
}
~~~

Operator name đặt tên cho sequence; metrics bật việc thu thập các phép đo tại vị trí đó. Nếu không đặt name, Reactor dùng tiền tố mặc định reactor.

Tích hợp cũ dựa vào Micrometer facade có mặt trên classpath. Nếu thiếu Micrometer, operator metrics có thể hoạt động như no-op: pipeline vẫn chạy nhưng không có metric được ghi nhận. Vì vậy, chỉ nhìn thấy code .metrics() không chứng minh rằng dữ liệu đang được xuất.

Trong phiên bản cũ, registry được cấu hình qua global registry của Reactor:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import reactor.util.Metrics;

public class LegacyRegistryConfiguration {

    public void configure(MeterRegistry registry) {
        Metrics.MicrometerConfiguration.useRegistry(registry);
    }
}
~~~

Cách này dùng cấu hình tĩnh toàn cục. Nó khiến việc kiểm soát registry theo từng pipeline hoặc từng ứng dụng khó rõ ràng hơn, đặc biệt trong test và ứng dụng có nhiều registry.

### Metric của Scheduler trong phiên bản cũ

Với Reactor 3.4.x, scheduler metrics được bật bằng:

~~~java
import reactor.core.scheduler.Schedulers;

public class LegacySchedulerMetrics {

    public void enable() {
        Schedulers.enableMetrics();
    }
}
~~~

Nên gọi phương thức này trước khi các Scheduler cần đo được tạo. Cơ chế cũ áp dụng decorator lên các ExecutorService đứng sau nhiều Scheduler. Nó có phạm vi toàn cục và có thể công bố dữ liệu từ các scheduler không cần theo dõi.

Nếu ứng dụng đang ở Reactor 3.4.x, hãy dùng API được tài liệu đúng phiên bản hỗ trợ. Khi có kế hoạch nâng lên 3.5+, chuyển dần sang reactor-core-micrometer thay vì mang cách cấu hình global registry sang phiên bản mới.

## 4. Reactor 3.5.0+: thêm module reactor-core-micrometer

Từ Reactor 3.5.0, phần hỗ trợ Micrometer được tách thành artifact riêng:

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-core-micrometer</artifactId>
</dependency>
~~~

Module này cung cấp entry point Micrometer và yêu cầu truyền registry tường minh. Nó không dựa vào một global MeterRegistry được cấu hình ẩn bên trong Reactor.

Với Maven, có thể dùng Reactor BOM để quản lý các artifact tương thích:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-bom</artifactId>
            <version>${reactor.bom.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-core</artifactId>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-core-micrometer</artifactId>
    </dependency>
</dependencies>
~~~

Khai báo property reactor.bom.version trong pom.xml hoặc thay placeholder bằng release train GA đã chọn. Trong ví dụ Gradle, khai báo reactorBomVersion trong gradle.properties hoặc thay bằng version cụ thể. Không dùng snapshot/milestone trong production nếu chưa có chủ đích.

Với Gradle:

~~~kotlin
dependencies {
    implementation(platform("io.projectreactor:reactor-bom:$reactorBomVersion"))
    implementation("io.projectreactor:reactor-core")
    implementation("io.projectreactor:reactor-core-micrometer")
}
~~~

Thay reactorBomVersion bằng release train tương thích với phiên bản Reactor mà dự án chọn. BOM quản lý một nhóm artifact có thể mang số phiên bản khác nhau; không giả định reactor-core-micrometer luôn có cùng số version với reactor-core.

Nếu ứng dụng đã dùng Spring Boot dependency management, kiểm tra xem BOM hiện tại có quản lý artifact reactor-core-micrometer hay không. Không thêm một BOM thứ hai một cách máy móc vì nó có thể ghi đè phiên bản Reactor mà Spring Boot đã chọn. Có thể dùng dependency management hiện có nếu nó quản lý đầy đủ; nếu không, chọn version tương thích có chủ đích và xác minh bằng dependency tree.

## 5. Đo Publisher bằng Micrometer.metrics

API Micrometer.metrics dùng tap để gắn SignalListener vào reactive sequence:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import reactor.core.observability.micrometer.Micrometer;
import reactor.core.publisher.Flux;

public class ReactorPublisherMetrics {

    private final MeterRegistry registry;

    public ReactorPublisherMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public Flux<Integer> numbers() {
        return Flux.range(1, 100)
                .name("orders.processing")
                .tag("source", "api")
                .tap(Micrometer.metrics(registry));
    }
}
~~~

Tên và tag được đặt trước tap để listener có thể nhận diện metadata của sequence. Nếu không đặt name, module dùng tiền tố mặc định reactor. Với hệ thống metrics yêu cầu schema tag nhất quán, hãy đặt tên rõ ràng và giữ cùng tập tag cho mọi series có cùng tên.

MeterRegistry được truyền trực tiếp vào Micrometer.metrics. Điều này làm rõ metric được ghi vào registry nào, thuận tiện cho ứng dụng có nhiều backend và cho kiểm thử với SimpleMeterRegistry.

Các metric do listener tạo ra mô tả vòng đời và tín hiệu của sequence, ví dụ thời lượng từ subscription đến termination/cancellation, độ trễ giữa các onNext và lượng request. Tên và kiểu meter cụ thể phụ thuộc phiên bản module; tham khảo danh sách meters của đúng phiên bản thay vì hard-code dashboard theo tài liệu khác release.

### Đặt tap đúng phạm vi cần đo

tap quan sát các tín hiệu đi qua vị trí của nó trong pipeline. Vì vậy, vị trí đặt tap quyết định đoạn sequence mà listener quan sát.

~~~java
Flux<Order> flow = orderSource()
        .name("orders.enrichment")
        .tag("stage", "enrichment")
        .tap(Micrometer.metrics(registry))
        .map(this::enrich)
        .flatMap(this::persist);
~~~

Trong ví dụ, instrumentation được gắn ở một vị trí cụ thể của chuỗi. Nếu mục tiêu là đo toàn bộ quá trình enrich và persist, hãy đặt tap tại vị trí bao quanh đúng phạm vi đó theo chiều tín hiệu của Reactor. Có thể dùng nhiều tên sequence cho các giai đoạn khác nhau, nhưng cần kiểm soát số meter và ý nghĩa từng phạm vi.

## 6. Chọn Micrometer.metrics hay Micrometer.observation

Module mới có hai cách gắn instrumentation phổ biến:

| API | Đầu vào | Mục tiêu | Đặc điểm |
| --- | --- | --- | --- |
| Micrometer.metrics(registry) | MeterRegistry | Thu thập bộ metrics cụ thể của Reactor publisher. | Cung cấp các meter về tín hiệu và vòng đời sequence. |
| Micrometer.observation(observationRegistry) | ObservationRegistry | Quan sát vòng đời một reactive chain theo mô hình Micrometer Observation. | Có thể tạo metrics, tracing span hoặc các handler khác tùy cấu hình. |

Ví dụ dùng Observation:

~~~java
import io.micrometer.observation.ObservationRegistry;
import reactor.core.observability.micrometer.Micrometer;
import reactor.core.publisher.Mono;

public class ReactorObservation {

    private final ObservationRegistry observationRegistry;

    public ReactorObservation(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public Mono<String> loadOrder() {
        return Mono.fromSupplier(() -> "order-123")
                .name("orders.load")
                .tap(Micrometer.observation(observationRegistry));
    }
}
~~~

ObservationRegistry là registry của Micrometer Observation, không phải MeterRegistry. Đừng truyền MeterRegistry vào phương thức observation hoặc ngược lại.

Observation phù hợp khi ứng dụng muốn dùng một điểm quan sát chung cho metrics, tracing và các handler liên quan. Việc nó tạo timer, span hoặc dữ liệu khác phụ thuộc ObservationHandler và cấu hình runtime. Chỉ thêm tap observation không tự động bảo đảm backend tracing hay metrics đã được cấu hình.

Micrometer.metrics và Micrometer.observation không tạo cùng một tập meter. Metrics tap cung cấp góc nhìn chi tiết về tín hiệu; Observation tập trung vào vòng đời của toàn bộ operation được quan sát. Chọn theo câu hỏi vận hành và tránh gắn cả hai vào cùng phạm vi chỉ vì muốn có nhiều metric hơn.

## 7. Theo dõi Scheduler bằng Micrometer.timedScheduler

Scheduler là thành phần quan trọng trong ứng dụng Reactor vì nó quyết định công việc bất đồng bộ được lập lịch và thực thi ở đâu. Module mới cung cấp Micrometer.timedScheduler để bọc một Scheduler cụ thể:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import reactor.core.observability.micrometer.Micrometer;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public class SchedulerInstrumentation {

    public Scheduler create(MeterRegistry registry) {
        Scheduler original = Schedulers.newParallel("orders-worker", 4);

        return Micrometer.timedScheduler(
                original,
                registry,
                "orders.worker",
                Tags.of("role", "order-processing"));
    }
}
~~~

Đối số đầu là Scheduler cần bọc; đối số thứ hai là MeterRegistry; đối số thứ ba là prefix của các meter; đối số cuối là tag bổ sung tùy chọn.

Chỉ các task được submit thông qua Scheduler wrapper trả về từ timedScheduler mới được đo. Nếu code tiếp tục submit trực tiếp vào original Scheduler, các task đó không đi qua wrapper và sẽ không được tính bởi instrumentation này.

Đây là lựa chọn có chủ đích: ứng dụng chọn Scheduler nào cần theo dõi và registry nào nhận dữ liệu. Nó tránh việc bật metrics toàn cục cho mọi executor như cách cũ.

Giữ reference đến Scheduler wrapper và quản lý dispose theo vòng đời của ứng dụng. Nếu wrapper dùng chung một Scheduler gốc, cần thống nhất component nào sở hữu và đóng Scheduler để không dispose tài nguyên khi nơi khác còn sử dụng.

## 8. Thay Schedulers.enableMetrics bằng timedScheduler

Trong code cũ, ứng dụng có thể gọi:

~~~java
Schedulers.enableMetrics();
~~~

Phương thức này đã deprecated từ Reactor 3.5.0. Hướng thay thế là bọc riêng Scheduler bằng Micrometer.timedScheduler và truyền MeterRegistry cùng prefix.

Không thay bằng một wrapper rồi vẫn gọi Schedulers.enableMetrics ở nơi khác cho cùng mục đích. Làm vậy có thể tạo hai cơ chế instrumentation, khó phân biệt nguồn meter và tăng số series hoặc ghi nhận trùng.

Nếu cần theo dõi nhiều Scheduler, tạo wrapper cho từng Scheduler với prefix và tag riêng:

~~~java
Scheduler ioScheduler = Micrometer.timedScheduler(
        Schedulers.newBoundedElastic(8, 1000, "io"),
        registry,
        "application.io",
        Tags.of("workload", "blocking-io"));

Scheduler cpuScheduler = Micrometer.timedScheduler(
        Schedulers.newParallel("cpu", 4),
        registry,
        "application.cpu",
        Tags.of("workload", "cpu"));
~~~

Prefix và tag nên phản ánh vai trò ổn định. Không tạo prefix từ request ID, tenant ID hoặc tên người dùng.

## 9. Tên sequence và tag phải ổn định

Reactor có thể phát hiện metadata từ name và tag operators ở upstream của tap. Ví dụ:

~~~java
source()
        .name("payment.authorize")
        .tag("provider", "primary")
        .tag("operation", "authorize")
        .tap(Micrometer.metrics(registry));
~~~

Nên dùng tên biểu diễn operation hoặc pipeline, chẳng hạn:

- orders.load
- orders.enrichment
- payment.authorize
- inventory.reserve
- events.consume

Tag phù hợp thường có tập giá trị hữu hạn:

- provider: primary, backup.
- operation: authorize, capture, refund.
- source: api, scheduler, message.
- result: success, error, cancelled.

Không đưa URL đầy đủ, order ID, user ID, request ID hoặc nội dung exception vào tag. Các giá trị đó tạo cardinality cao và làm backend metrics tăng chi phí lưu trữ.

Một số backend yêu cầu tất cả series có cùng tên metric phải có tập label nhất quán. Nếu pipeline cùng dùng tên nhưng một nhánh thêm tag khác nhánh còn lại, dữ liệu có thể khó tổng hợp hoặc bị backend từ chối. Hãy chuẩn hóa tag schema theo operation.

## 10. Phân biệt metrics và Observation trong kiến trúc Spring

Trong ứng dụng Spring Boot, MeterRegistry thường được cấu hình cùng Micrometer registry exporter. ObservationRegistry có thể được cấu hình bởi Spring Boot Actuator và Observation auto-configuration nếu các dependency tương ứng có mặt.

Hãy kiểm tra bean thực tế thay vì tự tạo một registry toàn cục:

- Dùng MeterRegistry được inject cho Micrometer.metrics.
- Dùng ObservationRegistry được inject cho Micrometer.observation.
- Giữ cấu hình naming/tag nhất quán giữa các reactive pipeline.
- Kiểm tra ObservationHandler nếu muốn Observation tạo timer hoặc tracing span.
- Kiểm tra exporter và endpoint để xác nhận meter thực sự được xuất.

Không cần tự gọi Metrics.MicrometerConfiguration.useRegistry trong code mới. API đó thuộc tích hợp cũ và không cấu hình registry cho reactor-core-micrometer.

## 11. Quản lý phiên bản Micrometer đi cùng Reactor

reactor-core-micrometer có dependency vào Micrometer. Hãy để dependency management của dự án chọn các phiên bản tương thích giữa Reactor, Micrometer Core và Micrometer Observation.

Các nguyên tắc:

1. Dùng Reactor BOM phù hợp với release train của reactor-core.
2. Không tự suy ra version của reactor-core-micrometer từ version reactor-core.
3. Không nâng riêng Micrometer lên một major/minor khác nếu chưa kiểm tra compatibility với Reactor và Spring Boot.
4. Kiểm tra dependency tree để phát hiện nhiều phiên bản Micrometer hoặc Reactor cùng xuất hiện.
5. Nếu dùng Spring Boot, ưu tiên bộ phiên bản mà Boot quản lý trừ khi có lý do rõ ràng để override.

Khi gặp lỗi NoSuchMethodError hoặc NoClassDefFoundError trong Micrometer/Reactor instrumentation, hãy kiểm tra runtime dependency resolution trước. Lỗi có thể do compile với API của một version nhưng runtime lại nạp version khác.

## 12. Kiểm thử publisher instrumentation

Có thể dùng SimpleMeterRegistry để xác minh tap tạo meter sau khi sequence được subscribe và kết thúc:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import reactor.core.observability.micrometer.Micrometer;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ReactorMetricsTest {

    @Test
    void recordsPublisherMetrics() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        Flux<Integer> measured = Flux.range(1, 3)
                .name("numbers")
                .tap(Micrometer.metrics(registry));

        StepVerifier.create(measured)
                .expectNext(1, 2, 3)
                .verifyComplete();

        assertThat(registry.find("numbers.flow.duration").summary())
                .isNotNull();
    }
}
~~~

Test cần dependency reactor-test ở test scope. Nếu tên hoặc loại meter thay đổi giữa các phiên bản module, kiểm tra meter thực tế được đăng ký và cập nhật assertion theo Javadoc của đúng version. Mục tiêu của test là xác nhận pipeline được subscribe và instrumentation ghi dữ liệu, không khóa test vào toàn bộ danh sách meter nội bộ.

Có thể dùng StepVerifier để kiểm tra cả completion, error và cancellation. Các kết thúc này có thể được phân biệt bằng tag status trong bộ metric Reactor. Đừng chỉ test luồng hoàn tất bình thường nếu ứng dụng có nhiều cancellation hoặc retry.

## 13. Kiểm thử Scheduler instrumentation

Với Scheduler wrapper, kiểm tra rằng task được submit qua wrapper tạo meter, trong khi task submit trực tiếp vào Scheduler gốc không được wrapper đo. Có thể dùng Scheduler nhỏ dành riêng cho test và đảm bảo dispose sau khi test kết thúc.

Khi kiểm thử, tránh dùng common Scheduler toàn cục rồi thay đổi trạng thái hoặc dispose nó. Dùng Scheduler riêng để test không ảnh hưởng các test khác.

Các trường hợp nên kiểm tra:

- Task submit qua wrapper được ghi nhận.
- Task hoàn tất và task lỗi có trạng thái phù hợp.
- Prefix và tag được áp dụng đúng.
- Scheduler được dispose khi test kết thúc.
- Không có hai wrapper cùng đo một đường thực thi ngoài ý muốn.

## 14. Quy trình chuyển từ API cũ sang API mới

Khi nâng từ Reactor 3.4.x lên 3.5.0 hoặc cao hơn, thực hiện theo thứ tự:

1. Kiểm tra phiên bản reactor-core thực tế trong runtime.
2. Chọn reactor-core-micrometer tương thích thông qua Reactor BOM.
3. Thêm dependency module mới.
4. Thay Flux.metrics hoặc Mono.metrics bằng tap(Micrometer.metrics(registry)).
5. Thay Schedulers.enableMetrics bằng Micrometer.timedScheduler cho các Scheduler cần đo.
6. Nếu cần tracing/Observation, cấu hình ObservationRegistry và dùng Micrometer.observation.
7. Chuẩn hóa name và tag trước tap.
8. Loại bỏ cấu hình global registry cũ sau khi không còn API legacy sử dụng.
9. Kiểm tra dependency tree và compile.
10. So sánh tên meter, tag và dashboard trước/sau migration; các tên metric có thể thay đổi nên cần cập nhật PromQL và alert.

Không bật đồng thời API cũ và mới trên cùng một pipeline để cố giữ dashboard cũ. Hai API có thể công bố tập meter và tên khác nhau; hãy lập kế hoạch migration cho dashboard thay vì đếm cùng một pipeline hai lần.

## 15. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy class Micrometer | Chưa thêm reactor-core-micrometer hoặc chọn sai version. | Kiểm tra dependency tree và thêm artifact tương thích. |
| Code .metrics() biên dịch nhưng không thấy metric | Micrometer không có trên classpath trong tích hợp cũ hoặc pipeline chưa được subscribe. | Kiểm tra classpath, subscription và registry. |
| API mới không tìm thấy | reactor-core cũ hơn 3.5.0 hoặc thiếu module mới. | Nâng version theo kế hoạch hoặc dùng API legacy đúng phiên bản. |
| Meter ghi vào registry khác | Code legacy dùng global registry hoặc API mới nhận nhầm registry. | Inject và truyền rõ MeterRegistry/ObservationRegistry. |
| Scheduler không có metric | Task vẫn submit vào Scheduler gốc thay vì wrapper. | Submit qua Scheduler trả về từ timedScheduler. |
| Có metric trùng | Bật cả legacy và instrumentation mới cho cùng pipeline. | Chỉ giữ một cơ chế cho mỗi phạm vi đo. |
| Dashboard đổi tên metric sau migration | Module mới chuẩn hóa tên và tag khác API cũ. | Kiểm tra exposition, cập nhật query và alert. |
| Build chạy nhưng runtime lỗi linkage | Version Reactor/Micrometer compile và runtime không tương thích. | Dùng BOM, kiểm tra dependencyInsight/dependency:tree. |
| Cardinality tăng nhanh | Dùng tag động hoặc name được tạo theo request. | Dùng operation name và tag-value hữu hạn. |
| Observation không tạo trace/span | ObservationHandler hoặc tracing bridge chưa được cấu hình. | Kiểm tra ObservationRegistry và handler tương ứng. |

## 16. Checklist chọn hỗ trợ Reactor

- [ ] Đã xác định phiên bản reactor-core thực tế ở runtime.
- [ ] Nếu dùng Reactor 3.4.x hoặc cũ hơn, đã hiểu giới hạn của API legacy và yêu cầu Micrometer trên classpath.
- [ ] Nếu dùng Reactor 3.5.0 trở lên, đã thêm reactor-core-micrometer tương thích.
- [ ] Dùng Reactor BOM hoặc dependency management rõ ràng để chọn version.
- [ ] Không giả định version reactor-core-micrometer bằng version reactor-core.
- [ ] Dùng Micrometer.metrics với MeterRegistry cho publisher metrics.
- [ ] Dùng Micrometer.observation với ObservationRegistry khi cần Observation/tracing.
- [ ] Dùng Micrometer.timedScheduler cho Scheduler cần đo.
- [ ] Task cần theo dõi được submit qua Scheduler wrapper.
- [ ] Name và tag được đặt trước tap, có schema ổn định và cardinality thấp.
- [ ] Không bật legacy và API mới cùng lúc cho một phạm vi đo.
- [ ] Đã kiểm tra runtime dependency tree và compile.
- [ ] Đã kiểm thử completion, error, cancellation và Scheduler lifecycle.
- [ ] Đã cập nhật dashboard/alert nếu meter name hoặc tag thay đổi.

Việc chọn hỗ trợ Micrometer của Reactor bắt đầu từ phiên bản reactor-core đã resolve. Với Reactor cũ, hiểu và duy trì API legacy trong phạm vi cần thiết; từ Reactor 3.5.0, ưu tiên reactor-core-micrometer với registry truyền tường minh. Chọn đúng giữa metrics, Observation và scheduler instrumentation giúp số liệu phản ánh đúng reactive pipeline mà không phụ thuộc vào cấu hình global ẩn.

## Tài liệu tham khảo

- [Reactor Reference Guide - Exposing Reactor metrics](https://projectreactor.io/docs/core/release/reference/metrics.html)
- [Reactor Migration Guide - 3.4.x to 3.5.0](https://github.com/reactor/reactor-core/wiki/Migration-Guides)
- [Reactor Reference Guide - BOM and versioning](https://projectreactor.io/docs/core/release/reference/gettingStarted.html)
- [Reactor API - Metrics deprecated in favor of reactor-core-micrometer](https://projectreactor.io/docs/core/release/api/reactor/util/Metrics.html)
