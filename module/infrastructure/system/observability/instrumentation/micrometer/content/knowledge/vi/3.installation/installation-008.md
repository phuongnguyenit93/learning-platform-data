# Quản lý đóng registry và tài nguyên khi ứng dụng kết thúc

Một ứng dụng dùng Micrometer cần quản lý vòng đời của MeterRegistry và những tài nguyên phụ trợ do quá trình xuất metrics tạo ra. Nếu registry hoặc scheduler tiếp tục chạy sau khi ứng dụng đã dừng xử lý nghiệp vụ, tiến trình có thể giữ lại thread, kết nối hoặc tác vụ nền không còn cần thiết. Nếu đóng registry quá sớm, các request đang hoàn tất có thể không ghi được số đo cuối cùng.

Nguyên tắc quan trọng là **mỗi tài nguyên cần có một chủ sở hữu vòng đời rõ ràng**. Thành phần tạo và quản lý tài nguyên chịu trách nhiệm đóng nó khi phạm vi sử dụng kết thúc. Trong Spring Boot, ApplicationContext thường là chủ sở hữu của các bean registry và đóng chúng khi context dừng. Với registry được tạo thủ công trong ứng dụng Java độc lập, mã tạo registry phải đóng registry tương ứng.

## 1. Những tài nguyên nào cần được quản lý?

MeterRegistry là điểm nhận các lần ghi meter. Tùy implementation, registry có thể quản lý thêm tài nguyên như scheduler dùng để xuất dữ liệu định kỳ, client hoặc bộ đệm phục vụ việc gửi metrics. Không phải registry nào cũng có cùng hành vi: registry kiểu pull thường chờ hệ thống giám sát đọc dữ liệu, trong khi registry kiểu push hoặc step có thể chạy tác vụ nền để gửi dữ liệu theo chu kỳ.

Ngoài registry, ứng dụng có thể sở hữu những tài nguyên liên quan:

| Tài nguyên | Ví dụ | Trách nhiệm khi dừng |
|---|---|---|
| MeterRegistry | SimpleMeterRegistry, registry cho Prometheus hoặc backend khác | Đóng registry do ứng dụng tạo và sở hữu |
| Bộ lập lịch xuất dữ liệu | Scheduler của push/step registry hoặc scheduler tự viết | Dừng lịch chạy, chờ tác vụ đang thực hiện trong giới hạn hợp lý |
| Executor và worker | Thread pool dùng cho tác vụ metrics tùy chỉnh | Ngừng nhận tác vụ mới, hoàn tất hoặc hủy tác vụ còn lại |
| Client hoặc exporter riêng | HTTP client, exporter do ứng dụng tự khởi tạo | Đóng nếu ứng dụng sở hữu tài nguyên đó |
| Máy chủ cung cấp endpoint scrape | HTTP server độc lập dùng để phục vụ metrics | Dừng server theo vòng đời của server |
| Đối tượng được Gauge quan sát | Queue, cache, pool hoặc cấu trúc dữ liệu nghiệp vụ | Giữ đối tượng sống trong thời gian cần đo và giải phóng theo vòng đời nghiệp vụ |

Việc đăng ký một meter không có nghĩa là mỗi meter cần được đóng riêng. Thông thường, MeterRegistry quản lý các meter đã đăng ký; khi registry kết thúc vòng đời, registry sẽ thực hiện phần dọn dẹp thuộc implementation của nó. Những tài nguyên bên ngoài registry, chẳng hạn executor do ứng dụng tự tạo, vẫn cần được quản lý riêng.

### Registry pull và registry push

Với mô hình pull, hệ thống giám sát chủ động đọc số liệu từ endpoint. Registry thường giữ trạng thái meter để trả lời các lần scrape. Nếu endpoint được phục vụ bởi một HTTP server riêng, vòng đời của server thuộc về thành phần quản lý server đó.

Với mô hình push hoặc step, registry có thể xuất số liệu theo chu kỳ. Scheduler và tác vụ xuất dữ liệu cần dừng khi registry đóng. Một lần đóng registry không nên được hiểu là cam kết mọi backend đều nhận được một lần gửi cuối cùng; hành vi flush hoặc publish cuối phụ thuộc implementation và cấu hình. Nếu yêu cầu vận hành cần lần gửi cuối, hãy dùng cơ chế flush được backend hỗ trợ và kiểm tra hành vi của phiên bản đang triển khai.

## 2. Xác định chủ sở hữu của MeterRegistry

Trước khi viết mã đóng registry, cần xác định registry được tạo ở đâu và ai chịu trách nhiệm vòng đời của nó.

- Registry do Spring Boot auto-configuration tạo và đăng ký thành bean thường thuộc quyền quản lý của Spring ApplicationContext.
- Registry do ứng dụng tự tạo trong một bean Spring nên được khai báo như một bean có lifecycle để Spring đóng khi context kết thúc.
- Registry được tạo trong một chương trình Java độc lập phải được đóng trong chính phạm vi mã tạo nó.
- Registry dùng chung giữa nhiều service hoặc component chỉ nên được đóng bởi chủ sở hữu chung. Component chỉ nhận registry qua dependency injection không được tự ý đóng tài nguyên dùng chung.

Quy tắc này ngăn lỗi đóng lặp hoặc đóng quá sớm. Ví dụ, một service nhận MeterRegistry qua constructor chỉ cần đăng ký Counter hoặc Timer. Service không sở hữu registry nên không gọi close trong phương thức dừng của chính nó. Nếu nhiều component cùng sử dụng một registry, việc một component đóng registry có thể khiến các component còn lại không ghi được số đo.

## 3. Spring Boot quản lý registry theo vòng đời ApplicationContext

Trong ứng dụng Spring Boot, nên sử dụng MeterRegistry đã được cấu hình và inject vào các component. Khi ApplicationContext dừng, Spring thực hiện quy trình hủy bean và gọi callback hủy tương ứng của những bean có hỗ trợ. MeterRegistry được quản lý như một bean vì thế có thể được đóng theo lifecycle của context.

Ví dụ component chỉ sử dụng registry:

~~~java
@Component
public class CheckoutMetrics {

    private final Counter completedOrders;

    public CheckoutMetrics(MeterRegistry meterRegistry) {
        this.completedOrders = meterRegistry.counter("checkout.orders.completed");
    }

    public void recordCompletedOrder() {
        completedOrders.increment();
    }
}
~~~

CheckoutMetrics chỉ sử dụng registry được inject. Component không cần tự đóng Counter hoặc MeterRegistry. Khi ứng dụng dừng, Spring quản lý vòng đời bean registry và thực hiện bước hủy phù hợp.

Nếu ứng dụng tự tạo một registry tùy chỉnh, có thể khai báo registry thành bean để Spring quản lý:

~~~java
@Configuration
public class MetricsConfiguration {

    @Bean(destroyMethod = "close")
    MeterRegistry reportingMeterRegistry() {
        return new SimpleMeterRegistry();
    }
}
~~~

Khai báo destroy method làm rõ rằng registry tùy chỉnh cần được đóng khi bean bị hủy. Trước khi tạo bean như ví dụ, hãy kiểm tra ứng dụng đã có registry phù hợp từ auto-configuration hay chưa. Tạo thêm registry không cần thiết có thể làm meter được ghi vào registry này nhưng hệ thống giám sát lại đọc registry khác.

Không nên gọi close trên registry được inject trong một component có vòng đời ngắn như controller, service nghiệp vụ hoặc request handler. Cũng không nên tạo registry mới cho từng request. Registry thường là tài nguyên dùng chung ở cấp ứng dụng và cần sống lâu hơn các request riêng lẻ.

## 4. Đóng registry trong Java độc lập

Khi không có Spring hoặc container quản lý lifecycle, mã tạo registry phải xác định rõ phạm vi sử dụng và đóng registry khi ra khỏi phạm vi đó. Nếu MeterRegistry được dùng trong một khối công việc hữu hạn, có thể sử dụng try-with-resources:

~~~java
public class MetricsExample {

    public static void main(String[] args) {
        try (MeterRegistry registry = new SimpleMeterRegistry()) {
            Counter counter = registry.counter("batch.jobs.completed");

            runBatch(counter);
        }
    }

    private static void runBatch(Counter counter) {
        // Xử lý batch và cập nhật metrics.
        counter.increment();
    }
}
~~~

Khi khối try kết thúc, registry được đóng kể cả khi xử lý phát sinh exception. Cách này phù hợp với tác vụ hữu hạn, công cụ dòng lệnh hoặc chương trình chạy một lần.

Với ứng dụng chạy lâu dài, hãy đặt registry ở phạm vi ứng dụng và đóng nó trong quy trình shutdown của ứng dụng. Tránh tạo một registry ở mỗi lần gọi hàm rồi để registry mất tham chiếu mà không có bước đóng rõ ràng. Việc chỉ mất tham chiếu không thay thế cho quản lý tài nguyên có thể giữ thread hoặc kết nối.

## 5. Dừng scheduler và executor do ứng dụng sở hữu

Một số registry kiểu push/step có scheduler nội bộ và tự quản lý scheduler đó trong lifecycle của registry. Khi sử dụng registry có sẵn, hãy để implementation thực hiện việc dừng tài nguyên của nó thông qua cơ chế đóng registry được hỗ trợ.

Ứng dụng cũng có thể tạo scheduler riêng để tính toán hoặc xuất số liệu tùy chỉnh. Tài nguyên này cần có lifecycle riêng. Ví dụ dưới đây thể hiện một bean tự quản lý ScheduledExecutorService:

~~~java
public final class MetricsBackgroundTask implements AutoCloseable {

    private final MeterRegistry registry;
    private final ScheduledExecutorService executor =
            Executors.newSingleThreadScheduledExecutor();

    public MetricsBackgroundTask(MeterRegistry registry) {
        this.registry = registry;
        executor.scheduleAtFixedRate(
                this::collect,
                0,
                30,
                TimeUnit.SECONDS
        );
    }

    private void collect() {
        registry.counter("metrics.background.collections").increment();
    }

    @Override
    public void close() {
        executor.shutdown();

        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException exception) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Có thể đăng ký đối tượng này như một bean Spring:

~~~java
@Configuration
public class BackgroundMetricsConfiguration {

    @Bean(destroyMethod = "close")
    MetricsBackgroundTask metricsBackgroundTask(MeterRegistry registry) {
        return new MetricsBackgroundTask(registry);
    }
}
~~~

Khi context dừng, Spring gọi close trên bean. Executor ngừng nhận lịch chạy mới và có một khoảng thời gian giới hạn để hoàn tất tác vụ đang chạy. Nếu hết thời gian, shutdownNow yêu cầu dừng các tác vụ còn lại. Việc khôi phục interrupt flag giúp giữ tín hiệu ngắt cho thread đang thực hiện quá trình đóng.

Không tạo một executor chỉ để thay thế scheduler đã được registry quản lý. Trước khi tự viết lịch xuất dữ liệu, hãy xác định registry có sẵn đã cung cấp cơ chế publish hay chưa. Mỗi scheduler bổ sung đều làm tăng số thread và thêm một lifecycle cần kiểm soát.

## 6. Thứ tự shutdown an toàn

Thứ tự dừng ảnh hưởng đến khả năng ghi nhận số liệu của các hoạt động cuối cùng. Nếu đóng registry khi request hoặc worker vẫn đang ghi meter, dữ liệu cuối có thể thiếu hoặc việc ghi có thể thất bại tùy implementation.

Một quy trình shutdown hợp lý gồm các bước:

1. **Ngừng nhận công việc mới**: dừng nhận request, message hoặc lịch chạy mới theo cơ chế của ứng dụng.
2. **Chờ công việc đang xử lý**: cho request và worker đang chạy hoàn tất trong thời gian graceful shutdown đã cấu hình.
3. **Dừng producer và scheduler tùy chỉnh**: không để tác vụ nền mới tiếp tục phát sinh số đo khi ứng dụng đã bước vào giai đoạn kết thúc.
4. **Hoàn tất việc xuất dữ liệu nếu cần**: gọi flush hoặc publish cuối chỉ khi registry/backend có hỗ trợ và ứng dụng có yêu cầu rõ ràng.
5. **Đóng registry và tài nguyên phụ trợ**: đóng những registry do ứng dụng sở hữu, sau đó đóng client hoặc tài nguyên riêng theo đúng quan hệ phụ thuộc.
6. **Kết thúc tiến trình**: xác nhận các thread nền đã dừng và không còn tác vụ giữ tiến trình sống ngoài dự kiến.

Trong Spring Boot, nhiều bước được điều phối bởi lifecycle của ApplicationContext, web server và các bean. Cần cấu hình graceful shutdown phù hợp với thời gian xử lý thực tế. Nếu một worker cần ghi vào MeterRegistry, hãy inject registry qua constructor để Spring nhận biết quan hệ phụ thuộc; bean worker sẽ được hủy trước registry mà nó sử dụng. Với ứng dụng tự quản lý thread hoặc exporter, cần khai báo lifecycle cho chúng và xác định thứ tự dừng sao cho worker không còn ghi metrics sau khi registry đã đóng.

Không nên dựa hoàn toàn vào một JVM shutdown hook tự viết trong ứng dụng Spring Boot. Shutdown hook có thể chạy ở thời điểm khó kiểm soát so với lifecycle của context và các bean phụ thuộc. Hãy dùng lifecycle của framework khi framework đang sở hữu ứng dụng. Với chương trình Java độc lập không có container, try-with-resources hoặc một điểm shutdown tập trung có thể quản lý các tài nguyên một cách rõ ràng.

## 7. Registry tổng hợp và nhiều backend

CompositeMeterRegistry cho phép một nhóm meter được chuyển đến nhiều registry con. Mô hình này hữu ích khi một ứng dụng cần xuất cùng số liệu đến nhiều hệ thống hoặc thay đổi registry đích theo cấu hình.

Khi dùng nhiều registry, cần lập danh sách những registry được tạo và chủ sở hữu của từng registry. Registry tổng hợp là điểm kết nối các meter; việc thêm một registry con vào composite không nên được xem là thay thế cho hợp đồng sở hữu tài nguyên của registry con. Nếu ứng dụng tự tạo registry con có scheduler, client hoặc kết nối riêng, hãy xác định rõ bean hoặc thành phần nào chịu trách nhiệm đóng nó. Tránh để nhiều component cùng gọi close trên một registry dùng chung.

Ví dụ cấu trúc khái niệm:

~~~java
CompositeMeterRegistry composite = new CompositeMeterRegistry();
MeterRegistry primary = createPrimaryRegistry();
MeterRegistry secondary = createSecondaryRegistry();

composite.add(primary);
composite.add(secondary);
~~~

Trong ví dụ này, ứng dụng tạo cả ba registry. Vì vậy, thiết kế lifecycle cần chỉ định rõ nơi đóng composite và từng registry con theo contract của implementation đang sử dụng. Nếu các registry được khai báo thành bean, hãy để container quản lý việc hủy bean theo dependency và cấu hình lifecycle. Không đóng registry con từ component nghiệp vụ chỉ vì component đó đang ghi meter vào composite.

## 8. Gauge và vòng đời đối tượng được quan sát

Gauge thường quan sát giá trị hiện tại của một đối tượng thay vì lưu một bộ đếm tích lũy. Nhiều cách triển khai Gauge sử dụng tham chiếu yếu đến đối tượng được quan sát. Vì vậy, ứng dụng cần giữ tham chiếu mạnh đến đối tượng trong suốt thời gian muốn theo dõi nó.

~~~java
@Component
public class QueueMetrics {

    private final Queue<Job> pendingJobs = new ConcurrentLinkedQueue<>();

    public QueueMetrics(MeterRegistry registry) {
        Gauge.builder(
                "jobs.pending",
                pendingJobs,
                Queue::size
        ).register(registry);
    }

    public void enqueue(Job job) {
        pendingJobs.add(job);
    }
}
~~~

Trong ví dụ, QueueMetrics giữ tham chiếu đến pendingJobs trong suốt vòng đời component. Nếu tạo queue ở một biến cục bộ, đăng ký Gauge rồi không giữ tham chiếu, đối tượng có thể bị garbage collector thu hồi và Gauge không còn phản ánh giá trị mong đợi.

Khi một đối tượng nghiệp vụ có vòng đời ngắn kết thúc, hãy cân nhắc việc loại bỏ meter động tương ứng nếu meter không còn ý nghĩa. Việc đăng ký một meter mới cho từng đối tượng rồi giữ tất cả meter mãi trong registry có thể làm số lượng meter tăng không giới hạn. Với meter gắn với toàn bộ ứng dụng như số request, số lỗi hoặc kích thước queue dùng chung, vòng đời thường gắn với registry và bean sở hữu đối tượng.

## 9. Những lỗi lifecycle thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Không đóng registry do ứng dụng tự tạo | Có thể còn scheduler, thread hoặc tài nguyên xuất dữ liệu | Gắn registry vào lifecycle bean hoặc dùng try-with-resources |
| Đóng registry được inject từ component nghiệp vụ | Component khác mất khả năng ghi metrics | Chỉ chủ sở hữu registry mới đóng registry |
| Đóng registry trước khi worker kết thúc | Số đo của công việc cuối có thể bị thiếu | Dừng nhận việc, chờ worker rồi mới đóng registry |
| Tạo registry hoặc executor trong mỗi request | Tăng số thread và tài nguyên, khó kiểm soát | Dùng tài nguyên dùng chung ở phạm vi ứng dụng |
| Giả định close luôn gửi lần publish cuối | Dữ liệu cuối có thể chưa đến backend | Kiểm tra contract và dùng flush được hỗ trợ nếu cần |
| Đóng lặp cùng một tài nguyên từ nhiều bean | Có thể phát sinh lỗi hoặc hành vi phụ thuộc implementation | Thiết kế một chủ sở hữu duy nhất |
| Gauge tham chiếu đến đối tượng không còn được giữ | Giá trị đo có thể không còn hợp lệ | Giữ đối tượng sống theo vòng đời meter |
| Tạo meter động nhưng không loại bỏ | Số lượng meter tăng theo thời gian | Xác định vòng đời meter và gỡ meter khi phù hợp |

Một vấn đề khác là thời gian shutdown. Nếu chờ vô hạn một executor hoặc exporter bị treo, tiến trình có thể không thoát. Nếu dừng ngay lập tức, tác vụ đang xử lý có thể bị cắt giữa chừng. Hãy đặt thời gian chờ hữu hạn, ghi log khi buộc phải hủy tác vụ và chọn giới hạn dựa trên thời gian xử lý thực tế của hệ thống.

## 10. Kiểm thử quá trình đóng tài nguyên

Kiểm thử lifecycle cần xác nhận cả registry lẫn tài nguyên phụ trợ được dừng. Không chỉ kiểm tra rằng ứng dụng khởi động và ghi được meter.

Các tình huống nên được kiểm tra gồm:

- Registry tự tạo được đóng khi khối try kết thúc hoặc khi Spring ApplicationContext bị đóng.
- Component sử dụng registry không tự đóng registry dùng chung.
- Scheduler không tiếp tục chạy sau khi bean quản lý scheduler bị hủy.
- Tác vụ đang chạy được chờ trong thời gian giới hạn; trường hợp timeout kích hoạt nhánh dừng cưỡng bức.
- Lỗi trong tác vụ nền không làm quá trình đóng bị bỏ qua.
- Với registry push/step, xác minh scheduler ngừng hoạt động và kiểm tra riêng hành vi publish cuối nếu backend yêu cầu.
- Với Gauge, đối tượng được quan sát tồn tại trong đúng khoảng thời gian và meter động được loại bỏ khi vòng đời nghiệp vụ kết thúc.

Có thể dùng một MeterRegistry đơn giản trong bộ nhớ để kiểm tra mã ghi meter, còn kiểm thử đóng scheduler hoặc exporter cần quan sát chính tài nguyên tương ứng. Với Spring Boot, đóng ApplicationContext trong bài kiểm thử là cách kiểm tra các callback hủy bean. Tránh chỉ kiểm tra bằng cách chờ một khoảng thời gian cố định; nên kiểm tra trạng thái executor hoặc dùng tín hiệu đồng bộ để xác nhận tác vụ đã dừng.

## 11. Checklist triển khai

Trước khi đưa instrumentation vào môi trường chạy thật, hãy xác nhận:

- [ ] Mỗi MeterRegistry có một chủ sở hữu lifecycle được xác định.
- [ ] Registry được tạo bởi Spring Boot được quản lý trong ApplicationContext.
- [ ] Registry tự tạo được đóng qua bean lifecycle hoặc try-with-resources.
- [ ] Component nghiệp vụ chỉ sử dụng registry được inject và không tự đóng registry dùng chung.
- [ ] Scheduler, executor, client và server do ứng dụng tự tạo có bước dừng riêng.
- [ ] Ứng dụng ngừng nhận công việc mới và chờ công việc đang chạy trước khi đóng registry.
- [ ] Nhu cầu flush cuối đã được xác minh theo registry/backend cụ thể.
- [ ] Gauge giữ được đối tượng cần quan sát trong suốt vòng đời cần đo.
- [ ] Meter động có quy tắc loại bỏ để tránh tăng không giới hạn.
- [ ] Kiểm thử xác nhận tài nguyên nền thực sự dừng sau shutdown.

Quản lý vòng đời là một phần của instrumentation có chất lượng. Registry cần sống đủ lâu để ghi nhận hoạt động của ứng dụng, nhưng phải được đóng đúng lúc để giải phóng tài nguyên. Khi xác định rõ quyền sở hữu, gắn tài nguyên vào lifecycle của Spring hoặc phạm vi try-with-resources, và dừng worker trước registry, ứng dụng có thể kết thúc gọn gàng mà vẫn giữ được độ tin cậy của số liệu vận hành.

