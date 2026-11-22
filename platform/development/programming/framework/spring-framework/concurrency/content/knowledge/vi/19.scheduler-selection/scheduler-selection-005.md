# DefaultManagedTaskScheduler trong môi trường Jakarta EE

Trong Spring Framework, việc chạy định kỳ hoặc chạy một lần sau một thời điểm được biểu diễn qua giao diện `TaskScheduler`. Khi ứng dụng chạy độc lập bằng Spring Boot hoặc trong một servlet container cho phép tự quản lý thread, người phát triển thường dùng `ThreadPoolTaskScheduler`. Nhưng trong **môi trường Jakarta EE application server được quản lý**, việc ứng dụng tự tạo và sở hữu thread có thể không phù hợp với chính sách của container. Spring cung cấp **`DefaultManagedTaskScheduler`** để sử dụng một bộ thực thi lịch chạy **do application server quản lý** thay vì dựng một pool riêng.

`DefaultManagedTaskScheduler` thuộc package `org.springframework.scheduling.concurrent`. Nó là một biến thể dựa trên JNDI của `ConcurrentTaskScheduler`; mặc định tra cứu `java:comp/DefaultManagedScheduledExecutorService` và ủy quyền việc lên lịch cho đối tượng `jakarta.enterprise.concurrent.ManagedScheduledExecutorService` do Jakarta EE container cung cấp. Đây là lựa chọn đúng khi hệ thống đã có managed scheduling resource và muốn tuân theo quản lý thread, vòng đời và component context của application server.

**Trọng tâm:** tên lớp này là một **Spring adapter**, không phải dịch vụ lập lịch bền vững xuyên máy chủ; nó không tự tạo Jakarta EE container, không tự tạo resource JNDI, không thay thế `@EnableScheduling`, và không làm cho job đã được lên lịch tồn tại qua khởi động lại JVM.

## 1. Mục tiêu học tập

Sau bài học, bạn sẽ có thể:

- Phân biệt `TaskScheduler` với `TaskExecutor` và biết khi nào nên chọn `DefaultManagedTaskScheduler`.
- Hiểu `ManagedScheduledExecutorService` thuộc Jakarta Concurrency/JSR-236 và JNDI mặc định `java:comp/DefaultManagedScheduledExecutorService`.
- Cấu hình Spring bean `TaskScheduler` dựa trên managed resource; sử dụng `@EnableScheduling` và `@Scheduled` hoặc gọi `TaskScheduler` trực tiếp.
- Biết cách điều chỉnh `jndiName` khi container khai báo resource riêng và xác nhận lookup tại lúc bean khởi tạo.
- Phân biệt managed scheduler với `ThreadPoolTaskScheduler`, `ConcurrentTaskScheduler` và `DefaultManagedTaskExecutor`.
- Hiểu vòng đời, thread/component context, transaction và chính sách thực thi thuộc trách nhiệm của Jakarta EE server.
- Biết vì sao không được tự gọi `shutdown()` hoặc thay cấu hình core/max pool bằng API của Spring wrapper.
- Kiểm tra các kiểu lập lịch: một lần, fixed-rate, fixed-delay và Spring `Trigger`/cron; quan sát lỗi, delay, trôi lịch và overload.
- Phát hiện các tình huống test local thiếu JNDI, nhiều replica cùng chạy `@Scheduled`, job mất sau restart và những giả định sai về transaction/security context.
- Chạy một ví dụ Java 17+ độc lập để luyện API `ScheduledExecutorService` và kiểm tra cancellation; hiểu rõ ví dụ này **không mô phỏng Jakarta EE container**.

## 2. Phân biệt TaskScheduler và TaskExecutor

Spring có hai nhóm abstraction rất dễ nhầm:

| Giao diện | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| `TaskExecutor` | Thực thi tác vụ khi được gửi; không nhất thiết có lịch tương lai | `ThreadPoolTaskExecutor`, `DefaultManagedTaskExecutor` |
| `TaskScheduler` | Lên lịch tác vụ chạy ở thời điểm xác định hoặc lặp theo chu kỳ/trigger | `ThreadPoolTaskScheduler`, `ConcurrentTaskScheduler`, `DefaultManagedTaskScheduler` |
| `ScheduledExecutorService` của JDK | API thấp hơn hỗ trợ `schedule`, `scheduleAtFixedRate`, `scheduleWithFixedDelay` | `ScheduledThreadPoolExecutor` |
| `ManagedScheduledExecutorService` của Jakarta | Mở rộng API scheduled executor với ngữ nghĩa container-managed/context | Resource do Jakarta EE server cung cấp qua JNDI/injection |

`@Async` là cơ chế chuyển một **lời gọi** sang executor; `@Scheduled` đánh dấu method để hạ tầng scheduling của Spring **đăng ký một lịch**. Hai nhu cầu này có thể cùng tồn tại nhưng cấu hình không tự thay thế nhau. `@EnableScheduling` kích hoạt phát hiện `@Scheduled`; `@EnableAsync` kích hoạt xử lý `@Async`, không phải điều kiện bắt buộc để chạy scheduled methods.

## 3. Vì sao Jakarta EE cần managed scheduler?

Một Jakarta EE application server quản lý tài nguyên cho các component: thread, classloader, naming context, security và các chính sách quản trị. Tự gọi:

~~~java
Executors.newScheduledThreadPool(5)
~~~

trong một bean ứng dụng có thể gây vấn đề nếu runtime hạn chế tạo unmanaged thread, không thể giới hạn/quản lý pool theo application server, hoặc không dọn được task khi redeploy. Đây là một biểu thức **Java SE minh họa**, không phải phương án khuyến nghị trong môi trường container-managed nghiêm ngặt.

Jakarta Concurrency định nghĩa resource `ManagedScheduledExecutorService` để app submit tác vụ chạy sau một delay, chạy định kỳ hoặc theo cơ chế trigger được Jakarta hỗ trợ. Resource được **container tạo và quản lý**, còn code ứng dụng chỉ sử dụng.

Sơ đồ:

~~~text
Spring application component
  |
  | @Scheduled / TaskScheduler.schedule(...)
  v
Spring DefaultManagedTaskScheduler
  |
  | JNDI lookup trong lúc khởi tạo bean
  v
java:comp/DefaultManagedScheduledExecutorService
  |
  v
Jakarta EE ManagedScheduledExecutorService
  |
  +-- container quản lý thread pool, component context, policy
  |
  +-- thực thi Runnable/Callable theo lịch
~~~

Đây là nguyên tắc **phân tách trách nhiệm**:

- Spring: cung cấp API scheduling và ánh xạ `@Scheduled`/`Trigger`.
- Jakarta EE server: cung cấp managed executor resource, kiểm soát thread, cấu hình vận hành, lifecycle và context theo specification.
- Ứng dụng: định nghĩa việc cần làm, lịch chạy, xử lý lỗi và sự an toàn nghiệp vụ (idempotency, transaction, retry...).

## 4. DefaultManagedTaskScheduler chính xác là lớp gì?

Javadoc Spring Framework mô tả:

- Tên đầy đủ: `org.springframework.scheduling.concurrent.DefaultManagedTaskScheduler`.
- Kế thừa: `ConcurrentTaskScheduler`.
- Triển khai: `InitializingBean` ngoài các giao diện scheduler/executor từ superclass.
- Không phải một scheduler tạo pool riêng khi gọi constructor.
- Mặc định tra cứu resource JNDI tên `java:comp/DefaultManagedScheduledExecutorService`.
- JNDI lookup được thực hiện ở `afterPropertiesSet()` khi Spring BeanFactory khởi tạo bean. Với một Spring bean thông thường, bạn **không cần tự gọi `afterPropertiesSet()`**.
- Có các property như `setJndiName`, `setJndiEnvironment`, `setJndiTemplate`, `setResourceRef` để thay cách tra cứu phù hợp môi trường.

Điểm thường bị bỏ qua: **chỉ tạo một object `new DefaultManagedTaskScheduler()` trong Java thuần không lập tức có một scheduled executor hoạt động**. Khi bean khởi tạo, class cần JNDI resource hợp lệ; chạy ngoài một naming environment có bind resource như Jakarta EE sẽ khiến lookup thất bại.

### JNDI chuẩn

Theo Jakarta Concurrency, môi trường Jakarta EE tương thích cung cấp default resource dưới tên:

~~~text
java:comp/DefaultManagedScheduledExecutorService
~~~

Đừng nhầm với:

~~~text
java:comp/DefaultManagedExecutorService
~~~

Tên thứ hai dành cho `ManagedExecutorService` phục vụ công việc không nhất thiết có scheduling API. Nếu cấu hình `DefaultManagedTaskScheduler` trỏ sang managed executor **không triển khai `ScheduledExecutorService`**, khởi tạo/sử dụng scheduler không đáp ứng contract.

### JSR-236 và package Jakarta

Tài liệu Spring vẫn thường dùng cụm “JSR-236” để chỉ nguồn gốc Java EE Concurrency Utilities. Trong Jakarta EE hiện đại, API nằm ở `jakarta.enterprise.concurrent.ManagedScheduledExecutorService`. Ở hệ thống Java EE/Jakarta EE cũ, bạn có thể gặp `javax.enterprise.concurrent.*`. **Không mặc định các package `javax` và `jakarta` là tương thích nhị phân.**

Khi dùng Spring Framework 6.x, cần kiểm tra runtime Jakarta EE và phiên bản Jakarta Concurrency tương thích; một application server cũ chỉ có `javax` không tự đáp ứng những điều Spring 6 dựa trên `jakarta`. Việc chỉ đổi dependency Maven mà không nâng server không sửa được namespace hoặc khả năng cung cấp resource.

## 5. Cấu hình Spring sử dụng managed scheduler mặc định

Trong một ứng dụng Spring deploy trên Jakarta EE application server có managed resource đúng tên JNDI:

Tệp **ManagedSchedulingConfig.java**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.DefaultManagedTaskScheduler;

@Configuration
@EnableScheduling
public class ManagedSchedulingConfig {

    @Bean(name = "taskScheduler")
    public TaskScheduler taskScheduler() {
        return new DefaultManagedTaskScheduler();
    }
}
~~~

Đây là **một Spring configuration class**, cần dependency `spring-context`, JNDI resource do Jakarta EE server cung cấp và một Spring ApplicationContext phù hợp. Không thể chạy riêng file này bằng `javac`/`java` mà không có các thư viện và container.

Giải thích:

1. `@EnableScheduling` bật hạ tầng nhận diện các method `@Scheduled` trong Spring context.
2. Bean tên `taskScheduler` có kiểu `TaskScheduler` giúp Spring lựa chọn scheduler cụ thể thay vì để hạ tầng tự tạo scheduler fallback.
3. `new DefaultManagedTaskScheduler()` chỉ khai báo wrapper Spring; khi BeanFactory khởi tạo bean và gọi `afterPropertiesSet()`, wrapper tra JNDI resource mặc định.
4. Sau lookup, Spring giao việc lập lịch qua managed scheduled executor, không tự sở hữu thread pool của executor đó.
5. Nếu JNDI resource không tồn tại hoặc không tương thích, ứng dụng có thể lỗi lúc khởi tạo bean. Điều này hữu ích để phát hiện cấu hình thiếu thay vì âm thầm chạy trên pool không được quản lý.

**Quan trọng:** đừng đăng ký đồng thời nhiều bean `TaskScheduler` cạnh tranh và kỳ vọng Spring chắc chắn tự chọn đúng. Tên `taskScheduler` là quy ước Spring tìm kiếm; hoặc dùng `SchedulingConfigurer` để chọn đích tường minh.

### Một scheduled method

Tệp **PeriodicCleanupJob.java**:

~~~java
import java.time.Instant;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class PeriodicCleanupJob {

    @Scheduled(fixedDelay = 60000)
    public void cleanExpiredEntries() {
        // Thực hiện cleanup có giới hạn thời gian và idempotent.
        System.out.println("cleanup requested at " + Instant.now());
    }
}
~~~

Đây là **Spring component class**; output timestamp thay đổi nên **không có stdout cố định**. `fixedDelay=60000` là 60.000 mili-giây và được tính từ khi một lần thực thi hoàn tất tới khi lần sau được lên lịch chạy. Mã thật phải có cơ chế quản lý exception, timeout, transaction và tránh kéo dài vô hạn.

Nếu application server không cung cấp resource JNDI cần thiết, việc chỉ có `@Scheduled` và `@EnableScheduling` không khiến `DefaultManagedTaskScheduler` tự tạo một resource quản lý mới.

## 6. Trường hợp JNDI name tùy chỉnh

Trong một số Jakarta EE server, administrator có thể khai báo một `ManagedScheduledExecutorService` riêng với giới hạn tài nguyên/monitoring khác default và expose qua một tên JNDI đã xác minh. Spring hỗ trợ override:

~~~java
@Bean(name = "taskScheduler")
public TaskScheduler taskScheduler() {
    DefaultManagedTaskScheduler scheduler = new DefaultManagedTaskScheduler();
    scheduler.setJndiName("java:comp/env/concurrent/ReportsScheduler");
    return scheduler;
}
~~~

Đây là **mã bean method Spring minh họa**, cần các import như `ManagedSchedulingConfig`. Tên `java:comp/env/concurrent/ReportsScheduler` chỉ là ví dụ cấu hình do administrator có thể đăng ký, **không phải JNDI resource luôn tồn tại trên mọi server**. Cần cấu hình resource/ref thật tại deployment descriptor hoặc application server và bảo đảm loại resource tra được triển khai `ScheduledExecutorService`.

Các setter khác:

- `setJndiEnvironment(Properties)`: đặt các thuộc tính JNDI environment nếu runtime yêu cầu.
- `setJndiTemplate(JndiTemplate)`: thay JNDI template để phù hợp integration/configuration.
- `setResourceRef(boolean)`: ảnh hưởng cách giải tên tương đối theo environment naming context `java:comp/env/`.
- `setJndiName(String)`: thay tên lookup mặc định.

Ưu tiên sử dụng **tên đầy đủ** khi muốn tránh nhầm quy tắc prefix. Khi tên đã bắt đầu bằng `java:`, không tự ghép thêm `java:comp/env/`. Không nên sửa tên lúc runtime sau khi bean đã lookup xong và kỳ vọng tất cả task cũ tự chuyển sang resource mới.

### Lookup tự chạy khi nào?

`DefaultManagedTaskScheduler` là Spring `InitializingBean`. Trong lifecycle của bean được Spring quản lý, `afterPropertiesSet()` được gọi sau khi set properties để thực hiện lookup. Do đó:

~~~text
Spring creates bean
  -> optional setJndiName / other setters
  -> BeanFactory invokes afterPropertiesSet()
  -> JNDI lookup resolves managed scheduler
  -> bean ready for schedule() / @Scheduled
~~~

Nếu bạn tự tạo wrapper bằng `new` **ngoài Spring**, bạn phải tự quản lý initialization và dependency; cách đó không phải pattern chính của bài này. **Không tự gọi afterPropertiesSet trong @Bean method** của bean do Spring quản lý; có thể gây lookup lặp hoặc lỗi lifecycle khó hiểu.

## 7. @EnableScheduling, @Scheduled và tên bean taskScheduler

Trong Spring 6.x, hạ tầng đăng ký `@Scheduled` tìm scheduler từ context theo quy tắc được tài liệu hóa: có thể chọn bean `TaskScheduler` duy nhất; hoặc bean với tên `taskScheduler`; cũng có cơ chế tìm `ScheduledExecutorService` nếu phù hợp. Khi không resolve được, Spring có thể tạo scheduler local single-thread mặc định.

Điều này dẫn đến một rủi ro: **thấy `@Scheduled` chạy không chứng minh ứng dụng đang sử dụng Jakarta managed scheduler**. Nếu cấu hình của bạn không được import hoặc bean scheduler không được chọn, Spring có thể chạy bằng scheduler dự phòng khác.

Kiểm tra bằng ba cách:

1. Spring context có bean tên `taskScheduler` đúng kiểu `DefaultManagedTaskScheduler`?
2. Bean đã lookup JNDI thành công, delegate là managed resource mong muốn?
3. Trong integration test trên **server thật**, task chạy theo policy/threads của managed executor, và metrics của application server phản ánh hoạt động?

### Chọn scheduler tường minh bằng SchedulingConfigurer

Khi một ứng dụng có nhiều scheduler:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.annotation.SchedulingConfigurer;
import org.springframework.scheduling.config.ScheduledTaskRegistrar;

@Configuration
public class ExplicitSchedulingSelection implements SchedulingConfigurer {
    private final TaskScheduler managedScheduler;

    public ExplicitSchedulingSelection(
            @Qualifier("taskScheduler") TaskScheduler managedScheduler) {
        this.managedScheduler = managedScheduler;
    }

    @Override
    public void configureTasks(ScheduledTaskRegistrar registrar) {
        registrar.setTaskScheduler(managedScheduler);
    }
}
~~~

Đây là **Spring configuration class** được dùng cùng `@EnableScheduling` ở cấu hình phù hợp. Nó tường minh ràng buộc các tác vụ do registrar quản lý tới bean `taskScheduler`, giảm nguy cơ chọn nhầm scheduler khi thêm bean mới.

Nếu bạn chủ động dùng `@Scheduled(scheduler = "beanName")` trong phiên bản Spring hỗ trợ qualifier scheduler, hãy kiểm chứng đúng tên/qualifier và tương tác với `SchedulingConfigurer`; không dựa vào mặc định khi có nhiều lựa chọn.

## 8. Các API TaskScheduler mà DefaultManagedTaskScheduler cung cấp

`DefaultManagedTaskScheduler` kế thừa khả năng của `ConcurrentTaskScheduler`, triển khai Spring `TaskScheduler`:

| API | Nghĩa |
| --- | --- |
| `schedule(Runnable, Instant)` | Lên lịch chạy một lần tại khoảng thời gian được biểu diễn bằng `Instant` |
| `schedule(Runnable, Trigger)` | Lên lịch theo một `Trigger` do Spring cung cấp, ví dụ cron/custom trigger |
| `scheduleAtFixedRate(Runnable, Duration)` | Lặp theo chu kỳ cố định từ mốc start mặc định |
| `scheduleAtFixedRate(Runnable, Instant, Duration)` | Lặp fixed-rate từ mốc bắt đầu được chỉ định |
| `scheduleWithFixedDelay(Runnable, Duration)` | Lặp sau một khoảng delay tính từ khi lần chạy trước hoàn tất |
| `scheduleWithFixedDelay(Runnable, Instant, Duration)` | Lặp fixed-delay với mốc đầu |
| `getClock()` | Clock dùng cho việc xác định thời điểm lên lịch, tùy implementation |

Mỗi method có thể trả một `ScheduledFuture<?>` (với `schedule(Trigger)` có thể không tạo future nếu trigger không cho lần chạy kế tiếp), giúp caller theo dõi/hủy lịch trong phạm vi semantics của executor. Một callback định kỳ kéo dài, exception và việc cancel cần được xử lý có chủ đích.

### Gọi chương trình theo một Instant

Tệp **ReportSchedulingService.java**:

~~~java
import java.time.Instant;
import java.util.concurrent.ScheduledFuture;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Service;

@Service
public class ReportSchedulingService {
    private final TaskScheduler scheduler;

    public ReportSchedulingService(TaskScheduler scheduler) {
        this.scheduler = scheduler;
    }

    public ScheduledFuture<?> requestReportOnce(
            String reportId, Instant at) {
        return scheduler.schedule(
                () -> generateReport(reportId), at);
    }

    private void generateReport(String id) {
        System.out.println("Generating report " + id);
    }
}
~~~

Đây là **Spring-managed service** cần bean `TaskScheduler`. Nó lên lịch một lần tại `at`. Giá trị `ScheduledFuture` là handle JVM phục vụ theo dõi/hủy lịch; nó **không phải một job ID bền vững** để lưu qua deployment. Nếu ứng dụng chạy nhiều replica, mỗi instance tự nhận `requestReportOnce` và lưu handle trong RAM sẽ không có phối hợp job toàn cụm.

### Dùng CronTrigger

~~~java
import java.time.ZoneId;
import org.springframework.scheduling.support.CronTrigger;

scheduler.schedule(
        () -> recalculateDailyStats(),
        CronTrigger.forFixedExecution("0 0 2 * * *"));
~~~

Đây là **đoạn tích hợp cần scheduler/recalculateDailyStats** do ứng dụng cung cấp. Với cron của Spring, biểu thức có sáu thành phần, bao gồm **giây**. Nếu cần chọn múi giờ, dùng API CronTrigger phù hợp phiên bản Spring hoặc khai báo `@Scheduled(cron = ..., zone = ...)`. Ví dụ trên chạy lúc 02:00 theo clock/timezone mặc định của trigger; không khẳng định nó chạy “02:00 tại Việt Nam” nếu chưa đặt zone.

**Lưu ý khi chọn Spring version:** API factory `CronTrigger.forFixedExecution(String)` có trong Spring 6.1.3+; khi dùng phiên bản cũ hơn, dùng constructor/factory tương thích đúng tài liệu phiên bản đó. Nếu mục tiêu chỉ là method annotation, `@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")` là lựa chọn rõ ý hơn.

## 9. Spring Trigger và Jakarta Trigger khác nhau ra sao?

Spring có interface `org.springframework.scheduling.Trigger` và class `CronTrigger`. Jakarta Concurrency có `jakarta.enterprise.concurrent.Trigger` và `ManagedScheduledExecutorService.schedule(Runnable, Trigger)`. Đây là **hai interface khác nhau**, không thể cast tùy ý.

`ConcurrentTaskScheduler` của Spring nhận biết một delegate kiểu `ManagedScheduledExecutorService` và có logic adapter để lập lịch theo `Spring Trigger` bằng trigger của Jakarta khi phù hợp. Nhờ vậy, một Spring service có thể dùng `scheduler.schedule(runnable, springTrigger)` mà không phải tự viết `jakarta.enterprise.concurrent.Trigger`.

~~~text
Spring CronTrigger
       |
       v
Spring TaskScheduler.schedule(Runnable, Spring Trigger)
       |
       v
ConcurrentTaskScheduler adapter
       |
       +-- delegate là ManagedScheduledExecutorService?
             |
             +-- Có: sử dụng Jakarta Trigger adapter khi thích hợp
             |
             +-- Không: fallback lên cách schedule theo delay của JDK
~~~

Điều này không đồng nghĩa các implementation có chi tiết scheduling hoàn toàn giống nhau. Cần integration test nhất là với cron, timezone, DST, misfire, skip và trigger tùy chỉnh. Chính sách của server vẫn ảnh hưởng thời điểm thật sự chạy.

## 10. Fixed-rate, fixed-delay và cron: không chọn chỉ dựa vào tên

Ba chiến lược cần hiểu:

### Fixed-rate

`scheduleAtFixedRate` biểu diễn chu kỳ dựa trên mốc bắt đầu. Nếu task chạy lâu hoặc executor bị quá tải, thời gian bắt đầu thực tế có thể lệch lịch. Theo contract `ScheduledThreadPoolExecutor` tiêu chuẩn, các lần thực thi định kỳ của **cùng một periodic task** không chạy đồng thời; nếu một lần kéo dài hơn chu kỳ, lần kế có thể bắt đầu muộn.

Không tự suy rộng mọi chi tiết đó cho mọi vendor implementation của `ManagedScheduledExecutorService`, nhất là các khả năng trigger mở rộng hoặc môi trường cluster. Cần kiểm thử/đọc tài liệu server.

### Fixed-delay

`scheduleWithFixedDelay` đợi một khoảng sau khi lần trước **kết thúc** rồi mới thực thi lần tiếp theo. Thường phù hợp khi muốn tránh chạy dồn các lần xử lý dữ liệu, nhất là tác vụ có thời gian chạy biến thiên.

### Cron/Trigger

`CronTrigger` dựa vào thời điểm lịch (giờ, ngày, thứ, tháng) hoặc `TriggerContext` của Spring. Kết quả thực tế chịu tác động của timezone, clock, daylight saving, thời gian task trước hoàn tất và semantics trigger. Với yêu cầu “mỗi ngày lúc 02:00” cần ghi rõ zone và xử lý ngày DST thiếu/lặp giờ. Với lịch công việc tài chính hoặc tích hợp có SLA, thêm idempotency và kiểm tra giờ thực tế.

### Bảng chọn

| Mong muốn | API/annotation phù hợp | Ghi chú |
| --- | --- | --- |
| Một lần sau 10 giây | `TaskScheduler.schedule(task, Instant)` | Không bền vững qua JVM restart |
| Cố gắng bắt đầu mỗi 60 giây | `scheduleAtFixedRate(..., Duration.ofSeconds(60))` | Task chậm hoặc overload có thể làm lệch nhịp |
| Đợi 60 giây sau lần trước kết thúc | `scheduleWithFixedDelay(..., Duration.ofSeconds(60))` | Thời gian thực giữa lần bắt đầu dài hơn duration |
| Mỗi ngày vào một giờ xác định | `@Scheduled(cron=..., zone=...)` hoặc `CronTrigger` | Cần hiểu timezone/DST và cron syntax |
| Dựa vào lần hoàn tất/thực tế | Spring `Trigger` tự định nghĩa | Test trigger theo `TriggerContext` |
| Khôi phục lịch sau khi server restart | Persistent job store/enterprise scheduler | Không phải chỉ DefaultManagedTaskScheduler |

## 11. Managed context được container hỗ trợ đến đâu?

Jakarta Concurrency định nghĩa rằng default `ManagedScheduledExecutorService` phải hỗ trợ những component context nhất định. Theo specification, context bắt buộc của default managed scheduled executor gồm **naming context**, **classloader** và **security information** liên quan đến component gửi task.

Điều này **không** có nghĩa:

- Toàn bộ `ThreadLocal` tùy chỉnh của request sẽ tự được sao chép.
- Mọi giá trị MDC/tracing context sẽ tự xuất hiện trên worker.
- Transaction đang hoạt động ở thread submit sẽ được truyền đến thread thực thi.
- `@RequestScoped` bean luôn có semantics giống khi chạy trong request HTTP sống lâu.
- Kết quả của một scheduled job sẽ tự được gửi đến client theo hợp đồng request/response.

Spec của managed executor nêu rõ task chạy **ngoài transaction của thread gửi**. Nếu task cần transaction, phải tự định nghĩa transaction boundary cho việc thực thi, ví dụ gọi một Spring service có `@Transactional` qua proxy và transaction manager phù hợp; Jakarta cũng có đường `UserTransaction` khi được phép.

### Ví dụ Spring service transactional riêng

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryRefreshService {
    private final InventoryRepository repository;

    public InventoryRefreshService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void refreshInventory() {
        repository.refreshCachedInventory();
    }
}
~~~

Đây là **Spring bean minh họa** với `InventoryRepository` thuộc ứng dụng. Scheduled method ở một bean khác:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class InventoryRefreshSchedule {
    private final InventoryRefreshService service;

    public InventoryRefreshSchedule(InventoryRefreshService service) {
        this.service = service;
    }

    @Scheduled(fixedDelay = 60000)
    public void refresh() {
        service.refreshInventory();
    }
}
~~~

Đây là **Spring component riêng**, gọi qua bean proxy của `InventoryRefreshService` để transaction có thể mở ở worker. Không gọi `this.refreshInventory()` trong cùng service rồi kỳ vọng `@Transactional` proxy mode luôn có hiệu lực. Cấu hình transaction manager phải phù hợp resource Jakarta EE/JTA/JDBC thực tế.

Nếu ứng dụng cần propagate tracing/MDC, sử dụng context propagation được framework/container hỗ trợ hoặc truyền dữ liệu cần thiết qua payload/id; tránh dựa vào thread name hoặc ThreadLocal ngầm.

## 12. Vòng đời thuộc Jakarta EE server, không thuộc bean Spring

Đây là khác biệt lớn so với `ThreadPoolTaskScheduler` tạo local executor.

`ManagedScheduledExecutorService` được application server quản lý và có thể chia sẻ giữa nhiều component. Jakarta Concurrency quy định ứng dụng **không được tự điều khiển vòng đời chung** của managed executor bằng `shutdown()`/`shutdownNow()`; các lifecycle operations này được đặc tả là ném `IllegalStateException` khi ứng dụng gọi chúng.

Vì vậy:

- Không gọi `shutdown()` trên managed resource lấy qua JNDI khi một Spring bean bị destroy.
- Không cấu hình `ThreadPoolTaskScheduler.setPoolSize()` rồi mong nó thay đổi pool do administrator tạo.
- Không lấy `ScheduledThreadPoolExecutor` từ Spring wrapper để chỉnh core threads: delegate thực tế có thể là container-managed object không hề expose API đó.
- Khi redeploy/shutdown, server có quyền đình chỉ/stop/cancel task theo policy; ứng dụng phải có idempotency và trạng thái bền cho công việc quan trọng.
- Tác vụ được chạy trong context của component; khi component không còn started, spec không cho phép các task của nó tiếp tục thực thi như đang hoạt động bình thường.

**Lifecycle của wrapper và managed delegate là hai thứ khác nhau.** Spring có thể khởi tạo/hủy bean `DefaultManagedTaskScheduler` của ứng dụng, nhưng không sở hữu quyền shutdown resource chung của Jakarta EE server.

### Cancellation trong ứng dụng

Một `ScheduledFuture<?>` do scheduler trả về có thể được dùng để yêu cầu hủy **lịch cụ thể**, tùy hợp đồng của executor. Đây không phải là lệnh shutdown toàn bộ managed scheduler. Đối với periodic jobs, hãy giữ handle nếu cần tắt lịch trong một instance; nhưng khi multi-instance hoặc restart, handle RAM không thể dùng làm danh tính job bền vững.

## 13. DefaultManagedTaskScheduler so với các lựa chọn khác

| Lớp | Executor phía dưới | Ai sở hữu thread/lifecycle? | Môi trường tiêu biểu |
| --- | --- | --- | --- |
| `DefaultManagedTaskScheduler` | JNDI `ManagedScheduledExecutorService` hoặc ScheduledExecutorService phù hợp | Container/owner của JNDI resource | Jakarta EE application server |
| `ConcurrentTaskScheduler` | `ScheduledExecutorService` được truyền vào hoặc cấu hình | Bên tạo/đưa executor vào | Adapter cho executor có sẵn |
| `ThreadPoolTaskScheduler` | Local `ScheduledThreadPoolExecutor` | Spring bean/app | Spring Boot standalone, môi trường cho phép tự quản thread |
| `DefaultManagedTaskExecutor` | JNDI `ManagedExecutorService` | Jakarta EE container | Task dispatch không nhất thiết cần lịch |
| `ThreadPoolTaskExecutor` | Local `ThreadPoolExecutor` | Spring bean/app | `@Async` hoặc task queue thông thường |

### Vì sao không dùng DefaultManagedTaskExecutor để đặt lịch?

`DefaultManagedTaskExecutor` lookup default `java:comp/DefaultManagedExecutorService`, không phải default scheduled executor. Nó thích hợp cho `execute/submit` các task không yêu cầu `schedule`/`fixedRate`/`Trigger`. Nếu cần lịch trong Jakarta EE, **DefaultManagedTaskScheduler** mới là adapter đúng.

### Vì sao không luôn dùng ThreadPoolTaskScheduler?

`ThreadPoolTaskScheduler` rất hợp lý trong ứng dụng độc lập. Nó cho phép cấu hình pool size, thread-name prefix, error handler, shutdown behavior bằng bean properties. Nhưng nó sở hữu local pool và có thể không tuân thủ chính sách threading của một Jakarta EE server nghiêm ngặt. Spring reference khuyến nghị managed scheduler khi không nên tự tạo thread trong application server.

### Embedded servlet container có đồng nghĩa Jakarta EE full runtime không?

Không. Một ứng dụng Spring Boot chạy với embedded Tomcat/Jetty thường **không có** Jakarta Concurrency default managed scheduled executor bind tại `java:comp/DefaultManagedScheduledExecutorService` chỉ vì nó sử dụng servlet API `jakarta.servlet.*`. Nếu không có resource/JNDI infrastructure, `DefaultManagedTaskScheduler` là lựa chọn không phù hợp; dùng `ThreadPoolTaskScheduler` hoặc một executor adapter được cấu hình rõ.

Ngược lại, trên Jakarta EE application server đầy đủ, đừng tự động tạo unmanaged pool chỉ để bỏ qua bước xác minh JNDI vì nó chạy được ở local.

## 14. Ví dụ Java 17+ độc lập để kiểm tra API scheduled executor

`DefaultManagedTaskScheduler` **không thể được chứng minh đúng môi trường Jakarta EE** chỉ bằng một chương trình JDK thuần. Để có ví dụ chạy được và dễ kiểm chứng, phần này dùng **`ScheduledExecutorService` local** — chính là dạng API mà managed scheduled executor mở rộng. Demo giúp thực hành một lần, hủy trước khi chạy và lịch định kỳ; sau đó phải test riêng bean managed scheduler trên server thật.

Tệp **ScheduledExecutorContractDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class ScheduledExecutorContractDemo {

    private static void ensure(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        CountDownLatch release = new CountDownLatch(1);

        try {
            AtomicBoolean oneShotRan = new AtomicBoolean();
            ScheduledFuture<?> oneShot = scheduler.schedule(
                    () -> oneShotRan.set(true),
                    0, TimeUnit.MILLISECONDS);
            oneShot.get(5, TimeUnit.SECONDS);
            System.out.println("oneShot=" + oneShotRan.get());

            CountDownLatch blockerStarted = new CountDownLatch(1);
            Future<?> blocker = scheduler.submit(() -> {
                blockerStarted.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            ensure(blockerStarted.await(5, TimeUnit.SECONDS),
                    "Blocker did not start");

            AtomicBoolean cancelledBodyRan = new AtomicBoolean();
            ScheduledFuture<?> queued = scheduler.schedule(
                    () -> cancelledBodyRan.set(true),
                    0, TimeUnit.MILLISECONDS);

            boolean cancelled = queued.cancel(false);
            release.countDown();

            blocker.get(5, TimeUnit.SECONDS);
            scheduler.schedule(() -> {},
                    0, TimeUnit.MILLISECONDS).get(5, TimeUnit.SECONDS);

            System.out.println("cancelBeforeStart=" + cancelled);
            System.out.println("cancelledBodyRan=" + cancelledBodyRan.get());

            AtomicInteger count = new AtomicInteger();
            CountDownLatch thirdRun = new CountDownLatch(3);

            ScheduledFuture<?> periodic = scheduler.scheduleAtFixedRate(
                    () -> {
                        int current = count.incrementAndGet();
                        if (current <= 3) {
                            thirdRun.countDown();
                        }
                    },
                    0, 10, TimeUnit.MILLISECONDS);

            ensure(thirdRun.await(5, TimeUnit.SECONDS),
                    "Periodic task did not run three times");

            boolean cancelledPeriodic = periodic.cancel(false);
            System.out.println("periodicAtLeastThree=" + (count.get() >= 3));
            System.out.println("periodicCancelled=" + cancelledPeriodic);
        } finally {
            release.countDown();
            scheduler.shutdownNow();
            scheduler.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ScheduledExecutorContractDemo.java
java ScheduledExecutorContractDemo
~~~

Stdout được kiểm soát bằng latch/Future:

~~~text
oneShot=true
cancelBeforeStart=true
cancelledBodyRan=false
periodicAtLeastThree=true
periodicCancelled=true
~~~

**Vì sao output xác định?**

1. `oneShot.get(timeout)` chỉ trả về sau khi runnable đầu tiên hoàn tất, nên `oneShot=true`.
2. `blockerStarted.await` chứng minh single worker đang bị giữ; task queued chưa có thread chạy, nên `cancel(false)` thành công. Marker task bảo đảm worker đã đi qua phần queue cần xác nhận; body bị hủy chưa từng chạy.
3. `thirdRun` đếm ít nhất ba executions của periodic task; không in số lần thực tế để tránh phụ thuộc scheduler chạy nhanh hơn main. `cancel(false)` kết thúc periodic Future chưa hoàn thành bình thường; nó có thể ngăn các lần tiếp theo, nhưng không bảo đảm làm gián đoạn một body đang chạy.
4. `finally` đóng **local executor do demo tự tạo**. Trong ứng dụng Jakarta EE thật, **không được copy đoạn `shutdownNow()` để gọi trên managed scheduled executor của server**.

Demo này minh họa **JDK contract**, không mô phỏng JNDI, security/context propagation, Jakarta scheduling Trigger hoặc policies của application server.

## 15. Kiểm thử tích hợp bắt buộc trên Jakarta EE server

Muốn chứng minh `DefaultManagedTaskScheduler` hoạt động thực, test cần chạy trong hoặc tích hợp với **Jakarta EE runtime mục tiêu**, không chỉ một unit test Spring Boot local.

### Checklist

1. **JNDI resource:** kiểm tra server expose `java:comp/DefaultManagedScheduledExecutorService` hoặc tên do administrator cấp; kiểm tra nó thật sự triển khai `ManagedScheduledExecutorService` tương thích.
2. **Bean lookup:** khởi tạo Spring context với `DefaultManagedTaskScheduler`; startup không báo `NamingException`/`BeanCreationException`.
3. **Scheduler được chọn:** xác minh `@EnableScheduling` đang dùng bean `taskScheduler` hoặc cấu hình `SchedulingConfigurer` đúng, không dùng fallback local.
4. **One-shot:** lên lịch task một lần, dùng `CountDownLatch` và `ScheduledFuture.get(timeout)` để xác nhận có chạy.
5. **Fixed-rate/fixed-delay:** lên lịch task ngắn với period/delay nhỏ trong môi trường test và hủy future trong `finally`; không dùng sleep ngẫu nhiên.
6. **Cron/Trigger:** test múi giờ và lịch trigger; kiểm tra Spring-to-Jakarta trigger adapter với version/server thật.
7. **Component context:** trong task kiểm tra naming/classloader/security theo hợp đồng của server; không khẳng định MDC/transaction tự kế thừa.
8. **Transaction:** xác minh task không tự tham gia transaction từ thread submit, và transactional service riêng có thể mở transaction theo Spring/JTA.
9. **Error path:** ném exception có kiểm soát, xác minh error handler/logging và chính sách chạy lại periodic task của container, không mặc định giống local executor.
10. **Overload/rejection:** dùng resource có quota trong môi trường kiểm thử để xác nhận cách server phản ứng; không ghi giả số liệu max pool hoặc queue.
11. **Redeploy/shutdown:** xem task của application component cũ được xử lý ra sao; không để job cũ thao tác trên classloader đã unload.
12. **Multi-instance:** deploy nhiều replica/nodes nếu môi trường yêu cầu, kiểm tra mỗi instance có schedule độc lập hay application server thực hiện cơ chế cluster riêng.

### Một test có latch

Giả sử đã inject `TaskScheduler scheduler` từ Spring:

~~~java
CountDownLatch received = new CountDownLatch(1);
ScheduledFuture<?> future = scheduler.schedule(
        received::countDown,
        java.time.Instant.now().plusSeconds(1));

try {
    if (!received.await(5, TimeUnit.SECONDS)) {
        throw new AssertionError("Managed task did not execute");
    }
} finally {
    if (future != null) {
        future.cancel(false);
    }
}
~~~

Đây là **fragment integration test**, cần imports `CountDownLatch`, `ScheduledFuture`, `TimeUnit` và context/container đã cấu hình. Nó chỉ xác nhận lịch chạy; muốn chứng minh **managed context**, phải kiểm tra thuộc tính context/JNDI và evidence từ server. Không dùng `Thread.sleep(1000)` rồi đoán rằng worker đã chạy.

### Không được “làm giả” managed scheduler bằng startup local

Một unit test có thể inject stub/mock `TaskScheduler` để kiểm tra logic ứng dụng, hoặc sử dụng `ThreadPoolTaskScheduler` trong local profile để chạy nhanh. Nhưng test đó **không chứng minh** lookup JNDI, lifecycle và Jakarta EE context. Nên tách:

- **Unit test:** logic task, tính idempotent, exception handling, cron expression validation.
- **Integration test:** JNDI lookup, actual managed executor, server lifecycle, context propagation và scheduler selection.

Đây là một phần quan trọng của quyết định lựa chọn scheduler theo **môi trường deploy**, không phải theo sự tiện lợi của bài unit test.

## 16. Lỗi, exception và sự cố scheduling

### Lỗi lúc bean startup

Nếu default JNDI name không tồn tại, `DefaultManagedTaskScheduler.afterPropertiesSet` có thể ném `NamingException`; khi Spring khởi tạo bean, lỗi được bao thành startup failure. Khắc phục bằng cách:

- Xác minh ứng dụng chạy trên Jakarta EE runtime có resource tương thích.
- Đối chiếu JNDI naming tree/descriptor và tên `setJndiName`.
- Kiểm tra quyền truy cập JNDI resource, deployment context và classloader.
- Kiểm tra namespace `javax`/`jakarta` và version Spring/Jakarta EE.
- Nếu là Spring Boot standalone không có resource, chọn local scheduler đúng mục tiêu thay vì dựng một JNDI giả để qua startup.

### Lỗi trong task

Periodic task có thể ném exception. Spring scheduler có cơ chế error handler, trong khi managed delegate và server có chính sách xử lý exception riêng. Không tự cho rằng exception được ném ngược tới caller đã đăng ký lịch; caller từ lâu có thể đã thoát.

Cần thiết kế:

- Log/metric có correlation/job ID, không ghi payload nhạy cảm.
- Error policy rõ: log, stop schedule, retry, dead-letter hoặc chuyển trạng thái trong job store.
- Giới hạn timeout cho I/O, tránh một lần thực thi bị treo chiếm managed worker.
- Cân nhắc `ScheduledFuture.get()` chỉ cho one-shot hoặc khi periodic đã hoàn thành/hủy; `get()` trên periodic task đang chạy thường block vô hạn.

`ConcurrentTaskScheduler` có `setErrorHandler(ErrorHandler)` ở Spring adapter; khi dùng, phải test tác động thực của handler trong periodic scheduling và managed delegate. Đừng nuốt exception để mọi lần lỗi lặp vô hạn mà không báo cáo.

### Rejection và quota

Container có thể áp giới hạn capacity, policies và lifecycle. Khi resource không nhận task, lời gọi schedule có thể thất bại. Spring không tự retry một cách bền vững. Để xử lý lịch quan trọng, lưu request/job bền vững và có cơ chế phát lại; không suy đoán task đã được nhận khi method schedule vừa bị exception.

### Đồng hồ và timezone

Lịch một lần dùng `Instant`, còn cron dùng calendar/timezone. Một JVM clock thay đổi, timezone/DST hoặc chính sách clock của server có thể ảnh hưởng cách tính lượt chạy. Cần log **scheduled time**, **actual start time**, **completion time** để phân tích drift; không so sánh mỗi số lần chạy tổng.

## 17. Multiple replicas, exactly-once và độ bền

`DefaultManagedTaskScheduler` **không phải clustered persistent scheduler**. Mỗi Spring application context/instance thường đăng ký lịch riêng. Nếu cùng ứng dụng chạy trên ba node và mỗi node đều có bean `@Scheduled`, có khả năng cả ba node cùng chạy job, trừ khi hạ tầng server/ứng dụng có một cơ chế cluster coordination được cấu hình cụ thể.

Không được suy ra: “managed by Jakarta EE” nghĩa là scheduler **chỉ chạy một lần trên toàn cụm**. Jakarta Concurrency quy định quality-of-service at-most-once cho **mỗi task submission** trong phạm vi managed executor, đồng thời các task mặc định mang tính **transient** và không sống qua process restart. Nó **không** đồng nghĩa global exactly-once của một business job trên nhiều replica.

Nếu cần một job duy nhất toàn cụm:

- Dùng distributed lock/lease có thời hạn và fencing token nếu phù hợp.
- Dùng database job table với claim atomically và retry/idempotency.
- Dùng Quartz với persistent JobStore/cluster mode nếu yêu cầu tương ứng.
- Dùng message broker/job queue và consumer coordination khi task thực chất là công việc cần phân phối.
- Định nghĩa idempotency key để task lặp không gây double-charge/double-notification.

Một lịch **đúng giờ** cũng không bảo đảm side effect thành công: job có thể fail, timeout hoặc app crash. Nên đo completion outcome riêng với số lần trigger.

### Restart và lịch bị mất

Scheduled task trong memory không tự được hồi phục qua shutdown/redeploy. Nếu một one-shot task được lên lịch cho 23:00 nhưng server restart lúc 22:59 và không có durable job store, lịch đó có thể mất. Với `@Scheduled` định kỳ, mỗi context mới có thể đăng ký lại lịch, nhưng đó là lịch mới sau startup, không phải phục hồi transaction/“missed executions” theo business contract.

## 18. Quan sát vận hành đúng trọng tâm

Với Jakarta EE, capacity/quota do administrator quản lý, nên metrics từ application server rất quan trọng. Ứng dụng nên đo thêm:

| Metric | Câu hỏi |
| --- | --- |
| `scheduled_jobs_registered` | Có bao nhiêu lịch được đăng ký? |
| `scheduled_task_started_total` | Có bao nhiêu lượt thật sự bắt đầu? |
| `scheduled_task_completed_total` | Có bao nhiêu lượt hoàn tất thành công? |
| `scheduled_task_failed_total` | Bao nhiêu lượt lỗi? |
| `scheduler_rejected_total` | Có bao nhiêu lần container không nhận lịch mới? |
| `schedule_start_delay` | Chậm bao lâu so với thời điểm mong muốn? |
| `task_execution_duration` | Mỗi lượt giữ worker trong bao lâu? |
| `cancel_requested_total` | Có bao nhiêu lịch/task được yêu cầu hủy? |
| `managed_executor_active_threads` | Container đang cấp bao nhiêu worker (nếu có metric vendor)? |
| `missed_business_deadline_total` | Có bao nhiêu job chậm so với SLA nghiệp vụ? |

Đừng tự bịa thread-pool metrics nếu vendor không expose hoặc lớp wrapper không có API tương ứng. Xem JMX/management API của application server. Gắn tags vừa đủ (job type, node, outcome), tránh label theo jobId duy nhất tạo cardinality quá lớn.

### Đo đúng ba mốc

~~~text
scheduled timestamp ------ actual start ------- actual completion
               drift                     processing duration
~~~

Nếu app chỉ log “job hoàn tất lúc 10:05”, khó phân biệt job được scheduler kích hoạt trễ hay job chạy quá lâu. Vì `DefaultManagedTaskScheduler` không tự lưu lịch chạy bền vững, telemetry nên là một phần của thiết kế ngay từ đầu.

## 19. Các lỗi phổ biến cần tránh

1. **Chạy DefaultManagedTaskScheduler trong Java SE/Spring Boot standalone** rồi kỳ vọng có JNDI resource chuẩn của Jakarta EE.
2. **Nhầm DefaultManagedTaskScheduler với DefaultManagedTaskExecutor.** Hai default JNDI name khác nhau; scheduler cần scheduled executor.
3. **Chỉ bật @EnableAsync để chạy @Scheduled.** Scheduling cần `@EnableScheduling` hoặc cơ chế tương đương.
4. **Có nhiều TaskScheduler bean nhưng không chỉ rõ loại dùng.** Spring có thể chọn sai hoặc fallback local.
5. **Gọi constructor rồi tưởng adapter tự tạo thread pool.** Nó lookup executor qua JNDI khi bean init.
6. **Tự gọi afterPropertiesSet() trong @Bean method.** BeanFactory đã gọi lifecycle hook.
7. **Đặt setJndiName sai hoặc dùng JNDI name không được bind.** Bean startup có thể lỗi.
8. **Bắt NamingException rồi âm thầm dùng local pool trong production Jakarta EE** mà không có quyết định kiến trúc về quản lý thread.
9. **Dùng javax.enterprise.concurrent.* với Spring 6/Jakarta mới mà không xem compatibility.** API namespace không tương đương.
10. **Gọi shutdown/shutdownNow trên managed executor.** Lifecycle do server sở hữu, ứng dụng không có quyền đóng nó.
11. **Cố setPoolSize trên DefaultManagedTaskScheduler.** Lớp wrapper không sở hữu pool kiểu ThreadPoolTaskScheduler.
12. **Coi default managed scheduled service tự bảo đảm bền vững.** Jakarta Concurrency task thông thường transient.
13. **Coi “at-most-once” tương đương exactly-once toàn cụm.** Không có ràng buộc đó.
14. **Coi managed thread tự mang transaction của request.** Task chạy ngoài transaction của submitter.
15. **Coi MDC/ThreadLocal bất kỳ đều được truyền tự động.** Specification chỉ có context cụ thể, các loại khác cần hỗ trợ riêng.
16. **Dùng @Scheduled cho gửi email/charge quan trọng mà không idempotency.** Node restart và multi-replica có thể làm thiếu/trùng.
17. **Dùng fixedRate cho task lâu mà không đo drift.** Tác vụ không thể đảm bảo chạy đúng thời điểm dưới overload.
18. **Nhầm fixedDelay với fixedRate.** Một loại dựa vào completion, một loại dựa vào chu kỳ mốc.
19. **Chọn cron mà quên zone/DST.** Kết quả khác kỳ vọng lúc chuyển múi giờ.
20. **Cho rằng @Scheduled đều chạy trên thread riêng khỏi application.** Phụ thuộc adapter/executor và cấu hình thực.
21. **Chỉ unit test với local ScheduledExecutorService rồi khẳng định Jakarta JNDI đã đúng.** Cần integration test trên runtime thật.
22. **Không xử lý task exception hoặc rejection.** Các lần sau có thể bị ảnh hưởng bởi implementation/policy.
23. **Dùng ScheduledFuture.get() ngay sau schedule periodic và block mãi.** Periodic future không hoàn thành bình thường mỗi lượt.
24. **Không dọn lịch theo lifecycle app** nhưng lại tự shutdown managed resource chung. Cần phân biệt hủy task riêng và hủy executor.
25. **Bỏ qua việc hủy/chạy khi redeploy.** Code cũ có thể không được phép chạy sau component stop.
26. **Đọc số thread local để quản trị managed executor của server.** Capacity policy thuộc server.
27. **Để nhiều application context đăng ký @Scheduled trùng.** Có thể nhân số lượt chạy ngoài dự kiến.
28. **Tưởng Docker/Kubernetes tự cấp Jakarta managed resource.** Container infrastructure không tương đương Jakarta EE application server.
29. **Xem TaskScheduler như durable job scheduler.** TaskScheduler chủ yếu là API lên lịch in-process.
30. **Tự động fallback không được phê duyệt khi JNDI hỏng.** Che sự cố deployment/quản trị và sai chính sách thread.

## 20. Quy trình chọn scheduler đúng môi trường

Hãy quyết định theo điều kiện vận hành:

1. **Runtime là gì?** Jakarta EE application server có managed scheduled executor không, hay Spring Boot standalone/embedded servlet?
2. **Ai có quyền quản lý thread?** Nếu application server yêu cầu managed threads, chọn managed resource đúng contract.
3. **Scheduler cần gì?** `@Scheduled`, cron, fixed-delay, dynamic scheduling, cancellation; có cần điều chỉnh riêng pool/queue không?
4. **JNDI name nào thực sự tồn tại?** Default chuẩn hay resource do administrator provision? Đọc tài liệu deployment đúng server/version.
5. **Spring chọn bean nào?** Đăng ký `taskScheduler` hoặc `SchedulingConfigurer` rõ ràng; tránh hai đường fallback mơ hồ.
6. **Transaction/security context nào cần thiết?** Managed executor có component context nhưng không tự kế thừa caller transaction; thiết kế bean transactional riêng.
7. **Có yêu cầu bền vững/cluster không?** Nếu có, đưa vào job store/Quartz/message queue, không chỉ phụ thuộc scheduler.
8. **Kiểm thử ở đâu?** Unit test logic với local/mock; integration test JNDI và managed execution trên server thực.
9. **Quan sát thế nào?** Log run ID, planned/actual time, kết quả, duration, rejection và JVM/node.
10. **Rollback khi cấu hình lỗi?** Chuẩn bị deployment config/health check; không chuyển sang unmanaged threads âm thầm.

### Bảng quyết định nhanh

| Bối cảnh | Lựa chọn khởi đầu |
| --- | --- |
| Jakarta EE application server, có JSR-236/Jakarta managed scheduled executor | **`DefaultManagedTaskScheduler`** |
| Spring Boot standalone, không có JNDI managed resource | **`ThreadPoolTaskScheduler`** |
| Có `ScheduledExecutorService` do bên khác tạo và sở hữu | **`ConcurrentTaskScheduler`** |
| Chỉ cần submit/execute qua managed executor | **`DefaultManagedTaskExecutor`** |
| Cần lịch bền vững/cluster/misfire recovery | **Persistent scheduler/job store**, có thể dùng Quartz |
| Có nhiều scheduler trong một context | **Đặt bean name/qualifier và SchedulingConfigurer rõ ràng** |
| Có yêu cầu không tự tạo thread trong app server | **Tránh local pool, ưu tiên managed resource** |

## 21. Câu hỏi tự kiểm tra

1. `DefaultManagedTaskScheduler` kế thừa class nào, và Spring dùng nó để giải quyết vấn đề gì?
2. JNDI name mặc định của nó là gì? Khác gì `java:comp/DefaultManagedExecutorService`?
3. Khi nào `afterPropertiesSet()` lookup resource? Vì sao không gọi bằng tay trong một `@Bean` do Spring quản lý?
4. `@EnableScheduling` khác `@EnableAsync` ở chỗ nào?
5. Khi nào nên đặt bean tên `taskScheduler` hoặc dùng `SchedulingConfigurer`?
6. Vì sao Spring Boot dùng embedded Tomcat không nhất thiết có default Jakarta Concurrency resource?
7. Phân biệt fixed-rate, fixed-delay và cron trong một task chạy lâu hơn chu kỳ.
8. `Spring Trigger` và `jakarta.enterprise.concurrent.Trigger` có phải một interface không?
9. Những loại component context nào được Jakarta Concurrency default managed scheduled executor hỗ trợ?
10. Vì sao worker không tự thừa hưởng transaction của thread submit? Nếu job cần DB transaction, bạn tổ chức Spring service thế nào?
11. Ai sở hữu lifecycle của `ManagedScheduledExecutorService`? Ứng dụng có được gọi `shutdownNow()` không?
12. Vì sao `@Scheduled` chạy được chưa đủ chứng minh Spring đang dùng `DefaultManagedTaskScheduler`?
13. Một scheduled future có phải định danh job bền vững qua redeploy không?
14. Khi deploy ứng dụng ở ba node, managed scheduler có tự bảo đảm job chỉ chạy một lần toàn cụm không?
15. Vì sao cần test JNDI resource trong Jakarta EE server thật thay vì chỉ mock scheduler trong local?
16. Một transaction tài chính cần chạy đúng một lần và không mất khi restart có nên dùng riêng DefaultManagedTaskScheduler không?
17. Nếu `schedule` bị từ chối khi server quá tải, hệ thống phải có những bước báo lỗi/ghi nhận nào?
18. Vì sao không nên tự fallback sang `Executors.newScheduledThreadPool` trên Jakarta EE khi lookup JNDI lỗi?

## 22. Tài liệu chính thức

- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — DefaultManagedTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/DefaultManagedTaskScheduler.html)
- [Spring Framework 6.2 — ConcurrentTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ConcurrentTaskScheduler.html)
- [Spring Framework — @EnableScheduling Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/EnableScheduling.html)
- [Spring Framework — TaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
- [Spring Framework — SchedulingConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/SchedulingConfigurer.html)
- [Jakarta Concurrency Specification 3.1](https://jakarta.ee/specifications/concurrency/3.1/jakarta-concurrency-spec-3.1)
- [Jakarta EE — Concurrency Explained](https://jakarta.ee/learn/specification-guides/concurrency-explained/)
- [Java SE 17 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)
- [Java SE 17 — ScheduledFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html)

**Ghi nhớ:** `DefaultManagedTaskScheduler` là **Spring TaskScheduler adapter dựa trên JNDI**, mặc định tra `java:comp/DefaultManagedScheduledExecutorService` của Jakarta EE. Chọn nó khi application server **sở hữu thread và lifecycle**; để `@Scheduled` dùng nó, phải cấu hình đúng Spring bean và `@EnableScheduling`. Không gọi shutdown trên managed executor, không giả định transaction tự truyền, và không nhầm scheduled tasks trong RAM với một **persistent/clustered job scheduler**. Khi chạy standalone không có JNDI, chọn local scheduler có quản trị rõ ràng thay vì giả định môi trường Jakarta EE.