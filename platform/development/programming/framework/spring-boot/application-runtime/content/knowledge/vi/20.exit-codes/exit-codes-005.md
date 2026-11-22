# Ngoại lệ cung cấp mã thoát và ExitCodeExceptionMapper trong Spring Boot

## Mục tiêu học tập

Một ứng dụng Spring Boot dạng CLI, batch job hoặc worker có thể kết thúc do **lỗi nghiệp vụ**, **lỗi cấu hình** hoặc **lỗi hạ tầng**. Hệ điều hành và công cụ điều phối thường chỉ nhìn thấy **mã thoát tiến trình** (*process exit status*), trong khi log Java chứa nhiều chi tiết về exception. Để phân biệt các trường hợp, Spring Boot cung cấp cơ chế lấy mã thoát từ **ngoại lệ triển khai `ExitCodeGenerator`** và từ một **bean `ExitCodeExceptionMapper`**.

Bài học thuộc **Spring Boot Application Runtime → Mã thoát**, tập trung đúng vào hai cơ chế khi ứng dụng gặp exception, đồng thời giải thích mối quan hệ với `SpringApplication.exit(...)`, `System.exit(...)` và `ExitCodeEvent`.

Sau bài này, bạn có thể:

1. Giải thích vai trò của mã thoát 0 và mã khác 0 đối với shell, CI/CD, container, batch scheduler.
2. Tạo một exception triển khai `org.springframework.boot.ExitCodeGenerator` và định nghĩa `getExitCode()`.
3. Khai báo một bean `org.springframework.boot.ExitCodeExceptionMapper` để ánh xạ **loại exception có sẵn** sang mã thoát.
4. Hiểu tại sao runner exception thường được Boot **bọc** trong một exception khác, và cách duyệt `getCause()` mà không chỉ kiểm tra exception ngoài cùng.
5. Nắm thứ tự chọn mã trong **đường startup failure của Spring Boot 3.3.13**: mappers trước; nếu chúng không trả mã khác 0 thì tìm exception triển khai `ExitCodeGenerator` trong chuỗi nguyên nhân.
6. Phân biệt `ExitCodeGenerator` là một **bean khi gọi `SpringApplication.exit`** với `ExitCodeGenerator` được triển khai **trên exception** khi startup thất bại.
7. Viết và chạy một project Java 17+ / Spring Boot 3.3.13, quan sát `ExitCodeEvent` và mã thoát thực từ lệnh `java -jar`.
8. Hiểu giới hạn khi context chưa active, lỗi sau khi ứng dụng đã ready, exceptions trên background thread, nhiều mapper, signal termination và phạm vi mã thoát.
9. Thiết kế bảng mã lỗi bền vững để các job scheduler nhận diện retryable/non-retryable failures.

**Phạm vi phiên bản:** Spring Boot **3.3.13**, Spring Framework 6.1.x, Java 17+. Các đoạn ví dụ khác với project hoàn chỉnh sẽ được ghi rõ là **snippet minh họa**.

## 1. Exit code là gì, và vì sao log exception chưa đủ?

Khi một tiến trình Java kết thúc, JVM trả một số nguyên cho môi trường đã khởi chạy nó. Theo quy ước rất phổ biến:

- **`0`**: tiến trình hoàn tất thành công theo hợp đồng ứng dụng.
- **Mã khác 0**: có lỗi, thất bại hoặc trạng thái đặc biệt mà caller cần xử lý.

Tuy nhiên, bản thân Java và Spring Boot **không áp đặt một từ điển nghiệp vụ chung** nói rằng 17 luôn là lỗi input hoặc 23 luôn là lỗi validation. Ứng dụng phải định nghĩa quy ước của chính mình và tài liệu hóa với bên điều phối.

Ví dụ một batch scheduler:

~~~text
exit 0  -> job thành công, không cần retry
exit 17 -> đầu vào không hợp lệ, cần người gửi sửa dữ liệu
exit 23 -> rule nghiệp vụ không thỏa, báo lỗi cho operator
exit 29 -> chính sách ánh xạ ưu tiên từ mapper
exit 1  -> lỗi chung hoặc mã mặc định của runtime/launcher
~~~

Các giá trị `17`, `23`, `29` trong bài là **quy ước của project mẫu**, không phải bảng mã được Spring Boot định nghĩa sẵn.

### Exception và exit status phục vụ hai đối tượng khác nhau

| Thông tin | Người dùng chính | Ví dụ |
| --- | --- | --- |
| Exception class | Java code, error handler, framework | `IllegalArgumentException` |
| Exception message | Người vận hành và log | “Missing input file” |
| Cause chain | Chẩn đoán nhiều tầng | `IllegalStateException → DomainException` |
| Stack trace | Debugging code | Vị trí dòng ném lỗi |
| Exit code | Shell, systemd, CI, scheduler, container runtime | `17` |
| `ExitCodeEvent` | Listener ở trong Spring application context | Exit code `17` được xác định |

**Một exception không tự thay thế mã thoát.** Không phải tất cả exception đều mang một số; trong nhiều chương trình, nếu `main` kết thúc bằng unchecked exception không xử lý, OS thường thấy mã thất bại chung, không phân biệt được nghiệp vụ.

## 2. Hai interface chủ đạo

Spring Boot định nghĩa hai hợp đồng khác nhau trong package `org.springframework.boot`.

### ExitCodeGenerator: đối tượng tự cung cấp mã

~~~java
@FunctionalInterface
public interface ExitCodeGenerator {
    int getExitCode();
}
~~~

Đây là **chữ ký minh họa**, không cần tự tạo interface khi viết project thật. Một bean hoặc một exception có thể implements `ExitCodeGenerator`.

Trường hợp exception:

~~~java
public class DataRejectedException
        extends RuntimeException implements ExitCodeGenerator {

    public DataRejectedException(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 23;
    }
}
~~~

Đây là class minh họa, cần import `org.springframework.boot.ExitCodeGenerator`. Khi loại exception này tham gia đường lỗi startup mà Boot xử lý, framework có thể lấy `getExitCode()` để xác định mã.

**Ưu điểm:** Loại lỗi nghiệp vụ sở hữu sẵn exit code; module bên ngoài không phải duy trì một mapping lớn chỉ cho exception này.

**Giới hạn:** Bạn phải có quyền sửa hoặc tạo class exception để implements interface. Ngoại lệ của JDK hoặc thư viện bên thứ ba thường không thể chỉnh sửa.

### ExitCodeExceptionMapper: ánh xạ exception thành mã

~~~java
@FunctionalInterface
public interface ExitCodeExceptionMapper {
    int getExitCode(Throwable exception);
}
~~~

Đây cũng là **chữ ký minh họa**, không phải file phải tự tạo. Mapper nhận một `Throwable` rồi trả một `int`:

- Trả một mã **khác 0** khi mapper áp dụng cho lỗi này.
- Trả **`0`** khi mapper không có mapping cho lỗi đang xét, để những cơ chế khác có thể tiếp tục quyết định.

Ví dụ một bean:

~~~java
@Bean
ExitCodeExceptionMapper exitCodeExceptionMapper() {
    return exception -> {
        Throwable current = exception;

        while (current != null) {
            if (current instanceof IllegalArgumentException) {
                return 17;
            }
            current = current.getCause();
        }

        return 0;
    };
}
~~~

Đoạn này là **snippet cấu hình**, cần import `@Bean` và interface, đặt trong một class `@Configuration` hoặc `@SpringBootApplication`. Nó minh họa kỹ thuật duyệt cause chain; project hoàn chỉnh sẽ chỉ ánh xạ **loại exception nghiệp vụ cụ thể**, tránh map mọi `IllegalArgumentException` thành lỗi dữ liệu nếu nó có thể là bug lập trình.

### So sánh hai chiến lược

| Tiêu chí | Exception implements `ExitCodeGenerator` | Bean `ExitCodeExceptionMapper` |
| --- | --- | --- |
| Vị trí logic | Ngay trên exception class | Trong một bean Spring |
| API | `int getExitCode()` | `int getExitCode(Throwable)` |
| Phải sửa class exception? | Có, hoặc tạo subtype | Không |
| Phù hợp exception bên thứ ba? | Không thuận tiện | Phù hợp |
| Có thể xem nguyên nhân ngoài cùng và các cause? | Boot tìm trong cause chain ở fallback | Mapper nhận Throwable và tự quyết định có duyệt cause hay không |
| Phụ thuộc context active khi startup fail? | Exception fallback không đòi mapper bean | Mapper bean chỉ được dùng trong điều kiện context phù hợp |
| Dùng khi `SpringApplication.exit(context)` thành công? | Có nếu là **bean ExitCodeGenerator** hoặc được truyền làm argument | Không phải đường xử lý exception mặc định của `exit(context)` |
| Vai trò chính | Lỗi tự biết mã của mình | Chính sách ánh xạ lỗi sang mã ở cấp ứng dụng |

**Cần nhớ:** `ExitCodeGenerator` là một interface tái sử dụng trong hai ngữ cảnh; không có nghĩa một exception được ném ở bất kỳ thread nào cũng làm JVM lập tức thoát bằng đúng mã đó.

## 3. Mã thoát được xử lý ở giai đoạn nào của startup?

Trong Spring Boot, một lần startup thông thường đi qua:

~~~text
SpringApplication.run(...)
    |
    +-- Environment / bootstrap
    +-- ApplicationContext được tạo và refresh
    +-- ApplicationStartedEvent
    +-- ApplicationRunner và CommandLineRunner
    +-- ApplicationReadyEvent
    +-- SpringApplication.run trả về context
~~~

Nếu một bước trong `run(...)` gặp lỗi, Boot đi qua nhánh **startup failure**:

~~~text
Failure Throwable trong SpringApplication.run
    |
    +-- handleRunFailure(...)
         |
         +-- Xác định exit code từ exception
         |      |
         |      +-- context active?
         |      |      |
         |      |      +-- Có: gọi ExitCodeExceptionMapper beans
         |      |                  |
         |      |                  +-- Kết quả non-zero -> sử dụng mã đó
         |      |                  +-- Kết quả 0 -> thử cách tiếp
         |      |
         |      +-- Tìm ExitCodeGenerator trên Throwable
         |             hoặc trên các cause
         |             |
         |             +-- Có -> gọi getExitCode()
         |             +-- Không -> không có custom non-zero
         |
         +-- Nếu non-zero: có thể phát ExitCodeEvent
         +-- Ghi nhận mã cho Boot exception handler nếu khả dụng
         +-- Xử lý ApplicationFailedEvent / error report
         +-- Đóng context khi có thể
         +-- Ném lỗi ra ngoài lời gọi SpringApplication.run(...)
~~~

Sơ đồ thể hiện thứ tự xử lý **trong nhánh lỗi startup của Spring Boot 3.3.13**, không phải toàn bộ từng dòng mã nội bộ. Dựa trên implementation 3.3.13, Boot thử mapper trước, rồi fallback sang ngoại lệ có `ExitCodeGenerator` nếu mapper cho 0. <escape>“Có thể”</escape> ở `ExitCodeEvent`/handler rất quan trọng vì lỗi có thể xảy ra trước khi có context hoạt động hoặc trong một môi trường không có exception handler JVM mong đợi.

### Context active mới có thể lấy mapper bean

`ExitCodeExceptionMapper` được đăng ký dưới dạng Spring bean. Khi failure xảy ra:

- **Sau refresh, trong runner:** Context thường đã active, mapper bean có thể được tìm và sử dụng.
- **Trước khi context tạo xong hoặc khi context không active:** Không nên giả định BeanFactory có thể cung cấp mapper. Spring Boot 3.3 kiểm tra context active trước khi tìm các mapper.
- **Exception implements `ExitCodeGenerator`:** Cơ chế fallback có thể tìm mã trực tiếp trên exception hoặc cause, ngay cả khi không có mapper bean để dùng.

Đây là lý do ví dụ runnable ở mục 8 tạo lỗi trong `ApplicationRunner`: context đã refresh, giúp chứng minh mapper bean được hoạt động đúng vai trò.

## 4. Cause chain: tại sao mapper thường phải duyệt getCause()?

Trong code doanh nghiệp, một exception nghiệp vụ có thể đi qua nhiều tầng:

~~~text
IllegalStateException:
  "Failed to execute ApplicationRunner"
     |
     +-- cause: InvalidInputException:
          "input.csv has invalid format"
~~~

Khi một `ApplicationRunner` hoặc `CommandLineRunner` throw, Spring Boot có thể bọc lỗi bằng một exception gắn thông tin callback thất bại. Do đó mapper không nhất thiết nhận trực tiếp `InvalidInputException` ở mức ngoài cùng.

Anti-pattern:

~~~java
return throwable -> throwable instanceof InvalidInputException
        ? 17
        : 0;
~~~

Nếu `throwable` là một `IllegalStateException` chứa `InvalidInputException` ở `getCause()`, biểu thức trên trả 0 dù nghiệp vụ mong mã 17.

### Giải pháp: duyệt toàn bộ cause chain

~~~java
static boolean hasCause(
        Throwable original, Class<? extends Throwable> type) {

    for (Throwable cursor = original;
            cursor != null;
            cursor = cursor.getCause()) {

        if (type.isInstance(cursor)) {
            return true;
        }
    }

    return false;
}
~~~

Đoạn code là helper minh họa chưa độc lập. Nó kiểm tra cả Throwable ngoài cùng và các cause ở dưới. Trong tình huống bình thường, chuỗi nguyên nhân có điểm kết thúc `null`.

Nếu muốn phòng ngừa exception tùy biến có **cause tự tham chiếu hoặc cycle** ngoài quy tắc khởi tạo thông thường của Java, có thể dùng set theo identity để không lặp vô hạn. Không cần biến đoạn code dạy học thành một exception framework phức tạp nếu input thuộc quyền kiểm soát của ứng dụng.

### getCause khác getSuppressed

Một `Throwable` có thể có:

- `getCause()`: exception làm nguyên nhân.
- `getSuppressed()`: exception phụ, ví dụ lỗi trong `close()` khi thân `try-with-resources` đã lỗi.

Spring Boot 3.3 trong fallback mã trên exception sẽ đi theo **cause chain**, không tự đi qua mọi suppressed exception. Mapper do bạn viết cũng cần quyết định có tìm trong suppressed hay không. Thường **không nên lấy một lỗi cleanup phụ** làm mã nghiệp vụ chính nếu root cause đã rõ.

### Đừng dùng message để phân loại khi có type rõ ràng

Code như:

~~~java
if (exception.getMessage().contains("timeout")) {
    return 17;
}
~~~

dễ lỗi vì message có thể `null`, thay đổi theo thư viện, ngôn ngữ hoặc chứa dữ liệu người dùng. Nên ưu tiên **exception type**, error code domain, structured metadata hoặc một contract riêng.

## 5. Khi mapper và exception cùng cung cấp mã, ai thắng?

Đây là điểm dễ trả lời sai nếu chỉ đọc hai interface.

Trong **đường startup failure của Spring Boot 3.3.13**, implementation chọn:

1. Lấy các `ExitCodeExceptionMapper` bean khi context active và hỏi mã cho throwable.
2. Nếu mapper trả được **mã khác 0**, sử dụng mã đó.
3. Nếu kết quả mapper là 0, tìm exception triển khai `ExitCodeGenerator` trong chuỗi `getCause()` và lấy `getExitCode()`.
4. Nếu không tìm được mã khác 0, framework không có custom non-zero từ hai cơ chế này; JVM/launcher thường cho trạng thái thất bại chung khi uncaught exception.

Ví dụ:

~~~text
Exception implement ExitCodeGenerator: 23
ExitCodeExceptionMapper cho cùng lỗi: 29
----------------------------------------
Mã Spring Boot xác định khi context active: 29
~~~

**Không nhầm ưu tiên này với `SpringApplication.exit(context)`**, nơi Boot thu thập các generator beans/arguments, không phải cùng nhánh mapping throwable trong startup failure.

### Nhiều mapper

Một ứng dụng có thể có hơn một bean `ExitCodeExceptionMapper`. Khi đó cần:

- Tránh hai mapper cùng tuyên bố match cho một loại lỗi mà lại trả hai mã khác nhau.
- Nếu có thứ tự ưu tiên, định nghĩa và kiểm chứng ordering (`Ordered`/`@Order` nơi áp dụng).
- Đưa mapping chuyên biệt trước mapping tổng quát hoặc gom quy tắc về một mapper tập trung.
- Mỗi mapper trả **0 cho lỗi không thuộc phạm vi của nó**.
- Không viết mapper “bắt mọi Throwable và trả 1” ở đầu rồi kỳ vọng mapper chuyên biệt sau vẫn được quyền phân loại.

Nguyên tắc Spring Boot khi có nhiều exit-code generators là **chọn mã khác 0 đầu tiên theo thứ tự được xác định**, không tự lấy min/max hoặc cộng mã lại.

### Trả 0 có nghĩa gì?

Với `ExitCodeExceptionMapper`, trả 0 là **không có mapping khác 0 từ mapper đó**. Nó không “nuốt” một exception và không làm `SpringApplication.run` trở thành thành công. Nếu tất cả mapper đều 0 mà cause có `ExitCodeGenerator`, fallback vẫn có thể trả mã khác 0.

Nếu một mapper có logic:

~~~java
return exception -> 0;
~~~

thì mapper đó không cung cấp mã lỗi phân biệt nào; nó không tự đảm bảo OS nhận mã 0 khi startup throw exception.

## 6. ExitCodeGenerator trên bean khác với trên exception

Ví dụ Spring Boot cho phép khai báo một bean:

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 42;
}
~~~

Và gọi:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

Đây là **hai snippet minh họa**, cần import `ExitCodeGenerator`, `Bean`, `SpringApplication`, `ConfigurableApplicationContext` và class `MyApplication`. Không ghép chúng nguyên xi vào project runnable mục 8.

Đường này có ý nghĩa khi **context đã chạy được** và application muốn kết thúc có chủ đích, ví dụ một batch task đã hoàn thành nhưng kết quả cần báo một trạng thái khác 0.

### Ba vai trò khác nhau

| API | Đầu vào | Khi dùng |
| --- | --- | --- |
| `Exception implements ExitCodeGenerator` | Chính exception khi xảy ra lỗi startup | Exception biết mã của mình |
| `@Bean ExitCodeExceptionMapper` | Throwable đang làm startup fail | Ánh xạ loại exception thành mã |
| `SpringApplication.exit(context, generators...)` | ApplicationContext + optional ExitCodeGenerator | Tính mã và đóng context sau khi application đã chạy |

`SpringApplication.exit(...)` **trả về một `int`**; nó đóng context nếu có thể, nhưng **không tự bắt hệ điều hành nhận mã đó**. Muốn trả exit status cho tiến trình, main phải truyền nó tới `System.exit(code)` hoặc cơ chế điều khiển process tương đương.

Ngược lại, khi một exception không được xử lý thoát khỏi `main`, đường uncaught-exception/Boot exception handler có thể ảnh hưởng mã thoát mà không có dòng `System.exit(...)` rõ ràng do bạn viết. Hãy chạy từ một JVM riêng và kiểm tra mã thật thay vì suy diễn từ lời gọi API.

### Vì sao không gọi SpringApplication.exit(null)?

`SpringApplication.exit(context)` yêu cầu `ApplicationContext` hợp lệ, không nhận `null` để xử lý lỗi bootstrap. Nếu `SpringApplication.run(...)` throw trước khi trả context, bạn **không có một context thành công để truyền cho `exit`**. Với startup failure, framework đã có đường `handleRunFailure(...)` riêng.

## 7. Quy ước mã thoát cho một CLI/batch application

Ví dụ một hệ thống nhập dữ liệu:

| Mã | Ý nghĩa đề xuất | Retry tự động? |
| --- | --- | --- |
| `0` | Xử lý thành công | Không |
| `17` | File input hoặc request schema không hợp lệ | Thường không; sửa input |
| `23` | Một business rule bắt buộc bị vi phạm | Phụ thuộc nghiệp vụ |
| `29` | Mapping chính sách override mã từ exception | Theo chính sách override |
| `1` | Lỗi chưa phân loại hoặc exception không được xử lý | Có thể cần điều tra trước khi retry |

Đây là **bảng quy ước minh họa** cho project dưới. Trong production, nhiều loại lỗi như timeouts, rate limit và unavailable dependency có thể đáng retry, nhưng không nên mặc định mọi mã non-zero đều retry vô hạn.

### Chọn mã có tính di động

Trên nhiều hệ Unix-like, shell chỉ hiển thị **8 bit thấp** của exit status thông thường: mã lớn có thể bị biến đổi khi quan sát từ `$?`. Để giảm bất ngờ giữa nền tảng/runner, các ví dụ dùng những mã dương nhỏ như 17, 23, 29.

**Không dựa vào mã âm hoặc mã lớn hơn 255** nếu cần tương thích nhiều môi trường. Trên Windows, quá trình xử lý exit code có khác biệt; nên document và test theo nền tảng của tổ chức.

### Tránh đụng mã dành riêng

Một số shell dùng `126` cho “command cannot execute”, `127` cho “command not found”, và `128 + signal` cho tiến trình kết thúc bởi tín hiệu. Với job chạy qua shell/script, dùng mã do ứng dụng định nghĩa trong dải nhỏ, tránh trùng các mã đặc biệt nếu có thể.

## 8. Project runnable: hai chiến lược và thứ tự ưu tiên

Dự án **Java 17+ / Spring Boot 3.3.13 / Gradle**, không cần database hay web server. Các lỗi được cố ý ném từ một `ApplicationRunner` sau khi context refresh, giúp `ExitCodeExceptionMapper` đã là bean trong một context active.

Các mode:

- `success`: runner hoàn tất, main đóng context, process kết thúc bình thường.
- `exception`: ném `RuleViolationException implements ExitCodeGenerator`, trả mã **23**.
- `mapped`: ném `InvalidInputException` bình thường; mapper trả mã **17**.
- `both`: ném `OverrideRuleException implements ExitCodeGenerator` có mã 23, nhưng mapper ánh xạ thành **29**; mã mapper được ưu tiên khi context active.
- `unknown`: ném exception không được mapper nhận diện và không implements generator; có lỗi startup, nhưng không có custom exit code từ hai cơ chế trong ví dụ.

### 8.1. Cấu trúc project

~~~text
exit-exception-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/exitcode/
    └── ExitCodeDemoApplication.java
~~~

**Tệp `settings.gradle`:**

~~~groovy
rootProject.name = 'exit-exception-demo'
~~~

**Tệp `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.exitcode.ExitCodeDemoApplication'
}
~~~

Bản demo cần Gradle tương thích với Spring Boot 3.3 và JDK 17 hoặc mới hơn. Nếu dependencies chưa có trong cache, cần truy cập Maven Central. Project không sinh Gradle Wrapper; bạn có thể dùng `gradle` đã cài hoặc tạo wrapper riêng.

### 8.2. Toàn bộ mã Java

**Tệp `src/main/java/com/example/exitcode/ExitCodeDemoApplication.java`:**

~~~java
package com.example.exitcode;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.ExitCodeEvent;
import org.springframework.boot.ExitCodeExceptionMapper;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ExitCodeDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ExitCodeDemoApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN: application ready");
        }

        System.out.println("MAIN: normal exit");
    }

    @Bean
    ApplicationRunner demoRunner(
            @Value("${demo.mode:success}") String mode) {

        return args -> {
            switch (mode) {
                case "success" -> {
                    System.out.println("RUNNER: success");
                }
                case "exception" -> {
                    System.out.println("RUNNER: exception");
                    throw new RuleViolationException(
                            "Business rule did not pass");
                }
                case "mapped" -> {
                    System.out.println("RUNNER: mapped");
                    throw new InvalidInputException(
                            "Input format is invalid");
                }
                case "both" -> {
                    System.out.println("RUNNER: both");
                    throw new OverrideRuleException(
                            "Mapping should win");
                }
                default -> {
                    System.out.println("RUNNER: unknown");
                    throw new IllegalStateException(
                            "Unknown demo.mode: " + mode);
                }
            }
        };
    }

    @Bean
    ExitCodeExceptionMapper exceptionMapper() {
        return exception -> {
            // Runner errors may have an outer IllegalStateException.
            for (Throwable current = exception;
                    current != null;
                    current = current.getCause()) {

                if (current instanceof InvalidInputException) {
                    return 17;
                }

                if (current instanceof OverrideRuleException) {
                    return 29;
                }
            }

            // No mapping: let Boot try ExitCodeGenerator in causes.
            return 0;
        };
    }

    @EventListener
    public void onExitCode(ExitCodeEvent event) {
        System.out.println(
                "EVENT: exit code=" + event.getExitCode());
    }

    public static final class RuleViolationException
            extends RuntimeException implements ExitCodeGenerator {

        public RuleViolationException(String message) {
            super(message);
        }

        @Override
        public int getExitCode() {
            return 23;
        }
    }

    public static final class InvalidInputException
            extends RuntimeException {

        public InvalidInputException(String message) {
            super(message);
        }
    }

    public static final class OverrideRuleException
            extends RuntimeException implements ExitCodeGenerator {

        public OverrideRuleException(String message) {
            super(message);
        }

        @Override
        public int getExitCode() {
            return 23;
        }
    }
}
~~~

### 8.3. Giải thích logic theo từng mode

**`success`**

- `ApplicationRunner` chạy và in `RUNNER: success`.
- Không ném exception, SpringApplication đạt ready và trả context.
- `main` in `MAIN: application ready`, đóng context qua `try-with-resources` rồi in `MAIN: normal exit`.
- Không gọi `SpringApplication.exit(context)` vì ví dụ không khai báo exit-code generator bean cho đường thành công.
- Process bình thường kết thúc với mã 0 khi JVM không còn non-daemon thread giữ lại.

**`exception`**

- Runner ném `RuleViolationException` với `getExitCode() == 23`.
- Mapper không nhận loại này, trả 0.
- Boot kiểm tra exception/cause chain; tìm thấy `ExitCodeGenerator` và lấy 23.
- Nếu context vẫn active, `ExitCodeEvent` với 23 được phát.
- `SpringApplication.run` không trả về bình thường; không in `MAIN: application ready` hoặc `MAIN: normal exit`.

**`mapped`**

- Runner ném `InvalidInputException`. Exception không implements `ExitCodeGenerator`.
- Mapper duyệt cause chain và trả 17.
- Boot dùng 17 nếu context active. Exception không cần sửa để thêm interface.
- Ví dụ này cũng xác nhận mapper không chỉ so sánh throwable ngoài cùng.

**`both`**

- Runner ném `OverrideRuleException` với `getExitCode() == 23`.
- Mapper cũng nhận exception đó và trả 29.
- Với context active, Boot lấy kết quả mapper non-zero trước; dùng **29** thay vì 23.
- Đây là thứ tự trong **SpringApplication startup-failure path**, không phải thứ tự chọn các bean `ExitCodeGenerator` khi gọi `SpringApplication.exit`.

**`unknown`**

- Runner ném `IllegalStateException` không phải loại mà mapper nhận diện.
- Mapper trả 0, exception không có `ExitCodeGenerator` trong cause chain.
- Không có custom `ExitCodeEvent` với mã khác 0 được xác định từ hai cơ chế.
- JVM thông thường báo thất bại do exception không được xử lý, nhưng mã chính xác của process có thể phụ thuộc launcher/handler. Không hứa Spring Boot “chủ động gán mã 1” chỉ vì mapper trả 0.

### 8.4. Build JAR

Từ thư mục `exit-exception-demo`:

~~~bash
gradle bootJar
~~~

Bản JAR sinh ra theo cấu hình tên mặc định thường là:

~~~text
build/libs/exit-exception-demo-0.0.1-SNAPSHOT.jar
~~~

Nếu dùng Gradle Wrapper, thay `gradle` bằng `./gradlew` trên Linux/macOS hoặc `.\gradlew.bat` trên Windows. Nếu bạn chỉnh `rootProject.name` hoặc `version`, tên JAR có thể thay đổi; xem output `bootJar` của chính project.

### 8.5. Chạy mode thành công và kiểm tra status

Trong Bash/Zsh:

~~~bash
java -jar build/libs/exit-exception-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=success
echo $?
~~~

Trong PowerShell:

~~~powershell
java -jar .\build\libs\exit-exception-demo-0.0.1-SNAPSHOT.jar --demo.mode=success
$LASTEXITCODE
~~~

**Các dòng do Java code tự in:**

~~~text
RUNNER: success
MAIN: application ready
MAIN: normal exit
~~~

Mã thoát process thông thường: **`0`**.

### 8.6. Chạy exception tự cấp mã 23

Trong Bash/Zsh:

~~~bash
java -jar build/libs/exit-exception-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=exception
echo $?
~~~

**Các dòng do code demo tự in** (không tính Boot stack trace/log):

~~~text
RUNNER: exception
EVENT: exit code=23
~~~

Mã thoát của JVM khi chạy theo launcher Spring Boot thông thường: **`23`**. Ngoài các dòng demo, Boot có thể ghi lỗi startup và stack trace; tiến trình kết thúc thất bại có chủ đích.

### 8.7. Chạy mapper mã 17

~~~bash
java -jar build/libs/exit-exception-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=mapped
echo $?
~~~

Các dòng do code demo tự in:

~~~text
RUNNER: mapped
EVENT: exit code=17
~~~

Mã thoát JVM dự kiến: **`17`**.

### 8.8. Khi cả hai cơ chế có mã

~~~bash
java -jar build/libs/exit-exception-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=both
echo $?
~~~

Các dòng do code demo tự in:

~~~text
RUNNER: both
EVENT: exit code=29
~~~

Mã thoát JVM dự kiến: **`29`**. Nếu thấy 23, cần kiểm tra liệu mapper bean có tồn tại trong context active và hàm nhận diện cause chain có match hay không.

### 8.9. Kiểm tra unknown mode

~~~bash
java -jar build/libs/exit-exception-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=unknown
echo $?
~~~

Dòng do code demo chắc chắn in **trước lỗi**:

~~~text
RUNNER: unknown
~~~

Boot/Java báo failure. Không có mapping non-zero từ hai cơ chế đã viết; hãy kiểm tra exit status trên shell thay vì khẳng định một số không do ứng dụng định nghĩa.

### 8.10. Vì sao không dùng exit code của gradle bootRun để đo?

`gradle bootRun` là một **Gradle task** khởi tạo JVM ứng dụng. Nếu process con kết thúc non-zero, Gradle có thể báo build failure và bản thân Gradle trả mã lỗi của **build tool**, không nhất thiết giữ nguyên mã nghiệp vụ của ứng dụng.

Để kiểm thử mã thoát của **chính JVM ứng dụng**, hãy:

1. Build bằng `gradle bootJar`.
2. Gọi trực tiếp `java -jar ...`.
3. Lấy `$?` hoặc `$LASTEXITCODE` **ngay sau lệnh java**.
4. Không đặt một lệnh khác trước bước đọc exit status, vì shell sẽ ghi đè trạng thái lệnh trước.

Đừng dùng việc log có dòng `EVENT: exit code=17` làm bằng chứng duy nhất OS nhận đúng 17; phải xác nhận cả process status khi yêu cầu của bài là điều phối bằng exit code.

## 9. Luồng xử lý thực tế của Spring Boot 3.3.13 khi runner ném exception

Theo implementation `SpringApplication` ở Spring Boot 3.3.13:

1. `callRunners(...)` gọi `ApplicationRunner`/`CommandLineRunner`, có thể bọc exception trong một `IllegalStateException` ghi chú callback thất bại.
2. Nhánh `catch(Throwable ex)` của `SpringApplication.run` gọi xử lý run failure.
3. `getExitCodeFromException(...)` thử `getExitCodeFromMappedException(context, ex)`.
4. Trong nhánh mapper, nếu context chưa tồn tại hoặc `!context.isActive()`, hàm không lấy mappers và trả 0.
5. Nếu context active, lấy các bean `ExitCodeExceptionMapper`, hỏi mã theo exception được cung cấp và chọn non-zero theo cơ chế generators.
6. Nếu không có mapped code khác 0, `getExitCodeFromExitCodeGeneratorException(ex)` duyệt `getCause()` cho đến khi gặp object implements `ExitCodeGenerator`.
7. Nếu exit code khác 0, Boot phát `ExitCodeEvent` khi có context và đăng ký mã với `SpringBootExceptionHandler` của luồng main trong điều kiện handler thích hợp.
8. Boot xử lý failure reporting, đóng context khi có thể và vẫn trả exception ra ngoài lời gọi `run`.

### Vì sao nguyên nhân có mã vẫn được tìm thấy dù runner bị wrap?

Nếu `RuleViolationException` được bọc:

~~~text
IllegalStateException("Failed to execute ApplicationRunner")
   |
   +-- caused by RuleViolationException
           |
           +-- getExitCode() -> 23
~~~

fallback đi theo `getCause()` và tìm thấy `RuleViolationException`. Vì vậy implementation của exception cung cấp mã vẫn có thể hoạt động khi runner bao ngoài thêm một exception.

### ExitCodeEvent được phát ở đâu?

`ExitCodeEvent` là một `ApplicationEvent` có method `getExitCode()`. Với nhánh startup failure non-zero, Boot có thể publish event trong context **trước** quá trình failure reporting và close tương ứng. `@EventListener` trong project runnable chỉ để quan sát, không tham gia chọn mã.

**Đừng biến event listener thành nơi gọi `System.exit(...)`**. Việc exit JVM bên trong listener có thể cắt ngang cleanup, test và logging. Nếu cần lập chính sách mã, dùng generator/mapper; nếu cần quan sát, dùng listener.

## 10. Khi bean mapper không thể tham gia

Một số lỗi xảy ra quá sớm:

- Environment/property parsing thất bại trước context creation.
- ApplicationContextInitializer thất bại khi context chưa active.
- Classpath/configuration lỗi trước khi BeanFactory có thể cung cấp mapper.
- Bean factory refresh thất bại và context không ở trạng thái active.
- Exception xảy ra trong code trước khi gọi `SpringApplication.run`.

Trong các trường hợp trên, **đừng đảm bảo bean `ExitCodeExceptionMapper` được gọi**. Đường mapper trên Spring Boot 3.3 kiểm tra context active.

Nếu exception tự implements `ExitCodeGenerator` và đi qua error handling của `SpringApplication.run`, fallback có thể cung cấp code dù mapper chưa dùng được.

**Không đồng nghĩa:** việc mapper không gọi **không có nghĩa** mọi startup exception chắc chắn được chuyển thành mã 0. JVM/launcher vẫn có hành vi thất bại do uncaught exception, còn Boot có thể đã xác định mã qua exception generator.

### Giải pháp cho lỗi rất sớm

Nếu cần mã ổn định cho lỗi trước khi context active, cân nhắc:

- Tạo exception domain tự mang `ExitCodeGenerator` khi bạn kiểm soát mã.
- Chuyển một số kiểm tra phụ thuộc bean sang `ApplicationRunner` nếu logic thực sự phù hợp với việc kiểm tra sau refresh và trước ready.
- Với lỗi ngoài SpringApplication, xử lý ở `main` bằng logic rõ ràng, vẫn giữ exception/cause để log và cleanup.
- Không bắt bừa `Throwable` rồi `System.exit(0)` khiến failure bị báo thành công.
- Không khởi tạo nhiều tài nguyên để cố gắng chạy mapper khi chính bootstrap đang hỏng.

## 11. Ngoại lệ sau khi ứng dụng đã ready có làm JVM thoát theo mapper không?

**Không tự động.**

Sau khi `SpringApplication.run(...)` trả context, một lỗi runtime có thể xuất hiện ở:

- Một HTTP controller của Spring MVC/WebFlux.
- Một message listener Kafka/RabbitMQ/JMS.
- Một `@Scheduled` method.
- Một `@Async` task hoặc `ExecutorService` worker.
- Một request xử lý batch được kích hoạt sau startup.

Những exception này đi qua **error handling riêng của công nghệ tương ứng**. Chúng **không tự động chạy lại** nhánh `handleRunFailure(...)` của SpringApplication. Do đó một `ExitCodeExceptionMapper` bean **không phải global exception handler cho mọi request/thread**.

Ví dụ:

~~~java
@GetMapping("/data")
String loadData() {
    throw new InvalidInputException("Bad request payload");
}
~~~

Đây là **snippet controller chưa độc lập** và cần Spring Web, imports, class controller. Trên HTTP request, ứng dụng thường trả HTTP error status qua cơ chế MVC/WebFlux exception handling; **không** mặc định kết thúc process bằng 17.

Nếu một job trong background thread throw, luồng chính và JVM có thể vẫn hoạt động; Boot không tự lấy `ExitCodeGenerator` trên exception đó rồi gọi `System.exit`. Muốn job quyết định exit status của toàn tiến trình, cần chuyển kết quả/lỗi về một **orchestrator** hoặc main thread và kết thúc có chủ đích sau khi cleanup.

## 12. Process status, HTTP status và batch status là ba tầng khác nhau

| Khái niệm | Giá trị ví dụ | Dùng cho |
| --- | --- | --- |
| HTTP response status | `400`, `422`, `500` | Một HTTP request |
| Spring Batch `ExitStatus` | `COMPLETED`, `FAILED` hoặc custom string | Trạng thái job trong Batch |
| Process exit code | `0`, `17`, `23` | Kết quả toàn bộ JVM/process |

Chúng có thể liên quan, nhưng **không là cùng một API**.

Một ứng dụng web có thể trả HTTP 422 cho một request không hợp lệ và tiếp tục phục vụ request khác, không thể vì một request fail mà mapper giết toàn bộ JVM.

Một Spring Batch job có thể hoàn thành với trạng thái riêng, và một `JobExecutionExitCodeGenerator` có thể góp phần chuyển trạng thái job sang mã process trong cấu hình phù hợp. Không nhầm `ExitStatus.getExitCode()` dạng string của Spring Batch với `ExitCodeGenerator.getExitCode()` dạng `int` của Spring Boot.

### Ứng dụng chạy dài hạn khác CLI chạy một lần

Nếu ứng dụng là HTTP server, startup exception khác 0 thường khiến instance không lên được; còn lỗi trong request là vấn đề request, không nên biến thành JVM exit chỉ bằng một mapper tổng quát.

Với CLI/batch app, `main` có thể chờ toàn bộ job hoàn tất, tính kết quả và chủ động kết thúc. Vì vậy exit code là một phần rất tự nhiên của hợp đồng batch.

## 13. Thứ tự ưu tiên và khả năng bảo trì của mapper

### Không viết mapper quá rộng

Một mapper trả non-zero cho mọi exception:

~~~java
@Bean
ExitCodeExceptionMapper alwaysOne() {
    return error -> 1;
}
~~~

có thể che mất mã đặc thù từ exception implements `ExitCodeGenerator`, vì mapped code có ưu tiên trong đường startup failure.

Nếu cần fallback generic, hãy định nghĩa chiến lược rõ, tránh đặt nó trước các mappers chuyên biệt một cách vô thức. Thực tế một mapper tập trung có logic:

~~~java
@Bean
ExitCodeExceptionMapper domainCodes() {
    return error -> {
        for (Throwable t = error; t != null; t = t.getCause()) {
            if (t instanceof InvalidInputException) {
                return 17;
            }
            if (t instanceof TemporaryDependencyException) {
                return 24;
            }
        }
        return 0;
    };
}
~~~

Đây là snippet minh họa: `InvalidInputException` và `TemporaryDependencyException` cần class thực tế, imports. Những mã 17 và 24 là contract ví dụ.

### Không lạm dụng @Order

Nếu có nhiều mapper, ordering có thể ảnh hưởng mã nào được dùng khi nhiều bean cùng trả non-zero. Có thể dùng `Ordered`/`@Order` theo contract của cơ chế sắp xếp generator, nhưng phải **test thực tế** trên phiên bản Boot/bean declaration tương ứng.

Đừng đoán thứ tự dựa vào tên class, thứ tự component scanning hoặc phương thức `@Bean` xuất hiện ở trên/dưới trong file. Nếu chính sách mapping phức tạp hoặc có xung đột, một mapper duy nhất với thứ tự điều kiện tường minh thường dễ giải thích hơn.

### Tránh lỗi trong chính getExitCode

`getExitCode()` nên là phép tính nhẹ, ổn định và không gây side effect. Không nên:

- Gọi HTTP/DB để quyết định code.
- Đọc bean đã destroy hoặc phụ thuộc vào context khi nó đang fail.
- Throw exception mới làm mất thông tin failure gốc.
- In bí mật từ exception trong log.
- Gọi `System.exit` từ generator/mapper.

Đây là thành phần của **error handling path**; càng đơn giản, càng ít khả năng tạo lỗi thứ cấp.

## 14. Mã thoát và cleanup

Exit code không thay thế việc đóng resources.

Với startup failure:

1. Boot cố xác định mã.
2. Báo cáo lỗi và phát event liên quan khi thích hợp.
3. Đóng application context nếu đã tạo và có thể đóng.
4. Các singleton hoàn chỉnh có thể nhận `@PreDestroy`/`DisposableBean.destroy()` theo lifecycle.
5. Exception vẫn đi ra khỏi `SpringApplication.run` trong nhánh lỗi.

Với planned exit sau successful run:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

`SpringApplication.exit` tính mã và đóng context theo API. `System.exit` thông báo process exit status cho OS. Code trên là snippet không độc lập, không phải sự thay thế cho xử lý lỗi **trước khi `run` trả về**.

### Không dừng JVM đột ngột trước khi dọn

Nếu một mapper/handler gọi thẳng `Runtime.getRuntime().halt(...)` hoặc ứng dụng gọi `System.exit(...)` ở thời điểm không phù hợp, có thể cắt ngắn các callback/flush logs hoặc khiến task background bị bỏ dở. Với các job quan trọng, cần dừng nhận việc, drain công việc, đóng resources rồi mới quyết định exit.

**Không có cách Java thuần đảm bảo mọi cleanup chạy khi SIGKILL, JVM crash hoặc host chết.** Thiết kế recovery/idempotency/checkpoint cho các trường hợp đó.

## 15. Kiểm thử exit code bằng JVM con

Khi test exception mapping, cần kiểm tra ở **hai tầng**.

### Tầng đơn vị (unit)

Gọi `getExitCode()` trên exception:

~~~java
RuleViolationException e =
        new RuleViolationException("rule failed");

assertEquals(23, e.getExitCode());
~~~

Đây là snippet JUnit giả định import/định nghĩa class phù hợp. Có thể test mapper trực tiếp với một cause chain:

~~~java
Throwable wrapped = new IllegalStateException(
        "Failed to execute ApplicationRunner",
        new InvalidInputException("invalid"));

ExitCodeExceptionMapper mapper = exception -> {
    for (Throwable t = exception; t != null; t = t.getCause()) {
        if (t instanceof InvalidInputException) {
            return 17;
        }
    }
    return 0;
};

assertEquals(17, mapper.getExitCode(wrapped));
~~~

Đây là snippet unit-test, không phải source runnable độc lập: dùng JUnit `assertEquals` và exception class đã định nghĩa.

### Tầng integration với process thật

Dùng `ProcessBuilder` hoặc test script khởi chạy JAR ở **một JVM con**, truyền mode, capture stdout/stderr và gọi `process.waitFor()` để lấy status.

Lý do không gọi `System.exit` trong cùng JVM test:

- Nó có thể kết thúc luôn JVM chứa JUnit/Gradle test runner.
- Hook shutdown và process exit code không thể được test như một phép gọi Java thông thường.
- Các launcher có thể chuyển đổi mã hoặc đóng gói lỗi khác nhau.
- Một SpringApplication context nằm trong test JVM không nhất thiết có cùng uncaught-exception handler và thread name như khi chạy từ JAR.

### Ma trận integration hợp lý

| Mode | Custom ExitCodeEvent | Mã JVM mong đợi khi chạy trực tiếp bằng launcher Boot |
| --- | --- | --- |
| `success` | Không có event lỗi non-zero | `0` |
| `exception` | `23` | `23` |
| `mapped` | `17` | `17` |
| `both` | `29` | `29` |
| `unknown` | Không có custom non-zero event | Kiểm tra mã thất bại thực tế; thường `1` |

Khi tạo kiểm thử tự động, đừng chỉ so sánh exit code: cần kiểm tra cả loại exception được ném, nguyên nhân, log, việc context cleanup và phương thức mapper có thật sự được gọi.

## 16. Các trường hợp khó

### 16.1. Mapper không được gọi khi context chưa active

Nếu BeanFactory chưa refresh xong, bean mapper chưa thể được lấy. Đừng sửa bằng cách “force create” bean trong trạng thái context hỏng. Với lỗi rất sớm mà bạn kiểm soát, exception mang `ExitCodeGenerator` hoặc xử lý tại main có thể phù hợp hơn.

### 16.2. Exception lồng nhiều tầng

Trong ứng dụng nhiều service layers, có thể có:

~~~text
IllegalStateException from runner
   └-- CompletionException
          └-- BusinessValidationException
~~~

Mapper nên duyệt cause chain khi contract yêu cầu. Không chỉ dùng `exception.getCause() instanceof ...` nếu có thể có nhiều lớp wrapper.

### 16.3. Bean implements ExitCodeGenerator dùng với SpringApplication.exit

Một singleton implements `ExitCodeGenerator` có thể trả 42 khi `SpringApplication.exit(context)` được gọi, nhưng **không tự được gọi chỉ vì request HTTP ném exception**. Hai cơ chế và hai ngữ cảnh khác nhau.

### 16.4. Trả mã khác 0 khi job không ném exception

Một batch job có thể hoàn thành execution mà vẫn có kết quả “có 5 bản ghi bị reject”. Nếu không muốn ném exception làm startup fail, hãy giữ kết quả trong bean `ExitCodeGenerator` và gọi `SpringApplication.exit(context)` sau job, rồi `System.exit(code)`. Khi đó mapping exception không tham gia.

### 16.5. Exception từ một background worker

Nếu runner chỉ submit task rồi trả về, ứng dụng có thể đã ready trước khi worker fail. Để mã exit phản ánh lỗi job, runner/orchestrator phải **chờ hoàn thành** hoặc có kênh báo lỗi về main; không mong mapper startup tự xử lý lỗi ở thread khác.

### 16.6. Nhiều SpringApplication contexts

Với parent/child contexts hoặc nhiều `SpringApplication.run` trong cùng JVM, phải xác định context nào có mapper bean, exception được xử lý ở context nào và lifecycle nào đóng. Không coi một mapper bean là global JVM singleton.

### 16.7. Container nhận SIGTERM hoặc SIGKILL

Terminated bởi tín hiệu là tình huống khác với exception khi startup. Không đòi mapper biến SIGTERM thành “business exit code”. Exit status do process/runtime/shell/orchestrator có thể dùng các quy tắc signal riêng, và SIGKILL bỏ qua Java shutdown hooks.

### 16.8. Một thư viện ném Error

SpringApplication xử lý `Throwable` trong startup path; tuy nhiên, nếu JVM đang ở trạng thái rất nghiêm trọng như `OutOfMemoryError`, không thể hứa mapper beans, event listeners và cleanup luôn hoạt động. Tránh thiết kế mã lỗi dựa trên việc khởi tạo thêm bean vào thời điểm memory đã cạn.

## 17. Anti-pattern và cách sửa

**1. “Mọi exception đều tự thành mã 1.”** Không phải chính sách mã nghiệp vụ do Spring Boot cấp. Uncaught exception thường khiến process thất bại chung; muốn mã ổn định thì tạo generator/mapper và test launcher thật.

**2. “ExitCodeGenerator chỉ dùng làm bean.”** Sai. Exception cũng có thể implements interface để cung cấp mã.

**3. “ExitCodeExceptionMapper là annotation.”** Sai. Nó là **functional interface**; triển khai hoặc trả lambda bean.

**4. “Mapper chạy trước khi context tồn tại.”** Không thể giả định; Boot 3.3 kiểm tra context active để dùng mapper beans.

**5. “Chỉ kiểm tra exception instanceof DomainException là đủ.”** Không khi runner/framework bọc exception. Duyệt cause chain đúng contract.

**6. “Mapper trả 0 tức là startup thành công.”** Sai. 0 chỉ là không có mapped non-zero code; exception vẫn có thể làm startup fail.

**7. “Nếu exception đã có mã 23, mapper không thể override.”** Sai với đường startup failure Boot 3.3 khi context active: mapped non-zero được thử trước fallback.

**8. “Mapper luôn thắng dù trả 0.”** Sai. Khi mapper ra 0, Boot tiếp tục tìm exception có `ExitCodeGenerator`.

**9. “System.exit không cần vì SpringApplication.exit đã đóng context.”** Nhầm return value với OS process status. `exit(context)` trả `int`; muốn gửi mã cho JVM process cần cơ chế exit thích hợp.

**10. “Chỉ gọi SpringApplication.exit(null) trong catch khi run fail.”** Không hợp lệ; không có context thành công để truyền, và SpringApplication có error path riêng.

**11. “Mã exit của gradle bootRun luôn chính xác bằng mã của ứng dụng.”** Không bảo đảm. Gradle là một process build tool; hãy gọi trực tiếp JAR nếu mục tiêu kiểm tra exit status của JVM app.

**12. “ExitCodeEvent luôn xuất hiện khi có lỗi.”** Không. Event non-zero tùy mã được xác định và context/event publisher khả dụng.

**13. “ExitCodeExceptionMapper xử lý cả HTTP 400/500.”** Không mặc định. HTTP error handlers hoạt động ở request layer.

**14. “Một exception trong @Async tự kết thúc JVM bằng mã từ ExitCodeGenerator.”** Không. Cần orchestration/propagation nếu muốn kết quả process-level.

**15. “Nhiều mapper trả non-zero thì Boot cộng hoặc lấy lớn nhất.”** Không. Cơ chế chọn non-zero theo thứ tự, không phải phép tổng hợp.

**16. “Có thể log full exception data vô điều kiện.”** Ngoại lệ có thể chứa file path, token, SQL hoặc personal data; cần redaction và log policy.

**17. “Mã âm hoặc >255 luôn portable.”** Không, shell Unix-like có cách biểu diễn có thể làm mất thông tin.

**18. “Mã business rule giống HTTP status.”** Không. Một HTTP request fail không mặc định làm toàn bộ JVM exit.

**19. “Có mapper rồi là khỏi cần cleanup.”** Không. Exit-code mapping không giải phóng database pool, file, thread hay external resource.

**20. “Một bean ExitCodeGenerator tự làm JVM thoát mỗi khi được tạo.”** Không. Bean chỉ cung cấp mã khi `SpringApplication.exit` hoặc một flow thích hợp gọi nó.

## 18. Quy trình thiết kế mã lỗi trong ứng dụng thật

Để một batch/CLI có hợp đồng ổn định:

1. **Liệt kê trạng thái cần phân biệt:** success, invalid input, non-retryable business error, temporary dependency failure, unclassified failure.
2. **Chọn mã gọn, không xung đột:** ưu tiên các số dương nhỏ, ghi chú nghĩa rõ.
3. **Xác định owner:** exception domain nào tự implement `ExitCodeGenerator`? Exception thư viện nào cần mapper?
4. **Quy định priority:** tránh các mapper cùng match nhưng trả mã khác nhau; ưu tiên mapping chuyên biệt.
5. **Xử lý wrapper:** mapper duyệt cause chain có giới hạn, không dựa vào exact exception message.
6. **Phân biệt startup failure và runtime failure:** chọn đúng entrypoint dùng mã.
7. **Cleanup trước exit:** đảm bảo tài nguyên được đóng và job result bền vững trước khi tiến trình kết thúc.
8. **Test trên JVM thật:** không tin hoàn toàn vào Gradle status hoặc một unit test gọi method.
9. **Theo dõi metrics/logs:** exit code, loại lỗi và correlation ID; không chứa secret.
10. **Tài liệu hóa với scheduler:** mã nào retry, mã nào cần người can thiệp, deadline và escalation.

Một bản đồ mã có thể viết:

~~~text
0  -> SUCCESS
17 -> INVALID_INPUT        (do not retry until corrected)
23 -> BUSINESS_RULE_FAILED (notify operator)
24 -> DEPENDENCY_TEMPORARY (bounded retry/backoff)
29 -> POLICY_OVERRIDE      (inspect reason)
1  -> UNKNOWN_FAILURE      (investigate)
~~~

Đây là **minh họa hợp đồng vận hành**, không phải các hằng số do Spring Boot cung cấp.

## 19. Bài tập thực hành

1. Nêu sự khác nhau giữa mã thoát `0`, `17` và `23` theo contract của project mẫu.
2. Viết một exception `InvalidBusinessStateException implements ExitCodeGenerator` và trả `31`. Nó được dùng trong nhánh lỗi nào?
3. Viết một `ExitCodeExceptionMapper` ánh xạ `NumberFormatException` thành `17`, chỉ khi lỗi nằm trong cause chain.
4. Vì sao mapper nhận `IllegalStateException("Failed to execute ApplicationRunner", cause)` có thể không match nếu chỉ kiểm tra Throwable ngoài cùng?
5. Chạy mode `exception`. Vì sao mapper trả 0 nhưng Boot vẫn xác định 23?
6. Chạy mode `mapped`. Tại sao không cần sửa `InvalidInputException` để implements interface?
7. Chạy mode `both`. Giải thích vì sao mã là 29 thay vì 23 trong context active.
8. Bỏ bean `exceptionMapper` khỏi project, chạy lại mode `both`. Với exception có `getExitCode() == 23`, mã fallback nào được kỳ vọng?
9. Bỏ mapper rồi chạy mode `mapped`. Vì sao không còn mã nghiệp vụ 17 được cung cấp?
10. Thử lỗi trong constructor bean trước khi context refresh hoàn tất. Mapper có chắc chắn tham gia không?
11. Dùng một exception có `getCause()` lồng ba tầng. Mapper cần viết ra sao để tìm subtype ở tầng trong cùng?
12. Viết hai mapper cùng trả non-zero cho một exception. Bạn sẽ chọn chính sách ordering hoặc gộp mapping như thế nào?
13. Tại sao mapper tổng quát luôn trả 1 có thể che mất các mã đặc thù?
14. So sánh `SpringApplication.exit(context)` và `System.exit(code)`. Phương thức nào tính mã và đóng context, phương thức nào thông báo JVM dừng?
15. Thêm `@Bean ExitCodeGenerator` trả 42. Sau khi context khởi chạy thành công, gọi `SpringApplication.exit(context)` và quan sát 42; bài học này khác startup failure mapper thế nào?
16. Chạy mode `mapped` bằng `gradle bootRun` và `java -jar`. Vì sao không nhất thiết có cùng shell exit status?
17. Trong Bash, chạy `java -jar` rồi chèn lệnh `echo hi` trước `echo $?`. Giá trị được đọc thuộc lệnh nào?
18. Trong PowerShell, vì sao cần lấy `$LASTEXITCODE` để kiểm tra process Java?
19. Cho runner chỉ submit `CompletableFuture` rồi trả ngay; background task sau đó ném `InvalidInputException`. Mapper startup có tự làm JVM exit 17 không?
20. Một web controller ném `InvalidInputException` trên một request. HTTP response và process exit status khác nhau ra sao?
21. Viết unit test cho mapper dùng nested cause và cho exception generator, sau đó viết integration test spawn JVM để đo process exit code.
22. Dùng `ExitCodeEvent` để ghi metric exit code; vì sao event listener không nên tự gọi `System.exit`?
23. Nếu exception không match mapper và không implements generator, có nên khẳng định Spring Boot chủ động trả 0 không? Vì sao?
24. Với Linux container bị SIGKILL, mã thoát quan sát có còn xuất phát từ mapper không? Tại sao không?
25. Thiết kế một bảng mã thoát ổn định cho job nhập liệu: invalid input, temporary unavailable DB, partial success và completed; mô tả retry policy từng mã.

## Ghi nhớ

- **`ExitCodeGenerator` trên exception:** ngoại lệ tự trả một số thông qua `getExitCode()`.
- **`ExitCodeExceptionMapper` bean:** ánh xạ một `Throwable` thành mã; hữu ích khi lỗi đến từ lớp thư viện hoặc cần chính sách thống nhất.
- Trong **startup-failure flow Spring Boot 3.3.13**, mapper được thử **trước**; nếu trả 0 thì fallback tìm exception implements `ExitCodeGenerator` trong cause chain.
- Mapper cần **ApplicationContext active**; lỗi quá sớm có thể không dùng được bean mapper.
- `ApplicationRunner`/`CommandLineRunner` có thể bọc exception; hãy duyệt `getCause()` thay vì chỉ kiểm tra lớp ngoài cùng.
- `0` từ mapper không có nghĩa là không có exception, và cũng không có nghĩa process chắc chắn trả 0.
- `SpringApplication.exit(context)` tính mã từ **generator beans/arguments** và đóng context; nó **không tự gọi `System.exit`**.
- `ExitCodeEvent` dùng để quan sát mã đã xác định; không phải nơi xử lý toàn bộ exception trong ứng dụng.
- Lỗi xảy ra sau khi ứng dụng ready trong HTTP request/background thread không tự kích hoạt nhánh startup mapper.
- Kiểm tra mã thoát bằng **`java -jar` và shell exit status**, không chỉ dựa vào log hoặc `gradle bootRun`.
- Exit code không thay thế cleanup, retry policy, transaction/idempotency và observability.

### Tài liệu tham khảo

- Spring Boot 3.3.13 — SpringApplication / Application Exit: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — `SpringApplication` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3.13 — `ExitCodeGenerator` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html
- Spring Boot 3.3.13 — `ExitCodeExceptionMapper` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeExceptionMapper.html
- Spring Boot 3.3.13 — `ExitCodeEvent` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeEvent.html
- Spring Boot 3.3.13 — `SpringApplication.java` source, failure handling and exit-code selection: https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/SpringApplication.java
- Java SE 17 — `Throwable` and cause chain: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html
- Java SE 17 — `System.exit`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#exit(int)
