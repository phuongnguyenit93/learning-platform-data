# Đo phương thức trả CompletableFuture và xác minh thời điểm hoàn tất

Khi một phương thức trả về `CompletableFuture`, việc gọi phương thức và việc hoàn thành công việc là hai thời điểm khác nhau. Phương thức có thể trả future gần như ngay lập tức, trong khi tác vụ bên trong tiếp tục chạy trên executor trong vài mili giây, vài giây hoặc lâu hơn.

Nếu dừng Timer ngay khi phương thức trả về, số đo chỉ phản ánh thời gian tạo hoặc lấy future, không phản ánh thời gian hoàn thành công việc bất đồng bộ. Micrometer xử lý trường hợp này trong `TimedAspect`: khi kiểu trả về của phương thức là `CompletionStage` hoặc một kiểu con như `CompletableFuture`, Timer chỉ được dừng khi stage hoàn tất bình thường hoặc exceptional.

Để dùng cách đo này, cần có `@Timed`, một `TimedAspect` được đăng ký trong ứng dụng và một cơ chế AOP thực sự chặn lời gọi phương thức. Bài học tập trung vào ranh giới đo, các đường hoàn tất của future và cách viết kiểm thử chứng minh Timer chưa dừng khi future còn pending.

## 1. Vì sao đo CompletableFuture khác đo phương thức đồng bộ?

Với phương thức đồng bộ, khi lời gọi trả về thì công việc đã kết thúc:

~~~java
@Timed("report.generate")
public Report generate() {
    return reportGenerator.generate();
}
~~~

Timer có thể dừng khi phương thức trả về hoặc ném exception. Thời lượng phản ánh khoảng thời gian thực thi của phương thức.

Với phương thức bất đồng bộ:

~~~java
@Timed("report.generate")
public CompletableFuture<Report> generateAsync() {
    return CompletableFuture.supplyAsync(reportGenerator::generate, executor);
}
~~~

Phương thức thường chỉ tạo và trả về một CompletableFuture. Công việc `reportGenerator.generate()` có thể chưa bắt đầu hoặc vẫn đang chạy sau khi lời gọi đã trả về.

Hai khoảng thời gian khác nhau:

| Khoảng đo | Điểm bắt đầu | Điểm kết thúc | Ý nghĩa |
|---|---|---|---|
| Thời gian gọi method | Khi AOP bắt đầu chặn lời gọi | Khi method trả future | Chi phí tạo hoặc lấy future |
| Thời gian hoàn tất async | Khi AOP bắt đầu chặn lời gọi | Khi future hoàn tất | Thời gian từ lúc gọi method đến khi kết quả async kết thúc |

Với `TimedAspect`, trường hợp trả `CompletionStage` sử dụng khoảng thứ hai. Đây là điều cần thiết nếu mục tiêu là đo thời gian hoàn thành một công việc bất đồng bộ.

## 2. CompletableFuture là CompletionStage

`CompletableFuture<T>` triển khai interface `CompletionStage<T>`. Micrometer dùng abstraction `CompletionStage` để nhận diện các kết quả bất đồng bộ, vì vậy không chỉ riêng CompletableFuture mới được hỗ trợ.

Các kiểu trả về được nhận diện gồm:

- `CompletableFuture<T>`.
- `CompletionStage<T>`.
- Các lớp khác triển khai hoặc mở rộng `CompletionStage<T>`.

`Future<T>` thông thường không triển khai `CompletionStage`. Nếu phương thức khai báo kiểu trả về chỉ là `Future<T>`, `TimedAspect` không thể gắn callback `whenComplete` theo cơ chế này.

Điểm quan trọng: `TimedAspect` xác định khả năng bất đồng bộ dựa trên **kiểu trả về được khai báo của phương thức**, không chỉ dựa trên kiểu object thực tế tại runtime. Ví dụ, phương thức khai báo trả về `Object` nhưng thực tế trả một CompletableFuture sẽ không được nhận diện như phương thức CompletionStage.

~~~java
// Được nhận diện là asynchronous return type
public CompletableFuture<String> loadAsync() {
    return CompletableFuture.supplyAsync(this::load);
}

// Cũng được nhận diện
public CompletionStage<String> loadStage() {
    return CompletableFuture.supplyAsync(this::load);
}

// Không được nhận diện bằng kiểm tra kiểu trả về CompletionStage
public Object loadAsObject() {
    return CompletableFuture.supplyAsync(this::load);
}
~~~

Hãy khai báo kiểu trả về cụ thể và đúng với hợp đồng bất đồng bộ của API.

## 3. Cấu hình TimedAspect

`@Timed` nằm trong `micrometer-core`, nhưng annotation không tự tạo ra AOP interceptor. Cần đăng ký `TimedAspect`:

~~~java
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetricsAopConfiguration {
    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
~~~

Với Spring Boot, thêm AOP starter để kích hoạt cơ chế proxy:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
~~~

Ứng dụng cũng cần registry Micrometer tương ứng, thường đã được cấu hình qua Spring Boot Actuator và exporter. Không tạo một SimpleMeterRegistry riêng trong TimedAspect nếu mục tiêu là xuất dữ liệu vào registry đang được ứng dụng sử dụng.

Với Spring Framework không dùng Spring Boot, cần cấu hình Spring AOP, chẳng hạn `@EnableAspectJAutoProxy`, và dependency AOP tương ứng. Nếu dùng AspectJ weaving thay cho Spring proxy, cần cấu hình weaving theo môi trường.

Spring Boot không tự áp dụng `@Timed` cho mọi phương thức tùy ý chỉ vì có Actuator. Đối với các service method thông thường, cần đăng ký `TimedAspect` hoặc dùng một cơ chế instrumentation khác đã được cấu hình.

## 4. Đánh dấu phương thức trả CompletableFuture bằng @Timed

Ví dụ một service tạo báo cáo bất đồng bộ:

~~~java
import io.micrometer.core.annotation.Timed;
import org.springframework.stereotype.Service;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

@Service
class ReportService {
    private final ReportGenerator generator;
    private final Executor reportExecutor;

    ReportService(ReportGenerator generator, Executor reportExecutor) {
        this.generator = generator;
        this.reportExecutor = reportExecutor;
    }

    @Timed(
            value = "report.generate",
            description = "Time until an asynchronous report generation completes",
            extraTags = {"component", "reporting"}
    )
    public CompletableFuture<Report> generateAsync(ReportRequest request) {
        return CompletableFuture.supplyAsync(
                () -> generator.generate(request),
                reportExecutor
        );
    }
}
~~~

Khi lời gọi đi qua Spring proxy:

1. `TimedAspect` bắt đầu một `Timer.Sample`.
2. Aspect gọi phương thức gốc.
3. Phương thức trả về CompletableFuture.
4. Aspect gắn callback hoàn tất vào CompletionStage.
5. Timer được ghi khi stage hoàn tất bình thường hoặc exceptional.

Tag cố định trong `extraTags` được gắn vào Timer. `TimedAspect` cũng ghi tag `exception` để phân biệt hoàn tất bình thường và exceptional. Giá trị mặc định cho trường hợp không có exception là `none`; khi có lỗi, aspect dùng tên lớp exception theo cơ chế của phiên bản Micrometer.

Không đưa request ID, report ID, user ID hoặc exception message vào tag. Những giá trị này có cardinality cao; hãy dùng log hoặc trace để liên kết một lần chạy cụ thể.

## 5. Thời điểm Timer bắt đầu và kết thúc

Giả sử phương thức trả future sau 2 ms, nhưng future chỉ hoàn tất sau 800 ms:

~~~text
T0        AOP bắt đầu và Timer.Sample được tạo
T0 + 2ms  Method trả CompletableFuture đang pending
T0 + 2ms  TimedAspect gắn callback hoàn tất
T0 + 800ms CompletableFuture hoàn tất
T0 + 800ms Timer.Sample được dừng và ghi vào Timer
~~~

Thời lượng được ghi xấp xỉ 800 ms, không phải 2 ms. Thời gian từ lúc gọi method đến khi future hoàn tất được tính vào cùng một lần đo.

Điều này có ý nghĩa với các công việc như:

- Gọi dịch vụ ngoài theo kiểu bất đồng bộ.
- Sinh báo cáo trên executor.
- Đọc dữ liệu từ nhiều nguồn rồi tổng hợp bằng CompletableFuture.
- Chạy pipeline xử lý có nhiều stage.
- Gửi message và chờ kết quả xử lý bất đồng bộ.

Nếu cần đo riêng thời gian tạo future và thời gian thực thi background, hãy tạo hai phép đo có tên và ranh giới khác nhau. Không diễn giải một Timer duy nhất như thể nó chỉ đo CPU time của worker.

## 6. Hoàn tất bình thường

Khi future hoàn tất với kết quả, callback của aspect dừng sample:

~~~java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(() -> "done", executor);
~~~

Sau khi stage hoàn tất:

- Timer count tăng một.
- Total time tăng theo thời lượng từ lúc aspect bắt đầu đến lúc stage hoàn tất.
- Tag `exception` có giá trị biểu thị không có exception.

Giá trị kết quả không cần là một kiểu cụ thể. Aspect chỉ quan tâm CompletionStage đã hoàn tất; nó không đo kích thước hoặc nội dung object kết quả trừ khi ứng dụng tự bổ sung instrumentation.

## 7. Hoàn tất exceptional

CompletableFuture có thể hoàn tất với lỗi:

~~~java
CompletableFuture<Report> future =
        CompletableFuture.supplyAsync(() -> {
            throw new ReportGenerationException("source unavailable");
        }, executor);
~~~

Khi future hoàn tất exceptional, callback vẫn chạy và Timer được dừng. Như vậy, lỗi không làm mất thời lượng của lần thực thi.

Micrometer ghi nhận exception bằng tag riêng. Trong ví dụ, tag có thể phản ánh lớp `ReportGenerationException` hoặc lớp cause theo cách triển khai của phiên bản Micrometer. Không nên dựa vào message lỗi để tạo tag vì message có thể chứa dữ liệu thay đổi liên tục.

Future exceptional khác với phương thức ném exception đồng bộ:

- **Exceptional completion:** method trả về future trước, sau đó future hoàn tất với lỗi. Aspect dừng Timer trong callback.
- **Synchronous throw:** method ném exception trước khi trả future. Aspect bắt lỗi quanh `proceed()`, dừng Timer ngay và ném lại exception.

Cả hai đường đều cần được kiểm thử.

## 8. Hủy future và timeout

Hủy CompletableFuture làm stage hoàn tất theo trạng thái cancellation, thường được biểu diễn bằng `CancellationException`. Vì đây là một dạng hoàn tất exceptional, callback của `TimedAspect` vẫn được gọi và Timer được ghi nhận.

~~~java
CompletableFuture<Report> future = reportService.generateAsync(request);
future.cancel(true);
~~~

Lưu ý rằng `cancel(true)` không bảo đảm mọi công việc nền thực sự dừng. Với CompletableFuture, cancellation chủ yếu làm thay đổi trạng thái future; tác vụ đang chạy có thể tiếp tục nếu executor hoặc công việc không hỗ trợ hủy tương ứng. Timer đo thời gian đến khi future chuyển sang trạng thái hoàn tất, không chứng minh tài nguyên nền đã được giải phóng.

Timeout có thể được tạo bằng:

~~~java
CompletableFuture<Report> timed =
        reportService.generateAsync(request)
                .orTimeout(2, TimeUnit.SECONDS);
~~~

Khi timeout làm future hoàn tất exceptional, Timer dừng ở thời điểm đó. Nếu công việc nền tiếp tục chạy sau timeout, thời gian chạy thực tế của công việc có thể dài hơn thời gian được ghi bởi future đã timeout. Nếu cần quan sát cả vòng đời worker, instrument worker riêng hoặc dùng LongTaskTimer.

## 9. Future không bao giờ hoàn tất

Nếu CompletableFuture vẫn pending, callback không được gọi và Timer chưa được ghi nhận. Điều này đúng với ngữ nghĩa đo: thao tác chưa kết thúc nên chưa có duration hoàn chỉnh.

Hệ quả vận hành:

- Timer count không tăng cho future đang pending.
- Không có mẫu duration hoàn tất cho thao tác bị treo.
- Dashboard Timer có thể trông bình thường dù có future tồn tại quá lâu.

Để quan sát các công việc đang chạy, kết hợp LongTaskTimer hoặc một Gauge đếm số future pending. Ví dụ, LongTaskTimer có thể bắt đầu khi submit và dừng khi stage hoàn tất. Khi đó:

- LongTaskTimer cho biết tác vụ nào đang active và đã chạy bao lâu.
- Timer cho biết duration của các lần đã hoàn tất.

Có thể yêu cầu `TimedAspect` dùng LongTaskTimer bằng thuộc tính `longTask`:

~~~java
@Timed(value = "report.generate.active", longTask = true)
public CompletableFuture<Report> generateAsync(ReportRequest request) {
    return generator.generateAsync(request);
}
~~~

Với CompletionStage, LongTaskTimer cũng được dừng khi stage hoàn tất. Meter này hữu ích để quan sát số tác vụ active và thời lượng đang chạy; khi sample dừng, nó không giữ lại phân phối duration của các lần đã hoàn tất như Timer.

Không dùng Timer hoàn tất như tín hiệu duy nhất để phát hiện future bị treo.

## 10. Method trả null

Nếu một phương thức khai báo trả CompletionStage nhưng thực tế trả `null`, aspect không thể chờ một stage không tồn tại. `TimedAspect` ghi Timer ngay sau khi method trả về null.

Đây thường là dấu hiệu hợp đồng API không nhất quán. Phương thức bất đồng bộ nên luôn trả về một CompletionStage hợp lệ, kể cả khi không có kết quả:

~~~java
return CompletableFuture.completedFuture(null);
~~~

hoặc trả về một stage hoàn tất với trạng thái nghiệp vụ phù hợp. Không dùng null để biểu diễn một future chưa sẵn sàng.

## 11. Kiểu trả về khai báo ảnh hưởng đến hành vi

Aspect kiểm tra kiểu trả về được khai báo của phương thức:

~~~java
private static boolean stopWhenCompleted(Method method) {
    return CompletionStage.class.isAssignableFrom(method.getReturnType());
}
~~~

Vì vậy:

| Khai báo method | Giá trị runtime | Dừng Timer |
|---|---|---|
| `CompletableFuture<T>` | CompletableFuture | Khi future hoàn tất |
| `CompletionStage<T>` | CompletableFuture | Khi stage hoàn tất |
| Một lớp con CompletionStage | Lớp con đó | Khi stage hoàn tất |
| `Future<T>` | FutureTask | Khi method trả về |
| `Object` | CompletableFuture | Khi method trả về |

Nếu cần đo đến khi hoàn tất, hãy khai báo kiểu trả về là CompletionStage hoặc một kiểu con. Với API chỉ có Future, có thể chuyển đổi sang CompletableFuture/CompletionStage hoặc tự quản lý Timer.Sample.

## 12. @Async kết hợp @Timed

Micrometer minh họa việc dùng `@Async` cùng `@Timed`:

~~~java
@Async("reportExecutor")
@Timed("report.generate")
public CompletableFuture<Report> generateAsync(ReportRequest request) {
    Report report = generator.generate(request);
    return CompletableFuture.completedFuture(report);
}
~~~

Trong ví dụ này, Spring `@Async` đưa phần thân method lên `reportExecutor`; method trả một future đã hoàn tất với kết quả tính được. Nếu thay phần thân bằng một `supplyAsync` khác, hãy tránh vô tình submit công việc hai lần lên hai executor khác nhau.

Thứ tự interceptor/proxy ảnh hưởng đến ranh giới bắt đầu của Timer khi có nhiều advice như `@Async` và `@Timed`. Tùy cách proxy được sắp xếp, thời gian chờ trong hàng đợi executor có thể nằm trong hoặc ngoài khoảng đo. Nếu SLA yêu cầu bao gồm queue wait, hãy kiểm tra cấu hình thực tế bằng test; nếu muốn tách queue wait và execution time, hãy instrument hai giai đoạn riêng.

Không giả định chỉ nhìn annotation là biết Timer có bao gồm thời gian chờ executor hay không. Hãy xác minh bằng một executor có thể điều khiển và một future được hoàn tất có chủ đích.

## 13. Spring AOP proxy boundary

Annotation chỉ có tác dụng khi lời gọi đi qua proxy hoặc được AspectJ weaving. Với Spring AOP proxy:

- Method cần được gọi từ một bean khác qua proxy.
- Self-invocation qua `this.method()` không đi qua proxy nên aspect thường không chạy.
- Private method không phải điểm join phù hợp cho proxy-based Spring AOP.
- Final method không thể được override bởi class-based proxy.
- Với JDK dynamic proxy, caller phải gọi qua interface mà proxy expose.

Ví dụ self-invocation:

~~~java
@Service
class ReportService {
    public CompletableFuture<Report> start() {
        return generateAsync(); // gọi nội bộ, bỏ qua proxy của generateAsync
    }

    @Timed("report.generate")
    public CompletableFuture<Report> generateAsync() {
        return CompletableFuture.supplyAsync(generator::generate);
    }
}
~~~

Trong ví dụ, `generateAsync()` được gọi trực tiếp trên `this`, không qua proxy. Có thể chuyển phương thức được đo sang một bean riêng hoặc gọi qua một collaborator được inject.

~~~java
@Service
class ReportFacade {
    private final TimedReportWorker worker;

    ReportFacade(TimedReportWorker worker) {
        this.worker = worker;
    }

    CompletableFuture<Report> start() {
        return worker.generateAsync();
    }
}

@Service
class TimedReportWorker {
    @Timed("report.generate")
    public CompletableFuture<Report> generateAsync() {
        return CompletableFuture.supplyAsync(generator::generate);
    }
}
~~~

## 14. Tránh đo trùng với instrumentation của framework

Spring Boot và các integration có thể đã instrument một số điểm như HTTP server request. Nếu thêm `@Timed` lên controller hoặc phương thức được framework đo sẵn, có thể xuất hiện hai meter mô tả các khoảng thời gian khác nhau hoặc trùng ý nghĩa.

Trước khi thêm annotation:

1. Kiểm tra framework đã tạo meter nào.
2. Xác định ranh giới của meter có sẵn.
3. Chỉ thêm `@Timed` nếu cần đo một thao tác nghiệp vụ riêng.
4. Dùng tên metric khác nếu ý nghĩa hoặc phạm vi đo khác.

Ví dụ, `http.server.requests` đo vòng đời request ở server. `report.generate` đo thời gian tạo báo cáo bất đồng bộ bên trong request. Hai meter có thể bổ sung cho nhau nếu được đặt tên và giải thích rõ.

## 15. Tự quản lý Timer.Sample khi không dùng AOP

Nếu method không đi qua proxy, hoặc cần kiểm soát chính xác callback và tag kết quả, có thể dùng `Timer.Sample`:

~~~java
public CompletableFuture<Report> generateAsync(ReportRequest request) {
    Timer.Sample sample = Timer.start(registry);
    CompletableFuture<Report> future;

    try {
        future = generator.generateAsync(request);
    } catch (RuntimeException | Error error) {
        sample.stop(registry.timer(
                "report.generate",
                "outcome", "synchronous-error"
        ));
        throw error;
    }

    if (future == null) {
        sample.stop(registry.timer(
                "report.generate",
                "outcome", "no-stage"
        ));
        return null;
    }

    return future.whenComplete((result, error) -> {
        String outcome = error == null ? "success" : "failure";
        sample.stop(registry.timer(
                "report.generate",
                "outcome", outcome
        ));
    });
}
~~~

Ví dụ này minh họa việc chọn tag ở thời điểm hoàn tất. Trong ứng dụng thực tế, cần chuẩn hóa outcome thành tập hữu hạn và quyết định hợp đồng xử lý null. Nếu future có thể bị hủy, callback `whenComplete` vẫn nhận completion exceptional và sample được dừng.

Không dùng cả @Timed và Timer.Sample thủ công cho cùng một ranh giới đo, nếu không thời lượng có thể bị ghi hai lần.

## 16. Kiểm thử thời điểm hoàn tất bằng CompletableFuture điều khiển được

Một kiểm thử tốt không nên dùng `Thread.sleep()` để đoán thời điểm future hoàn tất. Hãy giữ một CompletableFuture chưa hoàn tất, gọi method qua Spring proxy, xác minh Timer chưa tăng count, sau đó chủ động hoàn tất future.

Service được kiểm thử:

~~~java
@Service
public class AsyncReportService {
    private final CompletableFuture<String> pending = new CompletableFuture<>();

    @Timed("report.async")
    public CompletableFuture<String> load() {
        return pending;
    }

    void complete(String value) {
        pending.complete(value);
    }
}
~~~

Cấu hình test cần bật AOP và đăng ký TimedAspect:

~~~java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class TimedTestConfiguration {
    @Bean
    MockClock mockClock() {
        return new MockClock();
    }

    @Bean
    SimpleMeterRegistry meterRegistry(MockClock clock) {
        return new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
    }

    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }

    @Bean
    AsyncReportService asyncReportService() {
        return new AsyncReportService();
    }
}
~~~

Kiểm thử:

~~~java
@SpringJUnitConfig(TimedTestConfiguration.class)
class AsyncReportServiceTest {
    @Autowired
    AsyncReportService service;

    @Autowired
    MeterRegistry registry;

    @Autowired
    MockClock clock;

    @Test
    void recordsTimerOnlyAfterFutureCompletes() {
        CompletableFuture<String> returned = service.load();
        Timer timer = registry.get("report.async").timer();

        assertThat(returned).isNotNull();
        assertThat(returned.isDone()).isFalse();
        assertThat(timer.count()).isZero();

        clock.add(250, TimeUnit.MILLISECONDS);
        service.complete("ready");
        assertThat(returned.join()).isEqualTo("ready");

        assertThat(timer.count()).isEqualTo(1);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(250.0);
    }
}
~~~

Điểm cần xác minh không phải duration chính xác bằng bao nhiêu nanosecond. Kiểm thử cần chứng minh count vẫn bằng 0 khi future pending và chỉ tăng sau khi future hoàn tất.

Lưu ý: aspect gắn callback `whenComplete`, vì vậy stage được trả qua proxy có thể là một CompletionStage phụ thuộc được tạo bởi `whenComplete`, không nhất thiết cùng object identity với future ban đầu. Hãy kiểm tra kết quả và completion semantics thay vì dùng `assertSame` để yêu cầu proxy trả đúng cùng tham chiếu.

## 17. Kiểm thử exceptional completion

Dùng `completeExceptionally` để xác minh Timer vẫn được ghi:

~~~java
CompletableFuture<String> returned = service.load();
Timer timer = registry.get("report.async").timer();

assertThat(timer.count()).isZero();

service.fail(new IllegalStateException("source unavailable"));

assertThatThrownBy(returned::join)
        .isInstanceOf(CompletionException.class);

assertThat(timer.count()).isEqualTo(1);
~~~

Trong ví dụ, service cần cung cấp phương thức test hoặc collaborator để hoàn tất future exceptional:

~~~java
void fail(Throwable error) {
    pending.completeExceptionally(error);
}
~~~

Kiểm thử này xác nhận exceptional completion vẫn dừng Timer. Không kiểm tra tag exception bằng message lỗi; hãy kiểm tra tag theo lớp exception nếu cần và giữ danh mục tag hữu hạn.

## 18. Kiểm thử synchronous throw và cancellation

Hai đường kết thúc khác cần được kiểm thử riêng:

| Trường hợp | Hành vi mong đợi |
|---|---|
| Method ném exception trước khi trả stage | Aspect ghi Timer ngay rồi ném lại lỗi |
| Future bị cancel | Stage hoàn tất exceptional; callback ghi Timer |
| Future timeout | Stage hoàn tất exceptional; callback ghi Timer |
| Future pending mãi | Timer chưa được ghi vì chưa có completion |
| Method trả null | Aspect ghi Timer tại thời điểm method trả về null |

Với cancellation, hãy kiểm tra count tăng sau khi stage chuyển sang trạng thái cancelled. Không giả định tác vụ nền đã thực sự dừng; cần kiểm thử riêng cơ chế hủy của executor hoặc thư viện thực hiện công việc.

## 19. Quan sát Timer trên backend

Với Prometheus registry, Timer thường xuất các chuỗi thời gian count và sum; tên cuối cùng phụ thuộc naming convention:

~~~text
report_async_seconds_count
report_async_seconds_sum
~~~

Tốc độ hoàn tất:

~~~promql
rate(report_async_seconds_count[5m])
~~~

Thời lượng trung bình của các future hoàn tất trong cửa sổ:

~~~promql
rate(report_async_seconds_sum[5m])
/
rate(report_async_seconds_count[5m])
~~~

Nếu aspect ghi tag `exception`, có thể phân tích số lần hoàn tất theo loại kết quả:

~~~promql
sum by (exception) (
  rate(report_async_seconds_count[5m])
)
~~~

Kiểm tra scrape output để xác nhận tên và label thực tế. Không giả định tên metric luôn giống ví dụ vì registry có thể chuẩn hóa tên, thêm hậu tố đơn vị hoặc thay đổi convention.

Timer chỉ có dữ liệu cho các lần đã hoàn tất. Nếu cần biết số future pending hiện tại, bổ sung Gauge hoặc LongTaskTimer; không suy ra số future đang chạy từ Timer count.

## 20. Cardinality của exception và tag

`TimedAspect` thêm tag exception để phân biệt hoàn tất bình thường và exceptional. Thông tin exception thường là tên lớp, không phải message. Dù vậy, ứng dụng có thể tạo nhiều lớp exception động hoặc lớp proxy sinh tự động; cần quan sát số giá trị tag thực tế.

Các tag an toàn hơn:

- `outcome=success|failure|cancelled`.
- `operation=generate|refresh|export`.
- `dependency=inventory|pricing|catalog`.

Tránh:

- Exception message.
- Stack trace.
- Request ID hoặc trace ID.
- User ID, tenant ID hoặc report ID.
- URL có path động.

Metrics cần nhóm sự kiện để tổng hợp. Log và trace mới là nơi phù hợp để truy tìm một lần thực thi cụ thể.

## 21. Những lỗi thường gặp

**Dừng Timer khi method trả future.** Duration chỉ đo thời gian tạo future. Để aspect nhận diện CompletionStage và dừng khi future hoàn tất.

**Khai báo kiểu trả về là Object hoặc Future.** Aspect không nhận diện được CompletionStage theo kiểu khai báo. Dùng CompletableFuture hoặc CompletionStage khi hợp đồng API là bất đồng bộ.

**Cho rằng @Timed tự hoạt động.** Cần TimedAspect và AOP proxy hoặc AspectJ weaving. Spring Boot Actuator không tự áp dụng annotation cho mọi service method.

**Gọi method nội bộ qua this.** Self-invocation bỏ qua Spring proxy. Chuyển phương thức sang bean khác hoặc gọi qua proxy.

**Chỉ xử lý nhánh thành công.** Future exceptional hoặc cancelled cũng là completion. TimedAspect ghi Timer ở các nhánh này; với instrumentation thủ công phải gắn whenComplete hoặc xử lý mọi đường kết thúc.

**Dùng sleep để kiểm thử.** Thời gian thực khiến test chậm và không ổn định. Dùng future điều khiển được để xác minh count trước và sau completion.

**Cho rằng cancel luôn dừng công việc nền.** Cancellation của future không đảm bảo executor hoặc thư viện dừng tác vụ. Theo dõi lifecycle của worker riêng.

**Không quan sát future pending.** Timer chưa ghi nhận khi stage chưa hoàn tất. Dùng LongTaskTimer hoặc Gauge để theo dõi công việc đang chạy.

**Đo trùng cùng một thao tác.** Kiểm tra framework đã tạo HTTP/server Timer hay chưa và tránh kết hợp @Timed với Timer.Sample cho cùng ranh giới.

## 22. Checklist triển khai

Trước khi đưa annotation vào service bất đồng bộ, hãy xác minh:

- [ ] Phương thức khai báo trả về CompletableFuture hoặc CompletionStage.
- [ ] TimedAspect được đăng ký vào MeterRegistry đang xuất metrics.
- [ ] Spring AOP proxy hoặc AspectJ weaving thực sự hoạt động.
- [ ] Lời gọi đi qua proxy, không phải self-invocation.
- [ ] Timer chưa tăng count khi future còn pending.
- [ ] Timer tăng count khi future hoàn tất bình thường.
- [ ] Timer tăng count khi future hoàn tất exceptional.
- [ ] Synchronous throw được ghi nhận và exception vẫn được ném lại.
- [ ] Cancellation và timeout có hành vi được kiểm thử.
- [ ] Future không hoàn tất được theo dõi bằng LongTaskTimer hoặc Gauge nếu cần.
- [ ] Tag exception và extraTags có cardinality được kiểm soát.
- [ ] Không ghi trùng với instrumentation của framework.
- [ ] Dashboard phân biệt duration hoàn tất và số tác vụ đang active.

## 23. Kết luận

Với phương thức trả CompletableFuture, thời điểm method trả về không phải thời điểm công việc hoàn tất. `TimedAspect` nhận diện phương thức có kiểu trả về `CompletionStage` hoặc kiểu con, gắn callback hoàn tất và chỉ dừng Timer khi stage hoàn tất bình thường hoặc exceptional. Synchronous throw cũng được ghi nhận; stage bị hủy hoặc timeout được xem là hoàn tất exceptional.

Để phép đo hoạt động, cần đăng ký `TimedAspect`, bật AOP proxy và bảo đảm lời gọi đi qua proxy. Hãy kiểm thử bằng CompletableFuture điều khiển được: Timer count phải bằng 0 khi future pending và tăng sau khi future hoàn tất. Nếu cần theo dõi các future chưa hoàn tất hoặc bị treo, bổ sung LongTaskTimer/Gauge vì Timer chỉ ghi nhận các lần đã kết thúc.

## Tài liệu tham khảo

- [Micrometer – Timers and @Timed](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer – Timed annotation API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/annotation/Timed.html)
- [Micrometer – TimedAspect API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/aop/TimedAspect.html)
- [Spring Framework – Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Java – CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
