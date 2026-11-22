# Công việc thông thường chạy trên luồng của `ThreadPoolTaskScheduler`

## Mục tiêu

Một hiểu nhầm phổ biến khi dùng Spring scheduling là: **scheduler chỉ canh giờ, sau đó tự động chuyển tác vụ sang một thread pool xử lý khác**. Điều đó **không đúng với cách vận hành thông thường của `ThreadPoolTaskScheduler`**. Theo hợp đồng lớp này trong Spring Framework, nó bọc `ScheduledThreadPoolExecutor`, và **thân `Runnable` được thực thi trên chính các scheduler thread**. Vì vậy một tác vụ đồng bộ lâu hoặc bị blocking có thể chiếm scheduler worker và làm các công việc đến hạn khác phải chờ.

Bài Knowledge thuộc mục **Chọn scheduler** này làm rõ mô hình execution, hệ quả với `@Scheduled`, kích thước pool, `ScheduledFuture`, các kiểu lịch, cách chọn thời điểm tách công việc nặng sang `TaskExecutor`, và ví dụ Java 17+ với Spring Framework để quan sát điều đó một cách có kiểm soát.

Sau bài học, bạn có thể:

1. Giải thích quan hệ `TaskScheduler` → `ThreadPoolTaskScheduler` → `ScheduledThreadPoolExecutor` → scheduler worker.
2. Phân biệt **sắp lịch** và **thực thi** trong cùng pool với việc **chuyển giao** sang pool khác.
3. Giải thích vì sao `poolSize = 1` có thể gây nghẽn khi một scheduled task chạy lâu, và `poolSize` lớn hơn thay đổi điều gì.
4. Hiểu `schedule(Runnable, Instant)`, `scheduleAtFixedRate`, `scheduleWithFixedDelay`, `CronTrigger` và `@Scheduled`.
5. Dùng `ScheduledFuture<?>` đúng cách cho tác vụ một lần, tránh gọi `get()` sai trên công việc lặp mãi.
6. Chạy ví dụ Spring 6.2.12 xác nhận hai task dùng **cùng một scheduler thread** khi pool chỉ có một worker.
7. Thiết kế offload có chủ đích, xử lý lỗi/overload, cleanup, lifecycle, quan sát và tránh các nhầm lẫn về thread context.

**Kết luận cốt lõi:** Với `ThreadPoolTaskScheduler`, một tác vụ scheduled thông thường **không có bước offload mặc định**. Nếu nghiệp vụ cần scheduler chỉ kích hoạt rồi nhanh chóng trả worker, ứng dụng phải **chủ động** gửi phần xử lý sang executor khác hoặc chọn mô hình scheduler có đặc tính khác phù hợp.

## 1. `TaskScheduler` là gì?

`org.springframework.scheduling.TaskScheduler` là abstraction của Spring để lên lịch thực hiện `Runnable` tại một thời điểm hoặc theo chu kỳ. Nó tách **cách mô tả lịch** khỏi implementation scheduler cụ thể.

Một số API tiêu biểu:

```java
ScheduledFuture<?> schedule(Runnable task, Instant startTime);
ScheduledFuture<?> schedule(Runnable task, Trigger trigger);
ScheduledFuture<?> scheduleAtFixedRate(Runnable task, Duration period);
ScheduledFuture<?> scheduleWithFixedDelay(Runnable task, Duration delay);
```

Đây là **chữ ký minh họa từ `TaskScheduler`**, không phải chương trình Java độc lập. Trong chương trình thật, bạn nhận một bean `TaskScheduler`, truyền `Runnable` và thời điểm/chu kỳ tương ứng. Một lần `schedule` thông thường trả `ScheduledFuture<?>` để theo dõi hoặc yêu cầu hủy.

Hai câu hỏi không được nhập làm một:

- **Khi nào chạy?** Quyết định bởi `Instant`, fixed rate, fixed delay hoặc trigger như cron.
- **Chạy ở đâu?** Quyết định bởi scheduler implementation, executor dưới nó và mọi bước delegation mà code tự tạo.

`ThreadPoolTaskScheduler` là một implementation cụ thể. Nó dựa trên `ScheduledThreadPoolExecutor` của JDK, có cấu hình thread name, pool size, lifecycle và một số tùy chọn tiếp nhận/hủy task.

## 2. Cơ chế chính xác của `ThreadPoolTaskScheduler`

Mô hình mặc định:

```text
Caller / @Scheduled infrastructure
                 |
                 v
      ThreadPoolTaskScheduler
                 |
        tính thời điểm chạy
                 |
                 v
      ScheduledThreadPoolExecutor
                 |
        queue các lần chạy
                 |
          +------+------+
          |             |
    scheduler-1     scheduler-2    (nếu poolSize = 2)
          |             |
       task.run()     task.run()
          |             |
      hoàn tất lần chạy, cập nhật lịch nếu là task lặp
```

**Điểm then chốt:** `task.run()` xảy ra **ngay trên một scheduler worker**. Trong đường thực thi thông thường, nó **không tự tạo `ThreadPoolTaskExecutor` riêng** rồi chuyển phần xử lý sang pool đó.

Javadoc `ThreadPoolTaskScheduler` ghi rõ hai đặc điểm:

- Số scheduler thread mặc định là **1**; có thể tăng bằng `setPoolSize(int)`.
- Task execution diễn ra trên **scheduler threads**, không trên một nhóm execution thread riêng. `ScheduledFuture` từ lịch một lần phản ánh sự hoàn thành của chính Runnable đã được cung cấp.

Nếu `poolSize=1`, task A đang chạy sẽ giữ scheduler worker. Task B đến hạn trong lúc A chưa kết thúc vẫn phải đợi một scheduler worker có thể thực thi. B không được cứu chỉ vì B có lịch đến hạn sớm hay ưu tiên nghiệp vụ cao hơn.

```text
poolSize = 1

time ------->

worker-1: [ task A blocking ........................ ][task B][task C]
queue   :             B due, C due -> đợi A kết thúc
```

Lịch xác định thời điểm **đủ điều kiện** chạy; nó không phải cam kết **bắt đầu đúng mili giây** khi toàn bộ worker đang bận.

### Thread pool của scheduler và thread pool của executor

`ThreadPoolTaskScheduler` và `ThreadPoolTaskExecutor` có tên gần nhau, nhưng điểm chính khác nhau:

| Thành phần | Vai trò chính | Bên dưới | Dùng khi |
| --- | --- | --- | --- |
| `ThreadPoolTaskScheduler` | Chạy task ở thời điểm/chu kỳ | `ScheduledThreadPoolExecutor` | `@Scheduled`, `TaskScheduler.schedule`, fixed rate/delay, cron. |
| `ThreadPoolTaskExecutor` | Chạy task được gửi vào một execution pool | `ThreadPoolExecutor` | `@Async`, task nghiệp vụ cần concurrency/queue/rejection riêng. |
| `ConcurrentTaskScheduler` | Adapter cho một `ScheduledExecutorService` có sẵn | Delegate do ứng dụng cung cấp | Tích hợp scheduler được tạo/quản lý từ nơi khác. |
| `SimpleAsyncTaskScheduler` | Mô hình scheduler khác, hướng tới Java 21 virtual threads | Cơ chế scheduling/dispatch riêng | Chọn khi thực sự cần mô hình per-task thread và đã đánh giá ngoại lệ fixed-delay. |
| `DefaultManagedTaskScheduler` | Dùng scheduler do môi trường Jakarta EE quản lý | Managed scheduled executor | Môi trường yêu cầu container sở hữu threads. |

**Không suy ra mọi implementation của `TaskScheduler` đều có cùng mô hình thread.** Bài này đang mô tả cụ thể `ThreadPoolTaskScheduler` của Spring Framework 6.2.x.

## 3. `poolSize` ảnh hưởng gì khi job blocking?

`ThreadPoolTaskScheduler` có một cấu hình quan trọng:

```java
ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(1);
scheduler.setThreadNamePrefix("scheduled-");
```

Đây là snippet khai báo scheduler, cần gắn với lifecycle khởi tạo/quản lý đúng (thường trả từ một phương thức `@Bean` của Spring). Ví dụ đầy đủ ở phần 6 sẽ dùng Spring container để tự khởi tạo và đóng scheduler.

Với `poolSize=1`, dù có nhiều task đến hạn, **tối đa một** scheduled task đang thực thi trong scheduler tại một thời điểm thông thường. Nếu task giữ worker để chờ API hoặc đợi lock, những job khác dùng chung scheduler sẽ bị trễ.

Với `poolSize=4`, có thể có đến khoảng bốn task khác nhau chạy song song trên bốn worker của cùng scheduler, theo scheduling policy. Nhưng:

- Không có nghĩa mỗi cron task luôn sở hữu một worker riêng.
- Không có nghĩa một task lặp với fixed rate được chạy chồng nhiều invocation của **chính cùng periodic registration**. `ScheduledThreadPoolExecutor` không chạy chồng hai lần kế tiếp của cùng một periodic task; lượt sau có thể bắt đầu trễ.
- Không có nghĩa tăng `poolSize` vô hạn sẽ cải thiện throughput. CPU, DB connection, HTTP client, lock và memory vẫn là tài nguyên chung.
- Không có nghĩa fixed delay/fixed rate sẽ giữ chính xác thời gian khi server bận, JVM pause hoặc executor bị shutdown.

`ThreadPoolTaskScheduler` dùng scheduled executor với delayed queue. **Đừng tự áp dụng** tư duy `corePoolSize`, `maxPoolSize`, `queueCapacity` của `ThreadPoolTaskExecutor` cho scheduler. Hai implementation có chính sách queue và thread growth khác nhau. Với scheduled executor, số core thread (`poolSize`) là núm điều khiển quan trọng để chạy các tác vụ đến hạn.

### Ví dụ một scheduler bị chiếm

Giả sử scheduler chỉ có một worker, dùng cho hai job:

- Job A chạy 20 giây vì một HTTP call blocking chưa có timeout tốt.
- Job B là việc ghi heartbeat, cần chạy mỗi 5 giây.

Nếu A bắt đầu trước và chiếm worker 20 giây, B có thể bị trì hoãn qua nhiều thời điểm đến hạn. **Không phải** lỗi của cron; scheduler có lịch nhưng thiếu worker rảnh để chạy code của B.

Tách scheduler riêng cho nhóm quan trọng, tăng pool size có ngân sách, hoặc chủ động offload job blocking là các phương án cần đánh giá. Nếu B phải đáp ứng một deadline cứng, chỉ chỉnh `poolSize` mà không có timeout/overload control ở hạ nguồn thường chưa đủ.

## 4. `ScheduledFuture` đại diện cho điều gì?

Với `ThreadPoolTaskScheduler.schedule(Runnable, Instant)` cho **một lần chạy**, `ScheduledFuture<?>` đại diện cho task thực sự chạy ở scheduler worker.

```java
ScheduledFuture<?> handle = scheduler.schedule(
    () -> doWork(),
    Instant.now().plusSeconds(2)
);

handle.get(10, TimeUnit.SECONDS);
```

Đây là snippet có `scheduler` và `doWork` được định nghĩa trước. Với một task chạy một lần và hoàn tất bình thường, `get` có thể trả `null` vì `Runnable` không có result. Nếu thân `Runnable` bị lỗi theo hợp đồng future, `get` có thể ném `ExecutionException`; nếu caller chờ quá thời hạn, nó ném `TimeoutException`.

**Khác biệt quan trọng với task lặp:** nếu dùng `scheduleAtFixedRate`, `scheduleWithFixedDelay` hoặc cron trigger chạy liên tục, `ScheduledFuture.get()` có thể chờ vô hạn **cho đến khi task lặp bị hủy hoặc kết thúc bất thường**. Không gọi `.get()` để “đợi một vòng cron hoàn tất” như với one-shot task. Muốn theo dõi từng lần chạy, hãy có cơ chế completion/result riêng cho từng invocation, ví dụ metric, callback, store trạng thái hoặc một `CompletableFuture` một lần.

`ScheduledFuture.cancel(...)` là yêu cầu hủy các lần chạy tương lai hoặc cố hủy lần đang chạy theo semantics implementation và khả năng interruption của task. Nó **không tự bảo đảm** JDBC query, socket I/O hay tác dụng phụ nghiệp vụ được rollback.

Nếu scheduled method chỉ **gửi** một task khác tới executor rồi return, future của scheduler phản ánh **việc gửi** đã hoàn tất, không nhất thiết phản ánh task được gửi đã xử lý xong. Hãy tách hai completion handles khi thiết kế kiểu offload.

## 5. `@Scheduled` có dùng `ThreadPoolTaskScheduler` không?

Spring cho phép gắn `@Scheduled` lên method và kích hoạt bằng `@EnableScheduling` trong application context phù hợp. Hạ tầng `ScheduledAnnotationBeanPostProcessor` tìm các method được đánh dấu để đăng ký lịch với scheduler đã chọn.

Ví dụ:

```java
@Configuration
@EnableScheduling
class SchedulingConfiguration {
    @Bean("taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("scheduled-");
        return scheduler;
    }
}

@Component
class CleanupJob {
    @Scheduled(
        fixedDelay = 5,
        timeUnit = TimeUnit.SECONDS,
        scheduler = "taskScheduler"
    )
    public void cleanup() {
        // Nếu method này thực hiện blocking I/O,
        // scheduler worker vẫn bị chiếm cho tới khi method return.
    }
}
```

Đây là **cấu hình minh họa**, chưa phải chương trình độc lập: cần imports, component scanning/đăng ký bean và hạ tầng scheduling. Thuộc tính `scheduler` của `@Scheduled` cho phép chỉ rõ scheduler bean bằng qualifier hoặc bean name (được Spring hỗ trợ từ 6.1). Nếu chỉ có một scheduler rõ ràng, Spring cũng có các quy tắc chọn mặc định; **không nên dựa vào tên thread mặc định để suy đoán** bean thực sự được dùng khi có nhiều scheduler.

Một điểm quan trọng: **`@EnableScheduling` khác `@EnableAsync`**.

- `@EnableScheduling` kích hoạt việc tìm `@Scheduled` và đăng ký job theo lịch.
- `@EnableAsync` kích hoạt interception cho `@Async` ở Spring proxy mode.
- Thêm `@Scheduled` **không tự động** khiến thân method `cleanup()` chạy qua một `@Async` executor khác.
- Nếu cùng một method mang `@Scheduled` và `@Async`, cần xét ranh giới interception, executor, thứ tự xử lý và lỗi một cách tường minh; bài này khuyến nghị tách bean scheduling khỏi bean xử lý async để dễ kiểm soát.

Trong code chạy được ở phần 6, ta gọi `scheduler.schedule(...)` **trực tiếp bằng API** nên **không cần `@EnableScheduling`**. `@EnableScheduling` chỉ cần khi muốn Spring tự tìm và đăng ký method `@Scheduled` qua annotation.

## 6. Ví dụ Java 17+ chạy được: hai task tranh một scheduler worker

Ta kiểm chứng quan hệ **schedule và execute dùng cùng worker** bằng hai one-shot tasks. Cách kiểm tra không dựa vào `Thread.sleep` hoặc đo độ lệch thời gian bất định: dùng `CountDownLatch` giữ task A tại một điểm xác định, rồi gửi task B khi A đang chiếm worker của scheduler.

Với `poolSize=1`, B không thể chạy trước khi A được nhả. Sau đó cả hai hoàn tất; tên thread có tiền tố `scheduled-` và **cùng một worker** được dùng lại.

### Cấu trúc dự án

```text
scheduler-thread-demo/
├── pom.xml
└── src/main/java/example/SchedulerThreadDemo.java
```

Tạo tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>scheduler-thread-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                    <mainClass>example.SchedulerThreadDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo tệp `src/main/java/example/SchedulerThreadDemo.java`:

```java
package example;

import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

public class SchedulerThreadDemo {

    public static class Signals {
        final CountDownLatch firstStarted = new CountDownLatch(1);
        final CountDownLatch releaseFirst = new CountDownLatch(1);
        final AtomicReference<Thread> firstThread = new AtomicReference<>();
        final AtomicReference<Thread> secondThread = new AtomicReference<>();
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean("taskScheduler")
        public ThreadPoolTaskScheduler taskScheduler() {
            ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
            scheduler.setPoolSize(1);
            scheduler.setThreadNamePrefix("scheduled-");
            return scheduler;
        }

        @Bean
        public Signals signals() {
            return new Signals();
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            ThreadPoolTaskScheduler scheduler =
                context.getBean("taskScheduler", ThreadPoolTaskScheduler.class);
            Signals signals = context.getBean(Signals.class);
            Thread caller = Thread.currentThread();

            // Task A thực thi trên scheduler worker rồi chờ chốt.
            ScheduledFuture<?> first = scheduler.schedule(() -> {
                signals.firstThread.set(Thread.currentThread());
                signals.firstStarted.countDown();

                try {
                    signals.releaseFirst.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("First task interrupted", ex);
                }
            }, Instant.now());

            if (first == null) {
                throw new IllegalStateException("First task not scheduled");
            }

            try {
                if (!signals.firstStarted.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("First task did not start");
                }

                // Task B cũng đến hạn ngay, nhưng pool chỉ có 1 worker.
                ScheduledFuture<?> second = scheduler.schedule(
                    () -> signals.secondThread.set(Thread.currentThread()),
                    Instant.now()
                );

                if (second == null) {
                    throw new IllegalStateException("Second task not scheduled");
                }

                // Trước khi nhả A, B không thể lấy worker để chạy.
                boolean secondWaitedBehindFirst =
                    signals.secondThread.get() == null && !second.isDone();
                boolean firstWasStillRunning = !first.isDone();

                signals.releaseFirst.countDown();

                // Chờ completion thật của cả hai Runnable.
                first.get(10, TimeUnit.SECONDS);
                second.get(10, TimeUnit.SECONDS);

                Thread one = signals.firstThread.get();
                Thread two = signals.secondThread.get();

                System.out.println("callerAndSchedulerDifferent="
                    + (one != caller));
                System.out.println("firstOnSchedulerThread="
                    + one.getName().startsWith("scheduled-"));
                System.out.println("secondOnSchedulerThread="
                    + two.getName().startsWith("scheduled-"));
                System.out.println("sameSchedulerWorker=" + (one == two));
                System.out.println("secondWaitedBehindFirst="
                    + secondWaitedBehindFirst);
                System.out.println("firstPendingBeforeRelease="
                    + firstWasStillRunning);
                System.out.println("bothCompleted="
                    + (first.isDone() && second.isDone()));
            } finally {
                // Kể cả khi main bị lỗi, không để task A chờ vô hạn.
                signals.releaseFirst.countDown();
            }
        }
    }
}
```

Chạy từ thư mục `scheduler-thread-demo` (có JDK 17+ và Maven):

```bash
mvn -q compile exec:java
```

**Bảy dòng do chương trình in ra**, theo đúng thứ tự khi chạy thành công:

```text
callerAndSchedulerDifferent=true
firstOnSchedulerThread=true
secondOnSchedulerThread=true
sameSchedulerWorker=true
secondWaitedBehindFirst=true
firstPendingBeforeRelease=true
bothCompleted=true
```

### Tại sao không có race trong kết luận quan trọng?

1. `AnnotationConfigApplicationContext` khởi tạo Spring bean `ThreadPoolTaskScheduler` với `poolSize=1`; scheduler tạo/quản lý pool khi bean được khởi tạo.
2. Main gọi `schedule` tại `Instant.now()`. Scheduler worker nhận task A; task A lưu tham chiếu tới thread của mình, báo `firstStarted` rồi đợi `releaseFirst`.
3. Main chờ `firstStarted.await(...)` nên biết task A **đang giữ scheduler worker**, không chỉ đang nằm trong queue.
4. Main gửi task B cũng đến hạn tại `Instant.now()`. Trong lúc A chưa được nhả, pool chỉ có một worker nên B chưa thể thực thi, bất kể CPU bên ngoài còn rảnh. Hai biến `secondWaitedBehindFirst` và `firstWasStillRunning` được chụp **trước khi nhả chốt**.
5. Main nhả A. A return; task A one-shot hoàn tất. Worker tiếp tục lấy B từ scheduler queue và chạy B.
6. `first.get(...)` và `second.get(...)` chờ **Runnable thực sự hoàn tất**. Chúng không chỉ chờ thao tác “đã thêm lịch vào queue”.
7. Cả hai `Thread` được lưu đều có tên `scheduled-...`; do pool có đúng một worker và hai task tuần tự hoàn thành bình thường nên `sameSchedulerWorker=true`.
8. Chương trình chỉ `println` từ main sau khi cả hai future đã hoàn tất, vì thế thứ tự stdout ổn định.

**Giới hạn của demo:** `CountDownLatch` chỉ là công cụ kiểm soát thứ tự để học/test. Không dùng nó để giữ scheduler worker vô thời hạn trong hệ thống thật. Thời hạn `get(10, SECONDS)` ở caller là biện pháp test failure, **không** tự làm task đang chạy được hủy. Nếu máy quá tải nghiêm trọng, demo có thể timeout thay vì tạo output đúng; không suy diễn đó là quy tắc scheduling thay đổi.

## 7. `fixedRate`, `fixedDelay` và cron khi thân job chiếm scheduler worker

Ba kiểu lịch rất phổ biến:

| Kiểu | Điểm tham chiếu của lần kế tiếp | Hệ quả khi job lâu |
| --- | --- | --- |
| Fixed rate | Khoảng cách mục tiêu giữa các **thời điểm bắt đầu** | Task chạy lâu có thể làm lịch trễ; cùng một periodic registration của `ScheduledThreadPoolExecutor` không chạy chồng các lần kế tiếp. |
| Fixed delay | Chờ một khoảng thời gian **sau khi lần trước kết thúc** rồi mới đến hạn lần sau | Job 20 giây + delay 5 giây → lần sau bắt đầu không sớm hơn khoảng 25 giây tính từ lần bắt đầu trước, chưa tính chờ worker. |
| Cron trigger | Tính các mốc đến hạn theo biểu thức cron và trigger context | Nếu scheduler bận, lần thực thi có thể trễ; chính sách bỏ qua/makeup phụ thuộc trigger và cấu hình. |

Ví dụ API với chu kỳ 5 giây:

```java
scheduler.scheduleAtFixedRate(task, Duration.ofSeconds(5));
scheduler.scheduleWithFixedDelay(task, Duration.ofSeconds(5));
scheduler.schedule(task, new CronTrigger("0/5 * * * * *"));
```

Đây là snippet minh họa; cần import `Duration`, `CronTrigger`, `Runnable` và scheduler đã khởi tạo. Mỗi lần `schedule...` ở đây là **một registration khác** nếu thực thi cả ba dòng. Đừng dùng ví dụ này nguyên xi nếu chỉ muốn một job.

### Không suy diễn fixed rate = đồng thời vô hạn

`ScheduledThreadPoolExecutor` bảo đảm các invocation kế tiếp của **cùng một periodic task registration** không chạy đồng thời, ngay cả khi pool có nhiều worker. Nếu một lượt mất 8 giây còn period là 5 giây, các lượt kế tiếp có thể bắt đầu **trễ**, không tự tạo thêm lượt chạy chồng để “bắt kịp” đúng số giây.

Tuy nhiên, hai scheduled methods khác nhau hoặc hai registration riêng là các task khác nhau. Khi `poolSize > 1`, chúng có thể chạy song song. Nếu `@Scheduled` lặp lại nhiều annotation trên cùng một method, đó cũng có thể tạo các registration độc lập và dẫn đến chồng lấn; cần kiểm tra cấu hình ứng dụng.

### Cron không phải bảo đảm chính xác mốc thời gian

Một mốc cron đến hạn khi scheduler pool không có worker rảnh vẫn có thể bị trễ. Spring có các biến thể `CronTrigger` và chính sách tính mốc tiếp theo theo trigger context; không nên dựa vào giả định rằng mọi mốc bị bỏ lỡ sẽ được thực thi bù đầy đủ. Nếu xử lý định kỳ phải bù dữ liệu theo thời gian thực, hãy lưu mốc xử lý trong database và đọc theo watermark/idempotency thay vì suy từ số lần cron đã gọi.

## 8. Chuyển việc nặng sang `TaskExecutor` khi phù hợp

Nếu scheduled method có I/O blocking dài hoặc xử lý batch, một lựa chọn là làm nó thành **bộ kích hoạt ngắn** rồi giao công việc cho executor chuyên trách:

```text
ThreadPoolTaskScheduler
      |
      +-- mỗi 5 giây kích hoạt tick()
                  |
                  +-- submit job cho businessExecutor
                  |         |
                  |         +--> worker 1: xử lý batch
                  |         +--> worker 2: xử lý batch khác
                  |
                  +-- tick() return sớm, scheduler worker rảnh
```

Ví dụ cấu trúc qua **hai bean Spring khác nhau**:

```java
@Component
class ScheduleTick {
    private final BackgroundJobs jobs;

    ScheduleTick(BackgroundJobs jobs) {
        this.jobs = jobs;
    }

    @Scheduled(
        fixedRate = 5,
        timeUnit = TimeUnit.SECONDS,
        scheduler = "taskScheduler"
    )
    public void tick() {
        jobs.runBatchAsync(); // Gọi qua Spring bean/proxy khác.
    }
}

@Component
class BackgroundJobs {
    @Async("businessExecutor")
    public CompletableFuture<Void> runBatchAsync() {
        // Công việc lâu hoặc blocking thuộc pool businessExecutor.
        doBatchWork();
        return CompletableFuture.completedFuture(null);
    }

    private void doBatchWork() {
        // Logic nghiệp vụ được cài trong ứng dụng thật.
    }
}
```

**Đây là snippet kiến trúc**, không phải ứng dụng tự chạy: cần `@EnableScheduling`, `@EnableAsync`, imports, hai bean scheduler/executor, cấu hình error handling, giới hạn queue/concurrency và nghiệp vụ thực tế. Sử dụng hai bean để lời gọi đi qua async proxy; `this.runBatchAsync()` trong cùng bean sẽ **không tự chuyển sang executor** theo proxy mode mặc định.

**Offload là quyết định nghiệp vụ, không phải mặc định của `ThreadPoolTaskScheduler`.** Nó mang theo hệ quả:

- Fixed delay lúc này chỉ đo khoảng cách sau khi **tick trả về**, không phải sau khi **batch xử lý xong**. Lượt sau có thể gửi thêm batch khi batch trước vẫn chạy.
- Fixed rate có thể gửi task đều hơn khả năng xử lý, gây queue backlog. Cần giới hạn số job in-flight, queue, retry và backpressure.
- `ScheduledFuture` của tick không chứng minh batch đã thành công; phải theo dõi `CompletableFuture`, job ID, metric hoặc kết quả bền vững của batch riêng.
- Nếu `businessExecutor` có `CallerRunsPolicy`, khi bão hòa, call submit có thể khiến scheduler thread **tự chạy batch**, phá kỳ vọng “tick trả về ngay”.
- Nếu executor từ chối task (`TaskRejectedException`), lịch vẫn có thể đang chạy nhưng job nghiệp vụ không được chấp nhận. Xác định cách log/alert/ghi job record hoặc dừng kích hoạt.
- Nếu task quan trọng không được mất qua restart, queue RAM của executor chưa đủ; dùng database job store hoặc broker bền vững với idempotency.

Khi bản thân công việc rất ngắn, không blocking và không cần isolation, chạy trực tiếp trên scheduler worker có thể **đơn giản và hoàn toàn đúng**. Không phải job nào cũng cần thêm một executor.

## 9. Nhiều scheduler hay một scheduler có nhiều threads?

Có ít nhất ba hướng thiết kế:

**Một scheduler, `poolSize` đủ cho nhiều job nhỏ.** Hợp lý khi các job có thời gian ngắn, tải dự đoán được và không cần cách ly mạnh. Dễ quản lý bean và lifecycle, nhưng một nhóm blocking có thể ảnh hưởng nhóm khác nếu dùng hết worker.

**Nhiều scheduler riêng theo nhóm cần cách ly.** Ví dụ scheduler cho heartbeat/maintenance nhẹ và scheduler riêng cho công việc đòi độ trễ nghiêm ngặt. Cách ly worker và queue scheduling tốt hơn, nhưng tăng thread và cấu hình; các scheduler vẫn tranh chấp cùng CPU/DB/heap.

**Scheduler kích hoạt + `ThreadPoolTaskExecutor` xử lý.** Phù hợp khi chỉ cần xác định thời điểm gửi job, còn execution cần concurrency/queue, policy riêng. Đổi lại phải quản lý trạng thái in-flight, rejection, timeout, completion và job durable nếu cần.

| Câu hỏi thiết kế | Dấu hiệu cần chú ý |
| --- | --- |
| Job chiếm worker bao lâu? | p95/p99 duration dài hoặc bị block HTTP/DB. |
| Bao nhiêu job cùng đến hạn? | Cron cùng một giây, đợt nạp dữ liệu buổi sáng. |
| Job nào quan trọng hơn? | Heartbeat/health check không được đứng sau batch dài. |
| Có cần completion gắn với lịch? | Chạy trực tiếp hoặc theo dõi Future xử lý riêng khi offload. |
| Khi quá tải sẽ làm gì? | Chờ, bỏ lượt, trả lỗi, gộp lượt hay retry? |
| Có cần bền vững qua crash? | Dùng persistent job/broker thay vì chỉ scheduling RAM. |
| Tổng thread/connection budget? | Nhiều pool cùng có thể dùng hết connection hoặc CPU. |

## 10. Lỗi và `ErrorHandler` trong scheduled work

Với **one-shot** Runnable, exception có thể được phản ánh qua `ScheduledFuture.get()` dưới dạng `ExecutionException` (tùy lớp wrapper và error handler).

Với **periodic** work, một exception chưa được xử lý có thể ảnh hưởng đến việc lập lịch lần kế tiếp. Spring sử dụng error-handling strategy trong scheduling infrastructure; theo cấu hình mặc định của Spring, lỗi ở repeating tasks thường được log và **suppress** để những lần sau tiếp tục, trong khi one-shot task có semantics truyền lỗi khác. Không đoán rằng mọi exception sẽ dừng cron ngay hoặc mọi exception đều được nuốt.

Khi cần chính sách lỗi cụ thể, cấu hình `ErrorHandler`:

```java
ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(2);
scheduler.setThreadNamePrefix("jobs-");
scheduler.setErrorHandler(error ->
    System.err.println("Scheduled job failed: " + error.getMessage())
);
```

Đây là snippet cấu hình, không độc lập; cần `@Bean` hoặc quản lý lifecycle. Handler trên chỉ ghi lỗi, **không** tự retry/rollback hoặc lưu job status. Một `ErrorHandler` tự ném exception có thể thay đổi hành vi tiếp theo, nên hãy cân nhắc và test chính policy mong muốn.

Trong job định kỳ production, nên có các số liệu: số lần đến hạn, thời điểm **bắt đầu thật**, thời gian chờ scheduler queue, thời gian chạy, success/failure, last successful completion, số lượt bỏ qua, số job đang chạy và độ trễ so với lịch. Đừng chỉ log “cron fired” rồi kết luận batch đã hoàn tất.

### `@Scheduled` không trực tiếp trả Future cho caller

Các method `@Scheduled` thông thường không có caller theo kiểu RPC để trả một Future nghiệp vụ tại mỗi tick. Hạ tầng scheduling quản lý registration. Nếu muốn theo dõi kết quả từng invocation, dùng status record/metric, event, hoặc một completion handle do ứng dụng quản lý. Khi dùng reactive scheduled methods, Spring có hợp đồng riêng về Publisher subscription; không áp dụng suy luận từ Runnable đồng bộ cho mọi return type đặc biệt.

## 11. Shutdown, cancellation và xử lý công việc đang chạy

Scheduler bean do Spring container quản lý có vòng đời startup/shutdown. Trong Spring Framework 6.1+, `ThreadPoolTaskScheduler` còn hỗ trợ pause/resume và graceful shutdown theo lifecycle.

Một số câu hỏi cần thiết trước khi deploy:

1. Khi ứng dụng dừng, có ngừng nhận job mới ngay không?
2. One-shot task đã đến hạn nhưng chưa chạy có cần xử lý không?
3. Periodic job sẽ còn được chạy lại trong khi shutdown hay bị hủy?
4. Task đang chạy được phép hoàn tất trong bao lâu? Nó có hỗ trợ interruption không?
5. Nếu process crash giữa hai lần cron, dữ liệu nào cho biết lần xử lý còn thiếu?
6. Có bảo đảm idempotency để chạy lại một job mà không tạo side effect trùng không?

`setRemoveOnCancelPolicy(true)` (khi hỗ trợ bởi executor) có thể giúp loại task đã hủy khỏi delayed queue, giảm giữ tham chiếu không cần thiết. Các tùy chọn shutdown của `ScheduledThreadPoolExecutor`/Spring lifecycle quyết định task còn chờ được phép chạy hay không; phải đọc cấu hình thực tế, không suy từ việc gọi `cancel()`.

`ScheduledFuture.cancel(true)` có thể gửi yêu cầu interrupt nếu task đang chạy và implementation hỗ trợ, nhưng **không bảo đảm** JDBC call, network socket hoặc nghiệp vụ có side effect được rollback. Với công việc giá trị cao, cần trạng thái bền vững và recovery thay vì giả định scheduler trong RAM là queue đáng tin cậy.

## 12. ThreadLocal, transaction và Spring AOP khi scheduled task chạy

Vì thân task chạy trên scheduler worker, context có tính **thread-bound** của caller không tự đi theo:

- `ThreadLocal` tự định nghĩa, MDC logging, request ID/trace context.
- `SecurityContext` mặc định của request (tùy Spring Security strategy).
- Transaction JDBC/JPA gắn với caller thread.
- Request-scoped state hoặc HTTP request attributes.

`@Scheduled` thậm chí không nhất thiết có một HTTP caller tại thời điểm trigger; đừng giả định có request context từ đầu. Worker có thể được tái sử dụng qua nhiều lần chạy, nên bất kỳ `ThreadLocal` nào job tự set phải được cleanup bằng `try/finally` hoặc cơ chế context propagation có kiểm soát.

Nếu job cần ghi database một cách nguyên tử, hãy đặt transaction ở **bean dữ liệu** được gọi qua Spring proxy hoặc dùng `TransactionTemplate` trên scheduler/worker thread. Một transaction của request không tự được truyền sang scheduled job; không copy `TransactionSynchronizationManager` hay một JDBC connection sang thread khác.

Ví dụ hai bean:

```java
@Component
class ScheduledPoller {
    private final DatabaseWriter writer;

    ScheduledPoller(DatabaseWriter writer) {
        this.writer = writer;
    }

    @Scheduled(fixedDelay = 30, timeUnit = TimeUnit.SECONDS)
    public void run() {
        writer.saveBatch(); // qua transaction proxy của bean khác
    }
}

@Component
class DatabaseWriter {
    @Transactional
    public void saveBatch() {
        // Transaction bắt đầu ở scheduler thread trong mô hình trực tiếp.
    }
}
```

Đây là **mã cấu trúc**, cần imports, `@EnableScheduling`, `@EnableTransactionManagement`, transaction manager, data access và bean registration đúng. Nó cũng cho thấy nếu `saveBatch` là một transaction dài, scheduler worker bị giữ tới khi method return. Có thể chủ động offload sang executor nếu cần tách concurrency, nhưng transaction phải được mở trên worker thực sự xử lý dữ liệu, không ở thread submit.

## 13. Những sai lầm phổ biến

| Nhận định sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Scheduler chỉ bấm giờ; Spring tự tạo worker khác để chạy job.” | `ThreadPoolTaskScheduler` chạy Runnable ngay trên scheduler threads. | Kiểm tra thread name/stack và thiết kế offload nếu cần. |
| “`poolSize=1` vẫn chạy song song nhiều scheduled jobs.” | Một worker chỉ chạy một Runnable tại một thời điểm. | Tăng worker có ngân sách, hoặc tách pool. |
| “Tăng poolSize bảo đảm job luôn đúng giờ.” | CPU, DB, locks và overload có thể gây chậm. | Đo lag, duration, connection usage và timeout. |
| “Mọi lần fixed rate của một registration đều overlap khi job quá dài.” | `ScheduledThreadPoolExecutor` không chạy chồng lần kế tiếp của cùng periodic task. | Phân biệt nhiều registration với một registration. |
| “`ScheduledFuture.get()` dùng để chờ một vòng cron.” | Future của periodic job thường không complete bình thường sau mỗi lượt. | Có per-run completion/status riêng. |
| “Khai báo `@Scheduled` luôn cần `@EnableAsync`.” | `@Scheduled` dùng `@EnableScheduling`. | Chỉ bật async khi thật sự dùng `@Async`. |
| “Gửi sang executor khác vẫn tính fixed delay từ lúc batch kết thúc.” | Nếu scheduled tick chỉ submit rồi return, scheduler coi tick đã xong. | Theo dõi batch completion và admission control riêng. |
| “`ThreadPoolTaskScheduler` có queueCapacity/maxPoolSize như ThreadPoolTaskExecutor.” | Chúng dựa trên các loại JDK executor khác nhau. | Dùng đúng setPoolSize và hiểu delayed queue. |
| “`@Scheduled` có thể tự lấy transaction từ caller.” | Không có cùng caller thread/transaction. | Mở transaction riêng nơi thực thi nếu cần. |
| “Có `@Async` trong cùng bean nên self-call chắc offload.” | Self-invocation thường bỏ qua Spring proxy. | Gọi qua bean khác/injected proxy. |
| “`CallerRunsPolicy` luôn giữ scheduler rảnh.” | Khi pool đích bão hòa, submitter có thể phải chạy task. | Quản lý rejection và giới hạn inflight. |
| “Exception luôn dừng mọi lượt sau.” | Tùy one-shot/periodic handler của Spring/JDK. | Xác định ErrorHandler và giám sát failures. |
| “Task bị cancel nghĩa side effects tự rollback.” | Cancellation best effort không tự hoàn tác I/O/DB. | Timeout thật, idempotency, transaction và cleanup. |
| “Cron trong RAM bảo đảm xử lý mọi lượt sau restart.” | Lịch/queue không phải persistent job store. | Dùng job store/outbox/broker khi cần durability. |

## 14. Checklist khi chọn scheduler cho một module

1. **Task dài bao lâu?** Tách queue wait và execution time, đặc biệt p95/p99 dưới tải.
2. **Có blocking?** HTTP/JDBC/lock/file operations có timeout và mức concurrency riêng chưa?
3. **Mục tiêu scheduling là gì?** One-shot, fixed delay, fixed rate, cron theo múi giờ hay trigger tùy chỉnh?
4. **Cần bao nhiêu scheduler worker?** `poolSize` hiện tại có đủ cho các job đến hạn trùng nhau không?
5. **Job nào cần isolation?** Heartbeat/health check có bị batch chặn không?
6. **Có chủ động offload không?** Nếu có, kết quả của scheduler future và business future có khác nhau không?
7. **Có overload policy không?** Queue executor bên dưới có thể đầy, caller-runs có thể block scheduler.
8. **Có state bền vững không?** Khi crash/restart hoặc chạy nhiều replica, công việc có thể trùng/bỏ sót không?
9. **Có duplicate scheduling không?** Nhiều application replicas cùng bật cron? Có cần distributed lock/idempotency?
10. **Có đúng context/transaction không?** Không copy ThreadLocal/transaction mù quáng, dọn context trên reused worker.
11. **Có quan sát được không?** Log scheduler name, lag, duration, success/failure, skipped runs, backlog, saturation.
12. **Có shutdown strategy không?** Chờ task đang chạy, cancel future, dọn queue, retry task chưa hoàn tất ra sao?

## 15. Tự kiểm tra kiến thức

**Câu 1.** Một `ThreadPoolTaskScheduler` có `poolSize=1`. Task A đến hạn và chờ HTTP 15 giây; task B đến hạn sau A 2 giây. B có mặc định được chạy ở execution thread khác không?

**Đáp án:** Không. Thân task thông thường chạy trên scheduler worker; một worker đang bận với A làm B phải đợi đến khi có worker rảnh.

**Câu 2.** Gọi `schedule(Runnable, Instant)` và nhận `ScheduledFuture`. Future đó có đại diện cho kết quả `Runnable` đã chạy không, hay chỉ việc đặt lịch?

**Đáp án:** Với one-shot task trên `ThreadPoolTaskScheduler`, future phản ánh completion của chính `Runnable` trên scheduler thread. Chỉ nhận handle không có nghĩa task đã completed, nhưng `future.get()` hoàn tất bình thường chứng tỏ Runnable đã hoàn tất.

**Câu 3.** Nếu `@Scheduled` dùng `ThreadPoolTaskScheduler`, có cần `@EnableAsync` để thân job chạy trên scheduler worker không?

**Đáp án:** Không. `@EnableScheduling` đăng ký lịch. `@EnableAsync` chỉ cần nếu nghiệp vụ còn sử dụng proxy `@Async` cho offload khác.

**Câu 4.** Với một periodic registration fixed rate period 5 giây nhưng một lượt chạy 8 giây, JDK scheduler có tự chồng lượt kế tiếp của **cùng registration** không?

**Đáp án:** Không. `ScheduledThreadPoolExecutor` không thực thi đồng thời các lượt của cùng periodic task; lượt tiếp theo có thể bắt đầu muộn.

**Câu 5.** Tại sao trong ví dụ `secondWaitedBehindFirst=true` mà không cần `Thread.sleep()`?

**Đáp án:** Main chỉ gửi B sau khi A báo đã bắt đầu và đang đợi `releaseFirst`; với một scheduler worker, B không thể chạy trước khi main mở chốt. Đây là quan hệ thứ tự xác định, không phải đo timing ngẫu nhiên.

**Câu 6.** Một scheduled tick chỉ submit batch sang `ThreadPoolTaskExecutor` rồi return. `ScheduledFuture` của tick đã xong có nghĩa batch đã commit database không?

**Đáp án:** Không. Completion của tick chỉ bao phủ hành động scheduling/submission; batch có lifecycle và future/status riêng.

**Câu 7.** Vì sao `ScheduledFuture.get()` không phải cách đợi “vòng thứ nhất” của periodic job?

**Đáp án:** Periodic registration tiếp tục qua nhiều lượt, nên future không hoàn tất bình thường sau mỗi lượt. Dùng per-run completion/metrics hoặc thiết kế job status riêng.

**Câu 8.** Tăng `poolSize` từ 1 lên 8 có giải quyết mọi trễ nếu tất cả task chờ cùng một DB connection pool hai connection không?

**Đáp án:** Không. Worker có thể nhiều hơn nhưng bottleneck chuyển sang database/lock/connection. Cần giới hạn concurrency, timeout và sizing toàn hệ thống.

**Câu 9.** Khi job scheduled cập nhật dữ liệu cần transaction, transaction của HTTP caller có tự đi theo không?

**Đáp án:** Không. Cần mở transaction trên scheduler/worker thread, tốt nhất qua bean dữ liệu `@Transactional` hoặc `TransactionTemplate` phù hợp.

**Câu 10.** `ThreadPoolTaskScheduler` và `SimpleAsyncTaskScheduler` có cùng mô hình thread với mọi loại trigger không?

**Đáp án:** Không. `ThreadPoolTaskScheduler` chạy task trên scheduler threads; `SimpleAsyncTaskScheduler` có mô hình khác, đặc biệt trường hợp fixed delay. Cần đọc Javadoc của implementation được chọn và cân nhắc phiên bản JDK.

### Ghi nhớ

`ThreadPoolTaskScheduler` **vừa canh lịch, vừa thực thi công việc thông thường trên chính scheduler worker**. Với mặc định một thread, một task blocking có thể trì hoãn các task khác. Chọn `poolSize` dựa trên workload đo được; nếu cần scheduler chỉ kích hoạt ngắn rồi xử lý song song, **chủ động offload** qua executor riêng và theo dõi completion, rejection, timeout, overload và durability của phần việc được gửi. Đừng hiểu “đến hạn” là “bảo đảm đã bắt đầu”, hay “đã submit” là “đã xử lý xong”.

### Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — `ThreadPoolTaskScheduler` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html): trực tiếp xác nhận task chạy trên scheduler threads, `poolSize` mặc định 1 và `ScheduledFuture` phản ánh completion.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskScheduler`, `@Scheduled`, trigger, fixed rate/fixed delay, lifecycle và các scheduler implementations.
- [Spring Framework 6.2 — `TaskScheduler` API](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/scheduling/TaskScheduler.html): one-shot và recurring scheduling APIs.
- [Java SE 17 — `ScheduledThreadPoolExecutor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html): periodic executions, worker, cancellation, scheduling delays.
- [Java SE 17 — `ScheduledFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html): future và delay semantics.
