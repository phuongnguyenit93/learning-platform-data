# MeterProvider để tái sử dụng cấu hình chung khi tag được xác định động

Trong nhiều tình huống, meter có một phần cấu hình cố định và một vài tag chỉ biết được khi thao tác kết thúc. Ví dụ, mọi lần chạy một job đều dùng cùng tên Timer, cùng mô tả và cùng tag tên job, nhưng tag kết quả chỉ xác định được sau khi job thành công, thất bại hoặc bị từ chối.

Có thể tạo một builder mới ở mỗi lần ghi nhận, thêm tag động rồi đăng ký meter. Cách đó đúng về chức năng nhưng lặp lại cấu hình và tạo thêm builder object. **MeterProvider** của Micrometer giải quyết trường hợp này bằng một mẫu cấu hình dùng chung: tạo provider một lần từ builder và registry, sau đó gọi **withTag** hoặc **withTags** để bổ sung các tag thay đổi ở từng lần sử dụng.

MeterProvider phù hợp khi cần tái sử dụng cấu hình chung mà vẫn chọn được tag tại thời điểm chạy. Nó không phải một registry mới, không lưu trạng thái nghiệp vụ và cũng không tự giới hạn cardinality của tag. Mỗi tổ hợp tag động vẫn có thể tạo ra một meter riêng trong registry.

## 1. Vấn đề khi tạo builder lặp lại

Giả sử ứng dụng đo thời gian thực thi một job. Tên meter, mô tả và tên job đều cố định; chỉ trạng thái cuối cùng thay đổi:

~~~java
Timer.Sample sample = Timer.start(registry);
String status = "failure";

try {
    Result result = job.execute();
    status = result.status();
} finally {
    Timer timer = Timer.builder("job.execution")
        .description("Thời gian thực thi job")
        .tag("job.name", "invoice-export")
        .tag("status", status)
        .register(registry);

    sample.stop(timer);
}
~~~

Cách này tạo đúng Timer với tag status được xác định sau khi job chạy. Tuy nhiên, mỗi lần thực thi đều tạo lại Timer.Builder và lặp lại tên, mô tả cùng tag cố định. Khi instrumentation nằm trên đường xử lý có lưu lượng lớn, các object builder lặp lại tạo thêm công việc cho garbage collector và khiến mã dài hơn.

Với meter đơn giản, có thể dùng phương thức rút gọn của registry, ví dụ **registry.timer(name, tags)** hoặc **registry.counter(name, tags)**. Cách này phù hợp khi cấu hình chỉ có tên và một số tag. Khi cần tái sử dụng nhiều thuộc tính builder như description, base unit hoặc cấu hình phân phối, MeterProvider giúp gom phần cấu hình cố định vào một nơi.

## 2. MeterProvider là gì?

MeterProvider là interface tiện ích lồng trong **Meter** của Micrometer. Kiểu thường dùng có dạng **Meter.MeterProvider<T>**, trong đó T là loại meter cụ thể, chẳng hạn Timer hoặc Counter.

Provider được tạo từ builder bằng phương thức **withRegistry(registry)**. Builder chứa các thuộc tính cố định như tên meter, description, base unit, tag chung và cấu hình thống kê. Provider sau đó nhận các tag động qua **withTag(key, value)** hoặc **withTags(...)** và trả về meter đã đăng ký trong registry.

~~~java
Meter.MeterProvider<Timer> timerProvider =
    Timer.builder("job.execution")
        .description("Thời gian thực thi job")
        .tag("job.name", "invoice-export")
        .withRegistry(registry);
~~~

Ở đây, cấu hình dùng chung được xác định một lần:

- Tên meter là **job.execution**.
- Description mô tả thời lượng thực thi.
- Tag **job.name=invoice-export** có giá trị cố định.
- Registry nhận và quản lý các Timer được tạo từ provider.

Khi có kết quả, mã chỉ bổ sung tag động:

~~~java
Timer timer = timerProvider.withTag("status", "success");
~~~

Timer trả về có cả tag cố định **job.name** và tag động **status**. Nếu gọi lại với cùng tổ hợp tag, registry trả về meter đã đăng ký tương ứng thay vì tạo một meter ID khác.

MeterProvider được Micrometer hỗ trợ từ phiên bản 1.12.0. API này không có cho mọi loại meter; các builder phổ biến hỗ trợ provider gồm Counter, Timer, LongTaskTimer và DistributionSummary. Cần kiểm tra phiên bản Micrometer mà ứng dụng đang dùng trước khi áp dụng.

## 3. Phân biệt cấu hình cố định và tag động

Thiết kế provider bắt đầu bằng việc phân chia thuộc tính thành hai nhóm:

| Nhóm | Đặt ở đâu? | Ví dụ |
|---|---|---|
| Thuộc tính cố định | Builder trước khi gọi withRegistry | Tên meter, description, base unit, tên job, loại thao tác |
| Tag động | withTag hoặc withTags tại call site | Kết quả, kênh xử lý, nhóm phản hồi |

Ví dụ với Timer:

~~~java
Meter.MeterProvider<Timer> jobTimer = Timer.builder("job.execution")
    .description("Thời gian thực thi job nền")
    .tag("job.name", "invoice-export")
    .tag("operation", "export")
    .withRegistry(registry);
~~~

Hai tag **job.name** và **operation** luôn giống nhau nên thuộc builder. Tag **status** thay đổi theo kết quả và được thêm khi dừng sample.

Không nên đặt một giá trị có thể thay đổi theo từng request vào builder dùng chung. Builder tạo provider là mẫu cấu hình dài hạn; nếu cần tag động, hãy truyền tag ở lần gọi provider tương ứng. Cũng không nên tạo một provider mới cho mỗi request, vì khi đó không còn lợi ích tái sử dụng.

## 4. Ví dụ đầy đủ: đo job và chọn tag sau khi hoàn tất

Timer.Sample cho phép bắt đầu đo trước khi biết trạng thái cuối. Khi job kết thúc, provider chọn Timer theo tag status:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class JobMetrics {

    private final MeterRegistry registry;
    private final Meter.MeterProvider<Timer> executionTimer;

    public JobMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.executionTimer = Timer.builder("job.execution")
            .description("Thời gian thực thi job nền")
            .tag("job.name", "invoice-export")
            .withRegistry(registry);
    }

    public void execute(Runnable job) {
        Timer.Sample sample = Timer.start(registry);
        String status = "failure";

        try {
            job.run();
            status = "success";
        } catch (JobRejectedException exception) {
            status = "rejected";
            throw exception;
        } finally {
            Timer timer = executionTimer.withTag("status", status);
            sample.stop(timer);
        }
    }
}
~~~

Kết quả là cùng một meter name nhưng có các chuỗi riêng theo status:

- **job.execution{job.name="invoice-export", status="success"}**
- **job.execution{job.name="invoice-export", status="failure"}**
- **job.execution{job.name="invoice-export", status="rejected"}**

Mỗi lần chạy chỉ ghi thời lượng vào Timer tương ứng với kết quả cuối. Khối finally bảo đảm sample được dừng cả khi job ném exception. Giá trị status được khởi tạo là **failure** để các lỗi không được bắt riêng vẫn được phân loại. Trong ứng dụng thực tế, kiểu exception và quy tắc phân loại cần theo hợp đồng của job.

Ví dụ này giả định **JobRejectedException** là một loại RuntimeException. Nếu API của job dùng kiểu kết quả thay vì exception, hãy đặt status từ kết quả trả về rồi dừng sample tại cùng một điểm kết thúc.

## 5. Dùng withTags để bổ sung nhiều tag động

Khi có nhiều chiều chỉ được xác định ở thời điểm ghi nhận, dùng **withTags** với các cặp key-value:

~~~java
Meter.MeterProvider<Counter> processedJobs =
    Counter.builder("jobs.processed")
        .description("Số job đã xử lý")
        .tag("service", "billing")
        .withRegistry(registry);

// Tại thời điểm xử lý:
processedJobs.withTags(
    "status", "success",
    "queue", "priority"
).increment();
~~~

Counter được tạo với tag cố định **service=billing** và hai tag động **status** cùng **queue**. Phương thức withTags nhận các cặp khóa và giá trị xen kẽ; số phần tử phải là số chẵn.

Nếu chỉ có một tag động, **withTag(key, value)** giúp mã ngắn hơn. Nếu tag đã được chuẩn bị dưới dạng Iterable<Tag>, có thể truyền trực tiếp vào overload tương ứng.

Không nên truyền cùng một khóa nhiều lần trong cấu hình cố định và tag động. Hãy quy định rõ khóa nào thuộc builder, khóa nào thuộc call site để schema dễ đọc và không phụ thuộc hành vi ghi đè tag khi trùng key.

## 6. Tái sử dụng provider cho Counter

Counter phù hợp khi cần đếm sự kiện và phân loại bằng tag động. Ví dụ, số lần job hoàn tất có thể được phân nhóm theo kết quả:

~~~java
public final class JobOutcomeMetrics {

    private final Meter.MeterProvider<Counter> outcomes;

    public JobOutcomeMetrics(MeterRegistry registry) {
        this.outcomes = Counter.builder("jobs.outcomes")
            .description("Số kết quả xử lý job")
            .tag("job.name", "invoice-export")
            .withRegistry(registry);
    }

    public void record(String status) {
        outcomes.withTag("status", normalizeStatus(status))
            .increment();
    }

    private String normalizeStatus(String status) {
        if ("success".equals(status)
                || "failure".equals(status)
                || "rejected".equals(status)) {
            return status;
        }
        return "unknown";
    }
}
~~~

Provider tái sử dụng tên meter, description và tag job. Hàm record chỉ xác định status rồi tăng Counter tương ứng. Các giá trị được chuẩn hóa về tập hữu hạn để tránh tag tùy ý.

Có thể đọc từng Counter trong registry theo tổ hợp tag:

~~~java
double successes = registry.get("jobs.outcomes")
    .tag("job.name", "invoice-export")
    .tag("status", "success")
    .counter()
    .count();
~~~

Provider giúp tái sử dụng cấu hình và API đăng ký meter. Nó không làm cho Counter trở thành bộ đếm tổng duy nhất bất kể tag; mỗi tổ hợp tag là một meter ID riêng.

## 7. Provider cho LongTaskTimer và DistributionSummary

MeterProvider cũng dùng được với LongTaskTimer và DistributionSummary.

Với LongTaskTimer, provider có thể giữ cấu hình loại tác vụ, còn tag động xác định nhóm công việc tại thời điểm bắt đầu:

~~~java
Meter.MeterProvider<LongTaskTimer> activeJobs =
    LongTaskTimer.builder("jobs.active")
        .description("Số lượng và thời lượng job đang chạy")
        .tag("service", "billing")
        .withRegistry(registry);

LongTaskTimer.Sample sample =
    activeJobs.withTag("queue", "priority").start();

try {
    job.run();
} finally {
    sample.stop();
}
~~~

Mỗi lần chạy cần có Sample riêng và phải dừng trong finally. Tag queue nên đến từ một tập giá trị có giới hạn, ví dụ **priority**, **standard** hoặc **bulk**.

Với DistributionSummary, provider phù hợp khi cần ghi các giá trị số và phân loại chúng theo một chiều xác định lúc ghi:

~~~java
Meter.MeterProvider<DistributionSummary> payloadSizes =
    DistributionSummary.builder("message.payload.size")
        .description("Kích thước payload được xử lý")
        .baseUnit("bytes")
        .withRegistry(registry);

payloadSizes.withTag("format", "json").record(payloadBytes);
payloadSizes.withTag("format", "binary").record(payloadBytes);
~~~

Hai lần ghi sử dụng cùng cấu hình meter và khác giá trị tag format. DistributionSummary ghi nhận phân phối của payloadBytes trong từng nhóm format.

## 8. Provider được tái sử dụng thế nào trong Spring Boot?

Trong ứng dụng Spring Boot, MeterRegistry thường được auto-configure và quản lý theo vòng đời ApplicationContext. Component instrumentation có thể nhận registry qua constructor, tạo MeterProvider một lần và giữ provider trong field:

~~~java
@Component
public class ApiMetrics {

    private final Meter.MeterProvider<Counter> responses;

    public ApiMetrics(MeterRegistry registry) {
        this.responses = Counter.builder("api.responses")
            .description("Số phản hồi API theo kết quả")
            .tag("component", "orders")
            .withRegistry(registry);
    }

    public void record(String status) {
        responses.withTag("status", normalizeStatus(status)).increment();
    }

    private String normalizeStatus(String status) {
        if ("success".equals(status)
                || "failure".equals(status)
                || "rejected".equals(status)) {
            return status;
        }
        return "unknown";
    }
}
~~~

Bean singleton giữ provider trong suốt vòng đời ứng dụng. Mỗi lần xử lý chỉ gọi withTag để lấy Counter tương ứng và cập nhật. Component không cần tự tạo hoặc đóng registry được Spring quản lý.

Không tạo provider trong controller method hoặc mỗi lần nhận request. Việc đó làm tăng object allocation và lặp lại cấu hình. Cũng không đóng MeterRegistry từ component sử dụng; vòng đời registry thuộc container hoặc chủ sở hữu đã tạo nó.

## 9. MeterProvider không thay thế việc kiểm soát cardinality

Tag động là lý do chính để dùng MeterProvider, nhưng động không có nghĩa là không giới hạn. Mỗi giá trị tag mới có thể tạo thêm meter ID và chuỗi thời gian. Nếu status chỉ có ba giá trị thì số meter có thể dự đoán được. Nếu tag là request ID, user ID hoặc tên file tùy ý, số meter có thể tăng theo lưu lượng.

Nên chọn giá trị có tập hữu hạn:

| Tag động | Giá trị phù hợp | Giá trị cần tránh |
|---|---|---|
| status | success, failure, rejected | Nội dung exception |
| queue | priority, standard, bulk | Queue ID sinh theo từng job |
| region | ap-southeast, eu-west | IP hoặc tọa độ từng client |
| format | json, xml, binary | Tên file hoặc object ID |
| method | GET, POST, PUT, DELETE | Chuỗi method tùy ý từ request |

Nếu dữ liệu có thể thiếu, hãy chuẩn hóa về giá trị như **unknown** hoặc **not_applicable** thay vì bỏ hẳn tag ở một số nhánh. Các meter cùng tên nên có cùng tập khóa tag.

MeterProvider không tự giới hạn số giá trị. Có thể kết hợp chuẩn hóa đầu vào, enum, API instrumentation dùng chung và MeterFilter như một lớp bảo vệ. MeterFilter giúp giới hạn hoặc điều chỉnh meter theo cấu hình registry, nhưng không thay thế thiết kế tag hợp lý tại nơi phát sinh dữ liệu.

## 10. Khi nào nên dùng MeterProvider và khi nào không cần?

| Tình huống | Cách phù hợp | Lý do |
|---|---|---|
| Tên, tag và cấu hình đều cố định | Đăng ký meter một lần rồi giữ meter | Không cần provider nếu không có tag động |
| Chỉ có một tên và vài tag đơn giản | Dùng phương thức rút gọn của MeterRegistry | Mã ngắn và ít cấu hình |
| Nhiều thuộc tính builder cố định, tag thay đổi theo kết quả | MeterProvider | Tái sử dụng cấu hình và bổ sung tag tại call site |
| Cần chọn Timer sau khi thao tác kết thúc | Timer.Sample kết hợp MeterProvider | Chọn tag outcome ở thời điểm stop |
| Giá trị tag không giới hạn | Thiết kế lại tag trước khi dùng provider | Provider không ngăn cardinality tăng |
| Cần meter không hỗ trợ MeterProvider | Dùng builder hoặc API registry tương ứng | Provider chỉ có cho một số loại meter |

MeterProvider có ích nhất khi phần cấu hình chung đủ đáng kể và phần tag động có tập giá trị được kiểm soát. Với meter chỉ dùng một tổ hợp tag cố định, giữ trực tiếp meter trong field là đơn giản hơn.

## 11. Kiểm thử provider và các tổ hợp tag

Có thể dùng SimpleMeterRegistry để kiểm tra provider tạo hoặc lấy lại meter theo cùng tổ hợp tag:

~~~java
@Test
void providerReusesMeterForTheSameTagCombination() {
    try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
        Meter.MeterProvider<Counter> provider =
            Counter.builder("jobs.outcomes")
                .tag("job.name", "invoice-export")
                .withRegistry(registry);

        provider.withTag("status", "success").increment();
        provider.withTag("status", "success").increment();
        provider.withTag("status", "failure").increment();

        assertEquals(
            2.0,
            registry.get("jobs.outcomes")
                .tag("job.name", "invoice-export")
                .tag("status", "success")
                .counter()
                .count()
        );

        assertEquals(
            1.0,
            registry.get("jobs.outcomes")
                .tag("job.name", "invoice-export")
                .tag("status", "failure")
                .counter()
                .count()
        );

        assertEquals(2, registry.getMeters().size());
    }
}
~~~

Kiểm thử xác nhận hai lần ghi với status success cập nhật cùng một Counter, còn status failure tạo một meter ID khác. Tổng số meter trong registry là hai vì có hai tổ hợp status.

Trong kiểm thử thực tế, cần kiểm tra thêm:

- Các meter cùng tên có tập khóa tag giống nhau.
- Giá trị động luôn nằm trong tập cho phép.
- Builder chỉ được tạo một lần trong vòng đời component.
- Timer.Sample được dừng đúng một lần trong cả nhánh thành công và exception.
- Số tổ hợp tag được tạo không vượt mức dự kiến.
- MeterFilter và registry đích xử lý meter theo cấu hình mong muốn.

SimpleMeterRegistry kiểm tra logic đăng ký và cập nhật trong bộ nhớ. Khi cần xác minh tên metric, định dạng hoặc số chuỗi ở backend, hãy kiểm thử tích hợp với registry/exporter đích.

## 12. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Tạo provider trong mỗi request | Mất lợi ích tái sử dụng, tăng object allocation | Tạo provider một lần trong component |
| Đặt tag thay đổi vào builder dùng chung | Cấu hình không phản ánh đúng từng lần chạy | Đưa tag động vào withTag/withTags |
| Dùng request ID hoặc user ID làm tag | Cardinality tăng không giới hạn | Dùng nhóm giá trị hữu hạn |
| Bỏ tag khi dữ liệu không có | Schema cùng meter name thiếu nhất quán | Dùng fallback như unknown |
| Dùng provider cho meter không hỗ trợ | Không có API withRegistry tương ứng | Kiểm tra loại meter và builder |
| Nhầm MeterProvider của Micrometer với OpenTelemetry | Dùng sai API và dependency | Dùng đúng Meter.MeterProvider trong Micrometer |
| Nghĩ provider tạo registry riêng | Quản lý lifecycle sai | Provider sử dụng registry được truyền vào |
| Cho rằng provider giới hạn số meter | Có thể phát sinh cardinality cao | Chuẩn hóa tag và dùng MeterFilter khi cần |

## 13. Checklist triển khai

- [ ] Xác nhận phiên bản Micrometer hỗ trợ MeterProvider.
- [ ] Chọn tên meter, description, base unit và tag cố định trong builder.
- [ ] Gọi withRegistry(registry) một lần khi khởi tạo component.
- [ ] Giữ MeterProvider trong field để tái sử dụng.
- [ ] Bổ sung tag động bằng withTag hoặc withTags tại call site.
- [ ] Giữ tập khóa tag nhất quán cho cùng meter name.
- [ ] Chuẩn hóa giá trị tag về tập hữu hạn.
- [ ] Không đưa định danh riêng hoặc nội dung tự do vào tag.
- [ ] Dùng Timer.Sample nếu chỉ biết outcome sau khi thao tác kết thúc.
- [ ] Kiểm thử các tổ hợp tag và số meter thực tế.
- [ ] Xác minh output ở backend nếu cần kiểm soát chi phí chuỗi thời gian.

MeterProvider tách cấu hình meter dùng chung khỏi các tag chỉ xác định được khi chạy. Builder giữ tên, mô tả, đơn vị và tag cố định; provider nhận tag động và trả về meter tương ứng trong registry. Tạo provider một lần, tái sử dụng ở component instrumentation và kiểm soát tập giá trị tag để giảm lặp mã mà vẫn giữ cardinality trong giới hạn.

## Tài liệu tham khảo

- [Meter Provider — Micrometer Reference](https://docs.micrometer.io/micrometer/reference/concepts/meter-provider.html)
- [Meter.MeterProvider API — Micrometer Core](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/Meter.MeterProvider.html)

