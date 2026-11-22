# scheduleWithFixedDelay() và khoảng nghỉ sau khi hoàn tất

## 1. Mục tiêu và tình huống thực tế

Một ứng dụng Spring định kỳ đồng bộ tồn kho từ đối tác. Một lượt xử lý có khi mất 2 giây, có khi mất 15 giây. Yêu cầu nghiệp vụ là: **sau khi một lượt thực sự hoàn tất, nghỉ thêm 5 giây rồi mới bắt đầu lượt kế tiếp**. Nếu đối tác đang chậm, không muốn tạo một loạt lượt mới bám đuổi lịch cũ.

Đó là ý nghĩa của `TaskScheduler.scheduleWithFixedDelay(...)` trong Spring Framework: thời gian `delay` được tính **từ khi lượt thực thi trước kết thúc đến khi lượt tiếp theo được phép bắt đầu**. Nó không phải chu kỳ giữa hai thời điểm bắt đầu, không phải thời gian ngủ nằm bên trong task, cũng không phải cơ chế tự động tạo luồng nền vô hạn.

~~~text
fixed delay = 5 giây

Lượt 1:  START 10:00:00 ---- xử lý 7 s ---- END 10:00:07
                                                     |
                                                     +-- nghỉ ít nhất 5 s
Lượt 2:                                     START 10:00:12 ---- xử lý 2 s ---- END 10:00:14
                                                                                         |
                                                                                         +-- nghỉ ít nhất 5 s
Lượt 3:                                                                         START 10:00:19 ...

Công thức: start(n+1) >= finish(n) + delay
Thời điểm thực tế còn phụ thuộc tài nguyên scheduler, độ trễ hệ điều hành và tải.
~~~

Đừng hiểu `delay=5s` là “cứ 5 giây một lần”. Với lượt 1 chạy 7 giây, **khoảng giữa hai lần bắt đầu là ít nhất 12 giây**, không phải 5 giây. Nếu lượt 2 chạy 2 giây, khoảng bắt đầu từ lượt 2 đến lượt 3 là ít nhất 7 giây.

Mục tiêu sau bài học:

1. Dùng đúng hai overload `scheduleWithFixedDelay(Runnable, Duration)` và `scheduleWithFixedDelay(Runnable, Instant, Duration)`.
2. Phân biệt **fixed delay**, **fixed rate**, **cron**, `initialDelay` và lịch chạy một lần.
3. Hiểu vì sao một **chuỗi fixed-delay đơn lẻ không chồng lấp chính nó**, nhưng các job khác, annotation trùng và nhiều pod vẫn có thể chạy đồng thời.
4. Biết kiểm soát `ScheduledFuture`, cancel, lỗi nghiệp vụ, timeout, shutdown, pool size và observability.
5. Viết được chương trình Java 17 và ứng dụng Spring Boot minh họa thời điểm kết thúc rồi mới nghỉ.

Phiên bản minh họa: **Java 17, Spring Framework 6.x, Spring Boot 3.3.5**, dùng platform threads và `ThreadPoolTaskScheduler` thông thường. Chi tiết đặc biệt của Java 21 virtual threads được nêu riêng.

## 2. API TaskScheduler trong Spring Framework

`org.springframework.scheduling.TaskScheduler` là abstraction lập lịch của Spring. Nó tách code nghiệp vụ khỏi việc tạo và quản lý `ScheduledExecutorService`/worker threads. Những phương thức quan trọng:

~~~java
// Chữ ký rút gọn của TaskScheduler trong Spring Framework 6.x:
ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Duration delay);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Instant startTime, Duration delay);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Duration period);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Instant startTime, Duration period);

ScheduledFuture<?> schedule(
        Runnable task, Instant startTime);
~~~

Đây là **trích đoạn chữ ký API**, không phải class Java độc lập. Tham số `task` là `Runnable`; `Duration` thuộc `java.time`, `Instant` là mốc thời gian tuyệt đối; `ScheduledFuture<?>` thuộc `java.util.concurrent`.

### 2.1. Bắt đầu càng sớm càng tốt

~~~java
// Snippet trong service đã inject một TaskScheduler.
ScheduledFuture<?> handle = scheduler.scheduleWithFixedDelay(
        () -> refreshInventory(),
        Duration.ofSeconds(5));
~~~

- Lượt đầu **được phép chạy càng sớm càng tốt** khi scheduler có worker, không đợi 5 giây bắt buộc.
- Sau khi `refreshInventory()` kết thúc, scheduler mới tính khoảng nghỉ 5 giây tới lượt sau.
- Nếu scheduler quá tải, không có worker rảnh hoặc đang pause, giờ thực tế có thể muộn hơn.
- `handle` cho phép hủy chuỗi lặp; nó **không chứa kết quả mỗi lượt**.

`refreshInventory` và `scheduler` trong snippet là thành phần ứng dụng giả định. Không có annotation `@EnableScheduling` cũng có thể dùng trực tiếp API `TaskScheduler` miễn là có một scheduler đã khởi tạo/được Spring quản lý.

### 2.2. Chỉ định thời điểm lượt đầu

~~~java
// Snippet trong service đã có TaskScheduler.
Instant firstRun = scheduler.getClock().instant()
        .plus(Duration.ofSeconds(10));

ScheduledFuture<?> handle = scheduler.scheduleWithFixedDelay(
        () -> refreshInventory(),
        firstRun,
        Duration.ofSeconds(5));
~~~

Overload thứ hai dùng `startTime` cho **lần thực thi đầu tiên**, sau đó vẫn đợi 5 giây **từ lúc mỗi lượt hoàn tất**. Nếu `startTime` đã ở quá khứ, task được phép chạy ngay khi có thể. `scheduler.getClock()` giúp thống nhất nguồn thời gian của scheduler; trong ví dụ đơn giản dùng `Instant.now()` cũng được nếu đồng hồ hệ thống tương ứng.

**Không nhầm** `startTime` với một khoảng nghỉ sau mỗi lần chạy. Nếu muốn “đợi 10 giây trước lần đầu, rồi 5 giây sau mỗi lần kết thúc”, đây là cách trực tiếp.

### 2.3. Vì sao dùng Duration thay vì long?

Các overload kiểu `long` theo milliseconds từng tồn tại nhưng đã bị deprecate từ Spring Framework 6.0 để ưu tiên `Duration`. Viết `Duration.ofSeconds(5)` tránh nhầm `5000` là millisecond hay second. Trong ứng dụng có configuration properties, parse chúng thành `Duration` rõ ràng để kiểm tra và tránh đơn vị mơ hồ.

## 3. Fixed delay so với fixed rate và cron

| Cơ chế | Mốc tính lần kế tiếp | Phù hợp khi |
| --- | --- | --- |
| `scheduleWithFixedDelay(task, delay)` | **Kết thúc** lượt n + delay | Poll API/DB, đồng bộ định kỳ, muốn nghỉ sau khi xử lý |
| `scheduleAtFixedRate(task, period)` | **Bắt đầu dự kiến** lượt n + period | Lấy mẫu/heartbeat theo nhịp gần cố định |
| `schedule(task, instant)` | Một thời điểm chỉ định | Chạy một lần, không lặp |
| `@Scheduled(cron = "...")` | Mốc lịch tường minh (giờ/ngày, timezone) | Báo cáo hàng ngày, công việc theo giờ |
| `@Scheduled(fixedDelay = ...)` | Kết thúc invocation trước + delay | Cùng semantics fixed delay trong annotation |

Ví dụ `period/delay=5s`, lượt đầu xử lý 8s:

~~~text
FIXED DELAY:
  start 00:00 -> end 00:08 -> nghỉ 5s -> start ~00:13 -> ...

FIXED RATE trên ScheduledThreadPoolExecutor:
  kế hoạch starts: 00:00, 00:05, 00:10, 00:15...
  lượt đầu kéo dài 8s; lượt sau đến hạn có thể chạy ngay khi lượt đầu xong.
  Các invocation kế tiếp CỦA CÙNG MỘT periodic task không tự chồng lên nhau
  trong ScheduledThreadPoolExecutor, nhưng có thể xảy ra các lượt sát nhau.

CRON:
  ví dụ 02:00 mỗi ngày là mốc wall-clock; chịu ảnh hưởng timezone/DST.
~~~

**Fixed rate không tự có nghĩa “chạy song song một task trên nhiều worker”.** Với JDK `ScheduledThreadPoolExecutor`, các lần chạy liên tiếp của **cùng một periodic task** không overlap, kể cả khi pool có nhiều worker; nhưng nếu chạy lâu hơn period, có thể không còn khoảng nghỉ sau khi hoàn thành. Các scheduled task **khác nhau** có thể cạnh tranh hoặc đồng thời tùy số worker.

**Fixed delay không bù lịch chạy lỡ.** Khi một lượt mất 30 phút, scheduler không tạo 360 lượt để bù 5 giây đã trôi qua. Nó chờ lượt hiện tại kết thúc rồi mới đếm delay để chạy lượt tiếp theo. Đây là đặc tính có ích cho polling tránh dồn tải, nhưng không phù hợp nếu doanh nghiệp cần xử lý đúng **mỗi mốc thời gian lịch sử**. Trường hợp đó cần job ledger/cursor dữ liệu hoặc scheduler nghiệp vụ có khả năng catch-up.

### 3.1. Fixed delay không phải debounce/throttle

- **Debounce:** sau mỗi sự kiện mới, thường dời thời điểm xử lý, hay chỉ xử lý khi không còn event trong một khoảng.
- **Throttle/rate limit:** giới hạn số lần thực thi/số request trong một cửa sổ, có thể chia sẻ giữa nhiều node.
- **Fixed delay:** một chuỗi periodic task; sau khi lượt hiện tại kết thúc mới đếm thời gian nghỉ tới lượt sau.

Nếu server nhận 10.000 event/s, `scheduleWithFixedDelay` không tự giải quyết event ingestion hay backpressure. Nó chỉ quy định thời điểm **bắt đầu** từng lượt của một job định kỳ.

## 4. “Hoàn tất” chính xác là hoàn tất điều gì?

Trong `TaskScheduler` với `Runnable` đồng bộ, “hoàn tất” có nghĩa là **`Runnable.run()` đã trả về hoặc thoát vì exception đã được xử lý theo chính sách scheduler**. Đây **không mặc nhiên** là công việc business thực tế đã xong nếu `run()` chỉ dispatch một việc khác.

### 4.1. Sai lầm: Runnable chỉ submit rồi kết thúc

~~~java
// Anti-pattern: snippet; asyncWorker là service của ứng dụng.
scheduler.scheduleWithFixedDelay(() -> {
    asyncWorker.generateReport(); // Gửi sang executor khác rồi trả về rất nhanh.
}, Duration.ofSeconds(5));
~~~

Nếu `generateReport()` có `@Async` và caller đi qua Spring proxy, `Runnable` chỉ **gửi công việc**. “Lượt hoàn tất” của scheduler tính theo thời điểm **lời gọi gửi task** trả về, không đợi report thực tế xử lý xong. Vì vậy có thể có nhiều report còn đang chạy đồng thời dù scheduler đang dùng fixed delay.

Điều tương tự xảy ra khi:

~~~java
// Snippet: fire-and-forget bên trong một Runnable.
CompletableFuture.runAsync(() -> generateReport(), otherExecutor);
// Runnable gọi runAsync rồi trả về, không chờ completion.
~~~

Giải pháp phải theo **contract nghiệp vụ**: nếu cần các lượt **không overlap** theo hoàn tất thực tế, hãy để phần công việc chính nằm trong `Runnable` đồng bộ, hoặc quản lý một workflow có trạng thái `RUNNING` và không cho dispatch lượt mới khi lượt trước chưa terminal. Có thể `join/get` một Future trong Runnable để đợi, nhưng sẽ **chặn scheduler worker**; cần timeout, interruption, không dùng chính pool bị chặn để chạy những child task đang được đợi, nếu không có nguy cơ starvation/deadlock.

### 4.2. Fixed delay không tự đảm bảo exactly-once

Nếu deployment có 3 pod Spring, mỗi pod có thể đăng ký job fixed-delay riêng và chạy cùng logic trên mỗi JVM. Về mặt scheduler, **mỗi pod có một chuỗi không overlap**; toàn cụm vẫn có thể có 3 lượt xử lý đồng thời. Nếu job phải chạy đúng một instance, dùng distributed lock/lease, DB claim, message broker hoặc scheduler trung tâm, kết hợp idempotency.

Ngay trong một JVM, hai `@Scheduled` annotations trên cùng method (repeatable annotation), hai `TaskScheduler.scheduleWithFixedDelay` calls cho cùng Runnable hoặc hai context/bean instance đăng ký trùng có thể tạo **hai chuỗi độc lập**. “Không overlap” chỉ áp dụng cho **một handle của một periodic scheduling registration**, không phải mọi lời gọi tới cùng method từ bất kỳ đường nào.

## 5. Demo Java 17 độc lập: chứng minh nghỉ sau khi kết thúc

Ta dùng một worker cố định và `CountDownLatch` để giữ **lượt 1 đang chạy**, sau đó đo một khoảng tối thiểu từ lúc lượt 1 kết thúc tới lúc lượt 2 bắt đầu. Không dùng `Thread.sleep` làm bằng chứng và không dựa vào thời điểm ngẫu nhiên của hệ điều hành.

Lưu file **`FixedDelayDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public final class FixedDelayDemo {
    private static void await(CountDownLatch latch, String name)
            throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out waiting for " + name);
        }
    }

    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        AtomicInteger executions = new AtomicInteger();
        AtomicLong firstFinished = new AtomicLong();
        AtomicLong secondStarted = new AtomicLong();

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch secondStartedSignal = new CountDownLatch(1);

        ScheduledFuture<?> handle = scheduler.scheduleWithFixedDelay(
                () -> {
                    int attempt = executions.incrementAndGet();
                    if (attempt == 1) {
                        firstStarted.countDown();
                        try {
                            releaseFirst.await();
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                        } finally {
                            firstFinished.set(System.nanoTime());
                        }
                    } else if (attempt == 2) {
                        secondStarted.set(System.nanoTime());
                        secondStartedSignal.countDown();
                    }
                },
                0, 150, TimeUnit.MILLISECONDS);

        try {
            await(firstStarted, "first start");

            // Khi lượt 1 chưa kết thúc, lượt 2 chưa thể bắt đầu.
            System.out.println("SECOND_DURING_FIRST="
                    + (secondStartedSignal.getCount() == 0));

            releaseFirst.countDown();
            await(secondStartedSignal, "second start");

            System.out.println("SECOND_AFTER_FIRST_END="
                    + (secondStarted.get() > firstFinished.get()));

            long gapNanos = secondStarted.get() - firstFinished.get();
            System.out.println("GAP_AT_LEAST_100_MS="
                    + (gapNanos >= TimeUnit.MILLISECONDS.toNanos(100)));

            System.out.println("TWO_OR_MORE_RUNS="
                    + (executions.get() >= 2));
        } finally {
            releaseFirst.countDown();
            handle.cancel(false);
            scheduler.shutdownNow();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Scheduler did not stop");
            }
        }

        System.out.println("CANCELLED=" + handle.isCancelled());
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac --release 17 FixedDelayDemo.java
java FixedDelayDemo
~~~

Đầu ra các dòng do ứng dụng in:

~~~text
SECOND_DURING_FIRST=false
SECOND_AFTER_FIRST_END=true
GAP_AT_LEAST_100_MS=true
TWO_OR_MORE_RUNS=true
CANCELLED=true
~~~

**Vì sao kết quả xác định?**

- `firstStarted` xác nhận scheduler đã vào lượt 1 trước khi kiểm tra; `releaseFirst` còn đóng nên lượt 1 vẫn chưa kết thúc. Một recurring fixed-delay task chưa thể chạy lượt 2 khi lượt 1 đang xử lý.
- `firstFinished` được ghi ngay trước khi `run()` trả về. Scheduler bắt đầu đếm delay 150 ms **sau khi** task thực sự kết thúc, nên `gapNanos` đo được ít nhất khoảng delay; assertion chỉ dùng ngưỡng bảo thủ 100 ms để tránh khẳng định số đo chính xác ở mức từng millisecond.
- `secondStartedSignal` đánh dấu lượt 2 đã vào method; phép kiểm `TWO_OR_MORE_RUNS` không dựa vào việc lượt 3 có xảy ra hay chưa.
- `cancel(false)` hủy những lần kích hoạt kế tiếp của periodic task. Nó không có nghĩa “mọi tác vụ đã gửi tới DB đều rollback”, và `shutdownNow()` chỉ yêu cầu ngắt các task còn đang chạy.

Demo dùng JDK `ScheduledExecutorService` để thể hiện cùng nguyên lý nền của `ThreadPoolTaskScheduler`; phần Spring chạy được ở mục kế tiếp. Nếu JDK bị thiếu tài nguyên nghiêm trọng khiến các latch timeout, chương trình fail rõ ràng thay vì treo vô hạn.

## 6. Demo Spring Boot: scheduleWithFixedDelay(Runnable, Duration)

Dự án này sử dụng **Java 17, Maven, Spring Boot 3.3.5**. Nó đăng ký `ThreadPoolTaskScheduler` bean, gọi API `TaskScheduler.scheduleWithFixedDelay`, chứng minh khoảng nghỉ bắt đầu **sau lượt 1**. `ApplicationRunner` cố ý chờ bằng latch để in kết quả kiểm chứng rồi hủy recurring schedule; không cần web server, DB hay file ngoài những file liệt kê.

### 6.1. Cấu trúc

~~~text
spring-fixed-delay/
├── pom.xml
└── src/main/java/com/example/scheduler/
    └── FixedDelayApplication.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-fixed-delay</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. FixedDelayApplication.java

~~~java
package com.example.scheduler;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@SpringBootApplication
public class FixedDelayApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(FixedDelayApplication.class, args)) {
            // Sau runner, đóng context và hủy các tài nguyên đã đăng ký.
        }
    }

    @Bean("demoScheduler")
    ThreadPoolTaskScheduler demoScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("fixed-delay-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        return scheduler;
    }

    @Bean
    ApplicationRunner verifyFixedDelay(
            @Qualifier("demoScheduler") TaskScheduler scheduler) {
        return args -> {
            AtomicInteger count = new AtomicInteger();
            AtomicLong finishedFirst = new AtomicLong();
            AtomicLong beganSecond = new AtomicLong();

            CountDownLatch firstBegan = new CountDownLatch(1);
            CountDownLatch release = new CountDownLatch(1);
            CountDownLatch secondBegan = new CountDownLatch(1);

            Runnable task = () -> {
                int n = count.incrementAndGet();
                if (n == 1) {
                    firstBegan.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    } finally {
                        finishedFirst.set(System.nanoTime());
                    }
                } else if (n == 2) {
                    beganSecond.set(System.nanoTime());
                    secondBegan.countDown();
                }
            };

            ScheduledFuture<?> handle = scheduler.scheduleWithFixedDelay(
                    task, Duration.ofMillis(150));

            try {
                if (!firstBegan.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("First run did not start");
                }
                System.out.println("SECOND_WHILE_FIRST_RUNNING="
                        + (secondBegan.getCount() == 0));

                release.countDown();
                if (!secondBegan.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Second run did not start");
                }

                System.out.println("SECOND_AFTER_FIRST_END="
                        + (beganSecond.get() > finishedFirst.get()));
                System.out.println("PAUSE_AT_LEAST_100_MS="
                        + (beganSecond.get() - finishedFirst.get()
                                >= TimeUnit.MILLISECONDS.toNanos(100)));
                System.out.println("RUNS_AT_LEAST_2=" + (count.get() >= 2));
            } finally {
                release.countDown();
                handle.cancel(false);
            }

            System.out.println("HANDLE_CANCELLED=" + handle.isCancelled());
        };
    }
}
~~~

**Ý nghĩa của mã:**

- Bean `ThreadPoolTaskScheduler` được container khởi tạo, quản lý lifecycle và đóng khi context đóng. `setPoolSize(1)` chỉ phục vụ demo tái hiện dễ đọc; production phải chọn theo số task, thời gian xử lý và SLO.
- Không dùng `@EnableScheduling` vì ví dụ gọi **trực tiếp API TaskScheduler**. Annotation `@EnableScheduling` chỉ cần cho cơ chế tìm và đăng ký `@Scheduled` methods.
- `ApplicationRunner` giữ một `ScheduledFuture<?>` để hủy schedule sau khi quan sát đủ hai lần. Nếu không hủy, periodic task có thể tiếp tục chạy cho tới khi scheduler shutdown.
- Các `CountDownLatch` kiểm tra quan hệ giữa lượt đang chạy và lượt kế tiếp, không phụ thuộc `Thread.sleep` hay thứ tự log của nhiều workers.
- `Duration.ofMillis(150)` là thời gian nghỉ **sau** khi lượt trước hoàn tất, không phải chu kỳ giữa hai lần gọi.

### 6.4. Chạy và kết quả

Ở thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Bỏ qua log Boot/Maven, chương trình in:

~~~text
SECOND_WHILE_FIRST_RUNNING=false
SECOND_AFTER_FIRST_END=true
PAUSE_AT_LEAST_100_MS=true
RUNS_AT_LEAST_2=true
HANDLE_CANCELLED=true
~~~

Các dòng này đánh giá tính chất hành vi; không in timestamp tuyệt đối vì timestamp phụ thuộc môi trường. Nếu môi trường scheduler chậm, khoảng nghỉ thực tế **dài hơn** cấu hình vẫn phù hợp semantics fixed delay. Phép đo dùng ngưỡng 100 ms cho delay 150 ms, thay vì khẳng định scheduler luôn chính xác tới từng nanosecond.

## 7. Dùng @Scheduled(fixedDelay) thay cho API trực tiếp

Nếu chỉ cần định kỳ gọi một method đã biết từ lúc ứng dụng khởi động, `@Scheduled` ngắn gọn hơn. Ví dụ trong một ứng dụng Spring Boot đã có `@EnableScheduling`:

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class InventoryPoller {
    @Scheduled(
            initialDelay = 2,
            fixedDelay = 5,
            timeUnit = TimeUnit.SECONDS)
    public void poll() {
        // Thực hiện đồng bộ một lượt; trả về khi lượt kết thúc.
        syncInventory();
    }

    private void syncInventory() {
        // Code nghiệp vụ phải có timeout/observability.
    }
}
~~~

Trong một class `@Configuration`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulingConfig {
}
~~~

Đây là **hai class minh họa có thể đặt vào cùng dự án Spring**, không phải phần của demo chỉ gọi API ở mục 6. Với annotation trên:

- Lần đầu được phép chạy sau `initialDelay=2s` tính từ khi task được đăng ký/chạy scheduler theo lifecycle; không phải “2 giây sau HTTP request đầu tiên”.
- Sau khi `poll()` kết thúc, scheduler đợi `fixedDelay=5s` trước lần kế tiếp. Nếu `poll()` mất 8s, hai lần bắt đầu cách nhau ít nhất khoảng 13s.
- `timeUnit = TimeUnit.SECONDS` làm đơn vị số `2`/`5` rõ ràng. Nếu bỏ thuộc tính này, mặc định của `@Scheduled` là milliseconds.
- Method scheduled thông thường không nhận tham số; tránh block vô hạn, có timeout network/DB và ghi lại tình trạng lỗi.

Có thể dùng `fixedDelayString = "PT5S"` hoặc một property đã được Spring resolve để cấu hình từ môi trường. Khi dùng property bên ngoài, kiểm tra đơn vị, giá trị hợp lệ và profile đang chạy, vì một giá trị âm/không hợp lệ có thể khiến đăng ký lịch thất bại. Nếu thay delay khi ứng dụng đã chạy, không được mặc nhiên cho rằng annotation đã đăng ký tự reschedule ngay; tùy trường hợp cần đăng ký lại hoặc thiết kế trigger động.

### 7.1. Annotation không đồng nghĩa proxy của @Async

`@Scheduled` được Spring scheduling infrastructure phát hiện và đăng ký, trong khi `@Async` thường cần Spring proxy/interceptor. Đừng lấy quy tắc self-invocation của `@Async` rồi khẳng định rằng `@Scheduled` chỉ chạy khi có request đi qua proxy. Scheduler **tự kích hoạt** method theo lịch đã đăng ký. Ngược lại, chỉ khai báo `@Scheduled` mà không bật scheduling infrastructure trong context thì method có thể không được đăng ký.

Nếu một method vừa mang `@Scheduled` vừa mang `@Async`, hoặc method scheduled gọi sang một bean async khác, cần xác minh điểm nào được coi là “kết thúc”. Việc phương thức trả về ngay sau dispatch có thể làm fixed delay chỉ áp dụng cho **gửi việc** chứ không chờ task business đã kết thúc.

### 7.2. Đừng nhầm scheduler bean và executor bean

`spring.task.execution.*` cấu hình async task execution của Spring Boot khi auto-configuration áp dụng; `spring.task.scheduling.*` dành cho scheduler. Một `ThreadPoolTaskExecutor` cho `@Async` không tự biến thành `TaskScheduler` của `@Scheduled`. Khi viết hai lớp công việc, hãy đặt tên bean rõ và cấu hình đúng loại.

Ví dụ Spring Boot khi auto-config scheduler trong môi trường đủ điều kiện:

~~~properties
# Minh họa override do ứng dụng cung cấp; KHÔNG phải default:
spring.task.scheduling.pool.size=3
spring.task.scheduling.thread-name-prefix=poll-
~~~

Nếu ứng dụng đã tự tạo `@Bean ThreadPoolTaskScheduler` bằng setter như mục 6, **đừng** kỳ vọng Boot properties nhất thiết ghi đè số pool do code đã đặt. Hãy kiểm tra bean thực và resolved configuration.

## 8. Có thật sự không overlap?

### 8.1. Trong cùng một periodic registration

Đối với `ThreadPoolTaskScheduler` thông thường, backend là JDK `ScheduledExecutorService/ScheduledThreadPoolExecutor`. Các lần kích hoạt của **một** task được đăng ký qua `scheduleWithFixedDelay` không overlap: lượt kế tiếp chỉ trở nên eligible sau khi lượt trước kết thúc và hết delay. Tăng `poolSize` lên 10 không biến cùng một schedule thành 10 invocation song song.

### 8.2. Giữa các scheduled jobs khác nhau

Hai job `refreshProductCatalog` và `refreshSupplierCatalog` có thể chạy đồng thời nếu scheduler có nhiều worker, vì đó là **hai registrations riêng**. Nếu pool size=1, một job dài sẽ làm job kia chậm dù cả hai có delay riêng. Vì thế fixed delay là một nguyên tắc thời gian *mỗi schedule*, không phải mutex khóa toàn scheduler.

### 8.3. Khi code tách tác vụ qua async executor

Nếu `Runnable.run()` chỉ gửi một Future sang executor khác rồi trả về, lời gọi lịch có thể hoàn thành trong vài millisecond. Business task có thể vẫn chạy khi đến lượt dispatch sau; fixed delay không tự ngăn overlap của **các Future con**.

### 8.4. Giữa các application instances

Mỗi pod/JVM có một scheduler độc lập. Khi chạy nhiều pod, mỗi pod có thể bắt đầu job riêng và tranh cập nhật DB. Nếu chỉ được phép một job toàn cụm, dùng distributed lock/lease, atomic DB claim hoặc message broker. Cần idempotency để xử lý restart/retry, không chỉ dựa vào cron/fixed delay và pool size.

### 8.5. Với virtual threads và SimpleAsyncTaskScheduler

Spring Framework 6.1+ có `SimpleAsyncTaskScheduler` phù hợp định hướng virtual threads. Đặc biệt, fixed-delay tasks của implementation này chạy trên **một scheduler thread**, thay vì mỗi lượt đều được offload ra thread mới như fixed rate/cron. Tài liệu Spring khuyến nghị cân nhắc **fixed rate hoặc cron** với virtual-thread-aligned scheduler, nhất là khi công việc có thể block. Không mang máy móc các giả định về `ThreadPoolTaskScheduler` sang implementation khác chỉ vì cùng interface `TaskScheduler`.

## 9. Exception: phân biệt JDK raw scheduler với Spring wrapper

Đây là một trong những lỗi chẩn đoán quan trọng nhất.

### 9.1. Java ScheduledThreadPoolExecutor thuần

Theo JDK `ScheduledExecutorService.scheduleWithFixedDelay`, nếu một lần chạy của periodic command ném unchecked exception mà không được xử lý, **những lần chạy tiếp theo bị suppressed**. `ScheduledFuture` của chuỗi có thể chuyển sang exceptional completion; gọi `get()` nhận `ExecutionException`. Với chuỗi chạy bình thường chưa dừng, `ScheduledFuture.get()` **không trả kết quả cho từng lượt**, vì periodic task về bản chất chưa hoàn tất.

~~~java
// Snippet JDK, giả định rawExecutor là ScheduledExecutorService.
ScheduledFuture<?> handle = rawExecutor.scheduleWithFixedDelay(
        () -> {
            throw new IllegalStateException("failed");
        },
        0, 5, TimeUnit.SECONDS);

// Sau khi lượt đầu đã lỗi, get() có thể trả ExecutionException
// và lịch không tự khởi động lại.
~~~

### 9.2. Spring ThreadPoolTaskScheduler thông thường

Spring `ThreadPoolTaskScheduler` trang trí repeating `Runnable` bằng xử lý lỗi của Spring. Với error handler mặc định cho **repeating tasks**, Spring thường **ghi log rồi suppress exception**, cho phép các lần tiếp theo vẫn chạy. Vì vậy không được bê nguyên quy tắc “một exception sẽ dừng lịch” của raw JDK sang mọi ứng dụng Spring.

Spring `TaskUtils` có hai chiến lược minh họa:

- `LOG_AND_SUPPRESS_ERROR_HANDLER`: ghi lỗi, không rethrow; các lượt định kỳ có thể tiếp tục.
- `LOG_AND_PROPAGATE_ERROR_HANDLER`: ghi lỗi rồi rethrow; điều đó thường ngăn các lần sau trên scheduler JDK.

Nếu ứng dụng cung cấp `setErrorHandler(...)`, kết quả còn tùy handler có ném tiếp hay không.

~~~java
// Snippet trong @Configuration: chủ động log + tiếp tục.
ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(2);
scheduler.setErrorHandler(error -> {
    log.error("Scheduled iteration failed", error);
    failedRunsCounter.increment();
    // Không throw: iteration thất bại được ghi nhận, lịch tiếp tục.
});
~~~

`log` và `failedRunsCounter` là thành phần nghiệp vụ giả định; snippet không phải chương trình độc lập. Nếu lỗi mang ý nghĩa phải dừng job, chọn chính sách dừng rõ ràng và ghi trạng thái tại một job store; không đặt kỳ vọng vào một dòng log.

Một task “hoàn tất vì exception được wrapper xử lý” vẫn có thể khiến scheduler tính tiếp delay; **hoàn tất lịch chạy không đồng nghĩa nghiệp vụ thành công**. Theo dõi số lượt `FAILED`/`SUCCEEDED` riêng.

### 9.3. Dùng Future đúng cách

- `scheduleWithFixedDelay` trả `ScheduledFuture<?>` để **cancel/check status**, không để `get()` nhận kết quả của từng lượt.
- `handle.get()` khi lịch bình thường còn hoạt động có thể chờ vô hạn; tránh gọi ngay trên HTTP/startup thread để “đợi lượt đầu xong”.
- Muốn theo dõi lượt đầu, dùng callback/metric/job state, latch trong test, hoặc một Future kết quả do ứng dụng tự quản có deadline.
- `handle.isDone()` có thể chỉ rằng lịch đã bị cancel/terminated, **không** biểu thị “lượt gần nhất đã thành công”.
- Khi task bị từ chối đăng ký vì scheduler shutdown/overload, Spring có thể ném `TaskRejectedException` **ngay lúc gọi schedule**, trước khi trả handle.

## 10. Hủy, dừng ứng dụng và ScheduledFuture

### 10.1. Hủy lịch lặp

~~~java
ScheduledFuture<?> handle = scheduler.scheduleWithFixedDelay(
        this::runCleanup, Duration.ofMinutes(2));

// Ở nơi quản lý vòng đời của job:
boolean cancelled = handle.cancel(false);
~~~

`cancel(false)` chặn các lượt tương lai của chuỗi. Nếu task hiện đang chạy, cancellation không nhất thiết dừng ngay việc xử lý đang diễn ra. `cancel(true)` cho phép yêu cầu interrupt với backend có hỗ trợ, **không bảo đảm** DB transaction rollback, file đang được ghi sẽ biến mất hoặc I/O không hỗ trợ interruption dừng ngay.

Giữ `ScheduledFuture<?>` theo từng job registration; đừng tạo schedule mới mỗi request HTTP rồi vứt mất handle, vì việc không có chỗ hủy/giám sát có thể dẫn đến nhiều periodic jobs cùng chạy.

### 10.2. Shutdown và lifecycle Spring

`ThreadPoolTaskScheduler` là Spring-managed bean có lifecycle initialization/shutdown. Khi context đóng, ứng dụng phải dừng/huỷ lịch đúng chính sách đã chọn. Spring 6.1+ có thêm pause/resume và graceful-shutdown controls; chi tiết tùy version/configuration. Với job có side effects quan trọng, phải kiểm tra policy của task đang chạy, task đang đợi, shutdown timeout, và cách đảm bảo dữ liệu nhất quán sau restart.

Một `ScheduledFuture<?>` không là durable job queue. Nếu pod crash, toàn bộ handle trong JVM mất; muốn biết lần cuối đã xử lý tới đâu phải lưu checkpoint/watermark trong DB, không dựa vào `isDone()`.

### 10.3. Lưu ý thời điểm đăng ký

Một service có thể tự đăng ký schedule trong `@PostConstruct`, nhưng ở pha bean initialization có nguy cơ dependency/proxy chưa hoàn chỉnh hoặc cần lifecycle dừng chủ động. Tùy yêu cầu, dùng cấu hình bean, `ApplicationRunner`, `SmartLifecycle`, sự kiện sau refresh hoặc annotation `@Scheduled` phù hợp; tránh đăng ký hai lần khi context refresh hoặc nhiều instance được tạo.

## 11. Thiết kế job polling production: khoảng nghỉ, timeout, lỗi và dữ liệu

Ví dụ một job lấy hóa đơn mới từ API partner theo cursor. Yêu cầu “nghỉ 5s sau khi xong lượt trước” phù hợp fixed delay, nhưng để vận hành an toàn cần bổ sung:

1. **Điểm bắt đầu/hoàn tất thực:** log `startedAt`, `finishedAt` và `outcome` (success/failure) trong `Runnable` hoặc transaction quản lý job. Không đánh dấu hoàn tất khi chỉ dispatch Future khác.
2. **I/O timeout:** connection/read timeout cho HTTP client, query timeout/transaction timeout cho DB. Nếu `Runnable` treo vô hạn, lượt kế tiếp sẽ không được lên lịch dù đã cấu hình delay 5s.
3. **Checkpoint:** cập nhật cursor/watermark sau khi dữ liệu thực sự được ghi thành công, tránh bỏ sót sau restart hoặc khi có retry.
4. **Idempotency:** nếu request hoặc job bị retry hay nhiều pod chạy đồng thời, xử lý trùng theo key tự nhiên/unique index/upsert có điều kiện.
5. **Backpressure:** giới hạn batch size, số request song song tới partner, throughput DB và timeout; fixed delay chỉ kiểm soát **giữa các lượt**, không giới hạn tài nguyên **bên trong một lượt**.
6. **Lỗi và retry:** phân biệt lỗi tạm thời (429/503, timeout) và lỗi nghiệp vụ (payload sai, authorization). Có thể dùng exponential backoff/jitter và chính sách circuit breaker. Nếu cần interval động theo lỗi, một fixed delay bất biến có thể không đủ.
7. **Shutdown:** lưu trạng thái và hủy schedule; với lượt đang chạy, kết thúc an toàn hoặc cho phép restart phục hồi bằng job ledger.
8. **Giám sát:** metric successful_runs, failed_runs, last_success_timestamp, last_run_duration, delay_from_finish_to_next_start, scheduler_queue_delay, rejected scheduling attempts.
9. **Cluster:** nếu chỉ một worker toàn cụm được chạy, dùng distributed lease/scheduler ngoài JVM, không lấy poolSize=1 của từng pod làm khóa phân tán.

Nếu yêu cầu chính xác theo giờ địa phương (ví dụ 08:00 mỗi ngày), fixed delay không phù hợp vì **drift** theo thời gian xử lý và nghỉ. Khi ấy dùng cron với timezone rõ và quy tắc DST/missed execution riêng. Nếu partner quy định tối đa một request mỗi 5 giây kể từ lúc *trả kết quả*, fixed delay là công cụ gần đúng hữu ích, nhưng còn phải tính tất cả caller/task khác cùng gọi partner.

## 12. Kiểm thử scheduler mà không dựa vào sleep ngẫu nhiên

Một kiểm thử tốt có các tình huống:

| Test | Bằng chứng cần quan sát |
| --- | --- |
| Lượt 1 bị giữ bằng latch | Lượt 2 chưa bắt đầu khi lượt 1 chưa kết thúc |
| Lượt 1 được giải phóng | Lượt 2 chỉ bắt đầu sau khi đã hết delay kể từ kết thúc |
| Lượt 1 xử lý lâu hơn delay | Không có backlog nhiều lượt của cùng registration |
| Hủy `ScheduledFuture` | Không có lượt mới sau khi hủy (xem trạng thái cancellation/race) |
| Task ném exception | Phân biệt Spring default handler tiếp tục và raw JDK suppression |
| Một job A dài + job B khác | PoolSize=1 có thể trì hoãn B; nhiều workers có thể chạy song song |
| Executor shutdown | Đăng ký mới bị từ chối/cancel tùy policy, không chờ Future vô hạn |
| Cùng code trên hai pod | Có thể cùng chạy; cần coordination nếu yêu cầu một job toàn cụm |
| Task chỉ dispatch `@Async` | Fixed delay đo dispatch completion, không phải business completion |
| Virtual-thread-aligned scheduler | Semantics fixed delay cần được kiểm thử trên implementation thực |

Tại sao không nên test kiểu “`Thread.sleep(200)` rồi assert đã chạy đúng 2 lần”? Vì CI chậm, GC pause và hệ điều hành lên lịch không chính xác tuyệt đối. Với code nghiệp vụ, tách phần xử lý vào hàm độc lập để unit test sync; phần scheduling test bằng latch hoặc integration test có thời gian chờ hữu hạn. Đặt tolerance cho thời gian thực tế, không yêu cầu ms chính xác tuyệt đối.

### Test overlap và thứ tự

Một `AtomicInteger active` kết hợp `maxActive.accumulateAndGet(...)` có thể chứng minh cùng registration không có hai invocation đồng thời. Nhưng với fixed delay một worker trong demo, latch ở mục 5 đủ rõ. Nếu mã `Runnable` tách task sang executor khác, active counter phải bọc **công việc business thực tế**, không chỉ wrapper dispatch nhanh rồi trả về.

Khi có nhiều registration, cần test independent jobs và shared resource locks. Fixed delay không tự ngăn hai job **khác nhau** sửa cùng hàng trong DB.

## 13. Các lỗi thường gặp và cách sửa

| Hiểu nhầm / triệu chứng | Nguyên nhân thật | Cách sửa |
| --- | --- | --- |
| “delay=5s thì bắt đầu mỗi 5s” | Fixed delay tính từ **kết thúc** lượt trước | Dùng fixed rate nếu cần nhịp từ thời điểm bắt đầu |
| Lượt đầu chạy ngay, tưởng scheduler bỏ qua 5s | Overload không có `startTime` bắt đầu càng sớm càng tốt | Chỉ định `Instant` first run hoặc `@Scheduled(initialDelay=...)` |
| Lượt tiếp theo chậm hơn 5s | Delay là ngưỡng tối thiểu, không phải SLA start time | Đo worker contention, tải, GC, pause/resume |
| Tăng pool size mà một job vẫn không overlap | Mỗi periodic registration tuần tự theo fixed delay | Điều này đúng contract; dùng design khác nếu muốn parallel batches |
| Lịch vẫn chạy dù task ném exception | Spring default repeating ErrorHandler thường suppress lỗi | Theo dõi failed runs, cấu hình error policy có chủ đích |
| Lịch dừng sau exception trong JDK thuần | JDK periodic scheduling suppress các lượt tiếp theo | Handle lỗi trong task hoặc restart theo chính sách |
| `ScheduledFuture.get()` không trả | Future đại diện **chuỗi định kỳ**, không phải một lượt | Dùng metric/latch/job state, không chờ `get` vô hạn |
| Fixed delay mà report vẫn overlap | Task chỉ submit một `CompletableFuture` rồi trả về | Định nghĩa business-completion boundary, dùng gate/lease |
| API cần chạy đúng 02:00 nhưng bị trôi giờ | Fixed delay cộng cả thời gian xử lý | Dùng cron + timezone / job ledger |
| Có ba pod chạy ba lần | Mỗi pod có scheduler riêng | Distributed coordination, idempotency |
| Một scheduled job dài làm job khác trễ | Scheduler pool quá ít worker | Phân scheduler theo loại job hoặc tăng pool có kiểm soát |
| Đọc Boot execution core-size nhưng scheduler không thay đổi | Executor và scheduler khác abstraction/config | Dùng scheduling properties hoặc explicit scheduler bean |
| Task treo mãi khiến không có lượt mới | Không có timeout ở I/O hoặc task chờ Future vô hạn | Timeouts, deadline, cancellation contract |
| Đổi sang virtual threads thấy fixed-delay job bị nghẽn | `SimpleAsyncTaskScheduler` fixed-delay dùng scheduler thread | Chọn implementation/trigger phù hợp, kiểm thử tải |

## 14. Checklist code review

1. **Yêu cầu thời gian:** hệ thống cần nghỉ sau lúc hoàn tất hay bắt đầu mỗi N giây, hoặc chạy theo mốc giờ?
2. **Implementation:** ứng dụng dùng `TaskScheduler` nào (`ThreadPoolTaskScheduler`, `SimpleAsyncTaskScheduler`, scheduler do container quản lý)?
3. **Overload:** có chọn đúng `Duration` và `Instant startTime` cho lần đầu? Delay lớn hơn 0 và đơn vị rõ ràng?
4. **Completion boundary:** `Runnable` có thực thi đầy đủ nghiệp vụ hay chỉ dispatch qua `@Async` rồi trả về?
5. **Concurrency:** có nhiều registrations, @Scheduled annotation trùng hoặc nhiều pod khiến overlap ngoài ý muốn?
6. **Error handling:** dùng chính sách nào, lỗi được log/metric và có cần dừng lịch không?
7. **Lifecycle:** ai giữ `ScheduledFuture`, ai cancel, shutdown có chờ/hủy task đúng yêu cầu?
8. **Timeout:** network/DB và việc chờ child Future có deadline để tránh một lượt treo vô hạn?
9. **Observability:** có last success, failure rate, duration, scheduling lag và số lần chạy sau restart?
10. **State:** cursor/checkpoint/idempotency được lưu bền vững khi một lượt xử lý có side effect?
11. **Capacity:** pool size và số công việc khác đủ để không bỏ đói các job quan trọng?
12. **Validation:** có test latch chứng minh khoảng nghỉ sau completion, test exception và multi-instance?

## 15. Câu hỏi tự kiểm tra

1. Lượt A bắt đầu 09:00:00, kết thúc 09:00:11. `scheduleWithFixedDelay(..., Duration.ofSeconds(4))` có thể bắt đầu lượt B sớm nhất lúc nào nếu không bị chậm vì tải?
2. Vì sao `scheduleWithFixedDelay(task, Duration.ofSeconds(5))` có thể chạy lượt đầu ngay, còn overload có `Instant` thì chờ mốc giờ chỉ định?
3. Khác biệt giữa fixed delay và fixed rate khi một lượt chạy lâu hơn period?
4. Tăng `ThreadPoolTaskScheduler.poolSize` từ 1 lên 8 có khiến **cùng một periodic task** tự overlap không?
5. Một `@Scheduled(fixedDelay=5s)` gọi `@Async` ở bean khác và trở về ngay. Khoảng nghỉ 5s tính từ lúc nào?
6. Vì sao `handle.get()` trên `ScheduledFuture` định kỳ có thể chờ mãi?
7. Một exception trong raw JDK periodic Runnable so với Spring `ThreadPoolTaskScheduler` mặc định thường ảnh hưởng những lần chạy sau thế nào?
8. Nếu task gọi API ngoài không có read timeout và bị treo, fixed delay có tự khởi động lượt kế tiếp không?
9. Ba pod cùng bật `@Scheduled` fixed delay có tự điều phối để chỉ một pod xử lý không?
10. Khi nào cron phù hợp hơn fixed delay, và vì sao phải lưu cursor/checkpoint riêng?

**Ghi nhớ:** `scheduleWithFixedDelay()` mang nghĩa **“làm xong → nghỉ đủ delay → bắt đầu lượt kế tiếp khi có tài nguyên”**. Thời gian chạy của lượt trước làm thay đổi khoảng cách giữa các lần bắt đầu. Cơ chế này bảo vệ một chuỗi polling khỏi tự chồng lấp và đuổi lịch, nhưng **không** thay thế timeout, error handling, distributed lock, idempotency hay theo dõi kết quả nghiệp vụ.

## Tài liệu chính thức

- [Spring Framework 6.2 — TaskScheduler API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework 6.2 — ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Spring Framework 6.2 — @Scheduled Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html)
- [Spring Framework 6.2 — TaskUtils, xử lý lỗi tác vụ lặp](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/TaskUtils.html)
- [Java SE 17 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)
- [Java SE 17 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html)
