# Luồng ảo là daemon và nguy cơ ứng dụng nền kết thúc sớm

## 1. Vấn đề xảy ra khi bật virtual threads cho Spring Boot

Kể từ Java 21, **virtual threads** (luồng ảo) là một cơ chế concurrency chính thức cho phép thực hiện nhiều công việc chờ I/O với chi phí thread thấp hơn platform threads truyền thống. Spring Boot 3.3 có thể dùng virtual threads cho task execution và scheduling. Tuy nhiên, có một ràng buộc của JVM thường bị bỏ qua: **mọi virtual thread đều là daemon**.

**Daemon thread không giữ tiến trình JVM sống khi mọi non-daemon thread đã kết thúc.** Do đó, ứng dụng Spring Boot *không có web server*, chỉ chạy tác vụ nền hoặc **@Scheduled**, có thể khởi động thành công rồi **thoát sớm trước khi scheduled job đầu tiên được thực thi** nếu các luồng còn lại đều là virtual/daemon threads.

Ví dụ một chương trình quản lý lịch mỗi 30 phút:

~~~text
main (platform, non-daemon)
    |
    +-- SpringApplication.run(...)
    |      +-- tạo ApplicationContext
    |      +-- đăng ký ScheduledAnnotationBeanPostProcessor
    |      +-- auto-configure scheduler dùng virtual threads
    |      +-- gọi runners, phát ApplicationReadyEvent
    |
    +-- run(...) trả về
    +-- main() kết thúc
              |
              v
      non-daemon threads còn lại?
              |
              +-- KHÔNG -> JVM bắt đầu shutdown
              |           scheduled job chưa đến giờ -> không chạy
              |
              +-- CÓ   -> JVM có thể tiếp tục sống
                          scheduler có cơ hội kích hoạt
~~~

Điều này không có nghĩa Spring Boot lỗi khi phát hiện **@Scheduled**. Scheduler có thể đã được đăng ký đúng nhưng **JVM đã kết thúc trước lúc nó kịp chạy**. Vì vậy, chỉ nhìn vào thông báo **Started Application** hoặc một lần context test thành công không đủ xác nhận dịch vụ nền thực sự duy trì hoạt động.

Spring Boot 3.3 cung cấp hai property có nhiệm vụ khác nhau:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

- **spring.threads.virtual.enabled=true:** cho phép hạ tầng được Boot hỗ trợ dùng virtual threads khi chạy trên Java 21+.
- **spring.main.keep-alive=true:** giữ JVM hoạt động ngay cả khi những thread công việc còn lại là daemon/virtual threads, thích hợp với một service chạy nền lâu dài.

Bài viết theo **Java 21, Spring Boot 3.3.13 và Spring Framework 6.1**. Những ví dụ dùng **Thread.ofVirtual()**, **Thread.isVirtual()** không biên dịch được bằng JDK 17.

## 2. Quy tắc JVM: non-daemon giữ tiến trình, daemon thì không

Java định nghĩa một luồng có thể là daemon hoặc non-daemon. Trạng thái này ảnh hưởng đến **thời điểm JVM được phép bắt đầu shutdown thông thường**, chứ không biểu diễn mức độ quan trọng của công việc.

| Tiêu chí | Platform thread | Virtual thread (Java 21) |
| --- | --- | --- |
| Thread object | java.lang.Thread | java.lang.Thread |
| Có thể daemon | Có | **Luôn daemon** |
| Có thể non-daemon | Có | **Không** |
| Có thể giữ JVM sống | Có, nếu non-daemon còn hoạt động | Không, chỉ do nó tồn tại |
| Dùng API isDaemon() | Có | Có, luôn true |
| Dùng API isVirtual() | false | true |
| Thay đổi daemon trước start | Có thể với platform thread | Không thể đặt false cho virtual thread |
| Sử dụng công việc I/O | Có | Có, thường là một use case phù hợp |

**Quy tắc sống còn:** JVM bắt đầu shutdown sequence khi tất cả các **non-daemon threads đã start** đều đã kết thúc. Những virtual threads chưa hoàn thành không ngăn điều đó.

~~~text
Trạng thái A:
main (non-daemon)       alive
background-vt (daemon)  waiting
=> JVM còn sống vì main.

Trạng thái B:
main (non-daemon)       terminated
background-vt (daemon)  waiting
non-daemon khác          không có
=> JVM bắt đầu shutdown, dù background-vt chưa xong.

Trạng thái C:
main (non-daemon)       terminated
background-vt (daemon)  waiting
server-thread            non-daemon, alive
=> JVM vẫn sống vì server-thread.
~~~

Khi main kết thúc, **không thể suy luận ngay JVM sẽ thoát**: có thể còn web server, consumer hoặc thread khác ở trạng thái non-daemon. Nhưng nếu một chương trình non-web thực sự chỉ còn daemon tasks, rủi ro thoát sớm là có thật.

### 2.1. Vì sao virtual thread luôn daemon?

Virtual threads được Java thiết kế cho cách dùng **nhiều thread-per-task**. Chúng được JVM lên lịch trên một số carrier platform threads, cho phép một virtual thread tạm dừng khi chờ I/O mà không phải chiếm riêng một OS thread trong toàn bộ thời gian.

Khả năng tạo số lượng lớn không đồng nghĩa mỗi virtual thread phải chịu trách nhiệm giữ JVM hoạt động vô hạn. Java tách **vòng đời task** khỏi **vòng đời tiến trình** để ứng dụng tự quyết định cần chờ kết quả, giữ một service dài hạn hay kết thúc.

Daemon status **không có nghĩa** virtual thread bị ưu tiên thấp hơn, không được làm I/O hoặc không được chạy nghiệp vụ quan trọng. Nó chỉ không phải cơ chế keep-alive của JVM.

### 2.2. Thread.currentThread() phản ánh virtual thread, không phải carrier

Khi code đang chạy trong một virtual thread:

~~~java
Thread current = Thread.currentThread();
System.out.println(current.isVirtual());
System.out.println(current.isDaemon());
~~~

Kết quả là:

~~~text
true
true
~~~

Dù virtual thread đang thực thi trên một **carrier platform thread**, Thread.currentThread() vẫn trả về virtual Thread hiện tại. Đừng coi carrier thread là một non-daemon keeper được framework cam kết cung cấp cho ứng dụng.

### 2.3. Không thể đổi virtual thread thành non-daemon

Trên Java 21:

~~~java
Thread virtual = Thread.ofVirtual()
        .name("background-vt")
        .unstarted(() -> {});

System.out.println(virtual.isDaemon()); // true
virtual.setDaemon(false);               // IllegalArgumentException
~~~

Đây là snippet trong một Java method. Java quy định **Thread.setDaemon(false)** trên virtual thread ném **IllegalArgumentException**; không có builder option **Thread.ofVirtual().daemon(false)**. Vì vậy, sửa daemon flag không phải giải pháp.

## 3. Demo Java 21 độc lập: task còn chờ nhưng process đã thoát

Ví dụ sau tạo một virtual thread và dùng CountDownLatch bảo đảm thread thực sự đã bắt đầu. Sau đó virtual thread đợi một latch **không bao giờ mở**, trong khi main kết thúc.

Tạo tệp **VirtualDaemonExitDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class VirtualDaemonExitDemo {

    public static void main(String[] args)
            throws InterruptedException {

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        Thread worker = Thread.ofVirtual()
                .name("background-vt")
                .start(() -> {
                    Thread current = Thread.currentThread();

                    System.out.println(
                            "VT | virtual=" + current.isVirtual()
                            + " daemon=" + current.isDaemon());

                    started.countDown();

                    try {
                        neverReleased.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }

                    System.out.println("VT | finished");
                });

        started.await();

        Thread main = Thread.currentThread();
        System.out.println(
                "MAIN | virtual=" + main.isVirtual()
                + " daemon=" + main.isDaemon());
        System.out.println("MAIN | returning");

        // Không join(worker), không giải phóng neverReleased.
    }
}
~~~

Chạy với **JDK 21+**:

~~~bash
javac VirtualDaemonExitDemo.java
java VirtualDaemonExitDemo
~~~

Trong terminal chạy Java thông thường, các dòng chương trình in là:

~~~text
VT | virtual=true daemon=true
MAIN | virtual=false daemon=false
MAIN | returning
~~~

**Không có dòng VT | finished.** Task vẫn đang đợi neverReleased.await(), nhưng không còn non-daemon thread nào giữ JVM hoạt động sau khi main kết thúc.

Điểm thiết kế của ví dụ: started.await() chỉ giúp main đợi đến khi virtual thread **in dòng quan sát**, không đợi nó hoàn thành. Nếu bỏ CountDownLatch started, main có thể kết thúc trước cả lúc VT kịp in dòng đầu, khiến output nondeterministic.

**Lưu ý:** một IDE, debugger hoặc agent Java có thể tạo thêm non-daemon threads, làm lifetime của process trong môi trường đó khác với lệnh Java độc lập ở terminal. Hãy dùng executable process riêng khi thực nghiệm.

### 3.1. Đổi sang platform non-daemon thì sao?

Nếu đổi Thread.ofVirtual() thành **Thread.ofPlatform().daemon(false)**, worker đang chờ latch sẽ **giữ JVM sống** dù main đã trả về. Đây là khác biệt thường khiến ứng dụng từng chạy với một scheduler platform thread trở nên không ổn định sau khi chuyển sang virtual threads.

Không dùng một platform thread chờ vô hạn làm giải pháp production; cách đó tạo điều kiện treo shutdown và thiếu quản lý lifecycle.

## 4. Demo Java 21: chờ tác vụ hữu hạn bằng join

Với một CLI job có thời hạn, cách chính xác là **chờ completion**, không phải giữ tiến trình vô hạn.

Tạo **VirtualThreadJoinDemo.java**:

~~~java
public class VirtualThreadJoinDemo {

    public static void main(String[] args)
            throws InterruptedException {

        Thread job = Thread.ofVirtual()
                .name("report-job")
                .start(() -> {
                    System.out.println(
                            "TASK | virtual="
                            + Thread.currentThread().isVirtual());
                    System.out.println("TASK | completed");
                });

        job.join();
        System.out.println("MAIN | joined");
    }
}
~~~

Chạy:

~~~bash
javac VirtualThreadJoinDemo.java
java VirtualThreadJoinDemo
~~~

Stdout:

~~~text
TASK | virtual=true
TASK | completed
MAIN | joined
~~~

**join() làm luồng main non-daemon chờ** cho tới khi virtual thread kết thúc. Virtual thread vẫn daemon, nhưng JVM chưa shutdown vì main đang sống.

Một biến thể chuẩn hơn cho nhiều tác vụ hữu hạn:

~~~java
try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {

    Future<String> result =
            executor.submit(() -> "report-complete");

    System.out.println(result.get());
}
~~~

Đây là snippet, cần imports **ExecutorService**, **Executors**, **Future** và xử lý checked exceptions. Java 21 hỗ trợ ExecutorService dạng AutoCloseable; try-with-resources đóng executor và theo semantics của API chờ tác vụ khi cần. Phù hợp cho batch job cần kết thúc có kiểm soát.

### 4.1. Vì sao Thread.sleep không thay thế join?

Code:

~~~java
Thread.ofVirtual().start(() -> performBusinessTask());
Thread.sleep(500);
~~~

là snippet minh họa anti-pattern; assume đã có performBusinessTask(). 500 ms chỉ là phỏng đoán. Khi CI chậm hoặc API bên ngoài bị timeout, tác vụ có thể chưa hoàn thành và vẫn bị cắt ngang lúc main kết thúc.

**Chờ một điều kiện thực sự**: Thread.join(), Future.get(), CountDownLatch hoặc hợp đồng completion khác; dùng timeout và xử lý lỗi thích hợp khi cần giới hạn thời gian.

## 5. Spring Boot tự động cấu hình virtual-thread executor và scheduler ra sao?

Spring Boot 3.3 hỗ trợ:

~~~properties
spring.threads.virtual.enabled=true
~~~

khi runtime là Java 21+. Khi không có **custom Executor** làm thay đổi lựa chọn mặc định, Spring Boot có thể dùng:

- **SimpleAsyncTaskExecutor** với virtual threads cho công việc bất đồng bộ được Boot tích hợp như **@EnableAsync**, Spring MVC asynchronous request processing và một số integration khác.
- **SimpleAsyncTaskScheduler** với virtual threads khi ứng dụng cần scheduler, ví dụ đã bật **@EnableScheduling**.
- Nếu không bật virtual threads, các default tương ứng thông thường là **ThreadPoolTaskExecutor** và **ThreadPoolTaskScheduler**.

Đây là *lựa chọn auto-configuration*, không phải quy tắc mọi thread trong toàn JVM tự động thành virtual. Có những thành phần như **luồng main**, thread của thư viện và **custom Executor/TaskScheduler** vẫn có thể sử dụng platform threads.

### 5.1. Khi nào không thể kỳ vọng auto-configured virtual executor?

Nếu ứng dụng có:

~~~java
@Bean
Executor customExecutor() {
    return Executors.newFixedThreadPool(4);
}
~~~

đây là snippet cần imports và cách đóng Executor phù hợp. Một custom Executor bean có thể ngăn/ảnh hưởng auto-configuration và lựa chọn executor. Property virtual threads không tự động chuyển custom fixed-thread-pool thành virtual threads.

Tương tự, một **ThreadPoolTaskScheduler** do bạn tự khai báo vẫn dùng platform threads trừ khi chính nó được cấu hình theo cơ chế khác.

Kiểm tra executor/scheduler thực sự bằng bean wiring và Thread.currentThread().isVirtual() trong callback. Không kết luận chỉ từ một property.

### 5.2. Các thuộc tính pool có thể không còn áp dụng

Với **SimpleAsyncTaskExecutor** tạo virtual thread mỗi task, những property điều chỉnh pool của **ThreadPoolTaskExecutor** không còn có cùng tác dụng:

~~~properties
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
~~~

Các property này không tự trở thành một giới hạn 16 virtual tasks. Với SimpleAsyncTaskScheduler, các property pool của ThreadPoolTaskScheduler cũng không áp dụng theo cùng cách.

Do đó nếu downstream chỉ chịu được 20 database queries đồng thời, phải dùng **Semaphore**, connection-pool size, bulkhead hoặc cơ chế limit riêng. **Virtual threads không tạo thêm dung lượng cho database/network**.

## 6. Vì sao @Scheduled-only là trường hợp rủi ro nhất?

Với ứng dụng non-web:

~~~java
@SpringBootApplication
@EnableScheduling
public class ScheduleApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScheduleApplication.class, args);
    }
}
~~~

Spring Boot có thể đăng ký scheduled bean hợp lệ, gọi runner và phát ApplicationReadyEvent. Nhưng:

~~~text
0s       main gọi run()
1s       context refresh xong
1s       ApplicationReadyEvent
1s       main() trả về
1s       chỉ còn daemon/virtual work
1s       JVM bắt đầu shutdown
5s       @Scheduled dự kiến kích hoạt => không còn process
~~~

Các thời điểm chỉ là **ví dụ minh họa**.

**Một context đã sẵn sàng không chứng minh scheduled callback trong tương lai sẽ được thực thi.** Sự tồn tại của scheduled metadata hoặc executor bean trong context cũng không làm JVM được giữ sống.

### 6.1. @Scheduled có luôn chạy sau ApplicationReadyEvent không?

Không. Tùy thời điểm đăng ký scheduler, initialDelay, thời gian runners và tải máy, một scheduled callback có thể chạy trong lúc startup/runners chưa hoàn tất. Nhưng với một job có initialDelay dài hơn startup, nó chắc chắn cần process còn sống đến mốc lịch.

Đừng dựa vào thứ tự timing ngẫu nhiên để giải quyết keep-alive. Chọn rõ vòng đời dịch vụ.

### 6.2. Virtual threads không làm cron trở thành durable scheduler

**@Scheduled** thường chạy trong từng JVM instance. Nếu process kết thúc, lịch không tự được giao cho một process khác. Nếu có nhiều replicas, mỗi instance có thể chạy cùng một job, gây duplicate work.

Nếu yêu cầu phải thực thi bền vững, cần distributed scheduler/job database/queue, retry và idempotence. **Keep-alive chỉ giữ process sống**, không bảo đảm job được lưu và chạy đúng một lần trên toàn cụm.

## 7. Cách Spring Boot 3.3 giữ JVM sống: spring.main.keep-alive

Cấu hình:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Spring Boot 3.3 khuyến nghị bật **spring.main.keep-alive=true** khi dùng virtual threads, đặc biệt với @Scheduled hoặc công nghệ khác chỉ tạo daemon threads.

### 7.1. Hai property giải quyết hai vấn đề

| Property | Chức năng | Không bảo đảm |
| --- | --- | --- |
| **spring.threads.virtual.enabled=true** | Các execution components được Boot hỗ trợ có thể dùng virtual threads | Không giữ process sống |
| **spring.main.keep-alive=true** | Đảm bảo JVM còn sống ngay cả khi chỉ còn virtual/daemon work | Không bảo đảm job thành công hoặc sống qua SIGKILL |

Bật keep-alive **không đổi** giá trị Thread.isDaemon() của virtual threads. Java 21 vẫn trả true. Spring Boot dùng cơ chế giữ lifetime của ứng dụng, không hack daemon flag.

### 7.2. Keep-alive không giải quyết hết shutdown và lỗi

Property này không ngăn:

- SIGTERM/Ctrl+C và đường shutdown bình thường.
- System.exit(...) do ứng dụng chủ động gọi.
- SIGKILL, crash, out-of-memory hoặc container orchestration kết thúc process.
- ApplicationContext đóng theo lifecycle.
- Công việc async ném exception.
- Job mất vì executor chỉ lưu task trong bộ nhớ.

Vì vậy **keep-alive không phải durable queue**, cũng không phải cơ chế “chắc chắn mọi virtual thread sẽ chạy xong”.

### 7.3. Bật keep-alive cho workload nào?

**Phù hợp:** non-web background service cần sống liên tục để kích hoạt job theo lịch, consume messages, xử lý listener/watchers, và chạy task khi có sự kiện trong tương lai.

**Không luôn phù hợp:** CLI/batch job hữu hạn cần hoàn tất một công việc rồi thoát với exit code rõ ràng. Với loại này nên chờ completion rồi đóng context/kết thúc tiến trình có chủ đích.

## 8. Ví dụ Spring Boot 3.3 / Java 21 hoàn chỉnh

Bài thực hành giữ nguyên một chương trình, lần lượt chạy với **keep-alive=false** và **keep-alive=true**, quan sát process có còn sống đủ lâu cho một scheduled tick hay không.

### 8.1. Cấu trúc Maven

~~~text
virtual-keepalive-demo/
  pom.xml
  src/main/java/com/example/keepalive/VirtualKeepAliveApplication.java
~~~

Dùng **JDK 21+**, Spring Boot **3.3.13** và Maven 3.9+.

**pom.xml:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>virtual-keepalive-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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

### 8.2. Mã Java đầy đủ

Tạo **src/main/java/com/example/keepalive/VirtualKeepAliveApplication.java**:

~~~java
package com.example.keepalive;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableScheduling
public class VirtualKeepAliveApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(VirtualKeepAliveApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        application.run(args);

        System.out.println("MAIN | run returned");
        // Không đóng context, không System.exit().
    }

    @Bean
    ApplicationRunner startupThread() {
        return args -> {
            Thread thread = Thread.currentThread();
            System.out.println(
                    "RUNNER | virtual=" + thread.isVirtual()
                    + " daemon=" + thread.isDaemon());
        };
    }
}

@Component
class BackgroundHeartbeat {

    private final AtomicInteger counter = new AtomicInteger();

    @Scheduled(initialDelay = 5000, fixedRate = 2000)
    public void tick() {
        Thread thread = Thread.currentThread();
        int sequence = counter.incrementAndGet();

        System.out.println(
                "TICK | count=" + sequence
                + " virtual=" + thread.isVirtual()
                + " daemon=" + thread.isDaemon());
    }
}
~~~

**Giải thích code:**

- **@EnableScheduling** bật cơ chế nhận diện @Scheduled của Spring.
- **WebApplicationType.NONE** tránh việc có server HTTP tạo các thread giữ tiến trình, giúp demo tập trung vào scheduler.
- Không khai báo **Executor** hoặc **TaskScheduler** tùy chỉnh, để Boot auto-configuration hoạt động theo property virtual thread.
- **ApplicationRunner** đồng bộ thường chạy trên main thread; isVirtual() trả false và isDaemon() trả false trong cách chạy Java thông thường.
- **@Scheduled(initialDelay=5000, fixedRate=2000)** chờ khoảng năm giây trước tick đầu, sau đó lên lịch theo nhịp hai giây.
- Dùng **AtomicInteger** để lưu count một cách an toàn khi callback có khả năng chạy trên nhiều threads.
- **Thread.currentThread().isVirtual()** và **isDaemon()** kiểm tra bằng API thay vì đoán qua tên thread.
- Sau run, main in **MAIN | run returned** và kết thúc. Không có đoạn sleep vô hạn hay thủ thuật Thread tự tạo.

### 8.3. Build

~~~bash
java -version
mvn -q -DskipTests package
~~~

Xác nhận JDK 21+ cho cả **java** và **mvn**. Nếu dùng Maven Wrapper trên Windows:

~~~powershell
.\mvnw.cmd -q -DskipTests package
~~~

### 8.4. Lần A: bật virtual threads, tắt keep-alive

~~~bash
java -jar target/virtual-keepalive-demo-1.0.0.jar \
  --spring.threads.virtual.enabled=true \
  --spring.main.keep-alive=false
~~~

Trong một process demo không có non-daemon threads khác được tạo thêm, thường thấy:

~~~text
RUNNER | virtual=false daemon=false
MAIN | run returned
~~~

Rồi JVM có thể kết thúc trước tick đầu tiên. Nếu vậy **không thấy dòng TICK**, mặc dù @Scheduled đã được đăng ký.

**Đừng khẳng định output tuyệt đối trên mọi IDE, Java agent hoặc deployment.** Một thư viện khác có thể còn non-daemon thread và giữ process sống. Điều cần xác minh là **môi trường production thật** và chính sách lifetime.

### 8.5. Lần B: bật virtual threads và keep-alive

~~~bash
java -jar target/virtual-keepalive-demo-1.0.0.jar \
  --spring.threads.virtual.enabled=true \
  --spring.main.keep-alive=true
~~~

Startup thường in:

~~~text
RUNNER | virtual=false daemon=false
MAIN | run returned
~~~

Nhưng **process tiếp tục sống**. Khi @Scheduled callback chạy với SimpleAsyncTaskScheduler virtual thread của Boot, các dòng kỳ vọng:

~~~text
TICK | count=1 virtual=true daemon=true
TICK | count=2 virtual=true daemon=true
TICK | count=3 virtual=true daemon=true
~~~

Các dòng TICK xuất hiện theo thời gian, không bảo đảm đúng thời điểm tuyệt đối do scheduling latency. Bạn có thể dừng bằng Ctrl+C sau vài chu kỳ.

Điều quan trọng: **main đã trả về, còn scheduler vẫn chạy nhờ lifetime của application được giữ**. Virtual thread vẫn daemon=true; keep-alive không thay đổi bản chất thread.

### 8.6. Lần C: tắt virtual threads

~~~bash
java -jar target/virtual-keepalive-demo-1.0.0.jar \
  --spring.threads.virtual.enabled=false \
  --spring.main.keep-alive=false
~~~

Trong cấu hình mặc định với platform-thread scheduler, Spring Boot có thể dùng ThreadPoolTaskScheduler; các luồng scheduler platform non-daemon thường khiến process vẫn sống để chạy TICK:

~~~text
TICK | count=1 virtual=false daemon=false
~~~

Đây là **kết quả minh họa trong cấu hình mặc định**, không phải quy tắc cho mọi custom scheduler. Nếu có một TaskScheduler custom với daemon factory thì kết quả giữ JVM có thể khác.

### 8.7. Vì sao không dùng spring.task.scheduling.pool.size để chữa early exit?

Khi executor/scheduler thực sự dùng virtual threads, pool settings của ThreadPoolTaskScheduler không tự chuyển virtual threads thành non-daemon. Đổi:

~~~properties
spring.task.scheduling.pool.size=3
~~~

không giải quyết được bản chất daemon lifetime của virtual threads trong SimpleAsyncTaskScheduler. Khi cần lifetime, dùng **spring.main.keep-alive=true**; khi cần giới hạn/tối ưu concurrency, cấu hình đúng scheduler/executor được chọn.

## 9. Khác biệt giữa ứng dụng web, CLI và background worker

### 9.1. Web application

Spring MVC trên Tomcat hoặc một web stack khác có thể sở hữu **non-daemon threads** giữ JVM sống sau khi main trả về. Bật virtual threads không đồng nghĩa mọi web app sẽ thoát ngay.

Tuy vậy, nếu chuyển cùng artifact sang chế độ **non-web**, hoặc một deploy chỉ chạy scheduled task, nguồn non-daemon giữ tiến trình có thể không còn. Đừng dựa vào kết quả từ web deployment để bảo đảm một worker deployment có cùng lifecycle.

### 9.2. CLI/batch job hữu hạn

Một lệnh:

~~~bash
java -jar importer.jar --input=data.csv
~~~

thường cần **xử lý xong -> báo trạng thái -> thoát**. Với kiểu này:

~~~text
run()
  -> gửi các task hữu hạn
  -> Future.get()/join() hoặc chờ kết quả có timeout
  -> ghi output/commit
  -> đóng context
  -> trả exit code theo kết quả
~~~

sẽ phù hợp hơn **keep-alive vô hạn**. Nếu bật keep-alive mà không có đường shutdown rõ, batch pod/CI có thể không bao giờ chuyển trạng thái Completed.

### 9.3. Background service chạy liên tục

Worker/scheduler/consumer chờ công việc mới trong tương lai cần **process sống lâu**. Với Java 21 virtual threads, nên chủ động cấu hình keep-alive, theo dõi heartbeats và có đường shutdown phù hợp khi nhận SIGTERM.

**@Async** với executor trong bộ nhớ không tự có durability hoặc retry sau crash; nếu mất tác vụ là rủi ro nghiệp vụ, cân nhắc Spring Batch, database task table, message broker/outbox hoặc hạ tầng job chuyên dụng.

## 10. Không nhầm readiness với lifetime của process

Spring Boot phát **ApplicationReadyEvent** sau khi application context đã refresh và các runner chạy thành công. Nhưng mốc ready **không cam kết JVM còn tồn tại đủ lâu cho một scheduled tick tương lai**.

~~~text
Startup
   |
   +-- ApplicationStartedEvent
   +-- ApplicationRunner / CommandLineRunner
   +-- ApplicationReadyEvent
   +-- main() trả về
   +-- không còn non-daemon thread
   +-- JVM shutdown
   +-- tick dự kiến ở tương lai không xảy ra
~~~

**@Scheduled** có thể được kích hoạt trước hoặc sau ready tùy initialDelay và thời gian startup. Đừng dùng việc một tick tình cờ chạy trước ready để suy ra lifecycle của process đã an toàn.

Ngay cả khi ApplicationReadyEvent có trong log, cần có **smoke test thực sự theo dõi process tồn tại sau startup**.

## 11. Kiểm thử Java daemon contract bằng JUnit 5

Một unit test nhỏ có thể xác minh daemon property mà không cần Spring context. Trong Maven demo, thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo **src/test/java/com/example/keepalive/VirtualThreadDaemonTest.java**:

~~~java
package com.example.keepalive;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class VirtualThreadDaemonTest {

    @Test
    void virtualThreadCannotBeNonDaemon()
            throws InterruptedException {

        Thread vt = Thread.ofVirtual()
                .name("virtual-test")
                .unstarted(() -> {});

        assertTrue(vt.isVirtual());
        assertTrue(vt.isDaemon());

        assertThrows(IllegalArgumentException.class,
                () -> vt.setDaemon(false));

        vt.start();
        vt.join();
    }

    @Test
    void platformThreadCanBeNonDaemon()
            throws InterruptedException {

        Thread platform = Thread.ofPlatform()
                .daemon(false)
                .unstarted(() -> {});

        assertFalse(platform.isVirtual());
        assertFalse(platform.isDaemon());

        platform.start();
        platform.join();
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Test này kiểm tra hợp đồng Java 21: virtual thread luôn daemon và không thể đổi thành non-daemon. Nó **không kiểm tra Spring Boot keep-alive hoặc việc process production còn sống**.

### 11.1. Vì sao @SpringBootTest đơn giản chưa đủ?

Một test:

~~~java
@SpringBootTest
class ApplicationContextTest {
    @Test
    void contextLoads() {
    }
}
~~~

là **snippet** kiểm tra Spring context load. JUnit/Maven test runner có thread/lifecycle riêng, có thể giữ **test JVM** sống dù một executable JAR standalone sẽ thoát khi main kết thúc.

Vì vậy **contextLoads PASS không đồng nghĩa standalone process lifetime PASS**. Đây là lỗi kiểm thử thường gặp của ứng dụng scheduler-only.

### 11.2. Process-level smoke test mới kiểm tra đúng rủi ro

Hãy kiểm thử như sau:

1. Build executable JAR với JDK 21.
2. Start JAR trong **process riêng**, truyền đúng property virtual/keep-alive.
3. Ghi nhận mốc **MAIN | run returned**.
4. Đợi quá thời gian **initialDelay** cùng khoảng dự phòng scheduling hợp lý.
5. Với keep-alive=true: process phải còn sống và có ít nhất một **TICK**.
6. Gửi SIGTERM/Ctrl+C để yêu cầu dừng bình thường.
7. Đợi quá trình shutdown với timeout; nếu không thoát, coi đó là lỗi cần xử lý.
8. Với keep-alive=false: quan sát liệu process có kết thúc trước tick không; so sánh với config có keep-alive.

Để tự động hóa, một test harness có thể dùng **ProcessBuilder** để tạo child JVM và **Process.isAlive()** để kiểm tra. Ví dụ logic test:

~~~java
Process process = new ProcessBuilder(
        "java",
        "-jar",
        "target/virtual-keepalive-demo-1.0.0.jar",
        "--spring.threads.virtual.enabled=true",
        "--spring.main.keep-alive=true"
).inheritIO().start();

try {
    // Trong test thật: chờ điều kiện TICK bằng log/health signal
    // với deadline, không chỉ sleep một thời gian cố định.
    if (!process.isAlive()) {
        throw new AssertionError("Application exited too early");
    }
} finally {
    process.destroy();
    if (!process.waitFor(10, java.util.concurrent.TimeUnit.SECONDS)) {
        process.destroyForcibly();
    }
}
~~~

Đoạn trên **chỉ là skeleton**, cần có method/test wrapper khai báo **throws Exception**, bảo đảm JAR đã build và hoàn thiện phần chờ signal TICK trước khi dùng làm kiểm thử chính thức. Nó minh họa cách **quan sát một process độc lập và cleanup**, không phải JUnit test đầy đủ. Đừng chạy process child rồi bỏ quên trong CI.

### 11.3. Đừng kiểm tra bằng thread name đơn thuần

Trong callback @Scheduled:

~~~java
Thread t = Thread.currentThread();
System.out.println(
        "virtual=" + t.isVirtual()
        + " daemon=" + t.isDaemon()
        + " name=" + t.getName());
~~~

Các method **isVirtual()** và **isDaemon()** phản ánh API thật. Một thread có tên **virtual-worker** vẫn có thể là platform thread được đặt tên tùy ý; tên không phải bằng chứng.

Tuy nhiên, callback chạy trên virtual thread **không chứng minh JVM không có non-daemon thread khác**. Lifetime phải được kiểm chứng ở cấp process.

## 12. Shutdown và dữ liệu công việc khi có keep-alive

Giữ JVM sống là cần thiết cho service nền, nhưng không bảo đảm công việc hoàn tất nếu bị dừng bất ngờ.

~~~text
SIGTERM / Ctrl+C
     |
     +-- SpringApplication shutdown hook
     +-- ApplicationContext close
     +-- ContextClosedEvent / SmartLifecycle stop
     +-- scheduler/executor ngừng nhận task
     +-- destruction callbacks như @PreDestroy
     +-- process kết thúc
~~~

Thứ tự chi tiết phụ thuộc Spring lifecycle phases và dependency graph. **@PreDestroy không được bảo đảm chạy khi SIGKILL hoặc process crash**.

Đối với công việc có giá trị nghiệp vụ:

- Ghi state/checkpoint bền vững trước khi báo hoàn tất.
- Chống duplicate bằng idempotence.
- Có chính sách retry, timeout, dead-letter hoặc compensation thích hợp.
- Dừng nhận job mới trước khi drain job đang chạy.
- Dùng **termination grace period** phù hợp khi chạy container.
- Không giữ một task vô hạn trong shutdown chỉ để chờ kết quả không đến.

**spring.main.keep-alive** không thay thế được bất kỳ cơ chế nào trong số đó.

### 12.1. SIGTERM và SIGKILL khác nhau

SIGTERM cho ứng dụng cơ hội shutdown bình thường. SIGKILL, mất nguồn hoặc node crash không cho JVM cơ hội chạy toàn bộ cleanup. Nếu container orchestrator gửi SIGKILL sau thời gian grace, in-memory virtual-thread work có thể bị dừng giữa chừng.

Cần dựa vào hệ thống job durable cho những task không được phép mất, không dựa vào daemon flag hoặc keep-alive property.

### 12.2. Đừng bắt lỗi rồi thông báo thành công giả

Nếu async task lỗi, việc JVM vẫn sống không có nghĩa task đã thành công. Theo dõi future/exception và công bố metrics phù hợp; với job bắt buộc, báo status thất bại thật.

Ngược lại, nếu process tự thoát sớm mà log không có stack trace, đừng kết luận cấu hình bị lỗi Spring: cần phân biệt **normal JVM shutdown vì không còn non-daemon threads** với BeanCreationException, OOM, SIGTERM hay System.exit.

## 13. Những lỗi hiểu nhầm thường gặp

### 13.1. “Virtual threads được chạy trên carrier platform thread nên vẫn giữ JVM sống”

Sai. Java không cung cấp cam kết keeper qua carrier threads; virtual thread luôn daemon. Kiểm tra non-daemon threads thực tế hoặc dùng keep-alive đúng mục đích.

### 13.2. “Có @Scheduled bean thì scheduler tự giữ process”

Không nhất thiết. Trong Java 21 virtual-thread mode, scheduler có thể chỉ để lại daemon threads. Không coi annotation là hợp đồng process lifetime.

### 13.3. “Bật virtual threads đồng thời bật keep-alive”

Sai. Hai property độc lập. Khi cần ứng dụng nền chạy liên tục, khai báo tường minh **spring.main.keep-alive=true**.

### 13.4. “Có thể đổi virtual thread thành non-daemon”

Sai. Java 21 Thread API cấm và **setDaemon(false)** ném IllegalArgumentException.

### 13.5. “main trả về nghĩa context.close đã chạy”

Không nhất thiết. main và ApplicationContext có vòng đời khác nhau. JVM chỉ bắt đầu shutdown khi điều kiện thread và cơ chế shutdown khác thỏa. Việc tự gọi context.close() là hành động riêng.

### 13.6. “Ứng dụng web chạy ổn nên background-only deployment sẽ ổn”

Không đủ căn cứ. Web server có thể có non-daemon threads; ứng dụng non-web không có nguồn đó. Phải test riêng workload profile.

### 13.7. “@SpringBootTest xanh chứng minh standalone scheduler không thoát”

Sai. Test runner có non-daemon threads riêng. Cần **process-level** smoke test.

### 13.8. “Chỉ cần tăng pool size khi dùng virtual threads”

Sai. Scheduler/executor virtual không có semantics pool giống platform pool. Pool size không sửa daemon lifetime; limit concurrency phải áp dụng theo nguồn lực downstream.

### 13.9. “Bật keep-alive bảo đảm mọi job chạy xong trước SIGKILL”

Sai. Keep-alive chỉ giữ process trong điều kiện bình thường, không tạo durable guarantee.

### 13.10. “Ứng dụng CLI finite nên bật keep-alive để khỏi mất job”

Chưa chắc. Nếu CLI có một công việc hữu hạn, nên **await completion** rồi thoát; bật keep-alive vô hạn có thể khiến job pod/CI treo.

### 13.11. “Tạo một non-daemon Thread chờ vô hạn là giải pháp tốt”

Không nên. Nó thiếu lifecycle integration, dễ làm process không dừng khi context đóng. Spring Boot cung cấp **spring.main.keep-alive** phù hợp hơn cho ứng dụng nền dài hạn.

### 13.12. “Chỉ cần log Started Application là biết scheduled job chạy”

Sai. Startup và tick lịch là hai mốc khác. Cần metrics/log/job state xác minh callback thực sự được thực thi.

### 13.13. “Keep-alive ngăn được System.exit hoặc đóng context”

Sai. Keep-alive không phải cơ chế chống yêu cầu kết thúc chủ động; phải thiết kế đúng shutdown path và task completion.

## 14. Chiến lược vận hành an toàn

### 14.1. Xác định rõ workload

| Loại ứng dụng | Chính sách nên cân nhắc |
| --- | --- |
| Web service với server nhúng | Kiểm tra server lifetime, virtual-thread support và shutdown; có thể bật keep-alive để rõ policy |
| Background scheduler-only | **Bật keep-alive**, kiểm tra tick sau startup |
| Consumer chạy dài hạn | Quản lý lifecycle + keep-alive nếu chỉ còn virtual/daemon threads |
| One-shot CLI/batch job | Chờ Future/join, trả exit status, kết thúc có chủ đích |
| Multi-replica scheduled jobs | Ngoài keep-alive còn cần coordination/lock hoặc idempotence |

### 14.2. Quan sát các tín hiệu quan trọng

Nên biết:

- Process có còn **alive** sau main và sau initialDelay không.
- @Scheduled đã chạy lần gần nhất khi nào.
- Số job thành công/thất bại, thời lượng và deadline.
- Loại thread thực thi qua **isVirtual()/isDaemon()**.
- Executor/scheduler có bị override bằng bean custom không.
- Có error hoặc exit code bất thường không.
- Shutdown có đúng thời hạn không.
- Có task chưa commit hoặc cần retry sau restart không.

Không chỉ dựa vào thread name hoặc startup log. Khi cần debug sâu, có thể dùng **jcmd**, thread dump hoặc JDK Flight Recorder phù hợp với JDK 21, nhưng phải bảo đảm có process đang sống để thu thập dữ liệu.

### 14.3. Virtual threads không làm I/O hay CPU nhanh hơn một cách thần kỳ

Virtual threads có thể tăng concurrency hiệu quả cho workload chờ I/O; chúng không làm một phép tính CPU nặng chạy nhanh hơn. Nếu có hàng triệu virtual tasks cùng truy cập một database có connection pool 20, bottleneck vẫn nằm ở DB/pool.

Java 21 cũng có các vấn đề pinning trong một số tình huống synchronized/native blocking; cần đo throughput thực tế và giới hạn downstream. Những mối quan tâm này **khác vấn đề daemon/early exit**, nhưng có thể cùng xuất hiện khi chuyển ứng dụng sang virtual threads.

## 15. Checklist trước khi deploy

- [ ] Runtime thật sự là **Java 21+**, Maven/compiler cũng dùng JDK phù hợp.
- [ ] Phiên bản Spring Boot hỗ trợ hai property virtual và keep-alive.
- [ ] Xác nhận **spring.threads.virtual.enabled=true** ở deployment cần dùng.
- [ ] Phân biệt **service dài hạn** với **batch job hữu hạn**.
- [ ] Với non-web long-running service, bật **spring.main.keep-alive=true**.
- [ ] Không dựa vào virtual thread để giữ JVM hoạt động.
- [ ] Không gọi setDaemon(false) trên virtual thread.
- [ ] Có @EnableScheduling và scheduled bean được quản lý đúng cách.
- [ ] Kiểm tra auto-configured hoặc custom TaskScheduler thực tế.
- [ ] Không dựa vào platform pool settings cũ để giới hạn virtual concurrency.
- [ ] Test JDK isDaemon/isVirtual và test process lifetime riêng.
- [ ] Khởi động executable JAR độc lập và đợi đến sau scheduled initialDelay.
- [ ] Quan sát ít nhất một tick theo lịch trong process vẫn còn sống.
- [ ] Test shutdown bằng SIGTERM/Ctrl+C với timeout.
- [ ] Không bỏ quên child process trong CI.
- [ ] Job quan trọng có checkpoint, retry và idempotence.
- [ ] Với nhiều replicas, có cách tránh chạy trùng khi nghiệp vụ yêu cầu.
- [ ] CLI hữu hạn chờ completion rồi kết thúc, không giữ process vô hạn.
- [ ] Không suy luận thành công của job từ ApplicationReadyEvent.
- [ ] Logging và metrics thể hiện job thực sự chạy và trạng thái của nó.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Trên Java 21, virtual thread có thể là non-daemon không?

**Đáp án:** Không. Virtual thread luôn daemon; gọi setDaemon(false) không hợp lệ.

**Câu 2.** JVM bắt đầu shutdown thông thường khi nào?

**Đáp án:** Khi mọi non-daemon thread đã start đều đã kết thúc; daemon threads còn hoạt động không ngăn JVM bắt đầu shutdown.

**Câu 3.** Một @Scheduled-only app bật virtual threads có thể tự thoát ngay sau startup không?

**Đáp án:** Có, nếu không còn non-daemon thread nào khác giữ JVM sống và không dùng keep-alive.

**Câu 4.** Thuộc tính Spring Boot nào giúp xử lý rủi ro này?

**Đáp án:** **spring.main.keep-alive=true**.

**Câu 5.** spring.threads.virtual.enabled=true có thay thế keep-alive không?

**Đáp án:** Không. Nó lựa chọn cơ chế virtual-thread execution, không bảo đảm JVM sống lâu.

**Câu 6.** Vì sao Thread.join() giúp one-shot virtual task hoàn tất?

**Đáp án:** Main non-daemon chờ task kết thúc, nên JVM chưa bước vào shutdown vì main còn sống.

**Câu 7.** Một web app có non-daemon server thread chắc chắn tự thoát vì virtual threads không?

**Đáp án:** Không. Non-daemon server threads có thể giữ JVM sống.

**Câu 8.** @SpringBootTest contextLoads có đủ chứng minh tiến trình non-web sẽ sống qua giờ scheduled trigger không?

**Đáp án:** Không. Test JVM có lifecycle/threads riêng. Cần process-level smoke test.

**Câu 9.** Keep-alive có bảo đảm task không mất khi SIGKILL không?

**Đáp án:** Không. Cần persistence, checkpoint/retry hoặc job infrastructure.

**Câu 10.** Vì sao spring.task.scheduling.pool.size không giải quyết daemon status của virtual threads?

**Đáp án:** SimpleAsyncTaskScheduler dùng mô hình virtual threads khác pool platform; pool-size setting không đổi daemon semantics.

**Câu 11.** Khi ứng dụng CLI hoàn thành một task hữu hạn, có nên bật keep-alive để process không bao giờ thoát không?

**Đáp án:** Thông thường không; chờ Future/join, báo trạng thái rồi đóng context và kết thúc.

**Câu 12.** Nhiều replicas dùng @Scheduled, keep-alive có bảo đảm chỉ một job chạy trên toàn cụm không?

**Đáp án:** Không. Keep-alive quản lý mỗi JVM riêng; điều phối job phân tán là vấn đề khác.

## 17. Kết luận

**Virtual threads luôn là daemon trong Java 21.** Chúng có thể chạy nhiều tác vụ I/O hiệu quả, nhưng **không giữ JVM sống** sau khi tất cả non-daemon threads kết thúc. Vì thế một ứng dụng Spring Boot non-web chỉ dựa vào scheduler hoặc background virtual tasks có thể thoát sớm sau startup, trước khi scheduled job đến giờ.

Với **long-running background service**, dùng:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Với **batch job hữu hạn**, chờ kết quả bằng Future/join và kết thúc có chủ đích. Đừng đánh đồng giữ process sống với bảo đảm job hoàn tất hoặc giao nhận bền vững. Hãy test bằng executable process độc lập, kiểm tra tick sau initialDelay và bảo đảm shutdown/recovery có giới hạn, có thể quan sát.

## 18. Tài liệu tham khảo chính thức

- Spring Boot 3.3.13 — Virtual Threads, daemon và keep-alive: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Java SE 21 — Thread API (isDaemon, isVirtual, setDaemon): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html
- Oracle Java 21 — Virtual Threads: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- OpenJDK JEP 444 — Virtual Threads: https://openjdk.org/jeps/444
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html