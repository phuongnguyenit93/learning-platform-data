# Mối liên hệ giữa TaskExecutor, @Async, TaskScheduler và @Scheduled trong Spring Framework

## 1. Bức tranh tổng thể: thực thi tác vụ và quyết định thời điểm chạy

Spring Framework cung cấp hai nhóm khả năng thường được dùng cùng nhau nhưng giải quyết **hai câu hỏi khác nhau**:

- **Thực thi (execution):** một công việc đã được yêu cầu chạy thì chạy ở đâu, bằng luồng nào, có hàng đợi và bao nhiêu công việc được xử lý đồng thời? Đây là vai trò của **TaskExecutor**; **@Async** là cách khai báo để Spring gửi lời gọi phương thức sang executor.
- **Lập lịch (scheduling):** khi nào một công việc cần được kích hoạt: một lần trong tương lai, sau mỗi khoảng nghỉ, theo nhịp đều đặn hay theo lịch cron? Đây là vai trò của **TaskScheduler**; **@Scheduled** khai báo lịch kích hoạt một phương thức.

Hai nhóm này **độc lập**: ứng dụng chỉ cần xử lý bất đồng bộ có thể dùng @Async mà không bật @Scheduled; ứng dụng chỉ cần công việc định kỳ có thể dùng @Scheduled mà không bật @Async. Chúng kết hợp khi muốn *đến giờ thì kích hoạt một công việc, rồi giao phần xử lý nặng cho một executor khác*.

| Thành phần | Bản chất | Chức năng chính | Khi nào hoạt động? |
| --- | --- | --- | --- |
| **TaskExecutor** | Interface, mở rộng java.util.concurrent.Executor | Nhận Runnable và thực thi theo chính sách của executor | Khi có mã gửi task bằng execute hoặc Spring gửi lời gọi @Async |
| **@Async** | Annotation trên phương thức/kiểu | Đánh dấu lời gọi qua Spring proxy để đưa phần thân phương thức sang executor | Khi một đối tượng khác gọi phương thức qua Spring proxy |
| **TaskScheduler** | Interface | Đăng ký Runnable để chạy một lần hoặc lặp theo thời gian/Trigger | Khi mã đăng ký task hoặc Spring đăng ký @Scheduled |
| **@Scheduled** | Annotation trên phương thức | Khai báo fixedDelay, fixedRate, cron, initialDelay | Spring đăng ký lịch khi bean được khởi tạo; scheduler tự kích hoạt sau đó |

Hình dung hai luồng điều khiển:

~~~text
Người gọi HTTP/event/service
    └── gọi bean.method() qua Spring proxy
            └── @Async ──> TaskExecutor ──> worker thread ──> phương thức

Đồng hồ / lịch kích hoạt
    └── TaskScheduler ──> @Scheduled method trên bean
                               ├── xử lý trực tiếp trên scheduler thread
                               └── gọi bean khác qua proxy @Async
                                        └── TaskExecutor ──> worker thread
~~~

**Điểm mấu chốt:** @Async không tự tạo lịch; @Scheduled không mặc nhiên chuyển toàn bộ công việc sang pool @Async. Việc kích hoạt theo lịch và nơi thực thi công việc là hai quyết định riêng.

## 2. TaskExecutor và @Async liên quan với nhau thế nào?

**TaskExecutor** nhận tác vụ dạng Runnable qua phương thức execute(Runnable). Spring cung cấp nhiều triển khai; tên "executor" không bảo đảm rằng có thread pool: ví dụ SyncTaskExecutor chạy ngay trên luồng gọi, SimpleAsyncTaskExecutor tạo thread cho mỗi task (có thể được cấu hình dùng virtual threads trên JDK phù hợp), còn ThreadPoolTaskExecutor quản lý thread pool và queue.

Cách gọi trực tiếp:

~~~java
// Ví dụ phương thức nằm bên trong một Spring bean đã inject TaskExecutor.
public void submit(TaskExecutor executor) {
    executor.execute(() ->
            System.out.println(Thread.currentThread().getName()));
}
~~~

Với **@Async**, lập trình viên không tự bọc Runnable. Spring dùng cơ chế AOP/proxy (mặc định) để chặn lời gọi hợp lệ, gửi việc sang executor, rồi trả quyền điều khiển cho caller mà không chờ phần thân phương thức chạy xong. Điều này không có nghĩa mọi phương thức gắn @Async đều chạy nền: điều kiện kích hoạt proxy rất quan trọng.

Để bật annotation trong cấu hình Spring, dùng **@EnableAsync**. Phương thức @Async thường khai báo trả về **void**, **Future<T>** hoặc **CompletableFuture<T>**. Phương thức void phù hợp cho fire-and-forget có cơ chế xử lý lỗi riêng; CompletableFuture cho phép caller nhận kết quả, ghép bước hoặc xử lý thất bại mà không block. Tránh gọi get()/join() ngay lập tức nếu mục tiêu là không chặn luồng gọi.

Ví dụ ngắn về tách bean:

~~~java
@Service
class EmailWorker {
    @Async("appTaskExecutor")
    public CompletableFuture<String> send(String address) {
        // Thân phương thức chạy trên executor được chỉ định.
        return CompletableFuture.completedFuture("sent to " + address);
    }
}

@Service
class CheckoutService {
    private final EmailWorker worker;

    CheckoutService(EmailWorker worker) {
        this.worker = worker;
    }

    public CompletableFuture<String> checkout(String address) {
        // Gọi qua bean khác để proxy của Spring chặn được.
        return worker.send(address);
    }
}
~~~

Đoạn trên chỉ minh họa quan hệ giữa các bean; các import, cấu hình executor và ứng dụng chạy độc lập có ở ví dụ hoàn chỉnh bên dưới.

**Bẫy self-invocation:** nếu cùng một object gọi this.send() hoặc chỉ gọi send() nội bộ, lời gọi không đi qua proxy nên @Async có thể không phát huy tác dụng. Trong chế độ proxy mặc định, tránh đặt công việc async ở phương thức private/final không thể được proxy chặn đúng cách; ưu tiên phương thức public trên Spring bean được gọi từ bean khác. @Async không nên dùng như cách khởi tạo async trực tiếp trên phương thức @PostConstruct.

## 3. TaskScheduler và @Scheduled liên quan với nhau thế nào?

**TaskScheduler** biểu diễn năng lực lên lịch. Nó có các API như schedule(Runnable, Instant), schedule(Runnable, Trigger), scheduleAtFixedRate(Runnable, Duration), scheduleWithFixedDelay(Runnable, Duration). Các phương thức trả về ScheduledFuture trong những trường hợp thích hợp, cho phép hủy lịch bằng cancel(...).

**@Scheduled** là lớp khai báo phía trên chức năng ấy: Spring tìm những phương thức có annotation trên bean, đăng ký các lần kích hoạt với scheduler; bạn không cần tự gọi scheduler.schedule(...) cho từng phương thức. Bật tính năng này bằng **@EnableScheduling**.

Ví dụ khai báo:

~~~java
@Scheduled(initialDelay = 1000, fixedDelay = 5000)
public void refreshCache() {
    // Kích hoạt lần đầu sau khoảng 1 giây;
    // mỗi lần tiếp theo chờ 5 giây kể từ khi lần trước kết thúc.
}

@Scheduled(fixedRate = 5000)
public void updateHeartbeat() {
    // Nhịp dự kiến là 5 giây giữa các thời điểm bắt đầu.
}

@Scheduled(cron = "0 0 9 * * MON-FRI", zone = "Asia/Ho_Chi_Minh")
public void weekdayReport() {
    // 09:00 sáng thứ Hai đến thứ Sáu theo múi giờ đã chọn.
}
~~~

Mặc định các giá trị số trong ví dụ trên tính bằng **mili giây**; có thể dùng thuộc tính timeUnit của @Scheduled. Cron của Spring thông thường có **sáu trường** gồm giây, phút, giờ, ngày trong tháng, tháng, thứ trong tuần; không tự lấy cron năm trường của hệ Unix rồi áp dụng y nguyên. Với phương thức @Scheduled kiểu Java đồng bộ thông thường, khai báo **không tham số và trả về void**; kết quả trả về thông thường không được dùng. Spring Framework 6.1+ còn hỗ trợ riêng một số kiểu Publisher/reactive và Kotlin suspend với các quy tắc khác, không nên suy diễn từ ví dụ Java đồng bộ.

Phân biệt ba cách lập lịch:

| Cấu hình | Khoảng thời gian đo từ đâu? | Điều cần nhớ |
| --- | --- | --- |
| **fixedDelay** | Sau khi một lần *gọi phương thức được lập lịch* kết thúc mới chờ thêm khoảng delay | Phù hợp khi muốn có khoảng nghỉ giữa các lần chạy; nếu phương thức chỉ gửi async task rồi return, nó không chờ async task hoàn thành |
| **fixedRate** | Nhắm tới chu kỳ tính theo thời điểm bắt đầu đã lên lịch | Tác vụ có thể bị trễ vì scheduler bận; không suy ra mọi lần của một registration chắc chắn chạy chồng nhau |
| **cron** | Những thời điểm lịch khớp biểu thức, có thể gắn zone | Dùng cho lịch theo giờ/ngày; cân nhắc múi giờ và thay đổi giờ mùa hè ở các zone có DST |

Spring có **ThreadPoolTaskScheduler**, thường thực thi callback ngay trên các scheduler threads mà nó quản lý. Vì vậy một callback @Scheduled chạy lâu có thể chiếm chỗ và làm những lịch khác trễ nếu scheduler quá nhỏ. Spring 6.1 có **SimpleAsyncTaskScheduler** với cách thực thi khác (đặc biệt fixedDelay vẫn thực thi trên một scheduler thread); đừng đồng nhất mọi TaskScheduler với cùng một mô hình thread.

Nếu không chỉ định scheduler rõ ràng, Spring có cơ chế tìm scheduler phù hợp hoặc tạo fallback cục bộ; trong Spring Boot còn có auto-configuration phụ thuộc các bean và thuộc tính của ứng dụng. Vì vậy **không nên giả định scheduler và async executor là cùng một pool**. Khi có nhiều lựa chọn, khai báo bean hoặc chỉ định cấu hình minh bạch sẽ dễ kiểm soát hơn.

## 4. Ví dụ chạy được: lịch kích hoạt, executor xử lý

Bộ ví dụ này dùng **Java 17+ và Spring Boot 3.3.x (Spring Framework 6.1)**. Tạo project Gradle với cấu trúc:

~~~text
schedule-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/concurrency/
    ├── DemoApplication.java
    ├── TaskConfiguration.java
    ├── ReportWorker.java
    └── ReportSchedule.java
~~~

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'schedule-demo'
~~~

Tệp **build.gradle** (phiên bản là ví dụ ổn định, không hàm ý là bản mới nhất):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

**DemoApplication.java**:

~~~java
package demo.concurrency;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**TaskConfiguration.java** tạo **hai pool riêng biệt**. Tên appTaskExecutor được @Async chọn tường minh; tên taskScheduler cho Spring nhận diện scheduler của các phương thức @Scheduled.

~~~java
package demo.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
public class TaskConfiguration {
    @Bean(name = "appTaskExecutor")
    public ThreadPoolTaskExecutor appTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("async-");
        return executor;
    }

    @Bean(name = "taskScheduler")
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("schedule-");
        return scheduler;
    }
}
~~~

**ReportWorker.java** chạy việc nặng trên executor; CompletableFuture ghi nhận thành công hoặc thất bại. Giữ lại cờ ngắt khi sleep bị interrupt.

~~~java
package demo.concurrency;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {
    @Async("appTaskExecutor")
    public CompletableFuture<String> buildReport(int sequence) {
        System.out.printf("WORK start #%d thread=%s%n",
                sequence, Thread.currentThread().getName());

        try {
            TimeUnit.SECONDS.sleep(2);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(ex);
        }

        System.out.printf("WORK end   #%d thread=%s%n",
                sequence, Thread.currentThread().getName());
        return CompletableFuture.completedFuture("report-" + sequence);
    }
}
~~~

**ReportSchedule.java** chỉ nhận nhịp lịch và ủy quyền qua **bean khác** để Spring proxy xử lý @Async; không đợi công việc kéo dài hai giây.

~~~java
package demo.concurrency;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ReportSchedule {
    private final AtomicInteger counter = new AtomicInteger();
    private final ReportWorker worker;

    public ReportSchedule(ReportWorker worker) {
        this.worker = worker;
    }

    @Scheduled(initialDelay = 1000, fixedDelay = 4000)
    public void onTick() {
        int sequence = counter.incrementAndGet();

        System.out.printf("TICK       #%d thread=%s%n",
                sequence, Thread.currentThread().getName());

        worker.buildReport(sequence).whenComplete((result, error) -> {
            if (error != null) {
                System.err.printf("FAIL       #%d cause=%s%n",
                        sequence, error);
            } else {
                System.out.printf("DONE       #%d result=%s%n",
                        sequence, result);
            }
        });
    }
}
~~~

Dùng **Gradle 8.5+ và JDK 17+** cài trên máy; chạy tại thư mục schedule-demo:

~~~bash
gradle bootRun
~~~

Nếu dự án có Gradle Wrapper, dùng **./gradlew bootRun** trên Linux/macOS hoặc **gradlew.bat bootRun** trên Windows. Dừng bằng Ctrl+C để đóng application context.

Một lần chạy *có thể* in ra các dòng sau (đã bỏ log khởi động):

~~~text
TICK       #1 thread=schedule-1
WORK start #1 thread=async-1
WORK end   #1 thread=async-1
DONE       #1 result=report-1
TICK       #2 thread=schedule-1
WORK start #2 thread=async-2
WORK end   #2 thread=async-2
DONE       #2 result=report-2
~~~

Tên/số thứ tự thread thực tế, thời điểm và thứ tự các dòng phụ thuộc runtime; **không coi transcript trên là stdout duy nhất hoặc bất biến**. Điều cần quan sát là dòng TICK chạy trên **schedule-**, WORK chạy trên **async-**, còn lần kích hoạt tiếp theo không bị buộc phải chờ worker của lần trước.

### Vì sao ví dụ cần cả hai bean?

1. **taskScheduler** quản lý các lần kích hoạt onTick() theo fixedDelay. Nó không nhận trách nhiệm chạy toàn bộ report nặng.
2. **ReportSchedule** chạy ngắn, giao task rồi return. Vì thế khoảng fixedDelay bốn giây đo từ lúc onTick() kết thúc, không đo từ lúc ReportWorker hoàn tất.
3. **@Async("appTaskExecutor")** là nơi lời gọi buildReport() được chuyển sang executor pool. Annotation sẽ không có tác dụng như kỳ vọng nếu thay worker.buildReport(...) bằng một lời gọi nội bộ trên cùng object.
4. **appTaskExecutor** điều khiển lượng worker có thể thực thi/đang chờ. Nếu thời gian report lớn hơn chu kỳ kích hoạt và tốc độ đến vượt tốc độ xử lý, queue có thể tích tụ rồi dẫn đến từ chối task.
5. **whenComplete** quan sát lỗi hoặc giá trị của CompletableFuture. Callback có thể chạy trên thread hoàn thành future hoặc thread gắn callback, tùy thời điểm; không nên mặc định đó là scheduler thread hay một pool riêng.

Với cấu hình executor trên, corePoolSize=2, maxPoolSize=4 và queueCapacity=20. ThreadPoolExecutor thường ưu tiên tạo đến core pool, sau đó đưa task vào queue, rồi mới tăng trên core khi queue đầy; **maxPoolSize=4 không có nghĩa bốn worker luôn chạy ngay từ đầu**. Đặt queue quá lớn có thể gây độ trễ và sử dụng bộ nhớ tăng.

## 5. Các tổ hợp đúng và cách chọn thiết kế

| Nhu cầu | Dùng gì? | Giải thích |
| --- | --- | --- |
| Xử lý theo lời gọi người dùng mà không chặn caller | **@Async** + TaskExecutor | Caller chủ động tạo yêu cầu; executor quyết định thực thi |
| Gửi một Runnable thủ công sang pool | **TaskExecutor.execute(...)** | Không cần annotation nếu muốn gửi task trực tiếp |
| Chạy dọn dẹp định kỳ, nhanh, không block | **@Scheduled** + TaskScheduler | Scheduler tự đánh thức phương thức theo lịch |
| Chạy job định kỳ nhưng phần việc nặng nên tách pool | **@Scheduled** trong bean A gọi **@Async** trong bean B | Phân tách chính sách thời gian với năng lực xử lý |
| Tự đăng ký lịch linh hoạt và cần hủy | **TaskScheduler.schedule(...)**, giữ ScheduledFuture | Phù hợp khi lịch được tạo/hủy theo yêu cầu runtime |

Một ứng dụng cũng có thể dùng TaskScheduler trực tiếp mà không viết @Scheduled:

~~~java
// Trích đoạn nằm trong một Spring bean đã inject TaskScheduler.
ScheduledFuture<?> handle = taskScheduler.scheduleAtFixedRate(
        () -> System.out.println("heartbeat"),
        java.time.Duration.ofSeconds(5)
);

// Khi không cần chạy nữa:
handle.cancel(false);
~~~

Ở mức triển khai, TaskScheduler có thể dựa trên ScheduledExecutorService, còn TaskExecutor có thể dùng ThreadPoolExecutor. Dù cùng họ java.util.concurrent, API của Spring vẫn đại diện hai vai trò riêng. Việc một scheduler có thể thực thi Runnable không làm nó tự động trở thành executor cho mọi @Async.

### Có nên đặt @Scheduled và @Async trên cùng một phương thức?

Có những cấu hình có thể khiến chúng phối hợp, nhưng **khó dự đoán giới hạn chồng lấp và vòng đời** hơn: lúc phương thức được gọi theo lịch, lời gọi async có thể trả về trước khi công việc kết thúc; fixedDelay vì vậy không còn đại diện cho khoảng nghỉ giữa hai lần làm việc thực tế. Với một bài toán cần vận hành rõ ràng, nên tách **bean kích hoạt ngắn** (@Scheduled) và **bean xử lý nền** (@Async), như ví dụ phía trên.

Nếu yêu cầu là "chỉ được chạy một lần tại một thời điểm", riêng @Scheduled + @Async không đáp ứng cam kết đó. Phải có cơ chế không cho chạy chồng (khóa, semaphore, trạng thái job, queue giới hạn hoặc giải pháp orchestration phù hợp). Trong hệ nhiều instance, mỗi instance có thể tự đăng ký lịch giống nhau; @Scheduled tự nó không cung cấp điều phối **chạy duy nhất trên cả cluster**.

## 6. Lỗi và các ràng buộc quan trọng

**Không thấy @Async hoạt động:** kiểm tra @EnableAsync, bean có do Spring quản lý hay không, lời gọi có đi qua proxy hay không, method có phù hợp để proxy intercept hay không, executor có tồn tại theo qualifier. In Thread.currentThread().getName() ở cả caller và worker là cách chẩn đoán nhanh.

**Không thấy @Scheduled kích hoạt:** kiểm tra @EnableScheduling, bean có được tạo trong ApplicationContext, thuộc tính cron/fixedDelay có hợp lệ, scheduler có bị nghẽn hay không. Một phương thức bình thường gắn @Scheduled vẫn có thể bị gọi trực tiếp bằng Java; đó là lời gọi thường, không phải một lần kích hoạt do lịch tạo ra.

**Nhầm fixedDelay với thời gian hoàn thành công việc async:** nếu method @Scheduled gọi async rồi trả ngay, lần kích hoạt sau đo từ thời gian method ngắn đó hoàn tất. Muốn delay kể từ khi toàn bộ xử lý hoàn thành, hãy thiết kế callback được lập lịch để đợi/điều phối việc hoàn thành một cách chủ đích; cân nhắc tác động lên scheduler thread, timeout và throughput. Không sửa bằng cách thêm Thread.sleep() mù quáng.

**Bão task hoặc tài nguyên cạn:** tăng scheduler pool chỉ giúp đẩy nhiều callback, không giải quyết worker pool chậm; tăng worker pool vô hạn cũng không tạo thêm tài nguyên hệ thống. Cần đo thời gian xử lý, backlog, task rejected, CPU/I/O, giới hạn hàng đợi và dùng backpressure/chính sách bỏ hoặc gộp việc khi phù hợp.

**Lỗi bị mất dấu:** với @Async trả void, ngoại lệ không thể tự chuyển về caller giống lời gọi đồng bộ; cấu hình AsyncUncaughtExceptionHandler hoặc ghi log/giám sát phù hợp. Với Future/CompletableFuture, xử lý complete exceptionally, whenComplete, exceptionally hoặc get() ở ranh giới có chủ đích. Với @Scheduled đồng bộ, lỗi thuộc luồng scheduler và cơ chế ErrorHandler tương ứng; đừng coi hành vi xử lý lỗi của hai annotation là giống nhau.

**Ngữ cảnh thread không tự truyền:** transaction, ThreadLocal, MDC logging, SecurityContext hoặc request context không chắc có mặt trên async worker. Đặc biệt, @Transactional trên caller không có nghĩa worker dùng cùng transaction/connection. Nếu cần, truyền dữ liệu rõ ràng, bắt đầu transaction ở ranh giới worker, hoặc cấu hình TaskDecorator/cơ chế truyền context có kiểm soát. Không chia sẻ EntityManager hay đối tượng không thread-safe giữa các task.

**Tắt ứng dụng:** khi shutdown, xem xét chính sách chờ task hoàn thành, hủy scheduled trigger và xử lý interrupt. Không giả định chương trình dừng ngay hoặc sẽ luôn hoàn tất mọi công việc đang đợi; điều đó phụ thuộc cấu hình executor/scheduler và vòng đời Spring.

**Nhiều lịch trên một phương thức:** @Scheduled có thể lặp lại; mỗi declaration có trigger riêng và có thể tạo các lần chạy gần nhau/chồng lấp. Không trông cậy một pool nhỏ như một cơ chế khóa nghiệp vụ.

## 7. Câu hỏi tự kiểm tra

1. Một REST endpoint gọi phương thức @Async nhưng code gọi bằng this.method(): vì sao thread vẫn là HTTP request thread? **Vì lời gọi nội bộ bỏ qua proxy trong mode mặc định.**
2. @Scheduled(fixedDelay = 5000) gọi @Async rồi return sau 10 ms, worker mất 30 giây: lần kích hoạt kế tiếp có cần chờ worker xong không? **Không; fixedDelay gắn với lời gọi được lập lịch kết thúc, không tự quan sát completion của future.**
3. Có @EnableScheduling mà không có @EnableAsync, phương thức @Scheduled gọi một phương thức @Async khác: điều gì chắc chắn? **Lịch vẫn được kích hoạt, nhưng @Async chưa được bật thông qua annotation configuration này nên không thể mặc nhiên coi việc gọi đó là bất đồng bộ.**
4. Tạo ThreadPoolTaskExecutor với 2 core threads, 4 max threads và queue 20: khi tới task thứ ba, có luôn tạo thread thứ ba không? **Không; thường task được xếp vào queue trước khi tăng quá core size.**
5. Deploy ba bản sao ứng dụng cùng có @Scheduled cron 09:00: sẽ có bao nhiêu lần gọi? **Thông thường mỗi instance tự kích hoạt một lần; cần phối hợp bên ngoài nếu nghiệp vụ yêu cầu đúng một lần toàn hệ thống.**

## 8. Ghi nhớ và tài liệu gốc

- **TaskExecutor / @Async** trả lời "chạy công việc bằng tài nguyên nào và làm sao không giữ caller chờ".
- **TaskScheduler / @Scheduled** trả lời "khi nào Spring kích hoạt công việc".
- Hai nhóm chỉ phối hợp khi ta thiết kế chúng phối hợp; nếu một lần lịch có thể tạo nhiều việc nền, phải kiểm soát queue, lỗi, chồng lấp, context và shutdown.
- Bắt đầu bằng cách xác định mục tiêu: tác vụ theo sự kiện, tác vụ định kỳ, hay cả hai; sau đó chọn pool và chính sách giám sát riêng cho từng vai trò.

Tài liệu chính thức: [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html). Các chi tiết về mặc định executor/scheduler có thể khác theo phiên bản Spring Framework, Spring Boot và cấu hình ứng dụng; ví dụ trên chỉ định rõ hai bean để tránh phụ thuộc các mặc định đó.
