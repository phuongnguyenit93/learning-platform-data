# Thử luồng ảo và quan sát tác dụng của spring.main.keep-alive

**Chủ đề:** Spring Boot Application Runtime → **Thực hành tổng hợp**. Bài này thiết kế một thí nghiệm có thể chạy lại để kiểm chứng **virtual threads**, trạng thái **daemon**, tác dụng của hai cấu hình `spring.threads.virtual.enabled` và `spring.main.keep-alive`, hành vi của `@Scheduled`, cũng như giới hạn của việc “giữ JVM sống”. Một dự án Maven **Java 21+ / Spring Boot 3.5.x** gồm mã Java chạy được và một chương trình thăm dò tiến trình con bằng `ProcessBuilder`. Bài hướng dẫn quan sát cả ba yếu tố: luồng đang chạy loại gì, ứng dụng còn sống khi `main()` đã trả về hay không, và công việc có thật sự hoàn tất/được dọn khi tắt hay không.

**Câu hỏi thực hành:** Tại sao một Spring Boot CLI có `@Scheduled` chạy bằng virtual thread có thể **thoát ngay sau khởi động**, và vì sao thêm `spring.main.keep-alive=true` lại giữ tiến trình sống đến khi được chủ động dừng?

**Mốc phiên bản:** `Thread.ofVirtual()`, `Thread.isVirtual()` và virtual threads chính thức có từ **Java 21** (JEP 444). Java 17 **không** biên dịch lab này. Dùng Spring Boot **3.5.x** (ví dụ 3.5.16). Spring Boot 3.5 hướng dẫn Java 24+ để có trải nghiệm virtual threads tốt hơn, nhưng các API mẫu đều dùng được từ Java 21.

> **Bản chất:** Virtual threads là **daemon threads**. JVM không giữ process sống chỉ vì còn daemon threads. `spring.main.keep-alive=true` là cơ chế Spring Boot giúp giữ ứng dụng sống khi không có non-daemon thread nào khác; nó **không** tự biến virtual thread thành non-daemon, không tự retry công việc và không bảo đảm chống mất tác vụ khi crash hoặc SIGKILL.

## 1. Mục tiêu học tập

Sau bài, người học có thể:

1. Phân biệt **virtual threads** và **platform threads** bằng `Thread.currentThread().isVirtual()`.
2. Đọc `Thread.isDaemon()` và giải thích ảnh hưởng của daemon threads tới JVM process lifetime.
3. Hiểu tại sao `spring.threads.virtual.enabled=true` và `spring.main.keep-alive=true` là **hai cấu hình độc lập**.
4. Mô tả Spring Boot 3.5 auto-configure `SimpleAsyncTaskScheduler` với virtual threads và `ThreadPoolTaskScheduler` với platform threads, trong điều kiện phù hợp.
5. Thấy rằng scheduler thread virtual/daemon có thể **không giữ JVM sống**, dù `@Scheduled` đã được đăng ký.
6. Đặt `spring.main.keep-alive=true` cho ứng dụng nền chỉ có daemon tasks.
7. Tạo `@Scheduled(fixedRate=...)` in `isVirtual()/isDaemon()` và thấy task chạy định kỳ khi JVM còn sống.
8. Khởi chạy một virtual thread thủ công với `Thread.ofVirtual().start(...)` và biết `main` không tự đợi nó.
9. Thực nghiệm ba kịch bản: virtual+no keepalive, virtual+keepalive, platform scheduler+no keepalive.
10. Dùng tiến trình `java -jar` **độc lập** để không bị non-daemon threads của IDE/Maven/test harness làm sai kết quả.
11. Dùng `ProcessBuilder.waitFor(timeout)` xác định process đã tự thoát hay vẫn sống; không dựa vào log đơn lẻ.
12. Phân biệt `spring.main.keep-alive` với HTTP `Connection: keep-alive`, executor `keepAliveSeconds` và `@Scheduled` delay.
13. Không nhầm “process vẫn sống” với “mọi task đã xử lý thành công”.
14. Nêu cơ chế stop hợp lệ, `@PreDestroy`/`SmartLifecycle`, interrupt và đóng tài nguyên đúng owner.
15. Đề xuất admission control/backpressure, resource quotas, durable queue và idempotency nếu công việc quan trọng.
16. Diễn giải kết quả trên Java 21/24+, trường hợp app có web server/non-daemon threads, hoặc có cấu hình scheduler riêng.
17. Biết khi nào **không** bật keepalive: một CLI/batch job cần tự hoàn tất và trả exit status thay vì ở lại vô hạn.
18. Thu thập bằng chứng đủ để báo cáo khác biệt giữa daemon và keepalive một cách tái lập.

## 2. Hai cấu hình giải quyết hai vấn đề khác nhau

Đặt trong `application.properties`:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Đọc chính xác:

| Property | Câu hỏi nó giải quyết | Hành vi chính |
|---|---|---|
| `spring.threads.virtual.enabled` | Một số Spring-managed task/scheduling integrations dùng loại thread nào? | Trên Java 21+, Boot dùng virtual threads ở những integration được hỗ trợ |
| `spring.main.keep-alive` | JVM có được giữ sống dù không còn non-daemon threads không? | Khi true, Boot duy trì cơ chế giữ app sống |
| `spring.main.web-application-type=none` | Có embedded web server không? | Không tạo web server, giúp thí nghiệm đời sống JVM sạch |
| `spring.main.register-shutdown-hook` | Boot có đăng ký hook để đóng context lúc JVM shutdown? | Mặc định true; không thay thế durability hoặc keepalive |
| `spring.task.scheduling.pool.size` | Số threads platform scheduler khi dùng thread pool | Không đặt trần số virtual threads của SimpleAsyncTaskScheduler |

**Giá trị mặc định Spring Boot 3.5:** `spring.main.keep-alive=false`. Vì vậy khi virtual threads được bật, Spring Boot khuyến nghị cân nhắc bật keepalive, nhất là các app phụ thuộc `@Scheduled` hoặc các background tasks để duy trì process.

**Độc lập:** Khi đặt `spring.threads.virtual.enabled=false` nhưng `spring.main.keep-alive=true`, Boot vẫn có thể giữ process sống dù task scheduler dùng platform threads. Khi đặt virtual=true và keepalive=false, scheduler có thể dùng virtual daemon threads nhưng process vẫn không được đảm bảo tồn tại.

### 2.1. Bật virtual threads không đổi mọi Thread trong JVM

Một ứng dụng vẫn có main thread, GC threads, runtime/platform carrier threads, web containers và các threads do thư viện tự tạo. `spring.threads.virtual.enabled=true` tác động tới **những integration mà Spring Boot hỗ trợ**, không ép mọi `new Thread(...)` của thư viện thứ ba chuyển thành virtual thread.

Còn `Thread.ofVirtual()` tạo virtual thread **bất kể** property của Spring Boot, miễn chạy trên Java 21+. Vì vậy lab cố ý kiểm **hai nơi**:

- `@Scheduled`: dùng scheduler do Spring Boot auto-configure, để kiểm virtual threads của framework.
- `Thread.ofVirtual().start(...)`: dùng JDK API, để chứng minh một one-shot virtual daemon thread không tự giữ JVM sống.

### 2.2. Không đồng nhất daemon với “chạy nền”

“Background job” là khái niệm nghiệp vụ, còn `Thread.isDaemon()` là cờ quyết định **thread có giữ JVM sống hay không**. Một platform thread có thể được đặt daemon; một virtual thread luôn là daemon. “Đang làm việc quan trọng” không khiến một virtual thread tự được phép giữ process.

## 3. Cơ chế JVM: khi nào process tự kết thúc?

Theo Java Virtual Threads Guide, virtual threads là instance của `Thread` nhưng nhẹ hơn platform thread và phù hợp các thao tác thường chờ I/O. Chúng được scheduler JVM thực thi trên các carrier platform threads. **Virtual thread luôn daemon**, không thể biến thành non-daemon để giải quyết process liveness.

~~~text
main thread (platform, thường non-daemon)
   |
   +-- SpringApplication.run(...)
   |      |
   |      +-- tạo context, beans
   |      +-- đăng ký scheduler và scheduled jobs
   |      +-- chạy ApplicationRunner/CommandLineRunner
   |
   v
main() return
   |
   +-- Còn non-daemon thread khác?
   |       |
   |       +-- CÓ  -> JVM tiếp tục chạy
   |       |
   |       +-- KHÔNG -> JVM có thể bắt đầu shutdown
   |                     daemon threads không giữ nó sống
   |
   +-- spring.main.keep-alive=true?
           |
           +-- Boot hỗ trợ giữ JVM sống khi cần
               -> đợi operator/SIGTERM/stop hợp lệ
~~~

**Quan trọng:** JVM có thể shutdown vì **không còn non-daemon threads** ngay cả khi virtual threads vẫn `sleep`, `await` hoặc đang chờ kết quả network. Khi JVM kết thúc, các daemon threads không có cam kết chạy hết mọi `finally`/business job như một transaction. Trong shutdown bình thường, Java shutdown hooks của ứng dụng được kích hoạt; nhưng một task không được quản lý vẫn có thể bị bỏ dở khi process chấm dứt.

**Không suy luận sai:** JVM thoát tự nhiên với exit status 0 không có nghĩa background task đã thành công; status 0 có thể chỉ phản ánh rằng `main` hoàn thành bình thường và không có exception được chuyển thành exit status.

## 4. Spring Boot 3.5 dùng scheduler nào?

Với `@EnableScheduling` và khi không có custom scheduler overriding lựa chọn mặc định, Boot có thể auto-configure:

| Điều kiện | Scheduler thường được chọn | Thực hiện công việc |
|---|---|---|
| `spring.threads.virtual.enabled=true`, Java 21+ | `SimpleAsyncTaskScheduler` với virtual threads | Một scheduler thread và thread riêng cho các scheduled executions thích hợp |
| `spring.threads.virtual.enabled=false` | `ThreadPoolTaskScheduler` | Pool platform threads; mặc định thường một thread |
| Có custom `TaskScheduler` / `ScheduledExecutorService` bean | Phụ thuộc bean/config hiện hữu | Không được giả định giống Boot default |

**Với virtual threads, scheduler thread là daemon**, theo tài liệu Spring Boot. Nếu CLI chỉ trông chờ scheduler đó để giữ chương trình mở, JVM có thể thoát ngay khi main trở về.

**Chú ý kiểu trigger:** `SimpleAsyncTaskScheduler` có đặc điểm với `fixedDelay`: fixed-delay tasks chạy trên **scheduler thread** để giữ semantics, còn fixed-rate/cron thường được hand off cho các execution threads riêng. Lab dùng **`fixedRate`** để rõ ràng quan sát `Thread.isVirtual()` trong chính method được scheduled. Không khái quát rằng mọi `@Scheduled` trigger đều có hành vi giống nhau.

### 4.1. Những pool properties không quyết định số virtual threads

Khi Spring Boot dùng virtual scheduler, các cấu hình pool như:

~~~properties
spring.task.scheduling.pool.size=4
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
~~~

**không đặt trần virtual threads theo cách fixed platform thread pools**. Đừng thêm chúng để “giữ JVM sống” hoặc giới hạn mọi request đến database; chúng giải quyết vấn đề khác, và có thể không còn tác dụng với integrations virtual tương ứng.

Nếu workload tạo rất nhiều virtual threads tới database có pool 10 connections, DB vẫn chỉ có 10 connections theo cấu hình; các virtual threads còn lại chờ, timeout hoặc bị từ chối. Cần admission limit, semaphore/bulkhead, connection timeout, request deadline và quota theo tài nguyên thật.

### 4.2. @Async và @Scheduled cũng không đồng nhất

`@Scheduled` đăng ký công việc chạy theo thời gian; `@Async` dispatch qua task executor, tùy `@EnableAsync`/bean config. Khi bật virtual threads, Boot có thể cung cấp `SimpleAsyncTaskExecutor` cho async task execution, nhưng bean custom `Executor` có thể khiến auto-configuration backing off hoặc thay đường chọn executor.

Bài lab **không bật `@EnableAsync`**, nên không để một executor async khác làm nhiễu quan sát scheduler. Một virtual thread tạo qua JDK API cũng **không** do Spring tự quản lý lifecycle chỉ vì app bật virtual-thread property.

## 5. Thiết kế thí nghiệm sạch và có đối chứng

Ta dùng một ứng dụng CLI **không có Spring Web**, vì embedded web server có thể tạo non-daemon threads và giữ JVM sống ngay cả khi keepalive=false. App có ba thành phần:

1. `main()`: gọi `SpringApplication.run` rồi in `LAB_MAIN_RETURNED`.
2. `@Scheduled(fixedRate=1000, initialDelay=1000)`: in số tick và `isVirtual/isDaemon`.
3. `ApplicationRunner`: nộp một one-shot virtual thread qua `Thread.ofVirtual()`, nó ngủ 3 giây rồi in `LAB_JOB_DONE` nếu còn cơ hội.

**Các kịch bản chính:**

| Kịch bản | spring.threads.virtual.enabled | spring.main.keep-alive | Kỳ vọng trong CLI không web |
|---|---|---|---|
| A | `true` | `false` | Main return, JVM có thể tự thoát sớm, chưa kịp tick/job done |
| B | `true` | `true` | JVM tiếp tục sống, thấy ticks và one-shot job done |
| C | `false` | `false` | Platform scheduler thường có non-daemon thread, JVM tiếp tục sống |
| D (tùy chọn) | `false` | `true` | Vẫn sống; keepalive không cần để chứng minh virtual scheduler |

**Không ép một timestamp tuyệt đối:** số ticks, thread names và thứ tự `LAB_JOB_BEGIN`/`LAB_JOB_SUBMITTED` phụ thuộc scheduler/JIT/CPU. Dùng ít nhất vài giây để quan sát; nếu scenario A tồn tại lâu bất thường, kiểm xem còn non-daemon threads do thư viện, agent hoặc IDE tạo không.

### 5.1. Ba lời khẳng định độc lập cần kiểm

- **Loại thread:** `Thread.currentThread().isVirtual()` trong scheduled method.
- **Daemon:** `Thread.currentThread().isDaemon()` trong cùng thread.
- **Liveness:** tiến trình **đã tự thoát** hay vẫn chạy sau 6 giây, đo từ parent process.

Không dùng một dòng `@Scheduled` log làm phép đo duy nhất về keepalive. Một process vẫn sống có thể do web server, debug agent, thread tự tạo hoặc plugin runner; không nhất thiết vì `spring.main.keep-alive=true`.

## 6. Tạo Maven project Java 21 và Spring Boot 3.5

### 6.1. Cấu trúc

Tạo project qua Spring Initializr:

- Project: **Maven**, Language **Java**, Java **21** (hoặc 24+).
- Spring Boot: **3.5.x**, ví dụ **3.5.16**.
- Group: `com.example`.
- Artifact: `virtual-keepalive-lab`.
- Package: `com.example.virtualkeepalive`.
- Dependencies: **Spring Boot Starter** cơ bản; **không** thêm Spring Web.
- Packaging: Jar.

~~~text
virtual-keepalive-lab/
  pom.xml
  mvnw                         (nếu dùng Maven Wrapper)
  mvnw.cmd
  src/main/java/com/example/virtualkeepalive/
    VirtualKeepAliveLabApplication.java
    HeartbeatTask.java
  src/main/resources/
    application.properties
  ProcessProbe.java            (optional: chạy bằng Java source-file mode)
~~~

Hai files trong `src/main/java` là **mã biên dịch được trên JDK 21**, với starter Spring Boot tương ứng. `ProcessProbe.java` dùng **chỉ Java standard library** để khởi chạy JAR và đo process. Dự án không cần database, web server hay broker để test daemon/keepalive.

### 6.2. pom.xml hoàn chỉnh

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>virtual-keepalive-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
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

`spring-boot-starter` đưa vào Spring Context và Scheduling support. `@EnableScheduling` sẽ kích hoạt scheduled method processing. Vì không có Spring Web, `web-application-type=none` được đặt rõ trong properties để ngăn nhầm môi trường khi sau này thêm dependencies.

### 6.3. Main class và virtual one-shot worker

File `src/main/java/com/example/virtualkeepalive/VirtualKeepAliveLabApplication.java`:

~~~java
package com.example.virtualkeepalive;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class VirtualKeepAliveLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                VirtualKeepAliveLabApplication.class, args);

        System.out.println("LAB_MAIN_RETURNED");
    }

    @Bean
    ApplicationRunner launchOneShotVirtualJob() {
        return args -> {
            Thread job = Thread.ofVirtual()
                    .name("lab-one-shot")
                    .start(() -> {
                        Thread current = Thread.currentThread();
                        System.out.println("LAB_JOB_BEGIN virtual="
                                + current.isVirtual()
                                + " daemon=" + current.isDaemon());

                        try {
                            Thread.sleep(3_000);
                            System.out.println("LAB_JOB_DONE");
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            System.out.println("LAB_JOB_INTERRUPTED");
                        }
                    });

            System.out.println("LAB_JOB_SUBMITTED virtual="
                    + job.isVirtual()
                    + " daemon=" + job.isDaemon());
        };
    }
}
~~~

**Điều cần hiểu từng dòng:**

1. `@SpringBootApplication` đăng ký app config, auto-config và scan bean.
2. `@EnableScheduling` kích hoạt việc thực thi các methods `@Scheduled` trong `HeartbeatTask`.
3. `SpringApplication.run(...)` refresh context, chạy `ApplicationRunner` và hoàn thành startup; sau đó method main in `LAB_MAIN_RETURNED`.
4. `Thread.ofVirtual()` tạo virtual thread thuộc JDK; nó luôn là daemon, **không phụ thuộc** `spring.threads.virtual.enabled`.
5. `job.start(...)` làm task chạy bất đồng bộ; `ApplicationRunner` **không đợi** job. Một thread có thể bắt đầu thực thi trước khi caller ghi `LAB_JOB_SUBMITTED`, nên thứ tự hai dòng không cố định.
6. `Thread.sleep(3_000)` đặt một khoảng quan sát: nếu JVM mất non-daemon threads rất sớm, `LAB_JOB_DONE` có thể không xuất hiện; nếu keepalive hoạt động, job có cơ hội hoàn thành.
7. `InterruptedException` được xử lý riêng và khôi phục interrupt flag. **Không tự suy rằng keepalive interrupt task** — sleep có thể bị cắt vì những nguyên nhân khác hoặc process dừng.
8. Không dùng `job.join()` trong runner/main vì điều đó **giữ main non-daemon thread chờ đến khi job xong**, vô tình che khuất hành vi cần thử.
9. Task cố tình **không có lifecycle owner** để thấy rằng một one-shot daemon job có thể bị bỏ dở. Nó là **lab minh họa nguy cơ**, không phải mẫu production để xử lý đơn hàng/thanh toán.

### 6.4. Scheduled task quan sát loại thread

File `src/main/java/com/example/virtualkeepalive/HeartbeatTask.java`:

~~~java
package com.example.virtualkeepalive;

import java.util.concurrent.atomic.AtomicInteger;
import jakarta.annotation.PreDestroy;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class HeartbeatTask {

    private final AtomicInteger ticks = new AtomicInteger();

    @Scheduled(initialDelay = 1_000, fixedRate = 1_000)
    public void heartbeat() {
        Thread thread = Thread.currentThread();
        int count = ticks.incrementAndGet();

        System.out.println("LAB_TICK n=" + count
                + " virtual=" + thread.isVirtual()
                + " daemon=" + thread.isDaemon()
                + " name=" + thread.getName());
    }

    @PreDestroy
    public void onDestroy() {
        System.out.println(
                "LAB_CONTEXT_DESTROYED ticks=" + ticks.get());
    }
}
~~~

**Tại sao chọn `fixedRate` và initial delay một giây?**

- `initialDelay=1000` cho phép tách giai đoạn main startup khỏi tick đầu tiên.
- `fixedRate=1000` tạo các lần scheduled execution cách nhau theo cadence, không phải sleep 1 giây bên trong method.
- Với `SimpleAsyncTaskScheduler` virtual, fixed-rate execution dùng virtual worker threads theo implementation phù hợp để `Thread.isVirtual()` trong scheduled method phản ánh việc Boot bật virtual threads.
- Với `ThreadPoolTaskScheduler` mặc định, execution ở platform thread nên `isVirtual()==false`.
- Không đặt `Thread.sleep(5min)` trong chính `@Scheduled` để “giữ chương trình chạy” vì mục tiêu ở đây là đo daemon/liveness chứ không giữ busy task.
- `@PreDestroy` in số tick lúc Spring đóng context qua đường shutdown bình thường. Không suy “đã thấy marker destroy” đồng nghĩa tất cả external jobs đã hoàn tất.
- Lưu ý `@Scheduled` không tự có business retry/durable queue; nếu task lỗi, phải định nghĩa error policy và giám sát riêng.

### 6.5. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=virtual-keepalive-lab
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=WARN

# Chế độ mặc định của LAB A; CLI có thể override.
spring.threads.virtual.enabled=true
spring.main.keep-alive=false
~~~

**Giải thích:** Ta chủ động đặt keepalive=false trong file để làm đối chứng mặc định. Spring Boot 3.5 cũng mặc định `spring.main.keep-alive=false` nếu bỏ property. Khi chạy các kịch bản còn lại, truyền command-line arguments để override:

~~~text
--spring.threads.virtual.enabled=true
--spring.main.keep-alive=true
~~~

Vì `application.properties` đang có giá trị false, hãy chắc lệnh thật có flag `--spring.main.keep-alive=true` khi kiểm trường hợp B. Không đổi JAR giữa các kịch bản; giữ cùng dependencies, JDK và máy.

## 7. Build project bằng JDK 21+

### 7.1. Linux/macOS

~~~bash
java -version
./mvnw -version
./mvnw clean package
~~~

Nếu không có Maven Wrapper:

~~~bash
mvn -version
mvn clean package
~~~

### 7.2. Windows PowerShell

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd clean package
~~~

Nếu chỉ có Maven cài sẵn:

~~~powershell
mvn -version
mvn clean package
~~~

**Bắt buộc kiểm `java -version` và JDK mà Maven sử dụng.** `Thread.ofVirtual`/`Thread.isVirtual` xuất hiện từ Java 21. Nếu Maven dùng JDK 17, build sẽ fail với lỗi không tìm thấy method/API hoặc không hỗ trợ release 21. Nếu `JAVA_HOME` trỏ JDK mới nhưng `java` ở PATH cũ, running JAR cũng sai phiên bản.

JAR tạo theo POM là:

~~~text
target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar
~~~

Nếu đã thay `<version>` trong POM, dùng tên JAR thực tế. Với thí nghiệm lifetime, **chạy raw `java -jar`** thay vì `mvn spring-boot:run`, IDE Run hoặc JUnit. Các launcher trung gian có threads/process management khác, có thể làm kịch bản A không tự thoát như dự kiến.

## 8. Thí nghiệm A — virtual=true, keep-alive=false

Chạy một **process riêng**:

~~~bash
java -jar target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar \
  --spring.threads.virtual.enabled=true \
  --spring.main.keep-alive=false
~~~

Windows PowerShell viết một dòng:

~~~powershell
java -jar target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar --spring.threads.virtual.enabled=true --spring.main.keep-alive=false
~~~

**Dấu mốc thường thấy:**

~~~text
LAB_JOB_SUBMITTED virtual=true daemon=true
LAB_JOB_BEGIN virtual=true daemon=true
LAB_MAIN_RETURNED
LAB_CONTEXT_DESTROYED ticks=0
~~~

**Đây là một ví dụ về các marker, không phải stdout byte-for-byte.** `LAB_JOB_BEGIN` có thể đến trước `LAB_JOB_SUBMITTED`, `LAB_CONTEXT_DESTROYED` có thể xen vào các logs khác, và số ticks có thể khác 0 trong môi trường có non-daemon thread bất ngờ.

**Kết luận kỳ vọng:** Sau khi `main()` return, nếu không còn non-daemon threads, JVM tiến tới shutdown. Scheduler virtual/daemon và one-shot virtual/daemon **không giữ JVM sống**, nên một việc ngủ 3 giây có thể bị bỏ dở. `LAB_JOB_DONE` và `LAB_TICK` **có thể không xuất hiện**, điều này phù hợp thiết kế.

Trường hợp đó không phải Spring Boot “tắt @Scheduled”: scheduled method đã được đăng ký nhưng process không còn sống đủ lâu để đến thời điểm chạy. Nếu process không thoát sau vài giây, kiểm tình trạng các non-daemon threads, agent hoặc dependency đã thêm; **không giả định property bị ignore chỉ vì process còn sống**.

### 8.1. Nhìn mã thoát khi JVM tự kết thúc

Trong Bash:

~~~bash
java -jar target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar \
  --spring.threads.virtual.enabled=true \
  --spring.main.keep-alive=false
echo $?
~~~

Khi main thành công và process tự kết thúc bình thường, shell thường hiển thị `0`. Tuy nhiên **exit status 0 không chứng minh LAB_JOB_DONE đã xảy ra**. Nếu JVM bị OOM/startup failure hoặc process supervisor làm thay đổi exit behavior, status khác có thể xuất hiện.

Trong PowerShell, dùng `$LASTEXITCODE` ngay sau lệnh java để đọc native process exit status.

## 9. Thí nghiệm B — virtual=true, keep-alive=true

Chạy lại cùng JAR:

~~~bash
java -jar target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar \
  --spring.threads.virtual.enabled=true \
  --spring.main.keep-alive=true
~~~

Windows PowerShell:

~~~powershell
java -jar target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar --spring.threads.virtual.enabled=true --spring.main.keep-alive=true
~~~

Lần này main vẫn return nhưng process **cần tiếp tục sống** nhờ cơ chế keep-alive của Spring Boot. Sau khoảng vài giây, bạn có thể thấy:

~~~text
LAB_JOB_SUBMITTED virtual=true daemon=true
LAB_JOB_BEGIN virtual=true daemon=true
LAB_MAIN_RETURNED
LAB_TICK n=1 virtual=true daemon=true name=...
LAB_TICK n=2 virtual=true daemon=true name=...
LAB_TICK n=3 virtual=true daemon=true name=...
LAB_JOB_DONE
LAB_TICK n=4 virtual=true daemon=true name=...
~~~

Các tên thread/counter/time có thể thay đổi. Marker đáng tin là `LAB_TICK virtual=true daemon=true` và **process vẫn sống sau main return**. Khi qua thời gian 3 giây, one-shot job có thể hoàn thành và in `LAB_JOB_DONE` nếu không có lỗi/interrupt bất ngờ.

### 9.1. Tắt process và quan sát cleanup

Nhấn **Ctrl+C** trong terminal chạy Java hoặc gửi SIGTERM hợp lệ. Trong đường shutdown Spring Boot thông thường, context được đóng, bean có `@PreDestroy` nhận lifecycle destruction, ví dụ:

~~~text
LAB_CONTEXT_DESTROYED ticks=...
~~~

Đó là bằng chứng một bean đã tới hook destroy, không chứng minh mọi unmanaged virtual thread đã nhận interrupt và hoàn tất. Một app thật cần quản lý shutdown của executors, consumers, connections và jobs theo chủ sở hữu, deadline, cùng trạng thái bền vững.

**Tránh** dùng `kill -9` để kiểm graceful shutdown: SIGKILL không cho Java cơ hội chạy hooks một cách đáng tin. Khi chỉ cần dừng thí nghiệm, Ctrl+C hoặc SIGTERM phù hợp hơn.

### 9.2. Keep-alive không thay đổi loại thread

Trong output trên:

~~~text
virtual=true daemon=true
~~~

vẫn giữ nguyên khi bật keepalive. Nó **không** khiến `Thread.isDaemon()` thành false. Spring Boot tạo/giữ cơ chế cho process lifetime; nó không sửa cờ daemon của virtual threads, cũng không đổi một scheduled method thành platform thread chỉ để giữ app mở.

## 10. Thí nghiệm C — virtual=false, keep-alive=false

Thử điều khiển đối chứng:

~~~bash
java -jar target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar \
  --spring.threads.virtual.enabled=false \
  --spring.main.keep-alive=false
~~~

Windows PowerShell:

~~~powershell
java -jar target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar --spring.threads.virtual.enabled=false --spring.main.keep-alive=false
~~~

**Kỳ vọng:**

- `@Scheduled` chạy trên `ThreadPoolTaskScheduler` của Spring Boot, thường là **platform non-daemon** worker, log `LAB_TICK virtual=false daemon=false`.
- Vì scheduler có non-daemon thread, JVM thường **vẫn sống** dù keepalive=false.
- One-shot worker được tạo thủ công bằng `Thread.ofVirtual()` vẫn in `virtual=true daemon=true` và có thể hoàn thành sau 3 giây, vì scheduler platform giữ JVM sống.
- Bấm Ctrl+C để kết thúc, quan sát bean destruction.

Nếu app có custom scheduler làm thread daemon, logic liveness có thể khác. Lab được thiết kế **không có custom scheduler** và không có web server, nên nó thể hiện khác biệt của Boot defaults.

### 10.1. Vì sao kịch bản C quan trọng?

Nếu chỉ thử “virtual=true keepalive=false” và “virtual=true keepalive=true”, bạn biết keepalive ảnh hưởng liveness nhưng chưa chứng minh nguyên nhân nằm ở daemon scheduler. Kịch bản C cho thấy khi tắt virtual integration, scheduler platform có thể trở thành một **non-daemon thread giữ JVM sống**, dù không có keepalive.

Đây là causal comparison: **cùng một `@Scheduled`, cùng JAR, cùng Java, cùng tần suất**, chỉ thay hai flags. Không dùng kết quả này để nói virtual threads “chậm hơn”, vì thí nghiệm chỉ đo **liveness và daemon semantics**, không phải throughput/latency của tác vụ.

## 11. Tự động hóa phép thử bằng Java ProcessBuilder

Để quan sát process lifecycle một cách lặp lại mà không giữ IDE hoặc test harness làm “con tin”, dùng một chương trình Java độc lập **khởi chạy các child JVMs**. Parent có thể có non-daemon threads riêng nhưng **không làm child JVM sống lâu hơn**; đây là lý do phép thử qua process boundary đáng tin hơn gọi main trực tiếp trong JUnit.

Lưu file `ProcessProbe.java` ở thư mục project root, **không** trong `src/main/java`; dùng JDK 21 **source-file mode**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ProcessProbe {

    private record Scenario(
            String name, boolean virtual, boolean keepAlive) {
    }

    private static final List<Scenario> SCENARIOS = List.of(
            new Scenario("virtual-no-keepalive", true, false),
            new Scenario("virtual-with-keepalive", true, true),
            new Scenario("platform-no-keepalive", false, false));

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java ProcessProbe.java path/to/app.jar");
            System.exit(2);
        }

        Path jar = Path.of(args[0]).toAbsolutePath();
        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException(
                    "JAR does not exist: " + jar);
        }

        String javaBinary = System.getProperty("os.name")
                .startsWith("Windows") ? "java.exe" : "java";
        String java = Path.of(
                System.getProperty("java.home"), "bin",
                javaBinary).toString();

        for (Scenario scenario : SCENARIOS) {
            Path log = Path.of(
                    "probe-" + scenario.name() + ".log")
                    .toAbsolutePath();

            ProcessBuilder builder = new ProcessBuilder(
                    java,
                    "-jar",
                    jar.toString(),
                    "--spring.threads.virtual.enabled="
                            + scenario.virtual(),
                    "--spring.main.keep-alive="
                            + scenario.keepAlive());

            builder.redirectErrorStream(true);
            builder.redirectOutput(log.toFile());

            Process child = builder.start();

            // Neu process con tu ket thuc trong 6 giay,
            // waitFor tra true. Khong tu ket thuc => false.
            boolean exitedNaturally = child.waitFor(
                    6, TimeUnit.SECONDS);

            String initialStatus = exitedNaturally
                    ? "EXITED(code=" + child.exitValue() + ")"
                    : "STILL_RUNNING_AFTER_6S";

            // Don dep child process de probe khong de lai
            // JAR scheduler chay vo han sau phep thu.
            if (!exitedNaturally) {
                child.destroy();
                if (!child.waitFor(3, TimeUnit.SECONDS)) {
                    child.destroyForcibly();
                    child.waitFor();
                }
            }

            List<String> lines = Files.readAllLines(log);
            long ticks = lines.stream()
                    .filter(s -> s.contains("LAB_TICK n="))
                    .count();
            boolean jobDone = lines.stream()
                    .anyMatch(s -> s.contains("LAB_JOB_DONE"));
            boolean mainReturned = lines.stream()
                    .anyMatch(s -> s.contains("LAB_MAIN_RETURNED"));

            System.out.println("PROBE name=" + scenario.name()
                    + " initial=" + initialStatus
                    + " mainReturned=" + mainReturned
                    + " ticks=" + ticks
                    + " jobDone=" + jobDone
                    + " log=" + log);
        }
    }
}
~~~

**Đây là file Java đầy đủ** dùng standard library, không cần Spring dependencies cho `ProcessProbe`. Nó không kết nối Google Sheets, network hoặc dịch vụ thật. Mỗi child JVM tự đọc cùng JAR, với flags tương ứng.

Chạy trong project root sau khi build:

~~~bash
java ProcessProbe.java target/virtual-keepalive-lab-0.0.1-SNAPSHOT.jar
~~~

Trên PowerShell cũng dùng cùng cú pháp. Source-file mode từ JDK 11+, dùng JDK 21 phù hợp toàn bài. Program chạy ba kịch bản **tuần tự**; mỗi kịch bản tối đa 6 giây quan sát, sau đó dừng child nếu còn chạy. Chương trình ghi ba log files tại thư mục chạy, cho phép kiểm bằng mắt thay vì đoán.

### 11.1. Ý nghĩa kết quả

Trong môi trường local sạch, báo cáo tương tự:

~~~text
PROBE name=virtual-no-keepalive initial=EXITED(code=0) mainReturned=true ticks=0 jobDone=false log=...
PROBE name=virtual-with-keepalive initial=STILL_RUNNING_AFTER_6S mainReturned=true ticks=5 jobDone=true log=...
PROBE name=platform-no-keepalive initial=STILL_RUNNING_AFTER_6S mainReturned=true ticks=5 jobDone=true log=...
~~~

**Đây là output minh họa** (ticks, đường dẫn và trạng thái cụ thể tùy môi trường). Không kỳ vọng đúng `ticks=5`, vì startup và timing khác nhau. Những gì kiểm chứng có giá trị là process A tự thoát sớm khi không có non-daemon thread giữ sống, B còn chạy nhờ keepalive và C có non-daemon scheduler theo Boot default.

**Cẩn thận với `destroy()`:** Trong thăm dò, khi child chưa thoát, `Process.destroy()` yêu cầu dừng child; cơ chế signal cụ thể khác nhau theo OS và JVM. Nếu vượt 3 giây, `destroyForcibly()` dùng để tránh để lại process sống. Đây là **cleanup của công cụ thử nghiệm**, không phải một ví dụ bảo đảm graceful shutdown. Đọc `LAB_CONTEXT_DESTROYED` nếu xuất hiện, nhưng không xem nó bắt buộc trong trường hợp child bị force-kill.

### 11.2. Giới hạn của Probe

- Probe đo liệu process đã **tự thoát trong 6 giây**, không phải performance benchmark.
- Một JVM bị startup failure có thể tự thoát code nonzero; phải xem log, không kết luận daemon từ “EXITED” mà thiếu `LAB_MAIN_RETURNED`.
- `mainReturned=false` và `ticks=0` là tín hiệu setup/startup chưa thành công hoặc quá chậm, không phải bằng chứng keepalive.
- Các logs có thể được flush khi process shutdown bình thường; crash hoặc forced kill làm mất một phần output.
- Trên một số environments, JVM agents, profilers hoặc thư viện thứ ba tạo non-daemon threads; kịch bản A có thể còn chạy. Kiểm thread dump và chạy raw JAR không thêm agents.
- Log file names cố định cho các scenario; chạy lại probe ghi đè các **log files của chính lab**. Không trỏ script vào thư mục có log production quan trọng.
- Khi cần thử signal semantics production, dùng container/systemd/Kubernetes riêng và đối chiếu lifecycle logs, không dùng Java ProcessBuilder đơn lẻ làm proof end-to-end.

## 12. Tại sao thử bằng Maven Run/IDE/JUnit dễ sai?

Các công cụ phát triển có thể tạo luồng/tiến trình bổ sung:

| Cách chạy | Rủi ro |
|---|---|
| `mvn spring-boot:run` | Maven/plugin có thể dùng launcher/process management làm kết quả status/lifetime khó đọc |
| IDE Run/Debug | Debugger agent và threads riêng có thể ảnh hưởng liveness |
| JUnit trong cùng JVM | JUnit/TestContext và các test runner threads vẫn còn, che chuyện app tự thoát |
| Spring Boot DevTools | Restart classloader hoặc threads khác có thể duy trì process |
| Một app có Spring Web/Tomcat | Embedded server có thể giữ JVM bằng platform non-daemon threads |
| Shell chạy `java -jar` trực tiếp | Có thể kiểm process lifetime sát với runtime nhất |
| `ProcessBuilder` spawn `java -jar` | Cách tốt cho test tự động có timeout và capture output |

**Không dùng một test `@SpringBootTest` để khẳng định process sẽ tự thoát:** Test JVM do framework test quản lý và có thể tiếp tục chạy sau khi Spring application context đóng. Với câu hỏi về liveness, **đơn vị kiểm thử đúng là OS process**.

Trong Spring Boot 3.5, `@SpringBootTest` còn có `useMainMethod`, mặc định `NEVER`, nên nhiều test không đi qua custom setup trong main. Nếu muốn kiểm cấu hình riêng trong main thì test context phải chọn đường main phù hợp; nhưng **kiểm JVM exit** vẫn nên tách subprocess.

## 13. spring.main.keep-alive không phải các “keep alive” khác

| Cấu hình/khái niệm | Đối tượng | Không dùng thay `spring.main.keep-alive` |
|---|---|---|
| `spring.main.keep-alive` | SpringApplication / JVM process lifetime | **Đúng** property trong bài |
| HTTP `Connection: keep-alive` | Tái sử dụng TCP connection HTTP | Không giữ CLI JVM sống theo cách này |
| Tomcat `server.tomcat.keep-alive-timeout` | Timeout tái sử dụng HTTP connection | Không áp cho virtual scheduler daemon |
| `ThreadPoolExecutor.keepAliveTime` | Thời gian worker dư thừa idle trước khi thu nhỏ | Không ngăn JVM thoát khi chỉ còn daemon threads |
| `ThreadPoolTaskExecutor.setKeepAliveSeconds` | Idle lifetime của threads ngoài core | Không đảm bảo app background sống |
| Kubernetes liveness probe | Cơ chế platform phát hiện container không khỏe | Không làm JVM tự giữ một task daemon |
| Kubernetes readiness probe | Quyết định route traffic khi Pod sẵn sàng | Không phải cơ chế Java process keepalive |
| OS process supervisor restart policy | Có thể restart process đã thoát | Không làm job đã mất tự được khôi phục |

**Đặc biệt:** Đổi `spring.task.execution.pool.keep-alive` hoặc HTTP keep-alive timeout rồi không thấy hiệu quả với một `@Scheduled` virtual daemon là đúng vì chúng thuộc lớp khác.

## 14. Khi nào nên bật hoặc không nên bật?

### 14.1. Scheduled daemon service

Ứng dụng không phục vụ HTTP nhưng cần chạy `@Scheduled` lâu dài (cron poller, periodic audit, cleanup, event consumer). Với Java 21+ và Boot virtual scheduler, `spring.main.keep-alive=true` là một **lựa chọn hợp lý** để không tự thoát khi main return.

Tuy nhiên phải có thêm:

- Health/readiness hoặc external supervisor phù hợp workload.
- Retry/error handling cho task định kỳ.
- Quota/concurrency nếu mỗi lần tick gọi API hoặc DB.
- Shutdown lifecycle có deadline để dừng nhận job và dọn resource.
- Logs/metrics để biết scheduler vẫn chạy, không chỉ process đang sống.

### 14.2. Batch/CLI job hữu hạn

Một batch job chạy đúng một lần cần trả exit status cho scheduler/CI. Nếu bật keepalive=true mà không có cơ chế chủ động dừng, process **có thể ở lại vô hạn** sau khi job đã xong, khiến CI/Kubernetes Job chờ và timeout. Với workload này:

- Thực hiện công việc có điểm hoàn thành rõ ràng.
- Chờ `Future` hoặc completion stage có deadline khi cần.
- Dùng `SpringApplication.exit(context)` rồi `System.exit(code)` nếu contract yêu cầu mã cho OS, sau khi cleanup hợp lệ.
- Hoặc tự đóng context theo lifecycle nếu entrypoint được thiết kế cho CLI.
- Không dùng `spring.main.keep-alive=true` làm thay thế cho `join/get/await` của job hữu hạn.

### 14.3. Web application đã có non-daemon threads

Trong app Tomcat/Jetty/Netty, các platform threads do server/framework thường có thể giữ JVM sống dù `spring.main.keep-alive=false`. Vì vậy thử trên web server không chứng minh đúng lỗi daemon scheduler của CLI. Vẫn có thể bật keepalive=true theo thiết kế, nhưng hiệu ứng observable có thể không rõ ràng vì có nhiều nguồn giữ process sống.

### 14.4. Daemon jobs có side effect quan trọng

Nếu xử lý thanh toán, đơn hàng, email bắt buộc hoặc sự kiện broker, chỉ bật keepalive không bảo đảm chống mất công việc. Process có thể bị restart, OOM, SIGKILL, node chết hoặc deployment termination hết hạn. Khi nhận việc quan trọng, cần lưu bền, ack/retry đúng thời điểm và idempotency key.

## 15. Giữ JVM sống khác với kết thúc task đúng cách

**Keepalive giải quyết liveness**. Nó không giải quyết **lifecycle ownership** hay **durability**.

Với lab, `Thread.ofVirtual()` được tạo trong `ApplicationRunner` mà không được Spring bean nào quản lý. Khi operator dừng process, Spring không tự `join` mọi virtual thread thủ công. Nếu task còn chạy, nó có thể bị bỏ dở. Trong sản phẩm, hãy dùng owner phù hợp:

~~~text
RUNNING
   |
   v
QUIESCING: từ chối job mới, dừng intake HTTP/broker
   |
   v
DRAINING: chờ in-flight jobs trong deadline
   |
   +-- completed -> commit/ack
   +-- retryable -> lưu state/requeue đúng semantics
   +-- cancelled -> interrupt + cleanup hợp tác
   |
   v
CLOSING: đóng executors, sessions, connections
   |
   v
TERMINATED: context hoàn thành shutdown
~~~

**Ba tình huống cần phân biệt:**

1. **main return**: thread main kết thúc nhưng process có thể còn sống nếu có non-daemon threads/keepalive; không có nghĩa app đã shutdown.
2. **SpringApplication.exit(context) / context.close()**: ứng dụng chủ động vào shutdown lifecycle; keepalive **không** nên giữ một context đã đóng hoạt động vô hạn.
3. **SIGKILL/JVM crash**: không bảo đảm `@PreDestroy`, `SmartLifecycle`, `finally` hoặc logs cuối; dữ liệu chỉ ở RAM có thể mất.

### 15.1. Ví dụ quản lý ExecutorService có deadline (snippet)

Khi một bean sở hữu `ExecutorService`, nó cần stop logic có giới hạn:

~~~java
private void stopExecutor(ExecutorService executor) {
    executor.shutdown();
    try {
        if (!executor.awaitTermination(4, TimeUnit.SECONDS)) {
            executor.shutdownNow();

            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                System.err.println("Workers did not terminate");
            }
        }
    } catch (InterruptedException ex) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

**Đây là method snippet, không nằm trong hai file Java runnable của lab.** Cần imports `ExecutorService`/`TimeUnit` và gọi bởi đúng lifecycle owner (`@PreDestroy` hoặc `SmartLifecycle` phù hợp). `shutdownNow()` chỉ đưa ra yêu cầu dừng **best effort**; external I/O không tôn trọng interrupt vẫn có thể kéo dài. Có deadline ở JDBC/HTTP clients, cleanup trong `finally` và durable work state nếu không được mất việc.

**Không nhầm `ExecutorService.close()` với keepalive:** Java 21 `ExecutorService.close()` có thể chờ tasks hoàn thành; nếu task block không deadline, nó có thể giữ shutdown lâu ngoài mong đợi. Phải thiết kế shutdown budget thực tế thay vì gọi close vô hạn trong hook.

### 15.2. Keepalive không tự sửa virtual thread pinning

Trên JDK 21, blocking trong một số `synchronized`/native scenarios có thể pin virtual thread vào carrier, làm giảm throughput. JDK 24+ có cải tiến quan trọng theo JEP 491 đối với synchronized pinning. Đây là vấn đề **scheduler efficiency**, khác với việc process tự thoát do daemon semantics. Bật keepalive không cải thiện pinning và không thay thế profiling/JFR.

Nếu throughput chậm, đo JFR, CPU samples, thread dumps và downstream timeouts; không suy “keepalive=true” sẽ sửa performance hoặc đổi loại thread.

## 16. Giới hạn đồng thời và an toàn tài nguyên ngoài

Virtual threads nhẹ nhưng **không miễn phí** và không làm tăng số connections của database hoặc API quota. Ví dụ:

- 1.000 virtual threads có thể cùng chờ 10 JDBC connections.
- Một API đối tác chỉ chấp nhận 2 in-flight calls mặc dù ứng dụng tạo 100 virtual threads.
- Một `@Scheduled(fixedRate=100ms)` có thể tạo các executions chồng nhau nếu mỗi call lâu hơn cadence và scheduler cho phép.
- Một job bị retry vô hạn có thể tạo backlog dù JVM vẫn sống khỏe nhờ keepalive.

Dùng admission control hoặc `Semaphore` quanh tài nguyên khan hiếm. Ví dụ snippet:

~~~java
private final Semaphore slots = new Semaphore(2);

public void invokeExternalService() throws InterruptedException {
    if (!slots.tryAcquire(2, TimeUnit.SECONDS)) {
        throw new IllegalStateException("external capacity exhausted");
    }
    try {
        callExternalServiceWithTimeout();
    } finally {
        slots.release();
    }
}
~~~

**Đây là snippet thiết kế**, cần imports, field/method thực cho external service, error handling và đóng client. Semaphore chỉ giới hạn concurrency trong **một JVM**; nhiều replicas có thể vượt quota toàn cụm. Không giữ permit quá lâu khi job đợi việc không liên quan tới external call; phải có deadline và release trong `finally`.

**Phân biệt:** `spring.main.keep-alive=true` làm process tiếp tục sống, còn `Semaphore`/connection pool quyết định **bao nhiêu việc có thể thực hiện đồng thời**. Hai cơ chế không thay thế nhau.

## 17. Quan sát bằng jcmd/JFR và log

### 17.1. Đo thread thực tế

Chạy kịch bản B với keepalive=true, sau khi thấy `LAB_MAIN_RETURNED`, mở terminal thứ hai:

~~~bash
jcmd -l
jcmd PID Thread.dump_to_file -format=json virtual-lab-threads.json
~~~

Thay `PID` bằng PID JVM của ứng dụng đang chạy. Lệnh `jcmd` thuộc JDK, phải có quyền attach vào process và dùng bản JDK/tooling tương thích. Với JDK 21+, thread dump JSON hỗ trợ quan sát virtual threads theo format/khả năng version. Không kỳ vọng một virtual task rất ngắn luôn xuất hiện trong snapshot đúng lúc nếu nó đã hoàn thành.

Nếu chỉ có `jstack`, virtual thread support/format có thể khác; đối chiếu tài liệu JDK hiện tại. Có thể dùng JFR để quan sát virtual-thread events, pinning (khi phù hợp JDK) và blocking behavior.

### 17.2. Logging markers hữu ích

| Marker | Đo gì? | Không được suy ra |
|---|---|---|
| `LAB_MAIN_RETURNED` | Method main đã nhận lại kết quả `SpringApplication.run` và tới dòng cuối | JVM đã dừng |
| `LAB_JOB_SUBMITTED` | Runner đã tạo một virtual thread | Job đã hoàn thành |
| `LAB_JOB_BEGIN` | Virtual worker đã bắt đầu | Task có durability |
| `LAB_JOB_DONE` | One-shot demo đã chạy hết phần sleep theo code | External side effect đã commit |
| `LAB_TICK virtual=true` | Method scheduled đang chạy trên virtual thread | Toàn hệ thống chỉ dùng virtual threads |
| `LAB_TICK daemon=true` | Thread của method không giữ JVM sống | Process không có non-daemon thread khác |
| `LAB_CONTEXT_DESTROYED` | Bean destroy hook được gọi | Mọi công việc/connection đều đã cleanup |
| `PROBE ... EXITED` | Child process đã kết thúc trong budget quan sát | Mọi background job đều thành công |
| `PROBE ... STILL_RUNNING` | Child vẫn sống sau budget | Giữ sống là do keepalive nếu còn nguồn non-daemon khác |

Đối chiếu **ít nhất hai loại bằng chứng**: loại thread và process liveness. Nếu kết luận “scheduler virtual làm app tự thoát”, phải chỉ ra `virtual=true, daemon=true` hoặc docs, `main returned`, child process exited, đồng thời không có web server/non-daemon thủ công.

### 17.3. Đo bằng uptime và startup state

Trong production, process uptime/restart count không đủ để biết `@Scheduled` chạy thành công. Thêm metric heartbeat age, lần tick cuối, duration/failure count, upstream availability, queue backlog và job outcomes. Nếu process vẫn sống vì keepalive nhưng scheduler đã thất bại do exception/disabled configuration, uptime vẫn tăng — nên không dùng liveness một mình làm “healthy”.

## 18. Các tình huống dễ dẫn tới kết luận sai

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Bật virtual=true rồi CLI thoát ngay | Scheduler virtual/daemon, không còn non-daemon | Bật `spring.main.keep-alive=true` khi workload cần sống lâu |
| Keepalive=true nhưng không thấy tick | `@EnableScheduling` thiếu, bean không scan, cron/filter lỗi, startup fail | Kiểm scheduler bean, logs, job method và startup |
| Tắt keepalive nhưng app vẫn sống | Có non-daemon thread khác: scheduler platform, web, agent | Dùng raw JAR, thread dump, kiểm dependencies |
| Đặt `spring.task.scheduling.pool.size=4` mà vẫn một loại virtual scheduler | Pool setting bị bỏ qua trong virtual mode | Xác định `SimpleAsyncTaskScheduler`, dùng resource limits riêng |
| `@Scheduled(fixedDelay)` không giống fixedRate | SimpleAsyncTaskScheduler có special fixed-delay semantics | Dùng fixedRate trong lab, đọc Javadoc scheduler |
| Virtual worker `LAB_JOB_DONE` in ra dù keepalive=false | JVM còn sống vì một thread khác/timing | Kiểm process liveness và thread dump |
| Keepalive=true rồi CLI batch không tự hoàn tất | Keepalive giữ JVM ngay cả khi job xong | Dùng explicit exit/close cho batch |
| Chạy Maven/IDE thấy kết quả ngược | Launcher/agent có lifecycle riêng | Chạy `java -jar` subprocess độc lập |
| `Thread.currentThread().isVirtual()==false` trong scheduled task | Virtual integration chưa bật hoặc custom scheduler dùng platform | Kiểm properties/JDK/scheduler implementation |
| One-shot Thread.ofVirtual() vẫn true khi property false | Đây là JDK API độc lập Spring Boot setting | Không dùng nó để chứng minh Boot scheduler đã chuyển |
| Chỉ có 1 tick rồi app thoát | Process lifecycle hoặc exception/cancel/signal | Log signal, `@PreDestroy`, status, environment |
| App tắt khi container được thay thế dù keepalive=true | TERM/SIGKILL/platform termination | Keepalive không chặn operator shutdown |
| `@PreDestroy` không log khi kill -9 | SIGKILL không chạy Java hooks đáng tin | Dùng durability, không suy từ missing log |
| CPU cao khi dùng virtual threads | Work CPU-bound, pinning, too much concurrency | JFR/profiling, downstream limits |
| DB pool hết connections | Virtual threads vượt quota tài nguyên ngoài | Bounded admission, semaphore, timeout |
| Scheduler method chạy quá lâu | Fixed-rate overlap/backlog, I/O không timeout | Deadline, giới hạn concurrent calls, backpressure |
| App dùng Java 17 bị `NoSuchMethodError`/compile error | Virtual threads cần Java 21+ | Kiểm java/Maven runtime version |
| Chỉnh property mà scenario không đổi | CLI args/property precedence hoặc app đang chạy JAR cũ | Xem actual args, rebuild, log version |
| Unit test PASS nhưng process tự thoát ngoài prod | JUnit/test runner giữ JVM | Dùng ProcessBuilder end-to-end test |
| `LAB_CONTEXT_DESTROYED` có mà job vẫn dở | Virtual worker unmanaged | Thiết kế owner/shutdown state |
| PID từ jcmd không thấy | Process scenario A đã thoát quá nhanh | Quan sát kịch bản B keepalive=true |

## 19. Bài tập mở rộng theo mức độ

### Bài tập A — Nhận diện daemon threads

Trong một process B, ghi output `LAB_JOB_BEGIN virtual=true daemon=true` và `LAB_TICK virtual=true daemon=true`. Trả lời: vì sao `isDaemon==true` không có nghĩa JVM phải tắt **ngay lập tức** khi keepalive=true?

**Kết luận mẫu:** Keepalive bảo đảm process có cơ chế giữ sống độc lập với daemon state của các virtual workers; virtual worker không bị chuyển thành non-daemon.

### Bài tập B — So ba mode

Chạy ProcessProbe và lưu ba log files. Lập bảng `autoExited`, `mainReturned`, `tickCount`, `jobDone` cho A/B/C. Nếu A không tự thoát trong 6 giây, kiểm non-daemon threads và viết rõ limitation thay vì sửa kết quả theo mong đợi.

### Bài tập C — Thử duration của one-shot job

Trong bản copy lab, đổi `Thread.sleep(3_000)` thành 8 giây nhưng ProcessProbe vẫn quan sát 6 giây. Ở B, child có thể được probe terminate trước khi `LAB_JOB_DONE` xuất hiện. Điều này chứng minh **keepalive cho cơ hội chạy, không đảm bảo job hoàn thành trước khi operator tắt process**.

### Bài tập D — Đổi fixedRate sang fixedDelay

Thử `@Scheduled(initialDelay=1000, fixedDelay=1000)` trên bản copy, quan sát thread name/`isVirtual` và hành vi của `SimpleAsyncTaskScheduler`. Đọc Javadoc: fixed-delay có semantics chạy trên scheduler thread, không suy từ một kết quả rằng virtual threads đã bị tắt trên toàn ứng dụng.

### Bài tập E — Không web và có web

Thêm Spring Web vào một bản copy, chạy với virtual=true keepalive=false. So process lifetime với CLI. Tại sao embedded server có thể khiến A không còn tự thoát? Xóa dependency sau thí nghiệm để quay về baseline.

### Bài tập F — Tác vụ có kết quả bền vững

Thay one-shot sleep bằng việc ghi một record vào local test database/queue có xác nhận. Thử normal shutdown và forced kill trong môi trường giả lập, ghi nhận trường hợp job mất, redelivery và idempotency. Không đưa forced kill vào production dữ liệu thật.

### Bài tập G — Giới hạn upstream

Cho scheduled task phát 20 virtual calls tới một local mock API, quota chỉ 2 concurrent. Thêm `Semaphore(2)` và deadline acquire; đo external peak <=2, failed/rejected count, và nhắc lại rằng keepalive không giải quyết quota.

### Bài tập H — JDK 21 vs JDK 24+

Dùng cùng workload, so virtual thread behavior và JFR diagnostics. Trên JDK 21 kiểm `jdk.VirtualThreadPinned` khi có blocking trong `synchronized`; trên JDK 24+ đọc JEP 491 để hiểu thay đổi synchronized pinning. Không dùng benchmark một lần để kết luận JDK mới luôn nhanh hơn.

## 20. Checklist nghiệm thu

- [ ] Chạy đúng JDK 21+ và Maven build Spring Boot 3.5.x.
- [ ] `spring.main.web-application-type=none`, không có web starter trong baseline.
- [ ] Có `@EnableScheduling`, `@Scheduled(fixedRate=...)`.
- [ ] Biết virtual threads luôn daemon.
- [ ] Biết keepalive property mặc định false.
- [ ] Chạy riêng A: virtual=true, keepalive=false.
- [ ] Chạy riêng B: virtual=true, keepalive=true.
- [ ] Chạy riêng C: virtual=false, keepalive=false.
- [ ] Trong B, thấy `LAB_TICK virtual=true daemon=true` và process vẫn sống sau main return.
- [ ] Trong C, thấy `LAB_TICK virtual=false` với scheduler platform theo Boot default.
- [ ] Trong A, đánh giá process có tự thoát sớm không; kiểm non-daemon thread nếu không.
- [ ] Không dùng Maven Run/IDE/test runner làm bằng chứng duy nhất.
- [ ] Không hiểu `LAB_JOB_SUBMITTED` là job đã hoàn tất.
- [ ] Quan sát `LAB_JOB_DONE` trong điều kiện process còn sống đủ lâu.
- [ ] Thử Ctrl+C/SIGTERM, hiểu `@PreDestroy` khác cleanup của unmanaged threads.
- [ ] Biết keepalive=true không chặn deliberate shutdown, crash hay SIGKILL.
- [ ] Không nhầm main keepalive với HTTP keepalive hoặc executor idle timeout.
- [ ] Không dùng keepalive để thay `Future.get` hoặc durable queue.
- [ ] Biết virtual threads không tự mở rộng DB connections/upstream quota.
- [ ] Có bảng quan sát và ghi lại JVM version, Spring Boot version, environment.
- [ ] Giải thích đúng vì sao scheduled daemon tasks có thể không giữ JVM sống.

## 21. Tài liệu chính thức

1. **Spring Boot 3.5 — SpringApplication, Virtual Threads**: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html — Java 21+, daemon threads, `@Scheduled` và `spring.main.keep-alive=true`.
2. **Spring Boot 3.5 — Common Application Properties**: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/ — giá trị mặc định của `spring.main.keep-alive`.
3. **Spring Boot 3.5 — Task Execution and Scheduling**: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html — `SimpleAsyncTaskExecutor`, `SimpleAsyncTaskScheduler` và pool properties.
4. **Spring Boot 3.5 — SpringApplication API**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html — `isKeepAlive()`, `setKeepAlive(boolean)`.
5. **Java SE 21 — Virtual Threads Guide**: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html — virtual vs platform threads, daemon semantics và `Thread.ofVirtual()`.
6. **Java SE 21 — Thread API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html — `isVirtual()`, `isDaemon()`, `join()` và interruption.
7. **Java SE 21 — Process/ProcessBuilder API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html — chạy child process và quan sát exit.
8. **Spring Framework 6.2 — SimpleAsyncTaskScheduler API**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html — virtual mode và fixedDelay behavior.
9. **Spring Framework 6.2 — @Scheduled**: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html — cách kích hoạt và định nghĩa lịch.
10. **JEP 444 — Virtual Threads**: https://openjdk.org/jeps/444 — semantics và mục tiêu virtual threads.
11. **JEP 491 — Synchronize Virtual Threads without Pinning**: https://openjdk.org/jeps/491 — thay đổi pinning từ JDK 24.

**Tổng kết:** Khi Spring Boot 3.5 chạy Java 21+ và bật virtual threads, scheduler/worker có thể là **daemon**; vì vậy ứng dụng CLI chỉ có scheduled/background work có thể **kết thúc ngay sau `main()`**, dù task đã được đăng ký. `spring.main.keep-alive=true` giữ JVM tồn tại khi không còn non-daemon threads và cho phép tasks tiếp tục chạy, nhưng **không chuyển virtual threads thành platform threads, không đảm bảo business completion và không thay đổi shutdown/durability**. Cần kiểm bằng tiến trình `java -jar` thật, đối chiếu `isVirtual/isDaemon` và process liveness, rồi thêm lifecycle owner, deadline, backpressure và durable state cho công việc production.