# Ứng xử khi runner ném ngoại lệ trong Spring Boot

## 1. Vấn đề: một runner thất bại có làm toàn bộ startup thất bại không?

**Có.** Với luồng khởi động mặc định của Spring Boot 3.3.x, nếu một `ApplicationRunner` hoặc `CommandLineRunner` **ném exception ra khỏi phương thức `run(...)`**, Spring Boot coi đây là lỗi **khởi động ứng dụng**, không phải lỗi của một request thông thường. `SpringApplication.run(...)` không hoàn tất bình thường: Boot đi vào nhánh xử lý startup failure, phát `ApplicationFailedEvent` trong điều kiện có thể, thực hiện đóng context đã tạo và đưa ngoại lệ ra caller. Những runner nằm sau vị trí thất bại trong thứ tự thực thi sẽ không được tiếp tục gọi.

Đây là hành vi có chủ đích. Runner thường được dùng để thực hiện công việc phải hoàn tất trước khi Boot tuyên bố ứng dụng sẵn sàng phục vụ: kiểm tra cấu hình bắt buộc, xác minh dữ liệu tham chiếu hoặc hoàn thành một bước khởi tạo nghiệp vụ quan trọng. Nếu bước ấy thất bại, đánh dấu ứng dụng “ready” là nguy hiểm.

Tuy vậy, **không phải mọi lỗi trong runner đều phải làm chết ứng dụng**. Nếu việc chuẩn bị đó tùy chọn, có phương án fallback an toàn và trạng thái vận hành vẫn hợp lệ, code có thể bắt lỗi, ghi nhận và trả về thành công. Việc này cần là **quyết định thiết kế rõ ràng**, không phải cách che exception để log trông sạch.

Bài áp dụng cho **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+**; ở các phiên bản khác nên xác minh API và thứ tự lifecycle tương ứng.

## 2. Runner là gì và nó chạy ở mốc nào?

Spring Boot hỗ trợ hai interface:

```java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}

public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

Đây là chữ ký rút gọn để giải thích; không cần tạo lại hai interface này. Chúng đã thuộc `org.springframework.boot`, còn `ApplicationArguments` là API đọc các option đã được phân tích từ dòng lệnh.

- `ApplicationRunner` nhận `ApplicationArguments`, thuận tiện khi cần `getOptionNames()`, `getOptionValues(...)` hoặc các tham số không phải option.
- `CommandLineRunner` nhận mảng `String... args` tương ứng với những đối số thô truyền từ `main`.
- Cả hai là **Spring bean** mà `SpringApplication` thu thập sau khi `ApplicationContext` đã refresh.
- Spring sắp các runner qua cơ chế order của Spring, chẳng hạn `@Order` hoặc `Ordered`. **Không có quy tắc cố định rằng mọi `ApplicationRunner` phải chạy trước mọi `CommandLineRunner`**.
- Lời gọi `run` của từng runner trong chuỗi mặc định là **đồng bộ**. Một lời gọi chưa trả về hoặc đã ném exception sẽ tác động trực tiếp đến luồng startup.

Sơ đồ vòng đời bình thường:

```text
SpringApplication.run(args)
    |
    +--> Prepare Environment / ApplicationContext
    +--> Load bean definitions and refresh context
    +--> (embedded web server có thể đã bind port)
    +--> log "Started ..." nếu bật startup logging
    +--> ApplicationStartedEvent
    +--> AvailabilityChangeEvent(LivenessState.CORRECT)
    |
    +--> runner #1 (theo order)
    +--> runner #2
    +--> runner #3
    |
    +--> ApplicationReadyEvent
    +--> AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
    +--> SpringApplication.run(...) return
```

Điểm phân biệt quan trọng: **`ApplicationStartedEvent` phát trước runner, còn `ApplicationReadyEvent` phát sau khi mọi runner hoàn tất bình thường**. Tương tự, trạng thái **liveness** khác trạng thái **readiness**. Một instance có thể còn sống nhưng chưa đủ điều kiện nhận traffic.

## 3. Luồng xử lý khi runner ném ngoại lệ

Giả sử có ba runner theo thứ tự `@Order(10)`, `@Order(20)` và `@Order(30)`. Runner ở giữa ném ngoại lệ:

```text
SpringApplication.run(...)
  |
  +--> Context refreshed                     [thành công]
  +--> ApplicationStartedEvent                [đã phát]
  +--> LivenessState.CORRECT                   [đã công bố]
  |
  +--> Runner A, order=10
  |      hoàn thành                            [đã thực hiện]
  |
  +--> Runner B, order=20
  |      throw IllegalStateException          [thất bại]
  |            |
  |            +--> ngừng gọi các runner tiếp theo
  |            +--> nhánh handleRunFailure
  |                   +--> xử lý thông tin lỗi/exit code phù hợp
  |                   +--> ApplicationFailedEvent
  |                   +--> đóng context đã tạo, nếu có thể
  |                   +--> exception thoát ra caller của run(...)
  |
  +--X Runner C, order=30                     [không gọi]
  +--X ApplicationReadyEvent                  [không phát thành công]
  +--X ReadinessState.ACCEPTING_TRAFFIC       [không công bố theo đường ready]
  +--X run(...) return bình thường            [không xảy ra]
```

Đây là trình tự **startup thất bại tiêu chuẩn** của Boot 3.3.x; việc phát event và cleanup phụ thuộc tình trạng context, loại lỗi và khả năng thực thi của runtime. `ApplicationFailedEvent` không phải bảo đảm rằng mọi callback theo dõi đều luôn chạy được trong mọi kiểu crash. Nếu JVM bị kill cưỡng bức hoặc lỗi xảy ra quá sớm, vẫn có thể thiếu log hoặc không cleanup đầy đủ.

**Hệ quả có ý nghĩa vận hành:**

1. **Không còn gọi runner phía sau**: Spring không bỏ qua runner lỗi để tự tiếp tục danh sách.
2. **Một số tác động trước đó đã xảy ra**: Runner A có thể đã ghi database/file hoặc gửi message. Startup thất bại **không tự rollback toàn bộ side effect** đó.
3. **Context thường được đóng trong xử lý failure**: destruction callback của các singleton đủ điều kiện có cơ hội chạy. Nhưng không nên nhầm callback với giao dịch bù cho dữ liệu ngoài hệ thống.
4. **Không có mốc ready thành công**: `ApplicationReadyEvent` không phát ở đường này; readiness của Boot không được đưa sang `ACCEPTING_TRAFFIC` như khi startup hoàn tất.
5. **Có thể đã xuất hiện log `Started ...` trước lỗi**: dòng INFO đó là mốc sau refresh, không chứng minh runner đã thành công.

### 3.1. Exception có thể bị Spring Boot bọc lại

Method `run(...)` của runner có thể khai báo `throws Exception`. Spring Boot xử lý ngoại lệ khi gọi runner và trong một số đường đi có thể bọc nguyên nhân vào một `IllegalStateException` mang nội dung tương tự “Failed to execute ApplicationRunner” hoặc “Failed to execute CommandLineRunner”.

Vì vậy khi debug, cần phân biệt:

- **Exception bề mặt**: vị trí SpringApplication báo runner thực thi thất bại.
- **Root cause**: exception gốc trong runner, ví dụ `SQLException`, `IllegalArgumentException`, `TimeoutException` hoặc lỗi cấu hình ứng dụng.
- **Stack trace**: xem chuỗi `Caused by:` để tìm **điểm ném lỗi đầu tiên trong mã ứng dụng**, không chỉ lớp wrapper của Spring.

Đừng viết logic phụ thuộc vào chuỗi thông báo wrapper cụ thể giữa các phiên bản. Nếu cần xác định loại lỗi, sử dụng exception class hoặc causal chain được quản lý rõ ràng.

### 3.2. RuntimeException và checked exception khác nhau thế nào?

Cả `ApplicationRunner.run(...) throws Exception` và `CommandLineRunner.run(...) throws Exception` đều cho phép checked exception phát sinh (trong Java, method override có thể khai báo exception phù hợp). Không có khác biệt “checked exception thì Boot bỏ qua, unchecked exception thì Boot fail”:

- **Checked exception** thoát ra khỏi runner: startup thất bại.
- **RuntimeException** thoát ra khỏi runner: startup thất bại.
- **Error** nghiêm trọng: có thể đi vào nhánh failure hoặc khiến JVM không còn khả năng cleanup, tùy tình huống; không dùng `Error` cho kiểm soát nghiệp vụ.

Bản chất là **có ngoại lệ thoát khỏi lời gọi runner hay không**.

## 4. Ví dụ chạy được: runner B lỗi, runner C bị bỏ qua

Ví dụ nhỏ dùng **Spring Boot 3.3.13, Java 17 và Gradle**. Nó in ra thứ tự các event, runner, destruction callback và lỗi mà `main` nhận được. Đây là mô phỏng startup failure; không truy cập database, HTTP hoặc file thật, nên output do code tạo ra có thể đối chiếu được.

### 4.1. File build.gradle

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

File `settings.gradle`:

```groovy
rootProject.name = 'runner-failure-lab'
```

Trong `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

Việc tắt INFO không tắt các event. Bài dùng non-web mode để thấy rõ lifecycle. Với một web application, thông điệp thất bại và việc không đạt ready có ý nghĩa tương tự, nhưng web server có thể đã khởi động trước đó.

### 4.2. Một file Java hoàn chỉnh

Tạo file **`src/main/java/com/example/runner/RunnerFailureApplication.java`**:

```java
package com.example.runner;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class RunnerFailureApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(RunnerFailureApplication.class);
        app.addListeners(new FailureObserver());

        System.out.println("00 main: before run");

        // Chỉ bắt lỗi để demo có output dễ đọc.
        try {
            app.run(args);
            System.out.println("unexpected success");
        } catch (RuntimeException failure) {
            Throwable root = failure;
            while (root.getCause() != null) {
                root = root.getCause();
            }
            System.out.println("06 main caught: " + root.getMessage());
        }
    }

    // Đăng ký từ bootstrap để theo dõi lỗi kể cả khi context chưa tạo.
    static final class FailureObserver
            implements ApplicationListener<ApplicationFailedEvent> {

        @Override
        public void onApplicationEvent(ApplicationFailedEvent event) {
            System.out.println("04 ApplicationFailedEvent");
        }
    }

    // Bean listener đã tồn tại sau refresh.
    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("01 ApplicationStartedEvent");
    }

    @Component
    @Order(10)
    public static class ValidateConfiguration implements ApplicationRunner {

        @Override
        public void run(org.springframework.boot.ApplicationArguments args) {
            System.out.println("02 runner A: validated");
        }
    }

    @Component
    @Order(20)
    public static class LoadRequiredData implements ApplicationRunner {

        @Override
        public void run(org.springframework.boot.ApplicationArguments args) {
            System.out.println("03 runner B: failed");
            throw new IllegalStateException("required seed data missing");
        }
    }

    @Component
    @Order(30)
    public static class FinalizeStartup implements ApplicationRunner {

        @Override
        public void run(org.springframework.boot.ApplicationArguments args) {
            System.out.println("THIS MUST NOT PRINT: runner C");
        }
    }

    // Singleton bình thường để quan sát destruction.
    @Component
    public static class ShutdownObserver {

        @PreDestroy
        public void shutdown() {
            System.out.println("05 singleton @PreDestroy");
        }
    }
}
```

**Các quyết định trong ví dụ:**

- `FailureObserver` được đăng ký với `app.addListeners(...)` **trước** `run(...)`. Một listener `ApplicationFailedEvent` đặt thuần trong bean có thể không bắt được lỗi xảy ra trước khi context có bean; đăng ký bootstrap giúp quan sát nhiều loại startup failure hơn.
- `onStarted(...)` là method `@EventListener` trên application bean; nó hoạt động sau khi refresh.
- Ba class `static` lồng nhau có `@Component` và `@Order(10/20/30)`. Spring quét package `com.example.runner` và tìm các bean `ApplicationRunner` sau refresh.
- Runner B ném `IllegalStateException` cố ý để kiểm tra đường failure, không có phụ thuộc ngoài.
- `ShutdownObserver` là singleton; `@PreDestroy` giúp quan sát context được đóng khi Boot xử lý lỗi startup. Nó không thay thế cleanup cho file/database/remote side effect.
- `main` **bắt và không ném lại ngoại lệ chỉ trong thí nghiệm**. Vì thế JVM có thể kết thúc với exit code 0 dù startup không thành công. **Không copy nguyên mẫu `catch` này cho dịch vụ production**.

### 4.3. Chạy ứng dụng

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

Các dòng do **chính mã Java in ra trên stdout**, theo thứ tự với cấu hình như trên:

```text
00 main: before run
01 ApplicationStartedEvent
02 runner A: validated
03 runner B: failed
04 ApplicationFailedEvent
05 singleton @PreDestroy
06 main caught: required seed data missing
```

Spring Boot vẫn có thể in stack trace hoặc error log trên stderr (vì lỗi thật đã xảy ra), và Gradle có thể in thông tin task/build. Các dòng phụ đó không nằm trong danh sách stdout được so sánh.

Đặc biệt, sẽ **không xuất hiện** dòng:

```text
THIS MUST NOT PRINT: runner C
```

cũng như không có dòng của `ApplicationReadyEvent`, bởi runner B đã làm startup thất bại.

### 4.4. Vì sao dòng @PreDestroy có thể xuất hiện?

Trong failure handling thông thường, Boot đóng context đã được refresh. Khi context đóng, các singleton đủ điều kiện nhận destruction callback, ví dụ method `@PreDestroy` của `ShutdownObserver`. Do đó log dọn dẹp xuất hiện sau event failure và trước khi exception được trao về `main` trong ví dụ.

Điều này chỉ minh họa **cleanup của Spring-owned singleton**. Nếu runner A đã ghi một file, commit transaction, tạo một remote resource mà không gắn vào lifecycle bean, context close **không tự hoàn tác mọi việc đó**. Với `prototype`, Spring cũng không tự quản lý destruction callback cho từng instance chỉ vì context đóng.

### 4.5. Thử thay đổi để kiểm chứng

1. **Bỏ dòng `throw` trong Runner B:** Cả ba runner sẽ được gọi, Boot phát `ApplicationReadyEvent` và `SpringApplication.run(...)` trả về bình thường. Trong code demo, dòng “unexpected success” lúc đó sẽ xuất hiện; nó chỉ là nhãn dành cho bài thí nghiệm failure.
2. **Đổi `@Order(20)` của Runner B thành `@Order(40)`:** Runner C với order 30 sẽ chạy trước B và có side effect của chính nó trước khi B thất bại. Nhớ sửa nhãn log nếu cần.
3. **Cho Runner A ném exception trước B:** Runner B và Runner C đều không được gọi.
4. **Bắt lỗi ngay bên trong Runner B rồi return:** Nếu mọi runner đều trả về thành công, Boot vẫn có thể phát `ApplicationReadyEvent`. Chính xác sự khác biệt này là cơ sở để quyết định fail-fast hay graceful degradation.
5. **Bỏ `catch` trong `main`:** Exception có thể lan ra launcher, khiến run task thất bại với exit code không thành công; đây thường là tín hiệu đúng khi ứng dụng không thể hoạt động an toàn.

## 5. Khi nào nên ném ngoại lệ để fail-fast?

Runner nên fail-fast nếu nó xác minh một **điều kiện bắt buộc** để ứng dụng phục vụ đúng:

- Secret/cấu hình cần thiết không có hoặc không hợp lệ.
- Dữ liệu tham chiếu bắt buộc không thể tải và không có bản thay thế tin cậy.
- Migration hoặc schema invariant của hệ thống bắt buộc bị sai (dù việc migration thường nên do công cụ chuyên trách xử lý).
- Tài nguyên cần thiết cho mọi request không thể khởi tạo.
- Các quyền truy cập hoặc contract bảo mật quan trọng không đạt.
- Việc tiếp tục nhận traffic sẽ gây trả kết quả sai, mất dữ liệu hoặc vi phạm hợp đồng.

Khi điều kiện tiên quyết thất bại, cố chạy tiếp bằng một ứng dụng “ready giả” thường gây lỗi phân tán khó tìm hơn lỗi startup rõ ràng.

Có thể tạo exception thông báo **nguyên nhân và tác động**:

```java
@Override
public void run(ApplicationArguments args) {
    if (requiredCatalog.isEmpty()) {
        throw new IllegalStateException(
                "Cannot start: mandatory product catalog is empty");
    }
}
```

Đây là **đoạn minh họa**, không chạy độc lập: cần một runner class, import `ApplicationArguments` và một biến `requiredCatalog` đúng kiểu. Trong production, cần tránh đưa secret, password hoặc payload khách hàng vào message/stacktrace.

**Quan trọng:** “fail-fast” chỉ là lựa chọn đúng khi điều kiện đó thật sự bắt buộc. Đừng biến một endpoint monitoring tùy chọn thành điểm đơn lỗi khiến mọi instance restart vô hạn.

## 6. Khi nào nên bắt exception và tiếp tục?

Có thể xử lý lỗi trong runner rồi trả về bình thường nếu toàn bộ điều kiện sau được đáp ứng:

1. **Công việc thất bại là tùy chọn**, hoặc có fallback đã kiểm thử.
2. **Các bất biến nghiệp vụ vẫn đúng**; dữ liệu lỗi không gây kết quả sai hay mất an toàn.
3. **Trạng thái degraded được công khai** qua log/metrics/health phù hợp thay vì che lỗi.
4. **Có cách phục hồi**: retry nền có kiểm soát, refresh định kỳ hoặc thao tác vận hành.
5. **Không có side effect dở dang nguy hiểm**; nếu có thì đã có rollback/compensation phù hợp.

Ví dụ pseudo-code trong runner:

```java
@Override
public void run(ApplicationArguments args) {
    try {
        optionalSearchIndex.warmUp();
    } catch (SearchIndexUnavailableException ex) {
        log.warn("Optional index warm-up failed; using database fallback", ex);
        fallbackMode.enable();
    }
}
```

Đây là **đoạn minh họa**, cần class/import `optionalSearchIndex`, `fallbackMode`, `log` và exception thực tế. Nếu fallback thật sự đáp ứng yêu cầu phục vụ, runner có thể hoàn tất và Boot đạt mốc ready.

**Không dùng cách này với dữ liệu bắt buộc**. Câu lệnh:

```java
try {
    loadMandatoryData();
} catch (Exception ignored) {
    // Cấm kiểu xử lý này khi ứng dụng không thể hoạt động hợp lệ.
}
```

là phản ví dụ. Nó làm mất nguyên nhân lỗi và cho Boot đi tiếp tới mốc ready.

### 6.1. Ready của Boot không thay thế health check nghiệp vụ

Nếu runner bắt lỗi rồi return, Spring Boot chỉ thấy **runner hoàn tất**. Sau đó nó có thể phát `ApplicationReadyEvent` và `ReadinessState.ACCEPTING_TRAFFIC`. Điều đó không tự bảo đảm downstream service, search index hay database bên ngoài đã khỏe.

Khi readiness thực sự phụ thuộc một điều kiện có thể thay đổi theo thời gian, cân nhắc sử dụng:

- Actuator readiness group/`HealthIndicator` (khi có ứng dụng web và dependency Actuator).
- Trạng thái ứng dụng riêng, được đo bằng một probe đáp ứng hợp đồng vận hành.
- `ApplicationAvailability` nếu cần chủ động phát trạng thái readiness của ứng dụng; phải thiết kế rõ khi nào có thể nhận lại traffic.
- Cơ chế circuit breaker/fallback nếu dependency không bắt buộc.

Tách **“Boot hoàn thành startup”** khỏi **“đủ điều kiện nhận traffic theo hợp đồng hệ thống”**. Không chỉ xem port mở hoặc có log `Started ...` để quyết định.

## 7. Retry trong runner: dùng đúng mức và giới hạn

Lỗi tạm thời khi truy cập network có thể đáng retry, nhưng retry không giới hạn trong runner có thể khiến instance kẹt ở trạng thái chưa ready rất lâu. Một chiến lược tối thiểu nên có:

- **Giới hạn số lần thử** và tổng thời gian chờ.
- Phân biệt lỗi **transient** có thể retry với lỗi **permanent** như credentials sai, schema không tương thích.
- Dùng timeout cho từng I/O operation; `Thread.sleep` không giải quyết một request network có thể treo vô hạn.
- Backoff có giới hạn, cân nhắc jitter khi nhiều instance cùng khởi động để tránh “thundering herd”.
- Nếu bị interrupt, giữ nguyên interrupt signal hoặc để `InterruptedException` được truyền ra thích hợp.
- Sau khi hết retry: **ném exception** cho điều kiện bắt buộc; **fallback có quan sát** cho công việc tùy chọn.

Ví dụ logic Java 17 cho một phần thiết yếu, được thiết kế theo dependency injection:

```java
@Override
public void run(ApplicationArguments args) throws Exception {
    int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            requiredRemoteClient.checkReady(); // phải có timeout I/O riêng
            return;
        } catch (TransientRemoteException ex) {
            if (attempt == maxAttempts) {
                throw new IllegalStateException(
                        "Required remote service unavailable after retries", ex);
            }
            Thread.sleep(200L * attempt);
        }
    }
}
```

Đây là **đoạn minh họa trong một runner**, không phải file Java độc lập. `requiredRemoteClient` cần được inject, `TransientRemoteException` cần là type exception thực, và method `checkReady` cần có request timeout. `Thread.sleep` ở đây thể hiện backoff đơn giản; production có thể dùng thư viện retry có metric, jitter và deadline rõ ràng.

Nếu `Thread.sleep` bị interrupt, phương thức `run` khai báo `throws Exception` cho phép `InterruptedException` đi lên, khiến startup fail. Đừng bắt `InterruptedException` rồi bỏ qua; nếu buộc bắt, nên `Thread.currentThread().interrupt()` trước khi quyết định bước tiếp theo.

### 7.1. Vì sao không retry tất cả exception?

Một số lỗi không được retry bừa:

- `IllegalArgumentException` do cấu hình sai.
- `AuthenticationException` do credential bị thu hồi hoặc key sai.
- Validation dữ liệu bắt buộc không đạt.
- Schema migration không tương thích.
- Lỗi lập trình `NullPointerException`.

Retry các lỗi này chỉ kéo dài startup và làm nguyên nhân thực bị che bởi timeout. Tách lỗi domain cụ thể khỏi lỗi tạm thời và viết chính sách theo loại lỗi.

### 7.2. @Async trong runner không phải cách vượt qua failure

Nếu `run` chỉ mở một `CompletableFuture`, submit task lên executor hoặc khởi động thread nền rồi trả về ngay, Spring Boot **không tự chờ công việc đó**:

```java
@Override
public void run(ApplicationArguments args) {
    executor.submit(() -> loadRequiredCatalog());
    // Runner return ngay dù catalog có thể chưa nạp xong.
}
```

Đây là **phản ví dụ** với `executor` và `loadRequiredCatalog` giả định. Lỗi trong task async có thể được chứa trong `Future` hoặc báo vào handler khác, không tự trở thành exception từ runner. Boot có thể phát ready khi task còn chạy.

Nếu việc tải dữ liệu là điều kiện bắt buộc trước readiness, cần **chờ kết quả có timeout và propagate failure**, hoặc thiết kế readiness gate độc lập rõ ràng. `@Async` hay executor không tự tạo quan hệ “xong trước ready”.

## 8. Những side effect của runner trước đó không tự rollback

Giả sử startup chạy:

1. Runner A ghi một dòng đánh dấu vào database và commit.
2. Runner B gọi API ngoài, API trả lỗi và B throw.
3. Boot đóng context; runner C không được gọi.

**Dữ liệu đã commit của A vẫn có thể tồn tại**. Spring chỉ xử lý vòng đời context, không mở một giao dịch toàn cục bao trùm tất cả runner.

Hướng thiết kế an toàn:

- **Idempotency:** Runner khởi tạo dữ liệu theo key ổn định, upsert/kiểm tra tồn tại, không insert nhân bản sau mỗi restart.
- **Transaction boundary:** Các bước bắt buộc phải nguyên tử trong cùng database nên dùng transaction có phạm vi xác định, thay vì kỳ vọng toàn startup tự rollback.
- **Compensation:** Nếu đã gọi hệ thống ngoài và bước sau lỗi, cần cơ chế bù hoặc reconciliation nếu nghiệp vụ yêu cầu.
- **Checkpoint có version:** Cho phép restart chạy lại phần còn thiếu một cách có kiểm soát.
- **Không đặt migration rủi ro trong runner của mọi replica:** Khi deploy nhiều instance, tất cả có thể chạy đồng thời. Dùng công cụ migration hoặc job điều phối chuyên dụng.
- **Giới hạn thời gian:** Mọi I/O cần deadline, chứ không chỉ retry loop.
- **Quan sát nguyên nhân:** Log phase, attempt, resource ID không nhạy cảm và loại lỗi, không ghi secret.

Thử nghiệm fail/restart nhiều lần để kiểm tra runner có làm lệch dữ liệu hay không. Đây là điểm đặc biệt quan trọng trong rolling deployment và autoscaling.

## 9. Context đóng, destruction callback và tài nguyên ngoài container

Khi startup thất bại do runner, Boot cố gắng xử lý lỗi và đóng context đã refresh. Điều đó có thể dẫn tới:

- `@PreDestroy` trên singleton do container quản lý.
- `DisposableBean.destroy()` hoặc `@Bean(destroyMethod=...)` theo định nghĩa.
- Dừng các thành phần lifecycle/scheduler được container quản lý đúng cách.
- Shutdown web server và các tài nguyên đã được tích hợp với context.

Nhưng có giới hạn:

- **Bean prototype:** container thường không tự gọi destruction callback của từng instance prototype khi context đóng.
- **Tài nguyên tạo trực tiếp bằng `new`:** nếu chỉ nằm trong biến của runner, không được bean sở hữu/dọn dẹp, Spring không tự biết để gọi `close`.
- **Transaction đã commit hoặc remote side effect:** đóng context không hoàn tác chúng.
- **Đóng cưỡng bức/SIGKILL:** JVM không thể bảo đảm chạy Java callback.
- **Callback lỗi trong quá trình hủy:** cleanup có thể không hoàn tất, nên thiết kế resource có timeout, khả năng khôi phục và đóng lặp an toàn khi cần.

Nếu runner mở tài nguyên tạm thời, hãy đóng ngay trong phạm vi runner:

```java
@Override
public void run(ApplicationArguments args) throws Exception {
    try (InputStream input = Files.newInputStream(configFile)) {
        validate(input); // IOException tự propagate nếu không xử lý.
    }
}
```

Đây là **đoạn minh họa**, không phải file độc lập: `configFile` là `Path` được cung cấp từ cấu hình, `validate(InputStream)` là method ứng dụng và cần import `InputStream`, `Files`, `ApplicationArguments`. `try-with-resources` đóng stream kể cả khi validation throw.

Đừng đóng một connection pool hoặc HTTP client được một singleton khác sở hữu chỉ vì runner đang mượn nó. Quy tắc là **ai sở hữu resource phải quyết định lifetime của nó**.

## 10. ApplicationFailedEvent: quan sát lỗi, không phải công cụ chữa lỗi

Spring Boot phát `ApplicationFailedEvent` khi startup gặp lỗi và đang được xử lý. Event chứa exception và có thể chứa context (nếu đã được tạo). Cần phân biệt:

- `ApplicationStartedEvent`: context đã refresh, trước runner.
- `ApplicationReadyEvent`: sau khi runner thành công.
- `ApplicationFailedEvent`: startup đi vào đường failure.

**Một ứng dụng có thể phát cả `ApplicationStartedEvent` rồi `ApplicationFailedEvent` trong cùng lượt khởi động** nếu lỗi xảy ra ở runner. Điều này không mâu thuẫn: “started” là mốc trước runner, “ready” là sau runner.

Để quan sát các lỗi rất sớm, đăng ký listener từ bootstrap, không chỉ dựa vào `@Component`:

```java
SpringApplication app = new SpringApplication(MyApp.class);
app.addListeners(new MyFailureListener());
app.run(args);
```

Đây là đoạn minh họa; `MyFailureListener` cần triển khai `ApplicationListener<ApplicationFailedEvent>` và có implementation thực. Ví dụ runnable mục 4 dùng đúng cách này.

Có thể nghe `ApplicationFailedEvent` từ một bean trong những trường hợp context đã active (chẳng hạn lỗi runner), nhưng **không được giả định bean listener tồn tại với mọi lỗi giai đoạn đầu**. Đồng thời listener xử lý failure cũng có thể lỗi; nên ưu tiên **ghi nhận nhanh, ít side effect và không chặn vô hạn**.

Ứng dụng cần logging/observability phù hợp:

- Ghi root cause, tên runner, phase và correlation ID không nhạy cảm.
- Nếu cần alert/metric, thực hiện theo cơ chế không gây lỗi mới trong quá trình shutdown.
- Không phụ thuộc vào listener failure để “bật lại” trạng thái ready sau khi runner đã throw.
- Đừng cố gọi lại toàn bộ `SpringApplication.run(...)` bên trong failure listener để cứu startup; điều này tạo context mới và rủi ro về tài nguyên, side effect, cổng và thread.

## 11. Exit code: đừng che startup failure

### 11.1. Exception thoát ra main

Với entry point thông thường:

```java
public static void main(String[] args) {
    SpringApplication.run(MyApplication.class, args);
}
```

nếu runner fail và Boot không hoàn tất startup, ngoại lệ lan đến launcher. Một ứng dụng chạy bằng `java -jar` thông thường sẽ không kết thúc như thành công, và orchestration/build tool có thể nhận được trạng thái lỗi. Đó là tín hiệu hữu ích cho deployment.

Ngược lại, ví dụ mục 4 **bắt exception trong `main` và không throw lại** để in stdout rõ:

```java
try {
    app.run(args);
} catch (RuntimeException ex) {
    System.err.println("Startup failed: " + ex.getMessage());
    // Nếu chỉ return từ main tại đây, process có thể kết thúc 0.
}
```

Đây là **phản ví dụ trong production**. Nếu caller im lặng ăn exception, hệ điều phối có thể thấy process đã kết thúc “thành công” dù startup chưa đạt ready.

Lựa chọn production thường là **để Boot ném lỗi ra ngoài**. Nếu có thêm logging ở `main`, hãy rethrow sau khi ghi ngắn gọn:

```java
try {
    SpringApplication.run(MyApplication.class, args);
} catch (RuntimeException ex) {
    System.err.println("Startup failed: " + ex.getClass().getSimpleName());
    throw ex;
}
```

Đây là đoạn minh họa cần class `MyApplication` và import `SpringApplication`.

### 11.2. ExitCodeGenerator và exit code tùy chỉnh

Spring Boot còn có API `ExitCodeGenerator`, `ExitCodeExceptionMapper` và các cơ chế liên quan để gắn ý nghĩa riêng cho exit code. Đây là chủ đề lân cận với failure handling nhưng **không nên coi chỉ triển khai một interface là đã bảo đảm mọi launcher sẽ nhận đúng một số exit code**. Hành vi cuối cùng phụ thuộc cách ứng dụng khởi chạy, cách Spring Boot xử lý exit code và việc tiến trình kết thúc.

Nếu hạ tầng yêu cầu exit code chuẩn, hãy kiểm thử thực tế bằng đúng `java -jar`, container entrypoint hoặc build tool đang dùng. Tránh gọi `System.exit(0)` sau khi runner fail.

## 12. Web server có thể đã mở cổng nhưng service chưa ready

Với Servlet/Reactive web application, embedded web server thường được khởi tạo trong quá trình refresh context, **trước** runner. Vì vậy có tình huống:

```text
HTTP port listening
   |
   +--> ApplicationStartedEvent
   |
   +--> runner tải dữ liệu bắt buộc, sau 5 giây ném lỗi
   |
   +--> ApplicationFailedEvent
   +--> context/web server shutdown
   |
   X    ApplicationReadyEvent
```

Đừng sử dụng phép kiểm tra TCP “port đã mở” hoặc log “Started ...” làm tiêu chí duy nhất để route request. Đối với hệ thống có load balancer/Kubernetes, cần kết hợp readiness probe đúng endpoint/cổng/security với contract vận hành.

Spring Boot Actuator cung cấp nhóm health liveness/readiness khi cấu hình phù hợp. Khi startup chưa hoàn tất runner, trạng thái readiness của Boot chưa chuyển sang `ACCEPTING_TRAFFIC` theo đường ready thông thường.

Một số lưu ý:

- Actuator phải được thêm dependency và endpoint phải được cấu hình/phơi bày phù hợp.
- Readiness probe chỉ có tác dụng chặn traffic nếu **bộ điều phối thực sự sử dụng nó**.
- Nếu instance đang bind port nhưng readiness chưa thành công, ứng dụng vẫn có thể nhận request trực tiếp nếu một client bỏ qua load balancer/probe.
- Nếu dependency là điều kiện vận hành động, health/readiness indicator tùy chỉnh có thể cần phản ánh trạng thái sau startup, chứ không chỉ dựa vào runner chạy một lần.
- Liveness và readiness là hai tín hiệu khác nhau: không nên yêu cầu restart mọi lần dependency bên ngoài tạm chập chờn.

## 13. Các lỗi hiểu sai thường gặp

| Nhận định hoặc triệu chứng | Sai ở đâu? | Kiểm tra/cách xử lý |
| --- | --- | --- |
| “Có log `Started ...` tức mọi runner đã xong” | Log ở mốc sau refresh, trước runner | Theo dõi `ApplicationReadyEvent` hoặc readiness |
| “Runner B throw nhưng Boot vẫn tự gọi runner C” | Lời gọi runner đi theo chuỗi đồng bộ; lỗi ngắt startup | Xem runner order, exception gốc |
| “`CommandLineRunner` luôn chạy sau `ApplicationRunner`” | Hai loại runner được sắp thứ tự chung | Gắn `@Order`/`Ordered` rõ ràng |
| “`ApplicationStartedEvent` không thể đi cùng `ApplicationFailedEvent`” | Runner có thể fail **sau** started | Xem thứ tự event |
| “`ApplicationFailedEvent` chắc chắn do mọi bean listener nhận” | Bean có thể chưa được khởi tạo trong lỗi sớm | Đăng ký listener từ bootstrap |
| “Đóng context sẽ hoàn tác database commit của runner A” | Context destruction không phải transaction rollback toàn cục | Idempotency/transaction/compensation |
| “Bắt `Exception` rồi return để application khỏi crash luôn là tốt” | Có thể tạo ready giả với dữ liệu sai | Phân biệt bắt buộc/tùy chọn và trạng thái degraded |
| “Nếu dùng `@Async` thì lỗi task sẽ làm runner throw” | Runner có thể return trước task; exception không tự lan ngược | Await/có deadline hoặc readiness gate |
| “Tự retry liên tục thì cuối cùng chắc sẽ thành công” | Có lỗi permanent và nguy cơ deployment treo | Giới hạn attempts/deadline, phân loại lỗi |
| “Context luôn gọi `@PreDestroy` sau mọi crash” | Process có thể bị kill; context chưa tạo hoặc cleanup lỗi | Thiết kế phục hồi crash |
| “`@Order` chỉ cần có số là mọi runner sẽ chạy đủ” | Runner trước lỗi sẽ chặn runner sau | Test thứ tự và failure path |
| “Catch exception ở `main` rồi return chắc chắn vẫn exit nonzero” | Ngoại lệ bị nuốt thì process có thể exit 0 | Rethrow hoặc thiết kế exit rõ |
| “Khi runner throw thì mọi side effect đều biến mất” | Side effect trước đó có thể đã commit | Thiết kế idempotent và reconciliation |
| “Không có `ApplicationReadyEvent` thì process chắc đã chết ngay lập tức” | Đang có giai đoạn failure reporting/cleanup | Quan sát startup state, process và shutdown |

## 14. Checklist debug khi startup dừng ở runner

1. **Xác định đúng phase:** log/trace có `ApplicationStartedEvent` chưa? Nếu có mà chưa thấy ready, kiểm tra runner và ready listener.
2. **Xác định runner lỗi:** đọc stacktrace phần “Failed to execute ...Runner”, tìm class/method `run(...)` ứng dụng và root `Caused by`.
3. **Kiểm tra thứ tự:** `@Order`, `Ordered` và các bean cùng interface; đừng giả định tên class quyết định thứ tự.
4. **Xem tác động của runner trước lỗi:** file/database/message đã ghi chưa? Khởi động lại có làm lặp hay mất nhất quán không?
5. **Phân loại lỗi:** validation/config permanent, network transient, permission, schema, timeout hay lỗi code.
6. **Kiểm tra retry:** có timeout, attempt limit, backoff và propagation của lỗi cuối cùng không?
7. **Kiểm tra lỗi bị nuốt:** có `catch (Exception)` trống, `onErrorResume`/fallback thiếu điều kiện hoặc `Future` không được await không?
8. **Kiểm tra failure event và cleanup:** `ApplicationFailedEvent` có đến listener đăng ký sớm không? Singleton resource có shutdown hợp lệ không?
9. **Kiểm tra readiness trong triển khai:** load balancer/Kubernetes có thể nhìn thấy port mở trước ready? Có readiness probe đúng không?
10. **Kiểm tra process exit code:** thử bằng launcher thực (`java -jar`, container, Gradle), chú ý đoạn catch ở `main`.
11. **Kiểm tra multi-instance deployment:** runner có chạy song song ở mỗi replica và gây race/migration trùng không?
12. **Bổ sung test cho failure path:** kiểm chứng runner sau không gọi, ready không phát, side effects có thể retry an toàn và log có nguyên nhân hành động được.

Ghi log vừa đủ: tên runner, phase, loại lỗi, số lần thử, duration, context/instance ID. Không dump secret, credentials, token, thông tin cá nhân hay toàn bộ environment.

## 15. Tự đánh giá

**Câu 1.** Runner A `@Order(10)` thành công, Runner B `@Order(20)` throw, Runner C `@Order(30)` chưa gọi. Có thể xem startup thành công không?

**Đáp:** Không. Boot đi vào xử lý startup failure; runner C không tiếp tục, không phát `ApplicationReadyEvent` theo đường startup thành công.

**Câu 2.** Vì sao vẫn có thể thấy log “Started ExampleApplication” trước lỗi runner?

**Đáp:** Vì log started và `ApplicationStartedEvent` đến sau refresh nhưng **trước** lúc gọi runner.

**Câu 3.** Spring Boot sẽ tự rollback transaction đã commit trong runner trước đó?

**Đáp:** Không. Mỗi transaction/side effect có ranh giới riêng. Cần thiết kế idempotency, transaction hoặc compensation cụ thể.

**Câu 4.** Nếu một runner bắt lỗi của thao tác bắt buộc rồi return, điều gì có thể xảy ra?

**Đáp:** Boot có thể tiếp tục gọi các runner sau và báo ready dù điều kiện tiên quyết chưa đạt. Đây là hành vi nguy hiểm nếu dịch vụ không có fallback đúng.

**Câu 5.** `ApplicationFailedEvent` có thể xảy ra sau `ApplicationStartedEvent` không?

**Đáp:** Có. Runner có thể thất bại sau mốc started; event failure phản ánh startup cuối cùng không hoàn tất.

**Câu 6.** Một runner submit tác vụ nền rồi return. Nếu tác vụ nền throw, `SpringApplication.run` có chắc cũng throw không?

**Đáp:** Không. Ngoại lệ nằm ở luồng hoặc future khác, không tự làm thất bại lời gọi runner đồng bộ. Nếu tác vụ là điều kiện bắt buộc, phải chờ và propagate lỗi đúng cách.

**Câu 7.** Nên làm gì với lỗi transient khi runner cần kết nối downstream bắt buộc?

**Đáp:** Dùng I/O timeout, retry hữu hạn có backoff/jitter hợp lý; sau khi hết ngưỡng, propagate lỗi startup, không retry vô hạn.

**Câu 8.** Vì sao `@PreDestroy` của singleton có thể chạy sau runner failure nhưng không đủ để bảo đảm dữ liệu nhất quán?

**Đáp:** Context được đóng khi xử lý failure nên callback có thể chạy. Nhưng callback không tự đảo ngược các giao dịch đã commit, remote side effect hay crash do SIGKILL.

**Câu 9.** Nếu cần readiness khác với việc runner return, nên dùng công cụ gì?

**Đáp:** Readiness health checks/Actuator, `ApplicationAvailability` và orchestration probe thích hợp, dựa trên điều kiện thực sự phục vụ được.

**Câu 10.** Vì sao không nên nuốt exception ở `main` trong production?

**Đáp:** Launcher có thể nhận exit code thành công giả dù ứng dụng không hoạt động; nên để exception propagate hoặc dùng chiến lược exit code đã kiểm thử.

## 16. Tóm tắt và tài liệu tham khảo

**Cần ghi nhớ:**

- **Runner throw ra ngoài → Spring Boot 3.3.x xử lý như startup failure.** Runner phía sau không được gọi, `ApplicationReadyEvent` không xảy ra, `SpringApplication.run(...)` không return bình thường.
- **Started không đồng nghĩa ready:** `ApplicationStartedEvent` và log started có thể đã xuất hiện trước runner lỗi.
- **Failure reporting và cleanup có giới hạn:** `ApplicationFailedEvent` có thể được phát; singleton destruction callback có thể được gọi khi context đóng. Không nhầm điều này với rollback toàn bộ side effect.
- **Fail-fast cho điều kiện bắt buộc, fallback có quan sát cho điều kiện tùy chọn.** Tránh nuốt lỗi và báo ready sai.
- **Retry có giới hạn, I/O timeout, idempotency và exit code đúng** là những yếu tố vận hành cần thiết.
- **Không đưa công việc bắt buộc ra nền rồi return** nếu vẫn muốn startup/readiness phụ thuộc kết quả công việc ấy.

Nguồn tham khảo chính thức:

- [Spring Boot 3.3 — SpringApplication: Application Events and Listeners / CommandLineRunner and ApplicationRunner](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html).
- [Spring Boot 3.3 — SpringApplication Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html).
- [Spring Boot 3.3 — ApplicationFailedEvent Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html).
- [Spring Boot 3.3 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html).
- [Spring Boot 3.3 — Actuator Health/Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Một thông báo exception hữu ích không chỉ nói **runner nào thất bại**, mà còn nói **điều kiện bắt buộc nào chưa đạt, tác động trước đó có thể đã xảy ra và startup có nên tiếp tục hay không**. Thiết kế rõ những ranh giới này giúp ứng dụng khởi động và triển khai an toàn hơn.
