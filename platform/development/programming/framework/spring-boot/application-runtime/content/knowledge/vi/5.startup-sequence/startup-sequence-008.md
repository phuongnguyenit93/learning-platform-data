# Thông báo started, thực thi runner và thông báo ready

## 1. Vị trí của ba mốc trong chuỗi khởi động Spring Boot

Khi một ứng dụng Spring Boot chạy, thông báo **started**, giai đoạn chạy **runner** và thông báo **ready** diễn ra gần nhau nhưng không có cùng ý nghĩa. Với Spring Boot 3.3.x (Java 17+), trình tự quan trọng là:

1. `SpringApplication.run(...)` chuẩn bị môi trường, tạo `ApplicationContext`, đăng ký bean và **refresh context**; đối với ứng dụng web, web server được khởi tạo trong quá trình này.
2. Spring Boot có thể ghi log **`Started MyApplication in ... seconds`** sau khi refresh context thành công.
3. Spring Boot phát **`ApplicationStartedEvent`**: context đã được refresh, **chưa** chạy `ApplicationRunner` và `CommandLineRunner`.
4. Spring Boot công bố trạng thái liveness là **`LivenessState.CORRECT`**.
5. Spring Boot gọi các bean **`ApplicationRunner`** và **`CommandLineRunner`** theo thứ tự đã sắp xếp; các lời gọi này phải hoàn tất bình thường để đi tiếp.
6. Spring Boot phát **`ApplicationReadyEvent`** sau khi runner hoàn tất.
7. Spring Boot công bố trạng thái readiness **`ReadinessState.ACCEPTING_TRAFFIC`**.
8. `SpringApplication.run(...)` trả về `ConfigurableApplicationContext` cho caller nếu quá trình hoàn tất thành công.

```text
main()
  |
  +--> SpringApplication.run(...)
         |
         +--> Prepare environment / ApplicationContext
         +--> Load bean definitions, refresh context
         +--> Web server initialization (nếu là ứng dụng web)
         |
         +--> Log "Started <App> in ... seconds" (nếu bật startup INFO log)
         +--> ApplicationStartedEvent
         +--> AvailabilityChangeEvent(LivenessState.CORRECT)
         |
         +--> ApplicationRunner / CommandLineRunner
         |        (các runner được sắp thứ tự và chạy tuần tự)
         |
         +--> ApplicationReadyEvent
         +--> AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
         |
         +--> return ApplicationContext
  |
  +--> dòng tiếp theo trong main()
```

**Cốt lõi:** **started** có nghĩa Spring context đã khởi tạo xong ở mốc này; **ready** có nghĩa phần công việc khởi động đồng bộ, bao gồm các runner, đã hoàn tất và Boot chuyển sang trạng thái sẵn sàng phục vụ. **Log `Started ...` không phải một xác nhận rằng `ApplicationReadyEvent` đã xảy ra.**

Sơ đồ mô tả luồng khởi động mặc định của một `SpringApplication` trong Spring Boot 3.3.x. Các context cha–con, listener bất đồng bộ hoặc tùy biến lifecycle có thể bổ sung sự kiện, nhưng không làm thay đổi ý nghĩa chuẩn của ba mốc đang học.

## 2. Phân biệt log Started, ApplicationStartedEvent và ApplicationReadyEvent

| Dấu hiệu | Bản chất | Mốc xảy ra | Phù hợp để kết luận |
| --- | --- | --- | --- |
| Dòng log `Started ... in ... seconds` | Thông báo INFO của cơ chế startup logging | Thông thường sau refresh context, trước khi gọi các runner | Boot đã qua phần lớn bootstrap/context refresh; **chưa chứng minh readiness** |
| `ApplicationStartedEvent` | Một `SpringApplicationEvent` do Boot phát | Sau context refresh, trước runner | Context đã được refresh; có thể thực hiện logic quan sát mốc started |
| `ApplicationRunner` / `CommandLineRunner` | Callback khởi động dạng bean | Sau `ApplicationStartedEvent`, trước `ApplicationReadyEvent` | Thực hiện công việc một lần cần hoàn tất trước mốc ready |
| `ApplicationReadyEvent` | Event cuối giai đoạn startup thành công, phát sau runner | Sau khi các runner đã trả về thành công | Boot coi ứng dụng đã sẵn sàng ở mức vòng đời startup |
| `AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)` | Cập nhật trạng thái availability của Boot | Ngay sau `ApplicationReadyEvent` trong luồng thông thường | Hệ thống theo dõi readiness có thể nhận biết trạng thái chấp nhận traffic |

### 2.1. Thông báo log Started không phải là một event

Dòng log thường có hình thức:

```text
Started PaymentApplication in 2.145 seconds (process running for 2.802)
```

Các số giây chỉ **minh họa định dạng**, thay đổi theo môi trường, cấu hình, máy và phiên bản. Dòng này được phát bởi hệ thống logging khi startup info được bật. Nó **không phải** đối tượng `ApplicationStartedEvent` và không tự bảo đảm các runner đã hoàn tất.

Có thể điều khiển các dòng startup info qua:

```properties
spring.main.log-startup-info=false
```

Hoặc bằng cấu hình logging như `logging.level.root=ERROR` khi không muốn xuất log INFO. **Tắt log chỉ làm thay đổi thứ nhìn thấy trong console, không loại bỏ `ApplicationStartedEvent`, runner hay `ApplicationReadyEvent`.**

Ngược lại, thấy chữ “Started” trên console rồi nhưng runner đang tải dữ liệu 20 giây thì ứng dụng vẫn chưa đạt mốc ready của Boot. Nếu runner ném exception, dòng log started có thể đã xuất hiện trước khi startup thất bại.

### 2.2. ApplicationStartedEvent

Class: `org.springframework.boot.context.event.ApplicationStartedEvent`.

Spring Boot phát event này **sau khi context refresh thành công và trước khi gọi bất kỳ runner startup nào**. Bean listener đã được đăng ký trong context có thể lắng nghe bằng:

```java
@EventListener
public void onStarted(ApplicationStartedEvent event) {
    System.out.println("Context refreshed; runners not called yet");
}
```

Đây là **đoạn mã minh họa**; muốn biên dịch cần đặt trong một bean do Spring quản lý, import `org.springframework.context.event.EventListener` và `org.springframework.boot.context.event.ApplicationStartedEvent`.

`ApplicationStartedEvent` còn có `getTimeTaken()` trả về `Duration` biểu thị thời gian đến mốc started trong những phiên bản Boot 3.3.x hỗ trợ API này. Nó hữu ích khi phân tích độ trễ startup, nhưng **không bao gồm toàn bộ thời gian của runner**.

### 2.3. ApplicationReadyEvent

Class: `org.springframework.boot.context.event.ApplicationReadyEvent`.

Event này được phát **sau khi các bean `ApplicationRunner` và `CommandLineRunner` đã chạy xong thành công**. Listener:

```java
@EventListener
public void onReady(ApplicationReadyEvent event) {
    System.out.println("Startup runners completed");
}
```

Cũng là đoạn minh họa cần đặt trong Spring bean với các import tương ứng. `ApplicationReadyEvent#getTimeTaken()` phản ánh thời gian tới mốc ready; thường cao hơn `ApplicationStartedEvent#getTimeTaken()` nếu runner cần thời gian xử lý.

**Không nên xem `ApplicationReadyEvent` là bằng chứng mọi dịch vụ ngoài hệ thống đều khỏe mạnh mãi mãi**. Đây là dấu mốc của vòng đời khởi động một ứng dụng; sức khỏe database, broker, downstream API và khả năng nhận traffic cần cơ chế health/readiness phù hợp. Việc đọc một event cũng không đồng nghĩa web server chỉ bắt đầu lắng nghe từ lúc đó.

### 2.4. Thứ tự với các Spring application event liên quan

Trong Spring Boot 3.3.x, các mốc nổi bật quanh startup là:

```text
ApplicationStartingEvent
  -> ApplicationEnvironmentPreparedEvent
  -> ApplicationContextInitializedEvent
  -> ApplicationPreparedEvent
  -> (ContextRefreshedEvent / WebServerInitializedEvent trong giai đoạn refresh)
  -> ApplicationStartedEvent
  -> AvailabilityChangeEvent(LivenessState.CORRECT)
  -> [ApplicationRunner và CommandLineRunner]
  -> ApplicationReadyEvent
  -> AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
```

`ContextRefreshedEvent` là event của Spring Framework; `WebServerInitializedEvent` được gửi khi web server đã sẵn sàng (nếu có). Không nên dùng sự kiện web server để thay cho readiness, vì runner vẫn có thể đang chạy.

Nếu startup gặp exception, Boot phát `ApplicationFailedEvent` trong đường xử lý lỗi. Nó không phải một bước tiếp theo bắt buộc của startup thành công. Một lỗi trong runner có thể xảy ra **sau** `ApplicationStartedEvent` nhưng **trước** `ApplicationReadyEvent`.

## 3. Runner: công việc một lần giữa started và ready

Spring Boot có hai contract:

```java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}

public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

Hai interface trên là **minh họa chữ ký phương thức**; import thực là `org.springframework.boot.ApplicationRunner` và `org.springframework.boot.CommandLineRunner`, còn `ApplicationArguments` thuộc `org.springframework.boot.ApplicationArguments`.

Cả hai là bean Spring và được Spring Boot tự tìm, gọi trong `SpringApplication.run(...)`. Một runner không chạy trên JVM riêng hay là một controller xử lý HTTP. Nó phục vụ **công việc startup đồng bộ**.

| Đặc điểm | `ApplicationRunner` | `CommandLineRunner` |
| --- | --- | --- |
| Phương thức | `run(ApplicationArguments args)` | `run(String... args)` |
| Đầu vào | API đã phân tích tham số command-line thành option/non-option | Mảng tham số raw truyền từ `main` |
| Khi gọi | Sau `ApplicationStartedEvent` | Sau `ApplicationStartedEvent` |
| Khi kết thúc | Trước `ApplicationReadyEvent` | Trước `ApplicationReadyEvent` |
| Dùng khi | Cần kiểm tra option theo tên, đọc non-option argument | Cần tham số nguyên dạng hoặc tác vụ khởi động đơn giản |
| Thứ tự | Có thể đặt `@Order` hoặc triển khai `Ordered` | Có thể đặt `@Order` hoặc triển khai `Ordered` |

Ví dụ chạy với `--mode=import input.csv`:

- `ApplicationArguments.containsOption("mode")` có thể trả về `true`; `getOptionValues("mode")` chứa `import`, `getNonOptionArgs()` chứa `input.csv`.
- `CommandLineRunner` nhận các chuỗi `"--mode=import"` và `"input.csv"` theo thứ tự truyền vào.

### 3.1. Thứ tự nhiều runner

Spring Boot tập hợp các bean thuộc **cả hai** interface và dùng cơ chế Spring ordering để sắp thứ tự. **Không có quy tắc mặc định “ApplicationRunner luôn trước CommandLineRunner”**. Có thể đánh dấu:

```java
@Order(10)
@Component
class ValidateStartup implements ApplicationRunner { /* ... */ }

@Order(20)
@Component
class PreloadStartup implements CommandLineRunner { /* ... */ }
```

Đây chỉ là **minh họa thứ tự**, không phải file biên dịch độc lập. Class `ValidateStartup` và `PreloadStartup` cần triển khai method `run` và các import liên quan. Số order **nhỏ hơn được ưu tiên chạy trước**. Khi nhiều runner có cùng thứ tự hoặc không khai báo order, đừng dựa vào thứ tự quan sát được ở một lần chạy làm contract. Hãy đặt order rõ ràng nếu có phụ thuộc dữ liệu.

Một runner chặn trên I/O, sleep hoặc tính toán lâu sẽ **kéo dài khoảng started → ready**. Nếu runner tạo background thread rồi trả về ngay, Spring Boot chỉ biết phương thức `run` đã hoàn tất, **không tự đợi công việc nền kết thúc**; đừng dùng kỹ thuật này khi readiness thực sự phụ thuộc vào việc đó.

### 3.2. Nên đặt công việc gì trong runner?

Phù hợp khi cần hoàn tất **một lần sau context refresh, trước ready**, ví dụ kiểm tra dữ liệu cấu hình nghiệp vụ, nạp metadata nhỏ thiết yếu, kiểm tra invariant không thể trì hoãn, đăng ký việc cần biết lúc sẵn sàng.

Cần cân nhắc khi runner thực hiện migration nặng, gọi hệ thống ngoài dễ chập chờn hoặc xử lý batch có thời gian không giới hạn. Công việc kiểu đó làm deployment chậm ready, có thể khiến startup thất bại hoặc bị quá thời gian. Nếu nó không phải điều kiện tối thiểu để phục vụ, cân nhắc chuyển sang job độc lập, tác vụ nền có trạng thái riêng hoặc cơ chế điều phối phù hợp.

**Runner không thay thế `@PostConstruct`.** `@PostConstruct` là callback vòng đời của từng bean trong lúc bean được khởi tạo, có thể xảy ra trước khi toàn context sẵn sàng. Runner chạy **sau refresh** và có thể truy cập các bean cần thiết. Cả hai khác với `ApplicationReadyEvent`, vốn đến sau runner.

## 4. Ví dụ chạy được: in rõ các mốc startup

Thí nghiệm dùng **Spring Boot 3.3.13 và Java 17+**, trong một project Gradle có wrapper. Dùng `spring-boot-starter` để có ứng dụng non-web, tránh log HTTP server làm nhiễu; trình tự started → runner → ready **vẫn áp dụng cho ứng dụng web**.

### 4.1. build.gradle

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

Dự án cần wrapper Gradle tương thích với Spring Boot 3.3 (ví dụ Gradle 8.5) và Java 17+ được cấu hình cho build. Nếu tạo từ Spring Initializr, giữ `settings.gradle` và Gradle Wrapper do dự án sinh ra.

### 4.2. application.properties

Tạo `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

Những thuộc tính này giúp ví dụ chỉ in dòng chúng ta chủ động viết. `log-startup-info=false` không tắt event; nó chỉ tắt nhóm log startup info. `web-application-type=none` bảo đảm thí nghiệm không cần server HTTP.

### 4.3. Mã Java hoàn chỉnh trong một file

Đặt file tại **`src/main/java/com/example/startup/StartupTimelineApplication.java`**:

```java
package com.example.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class StartupTimelineApplication {

    public static void main(String[] args) {
        System.out.println("01 main: before run");
        SpringApplication.run(StartupTimelineApplication.class, args);
        System.out.println("08 main: after run");
    }

    @Component
    static class EventObserver {

        @EventListener
        public void started(ApplicationStartedEvent event) {
            System.out.println("02 ApplicationStartedEvent");
        }

        @EventListener
        public void availability(AvailabilityChangeEvent<?> event) {
            if (event.getState() == LivenessState.CORRECT) {
                System.out.println("03 LivenessState.CORRECT");
            } else if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
                System.out.println("07 ReadinessState.ACCEPTING_TRAFFIC");
            }
        }

        @EventListener
        public void ready(ApplicationReadyEvent event) {
            System.out.println("06 ApplicationReadyEvent");
        }
    }

    @Component
    @Order(10)
    static class StartupValidation implements ApplicationRunner {

        @Override
        public void run(ApplicationArguments args) {
            System.out.println("04 ApplicationRunner: options="
                    + args.getOptionNames().size());
        }
    }

    @Component
    @Order(20)
    static class StartupPreparation implements CommandLineRunner {

        @Override
        public void run(String... args) {
            System.out.println("05 CommandLineRunner: rawArgs="
                    + args.length);
        }
    }
}
```

Tất cả các class cần thiết nằm trong một file Java; hai class `static` lồng nhau được `@Component` đăng ký thành bean khi Boot quét package `com.example.startup`. `@Order(10)` và `@Order(20)` giúp thứ tự hai runner rõ ràng. `@EventListener` trên bean `EventObserver` lắng nghe event sau khi context refresh. Mặc định listener được gọi đồng bộ trên luồng phát event.

Chú ý: `AvailabilityChangeEvent<?>` có thể mang nhiều loại availability state. Code chỉ in khi thấy `LivenessState.CORRECT` hoặc `ReadinessState.ACCEPTING_TRAFFIC`, nên không in những thay đổi trạng thái khác.

### 4.4. Chạy ví dụ

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

Nếu cần đóng gói rồi chạy bằng Java:

```bash
./gradlew bootJar
java -jar build/libs/startup-demo-0.0.1-SNAPSHOT.jar
```

Tên JAR trong ví dụ là **minh họa**; file thực tế phụ thuộc vào tên project và cấu hình `bootJar`. Dùng đúng tên artifact hiện có trong thư mục `build/libs`.

### 4.5. Kết quả dự kiến

Khi chạy **không truyền tham số** và chưa có bean startup bổ sung khác, các dòng **do mã Java in ra** theo thứ tự:

```text
01 main: before run
02 ApplicationStartedEvent
03 LivenessState.CORRECT
04 ApplicationRunner: options=0
05 CommandLineRunner: rawArgs=0
06 ApplicationReadyEvent
07 ReadinessState.ACCEPTING_TRAFFIC
08 main: after run
```

Gradle có thể in thêm thông tin task build. Trong trường hợp có log lỗi hoặc config khác, console có thể xuất hiện dòng phụ; thứ tự các mốc bên trên vẫn phản ánh các callback trong thí nghiệm mặc định. Ở ứng dụng non-web này, sau khi `main` kết thúc, JVM thường thoát nếu không còn thread không-daemon hoặc công việc khác giữ sống.

Lý giải thứ tự:

- `01` in trước khi Spring Boot tạo context.
- `02` xác nhận `ApplicationStartedEvent` đã được gửi.
- `03` là công bố liveness tương ứng ngay sau started.
- `04` và `05` thuộc hai runner được Spring sắp thứ tự.
- `06` xác nhận Boot đã đi qua tất cả runner thành công.
- `07` là công bố readiness sau ready event.
- `08` cho thấy `SpringApplication.run(...)` đã trả về caller.

**Thử thêm đối số:** Chạy `.\gradlew.bat bootRun --args="--mode=demo"` trên Windows hoặc `./gradlew bootRun --args='--mode=demo'` trên macOS/Linux. Khi đó dòng `ApplicationRunner` thường có `options=1` và `CommandLineRunner` có `rawArgs=1`, minh họa sự khác nhau về cách nhận đối số.

## 5. Thấy chữ Started nhưng vẫn chưa ready

Để quan sát thực tế, đổi `application.properties` từ:

```properties
spring.main.log-startup-info=false
logging.level.root=ERROR
```

thành:

```properties
spring.main.log-startup-info=true
logging.level.root=INFO
```

Khi chạy lại, console sẽ có thêm startup INFO log, ví dụ dòng:

```text
Started StartupTimelineApplication in 0.812 seconds (process running for 1.217)
02 ApplicationStartedEvent
03 LivenessState.CORRECT
04 ApplicationRunner: options=0
05 CommandLineRunner: rawArgs=0
06 ApplicationReadyEvent
```

Đây là **trích đoạn mô phỏng trình tự**, không phải toàn bộ output được cam kết; thời gian, logging prefix và các dòng trước/sau thay đổi theo máy. Trong Spring Boot 3.3.x mặc định, dòng INFO `Started ...` có thể xuất hiện **trước** callback `ApplicationStartedEvent` và **chắc chắn không cần chờ runner**. Vì vậy không được dùng một phép grep log `Started` để tuyên bố ứng dụng đã xử lý xong bước chuẩn bị dữ liệu trong runner.

### 5.1. Runner chậm

Đổi một runner trong ví dụ thành công việc kéo dài:

```java
@Override
public void run(ApplicationArguments args) throws InterruptedException {
    System.out.println("Runner begins");
    Thread.sleep(3000);
    System.out.println("Runner ends");
}
```

Đây là **đoạn thay thế method** `run` của `StartupValidation`, không phải file độc lập. `Thread.sleep` chỉ để biểu diễn độ trễ; không dùng sleep để mô phỏng chờ phụ thuộc trong production. Khoảng giữa `ApplicationStartedEvent` và `ApplicationReadyEvent` sẽ tăng khoảng ba giây, cộng thời gian thực thi khác.

Nếu cần nắm rõ thời gian, so sánh `ApplicationStartedEvent#getTimeTaken()` và `ApplicationReadyEvent#getTimeTaken()`, hoặc ghi timestamp quanh runner. Không dựa trên số giây cố định trong log mẫu.

### 5.2. Runner ném exception

Thử thay body của một runner bằng:

```java
@Override
public void run(String... args) {
    throw new IllegalStateException("Startup data is invalid");
}
```

Đây cũng là đoạn thay thế một method, không phải file chạy độc lập. Khi chạy, event started và các runner trước điểm lỗi **có thể đã xảy ra**, nhưng Spring Boot sẽ xử lý startup failure. Nó **không đạt tới `ApplicationReadyEvent`**; thường có exception log, `ApplicationFailedEvent` và quá trình đóng context. Không thể dùng log `Started` trước đó làm bằng chứng startup đã hoàn thành.

Nếu muốn quan sát lỗi từ rất sớm (trước khi context tạo bean), cần đăng ký `ApplicationListener<ApplicationFailedEvent>` trực tiếp với `SpringApplication.addListeners(...)` hoặc cơ chế bootstrap thích hợp. Listener được đăng ký **chỉ bằng `@Component`** có thể chưa tồn tại khi lỗi xảy ra quá sớm trong startup.

## 6. Started, ready và trạng thái liveness/readiness

Spring Boot cung cấp `ApplicationAvailability` để biểu diễn trạng thái ứng dụng:

- `LivenessState.CORRECT`: Spring Boot coi process/application context còn hoạt động bình thường ở mức lifecycle. Trạng thái này được phát ngay sau `ApplicationStartedEvent` trong luồng thành công.
- `ReadinessState.REFUSING_TRAFFIC`: ứng dụng chưa muốn được gửi request vào. Đây là trạng thái readiness thường gặp trước khi các runner hoàn tất.
- `ReadinessState.ACCEPTING_TRAFFIC`: Spring Boot coi ứng dụng sẵn sàng nhận traffic; được phát **sau `ApplicationReadyEvent`**.

Đừng đồng nhất **liveness** và **readiness**. Một service có thể còn sống, không nên restart, nhưng đang chưa thể phục vụ request vì đang nạp dữ liệu hoặc tạm ngừng nhận tải.

Các API có thể dùng trong bean:

```java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;

// Đoạn minh họa trong class đã được Spring quản lý:
LivenessState live = availability.getLivenessState();
ReadinessState ready = availability.getReadinessState();
```

Biến `availability` trong đoạn này cần được **inject kiểu `ApplicationAvailability`** qua constructor. Đây không phải code độc lập biên dịch được khi đứng riêng. Khi quan sát trong listener của `ApplicationReadyEvent`, nhớ rằng event công bố readiness `ACCEPTING_TRAFFIC` được gửi **ngay sau** event ready; giá trị đọc *ngay trong* ready listener có thể vẫn là trạng thái trước đó, tùy cách nhận event. Nếu cần chính xác trạng thái availability, hãy lắng nghe `AvailabilityChangeEvent<ReadinessState>` hoặc đọc bean availability sau khi sự kiện chuyển trạng thái được xử lý.

### 6.1. HTTP server lắng nghe trước ready có được không?

Có thể. Khi ứng dụng web refresh context, embedded server thường được khởi động **trước** bước runner và ready. Hạ tầng có thể đã bind port trong lúc runner vẫn đang thực thi. Do đó:

- **“Port mở”** không đồng nghĩa **“Boot đã phát ready”**.
- **“Boot phát ready”** không có nghĩa bên ngoài chắc chắn định tuyến đúng: phải có health/readiness probe hoặc cơ chế tương đương và bộ điều phối thực sự sử dụng nó.
- **Readiness** là tín hiệu mong muốn để load balancer/Kubernetes quyết định có gửi traffic vào instance hay chưa.

Khi triển khai trên Kubernetes với Spring Boot Actuator, có thể dùng readiness/liveness health group. Ở môi trường ngoài Kubernetes, bật probe khi thực sự cần:

```properties
management.endpoint.health.probes.enabled=true
```

Với dependency `spring-boot-starter-actuator` và ứng dụng web, những endpoint tiêu biểu là `/actuator/health/liveness` và `/actuator/health/readiness` khi health group được cấu hình/phơi bày phù hợp. HTTP status có thể là 503 khi readiness không chấp nhận traffic và 200 khi sẵn sàng trong thiết lập mặc định phù hợp. Cần cấu hình Kubernetes/load balancer theo đúng endpoint, cổng, security và deployment; chỉ thêm Actuator không tự động làm traffic bị chặn.

### 6.2. Có nên dùng ready listener để chạy tác vụ nặng?

`ApplicationReadyEvent` là dấu mốc công bố ứng dụng sẵn sàng; listener Spring mặc định **đồng bộ**. Một ready listener mất nhiều thời gian có thể kéo dài giai đoạn phát ready và làm chậm việc công bố trạng thái `ACCEPTING_TRAFFIC`. Nếu tác vụ bắt buộc hoàn tất **trước** khi ready, runner là vị trí thể hiện ý định rõ hơn.

Nếu tác vụ có thể chạy sau khi service sẵn sàng, dùng cơ chế nền có quản lý lifecycle, lỗi và quan sát phù hợp. Không dùng `@Async` như một cách bảo đảm không còn ràng buộc startup: ứng dụng có thể được coi ready khi công việc thực sự chưa xong.

## 7. Các lỗi hiểu sai thường gặp

| Phát biểu/dấu hiệu | Vì sao dễ sai? | Kiểm tra hoặc xử lý |
| --- | --- | --- |
| “Có `Started ...` trong log, service chắc chắn ready” | Log được in trước khi runner hoàn tất | Quan sát `ApplicationReadyEvent`/readiness, kiểm tra runner |
| “`ApplicationStartedEvent` xảy ra sau mọi runner” | Event này ở **trước** runner trong Boot 3.3 | Xem thứ tự lifecycle và thí nghiệm ở trên |
| “`ApplicationRunner` luôn chạy trước `CommandLineRunner`” | Hai loại runner được sắp thứ tự chung | Gắn `@Order`/`Ordered` cho từng runner |
| “ApplicationReadyEvent xảy ra ngay khi web server bind port” | Web server có thể khởi động khi refresh context | Dùng readiness thay vì port-open làm tiêu chí |
| “Thấy `@PostConstruct` chạy nghĩa là ready” | Init của bean xảy ra trong giai đoạn tạo bean/refresh | Dùng runner hoặc ready event đúng mục đích |
| “Ứng dụng liveness CORRECT nghĩa là có thể nhận traffic” | Liveness không bằng readiness | Dùng `ReadinessState` và readiness health check |
| “Runner tạo background task rồi return, Boot sẽ đợi task đó” | Boot đợi lời gọi runner đồng bộ, không biết mọi tác vụ nền | Chờ công việc thật sự cần thiết hoặc thay đổi thiết kế |
| “Event listener trong bean nhận mọi sự kiện Boot từ đầu” | Một số sự kiện đến trước khi bean/context tồn tại | Đăng ký listener từ `SpringApplication.addListeners` cho early events |
| “Runner ném exception mà Ready vẫn phát” | Startup failure xảy ra trước mốc ready | Kiểm tra root cause, `ApplicationFailedEvent` và exit code |
| “Tắt startup INFO log đồng nghĩa tắt StartedEvent” | Logging và event publishing là hai cơ chế khác nhau | Kiểm chứng bằng listener, không suy từ console |

## 8. Thực hành kiểm tra và câu hỏi tự đánh giá

### Bài thực hành A: khẳng định thứ tự

Chạy ví dụ ở mục 4, rồi trả lời:

1. Dòng nào chứng minh context đã refresh xong? **`02 ApplicationStartedEvent`.**
2. Dòng nào chứng minh runner thứ hai đã chạy xong? **`05 CommandLineRunner...`** (trong ví dụ nó được in khi method chạy; muốn bảo đảm hoàn thành một tác vụ thực, in thêm dấu sau tác vụ).
3. Dòng nào chứng minh Spring Boot đã phát ready event? **`06 ApplicationReadyEvent`.**
4. Tại sao `07 ReadinessState.ACCEPTING_TRAFFIC` lại xuất hiện sau `06`? Vì Boot công bố availability state sau ready event.
5. Tại sao `08` nằm cuối? Vì `SpringApplication.run(...)` trả về sau các bước startup thành công.

### Bài thực hành B: đổi thứ tự runner

Thử đổi `@Order(10)` của `StartupValidation` thành `@Order(30)`. Khi chạy lại, **`CommandLineRunner` sẽ được gọi trước `ApplicationRunner`**, dù bản thân interface không thay đổi. Đây là bằng chứng thứ tự phụ thuộc `@Order`/`Ordered`, không phụ thuộc tên runner.

### Bài thực hành C: runner lỗi

Thay `StartupPreparation.run(...)` để ném exception như mục 5.2. Kiểm tra rằng:

- Started event đã có thể được phát trước lỗi.
- `ApplicationReadyEvent` và trạng thái `ACCEPTING_TRAFFIC` của startup thành công không xảy ra sau lỗi đó.
- Build/run có thể trả về exit code lỗi. Đọc exception gốc trong console để tìm nguyên nhân, không chỉ nhìn thông báo log Started.

### Câu hỏi ôn tập

**Hỏi:** Khi một service phải preload dữ liệu trước khi được gửi request, nên dùng gì?

**Đáp:** Đặt phần preload bắt buộc trong `ApplicationRunner`/`CommandLineRunner` với lỗi được xử lý rõ ràng; sau đó dùng readiness probe của hệ thống triển khai để không điều phối traffic vào instance trước mốc ready. Đảm bảo preload có giới hạn thời gian và không gây phụ thuộc vòng.

**Hỏi:** Có thể dùng `ApplicationReadyEvent` thay `ApplicationRunner` để tải dữ liệu bắt buộc không?

**Đáp:** Có thể chạy mã trong listener, nhưng về ngữ nghĩa ready event xuất hiện sau runner để công bố mốc đã sẵn sàng. Công việc bắt buộc cho trạng thái ready nên được đặt trước mốc ấy, thường bằng runner hoặc một bước startup đồng bộ thích hợp.

**Hỏi:** `ApplicationReadyEvent` có xuất hiện sau `SpringApplication.run(...)` return không?

**Đáp:** Không, trong luồng mặc định nó được gửi **trước khi** lời gọi `run` trả về; do đó một lệnh in ngay sau `run` trong `main` xuất hiện sau ready event.

**Hỏi:** Nếu một runner mất 10 giây thì dòng log Started báo thời gian 10 giây đó không?

**Đáp:** Log `Started ...` của Boot 3.3.x thường được ghi sau refresh và trước runner, nên thời gian runner không được tính vào mốc log đó. Thời gian đến `ApplicationReadyEvent` sẽ phản ánh công việc runner và những bước tiếp theo.

## 9. Ghi nhớ nhanh và nguồn tham khảo

- **`ApplicationStartedEvent`:** context đã refresh, runner **chưa** chạy.
- **Runner:** chạy **sau started, trước ready**, theo thứ tự `@Order`/`Ordered` nếu được khai báo; lỗi tại đây làm startup không hoàn tất.
- **`ApplicationReadyEvent`:** sau các runner và trước khi `SpringApplication.run` trả về bình thường.
- **`LivenessState.CORRECT`:** được công bố ngay sau started event.
- **`ReadinessState.ACCEPTING_TRAFFIC`:** được công bố ngay sau ready event.
- **Dòng INFO `Started ...`:** thông báo của logger về mốc startup, **không đồng nghĩa service đã sẵn sàng**.
- **Port mở, liveness và readiness là những dấu hiệu khác nhau**; khi vận hành, cần dùng tín hiệu readiness thực tế được bộ điều phối theo dõi.

Tài liệu chính thức để đối chiếu theo phiên bản:

- [Spring Boot 3.3 Reference — SpringApplication: Application Events, Runner, Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 Reference — Actuator Endpoints và Health/Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

Các mốc trên là contract cần nắm khi đọc log và debug startup. Với các hệ thống dùng nhiều `ApplicationContext` hoặc tùy biến listener bất đồng bộ, hãy xác định context phát event và các công việc khởi động thực sự phải hoàn tất trước khi hệ thống nhận traffic.
