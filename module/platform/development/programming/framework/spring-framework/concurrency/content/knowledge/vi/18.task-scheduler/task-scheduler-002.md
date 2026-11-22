# schedule() để chạy một lần tại thời điểm chỉ định

## 1. Mục tiêu: hẹn một công việc chạy một lần với TaskScheduler

Trong Spring Framework, `TaskScheduler` là abstraction dùng để yêu cầu một `Runnable` chạy **ở một thời điểm xác định** hoặc theo các quy tắc lặp lại. Khi ứng dụng cần gửi một lời nhắc, thực hiện bước hậu xử lý, kích hoạt một lần kiểm tra trạng thái hoặc chạy tác vụ sau một thời điểm do người dùng chọn, API trực tiếp nhất là:

```java
ScheduledFuture<?> handle = taskScheduler.schedule(
        runnable,
        startTime   // java.time.Instant
);
```

Với overload **`schedule(Runnable, Instant)`**, tác vụ được **lên lịch chạy một lần**. Không có `period`, không lặp lại theo cron và không tự tạo một chuỗi lần chạy. Đây là khác biệt quan trọng so với `scheduleAtFixedRate(...)`, `scheduleWithFixedDelay(...)` hay `schedule(Runnable, Trigger)`.

**Cần phân biệt hai việc:**

1. **Chấp nhận lịch chạy:** khi gọi `schedule(...)` thành công, scheduler giữ một công việc sẽ đến hạn ở thời điểm yêu cầu.
2. **Thực sự chạy và hoàn tất:** scheduler cần còn sống, còn worker khả dụng và dependency cần thiết vẫn hoạt động khi đến hạn.

Lịch đã được chấp nhận không có nghĩa công việc đã chạy, không bảo đảm chạy đúng chính xác từng mili-giây, và **không tự bảo đảm tồn tại sau khi JVM/process khởi động lại**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Gọi đúng `TaskScheduler.schedule(Runnable, Instant)` để tạo **one-shot task**.
- Dùng `Instant`, `ZoneId`, `LocalDateTime` đúng khi người dùng nhập giờ địa phương.
- Hiểu trường hợp thời điểm tương lai, thời điểm quá khứ và khi scheduler bị quá tải.
- Sử dụng `ScheduledFuture<?>` để kiểm tra trạng thái, đợi kết quả, quan sát lỗi hoặc yêu cầu hủy.
- Cấu hình một `ThreadPoolTaskScheduler` bean và gọi nó từ service Spring.
- Viết ví dụ Java 17 chạy được, có kết quả xác định thay vì dùng `Thread.sleep(...)` để đoán task đã chạy.
- Tránh lỗi liên quan đến scheduler thread, đóng application, nhiều instance và lịch cần lưu bền vững.

## 2. Hợp đồng API: TaskScheduler.schedule(Runnable, Instant)

Giao diện của Spring có phương thức:

```java
ScheduledFuture<?> schedule(Runnable task, Instant startTime);
```

Trong đó:

- **`task`:** công việc triển khai `Runnable`, thường là lambda `() -> doSomething()`. Vì `Runnable.run()` trả `void`, future của tác vụ hoàn thành bình thường không chứa giá trị nghiệp vụ.
- **`startTime`:** thời điểm mong muốn được biểu diễn dưới dạng `java.time.Instant`, tức một điểm thời gian tuyệt đối trên trục UTC.
- **Giá trị trả về:** `ScheduledFuture<?>` để quản lý lần chạy đã được lên lịch, ví dụ `isDone()`, `cancel(...)`, `getDelay(...)`, `get(...)`.
- **Nếu `startTime` đã ở quá khứ:** theo hợp đồng API, công việc sẽ được thực thi **ngay khi có thể**, không tự báo lỗi chỉ vì thời điểm đã qua.
- **Nếu scheduler không chấp nhận task:** có thể ném `TaskRejectedException`, chẳng hạn scheduler đang shutdown hoặc bị chính sách giới hạn/từ chối nội bộ.
- **Nếu thời điểm đến hạn nhưng worker bận:** lần chạy có thể bắt đầu **muộn hơn** thời điểm yêu cầu; đây là scheduling best-effort trên executor, không phải một cơ chế hard real-time.

Ví dụ tạo lịch sau 3 giây:

```java
Instant fireAt = Instant.now().plusSeconds(3);
ScheduledFuture<?> handle = taskScheduler.schedule(
        () -> System.out.println("Run once"),
        fireAt
);
```

Đây là **snippet tích hợp**, giả định `taskScheduler` là một bean đã được inject/khởi tạo, không phải class Java độc lập. Lệnh `schedule` trả về ngay sau khi nộp lịch trong điều kiện bình thường; thread caller **không phải chờ ba giây**. Khi scheduler worker có khả năng phục vụ, callback sẽ được gọi vào hoặc sau thời điểm `fireAt`.

### Đừng nhầm “đúng giờ” với “đúng từng nano-giây”

`Instant` có thể có độ chính xác nano-giây ở cấp kiểu dữ liệu, nhưng thực thi còn phụ thuộc độ phân giải clock/timer, CPU scheduler, GC, lock, thread pool, độ dài task khác, contention và tình trạng máy. Vì thế điều kiện đúng cho nhiều ứng dụng là “không trước thời điểm mong muốn, chạy càng gần thời điểm đó càng tốt”, chứ không bảo đảm timestamp thực tế trùng hoàn toàn với `Instant` đầu vào.

Nếu nghiệp vụ yêu cầu hạn chót nghiêm ngặt, phải đặt **deadline**, đo độ trễ và quyết định thế nào là chạy quá muộn; đừng dùng `schedule` như đồng hồ thời gian thực cứng.

## 3. Dòng thời gian của một tác vụ chạy một lần

Xét yêu cầu lúc 10:00:00 đặt lịch chạy lúc 10:00:05:

```text
caller thread                 scheduler                       worker thread
     |                           |                                  |
     |  schedule(task, t=10:00:05)                                  |
     |-------------------------->|                                  |
     |                           | giữ delayed task                 |
     |<------ ScheduledFuture ---|                                  |
     |                           |                                  |
     |        caller có thể tiếp tục xử lý request                 |
     |                           |                                  |
     |                    đến hạn 10:00:05                          |
     |                           |-- dispatch khi có worker ------->|
     |                           |                                  | task.run()
     |                           |                                  | hoàn tất
     |                           |<------------------- future done -|
     |                           |                                  |
     |                         KHÔNG tự lặp lại                     |
```

Các trạng thái chính:

| Giai đoạn | Ý nghĩa | Kiểm tra được bằng gì? |
| --- | --- | --- |
| Mới submit | Scheduler đã chấp nhận lịch | Có `ScheduledFuture<?>`; không nhận rejection |
| Đang chờ đến hạn | Task chưa chạy | `future.isDone()` thường là `false`; `getDelay(...)` còn dương (xấp xỉ) |
| Đã đến hạn, chờ worker | Thời gian đã qua nhưng chưa bắt đầu vì bận/tắc nghẽn | Metric queue, active worker, lateness |
| Đang chạy | `Runnable.run()` đang thực thi | Instrument task start/end; future thường chưa done |
| Hoàn tất bình thường | `run()` trả về | `future.isDone() == true`; `get()` hoàn tất |
| Hoàn tất ngoại lệ | Task ném lỗi và executor ghi nhận exception theo implementation | `get()` có thể báo `ExecutionException` |
| Bị hủy | Yêu cầu cancel được chấp nhận | `isCancelled()`; `get()` ném `CancellationException` |

**Lưu ý:** `ScheduledFuture.getDelay(TimeUnit)` biểu diễn thời gian ước lượng còn tới lịch chạy, **không** cho biết task đã chạy xong. Khi đã quá hạn, delay có thể bằng không hoặc âm trong khi task vẫn chưa hoàn tất.

Để biết task **đã hoàn tất**, dùng `future.get(timeout, unit)` trong môi trường cho phép blocking, hoặc instrument/callback/bảng trạng thái của ứng dụng; không chỉ đọc delay.

## 4. Ví dụ hoàn chỉnh Java 17 + Spring Framework 6.2: một lần chạy và một lần hủy

Ví dụ sử dụng trực tiếp `ThreadPoolTaskScheduler`, một implementation phổ biến của Spring. Ta khởi tạo scheduler bằng code để chương trình **có thể chạy ngoài Spring Boot** và không phải triển khai server. Với Spring-managed bean ở ứng dụng thực, lifecycle được ApplicationContext quản lý; ví dụ CLI này tự gọi `initialize()` và `shutdown()`.

**Điều kiện:** JDK 17+, Maven 3.x, Spring Framework `6.2.14`.

Cấu trúc thư mục:

```text
spring-one-shot/
├── pom.xml
└── src/main/java/demo/OneShotDemo.java
```

### 4.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-one-shot</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.OneShotDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.2. src/main/java/demo/OneShotDemo.java

```java
package demo;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

public final class OneShotDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("one-shot-");
        scheduler.initialize(); // Vì ví dụ chạy ngoài Spring ApplicationContext.

        AtomicInteger runs = new AtomicInteger();
        AtomicBoolean properThread = new AtomicBoolean(false);
        AtomicInteger cancelledRuns = new AtomicInteger();

        try {
            Instant runAt = Instant.now().plusMillis(250);

            ScheduledFuture<?> first = scheduler.schedule(() -> {
                properThread.set(
                        Thread.currentThread().getName()
                                .startsWith("one-shot-"));
                runs.incrementAndGet();
            }, runAt);

            // Demo CLI có thể blocking để xác minh tác vụ đã chạy xong.
            first.get(5, TimeUnit.SECONDS);
            System.out.println("onSchedulerThread=" + properThread.get());
            System.out.println("completedRuns=" + runs.get());
            System.out.println("firstDone=" + first.isDone());

            // Lần chạy khác đặt xa trong tương lai và hủy ngay.
            ScheduledFuture<?> later = scheduler.schedule(
                    () -> cancelledRuns.incrementAndGet(),
                    Instant.now().plus(Duration.ofDays(1)));

            boolean accepted = later.cancel(false);
            System.out.println("cancelAccepted=" + accepted);
            System.out.println("laterCancelled=" + later.isCancelled());
            System.out.println("laterRuns=" + cancelledRuns.get());
        } finally {
            scheduler.shutdown();
        }
    }
}
```

Chạy trong thư mục `spring-one-shot`:

```bash
mvn -q compile exec:java
```

**Standard output dự kiến khi chương trình chạy bình thường:**

```text
onSchedulerThread=true
completedRuns=1
firstDone=true
cancelAccepted=true
laterCancelled=true
laterRuns=0
```

### 4.3. Phân tích hành vi của chương trình

1. `scheduler.initialize()` tạo scheduled executor bên dưới. Nếu bỏ bước này khi tự tạo object ngoài Spring context, scheduler chưa sẵn sàng để nhận lịch.
2. `setThreadNamePrefix("one-shot-")` cho phép kiểm tra task chạy trên thread do scheduler tạo; chương trình in giá trị boolean thay vì in tên thread có số thứ tự không cố định.
3. `Instant.now().plusMillis(250)` đặt thời điểm tương lai ngắn. Thời gian thực có thể lệch vài mili-giây, nhưng `first.get(5, ...)` **đợi đến lúc task hoàn tất**, nên phép kiểm tra số lần chạy không phụ thuộc vào `Thread.sleep`.
4. `runs.incrementAndGet()` chỉ được gọi một lần bởi one-shot task; kết quả bình thường là `completedRuns=1`. `first.isDone()` trở thành true sau khi task hoàn tất.
5. Tác vụ thứ hai được lên lịch sau một ngày và hủy **trước thời điểm đến hạn**. `later.cancel(false)` được chấp nhận, `later.isCancelled()` là true và `cancelledRuns` vẫn bằng 0.
6. `finally` đóng scheduler. Đoạn này rất quan trọng đối với CLI/test: nếu tạo thread pool rồi không đóng, chương trình có thể vẫn còn thread sống. Trong Spring context thật, dùng bean lifecycle thay vì tự khởi tạo một scheduler cho từng request.

**Không nên suy rộng:** đây là tình huống đơn giản, một JVM, không có restart, độ trễ nhỏ và không có DB/API. Nó chứng minh one-shot scheduling và hủy trước khi chạy, **không chứng minh độ chính xác tuyệt đối hoặc khả năng chạy sau khi server tắt**. Không đưa các dòng output timestamp cố định vì thời gian thực luôn khác.

Nếu môi trường cực kỳ quá tải khiến task không hoàn tất trong 5 giây, `get(5, ...)` sẽ ném `TimeoutException`: đây là điều kiện kiểm thử báo lỗi thay vì cho kết quả sáu dòng như dự kiến.

## 5. Dùng TaskScheduler như một Spring bean trong ứng dụng thật

Trong ứng dụng Spring Framework/Spring Boot, nên quản lý scheduler bằng container và inject qua abstraction `TaskScheduler`, thay vì `new ThreadPoolTaskScheduler()` mỗi khi nhận request.

**SchedulingConfiguration.java** — ví dụ class cấu hình tích hợp:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
public class SchedulingConfiguration {

    @Bean("oneShotScheduler")
    public ThreadPoolTaskScheduler oneShotScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("reminder-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(10);
        return scheduler;
    }
}
```

Đây là **class tích hợp**, không phải một file chạy độc lập chỉ bằng `javac`: ứng dụng phải có Spring context và đặt cấu hình trong component scan/import thích hợp. Spring sẽ gọi lifecycle initialization/destruction của `ThreadPoolTaskScheduler` bean; không cần gọi `initialize()` thủ công trên bean được quản lý bình thường.

**ReminderService.java** — nhận yêu cầu hẹn đúng một lần:

```java
import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.ScheduledFuture;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Service;

@Service
public class ReminderService {
    private final TaskScheduler scheduler;
    private final ReminderSender sender;

    public ReminderService(
            @Qualifier("oneShotScheduler") TaskScheduler scheduler,
            ReminderSender sender) {
        this.scheduler = scheduler;
        this.sender = sender;
    }

    public ScheduledFuture<?> scheduleReminder(String reminderId, Instant at) {
        Objects.requireNonNull(reminderId, "reminderId");
        Objects.requireNonNull(at, "at");

        return scheduler.schedule(
                () -> sender.sendReminder(reminderId),
                at);
    }
}
```

Ở đây `ReminderSender` là **service nghiệp vụ do ứng dụng tự định nghĩa**, cần cung cấp bean tương ứng. Snippet minh họa API, không phải chương trình hoàn chỉnh cho tới khi có `ReminderSender`, main/bootstrapping, cấu hình và dependencies.

**Ví dụ caller:**

```java
Instant at = Instant.parse("2026-11-01T02:00:00Z");
ScheduledFuture<?> handle =
        reminderService.scheduleReminder("REM-100", at);
```

Caller nhận handle sau khi scheduler chấp nhận lịch; **không** nhận “reminder đã gửi thành công”. Với endpoint web, không nên gọi ngay `handle.get()` nếu điều đó làm request thread đợi đến tận thời điểm hẹn nhiều giờ sau.

### Có bắt buộc @EnableScheduling không?

**Không bắt buộc chỉ để gọi programmatic `TaskScheduler.schedule(...)` trên một bean đã được khởi tạo.** `@EnableScheduling` chủ yếu kích hoạt cơ chế xử lý các phương thức gắn `@Scheduled` trong Spring context. Hai cách sử dụng có thể cùng tồn tại, nhưng chúng khác nhau về cách đăng ký:

- `TaskScheduler.schedule(Runnable, Instant)`: caller quyết định một thời điểm cụ thể và chủ động tạo lịch.
- `@Scheduled`: phương thức được framework đăng ký theo metadata lịch trên bean, thông thường cho cron/fixed-rate/fixed-delay hoặc cơ chế one-time delay hỗ trợ bởi phiên bản cụ thể.

Với tính năng “người dùng đặt lịch gửi thông báo vào 09:00 ngày X” thay đổi theo từng yêu cầu, gọi `schedule(...)` trực tiếp thường rõ ràng hơn cố gắng gắn annotation cho hàng nghìn thời điểm động.

## 6. Instant, múi giờ và thời điểm do người dùng nhập

`Instant` đại diện **một thời điểm tuyệt đối**, không mang tên múi giờ địa phương. Còn giao diện người dùng thường nhập:

```text
"01/11/2026 09:00"    (giờ địa phương)
```

Chỉ chuỗi này chưa đủ để xác định thời điểm toàn cầu: phải biết **múi giờ của người dùng hoặc nghiệp vụ**. Không lấy timezone mặc định của server Docker rồi coi đó là múi giờ của mọi khách hàng.

Ví dụ chuyển 09:00 tại Việt Nam ngày 1/11/2026 sang `Instant`:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDateTime local = LocalDateTime.of(2026, 11, 1, 9, 0);
Instant fireAt = local.atZone(zone).toInstant();

System.out.println(fireAt);
// 2026-11-01T02:00:00Z
```

Đây là **snippet** trong một method có import thích hợp. Múi giờ `Asia/Ho_Chi_Minh` hiện sử dụng UTC+07:00 nên phép chuyển trên cho 02:00 UTC. Chọn `ZoneId` theo thông tin nghiệp vụ; một server có thể phục vụ nhiều zone.

### Daylight Saving Time (DST)

Một số múi giờ có giờ mùa hè và chuyển đổi DST:

- Một `LocalDateTime` có thể **không tồn tại** tại địa phương khi đồng hồ nhảy tới giờ mới.
- Một `LocalDateTime` có thể xuất hiện **hai lần** khi đồng hồ quay lại.
- `local.atZone(zone)` có quy tắc điều chỉnh/chọn offset; không mặc định đó luôn là quyết định nghiệp vụ bạn muốn.
- Nếu cần lịch có tính chính xác cao, xác thực qua `zone.getRules().getValidOffsets(local)`. Danh sách có 0 offset nghĩa là gap, 2 offset là overlap; yêu cầu người dùng xử lý hoặc chọn một chính sách được định nghĩa rõ.

Nếu người dùng chọn thời điểm tuyệt đối qua API, có thể nhận ISO-8601 có offset, chuyển sang `Instant` và lưu cùng zone gốc nếu sau này còn phải hiển thị đúng địa phương. Đừng xây lịch tương lai bằng phép cộng số giờ cố định thay cho quy tắc timezone khi tính “ngày mai lúc 9 giờ” tại zone có DST.

### Thời điểm đã qua có được chạy không?

Theo hợp đồng `schedule(Runnable, Instant)`, thời điểm quá khứ sẽ được chạy **ngay khi có thể**. Ví dụ một request đặt `Instant.now().minusSeconds(10)` không phải tự động “không hợp lệ”.

Nhưng nghiệp vụ có thể muốn **từ chối lịch quá hạn**:

```java
if (!requestedTime.isAfter(scheduler.getClock().instant())) {
    throw new IllegalArgumentException("Schedule time must be future");
}
ScheduledFuture<?> future = scheduler.schedule(job, requestedTime);
```

Snippet này có các biến `requestedTime`, `job` và `scheduler` đã được khởi tạo. Đây là kiểm tra nghiệp vụ, **không phải quy tắc tự động của API**; giữa lúc kiểm tra và lúc submit vẫn có race nếu thời gian vừa trôi qua. Nếu cần xử lý trường hợp đó, quy định rõ “chạy ngay”, “từ chối” hoặc “đánh dấu missed” thay vì âm thầm giả định.

## 7. ScheduledFuture: theo dõi, đợi, hủy

`schedule(...)` trả về một `ScheduledFuture<?>` kết hợp API của `Future` với API lấy độ trễ `Delayed`.

| Phương thức | Dùng để làm gì? | Điều không tự bảo đảm |
| --- | --- | --- |
| `getDelay(unit)` | Ước lượng còn bao lâu đến hạn | Không báo chắc task đã bắt đầu/hoàn tất |
| `isDone()` | Future đã hoàn tất theo trạng thái của nó | Không nhất thiết là thành công (có thể lỗi/hủy) |
| `isCancelled()` | Future ở trạng thái cancelled | Không chứng minh mọi side effect đã được rollback |
| `cancel(false)` | Cố hủy lịch; không yêu cầu interrupt task đang chạy | Không bảo đảm dừng task đã bắt đầu |
| `cancel(true)` | Cố hủy, có thể yêu cầu interrupt task đang chạy theo implementation | Không bảo đảm JDBC/HTTP/remote operation lập tức dừng |
| `get()` | Đợi tới khi task hoàn tất hoặc lỗi/hủy | Có thể chặn caller rất lâu |
| `get(timeout, unit)` | Chờ kết quả có hạn | Timeout đợi **không** tự cancel task |

**Đoạn bắt trạng thái trong test/CLI:**

```java
try {
    future.get(5, TimeUnit.SECONDS);
    System.out.println("success=true");
} catch (java.util.concurrent.CancellationException ex) {
    System.out.println("cancelled=true");
} catch (java.util.concurrent.ExecutionException ex) {
    Throwable original = ex.getCause();
    System.err.println("Task failed: " + original);
} catch (java.util.concurrent.TimeoutException ex) {
    System.err.println("Still waiting or running");
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
}
```

Snippet giả định đã có `future` và import `TimeUnit`. Dùng `get()` trong request handler chỉ khi có lý do hợp lệ để blocking; đa số endpoint lập lịch nên **trả xác nhận đã nhận yêu cầu và một ID theo dõi**, không đợi hàng giờ để gửi phản hồi.

### Hủy trước hạn

Nếu task chưa bắt đầu, `future.cancel(false)` thường ngăn task thực thi. Với một `ThreadPoolTaskScheduler` dựa trên `ScheduledThreadPoolExecutor`, việc hủy delayed task còn liên quan chính sách **remove-on-cancel**: một task đã cancel có thể vẫn được giữ trong queue cho đến thời điểm trigger nếu không bật xóa khi hủy.

Tùy cấu hình/version, có thể bật trên underlying executor:

```java
scheduler.getScheduledThreadPoolExecutor()
         .setRemoveOnCancelPolicy(true);
```

Snippet này chỉ gọi được khi `ThreadPoolTaskScheduler` **đã được khởi tạo** và implementation bên dưới là `ScheduledThreadPoolExecutor`. Nó tác động tới cách giữ task đã hủy trong queue, không thay đổi nghĩa của `cancel(...)` với công việc đã thực sự chạy.

### Hủy sau khi task bắt đầu

`cancel(false)` không gửi interrupt; `cancel(true)` có thể khiến worker bị interrupt theo semantics executor nhưng task phải **hợp tác** để dừng. Khi Runnable đang gọi remote service hoặc xử lý giao dịch DB, không coi future cancelled là bằng chứng remote request chưa xảy ra. Với tác vụ có side effect, cần cancellation-aware client, timeout, transaction và idempotency.

Nếu `cancel(...)` trả `false`, task có thể đã hoàn tất, bị hủy trước đó hoặc không thể hủy trong trạng thái hiện tại. Không coi `false` là “đã chạy thành công” khi chưa kiểm tra kết quả.

## 8. Lỗi trong Runnable và lỗi lúc đăng ký lịch

Có **hai nơi khác nhau** để lỗi xuất hiện:

### 8.1. Lỗi ở thời điểm submit

Nếu scheduler đang đóng hoặc từ chối lịch vì lý do nội bộ, `schedule(...)` có thể ném `TaskRejectedException` **trực tiếp ở caller**:

```java
try {
    ScheduledFuture<?> handle = scheduler.schedule(job, when);
    // Đã nhận lịch, CHƯA có nghĩa job đã hoàn tất.
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Lịch KHÔNG được nhận vào scheduler: trả lỗi phù hợp,
    // hoặc lưu lại theo cơ chế bền vững và retry có giới hạn.
}
```

Snippet này yêu cầu `scheduler`, `job`, `when` có sẵn trong integration code. Rejection lúc submit không đồng nghĩa task đã chạy và ném exception; callback có thể chưa bắt đầu lần nào.

### 8.2. Lỗi khi job thực thi

Nếu `Runnable.run()` đã chạy và ném `RuntimeException`, scheduler có thể ghi lại lỗi vào Future và/hoặc gửi qua `ErrorHandler` tùy implementation và cấu hình. Với one-shot scheduling trên `ThreadPoolTaskScheduler` theo cơ chế xử lý lỗi mặc định, exception của lần chạy có thể được phản ánh qua `ScheduledFuture.get()` dưới dạng `ExecutionException`; nếu ứng dụng cấu hình `ErrorHandler` riêng để nuốt lỗi thì semantics quan sát có thể thay đổi.

Điểm quan trọng: **không mặc định exception sẽ được ném ngược về thread đã gọi `schedule(...)`**. Thread caller thường đã tiếp tục từ lâu.

Một Runnable có xử lý lỗi nghiệp vụ:

```java
Runnable job = () -> {
    try {
        sender.sendReminder("REM-100");
    } catch (RemoteServiceException ex) {
        metric.increment();
        throw ex;
    }
};
```

Đây là snippet minh họa với `sender`, `RemoteServiceException` và `metric` do ứng dụng định nghĩa. Nếu cần retry, hãy quy định rõ retry budget, idempotency và trạng thái job; **không** giả định Spring sẽ tự động chạy lại one-shot task sau exception.

### 8.3. Đừng quên ErrorHandler

`ThreadPoolTaskScheduler.setErrorHandler(...)` cho phép thiết lập cách báo lỗi từ task. Lựa chọn handler cần phù hợp one-shot vs recurring: nếu handler chỉ log rồi suppress, callback có thể bị coi là đã hoàn tất bình thường ở tầng future/scheduler dù nghiệp vụ thất bại. Vì vậy phải có **một nơi sở hữu trạng thái FAILED** của job, không phụ thuộc hoàn toàn vào log của worker.

Với task quan trọng, nên lưu job ID/trạng thái trước khi đăng ký, rồi đánh dấu `RUNNING`/`SUCCEEDED`/`FAILED` từ boundary nghiệp vụ. Đừng dùng chỉ `future.isDone()` để quyết định đã gửi thành công.

## 9. Khác nhau giữa schedule() một lần và lịch lặp lại

| API | Đặc điểm | Tình huống phù hợp |
| --- | --- | --- |
| `schedule(Runnable, Instant)` | **Một lần**, tại/sau Instant | Gửi reminder tại thời điểm chỉ định |
| `schedule(Runnable, Trigger)` | Lịch do Trigger xác định; có thể tiếp tục phát sinh lần chạy | Cron, lịch tùy biến |
| `scheduleAtFixedRate(Runnable, Duration)` | Lặp theo nhịp cố định | Thu thập metric định kỳ |
| `scheduleAtFixedRate(Runnable, Instant, Duration)` | Có thời điểm bắt đầu và chu kỳ cố định | Bắt đầu một periodic job từ mốc X |
| `scheduleWithFixedDelay(Runnable, Duration)` | Đợi một khoảng sau khi lần trước hoàn tất | Polling có khoảng nghỉ |
| `scheduleWithFixedDelay(Runnable, Instant, Duration)` | Có mốc đầu và delay sau lần trước | Polling bắt đầu từ mốc được chọn |

**Tình huống dễ sai:** muốn gửi email đúng một lần vào 17:00 nhưng lại dùng `scheduleAtFixedRate(task, Duration.ofHours(24))`. Cách này tiếp tục gửi email vào những ngày sau. Muốn đúng một lần, dùng `schedule(task, instant)`.

Nếu muốn tạo một lịch **hàng ngày lúc 09:00 theo múi giờ**, đó là bài toán recurrence có DST và timezone, không tương đương “cộng 24 giờ vào Instant” ở những zone có DST. Dùng Trigger/Cron phù hợp hoặc scheduler lưu lịch bền vững theo quy tắc nghiệp vụ.

### Sự khác biệt giữa TaskScheduler và TaskExecutor

`TaskExecutor.execute(task)` thường yêu cầu thực thi càng sớm càng tốt; `TaskScheduler.schedule(task, instant)` yêu cầu **không chạy trước mốc được chỉ định**, rồi chạy khi đủ tài nguyên. Cả hai đều chịu hạn chế của thread, queue, scheduling và shutdown, nhưng một bên có **mốc thời gian tương lai**.

## 10. Năng lực thực thi: scheduler thread, pool size và việc chậm giờ

`ThreadPoolTaskScheduler` bao bọc `ScheduledThreadPoolExecutor` của JDK. Trong Spring Framework 6.2, giá trị mặc định `poolSize` là **1**. Không nên suy ra từ tên “thread pool scheduler” rằng nó có nhiều worker mặc định.

Đáng chú ý, theo Javadoc, task của `ThreadPoolTaskScheduler` **chạy trên chính scheduler thread**, thay vì tự động được chuyển sang một execution pool khác. Vì vậy:

- Một task chạy lâu có thể chiếm scheduler thread và làm job khác đến hạn cũng phải đợi.
- Với pool size 1, các one-shot jobs có thể bắt đầu tuần tự dù chúng có cùng `Instant`.
- Tăng pool size có thể giúp nhiều task đến hạn chạy đồng thời, nhưng không tăng DB connection/quota remote.
- Một scheduler thread đang chờ mạng vẫn chiếm worker của scheduler nếu dùng blocking client.
- Vùng scheduled queue không phải job queue bền vững trên disk.

Ví dụ hai job đến hạn lúc cùng thời điểm trên scheduler pool size 1:

```text
T = 10:00:00
Job A (chạy 8 giây) -----------+-------------------->
                               |
Job B (đến hạn cùng 10:00:00)   | [đợi worker]
                               +----> bắt đầu sau khi A kết thúc
```

Do đó, `Instant` là **desired time**, không phải deadline được bảo đảm. Nếu job quan trọng phải phát lệnh đúng hạn, cần đo **scheduling lag** = actualStart - desiredTime và có chính sách xử lý quá muộn.

### Có nên schedule một Runnable rồi tự submit sang executor khác?

Có thể dùng một Runnable **rất ngắn** tại thời điểm đến hạn để nộp công việc nặng sang executor riêng:

```java
scheduler.schedule(
        () -> workerExecutor.execute(
                () -> reportService.generateReport(reportId)),
        runAt);
```

Đây là snippet tích hợp với `scheduler`, `workerExecutor`, `reportService`, `reportId` và `runAt` đã có. **Cảnh báo quan trọng:** future trả về từ `schedule(...)` trong ví dụ này theo dõi **việc submit sang worker executor**, không theo dõi toàn bộ `generateReport` chạy ở worker khác. Nếu worker executor reject, điều đó cũng cần xử lý rõ ràng. Nếu cần kết quả nghiệp vụ, hãy lưu task ID và status, hoặc xây `CompletableFuture`/completion tracking đúng.

Đừng tạo một thread mới cho mỗi task chỉ để tránh scheduler pool nhỏ; chọn bounded executor và tính công suất downstream, memory và backpressure.

### Theo dõi metric

Các chỉ số hữu ích:

- Số job được lập lịch, đã đến hạn, bắt đầu, hoàn tất, thất bại, bị hủy.
- Queue depth, active scheduler threads, pool size và rejected schedules.
- Scheduling lag từ `Instant` dự kiến đến actual start, phân phối p50/p95/p99.
- Execution duration, số job chạy đồng thời và tổng backlog quá hạn.
- JDBC/HTTP pool saturation nếu callback gọi dependency.
- Số lượng lịch rất xa trong tương lai, số đã cancel nhưng còn ở queue.

Với Spring Boot Actuator/Micrometer, metric cụ thể phụ thuộc cách bind executor/scheduler và phiên bản. Không giả định `getPoolSize()` hay `getActiveCount()` tự xuất hiện thành dashboard nếu ứng dụng chưa cấu hình instrumentation.

## 11. Shutdown, restart và nhiều instance: giới hạn lớn nhất của one-shot trong RAM

Một câu lệnh `scheduler.schedule(job, when)` với `ThreadPoolTaskScheduler` lưu lịch trong **bộ nhớ của JVM hiện tại**. Điều này có hệ quả:

### 11.1. Ứng dụng restart trước thời điểm chạy

Nếu JVM dừng và khởi động lại, handle `ScheduledFuture` của tiến trình cũ không thể được sử dụng lại. Lịch đang chờ trong scheduled executor cũng không tự được phục hồi từ DB. Nếu ứng dụng cần lịch sống qua restart, phải **lưu dữ liệu lịch bền vững** và có cơ chế khôi phục.

Ngay cả khi cấu hình shutdown “chờ task hoàn tất”, một lần restart/deploy vẫn không tạo ra hệ thống durable scheduling cho các lịch sau vài ngày. Không giữ request HTTP hoặc shutdown JVM tới ngày hẹn chỉ để bảo toàn một lịch không có DB.

### 11.2. Nhiều instance cùng đăng ký một job

Nếu ứng dụng chạy 4 pod và mỗi pod đều gọi `schedule(job, when)` cho cùng job ID, có thể có **4 bản sao cùng thực thi** khi tới hạn. `TaskScheduler` cục bộ không tự có distributed lock hoặc exactly-once coordination.

Nếu chỉ một pod nhận request và giữ lịch, pod đó chết thì lịch có thể mất; load balancer chuyển request sau đó sang pod khác cũng không tự chuyển `ScheduledFuture` từ JVM cũ.

### 11.3. Cần idempotency và trạng thái bền vững

Với công việc nghiêm túc như gửi hóa đơn, chuyển trạng thái đơn hàng hoặc phát thông báo có chi phí, kiến trúc nên có:

```text
API nhận yêu cầu lập lịch
       |
       v
DB lưu: job_id, execute_at (Instant), status, payload/ref, version
       |
       v
worker/scheduler tìm các job due
       |
       v
atomic claim / transaction / lease theo job_id
       |
       v
chạy xử lý idempotent
       |
       +--> SUCCEEDED
       +--> FAILED / RETRY_AT
```

Cần cân nhắc **idempotency key** ở downstream, transaction/constraint của DB, lease timeout khi worker crash, retry budget và cách phân biệt “đã gửi nhưng chưa kịp ghi SUCCEEDED”.

**Không hứa exactly-once chỉ bằng khóa:** một worker có thể gọi external API thành công rồi crash trước khi commit trạng thái. Lúc retry có thể gửi lại; cần idempotency hoặc nghiệp vụ chịu được at-least-once.

### 11.4. Khi nào chọn Quartz hoặc job queue?

- **One-shot đơn giản, có thể mất khi restart, không có nhiều replica:** `ThreadPoolTaskScheduler` đủ tốt.
- **Lịch cần lưu và khôi phục:** cân nhắc Quartz với JDBC job store cấu hình đúng, hoặc cơ chế job table + worker với claiming bền vững.
- **Cần retry, dead-letter, workflow nhiều bước:** message broker/job queue/workflow engine thích hợp hơn một `ScheduledFuture` chỉ nằm trong RAM.
- **Chạy multi-node:** đảm bảo coordination trong job store hoặc tầng phân phối, không xem một instance `TaskScheduler` là khóa phân tán.

Không phải Quartz tự động giải quyết mọi vấn đề: phải chọn job store/persistence, cấu hình cluster/locking, misfire handling, concurrency, recovery và nghiệp vụ idempotent đúng.

## 12. Khi nào dùng Clock và cách kiểm thử thời gian?

API `TaskScheduler.getClock()` cho phép làm việc với clock của scheduler. `ThreadPoolTaskScheduler.setClock(Clock)` hỗ trợ chỉ định nguồn clock cho việc tính thời gian. Điều này hữu ích cho testing/time interpretation nhưng **không biến executor thành bộ điều khiển thời gian ảo hoàn toàn**: scheduler bên dưới vẫn có cơ chế delay/timing thực tế.

### Tách tính toán thời điểm khỏi việc thực thi

Để test nhanh và xác định, nên tách logic:

1. Parse/validate thời điểm do người dùng nhập, múi giờ và business rule.
2. Tạo `Instant scheduledAt` từ một `Clock` được inject.
3. Gọi một interface `TaskScheduler` (có thể mock/spy) với đúng `Runnable` và `Instant`.
4. Trong integration test riêng, dùng scheduler thật và `Future.get(timeout)`/latch để xác minh callback được chạy.

Snippet phương thức có Clock:

```java
public Instant nextFireTime(Clock clock, Duration delay) {
    if (delay.isNegative()) {
        throw new IllegalArgumentException("delay must not be negative");
    }
    return clock.instant().plus(delay);
}
```

Đây là method-body snippet cần import `Clock`, `Duration` và `Instant`. Với `Clock.fixed(...)` trong unit test, kết quả tính toán hoàn toàn xác định; không cần ngủ chờ vài phút.

**Đừng dùng cố định clock rồi nghĩ executor thật tự nhảy tới tương lai.** `ThreadPoolTaskScheduler` vẫn tính delay từ thời điểm hiện tại của clock cấu hình tại lúc schedule và phụ thuộc việc worker/timer thực tế thực thi. Với một lịch đã nộp, thay đổi clock hệ thống sau đó không nhất thiết dịch chuyển lại thời điểm thực thi theo wall-clock như bạn kỳ vọng.

### Cách kiểm thử one-shot với scheduler thật

- Dùng mốc tương lai ngắn và `Future.get(timeout)` hoặc `CountDownLatch.await(timeout)`.
- Kiểm tra counter == 1 sau khi Future hoàn tất.
- Kiểm tra cancellation khi task chắc chắn còn rất xa trong tương lai.
- Kiểm tra xử lý `TaskRejectedException` khi scheduler đã shutdown trong test chuyên biệt.
- Kiểm tra callback lỗi qua `ExecutionException` và logging/status ở business boundary.
- Kiểm tra không có lần chạy thứ hai, nhưng không dựa trên `Thread.sleep(5s)` để “chứng minh mãi mãi không lặp”: hợp đồng one-shot + Future hoàn tất cùng counter là bằng chứng phù hợp.
- Với chức năng theo múi giờ, unit-test DST gap/overlap cùng conversion từ `LocalDateTime` sang `Instant`.
- Với persistence, test restart/crash, duplicate claiming và retry/idempotency thay vì chỉ unit test scheduler.

## 13. Các lỗi thường gặp và cách sửa

### Lỗi 1: Dùng LocalDateTime như một thời điểm tuyệt đối

`LocalDateTime` không có timezone. Dùng `ZoneId` rõ ràng rồi chuyển sang `Instant`; không dựa vào timezone mặc định của server. Cẩn thận DST gap/overlap.

### Lỗi 2: Tưởng schedule() tạo lịch lặp lại

`schedule(Runnable, Instant)` là one-shot. Muốn lặp dùng Trigger/fixed-rate/fixed-delay; không tự giả định một lần chạy sẽ được scheduler tạo lại.

### Lỗi 3: Coi Instant là lời hứa đúng tới từng mili-giây

Sự kiện đến hạn khác với sự kiện worker bắt đầu. Một task chậm có thể làm những task khác trễ; đo scheduling lag và đặt capacity/deadline.

### Lỗi 4: Chờ ScheduledFuture.get() trong HTTP request nhiều giờ

Caller có thể bị block đến tận khi job chạy xong, dẫn tới timeout và giữ request thread/connection. Trả job ID/accepted response; theo dõi kết quả qua status/event, không chặn request.

### Lỗi 5: Tự new ThreadPoolTaskScheduler cho từng request

Mỗi instance có thread pool/lifecycle riêng; làm vậy tăng tài nguyên và khó đóng đúng. Dùng singleton Spring bean được quản lý, hoặc scheduler có owner/lifecycle rõ ràng.

### Lỗi 6: Không initialize scheduler trong chương trình tự tạo

Nếu tự tạo `new ThreadPoolTaskScheduler()` ngoài Spring container, cần `initialize()` trước khi `schedule()`; đóng sau khi xong. Với bean chuẩn, lifecycle do Spring quản lý.

### Lỗi 7: Quên xử lý job bị cancel hoặc lỗi

`isDone()` có thể true khi lỗi/cancel, không chỉ khi thành công. Với Future, kiểm tra `isCancelled()` và `get()`; với nghiệp vụ quan trọng có status/metric riêng.

### Lỗi 8: Cho rằng cancel(true) hủy mọi side effect

Interrupt không bắt buộc dừng remote HTTP/DB hoặc rollback giao dịch đã commit. Dùng cancellation-aware API, timeout và idempotency.

### Lỗi 9: Mặc định @EnableScheduling phải có cho programmatic schedule()

Với bean `TaskScheduler` đã được quản lý, gọi trực tiếp `schedule(...)` không đòi `@EnableScheduling`. Annotation này dành cho infrastructure xử lý `@Scheduled`. Không trộn hai cơ chế rồi không biết job được đăng ký từ đâu.

### Lỗi 10: Lưu ScheduledFuture vào static map và gọi đó là persistent scheduling

Map và handle chỉ tồn tại trong JVM. Restart mất tất cả, nhiều pod có map riêng. Nếu lịch phải sống qua deploy/restart, dùng storage bền vững và cơ chế khôi phục.

### Lỗi 11: Nhiều pod đều chạy một công việc

Một lịch cục bộ không có đảm bảo toàn cluster. Dùng atomic claim/distributed coordination đúng và xử lý duplicate với idempotency.

### Lỗi 12: Giao Runnable nặng cho scheduler pool chỉ có một thread

`ThreadPoolTaskScheduler` chạy task trên scheduler thread. Công việc blocking dài làm trễ job đến hạn khác. Tăng pool có kiểm soát hoặc chuyển việc nặng sang worker executor có tracking/rejection rõ.

### Lỗi 13: Tự động retry mọi lỗi bằng schedule() mới mà không kiểm soát

Nếu job lỗi rồi lặp vô hạn bằng cách tự đăng ký sau 100 ms, backlog có thể tăng và gây retry storm. Cần retry budget, exponential backoff/jitter, job ID cố định và idempotency.

### Lỗi 14: Bỏ qua thời điểm quá khứ

Theo API, quá khứ chạy ngay khi có thể; nhưng sản phẩm có thể muốn reject hoặc đánh dấu missed. Phải xác định hành vi rõ cho người dùng, nhất là với reminder/hợp đồng có hạn giờ.

## 14. Checklist đưa vào production

Trước khi triển khai một tính năng one-shot scheduling:

1. **Xác định điểm thời gian:** input gồm timezone/offset hay không? Có DST? Lưu `Instant` hay cả timezone gốc?
2. **Xác định độ chính xác chấp nhận được:** trễ 1 giây, 1 phút hay không được trễ? Có chính sách missed/deadline?
3. **Chọn lifecycle:** lịch chỉ cần khi JVM đang chạy hay phải tồn tại sau restart?
4. **Xác định số instance:** một JVM hay nhiều pod? Job có thể chạy trùng?
5. **Chọn API đúng:** `schedule(Runnable, Instant)` cho một lần, không dùng periodic API nếu không muốn lặp.
6. **Giới hạn công suất:** scheduler pool size, công việc blocking, DB/HTTP connection, quota downstream và backlog.
7. **Quản lý handle:** có job ID, cơ chế cancel, trạng thái và quyền người dùng để hủy không?
8. **Phân biệt lỗi:** schedule reject tại caller, callback failure ở worker, future cancellation và timeout khi caller đợi.
9. **Bảo đảm cleanup:** lifecycle của scheduler, shutdown, cancellation; không để thread pool không được đóng.
10. **Quan sát:** start lag, run duration, success/failure/cancel, missed deadline và queue depth.
11. **Kiểm thử:** runnable example, thời điểm tương lai/quá khứ, nhiều jobs cùng hạn, restart, nhiều instance, duplicate và idempotency.
12. **Đảm bảo nghiệp vụ:** nếu cần “chạy đúng một lần” theo nghĩa tác động kinh doanh, thiết kế job store và idempotency; one-shot API chỉ giới hạn lịch **trong một scheduler instance**.

### Bảng lựa chọn nhanh

| Nhu cầu | Cơ chế thường phù hợp | Giới hạn cần nhớ |
| --- | --- | --- |
| Một lần sau vài giây trong JVM đang chạy | `TaskScheduler.schedule(Runnable, Instant)` | Không bền vững qua restart |
| Một lần vào giờ cụ thể của người dùng | Chuyển `LocalDateTime + ZoneId → Instant` rồi `schedule` | Phải xử lý timezone/DST |
| Lặp mỗi khoảng thời gian | `scheduleAtFixedRate` / `scheduleWithFixedDelay` | Không phải one-shot |
| Theo cron/timezone | `Trigger`/Cron hoặc scheduler chuyên dụng | DST, misfire, job lifecycle |
| Rất nhiều lịch kéo dài nhiều ngày, cần recovery | Persistent job store/Quartz JDBC | Cần clustering, retry và idempotency |
| Hẹn giờ rồi giao việc nặng | One-shot schedule để submit sang bounded executor | Future của schedule có thể chỉ theo dõi submission |
| Hủy một lịch chưa chạy | Giữ `ScheduledFuture` rồi `cancel(false)` | Handle cục bộ JVM, không bền vững |
| Mọi pod không được xử lý trùng | Durable claiming/coordination | Không tự có với TaskScheduler cục bộ |

## 15. Tổng kết và tài liệu chính thức

**Tám ý quan trọng:**

1. `TaskScheduler.schedule(Runnable, Instant)` đăng ký một công việc chạy **một lần** tại hoặc sau thời điểm chỉ định.
2. `Instant` là điểm thời gian tuyệt đối; convert từ ngày/giờ địa phương bằng `ZoneId` trước khi schedule.
3. Nếu thời điểm đã qua, API lên lịch chạy **ngay khi có thể**, không tự bỏ task.
4. `ScheduledFuture<?>` là handle theo dõi completion/cancel; `get()` có thể chặn và không nên gọi trong HTTP request chỉ để đợi một lịch dài hạn.
5. `ThreadPoolTaskScheduler` chạy việc trên chính scheduler threads, mặc định pool size là 1; task dài có thể làm lịch khác chậm.
6. Lỗi từ `schedule(...)` khi bị từ chối khác với lỗi xảy ra bên trong `Runnable.run()`.
7. Cancellation/shutdown **không** đồng nghĩa rollback tác động đã xảy ra ở database/remote system.
8. Để lịch chạy qua restart hoặc chỉ một instance thực thi trong cluster, cần persistence, claim/idempotency và cơ chế điều phối ngoài một scheduler cục bộ.

**Tài liệu chính thức:**

- [Spring Framework 6.2 – TaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/TaskScheduler.html) — `schedule(Runnable, Instant)`, trường hợp thời điểm quá khứ và `TaskRejectedException`.
- [Spring Framework 6.2 – ThreadPoolTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html) — pool size, lịch chạy, lifecycle, error handler và chính sách hủy.
- [Spring Framework 6.2 – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html) — cách dùng abstraction và các loại scheduler.
- [Java SE 17 – ScheduledFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html) — `getDelay`, `cancel`, `get` và completion state.
- [Java SE 17 – ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html) — scheduled queue, worker pool và remove-on-cancel.
- [Java SE 17 – Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) — thời điểm tuyệt đối.
- [Java SE 17 – ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html) — chuyển đổi múi giờ, daylight saving rules.

**Kết luận:** `schedule(task, instant)` là lựa chọn rõ ràng để **chạy một lần tại thời điểm mong muốn** trong một Spring scheduler đang sống. Hãy dùng `ScheduledFuture` để quản lý lịch cục bộ, giám sát độ trễ thực tế và chủ động thiết kế persistence/cluster coordination nếu đây là một yêu cầu nghiệp vụ quan trọng không được mất khi deploy hoặc restart.
