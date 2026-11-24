# @Timed với longTask và cách đọc dữ liệu tác vụ đang chạy

Micrometer cung cấp annotation **@Timed** để gắn phép đo thời gian vào method hoặc type. Khi đặt thuộc tính **longTask = true**, method được đo bằng **LongTaskTimer** thay vì Timer thông thường. LongTaskTimer bắt đầu khi method được gọi và tiếp tục công bố trạng thái trong suốt thời gian công việc còn chạy. Nhờ vậy, hệ thống giám sát có thể phát hiện một tác vụ đang kéo dài bất thường mà không cần đợi tác vụ hoàn tất.

Để đọc đúng dữ liệu, cần phân biệt ba phép đo của LongTaskTimer: số tác vụ đang hoạt động, tổng thời lượng của tất cả tác vụ đang hoạt động và thời lượng của tác vụ đang chạy lâu nhất. Khi tác vụ dừng, nó biến mất khỏi tập active; LongTaskTimer không giữ lịch sử thời lượng đã hoàn tất. Nếu cần cả trạng thái đang chạy và thời lượng sau khi hoàn tất, hãy ghi thêm một Timer thông thường.

## 1. Khi nào cần @Timed longTask?

Timer thông thường phù hợp với thao tác ngắn hoặc request có điểm bắt đầu và kết thúc rõ ràng. Nó ghi nhận count và total time sau khi một lần thực thi hoàn tất. Nếu một tác vụ chạy hàng chục phút, dashboard dựa trên Timer không thể biết lần chạy đó đang ở phút thứ mười hay phút thứ hai mươi; dữ liệu chỉ xuất hiện sau khi method kết thúc.

LongTaskTimer giải quyết trường hợp này bằng cách công bố trạng thái ngay khi tác vụ còn chạy. Những tình huống phù hợp gồm:

- Job đồng bộ dữ liệu từ hệ thống bên ngoài.
- Tác vụ tạo báo cáo hoặc xuất dữ liệu lớn.
- Batch xử lý nhiều bản ghi.
- Tác vụ bảo trì, kiểm tra hoặc làm mới cache theo lịch.
- Quy trình migration hoặc reconciliation kéo dài.
- Công việc nền có thời gian hoàn tất không xác định trước.

Ví dụ, một job làm mới metadata thường hoàn tất trong vài phút. Nếu dịch vụ bên ngoài chậm và job kéo dài một giờ, LongTaskTimer cho phép cảnh báo ngay trong khi job vẫn chạy. Với Timer thông thường, cảnh báo dựa trên thời lượng của lần chạy đó chỉ có thể được đánh giá sau khi job kết thúc.

## 2. Phân biệt Timer và LongTaskTimer

Hai meter đều đo thời gian nhưng công bố dữ liệu với mục tiêu khác nhau:

| Đặc điểm | Timer | LongTaskTimer |
|---|---|---|
| Khi bắt đầu ghi nhận | Khi method bắt đầu hoặc khi gọi record | Khi sample được start |
| Khi công bố thời lượng | Sau khi thao tác hoàn tất | Trong khi thao tác còn chạy |
| Số lần thực thi | Count của các lần đã hoàn tất | activeTasks của các lần đang chạy |
| Tổng thời lượng | Tổng thời lượng các lần đã ghi | Tổng thời lượng đã trôi qua của các lần đang active |
| Max | Giá trị max theo cấu hình và cửa sổ thống kê | Thời lượng của tác vụ active lâu nhất |
| Lịch sử sau khi hoàn tất | Có count và total time | Không giữ số liệu của tác vụ đã hoàn tất |
| Câu hỏi chính | Các lần thực thi đã mất bao lâu? | Hiện có bao nhiêu tác vụ chạy và chúng đã chạy bao lâu? |

Giả sử có hai lần chạy đồng thời, một lần đã chạy 30 giây và lần còn lại đã chạy 10 giây:

- activeTasks bằng 2.
- duration(TimeUnit.SECONDS) xấp xỉ 40 giây.
- max(TimeUnit.SECONDS) xấp xỉ 30 giây.

Khi tác vụ 30 giây kết thúc, activeTasks giảm còn 1, duration còn xấp xỉ 10 giây và max cũng xấp xỉ 10 giây. Các giá trị này mô tả tập tác vụ đang chạy tại thời điểm đọc, không phải tổng lịch sử.

## 3. @Timed có thuộc tính longTask

Annotation nằm trong package **io.micrometer.core.annotation**. Thuộc tính **longTask** chọn loại meter:

~~~java
@Timed(
    value = "metadata.refresh.active",
    longTask = true,
    description = "Thời lượng của các lần làm mới metadata đang chạy",
    extraTags = {"job", "metadata-refresh"}
)
public void refreshMetadata() {
    metadataClient.refresh();
}
~~~

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| value | Tên metric được đăng ký |
| longTask | true để dùng LongTaskTimer |
| description | Mô tả meter |
| extraTags | Các cặp key-value tag cố định |
| histogram | Bật percentile histogram cho Timer thông thường |
| percentiles | Chọn percentile phía ứng dụng cho Timer thông thường |
| serviceLevelObjectives | Các ngưỡng SLO cho Timer thông thường |

Với longTask, hãy tập trung vào tên meter, description và các tag biết được ngay khi tác vụ bắt đầu. Các thống kê phân phối dành cho Timer thông thường không nên được hiểu là cách cấu hình lịch sử hoàn tất cho LongTaskTimer. LongTaskTimer có tập phép đo active riêng.

Tag phải có cardinality thấp. Ví dụ, tag job có thể là metadata-refresh hoặc invoice-export. Không dùng job ID, request ID, tên file tùy ý hoặc user ID làm tag; mỗi giá trị mới có thể tạo một meter ID mới.

## 4. @Timed chỉ có tác dụng khi có thành phần xử lý annotation

Bản thân @Timed chỉ là metadata gắn vào method hoặc type. Một framework hoặc aspect phải đọc annotation và thực hiện việc ghi nhận. Spring Boot không tự động áp dụng @Timed cho mọi method trong mọi bean.

Có hai trường hợp cần phân biệt:

- **Spring Data Repository**: Spring Boot hỗ trợ @Timed trên Repository interface và method. Có thể dùng longTask = true để tạo LongTaskTimer cho lời gọi repository.
- **Service hoặc bean thông thường**: cần cấu hình Micrometer TimedAspect hoặc cơ chế AspectJ tương đương để các method được proxy có thể được intercept.

Micrometer cung cấp TimedAspect trong module micrometer-core. Với Spring Boot, có thể đăng ký aspect thành bean:

~~~java
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsAopConfiguration {

    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
~~~

TimedAspect là một aspect đang ở trạng thái incubating trong Micrometer. Hãy kiểm tra API và hành vi của phiên bản Micrometer mà ứng dụng khóa khi nâng cấp.

Ứng dụng cần có Spring AOP proxy infrastructure. Với Spring Boot, dependency spring-boot-starter-aop thường được dùng để cung cấp cấu hình AOP và thư viện cần thiết:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-aop")
~~~

Sau khi cấu hình, một bean Spring có thể dùng @Timed:

~~~java
import io.micrometer.core.annotation.Timed;
import org.springframework.stereotype.Service;

@Service
public class MetadataRefreshService {

    @Timed(
        value = "metadata.refresh.active",
        longTask = true,
        extraTags = {"job", "metadata-refresh"}
    )
    public void refresh() {
        metadataClient.refreshAll();
    }
}
~~~

Method phải được gọi qua Spring proxy thì aspect mới intercept được. Nếu gọi nội bộ bằng this.refresh() trong cùng object, lời gọi không đi qua proxy và phép đo có thể không được kích hoạt. Method cũng phải phù hợp với cách proxy đang dùng; tránh đặt instrumentation lên private hoặc final method khi proxy không thể intercept chúng.

Không tạo TimedAspect nhiều lần cho cùng registry nếu không có chủ đích. Một aspect bean dùng chung thường là đủ cho các bean được proxy trong ApplicationContext.

## 5. Ví dụ với tác vụ chạy theo lịch

Job làm mới dữ liệu là một ví dụ điển hình cho LongTaskTimer:

~~~java
import io.micrometer.core.annotation.Timed;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MetadataRefreshJob {

    private final MetadataRefreshService service;

    public MetadataRefreshJob(MetadataRefreshService service) {
        this.service = service;
    }

    @Scheduled(fixedDelayString = "PT10M")
    public void refresh() {
        service.refresh();
    }
}
~~~

Ứng dụng cũng cần bật scheduling bằng @EnableScheduling hoặc cấu hình tương đương để Spring đăng ký method @Scheduled.

~~~java
@Service
public class MetadataRefreshService {

    @Timed(
        value = "metadata.refresh.active",
        longTask = true,
        extraTags = {"job", "metadata-refresh"}
    )
    public void refresh() {
        // Gọi nguồn dữ liệu, đồng bộ và cập nhật trạng thái.
        metadataClient.refreshAll();
    }
}
~~~

Trong ví dụ này, scheduler gọi một bean service riêng. Lời gọi service đi qua proxy của Spring nên TimedAspect có thể bắt đầu và dừng LongTaskTimer. Nếu đặt @Timed trực tiếp lên method được scheduler gọi, hãy xác nhận bean vẫn được proxy và scheduler gọi method qua proxy đó.

Không nhầm @Timed với @Scheduled. @Scheduled quyết định thời điểm gọi method; @Timed đo thời gian thực thi method. Một annotation không tự thay thế chức năng của annotation còn lại.

## 6. LongTaskTimer bắt đầu và dừng lúc nào?

Với method đồng bộ, TimedAspect bắt đầu LongTaskTimer trước khi gọi method và dừng sample khi method trả về hoặc ném exception. Do đó, thời gian xử lý lỗi cũng đi qua nhánh cleanup và không để sample tiếp tục active sau khi method đã thoát.

~~~java
@Timed(value = "reports.export.active", longTask = true)
public void exportReport() {
    reportExporter.export();
}
~~~

Vòng đời có thể hình dung như sau:

~~~mermaid
sequenceDiagram
    participant Caller
    participant Proxy as TimedAspect
    participant Service
    participant Registry as LongTaskTimer

    Caller->>Proxy: Gọi exportReport()
    Proxy->>Registry: start sample
    Proxy->>Service: proceed()
    Service-->>Service: Đang xuất dữ liệu
    Note over Registry: activeTasks tăng và duration tiếp tục tăng
    Service-->>Proxy: return hoặc throw
    Proxy->>Registry: stop sample
    Note over Registry: activeTasks giảm
    Proxy-->>Caller: Trả kết quả hoặc ném lại exception
~~~

Nếu method trả về **CompletionStage** hoặc một kiểu con như CompletableFuture, TimedAspect giữ sample active cho đến khi stage hoàn tất bình thường hoặc exceptional. Như vậy, LongTaskTimer đo thời gian của công việc bất đồng bộ cho đến khi kết quả cuối cùng được hoàn thành, thay vì chỉ đo thời gian tạo future.

~~~java
@Timed(value = "reports.export.active", longTask = true)
public CompletableFuture<ExportResult> exportAsync() {
    return CompletableFuture.supplyAsync(reportExporter::export);
}
~~~

Lưu ý, TimedAspect nhận diện CompletionStage. Không mặc định rằng mọi kiểu bất đồng bộ đều được theo dõi đến lúc hoàn tất. Với Future không triển khai CompletionStage hoặc reactive type như Mono/Flux, method có thể trả về trước khi công việc thực tế kết thúc; aspect không tự động chờ tín hiệu hoàn tất của những kiểu này. Với reactive pipeline, hãy dùng instrumentation phù hợp với Reactor/Observation hoặc tự đặt ranh giới đo theo subscribe và terminal signal.

## 7. Đọc dữ liệu tác vụ đang chạy qua LongTaskTimer

Sau khi method được intercept và sample bắt đầu, registry có meter LongTaskTimer theo tên và tag đã khai báo. Có thể truy vấn trực tiếp:

~~~java
LongTaskTimer timer = registry.get("metadata.refresh.active")
    .tag("job", "metadata-refresh")
    .longTaskTimer();

int activeTasks = timer.activeTasks();

double totalActiveSeconds =
    timer.duration(TimeUnit.SECONDS);

double longestActiveSeconds =
    timer.max(TimeUnit.SECONDS);
~~~

Ba phép đo có ý nghĩa:

- **activeTasks()**: số lần thực thi hiện chưa kết thúc.
- **duration(TimeUnit)**: tổng thời gian đã trôi qua của tất cả lần thực thi còn active.
- **max(TimeUnit)**: thời lượng của lần thực thi active lâu nhất.

Nếu có ba job đang chạy được 5, 8 và 12 giây, activeTasks là 3, duration xấp xỉ 25 giây và max xấp xỉ 12 giây. Nếu job 12 giây kết thúc, các phép đo được tính lại trên hai job còn lại.

Khi không có tác vụ đang chạy, activeTasks, duration và max của tập active trở về 0. Không diễn giải duration là tổng thời gian đã xử lý trong ngày hoặc tổng thời gian của mọi job đã hoàn tất.

## 8. Đọc dữ liệu qua Spring Boot Actuator

Nếu Actuator được cấu hình và endpoint metrics được expose, có thể kiểm tra meter bằng HTTP:

~~~text
GET /actuator/metrics/metadata.refresh.active
~~~

Endpoint trả về tên meter, measurements và các tag có sẵn. Với LongTaskTimer, các phép đo tương ứng thường gồm active task count, duration và max. Tên statistic và định dạng phản hồi cụ thể phụ thuộc phiên bản Spring Boot và registry.

Có thể lọc theo tag:

~~~text
GET /actuator/metrics/metadata.refresh.active?tag=job:metadata-refresh
~~~

Endpoint metrics của Actuator hữu ích để kiểm tra meter đã được đăng ký và các giá trị hiện tại. Nó không nhất thiết hiển thị cùng tên chuỗi với exporter. Ví dụ, Prometheus có thể chuẩn hóa tên metric và đơn vị; cấu trúc series cụ thể phụ thuộc PrometheusMeterRegistry.

Khi kiểm tra trên dashboard, hãy xác định series nào biểu diễn số task active, tổng duration active và max active duration. Không giả định mọi registry đều đặt hậu tố hoặc tên chuỗi giống nhau.

## 9. Cách diễn giải các số liệu trên dashboard

Các phép đo LongTaskTimer hỗ trợ một số câu hỏi vận hành:

| Tín hiệu | Cách đọc | Câu hỏi cần điều tra |
|---|---|---|
| activeTasks tăng liên tục | Nhiều lần chạy đang chồng lấn hoặc chưa kết thúc | Scheduler có khởi chạy job mới trước khi job cũ xong không? |
| duration tăng nhanh | Tổng thời lượng của các task active đang tăng | Có quá nhiều tác vụ đồng thời hoặc từng task đang chậm không? |
| max tăng vượt ngưỡng | Có ít nhất một task đang chạy quá lâu | Phụ thuộc bên ngoài, lock hoặc batch có bị nghẽn không? |
| activeTasks không giảm | Sample chưa dừng hoặc công việc thực sự bị treo | Có đường thoát nào không đi qua cleanup không? |
| activeTasks bằng 0 | Không có task active tại thời điểm scrape | Job đã hoàn tất, chưa chạy hay bị bỏ lịch? |

Một cảnh báo có thể được tạo khi max active duration vượt thời gian vận hành cho phép. Với push registry, cảnh báo xuất hiện ở lần publish tiếp theo; với pull registry, nó xuất hiện ở lần scrape tiếp theo. Do đó, độ trễ phát hiện còn phụ thuộc chu kỳ xuất hoặc scrape.

Không nên cảnh báo chỉ dựa trên duration tổng nếu hệ thống cho phép nhiều job chạy đồng thời. Tổng duration tăng khi số task tăng, ngay cả khi từng task vẫn chạy bình thường. Đối với phát hiện một job bị treo, max thường là tín hiệu phù hợp hơn; kết hợp activeTasks để hiểu số lượng công việc đang chồng lấn.

## 10. Kết hợp LongTaskTimer với Timer thông thường

LongTaskTimer chỉ công bố tác vụ đang chạy. Sau khi sample dừng, nó không giữ lại count và total time của lần thực thi đã hoàn tất. Nếu cần cả hai góc nhìn, hãy dùng một metric name riêng cho Timer và LongTaskTimer.

Spring Boot hỗ trợ @Timed trên Spring Data Repository. Với repository invocation, một @Timed có longTask = true cần metric name riêng và có thể được kết hợp với short task timer. Với service method thông thường, có thể dùng @Timed longTask cho trạng thái active và ghi Timer riêng ở lớp điều phối:

~~~java
@Component
public class ReportRefreshCoordinator {

    private final MetadataRefreshService service;
    private final MeterRegistry registry;

    public ReportRefreshCoordinator(
            MetadataRefreshService service,
            MeterRegistry registry) {
        this.service = service;
        this.registry = registry;
    }

    public void runRefresh() {
        Timer.Sample sample = Timer.start(registry);

        try {
            service.refresh();
        } finally {
            sample.stop(registry.timer("metadata.refresh.duration"));
        }
    }
}
~~~

Trong ví dụ này:

- metadata.refresh.active là LongTaskTimer do @Timed longTask tạo.
- metadata.refresh.duration là Timer ghi nhận thời lượng sau khi lần gọi hoàn tất.
- Timer.Sample dừng trong finally nên cả trường hợp exception đều có một lần ghi nhận thời lượng hoàn tất.

Không dùng cùng một metric name cho LongTaskTimer và Timer. Hai meter có loại và ý nghĩa thống kê khác nhau; hãy dùng tên rõ ràng để backend không trộn lẫn.

## 11. Tag và cardinality của @Timed longTask

LongTaskTimer tạo meter theo tên và tổ hợp tag. Nếu mỗi lần chạy có một giá trị tag mới, registry có thể tạo thêm một meter ID. Vì vậy, tag phải phản ánh nhóm tác vụ có tập giá trị hữu hạn.

Ví dụ phù hợp:

~~~java
@Timed(
    value = "batch.processing.active",
    longTask = true,
    extraTags = {"batch.type", "invoice"}
)
public void processInvoices() {
    // ...
}
~~~

Ví dụ không phù hợp là gắn job ID hoặc file ID vào extraTags. Những định danh riêng này tạo cardinality cao và làm tăng bộ nhớ cùng số chuỗi thời gian ở backend.

Một LongTaskTimer có thể đại diện cho nhiều lần chạy đồng thời có cùng tag. Các phép đo active được cộng gộp trên meter đó. Nếu cần xác định chính xác job nào đang treo, dùng log hoặc trace với định danh riêng; không đưa định danh đó vào metric tag.

Với LongTaskTimer, tag cần có sẵn khi sample bắt đầu. Không thể dùng trạng thái cuối cùng của method để thay đổi tag cho sample đã active. Nếu cần phân tích kết quả success/failure sau khi hoàn tất, ghi thêm Counter hoặc Timer thông thường với outcome tag có tập giá trị hữu hạn.

## 12. Các giới hạn của AOP và @Timed

Khi sử dụng TimedAspect, cần kiểm tra các điều kiện sau:

- Bean phải do Spring quản lý hoặc được AspectJ weaving theo cách tương ứng.
- Lời gọi phải đi qua proxy; self-invocation không được intercept bởi proxy-based Spring AOP.
- Method không nên là private hoặc final nếu proxy strategy không thể intercept method đó.
- TimedAspect không tự xử lý meta-annotation có chứa @Timed.
- Spring Boot không tự động áp dụng @Timed cho mọi service method; cấu hình TimedAspect cho những method cần đo.
- Nếu một component đã được framework instrumentation, tránh thêm @Timed trùng cho cùng một thao tác.
- Với CompletionStage, sample được giữ đến khi stage hoàn tất; các kiểu asynchronous khác cần instrumentation riêng.

Nếu method không thể được intercept, có thể dùng LongTaskTimer trực tiếp:

~~~java
LongTaskTimer timer = LongTaskTimer.builder("metadata.refresh.active")
    .description("Thời gian làm mới metadata đang chạy")
    .register(registry);

public void refresh() {
    LongTaskTimer.Sample sample = timer.start();

    try {
        metadataClient.refreshAll();
    } finally {
        sample.stop();
    }
}
~~~

Cách dùng thủ công phù hợp khi cần kiểm soát ranh giới tác vụ chính xác hoặc không muốn phụ thuộc AOP. Mỗi lần start cần có một lần stop trong mọi đường thoát có kiểm soát.

## 13. Kiểm thử @Timed longTask

Kiểm thử cần chứng minh rằng meter active xuất hiện trong lúc method còn chạy và trở về 0 sau khi method kết thúc. Có thể dùng CountDownLatch để giữ method đang thực thi trong một khoảng thời gian có kiểm soát:

~~~java
@Service
public class BlockingRefreshService {

    @Timed(value = "test.refresh.active", longTask = true)
    public void refresh(
            CountDownLatch started,
            CountDownLatch release) throws InterruptedException {
        started.countDown();
        release.await();
    }
}
~~~

Một kiểm thử tích hợp trong Spring context có thể thực hiện như sau:

~~~java
@Test
void exposesActiveTaskUntilMethodCompletes() throws Exception {
    CountDownLatch started = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);

    ExecutorService executor = Executors.newSingleThreadExecutor();

    try {
        Future<?> invocation =
            executor.submit(() -> service.refresh(started, release));

        assertTrue(started.await(5, TimeUnit.SECONDS));

        LongTaskTimer timer = registry.get("test.refresh.active")
            .longTaskTimer();

        assertEquals(1, timer.activeTasks());
        assertTrue(timer.duration(TimeUnit.MILLISECONDS) > 0);

        release.countDown();
        invocation.get(5, TimeUnit.SECONDS);

        assertEquals(0, timer.activeTasks());
    } finally {
        release.countDown();
        executor.shutdownNow();
    }
}
~~~

Kiểm thử này cần TimedAspect được đăng ký trong test ApplicationContext và service phải được gọi qua Spring proxy. Trong ví dụ, executor bên ngoài chỉ giúp test quan sát method trong lúc đang chờ latch; LongTaskTimer được tạo bởi aspect.

Nên kiểm tra thêm:

- Method kết thúc bình thường thì activeTasks giảm.
- Method ném exception thì activeTasks vẫn giảm.
- CompletionStage chỉ dừng sample khi stage hoàn tất.
- Hai lần gọi đồng thời cùng tag làm activeTasks tăng lên 2.
- Meter name và extraTags đúng như cấu hình.
- Không có tag riêng cho từng lần chạy.
- Nếu dùng cả Timer và LongTaskTimer, hai metric name tách biệt và Timer count tăng sau khi hoàn tất.

Dùng timeout cho latch và Future để tránh test bị treo nếu assertion thất bại. Sau mỗi test, luôn giải phóng latch và shutdown executor.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ @Timed tự động chạy trên mọi method | Không có meter vì chưa có aspect hoặc framework hỗ trợ | Đăng ký TimedAspect cho service method |
| Gọi method bằng self-invocation | AOP proxy không intercept | Gọi qua bean proxy khác |
| Dùng Timer khi cần biết task đang chạy | Không có số liệu cho đến khi task hoàn tất | Dùng longTask = true |
| Đọc duration như lịch sử đã hoàn tất | Diễn giải sai dữ liệu active | Chỉ xem duration là tổng của các task đang chạy |
| Dùng cùng metric name cho Timer và LongTaskTimer | Xung đột loại meter hoặc semantics | Dùng tên riêng cho active và completed |
| Dùng job ID làm tag | Cardinality tăng theo từng lần chạy | Dùng nhóm tác vụ có tập giá trị hữu hạn |
| Cho rằng Future/Mono được theo dõi đến khi hoàn tất | LongTaskTimer có thể dừng khi method trả về | Kiểm tra kiểu trả về; dùng CompletionStage hoặc instrumentation reactive phù hợp |
| Không dừng sample trong nhánh lỗi khi đo thủ công | Task active bị giữ lại sau khi công việc kết thúc | Đặt stop trong finally |
| Coi activeTasks bằng 0 là job đã chạy thành công | Không phân biệt chưa chạy, đã xong hoặc bị bỏ lịch | Kết hợp trạng thái job, log và metric completed |

## 15. Checklist triển khai

- [ ] Chọn LongTaskTimer cho công việc cần quan sát trong lúc đang chạy.
- [ ] Đặt tên metric riêng cho trạng thái active.
- [ ] Dùng @Timed(longTask = true) trên method được framework hoặc TimedAspect xử lý.
- [ ] Đăng ký TimedAspect nếu cần đo service method thông thường.
- [ ] Bảo đảm lời gọi đi qua Spring proxy.
- [ ] Dùng CompletionStage nếu cần aspect chờ hoàn tất công việc bất đồng bộ.
- [ ] Đọc activeTasks, duration và max theo đúng ngữ nghĩa active.
- [ ] Dùng Timer riêng nếu cần count và total time của tác vụ đã hoàn tất.
- [ ] Giữ extraTags có cardinality thấp và giá trị ổn định.
- [ ] Không đưa job ID hoặc request ID vào metric tag.
- [ ] Kiểm tra endpoint Actuator và dữ liệu backend.
- [ ] Kiểm thử success, exception, concurrency và async completion.
- [ ] Đặt ngưỡng cảnh báo dựa trên max active duration và chu kỳ scrape/publish.

@Timed với longTask giúp theo dõi công việc trong lúc nó còn chạy. TimedAspect bắt đầu LongTaskTimer khi method được intercept và dừng khi method hoặc CompletionStage hoàn tất. Hãy đọc activeTasks, duration và max như trạng thái hiện tại; dùng Timer riêng để lưu thời lượng hoàn tất, giữ tag có cardinality thấp và xác minh method thực sự đi qua AOP proxy trước khi tin vào số liệu.

## Tài liệu tham khảo

- [Micrometer Long Task Timers](https://docs.micrometer.io/micrometer/reference/concepts/long-task-timers.html)
- [Micrometer Timers and @Timed](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Spring Boot Metrics — Spring Data Repository Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Timed Annotation API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/annotation/Timed.html)
- [TimedAspect API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/aop/TimedAspect.html)

