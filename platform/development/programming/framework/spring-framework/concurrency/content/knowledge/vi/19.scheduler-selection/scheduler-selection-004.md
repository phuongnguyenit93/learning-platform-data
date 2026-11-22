# ConcurrentTaskScheduler thích nghi bộ lập lịch JDK

## 1. Vấn đề: đã có scheduler JDK, muốn dùng giao diện Spring

Trong Java, `ScheduledExecutorService` là API chuẩn để lên lịch thực thi `Runnable` hoặc `Callable` sau một khoảng trễ, theo **fixed rate** hoặc **fixed delay**. Trong Spring Framework, `TaskScheduler` là abstraction phục vụ cùng mục đích nhưng có thêm các phương thức gắn với `Instant`, `Duration`, `Trigger` và cách phối hợp với cấu hình Spring.

Nếu ứng dụng **đã có một `ScheduledExecutorService` do JDK hoặc môi trường khác cung cấp**, bạn không nhất thiết phải viết lại scheduler. **`ConcurrentTaskScheduler`** là adapter nhận `java.util.concurrent.ScheduledExecutorService`, rồi **cung cấp giao diện `org.springframework.scheduling.TaskScheduler`** cho các Spring component.

~~~text
Ứng dụng Spring
       |
       |  TaskScheduler.schedule(task, Instant)
       |  TaskScheduler.schedule(task, Trigger)
       |  TaskScheduler.scheduleAtFixedRate(task, Duration)
       v
+------------------------------+
| ConcurrentTaskScheduler      |  <- adapter Spring
| - dịch lịch về JDK scheduling |
| - hỗ trợ Spring Trigger      |
| - xử lý lỗi task             |
+---------------+--------------+
                |
                | delegate
                v
+------------------------------+
| ScheduledExecutorService     |  <- tài nguyên thực thi JDK
| thường là ScheduledThreadPool|
| Executor                     |
+---------------+--------------+
                |
                v
             worker threads
~~~

**Điểm phải nhớ:** adapter không biến `ScheduledExecutorService` thành một scheduler bền vững hay tự tạo transaction. Số worker, thread factory, chính sách shutdown, khả năng nhận task và năng lực chịu tải **vẫn phụ thuộc executor phía dưới**. Cách cấu hình lifecycle phải thể hiện rõ thành phần nào sở hữu executor.

Bài nằm trong nhóm **Chọn scheduler** của **Spring Framework – concurrency**. Trọng tâm là cách `ConcurrentTaskScheduler` thích nghi JDK, API sử dụng, trigger scheduling, vòng đời, so sánh với `ThreadPoolTaskScheduler` và ví dụ Java 17 + Spring có thể chạy.

## 2. Hai giao diện: ScheduledExecutorService và TaskScheduler

### 2.1. JDK ScheduledExecutorService

`ScheduledExecutorService` kế thừa `ExecutorService`. Các API thường dùng:

~~~java
ScheduledFuture<?> oneTime =
        scheduledExecutor.schedule(task, 2, TimeUnit.SECONDS);

ScheduledFuture<?> fixedRate =
        scheduledExecutor.scheduleAtFixedRate(
                task, 1, 5, TimeUnit.SECONDS);

ScheduledFuture<?> fixedDelay =
        scheduledExecutor.scheduleWithFixedDelay(
                task, 1, 5, TimeUnit.SECONDS);
~~~

Đây là **mảnh code minh họa**, cần `scheduledExecutor`, `task` và các import `java.util.concurrent`. Các đối số thời gian trong JDK trên là **relative delay** theo đơn vị thời gian.

- `schedule`: chạy **một lần** sau khoảng trễ được yêu cầu.
- `scheduleAtFixedRate`: lặp theo lịch dựa trên thời điểm bắt đầu được dự kiến và period.
- `scheduleWithFixedDelay`: lặp với khoảng chờ giữa **lần chạy trước hoàn tất** và **lần chạy tiếp theo bắt đầu**.
- `ScheduledFuture`: có thể theo dõi kết thúc/hủy. Với periodic tasks thông thường nó không tự hoàn thành thành công như một one-shot future; cần hủy khi không còn cần chạy.

Với một periodic task duy nhất được lịch JDK lập qua `scheduleAtFixedRate` hoặc `scheduleWithFixedDelay`, các lần chạy **không chồng lấp chính chúng** theo contract của `ScheduledThreadPoolExecutor`; nếu một lần chạy quá lâu thì các lần sau có thể trễ. **Các task khác nhau** vẫn có thể chạy song song nếu pool có đủ thread.

### 2.2. Spring TaskScheduler

Giao diện `TaskScheduler` (Spring Framework 6.1) chủ yếu có:

~~~java
Clock getClock();

ScheduledFuture<?> schedule(Runnable task, Instant startTime);

ScheduledFuture<?> schedule(Runnable task, Trigger trigger);

ScheduledFuture<?> scheduleAtFixedRate(Runnable task, Duration period);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Instant startTime, Duration period);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Duration delay);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Instant startTime, Duration delay);
~~~

Đây là **trích dạng chữ ký minh họa**, không phải một class Java đầy đủ. Khác JDK, Spring nhận `Instant` (mốc thời gian tuyệt đối), `Duration` (khoảng thời gian) và `Trigger` (tự tính lần chạy tiếp theo theo ngữ cảnh lịch).

Hai abstraction tách **ý định lên lịch** khỏi **cách cấp thread và thực thi**. Code nghiệp vụ có thể phụ thuộc vào `TaskScheduler` và dùng một backend JDK khi chạy đơn giản, backend do container quản lý trong Jakarta EE, hoặc backend Spring cấu hình theo bean.

### 2.3. Bảng đối chiếu

| Nhu cầu | JDK ScheduledExecutorService | Spring TaskScheduler |
| --- | --- | --- |
| Chạy một lần sau khoảng trễ | `schedule(command, delay, unit)` | `schedule(command, Instant)` |
| Fixed rate | `scheduleAtFixedRate(command, initialDelay, period, unit)` | `scheduleAtFixedRate(command, Duration)` hoặc có `Instant` |
| Fixed delay | `scheduleWithFixedDelay(command, initialDelay, delay, unit)` | `scheduleWithFixedDelay(command, Duration)` hoặc có `Instant` |
| Lịch dựa trên Cron | Không có Cron API chung trực tiếp | `schedule(task, new CronTrigger(...))` |
| Lịch tùy biến theo lần chạy trước | Phải tự lập logic/điều phối | `schedule(task, Trigger)` |
| Hủy lịch | `ScheduledFuture.cancel(...)` | `ScheduledFuture.cancel(...)` |
| Thread pool và vòng đời | Cấu hình/quản lý executor cụ thể | Phụ thuộc implementation hoặc tài nguyên delegate |

`ConcurrentTaskScheduler` làm cầu nối để code Spring dùng cột bên phải, trong khi backend là một đối tượng JDK ở cột trái.

## 3. ConcurrentTaskScheduler thực sự làm gì?

`org.springframework.scheduling.concurrent.ConcurrentTaskScheduler` kế thừa `ConcurrentTaskExecutor` và implement `TaskScheduler`. Vì vậy nó có khả năng hoạt động như một `TaskExecutor`/`SchedulingTaskExecutor` cho task thông thường, đồng thời cung cấp API lên lịch.

Trên nhánh **TaskScheduler**, nó chuyển các lời gọi đến `ScheduledExecutorService` được cấu hình. Với các lịch theo `Trigger`, khi backend là scheduler JDK thông thường, Spring sử dụng logic tính lần chạy tiếp theo và **lên lịch lại** (rescheduling) trên JDK executor theo từng lần chạy.

~~~text
taskScheduler.schedule(task, springTrigger)
                   |
                   v
             Trigger.nextExecution(context)
                   |
                   v
        tính thời điểm chạy tiếp theo
                   |
                   v
        ScheduledExecutorService.schedule(...)
                   |
                   v
             Runnable hoàn tất
                   |
                   v
         cập nhật TriggerContext
                   |
                   +----> tính/lên lịch lần kế tiếp
~~~

**Lưu ý:** với `ManagedScheduledExecutorService` theo **JSR-236/Jakarta Concurrency** trong môi trường phù hợp, `ConcurrentTaskScheduler` có cơ chế nhận diện và có thể dùng kiểu scheduling theo Trigger do môi trường quản lý thay vì nhánh rescheduling cục bộ. Nếu bạn chạy JDK thuần như ví dụ trong bài, hãy hiểu nó dùng backend `ScheduledExecutorService` thông thường.

Adapter còn có tùy chọn `setErrorHandler(...)` cho lỗi của task và `setClock(...)` để xác định Clock dùng trong tính toán lịch. Nó **không phải** persistence layer, distributed scheduler hay cơ chế đảm bảo chạy đúng giờ tuyệt đối trong điều kiện hệ thống bão hòa.

### 3.1. Ba constructor và phiên bản Spring

Trong dòng Spring Framework 6.1 có các cách khởi tạo đáng chú ý:

~~~java
// Ưu tiên khi một JDK scheduler phục vụ cả hai vai trò.
ConcurrentTaskScheduler scheduler =
        new ConcurrentTaskScheduler(jdkScheduledExecutor);

// Nếu muốn executor chạy task thường và scheduler khác nhau:
ConcurrentTaskScheduler separated =
        new ConcurrentTaskScheduler(
                generalExecutor, jdkScheduledExecutor);
~~~

Đây là **mảnh code minh họa**; cần khai báo `generalExecutor` kiểu `Executor` và `jdkScheduledExecutor` kiểu `ScheduledExecutorService`.

Constructor thứ nhất dùng **cùng một ScheduledExecutorService** làm delegate cho việc scheduling và, theo API constructor, các lời gọi task execution thông thường. Constructor thứ hai nhận **hai delegate** riêng: `Executor` cho các lời gọi `SchedulingTaskExecutor`, `ScheduledExecutorService` cho các phương thức `TaskScheduler`.

Constructor **không tham số** tồn tại trong Spring 6.1 nhưng đã được **đánh dấu deprecated**; trong code mới, nên cung cấp backend rõ ràng qua constructor thay vì dựa vào scheduler mặc định ngầm.

Có phương thức `setScheduledExecutor(ScheduledExecutorService)`, nhưng chú ý nó **chỉ thay delegate của nhánh scheduling**. Nếu muốn `execute`/`submit` của `ConcurrentTaskExecutor` đi vào một executor khác/giống backend mới, phải cấu hình nhánh concurrent executor tương ứng (ví dụ `setConcurrentExecutor(...)`) hoặc dùng constructor hai tham số.

### 3.2. Không nhầm adapter với ThreadPoolTaskScheduler

`ThreadPoolTaskScheduler` là một implementation Spring thường tiện hơn khi ứng dụng **muốn Spring cấu hình và quản lý pool** bằng các thuộc tính kiểu bean như pool size, thread name prefix, shutdown policies và lifecycle integration. `ConcurrentTaskScheduler` phù hợp khi **đã có `ScheduledExecutorService`** hoặc cần thích nghi một implementation JDK được tạo theo chính sách riêng.

Nếu chỉ cần một scheduler pool do Spring quản lý và không có backend JDK sẵn, `ThreadPoolTaskScheduler` thường ít cấu hình hơn. Chọn adapter để dùng tài nguyên bên dưới đã có, không phải vì tên "Concurrent" sẽ tự tạo thêm parallelism so với pool đã cấp.

## 4. Cấu hình Spring bean với JDK ScheduledExecutorService

### 4.1. Tạo backend trước, sau đó bọc bằng adapter

~~~java
@Configuration(proxyBeanMethods = false)
public class SchedulingConfig {

    @Bean(destroyMethod = "shutdown")
    public ScheduledExecutorService jdkScheduledExecutor() {
        return Executors.newScheduledThreadPool(2);
    }

    @Bean("taskScheduler")
    public TaskScheduler taskScheduler(
            ScheduledExecutorService jdkScheduledExecutor) {
        return new ConcurrentTaskScheduler(jdkScheduledExecutor);
    }
}
~~~

Đây là **mảnh cấu hình**; cần import `Configuration`, `Bean`, `TaskScheduler`, `ConcurrentTaskScheduler`, `Executors` và `ScheduledExecutorService`. Nó thể hiện rõ **ai quản lý tài nguyên**: backend JDK là Spring bean; lệnh `destroyMethod = "shutdown"` yêu cầu Spring shutdown nó khi context đóng.

Khi dùng JDK executor đã có sẵn trong ứng dụng, hãy đăng ký/wire instance đó vào bean adapter, không cần tạo pool thứ hai. Nếu executor được quản lý bởi **application server**, việc gọi `shutdown()` từ một ứng dụng con thường **không đúng quyền sở hữu**. Phải để container sở hữu lifecycle.

**Không dùng `new ConcurrentTaskScheduler()` rồi bỏ qua chuyện shutdown một executor ngầm**. Trong Spring 6.1 constructor không tham số đã deprecated; explicit dependency và owner rõ ràng giúp giảm thread leaks.

### 4.2. Nếu có nhiều ScheduledExecutorService bean

Constructor injection theo type có thể mơ hồ. Hãy dùng `@Qualifier`:

~~~java
@Bean("reportTaskScheduler")
public TaskScheduler reportTaskScheduler(
        @Qualifier("reportJdkExecutor")
        ScheduledExecutorService backend) {
    return new ConcurrentTaskScheduler(backend);
}
~~~

Đây là mảnh cấu hình, giả định một bean `reportJdkExecutor` đã tồn tại và import phù hợp. Khi có nhiều `TaskScheduler`, các consumer nên inject bằng qualifier thay vì dựa vào lựa chọn ngầm.

Đừng đặt tên `taskScheduler` cho nhiều bean khác nhau rồi trông chờ `@Scheduled` tự chọn đúng: điều phối annotation phụ thuộc cấu hình scheduler selection của context.

## 5. Chạy một lần bằng Instant

API thuận tiện nhất:

~~~java
ScheduledFuture<?> handle =
        taskScheduler.schedule(
                () -> System.out.println("once"),
                Instant.now().plusSeconds(10));
~~~

Đây là đoạn Java minh họa, `taskScheduler` phải là reference `TaskScheduler` đã được inject. `Instant` diễn tả **mốc thời gian trên timeline**. Backend JDK cần một delay tương đối, nên adapter tính delay giữa Clock hiện tại và mốc cần chạy rồi chuyển cho delegate.

Điều gì xảy ra nếu `startTime` đã ở trong quá khứ? Scheduler thông thường sẽ thực thi càng sớm càng có thể theo quy tắc scheduling delay; không bảo đảm một nanosecond hay millisecond cụ thể. Việc chuyển giờ hệ điều hành, pause JVM, pool bận hoặc backlog đều có thể khiến thời gian chạy thực tế lệch.

Lưu ý `schedule(Runnable, Trigger)` có thể trả **null** nếu `Trigger` không có thời điểm chạy tiếp theo; việc sử dụng `ScheduledFuture` phải xét kết quả ấy. Với schedule theo `Instant`, backend bình thường trả một handle có thể hủy.

## 6. Fixed rate và fixed delay qua adapter

### 6.1. Fixed rate: thời điểm bắt đầu dự kiến

~~~java
ScheduledFuture<?> fixedRate =
        taskScheduler.scheduleAtFixedRate(
                () -> refreshCache(),
                Duration.ofSeconds(5));
~~~

Mảnh code này cần method `refreshCache()` phù hợp. "Fixed rate" nghĩa là cố duy trì **khoảng cách giữa các mốc bắt đầu dự kiến**, không phải mỗi lần chắc chắn bắt đầu đúng giờ. Nếu job chạy lâu hơn period hoặc pool bận, các lần chạy sau có thể bị muộn.

### 6.2. Fixed delay: chờ sau khi kết thúc

~~~java
ScheduledFuture<?> fixedDelay =
        taskScheduler.scheduleWithFixedDelay(
                () -> pullMessages(),
                Duration.ofSeconds(5));
~~~

Mảnh này cần `pullMessages()`. "Fixed delay" đo từ **thời điểm job trước kết thúc** đến thời điểm job tiếp theo có thể bắt đầu. Nếu job mất 12 giây, delay 5 giây, lần tiếp theo thường chỉ đủ điều kiện chạy sau khoảng 17 giây tính từ lúc bắt đầu lần trước (cộng overhead).

### 6.3. Minh họa trục thời gian

~~~text
Một task chạy khoảng 3 đơn vị; period/delay = 5 đơn vị:

Fixed rate (mốc bắt đầu dự kiến: 0,5,10,...):
0    3  5    8 10   13
|====|  |====|  |====|
run 1   run 2   run 3

Fixed delay (khoảng chờ sau khi hoàn thành: 5):
0    3       8   11      16
|====|-------|===|-------|====
run 1  delay  run 2 delay  run 3
~~~

Đây là timeline minh họa lý tưởng, không có áp lực hệ thống. Với pool thực, thời điểm chạy có thể trễ. **Hai lần thực thi kế tiếp của cùng một periodic schedule** không mặc nhiên được chạy chồng lấp chỉ vì scheduler có nhiều worker; các job **khác** có thể cùng chạy nếu pool có capacity.

### 6.4. Dùng overload có Instant

~~~java
Instant firstRun = Instant.now().plusSeconds(30);

ScheduledFuture<?> rate =
        taskScheduler.scheduleAtFixedRate(
                task, firstRun, Duration.ofMinutes(1));

ScheduledFuture<?> delay =
        taskScheduler.scheduleWithFixedDelay(
                task, firstRun, Duration.ofMinutes(1));
~~~

Đây là đoạn minh họa cần `task`. Mốc `firstRun` cho phép chọn thời điểm chạy đầu tiên. Tránh nhầm overload có `Instant` của Spring với bản JDK lấy `initialDelay` tương đối.

## 7. Trigger: khả năng nổi bật khi thích nghi từ JDK

`ScheduledExecutorService` tự nó không có API tổng quát kiểu "hãy chạy theo cron biểu thức này". Spring `TaskScheduler.schedule(Runnable, Trigger)` giải quyết nhu cầu ấy.

### 7.1. CronTrigger

~~~java
ScheduledFuture<?> cronJob =
        taskScheduler.schedule(
                () -> System.out.println("quarter-hour tick"),
                new CronTrigger("0 */15 * * * *"));
~~~

Đây là đoạn minh họa, cần import `CronTrigger`; biểu thức gồm **sáu trường** Spring cron, nghĩa là chạy ở giây 0 mỗi 15 phút. Đặt `zone` rõ ràng khi nghiệp vụ phụ thuộc múi giờ:

~~~java
CronTrigger vietnamBusinessTime =
        new CronTrigger(
                "0 0 9 * * MON-FRI",
                ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Đây là mảnh code minh họa; import `ZoneId`. Nó diễn tả lịch 09:00 mỗi ngày làm việc theo múi giờ đã chọn (theo quy tắc cron Spring). `ZoneId` khiến cách diễn giải cron rõ ràng hơn khi ứng dụng chạy ở server có timezone khác.

Không sử dụng cron cho thời gian đo bằng mili-giây trong unit test. Cron theo giây và calendar scheduling có thể bị ảnh hưởng múi giờ và thay đổi thời gian (DST) ở một số khu vực.

### 7.2. PeriodicTrigger

~~~java
PeriodicTrigger trigger =
        new PeriodicTrigger(Duration.ofSeconds(10));

trigger.setInitialDelay(Duration.ofSeconds(2));
trigger.setFixedRate(false); // mặc định fixed-delay

ScheduledFuture<?> handle =
        taskScheduler.schedule(task, trigger);
~~~

Đây là mảnh code minh họa. `PeriodicTrigger` hữu ích khi một thành phần muốn nhận **`Trigger` trừu tượng**, có thể thay `CronTrigger`, `PeriodicTrigger` hoặc trigger tự định nghĩa. Nếu mục đích chỉ là fixed rate/fixed delay, dùng trực tiếp các method `scheduleAtFixedRate`/`scheduleWithFixedDelay` thường dễ hiểu hơn.

### 7.3. Custom Trigger và TriggerContext

Trong Spring 6.1, `Trigger.nextExecution(TriggerContext)` trả `Instant` (hoặc null khi không có lịch tiếp):

~~~java
Trigger custom = context -> {
    Instant last = context.lastCompletion();

    if (last == null) {
        return context.getClock().instant().plusSeconds(3);
    }

    return last.plusSeconds(15);
};
~~~

Đây là mảnh code minh họa; khi dùng custom trigger, hãy kiểm tra nullability, timestamp và logic cuối cùng. `TriggerContext` cung cấp thông tin như `lastScheduledExecution()`, `lastActualExecution()`, `lastCompletion()` và `getClock()`. Mỗi lần chạy xong, Spring có thể gọi trigger để tìm mốc kế tiếp và lên lịch lại trên executor JDK.

Nếu trigger trả `null`, lịch kết thúc theo contract trigger; không xem đây là một lần lỗi. Một custom trigger ném exception hoặc tính mốc bất hợp lý cần được kiểm thử và xử lý theo API.

## 8. Ví dụ chạy được: Java 17, Spring Framework 6.1 và ScheduledExecutorService

Đây là project command-line hoàn chỉnh chứng minh:

1. Spring bean `TaskScheduler` thực chất là một **`ConcurrentTaskScheduler` bọc `ScheduledExecutorService` JDK**.
2. One-shot `schedule(..., Instant)` chạy trên thread do JDK factory tạo.
3. `scheduleAtFixedRate(..., Duration)` chạy nhiều lần, không yêu cầu `@EnableScheduling`.
4. `schedule(..., PeriodicTrigger)` chạy nhiều lần qua cơ chế Trigger Spring.
5. `ScheduledFuture.cancel(false)` được dùng để ngừng nhận các lần chạy định kỳ trong demo.
6. Spring đóng JDK executor khi `ApplicationContext` đóng nhờ cấu hình bean destroy method.

Demo dùng **CountDownLatch** để kiểm tra số lần chạy và tránh suy luận từ `Thread.sleep` ngẫu nhiên. Không in tên thread hoặc timestamp dao động; stdout dùng boolean có kết quả xác định khi task hoàn thành trước timeout.

**Môi trường:** JDK 17+, Gradle 8.5+ (hoặc Gradle tương thích với JDK dự án), Spring Framework 6.1.14.

### 8.1. Cấu trúc project

~~~text
jdk-scheduler-adapter/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SchedulerAdapterDemo.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'jdk-scheduler-adapter'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
}

application {
    mainClass = 'demo.SchedulerAdapterDemo'
}
~~~

**src/main/java/demo/SchedulerAdapterDemo.java**

~~~java
package demo;

import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ConcurrentTaskScheduler;
import org.springframework.scheduling.support.PeriodicTrigger;

public final class SchedulerAdapterDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            TaskScheduler scheduler = context.getBean(TaskScheduler.class);

            AtomicBoolean allUsedJdkThreads = new AtomicBoolean(true);
            CountDownLatch oneShotRan = new CountDownLatch(1);
            CountDownLatch fixedRanTwice = new CountDownLatch(2);
            CountDownLatch triggerRanTwice = new CountDownLatch(2);

            // Chạy một lần theo mốc Instant.
            ScheduledFuture<?> oneShot = Objects.requireNonNull(
                    scheduler.schedule(() -> {
                        checkThread(allUsedJdkThreads);
                        oneShotRan.countDown();
                    }, Instant.now().plusMillis(20)));

            // Chạy nhiều lần theo fixed rate.
            ScheduledFuture<?> fixedRate =
                    scheduler.scheduleAtFixedRate(() -> {
                        checkThread(allUsedJdkThreads);
                        fixedRanTwice.countDown();
                    }, Duration.ofMillis(30));

            // Spring Trigger được thực thi qua JDK backend.
            PeriodicTrigger periodic =
                    new PeriodicTrigger(Duration.ofMillis(30));
            periodic.setInitialDelay(Duration.ZERO);

            ScheduledFuture<?> byTrigger = Objects.requireNonNull(
                    scheduler.schedule(() -> {
                        checkThread(allUsedJdkThreads);
                        triggerRanTwice.countDown();
                    }, periodic));

            try {
                oneShot.get(5, TimeUnit.SECONDS);

                if (!fixedRanTwice.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Fixed-rate timeout");
                }
                if (!triggerRanTwice.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Trigger timeout");
                }

                System.out.println("one-shot fired: " +
                        (oneShotRan.getCount() == 0));
                System.out.println("fixed-rate fired twice: " +
                        (fixedRanTwice.getCount() == 0));
                System.out.println("trigger fired twice: " +
                        (triggerRanTwice.getCount() == 0));
                System.out.println("JDK threads used: " +
                        allUsedJdkThreads.get());
            } finally {
                // Hủy các lịch định kỳ; không cần ngắt task đang chạy.
                fixedRate.cancel(false);
                byTrigger.cancel(false);
            }
        }
    }

    private static void checkThread(AtomicBoolean observed) {
        if (!Thread.currentThread().getName()
                .startsWith("jdk-scheduler-")) {
            observed.set(false);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean(destroyMethod = "shutdown")
        public ScheduledExecutorService jdkScheduledExecutor() {
            AtomicInteger sequence = new AtomicInteger();

            return Executors.newScheduledThreadPool(2, command ->
                    new Thread(command, "jdk-scheduler-" +
                            sequence.incrementAndGet()));
        }

        @Bean("taskScheduler")
        public TaskScheduler taskScheduler(
                ScheduledExecutorService jdkScheduledExecutor) {

            return new ConcurrentTaskScheduler(jdkScheduledExecutor);
        }
    }
}
~~~

### 8.2. Chạy và kết quả

Từ thư mục `jdk-scheduler-adapter`, khi đã cài Java 17+ và Gradle:

~~~bash
gradle run
~~~

Nếu project có Gradle Wrapper, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows.

**Các dòng stdout do chương trình tự in trên đường chạy thành công**:

~~~text
one-shot fired: true
fixed-rate fired twice: true
trigger fired twice: true
JDK threads used: true
~~~

Có thể có thông báo do Gradle/Spring in thêm. Những con số "hai lần" ở đây là **điều kiện test** (CountDownLatch về 0), không khẳng định task chỉ chạy đúng hai lần. Lịch định kỳ có thể chạy thêm trong khi caller đang quan sát, trước lúc hủy; điều này không ảnh hưởng boolean. Nếu môi trường quá tải hoặc scheduler không chạy trong 5 giây, chương trình ném exception thay vì báo thành công giả.

### 8.3. Vì sao ví dụ chứng minh được adapter?

- Thread factory của **JDK `ScheduledExecutorService`** chủ động đặt prefix `jdk-scheduler-`; mọi task chạy thực đều kiểm tra prefix đó.
- Spring **không tạo một thread pool thứ hai**: `new ConcurrentTaskScheduler(jdkScheduledExecutor)` nhận đúng delegate từ bean.
- `TaskScheduler.schedule(..., Instant)` dùng lịch một lần.
- `scheduleAtFixedRate(..., Duration)` chuyển vào scheduling backend.
- `schedule(..., PeriodicTrigger)` dùng abstraction Trigger của Spring và scheduling backend JDK.
- `oneShot.get(timeout)` đảm bảo one-shot đã hoàn tất trước khi in kết quả; latch của các task định kỳ xác nhận mỗi loại đã bắt đầu ít nhất hai lần.
- `finally` hủy fixed-rate và trigger schedule. `@Bean(destroyMethod="shutdown")` giúp backend JDK có lifecycle theo Spring context; adapter không cần được ép tự đóng một pool không do nó sở hữu.
- Không có `@EnableScheduling` vì code **gọi trực tiếp API TaskScheduler**, không dùng `@Scheduled`. Nếu thêm annotation-driven scheduling, cần bật hạ tầng tương ứng như mục 9.

## 9. Tích hợp với @Scheduled: phân biệt lập lịch thủ công và annotation

### 9.1. TaskScheduler không tự bật @Scheduled

Lệnh này tự đăng ký lịch khi được gọi:

~~~java
taskScheduler.scheduleAtFixedRate(
        this::refreshIndex, Duration.ofMinutes(1));
~~~

Mảnh code minh họa trên cần class có method `refreshIndex`. **Không bắt buộc** bật `@EnableScheduling` chỉ để gọi trực tiếp TaskScheduler.

Ngược lại, annotation:

~~~java
@Component
class MaintenanceJobs {
    @Scheduled(fixedDelay = 60000)
    public void refreshIndex() {
        // Thực hiện công việc.
    }
}
~~~

Mảnh này cần Spring imports, bean component scan, và **`@EnableScheduling`** trong ApplicationContext. Annotation không tự hoạt động chỉ vì bạn có một bean `ConcurrentTaskScheduler`.

### 9.2. Chỉ rõ TaskScheduler cho annotation-driven scheduling

Trong cấu hình đơn giản, Spring scheduling infrastructure có thể tìm một `TaskScheduler` duy nhất hoặc một bean tên `taskScheduler` theo quy tắc của phiên bản. Cấu hình explicit hữu ích khi có nhiều loại scheduler:

~~~java
@Configuration
@EnableScheduling
public class ScheduledJobsConfig implements SchedulingConfigurer {

    private final TaskScheduler adapter;

    public ScheduledJobsConfig(
            @Qualifier("reportTaskScheduler") TaskScheduler adapter) {
        this.adapter = adapter;
    }

    @Override
    public void configureTasks(ScheduledTaskRegistrar registrar) {
        registrar.setTaskScheduler(adapter);
    }
}
~~~

Đây là **mảnh cấu hình**, cần import `@Configuration`, `@EnableScheduling`, `SchedulingConfigurer`, `ScheduledTaskRegistrar`, `@Qualifier` và một bean `reportTaskScheduler`. Cách này để các `@Scheduled` tasks đi qua scheduler mong muốn thay vì dựa vào chọn bean mơ hồ.

`@Async` là cơ chế khác: nó yêu cầu `@EnableAsync` (hoặc cấu hình tương đương) và executor phù hợp. Việc có `ConcurrentTaskScheduler` **không làm tất cả method `@Async` tự động chạy theo lịch**. `@Scheduled` xác định **khi nào** method được kích hoạt; `@Async` xác định **cách dispatch** lời gọi method khi Spring proxy intercept. Hai ý niệm có thể phối hợp nhưng cần kiểm tra số thread, ordering, rejection và exception handling.

### 9.3. Tránh đăng ký lịch hai lần

Nếu cùng một hành động đã có `@Scheduled`, lại gọi `scheduler.schedule(...)` cho nó khi startup, ứng dụng có thể tạo **hai lịch độc lập**. Sự cố thường bị hiểu nhầm là Spring gọi method trùng. Trước khi sửa bằng lock, hãy kiểm tra có bao nhiêu registration thực sự được tạo và ai sở hữu các `ScheduledFuture` tương ứng.

## 10. Quản lý vòng đời backend JDK

### 10.1. Ai tạo executor thì người đó phải có chính sách dừng

`ScheduledExecutorService` do `Executors.newScheduledThreadPool(...)` tạo có worker threads và lịch đang chờ. Nếu bạn chỉ đặt nó vào một adapter rồi bỏ reference/lifecycle, JVM có thể không kết thúc và lịch vẫn tiếp tục chạy sau khi component nghiệp vụ không còn cần.

Các cách hợp lệ:

- Trong Spring, tạo `ScheduledExecutorService` thành bean và khai báo `destroyMethod = "shutdown"` hoặc một destroy strategy phù hợp.
- Nếu code tự tạo pool ngoài container, đóng trong `finally` bằng `shutdown()` hoặc `shutdownNow()` theo hợp đồng.
- Nếu backend do Jakarta EE/container cung cấp, **không shutdown tài nguyên server-wide** từ application code; để môi trường quản lý.
- Nếu đăng ký một lịch theo yêu cầu người dùng, lưu `ScheduledFuture` và cho phép hủy lịch khi yêu cầu bị gỡ bỏ.

### 10.2. shutdown và shutdownNow khác nhau

~~~java
ScheduledExecutorService backend =
        Executors.newScheduledThreadPool(2);

try {
    // Đăng ký và dùng các lịch.
} finally {
    backend.shutdown();
    if (!backend.awaitTermination(5, TimeUnit.SECONDS)) {
        backend.shutdownNow();
    }
}
~~~

Đây là mảnh code minh họa, đặt trong method có `throws InterruptedException` hoặc catch phù hợp; không phải class độc lập. `shutdown()` ngừng nhận task mới và xử lý phần còn lại theo shutdown policies của implementation; `shutdownNow()` cố yêu cầu ngắt worker và trả về các task chờ chưa thực thi. **Không API nào hứa mọi callback đã an toàn dừng hoặc side effect đã rollback**.

Nếu thread đang chờ `awaitTermination` bị interrupt, phải xử lý `InterruptedException` đúng contract (thường yêu cầu shutdownNow nếu thực sự sở hữu backend, rồi restore status hoặc propagate).

### 10.3. ScheduledThreadPoolExecutor shutdown policies

Khi cần kiểm soát chi tiết, có thể dùng `ScheduledThreadPoolExecutor` thay vì factory tổng quát. Nó có một số thuộc tính như:

- `setRemoveOnCancelPolicy(true)`: giúp dọn các cancelled delayed tasks khỏi delay queue theo policy để giảm giữ tài nguyên.
- `setExecuteExistingDelayedTasksAfterShutdownPolicy(...)`: quyết định có thực thi các delayed tasks còn chờ sau khi shutdown hay không.
- `setContinueExistingPeriodicTasksAfterShutdownPolicy(...)`: quyết định các periodic tasks đã có có được tiếp tục sau shutdown theo policy hay không.

Các lựa chọn này cần được kiểm thử cùng SLA shutdown. Không gán chính sách quá mạnh như "luôn hủy mọi task" chỉ từ việc `ConcurrentTaskScheduler` được khai báo: **executor phía dưới** quyết định phần lớn lifecycle thực tế.

## 11. Cancellation, ScheduledFuture và bài toán hủy một lịch

`TaskScheduler` trả `ScheduledFuture<?>` để caller có thể hủy lịch:

~~~java
ScheduledFuture<?> handle =
        scheduler.scheduleAtFixedRate(
                this::runMaintenance, Duration.ofMinutes(10));

// Khi không còn muốn nhận các lần chạy sau:
boolean cancellationRequested = handle.cancel(false);
~~~

Đây là đoạn minh họa. Với `cancel(false)`, code không yêu cầu interrupt một lần chạy đang active. `cancel(true)` có thể yêu cầu interrupt worker nếu implementation hỗ trợ, nhưng **không bảo đảm** task đang làm JDBC/HTTP hoặc external side effect sẽ dừng tức thì.

Điều quan trọng:

- **Cancel schedule** và **cancel một business job** không hoàn toàn giống nhau. Một lần chạy có thể đã kích hoạt nhiệm vụ nền khác.
- Một periodic schedule có thể đã chạy một số lần trước khi bị hủy; `cancel` chỉ tác động theo hợp đồng tại thời điểm gọi.
- `ScheduledFuture.isCancelled()` báo trạng thái handle; không chứng minh mọi downstream operation đã rollback.
- Với custom `Trigger`, scheduler Spring có thể tạo những lần scheduling mới sau mỗi completion; hãy giữ **handle do `TaskScheduler.schedule(..., trigger)` trả về**, không tự hủy một internal task riêng mà adapter có thể tiếp tục reschedule.
- Không gọi `get()` không timeout trên một Future định kỳ vốn được kỳ vọng chạy mãi; nó có thể không bao giờ hoàn thành bình thường.

Khi một nhiệm vụ thật sự có deadline, cần thêm timeout cho I/O, cancellation token hoặc trạng thái job, không chỉ rely on scheduled future.

## 12. Xử lý lỗi task: adapter Spring và hành vi JDK

### 12.1. Exception trong scheduled Runnable

Với JDK `ScheduledExecutorService.scheduleAtFixedRate` trực tiếp, nếu một execution ném exception không được xử lý, các lần thực thi tiếp theo của lịch định kỳ có thể bị **suppressed** theo contract JDK.

`ConcurrentTaskScheduler` có `setErrorHandler(ErrorHandler)` và sử dụng cơ chế Spring trang trí scheduled tasks. Với cấu hình mặc định Spring, các **repeating tasks** thường được log và **suppress exception** để cho phép tiếp tục lịch; **one-shot tasks** thường log và propagate exception để nó hiện qua Future. Khi cấu hình handler tùy biến, hành vi có thể thay đổi đáng kể.

~~~java
ConcurrentTaskScheduler adapter =
        new ConcurrentTaskScheduler(jdkBackend);

adapter.setErrorHandler(error -> {
    // Ghi metric, log có rate limit, cập nhật trạng thái task.
    recordScheduledFailure(error);

    // Nếu rethrow ở đây, lịch có thể dừng theo policy.
});
~~~

Đây là mảnh code minh họa, `jdkBackend` và `recordScheduledFailure` chưa định nghĩa. Không dùng handler chỉ nuốt mọi lỗi khi nghiệp vụ cần biết job thất bại; nhưng cũng không tự ném ngoại lệ trên mọi periodic callback mà không hiểu hậu quả ngừng lịch.

### 12.2. Rejection ở thời điểm lên lịch

Khi ScheduledExecutorService đã shutdown hoặc không nhận thêm việc, `schedule` có thể ném `RejectedExecutionException`. Qua API Spring, `ConcurrentTaskScheduler` có thể chuyển lỗi ấy thành `TaskRejectedException` theo hợp đồng Spring.

**Phân biệt hai pha**:

~~~text
scheduler.schedule(task, time)
        |
        +-- Rejected at registration? -> lỗi ngay tại caller
        |
        +-- Accepted -> ScheduledFuture
                         |
                         +-- task chạy và thành công
                         +-- task lỗi, xử lý theo ErrorHandler
                         +-- handle bị cancel
                         +-- backend shutdown / process crash
~~~

Nhận một `ScheduledFuture` **không có nghĩa** hệ thống bảo đảm task sẽ chạy đúng giờ, sẽ hoàn thành hay sống sót sau restart. Cần theo dõi cả số lần **registration**, **actual start**, **completed/failed**, **cancelled** và **missed deadlines** theo yêu cầu nghiệp vụ.

### 12.3. @Scheduled và AsyncUncaughtExceptionHandler không phải một

`AsyncUncaughtExceptionHandler` chủ yếu áp dụng cho `@Async void`. Nó không phải một giải pháp chung để quản lý lỗi của mọi method do `TaskScheduler` gọi. Các scheduled runnables có error handling của scheduler; hệ thống production nên đặt chính sách logging/metrics rõ ở **đúng tầng**.

## 13. So sánh các lựa chọn scheduler Spring

| Lựa chọn | Backend chính | Khi nào phù hợp? | Lưu ý |
| --- | --- | --- | --- |
| `ConcurrentTaskScheduler` | `ScheduledExecutorService` do ứng dụng/container cung cấp | Đã có JDK scheduler và muốn Spring `TaskScheduler`/Trigger | Lifecycle pool phụ thuộc owner, cần cấu hình rõ |
| `ThreadPoolTaskScheduler` | Spring quản lý `ScheduledThreadPoolExecutor` bên dưới | Muốn cấu hình pool, naming, shutdown qua Spring bean | Thường thuận tiện hơn khi bắt đầu từ đầu |
| `DefaultManagedTaskScheduler` | Managed scheduler từ Jakarta EE/container, thường qua JNDI | Môi trường không cho ứng dụng tự sở hữu threads | Server quản lý lifecycle |
| `SimpleAsyncTaskScheduler` (Spring 6.1+) | Một scheduler thread điều phối, cấp thread chạy task theo mô hình riêng | Nhu cầu scheduler đơn giản, có thể phối hợp JDK 21 virtual threads | Với fixed-delay, các lần chạy diễn ra trên một scheduler thread theo thiết kế; phải cân nhắc tác vụ blocking |
| JDK `ScheduledExecutorService` thuần | ScheduledExecutorService | Chỉ cần Java scheduling, không cần Spring Trigger/DI | Không có TaskScheduler abstraction để Spring component dùng |
| Quartz | Scheduler chuyên biệt | Lịch phức tạp/persistent jobs, nhiều node tùy cấu hình | Thiết lập và vận hành phức tạp hơn; độ bền tùy JobStore/configuration |

**Khuyến nghị lựa chọn:** nếu bạn cần adapt một executor đã có, chọn `ConcurrentTaskScheduler`. Nếu muốn tạo pool scheduler tiêu chuẩn trong Spring với lifecycle tiện lợi, chọn `ThreadPoolTaskScheduler`. Nếu cần lịch phải **khôi phục sau crash**, job definitions bền vững hoặc coordination giữa nhiều node, nghiên cứu một scheduler/job store chuyên biệt thay vì dựa vào in-memory ScheduledExecutorService.

## 14. Khả năng đồng thời thực tế phụ thuộc executor

Tên `ConcurrentTaskScheduler` dễ gây hiểu nhầm: nó **không** bảo đảm mọi lịch chạy song song. Nếu backend:

~~~java
ScheduledExecutorService single =
        Executors.newSingleThreadScheduledExecutor();

TaskScheduler adapter = new ConcurrentTaskScheduler(single);
~~~

Các scheduled tasks dùng cùng **một worker**, nên callback blocking dài có thể làm tất cả lịch còn lại trễ. Nếu backend là pool hai thread, tối đa số task đang chạy cùng lúc còn phụ thuộc số worker thực tế và cách job sử dụng tài nguyên.

### 14.1. Phân biệt scheduling thread và công việc được dispatch tiếp

Một callback scheduled có thể:

1. Chạy công việc trực tiếp, giữ worker scheduler đến khi xong.
2. Chỉ tạo job/submit vào một `TaskExecutor` khác rồi trả về, để scheduler thread rảnh sớm.

Mẫu thứ hai giúp scheduler tiếp tục điều phối lịch đúng lúc hơn khi job nặng, nhưng tạo **hai tầng queue/rejection/lifecycle**. Phải quản lý task executor đích; không tự động đồng nghĩa job đã hoàn tất chỉ vì callback scheduler trả về.

~~~text
JDK ScheduledExecutorService
         |
         +-- trigger: gọi Runnable ngắn
                          |
                          +--> TaskExecutor.execute(heavyTask)
                                        |
                                        +--> worker pool riêng
~~~

Nếu `heavyTask` quan trọng, việc `execute` thành công chưa bảo đảm durable delivery. Hãy dùng job store/outbox/broker phù hợp khi cần persist công việc.

### 14.2. Downstream có thể làm pool nghẽn

Ngay cả với `newScheduledThreadPool(8)`, tám job cùng chờ một DB connection duy nhất không tăng throughput. Các nguồn nghẽn thường là:

- JDBC connection pool nhỏ hơn số job cùng đòi kết nối.
- Remote API rate limit/HTTP connection cap.
- Lock trên singleton mutable state.
- Lịch có cùng thời điểm kích hoạt tạo burst.
- Cron chạy vào giờ cao điểm.
- Callback có retry vô hạn, sleep/block quá lâu hoặc quên timeout.

Dùng bounded concurrency, timeout, retries có giới hạn và quan sát queue wait/deadline lag. Không chỉ tăng thread count để sửa mọi sự cố trễ lịch.

## 15. Cron, Clock, múi giờ và thay đổi thời gian

`ConcurrentTaskScheduler.setClock(Clock)` cho biết Clock dùng để tính các thời điểm scheduling, mặc định là system clock theo zone mặc định của process. `getClock()` trả Clock đó theo `TaskScheduler`.

~~~java
ConcurrentTaskScheduler adapter =
        new ConcurrentTaskScheduler(jdkBackend);

adapter.setClock(
        Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")));
~~~

Mảnh code minh họa này cần import `Clock`, `ZoneId`; `jdkBackend` đã được tạo. Đây là lựa chọn clock của adapter; không nên nhầm với việc thay đồng hồ hệ điều hành hay thay implementation timer monotonic của `ScheduledExecutorService`.

Với cron theo business timezone, **chỉ rõ ZoneId trên CronTrigger** là cách thể hiện ý định dễ hiểu. Cron có thể tạo nhiều trường hợp đặc biệt tại nơi có DST, khi giờ bị bỏ qua hoặc lặp lại; cần kiểm tra chính sách và kỳ vọng theo time zone thực.

`Instant` là mốc tuyệt đối; `Duration` biểu diễn khoảng thời gian. Khi dựa vào Calendar lịch sử và business hours, dùng `CronTrigger`/Clock phù hợp; khi chỉ cần "mỗi n giây", fixed-rate/fixed-delay và `Duration` thường rõ hơn.

**Test thời gian:** Có thể dùng Clock giả cho logic tính mốc trigger, nhưng việc chỉ thay Clock của adapter **không tự đẩy thời gian của JDK worker**. Các integration tests có thể cần `CountDownLatch`, khoảng chờ có timeout và instrumentation để xác minh task thật đã chạy.

## 16. Monitoring và bảo vệ vận hành

Nên đo ít nhất:

- **scheduled registrations**: số lịch one-shot/periodic đang đăng ký.
- **next planned execution**: mốc dự kiến tiếp theo (nếu abstraction/registry cung cấp).
- **actual start** và **completion time**: độ trễ giữa planned và actual.
- **execution duration**, error count, cancellation count, rejection count.
- **active workers**, queue depth, task waiting time ở ScheduledThreadPoolExecutor.
- **retry/overlap state** nếu callback gửi tiếp công việc sang pool khác.
- **shutdown duration** và số lịch còn pending trước khi đóng ứng dụng.

Với `ScheduledThreadPoolExecutor` cụ thể, có thể quan sát trạng thái pool/queue theo API JDK hoặc metrics framework. Với `ScheduledExecutorService` trừu tượng, không phải implementation nào cũng hỗ trợ pool size/queue depth giống nhau; **không cast mù quáng** sang `ScheduledThreadPoolExecutor` khi backend được cung cấp từ môi trường khác.

Đặt tên thread qua `ThreadFactory` (như demo `jdk-scheduler-`) giúp thread dump và log rõ hơn. Trong production, thêm structured logging, job ID và correlation ID. Không đưa token/PII vào thread name; một thread pool được tái sử dụng cho nhiều jobs khác nhau.

### 16.1. Scheduler không tự bảo đảm exactly-once

Giả sử một job gửi email có lịch 09:00. Nếu JVM dừng lúc 08:59 và chỉ khởi động lại 09:05, một lịch chỉ tồn tại trong memory **không tự khôi phục lần chạy 09:00 bị bỏ lỡ**. Một `ScheduledFuture` cũng không phải xác nhận email đã đến người nhận.

Với job quan trọng:

1. Lưu định nghĩa lịch hoặc job due time trong DB/job store.
2. Có cơ chế claim/lease khi nhiều node cùng chạy.
3. Theo dõi trạng thái pending/running/succeeded/failed/missed.
4. Retry có idempotency key hoặc deduplication.
5. Quy định có chạy bù (misfire handling) sau restart hay không.
6. Phân biệt lịch kích hoạt với side effect đã commit.

`ConcurrentTaskScheduler` chỉ là adapter cho scheduling trong process; nó **không thay thế** các cơ chế durable job execution ấy.

## 17. Anti-pattern và cách sửa

| Anti-pattern | Rủi ro | Cách sửa |
| --- | --- | --- |
| Dùng no-arg `new ConcurrentTaskScheduler()` trong Spring 6.1 rồi quên pool | Constructor deprecated, lifecycle mơ hồ | Inject `ScheduledExecutorService` rõ ràng |
| Bean adapter tạo `Executors.newScheduledThreadPool()` nội bộ không quản lý | Thread leak, shutdown không rõ | Tạo JDK executor thành bean có destroy method |
| Cho rằng `setScheduledExecutor` đổi cả `execute` | Nhầm hai delegate của adapter | Dùng constructor phù hợp hoặc cấu hình `setConcurrentExecutor` |
| Một scheduler worker chạy job blocking rất dài | Lịch khác trễ | Tăng capacity đúng mức hoặc dispatch sang bounded worker pool riêng |
| Đặt `@Scheduled` mà không bật `@EnableScheduling` | Annotation không được đăng ký | Bật scheduling đúng context |
| Tự schedule thêm cùng method đã có `@Scheduled` | Job chạy trùng | Chọn một nơi đăng ký lịch |
| Hiểu fixed rate là luôn đúng mốc hoặc luôn overlap | Quá tải, kỳ vọng sai | Đo lag, timeout, điều chỉnh period và pool |
| Dùng cron không zone cho business giờ địa phương | Lệch giờ khi deploy server khác | Chỉ định ZoneId |
| Bắt exception rồi bỏ qua mà không metric | Job hỏng âm thầm | ErrorHandler và observability rõ |
| Bắt lỗi và luôn rethrow periodic callback | Có thể làm lịch dừng | Quyết định stop/retry/continue theo hợp đồng |
| `future.get()` vô hạn trên periodic schedule | Caller có thể treo | Dùng cancellation/status thay vì chờ hoàn thành bình thường |
| `cancel(true)` được coi là worker chắc chắn dừng | Side effect có thể vẫn chạy | Hủy hợp tác và timeout downstream |
| Gửi tác vụ mới lúc executor shutdown | Bị reject | Quản lý producer/lifecycle, bắt lỗi từ chối |
| Dùng adapter để mong lịch sống qua restart | In-memory state bị mất | Durable job store/Quartz/outbox tùy yêu cầu |
| Chia sẻ một ScheduledExecutorService toàn hệ thống nhưng app con tự shutdown | Ảnh hưởng các bên khác | Tuân quyền sở hữu tài nguyên của container |

## 18. Checklist khi chọn ConcurrentTaskScheduler

- [ ] Ứng dụng **đã có** `ScheduledExecutorService` hoặc cần đặc tính riêng của nó.
- [ ] Đã phân biệt `TaskScheduler` và `TaskExecutor`; chọn constructor một/hai delegate đúng ý.
- [ ] Constructor no-arg deprecated của 6.1 không được dùng trong code mới.
- [ ] Backend được cấp qua DI, không tạo ngầm một executor mỗi lần đăng ký lịch.
- [ ] Lịch cron có timezone rõ khi cần; fixed period dùng `Duration`, mốc dùng `Instant`.
- [ ] Có quy tắc dùng `@EnableScheduling` cho `@Scheduled`, tách khỏi lời gọi API programmatic.
- [ ] Khi nhiều scheduler bean, có `@Qualifier` hoặc `SchedulingConfigurer`.
- [ ] Có owner shutdown JDK executor khi context/app kết thúc; không tắt backend container-wide trái quyền.
- [ ] Đã chọn pool size/thread factory và tính đến DB/HTTP downstream capacity.
- [ ] Có `ScheduledFuture` và cơ chế cancel khi đăng ký lịch động.
- [ ] Có chính sách exception của scheduled tasks, không đoán job chắc chắn tiếp tục hay dừng.
- [ ] Bắt/quan sát task rejection khi executor shutdown hoặc saturation.
- [ ] Không gọi `get()` vô hạn trên Future định kỳ.
- [ ] Có metrics về execution lag/duration/error/cancellation.
- [ ] Không coi scheduler trong memory là job store bền vững.
- [ ] Có test bằng latch/timeouts và cleanup, không dựa hoàn toàn vào `Thread.sleep`.

## 19. Câu hỏi tự kiểm tra

1. **ConcurrentTaskScheduler thích nghi interface nào của JDK?** `ScheduledExecutorService`, để cung cấp API `TaskScheduler` của Spring.
2. **Adapter có tự tạo pool khi dùng constructor một tham số không?** Không. Nó dùng executor được truyền vào.
3. **Hai tham số constructor thể hiện hai mục đích nào?** Một `Executor` cho task execution thông thường, một `ScheduledExecutorService` cho scheduling.
4. **`setScheduledExecutor` có nhất thiết đổi delegate của `execute` không?** Không; nó ảnh hưởng nhánh TaskScheduler, không mặc nhiên đổi concurrent delegate.
5. **Tại sao dùng Spring Trigger nếu JDK đã có scheduleAtFixedRate?** Trigger hỗ trợ cron, điều kiện thời gian và lịch tính dựa trên ngữ cảnh chạy trước.
6. **`PeriodicTrigger` mặc định fixed rate hay fixed delay?** Fixed delay; có thể đổi bằng `setFixedRate(true)`.
7. **Trong fixed delay, khoảng delay được đo từ lúc nào?** Từ khi lần chạy trước hoàn tất đến mốc lần tiếp theo.
8. **Một periodic task chạy lâu thì fixed rate có chạy chồng lên chính nó không?** Theo hợp đồng JDK `ScheduledThreadPoolExecutor`, các executions của cùng periodic schedule không overlap; chúng có thể trễ.
9. **Có TaskScheduler bean rồi thì `@Scheduled` tự hoạt động chưa?** Chưa; cần scheduling annotation infrastructure như `@EnableScheduling` đúng context.
10. **Gọi `schedule(task, trigger)` có bắt buộc `@EnableScheduling` không?** Không; đây là API gọi trực tiếp.
11. **Ai phải shutdown JDK scheduled executor?** Thành phần sở hữu tài nguyên (bean/app/container) theo lifecycle phù hợp, không phải tùy tiện ở mọi consumer.
12. **`setErrorHandler` ảnh hưởng gì?** Cách xử lý exception của scheduled tasks; nó có thể quyết định task lỗi được ghi nhận và lịch tiếp tục hoặc dừng.
13. **`cancel(false)` chắc chắn hủy mọi side effect của job đang chạy không?** Không; nó không yêu cầu ngắt task active thông qua tham số.
14. **Vì sao `schedule(..., CronTrigger)` dễ chịu ảnh hưởng timezone?** Cron diễn tả lịch theo calendar; cần zone để diễn giải giờ kinh doanh đúng.
15. **Chọn `ConcurrentTaskScheduler` hay `ThreadPoolTaskScheduler` khi bắt đầu dự án từ đầu?** Nếu không có backend JDK riêng, `ThreadPoolTaskScheduler` thường tiện hơn để cấu hình pool/lifecycle.
16. **Nếu cần lịch tồn tại qua JVM restart, ConcurrentTaskScheduler có đủ chưa?** Không; cần durable scheduling/job store và quy tắc misfire/retry/idempotency.
17. **Làm sao biết adapter dùng đúng JDK worker?** Đặt tên thread bằng ThreadFactory, test task qua TaskScheduler và quan sát prefix/metrics.
18. **Vì sao tên Concurrent không đồng nghĩa chạy tất cả lịch đồng thời?** Năng lực thực phụ thuộc executor JDK và các tài nguyên/khóa/downstream.
19. **Có thể dùng ManagedScheduledExecutorService của Jakarta EE không?** Có khi môi trường tương thích; adapter có cơ chế nhận diện. Quyền quản lý lifecycle nằm ở container.
20. **Làm sao tránh một cron job chạy hai lần trong application?** Kiểm tra có annotation registration và programmatic registration trùng hoặc nhiều instances/nodes cùng chạy; nếu phải chạy một lần toàn cụm cần coordination ở tầng cao.

**Kết luận:** `ConcurrentTaskScheduler` là **cầu nối từ JDK `ScheduledExecutorService` sang Spring `TaskScheduler`**, bổ sung API Spring cho `Instant`, `Duration` và `Trigger` mà vẫn dùng backend JDK đã có. Chọn nó khi cần **thích nghi executor bên ngoài**; dùng `ThreadPoolTaskScheduler` khi muốn Spring tự quản lý scheduler pool. Dù chọn cách nào, phải quản lý **lifecycle, cancellation, error handling, concurrency và durability** theo hợp đồng của ứng dụng.

### Tài liệu chính thức

- [Spring Framework 6.1 — ConcurrentTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ConcurrentTaskScheduler.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework 6.1 — TaskScheduler](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
- [Spring Framework 6.1 — PeriodicTrigger](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/support/PeriodicTrigger.html)
- [Spring Framework 6.1 — CronTrigger](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/support/CronTrigger.html)
- [Spring Framework 6.1 — ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Java 17 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)
- [Java 17 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html)
- [Java 17 — ScheduledFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html)
