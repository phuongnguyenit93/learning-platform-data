# ThreadPoolTaskScheduler dựa trên ScheduledExecutorService

## 1. Tổng quan và mục tiêu

Spring Framework cung cấp `ThreadPoolTaskScheduler` để chạy các công việc **vào một thời điểm trong tương lai** hoặc **lặp lại theo chu kỳ/trigger**. Thay vì tự tạo và quản lý `ScheduledExecutorService` ở nhiều nơi, ứng dụng Spring có thể khai báo một bean scheduler, sử dụng API `TaskScheduler` hoặc kết hợp với `@EnableScheduling` và `@Scheduled`.

Điểm kiến trúc cốt lõi:

> **`ThreadPoolTaskScheduler` là implementation Spring của `TaskScheduler`, bao bọc một `java.util.concurrent.ScheduledThreadPoolExecutor` (một `ScheduledExecutorService` của JDK). Task thực thi ngay trên các scheduler thread do pool này quản lý.**

Vì vậy nó **không phải một bộ định giờ chạy ở một thread rồi mặc định đẩy toàn bộ tác vụ sang một worker pool riêng**. Nếu công việc được hẹn chạy mất 30 giây và pool chỉ có một thread, những công việc khác của **cùng scheduler** có thể phải đợi.

### Bạn sẽ học được gì?

- Phân biệt vai trò `ScheduledExecutorService`, `ScheduledThreadPoolExecutor`, `TaskScheduler` và `ThreadPoolTaskScheduler`.
- Dùng `schedule(Runnable, Instant)`, `scheduleAtFixedRate(...)`, `scheduleWithFixedDelay(...)` và `schedule(Runnable, Trigger)`.
- Hiểu **fixed rate theo nhịp bắt đầu**, **fixed delay theo lúc kết thúc**, trigger cron theo lịch và ảnh hưởng của task kéo dài.
- Biết **`setPoolSize(1)` là mặc định**, task chạy trên scheduler worker, và vì sao số worker không phải số job bền vững.
- Cấu hình một bean `ThreadPoolTaskScheduler` trong Spring Framework 6.1.3 và chạy chương trình hoàn chỉnh với **Java 17+**.
- Phân biệt `ThreadPoolTaskScheduler` với `ThreadPoolTaskExecutor`, cả về scheduling, queue và lifecycle.
- Hiểu `ScheduledFuture`, hủy task, rejection, error handling của Spring, shutdown, pause/resume và những giới hạn khi triển khai nhiều instance.
- Thiết kế monitoring, timeout, idempotency và lịch có time zone rõ ràng.

**Phiên bản:** Các ví dụ biên dịch theo **Java 17+**, sử dụng **Spring Framework 6.1.3** cho project Maven. Cơ chế `ScheduledExecutorService` đã có từ Java 5; `Duration`/`Instant` được dùng trong Spring `TaskScheduler` của Spring 6.x. Một số tính năng Spring 6.1 (pause/resume, tích hợp virtual-thread-aligned scheduler khác) được phân biệt rõ với bản JDK hoặc Spring cũ.

## 2. Kiến trúc: Spring TaskScheduler bao ngoài JDK ScheduledExecutorService

### 2.1. Lớp API của JDK

`ScheduledExecutorService` là một interface kế thừa `ExecutorService`. Ngoài việc `execute`/`submit` ngay lập tức, nó có các thao tác hẹn:

~~~java
// Chữ ký minh họa của JDK, không phải class độc lập.
ScheduledFuture<?> schedule(
        Runnable task, long delay, TimeUnit unit);

<V> ScheduledFuture<V> schedule(
        Callable<V> task, long delay, TimeUnit unit);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, long initialDelay, long period, TimeUnit unit);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, long initialDelay, long delay, TimeUnit unit);
~~~

Implementation phổ biến trong Java 17 là `ScheduledThreadPoolExecutor`. Nó sử dụng hàng đợi công việc có delay, một số worker threads và trả `ScheduledFuture` để theo dõi hoặc hủy lịch.

~~~text
Caller
  |
  | schedule(task, delay) / scheduleAtFixedRate(...) / ...
  v
ScheduledExecutorService (JDK interface)
  |
  v
ScheduledThreadPoolExecutor (JDK implementation)
  |                  |
  |-- delayed queue |-- worker-1
  |                  |-- worker-2
  |
  +-- ScheduledFuture<?>  (theo dõi / hủy)
~~~

Điểm quan trọng: task chỉ được phép bắt đầu khi đến hạn, **không được đảm bảo chính xác thời điểm đó**. Hệ điều hành, hàng đợi, thời gian task khác đang chạy và số scheduler threads có thể gây trễ. Đây là công cụ scheduling trong JVM, không phải bộ định thời gian thực (hard real-time).

### 2.2. Lớp API của Spring

`org.springframework.scheduling.TaskScheduler` dùng API thân thiện với Spring và kiểu thời gian của `java.time`:

~~~java
// Chữ ký tiêu biểu trong Spring Framework 6.1.x.
// Fragment interface minh họa, không phải file biên dịch độc lập.
ScheduledFuture<?> schedule(Runnable task, Instant startTime);

ScheduledFuture<?> schedule(Runnable task, Trigger trigger);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Duration period);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Instant startTime, Duration period);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Duration delay);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Instant startTime, Duration delay);
~~~

`ThreadPoolTaskScheduler` triển khai interface này, đồng thời bao bọc `ScheduledThreadPoolExecutor` của JDK. Với implementation mặc định, có thể lấy đối tượng gốc qua:

~~~java
// Fragment sau khi bean ThreadPoolTaskScheduler đã khởi tạo.
ScheduledExecutorService nativeScheduler =
        scheduler.getScheduledExecutor();

ScheduledThreadPoolExecutor nativePool =
        scheduler.getScheduledThreadPoolExecutor();
~~~

Hai accessor trên hữu ích khi cần thống kê, cấu hình native đặc biệt hoặc điều tra hành vi. Nhưng **code nghiệp vụ nên phụ thuộc `TaskScheduler`** khi không cần thuộc tính implementation để dễ đổi backend.

### 2.3. Task có chạy trên thread khác do Spring giao tiếp không?

Một điểm Spring Javadoc nhấn mạnh: **task của `ThreadPoolTaskScheduler` thực thi trên chính scheduler thread(s)**, không mặc định đi tiếp tới một execution pool khác. Khi một task đang chặn I/O:

- Worker scheduler đó bị chiếm trong suốt khoảng thời gian task chờ.
- Pool có một worker có thể làm các lịch khác chậm, dù chúng đến hạn.
- Nếu tăng `setPoolSize(4)`, các task **khác nhau** có thể dùng những worker khác; nhưng từng lần lặp của **cùng một periodic JDK task** không tự chồng lấn chính nó.
- Nếu task thật được nộp sang executor khác hoặc method `@Scheduled` tự gọi service `@Async`, thời điểm hoàn thành thao tác thật có thể **khác thời điểm kết thúc lời gọi scheduled callback**. Đó là kiến trúc do ứng dụng chọn thêm, không phải mặc định của scheduler.

## 3. Một lần, fixed rate, fixed delay và trigger

### 3.1. Lệnh `schedule(Runnable, Instant)` chỉ chạy một lần

~~~java
// Fragment khi đã có TaskScheduler scheduler.
ScheduledFuture<?> future = scheduler.schedule(
        () -> sendReminder(),
        Instant.now().plusSeconds(10)
);
~~~

Lời gọi trả `ScheduledFuture<?>` để caller có thể `cancel(...)` hoặc `get()`. Với `Runnable` hoàn tất bình thường, `get()` trả `null`. Nếu thời điểm yêu cầu là quá khứ, scheduler có thể chạy task sớm nhất có thể; không dùng giá trị `Instant` quá khứ làm bảo đảm task chạy “quay ngược thời gian”.

Đây là fragment: `sendReminder()` và `scheduler` cần được định nghĩa trong ứng dụng. Với công việc có side effect như gửi email, cần idempotency và một nơi lưu trạng thái, không giả định việc schedule trong bộ nhớ là giao hàng chính xác một lần.

### 3.2. Fixed rate: nhịp tính từ lúc bắt đầu dự kiến

~~~java
// Fragment Spring 6.x.
ScheduledFuture<?> pulse = scheduler.scheduleAtFixedRate(
        () -> refreshCounters(),
        Duration.ofSeconds(5)
);
~~~

Mục tiêu là lặp theo nhịp khoảng 5 giây giữa **các mốc bắt đầu dự kiến**. Nếu lần chạy mất lâu hơn period, lần sau có thể **bắt đầu trễ**; đối với `ScheduledThreadPoolExecutor.scheduleAtFixedRate`, các lần thực thi của **cùng periodic task không chạy song song chồng nhau**, dù có nhiều worker.

~~~text
Ví dụ fixedRate period = 5s, mỗi lần task mất 8s:

mốc kỳ vọng:  0s    5s    10s    15s
chạy thực:    [0------------8][8------------16][16---------...]
                    bị trễ, không tạo bản sao song song
~~~

Đồ thị minh họa **độ trễ tích lũy**, không phải cam kết scheduler sẽ bắt đầu chính xác từng mốc. Những task khác trên cùng scheduler vẫn có thể chạy đồng thời nếu pool còn worker.

### 3.3. Fixed delay: đợi thêm sau khi lần trước kết thúc

~~~java
// Fragment Spring 6.x.
ScheduledFuture<?> cleanup = scheduler.scheduleWithFixedDelay(
        () -> deleteTemporaryFiles(),
        Duration.ofSeconds(5)
);
~~~

Delay 5 giây được đo từ **lúc hoàn tất** một lần chạy tới lúc bắt đầu lần kế tiếp, không tính từ lịch bắt đầu lý tưởng.

~~~text
Ví dụ fixedDelay = 5s, mỗi lần task mất 8s:

lần 1:       [0-------------8]
chờ delay:                    [8---13]
lần 2:                              [13-------------21]
chờ tiếp:                                            [21---26]
~~~

Với việc cần “hoàn tất, nghỉ một khoảng rồi tiếp tục”, `fixedDelay` hợp lý hơn `fixedRate`. Nó có độ dài chu kỳ bằng **duration thực của task + delay**, không phải chỉ delay.

### 3.4. Cron và Trigger: thời điểm theo lịch

Spring có `Trigger` để xác định thời điểm tiếp theo và `CronTrigger` để biểu diễn lịch dạng cron:

~~~java
// Fragment Spring Framework 6.1.3:
ScheduledFuture<?> billing = scheduler.schedule(
        () -> reconcileBilling(),
        new CronTrigger("0 0 2 * * *", ZoneId.of("Asia/Ho_Chi_Minh"))
);
~~~

Cron ở đây theo cú pháp Spring **6 trường** (giây, phút, giờ, ngày trong tháng, tháng, ngày trong tuần), ví dụ trên nhắm **02:00 hằng ngày theo giờ Việt Nam**. `reconcileBilling` là logic ứng dụng chưa định nghĩa. Hãy ghi rõ timezone bằng `ZoneId` nếu kết quả phụ thuộc ngày lịch. Cron không tự biến tác vụ thành một job bền vững.

Với `CronTrigger` thông thường, thời điểm tiếp theo được tính dựa trên thông tin hoàn tất trước đó (lenient execution). Khi task kéo dài, các lần kích hoạt bị lỡ có thể được **bỏ qua**, không mặc nhiên chạy bù hết. Ở Spring 6.1.3 có các factory như `CronTrigger.forFixedExecution(...)` và `forLenientExecution(...)` để chọn cách xử lý mốc theo nhu cầu; cần kiểm tra ý nghĩa trước khi dùng, đặc biệt với nghiệp vụ không được bỏ lần chạy.

### 3.5. So sánh nhanh

| Loại lịch | Điểm tính mốc tiếp theo | Tình huống thích hợp |
| --- | --- | --- |
| `schedule(Runnable, Instant)` | Một thời điểm | Nhắc việc một lần, điều phối một bước |
| `scheduleAtFixedRate(task, period)` | Các mốc bắt đầu theo period | Sampling, đồng bộ trạng thái định kỳ với nhịp mong muốn |
| `scheduleWithFixedDelay(task, delay)` | Sau khi lần trước hoàn tất thêm một khoảng delay | Cleanup/batch đơn giản không cần nhịp bắt đầu cố định |
| `schedule(task, CronTrigger)` | Lịch ngày/giờ theo cron, zone và trigger context | Công việc hằng ngày, giờ hành chính, ngày trong tuần |

**Không dùng fixedRate nếu bạn kỳ vọng auto-overlap một task để “đuổi kịp” backlog.** Trong `ScheduledThreadPoolExecutor`, cùng một periodic series không overlap. Muốn xử lý nhiều công việc song song, thiết kế hàng đợi tác vụ và worker pool riêng, đồng thời kiểm soát việc nhân bản side effects.

## 4. Bằng chứng từ Java 17: ScheduledExecutorService chạy task hẹn giờ

Chương trình thuần JDK sau giúp hiểu phần nền Spring đang dùng: lập lịch một task trả dữ liệu sau delay, rồi đăng ký một task lặp `fixedDelay`. Sử dụng `CountDownLatch` để quan sát **ít nhất ba lần chạy**, không phụ thuộc việc thread in log theo thứ tự ngẫu nhiên.

Lưu thành `JdkScheduledExecutorDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public final class JdkScheduledExecutorDemo {

    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newScheduledThreadPool(1);

        try {
            ScheduledFuture<String> once =
                    scheduler.schedule(
                            () -> "one-shot-ready",
                            20, TimeUnit.MILLISECONDS);

            System.out.println("value="
                    + once.get(5, TimeUnit.SECONDS));

            CountDownLatch three = new CountDownLatch(3);

            ScheduledFuture<?> periodic =
                    scheduler.scheduleWithFixedDelay(
                            three::countDown,
                            0, 20, TimeUnit.MILLISECONDS);

            try {
                if (!three.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "periodic task did not run 3 times");
                }
                System.out.println("threeRunsObserved=true");
            } finally {
                periodic.cancel(false);
            }
        } finally {
            scheduler.shutdown();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                scheduler.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac JdkScheduledExecutorDemo.java
java JdkScheduledExecutorDemo
~~~

**Đầu ra do `main` in khi executor hoạt động bình thường:**

~~~text
value=one-shot-ready
threeRunsObserved=true
~~~

Giải thích:

1. `schedule(Callable<String>, ...)` tạo `ScheduledFuture<String>`; `get(5, SECONDS)` chờ task chạy và nhận giá trị.
2. `scheduleWithFixedDelay(three::countDown, ...)` thực hiện callback lặp; mỗi lần chạy giảm latch một đơn vị cho đến khi bằng 0.
3. `three.await(...)` chỉ trở về `true` khi **ít nhất ba lần callback đã chạy**. Có thể có thêm lượt gần thời điểm hủy, vì vậy chương trình **không** tuyên bố tổng số execution luôn đúng ba.
4. `periodic.cancel(false)` hủy những lần lập lịch tiếp theo; `false` không yêu cầu interrupt nếu callback đang chạy.
5. `shutdown/awaitTermination` giữ lifecycle gọn. Nếu scheduler không chạy đúng trong 5 giây, chương trình báo lỗi có chủ đích chứ không in kết quả giả.

Chỉ có thread `main` in output. Worker không in bên trong callback, nên chương trình không lệ thuộc thứ tự log giữa các threads.

## 5. Ví dụ Spring Framework 6.1.3 hoàn chỉnh: dùng bean ThreadPoolTaskScheduler

Ở đây ta chứng minh bằng API **native** và API **Spring** rằng `ThreadPoolTaskScheduler` sử dụng `ScheduledThreadPoolExecutor`, cấu hình `poolSize` và thực thi callback trên scheduler worker.

### 5.1. Cấu trúc Maven

~~~text
spring-task-scheduler-demo/
├── pom.xml
└── src/main/java/demo/
    ├── SchedulerConfig.java
    └── SpringSchedulerDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-task-scheduler-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.3</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.SpringSchedulerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/SchedulerConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
public class SchedulerConfig {

    @Bean("taskScheduler")
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("lesson-sched-");
        return scheduler;
    }
}
~~~

`@Bean("taskScheduler")` đăng ký scheduler để Spring quản lý khởi tạo và đóng. `setPoolSize(2)` chọn **hai scheduler threads** thay vì mặc định một. Trong ví dụ này **không cần `@EnableScheduling`**, vì ta gọi trực tiếp `TaskScheduler.schedule...` từ `main`; `@EnableScheduling` chỉ cần khi muốn Spring tự nhận diện các phương thức `@Scheduled`.

Tệp `src/main/java/demo/SpringSchedulerDemo.java`:

~~~java
package demo;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

public final class SpringSchedulerDemo {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             SchedulerConfig.class)) {

            ThreadPoolTaskScheduler scheduler =
                    context.getBean(
                            "taskScheduler", ThreadPoolTaskScheduler.class);

            ScheduledThreadPoolExecutor nativePool =
                    scheduler.getScheduledThreadPoolExecutor();

            System.out.println("nativeBackend="
                    + (scheduler.getScheduledExecutor()
                    instanceof ScheduledThreadPoolExecutor));
            System.out.println("poolCore=" + nativePool.getCorePoolSize());

            AtomicReference<String> threadName = new AtomicReference<>();

            ScheduledFuture<?> once = scheduler.schedule(
                    () -> threadName.set(
                            Thread.currentThread().getName()),
                    Instant.now().plusMillis(20));

            if (once == null) {
                throw new IllegalStateException("No execution scheduled");
            }

            once.get(5, TimeUnit.SECONDS);

            System.out.println("onSchedulerThread="
                    + threadName.get().startsWith("lesson-sched-"));

            CountDownLatch twice = new CountDownLatch(2);

            ScheduledFuture<?> repeated =
                    scheduler.scheduleWithFixedDelay(
                            twice::countDown, Duration.ofMillis(30));

            try {
                if (!twice.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "repeated task did not run twice");
                }
                System.out.println("twoRunsObserved=true");
            } finally {
                repeated.cancel(false);
            }
        }
    }
}
~~~

Chạy từ thư mục `spring-task-scheduler-demo`:

~~~bash
mvn -q compile exec:java
~~~

**Stdout do chương trình Java in (không tính log Maven):**

~~~text
nativeBackend=true
poolCore=2
onSchedulerThread=true
twoRunsObserved=true
~~~

### 5.2. Vì sao ví dụ này đúng và có thể kiểm chứng?

- Spring quản lý `ThreadPoolTaskScheduler` được tạo trong `SchedulerConfig`. Sau khi bean khởi tạo, `getScheduledExecutor()` trả về backend, còn `getScheduledThreadPoolExecutor()` cho truy cập native implementation ở cấu hình chuẩn.
- `nativeBackend=true` cho thấy backend thực tế là `ScheduledThreadPoolExecutor`, không chỉ tương thích interface `ScheduledExecutorService`.
- `poolCore=2` phản ánh giá trị `setPoolSize(2)` đã khai báo. Đây là **core pool size**, không phải số task đã chạy hoặc worker hiện đang hoạt động.
- `schedule(..., Instant)` đăng ký callback một lần; callback lấy tên **chính thread đang chạy**. Prefix `lesson-sched-` do bean cấu hình, vì vậy `onSchedulerThread=true`.
- `scheduleWithFixedDelay(..., Duration)` đăng ký callback lặp, latch quan sát **ít nhất hai lần**, sau đó `cancel(false)` ngăn các lần lặp về sau. Chương trình không in tên thread hay timestamp phụ thuộc môi trường.
- `try-with-resources` đóng `AnnotationConfigApplicationContext` và để Spring quản lý shutdown của scheduler, thay vì tạo một pool mới cho mỗi lần gọi.

**Giới hạn test:** Những lệnh `get(5, SECONDS)` và `await(5, SECONDS)` là giới hạn chờ phòng lỗi. Nếu máy bị đình trệ quá 5 giây, chương trình có thể báo lỗi timeout; đây là tình huống không hoàn tất được tác vụ, không phải một stdout bổ sung cần “sửa” để khớp.

## 6. Tích hợp @Scheduled: chỉ bật khi cần annotation-driven scheduling

Spring hỗ trợ viết method có `@Scheduled` và tự đăng ký lịch lúc ApplicationContext sẵn sàng. Để bật:

~~~java
// Fragment cấu hình, cần import Spring annotations.
@Configuration
@EnableScheduling
public class SchedulingConfig {

    @Bean("taskScheduler")
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(3);
        scheduler.setThreadNamePrefix("jobs-");
        return scheduler;
    }

    @Bean
    public CleanupJob cleanupJob() {
        return new CleanupJob();
    }
}
~~~

Method nghiệp vụ nằm trong bean được container quản lý:

~~~java
// Fragment trên class riêng; cần import @Scheduled.
public class CleanupJob {

    @Scheduled(fixedDelay = 5000)
    public void cleanup() {
        // Cleanup xong, đợi 5 giây rồi lặp lại.
    }

    @Scheduled(cron = "0 0 3 * * *", zone = "Asia/Ho_Chi_Minh")
    public void refreshDailyIndex() {
        // 03:00 hằng ngày theo múi giờ đã chọn.
    }
}
~~~

Các đoạn ở mục này là **mảnh kiến trúc**, không thuộc project `SpringSchedulerDemo` độc lập ở phần 5. Trong app thật cần import `EnableScheduling`, `Scheduled`, `Bean`, `Configuration`, `ThreadPoolTaskScheduler` và đặt class đúng file/package.

### Cách Spring tìm scheduler cho @Scheduled

Theo Javadoc `@EnableScheduling` của Spring 6.1.3, Spring tìm một `TaskScheduler` bean duy nhất trong context hoặc bean có tên chuẩn **`taskScheduler`**; cũng có khả năng tìm `ScheduledExecutorService` theo quy tắc tương ứng. Nếu không có scheduler phù hợp, framework có thể tạo **default local single-thread scheduler**.

Vì thế:

- Khai báo bean tên `taskScheduler` là cách trực tiếp để routing cho `@Scheduled` thông thường.
- Nếu có **nhiều scheduler beans**, cấu hình lựa chọn rõ ràng, ví dụ `@Scheduled(scheduler = "criticalScheduler", fixedRate = 5000)` khi dùng Spring 6.1+ hoặc thông qua `SchedulingConfigurer`.
- Đừng suy luận có một bean tên `businessExecutor` hay `ioExecutor` thì `@Scheduled` tự dùng nó. Executor cho `@Async` và scheduler cho `@Scheduled` là hai bài toán lựa chọn khác nhau.

`@Scheduled` có thể được khai báo trên method trong lớp `@Configuration` theo Javadoc `@EnableScheduling`. Đây là **quy tắc của @Scheduled**, không nên nhầm với giới hạn riêng của `@Async` trên methods thuộc lớp `@Configuration`.

### 6.1. @Scheduled không có tham số và kết quả thường bị bỏ qua

Một scheduled method thông thường không nhận tham số; trường hợp phổ biến nhất là `void`. Đừng khai báo scheduled callback cần một đối số chưa được Spring cung cấp rồi kỳ vọng hệ thống tự inject argument vào mỗi lần chạy.

Trong Spring 6.1, scheduled methods có hỗ trợ thêm các reactive return types với quy tắc riêng. Nhưng với việc học scheduler truyền thống, hãy tập trung vào **`Runnable`/`void` callback**; đừng xem việc return một `CompletableFuture` từ scheduled method là chắc chắn một “job đã chờ đến khi Future hoàn tất”.

### 6.2. @Scheduled và @Async có thể thay đổi ý nghĩa hoàn tất

Ví dụ một method `@Scheduled` lập tức gọi một `@Async` service rồi return:

~~~java
// Fragment: reportService là một Spring bean khác có method @Async.
@Scheduled(fixedDelay = 5000)
public void triggerReport() {
    reportService.generateAsync();
}
~~~

Trong tình huống này, scheduled callback có thể kết thúc **ngay sau khi nộp** công việc; `fixedDelay` khi đó tính từ lúc callback hoàn tất, **không nhất thiết** từ lúc báo cáo thật hoàn thành trên async executor. Nhiều công việc báo cáo có thể chồng nhau dù bản thân callback trên scheduler không overlap.

Nếu yêu cầu **không có hai job nghiệp vụ chạy đồng thời**, cần cơ chế backpressure/lock/queue hoặc chờ completion theo thiết kế, thay vì chỉ dựa vào `fixedDelay` ở callback gửi việc.

## 7. Sizing: tại sao ThreadPoolTaskScheduler khác ThreadPoolTaskExecutor?

Cả hai đều tạo pool bean, nhưng API và backend khác nhau:

| Điểm | `ThreadPoolTaskScheduler` | `ThreadPoolTaskExecutor` |
| --- | --- | --- |
| Vai trò chính | Lên lịch một lần hoặc định kỳ | Thực thi task async do caller nộp |
| Backend thường dùng | `ScheduledThreadPoolExecutor` | `ThreadPoolExecutor` |
| Interface Spring chính | `TaskScheduler` | `TaskExecutor` / `AsyncTaskExecutor` |
| Thời điểm bắt đầu | Theo delay, fixedRate, fixedDelay, cron trigger | Theo lúc nộp, worker/queue |
| Số worker cấu hình chính | `setPoolSize(int)`; mặc định **1** | `corePoolSize`, `maxPoolSize`, `queueCapacity` |
| Queue | Delayed queue gắn với `ScheduledThreadPoolExecutor`, về cơ bản **không giới hạn cố định** | Thường có queue cấu hình theo capacity |
| Task chạy ở đâu? | **Chính scheduler thread(s)** | Worker thread(s) của executor |
| Hủy/tình trạng | `ScheduledFuture` | `Future` hoặc thông qua API khác |
| Rủi ro nổi bật | Task dài làm trễ lịch; pending delayed tasks chiếm bộ nhớ | Queue dồn, pool quá tải, rejection, task chậm |

`ScheduledThreadPoolExecutor` trong Java 17 hoạt động như fixed-size pool với `corePoolSize` threads và **unbounded delayed queue**. Vì vậy thay đổi `maximumPoolSize` theo phong cách `ThreadPoolExecutor` **không hữu ích** cho backend này. Đừng tìm `setMaxPoolSize`/`setQueueCapacity` của `ThreadPoolTaskExecutor` để áp vào scheduler như thể hai class có cùng cấu trúc quản lý queue.

Nếu số lượng lịch tăng không kiểm soát, unbounded delayed queue có thể dẫn đến **retention bộ nhớ**; scheduler này không tạo ra độ bền hay khả năng tự phân phối jobs. Hãy giới hạn số lịch được tạo, quản lý hủy và lưu trạng thái ở hệ thống phù hợp khi cần.

### 7.1. Chọn poolSize theo workload

`setPoolSize(1)` phù hợp nếu rất ít job, chạy nhanh và không yêu cầu đồng thời. `setPoolSize(4)` cho phép những task khác nhau sử dụng nhiều scheduler threads, nhưng không giúp một task đang chờ I/O tự hoàn tất sớm.

Với task CPU-bound, số worker hợp lý phụ thuộc lõi CPU và tải khác. Với blocking I/O, nhiều scheduler worker có thể giúp chạy các job khác nhưng vẫn phải đặt timeout cho HTTP/SQL. Việc tăng poolSize quá lớn có thể tạo thêm contention và kéo dài queue/side effects.

Một cách tổ chức thường hữu ích:

~~~text
TaskScheduler (ít thread, điều phối giờ chạy)
      |
      +--> nhẹ: cập nhật cache/metric nhanh trên scheduler worker
      |
      +--> nặng: nộp một đơn vị việc sang TaskExecutor/queue riêng
                    |
                    +--> TaskExecutor workers + timeout + backpressure
~~~

Nếu tách việc nặng như vậy, phải lưu ý **ScheduledFuture chỉ đại diện callback đã schedule**, không nhất thiết đại diện toàn bộ công việc mà callback gửi sang một executor khác. Cần theo dõi Future hoặc job ID ở hệ thống xử lý thật.

### 7.2. Scheduling không phải durable queue

`ThreadPoolTaskScheduler` làm việc trong bộ nhớ của **một JVM**. Khi process restart, lịch tạo động bằng code có thể mất nếu không được đăng ký/lưu lại. Nếu ứng dụng chạy ba replicas và mỗi replica có `@Scheduled`, công việc có thể chạy **ba lần**, không tự có global single leader.

Với tác vụ không được phép trùng hoặc mất, hãy cân nhắc:

- Database-backed job state và distributed lock/leader election có timeout, fencing phù hợp.
- Quartz với job store phù hợp hoặc một bộ điều phối/queue bền vững.
- Idempotency keys, deduplication, transactional outbox khi side effects quan trọng.
- Monitoring “missed runs”, retries có giới hạn, reconciliation sau downtime.

Không dùng riêng bean scheduler làm đảm bảo “exactly once” hoặc “cluster-wide scheduling”.

## 8. ScheduledFuture: hủy và quan sát đúng

Khi gọi `TaskScheduler.schedule...`, Spring thường trả `java.util.concurrent.ScheduledFuture<?>`. Đừng nhầm Future này với một lời hứa rằng task luôn chạy đúng mốc đã đặt.

### 8.1. Một lần chạy

Với `schedule(Runnable, Instant)`, `future.get()` trả `null` nếu callback hoàn tất bình thường; nếu callback thất bại, Spring có thể chuyển exception theo cơ chế xử lý lỗi của scheduler. Với `schedule(Runnable, Trigger)`, việc trả `null` có thể xảy ra nếu trigger không định ra lần kích hoạt nào; hãy xem hợp đồng return của overload cụ thể.

### 8.2. Lịch lặp không có “giá trị cuối” tự nhiên

Với `scheduleAtFixedRate` hoặc `scheduleWithFixedDelay`, Future đại diện **chuỗi lần chạy định kỳ**. Một chuỗi có thể tiếp tục lâu dài cho đến khi bị hủy hoặc scheduler shutdown; vì vậy **không gọi `future.get()` vô thời hạn** rồi mong nó trả kết quả “tick tiếp theo”.

~~~java
// Fragment: periodic là ScheduledFuture<?> từ scheduleAtFixedRate(...).
boolean canceled = periodic.cancel(false);
boolean done = periodic.isDone();
~~~

`cancel(false)` yêu cầu ngừng các lần kích hoạt tiếp theo mà không cố interrupt callback đang chạy. `cancel(true)` thử interrupt trong những implementation hỗ trợ; task phải hợp tác với interrupt, và I/O bên dưới không tự rollback. Không dùng cancellation làm một lời bảo đảm side effect chưa xảy ra.

### 8.3. remove-on-cancel và bộ nhớ delayed queue

`ScheduledThreadPoolExecutor` của JDK có chính sách `setRemoveOnCancelPolicy(boolean)`. Khi bật, các delayed tasks đã cancel có thể được lấy ra khỏi queue sớm hơn, giảm retention nếu ứng dụng hủy rất nhiều lịch đang chờ.

~~~java
// Fragment sau khi bean scheduler đã được khởi tạo.
scheduler.getScheduledThreadPoolExecutor()
        .setRemoveOnCancelPolicy(true);
~~~

Ở một số phiên bản Spring, method convenience `ThreadPoolTaskScheduler.setRemoveOnCancelPolicy(true)` tồn tại nhưng đã deprecated; Javadoc hướng dẫn dùng native accessor khi phù hợp. Đừng bật policy bằng cách sửa một instance chưa khởi tạo hoặc nhầm với queue capacity của executor thường.

### 8.4. Shutdown policies

`ScheduledThreadPoolExecutor` có các chính sách như `setContinueExistingPeriodicTasksAfterShutdownPolicy` và `setExecuteExistingDelayedTasksAfterShutdownPolicy`. Chúng ảnh hưởng liệu lịch lặp hoặc tác vụ một lần đang chờ có được tiếp tục chạy sau `shutdown()` hay không.

Không tự đặt `true` cho mọi chính sách và mong shutdown ứng dụng nhanh. Thay vào đó, xác định job nào được phép hoàn tất, có cần lưu tiến độ để resume, và có deadline dừng hợp lý. Với Spring, tham số lifecycle của bean và đóng `ApplicationContext` liên quan trực tiếp đến hành vi dọn scheduler.

## 9. Error handling: Spring không hoàn toàn giống JDK thuần

Đây là một khác biệt quan trọng khi chọn scheduler.

### 9.1. JDK ScheduledExecutorService thuần

Với `ScheduledThreadPoolExecutor.scheduleAtFixedRate`/`scheduleWithFixedDelay`, nếu **một lần chạy ném exception chưa được xử lý**, các lần chạy tiếp theo của cùng periodic task **bị ngừng**, và `ScheduledFuture.get()` có thể ném `ExecutionException`. Đây là hợp đồng của JDK Java 17.

Để quan sát, lưu thành `JdkScheduledFailureDemo.java`:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class JdkScheduledFailureDemo {

    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        AtomicInteger attempts = new AtomicInteger();

        try {
            ScheduledFuture<?> repeated =
                    scheduler.scheduleAtFixedRate(() -> {
                        attempts.incrementAndGet();
                        throw new IllegalStateException("boom");
                    }, 0, 10, TimeUnit.MILLISECONDS);

            try {
                repeated.get(5, TimeUnit.SECONDS);
                System.out.println("unexpected-success");
            } catch (ExecutionException ex) {
                System.out.println("cause="
                        + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("attempts=" + attempts.get());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~bash
javac JdkScheduledFailureDemo.java
java JdkScheduledFailureDemo
~~~

Đầu ra:

~~~text
cause=IllegalStateException
attempts=1
~~~

Lần đầu ném `IllegalStateException`, JDK Future giữ exception và không chạy những lần định kỳ tiếp theo.

### 9.2. Spring ThreadPoolTaskScheduler mặc định

Spring có lớp bọc error handling cho scheduled Runnables. Theo `TaskUtils`, **mặc định**:

- Tác vụ **lặp**: lỗi được log, thường **bị suppress** để lần tiếp theo còn có thể chạy.
- Tác vụ **one-shot**: lỗi được log rồi **propagate**, vì caller có thể mong đọc lỗi từ `Future`.

Do đó không nên suy luận đơn giản “một exception trong `@Scheduled(fixedRate=...)` chắc chắn dừng lịch” chỉ từ hợp đồng JDK thuần. **Spring wrapper có thể bắt/suppress exception trước khi nó tới ScheduledThreadPoolExecutor.**

Có thể cài chính sách qua `setErrorHandler(...)`:

~~~java
// Fragment: scheduler là ThreadPoolTaskScheduler chưa initialize.
scheduler.setErrorHandler(error -> {
    // Log kèm job ID, metric/alert theo chính sách ứng dụng.
    // Nếu cần fail-stop, chủ động chọn cách propagate phù hợp.
});
~~~

Ví dụ handler trên **không ném lại lỗi**, nên nó đang thực hiện chính sách **suppress**. Nếu ứng dụng đòi hỏi dừng lịch sau lỗi, phải thiết kế rõ việc propagate/cancel và đảm bảo alert; nếu đòi hỏi chạy tiếp, phải có retry budget/idempotency để không lặp mãi lỗi có side effects.

**Cảnh báo:** `ErrorHandler` không phải đường xử lý mọi loại failure. Nếu method scheduled chỉ gửi một tác vụ sang executor khác, lỗi trong task thật có thể xuất hiện ở Future/handler **của executor kia**, không phải trong callback hẹn giờ.

### 9.3. Rejection tại điểm schedule

Khi executor đã shutdown hoặc không nhận thêm task, `schedule(...)` có thể ném **`TaskRejectedException`** của Spring (JDK native ném `RejectedExecutionException`). Lỗi này xảy ra **ngay tại điểm đặt lịch**, trước khi caller nhận được `ScheduledFuture`.

~~~java
// Fragment trong nơi điều phối công việc.
try {
    ScheduledFuture<?> handle =
            scheduler.schedule(() -> doWork(), Instant.now());
    storeHandle(handle);
} catch (org.springframework.core.task.TaskRejectedException ex) {
    reportScheduleFailure(ex);
}
~~~

`doWork`, `storeHandle` và `reportScheduleFailure` là hàm ứng dụng chưa được khai báo; đoạn này chỉ minh họa vị trí bắt lỗi. Không log “job đã được lên lịch” nếu lời gọi đã bị từ chối.

## 10. Lifecycle, pause/resume và ngữ cảnh thực thi

### 10.1. Bean lifecycle

Khi tạo scheduler bằng `@Bean`, container quản lý các callback khởi tạo, kết thúc và sự kiện context. Với project Java `main`, dùng `try-with-resources` đóng `AnnotationConfigApplicationContext` là cách dọn worker. Với ứng dụng web/Boot, hãy đảm bảo quá trình shutdown có chính sách rõ ràng cho task đang chạy.

Spring Framework 6.1 bổ sung **pause/resume** và cơ chế graceful shutdown qua lifecycle của `ThreadPoolTaskScheduler`. Điều này giúp điều phối hoạt động trong app, nhưng pause không phải freeze JVM hoàn hảo, không biến scheduler thành queue bền vững và không thay thế thiết kế xử lý công việc chưa hoàn tất.

### 10.2. Context propagation

Một worker scheduler là **thread khác request thread**. MDC, request attributes, Spring Security context và transaction của caller **không tự xuất hiện đúng** trong scheduled callback. Đặc biệt, việc sử dụng `InheritableThreadLocal` không phải giải pháp chung cho pool tái sử dụng workers: giá trị kế thừa lúc tạo thread, không phải mỗi lần job chạy.

Với scheduler chạy lặp mỗi giờ/ngày, nên thiết kế job tự lấy **dữ liệu và security context phù hợp ở thời điểm chạy**, dùng principal/service account được cấp quyền theo chính sách, và mở transaction boundary riêng cho job nếu cần.

Không lưu `HttpServletRequest`, entity session hoặc connection vào một `Runnable` chạy sau nhiều giờ. Truyền ID bất biến hoặc một job specification tối thiểu và truy xuất dữ liệu lại khi chạy.

### 10.3. Scheduler không quyết định độ chính xác của cron trong mọi tình huống

Cron liên quan đến timezone và lịch tường, nên khi múi giờ chuyển DST, có thể có giờ không tồn tại hoặc giờ lặp. Cron trigger phải được kiểm thử theo zone và version; không giả định 24 giờ luôn có 24 lần chạy ở mọi múi giờ.

Nếu task chậm và `CronTrigger` ở chế độ lenient, một số mốc lịch có thể bị bỏ qua. Với nghiệp vụ cần xử lý từng kỳ, hãy lưu watermark/job-period ID và tự lập kế hoạch catch-up hợp lệ, thay vì chỉ dựa vào số lần callback scheduler đánh thức.

## 11. Quan sát hệ thống và xử lý khi lịch trễ

### 11.1. Các metric nên ghi nhận

- **Scheduled lag**: chênh lệch giữa thời gian dự kiến và thời điểm task thật bắt đầu.
- **Execution duration**: thời gian task chiếm scheduler thread; phân biệt với thời gian toàn bộ job nếu task gửi việc sang pool khác.
- **Active worker** và **pool size**: `getActiveCount()`, `getPoolSize()` của scheduler theo thời gian.
- **Delayed queue depth**: kích thước queue native và số lịch chờ; cân nhắc cancel retention.
- **Failures**: số lần lỗi ở callback, số lần retry, số lần schedule bị từ chối và tình trạng downstream.
- **Missed run / duplicate run**: kỳ hạn bỏ lỡ, chạy lặp lại do redeploy, chạy trùng giữa replicas.

Với backend chuẩn có thể đọc:

~~~java
// Fragment sau khi scheduler đã initialize.
int activeWorkers = scheduler.getActiveCount();
int liveWorkers = scheduler.getPoolSize();

int delayedQueueDepth =
        scheduler.getScheduledThreadPoolExecutor()
                .getQueue().size();
~~~

Các số liệu này là **snapshot tức thời**; không suy ra SLA chỉ từ một lần đọc. Một queue dài chưa chắc có nghĩa pool nghẽn vì queue còn chứa lịch **chưa đến hạn**. Đo thêm những task **đã đến hạn nhưng phải chờ**, và phân biệt số task scheduled với số task executable.

### 11.2. Tình huống điều tra: @Scheduled không chạy

Giả sử method annotated `@Scheduled` không xuất hiện log trong vài phút. Kiểm tra theo thứ tự:

1. `@EnableScheduling` có được bật đúng application context hay chưa?
2. Bean chứa `@Scheduled` có được Spring container quản lý và khởi tạo duy nhất không?
3. Scheduler mà annotation đang chọn có đúng tên/qualifier không?
4. `setPoolSize(1)` có một task khác đang giữ worker quá lâu không? Kiểm tra thread dump/active count.
5. Method có exception và Spring error handler đang log/suppress không, hay chính sách tùy chỉnh đang dừng schedule?
6. Cron expression, timezone và thời gian hiện tại có phù hợp không? Có rơi vào DST hoặc lịch không có fire time không?
7. Context có đang shutdown/pause không? Có bean scheduler bị đóng sớm không?
8. Ứng dụng nhiều replicas có log ở instance khác mà bạn đang bỏ sót không?

Đừng vội tăng poolSize trước khi xác định task nào đang giữ worker và đang chờ tài nguyên gì.

## 12. Chọn công cụ phù hợp

| Nhu cầu | Lựa chọn cân nhắc |
| --- | --- |
| Hẹn một việc ngắn sau một khoảng delay | `ThreadPoolTaskScheduler` hoặc `ScheduledExecutorService` |
| Chạy việc định kỳ trong một app Spring | `ThreadPoolTaskScheduler` + `@Scheduled` |
| Lịch cron có timezone và cấu hình DI | Spring `CronTrigger` / `@Scheduled(cron=..., zone=...)` |
| Chạy nhiều task được submit tức thời, cần queue capacity và pool tuning riêng | `ThreadPoolTaskExecutor` |
| Điều phối lịch rồi xử lý việc nặng | `TaskScheduler` kích hoạt + worker executor/queue riêng có backpressure |
| Sử dụng Jakarta EE managed threads | `DefaultManagedTaskScheduler` hoặc managed scheduled executor |
| Cần task durable, cluster coordination, persistence, retry | Quartz/job store, workflow engine, broker/durable queue và idempotency |
| Tận dụng virtual threads trên JDK 21+ | `SimpleAsyncTaskScheduler` hoặc executor virtual-thread phù hợp; đánh giá bản Spring/JDK và semantics khác |

**Phân biệt `SimpleAsyncTaskScheduler` với `ThreadPoolTaskScheduler`:** Spring 6.1 có lựa chọn scheduler phù hợp virtual threads của JDK 21, với một scheduler thread kích hoạt task execution khác, nhưng fixed-delay có đặc điểm riêng trên scheduler thread. Không lấy hành vi này áp sang `ThreadPoolTaskScheduler` truyền thống; hai implementation có thiết kế khác nhau.

## 13. Những nhầm lẫn thường gặp

1. **“`ThreadPoolTaskScheduler` là một `ThreadPoolTaskExecutor` có thêm timer.”** Không đúng. Scheduler bao `ScheduledThreadPoolExecutor`, có API và queue semantics khác.
2. **“Task được scheduler đánh thức rồi chạy trên worker pool tách biệt.”** Không mặc định. `ThreadPoolTaskScheduler` chạy callback trên chính scheduler threads.
3. **“Pool mặc định đủ cho mọi job.”** Mặc định một thread; task chạy lâu có thể làm các lịch khác trễ.
4. **“`setMaxPoolSize(100)` là cách tăng scheduling concurrency.”** Không đúng với `ScheduledThreadPoolExecutor`; chỉnh `setPoolSize` của Spring scheduler.
5. **“Fixed rate bảo đảm bắt đầu đúng mỗi 5 giây dù task mất 10 giây.”** Sai. Lần sau có thể bắt đầu muộn; cùng periodic JDK task không overlap.
6. **“Fixed delay tính từ lúc bắt đầu task.”** Sai. Delay được tính sau khi lần trước kết thúc.
7. **“Cron tự chạy bù tất cả mốc bị bỏ qua.”** Sai. Tùy trigger semantics; lenient trigger có thể bỏ mốc.
8. **“`@Scheduled` chắc chắn có executor riêng nếu đã khai báo `@Async`.”** Sai. Hai cơ chế chọn tài nguyên riêng.
9. **“`@Scheduled` trong Spring luôn dừng lặp khi một lần callback ném exception.”** Không chắc. Spring mặc định log/suppress nhiều lỗi của repeating tasks.
10. **“`ScheduledFuture.get()` của periodic task sẽ trả mỗi khi có tick.”** Sai. Một Future đại diện cả chuỗi; có thể không bao giờ hoàn tất bình thường.
11. **“Đã cancel Future nên chắc chắn ngắt HTTP/SQL.”** Sai. `cancel(true)` chỉ thử interrupt; thư viện I/O và worker phải hợp tác.
12. **“Delayed queue dài có nghĩa từng ấy job đã tới hạn.”** Sai. Queue còn giữ task chưa đến hạn.
13. **“Mỗi replica tự chạy @Scheduled bảo đảm toàn cluster một lần.”** Sai. Scheduler cục bộ không tự có distributed lock.
14. **“Dùng scheduler là đã có persistent jobs.”** Sai. Cần job store hoặc queue durable.
15. **“Spring @Scheduled và Spring @Async có cùng giới hạn trên @Configuration.”** Sai. Javadoc `@EnableScheduling` cho phép @Scheduled trên method cấu hình, còn @Async có hợp đồng riêng.
16. **“Pause/resume từ Spring 6.1 là thay thế lưu tiến độ job.”** Sai. Lifecycle control không bảo đảm phục hồi các job bị mất sau JVM restart.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `ThreadPoolTaskScheduler` dựa trên implementation nào của JDK?  
**Đáp án:** Theo mặc định, nó bao bọc `ScheduledThreadPoolExecutor`, triển khai `ScheduledExecutorService`.

**Câu 2.** Task của `ThreadPoolTaskScheduler` được thực thi ở đâu?  
**Đáp án:** Trên **chính scheduler thread(s)**, không tự được chuyển sang một pool xử lý khác.

**Câu 3.** Mặc định scheduler có bao nhiêu threads và tăng ở đâu?  
**Đáp án:** Mặc định **một thread**; gọi `setPoolSize(int)` để tăng số scheduler workers khi phù hợp.

**Câu 4.** Fixed rate period 5 giây, task mất 8 giây: hai lần của cùng periodic task có overlap trên `ScheduledThreadPoolExecutor` không?  
**Đáp án:** Không. Lần sau có thể bắt đầu muộn nhưng các lần chạy của cùng một series không chồng lên nhau.

**Câu 5.** Fixed delay 5 giây, task mất 8 giây: mốc bắt đầu tiếp theo gần nhất sau bao lâu tính từ lúc bắt đầu trước?  
**Đáp án:** Khoảng **13 giây** (8 giây chạy + 5 giây chờ), chưa tính scheduler lag.

**Câu 6.** `@Scheduled` có cần `@EnableScheduling` không?  
**Đáp án:** Có nếu muốn Spring tự quét và đăng ký annotation-driven scheduling trong application context, trừ khi infrastructure tương đương được bật bằng cách khác. **Không cần** nếu bạn chỉ gọi trực tiếp `TaskScheduler.schedule` trong code.

**Câu 7.** Vì sao `ScheduledFuture.get()` có thể chặn vô thời hạn?  
**Đáp án:** Với lịch lặp, Future đại diện **cả chuỗi** và có thể không bao giờ hoàn tất bình thường cho đến khi hủy, lỗi hoặc shutdown.

**Câu 8.** Vì sao ScheduledThreadPoolExecutor không có kiểu `maxPoolSize`/`queueCapacity` giống ThreadPoolTaskExecutor?  
**Đáp án:** Backend scheduler dùng pool size theo core thread và delayed queue về cơ bản unbounded; tăng maximum pool size không có hiệu quả tương tự queue bounded của executor thường.

**Câu 9.** Với Spring, repeating task ném exception có chắc bị dừng luôn?  
**Đáp án:** Không; Spring mặc định thường log/suppress lỗi cho repeating tasks, khác với JDK native periodic schedule không có wrapper.

**Câu 10.** Làm thế nào để một scheduled job chỉ chạy một lần trên toàn bộ ba replicas?  
**Đáp án:** Cần cơ chế điều phối cluster như distributed lock/leader election, Quartz job store hoặc hệ thống queue/workflow phù hợp cùng idempotency; `ThreadPoolTaskScheduler` cục bộ không tự giải quyết.

## 15. Tài liệu chính thức

- [Spring Framework 6.1.x — ThreadPoolTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html): backend `ScheduledThreadPoolExecutor`, default poolSize=1, task chạy trên scheduler workers, cấu hình native và lifecycle.
- [Spring Framework 6.1.3 — TaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/TaskScheduler.html): API `schedule`, fixed rate, fixed delay và trigger.
- [Spring Framework 6.1.3 — EnableScheduling Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/annotation/EnableScheduling.html): cấu hình `@Scheduled` và cách chọn bean scheduler.
- [Spring Framework 6.1.3 — CronTrigger Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/support/CronTrigger.html): cron, múi giờ, lenient/fixed execution.
- [Spring Framework 6.1.x — TaskUtils](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/support/TaskUtils.html): mặc định log/suppress lỗi repeating task và propagate one-shot.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): kiến trúc scheduler, `@Scheduled`, `CronTrigger`, task lifecycle và implementations.
- [Java SE 17 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): định nghĩa delay, periodic schedule và `ScheduledFuture`.
- [Java SE 17 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html): delayed queue, fixed-size core pool, no-overlap, exception suppression trong JDK native, remove-on-cancel và shutdown.
- [Java SE 17 — ScheduledFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html): Future cho task có độ trễ, cancel và trạng thái.
