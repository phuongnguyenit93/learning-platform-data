# Giữ JVM hoạt động bằng spring.main.keep-alive

## 1. Vấn đề: ứng dụng đã “Started” nhưng JVM tự kết thúc

Trong các ứng dụng **Spring Boot 3.3.x** sử dụng **Java 21+ và virtual threads (luồng ảo)**, một tình huống gây nhầm lẫn là chương trình khởi động thành công, `ApplicationContext` đã refresh, thậm chí có bean `@Scheduled`, nhưng tiến trình Java lại **kết thúc ngay sau khi `main` trả về**. Đây có thể không phải exception hay lỗi khởi tạo Spring.

Để hiểu nguyên nhân, phải phân biệt:

1. **Spring Boot khởi động thành công:** Container đã khởi tạo, các runner đã hoàn tất và `SpringApplication.run(...)` trả về một `ApplicationContext`.
2. **Có background work được lập lịch:** `@Scheduled` hoặc executor có thể đang chờ tới kỳ chạy tiếp theo.
3. **JVM còn lý do để tiếp tục chạy:** Theo quy tắc JVM, một tiến trình Java thông thường có thể kết thúc khi chỉ còn **daemon threads**; chúng **không giữ JVM sống**.
4. **Spring Boot được yêu cầu duy trì JVM:** `spring.main.keep-alive=true` tạo cơ chế để JVM tiếp tục tồn tại ngay cả khi những thread còn lại đều là daemon, ví dụ tất cả là virtual threads.

Trong Java 21, **virtual threads luôn là daemon threads**. Bởi vậy khi ứng dụng chỉ trông vào scheduler hoặc các task được chạy bằng virtual threads để duy trì tiến trình, việc `SpringApplication.run(...)` trả về có thể khiến JVM kết thúc trước kỳ scheduled task tiếp theo.

Giải pháp mà tài liệu chính thức Spring Boot 3.3 khuyến nghị:

```properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
```

**Giới hạn rất quan trọng:** `spring.main.keep-alive` không có nghĩa “giữ mọi tác vụ sống cho tới khi hoàn thành” và không biến daemon virtual thread thành non-daemon. Nó chỉ giải quyết **điều kiện tồn tại của JVM** trong trường hợp không còn non-daemon threads khác. Tác vụ vẫn có thể thất bại, bị hủy, treo, hoặc chưa được lập lịch như dự kiến.

Bài này giải thích cơ chế JVM, cấu hình Spring Boot, khi nào cần dùng, ví dụ Java 21+ chạy được, cách kiểm tra và các ngộ nhận dễ gặp. Nội dung được đối chiếu theo **Spring Boot 3.3.13 / Spring Framework 6.1.x**; không lấy default hoặc cú pháp của Boot major version mới hơn làm mặc định cho Boot 3.3.

## 2. Daemon thread, platform thread và virtual thread

### 2.1. JVM tự kết thúc khi nào?

Trong mô hình Java thông thường, JVM có thể bắt đầu trình tự shutdown khi **tất cả những thread còn sống đều là daemon**. Non-daemon thread đang sống là một lý do khiến JVM tiếp tục chạy; daemon thread **không ngăn** quá trình shutdown bắt đầu.

Một cách hình dung:

```text
JVM đang chạy
    |
    +--> main thread: platform, non-daemon
    |
    +--> background virtual thread: daemon
    |
    +--> scheduler/task virtual threads: daemon
    |
    +--> main() hoàn tất, các non-daemon thread khác không còn
           |
           +--> Chỉ còn daemon threads
           |
           +--> JVM có thể bắt đầu shutdown
           |
           +--> Các virtual threads chưa hoàn thành có thể bị dừng
```

Quy tắc trên **không phụ thuộc** việc Spring bean đã được khởi tạo hoặc `@Scheduled` có đăng ký thành công hay chưa. Java không “đếm các job đang chờ” để quyết định tồn tại của JVM; JVM xét các thread theo ngữ nghĩa daemon/non-daemon và các cơ chế shutdown.

### 2.2. Virtual threads của Java 21 luôn daemon

Java 21 cung cấp virtual threads như những instance `Thread` được JVM triển khai theo mô hình lightweight thread. Chúng phù hợp với workload có rất nhiều tác vụ chờ I/O, nhưng có hai điểm không nên nhầm:

- Virtual thread **vẫn là thread** theo API Java, nhưng khác về cách scheduling so với platform thread thông thường.
- Virtual thread **luôn là daemon thread**, không có tùy chọn đổi thành non-daemon. Không thể dùng `setDaemon(false)` để biến một virtual thread thành công cụ giữ JVM sống.

Ngay cả khi thread `isAlive()` là true, nếu nó là daemon thì bản thân nó vẫn **không giữ tiến trình tồn tại** sau khi tất cả non-daemon threads đã kết thúc.

### 2.3. Chương trình Java 21 độc lập xác nhận tính chất daemon

Tạo file **`VirtualThreadDaemonFact.java`** (không phụ thuộc Spring):

```java
public class VirtualThreadDaemonFact {
    public static void main(String[] args) throws InterruptedException {
        Thread virtual = Thread.startVirtualThread(() -> {
            Thread t = Thread.currentThread();
            System.out.println("virtual=" + t.isVirtual());
            System.out.println("daemon=" + t.isDaemon());
        });

        virtual.join(); // Chỉ đợi in xong để stdout ổn định.
    }
}
```

Biên dịch/chạy bằng **JDK 21+**:

```bash
javac VirtualThreadDaemonFact.java
java VirtualThreadDaemonFact
```

Stdout chính xác:

```text
virtual=true
daemon=true
```

`join()` trong ví dụ **không làm virtual thread hết daemon**. Nó chỉ giữ **main thread non-daemon** chờ tới khi virtual thread in xong, cho nên chương trình có output đáng tin. Nếu không có `join()` và main kết thúc quá sớm, không được bảo đảm virtual thread kịp in ra.

Đây chính là ranh giới cần hiểu trước khi dùng `spring.main.keep-alive`: không có một Java API nào mặc định buộc JVM chờ tất cả virtual threads hoàn thành khi main đã hết việc.

## 3. Spring Boot 3.3 có những cấu hình nào liên quan?

| Thuộc tính / API | Ý nghĩa | Điều không nên suy ra |
| --- | --- | --- |
| `spring.threads.virtual.enabled=true` | Cho phép các integration được Boot hỗ trợ sử dụng virtual threads trên Java 21+ | Không làm tất cả thư viện/đoạn `new Thread(...)` tự động chuyển sang virtual |
| **`spring.main.keep-alive=true`** | Giữ JVM tiếp tục chạy dù không còn non-daemon threads khác | Không bắt mọi background task hoàn tất và không bảo đảm không crash |
| `spring.main.keep-alive=false` | **Mặc định** của Boot 3.3 | Không bắt JVM phải thoát; một non-daemon thread khác vẫn có thể giữ JVM sống |
| `SpringApplication.setKeepAlive(boolean)` | Cấu hình hành vi keep-alive qua Java bootstrap API, có từ Boot 3.2 | Không thay đổi daemon flag của virtual threads |
| `@EnableScheduling` | Cho Spring phát hiện, đăng ký các method `@Scheduled` | Không tự bảo đảm process sống nếu chỉ còn daemon threads |
| `@Scheduled` | Lên lịch chạy method theo fixed rate/delay/cron | Không tạo quy tắc JVM “phải chờ tới tất cả kỳ chạy” |
| `spring.task.scheduling.pool.size` | Tuning scheduler dùng pool-based implementation | Không có hiệu lực tương tự với virtual-thread scheduler `SimpleAsyncTaskScheduler` |
| `spring.task.execution.pool.keep-alive` | Điều chỉnh thời gian nhàn rỗi của pool worker khi dùng pool-based executor | **Không phải** `spring.main.keep-alive` và không giữ toàn JVM sống |
| `server.tomcat.keep-alive-timeout` | Thời gian HTTP keep-alive trên connector Tomcat | Không liên quan vấn đề JVM thoát khi chỉ còn daemon threads |

Hai property cần phối hợp:

```properties
# Tự động sử dụng virtual threads ở các integration Boot 3.3 hỗ trợ.
spring.threads.virtual.enabled=true

# Bảo đảm JVM không tự thoát chỉ vì không còn non-daemon threads.
spring.main.keep-alive=true
```

Trong Boot 3.3.x, `spring.main.keep-alive` là **boolean**, giá trị **mặc định false**. Có thể đặt trong `application.properties`, `application.yml` hoặc nguồn cấu hình Boot hỗ trợ. Nếu thay bằng command-line option, cần xét precedence của externalized configuration.

**Yêu cầu phiên bản:** `spring.threads.virtual.enabled=true` chỉ có ý nghĩa khi chạy Java 21 hoặc mới hơn. Spring Boot 3.3 hỗ trợ Java 17 làm baseline, nhưng **Java 17 không có virtual threads API chính thức** để chạy bài học này. Vì thế ví dụ phía dưới yêu cầu **JDK 21**, không dùng Java 17 rồi chỉ bật property.

### 3.1. Spring Boot đã giải quyết được gì từ phiên bản nào?

`SpringApplication.setKeepAlive(boolean)` và property `spring.main.keep-alive` có mặt từ **Spring Boot 3.2**. Đây không phải cú pháp vừa được đưa vào Boot 4. Tài liệu Boot 3.3.13 tiếp tục khuyến nghị bật nó cho ứng dụng virtual-thread để tránh JVM thoát do thiếu non-daemon threads.

### 3.2. Có phải bắt buộc enable virtual threads thì keep-alive mới hoạt động?

**Không.** Hợp đồng của `spring.main.keep-alive=true` là giữ JVM sống khi không còn non-daemon threads; virtual thread chỉ là một **trường hợp quan trọng** vì chúng luôn daemon. Một ứng dụng non-web chỉ có daemon thread tự tạo cũng có thể gặp vấn đề tương tự.

Ngược lại, nếu ứng dụng dùng **platform non-daemon threads** do server/executor khác đang duy trì, JVM có thể vẫn chạy dù `spring.main.keep-alive=false`. Đó là lý do không thể nhìn tiến trình đang sống để kết luận property đã được áp dụng.

## 4. @Scheduled và virtual threads: vì sao scheduler không giữ tiến trình?

Spring Boot 3.3 có thể tự cấu hình scheduler khi ứng dụng dùng `@EnableScheduling`. Với Java 21+ và `spring.threads.virtual.enabled=true`, scheduler tự cấu hình là **`SimpleAsyncTaskScheduler` dùng virtual threads**, thay vì scheduler pool-based mặc định khi virtual threads không được bật.

Thí dụ một bean:

```java
@Component
class CleanupTick {
    @Scheduled(initialDelay = 1000L, fixedRate = 1000L)
    void run() {
        System.out.println("periodic cleanup");
    }
}
```

Đây là **đoạn minh họa**, cần `@EnableScheduling`, các import và Spring application hợp lệ. Khi context refresh, method được đăng ký để chạy ở các thời điểm thích hợp. Nhưng:

- “Method đã được scheduled” chỉ nói scheduler biết lịch.
- “Method sẽ có lúc được gọi” phụ thuộc tiến trình JVM **còn tồn tại** và scheduler còn hoạt động.
- Khi `spring.main.keep-alive=false`, nếu không còn non-daemon thread, JVM có thể kết thúc trước lần scheduled tiếp theo.
- Khi `spring.main.keep-alive=true`, Boot giữ JVM sống để scheduler có điều kiện tiếp tục tạo và thực thi các tick theo lịch, **không tự bảo đảm mỗi tick thành công**.

### 4.1. fixedRate, fixedDelay và SimpleAsyncTaskScheduler

Spring Framework 6.1 `SimpleAsyncTaskScheduler` được thiết kế phù hợp với virtual threads: nó có một luồng điều phối và thường khởi chạy từng lần thực thi định kỳ trên một thread riêng.

Cần đặc biệt lưu ý:

- **`fixedRate` hoặc cron:** thích hợp hơn với cơ chế virtual-thread-per-task mà Spring Framework khuyến nghị.
- **`fixedDelay`:** trên `SimpleAsyncTaskScheduler`, các tác vụ fixed-delay chạy trên **một scheduler thread**, không theo mô hình “mỗi lần chạy tạo một virtual thread riêng” giống fixed-rate/cron. Vì vậy việc dùng fixed-delay cho tác vụ blocking có thể làm nghẽn scheduler.
- Pool settings như `spring.task.scheduling.pool.size` **không có tác dụng như khi dùng ThreadPoolTaskScheduler** trong virtual-thread mode.

Ví dụ minh họa:

```java
@Scheduled(fixedRate = 5000)
public void poll() {
    // Mỗi 5 giây thử khởi tạo một lần chạy theo fixed-rate semantics.
}
```

Đây là đoạn method minh họa; execution thực tế vẫn tùy scheduler, tải hệ thống và xử lý trùng lặp. **fixedRate không bảo đảm một tác vụ trước đã hoàn tất trước khi tác vụ sau bắt đầu**. Nếu không cho phép overlap, phải kiểm soát concurrency hoặc dùng cơ chế thiết kế phù hợp, không chỉ chọn fixedRate để tận dụng virtual thread.

### 4.2. @Async cũng có ranh giới tương tự

`@Async` thường gửi việc vào executor rồi return cho caller theo contract bất đồng bộ. Nếu một `ApplicationRunner` gọi `@Async` rồi trả về ngay, Boot có thể phát `ApplicationReadyEvent` trong khi công việc vẫn chạy. Bật `spring.main.keep-alive` không thay đổi ranh giới này: nó chỉ ngăn JVM tự thoát vì thiếu non-daemon threads, **không đợi Future** và không biến async failure thành startup failure.

Công việc bắt buộc trước readiness phải có cơ chế await/timeout hoặc readiness gate được thiết kế riêng.


## 5. Ví dụ chạy được: Spring Boot 3.3.13 + Java 21 + @Scheduled

Ví dụ sử dụng ứng dụng **non-web** để loại ảnh hưởng của embedded Tomcat/Netty và quan sát riêng cơ chế giữ JVM sống. Khi bật `spring.main.keep-alive=true`, chương trình sẽ tiếp tục chạy sau khi `main` đã in thông báo hoàn tất, đồng thời có các tick được lên lịch. Khi tắt keep-alive, nếu không còn non-daemon thread khác, JVM thường kết thúc mà không đợi các tick trong tương lai.

### 5.1. Tạo dự án Gradle

Tạo một project Gradle Groovy có **Gradle Wrapper tương thích JDK 21** và các file sau. Dùng **Java toolchain 21** chứ không phải 17.

File **`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

File **`settings.gradle`**:

```groovy
rootProject.name = 'keepalive-virtual-lab'
```

File **`src/main/resources/application.properties`**:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR

spring.threads.virtual.enabled=true
spring.main.keep-alive=true
```

Đây là non-web application: không có HTTP listener tạo ra một non-daemon thread khác ngoài ý muốn. Thí nghiệm tập trung vào scheduler tự cấu hình khi bật virtual threads.

### 5.2. Viết Java trong đúng package/file

Tạo file **`src/main/java/com/example/keepalive/KeepAliveVirtualApplication.java`**:

```java
package com.example.keepalive;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableScheduling
public class KeepAliveVirtualApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(KeepAliveVirtualApplication.class, args);

        System.out.println("MAIN: run returned; active=" + context.isActive());
        // Không tự close context: muốn quan sát Boot giữ JVM sống.
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("READY: Spring Boot startup completed");
    }

    @Component
    public static class TickJob {

        private final AtomicInteger count = new AtomicInteger();

        @Scheduled(initialDelay = 1500L, fixedRate = 1000L)
        public void tick() {
            Thread current = Thread.currentThread();
            System.out.println(
                    "TICK " + count.incrementAndGet()
                            + ": virtual=" + current.isVirtual()
                            + ", daemon=" + current.isDaemon());
        }

        @PreDestroy
        public void onDestroy() {
            System.out.println("STOP: bean destruction callback");
        }
    }
}
```

Code ở trên là **một chương trình Spring Boot hoàn chỉnh trong một file Java**. Package, class name, starter và annotation import nhất quán.

**Giải thích từng chi tiết:**

1. `@SpringBootApplication` tạo application context theo cấu hình. `@EnableScheduling` kích hoạt phát hiện các `@Scheduled` methods.
2. `spring.main.web-application-type=none` làm rõ đây không phải web server; việc process tiếp tục tồn tại không được giải thích bằng HTTP connector.
3. `spring.threads.virtual.enabled=true` yêu cầu Boot tự cấu hình task scheduler phù hợp virtual threads trên Java 21.
4. `spring.main.keep-alive=true` yêu cầu Boot giữ JVM tiếp tục chạy kể cả khi không còn non-daemon threads do các thành phần khác cung cấp.
5. Method `tick()` in `Thread.currentThread().isVirtual()` và `isDaemon()`. Với scheduler virtual auto-configured trong cấu hình mẫu, kỳ chạy fixed-rate được thực hiện trên virtual thread, nên thường thấy `virtual=true, daemon=true`.
6. `initialDelay=1500L` làm lần chạy đầu có độ trễ sau khi scheduling được đăng ký; `fixedRate=1000L` chỉ định chu kỳ ước muốn giữa các lần khởi chạy. Thời gian tick thực tế phụ thuộc tải và scheduler.
7. `@EventListener(ApplicationReadyEvent)` đánh dấu mốc startup hoàn tất. `SpringApplication.run(...)` trả về sau khi chạy runner và ready path bình thường.
8. `main` in `context.isActive()` rồi **không đóng context**. Đó là lựa chọn có chủ đích để quan sát keep-alive; nếu dùng `try-with-resources` đóng context ngay, scheduled bean sẽ bị dừng nên không còn thí nghiệm giữ ứng dụng chạy.
9. `@PreDestroy` minh họa shutdown callback khi context được đóng có kiểm soát. Không dùng nó làm bằng chứng callback luôn chạy trong SIGKILL/crash.

### 5.3. Lệnh build và chạy

Windows PowerShell:

```powershell
.\gradlew.bat bootJar
java -jar build/libs/keepalive-virtual-lab-0.0.1-SNAPSHOT.jar
```

macOS/Linux:

```bash
./gradlew bootJar
java -jar build/libs/keepalive-virtual-lab-0.0.1-SNAPSHOT.jar
```

Hãy chạy bằng **JDK 21+**. Nếu terminal có nhiều phiên bản JDK, kiểm tra `java -version`, `javac -version` và Gradle toolchain.

Một **mẫu output minh họa** khi chạy ổn định (số lần tick và vị trí log theo thời gian có thể khác):

```text
READY: Spring Boot startup completed
MAIN: run returned; active=true
TICK 1: virtual=true, daemon=true
TICK 2: virtual=true, daemon=true
TICK 3: virtual=true, daemon=true
...
```

**Đây không phải lời hứa thứ tự tuyệt đối giữa dòng MAIN và tick đầu**. `@Scheduled` có lịch riêng; nếu startup bị chậm, một tick có thể xuất hiện sớm hơn dòng MAIN. Điều cần quan sát là **sau khi `main` return, tiến trình vẫn còn và các tick tương lai tiếp tục xuất hiện** nhờ keep-alive.

Khi cần dừng, gửi tín hiệu dừng có kiểm soát theo cách vận hành phù hợp, ví dụ Ctrl+C trong terminal trực tiếp, hoặc SIGTERM trong container. Trong đường shutdown bình thường, bean có cơ hội chạy `@PreDestroy`. Không dựa vào callback nếu bị kill cưỡng bức.

### 5.4. Lần chạy đối chứng: tắt keep-alive

Không sửa Java, chỉ override property ở command line:

```bash
java -jar build/libs/keepalive-virtual-lab-0.0.1-SNAPSHOT.jar --spring.main.keep-alive=false
```

Trong môi trường chỉ có các daemon/virtual background threads sau khi main kết thúc, JVM **có thể và thường sẽ kết thúc** thay vì ở lại chờ scheduler. Có thể thấy `READY` và `MAIN`, nhưng không có các tick tiếp theo hoặc số tick ít hơn vì process không còn tồn tại.

**Không khẳng định stdout chính xác một số dòng cho lần keep-alive=false**: tốc độ startup, thời gian tick đầu, thread khác do agent/library/launcher tạo và khả năng shutdown là yếu tố quan trọng. Khi false, property **không ép JVM thoát**; nó đơn giản không còn tạo lý do keep-alive từ SpringApplication. Nếu một non-daemon thread khác đang sống, process vẫn có thể tiếp tục.

### 5.5. Đối chứng thứ hai: tắt virtual threads nhưng giữ keep-alive

Chạy:

```bash
java -jar build/libs/keepalive-virtual-lab-0.0.1-SNAPSHOT.jar --spring.threads.virtual.enabled=false --spring.main.keep-alive=true
```

Khi virtual threads tắt, auto-configured scheduler mặc định thường là `ThreadPoolTaskScheduler` dùng platform threads. `Thread.currentThread().isVirtual()` trong tick sẽ là `false` nếu không có scheduler tùy biến. Dù vậy `spring.main.keep-alive=true` vẫn có hiệu lực vì nó là thuộc tính cấp `SpringApplication`, không phụ thuộc vào việc có virtual threads hay không.

Sự khác biệt giúp kiểm tra hai trục **độc lập**:

- `spring.threads.virtual.enabled` quyết định kiểu thực thi của những integration được Boot auto-configure.
- `spring.main.keep-alive` quyết định ứng dụng có yêu cầu giữ JVM sống khi không còn non-daemon threads khác.

### 5.6. Giữ JVM sống không bảo đảm job chạy thành công

Ngay cả khi tick liên tục in `virtual=true`, trong method bạn có thể gọi API ngoài, gặp exception hoặc timeout. Property `spring.main.keep-alive` không retry task, không chờ batch trước, không tự tạo error handler, không kiểm tra idempotency và không xác nhận business result.

Bài kiểm tra nên ghi nhận cả **tình trạng process** và **kết quả tác vụ** thay vì chỉ một trong hai.


## 6. Cấu hình bằng Java thay cho application.properties

Spring Boot 3.3 có API công khai `SpringApplication.setKeepAlive(boolean)`:

```java
public static void main(String[] args) {
    SpringApplication application =
            new SpringApplication(KeepAliveVirtualApplication.class);
    application.setKeepAlive(true);
    application.run(args);
}
```

Đây là **một phiên bản minh họa để thay main hiện tại**, không dán cùng main cũ trong file. Cần import `org.springframework.boot.SpringApplication` và class application thật. `setKeepAlive(true)` có cùng mục tiêu: giữ JVM sống khi không còn non-daemon threads.

Trong các ứng dụng có cấu hình externalized rõ, thường **ưu tiên property** vì dễ thay đổi theo môi trường và triển khai. Nếu cấu hình cả qua API lẫn properties/arguments, hãy kiểm tra lại cấu hình hiệu lực thay vì đoán precedence trong mọi bootstrap custom.

### 6.1. application.yml tương đương

```yaml
spring:
  main:
    keep-alive: true
  threads:
    virtual:
      enabled: true
```

Đây là **một lựa chọn thay thế** `application.properties`, không cần dùng đồng thời cả hai nếu không có chủ đích. Property names đúng là `spring.main.keep-alive` và `spring.threads.virtual.enabled`.

### 6.2. Biến môi trường và command line

Trong hệ thống triển khai có externalized configuration, property có thể được cấu hình qua environment hoặc argument:

```text
SPRING_MAIN_KEEPALIVE=true
SPRING_THREADS_VIRTUAL_ENABLED=true
```

Hai dòng trên là tên biến môi trường minh họa theo relaxed binding, không phải lệnh shell đặt biến chung cho mọi hệ điều hành. Với process entrypoint, cách ít nhầm hơn là command line:

```bash
java -jar app.jar --spring.main.keep-alive=true --spring.threads.virtual.enabled=true
```

`app.jar` là tên file minh họa; với dự án mục 5, dùng tên `keepalive-virtual-lab-0.0.1-SNAPSHOT.jar`.

Điều cần kiểm chứng không chỉ là key có trong config repository mà còn là process **thực sự nhận đúng property value**, chạy đúng JDK và đúng Boot version. Đừng nhầm một tên biến môi trường chưa được inject vào container với cấu hình đã có hiệu lực.

## 7. Tình huống nào cần bật keep-alive?

| Kiểu ứng dụng | Rủi ro không có non-daemon threads | Khuyến nghị |
| --- | --- | --- |
| Non-web app chỉ có `@Scheduled` chạy bằng virtual threads | **Có** | Bật `spring.main.keep-alive=true` để giữ JVM sống |
| App consumer/job poller dùng virtual-thread executor | **Có thể có** | Kiểm tra các thread và owner, cân nhắc keep-alive |
| Web app Servlet/Reactive dùng virtual threads | Phụ thuộc server, connector, thread thực tế | Bật keep-alive là biện pháp an toàn theo tài liệu Boot; không giả định port tự bảo đảm JVM sống mãi |
| CLI một lần, chạy xong phải exit | **Không mong muốn** giữ process vô hạn | Không bật keep-alive, đóng context rõ ràng nếu cần |
| Spring Batch/command-line tool có lifecycle do job quyết định | Muốn process exit theo kết quả job | Thiết kế exit code/shutdown và tránh giữ JVM không cần thiết |
| Ứng dụng có non-daemon platform worker thường trực | Có thể không gặp rủi ro daemon-only | Keep-alive có thể không cần, nhưng không lấy đó thay cho lifecycle ownership |
| Integration framework tự mở non-daemon threads | Phụ thuộc implementation và cấu hình | Xác minh thực tế, không suy theo tên thư viện |

**Không nên coi `spring.main.keep-alive=true` là “cấu hình luôn đúng cho mọi ứng dụng Java”.** Đối với CLI/job một lần, mục tiêu đúng là **hoàn thành công việc rồi exit**. Nếu bật keep-alive mà không có cơ chế đóng ứng dụng, quy trình CI/CD hoặc batch orchestrator có thể **chờ mãi** dù công việc đã xong.

### 7.1. Trường hợp web server đã mở port

Một web server có thể có non-daemon threads giữ JVM hoạt động. Tuy nhiên còn tùy embedded server, virtual-thread integration và cấu hình. Spring Boot vẫn khuyến nghị bật keep-alive cho virtual-thread applications để tránh phụ thuộc ngẫu nhiên vào một thread nền khác.

Mặt khác, **giữ JVM sống không bảo đảm HTTP server healthy**. Port có thể sai, context có thể không ready, runner có thể lỗi hoặc web server đã bị đóng. Phải kết hợp readiness/liveness, logs và probe phù hợp.

### 7.2. Trường hợp scheduled task định kỳ

Nếu service có trách nhiệm chạy hàng giờ/ngày, scheduler phải được phép tồn tại đến lần chạy tiếp theo. Một daemon virtual thread đang ngủ hoặc scheduler biết cron expression **không đủ** để bảo đảm process sống đến lúc đó. `spring.main.keep-alive=true` giải quyết lý do JVM tự thoát trong cấu hình daemon-only; scheduling và business success vẫn cần được quan sát riêng.

### 7.3. Trường hợp task duy nhất đã hoàn tất

Nếu ứng dụng chỉ chạy một `ApplicationRunner` để xuất báo cáo rồi muốn exit, việc giữ JVM sống “để phòng trường hợp” có thể làm command treo dù runner đã return. Không dùng keep-alive cho mục tiêu này; hãy quản lý resource và đóng context khi công việc đã hoàn tất.

## 8. Giữ JVM sống không phải giữ Spring context chạy bất kể mọi thứ

Cần tách **sự tồn tại của process** với **sự tồn tại và trạng thái của ApplicationContext**.

- `spring.main.keep-alive=true` yêu cầu SpringApplication giữ JVM sống khi không còn non-daemon threads khác; nó không thay thế lifecycle quản lý context.
- Nếu ứng dụng **tự gọi `context.close()`**, các bean scheduler/executor thuộc context có thể bị dừng và destruction callbacks có thể chạy. Không mong đợi `@Scheduled` còn tiếp tục chạy sau khi context đã đóng.
- Nếu ứng dụng **gọi `System.exit(...)`**, JVM tiến hành shutdown theo contract tương ứng. Keep-alive không ngăn một lệnh exit chủ động.
- Nếu hệ điều hành/container gửi SIGTERM và shutdown hook hoạt động bình thường, Spring có cơ hội đóng context và dọn resource. `spring.main.keep-alive` không phải một “khóa” chống lại termination signal.
- Nếu bị SIGKILL, crash VM, host mất điện hoặc lỗi OOM nghiêm trọng, không thể bảo đảm callback Java hay task nền hoàn tất.
- Nếu task được gửi vào một queue chỉ nằm trong RAM, keep-alive không biến nó thành queue durable sống qua restart.

**Đặc biệt với `try-with-resources`:** trong demo này **không** viết:

```java
try (ConfigurableApplicationContext context =
        SpringApplication.run(KeepAliveVirtualApplication.class, args)) {
    System.out.println("main done");
}
// context.close() ở đây có thể dừng scheduled beans.
```

Đây là **phản ví dụ đối với mục tiêu chạy scheduler lâu dài** chứ không phải cú pháp Java sai. `try-with-resources` rất hữu ích cho chương trình batch có điểm kết thúc xác định; nhưng nếu đặt ngay quanh `SpringApplication.run` rồi rời khối, nó sẽ đóng context và làm scheduled work dừng theo lifecycle.

### 8.1. Keep-alive không phải thứ tự chờ Future

Giả sử một runner:

```java
@Override
public void run(ApplicationArguments args) {
    executor.submit(() -> preloadRequiredCatalog());
    // Runner return mà không đợi Future.
}
```

Đây là **đoạn minh họa**, cần `executor`, method `preloadRequiredCatalog` và class runner thật. Dù keep-alive=true, Boot có thể vẫn phát `ApplicationReadyEvent` sau khi runner return. Property chỉ ngăn kết thúc JVM do daemon-only threads, **không tự đợi `Future.get`**.

Nếu dữ liệu preload là điều kiện bắt buộc cho readiness, phải đợi task có timeout, propagate exception hoặc thiết kế readiness health gate. Keep-alive không thay cho việc phân biệt “submitted” và “completed”.

### 8.2. Keep-alive không làm daemon thread thành non-daemon

`Thread.currentThread().isDaemon()` của virtual thread vẫn là `true`. Keep-alive là giải pháp ở **cấp ứng dụng/JVM**, không thay đổi thuộc tính của các virtual threads đã tạo. Vì vậy trong thí nghiệm bạn có thể cùng lúc thấy:

```text
TICK ... virtual=true, daemon=true
```

và JVM vẫn tồn tại sau khi main return. Hai điều không mâu thuẫn.

## 9. Shutdown, SIGTERM và vận hành trong container

Trong Spring Boot 3.3, `SpringApplication` mặc định đăng ký JVM shutdown hook để context có cơ hội đóng bình thường khi process được yêu cầu dừng. Thuộc tính liên quan:

```properties
spring.main.register-shutdown-hook=true
```

Đây là giá trị mặc định; không cần khai báo nếu không có yêu cầu khác. **Nó khác `spring.main.keep-alive`**:

- **keep-alive:** tránh JVM kết thúc chỉ vì không còn non-daemon threads.
- **register-shutdown-hook:** cho Spring context cơ hội dọn dẹp khi JVM đang shutdown.
- **graceful shutdown:** chính sách dừng web server / lifecycle components, xử lý request hoặc task đang chạy theo cấu hình và thời hạn.

Nếu ứng dụng có web server, có thể cấu hình graceful shutdown tùy trường hợp:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Hai property này **không phải cách giữ JVM sống** và không bắt mọi task async hoàn tất. Cần phối hợp thời hạn shutdown với Kubernetes `terminationGracePeriodSeconds`, health/readiness probes, timeout I/O và cơ chế retry/idempotency.

### 9.1. Kubernetes restart loops và keep-alive

Giả sử một deployment non-web scheduler dùng virtual threads, với `spring.main.keep-alive=false`, JVM có thể exit 0 ngay sau startup. Kubernetes Deployment có `restartPolicy=Always` theo hành vi chuẩn của Pod template; container có thể được chạy lại liên tục. Nhìn vào log, bạn có thể thấy startup lại nhiều lần mà không có Java exception.

Đừng vội tăng `restartPolicy` hoặc cho ứng dụng `Thread.sleep(Long.MAX_VALUE)` trong main. Hãy kiểm tra:

1. Có phải chỉ còn daemon virtual threads?
2. `spring.threads.virtual.enabled` có thực sự bật?
3. `spring.main.keep-alive` đang là gì?
4. Có web server/non-daemon worker giữ process không?
5. Đây là **Deployment service** cần chạy liên tục hay **CronJob/Job** phải hoàn thành rồi exit?

Nếu là CronJob chạy một lần, exit 0 sau khi hoàn tất có thể **đúng thiết kế**. Đừng ép giữ process vô hạn chỉ vì “pod cứ kết thúc”.

### 9.2. Khi nào cần cleanup thực sự?

Đối với scheduler/consumer dài hạn, nên cho `ApplicationContext` quản lý các resource sở hữu, đóng thread/executor, connection pool và message consumer bằng lifecycle callbacks hoặc `SmartLifecycle` phù hợp. Không chỉ dùng keep-alive để giữ tiến trình rồi bỏ qua:

- timeout và interruption handling;
- dừng nhận công việc mới khi shutdown;
- xử lý task đang chạy trong giới hạn;
- giải phóng tài nguyên sở hữu;
- phát trạng thái readiness thích hợp nếu có traffic;
- phục hồi job chưa hoàn tất khi process chết bất thường.

## 10. Các thuộc tính “keep alive” dễ bị nhầm

| Tên / khái niệm | Phạm vi | Khác `spring.main.keep-alive` thế nào? |
| --- | --- | --- |
| **`spring.main.keep-alive`** | SpringApplication/JVM process lifetime | Giữ JVM sống khi hết non-daemon threads |
| `spring.task.execution.pool.keep-alive` | Executor pool worker idle timeout | Chỉ là thời gian thread trong pool chờ khi idle |
| `server.tomcat.keep-alive-timeout` | HTTP connector connection persistence | Là thời gian chờ HTTP keep-alive giữa các request |
| HTTP `Connection: keep-alive` | Giao thức HTTP/client-server connection | Không giữ JVM sống theo daemon rules |
| TCP `SO_KEEPALIVE` | Socket-level liveness probe | Không liên quan Java daemon threads |
| Database connection pool idle/maxLifetime | Quản lý vòng đời kết nối DB | Không quyết định JVM có non-daemon threads |
| `Thread.sleep(...)` trong `main` | Chặn một thread hiện tại | Không phải cấu hình lifecycle Boot chuẩn |
| `Future.get()` | Chờ một computation cụ thể | Không phải cơ chế giữ service định kỳ sống vĩnh viễn |

Đặc biệt đừng nhầm **`spring.task.execution.pool.keep-alive=60s`** với cách ngăn JVM thoát. Cái tên gần giống nhưng là hai vấn đề khác nhau. Khi bật virtual-thread executor, một số pool-based tuning properties còn **bị bỏ qua** theo tài liệu Boot vì không còn cùng mô hình pool-based.

## 11. Vì sao không nên tự tạo non-daemon thread ngủ vô hạn?

Một workaround đôi khi gặp:

```java
new Thread(() -> {
    while (true) {
        try {
            Thread.sleep(60_000);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return;
        }
    }
}, "fake-keep-alive").start();
```

Đây là **đoạn phản ví dụ** để nhận diện mùi thiết kế, không phải khuyến nghị triển khai. Vì `new Thread(...)` tạo platform thread thông thường non-daemon nếu không bị ảnh hưởng bởi daemon status của thread tạo, nó có thể giữ JVM sống. Nhưng:

- Việc dừng/interrupt và lifecycle của “thread canh giữ” trở thành trách nhiệm của ứng dụng.
- Nếu quên dừng thread, tác vụ CLI/batch có thể treo và không exit.
- Thread bổ sung không giám sát scheduler, không xử lý failure/ready và không giải quyết resource leaks.
- Khi JVM chịu shutdown signal, nó không thay thế callback dọn dẹp chuẩn.
- Một bug trong thread này lại tạo thêm một thành phần phải monitor.

Với Spring Boot 3.3.x, dùng **`spring.main.keep-alive=true`** khi vấn đề đúng là daemon-only JVM exit thường rõ ràng, ít boilerplate và được framework hỗ trợ hơn.

### 11.1. Không “chữa” bằng cách giữ main block vô hạn

`Thread.currentThread().join()` trong chính main hoặc một `while(true) Thread.sleep(...)` có thể khiến process còn sống nhưng làm code khó hiểu và đóng ứng dụng không rõ ràng. Phần mềm vẫn có thể bị kill, background task vẫn có thể fail, và việc tách lifecycle khỏi Spring dễ gây lệch readiness.

Nếu mục tiêu là một service chạy lâu dài, sử dụng lifecycle Boot và orchestration phù hợp thay vì giữ một platform thread vô nghĩa.


## 12. Chẩn đoán: JVM vừa Started đã exit

Một quy trình điều tra có hệ thống:

**Bước 1 — xem có startup failure thật hay không.** Tìm `ApplicationFailedEvent`, stacktrace, lỗi bind port, runner ném exception, exit code và log container. Nếu có exception, keep-alive không tự sửa lỗi startup.

**Bước 2 — kiểm tra đúng Java runtime.** Chạy:

```bash
java -version
```

Cần Java **21+** nếu đang bật virtual threads. Không chạy ví dụ `Thread.isVirtual()` trên Java 17.

**Bước 3 — kiểm tra application type.** Ứng dụng không có web starter hoặc đặt `spring.main.web-application-type=none` thường không có web connector giữ process. Điều này là bình thường đối với scheduler/batch, không phải một lỗi.

**Bước 4 — kiểm tra property hiệu lực.** Xác minh:

```properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
```

Nếu override ở container/command line, cần chắc rằng đúng process đã nhận đúng giá trị, tránh kiểm tra nhầm file config hoặc profile.

**Bước 5 — kiểm tra thread và scheduler.** Trong method đang chạy, log:

```java
Thread t = Thread.currentThread();
System.out.println("virtual=" + t.isVirtual()
        + ", daemon=" + t.isDaemon());
```

Đây là **đoạn Java 21+ minh họa**, không phải một file độc lập. Nếu dùng scheduler custom hoặc executor tự khai báo, nó có thể khác scheduler auto-configured của Boot; đừng suy mọi thread đều virtual chỉ từ property.

**Bước 6 — thử so sánh true/false.** Dùng chính file `.jar` từ mục 5, chạy `--spring.main.keep-alive=true` rồi `false`, quan sát process có tiếp tục in các tick hay không. Thử trên terminal trực tiếp, phân biệt launcher như Gradle/IDE, không phụ thuộc một số tick cố định.

**Bước 7 — phân biệt process không còn với task không còn.** Process vẫn chạy nhưng `@Scheduled` không in thì có thể method chưa được quét, thiếu `@EnableScheduling`, lịch sai, trigger bị vô hiệu hóa, exception, scheduler không chạy hoặc log được lọc. Keep-alive không sửa các lỗi đó.

**Bước 8 — phân biệt ready và alive.** `ApplicationReadyEvent` chỉ đánh dấu Boot startup hoàn tất. Nó không bảo đảm một periodic task đã tới kỳ, và không thay thế health/monitoring cho một scheduler service.

### 12.1. Bảng triệu chứng thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Log “Started …”, sau đó process tự exit 0, không có exception | Chỉ còn daemon/virtual threads, không bật keep-alive | Bật `spring.main.keep-alive=true` nếu đúng là service dài hạn |
| Process vẫn chạy khi keep-alive=false | Có non-daemon thread khác | Không xem false là lệnh ép exit |
| Đã bật keep-alive nhưng `@Scheduled` không chạy | Scheduling chưa bật, bean không scan, trigger sai, error/task bị block | Kiểm tra `@EnableScheduling`, bean registration và logs |
| Boot báo ready trước khi job khởi tạo bắt buộc hoàn thành | Runner submit async rồi return | Chờ Future/ack hoặc readiness gate |
| JVM tự thoát dù có `@Async` virtual thread đang làm I/O | Virtual thread daemon không giữ JVM | Keep-alive cho service dài hạn và ownership/await phù hợp |
| Bật keep-alive thì CLI job không exit | Không có cơ chế đóng app, giữ process vô hạn | Tắt property cho batch hoặc đóng context/exit hợp lệ |
| Bật virtual threads nhưng task vẫn platform | Custom executor/scheduler hoặc integration không áp dụng virtual | Kiểm tra type của executor và `Thread.isVirtual()` |
| Tuning `spring.task.scheduling.pool.size` không có tác dụng | Boot dùng `SimpleAsyncTaskScheduler` khi virtual enabled | Chọn đúng chính sách concurrency, scheduling và metrics |
| `fixedDelay` dài làm scheduler bị chậm | Với SimpleAsyncTaskScheduler, fixed-delay hoạt động trên một scheduler thread | Cân nhắc fixedRate/cron, giới hạn overlap theo contract |
| Container restart loop dù Java exit 0 | Service định kỳ cần chạy mãi nhưng daemon-only process kết thúc | Chọn keep-alive hoặc thay workload thành đúng Kubernetes Job/CronJob |
| SIGTERM khiến app dừng dù keep-alive=true | Keep-alive không chống termination signal | Phân biệt shutdown bình thường và exit do daemon-only |
| Chỉ thấy tick một vài lần rồi không còn | Process đã dừng, scheduler bị shutdown, method lỗi, hoặc thread khác không chạy | Kiểm tra process lifetime, context lifecycle và error logs |
| App web có port open nhưng không ready | Readiness khác socket binding | Kiểm tra `ApplicationAvailability`/readiness probe |
| @Scheduled method ném exception nhưng JVM vẫn sống | Keep-alive không xử lý exception của task | Logging/alert/retry/idempotency, xử lý failure tại task |

### 12.2. Gợi ý quan sát cho production

Đối với ứng dụng scheduler/consumer dài hạn:

- Theo dõi process up/down, restart count và exit code.
- Theo dõi lần cuối task chạy `lastRunAt`, lần cuối thành công `lastSuccessAt`, duration và số lần fail.
- Theo dõi backlog/job age nếu có queue, không chỉ số thread.
- Giữ log lỗi ở task và correlation ID, tránh dump token/secret.
- Thêm health indicator khi cần để cho biết “service còn khả năng làm việc” thay vì chỉ “JVM đang sống”.
- Nếu công việc dùng resource ngoài, có I/O timeout, bounded retry và chính sách phục hồi sau restart.
- Phân biệt service readiness/liveness với tình trạng hoàn thành của **một job cụ thể**.

Keep-alive là **điều kiện tiên quyết về lifetime**, không phải chiến lược observability hay xử lý lỗi.

## 13. Những câu hỏi tự kiểm tra

**Câu 1.** Virtual threads có mặc định là daemon không?

**Đáp:** Có. Trong Java 21, virtual threads luôn là daemon và không ngăn JVM bắt đầu shutdown khi không còn non-daemon threads.

**Câu 2.** Boot 3.3 mặc định `spring.main.keep-alive` là gì?

**Đáp:** `false`. Bật `true` khi cần JVM tồn tại ngay cả khi các thread còn lại đều daemon.

**Câu 3.** `spring.threads.virtual.enabled=true` có thay thế `spring.main.keep-alive=true` không?

**Đáp:** Không. Một property chọn virtual threads ở những integration Boot hỗ trợ; property còn lại giữ JVM sống trong trường hợp daemon-only.

**Câu 4.** Đã có bean `@Scheduled` thì JVM chắc chắn chờ đến lần chạy kế tiếp?

**Đáp:** Không. Scheduler biết lịch nhưng daemon threads không giữ JVM sống. Cần kiểm tra process lifetime.

**Câu 5.** Vì sao ứng dụng non-web dễ bộc lộ vấn đề này?

**Đáp:** Nó có thể không có web server/non-daemon thread khác; main kết thúc là chỉ còn scheduler/virtual daemon threads.

**Câu 6.** Keep-alive=false có ép JVM thoát ngay khi main return không?

**Đáp:** Không. Nếu còn non-daemon thread khác thì JVM vẫn có thể chạy.

**Câu 7.** Keep-alive=true có bảo đảm task `@Async` thành công không?

**Đáp:** Không. Nó không await Future, không retry và không phát hiện business failure.

**Câu 8.** Java 17 có thể chạy `Thread.currentThread().isVirtual()` không?

**Đáp:** Không. API chính thức cho virtual threads trong thí nghiệm yêu cầu Java 21+.

**Câu 9.** Tại sao `spring.task.execution.pool.keep-alive` không giải quyết daemon-only JVM exit?

**Đáp:** Nó chỉ cấu hình pool worker idle lifetime, không phải SpringApplication/JVM keep-alive.

**Câu 10.** `@Scheduled(fixedDelay=...)` có luôn chạy trên virtual thread riêng trong `SimpleAsyncTaskScheduler`?

**Đáp:** Không. Với implementation này, fixed-delay có cơ chế chạy trên một scheduler thread; Spring Framework khuyến nghị fixedRate/cron phù hợp hơn với virtual-thread scheduling.

**Câu 11.** Nếu main đóng context ngay sau `run`, keep-alive=true có khiến scheduled bean vẫn chạy?

**Đáp:** Không nên kỳ vọng. Đóng context sẽ tiến hành shutdown của các bean scheduler và lifecycle resource tương ứng.

**Câu 12.** Khi JVM bị SIGKILL, keep-alive có bảo vệ đang chạy không?

**Đáp:** Không. Nó không chống process termination do hệ điều hành và không bảo đảm finally, `@PreDestroy` hoặc task hoàn tất.

**Câu 13.** Một ứng dụng batch chạy xong cần trả exit code, có nên bật keep-alive vô điều kiện?

**Đáp:** Không. Điều đó có thể khiến tiến trình đứng chờ mãi sau khi job đã hoàn thành; nên quản lý lifecycle và exit đúng hợp đồng.

**Câu 14.** Vì sao HTTP keep-alive timeout không giống Spring main keep-alive?

**Đáp:** HTTP keep-alive liên quan thời gian duy trì kết nối client/server, còn `spring.main.keep-alive` liên quan việc JVM tiếp tục chạy dù chỉ còn daemon threads.

## 14. Tóm tắt và nguồn tham khảo

- **Java 21 virtual threads luôn daemon**; daemon threads **không giữ JVM sống** khi các non-daemon threads đã kết thúc.
- Với Spring Boot 3.3, `spring.threads.virtual.enabled=true` bật virtual-thread support trong các integration Boot tương thích.
- `spring.main.keep-alive=true` yêu cầu Boot giữ JVM tồn tại kể cả khi toàn bộ các thread còn lại là daemon/virtual. **Default của Boot 3.3 là false.**
- Tình huống quan trọng nhất là **non-web scheduler với `@Scheduled`** chạy trên virtual threads: đã scheduling không có nghĩa process sẽ đợi tới tick.
- Spring Boot 3.3 tự cấu hình `SimpleAsyncTaskScheduler` khi virtual threads enabled; Spring Framework 6.1 khuyến nghị fixedRate/cron thay fixedDelay cho cách thực thi này.
- **Keep-alive không đồng nghĩa task completed, app ready, graceful shutdown hoặc chống SIGTERM/SIGKILL.** Nếu việc nền bắt buộc, vẫn cần chờ Future hoặc readiness gate.
- Không nhầm `spring.main.keep-alive` với pool thread idle keep-alive, TCP keepalive hay HTTP connection keep-alive.
- Với batch/CLI có thời điểm kết thúc rõ, tránh giữ JVM không cần thiết.

Tài liệu chính thức:

1. [Spring Boot 3.3.13 — SpringApplication, Virtual Threads](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): Java 21+, daemon threads và khuyến nghị `spring.main.keep-alive`.
2. [Spring Boot 3.3.13 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.main.keep-alive` mặc định false, các property task scheduling/execution.
3. [Spring Boot 3.3.13 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): `SimpleAsyncTaskScheduler` với virtual threads và các pool settings bị bỏ qua.
4. [Spring Boot 3.3.13 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html): `setKeepAlive(boolean)`/`isKeepAlive()`, có từ Spring Boot 3.2.
5. [Spring Framework 6.1 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): virtual-thread-aligned scheduler và lưu ý fixedDelay.
6. [Java SE 21 — Thread API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): virtual threads là daemon và không ngăn JVM shutdown.

**Kết luận:** Nếu ứng dụng Spring Boot sử dụng virtual threads và cần chạy lâu dài, `spring.main.keep-alive=true` là cấu hình bảo vệ **lifetime của JVM**. Sau khi giải quyết việc “tiến trình còn chạy”, vẫn phải xây dựng riêng cơ chế xác nhận “task đã chạy, đã thành công, có thể tiếp tục phục vụ và sẽ dừng sạch khi cần”.
