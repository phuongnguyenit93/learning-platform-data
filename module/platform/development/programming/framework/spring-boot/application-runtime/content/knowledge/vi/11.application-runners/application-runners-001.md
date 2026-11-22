# Vai trò của ApplicationRunner và CommandLineRunner trong Spring Boot

## Mục tiêu học tập

Trong Spring Boot, có những việc nên chạy **sau khi Spring đã tạo xong application context và khởi tạo các bean cần thiết**, nhưng **trước khi ứng dụng được xem là sẵn sàng nhận traffic**. Ví dụ: xác thực dữ liệu tham chiếu, kiểm tra điều kiện bắt buộc khi startup, làm nóng một cache có giới hạn, hoặc thực hiện một tác vụ CLI/batch dựa trên tham số dòng lệnh.

`ApplicationRunner` và `CommandLineRunner` là hai callback chính thức dành cho tình huống này. Chúng không phải controller, không phải một vòng lặp chạy nền và cũng không được Spring Framework tự động gọi trong mọi kiểu khởi tạo context; đây là hợp đồng được **SpringApplication** của Spring Boot tìm và thực thi khi khởi động.

Sau bài học này, bạn có thể:

1. Xác định chính xác runner nằm ở đâu giữa `ApplicationStartedEvent` và `ApplicationReadyEvent`.
2. Phân biệt `run(ApplicationArguments args)` và `run(String... args)`, chọn interface phù hợp.
3. Dùng `ApplicationArguments` để đọc option, cờ không giá trị, option lặp lại và non-option arguments.
4. Đăng ký một hoặc nhiều runner bằng `@Component` hoặc `@Bean`; kiểm soát thứ tự bằng `@Order`/`Ordered`.
5. Viết, biên dịch và chạy một project Java 17+ / Spring Boot 3.3 với hai runner và kết quả log có thể kiểm chứng.
6. Hiểu tác động của runner chậm, lỗi runner, retry, transaction, readiness và vòng đời ứng dụng.
7. Tránh nhầm runner với `@PostConstruct`, `ApplicationContextInitializer`, `ApplicationReadyEvent`, scheduled task hoặc request handler.

**Bối cảnh:** Spring Boot Application Runtime → Runner. Các API và ví dụ chính dùng Spring Boot **3.3.13**, Spring Framework 6.1 và Java 17.

## 1. Runner xuất hiện ở giai đoạn nào?

Thứ tự rút gọn của một lần `SpringApplication.run(...)` **thành công**:

~~~text
main(String[] args)
   |
   +-- SpringApplication.run(args)
        |
        +-- Chuẩn bị Environment và ApplicationContext
        +-- ApplicationContext.refresh()
        |    +-- Tạo bean definitions/bean instances phù hợp
        |    +-- Khởi tạo singleton non-lazy
        |    +-- Khởi động hạ tầng của context
        |    +-- ContextRefreshedEvent
        |
        +-- ApplicationStartedEvent
        +-- AvailabilityChangeEvent(LivenessState.CORRECT)
        |
        +-- Tìm các bean ApplicationRunner và CommandLineRunner
        +-- Sắp xếp bằng Ordered / @Order khi có
        +-- Gọi run(...) của từng runner
        |
        +-- ApplicationReadyEvent
        +-- AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
        |
        +-- Trả về ConfigurableApplicationContext
             |
             +-- Ứng dụng tiếp tục hoạt động cho đến lúc dừng
~~~

Đây là **sơ đồ các mốc chính**, không liệt kê mọi callback nội bộ. Trong ứng dụng web, embedded server có thể đã được khởi động trong giai đoạn refresh; cổng mở không đồng nghĩa startup runner đã hoàn tất.

Điểm mấu chốt:

- **Trước runner:** Context đã refresh thành công; các singleton cần khởi tạo sớm thường đã được tạo, injection đã hoạt động. Spring Boot đã phát `ApplicationStartedEvent` và thông báo liveness `CORRECT`.
- **Trong runner:** Đây vẫn là phần của **tiến trình startup** do `SpringApplication.run` điều phối. Một runner đồng bộ chưa kết thúc có thể khiến toàn bộ lần startup chưa đạt ready.
- **Sau tất cả runner chạy thành công:** Boot mới phát `ApplicationReadyEvent` rồi cập nhật readiness thành `ACCEPTING_TRAFFIC`.
- **Khi runner ném exception không được xử lý:** Lần khởi động có thể thất bại. Các runner ở phía sau trong thứ tự thực thi không nhất thiết được gọi; `ApplicationReadyEvent` và trạng thái readiness accepting không xuất hiện trong đường thành công bình thường.

Nói “runner chạy khi startup xong” cần hiểu chính xác: **xong phần context refresh**, nhưng **chưa xong toàn bộ SpringApplication startup**. Chính runner là một phần được tính trong thời gian tiến đến ready.

## 2. Hai interface có cùng mục đích, khác cách nhận tham số

### ApplicationRunner

Chữ ký API trong Spring Boot 3.3:

~~~java
@FunctionalInterface
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

Đây là **chữ ký minh họa**, không tạo lại `org.springframework.boot.ApplicationRunner` trong mã nguồn. `ApplicationArguments` cung cấp cả argument gốc và dữ liệu đã phân loại:

- `getSourceArgs()`: toàn bộ tham số nguồn dạng `String[]`.
- `getOptionNames()`: tập tên option.
- `containsOption("name")`: có option này hay không.
- `getOptionValues("name")`: các giá trị của option đó; có thể `null` khi vắng mặt.
- `getNonOptionArgs()`: các tham số không có dạng option.

Đây là lựa chọn thường hợp lý hơn khi bạn muốn viết một startup command có option kiểu `--mode=verify`, `--dry-run`, `--region=apac` hoặc cần tách tham số positional khỏi option.

### CommandLineRunner

Chữ ký API:

~~~java
@FunctionalInterface
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

Đây cũng là **chữ ký minh họa**, không tạo lại interface của Spring. `String...` là Java varargs; ở runtime callback nhận mảng các chuỗi argument được chuyển từ `main(String[] args)`/`SpringApplication.run(args)`. Runner này tiện cho logic cần toàn bộ arguments ở dạng thô, hoặc project nhỏ không cần API phân tích riêng.

### Bảng so sánh

| Tiêu chí | `ApplicationRunner` | `CommandLineRunner` |
| --- | --- | --- |
| Package | `org.springframework.boot` | `org.springframework.boot` |
| Phương thức | `run(ApplicationArguments args)` | `run(String... args)` |
| Kiểu arguments | Wrapper phân loại option/non-option | Mảng chuỗi gốc |
| Tự có API đọc `--name=value` | Có | Không; phải tự phân tích nếu cần |
| Có đọc được chuỗi raw? | Có, `getSourceArgs()` | Có, ngay trong `args` |
| Thời điểm Boot gọi | Sau refresh, trước ready | Sau refresh, trước ready |
| Có nhận dependency injection? | Có, khi runner là Spring bean | Có, khi runner là Spring bean |
| Có thể dùng `@Order`/`Ordered`? | Có | Có |
| Phương thức có thể throw `Exception`? | Có | Có |
| Có tự lặp theo mỗi HTTP request? | Không | Không |
| Có tự chạy theo lịch cron? | Không | Không |

**Không có interface nào “chạy trước” interface kia chỉ vì tên loại.** Nếu muốn ưu tiên giữa chúng, hãy cấu hình thứ tự rõ ràng. Các runner thuộc hai loại được Spring Boot thu thập và sắp xếp trong cùng giai đoạn startup.

## 3. ApplicationArguments: đọc tham số cho đúng

Giả sử khởi chạy ứng dụng với arguments sau:

~~~bash
--mode=demo --tag=alpha --tag=beta job-42 --dry-run
~~~

Đây là phần **application arguments**, không phải cú pháp một shell command độc lập. Trong CLI thực tế, các tham số đứng sau tên JAR, hoặc được truyền bởi cơ chế chạy Gradle/Maven/IDE.

Phân tích:

| Biểu thức | Kết quả từ `ApplicationArguments` |
| --- | --- |
| `containsOption("mode")` | `true` |
| `getOptionValues("mode")` | `[demo]` |
| `getOptionValues("tag")` | `[alpha, beta]` |
| `getNonOptionArgs()` | `[job-42]` |
| `containsOption("dry-run")` | `true` |
| `getOptionValues("dry-run")` | Danh sách rỗng `[]` vì cờ có mặt nhưng không có giá trị |
| `getOptionValues("missing")` | `null` vì option vắng mặt |
| `getSourceArgs()` | Mảng raw chứa toàn bộ năm phần tử đã truyền |

**Phân biệt ba trường hợp của `getOptionValues`:**

1. Option **không tồn tại** → `null`.
2. Option tồn tại **không có giá trị**, như `--dry-run` → danh sách rỗng `[]`.
3. Option có một hoặc nhiều giá trị `--tag=...` → danh sách các chuỗi, giữ các giá trị đã phân tích.

Vì vậy đừng gọi `args.getOptionValues("mode").get(0)` trước khi kiểm tra `null`/`isEmpty()`. Nếu một option bắt buộc phải có đúng một giá trị, hãy validate tường minh thay vì để lỗi `NullPointerException` hoặc `IndexOutOfBoundsException` xuất hiện mơ hồ.

Ví dụ kiểm tra option bắt buộc:

~~~java
List<String> modes = args.getOptionValues("mode");

if (modes == null || modes.size() != 1
        || modes.get(0).isBlank()) {
    throw new IllegalArgumentException(
            "Expected exactly one --mode=value");
}

String mode = modes.get(0);
~~~

Đoạn code này minh họa **thân `ApplicationRunner.run`**, cần import `java.util.List` và biến `args` kiểu `ApplicationArguments`. Nó không phải file Java chạy độc lập.

### Cú pháp --name=value khác --name value

Spring Boot phân tích các command-line option dạng `--name=value`. Với chuỗi:

~~~text
--mode demo
~~~

`--mode` là option **không có giá trị gắn trực tiếp**, trong khi `demo` được xem là non-option argument theo cách parser chuẩn phân tích. Đừng mặc nhiên coi hai cách truyền trên tương đương.

Ngoài ra, `-Dspring.profiles.active=dev` là **JVM system property** khi đặt trước `-jar`, không phải một argument `--...` trong mảng `main`. Tương tự, `-Xmx512m` là tham số JVM, không phải một phần của `CommandLineRunner.run` nếu được truyền đúng vị trí cho JVM.

### Cờ không giá trị và boolean

`--dry-run` mang ý nghĩa “cờ hiện diện” theo `containsOption("dry-run")`. Còn `--dry-run=false` vẫn khiến `containsOption("dry-run")` trả về `true`; lúc này `getOptionValues("dry-run")` là `[false]`. Nếu muốn hỗ trợ cả hai kiểu, phải định nghĩa cách diễn giải:

~~~java
boolean requestedDryRun = args.containsOption("dry-run");
~~~

Dòng trên biểu diễn **cờ hiện diện**, không phải parser boolean tổng quát. Với option có thể truyền `true`/`false`, hãy phân tích giá trị và validate rõ ràng.

### Dữ liệu kiểu số, enum hoặc đường dẫn

`ApplicationArguments` trả về **chuỗi**, không tự đổi mọi `--retries=3` thành `int` cho code của bạn. Có thể dùng `Integer.parseInt(...)`, `Enum.valueOf(...)`, conversion service hoặc binding sang configuration properties sau khi kiểm tra lỗi và giá trị hợp lệ.

Không dùng tham số dòng lệnh tùy ý đưa thẳng vào tên file, truy vấn hoặc lệnh hệ thống mà không validate. Chú ý các argument có secret: shell history, process list, build logs hoặc startup logs có thể làm lộ chúng; với secret hãy ưu tiên kênh cấu hình bảo mật phù hợp.

## 4. SpringApplication truyền và xử lý arguments như thế nào?

Với phương thức main chuẩn:

~~~java
public static void main(String[] args) {
    SpringApplication.run(MyApplication.class, args);
}
~~~

`args` của `main` được chuyển sang `SpringApplication.run(...)`. Sau khi tạo `ApplicationContext`, Boot đăng ký `ApplicationArguments` để các bean có thể inject:

~~~java
@Component
class StartupArgumentsInspector {

    StartupArgumentsInspector(ApplicationArguments args) {
        boolean debugEnabled = args.containsOption("debug");
        // Có thể dùng để chuẩn bị cấu hình phù hợp.
    }
}
~~~

Đây là **đoạn minh họa chưa độc lập**, cần import `Component`/`ApplicationArguments`. Việc inject `ApplicationArguments` không có nghĩa nó tự chạy `run`; chỉ bean triển khai runner hoặc cơ chế callback thích hợp mới được Spring Boot gọi trong pha runners.

Spring Boot mặc định cũng đưa **command-line property source** vào `Environment`, nên một option như `--server.port=9090` có thể tham gia cơ chế ưu tiên cấu hình. Nhưng đó là **hai cơ chế khác nhau**:

- `ApplicationArguments` phân loại input truyền vào `run`.
- `Environment` giải quyết các property từ nhiều nguồn theo thứ tự ưu tiên.

Nếu programmatic code gọi `SpringApplication.setAddCommandLineProperties(false)` trước `run`, việc expose command-line args thành property source bị tắt, **không đồng nghĩa** `ApplicationArguments` không còn các raw arguments truyền vào. Không nhầm vai trò startup runner với việc bind cấu hình bằng `@ConfigurationProperties`.

## 5. Bean runner được tạo lúc nào và gọi bao nhiêu lần?

Một class có thể trở thành runner bằng component scanning:

~~~java
@Component
public class VerifyStartup implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) throws Exception {
        // Thực hiện kiểm tra startup.
    }
}
~~~

Hoặc bạn có thể khai báo qua `@Bean`:

~~~java
@Configuration
class StartupConfiguration {

    @Bean
    CommandLineRunner logArguments() {
        return args -> System.out.println(
                "Arguments: " + Arrays.toString(args));
    }
}
~~~

Hai ví dụ là **các đoạn cấu hình**, chưa phải project độc lập; cần import `Component`/`ApplicationRunner` hoặc `Configuration`/`Bean`/`CommandLineRunner`, `Arrays`.

Điểm quan trọng:

1. `ApplicationRunner` và `CommandLineRunner` là **functional interface**, dễ viết lambda hay class.
2. Runner phải là **bean được SpringApplication quản lý** để Boot phát hiện và gọi tự động. Chỉ `new VerifyStartup()` trong mã khác mà không đăng ký làm bean không khiến nó tự chạy.
3. Theo mặc định, class `@Component` không lazy thường được khởi tạo trong refresh; **phương thức `run` chưa được gọi tại constructor**. Callback được gọi ở giai đoạn runner sau refresh.
4. Một runner thông thường được gọi **một lần trong mỗi lần `SpringApplication.run` thành công đi đến pha runner**. Nếu ứng dụng có nhiều context/lần run, có thể có nhiều lần gọi trong toàn JVM. Nếu bean implements **cả hai interface**, Boot có thể gọi cả hai callback riêng biệt.
5. Spring không biến runner thành scheduler: `run` không tự chạy lại mỗi phút, mỗi request hoặc mỗi khi BeanFactory tạo thêm bean khác.

Nếu cần một command được gọi bởi mỗi request, hãy dùng controller/service; nếu cần lịch lặp, nghiên cứu `@Scheduled`; nếu cần xử lý message liên tục, dùng consumer/worker có lifecycle riêng.

## 6. Thứ tự giữa nhiều runner: @Order và Ordered

Khi có từ hai runner trở lên, thứ tự thực thi quan trọng nếu bước sau phụ thuộc kết quả bước trước. Spring Boot cho phép dùng:

- `org.springframework.core.annotation.Order` trên class.
- `org.springframework.core.Ordered` trên bean.
- `PriorityOrdered` trong trường hợp đặc biệt cần semantics ưu tiên cao hơn.

Ví dụ:

~~~java
@Component
@Order(10)
public class ValidateRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Validate startup");
    }
}
~~~

~~~java
@Component
@Order(20)
public class WarmupRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("Warm up cache");
    }
}
~~~

Hai đoạn minh họa class cần các import tương ứng. **Giá trị order nhỏ hơn thường được gọi trước**. Ở đây `ValidateRunner` được gọi trước `WarmupRunner` mặc dù chúng triển khai hai interface khác nhau.

Không nên dựa vào thứ tự tên file, thứ tự `@Component` scan hoặc thứ tự bean definitions để suy ra runner nào chạy trước. Nếu có dependency bắt buộc phải hoàn thành theo thứ tự, cấu hình order rõ ràng hoặc gộp logic thành một orchestration service với các bước tường minh.

### Không dùng @DependsOn để thay thế @Order

`@DependsOn` có thể ảnh hưởng **thứ tự tạo/khởi tạo bean**, nhưng không phải là hợp đồng xếp thứ tự callback `run(...)` giữa các runner sau refresh. Muốn điều khiển thứ tự **thực thi runner**, dùng `@Order`/`Ordered`.

### Tránh một bean implements cả hai interface

Ví dụ **không khuyến nghị**:

~~~java
class DualRunner implements ApplicationRunner, CommandLineRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("ApplicationRunner callback");
    }

    @Override
    public void run(String... args) {
        System.out.println("CommandLineRunner callback");
    }
}
~~~

Mã trên minh họa class Java hợp lệ nếu import hai interface. Nếu class này là Spring bean, SpringApplication có thể coi nó đồng thời là hai loại runner và gọi **cả hai phương thức** trong một startup. Điều đó không có nghĩa một phương thức được tự động chọn để chạy thay phương thức kia. Hãy chọn một interface cho mỗi trách nhiệm để tránh side effect lặp.

## 7. Dự án chạy được: so sánh hai runner và các sự kiện startup

Ví dụ có bốn class Java, một file Gradle settings và một file Gradle build. Ứng dụng **không mở HTTP server**; ở cuối thí nghiệm `main` đóng context để chương trình kết thúc. Điều này giúp quan sát vòng đời rõ ràng.

### 7.1. Cấu trúc project

~~~text
runner-lifecycle-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/runner/
    ├── RunnerDemoApplication.java
    ├── OptionsRunner.java
    ├── RawArgumentsRunner.java
    └── StartupEventObserver.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'runner-lifecycle-demo'
~~~

**`build.gradle`:**

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
    mainClass = 'com.example.runner.RunnerDemoApplication'
}
~~~

Spring Boot plugin phiên bản 3.3.13 cùng BOM chỉ định dependencies tương ứng. Project yêu cầu Gradle tương thích Spring Boot 3.3, JDK 17 hoặc mới hơn và kết nối tới Maven Central nếu dependency chưa được cache.

### 7.2. Main: SpringApplication.run và đóng context

**`src/main/java/com/example/runner/RunnerDemoApplication.java`:**

~~~java
package com.example.runner;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class RunnerDemoApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                RunnerDemoApplication.class);

        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN: run returned");
        }

        System.out.println("MAIN: context closed");
    }
}
~~~

`@SpringBootApplication` quét package `com.example.runner` để phát hiện ba bean ở các tệp tiếp theo. `WebApplicationType.NONE` bảo đảm ứng dụng demo không tạo web server. `Banner.Mode.OFF` và `setLogStartupInfo(false)` hạn chế output phần startup; chúng không xóa mọi log hệ thống.

Chúng ta dùng `try-with-resources` để đóng context sau khi chạy thử. **Ứng dụng web chạy dài hạn không nên đóng context ngay khi `run` trả về**; đây chỉ là cách kết thúc chương trình CLI ví dụ.

### 7.3. ApplicationRunner: tham số có cấu trúc

**`src/main/java/com/example/runner/OptionsRunner.java`:**

~~~java
package com.example.runner;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class OptionsRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {

        System.out.println(
                "APP_RUNNER: mode=" + args.getOptionValues("mode"));

        System.out.println(
                "APP_RUNNER: tags=" + args.getOptionValues("tag"));

        System.out.println(
                "APP_RUNNER: nonOptions=" + args.getNonOptionArgs());

        if (args.containsOption("fail-demo")) {
            System.out.println("APP_RUNNER: intentional failure");
            throw new IllegalStateException(
                    "Demo startup validation failed");
        }
    }
}
~~~

Runner này cho thấy `ApplicationArguments` cho phép đọc option lặp lại `--tag=...` và dữ liệu positional. `@Order(10)` khiến runner được ưu tiên trước bean có `@Order(20)`, **không phải** vì nó là ApplicationRunner.

Đoạn `--fail-demo` chỉ chạy khi được cung cấp cờ; nó cho phép thử nhánh startup thất bại mà không cần sửa code.

### 7.4. CommandLineRunner: mảng argument gốc

**`src/main/java/com/example/runner/RawArgumentsRunner.java`:**

~~~java
package com.example.runner;

import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class RawArgumentsRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println(
                "CMD_RUNNER: raw=" + Arrays.toString(args));
    }
}
~~~

Runner này không phân loại arguments; nó chỉ in toàn bộ mảng nhận được. Trong một ứng dụng cần parse format đặc thù hoặc truyền nguyên arguments cho công cụ dòng lệnh khác, cách này có thể phù hợp. Với option `--name=value` thông thường, `ApplicationRunner` giúp tránh phải tự viết parser.

### 7.5. Quan sát ApplicationStartedEvent và ApplicationReadyEvent

**`src/main/java/com/example/runner/StartupEventObserver.java`:**

~~~java
package com.example.runner;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupEventObserver {

    @EventListener(ApplicationStartedEvent.class)
    public void onStarted() {
        System.out.println("EVENT: started");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("EVENT: ready");
    }
}
~~~

Hai listener này được đăng ký khi context xử lý bean. `ApplicationStartedEvent`/`ApplicationReadyEvent` đều phát sau refresh, nên listener bean có thể nhận được chúng. Chúng dùng để minh họa hai đầu khoảng thời gian mà các runner được gọi, **không phải** API để chạy chính runner.

### 7.6. Chạy với arguments và kiểm tra output

Trong thư mục `runner-lifecycle-demo`:

~~~bash
gradle bootRun --args="--mode=demo --tag=alpha --tag=beta job-42"
~~~

Nếu đã có Gradle Wrapper, thay `gradle` bằng `./gradlew` trên Linux/macOS hoặc `.\gradlew.bat` trên Windows. Bản project mẫu không tự sinh wrapper. Trong IDE, cấu hình **program arguments** là `--mode=demo --tag=alpha --tag=beta job-42`, không đưa cả lệnh Gradle vào trường arguments.

Bỏ qua log của Gradle/Spring và nhìn các dòng do **mã Java của demo** tự in, thứ tự mong đợi là:

~~~text
EVENT: started
APP_RUNNER: mode=[demo]
APP_RUNNER: tags=[alpha, beta]
APP_RUNNER: nonOptions=[job-42]
CMD_RUNNER: raw=[--mode=demo, --tag=alpha, --tag=beta, job-42]
EVENT: ready
MAIN: run returned
MAIN: context closed
~~~

**Tại sao đúng thứ tự?**

1. `EVENT: started`: context đã refresh, Boot chưa gọi runner.
2. `APP_RUNNER`: `OptionsRunner` có `@Order(10)`, nhận `ApplicationArguments` và in các giá trị đã phân tích.
3. `CMD_RUNNER`: `RawArgumentsRunner` có `@Order(20)`, nhận đúng mảng raw.
4. `EVENT: ready`: hai runner đã chạy hết mà không ném exception.
5. `MAIN: run returned`: lời gọi `SpringApplication.run(...)` đã trả về context.
6. `MAIN: context closed`: khối `try-with-resources` kết thúc, gọi đóng context.

Lưu ý kết quả trên là **các dòng do code ví dụ in ra**, không bao gồm log framework và thông báo build. Với flags/arguments khác, những dòng in arguments sẽ thay đổi theo đầu vào.

### 7.7. Kiểm chứng đường lỗi startup

Chạy một phiên mới, cố ý yêu cầu runner đầu tiên thất bại:

~~~bash
gradle bootRun --args="--mode=demo --tag=alpha --tag=beta job-42 --fail-demo"
~~~

Những dòng do chương trình in **trước khi lỗi được Spring Boot xử lý**:

~~~text
EVENT: started
APP_RUNNER: mode=[demo]
APP_RUNNER: tags=[alpha, beta]
APP_RUNNER: nonOptions=[job-42]
APP_RUNNER: intentional failure
~~~

Sau đó Boot/Gradle có thể in stack trace, failure analysis và trạng thái exit khác 0. `RawArgumentsRunner` không chạy do runner trước ném exception; `ApplicationReadyEvent` cũng không được phát trên đường thành công, nên không có `EVENT: ready`. `app.run(args)` ném exception, vì vậy không in `MAIN: run returned`; code phía sau `try` cũng không in `MAIN: context closed`.

**Phân biệt:** Spring Boot vẫn có thể chạy đường xử lý lỗi và cleanup context đã tạo. Sự vắng mặt của dòng log từ `main` **không** có nghĩa container không làm cleanup.

### 7.8. Điều gì sẽ xảy ra nếu bỏ @Order?

Nếu bỏ `@Order` ở hai runner, **không viết kiểm thử bắt buộc runner nào luôn chạy trước** chỉ dựa trên tên class hoặc thứ tự component scanning. Kết quả có thể tình cờ ổn định trong một project nhỏ nhưng không nên biến thành hợp đồng nghiệp vụ.

Nếu runner A phải hoàn thành rồi mới đến B, hãy định nghĩa thứ tự tường minh. Khi phụ thuộc mạnh hoặc có rollback phức tạp, cân nhắc dùng **một runner điều phối** và các service được gọi theo các bước rõ ràng, dễ kiểm thử hơn.

## 8. Chọn runner hay một lifecycle callback khác?

| Nhu cầu | Công cụ thường phù hợp | Vì sao |
| --- | --- | --- |
| Thiết lập invariant của một bean khi dependency đã inject | `@PostConstruct` / `InitializingBean` | Gắn với initialization **của chính bean** |
| Tùy biến `ApplicationContext` trước refresh | `ApplicationContextInitializer` | Context đã được tạo, chưa khởi tạo tất cả bean |
| Chạy nhiệm vụ startup sau refresh, cần hoàn tất trước ready | `ApplicationRunner` / `CommandLineRunner` | Đúng hợp đồng run-on-startup của Boot |
| Quan sát context đã refresh | `ContextRefreshedEvent` | Thể hiện mốc Spring context |
| Quan sát Boot đã started trước runners | `ApplicationStartedEvent` | Mốc after-refresh nhưng chưa chạy runners |
| Quan sát Boot đã gọi runners xong | `ApplicationReadyEvent` | Phát sau runner và trước readiness accepting event |
| Khởi động/dừng thành phần có lifecycle được quản lý | `SmartLifecycle` | Tham gia bắt đầu/dừng các thành phần runtime |
| Thực hiện tác vụ theo lịch | `@Scheduled` hoặc scheduler | Callback lặp theo trigger riêng |
| Phục vụ mỗi HTTP request | Spring MVC/WebFlux controller/service | Phạm vi request, không phải app startup |
| Chạy batch định kỳ có checkpoint/restart | Scheduler + Spring Batch (nếu phù hợp) | Có mô hình job, trạng thái, retry và recovery |

**Không nên đưa một vòng lặp vô hạn vào runner** chỉ vì muốn “chạy ngay lúc boot”. Nếu `run` không trả về, Boot chưa thể tiến tới `ApplicationReadyEvent` và readiness accepting. Với consumer/background worker, có thể dùng runner chỉ để *khởi tạo hoặc lên lịch* việc chạy nền rồi trả về, kèm cơ chế `SmartLifecycle`, shutdown và health phù hợp. Khi nền tảng cần bảo đảm consumer thật sự sẵn sàng trước khi nhận traffic, phải đưa điều kiện đó vào readiness policy.

`@PostConstruct` cũng không phải runner thu nhỏ: nó được gọi trong lúc bean initialization; các singleton không liên quan có thể chưa tạo xong. Runner chạy sau khi context refresh, nên thường có môi trường DI đã ổn định hơn cho công việc cấp ứng dụng.

## 9. Những use case phù hợp và không phù hợp

### 9.1. Validation bắt buộc trước ready

Ví dụ ứng dụng cần kiểm tra danh sách cấu hình phải có:

~~~java
@Component
class RequiredConfigurationRunner implements ApplicationRunner {

    private final PaymentSettings settings;

    RequiredConfigurationRunner(PaymentSettings settings) {
        this.settings = settings;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (settings.getMerchantId() == null
                || settings.getMerchantId().isBlank()) {
            throw new IllegalStateException(
                    "Missing payment merchant id");
        }
    }
}
~~~

Đây là **đoạn minh họa**, cần class `PaymentSettings` và import `Component`/`ApplicationRunner`/`ApplicationArguments`. Nếu merchant ID là điều kiện không thể thiếu để ứng dụng phục vụ, fail-fast là hợp lý. Tuy nhiên nhiều validation cấu hình đơn giản có thể giải quyết sớm hơn bằng `@ConfigurationProperties` + Bean Validation; không buộc mọi cấu hình phải có runner.

### 9.2. Warm-up có giới hạn

Một runner có thể gọi service tạo cache để rút ngắn độ trễ request đầu tiên:

~~~java
@Component
class CacheWarmupRunner implements CommandLineRunner {

    private final ReferenceCache cache;

    CacheWarmupRunner(ReferenceCache cache) {
        this.cache = cache;
    }

    @Override
    public void run(String... args) {
        cache.warmup();
    }
}
~~~

Đây cũng là mã minh họa cần định nghĩa `ReferenceCache`. Hàm `warmup()` nên có giới hạn thời gian, giới hạn tài nguyên, idempotency và chính sách lỗi được quyết định rõ: *bắt buộc* thất bại startup hay *best effort* chỉ ghi cảnh báo.

Nếu warm-up có thể kéo dài vài phút, đừng mặc định chặn readiness lâu sẽ luôn tốt; hãy cân nhắc liệu chỉ cần một tập dữ liệu thiết yếu hay có thể warm-up phần còn lại ở background.

### 9.3. CLI và batch job có tham số

Ví dụ cùng một JAR hỗ trợ:

~~~bash
java -jar app.jar --task=validate input.csv
java -jar app.jar --task=import input.csv
~~~

`ApplicationRunner` tiện cho parser `--task=...` và positional input file. Sau khi job xong, ứng dụng CLI có thể đóng context và trả exit code phù hợp cho orchestrator.

Nếu ứng dụng là web server, runner **không tự chạy lại mỗi lần** người dùng gọi endpoint import. Muốn chạy batch theo lịch hoặc trigger riêng, cần một API/job scheduler thích hợp.

### 9.4. Không dùng runner để chứa tác vụ một lần nhưng không thể khôi phục

Runner mặc định chạy lại mỗi khi **instance khởi động lại**. Trong Kubernetes, rolling update hoặc autoscaling có thể làm nhiều instance chạy runner đồng thời. Vì thế:

- Không trừ tiền, gửi email, tạo đơn hàng hoặc thay đổi dữ liệu quan trọng theo kiểu “chạy đúng một lần toàn hệ thống” chỉ bằng runner.
- Nếu cần seed dữ liệu, dùng upsert/unique constraint/migration tool có idempotency.
- Nếu cần một công việc chỉ có một instance thực hiện, thiết kế khóa phân tán, leader election, scheduled job hoặc hệ thống điều phối phù hợp.
- Không dùng in-memory flag của một JVM làm bằng chứng công việc chưa chạy ở replica khác.

## 10. Tác động tới readiness, liveness và startup timeout

Ở Spring Boot 3.3, **liveness correct** đến sau `ApplicationStartedEvent`, **trước** runner; **readiness accepting traffic** đến sau `ApplicationReadyEvent`, **sau** runner thành công.

~~~text
Context refreshed
   |
ApplicationStartedEvent
   |
LivenessState.CORRECT
   |
+--- Runner 1: kiểm tra cấu hình
+--- Runner 2: warm up dữ liệu
+--- Runner 3: xác minh điều kiện nghiệp vụ
   |
ApplicationReadyEvent
   |
ReadinessState.ACCEPTING_TRAFFIC
~~~

Trong khi runner còn làm việc, ứng dụng có thể **live nhưng chưa ready**. Điều này hữu ích khi cấu hình readiness probe cho Kubernetes/load balancer.

Tuy nhiên một web server có thể đã bind port trong refresh trước khi runners kết thúc; nếu gọi trực tiếp URL mà không qua cơ chế readiness/load balancing, có thể vẫn thấy kết nối hoặc một số response. Do đó **“port mở” không phải “app ready”**.

Nếu runner mất thời gian quá lâu, startup probe hoặc deployment timeout có thể kích hoạt restart. Các biện pháp phù hợp là đo thời gian, giảm công việc bắt buộc, cấu hình timeout có lý do, cải thiện warm-up và thiết kế readiness chính xác; không đơn giản tăng timeout vô hạn.

### Khi runner ném lỗi

Một exception không xử lý trong `run(...)` được Boot xem là lỗi startup trong pha runner. Ứng dụng có thể phát `ApplicationFailedEvent`, ghi failure analysis và đóng context theo đường lỗi. `ApplicationReadyEvent` không xuất hiện nếu startup thất bại trước ready. Nhưng những side effect **đã hoàn thành trước khi ném lỗi** trong DB/API/file không tự được rollback chỉ vì context đóng.

### Khi runner tự tạo background thread

Ví dụ:

~~~java
@Override
public void run(ApplicationArguments args) {
    executor.execute(this::warmupInBackground);
}
~~~

Đây là đoạn minh họa chưa độc lập, giả sử có `executor` và phương thức `warmupInBackground`. `run` trả về ngay sau khi submit task; Boot có thể đạt ready **trước** khi warm-up hoàn tất. Chỉ dùng khi việc nền không phải điều kiện chặn readiness, hoặc bạn có cơ chế readiness khác phản ánh trạng thái thực.

Đừng spawn thread không quản lý trong mỗi startup rồi quên dọn khi shutdown; sử dụng `TaskExecutor`/`SmartLifecycle` hoặc cơ chế job/consumer có shutdown hook thích hợp.

## 11. Kiểm soát lỗi và chính sách retry

Runner là một phần của startup, nên phải quyết định **lỗi nào là fatal** và **lỗi nào có thể bỏ qua**.

### Lỗi fatal

Nếu thiếu điều kiện bắt buộc (ví dụ sai schema dữ liệu tối thiểu, thiếu khóa thiết yếu, không thể xác minh cấu hình an toàn), thường nên:

1. Ném một exception có thông điệp **hành động được**, không lộ secret.
2. Để startup thất bại và hạ tầng orchestration báo lỗi.
3. Có cảnh báo/log/metric cho nguyên nhân chính.
4. Tránh tiếp tục đến ready khi ứng dụng chắc chắn không thể phục vụ đúng.

### Lỗi có thể retry

Với tài nguyên bên ngoài tạm unavailable:

1. Chọn timeout cho từng lần gọi.
2. Có retry hữu hạn, backoff và jitter khi phù hợp.
3. Quy định hành vi sau khi hết retry: fail-fast hay degrade có chủ đích.
4. Bảo đảm thao tác retry **idempotent**, tránh tạo dữ liệu trùng.
5. Không dùng vòng lặp `while(true)` không có deadline trong `run`.

### Lỗi best-effort

Nếu tác vụ chỉ phục vụ tiện ích, chẳng hạn nạp sẵn gợi ý tìm kiếm không thiết yếu, có thể bắt lỗi, ghi cảnh báo và để ứng dụng tiếp tục. Nhưng không được ghi `READY` rồi giả định warm-up chắc chắn thành công. Health/metrics cần phản ánh tình trạng thực nếu nó quan trọng cho vận hành.

Một lựa chọn thiết kế sai thường gặp là bắt `Exception` rồi `printStackTrace()` và tiếp tục trong mọi trường hợp. Điều đó làm mất ranh giới giữa lỗi cấu hình nghiêm trọng và lỗi phụ không bắt buộc.

## 12. Test runner tách biệt khỏi toàn bộ SpringApplication

Vì cả hai runner đều là class Java thông thường, có thể kiểm tra logic mà không cần boot toàn bộ context, bằng cách gọi trực tiếp `run` với dữ liệu đầu vào kiểm soát được.

Ví dụ **minh họa kiểm thử thủ công** `OptionsRunner` với `DefaultApplicationArguments`:

~~~java
ApplicationArguments arguments = new DefaultApplicationArguments(
        "--mode=test",
        "--tag=a",
        "--tag=b",
        "sample.txt");

OptionsRunner runner = new OptionsRunner();
runner.run(arguments);
~~~

Đoạn này chưa phải file test độc lập; cần import `org.springframework.boot.ApplicationArguments` và `org.springframework.boot.DefaultApplicationArguments`, đồng thời đặt trong project chứa `OptionsRunner`. Expected lines từ runner:

~~~text
APP_RUNNER: mode=[test]
APP_RUNNER: tags=[a, b]
APP_RUNNER: nonOptions=[sample.txt]
~~~

Tương tự, kiểm tra `CommandLineRunner` bằng cách gọi:

~~~java
new RawArgumentsRunner().run("--mode=test", "sample.txt");
~~~

Dòng tương ứng:

~~~text
CMD_RUNNER: raw=[--mode=test, sample.txt]
~~~

Kiểm thử logic trực tiếp **không kiểm tra** được việc Spring Boot gọi runner theo thứ tự lifecycle. Muốn kiểm tra integration, chạy SpringApplication context hoặc dùng công cụ test của Spring Boot, xác minh các mốc `ApplicationStartedEvent` → runner → `ApplicationReadyEvent` và lỗi startup như demo.

Nên tránh unit test chỉ dựa trên thứ tự mọi log framework (vì phụ thuộc phiên bản, cấu hình và môi trường). Có thể dùng spy/recorded state/structured logs để khẳng định callback nào diễn ra và quan hệ trước-sau quan trọng.

## 13. Lỗi thường gặp và cách sửa

**1. “Runner chạy ngay khi bean được tạo.”** Sai. Constructor/`@PostConstruct` chạy trong initialization; Boot gọi `run` sau refresh.

**2. “CommandLineRunner luôn chạy sau ApplicationRunner.”** Sai. Hai loại cùng thuộc một pha và được sắp thứ tự theo `@Order`/`Ordered`, không theo tên interface.

**3. “ApplicationRunner chỉ là CommandLineRunner với tên dài hơn.”** Sai về dữ liệu đầu vào. `ApplicationRunner` nhận `ApplicationArguments` đã phân tích option/non-option; `CommandLineRunner` nhận raw string array. Mục đích lifecycle giống nhau.

**4. “--dry-run=false nghĩa là containsOption('dry-run') trả false.”** Sai. `containsOption` kiểm tra sự hiện diện; nếu cần giá trị boolean, phải parse và validate.

**5. “--mode demo luôn tương đương --mode=demo.”** Không nên dựa vào đó. Dạng option có giá trị chuẩn là `--mode=demo`; khoảng trắng có thể tạo một non-option riêng.

**6. “Runner tự chạy lại khi có request.”** Sai. Runner chạy trong `SpringApplication.run`; HTTP request có lifecycle riêng.

**7. “@DependsOn đã bảo đảm thứ tự run.”** `@DependsOn` thiên về thứ tự tạo bean; thứ tự callback startup runner sử dụng `@Order`/`Ordered`.

**8. “Bean implements cả ApplicationRunner và CommandLineRunner chỉ gọi một run.”** Không bảo đảm như vậy; hai callback khác chữ ký đều có thể được gọi. Tránh implements đồng thời nếu muốn đúng một tác vụ.

**9. “Runner ném lỗi nhưng Spring Boot vẫn báo ready.”** Một lỗi không xử lý trong runner thường làm startup fail; đường ready thành công không được tiếp tục.

**10. “Bắt lỗi và chỉ printStackTrace là an toàn.”** Nếu tác vụ bắt buộc, cách này khiến hệ thống có thể báo ready khi điều kiện quan trọng chưa được thỏa mãn. Phải định nghĩa chính sách failure đúng với nghiệp vụ.

**11. “Dùng runner để làm việc đúng một lần toàn cluster.”** Mỗi instance có thể chạy runner trong startup của nó. Muốn một lần toàn hệ thống cần khóa/coordination hoặc job điều phối.

**12. “Dùng runner để chờ một hệ thống bên ngoài mãi mãi.”** Vòng lặp blocking vô hạn có thể khiến readiness mãi không đạt và deployment timeout. Dùng timeout/retry hữu hạn hoặc thiết kế trạng thái degraded rõ ràng.

**13. “Cổng web mở nghĩa là runner đã xong.”** Port có thể bind trước ready. Hạ tầng nhận traffic nên dựa trên readiness phù hợp.

**14. “@ApplicationRunner là annotation trên method.”** Không có annotation Boot mang tên đó cho callback chuẩn: `ApplicationRunner` là **interface**. Muốn dùng một lambda, trả interface từ `@Bean`.

**15. “ApplicationArguments luôn tự động convert thành kiểu ứng dụng cần.”** Nó cung cấp chuỗi đã parse, không validate hết range, enum hoặc schema. Hãy kiểm tra/convert tường minh hoặc dùng config binding thích hợp.

**16. “Một runner chạy xong nghĩa là tác vụ async do nó submit đã hoàn tất.”** Sai. Nếu `run` chỉ submit, readiness có thể đạt khi background task vẫn chạy.

**17. “Nếu startup fail, thao tác trước đó tự rollback.”** Context cleanup không tự rollback mọi side effect ngoài transaction. Cần idempotency, transaction boundary và cơ chế khôi phục.

**18. “Có runner trong một context được tạo thủ công nghĩa là nó tự chạy.”** Runner callback thuộc `SpringApplication`. Nếu bạn chỉ gọi `new AnnotationConfigApplicationContext(...)` hoặc `refresh()` trực tiếp, Boot không tự chạy toàn bộ pha runners theo cùng cách.

## 14. Bài tập thực hành

1. Chạy demo với `--mode=demo --tag=alpha --tag=beta job-42`. Ghi thứ tự event started, hai runner và event ready.
2. Đổi `@Order(10)` trên `OptionsRunner` thành `@Order(30)`. Dự đoán runner nào chạy trước, sau đó kiểm tra output.
3. Bỏ `@Order` khỏi cả hai class. Vì sao không nên viết test dựa vào thứ tự thực thi tình cờ quan sát được?
4. Thử `--dry-run`, `--dry-run=false` và thiếu `--dry-run`. So sánh `containsOption`, `getOptionValues` và ý nghĩa của từng kết quả.
5. Thử `--mode demo` thay vì `--mode=demo`. Quan sát phần option và non-option có gì khác.
6. Thử `--tag=a --tag=b --tag=c`. `ApplicationArguments` có thể lấy được bao nhiêu giá trị? `CommandLineRunner` thấy bao nhiêu raw tokens?
7. Thêm validation bắt buộc `--mode=...` vào `OptionsRunner`. Khi thiếu giá trị, exception nào nên được ném và thông điệp lỗi nên chứa gì?
8. Chạy `--fail-demo`. Vì sao `RawArgumentsRunner` và `ApplicationReadyEvent` không xuất hiện trong log?
9. Thêm một runner khác với `@Order(5)` để kiểm tra đầu vào. Nếu nó fail, các runner còn lại có tiếp tục không?
10. Thêm một bean `@PostConstruct` có log. So sánh thời điểm nó chạy với `ApplicationStartedEvent` và hai runner.
11. Thử chuyển một warm-up từ chạy đồng bộ trong `run` sang submit lên executor. Khi nào ready xuất hiện so với lúc warm-up hoàn tất?
12. Giả sử chạy 3 replicas. Nếu một runner insert 100 bản ghi seed mỗi lần startup, sẽ xảy ra nguy cơ gì? Hãy thiết kế một chiến lược idempotent.
13. Với ứng dụng web, dùng readiness probe để quan sát khoảng thời gian khi runner đang chạy. Vì sao có thể thấy TCP port đã mở nhưng readiness chưa accepting?
14. Viết unit test cho `OptionsRunner` bằng `DefaultApplicationArguments` và assert lỗi khi thiếu `--mode` bắt buộc.
15. Với job import chạy một lần rồi thoát, khi nào nên dùng `SpringApplication.exit`/`ExitCodeGenerator` thay vì coi đó là web server chạy mãi?
16. Một tác vụ gửi thông báo không bắt buộc thất bại giữa startup. Bạn nên fail startup hay ghi cảnh báo? Hãy nêu tiêu chí, timeout và cách quan sát vận hành.

## Ghi nhớ

- `ApplicationRunner` và `CommandLineRunner` là **hai callback Spring Boot** chạy sau `ApplicationContext.refresh()` nhưng trước khi `SpringApplication.run(...)` hoàn tất và ứng dụng đạt ready.
- `ApplicationRunner` nhận `ApplicationArguments` với option, non-option và source arguments; `CommandLineRunner` nhận raw `String... args`.
- Hai loại runner thuộc cùng một pha; dùng `@Order`/`Ordered` khi thứ tự quan trọng.
- Runner là **bean của context**, phương thức `run` không tự gọi bởi component scanning, không lặp theo request, timer hoặc thông điệp.
- Runner đồng bộ chặn sự tiến tới `ApplicationReadyEvent` cho đến khi hoàn tất; ném exception không xử lý thường làm startup thất bại.
- Nếu tác vụ là bắt buộc trước ready, runner có thể phù hợp. Nếu tác vụ là background dài hạn, cần lifecycle, timeout, health và cơ chế quản lý riêng.
- Spring event, readiness và port mở là **những tín hiệu khác nhau**. Đừng coi liveness correct hoặc TCP port đã bind là bằng chứng mọi runner đã xong.
- Mỗi replica/restart có thể chạy lại startup runner: thiết kế idempotency và xử lý lỗi dựa trên nghiệp vụ thực tế.

### Tài liệu tham khảo

- Spring Boot 3.3.13 — Using the ApplicationRunner or CommandLineRunner: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.command-line-runner
- Spring Boot 3.3.13 — ApplicationRunner Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3.13 — CommandLineRunner Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html
- Spring Boot 3.3.13 — ApplicationArguments Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Boot 3.3.13 — Application Events and Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework — Lifecycle Callbacks: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
