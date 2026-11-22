# Chọn lập lịch trực tiếp hay annotation theo mức cần điều khiển

> **Module:** Spring Framework – concurrency  
> **Nhóm:** TaskScheduler  
> **Mục tiêu:** Biết khi nào dùng `@Scheduled` để khai báo tác vụ lặp ổn định, khi nào gọi `TaskScheduler` trực tiếp để chủ động tạo, thay đổi, hủy và theo dõi lịch ở runtime; hiểu rằng cả hai có thể dùng cùng hạ tầng scheduler và đều cần kiểm soát tải, lỗi, thời gian và nhiều instance.

## 1. Câu trả lời nhanh

Trong Spring Framework, **`@Scheduled` là cách mô tả lịch cố định trên một phương thức do Spring quản lý**, còn **`TaskScheduler` là API điều khiển lịch bằng chương trình**. Đây không phải hai hệ thống thực thi tách biệt: một phương thức `@Scheduled` thường được đăng ký với scheduler tương thích, trong khi code có thể inject chính `TaskScheduler` ấy để lên lịch khác.

Chọn **`@Scheduled`** khi công việc có lịch tương đối ổn định, biết trước lúc ứng dụng khởi động, không đòi mỗi job có một handle để hủy/thay thế theo yêu cầu. Ví dụ: quét dữ liệu rác mỗi đêm, cập nhật cache định kỳ, ghi thống kê tổng hợp 5 phút/lần. Lịch có thể được externalize bằng property, nhưng được đăng ký theo vòng đời bean khi context khởi tạo.

Chọn **gọi `TaskScheduler` trực tiếp** khi lịch phụ thuộc vào dữ liệu hoặc hành động runtime: mỗi đơn hàng có thời điểm hết hạn riêng, người dùng bật/tắt một job, cần hủy một callback chưa chạy, đổi chu kỳ tại thời điểm thực thi, hoặc đưa một `Trigger` vào hệ thống do ứng dụng tính toán.

**Không chọn chỉ vì hiệu năng.** `@Scheduled` không phải “chậm hơn” `TaskScheduler`, và code gọi scheduler trực tiếp không tự có tính bền vững hoặc tính đúng cao hơn. Các yếu tố quyết định là **ai sở hữu lịch, ai có thể đổi/hủy lịch, lịch sống đến khi nào và hệ thống cần bảo đảm gì sau restart**.

## 2. Bức tranh cơ chế: annotation và API đều cần scheduler

~~~text
Nhánh A: lịch khai báo
  Spring context khởi tạo bean
         |
         v
  @EnableScheduling / scheduled annotation processor
         |
         v
  Tìm các phương thức @Scheduled
         |
         v
  Đăng ký tác vụ định kỳ vào scheduler
         |
         v
  ThreadPoolTaskScheduler / hạ tầng phù hợp
         |
         v
  Thực thi callback theo lịch

Nhánh B: lịch lập bằng chương trình
  Service nhận command hoặc dữ liệu runtime
         |
         v
  taskScheduler.schedule(...)/scheduleAtFixedRate(...)
         |
         v
  Giữ ScheduledFuture để cancel/kiểm tra
         |
         v
  Cùng scheduler (nếu inject cùng bean)
         |
         v
  Thực thi callback theo lịch
~~~

`TaskScheduler` là interface `org.springframework.scheduling.TaskScheduler`. Nó có API lên lịch một lần theo `Instant`, lên lịch bằng `Trigger`, chạy chu kỳ fixed-rate và fixed-delay.

`ThreadPoolTaskScheduler` là implementation thông dụng của Spring. Nó dùng scheduler thread pool có cấu hình, cung cấp vòng đời Spring, theo dõi và các hook liên quan. Khi dùng implementation này, **task thường thực thi ngay trên các scheduler thread**. Không được tưởng rằng scheduler chỉ gửi tín hiệu rồi một thread pool vô hạn khác tự chạy phần logic nặng.

`@Scheduled` là annotation trong package `org.springframework.scheduling.annotation`. Annotation chỉ có tác dụng khi Spring xử lý bean có lịch và scheduling được kích hoạt đúng context. Một method Java thông thường được gọi thủ công không vì thế trở thành một scheduled invocation.

## 3. Ma trận chọn cách lập lịch

| Yêu cầu | `@Scheduled` | `TaskScheduler` trực tiếp |
| --- | --- | --- |
| Chạy mỗi 5 phút hoặc vào giờ định sẵn, cấu hình ổn định | Rất phù hợp | Được, nhưng thêm code quản lý |
| Sử dụng property cho cron hoặc fixed delay từ lúc startup | Hỗ trợ tốt | Hỗ trợ qua code/config |
| Mỗi khách hàng có một lịch khác nhau | Không tiện, số phương thức không tương ứng số job | Phù hợp hơn để tạo lịch runtime |
| Có API “hủy job X” | Không có handle per-business-job trực tiếp từ annotation | Giữ và `cancel()` `ScheduledFuture` |
| Cần đổi chu kỳ lập tức mà không restart | Không tự động chỉ nhờ sửa property trong môi trường | Hủy và đăng ký lại theo code |
| Chỉ cần chạy một lần sau 30 giây | Không phải use case tự nhiên của `@Scheduled` | `schedule(Runnable, Instant)` |
| Lịch dựa trên kết quả bước trước hoặc điều kiện runtime | Có thể phải viết logic phụ | `Trigger` hoặc schedule lại sau completion |
| Tác vụ phải tồn tại qua JVM crash/restart | **Không tự bảo đảm** | **Không tự bảo đảm** |
| Chạy một lần toàn cluster khi có nhiều replica | **Không tự bảo đảm** | **Không tự bảo đảm** |
| Tránh đụng độ worker/DB khi quá tải | Cần thiết kế riêng | Cần thiết kế riêng |
| Muốn ít code, cấu hình dễ đọc với Spring | Thường tốt hơn | Tốt nếu cần quyền điều khiển thật sự |

Quy tắc quyết định: nếu lịch là **một phần của cấu hình triển khai**, hãy bắt đầu bằng `@Scheduled`. Nếu lịch là **một thực thể nghiệp vụ có ID, trạng thái và vòng đời riêng**, hãy bắt đầu từ API `TaskScheduler` hoặc một job scheduler bền vững hơn.

## 4. Lập lịch bằng @Scheduled: khai báo ngay trên bean

Trong một Spring Framework application, bật xử lý lịch:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}
~~~

Đây là **configuration snippet**; phải nằm trong context chứa bean muốn lập lịch. Khi dùng Spring Boot, cần xem các auto-configuration và `@EnableScheduling` thực tế, không tự suy đoán mọi dự án Boot đều bật lịch.

Bean có method:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class CacheCleanupJob {
    @Scheduled(fixedDelay = 60_000)
    public void cleanup() {
        // Xóa những entry đã hết hạn theo logic ứng dụng.
    }
}
~~~

Đây là đoạn mã **tích hợp**, nội dung `cleanup()` cần implementation thực tế. `fixedDelay = 60_000` có đơn vị mặc định milliseconds: lần chạy tiếp theo được tính sau khi lần hiện tại **hoàn tất**, không phải cứ đúng 60 giây tính từ lúc bắt đầu.

Đặc trưng của hướng khai báo:

- Đăng ký theo vòng đời bean trong `ApplicationContext`.
- Mức điều khiển phù hợp với lịch **biết trước**: cron, fixed delay/fixed rate, initial delay và cấu hình thay thế bằng property.
- Không phải vì method có annotation mà bạn có một `ScheduledFuture` gắn với business ID để tự gọi `cancel()`.
- Return value của method imperative `@Scheduled` thường không được dùng làm kết quả nghiệp vụ. Đừng mong `return orderId` chuyển thành một job result cho API caller.
- Với use case thông thường, method nên không có tham số để scheduler có thể gọi mà không cần request input.
- Không chuyển thông tin của một request web vào field mutable của singleton scheduled bean để chờ lần chạy sau: đây là shared state dễ tạo race.

## 5. fixedRate, fixedDelay và cron khác nhau

`@Scheduled` hỗ trợ ba cách mô tả lịch phổ biến:

~~~java
@Scheduled(fixedRate = 5_000)
public void metricsPulse() { /* task nhanh */ }

@Scheduled(fixedDelay = 5_000)
public void reconcileAfterLastRun() { /* task dài */ }

@Scheduled(cron = "0 */5 * * * *", zone = "UTC")
public void everyFiveMinutes() { /* task theo đồng hồ */ }
~~~

Ba method trên là **các snippet mô tả**, không phải một Java class độc lập. Đừng chạy cả ba để thực hiện cùng một nghiệp vụ trừ khi thực sự cần ba lịch riêng.

| Loại | Mốc tính lần chạy kế tiếp | Ý nghĩa |
| --- | --- | --- |
| `fixedRate` | Lịch theo chu kỳ tính từ các thời điểm bắt đầu dự kiến | Thích hợp heartbeat/poll định kỳ; có thể trễ khi scheduler bận |
| `fixedDelay` | Sau khi **lần chạy trước hoàn tất** cộng delay | Thích hợp khi cần khoảng nghỉ giữa hai lượt |
| `cron` | Biểu thức dựa trên thời điểm trên lịch | Thích hợp chạy mỗi sáng, đầu giờ, ngày trong tuần... |

Ví dụ task mất 3 giây và `fixedDelay=5s`: nếu start tại `t=0`, hoàn tất `t=3s`, lần tiếp theo dự kiến khoảng `t=8s`, chưa xét scheduler contention. Với `fixedRate=5s`, mốc định kỳ dự kiến sẽ là `t=0,5,10...`, nhưng runtime không bảo đảm callback bắt đầu đúng tuyệt đối tại mọi mốc.

Đừng khẳng định rằng một fixed-rate task trên `ScheduledThreadPoolExecutor` mặc nhiên sẽ chạy **chồng lấn với chính nó** khi mất hơn một period: implementation JDK này không chạy chồng lấn những lần thực thi kế tiếp của **cùng một periodic task**. Tuy nhiên các lịch khác nhau, annotation repeatable, task chạy `@Async`, và các instance ứng dụng khác nhau vẫn có thể tạo **concurrency** thực tế.

Spring cron dùng **sáu trường**, có trường **giây** ở đầu: `0 */5 * * * *` là phút 0, 5, 10... tại giây 0. Không sao chép một biểu thức Unix cron năm trường rồi nghĩ rằng thứ tự giống hệt.

## 6. Chỉnh lịch khai báo qua property, và giới hạn runtime

Để lịch khác nhau giữa các môi trường triển khai:

~~~java
@Component
public class DailyCleanupJob {
    @Scheduled(cron = "${jobs.cleanup.cron:-}", zone = "UTC")
    public void cleanup() {
        // Công việc được gọi ở các mốc cron.
    }
}
~~~

Trong `application.yaml`:

~~~yaml
jobs:
  cleanup:
    cron: "0 0 2 * * *"
~~~

Đây là **mã Spring và cấu hình tích hợp**. Dấu `-` là giá trị disabled cron được Spring hỗ trợ khi dùng `@Scheduled`: cho phép tắt lịch bằng property. Tên property trong ví dụ là tùy ứng dụng.

Giới hạn: giá trị placeholder/SpEL thông thường được Spring đọc khi đăng ký lịch trong quá trình khởi tạo bean/context. **Thay đổi giá trị trong một cấu hình bên ngoài không mặc nhiên đăng ký lại lịch ngay lập tức** trong một ứng dụng thông thường. Nếu một hệ thống có hot reload config chuyên dụng, cần xác nhận nó thật sự hủy lịch cũ và đăng ký lịch mới; không đoán từ việc bean đọc lại property.

Khi cần người dùng nhấn “đổi từ 5 phút thành 10 phút” có hiệu lực tại runtime, hãy có một **service điều phối lịch bằng code** thay vì dùng một `@Scheduled` cố định rồi thay field mutable trong method.

## 7. Lập lịch trực tiếp: điều khiển bằng TaskScheduler

Inject `TaskScheduler` vào một service. Ba nhóm API thường dùng:

~~~java
ScheduledFuture<?> oneTime =
    scheduler.schedule(
        () -> doOneTimeWork(),
        Instant.now().plusSeconds(30));

ScheduledFuture<?> fixedRate =
    scheduler.scheduleAtFixedRate(
        () -> poll(),
        Duration.ofSeconds(10));

ScheduledFuture<?> fixedDelay =
    scheduler.scheduleWithFixedDelay(
        () -> processBatch(),
        Duration.ofSeconds(10));
~~~

Đây là **các snippet API**, giả định có `scheduler`, `doOneTimeWork`, `poll` và `processBatch`. Import `TaskScheduler`, `ScheduledFuture`, `Duration`, `Instant`. Cách đặt lịch thực tế nằm ở các overload tương ứng và implementation được inject.

Khác với annotation, **caller chủ động quyết định khi nào đăng ký**: lúc nhận API request, lúc đọc một bản ghi deadline, khi công việc trước hoàn tất hoặc sau khi áp dụng business rule. Lời gọi trả một `ScheduledFuture` (trường hợp lập lịch với một số `Trigger` có thể không có lần chạy tiếp theo và trả `null`) để ứng dụng theo dõi hoặc cancel.

`schedule(Runnable, Instant)` đặt **một lần thực thi** vào thời điểm cho trước; khi đặt thời điểm đã trôi qua, scheduler có thể thực thi ngay hoặc sớm nhất có thể. Nó không lưu một job bền vững vào database: nếu JVM chết trước thời điểm đó, task được giữ trong bộ nhớ có thể mất.

`scheduleAtFixedRate` và `scheduleWithFixedDelay` tạo **lịch lặp**. Nếu đã nhận handle, controller/service có thể gọi `cancel(false)` khi job bị dừng theo nghiệp vụ. Điều này có ý nghĩa vì business user có thể muốn bật/tắt lịch mà không cần rebuild/redeploy ứng dụng.

## 8. ScheduledFuture: quyền hủy không đồng nghĩa rollback

Với API `TaskScheduler`, handle có thể giữ lại:

~~~java
ScheduledFuture<?> handle =
    scheduler.scheduleAtFixedRate(action, Duration.ofSeconds(15));

// Khi nhận yêu cầu dừng:
boolean accepted = handle.cancel(false);
~~~

Đây là **mẫu tích hợp**, biến `scheduler`/`action` phải được cung cấp. `cancel(false)` ngăn những lần kích hoạt kế tiếp khi cancel thành công, **không yêu cầu interrupt một lượt đang chạy**. Với `cancel(true)`, implementation có thể cố gửi interrupt đến task, nhưng không bảo đảm JDBC, HTTP, file I/O hay remote side effect thực sự dừng.

Một số lưu ý:

- Nếu task đã hoàn tất, đã bị hủy, hoặc scheduler đã từ chối, `cancel` không nên được diễn giải là “chắc chắn mọi thứ đã dừng”.
- Lịch repeating bị cancel có thể vẫn có **một lần chạy đang in-flight**; handler nghiệp vụ phải idempotent và kiểm tra trạng thái nếu cần.
- Giữ `ScheduledFuture` chỉ trong `Map` của JVM là điều khiển **cục bộ**. Sau restart, map mất; không có automatic restore lịch theo business ID.
- Hủy lịch cũ rồi đăng ký lại có một khoảng chuyển tiếp. Nếu song song có nhiều caller, cần khóa/trạng thái để tránh hai lịch cùng đăng ký.
- Nếu hủy vì request hết deadline, vẫn cần I/O timeout thật ở HTTP/DB; việc cancel future không xóa giao dịch đã commit.

Đừng tạo một bản ghi “CANCELLED” ở DB và tin rằng mọi app instance đã dừng lịch chỉ vì một instance có handle. Bài toán nhiều node cần ownership/leader election/lease hoặc scheduler phân tán phù hợp.

## 9. Ví dụ Java 17 + Spring Framework chạy được: annotation và API cạnh nhau

Ví dụ dưới đây dùng **Spring Framework 6.2.9**. Một `@Scheduled` method tự kích hoạt sau initial delay. Đồng thời `main` dùng chính bean `TaskScheduler` để tạo một lịch chạy một lần và một lịch recurring sẽ bị hủy trước lần đầu.

Chương trình dùng latch để không phụ thuộc vào thứ tự thực thi của worker. Ba dòng in chỉ do `main` xuất ra nên thứ tự xác định; không cần internet, database hay Spring Boot.

### Cấu trúc

~~~text
spring-scheduling-choice/
├── pom.xml
└── src/main/java/demo/SchedulingChoiceDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-scheduling-choice</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.9</version>
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
      </plugin>
    </plugins>
  </build>
</project>
~~~

### src/main/java/demo/SchedulingChoiceDemo.java

~~~java
package demo;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

public class SchedulingChoiceDemo {
    private static final CountDownLatch ANNOTATED = new CountDownLatch(1);

    public static class Heartbeat {
        @Scheduled(initialDelay = 50, fixedDelay = 200)
        public void pulse() {
            ANNOTATED.countDown();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableScheduling
    public static class SchedulingConfig {
        @Bean
        public Heartbeat heartbeat() {
            return new Heartbeat();
        }

        @Bean("taskScheduler")
        public ThreadPoolTaskScheduler taskScheduler() {
            ThreadPoolTaskScheduler scheduler =
                    new ThreadPoolTaskScheduler();
            scheduler.setPoolSize(2);
            scheduler.setThreadNamePrefix("schedule-");
            return scheduler;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     SchedulingConfig.class)) {
            TaskScheduler scheduler = context.getBean(TaskScheduler.class);
            boolean annotationExecuted = ANNOTATED.await(3, TimeUnit.SECONDS);

            CountDownLatch DIRECT = new CountDownLatch(1);
            ScheduledFuture<?> once = scheduler.schedule(
                DIRECT::countDown,
                Instant.now().plusMillis(100));
            boolean directExecuted =
                once != null && DIRECT.await(3, TimeUnit.SECONDS);

            ScheduledFuture<?> repeating = scheduler.scheduleAtFixedRate(
                () -> { },
                Instant.now().plusSeconds(10),
                Duration.ofSeconds(1));
            boolean recurringCancelled = repeating.cancel(false);

            System.out.println("Annotation executed: " + annotationExecuted);
            System.out.println("Direct schedule executed: " + directExecuted);
            System.out.println("Recurring cancelled: " + recurringCancelled);
        }
    }
}
~~~

Chạy từ thư mục project (JDK 17+, Maven):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SchedulingChoiceDemo
~~~

**Stdout mong đợi trên máy đủ tài nguyên để xử lý callback trong hạn 3 giây**:

~~~text
Annotation executed: true
Direct schedule executed: true
Recurring cancelled: true
~~~

Mã đã được **biên dịch với target Java 17 và thực thi** cùng Spring Framework 6.2.9 trên JDK mới hơn; ba dòng stdout trên đã được kiểm tra chính xác.

Giải thích chi tiết:

1. `@EnableScheduling` đăng ký xử lý annotation trong context và `Heartbeat` là bean `@Bean`, nên method `pulse()` được đăng ký dù caller không gọi nó thủ công.
2. Bean `ThreadPoolTaskScheduler` tên `taskScheduler` có pool size 2; `@Scheduled` và API trực tiếp đều có thể dùng cùng scheduler này.
3. `ANNOTATED.await(...)` chỉ là điểm đồng bộ cho demo. Application production không cần main thread chờ từng tick.
4. Lệnh `schedule(..., Instant.now().plusMillis(100))` lên lịch một tác vụ một lần; latch xác nhận callback đã chạy.
5. Lệnh `scheduleAtFixedRate(..., Instant.now().plusSeconds(10), ...)` tạo lịch có lần đầu ở tương lai; `cancel(false)` được gọi ngay nên xác nhận có thể hủy lịch trước khi nó chạy.
6. `try`-with-resources đóng `ApplicationContext`; Spring quản lý lifecycle và shutdown scheduler bean. Không để thread pool demo sống mãi sau khi chương trình kết thúc.

**Giới hạn test:** Không nên lấy ba giá trị `true` làm cam kết mọi máy/VM đều lên lịch chính xác từng mili giây. Khi hệ thống bị treo hoặc scheduler shutdown, một latch có thể hết hạn. Điều quan trọng của demo là wiring và cơ chế registration/cancellation.

## 10. Dynamic job registry: khi mỗi job có ID và quyền dừng

Với API nghiệp vụ “bắt đầu polling đơn hàng `order-42` mỗi 10 giây, thay chu kỳ, dừng polling”, một service có thể lưu `ScheduledFuture` theo business key. Đây là **mã tích hợp Spring**, không phải app độc lập; nó giả định đã có `TaskScheduler` bean.

~~~java
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ScheduledFuture;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Service;

@Service
public class DynamicJobRegistry implements DisposableBean {
    private final TaskScheduler scheduler;
    private final Map<String, ScheduledFuture<?>> tasks = new HashMap<>();

    public DynamicJobRegistry(TaskScheduler scheduler) {
        this.scheduler = scheduler;
    }

    public synchronized void startOrReplace(
            String jobId, Runnable work, Duration period) {
        if (jobId == null || jobId.isBlank() ||
            work == null || period == null || period.isZero() ||
            period.isNegative()) {
            throw new IllegalArgumentException("Invalid job settings");
        }

        stop(jobId);
        ScheduledFuture<?> next =
            scheduler.scheduleAtFixedRate(work, period);
        tasks.put(jobId, next);
    }

    public synchronized boolean stop(String jobId) {
        ScheduledFuture<?> previous = tasks.remove(jobId);
        return previous != null && previous.cancel(false);
    }

    @Override
    public synchronized void destroy() {
        for (ScheduledFuture<?> future : tasks.values()) {
            future.cancel(false);
        }
        tasks.clear();
    }
}
~~~

**Điều gì được cải thiện so với annotation?**

- Business ID của từng lịch xuất hiện rõ trong map, không cần một method `@Scheduled` khác cho mỗi ID.
- API/controller có thể gọi `startOrReplace` khi thông số thay đổi và `stop` khi người dùng tắt job.
- `synchronized` bảo vệ các thao tác cập nhật map trong **một JVM**, tránh hai request đồng thời thay đổi cùng `jobId` trong cùng instance.
- `DisposableBean.destroy()` yêu cầu hủy handle khi container shutdown; các callback đang chạy vẫn cần dừng/cleanup theo hợp đồng riêng.

**Giới hạn quan trọng:** Đây là **registry cục bộ trong bộ nhớ**, không phải production multi-node scheduler. Nó không lưu thời điểm và trạng thái job trong DB, không khôi phục sau process restart, không ngăn hai replica có hai lịch cho cùng job, và `cancel(false)` không đảo ngược một lượt đang chạy. Nếu có yêu cầu khắt khe về delivery hoặc cluster, cần một job store/lease/leader selection phù hợp.

Ngoài ra, thao tác “hủy lịch cũ rồi đăng ký lịch mới” không atomic với callback đã chạy. Một bản triển khai chặt chẽ có thể cần generation/version token: callback kiểm tra phiên bản job đang sở hữu trước khi tạo side effect.

## 11. Trigger khi thời điểm tiếp theo không phải chu kỳ cố định

Đôi khi thời điểm tiếp theo phụ thuộc vào lịch làm việc, kết quả lần chạy trước hoặc quy tắc runtime. `TaskScheduler.schedule(Runnable, Trigger)` cho phép đăng ký với một `Trigger`.

Ví dụ dùng `CronTrigger`:

~~~java
TaskScheduler scheduler = /* bean được Spring inject */;

ScheduledFuture<?> handle = scheduler.schedule(
    this::runReconciliation,
    new CronTrigger("0 */10 * * * *", ZoneId.of("UTC"))
);
~~~

Đây là **snippet tích hợp**, không phải class độc lập; cần import `CronTrigger`, `ZoneId`, `ScheduledFuture`, và method `runReconciliation`. Spring 6.2 hỗ trợ khởi tạo `CronTrigger` với timezone/zone. `schedule` có thể trả `null` nếu trigger không có thời điểm thực thi tiếp theo; code giữ handle phải kiểm tra điều này.

Với `Trigger` do ứng dụng định nghĩa, Spring truyền `TriggerContext` (các thời điểm được lên lịch, thực tế và hoàn tất trước đó) để tính lần kế tiếp. Có thể dùng để né giờ bảo trì hoặc áp delay phụ thuộc kết quả. Tuy nhiên nếu cần thay lịch ngay trong khi trigger đã đăng ký, việc thay đổi một object mutable bên ngoài dễ gây race; **hủy handle cũ và đăng ký handle mới** thường dễ kiểm soát hơn.

Đừng đánh đồng việc tính `nextExecution()` với một hệ thống lưu thời gian vào database: một `Trigger` trong memory không mang lại recovery sau crash.

## 12. Thread pool, độ trễ và tác vụ chặn

Cả hai cách lập lịch đều có thể gặp quá tải khi scheduler thread chạy công việc quá lâu.

Ví dụ một `ThreadPoolTaskScheduler` cấu hình `poolSize=1` và một task truy vấn DB mất 30 giây: các lịch khác dùng cùng scheduler có thể bị chậm dù chúng chỉ chạy vài mili giây. Dùng API trực tiếp thay vì annotation **không tự tạo thêm worker**.

Gợi ý thiết kế:

1. **Task rất ngắn:** chạy trực tiếp trên scheduler thread có thể đơn giản và đủ dùng.
2. **Task I/O/blocking dài:** dùng scheduler để phát tín hiệu đến một `TaskExecutor` riêng có pool/queue hữu hạn, hoặc dùng một job worker có giới hạn. Khi executor bão hòa, xử lý rejection/backpressure thay vì nộp mãi.
3. **Task có side effect lớn:** ngoài số thread, cần timeout, idempotency, retry policy và trạng thái job.
4. **Nhiều lịch cho nhiều tenant:** đếm tổng callback đến hạn, không chỉ số lịch được đăng ký. Một thời điểm cron chung có thể tạo thundering herd.
5. **SLA ngắn:** đo `scheduled_at`, `actual_started_at`, `finished_at` và tính scheduling lag; fixedRate/cron không cam kết exact real-time.
6. **Lịch lặp quá nhanh:** cân nhắc tối thiểu period, rate limiting và tránh polling khi hệ thống chưa phục hồi.

Trong Spring, `TaskScheduler` và `TaskExecutor` là hai abstraction khác nhau. Có thể cấu hình hai bean riêng có tên rõ ràng, tránh dựa vào auto-configuration không được kiểm chứng.

## 13. fixedRate, reentrancy và nhiều lịch chồng lấn

Một sai lầm thường gặp là nghĩ “tôi chỉ có một method `@Scheduled`, nên không thể có hai lượt xử lý cùng một nghiệp vụ”.

Các nguồn overlap bao gồm:

- Cùng bean có nhiều `@Scheduled` annotation áp lên cùng method (repeatable schedules) với trigger khác nhau.
- Code gọi trực tiếp method nghiệp vụ song song với lượt do scheduler kích hoạt.
- Có hai hoặc nhiều **replica** ứng dụng, mỗi replica đăng ký cùng một annotation.
- Task `@Scheduled` nhanh chóng submit một `@Async` job khác rồi return, khiến các lần async xử lý có thể overlap.
- Runtime registry tạo hai handle cho cùng business key do race hoặc recovery chưa đồng bộ.

Các giải pháp tùy bối cảnh: lock cục bộ khi chỉ có một JVM, version/lease hoặc khóa phân tán nếu nhiều instance, idempotency key khi có side effect và tránh dùng mutable state không thread-safe.

Không dùng `synchronized` ở một Spring bean rồi tưởng rằng nó bảo đảm **mỗi cluster chỉ có một job chạy**. Monitor lock lease, duplicate execution và partial failure, nhất là khi công việc tạo invoice, thu tiền hoặc gửi notification.

## 14. Timezone, cron và mốc thời gian

`@Scheduled(cron = "0 0 2 * * *", zone = "UTC")` thể hiện lịch theo **thời gian đồng hồ của một timezone**. Khi zone có daylight saving time, có ngày một giờ địa phương bị bỏ qua hoặc lặp lại; cần xem chính sách của business nếu job chạy vào 02:00.

Lưu ý:

- Cron mang ý nghĩa **calendar schedule**; fixed delay/rate dựa trên khoảng thời gian giữa các lần thực thi.
- Đối với bản ghi “hết hạn sau 15 phút”, thường nên lưu một **`Instant` deadline** thay vì một cron của server. Khi reload từ DB, tính lại thời điểm.
- Nên dùng `ZoneId`/timezone được chỉ rõ thay vì ngầm dựa vào default timezone của container.
- Nếu công việc yêu cầu chính xác một lần mỗi ngày theo giờ địa phương, phải có **business date key** và dedupe phù hợp, không chỉ tin scheduler.
- Clock shift/NTP, pause, GC stop-the-world, autoscaling và process restart có thể làm một lịch bị trễ; nếu phải catch-up, ứng dụng cần quy tắc riêng.
- Một cron schedule trong memory không có lịch sử phát lại những thời điểm đã bỏ lỡ sau restart.

## 15. Error handling, shutdown và cancellation

Một scheduled callback ném exception cần được ghi nhận và phân loại. Nếu chỉ tin rằng scheduler sẽ tiếp tục theo bất kỳ policy nào, ứng dụng có thể âm thầm bỏ công việc.

Với Spring `ThreadPoolTaskScheduler`, có thể cấu hình `ErrorHandler` phù hợp và xử lý lỗi tại ranh giới công việc. Hành vi tiếp tục hay dừng các future periodic sau lỗi có thể phụ thuộc wrapper, implementation và cách scheduler xử lý exception; hãy **test thực tế** thay vì suy luận từ exception của một method.

Một số nguyên tắc:

- Callback phải ghi log có correlation/job ID nhưng không dump thông tin nhạy cảm; metric có label cardinality thấp.
- Không auto-retry vô hạn hoặc retry nóng ngay trong scheduler thread khi downstream quá tải.
- Nếu cần retry, chọn backoff/jitter, max attempts, deadline và idempotency, có thể đưa retry vào job store.
- Khi shutdown, cần xác định task đang chạy sẽ được kết thúc, chờ bao lâu và có được interrupt hay không. `ThreadPoolTaskScheduler` có các tùy chọn lifecycle; không giả định default phù hợp mọi workload.
- `ScheduledFuture.cancel(false)` ngăn những lần chạy tiếp theo khi được chấp nhận; nó **không** bảo đảm giao dịch/HTTP call đang chạy bị dừng.
- Với lịch trực tiếp, **sở hữu handle** và vòng đời registry là trách nhiệm của service đăng ký. Nếu context đóng, các handle trong map không nên được coi là job persistent.

Từ góc độ API, status “job stopped” có thể nghĩa là **không đăng ký lần chạy kế tiếp**, khác với “không còn work đang chạy”. Hai trạng thái cần đặt tên riêng khi nghiệp vụ quan trọng.

## 16. Độ tin cậy: cả annotation lẫn direct đều không phải durable job store

Trong ứng dụng Spring chạy trên một JVM, `@Scheduled` và `TaskScheduler` dựa trên runtime process. Khi process crash hoặc được thay thế trong deployment, các lịch trong memory không tự được khôi phục như một hàng đợi durable.

Hỏi trước khi chọn:

- **Có được phép bỏ lỡ một lượt?** Với metrics refresh, có thể chấp nhận. Với hóa đơn đến hạn, có thể không.
- **Job có cần chạy đúng một lần toàn cluster?** `@Scheduled` chạy ở mọi replica trừ khi thiết kế cơ chế đồng bộ. Direct schedule trong nhiều replica cũng vậy.
- **Có cần lưu job ID và next fire time?** Nếu có, cần DB/job store để quản lý state và recovery.
- **Có cần pause/resume theo tenant, người dùng hay feature?** Direct registration hữu ích trong JVM; đa node phải có cơ chế ownership.
- **Có cần phục hồi công việc đang chạy khi worker chết?** Khi đó là bài toán durable queue, lease/retry, checkpoint và idempotency, không chỉ về cú pháp scheduling.

Các lựa chọn có thể gồm Quartz với JDBC JobStore, một broker/job queue và worker có lịch, hoặc hệ thống workflow orchestration tùy yêu cầu. Việc dùng Quartz không tự bảo đảm business effect exactly-once nếu worker crash sau side effect nhưng trước khi đánh dấu job hoàn tất.

**Tách hai lớp:** lớp “khi nào job đến hạn” và lớp “job được thực hiện đáng tin cậy ra sao”. `TaskScheduler` giải quyết lớp đầu trong tiến trình hiện tại; durability, dedupe, distributed coordination thuộc lớp thiết kế hệ thống.

## 17. Spring Boot: kiểm tra auto-configuration, đừng suy đoán

Spring Boot có hỗ trợ task scheduling auto-configuration và thuộc tính `spring.task.scheduling.*`. Tuy nhiên hành vi cụ thể phụ thuộc version Boot, các bean đã tự khai báo và lựa chọn virtual threads.

Trong một project Spring Framework thuần, ví dụ mục 9 **chủ động khai báo** `ThreadPoolTaskScheduler` để không phụ thuộc việc một framework khác có tạo scheduler hay không.

Khi làm việc với Boot:

1. Xác nhận `@EnableScheduling` thực sự được bật.
2. Kiểm tra bean `TaskScheduler` mà `@Scheduled` đang dùng; ghi rõ tên và `poolSize`.
3. Kiểm tra bean `TaskExecutor` cho `@Async` là một thành phần **khác**; đừng nghĩ tăng `spring.task.execution.pool.max-size` luôn làm scheduled callback chạy song song hơn.
4. Khi ứng dụng định nghĩa custom scheduler, thuộc tính auto-config có thể không tác động như mong đợi.
5. Nếu nhiều scheduler tồn tại, chỉ định lựa chọn với tên/qualifier hoặc cấu hình scheduling rõ ràng; không để việc chọn ngẫu nhiên theo bean order.
6. Với virtual threads, đọc tài liệu Spring Boot của phiên bản đang dùng, đặc biệt sự khác nhau giữa scheduler thread pool và `SimpleAsyncTaskScheduler`.

Một cấu hình chủ động đủ cho nhiều project:

~~~java
@Configuration
@EnableScheduling
public class ProductionSchedulerConfig {
    @Bean("taskScheduler")
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
            new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(4);
        scheduler.setThreadNamePrefix("jobs-");
        return scheduler;
    }
}
~~~

Đây là **cấu hình tích hợp**; cần imports tương ứng và benchmark theo workload, không coi `poolSize=4` là một giá trị tối ưu chung.

## 18. Quan sát và kiểm thử sự khác biệt

Một bộ test tốt phải kiểm tra **quyền điều khiển lịch**, không chỉ kiểm tra method có chạy:

1. **Wiring annotation:** tạo context có `@EnableScheduling`, bean `@Scheduled`, latch và scheduler đã xác định. Assert method kích hoạt trong thời hạn hợp lý.
2. **Direct one-shot:** gọi `schedule(Runnable, Instant)` và xác nhận callback chạy một lần tại thời điểm không sớm hơn hợp đồng cho phép.
3. **Cancel trước lần chạy đầu:** lên lịch xa trong tương lai rồi gọi `cancel(false)`; xác nhận task không chạy trong khoảng kiểm thử.
4. **Cancel khi đang chạy:** dùng `CountDownLatch` giữ callback, gọi cancel và kiểm tra **khác biệt** giữa ngăn lượt sau và interrupt.
5. **Dynamic reconfiguration:** start ID A với chu kỳ P, thay bằng chu kỳ Q, bảo đảm không còn hai handle active cho cùng ID trong một JVM.
6. **Lỗi callback:** chủ động ném exception, đo log/metric và kiểm tra policy tiếp tục của scheduled job trên implementation đang chạy.
7. **Scheduler saturation:** giữ scheduler thread bằng latch, đo độ trễ của callback khác để chứng minh pool contention.
8. **Multiple replicas:** triển khai hai application instances, kiểm tra event có thể được thực hiện hai lần; xác nhận lease/lock hoặc dedupe hoạt động.
9. **Restart:** tạo job rồi restart JVM; kiểm tra contract khôi phục thực tế từ persistent store nếu có.
10. **Cron timezone:** test lịch qua mốc giờ mùa hè/giờ địa phương nếu nghiệp vụ yêu cầu.
11. **Integration với downstream:** kiểm tra database timeout, retry và hiệu ứng trùng lặp thay vì chỉ assert scheduler callback được gọi.
12. **Context shutdown:** đóng context và xác nhận scheduler thread được release, không còn job mới từ instance đã dừng.

Metric gợi ý: `scheduled_jobs_active`, `schedule_trigger_total`, `schedule_lag_ms`, `job_duration_ms`, `job_failure_total`, `job_cancel_total`, `scheduler_queue_depth` (nếu implementation expose), executor saturation và backlog persistent nếu có. Không gắn raw job/user ID có cardinality cao lên metric label; đưa ID vào trace/log có kiểm soát.

Với unit test, có thể mock `TaskScheduler` để kiểm tra `schedule`/`cancel` đúng hợp đồng; với test thời gian thực, dùng latch và tolerance phù hợp. Tránh viết test dễ flake chỉ vì `Thread.sleep(50)`.

## 19. Tình huống áp dụng

### A. Xóa cache mỗi đêm

**Yêu cầu:** một tác vụ kiểm tra cache hết hạn lúc 02:00 UTC mỗi ngày; không có business ID riêng, không cần từng khách hàng bật/tắt.

**Chọn:** `@Scheduled(cron = "0 0 2 * * *", zone = "UTC")`. Đưa cron vào property; theo dõi run duration và failure. Nếu triển khai nhiều replica, cân nhắc thực hiện idempotent hoặc có leader/lock nếu không muốn mỗi instance tự xóa.

### B. Hẹn giờ hết hạn phiên làm việc theo từng session

**Yêu cầu:** mỗi session có một `expiresAt` khác nhau, khi gia hạn thì dời thời điểm, khi logout thì hủy lịch.

**Chọn:** `TaskScheduler.schedule(Runnable, Instant)` với registry cho session/job ID, nếu scale nhỏ trong một process và chấp nhận mất lịch khi restart. Với sản phẩm cần chính xác qua restart và nhiều node, lưu `expiresAt` trong DB/TTL store, có scanner/queue bền vững và kiểm tra expiry lại khi xử lý; direct timer chỉ là tối ưu latency, không phải nguồn chân lý.

### C. Poll API bên ngoài sau khoảng nghỉ do server chỉ dẫn

**Yêu cầu:** sau khi gọi API, server trả `Retry-After`, và lượt tiếp theo phụ thuộc trạng thái runtime.

**Chọn:** direct scheduling hoặc trigger/async retry component có giới hạn. Không cần đặt một method `@Scheduled` cố định 100ms rồi liên tục kiểm tra xem đến giờ retry chưa. Khi downstream quá tải, tôn trọng quota, backoff/jitter, deadline và cancellation.

### D. Tổng hợp báo cáo theo thời khóa biểu đơn vị

**Yêu cầu:** chạy mỗi thứ Hai theo timezone của từng chi nhánh, có yêu cầu không bỏ sót và không thực thi trùng.

**Chọn:** business schedule được lưu bền và một scheduler/worker phân tán có policy về calendar, catch-up và deduplication. Có thể dùng `@Scheduled` rất nhẹ để đánh thức poller đọc danh sách job đến hạn, nhưng phần chính của bài toán là **job store và coordination**, không phải annotation hay API nào đẹp hơn.

## 20. Những hiểu nhầm và phản ví dụ

| Hiểu nhầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| “`@Scheduled` và `TaskScheduler` là hai engine độc lập.” | Annotation thường đăng ký lên scheduler tương thích | Nhìn vào scheduler bean thực tế |
| “Chỉ cần `@Scheduled` là có job ID để hủy.” | Annotation không trả `ScheduledFuture` cho business caller | Dùng direct scheduling nếu cần handle |
| “Sửa config cron thì job lập tức đổi mốc.” | Context có thể đã đăng ký lịch từ lúc startup | Implement dynamic re-registration có kiểm soát |
| “`TaskScheduler` cho phép job sống qua restart.” | Local scheduler giữ handle trong memory | Lưu job state vào DB/job store |
| “fixedRate luôn chạy đồng thời nhiều lượt cùng task.” | JDK periodic schedule không overlap cùng periodic task | Xem scheduler implementation và các nguồn concurrency khác |
| “fixedDelay chỉ là fixedRate viết khác cú pháp.” | Delay tính từ **completion**, rate theo chu kỳ nominal | Chọn đúng semantics dựa trên workload |
| “TaskScheduler tự cancel HTTP/SQL khi `Future.cancel`.” | Cancel không đảm bảo remote operation dừng | Đặt I/O timeout và idempotency |
| “`poolSize=1` đủ cho mọi @Scheduled job.” | Một callback blocking giữ scheduler thread lâu | Đo tải, tách worker pool hoặc tăng capacity hợp lý |
| “Một `synchronized` method đảm bảo một lượt trên toàn cluster.” | Lock chỉ trong một JVM | Lease/distributed lock/deduplication |
| “Cron luôn chạy bù mọi lần đã lỡ sau shutdown.” | Lịch memory thường không có replay history | Persist schedule/catch-up policy |
| “`@Scheduled` có thể nhận trực tiếp mọi tham số HTTP request.” | Method định kỳ được framework gọi, không gắn request input | Dùng queue/job record và direct control |
| “Thay annotation bằng direct là tự có backpressure.” | Chỉ khác registration/control, không khác resource limits | Bounded executor, rate limiting và metrics |

## 21. Checklist code review

- Tôi xác định lịch là **cấu hình cố định** hay **thực thể runtime** có ID và vòng đời riêng.
- Với lịch ổn định, tôi ưu tiên `@Scheduled` và `@EnableScheduling` đúng context.
- Với lịch động, tôi có registry/handle rõ ràng khi dùng `TaskScheduler`, biết khi nào cancel/reschedule.
- Tôi chọn `fixedRate`, `fixedDelay`, `cron` theo đúng mốc thời gian và hiểu timezone.
- Tôi không tin property đổi trong runtime sẽ tự động cập nhật mọi `@Scheduled` job.
- Tôi hiểu `ScheduledFuture.cancel(false)` không hủy tác vụ đã chạy hoặc rollback side effect.
- Scheduler thread không chạy blocking I/O vô hạn; tôi có timeout và pool/queue hữu hạn nếu cần.
- Tôi có chiến lược xử lý lỗi, retry/backoff, shutdown và lịch trễ.
- Tôi biết lịch có sống qua JVM restart hay không, và ai sở hữu job state bền vững.
- Tôi kiểm soát duplicate execution trong nhiều replica bằng lease/lock/dedupe/idempotency.
- Tôi test annotation registration, direct schedule, cancel, overload, nhiều node và recovery phù hợp.
- Tôi có metric job lag, duration, failure, cancellation, pending/retry và log correlation an toàn.

**Kết luận:** `@Scheduled` phù hợp nhất cho những công việc định kỳ **khai báo một lần theo cấu hình**, đơn giản và dễ vận hành. `TaskScheduler` phù hợp khi cần **ra quyết định tại runtime, nhận handle, hủy hoặc thay đổi lịch theo business ID**. Hai lựa chọn không khác nhau ở bảo đảm durability, tránh thực thi trùng hay chống quá tải: những yêu cầu đó cần scheduler/worker architecture, timeout, idempotency và persistence phù hợp.

## Tài liệu tham khảo chính thức

- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableScheduling`, `@Scheduled`, `TaskScheduler`, `Trigger` và cách đăng ký công việc.
- [Spring Framework – TaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/TaskScheduler.html): `schedule`, `scheduleAtFixedRate`, `scheduleWithFixedDelay` và `ScheduledFuture`.
- [Spring Framework – @Scheduled Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html): `fixedDelay`, `fixedRate`, cron, zone và semantics đăng ký.
- [Spring Framework – CronTrigger Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/support/CronTrigger.html): trigger theo cron và zone.
- [Spring Framework – ThreadPoolTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html): scheduler pool và vòng đời.
- [Java SE 17 – ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): cơ chế periodic scheduling và quy tắc không overlap của cùng periodic task.
- [Spring Boot – Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): auto-configuration và configuration property liên quan.
