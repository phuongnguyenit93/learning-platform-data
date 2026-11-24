# Vai trò của annotation và thành phần thực thi phép đo phía sau

Annotation của Micrometer giúp khai báo ý định đo lường ngay trên method hoặc class. Tuy nhiên, annotation chỉ là metadata. Một thành phần thực thi như AOP aspect hoặc cơ chế annotation scanning phải đọc metadata, chặn lời gọi method, chạy nghiệp vụ và ghi kết quả vào MeterRegistry. Nếu thiếu thành phần thực thi, method có thể chạy bình thường nhưng không tạo ra phép đo nào.

Hiểu sự tách biệt này giúp tránh lỗi phổ biến: thêm @Timed hoặc @Counted vào code rồi chờ metrics xuất hiện. Cần xác định rõ ứng dụng đang dùng TimedAspect/CountedAspect do mình cấu hình, tính năng annotation scanning của Spring Boot, hay một framework khác đã xử lý annotation. Mỗi cơ chế có điều kiện kích hoạt và giới hạn riêng.

Bài học thuộc module OBSERVABILITY_INSTRUMENTATION_MICROMETER. Module này hướng dẫn sử dụng Micrometer để đo lường ứng dụng Java bằng counter, gauge, timer, distribution summary và nhãn có kiểm soát; tích hợp Spring Boot, xuất metrics đến hệ giám sát, kiểm soát cardinality, kiểm thử instrumentation và diễn giải số đo vận hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích annotation mô tả phép đo nhưng không tự thực thi instrumentation.
- Phân biệt @Timed, @Counted, @Observed và @MeterTag.
- Nhận biết vai trò của TimedAspect, CountedAspect và Spring AOP proxy.
- Cấu hình annotation instrumentation trong Spring Boot.
- Hiểu thời điểm ghi nhận với method đồng bộ và CompletionStage.
- Nhận biết self-invocation và các giới hạn của proxy.
- Tránh đo trùng với instrumentation tự động của Spring.
- Thiết kế tag có cardinality thấp và kiểm thử annotation qua Spring context.

## 1. Annotation là metadata, không phải bộ máy đo

Annotation gắn thông tin vào class, method hoặc parameter. Ví dụ, @Timed mô tả một method cần đo thời gian thực thi; @Counted mô tả một method cần đếm số lần gọi.

Khi biên dịch, annotation được lưu dưới dạng metadata theo retention policy của nó. JVM và framework có thể đọc metadata này bằng reflection hoặc cơ chế weaving/proxy. Nhưng bản thân annotation không tự gọi Timer.record(), không tự tăng Counter và không tự xuất dữ liệu.

Cần có một thành phần đọc annotation và thực thi phép đo:

- Aspect đọc annotation, chặn lời gọi method và ghi nhận kết quả.
- Spring AOP tạo proxy cho bean, để lời gọi đi qua interceptor.
- Annotation scanning của Spring Boot/Micrometer đăng ký cơ chế xử lý các annotation observability khi được bật.
- MeterRegistry nhận Counter hoặc Timer do thành phần thực thi tạo ra.

Luồng xử lý điển hình:

~~~mermaid
flowchart TD
    A["Ứng dụng gọi method trên Spring bean"] --> B["AOP proxy nhận lời gọi"]
    B --> C["Aspect đọc annotation"]
    C --> D["Bắt đầu đo / đếm"]
    D --> E["Gọi method nghiệp vụ"]
    E --> F{"Method kết thúc?"}
    F -->|"Thành công"| G["Ghi kết quả success"]
    F -->|"Ném exception"| H["Ghi kết quả failure"]
    G --> I["MeterRegistry"]
    H --> I
    I --> J["Registry exporter / backend"]
~~~

Nếu lời gọi không đi qua proxy hoặc không có thành phần xử lý annotation, bước aspect sẽ không diễn ra. Vì vậy, sự hiện diện của annotation trong source code chưa đủ để kết luận metric đã được ghi.

## 2. Các annotation thường gặp

| Annotation | Ý nghĩa | Dữ liệu thường được ghi |
| --- | --- | --- |
| @Timed | Đo thời lượng thực thi method | Timer count, total time, max, histogram hoặc percentile tùy cấu hình |
| @Counted | Đếm số lần thực thi method | Counter cho lượt gọi; có thể phân biệt success và failure |
| @Observed | Tạo một Observation bao quanh thao tác | Observation có thể tạo metrics và traces tùy handler được đăng ký |
| @MeterTag | Bổ sung tag từ parameter hoặc kết quả method | Chiều phân loại cho meter được tạo bởi aspect tương ứng |

### @Timed

@Timed biểu diễn ý định đo thời gian một method chạy. Khi aspect thực thi, nó bắt đầu Timer.Sample trước khi gọi method và ghi thời lượng khi method kết thúc.

Một method có thể khai báo:

~~~java
import io.micrometer.core.annotation.Timed;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    @Timed(
            value = "checkout.payment.duration",
            extraTags = {"component", "payment"},
            description = "Thời lượng xử lý thanh toán"
    )
    public PaymentResult pay(PaymentCommand command) {
        // Thực hiện thanh toán
        return PaymentResult.approved();
    }
}
~~~

Tên metric được chỉ định bằng value. extraTags là các cặp key-value tĩnh được thêm vào Timer. Khi method chạy qua aspect, Timer ghi nhận thời lượng dù method kết thúc bình thường hay ném exception.

Nếu method trả về CompletionStage hoặc lớp con của nó, TimedAspect có thể chờ stage hoàn tất rồi mới dừng Timer. Điều này quan trọng với method bất đồng bộ: thời gian trả về object Future không nhất thiết là thời gian hoàn tất công việc.

@Timed còn hỗ trợ longTask=true để tạo LongTaskTimer cho công việc kéo dài. LongTaskTimer có ngữ nghĩa khác Timer thông thường: nó quan sát các task đang chạy và thời gian của chúng. Khi cần cả thời gian từng lần hoàn tất và trạng thái task đang chạy, có thể thiết kế hai phép đo với tên meter phù hợp.

### @Counted

@Counted biểu diễn ý định đếm số lần method được thực thi:

~~~java
import io.micrometer.core.annotation.Counted;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    @Counted(
            value = "invoice.generate.calls",
            extraTags = {"operation", "generate"},
            description = "Số lần gọi tạo hóa đơn"
    )
    public Invoice generate(InvoiceCommand command) {
        // Tạo hóa đơn
        return new Invoice();
    }
}
~~~

CountedAspect mặc định ghi nhận cả lần thành công và thất bại. Các meter được gắn tag kết quả, thường gồm result=success hoặc result=failure; trường hợp thất bại còn có tag exception với tên class exception. Có thể dùng recordFailuresOnly=true nếu chỉ muốn đếm các lần thất bại.

Với method trả về CompletionStage, CountedAspect ghi nhận khi stage hoàn tất. Nếu stage hoàn tất bất thường, aspect ghi nhận failure; nếu thành công và không bật chế độ chỉ ghi failure, aspect ghi nhận success.

Không nhất thiết thêm @Counted cho mọi method đã có @Timed. Timer vốn đã xuất count của các lần được ghi nhận cùng với thời lượng. Chỉ thêm Counter riêng khi cần ngữ nghĩa đếm khác, chẳng hạn đếm một sự kiện nghiệp vụ không tương ứng một lần thực thi method được đo thời gian.

### @Observed

@Observed thuộc Micrometer Observation. Annotation này mô tả một thao tác cần tạo Observation, từ đó các ObservationHandler có thể tạo metrics, traces hoặc các tín hiệu khác.

~~~java
import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
public class CheckoutWorkflow {

    @Observed(
            name = "checkout.workflow",
            contextualName = "process-checkout"
    )
    public CheckoutResult process(CheckoutCommand command) {
        // Xác thực, tính tiền và tạo đơn hàng
        return CheckoutResult.completed();
    }
}
~~~

@Observed rộng hơn @Timed. Nó tạo một Observation có tên và context; handler được đăng ký trong ObservationRegistry quyết định cách chuyển Observation thành Timer, Counter, span hoặc tín hiệu khác. Trong Spring Boot, metrics và traces thường được xây dựng trên Micrometer Observation.

Không xem @Observed là một alias trực tiếp của @Timed. Nếu chỉ cần một Timer đơn giản, @Timed có thể đủ. Nếu muốn một thao tác có thể tạo cả metrics và traces theo Observation convention, @Observed là lựa chọn phù hợp hơn.

### @MeterTag

@MeterTag dùng để lấy giá trị từ parameter hoặc kết quả method và bổ sung tag cho meter do @Timed hoặc @Counted tạo ra.

Ví dụ, một method có thể phân loại theo channel:

~~~java
@Timed("checkout.payment.duration")
public PaymentResult pay(
        @MeterTag(key = "channel") String channel,
        PaymentCommand command
) {
    // Xử lý thanh toán
    return PaymentResult.approved();
}
~~~

Việc đọc @MeterTag cần handler tương ứng được cấu hình cho TimedAspect hoặc CountedAspect. Với giá trị cần chuyển đổi, có thể cung cấp ValueResolver hoặc ValueExpressionResolver phù hợp.

Trong file Java hoàn chỉnh, import annotation này từ `io.micrometer.core.annotation.MeterTag`. TimedAspect không tự bật xử lý @MeterTag nếu chưa cấu hình MeterTagAnnotationHandler.

Chỉ dùng các giá trị có tập hữu hạn, đã chuẩn hóa. Nếu parameter là order ID, email, request ID hoặc chuỗi tự do, không đưa nguyên giá trị đó vào tag. Mỗi giá trị mới có thể tạo một Meter.Id mới và làm cardinality tăng nhanh.

## 3. Aspect là thành phần thực thi annotation

Micrometer cung cấp TimedAspect và CountedAspect trong micrometer-core. Các aspect này dùng AspectJ pointcut để tìm method hoặc class có annotation tương ứng, sau đó thực thi logic ghi nhận.

TimedAspect chịu trách nhiệm:

1. Nhận lời gọi method được đánh dấu @Timed.
2. Tạo Timer.Sample trước khi chạy method.
3. Gọi method nghiệp vụ.
4. Đo thời lượng đến khi method kết thúc hoặc CompletionStage hoàn tất.
5. Ghi Timer với các tag phù hợp, bao gồm thông tin exception nếu có.

CountedAspect chịu trách nhiệm:

1. Nhận lời gọi method được đánh dấu @Counted.
2. Gọi method nghiệp vụ.
3. Xác định method thành công hay thất bại.
4. Tăng Counter tương ứng và gắn tag kết quả.
5. Chờ CompletionStage hoàn tất trước khi ghi nhận nếu method trả về CompletionStage.

Aspect không thay thế logic nghiệp vụ. Nó bao quanh lời gọi để thêm hành vi quan sát mà không cần viết Timer.record() hoặc Counter.increment() trực tiếp trong method.

Các aspect Micrometer hiện hành không tự hỗ trợ meta-annotation bọc @Timed hoặc @Counted. Nếu xây dựng annotation nội bộ như @Measured để gắn lên method, cần xác nhận framework xử lý meta-annotation đó hoặc cấu hình pointcut riêng.

### Đăng ký aspect thủ công

Trong Spring Boot, có thể cấu hình aspect thành bean:

~~~java
import io.micrometer.core.aop.CountedAspect;
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsAspectConfiguration {

    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }

    @Bean
    CountedAspect countedAspect(MeterRegistry registry) {
        return new CountedAspect(registry);
    }
}
~~~

Để Spring AOP xử lý aspect, ứng dụng cần có AspectJ weaving API/runtime phù hợp và cơ chế tạo proxy. Với Spring Boot 3, dependency thường dùng là:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-aop")
}
~~~

Với Spring Boot 4, starter AOP được tổ chức lại; dùng starter AspectJ tương ứng với phiên bản Boot đang chạy. Nếu ứng dụng đã có cấu hình Spring AOP, không cần bật proxy thêm lần nữa. Trong cấu hình Spring không dùng auto-configuration, có thể bật proxy bằng @EnableAspectJAutoProxy.

Không đăng ký TimedAspect hoặc CountedAspect thủ công nếu một cơ chế annotation scanning khác đã xử lý cùng annotation cho cùng method. Hai cơ chế có thể tạo phép đo trùng lặp.

## 4. Annotation scanning trong Spring Boot

Spring Boot cung cấp tính năng quét và xử lý các observability annotation như @Observed, @Timed, @Counted, @MeterTag và @NewSpan. Tính năng này cần được bật rõ ràng:

~~~properties
management.observations.annotations.enabled=true
~~~

Ứng dụng cũng cần dependency AspectJ weaver tương ứng với phiên bản Spring Boot. Trong Spring Boot 3.x, dependency thường được cung cấp bởi spring-boot-starter-aop; Spring Boot 4.x dùng starter AspectJ theo cấu trúc dependency mới.

Khi annotation scanning được bật, Spring Boot/Micrometer thiết lập cơ chế thực thi annotation. Hãy kiểm tra tài liệu của đúng phiên bản Spring Boot vì tên starter và cách tổ chức package có thể thay đổi giữa các major version.

Một cấu hình ví dụ:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-aop")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

~~~properties
management.observations.annotations.enabled=true
management.endpoints.web.exposure.include=health,prometheus
~~~

Với ứng dụng Boot 4, thay dependency AOP bằng starter AspectJ tương ứng. Registry Prometheus chỉ là đích xuất metrics; nó không tự quyết định annotation nào được intercept.

### Chọn một cơ chế xử lý nhất quán

Có hai cách phổ biến:

| Cách | Cấu hình | Khi phù hợp |
| --- | --- | --- |
| Đăng ký TimedAspect/CountedAspect thủ công | Khai báo bean aspect và bật Spring AOP | Muốn kiểm soát aspect hoặc dùng ứng dụng Micrometer/Spring tùy chỉnh |
| Spring Boot annotation scanning | Bật management.observations.annotations.enabled và thêm AspectJ dependency | Muốn dùng cơ chế annotation observability do Boot hỗ trợ |

Không bật cả hai cách cho cùng annotation và cùng method nếu không có skip predicate hoặc cấu hình loại trừ rõ ràng. Nếu cả hai aspect đều intercept, Timer hoặc Counter có thể bị ghi hai lần.

## 5. Spring AOP proxy quyết định lời gọi có được đo hay không

Spring AOP thường hoạt động bằng proxy. Bean được Spring quản lý có thể được bọc bởi JDK dynamic proxy hoặc CGLIB proxy. Khi một component khác gọi method thông qua proxy, interceptor có cơ hội kiểm tra annotation và ghi metrics.

~~~mermaid
flowchart LR
    A["Controller / caller"] --> B["Spring proxy"]
    B --> C["TimedAspect / CountedAspect"]
    C --> D["Target service method"]
    D --> C
    C --> E["MeterRegistry"]
~~~

Nếu method được gọi trực tiếp trên target object, không qua proxy, aspect sẽ không chạy.

### Self-invocation bỏ qua proxy

Ví dụ:

~~~java
@Service
public class ReportService {

    public void exportAll() {
        exportOne(); // Gọi nội bộ qua this, không qua proxy
    }

    @Timed("report.export.one.duration")
    public void exportOne() {
        // Xuất một báo cáo
    }
}
~~~

Khi caller gọi exportAll() qua proxy, proxy chỉ intercept exportAll(). Lời gọi exportOne() bên trong target object là self-invocation và không quay lại proxy. Vì vậy, @Timed trên exportOne() có thể không tạo Timer.

Cách xử lý thường là tách method được đo sang một bean khác và inject bean đó:

~~~java
@Service
public class SingleReportExporter {

    @Timed("report.export.one.duration")
    public void exportOne() {
        // Xuất một báo cáo
    }
}

@Service
public class ReportService {

    private final SingleReportExporter exporter;

    public ReportService(SingleReportExporter exporter) {
        this.exporter = exporter;
    }

    public void exportAll() {
        exporter.exportOne(); // Lời gọi đi qua proxy của bean exporter
    }
}
~~~

Cách tách bean giúp ranh giới đo lường rõ ràng và dễ kiểm thử.

### Các giới hạn của proxy

- Với JDK dynamic proxy, chỉ các method được expose qua interface proxy mới có thể được intercept khi caller truy cập qua interface.
- Với CGLIB, class cần có khả năng được subclass; final class không thể được proxy theo cách này.
- Private method không thể được override để tạo advice bằng CGLIB.
- Final method không thể được override để áp dụng advice.
- Method được gọi từ bên trong cùng target object sẽ bỏ qua proxy.

Nếu cần intercept cả self-invocation hoặc các method không thể proxy theo quy tắc trên, AspectJ compile-time hoặc load-time weaving có thể là lựa chọn khác. Đây là cơ chế weaving bytecode, có cấu hình và chi phí vận hành riêng.

## 6. Đo method đồng bộ và bất đồng bộ

Với method đồng bộ, aspect đo từ lúc bắt đầu gọi method đến khi method trả về hoặc ném exception.

Với method trả về CompletionStage, TimedAspect và CountedAspect có thể trì hoãn việc ghi nhận đến khi stage hoàn tất. Ví dụ:

~~~java
@Async
@Timed("invoice.generate.duration")
public CompletableFuture<Invoice> generateAsync(InvoiceCommand command) {
    return CompletableFuture.supplyAsync(
            () -> generateInvoice(command)
    );
}
~~~

Nếu đo thời gian method bất đồng bộ, cần xác định rõ mục tiêu:

- Thời gian tạo và trả về Future.
- Thời gian toàn bộ công việc bất đồng bộ hoàn tất.
- Thời gian chờ một dependency bên ngoài.
- Thời gian xử lý từng giai đoạn.

TimedAspect hỗ trợ CompletionStage để đo đến khi stage hoàn tất. Với kiểu reactive như Mono hoặc Flux, không nên giả định một aspect method thông thường sẽ tự đo đúng toàn bộ vòng đời subscription; hãy dùng cơ chế Observation hoặc instrumentation phù hợp với reactive pipeline và phiên bản thư viện.

Ngoài ra, @Async và AOP có thể tạo nhiều proxy hoặc interceptor cùng một bean. Cần kiểm thử thực tế để bảo đảm Timer bắt đầu và kết thúc ở đúng ranh giới công việc.

## 7. Tránh ghi metrics trùng lặp

Spring Boot đã tự động instrument nhiều thành phần như HTTP server, Spring Data repositories, DataSource, cache và executor khi các điều kiện tương ứng được thỏa mãn.

Nếu thêm @Timed hoặc @Observed lên một method đã được instrument tự động, cùng một thao tác có thể tạo nhiều observation hoặc Timer. Điều này làm count tăng gấp đôi, histogram bị phân tách hoặc dashboard khó diễn giải.

Ví dụ, Spring Data repository invocation có thể đã có metric tự động. Nếu thêm @Timed lên cùng method repository, hãy xác định rõ có cần phép đo tùy chỉnh không.

Có thể xử lý theo một trong các hướng:

- Giữ instrumentation tự động và bỏ annotation trùng.
- Giữ annotation tùy chỉnh, đồng thời tắt instrumentation tự động tương ứng bằng property.
- Dùng ObservationPredicate để loại những observation không cần ghi nhận.
- Dùng skip predicate của aspect khi một nhóm method đã được thành phần khác xử lý.

Không chỉ so sánh tên metric để xác định trùng lặp. Hãy kiểm tra tên, tag, thời điểm ghi và ranh giới thao tác được đo.

## 8. Tag và cardinality khi dùng annotation

Annotation có thể thêm tag tĩnh bằng extraTags hoặc tag động bằng @MeterTag. Tag động rất tiện, nhưng cũng là nguồn cardinality cao nếu lấy trực tiếp từ dữ liệu đầu vào.

Nên dùng các chiều phân loại có tập giá trị hữu hạn:

~~~java
@Timed(
        value = "checkout.payment.duration",
        extraTags = {"operation", "authorize"}
)
public PaymentResult authorize(PaymentCommand command) {
    // ...
}
~~~

Nếu cần tag từ parameter, chuẩn hóa trước khi gắn vào meter. Ví dụ, channel chỉ nhận các giá trị web, mobile hoặc partner. Các giá trị ngoài danh sách có thể được gom vào other.

Không dùng các giá trị sau làm metric tag:

- order ID, customer ID hoặc user ID.
- request ID, trace ID hoặc session ID.
- Email, số điện thoại hoặc dữ liệu cá nhân.
- Raw URL, query string hoặc nội dung payload.
- Exception message có chứa dữ liệu đầu vào.

Với lỗi, dùng exception class hoặc nhóm lỗi đã chuẩn hóa thay vì message tùy ý. Với request, dùng route template như /orders/{id} thay cho raw path.

## 9. Kiểm thử annotation instrumentation

Kiểm thử annotation cần xác nhận hai việc riêng:

1. Method có annotation đúng.
2. Thành phần AOP thực sự intercept lời gọi và ghi metric vào registry.

Chỉ dùng reflection để xác nhận annotation tồn tại chưa chứng minh aspect hoạt động.

### Kiểm thử @Timed qua Spring context

Ví dụ test tích hợp với SimpleMeterRegistry:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "management.observations.annotations.enabled=true",
        "management.simple.metrics.export.enabled=true"
})
class TimedAnnotationIntegrationTest {

    @Autowired
    PaymentService paymentService;

    @Autowired
    MeterRegistry registry;

    @Test
    void recordsDurationWhenAnnotatedMethodIsCalledThroughProxy() {
        paymentService.pay(new PaymentCommand());

        assertThat(registry.get("checkout.payment.duration")
                .tag("component", "payment")
                .timer()
                .count())
                .isEqualTo(1L);
    }
}
~~~

Test cần có AspectJ dependency và PaymentService là Spring bean. Nếu dùng aspect thủ công, hãy đăng ký TimedAspect trong test configuration thay cho annotation scanning. Không bật cả hai cơ chế trong cùng test.

Tên và tag phải khớp cấu hình annotation. Nếu metric không xuất hiện, kiểm tra registry được inject, property annotation scanning, dependency AspectJ và lời gọi có đi qua proxy không.

### Kiểm thử @Counted

Có thể kiểm tra số lần gọi và tag kết quả:

~~~java
assertThat(registry.get("invoice.generate.calls")
        .tag("operation", "generate")
        .tag("result", "success")
        .counter()
        .count())
        .isEqualTo(1.0);
~~~

Với test failure, tạo method có thể ném exception đã biết và xác nhận counter có tag result=failure cùng exception class tương ứng. Không nên bắt exception rồi bỏ qua nếu mục tiêu test là xác nhận aspect giữ nguyên hành vi ném lỗi của method.

### Kiểm thử self-invocation

Tạo hai method trong cùng bean: method ngoài gọi method được annotate nội bộ. So sánh với trường hợp method được gọi từ một bean khác qua proxy. Test này giúp phát hiện instrumentation bị bỏ qua do self-invocation.

### Kiểm thử tránh đo trùng

Nếu ứng dụng có auto-instrumentation cho controller hoặc repository, hãy kiểm tra một thao tác chỉ tạo số observation mong đợi. Test nên xác nhận count và tag cụ thể, không chỉ kiểm tra meter tồn tại.

## 10. Các lỗi thường gặp

| Lỗi | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Chỉ thêm @Timed rồi chờ có metric | Method chạy nhưng Timer không xuất hiện | Đăng ký TimedAspect hoặc bật annotation scanning |
| Chỉ thêm @Counted mà thiếu CountedAspect | Counter không tăng | Cấu hình thành phần thực thi |
| Thiếu AspectJ weaver hoặc AOP proxy | Annotation không được intercept | Thêm dependency và kiểm tra proxy configuration |
| Gọi method qua self-invocation | Không có metric cho method nội bộ | Tách method sang bean khác hoặc dùng weaving |
| Annotate private/final method | Proxy không intercept được | Chọn method có thể được proxy |
| Bật cả TimedAspect và annotation scanning | Timer bị ghi hai lần | Chỉ dùng một cơ chế cho cùng method |
| Annotate controller đã có HTTP metrics | Có quan sát trùng lặp | Giữ một nguồn instrumentation |
| Đo method trả Future như method đồng bộ | Thời lượng có thể kết thúc quá sớm | Dùng CompletionStage support hoặc Observation phù hợp |
| Dùng @MeterTag với ID động | Cardinality tăng nhanh | Chuẩn hóa thành enum hoặc nhóm hữu hạn |
| Nghĩ @Observed chỉ tạo Timer | Bỏ qua khả năng tạo trace hoặc handler khác | Hiểu ObservationRegistry và ObservationHandler |
| Test annotation chỉ bằng reflection | Không phát hiện AOP không chạy | Test qua Spring bean proxy và kiểm tra MeterRegistry |

## 11. Checklist thiết kế annotation và AOP

Trước khi đưa annotation instrumentation vào ứng dụng, hãy xác nhận:

1. Annotation có phản ánh đúng loại phép đo cần tạo không?
2. Có cần @Timed, @Counted hay @Observed?
3. Thành phần nào thực thi annotation: TimedAspect, CountedAspect hay Boot scanning?
4. AspectJ dependency và Spring proxy đã được cấu hình chưa?
5. Method được gọi qua Spring bean proxy không?
6. Có self-invocation hoặc method private/final làm mất intercept không?
7. Method bất đồng bộ được đo đến lúc trả Future hay đến khi Future hoàn tất?
8. Có instrumentation tự động nào đang đo cùng thao tác không?
9. Tag tĩnh và động có cardinality thấp không?
10. Integration test đã xác nhận metric được ghi đúng một lần chưa?

## Kết luận

Annotation của Micrometer mô tả ý định đo lường. TimedAspect, CountedAspect hoặc cơ chế annotation scanning của Spring Boot mới đọc metadata, chặn lời gọi method và ghi dữ liệu vào MeterRegistry. @Timed tạo Timer, @Counted tạo Counter, @Observed tạo Observation có thể được chuyển thành metrics hoặc traces, còn @MeterTag bổ sung chiều phân loại cho meter.

Hãy xác định rõ cơ chế thực thi đang dùng, bảo đảm lời gọi đi qua proxy và tránh tự gọi nội bộ làm bỏ qua aspect. Khi dùng annotation cùng instrumentation tự động, kiểm tra khả năng đo trùng; khi tạo tag động, chuẩn hóa giá trị để cardinality có giới hạn. Kiểm thử qua Spring context và MeterRegistry giúp xác nhận phép đo thực sự được ghi thay vì chỉ tồn tại dưới dạng annotation trong source code.

## Tài liệu tham khảo

- [Micrometer: Timers và @Timed](https://docs.micrometer.io/micrometer/reference/concepts/timers.html) — TimedAspect, thời điểm ghi nhận, CompletionStage và MeterTag.
- [Micrometer: Counters và @Counted](https://docs.micrometer.io/micrometer/reference/concepts/counters.html) — CountedAspect, kết quả success/failure và MeterTag.
- [Spring Boot: Observability annotations support](https://docs.spring.io/spring-boot/reference/actuator/observability.html) — bật annotation scanning, dependency AspectJ và cảnh báo duplicate observations.
- [Spring Framework: Proxying mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html) — JDK proxy, CGLIB, self-invocation và giới hạn method.
