# MeterBinder đóng gói việc gắn phép đo cho một thành phần

Một thành phần Java thường sở hữu trạng thái mà ứng dụng muốn quan sát: hàng đợi có bao nhiêu phần tử, bộ nhớ đệm đang giữ bao nhiêu mục, executor có bao nhiêu worker đang bận hoặc một client đã thực hiện bao nhiêu thao tác. Nếu mỗi nơi sử dụng tự đăng ký meter, logic instrumentation dễ bị phân tán và khó tái sử dụng.

**MeterBinder** cho phép đóng gói việc đăng ký một nhóm meter thành một thành phần riêng. Binder nhận **MeterRegistry** qua phương thức **bindTo(registry)** rồi gắn các meter phản ánh trạng thái hoặc hoạt động của đối tượng mà nó theo dõi. Nhờ đó, mã nghiệp vụ có thể tập trung vào cập nhật trạng thái; binder chịu trách nhiệm mô tả trạng thái ấy bằng metrics.

MeterBinder đặc biệt hữu ích khi phép đo phụ thuộc vào bean hoặc tài nguyên khác. Trong Spring Boot, các bean triển khai MeterBinder được tự động bind vào registry do Spring quản lý. Ở ứng dụng Java độc lập, có thể gọi bindTo trực tiếp cho registry đang sử dụng.

## 1. MeterBinder giải quyết vấn đề gì?

Không dùng binder, component có thể tự đăng ký meter trong constructor hoặc một phương thức khởi tạo:

~~~java
public final class JobQueue {
    private final Queue<Job> queue;

    public JobQueue(MeterRegistry registry) {
        this.queue = new ConcurrentLinkedQueue<>();

        Gauge.builder("jobs.queue.size", queue, Queue::size)
            .description("Số job hiện có trong hàng đợi")
            .register(registry);
    }
}
~~~

Cách này hoạt động, nhưng JobQueue phải biết về MeterRegistry và API của Micrometer. Khi muốn kiểm thử logic hàng đợi độc lập hoặc tái sử dụng cùng component ở một môi trường không bật metrics, dependency instrumentation trở thành một phần của mã nghiệp vụ.

Có thể tách việc đăng ký meter sang binder:

~~~java
public final class JobQueueMetrics implements MeterBinder {

    private final Queue<Job> queue;

    public JobQueueMetrics(Queue<Job> queue) {
        this.queue = queue;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder("jobs.queue.size", queue, Queue::size)
            .description("Số job hiện có trong hàng đợi")
            .register(registry);
    }
}
~~~

JobQueueMetrics chỉ cần tham chiếu đến queue và biết cách công bố kích thước của nó. Registry được truyền vào khi bind. Component nghiệp vụ không cần tự đăng ký meter.

Tách biệt này có một số lợi ích:

- Gom các meter liên quan đến cùng một thành phần vào một nơi.
- Giữ mã nghiệp vụ ít phụ thuộc vào API instrumentation.
- Dễ tái sử dụng bộ phép đo trong nhiều ứng dụng hoặc nhiều registry.
- Làm rõ đối tượng nào cung cấp dữ liệu cho Gauge, FunctionCounter hoặc các meter khác.
- Kiểm thử phần đăng ký metrics độc lập với xử lý nghiệp vụ.

## 2. Contract của MeterBinder

MeterBinder là interface trong package **io.micrometer.core.instrument.binder**. Contract chính của nó là phương thức:

~~~java
void bindTo(MeterRegistry registry);
~~~

Khi bind được gọi, binder đăng ký các meter cần thiết vào registry được truyền vào. Binder không tạo registry mới và không quyết định backend nào sẽ nhận dữ liệu. Registry chịu trách nhiệm giữ meter và chuyển dữ liệu theo implementation tương ứng.

Một binder thường thực hiện các bước sau:

1. Nhận các đối tượng hoặc nguồn trạng thái cần đo qua constructor.
2. Trong bindTo, tạo meter với tên, description, tag và loại phù hợp.
3. Dùng các nguồn trạng thái đó làm đối tượng được Gauge hoặc FunctionCounter quan sát.
4. Để mã thành phần cập nhật trạng thái hoặc bộ đếm tích lũy trong quá trình hoạt động.
5. Đảm bảo việc bind vào registry không tạo ra các meter có tên hoặc tag xung đột.

Binder nên giữ cấu hình và tham chiếu đến đối tượng cần đo. Tránh giữ một trường Meter duy nhất được đăng ký trong lần bind đầu tiên nếu cùng binder có thể được bind vào nhiều registry. Mỗi registry cần có meter riêng của nó; hãy tạo hoặc tra cứu meter trong bindTo(registry).

## 3. Ví dụ đầy đủ: đo hàng đợi và số job đã tiếp nhận

Giả sử một dịch vụ dùng queue để giữ job chờ xử lý. Ta muốn quan sát hai đại lượng:

- Số job hiện đang nằm trong queue: giá trị có thể tăng và giảm, nên dùng Gauge.
- Tổng số job đã được tiếp nhận: giá trị tích lũy, chỉ tăng, nên dùng FunctionCounter.

Binder nhận queue và một AtomicLong lưu tổng số job đã tiếp nhận:

~~~java
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;

import java.util.Queue;
import java.util.concurrent.atomic.AtomicLong;

public final class JobQueueMeterBinder implements MeterBinder {

    private final Queue<Job> queue;
    private final AtomicLong acceptedJobs;

    public JobQueueMeterBinder(
            Queue<Job> queue,
            AtomicLong acceptedJobs) {
        this.queue = queue;
        this.acceptedJobs = acceptedJobs;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder("jobs.queue.size", queue, Queue::size)
            .description("Số job đang chờ xử lý")
            .register(registry);

        FunctionCounter.builder(
                "jobs.accepted",
                acceptedJobs,
                AtomicLong::get
            )
            .description("Tổng số job đã được tiếp nhận")
            .register(registry);
    }
}
~~~

Gauge đọc kích thước queue tại thời điểm registry lấy giá trị. Khi worker lấy job khỏi queue, giá trị Gauge giảm. FunctionCounter quan sát AtomicLong và công bố giá trị tích lũy; mã nghiệp vụ tăng AtomicLong khi tiếp nhận job.

Ví dụ cập nhật trạng thái:

~~~java
public void submit(Job job) {
    queue.add(job);
    acceptedJobs.incrementAndGet();
}
~~~

Không gọi increment cho FunctionCounter trực tiếp. FunctionCounter đọc một hàm cung cấp giá trị đơn điệu từ đối tượng nguồn. Vì vậy, nguồn phải giữ giá trị tăng dần trong vòng đời tiến trình. Nếu cần một bộ đếm mà mã gọi increment trực tiếp, hãy đăng ký Counter thay cho FunctionCounter.

Đối với queue đồng thời, cần chọn implementation và phép đọc kích thước phù hợp. Một số queue có size() tốn chi phí tuyến tính theo số phần tử hoặc chỉ cung cấp ước lượng trong lúc cập nhật đồng thời. Gauge được đọc khi scrape; không nên đặt một phép tính đắt tiền hoặc có tác dụng phụ trong hàm lấy giá trị.

## 4. Đăng ký MeterBinder thủ công

Trong ứng dụng Java không dùng Spring, tạo binder rồi bind vào registry:

~~~java
MeterRegistry registry = new SimpleMeterRegistry();

Queue<Job> queue = new ConcurrentLinkedQueue<>();
AtomicLong acceptedJobs = new AtomicLong();

JobQueueMeterBinder binder =
    new JobQueueMeterBinder(queue, acceptedJobs);

binder.bindTo(registry);
~~~

Sau khi bind, component có thể cập nhật queue và acceptedJobs. Registry đọc trạng thái hiện tại khi lấy các meter tương ứng.

Nếu ứng dụng xuất metrics đến nhiều backend, có thể bind cùng một binder vào từng registry:

~~~java
binder.bindTo(prometheusRegistry);
binder.bindTo(statsdRegistry);
~~~

Mỗi registry giữ meter của riêng nó, nhưng cùng quan sát nguồn trạng thái của thành phần. Cách này hữu ích khi một ứng dụng có nhiều registry độc lập. Nếu ứng dụng đã dùng CompositeMeterRegistry, có thể bind vào composite theo kiến trúc registry của ứng dụng để các registry con nhận meter theo cơ chế composite.

Với composite, hãy hoàn tất việc thêm registry con và cấu hình filter trước khi bind meter. Meter được tạo trước khi một registry con được thêm vào composite có thể không chuyển tiếp các lần ghi đã xảy ra trước thời điểm thêm registry đó.

Không gọi bindTo lặp lại tùy tiện cho cùng một registry. Hãy chọn một điểm khởi tạo rõ ràng và bind mỗi binder một lần cho mỗi registry. Đăng ký trùng có thể tạo cảnh báo hoặc hành vi khó hiểu nếu meter ID không giống nhau, hoặc nếu binder tham chiếu đến những nguồn dữ liệu khác nhau.

## 5. Tích hợp MeterBinder với Spring Boot

Spring Boot tự động bind các bean triển khai MeterBinder vào MeterRegistry do Spring quản lý. Vì vậy, khi dùng Spring Boot, thông thường chỉ cần khai báo binder như một bean.

~~~java
@Configuration(proxyBeanMethods = false)
public class JobMetricsConfiguration {

    @Bean
    MeterBinder jobQueueMetrics(
            Queue<Job> jobQueue,
            AtomicLong acceptedJobs) {
        return new JobQueueMeterBinder(jobQueue, acceptedJobs);
    }
}
~~~

Khi ApplicationContext khởi tạo và registry được cấu hình, Spring Boot sẽ bind MeterBinder bean. Binder nhận đúng các dependency đã được Spring quản lý. Điều này bảo đảm queue và bộ đếm trạng thái đã được cung cấp trước khi Gauge hoặc FunctionCounter đọc dữ liệu.

Nếu binder là một component độc lập, cũng có thể đánh dấu class bằng **@Component** và inject dependency qua constructor. Dùng một cách đăng ký phù hợp với kiến trúc ứng dụng; tránh vừa khai báo bean vừa tự gọi bindTo thủ công cho cùng registry.

Một cấu hình common tags có thể được áp dụng trước khi meter được đăng ký:

~~~java
@Bean
MeterRegistryCustomizer<MeterRegistry> metricsCommonTags() {
    return registry -> registry.config()
        .commonTags("service", "job-worker", "environment", "production");
}
~~~

MeterRegistryCustomizer dùng để cấu hình registry, ví dụ common tags hoặc NamingConvention. MeterBinder đăng ký các meter cụ thể của thành phần. Hai cơ chế có trách nhiệm khác nhau và có thể cùng xuất hiện trong ứng dụng.

## 6. Quan hệ dependency và thời điểm đọc Gauge

Một lợi ích quan trọng của MeterBinder trong Spring Boot là mô tả được quan hệ dependency giữa metric và bean cung cấp giá trị. Ví dụ, binder nhận Queue bean qua tham số phương thức @Bean, rồi Gauge đọc queue đó trong các lần scrape.

Gauge thường giữ tham chiếu yếu đến đối tượng được quan sát. Nếu đối tượng chỉ tồn tại trong một biến cục bộ và không còn tham chiếu mạnh nào khác, garbage collector có thể thu hồi nó. Khi đó Gauge có thể không còn trả về giá trị mong đợi.

Vì vậy:

- Bean hoặc thành phần sở hữu trạng thái cần giữ đối tượng sống trong suốt thời gian meter được sử dụng.
- Binder nên giữ tham chiếu đến đối tượng mà Gauge quan sát nếu binder là chủ sở hữu hợp lý của liên kết đó.
- Với cách bind thủ công, giữ binder hoặc đối tượng nguồn trong một phạm vi sống đủ lâu; gọi bindTo xong rồi để mọi tham chiếu đến nguồn biến mất có thể làm Gauge mất đối tượng được quan sát.
- Không tạo một bản sao số tại thời điểm bind nếu mục tiêu là quan sát giá trị thay đổi theo thời gian.
- Dùng một nguồn dữ liệu có phép đọc an toàn khi nhiều thread cập nhật đồng thời.

Ví dụ sau đăng ký Gauge từ giá trị hiện tại tại thời điểm khởi tạo:

~~~java
registry.gauge("jobs.queue.size", queue.size());
~~~

Đây là overload nhận một giá trị số, không phải một nguồn trạng thái sống. Nếu queue thay đổi sau đó, số đã truyền vào không tự thay đổi. Muốn quan sát trạng thái hiện tại, truyền đối tượng cùng hàm đọc:

~~~java
Gauge.builder("jobs.queue.size", queue, Queue::size)
    .register(registry);
~~~

## 7. Chọn loại meter phù hợp với dữ liệu của thành phần

MeterBinder không giới hạn loại meter. Binder có thể đăng ký một nhóm meter phản ánh nhiều khía cạnh của cùng một component.

| Dữ liệu của thành phần | Meter phù hợp | Ví dụ |
|---|---|---|
| Kích thước queue hiện tại | Gauge | jobs.queue.size |
| Tổng số job đã tiếp nhận | FunctionCounter hoặc Counter | jobs.accepted |
| Thời gian xử lý từng job | Timer | jobs.execution |
| Số job đang chạy lâu | LongTaskTimer | jobs.active |
| Kích thước payload đã xử lý | DistributionSummary | jobs.payload.size |

Nếu binder đo một executor, có thể đăng ký Gauge cho số thread đang hoạt động, số tác vụ chờ và kích thước pool; FunctionCounter cho số tác vụ hoàn tất; Timer cho thời gian thực thi hoặc thời gian chờ. Các binder có sẵn của Micrometer như ExecutorServiceMetrics đã thực hiện phần lớn công việc này cho những loại ExecutorService được hỗ trợ.

Không nên tạo meter chỉ vì nguồn dữ liệu có sẵn. Mỗi meter cần có câu hỏi vận hành cụ thể và đơn vị rõ ràng. Đối với một trạng thái có thể tăng và giảm, dùng Gauge; đối với sự kiện tích lũy, dùng Counter hoặc FunctionCounter; đối với thời lượng, dùng Timer hoặc LongTaskTimer tùy câu hỏi cần trả lời.

## 8. MeterBinder có thể đóng gói nhiều meter

Một binder có thể đăng ký cả nhóm meter liên quan đến cùng một thành phần. Ví dụ, một binder cho cache có thể công bố:

- Số entry hiện tại bằng Gauge.
- Số lần hit và miss tích lũy bằng FunctionCounter.
- Tổng dung lượng hoặc kích thước cache bằng Gauge.
- Thời lượng thao tác load bằng Timer nếu nguồn dữ liệu có thể cung cấp sự kiện đó.

Giữ các meter trong cùng binder khi chúng cùng phụ thuộc một đối tượng và cùng một vòng đời. Nếu một binder trở nên quá lớn, phụ thuộc nhiều thành phần không liên quan hoặc khó kiểm thử, hãy tách thành nhiều binder nhỏ theo ranh giới component.

Một binder không nên trở thành nơi chứa toàn bộ metrics của ứng dụng. Mục tiêu của nó là đóng gói một bộ phép đo có quan hệ rõ ràng với một thành phần hoặc một nhóm tài nguyên.

## 9. Idempotency, nhiều registry và tránh đăng ký trùng

Trong Spring Boot, một MeterBinder bean thường được bind tự động. Trong ứng dụng có nhiều registry, cùng binder có thể được bind cho từng registry. Vì vậy, thiết kế binder cần tính đến các trường hợp sau:

- **Một binder, một registry**: đăng ký meter của thành phần vào registry.
- **Một binder, nhiều registry**: mỗi registry nhận meter riêng, cùng quan sát nguồn dữ liệu.
- **Một binder bị bind lặp vào cùng registry**: tránh gọi lặp do khởi tạo thủ công hoặc cấu hình bean trùng.
- **Nhiều binder cùng đăng ký một meter ID**: cần thống nhất một chủ sở hữu cho meter để tránh cấu hình hoặc nguồn dữ liệu xung đột.

Dùng tên meter và tập tag ổn định. Đừng thêm một tag riêng cho mỗi lần bind để né trùng, vì điều đó làm tăng cardinality và tạo dữ liệu không thể tổng hợp đúng nghĩa.

Không giữ một Counter, Timer hoặc Gauge duy nhất trong field của binder rồi tái sử dụng cho mọi registry. Meter gắn với registry nơi nó được đăng ký. Hãy gọi builder với registry hiện tại trong bindTo; nếu cần cập nhật trực tiếp meter theo sự kiện, thiết kế component sử dụng registry phù hợp hoặc duy trì trạng thái nguồn rồi để các meter của từng registry quan sát trạng thái đó.

## 10. Cardinality và quy ước tag

Binder thường gắn meter với một thành phần cụ thể, nhưng điều đó không có nghĩa mọi thuộc tính của thành phần đều thích hợp làm tag.

Ví dụ tag có tập giá trị hữu hạn:

- queue=priority, queue=standard, queue=bulk.
- result=success, result=failure, result=rejected.
- region=ap-southeast, region=eu-west.

Ví dụ tag cần tránh:

- Job ID riêng của từng lần chạy.
- User ID hoặc request ID.
- Tên file tùy ý hoặc URL chứa ID.
- Nội dung exception hoặc thông điệp lỗi đầy đủ.

Mỗi tổ hợp tag có thể tạo ra một meter ID và một hoặc nhiều chuỗi thời gian. Nếu binder theo dõi hàng nghìn queue có ID riêng rồi thêm ID vào tag, số chuỗi có thể tăng theo số tài nguyên. Hãy cân nhắc nhóm tài nguyên theo loại hoặc mức ưu tiên và dùng log/trace để điều tra từng lần chạy cụ thể.

Cũng cần giữ cùng tập khóa tag cho các meter cùng tên. Nếu một nhánh đăng ký tag result, nhánh khác thêm exception hoặc bỏ result, schema có thể không tương thích với backend và làm truy vấn khó duy trì.

## 11. Phân biệt MeterBinder, MeterRegistryCustomizer và MeterFilter

Ba cơ chế thường xuất hiện cùng nhau trong ứng dụng Spring Boot nhưng giải quyết các vấn đề khác nhau:

| Cơ chế | Trách nhiệm | Ví dụ |
|---|---|---|
| MeterBinder | Đăng ký các meter cho một thành phần | Queue binder đăng ký Gauge kích thước queue |
| MeterRegistryCustomizer | Cấu hình registry trước khi meter được đăng ký | Thêm common tags, cấu hình NamingConvention |
| MeterFilter | Điều chỉnh hoặc giới hạn meter ID khi đăng ký | Từ chối meter không mong muốn hoặc chuẩn hóa tag |

MeterBinder không thay thế MeterFilter. Nếu cần chặn tag có cardinality cao hoặc giới hạn số meter, hãy đặt quy tắc ở API instrumentation và/hoặc MeterFilter. Nếu cần thêm service, region hoặc environment cho toàn registry, dùng common tags qua customizer.

Đặt cấu hình registry trước khi binder đăng ký meter để các meter nhận được quy ước chung. Trong Spring Boot, customizer được áp dụng trong quá trình cấu hình registry trước khi các meter được đăng ký.

## 12. Các binder có sẵn trong Micrometer

Micrometer cung cấp nhiều binder để quan sát JVM, hệ điều hành và tài nguyên thư viện. Không cần tự viết binder nếu thư viện đã có binder phù hợp.

Một số ví dụ thường dùng:

| Binder | Dữ liệu điển hình |
|---|---|
| ClassLoaderMetrics | Số class đã tải, đang được tải hoặc đã unload |
| JvmMemoryMetrics | Mức sử dụng heap, non-heap và memory pool |
| JvmGcMetrics | Thông tin garbage collection và thời gian pause |
| JvmThreadMetrics | Số thread đang sống, daemon và peak |
| ProcessorMetrics | Mức sử dụng CPU hệ thống và process |
| ExecutorServiceMetrics | Thread pool, tác vụ active/queued/completed và thời lượng xử lý |
| DiskSpaceMetrics | Dung lượng đĩa còn trống và tổng dung lượng |
| FileDescriptorMetrics | File descriptor đang mở và giới hạn |

Ví dụ bind các JVM meter vào registry:

~~~java
new ClassLoaderMetrics().bindTo(registry);
new JvmMemoryMetrics().bindTo(registry);
new JvmGcMetrics().bindTo(registry);
new ProcessorMetrics().bindTo(registry);
new JvmThreadMetrics().bindTo(registry);
~~~

Với ExecutorService:

~~~java
new ExecutorServiceMetrics(
    executorService,
    "background-worker",
    Tags.of("pool", "reporting")
).bindTo(registry);
~~~

Danh sách meter và điều kiện hỗ trợ có thể khác theo phiên bản Micrometer, loại executor và phiên bản Java. Một số binder quản lý listener hoặc tài nguyên phụ trợ và có thể triển khai AutoCloseable; khi dùng ngoài container có lifecycle, cần đóng chúng theo tài liệu của binder cụ thể. Không giả định mọi MeterBinder đều cần close hoặc mọi binder đều chỉ đăng ký meter thuần túy.

## 13. Kiểm thử MeterBinder

Có thể dùng SimpleMeterRegistry để xác minh binder đăng ký đúng meter và các meter đọc được trạng thái hiện tại.

~~~java
@Test
void bindsQueueSizeAndAcceptedJobCount() {
    try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
        Queue<Job> queue = new ConcurrentLinkedQueue<>();
        AtomicLong acceptedJobs = new AtomicLong();

        JobQueueMeterBinder binder =
            new JobQueueMeterBinder(queue, acceptedJobs);

        binder.bindTo(registry);

        queue.add(new Job());
        queue.add(new Job());
        acceptedJobs.set(2);

        assertEquals(
            2.0,
            registry.get("jobs.queue.size").gauge().value()
        );

        assertEquals(
            2.0,
            registry.get("jobs.accepted").functionCounter().count()
        );
    }
}
~~~

Bài kiểm thử xác nhận Gauge đọc queue sau khi queue thay đổi và FunctionCounter đọc giá trị tích lũy từ AtomicLong. Điều này kiểm tra rằng binder đăng ký nguồn trạng thái sống thay vì chỉ ghi một snapshot tại thời điểm khởi tạo.

Nên kiểm tra thêm:

- Meter name, loại meter, description và tag đúng theo quy ước.
- Gauge phản ánh thay đổi của đối tượng nguồn.
- FunctionCounter chỉ quan sát giá trị đơn điệu tăng.
- Binder hoạt động với từng registry mà ứng dụng hỗ trợ.
- Không có hai binder đăng ký cùng meter ID với nguồn dữ liệu hoặc cấu hình xung đột.
- ApplicationContext đóng và khởi tạo đúng các bean dependency.
- Tài nguyên phụ trợ của binder được dọn dẹp nếu binder cụ thể yêu cầu.

SimpleMeterRegistry đủ cho kiểm thử đăng ký và đọc meter trong bộ nhớ. Nếu cần xác minh tên metric sau NamingConvention, định dạng exporter hoặc hành vi backend, hãy bổ sung kiểm thử tích hợp với registry đích.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đăng ký meter trực tiếp trong nhiều component | Logic instrumentation phân tán và trùng lặp | Gom meter liên quan vào binder |
| Tự tạo MeterRegistry trong binder | Tách dữ liệu khỏi registry ứng dụng | Nhận registry qua bindTo |
| Giữ meter của registry thứ nhất trong field rồi dùng cho registry khác | Meter không được đăng ký ở registry đích | Tạo meter trong bindTo của từng registry |
| Bind cùng binder nhiều lần vào một registry | Đăng ký trùng hoặc cấu hình xung đột | Chọn một điểm bind rõ ràng |
| Gauge chỉ nhận giá trị snapshot | Không phản ánh thay đổi trạng thái | Truyền đối tượng cùng hàm đọc |
| Đối tượng Gauge bị garbage collector thu hồi | Gauge không còn dữ liệu đáng tin cậy | Giữ tham chiếu mạnh trong vòng đời cần đo |
| FunctionCounter quan sát giá trị có thể giảm | Vi phạm ngữ nghĩa bộ đếm tích lũy | Dùng Gauge hoặc Counter phù hợp |
| Dùng ID từng tài nguyên làm tag | Cardinality tăng mạnh | Dùng nhóm tag hữu hạn |
| Tự viết binder dù đã có binder chuẩn | Tăng mã bảo trì và nguy cơ khác quy ước | Kiểm tra binder có sẵn trước |

## 15. Checklist triển khai

- [ ] Xác định rõ thành phần hoặc tài nguyên mà binder chịu trách nhiệm đo.
- [ ] Inject đối tượng nguồn qua constructor hoặc dependency injection.
- [ ] Đăng ký meter trong bindTo(MeterRegistry).
- [ ] Không tạo registry mới bên trong binder.
- [ ] Không tái sử dụng meter gắn với một registry cho registry khác.
- [ ] Giữ đối tượng được Gauge quan sát sống trong suốt vòng đời meter.
- [ ] Dùng FunctionCounter chỉ với nguồn dữ liệu tích lũy, đơn điệu.
- [ ] Giữ tag có cardinality thấp và tập khóa ổn định.
- [ ] Trong Spring Boot, đăng ký binder thành bean để được tự động bind.
- [ ] Trong ứng dụng độc lập, bind rõ ràng một lần cho mỗi registry.
- [ ] Kiểm thử meter và nguồn dữ liệu bằng SimpleMeterRegistry.
- [ ] Kiểm tra lifecycle và tài nguyên phụ trợ của binder cụ thể nếu có.

MeterBinder tạo một ranh giới rõ ràng giữa thành phần cung cấp trạng thái và registry công bố metrics. Binder nhận đối tượng cần đo, đăng ký meter trong bindTo và để các meter đọc trạng thái hiện tại hoặc bộ đếm tích lũy của thành phần. Dùng binder khi một component có một nhóm phép đo liên quan, tận dụng tự động bind của Spring Boot hoặc gọi thủ công trong ứng dụng độc lập, đồng thời kiểm soát nguồn Gauge, tag và số lần bind để dữ liệu vận hành đáng tin cậy.

## Tài liệu tham khảo

- [Metrics — Spring Boot Reference](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [JVM Metrics — Micrometer Reference](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [Netty Instrumentation — Micrometer Reference](https://docs.micrometer.io/micrometer/reference/reference/netty.html)

