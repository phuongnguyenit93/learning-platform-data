# Phân biệt thời gian tiến trình JVM với thời gian khởi động ứng dụng Spring Boot

## 1. Vì sao Spring Boot ghi hai khoảng thời gian trong cùng một dòng log?

Khi khởi động ứng dụng Spring Boot, bạn thường thấy một dòng tương tự:

```text
Started DemoApplication in 3.214 seconds (process running for 4.086)
```

Các số **3.214** và **4.086** trong ví dụ này chỉ là số **minh họa**; kết quả thực tế thay đổi theo máy, thư viện, cấu hình và từng lần chạy.

Hai khoảng thời gian có cùng đơn vị giây nhưng bắt đầu từ **hai mốc khác nhau**:

- **`Started ... in 3.214 seconds`**: thời lượng quá trình **Spring Boot khởi động ứng dụng**, tính từ giai đoạn bắt đầu `SpringApplication.run(...)` đến lúc `ApplicationContext` được làm mới và ứng dụng đạt mốc *started*. Ở thời điểm này các `ApplicationRunner` và `CommandLineRunner` chưa được gọi.
- **`process running for 4.086`**: thời gian mà **tiến trình Java/JVM hiện tại đã hoạt động** tính từ lúc JVM bắt đầu chạy đến thời điểm dòng log được ghi. Khoảng này còn bao gồm thời gian **trước khi Spring Boot bắt đầu đo startup**, chẳng hạn quá trình JVM khởi tạo và mã chạy trước `SpringApplication.run(...)`.

Do đó, **thời gian JVM đã chạy không đồng nghĩa với thời gian Spring Boot khởi động**. Cả hai cũng khác với **thời gian tồn tại tổng cộng của tiến trình** sau khi ứng dụng đã khởi động và khác với **thời điểm ứng dụng thực sự sẵn sàng phục vụ** sau các runner.

Điểm dễ nhầm nhất: `process running for` không phải thời gian “Spring chạy xong rồi JVM chạy thêm” hay một giai đoạn nối tiếp **sau** `Started ... in`. Hai đồng hồ **đang đo những khoảng có phần chồng lên nhau**, không phải hai đoạn rời để cộng lại.

## 2. Xây dựng dòng thời gian khởi động

Quan sát các mốc khái niệm:

```text
t0             t1                    t2                  t3                 t4
|--------------|---------------------|-------------------|------------------|
JVM bắt đầu    SpringApplication     ApplicationStarted  ApplicationReady   JVM còn
chạy           .run(...) bắt đầu     (context refreshed) (runners xong)     hoạt động
               / Boot bắt đầu đo

<------------------- JVM uptime tại t2 ------------------->
               <--- Spring startup (started) --->
               <------------ Time to ready --------------->

<--------------------------- JVM uptime tại t4 ---------------------------------->
```

Các mốc:

1. **t0 – JVM start:** hệ điều hành khởi động tiến trình Java, JVM bắt đầu thực thi. Trước `main` có thể có khởi tạo runtime, class loading, tác nhân Java (Java agent), thao tác của launcher hoặc các giai đoạn khác.
2. **t1 – Boot run bắt đầu:** chương trình gọi `SpringApplication.run(...)`. Spring Boot chuẩn bị `Environment`, cấu hình, `ApplicationContext`, bean và Web server nếu là ứng dụng Web.
3. **t2 – ApplicationStarted:** context đã được refresh; Spring Boot báo mốc started. Các runner chưa được gọi.
4. **t3 – ApplicationReady:** sau khi những `ApplicationRunner` và `CommandLineRunner` chạy xong, Spring Boot phát sự kiện ready và cập nhật trạng thái readiness theo quy trình mặc định.
5. **t4 – Sau khởi động:** JVM có thể tiếp tục chạy nhiều giờ hoặc nhiều ngày, dù “startup” chỉ mất vài giây.

Nếu ký hiệu `U(t)` là JVM uptime tại thời điểm `t`, ta có cách hiểu gần đúng:

```text
JVM uptime tại t2 ≈ t2 - t0
Spring started time ≈ t2 - t1
Spring ready time   ≈ t3 - t1
JVM uptime tại t4  ≈ t4 - t0
```

Các biểu thức dùng để giải thích **ranh giới phép đo**, không phải công thức cam kết mọi mili-giây đều khớp. Đồng hồ nội bộ, các callback và điểm chốt phép đo có thể không trùng hoàn toàn với các mốc vẽ giản lược.

Đặc biệt: **`t2` khác `t3`**. Một tiến trình có thể đã báo `Started` nhưng chưa hoàn thành runner, kiểm tra phụ thuộc hoặc toàn bộ công đoạn đánh dấu sẵn sàng. Cần đo đúng mục tiêu mới có kết luận đúng.

## 3. Đọc chính xác thông báo Started ... (process running for ...)

Ví dụ giả định:

```text
2026-11-09T09:00:05.200+07:00  INFO 12345 --- [main] c.e.demo.DemoApplication :
Started DemoApplication in 4.100 seconds (process running for 5.300)
```

Dòng này cho biết:

- **`09:00:05.200`** là **thời điểm trên đồng hồ** mà log được tạo (wall-clock timestamp).
- **`12345`** là PID trong ví dụ, dùng để nhận diện tiến trình; PID có thể đổi mỗi lần chạy.
- **`Started DemoApplication`** báo mốc Spring Boot started.
- **`in 4.100 seconds`** là độ dài của khoảng startup ứng dụng mà Spring Boot đo.
- **`process running for 5.300`** là JVM uptime tại thời điểm log, được hiển thị theo đơn vị giây trong dòng thông báo này.

Không nên suy luận rằng chênh lệch `5.300 - 4.100 = 1.200` giây **chỉ** là thời gian tạo JVM, vì còn có thể có lớp khởi động, Java agent, mã trước `run`, chênh giữa thời điểm đo/log và chi phí khác. Phép trừ cho một **ước lượng tổng phần thời gian ngoài khoảng Spring Boot startup trước mốc log**, chứ không tự động xác định được riêng nguyên nhân.

Một vài điều cần phân biệt thêm:

| Giá trị | Bắt đầu từ đâu? | Kết thúc khi nào? | Trả lời câu hỏi |
|---|---|---|---|
| `Started ... in X seconds` | Điểm Spring Boot bắt đầu chạy/đo startup | Mốc Spring Boot started | Mất bao lâu để Spring khởi tạo context? |
| `process running for Y` | JVM bắt đầu hoạt động | Thời điểm ghi log Started | JVM đã chạy bao lâu tại lúc đó? |
| `ApplicationReadyEvent.getTimeTaken()` | Đầu chuỗi Spring Boot run | Mốc ready sau các runner | Bao lâu để Spring Boot sẵn sàng? |
| `RuntimeMXBean.getUptime()` | JVM bắt đầu hoạt động | **Ngay lúc gọi phương thức** | JVM đã sống bao lâu tới thời điểm hiện tại? |
| Thời gian tồn tại toàn tiến trình | JVM bắt đầu hoạt động | JVM thoát | Tiến trình đã tồn tại tổng cộng bao lâu? Chỉ xác định đầy đủ sau khi thoát. |
| Thời gian build `bootJar`/`bootRun` | Bắt đầu tác vụ Gradle tương ứng | Kết thúc giai đoạn đo | Công cụ build/launch mất bao lâu, kể cả những phần không thuộc JVM ứng dụng? |

**Lưu ý:** Dòng `Started` được ghi ở mức `INFO` theo cấu hình thông thường. Tắt log startup bằng `spring.main.log-startup-info=false` hoặc cấu hình logging có thể khiến dòng này không xuất hiện, **không** có nghĩa ứng dụng không chạy hay Spring Boot không có giai đoạn startup.

## 4. Tại sao process running for thường lớn hơn Started in?

Trong cách chạy thông thường `java -jar`, trình tự có thể như sau:

```text
Hệ điều hành khởi chạy java
        |
JVM khởi tạo / class loader / Java agent
        |
Spring Boot executable JAR launcher tìm lớp main
        |
Mã trong main chạy trước SpringApplication.run (nếu có)
        |
----------------- bắt đầu khoảng Spring Boot đo -----------------
        |
Chuẩn bị Environment, đọc cấu hình, tạo ApplicationContext
        |
Khởi tạo các bean, auto-configuration và server nếu có
        |
ApplicationContext.refresh hoàn tất
        |
Started ... in X seconds (process running for Y)
        |
ApplicationRunner / CommandLineRunner
        |
ApplicationReadyEvent
        |
Tiến trình tiếp tục làm việc hoặc thoát
```

**`process running for`** bao trùm cả phần nằm **trước** đường phân cách; **`Started ... in`** chủ yếu đo từ vùng Spring Boot run trở đi đến mốc started.

Những yếu tố có thể ảnh hưởng khoảng trước `SpringApplication.run`:

- JVM runtime, class loader và cơ chế launcher (ví dụ `java -jar` so với chạy main class trực tiếp).
- Các Java agent hoặc tác vụ instrumentation.
- Các câu lệnh trong `main` trước khi gọi `SpringApplication.run`: đọc file, kiểm tra cấu hình, tính toán, chờ mạng, `Thread.sleep`.
- Thời gian tạo đối tượng, cấu hình `SpringApplication` và khởi tạo dữ liệu sớm trước `run`.
- Sự khác biệt JVM, hệ điều hành, môi trường/container và tài nguyên máy.

Những yếu tố này giải thích vì sao **cùng source code** có thể có chênh lệch giữa hai đồng hồ khác nhau ở mỗi lần chạy. Không nên dùng chênh lệch để phán đoán chắc chắn JVM “chậm” nếu chưa gắn phép đo vào từng mốc.

## 5. Đo JVM uptime chính xác bằng Java Management API

Java cung cấp `RuntimeMXBean`, truy xuất qua `ManagementFactory.getRuntimeMXBean()`:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;

public class UptimeDemo {
    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();

        System.out.println("PID: " + runtime.getPid());
        System.out.println("JVM start (epoch ms): " + runtime.getStartTime());
        System.out.println("JVM uptime (ms): " + runtime.getUptime());
    }
}
```

Đây là chương trình **Java 17+ độc lập**, không cần Spring Boot. Lưu vào `UptimeDemo.java` rồi chạy:

```bash
javac UptimeDemo.java
java UptimeDemo
```

**Không có stdout cố định** vì PID và các giá trị thời gian phụ thuộc vào đúng lần chạy. Các dòng `getStartTime()` và `getUptime()` có đơn vị **mili-giây**, khác với số **giây** được hiển thị trong log Spring Boot. Chẳng hạn `getUptime() == 4850` có nghĩa JVM đã hoạt động khoảng `4.85` giây ở thời điểm gọi API.

Để quan sát thời điểm bắt đầu JVM theo lịch:

```java
import java.lang.management.ManagementFactory;
import java.time.Instant;

Instant jvmStartedAt = Instant.ofEpochMilli(
        ManagementFactory.getRuntimeMXBean().getStartTime());
System.out.println(jvmStartedAt);
```

Đoạn này dùng trong một phương thức Java phù hợp sau khi thêm các `import`; không tự chứa lớp `main` nên không chạy độc lập nếu chỉ sao chép ba dòng.

**Phân biệt:** `getStartTime()` trả về một **timestamp** (thời điểm bắt đầu JVM), còn `getUptime()` trả về một **duration** (độ dài thời gian JVM đã chạy). Đừng trừ các giá trị có ý nghĩa/đơn vị khác nhau mà không kiểm tra.

`RuntimeMXBean` báo thời gian của **JVM hiện tại**. Nếu ứng dụng chạy trong container, vẫn là JVM của tiến trình Java đang thực thi, không phải tổng tuổi thọ Docker container hoặc hệ điều hành host. Nếu Gradle chạy một JVM riêng để thực hiện build, `getUptime()` trong ứng dụng **không** đo JVM Gradle đó.

## 6. Đo hai mốc Spring Boot bằng ApplicationStartedEvent và ApplicationReadyEvent

Spring Boot cung cấp sự kiện lifecycle có sẵn thời lượng:

- `ApplicationStartedEvent`: context đã refresh, **trước** các `ApplicationRunner`/`CommandLineRunner`; `getTimeTaken()` trả về khoảng thời gian để **start** ứng dụng, có thể `null` nếu runtime không cung cấp.
- `ApplicationReadyEvent`: được phát rất muộn trong quá trình startup, sau khi các runner hoàn tất; `getTimeTaken()` cho biết thời gian đạt **ready**, có thể `null` nếu không xác định được.

Điều này cho phép đo **time to started** và **time to ready** riêng, thay vì suy từ uptime.

### Ví dụ Spring Boot 3.3.x + Java 17+ có thể chạy

Để thấy sự khác nhau rõ ràng, ví dụ cố ý chờ **900 ms trước `run`** và **1.200 ms trong `CommandLineRunner`**. Thời gian chờ là công cụ minh họa; ứng dụng sản xuất không nên thêm chờ giả.

Cấu trúc project:

```text
startup-clock-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/clock/
    └── StartupClockApplication.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'startup-clock-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Chỉ dùng `spring-boot-starter` nên không cần Web server. Nếu muốn dùng Gradle Wrapper, tạo dự án qua Spring Initializr hoặc Gradle có sẵn để có `gradlew`/`gradlew.bat`; tệp Wrapper không tự sinh chỉ từ `build.gradle`.

**`src/main/java/com/example/clock/StartupClockApplication.java`:**

```java
package com.example.clock;

import java.lang.management.ManagementFactory;
import java.time.Duration;
import java.util.Locale;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupClockApplication {

    public static void main(String[] args) throws InterruptedException {
        // Mô phỏng mã chạy trước khi SpringApplication.run bắt đầu.
        Thread.sleep(900);

        System.out.println("Before run - JVM uptime ms: " + jvmUptimeMs());

        SpringApplication application =
                new SpringApplication(StartupClockApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        application.addListeners(
                (ApplicationListener<ApplicationStartedEvent>) event -> {
                    System.out.println(
                            "Started event - Spring duration: "
                            + seconds(event.getTimeTaken()));
                    System.out.println(
                            "Started event - JVM uptime ms: " + jvmUptimeMs());
                });

        application.addListeners(
                (ApplicationListener<ApplicationReadyEvent>) event -> {
                    System.out.println(
                            "Ready event - Spring duration: "
                            + seconds(event.getTimeTaken()));
                    System.out.println(
                            "Ready event - JVM uptime ms: " + jvmUptimeMs());
                });

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            System.out.println(
                    "After run - JVM uptime ms: " + jvmUptimeMs());
        }
    }

    @Bean
    CommandLineRunner simulateInitialization() {
        return args -> {
            System.out.println("Runner starting");
            Thread.sleep(1200);
            System.out.println("Runner finished");
        };
    }

    private static long jvmUptimeMs() {
        return ManagementFactory.getRuntimeMXBean().getUptime();
    }

    private static String seconds(Duration duration) {
        if (duration == null) {
            return "khong xac dinh";
        }
        return String.format(Locale.ROOT, "%.3f s",
                duration.toNanos() / 1_000_000_000.0);
    }
}
```

**Tại sao dùng `ApplicationListener` đăng ký vào `SpringApplication`?** Các sự kiện lifecycle cần được lắng nghe từ lúc run. Đăng ký trực tiếp `application.addListeners(...)` ở trước `run` giúp listener nhận các sự kiện được phát trong giai đoạn Spring Boot khởi động. Không cần đoán thứ tự khởi tạo bean để đăng ký listener này.

Trong thư mục dự án đã có Wrapper, chạy:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Vì startup chịu ảnh hưởng môi trường, **không có số giây cố định** để chép làm expected output. Bạn sẽ quan sát các dòng của chương trình với thứ tự ý nghĩa gần như sau (bỏ qua những dòng log do Spring Boot/Gradle tự in):

```text
Before run - JVM uptime ms: <so-thuc-te>
Started event - Spring duration: <so-thuc-te> s
Started event - JVM uptime ms: <so-thuc-te>
Runner starting
Runner finished
Ready event - Spring duration: <so-thuc-te> s
Ready event - JVM uptime ms: <so-thuc-te>
After run - JVM uptime ms: <so-thuc-te>
```

Các biểu thức `<so-thuc-te>` chỉ là cách chú thích trong **khung minh họa thứ tự log**, không phải chuỗi literal mà code in ra.

### Phân tích kết quả quan sát

1. `Before run`: JVM đã chạy **ít nhất khoảng 900 ms chờ có chủ ý** cộng với chi phí JVM và mã khác, dù Spring Boot chưa bắt đầu `run`.
2. `Started event`: thời lượng Spring Boot đo **không cộng 900 ms chờ nằm trước `run`**. JVM uptime tại cùng thời điểm vẫn đã tính phần chờ đó.
3. `Runner starting/finished`: runner được gọi sau mốc `ApplicationStartedEvent` và trước `ApplicationReadyEvent`.
4. `Ready event`: thời gian `getTimeTaken()` ở mốc ready thường **lớn hơn** thời gian tại started vì còn bao gồm runner ngủ khoảng 1.200 ms.
5. `After run`: `SpringApplication.run` đã trả về context; JVM uptime tiếp tục tăng vì đồng hồ JVM không dừng tại mốc started/ready.

Ví dụ sử dụng `try-with-resources` để đóng context sau khi quan sát. Đây là cơ chế dọn tài nguyên của bài thực hành, không phải lời khuyên rằng ứng dụng Web phải tự đóng context ngay sau khởi động.

**Đừng so sánh thời lượng giữa hai lần chạy khác nhau như thể chúng dùng cùng đồng hồ gốc.** Hãy xem cùng PID/cùng một lần khởi động khi đối chiếu các mốc.

## 7. Mốc Started chưa đồng nghĩa với mốc Ready

Spring Boot có trình tự sự kiện quan trọng:

```text
ApplicationStartingEvent
         |
ApplicationEnvironmentPreparedEvent
         |
ApplicationContextInitializedEvent
         |
ApplicationPreparedEvent
         |
ApplicationContext được refresh
         |
ApplicationStartedEvent
         |
ApplicationRunner / CommandLineRunner
         |
ApplicationReadyEvent
         |
ReadinessState.ACCEPTING_TRAFFIC (trong quy trình mặc định)
```

**ApplicationStartedEvent** báo context đã khởi tạo thành công trước các runner; **ApplicationReadyEvent** có ý nghĩa sẵn sàng ở cuối chuỗi bootstrap. Dòng `Started ... in ...` theo thông lệ Spring Boot tương ứng mốc started, nên **không** nên coi nó luôn là thời điểm mà mọi tác vụ khởi động của người viết ứng dụng đã hoàn tất.

Ví dụ thực tế:

- `CommandLineRunner` chạy tác vụ kiểm tra dữ liệu mất 8 giây.
- Context đã refresh sau 3 giây, log `Started ... in 3 seconds`.
- Thời gian đạt `ApplicationReadyEvent` có thể khoảng 11 giây hoặc cao hơn, tùy phần việc khác.

Đó là một ví dụ **giả định** để diễn giải: không thể lấy con số 3 giây từ log started rồi tuyên bố ứng dụng **ready sau 3 giây**.

Nếu hệ thống dùng Kubernetes hoặc một nền tảng triển khai khác, nên phân biệt thêm: **readiness probe trả kết quả thành công tại một thời điểm** có thể phụ thuộc cách probe được cấu hình, khoảng poll, phụ thuộc mạng và kiểm tra sức khỏe. Vì vậy mốc ready trong Spring Boot và **thời điểm nền tảng bắt đầu route traffic** không nhất thiết trùng tuyệt đối.

## 8. Các thời gian khác cũng thường bị nhầm

### 8.1. Thời gian Gradle build so với thời gian JVM ứng dụng

Khi chạy:

```bash
./gradlew clean bootJar
java -jar build/libs/startup-clock-demo-0.0.1-SNAPSHOT.jar
```

Tác vụ `clean bootJar` có thể tải dependency, biên dịch mã, xử lý tài nguyên, đóng gói JAR. Những việc đó thường diễn ra **trước** khi JVM chạy JAR, nên **không** có trong `process running for` của JVM ứng dụng.

Khi chạy:

```bash
./gradlew bootRun
```

Gradle cũng có thể chạy tác vụ chuẩn bị, biên dịch trước khi khởi tạo JVM ứng dụng. Tùy cách thực thi, sẽ có JVM Gradle và JVM ứng dụng riêng. Lấy `ManagementFactory.getRuntimeMXBean().getUptime()` **trong ứng dụng** chỉ đo JVM của ứng dụng, không đo tổng thời gian lệnh Gradle từ khi người dùng nhấn Enter.

Cũng cần phân biệt chi phí build **warm cache** và **cold cache** khi so sánh hiệu năng vận hành: không nên coi Gradle task duration là Spring Boot startup duration.

### 8.2. Timestamp log so với khoảng thời gian

Một timestamp như `2026-11-09T09:00:05.200+07:00` là **một thời điểm lịch**. `3.214 seconds` là **một khoảng dài thời gian**. Nếu muốn tính khoảng giữa hai sự kiện trong cùng JVM, `System.nanoTime()` phù hợp hơn `System.currentTimeMillis()` vì được dùng để đo elapsed time.

Đo một công đoạn riêng:

```java
long begin = System.nanoTime();
// Thực hiện một thao tác đồng bộ mà bạn muốn đo.
long elapsedNanos = System.nanoTime() - begin;
System.out.println("Elapsed ms: " + elapsedNanos / 1_000_000.0);
```

Đây là đoạn code **minh họa**, đặt trong một phương thức Java. Nếu thao tác chưa được thêm giữa hai mốc, số đo chỉ là chi phí đo chính nó. `nanoTime` không phải epoch time và không dùng để in ngày giờ.

### 8.3. Uptime hiện tại so với tuổi thọ toàn tiến trình

`RuntimeMXBean.getUptime()` tiếp tục tăng trong suốt thời gian JVM tồn tại. Ví dụ service chạy 24 giờ, startup chỉ mất vài giây:

```text
Spring Boot startup:            vài giây
JVM uptime hiện tại:            ~24 giờ
Tổng tuổi thọ của tiến trình:   chưa xác định, vì service vẫn chạy
```

Không có lý do gì để gọi thời gian 24 giờ là “startup 24 giờ”. Tương tự, PID hoặc uptime thay đổi khi service được khởi động lại, kể cả Spring Boot dùng cùng tên ứng dụng và cổng.

### 8.4. Thời gian đáp ứng request so với startup

Một HTTP request mất 150 ms là **request latency**, không phải thời gian tạo context Spring Boot. Sau khi service ready, JVM có thể tiếp tục JIT compile, warm cache hoặc tải lazy bean trong những request đầu. Khi đánh giá hiệu năng, nên phân biệt **startup**, **readiness**, **first-request latency** và **steady-state latency**.

## 9. Quan sát chi tiết startup khi cần chẩn đoán

Dòng `Started ... in ...` cho **tổng thời gian tới mốc started**, nhưng chưa nói công đoạn nào đang chậm. Spring Boot có hỗ trợ **ApplicationStartup** để ghi các bước khởi tạo. Ví dụ:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

// Đặt trong phương thức main của một ứng dụng Spring Boot hợp lệ:
SpringApplication application = new SpringApplication(MyApplication.class);
application.setApplicationStartup(new BufferingApplicationStartup(2048));
application.run(args);
```

Đoạn trên là **mẫu tích hợp**, chưa phải một chương trình độc lập; cần có `MyApplication` và import thích hợp. `BufferingApplicationStartup` lưu các startup step (ví dụ bước tạo bean) trong buffer. Có thể dùng endpoint `/actuator/startup` nếu dự án thêm `spring-boot-starter-actuator`, cấu hình endpoint hỗ trợ và mở quyền truy cập phù hợp. Endpoint này cung cấp **chi tiết các bước startup**, khác với một con số JVM uptime tổng quát.

Ví dụ cấu hình cho dự án Web đã có Actuator:

```properties
management.endpoints.web.exposure.include=health,startup
```

Khi endpoint đã được cấu hình, bảo vệ và ứng dụng đang chạy:

```bash
curl http://localhost:8080/actuator/startup
```

**Không tự nhiên xuất hiện endpoint HTTP trong dự án `WebApplicationType.NONE`** như ví dụ phần 6. Nếu ứng dụng đang chạy non-web, có thể đọc startup steps qua các API nội bộ hoặc chuyển sang một dự án Web thử nghiệm đã cấu hình phù hợp.

Các công cụ khác như Java Flight Recorder (JFR), Java profiling, log timing hoặc Micrometer/Actuator metrics giúp phân tích JVM class loading, allocation, bean initialization hay các giai đoạn chạy; nhưng mỗi công cụ có **phạm vi đo riêng**. Đừng lấy chi tiết một công đoạn và coi đó là toàn bộ JVM uptime.

## 10. Các sai lầm thường gặp và cách sửa

| Hiểu nhầm | Vì sao sai | Cách hiểu hoặc kiểm chứng đúng |
|---|---|---|
| “Process running for 5 s nghĩa là Spring Boot mất 5 s để start” | Đó là thời gian JVM từ lúc bắt đầu đến mốc log. | Dùng `Started ... in X` hoặc `ApplicationStartedEvent.getTimeTaken()` cho startup Spring. |
| “Hai số trong log là hai giai đoạn nối tiếp” | Hai khoảng có phần **chồng nhau**. | Vẽ các mốc `t0`, `t1`, `t2` theo một timeline. |
| “Started rồi tức là CommandLineRunner đã xong” | Runner được gọi **sau** `ApplicationStartedEvent`. | Đo `ApplicationReadyEvent.getTimeTaken()` và log runner. |
| “Uptime lớn do Spring tự động cấu hình chậm” | Uptime có cả thời gian trước `run`. | Đặt mốc trong `main`, đo Boot started và JVM uptime tại cùng thời điểm. |
| “Chạy Gradle mất 30 s nghĩa là Boot startup 30 s” | Gradle còn có biên dịch, plugin và chuẩn bị dự án. | Tách build duration, launch overhead và startup của JVM ứng dụng. |
| “JVM uptime cao nghĩa là ứng dụng sắp chết” | Uptime cao chỉ có nghĩa JVM đã chạy lâu. | Dùng health, liveness, readiness, logs và metrics phù hợp. |
| “Không thấy log Started nghĩa là không có startup” | Cấu hình logging có thể ẩn log. | Kiểm tra `spring.main.log-startup-info`, các sự kiện và trạng thái service. |
| “Lấy timestamp trừ nhau là luôn đo chính xác elapsed” | Wall clock có thể điều chỉnh và log có độ trễ. | Dùng `System.nanoTime` cho công đoạn đo trong cùng JVM. |
| “Vì Actuator startup có event nên đó là cùng số process running for” | Startup steps mô tả các công đoạn Spring; JVM uptime bắt đầu sớm hơn. | Đối chiếu nguồn đo và mốc bắt đầu/kết thúc của từng metric. |
| “Cùng một tên service thì chắc cùng JVM” | Service có thể đã restart hoặc có nhiều replica. | So sánh PID, pod/container, JVM start time và định danh instance. |

### Khi thời gian khởi động bất thường

Một quy trình kiểm tra có căn cứ:

1. **Xác định metric nào chậm:** tổng thời gian chạy lệnh, uptime JVM tại started, Spring started hay thời gian ready.
2. **Xác định đúng một lần khởi động:** ghi PID, instance/container, Java version, chế độ chạy, profile và thời điểm bắt đầu.
3. **Tách công đoạn trước `run`:** agent, mã `main`, launcher và hoạt động trước Spring Boot startup.
4. **Tách công đoạn trong Spring:** khởi tạo context/bean, database migration, kết nối ngoài, server initialization, auto-configuration.
5. **Tách phần sau started:** các runner, listener, readiness check hoặc thao tác chuẩn bị khác.
6. **Đo lặp nhiều lần trong điều kiện tương đương**; so sánh phân phối thay vì một con số đơn lẻ. Nếu thay đổi cấu hình, dependency hoặc JVM, phải ghi nhận vì nó có thể ảnh hưởng cả hai chỉ số.

## 11. Bài thực hành đối chiếu hai đồng hồ

Dùng project `startup-clock-demo` ở phần 6. Các lần chạy dưới đây minh họa một biến duy nhất tại một thời điểm:

**Thử nghiệm A — thời gian trước run:** giữ `Thread.sleep(900)` trước `SpringApplication.run`. Quan sát `Before run - JVM uptime ms` đã vượt khoảng chờ này trong khi `Started event - Spring duration` không tính nó. Tăng thời gian chờ trước run lên 2.000 ms và quan sát xu hướng tăng của JVM uptime tại started; Spring started duration không cần tăng tương ứng.

**Thử nghiệm B — thời gian runner:** giữ phần trước run, đổi `Thread.sleep(1200)` trong `CommandLineRunner` thành 2.500 ms. `Started event - Spring duration` được chốt trước runner nên không tính thời gian chờ bổ sung này; `Ready event - Spring duration` tăng tương ứng. Mọi uptime đo **sau** runner cũng tăng.

**Thử nghiệm C — phép đo JVM tại thời điểm khác:** in `jvmUptimeMs()` ngay đầu `main` và sau `application.run(args)`. Giá trị tại thời điểm sau phải phản ánh thời gian đã trôi qua, không phải chỉ thời gian Spring Boot tạo context.

**Thử nghiệm D — đo thời gian khởi chạy bên ngoài JVM:** đo tổng thời gian chạy lệnh Gradle với công cụ hệ điều hành, đối chiếu với `ApplicationStartedEvent.getTimeTaken()` trong JVM. Kỳ vọng hai số khác nhau vì ranh giới đo khác nhau; không cần cố ép chúng bằng nhau.

### Câu hỏi tự kiểm tra

1. Dòng `Started X in 4.0 seconds (process running for 5.5)` có nghĩa ứng dụng đạt ready sau **4.0 s** chưa? Vì sao?
2. Nếu thêm `Thread.sleep(2000)` **trước** `SpringApplication.run`, đại lượng nào có thể tăng rõ nhất tại log started?
3. Nếu thêm một `CommandLineRunner` mất 5 s, đại lượng nào thay đổi rõ: started time hay ready time?
4. Vì sao tổng thời gian `./gradlew bootRun` từ lúc nhấn Enter có thể lớn hơn `process running for` của JVM ứng dụng?
5. Tại sao `RuntimeMXBean.getUptime()` sau một ngày chạy không dùng làm số đo Spring startup?

Lý giải được năm câu này giúp bạn đọc log startup của Spring Boot chính xác, chọn đúng chỉ số để tối ưu và tránh chẩn đoán sai khi thời gian khởi chạy tăng.

## Tài liệu tham khảo

- Spring Boot 3.3, `SpringApplication` và ví dụ log startup: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3, `ApplicationStartedEvent` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html
- Spring Boot 3.3, `ApplicationReadyEvent` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Boot 3.3, Actuator `startup` endpoint: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html
- Java 21, `RuntimeMXBean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/RuntimeMXBean.html

**Ghi nhớ:** `Started ... in` đo thời gian Spring Boot khởi tạo đến mốc started; `process running for` đo **JVM uptime** đến thời điểm ghi log; `ApplicationReadyEvent` giúp đánh giá mốc ready sau runner. Ba khái niệm có mốc đo riêng và phải được dùng đúng mục đích.