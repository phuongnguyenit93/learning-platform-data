# poolSize mặc định và ảnh hưởng của công việc chạy lâu trong Spring TaskScheduler

## 1. Vấn đề thực tế: một job dài khiến job khác bị trễ

Giả sử ứng dụng Spring có hai công việc định kỳ:

- **Job A:** tổng hợp báo cáo, thường mất vài phút vì phải truy vấn cơ sở dữ liệu và gọi dịch vụ ngoài.
- **Job B:** cập nhật heartbeat hoặc trạng thái đơn hàng mỗi vài giây, cần có độ trễ nhỏ.

Cấu hình ban đầu không định nghĩa scheduler cụ thể, chỉ bật `@EnableScheduling` và đặt `@Scheduled` trên hai method. Môi trường có thể dùng một scheduler **chỉ có một thread**. Khi A giữ scheduler thread để chạy một tác vụ dài, B không thể bắt đầu đúng giờ dù trigger đã đến hạn.

Đây thường không phải lỗi của cron, lỗi của `@Scheduled` hay do một lời gọi `Thread.sleep()` bị sai. Đó là **cạnh tranh tài nguyên**: nhiều scheduled jobs cùng cần worker, nhưng scheduler chỉ có một worker khả dụng.

Câu hỏi cần trả lời:

1. `ThreadPoolTaskScheduler` dùng `poolSize` bao nhiêu nếu không thiết lập?
2. Điều gì xảy ra nếu thời gian chạy của task dài hơn chu kỳ của chính nó hoặc trùng thời điểm job khác?
3. Khi nào nên tăng `poolSize`, tách scheduler hoặc tách phần thực thi dài sang `TaskExecutor`?
4. Làm sao kiểm chứng job bị trễ bởi scheduler mà không đoán theo tên thread hoặc chỉ nhìn cron expression?

**Kết luận quan trọng nhất:** với Spring Framework 6.2, `ThreadPoolTaskScheduler` mặc định có **poolSize = 1**. Nó **chạy task trên chính scheduler thread**, không tự chuyển phần thân task sang một executor độc lập. Nếu một task giữ thread quá lâu, các task cùng scheduler bị trì hoãn. Tuy nhiên, `poolSize=1` không phải mặc định duy nhất của mọi sản phẩm hoặc mọi implementation mang tên scheduler trong toàn hệ Spring.

## 2. TaskScheduler khác ThreadPoolTaskExecutor như thế nào?

Hai abstraction có vai trò khác nhau:

| API / implementation | Trả lời câu hỏi gì? | Nguồn worker | Thuộc tính thường dùng |
| --- | --- | --- | --- |
| `TaskScheduler` | **Khi nào** chạy một Runnable? | Phụ thuộc implementation | Trigger, fixed rate, fixed delay, cron |
| `ThreadPoolTaskScheduler` | Lên lịch và **thực thi** các task trên scheduled executor | `ScheduledThreadPoolExecutor` | `setPoolSize(int)`, thread prefix, error handler |
| `TaskExecutor` | **Ở đâu / bằng cách nào** thực thi một Runnable? | Phụ thuộc implementation | `execute(Runnable)` |
| `ThreadPoolTaskExecutor` | Thực thi và queue các task thông thường | `ThreadPoolExecutor` | `corePoolSize`, `maxPoolSize`, `queueCapacity` |
| `SimpleAsyncTaskScheduler` (Spring 6.1+) | Scheduler đơn giản, phù hợp virtual threads | Một thread điều phối và thread thực thi tùy loại trigger | Không đồng nhất với pool tuning của ThreadPoolTaskScheduler |

**Không nhầm `poolSize` của scheduler với `maxPoolSize` của executor thường.** Khi cần tăng số scheduled jobs có thể chạy song song trên `ThreadPoolTaskScheduler`, dùng `setPoolSize(...)`; không tìm cách sửa `queueCapacity` như ở `ThreadPoolTaskExecutor`. `ScheduledThreadPoolExecutor` dùng một delayed queue và core pool cố định, nên việc đổi `maximumPoolSize` của lớp cha thường không mang lại tác dụng tăng concurrency mong đợi.

### 2.1. Scheduler chạy task trực tiếp trên scheduler thread

Javadoc của `ThreadPoolTaskScheduler` ghi rõ nó bọc `ScheduledThreadPoolExecutor`. Task execution diễn ra trên các scheduler threads, **không phải một thread pool riêng tự sinh thêm cho từng job**.

Hệ quả:

- Một lần chạy 30 giây giữ một worker khoảng 30 giây, kể cả khi phần lớn thời gian là block I/O.
- Nếu chỉ có một worker, một job khác đến hạn trong khoảng đó phải chờ.
- Nếu có hai worker, có thể có hai **scheduled executions độc lập** đang chạy cùng lúc.
- Nếu cả hai worker đều bị giữ bởi hai job dài, job thứ ba vẫn có thể bị trễ.
- Vì vậy tăng poolSize **tăng trần concurrency**, không tự làm giảm thời gian thực hiện của job.

## 3. Mặc định poolSize=1 có phạm vi nào?

Cần phân biệt những con đường tạo scheduler.

### 3.1. Tự tạo ThreadPoolTaskScheduler nhưng không setPoolSize

```java
@Bean("taskScheduler")
public ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setThreadNamePrefix("schedule-");
    return scheduler;
}
```

Đây là **fragment** đặt trong class `@Configuration`, với imports `@Bean` và `ThreadPoolTaskScheduler`. Trong Spring Framework 6.2.1, nếu không gọi `setPoolSize(...)` thì scheduler có **một thread** theo mặc định.

### 3.2. Bật @EnableScheduling nhưng không cung cấp scheduler

Khi `@EnableScheduling` không tìm được scheduler phù hợp qua các cơ chế lookup trong ApplicationContext, Spring có thể tạo **một scheduler cục bộ một thread** để chạy `@Scheduled` jobs. Đừng mặc định rằng đã bật `@EnableScheduling` thì tự động có một pool lớn.

### 3.3. XML task namespace

Trong Spring XML, khai báo:

```xml
<task:scheduler id="taskScheduler"/>
```

nếu không thêm `pool-size` thì task namespace cũng tạo scheduler chỉ có **một thread**. Đặt rõ:

```xml
<task:scheduler id="taskScheduler" pool-size="4"/>
```

để có pool bốn thread cho scheduler do phần tử này khai báo. Đây là fragment XML, cần root `<beans>`, namespace `task` và schema tương ứng.

### 3.4. Spring Boot và hệ sinh thái có thể có mặc định khác

Với Spring Boot dùng scheduler auto-configured dựa trên `ThreadPoolTaskScheduler` (không bật virtual threads), tài liệu Boot nêu kích thước pool mặc định là **một thread**, có thể chỉnh qua property:

```properties
spring.task.scheduling.pool.size=4
spring.task.scheduling.thread-name-prefix=scheduling-
```

Đây là fragment cấu hình Spring Boot và chỉ có tác dụng khi **auto-configured scheduler thực sự được dùng**; một bean `@Bean ThreadPoolTaskScheduler` tự tạo không mặc nhiên nhận lại các properties này.

Với Boot ở phiên bản hỗ trợ và bật virtual threads bằng `spring.threads.virtual.enabled=true` trên Java 21+, implementation tự động có thể là `SimpleAsyncTaskScheduler` và bỏ qua properties pooling. Khi đó không nên gán kết quả của `setPoolSize(...)` trên ThreadPoolTaskScheduler cho scheduler đang chạy thực tế.

**Lưu ý các framework phụ:** Spring Integration, Quartz hoặc scheduler được application server quản lý có thể có chính sách mặc định riêng. Phải kiểm tra implementation và cấu hình đã được Spring resolve trong đúng ApplicationContext, không áp câu “mọi Spring scheduler mặc định một thread” một cách tuyệt đối.

## 4. Một scheduler một thread gây hiện tượng gì?

Xét ba job dùng chung một scheduler một thread:

```text
Tương đối theo thời gian:
 0s      2s      4s      6s      8s      10s
 |-------|-------|-------|-------|--------|

Scheduler thread-1
 [========== JOB A chiếm worker 0s..8s ==========][B][C]
          ^ B đến hạn ở 2s
                    ^ C đến hạn ở 4s
                                  ^ A mới hoàn tất ở 8s

B và C chỉ có thể bắt đầu khi worker có cơ hội nhận chúng.
```

Đây là sơ đồ ý tưởng, **không phải khẳng định chính xác thứ tự bắt đầu của mọi loại trigger**. Với fixedRate/fixedDelay/cron, cách xác định lần kích hoạt tiếp theo và các lần trễ khác nhau. Một số cron triggers có thể tính lần tiếp theo theo thời điểm hoàn tất và **bỏ qua những lần firing đã lỡ**, thay vì đưa tất cả lần lỡ vào queue để chạy bù.

Những hậu quả có thể đo được:

- Job B bị trễ dù logic của B chỉ mất vài mili giây.
- Latency từ thời điểm đến hạn đến thời điểm bắt đầu thực tế tăng.
- Heartbeat, cache refresh, batch và housekeeping có thể xuất hiện log không đều.
- Worker đang block I/O khiến CPU thấp nhưng scheduler vẫn “nghẽn”.
- Nhiều scheduled jobs cộng dồn có thể tạo **schedule drift** và làm SLO bị vi phạm.

**Điểm mấu chốt:** scheduler bị block không nhất thiết xuất hiện như CPU cao; nhìn active threads, task duration và lịch thực tế mới thấy rõ.

## 5. fixedDelay, fixedRate và cron khác nhau khi task chạy lâu

Giả sử một job cần **7 giây** để hoàn tất, trong khi lịch mong muốn là **3 giây**.

| Cách khai báo | Cách quyết định lần tiếp theo | Khi job mất 7 giây |
| --- | --- | --- |
| `@Scheduled(fixedDelay = 3000)` | Chờ **3 giây sau khi lần trước kết thúc** rồi mới đến hạn lần sau | Một chu kỳ từ start tới start khoảng 10 giây, chưa tính scheduler delay |
| `@Scheduled(fixedRate = 3000)` | Đến hạn theo nhịp đều 3 giây từ mốc bắt đầu | Lần chạy sau có thể **bắt đầu muộn** vì lần trước chưa xong; trong một periodic schedule trên ScheduledThreadPoolExecutor, không chạy chồng lấn cùng schedule |
| `@Scheduled(cron = "*/3 * * * * *")` | Theo các mốc cron mỗi ba giây | Hành vi khi chạy lâu/missed firing phụ thuộc trigger và cơ chế reschedule; không mặc định mọi lần bỏ lỡ đều được chạy bù |

### 5.1. fixedDelay

Ví dụ:

```java
@Scheduled(fixedDelay = 3000, initialDelay = 1000)
public void refresh() {
    blockingRefresh();
}
```

Fragment này nằm trên Spring-managed bean và cần `@EnableScheduling`, method `blockingRefresh()` có thật. Nếu `refresh()` mất 7 giây, lần sau không đến hạn trước khoảng 3 giây *sau khi lần trước kết thúc*. Với cùng một fixed-delay registration, tăng poolSize không làm **riêng job này** chạy nhiều bản sao song song; mục tiêu tăng poolSize là giải phóng chỗ cho **các jobs độc lập**.

### 5.2. fixedRate

```java
@Scheduled(fixedRate = 3000, initialDelay = 1000)
public void collectMetrics() {
    longRunningCollection();
}
```

Ở đây nhịp fixed rate tính theo các mốc thời gian mong muốn. Nếu công việc kéo dài hơn period, execution kế tiếp có thể muộn. Với một periodic task đã đăng ký bằng `ScheduledThreadPoolExecutor.scheduleAtFixedRate(...)`, JDK bảo đảm **các lần thực hiện nối tiếp của chính periodic registration ấy không chồng lấn**.

Do đó, đừng khẳng định “đặt poolSize=8 và fixedRate=3s trong khi task chạy 7s sẽ làm tám bản của cùng một registration chạy đồng thời”. Các jobs **khác nhau** hoặc các registration độc lập có thể chạy song song nếu scheduler có đủ threads.

### 5.3. cron

```java
@Scheduled(cron = "0 */5 * * * *", zone = "Asia/Ho_Chi_Minh")
public void everyFiveMinutes() {
    exportSummary();
}
```

Đây là fragment, `exportSummary()` cần tồn tại. Cron biểu diễn các mốc theo lịch và timezone; việc diễn giải missed executions có thể khác với fixedRate, phụ thuộc `CronTrigger` và cách lập lịch lại. Chú ý DST/timezone khi nghiệp vụ dựa vào lịch địa phương và môi trường có chuyển giờ.

Nếu một job chạy 7 phút nhưng cron mỗi 5 phút, không mặc định sẽ có hai bản đồng thời hoặc sẽ “bù” chính xác mọi lần bỏ lỡ. Cần đo behavior implementation đang dùng và thiết kế cơ chế concurrency cho business requirement.

### 5.4. @Scheduled lặp nhiều lần trên cùng method

Spring cho phép khai báo lặp `@Scheduled`. Mỗi declaration có thể tạo một registration/trigger riêng; những registration **độc lập** đó có thể overlap hoặc chạy song song nếu scheduler có đủ worker. Vì thế câu “một scheduled method không bao giờ chạy chồng lấn” là quá rộng: chỉ có thể kết luận hẹp theo **một registration** và semantics thực tế của scheduler.

## 6. Ví dụ runnable chứng minh poolSize=1 gây chậm job khác

Ví dụ kiểm thử bằng **Spring Framework 6.2.1, Java 21 và Maven**, không cần Spring Boot. Ta tạo hai scheduler:

- `singleScheduler`: không gọi `setPoolSize(...)`, để nguyên **mặc định 1**.
- `parallelScheduler`: gọi `setPoolSize(2)`, có **2 scheduler workers**.

Với mỗi scheduler, ta lập lịch **hai tác vụ một lần** vào thời điểm gần `Instant.now()`:

1. Tác vụ **slow** chạy trước rồi đợi `CountDownLatch` để giữ worker.
2. Khi slow đã bắt đầu, lập lịch tác vụ **fast** chỉ đếm xuống một latch.
3. Kiểm tra liệu fast có chạy **khi slow chưa được giải phóng** hay không.
4. Giải phóng slow, đợi cả hai Future hoàn tất, kiểm tra kết quả.

Không dùng `Thread.sleep()` hay suy đoán thứ tự thread. Test đặt điều kiện thời gian đủ lớn để quan sát việc fast có thể bắt đầu trước release trên máy bình thường, và có assertions để phát hiện nếu môi trường vận hành không đủ tài nguyên.

### 6.1. Cấu trúc dự án

```text
scheduler-pool-demo/
├── pom.xml
└── src/main/java/demo/SchedulerPoolDemo.java
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>scheduler-pool-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.1</version>
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
        <version>3.5.0</version>
        <configuration>
          <mainClass>demo.SchedulerPoolDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**Tệp `src/main/java/demo/SchedulerPoolDemo.java`:**

```java
package demo;

import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

public class SchedulerPoolDemo {
    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("singleScheduler")
        public ThreadPoolTaskScheduler singleScheduler() {
            ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
            scheduler.setThreadNamePrefix("single-");
            return scheduler;  // setPoolSize() absent: default is 1.
        }

        @Bean("parallelScheduler")
        public ThreadPoolTaskScheduler parallelScheduler() {
            ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
            scheduler.setPoolSize(2);
            scheduler.setThreadNamePrefix("parallel-");
            return scheduler;
        }
    }

    private static boolean fastStartedWhileSlowBlocked(
            ThreadPoolTaskScheduler scheduler) throws Exception {
        CountDownLatch slowStarted = new CountDownLatch(1);
        CountDownLatch releaseSlow = new CountDownLatch(1);
        CountDownLatch fastStarted = new CountDownLatch(1);

        ScheduledFuture<?> slow = scheduler.schedule(() -> {
            slowStarted.countDown();
            try {
                if (!releaseSlow.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Slow task not released");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Slow task interrupted", ex);
            }
        }, Instant.now());

        try {
            if (!slowStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Slow task never started");
            }
            ScheduledFuture<?> fast =
                    scheduler.schedule(fastStarted::countDown, Instant.now());

            boolean fastRanBeforeRelease =
                    fastStarted.await(300, TimeUnit.MILLISECONDS);
            releaseSlow.countDown();

            if (!fastStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Fast task never started");
            }

            slow.get(5, TimeUnit.SECONDS);
            fast.get(5, TimeUnit.SECONDS);
            return fastRanBeforeRelease;
        } finally {
            releaseSlow.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            ThreadPoolTaskScheduler one =
                    context.getBean("singleScheduler", ThreadPoolTaskScheduler.class);
            ThreadPoolTaskScheduler two =
                    context.getBean("parallelScheduler", ThreadPoolTaskScheduler.class);

            int oneConfiguredCore =
                    one.getScheduledThreadPoolExecutor().getCorePoolSize();
            int twoConfiguredCore =
                    two.getScheduledThreadPoolExecutor().getCorePoolSize();

            boolean oneFast =
                    fastStartedWhileSlowBlocked(one);
            boolean twoFast =
                    fastStartedWhileSlowBlocked(two);

            if (oneConfiguredCore != 1 || twoConfiguredCore != 2 ||
                    oneFast || !twoFast) {
                throw new AssertionError("Unexpected scheduler concurrency");
            }

            System.out.println("defaultCoreSize=" + oneConfiguredCore);
            System.out.println("configuredCoreSize=" + twoConfiguredCore);
            System.out.println("fastBeforeReleasePool1=" + oneFast);
            System.out.println("fastBeforeReleasePool2=" + twoFast);
            System.out.println("bothFastJobsCompleted=true");
        }
    }
}
```

### 6.2. Lệnh chạy và output kiểm chứng

Cần Maven và JDK 21 trở lên. Từ thư mục `scheduler-pool-demo`:

```bash
mvn -q -DskipTests compile exec:java
```

**Stdout đã biên dịch/chạy với Spring Framework 6.2.1:**

```text
defaultCoreSize=1
configuredCoreSize=2
fastBeforeReleasePool1=false
fastBeforeReleasePool2=true
bothFastJobsCompleted=true
```

Diễn giải:

- `defaultCoreSize=1`: bean không setPoolSize có core pool size một thread.
- `configuredCoreSize=2`: bean được cấu hình rõ pool hai workers.
- `fastBeforeReleasePool1=false`: khi slow đang giữ scheduler một thread, fast chưa có worker rảnh để bắt đầu.
- `fastBeforeReleasePool2=true`: scheduler hai thread có worker khác để fast bắt đầu trong lúc slow vẫn chờ.
- `bothFastJobsCompleted=true`: cuối mỗi lượt, cả slow và fast đã thực thi xong; việc fast bị trễ trong pool1 không có nghĩa task fast đã bị bỏ qua hoàn toàn.

Ví dụ dùng **one-shot scheduling** qua `TaskScheduler.schedule(Runnable, Instant)` để cô lập vấn đề pool concurrency, không dùng `@Scheduled`; ý tưởng tranh chấp scheduler threads cũng áp dụng khi các job được `@Scheduled` đăng ký vào cùng `ThreadPoolTaskScheduler`.

Phép thử dùng một cửa sổ 300 ms để quan sát. Một môi trường cực kỳ quá tải hoặc bị pause lâu có thể làm test false negative cho pool2; vì vậy trong production nên đo scheduling delay bằng metrics qua nhiều mẫu, không dùng một boolean như SLO thực tế.

## 7. Cấu hình rõ scheduler trong Java @Configuration

Một ứng dụng dùng `@Scheduled` thực tế thường khai báo:

```java
@Configuration(proxyBeanMethods = false)
@EnableScheduling
public class SchedulingConfig {

    @Bean("taskScheduler")
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(4);
        scheduler.setThreadNamePrefix("app-schedule-");
        scheduler.setErrorHandler(ex ->
                System.err.println("Scheduled job failed: " + ex));
        return scheduler;
    }
}
```

Đây là **fragment** cần import `Configuration`, `EnableScheduling`, `Bean` và `ThreadPoolTaskScheduler`. `setErrorHandler` trong ví dụ chỉ minh họa điểm xử lý lỗi; production cần logging/alert đúng chỗ, tránh coi `System.err` là hệ thống quan sát đầy đủ.

Vì bean có tên `taskScheduler` và type `TaskScheduler`, Spring có một scheduler rõ ràng để sử dụng cho các `@Scheduled` method trong context phù hợp. Dù vậy, nếu dự án có nhiều schedulers hoặc có custom scheduling registrar, phải xác nhận đúng bean được chọn; đừng cho rằng bean vừa khai báo sẽ tự động thay thế mọi scheduler trong mọi context con.

### 7.1. Dùng XML namespace

Nếu ứng dụng giữ cấu hình Spring XML:

```xml
<task:scheduler id="taskScheduler" pool-size="4"/>
<task:annotation-driven scheduler="taskScheduler"/>
```

Đây là **fragment**, cần khai báo namespace `task`, schema và bean definitions phù hợp. `<task:scheduler>` tạo tài nguyên; `<task:annotation-driven>` kích hoạt xử lý `@Scheduled`/các annotation tương ứng khi được cấu hình. Chỉ tạo scheduler bean không tự có nghĩa mọi method annotated được scan và đăng ký.

### 7.2. Chọn scheduler riêng cho từng nhóm việc

Spring Framework 6.1+ cho phép dùng thuộc tính `scheduler` trên `@Scheduled` để chọn bean bằng tên/qualifier:

```java
@Scheduled(fixedDelay = 1_000, scheduler = "quickScheduler")
public void heartbeat() {
    sendHeartbeat();
}

@Scheduled(cron = "0 0 * * * *", scheduler = "batchScheduler")
public void hourlyBatch() {
    performLongBatch();
}
```

Đây là **fragment** trong một Spring-managed class, cần cấu hình hai bean `quickScheduler` và `batchScheduler`, bật `@EnableScheduling` và các method nghiệp vụ có thật. Mỗi nhóm sẽ có scheduler pool và metric riêng. Đặc biệt hữu ích khi job I/O dài có khả năng ảnh hưởng heartbeat hoặc lịch nhỏ cần chạy đều.

Ví dụ định nghĩa bean cho hai nhóm:

```java
@Bean("quickScheduler")
public ThreadPoolTaskScheduler quickScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("quick-");
    return scheduler;
}

@Bean("batchScheduler")
public ThreadPoolTaskScheduler batchScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("batch-");
    return scheduler;
}
```

Đặt fragments trong `@Configuration`, imports phù hợp. Điều quan trọng không phải con số 2 mà là **cách chia tài nguyên theo loại công việc/SLO**, tránh một hàng đợi chung khiến batch dài chặn job quan trọng.

## 8. Scheduler poolSize lớn hơn không giải quyết mọi vấn đề

Nếu job chạy lâu vì chờ database hoặc external API, tăng pool từ 1 lên 4 có thể giúp các job khác bắt đầu sớm hơn. Nhưng nếu tăng concurrency vượt khả năng downstream:

- Bốn job có thể cùng giữ DB connections, gây nghẽn pool JDBC.
- Retry trong nhiều job có thể tạo một đợt bùng nổ lưu lượng.
- Tất cả scheduler threads có thể bị block, dẫn tới delay mới.
- Scheduled tasks có side effect đồng thời có thể ghi đè/chồng dữ liệu.
- Nếu cùng một lịch xuất hiện trên nhiều application instances, tổng concurrency thực tế tăng theo số instance.

Vì vậy quy trình thiết kế là: **đo → xác định bottleneck → điều chỉnh isolation/concurrency → kiểm tra lại SLO và safety**. Không mặc định “pool càng lớn càng nhanh”.

### 8.1. Tính sơ bộ số workers

Một phép ước lượng **chỉ mang tính hoạch định**:

Giả sử có nhiều **jobs độc lập** đến hạn trong mỗi khoảng thời gian, mỗi job chiếm worker trung bình `S` giây và tần suất trung bình `λ` jobs/giây. Tải sử dụng worker trung bình xấp xỉ:

```text
requiredBusyWorkers ≈ λ × S
targetWorkers        > requiredBusyWorkers (có headroom cho burst)
```

Ví dụ nếu 2 scheduled executions độc lập mỗi giây, mỗi execution giữ worker trung bình 1,5 giây, trung bình có khoảng 3 workers bận. Pool 3 workers có thể là mức quá sát ngưỡng; thực tế cần headroom để xử lý sự biến động và tránh queue delay lớn.

Công thức không thay thế phân tích peak concurrency, cron synchronization, thời gian p99, locking và giới hạn DB. Không áp trực tiếp cho một periodic schedule duy nhất với các lần chạy không overlap; đó là tính tải **tổng cộng của nhiều scheduled jobs**.

### 8.2. CPU-bound và I/O-bound

- CPU-bound jobs: vượt quá số core hiệu dụng thường chỉ tăng context switching và contention.
- I/O-bound jobs: tăng workers có thể có ích cho các job độc lập, nhưng phải tôn trọng DB/HTTP connection pool, quota và timeout.
- Critical low-latency jobs: có thể cần scheduler riêng thay vì “đấu” với batch dài trong cùng pool.
- Long-running external calls: đặt timeout ở downstream, không để một network call treo vô hạn và giữ scheduler worker.

## 9. Tránh để scheduler thực thi công việc nặng trực tiếp khi cần điều phối nhẹ

Một thiết kế là dùng scheduler chỉ để **quyết định thời điểm**, còn phần thực thi nặng do `TaskExecutor` khác xử lý.

```text
TaskScheduler ("clock / trigger")
       |
       v
short scheduling callback
       |
       +-- bounded submission --> TaskExecutor ("workers")
                                   |
                                   +-- long-running I/O task
```

Ví dụ fragment:

```java
@Component
public class BatchTrigger {
    private final AsyncTaskExecutor batchExecutor;

    public BatchTrigger(@Qualifier("batchExecutor") AsyncTaskExecutor batchExecutor) {
        this.batchExecutor = batchExecutor;
    }

    @Scheduled(fixedDelay = 5_000, scheduler = "quickScheduler")
    public void trigger() {
        batchExecutor.execute(this::runBatchSafely);
    }

    private void runBatchSafely() {
        // Công việc nặng được chạy trên executor riêng.
    }
}
```

Đây là **fragment**, yêu cầu `@EnableScheduling`, bean `quickScheduler`, bean `batchExecutor` và các imports `@Component`, `@Scheduled`, `@Qualifier`, `AsyncTaskExecutor`.

Lợi ích: scheduling callback không phải chờ toàn bộ batch; scheduler thread nhanh chóng rảnh cho các trigger khác.

**Rủi ro rất quan trọng:** khi callback trả về ngay sau submit, `fixedDelay` đo từ lúc **callback kết thúc**, không phải từ lúc batch thực sự hoàn tất. Nếu batch mất 30 giây và trigger mỗi 5 giây, ứng dụng có thể submit nhiều batch chồng lấn. Phải thêm **admission control**: `Semaphore`, job status/lease, bounded queue, rejection policy, idempotency, deduplication hoặc distributed lock (nếu nhiều instance). Không biến một scheduler nghẽn thành một executor queue vô hạn.

### 9.1. @Async trên @Scheduled có phù hợp?

Gắn `@Async` để chuyển phần chạy sang executor khác cũng có thể giảm thời gian chiếm scheduler thread khi được cấu hình và intercept đúng. Tuy nhiên, khi scheduling callback trả về sớm, nhịp kích hoạt có thể tạo **nhiều execution đang chạy cùng lúc**. Điều này không phủ định bảo đảm no-overlap của một periodic task ở scheduler-level: task được scheduler quan sát ở đây chỉ là **callback gửi việc**, không phải toàn bộ công việc nền.

Vì thế luôn hỏi: **“Tôi đang giới hạn sự chồng lấn của callback hay của job nghiệp vụ thực?”** Đây là hai ranh giới khác nhau.

## 10. Lỗi và đời sống của ScheduledFuture

Khi dùng `TaskScheduler.schedule(...)`, caller nhận một `ScheduledFuture<?>` cho task tương ứng.

Với một one-shot scheduled task:

- `get()` có thể trả sau khi task hoàn tất, hoặc ném exception/cancellation nếu task lỗi/bị hủy.
- `cancel(...)` là yêu cầu hủy theo semantics của Future/implementation, không đảm bảo rollback side effect.
- Nếu scheduler shutdown hoặc không nhận task, lời gọi schedule có thể bị từ chối.

Với **periodic task**:

- `ScheduledFuture.get()` thường **không trở về bình thường** trong lúc chuỗi thực thi định kỳ còn hoạt động; nó chỉ kết thúc qua cancellation/abnormal completion.
- Không nên gọi `get()` vô hạn trên scheduled periodic future chỉ để “đợi một lượt chạy” — caller có thể bị chặn mãi.
- Một exception không được bắt bên trong Runnable định kỳ của JDK `ScheduledThreadPoolExecutor` có thể khiến các lượt tiếp theo bị dừng theo hợp đồng JDK; Spring có thể áp dụng error handler cho scheduled task để ghi log/xử lý khác. Phải kiểm tra implementation và error handling thực tế của ứng dụng.
- `cancel(true)` chỉ thử interrupt nếu implementation hỗ trợ và task phối hợp; không dùng làm cơ chế dừng cưỡng bức chắc chắn.

**Lưu ý cleanup:** ScheduledThreadPoolExecutor có delayed queue. Những delayed tasks bị cancel có thể còn nằm trong queue theo chính sách mặc định cho đến khi đến hạn; cần hiểu `removeOnCancelPolicy` khi lịch nhiều hoặc thay đổi thường xuyên. Đó là câu chuyện queue retention, **không phải** cách tăng số workers.

## 11. Quan sát độ trễ lịch và thời gian chạy

Tăng poolSize nên dựa vào dữ liệu đo được. Tối thiểu cần:

1. **Scheduled fire time** hoặc “lúc đáng lẽ task tới hạn”.
2. **Actual start time** ở worker.
3. **Finish time** của business task.
4. **Scheduler queue delay** = actual start − expected due time, có thể cần mốc do scheduler/trigger cung cấp.
5. **Task runtime** = finish − start.
6. **Active threads/pool size**, backlog, số job bị từ chối/cancel.
7. **Business outcome** và độ trễ hoàn tất end-to-end.

Ví dụ khi chủ động gọi `schedule(task, Instant)`, bạn biết thời điểm yêu cầu nên chạy và có thể lưu nó để ghi metrics khi task bắt đầu:

```java
Instant requestedStart = Instant.now().plusSeconds(10);
scheduler.schedule(() -> {
    Instant actualStart = Instant.now();
    Duration lateness = Duration.between(requestedStart, actualStart);
    recordScheduleLateness(lateness);
    executeBusinessJob();
}, requestedStart);
```

Đây là fragment; cần `scheduler`, imports `Instant`/`Duration`, hai hàm thống kê/nghiệp vụ. Đối với đo duration bên trong một process, `System.nanoTime()` thích hợp hơn để tránh việc wall clock bị điều chỉnh. Đối với cron, expected fire time cần được xác định theo đúng trigger/timezone; **không nên lấy “giờ trong cron expression” rồi tính trừ tùy tiện khi cron có policy skip/missed firing**.

### 11.1. Đừng chỉ nhìn queue size

Bản thân delayed queue có thể chứa các future executions còn lâu mới đến hạn; queue size lớn không đồng nghĩa tất cả là task đã quá hạn đang chờ worker. Cần phân biệt **chưa đến hạn** với **đã đến hạn nhưng chưa được bắt đầu**.

Ngược lại, queue size nhỏ không chứng minh scheduler đúng giờ; một long-running job vẫn có thể chặn mọi task khác nếu poolSize=1.

### 11.2. Log thread name không thay cho metrics

Gắn `threadNamePrefix` giúp chẩn đoán và đọc thread dump, nhưng không dùng tên thread làm logic nghiệp vụ. Sử dụng trace, task ID, start/end timestamps, metrics và audit trạng thái công việc.

## 12. Lựa chọn poolSize và chiến lược theo tình huống

| Tình huống | Hướng tiếp cận | Lưu ý |
| --- | --- | --- |
| Một job nhẹ, hiếm chạy, không có SLO chặt | poolSize=1 có thể đủ | Đo runtime và missed schedule |
| Nhiều jobs độc lập, một job đôi lúc chậm | Tăng poolSize có giới hạn | Tránh một job chặn tất cả |
| Heartbeat/job quan trọng cần đúng giờ | Scheduler riêng cho critical jobs | Theo dõi scheduler latency |
| Batch I/O lâu, dễ chồng lấn | Scheduler nhỏ + bounded TaskExecutor riêng | Phải có cơ chế chống overlap/backpressure |
| CPU-bound jobs dày đặc | Pool theo CPU budget và workload thực | Tránh oversubscription |
| Cron nhiều instance | Leader election/distributed lock/job store | poolSize chỉ giới hạn **mỗi instance** |
| Cần lịch bền vững sau restart/missed trigger | Job store/broker/Quartz tùy yêu cầu | @Scheduled in-memory không phải durable scheduling |
| Spring Boot virtual threads | Kiểm tra SimpleAsyncTaskScheduler thực tế | Pool properties có thể không áp dụng |

**Không có “poolSize tốt nhất cho mọi ứng dụng”.** Con số phải dựa vào số jobs đồng thời, runtime distribution, độ quan trọng của lịch, giới hạn tài nguyên và yêu cầu xử lý sau sự cố.

## 13. Spring Boot cấu hình gì và vì sao property có thể không tác dụng?

Trong ứng dụng Spring Boot, property thường dùng khi Boot auto-configured `ThreadPoolTaskScheduler` với platform threads:

```yaml
spring:
  task:
    scheduling:
      pool:
        size: 4
      thread-name-prefix: "scheduling-"
```

Nhưng nếu ứng dụng có bean `TaskScheduler` tùy chỉnh, cấu hình Boot có thể back off hoặc không áp property này lên bean bạn tự tạo. Cần kiểm tra actual bean type và `getScheduledThreadPoolExecutor().getCorePoolSize()` ở trường hợp `ThreadPoolTaskScheduler`.

Khi Boot hỗ trợ và đã bật virtual threads, auto-configured scheduler có thể thành `SimpleAsyncTaskScheduler`, **không sử dụng pool.size theo cùng cách**. Spring Framework 6.1+ có scheduler này được thiết kế gần với JDK 21 virtual threads: nó dùng một scheduler thread để kích hoạt task và tạo thread thực thi riêng cho nhiều loại trigger, nhưng **fixed-delay tasks đều hoạt động trên scheduler thread** theo mô tả chính thức, nên blocking fixed-delay vẫn cần được đánh giá.

Đừng đọc một property rồi tuyên bố scheduler thật đã có bốn workers. Hãy kiểm tra implementation trong context và concurrency behavior bằng integration test.

## 14. Một job chậm, ba khả năng lỗi khác nhau

### 14.1. Scheduler starvation

- Job A chiếm tất cả scheduler threads.
- Job B đã đến hạn nhưng chưa được worker nhận.
- Chỉ số “schedule lateness” cao, dù body B nhanh.

Giải pháp: poolSize hợp lý, isolation giữa jobs, tránh blocking lâu trực tiếp trong scheduler.

### 14.2. Business execution chậm

- Job B bắt đầu đúng giờ.
- Body B chậm vì query/HTTP/lock.
- Runtime của B cao, scheduler latency có thể vẫn thấp ở giai đoạn đầu.

Giải pháp: tối ưu logic/downstream, timeout, batching, connection pool; chỉ tăng scheduler pool không chữa runtime của B.

### 14.3. Trigger/misfire semantics

- Job đã bỏ lỡ mốc cron khi app downtime hoặc khi lịch quá dày.
- Sau restart không thấy tất cả lần đã lỡ chạy bù.
- Không nhất thiết là scheduler worker bị thiếu; có thể do cơ chế trigger, in-memory registration và policy missed execution.

Giải pháp: xác định semantics chính xác cho cron, durable scheduling, missed-run reconciliation và leader election nếu nghiệp vụ đòi hỏi.

**Đừng đánh đồng ba nhóm lỗi.** Cả ba có thể làm người dùng thấy “job không chạy đúng giờ”, nhưng nguyên nhân và phương án sửa hoàn toàn khác nhau.

## 15. Concurrency, transaction, retry và nhiều instance

Tăng scheduler poolSize cho phép các jobs độc lập chạy gần nhau hơn; vì vậy phải kiểm tra race conditions:

- Hai jobs có thể truy cập cùng một bảng DB hoặc file đồng thời.
- Transaction được gắn với thread thực thi; scheduler workers khác nhau không tự dùng chung một transaction của caller.
- Lặp lại job sau timeout có thể nhân đôi side effect nếu không có idempotency.
- Một job đã bắt đầu có thể tiếp tục chạy dù endpoint đã trả timeout.
- Nếu ứng dụng chạy trên ba pods, mỗi pod có scheduler poolSize=4 thì **không có một giới hạn toàn cụm là 4**. Mỗi node có thể kích hoạt cùng scheduled method. Muốn duy nhất một node chạy, dùng coordination/distributed lock, leader election hoặc scheduler có job store phù hợp.
- Khi scheduling callback submit vào executor khác, số business tasks in-flight có thể lớn hơn poolSize của scheduler rất nhiều; phải giới hạn cả queue và tốc độ nhận việc.

**Độ tin cậy:** Spring `@Scheduled` thông thường không tự cung cấp durable job history, replay missed runs hoặc exactly-once trong cluster. Hệ thống giao dịch/đối soát cần job store/outbox và kiểm soát idempotency tương ứng.

## 16. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ mặc định ThreadPoolTaskScheduler có nhiều thread | Job dài chặn job khác | Xác nhận default 1, cấu hình setPoolSize |
| Tăng `ThreadPoolTaskExecutor.maxPoolSize` để sửa scheduler | Không đổi scheduled executor pool | Chỉnh chính scheduler bean |
| Chỉ khai báo `@EnableScheduling` rồi nghĩ đã có pool lớn | Fallback có thể là một thread | Cấu hình TaskScheduler rõ ràng |
| Tăng poolSize=10 và nghĩ một fixedRate registration có 10 lượt overlap | JDK periodic registration không overlap | Phân biệt một registration với nhiều jobs |
| Coi fixedDelay tương đương fixedRate | Dự đoán sai mốc chạy | Hiểu delay sau finish vs nhịp fixed-rate |
| Nghĩ cron sẽ chạy bù tất cả missed fires | Sai trigger/misfire semantics | Kiểm tra trigger chính xác và durable scheduler |
| Đưa batch dài và heartbeat vào cùng pool 1 thread | Heartbeat trễ | Tách scheduler/đặt concurrency phù hợp |
| Tách batch sang TaskExecutor nhưng không giới hạn submission | Chồng lấn và queue phát triển | Bounded executor, semaphore, job state |
| Thấy CPU thấp thì tăng pool vô hạn | DB/HTTP có thể đã nghẽn | Đo downstream và giới hạn concurrency |
| Chỉ nhìn queue size để đo lịch bị trễ | Delayed queue có future tasks chưa đến hạn | Đo due-time-to-start latency |
| Dùng `get()` vô hạn trên periodic ScheduledFuture | Caller có thể chờ mãi | Dùng metrics/latch cho từng lượt, cancel khi cần |
| Coi Boot property chắc chắn điều khiển custom bean | Property có thể không được áp | Kiểm tra auto-config và bean type |
| Bật virtual threads rồi chỉnh pool.size để tăng threads | SimpleAsyncTaskScheduler bỏ qua pool property | Cấu hình theo đúng implementation |
| Coi scheduler poolSize là giới hạn toàn cluster | Mỗi instance có scheduler riêng | Distributed lock/leader election |
| Tăng concurrency mà quên idempotency/transaction | Race, duplicate side effect | Kiểm thử concurrent jobs và rollback |
| Dùng Thread.sleep() để test overlap | Test dễ flake theo timing | Dùng CountDownLatch, bounded await, assertions |

## 17. Bài tập tự kiểm tra

**Câu 1.** Tạo `new ThreadPoolTaskScheduler()` rồi đăng ký bean mà không gọi `setPoolSize`. Pool size theo Spring Framework 6.2 là bao nhiêu?

Một thread. Đó là mặc định của implementation `ThreadPoolTaskScheduler`, không phải quy tắc áp dụng cho mọi scheduler khác.

**Câu 2.** Một scheduler có poolSize=1. Job A bắt đầu lúc 10:00 và giữ worker 7 phút. Job B đến hạn lúc 10:01. B có chắc bắt đầu đúng 10:01 không?

Không. Nếu B dùng cùng scheduler và cần scheduler worker, nó phải đợi đến khi worker rảnh; nếu B là một trigger cần reschedule, behavior trễ/missed execution còn phụ thuộc loại trigger.

**Câu 3.** Với `fixedDelay=3000ms`, job mất 7000ms. Khoảng start-to-start tối thiểu theo điều kiện lý tưởng là bao nhiêu?

Khoảng 10.000ms: chạy 7 giây rồi đợi thêm 3 giây sau completion. Scheduler contention có thể khiến khoảng thực tế dài hơn.

**Câu 4.** Với một periodic `scheduleAtFixedRate` registration trên `ScheduledThreadPoolExecutor`, tăng poolSize=8 có tự làm các lượt của chính registration đó overlap không?

Không. JDK bảo đảm các lần thực thi liên tiếp của cùng periodic task không overlap; chúng có thể đến muộn khi task chạy lâu hơn period.

**Câu 5.** Nếu tách @Scheduled callback sang một TaskExecutor thì pool scheduler nhỏ có chắc an toàn chưa?

Chưa. Callback có thể submit nhiều công việc trùng nhau trước khi batch cũ xong; phải thêm bounded capacity, backpressure và ngăn overlap nếu nghiệp vụ yêu cầu.

**Câu 6.** Vì sao Java+Spring test trong bài dùng latch thay vì `Thread.sleep(100)`?

Vì latch xác nhận slow đã chiếm worker và kiểm soát lúc nó được giải phóng. Thử nghiệm phân biệt cấu hình pool một và hai worker theo trạng thái có kiểm soát, không trông đợi timing may rủi.

**Câu 7.** Một ứng dụng có ba instances, mỗi instance cấu hình scheduler poolSize=4. Có nghĩa toàn hệ thống chỉ có bốn scheduled jobs cùng chạy?

Không. poolSize điều khiển scheduler trong **một instance**. Nếu cả ba cùng kích hoạt, số executions đồng thời toàn cụm có thể cao hơn; muốn global limit cần coordination riêng.

## 18. Checklist trước khi đưa lịch vào production

- Đã kiểm tra **implementation thực tế** là `ThreadPoolTaskScheduler`, `SimpleAsyncTaskScheduler` hay scheduler khác?
- Đã biết poolSize mặc định hoặc configured thực tế, thay vì chỉ đoán từ property?
- Những jobs nào chia sẻ scheduler, jobs nào cần scheduler/worker riêng?
- Runtime trung bình/p95/p99 của mỗi job là bao nhiêu? Có I/O/lock/DB wait không?
- Có đo schedule due-time-to-start latency và business completion latency riêng?
- FixedDelay/fixedRate/cron được chọn đúng semantics chưa?
- Khi job dài hơn period, chính sách backlog, skip, overlap hoặc dedup đã rõ chưa?
- Nếu callback submit vào executor khác, có bounded queue và admission control không?
- Có timeout ở HTTP/JDBC downstream để scheduler worker không bị treo?
- Có thể tăng scheduler pool mà không làm cạn DB/HTTP connection pool không?
- Có log/metrics cho exceptions, cancels, rejections, shutdown và job outcome?
- Nếu triển khai nhiều nodes, có cần lock/leader election/job store để tránh chạy trùng?
- Khi ứng dụng restart, có yêu cầu replay missed runs hoặc durable job history không?
- Đã có integration test dùng latch kiểm tra contention thay vì chỉ test một method độc lập chưa?

## 19. Kết luận

Với Spring Framework 6.2, **`ThreadPoolTaskScheduler` mặc định chỉ có poolSize=1**. Vì scheduled task thực thi trên chính scheduler thread, một công việc chạy lâu hoặc block I/O có thể khiến **những công việc khác dùng chung scheduler** bắt đầu trễ. Tăng `setPoolSize(...)` cho phép nhiều jobs độc lập chạy đồng thời hơn, nhưng không làm chính một periodic registration của `ScheduledThreadPoolExecutor` tự overlap và không tự khắc phục bottleneck downstream.

Hãy xác minh implementation/default thực tế, phân biệt fixedDelay/fixedRate/cron, đo độ trễ đến lúc worker bắt đầu, tách critical jobs khỏi batch dài khi cần, và kiểm soát duplicate/overlap khi chuyển việc sang executor khác. Với production nhiều instance hoặc job cần replay, poolSize chỉ là một mảnh của bài toán: reliability và coordination phải được thiết kế riêng.

### Tài liệu tham khảo

- [Spring Framework 6.2.1 — ThreadPoolTaskScheduler API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — EnableScheduling API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/annotation/EnableScheduling.html)
- [Spring Framework 6.2 — Scheduled API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html)
- [Java SE 21 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html)
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)