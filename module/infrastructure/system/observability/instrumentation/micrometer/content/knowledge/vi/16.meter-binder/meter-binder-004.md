# Đăng ký binder thủ công trong Java hoặc dưới dạng bean trong Spring

Micrometer dùng MeterRegistry để quản lý các meter và kết nối chúng với hệ thống thu thập metrics. Khi một thành phần như queue, connection pool hoặc thư viện nội bộ đã có trạng thái cần quan sát, MeterBinder cung cấp một điểm tích hợp để đăng ký các meter đó vào registry.

MeterBinder là một interface có phương thức bindTo(MeterRegistry registry). Lớp triển khai nhận registry được cung cấp, sau đó đăng ký Gauge, Counter, Timer hoặc meter phù hợp. Trong ứng dụng Java thuần, mã khởi tạo gọi bindTo() trực tiếp. Trong Spring Boot, có thể khai báo một bean kiểu MeterBinder; cơ chế metrics auto-configuration sẽ bind bean đó vào các registry được quản lý.

## 1. MeterBinder giải quyết việc gì?

Một binder đóng gói cách chuyển trạng thái của một thành phần thành metrics. Nó không phải một meter và cũng không phải registry. Vai trò của nó là đăng ký các meter cần thiết vào registry được truyền vào.

~~~mermaid
flowchart TD
    A["Thành phần ứng dụng<br/>Queue / Pool / Cache"] --> B["Nguồn trạng thái"]
    B --> C["MeterBinder.bindTo(registry)"]
    C --> D["Đăng ký Gauge / Counter / Timer..."]
    D --> E["MeterRegistry"]
    E --> F["Exporter hoặc endpoint scrape"]
    F --> G["Backend giám sát"]
~~~

Ví dụ, một queue có thể cung cấp:

- Độ sâu queue hiện tại bằng Gauge.
- Tổng số job hoàn tất bằng FunctionCounter nếu nguồn đếm đã được thành phần khác quản lý.
- Thời gian xử lý job bằng Timer nếu binder sở hữu điểm bắt đầu và kết thúc của thao tác.

Binder tập trung việc đặt tên, tags, đơn vị và cách đọc trạng thái. Thành phần nghiệp vụ vẫn chịu trách nhiệm cập nhật trạng thái thật; registry chịu trách nhiệm quản lý và xuất meter.

## 2. Hợp đồng của MeterBinder

Interface cốt lõi:

~~~java
package io.micrometer.core.instrument.binder;

import io.micrometer.core.instrument.MeterRegistry;

public interface MeterBinder {
    void bindTo(MeterRegistry registry);
}
~~~

bindTo() nhận registry đích và đăng ký các meter vào registry đó. Binder không nên tự tạo một MeterRegistry mới bên trong phương thức này, vì làm vậy sẽ tách metrics khỏi registry mà ứng dụng hoặc Spring Boot đang export.

Các nguyên tắc thiết kế:

- Dùng đúng registry được truyền vào.
- Đăng ký meter với tên, tags và đơn vị ổn định.
- Giữ tham chiếu đến nguồn trạng thái có vòng đời đủ dài.
- Không reset trạng thái nghiệp vụ trong bindTo().
- Không thực hiện truy vấn mạng hoặc I/O nặng khi bind.
- Không giả định chỉ có một registry trong toàn bộ ứng dụng.

bindTo() thường được gọi trong giai đoạn khởi tạo registry. Nó không phải nơi cập nhật số liệu cho mỗi request. Các thao tác nghiệp vụ tiếp tục cập nhật queue, counter hoặc trạng thái nguồn; meter đọc những giá trị đó khi được thu thập.

## 3. Ví dụ binder cho queue trong Java thuần

Giả sử ứng dụng có một queue và một bộ đếm tổng số job đã hoàn tất. Queue là nguồn cho Gauge; bộ đếm tích lũy là nguồn cho FunctionCounter.

~~~java
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.atomic.AtomicLong;

public final class JobQueueMeterBinder implements MeterBinder {

    private final BlockingQueue<Job> queue;
    private final AtomicLong completedJobs;

    public JobQueueMeterBinder(
        BlockingQueue<Job> queue,
        AtomicLong completedJobs
    ) {
        this.queue = queue;
        this.completedJobs = completedJobs;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder(
            "jobs.queue.depth",
            queue,
            BlockingQueue::size
        )
        .description("Số job hiện đang chờ trong queue")
        .tag("queue", "email")
        .register(registry);

        FunctionCounter.builder(
            "jobs.completed",
            completedJobs,
            AtomicLong::doubleValue
        )
        .description("Tổng số job đã hoàn tất")
        .tag("queue", "email")
        .register(registry);
    }
}
~~~

Job đại diện cho kiểu công việc của ứng dụng. completedJobs phải là giá trị tích lũy chỉ tăng; nếu nguồn đếm có thể giảm hoặc reset tùy ý, không nên diễn giải nó như FunctionCounter. Trong trường hợp đó, hãy chọn Gauge cho trạng thái hiện tại hoặc Counter để ghi nhận trực tiếp từng sự kiện hoàn tất.

Gauge đọc queue.size() tại thời điểm thu thập. FunctionCounter đọc giá trị tích lũy từ AtomicLong; nó không tăng số đếm khi scrape. Thành phần xử lý job phải tăng completedJobs sau khi một job thực sự hoàn tất.

### Khởi tạo và bind thủ công

Với Java thuần, ứng dụng tạo registry, tạo binder từ các đối tượng trạng thái đang được sử dụng và gọi bindTo():

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicLong;

public class MetricsBootstrap {

    public static void main(String[] args) {
        MeterRegistry registry = new SimpleMeterRegistry();
        BlockingQueue<Job> queue = new LinkedBlockingQueue<>();
        AtomicLong completedJobs = new AtomicLong();

        JobQueueMeterBinder binder =
            new JobQueueMeterBinder(queue, completedJobs);

        binder.bindTo(registry);

        // Các thành phần nghiệp vụ tiếp tục cập nhật queue và completedJobs.
        queue.add(new Job());
        completedJobs.incrementAndGet();

        // Khi kết thúc vòng đời của registry do ứng dụng sở hữu:
        registry.close();
    }
}
~~~

SimpleMeterRegistry phù hợp để minh họa hoặc kiểm thử trong bộ nhớ. Ứng dụng production cần dùng registry/exporter tương ứng với backend, chẳng hạn Prometheus hoặc một hệ thống metrics khác.

Ứng dụng nên gọi bindTo() sau khi đã có registry và các nguồn trạng thái, nhưng trước khi cần thu thập các meter. Đóng registry tại điểm kết thúc vòng đời do chính ứng dụng sở hữu; không đóng một registry dùng chung từ một thành phần nghiệp vụ có vòng đời ngắn.

## 4. Đăng ký MeterBinder dưới dạng bean trong Spring Boot

Trong Spring Boot, có thể khai báo binder bằng @Bean. Khi metrics auto-configuration đang hoạt động, Spring Boot phát hiện các bean kiểu MeterBinder và tự động bind chúng vào MeterRegistry được quản lý.

~~~java
import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsConfiguration {

    @Bean
    MeterBinder jobQueueMeterBinder(
        JobQueue jobQueue,
        JobCompletionState completionState
    ) {
        return new JobQueueMeterBinder(
            jobQueue.queue(),
            completionState.completedJobs()
        );
    }
}
~~~

Trong ví dụ, JobQueue và JobCompletionState là các bean nghiệp vụ do ứng dụng quản lý. queue() trả về queue thật đang được worker sử dụng; completedJobs() trả về bộ đếm tích lũy mà worker cập nhật. Binder dùng chính các đối tượng đó để đăng ký meter.

Không cần gọi jobQueueMeterBinder.bindTo(registry) bên trong bean factory. Spring Boot thực hiện bước bind khi cấu hình registry. Nếu tự bind thêm lần nữa, ứng dụng sẽ làm vòng đời đăng ký khó hiểu và có thể tạo xung đột identity hoặc cấu hình không nhất quán.

### Cần dependency và registry phù hợp

Để binder được tự động bind, ứng dụng cần có Micrometer và Spring Boot metrics auto-configuration. Trong ứng dụng dùng Actuator, các dependency thường gặp là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Dependency registry xác định cách metrics được export. Nếu dùng Prometheus, có thể expose endpoint tương ứng:

~~~properties
management.endpoints.web.exposure.include=health,prometheus
~~~

Property này chỉ expose endpoint khi ứng dụng đã có registry và cấu hình Actuator tương ứng. Nó không thay thế dependency của registry.

## 5. Phân biệt MeterBinder với MeterRegistryCustomizer

Hai cơ chế thường xuất hiện cạnh nhau trong Spring Boot nhưng có mục đích khác nhau:

| Cơ chế | Mục đích | Ví dụ |
| --- | --- | --- |
| MeterBinder | Đăng ký các meter từ một thành phần hoặc nguồn trạng thái | Queue depth, cache size, pool state |
| MeterRegistryCustomizer | Cấu hình registry trước khi dùng | Common tags, naming/filter policy |

Ví dụ common tags bằng MeterRegistryCustomizer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CommonMetricsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonTags() {
        return registry -> registry.config().commonTags(
            "service", "order-service",
            "environment", "production"
        );
    }
}
~~~

Customizer thiết lập cấu hình chung của registry. Binder đăng ký meter cụ thể. Nếu một metric cần tag riêng như queue=email, hãy khai báo tag đó trong binder; nếu mọi metric cần tag service và environment, common tags phù hợp hơn.

Không dùng MeterRegistryCustomizer để thay thế binder khi cần đóng gói logic đọc trạng thái của một thành phần. Cũng không dùng binder chỉ để đặt common tags cho mọi meter.

## 6. Một binder có thể bind vào nhiều registry

Ứng dụng có thể có nhiều registry, ví dụ registry cho Prometheus và registry cho một backend khác. Cơ chế quản lý registry có thể gọi bindTo() cho từng registry đích.

Vì vậy, binder nên được thiết kế theo cách:

- Mỗi lần bindTo(registry) chỉ đăng ký meter vào registry được truyền vào.
- Không giữ một field registry toàn cục trong binder.
- Không thay đổi hoặc reset nguồn trạng thái khi bind.
- Dùng cùng tên, tags và semantics cho cùng metric trên các registry.
- Tránh giả định một binder chỉ được gọi đúng một lần trong toàn bộ tiến trình.

Nếu hai registry xuất cùng nguồn trạng thái, mỗi registry có meter riêng để export nhưng cùng quan sát một trạng thái ứng dụng. Việc ghi nhận nghiệp vụ không cần tăng gấp đôi chỉ vì có hai registry; binder chỉ kết nối nguồn trạng thái với từng registry.

Đối với CompositeMeterRegistry, hãy hiểu rõ registry nào đang sở hữu các registry con và cách binder được bind trong cấu hình ứng dụng. Tránh tự đăng ký cùng binder ở cả composite và các registry con nếu framework đã quản lý việc đó, vì có thể gây đăng ký lặp hoặc khó kiểm soát.

## 7. Vòng đời và tham chiếu của nguồn dữ liệu

Gauge thường giữ tham chiếu yếu đến object được quan sát. Nếu nguồn trạng thái không còn tham chiếu mạnh nào khác, garbage collector có thể thu hồi object và Gauge không còn đọc được giá trị mong muốn.

Trong binder, hãy giữ nguồn dữ liệu trong field:

~~~java
public final class QueueMeterBinder implements MeterBinder {

    private final BlockingQueue<Job> queue;

    public QueueMeterBinder(BlockingQueue<Job> queue) {
        this.queue = queue;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder("jobs.queue.depth", queue, BlockingQueue::size)
            .register(registry);
    }
}
~~~

Trong Spring, queue thường được giữ bởi bean JobQueue và binder cũng giữ tham chiếu đến queue. Cách này giúp nguồn dữ liệu tồn tại trong suốt thời gian metrics cần được thu thập.

Không tạo một object tạm bên trong bindTo() rồi chỉ truyền object đó cho Gauge nếu không có nơi nào khác giữ tham chiếu mạnh. Ví dụ, tạo new AtomicInteger() trực tiếp trong lời gọi Gauge.builder() có thể khiến object bị thu hồi sau khi bind.

## 8. Thread safety và chi phí khi thu thập

bindTo() thường chỉ chạy lúc khởi tạo, nhưng supplier của Gauge hoặc FunctionCounter được gọi trong lúc thu thập metrics. Nguồn trạng thái vì vậy phải hỗ trợ truy cập đồng thời:

- Dùng queue concurrent hoặc API trạng thái thread-safe của thư viện.
- Dùng AtomicLong/LongAdder cho bộ đếm được nhiều thread cập nhật.
- Không truy vấn database hoặc gọi HTTP trong supplier.
- Không giữ lock lâu khi đọc trạng thái.
- Không cập nhật trạng thái trong quá trình đọc metrics.

Nếu một binder đọc nhiều giá trị có quan hệ với nhau, cần quyết định có yêu cầu snapshot nhất quán hay không. Đọc ba AtomicLong liên tiếp có thể nhận ba giá trị ở những thời điểm hơi khác nhau. Nếu sai khác đó không ảnh hưởng vận hành, có thể chấp nhận; nếu cần snapshot nhất quán, hãy lấy snapshot từ thành phần sở hữu trạng thái bằng cơ chế đồng bộ ngắn.

## 9. Đặt tên, tags và kiểm soát cardinality

Binder là nơi thuận tiện để chuẩn hóa tên metric và tags cho một thành phần. Hãy chọn tags mô tả nhóm có số lượng hữu hạn:

| Nên dùng | Tránh dùng |
| --- | --- |
| queue=email hoặc queue=report | job_id |
| pool=primary hoặc pool=replica | connection_id |
| result=success hoặc result=failure | Exception message tự do |
| operation=submit hoặc operation=consume | request_id |

Không tạo meter cho từng request, user hoặc job. Nếu có nhiều queue động, hãy giới hạn danh sách queue được instrument hoặc gom theo nhóm có ý nghĩa vận hành.

Đặt tên theo đại lượng được đo và dùng đơn vị rõ ràng. Ví dụ, jobs.queue.depth là số job đang chờ; jobs.completed là tổng job hoàn tất. Không dùng cùng một tên cho hai đại lượng có semantics khác nhau.

## 10. Kiểm thử binder trong Java

Có thể kiểm tra binder với SimpleMeterRegistry mà không cần chạy Spring context:

~~~java
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicLong;

import static org.assertj.core.api.Assertions.assertThat;

class JobQueueMeterBinderTest {

    @Test
    void bindsQueueGaugeAndCompletedFunctionCounter() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        BlockingQueue<Job> queue = new LinkedBlockingQueue<>();
        AtomicLong completedJobs = new AtomicLong(5);

        queue.add(new Job());
        queue.add(new Job());

        new JobQueueMeterBinder(queue, completedJobs).bindTo(registry);

        Gauge depth = registry.find("jobs.queue.depth")
            .tag("queue", "email")
            .gauge();
        FunctionCounter completed = registry.find("jobs.completed")
            .tag("queue", "email")
            .functionCounter();

        assertThat(depth).isNotNull();
        assertThat(depth.value()).isEqualTo(2.0);
        assertThat(completed).isNotNull();
        assertThat(completed.count()).isEqualTo(5.0);

        queue.poll();
        completedJobs.incrementAndGet();

        assertThat(depth.value()).isEqualTo(1.0);
        assertThat(completed.count()).isEqualTo(6.0);

        registry.close();
    }
}
~~~

Kiểm thử xác nhận binder đăng ký meter với đúng tên/tags và các meter đọc trạng thái mới. Nó cũng xác nhận FunctionCounter đọc bộ đếm tích lũy mà không tự tăng khi scrape.

### Kiểm thử đăng ký trong Spring Boot

Với binder bean, nên có một integration test dùng Spring application context để xác minh:

- Bean MeterBinder được tạo từ các dependency đúng.
- Meter xuất hiện trong registry do Spring Boot quản lý.
- Meter có common tags và tags riêng theo cấu hình.
- Endpoint scrape/export hiển thị metric khi registry tương ứng được cấu hình.
- Không có binder bị bind thủ công lần thứ hai.

Unit test với SimpleMeterRegistry kiểm tra logic binder; integration test kiểm tra đường auto-configuration của Spring Boot và exporter.

## 11. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tạo registry mới bên trong bindTo() | Metrics không đi vào registry mà ứng dụng export | Dùng registry được truyền vào |
| Khai báo binder bean rồi tự gọi bindTo() lần nữa | Đăng ký lặp và cấu hình khó theo dõi | Để Spring Boot tự bind bean |
| Tạo nguồn Gauge tạm thời trong bindTo() | Nguồn có thể bị garbage collector thu hồi | Giữ nguồn trạng thái trong field hoặc bean |
| Reset counter khi bind | Mất trạng thái tích lũy nghiệp vụ | Không thay đổi state trong bindTo() |
| Dùng tag động như job ID | Cardinality tăng nhanh | Dùng nhóm giá trị hữu hạn |
| Supplier thực hiện I/O | Scrape chậm và có thể gây tải phụ | Đọc trạng thái trong bộ nhớ |
| Chỉ kiểm thử binder mà không kiểm tra endpoint | Có thể bỏ sót lỗi auto-configuration/export | Bổ sung integration test |

## 12. Quy trình lựa chọn cách đăng ký

Khi tích hợp metrics cho một thành phần:

1. Xác định nguồn trạng thái và meter phù hợp với semantics.
2. Đóng gói việc đăng ký vào một lớp triển khai MeterBinder.
3. Giữ tham chiếu đến nguồn dữ liệu có vòng đời phù hợp.
4. Nếu dùng Java thuần, tạo registry rồi gọi bindTo(registry) trong giai đoạn khởi tạo.
5. Nếu dùng Spring Boot, khai báo binder bằng @Bean để auto-configuration bind vào registry.
6. Dùng MeterRegistryCustomizer cho common tags và cấu hình registry.
7. Giữ tên, tags và đơn vị ổn định; kiểm soát cardinality.
8. Kiểm thử với SimpleMeterRegistry và kiểm tra auto-binding/export bằng integration test.
9. Để thành phần sở hữu registry quản lý shutdown; binder không tự đóng registry.

MeterBinder giúp tách logic đăng ký metrics khỏi mã nghiệp vụ và có thể tái sử dụng với nhiều registry. Trong Java thuần, ứng dụng kiểm soát thời điểm gọi bindTo(). Trong Spring Boot, bean MeterBinder được cơ chế metrics quản lý tự động bind. Chọn đúng cách đăng ký, giữ nguồn trạng thái an toàn và kiểm tra đường export sẽ giúp instrumentation hoạt động nhất quán trong suốt vòng đời ứng dụng.
