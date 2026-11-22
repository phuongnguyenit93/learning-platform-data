# Thiết kế tác vụ chạy một lần: thành công, lỗi đầu vào và lỗi thực thi

Một chương trình Spring Boot không nhất thiết phải là HTTP server chạy liên tục. Nó có thể là **one-shot job**: được shell, CI/CD, cron, Kubernetes Job hoặc một bộ điều phối kích hoạt, nhận đối số, xử lý một đơn vị công việc, giải phóng tài nguyên rồi **kết thúc JVM với mã thoát phản ánh kết quả thật**.

Ví dụ: nhập dữ liệu, đồng bộ một lô đơn hàng, chạy một bước migration, tái lập chỉ mục, xuất báo cáo hay kiểm tra cấu hình. Với các tác vụ này, dòng log “Completed” không đủ: shell và job controller thường dựa vào **process exit code** để đánh giá thành công/thất bại.

Bài học thiết kế ba kết quả rõ ràng:

| Kết quả | Điều kiện | Exit code minh họa |
|---|---|---|
| Thành công | Đầu vào hợp lệ; xử lý hoàn tất; kết quả cần thiết đã được xác nhận | `0` |
| Lỗi đầu vào | Thiếu/sai/không hợp lệ arguments; chưa nên thực hiện tác vụ | `2` |
| Lỗi thực thi | Input hợp lệ nhưng trong lúc chạy gặp lỗi, timeout hoặc commit thất bại | `10` |

**Mã `2` và `10` là quy ước của ví dụ, không phải mã chuẩn bắt buộc của Spring Boot.** Mỗi hệ thống có thể xây dựng hợp đồng khác, nhưng phải tài liệu hóa ý nghĩa, mã cụ thể và chính sách retry tương ứng.

Ví dụ chính dùng **Java 17+ và Spring Boot 3.3.x**. Trọng tâm gồm `ApplicationRunner`, `ApplicationArguments`, `ExitCodeGenerator`, `SpringApplication.exit(...)`, `System.exit(...)`, kiểm thử mã thoát thật và xử lý lỗi ngoài luồng chạy bình thường.

## 1. Phân biệt process exit code với trạng thái ứng dụng

**Exit code** là số nguyên OS hoặc process supervisor nhận khi một tiến trình chấm dứt. Theo quy ước Unix, `0` thường có nghĩa thành công, mã khác 0 thường có nghĩa lỗi. Với các shell Unix, có những hạn chế về phạm vi exit status và quy ước mã dựa trên signals; để dễ tích hợp, thường chọn các mã nhỏ, không âm.

Các tín hiệu dưới đây không tự thay thế process exit status:

- `HTTP 200` hoặc `HTTP 500` là kết quả **một request**, không phải toàn bộ job.
- `ApplicationContext.isActive()` chỉ cho biết context đang active.
- `ApplicationReadyEvent` là một mốc startup của Spring Boot, không tự chứng minh dữ liệu nghiệp vụ đã được commit bền vững.
- In `EXIT_CODE=10` vào log **không làm OS nhận mã 10** nếu JVM cuối cùng kết thúc bình thường với mã 0.
- Exception bị catch rồi không báo outcome có thể khiến job **thất bại nhưng process báo 0**.
- `SpringApplication.exit(context)` lấy mã thoát và đóng context; cần phân biệt với `System.exit(code)`, lệnh yêu cầu JVM kết thúc với mã đó.

Hợp đồng kỳ vọng:

~~~text
Bắt đầu
   |
   v
Parse + validate arguments
   |
   +--- thiếu/sai ----> INPUT_ERROR (code 2)
   |
   v
Thực thi nghiệp vụ
   |
   +--- lỗi ----------> EXECUTION_ERROR (code 10)
   |
   v
Xác nhận kết quả/commit
   |
   +--- hoàn tất -----> SUCCESS (code 0)
   |
   v
Đóng resources / ApplicationContext
   |
   v
OS nhận exit code
~~~

Cần **xác định kết quả cuối cùng trước khi truyền mã cho OS**. Nếu một worker còn đang chạy trong background, không được coi “đã submit task thành công” là “đã xử lý hoàn tất”.

## 2. Vì sao ApplicationRunner phù hợp cho one-shot job?

Spring Boot gọi các bean `ApplicationRunner` và `CommandLineRunner` **sau khi ApplicationContext refresh**, nhưng **trước khi `SpringApplication.run(...)` hoàn tất**. Đây là thời điểm phù hợp để xử lý nghiệp vụ cần các Spring beans đã được inject, chẳng hạn datasource, HTTP client, repository hoặc transaction service.

Luồng rút gọn:

~~~text
main(String[] args)
    |
    +-- SpringApplication.run(args)
    |        |
    |        +-- Load bean definitions
    |        +-- Create/inject singleton beans
    |        +-- Refresh ApplicationContext
    |        +-- Call ApplicationRunner.run(ApplicationArguments)
    |                    |
    |                    +-- Validate arguments
    |                    +-- Execute job
    |                    +-- Save outcome
    |
    +-- SpringApplication.exit(context)
    |        |
    |        +-- Read ExitCodeGenerator bean
    |        +-- Close context and destroy beans
    |
    +-- System.exit(exitCode)
             |
             +-- Shell / Kubernetes / CI sees status
~~~

Đối với tác vụ batch không phục vụ request HTTP, nên đặt `WebApplicationType.NONE` để không tạo web server giữ tiến trình sống ngoài nhu cầu. Chỉ dùng web environment khi job thực sự cần một HTTP endpoint và bạn đã thiết kế riêng thời điểm kết thúc.

Không nên chạy import hoặc migration nặng trong constructor hay `@PostConstruct`: đó là callback tạo bean, không phải một nơi tốt để điều phối kết quả, phân loại mã lỗi và xử lý việc chạy một lần sau khi cấu hình hoàn tất.

### ApplicationArguments khác raw String[]

`ApplicationRunner.run(ApplicationArguments args)` nhận interface cho phép đọc:

| API | Ý nghĩa |
|---|---|
| `getSourceArgs()` | Toàn bộ arguments gốc |
| `getOptionNames()` | Tên các option, ví dụ `count` |
| `containsOption("flag")` | Flag/option có xuất hiện hay không |
| `getOptionValues("count")` | Danh sách giá trị của option, hoặc `null` nếu vắng mặt |
| `getNonOptionArgs()` | Positional arguments không phải option |

Ví dụ `--count=3 --dry-run report.csv`: `count` và `dry-run` là options, `report.csv` là non-option. Đối với những option có giá trị, nên dùng dạng `--count=3`, không suy đoán `--count 3` sẽ được parse giống hệt.

`getOptionValues("count")` có ba trạng thái cần phân biệt:

~~~text
Không có --count                 -> null
Có --count nhưng không có giá trị -> []
Có --count=3                    -> ["3"]
Có --count=3 --count=4          -> ["3", "4"]
~~~

Tùy hợp đồng, một option lặp có thể hợp lệ hoặc là lỗi. Ví dụ bên dưới yêu cầu chính xác **một** giá trị `count`.

## 3. Quy ước lỗi đầu vào và lỗi thực thi

Không nên gộp tất cả exception thành một mã duy nhất:

| Ví dụ | Loại đề xuất | Vì sao? |
|---|---|---|
| Thiếu `--count` | Input error | Không thể chạy nếu chưa có tham số |
| `--count=abc` | Input error | Sai kiểu dữ liệu |
| `--count=0` khi miền hợp lệ là 1–1000 | Input error | Sai ràng buộc nghiệp vụ |
| Truyền hai `--count` | Input error | Không rõ giá trị phải sử dụng |
| Unknown option không được phép | Input error | Sai interface của job |
| Database timeout trong xử lý | Execution error | Input có thể hoàn toàn hợp lệ |
| Lỗi I/O khi đang ghi output | Execution error | Công việc thất bại ở runtime |
| Commit transaction không thành công | Execution error | Kết quả chưa hoàn tất bền vững |
| Bug gây `NullPointerException` | Execution/internal failure | Không nên đổ nhầm cho người vận hành |

Ranh giới có thể khác theo ứng dụng. Ví dụ file `--input=/missing.csv` được phát hiện trước khi xử lý có thể được xếp input error; cùng file bị xóa giữa chừng lại là execution failure. Cần tài liệu hóa quyết định, không tự động kết luận mọi `IOException` đều thuộc một nhóm.

**Retry policy cũng khác:** lỗi input thường cần **sửa input**, còn execution failure có thể tạm thời hoặc vĩnh viễn. Retry mã 10 chỉ an toàn khi nghiệp vụ có thiết kế idempotency, timeout, backoff và giới hạn số lần thử.

## 4. Ví dụ Spring Boot chạy được: mã 0, 2 và 10

Chương trình sau tính tổng các số nguyên từ 1 đến `count`. Flag `--fail-execution` cố ý làm tác vụ thất bại sau item thứ nhất. Mọi thao tác trong demo chỉ xảy ra **trong bộ nhớ**, không cần database, file hay HTTP service để kết quả có thể kiểm chứng.

### 4.1 Cấu trúc dự án

~~~text
one-shot-job/
├── build.gradle
└── src/
    └── main/
        ├── java/com/example/oneshot/OneShotJobApplication.java
        └── resources/application.properties
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.1.0'

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

springBoot {
    mainClass = 'com.example.oneshot.OneShotJobApplication'
}

tasks.named('bootJar') {
    archiveFileName = 'one-shot-job.jar'
}
~~~

Tệp `src/main/resources/application.properties`:

~~~properties
spring.application.name=one-shot-job
logging.level.root=WARN
~~~

Mục đích của mức log `WARN` ở ví dụ là giảm nhiễu để quan sát các dòng chương trình in. Production cần logging đầy đủ hơn cho lỗi thực thi và correlation/job ID.

### 4.2 File Java đầy đủ

Tạo `src/main/java/com/example/oneshot/OneShotJobApplication.java`:

~~~java
package com.example.oneshot;

import java.util.List;
import java.util.Set;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OneShotJobApplication {

    private static final int SUCCESS = 0;
    private static final int INVALID_INPUT = 2;
    private static final int EXECUTION_ERROR = 10;

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(OneShotJobApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);

        // run() gọi runner trước khi trả ApplicationContext.
        ConfigurableApplicationContext context =
                application.run(args);

        // Đóng context và lấy mã từ ExitCodeGenerator bean.
        int exitCode = SpringApplication.exit(context);
        System.out.println("EXIT_CODE=" + exitCode);

        // Trả mã cho hệ điều hành / process supervisor.
        System.exit(exitCode);
    }

    @Bean
    JobOutcome jobOutcome() {
        return new JobOutcome();
    }

    @Bean
    ApplicationRunner oneShotJob(JobOutcome outcome) {
        return args -> {
            try {
                JobOptions options = parseOptions(args);
                long checksum = execute(options);

                outcome.record(SUCCESS);
                System.out.println(
                        "SUCCESS items=" + options.count()
                                + " checksum=" + checksum);
            } catch (InvalidInputException ex) {
                outcome.record(INVALID_INPUT);
                System.err.println(
                        "INPUT_ERROR: " + ex.getMessage());
            } catch (RuntimeException ex) {
                outcome.record(EXECUTION_ERROR);
                System.err.println(
                        "EXECUTION_ERROR: " + ex.getMessage());
            }
        };
    }

    private static JobOptions parseOptions(
            ApplicationArguments args) {

        Set<String> supported =
                Set.of("count", "fail-execution");

        if (!args.getNonOptionArgs().isEmpty()) {
            throw new InvalidInputException(
                    "positional arguments are not supported");
        }

        for (String name : args.getOptionNames()) {
            if (!supported.contains(name)) {
                throw new InvalidInputException(
                        "unknown option --" + name);
            }
        }

        List<String> values = args.getOptionValues("count");
        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new InvalidInputException(
                    "expected exactly one --count=<1..1000>");
        }

        final int count;
        try {
            count = Integer.parseInt(values.get(0));
        } catch (NumberFormatException ex) {
            throw new InvalidInputException(
                    "--count must be an integer");
        }

        if (count < 1 || count > 1000) {
            throw new InvalidInputException(
                    "--count must be in [1,1000]");
        }

        boolean simulateFailure =
                args.containsOption("fail-execution");

        if (simulateFailure
                && !args.getOptionValues(
                        "fail-execution").isEmpty()) {
            throw new InvalidInputException(
                    "--fail-execution does not accept a value");
        }

        return new JobOptions(count, simulateFailure);
    }

    private static long execute(JobOptions options) {
        long checksum = 0;

        for (int item = 1; item <= options.count(); item++) {
            checksum += item;

            if (options.simulateFailure() && item == 1) {
                throw new IllegalStateException(
                        "simulated failure after item 1");
            }
        }

        return checksum;
    }

    private record JobOptions(
            int count, boolean simulateFailure) {
    }

    public static final class JobOutcome
            implements ExitCodeGenerator {

        // Không mặc định thành công nếu runner chưa báo kết quả.
        private volatile int code = EXECUTION_ERROR;

        void record(int code) {
            this.code = code;
        }

        @Override
        public int getExitCode() {
            return code;
        }
    }

    private static final class InvalidInputException
            extends RuntimeException {

        InvalidInputException(String message) {
            super(message);
        }
    }
}
~~~

### 4.3 Giải thích cơ chế trong code

**Spring Application setup**

`application.setWebApplicationType(WebApplicationType.NONE)` ngăn việc tạo HTTP server cho tác vụ batch. `application.run(args)` khởi tạo container và gọi `ApplicationRunner`.

**Input validation**

`parseOptions(...)` chặn unknown option, positional arguments, thiếu hoặc lặp count, giá trị rỗng, không phải số và ngoài phạm vi. Khi validation thất bại, `execute(...)` chưa được gọi. Đây là lựa chọn quan trọng để tránh side effects trước khi biết input hợp lệ.

**Execution**

`execute(...)` xử lý các items và tính checksum. `--fail-execution` là cờ mô phỏng lỗi thực thi **sau khi bắt đầu xử lý**, nhằm tách rõ failure trong nghiệp vụ với failure do input.

**Outcome**

Bean `JobOutcome` implement `ExitCodeGenerator`. `SpringApplication.exit(context)` sẽ xem xét các generator beans, lấy kết quả đã ghi và đóng context. Biến `volatile` đủ cho ví dụ đồng bộ này; nếu chuyển sang async work phải kiểm soát completion và visibility riêng.

**Process exit**

Chỉ `main()` gọi `System.exit(exitCode)`. Không kết thúc JVM ngay trong runner, tránh bỏ qua việc đọc outcome và đóng context có chủ đích.

**Exception handling**

Bắt `RuntimeException` trong ví dụ là cách ánh xạ lỗi của demo về code 10. Với production, cần log stack trace và dữ liệu chẩn đoán có kiểm soát thay vì chỉ một message; không bắt `Throwable` rồi che giấu lỗi nghiêm trọng của JVM.

**Một điều cần lưu ý:** vì runner đã catch lỗi và return bình thường, Spring Boot có thể phát `ApplicationReadyEvent` như khi startup thành công, dù outcome nghiệp vụ là 2 hoặc 10. Chương trình này **không phục vụ traffic và thoát ngay sau đó**, nên đó là một cách biểu diễn outcome hợp lệ cho batch. Không dùng nguyên mẫu này cho service web chạy lâu mà readiness phải phản ánh failure.

### 4.4 Build và chạy qua JAR

Với JDK 17+ và dự án có Gradle wrapper:

~~~bash
./gradlew bootJar
java -jar build/libs/one-shot-job.jar --count=3
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootJar
java -jar .\build\libs\one-shot-job.jar --count=3
~~~

Nếu chưa có Gradle wrapper, cần cài hoặc tạo wrapper tương thích. Vì đây là Spring Boot project, không thể chạy `javac OneShotJobApplication.java` đơn lẻ nếu không có classpath của Spring Boot/Spring Framework.

**Chạy JAR trực tiếp quan trọng hơn dùng mỗi `bootRun` khi kiểm thử exact exit code**, bởi Gradle là một process wrapper có thể báo status riêng của task thất bại, không bảo đảm giữ nguyên giá trị 2/10 do chương trình trả.

## 5. Kết quả kiểm chứng ba trường hợp

### 5.1 Thành công

~~~bash
java -jar build/libs/one-shot-job.jar --count=3
echo $?
~~~

Những dòng do code chương trình in trên **stdout**:

~~~text
SUCCESS items=3 checksum=6
EXIT_CODE=0
~~~

Giá trị của `echo $?` trên shell Unix phải là **`0`** khi chạy trực tiếp và hoàn tất bình thường. Tổng `1+2+3=6` là kết quả deterministic, không cần external dependency.

### 5.2 Lỗi đầu vào

~~~bash
java -jar build/libs/one-shot-job.jar --count=abc
echo $?
~~~

Dòng chương trình in trên **stderr**:

~~~text
INPUT_ERROR: --count must be an integer
~~~

Dòng in trên **stdout**:

~~~text
EXIT_CODE=2
~~~

Exit status thực là **`2`**. Hàm `execute(...)` không chạy, vì lỗi được phát hiện ngay khi parse. Các trường hợp đầu vào sai khác cùng nhóm:

| Arguments | Lý do |
|---|---|
| Không truyền `--count` | Thiếu tham số |
| `--count` | Không có giá trị |
| `--count=0` hoặc `--count=1001` | Ngoài phạm vi 1–1000 |
| `--count=3 --count=4` | Option lặp |
| `--count=3 input.csv` | Không hỗ trợ positional arguments |
| `--count=3 --other=yes` | Unknown option |
| `--count=3 --fail-execution=yes` | Flag không nhận value |

### 5.3 Lỗi thực thi

~~~bash
java -jar build/libs/one-shot-job.jar --count=3 --fail-execution
echo $?
~~~

Dòng trên **stderr**:

~~~text
EXECUTION_ERROR: simulated failure after item 1
~~~

Dòng trên **stdout**:

~~~text
EXIT_CODE=10
~~~

Shell nhận **`10`**. Input `--count=3` hợp lệ, nhưng tác vụ thất bại sau item đầu tiên. Trong demo không ghi dữ liệu ngoài; với job thật, **đã có thể có một phần side effect** trước khi lỗi. Vì vậy retry phải dựa vào transaction, checkpoint và idempotency.

**Không dựa vào thứ tự xen kẽ stdout/stderr** nếu console hoặc CI gộp cả hai luồng: chúng có thể được buffer khác nhau. Dùng process status để xác minh kết quả.

### 5.4 Windows PowerShell

~~~powershell
java -jar .\build\libs\one-shot-job.jar --count=3
$LASTEXITCODE

java -jar .\build\libs\one-shot-job.jar --count=abc
$LASTEXITCODE

java -jar .\build\libs\one-shot-job.jar --count=3 --fail-execution
$LASTEXITCODE
~~~

Ba giá trị mong đợi lần lượt là `0`, `2`, `10`. `$LASTEXITCODE` phải được đọc ngay sau native process tương ứng, tránh nhầm với một command khác vừa chạy.

## 6. Vì sao cần SpringApplication.exit và System.exit?

Đoạn từ ví dụ:

~~~java
ConfigurableApplicationContext context =
        application.run(args);

int exitCode = SpringApplication.exit(context);
System.exit(exitCode);
~~~

Đây là code trong `main` đã có `application` và import phù hợp. Hai lệnh cuối làm hai việc khác nhau:

| API | Chức năng |
|---|---|
| `SpringApplication.exit(context)` | Hỏi `ExitCodeGenerator`, tính mã thoát, đóng context nếu có thể, trả số nguyên |
| `System.exit(exitCode)` | Yêu cầu JVM kết thúc với mã đó để OS/launcher quan sát |

Nếu chỉ gọi `SpringApplication.exit(context)` rồi in mã, tiến trình có thể chưa trả đúng mã đó cho OS. Ngược lại, nếu `System.exit(0)` được gọi trước khi job hoàn tất hoặc trước khi outcome được cập nhật, hệ thống điều phối có thể nhận **thành công giả**.

### Nhiều ExitCodeGenerator thì sao?

Spring Boot hỗ trợ các bean `ExitCodeGenerator` và các generator được truyền trực tiếp vào `SpringApplication.exit(context, ...)`. Khi có nhiều generator, Boot dùng mã **khác 0 đầu tiên** theo thứ tự áp dụng; có thể dùng `Ordered` hoặc `@Order` để điều khiển thứ tự.

Với batch đơn giản, nên có **một nguồn kết quả thống nhất**. Nếu nhiều tầng cùng quyết định mã thoát, cần quy tắc ưu tiên minh bạch, ví dụ execution failure ưu tiên trước warning, không để một bean tình cờ ghi đè outcome của bean khác.

`JobOutcome` trong ví dụ khởi đầu bằng `EXECUTION_ERROR=10` nhằm tránh tự báo thành công nếu runner chưa ghi kết quả. Tuy nhiên nếu Spring Boot thất bại quá sớm trước khi runner/context hoàn tất, đường exception handling của startup vẫn phải được xử lý riêng.

## 7. Một phương án khác: để exception thoát và map lỗi

Ví dụ chính dùng `Outcome` để xử lý ba tình huống một cách xác định. Nhưng Spring Boot cũng cho phép:

- Exception implement `ExitCodeGenerator`.
- Bean `ExitCodeExceptionMapper` ánh xạ exception sang mã thoát trong quá trình xử lý startup failure.

Một class **minh họa riêng**, chưa tích hợp vào chương trình ở mục 4:

~~~java
import org.springframework.boot.ExitCodeGenerator;

public final class InvalidArgumentsFailure
        extends RuntimeException
        implements ExitCodeGenerator {

    public InvalidArgumentsFailure(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 2;
    }
}
~~~

Nếu exception này được ném ở một pha mà Spring Boot xử lý như startup failure, framework có thể lấy mã từ `getExitCode()`. Ngoài ra, một bean kiểu `ExitCodeExceptionMapper` có thể duyệt loại exception/cause chain và trả một mã thích hợp.

Ví dụ **factory method minh họa** đặt trong class cấu hình với import cần thiết:

~~~java
@Bean
ExitCodeExceptionMapper exitCodeExceptionMapper() {
    return exception -> {
        // Hợp đồng ví dụ: lỗi chưa phân loại thành mã 10.
        return 10;
    };
}
~~~

**Cẩn thận:** nếu lỗi xảy ra rất sớm trước khi context tạo được mapper bean, mapper không nhất thiết có mặt. Không coi một bean mapper là cơ chế universal cho mọi lỗi JVM.

### Hai mô hình có sự khác biệt trong lifecycle

| Thiết kế | Runner gặp lỗi | Spring Boot nhìn nhận | Cách lấy exit code |
|---|---|---|---|
| **Lưu Outcome** như ví dụ | Catch lỗi, ghi 2/10, return bình thường | Runner hoàn tất; startup tiếp tục | `SpringApplication.exit(context)` sau `run` |
| **Ném exception** | Exception thoát khỏi runner | `SpringApplication.run` có thể thất bại, `ApplicationFailedEvent` | Boot startup-failure handling và generator/mapper có sẵn |

Nếu `SpringApplication.run(...)` ném exception trước khi trả context, **không được viết logic giả định đã có context từ `run` để gọi `SpringApplication.exit(context)` ở dòng tiếp theo**.

Đối với one-shot không có web traffic, mô hình lưu Outcome thường dễ test process exit một cách deterministic. Với service dài hạn, mô hình ném failure có thể phù hợp hơn vì readiness/startup events phải phản ánh thất bại.

## 8. Lỗi bootstrap khác lỗi đầu vào của job

Một one-shot job có thể thất bại **trước khi ApplicationRunner được gọi**:

- Bean không được tạo do dependency hoặc cấu hình sai.
- Không đọc được config, secret, connection pool initialization.
- Có lỗi classpath, unsupported Java runtime.
- Spring context refresh không thành công.

Với những tình huống này, `JobOutcome` có thể chưa được tạo hoặc chưa cập nhật; không khẳng định mọi lỗi bootstrap sẽ luôn có mã 10 từ ví dụ. Cần thiết kế startup failure policy riêng và kiểm tra bằng **quá trình khởi động JVM thật**.

Gợi ý phân loại:

~~~text
Bootstrap failure
    -> technical/startup failure handling

Valid Spring context + invalid job arguments
    -> input error (2)

Valid context + valid arguments + failed job
    -> execution error (10)

Valid context + job completed
    -> success (0)
~~~

Nếu muốn chuẩn hóa thêm startup failure thành mã 20, cần thiết kế cơ chế cho cả trường hợp context chưa có mapper bean; không bắt tất cả exception ở `main` rồi vô điều kiện `System.exit(0)`.

## 9. Thành công thật sự phải bao gồm hoàn tất, không chỉ “đã submit”

Một lỗi nguy hiểm là:

~~~java
@Async
public void importAsync() {
    // Công việc mất nhiều phút.
}

@Bean
ApplicationRunner runner(ImportService service) {
    return args -> service.importAsync();
}
~~~

Đây là **hai đoạn code minh họa**, cần class `ImportService`, `@EnableAsync` và khai báo bean phù hợp; không phải code chạy độc lập.

Trong trường hợp proxy async có hiệu lực, runner có thể kết thúc **ngay khi submit**, trước khi import thực sự xử lý/commit. Nếu `main` gọi exit 0, OS nhận success trong khi background task còn dở.

Cách xử lý đúng là chờ completion với timeout rõ ràng:

~~~java
CompletableFuture<ImportResult> future =
        importService.importAsync();

ImportResult result =
        future.get(timeoutSeconds, TimeUnit.SECONDS);
~~~

Đây là đoạn minh họa trong service có các type/biến đã khai báo. Production còn cần xử lý `InterruptedException`, `ExecutionException`, `TimeoutException`, cancellation và rollback/compensation.

**Success phải dựa vào hợp đồng nghiệp vụ**, ví dụ:

1. Input hợp lệ.
2. Các item cần xử lý đã được thực hiện.
3. Transaction/output đã được commit hoặc publish thành công.
4. Các ack/checkpoint cần thiết đã lưu bền vững.
5. Không còn task quan trọng chưa được await.
6. Chỉ sau đó ghi mã `0`.

Một method chạy xong mà không ném exception không tự chứng minh các bước trên đã hoàn tất nếu nó che lỗi, trả future chưa complete hoặc chỉ gửi message vào queue trong bộ nhớ.

## 10. Retry: tránh biến lỗi thực thi thành trùng dữ liệu

Giả sử một job xử lý 1000 records nhưng thất bại sau record thứ 600. Mã 10 cho biết **job thất bại**, không nói những records 1–599 đã ghi hay chưa.

Những tình huống cần phân biệt:

| Thời điểm lỗi | Side effect có thể xảy ra? | Retry cần làm gì? |
|---|---|---|
| Parse arguments | Chưa, nếu validation trước execution | Sửa input; thường không retry nguyên yêu cầu |
| Giữa quá trình xử lý | Có | Kiểm tra checkpoint, transaction, idempotency |
| Sau commit nhưng trước khi OS nhận code 0 | Có thể đã thành công nghiệp vụ | Đối soát durable state, tránh chạy trùng |
| JVM bị SIGKILL hoặc OOMKilled | Không đủ thông tin từ mã 0/2/10 | Recovery theo persisted job state |

Với job có side effects, nên có:

- **job ID** ổn định để nhận diện lần chạy/retry.
- **idempotency key** cho các thao tác có nguy cơ lặp.
- **checkpoint/offset** được lưu bền vững sau những bước hoàn tất.
- **transaction boundary** và cơ chế ack/commit theo đúng yêu cầu.
- **retry với backoff, giới hạn** và phân biệt lỗi tạm thời/vĩnh viễn.
- **metrics/logs** có processed count và failure stage.

Một `ConcurrentHashMap` trong JVM không thay thế durable state khi container có thể restart. Nếu đã commit một giao dịch nhưng JVM chết trước khi báo success, lần retry phải có cách nhận ra kết quả đã tồn tại.

## 11. Dùng exit code trong shell và CI

POSIX shell:

~~~bash
java -jar build/libs/one-shot-job.jar --count=3
status=$?

if [ "$status" -eq 0 ]; then
    echo "batch succeeded"
elif [ "$status" -eq 2 ]; then
    echo "invalid arguments: change input"
else
    echo "execution/startup failure: investigate"
fi
~~~

Lưu `$?` **ngay sau lệnh Java**; bất kỳ command tiếp theo cũng có thể ghi đè giá trị.

Với shell script dùng `set -e`, một command trả mã khác 0 có thể làm script thoát trước khi bạn kiểm tra mã. Dùng `if command; then ... else ... fi` hoặc một cơ chế kiểm soát lỗi có chủ đích, thay vì thêm `|| true` để che toàn bộ thất bại.

Ví dụ:

~~~bash
if java -jar build/libs/one-shot-job.jar --count=abc; then
    echo "success"
else
    code=$?
    echo "job failed with code=$code"
fi
~~~

Trên PowerShell:

~~~powershell
java -jar .\build\libs\one-shot-job.jar --count=abc
$code = $LASTEXITCODE

if ($code -eq 2) {
    Write-Host "Input error - fix arguments"
}
~~~

Đừng phụ thuộc vào từ “SUCCESS” trong log. Pipeline phải kiểm tra **status của process con**, không phải exit code của một wrapper hoặc lệnh echo ở phía sau.

## 12. Kubernetes Job: success và failed Pod

Một one-shot Spring Boot batch có thể chạy như Kubernetes Job:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: one-shot-demo
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: app
          image: example.invalid/one-shot-job:demo
          args: ["--count=3"]
~~~

Đây là ví dụ manifest để **giải thích**; image `example.invalid/...` là placeholder, cần image thật trước khi deploy.

Theo cơ chế Job/Pod thông thường:

- Container exit với mã 0: run được coi là hoàn tất thành công.
- Container exit khác 0: Job có thể ghi nhận failure và retry tùy `backoffLimit`, `restartPolicy` và các chính sách khác.
- `restartPolicy: Never` không đồng nghĩa **Job không retry**; controller có thể tạo Pod mới.
- `--count=abc` là input error; retry lặp lại input cũ sẽ tiếp tục lỗi, trừ khi job spec được sửa.
- Platform termination như OOMKilled/SIGKILL không nhất thiết tạo mã ứng dụng theo 0/2/10.

Nếu muốn điều phối dựa trên mã cụ thể, Kubernetes có cơ chế như `podFailurePolicy` ở môi trường/phiên bản phù hợp. Nhưng **exit code chỉ là tín hiệu**: hệ thống điều phối phải được cấu hình để không retry mã input invalid, hoặc chỉ retry những lỗi được đánh giá là transient.

CronJob có thể tạo Job ở nhiều thời điểm, nên không tự bảo đảm một nghiệp vụ thực thi đúng một lần toàn cụm. Vẫn cần idempotency, job key và chính sách concurrency.

## 13. Kiểm thử chính xác exit code

Có ít nhất hai cấp độ:

### A. Unit test logic

Kiểm tra input parser và chức năng xử lý:

- `--count=3` hợp lệ.
- Thiếu `--count`, `--count` không có giá trị, `--count=abc`, `--count=0`, `--count=1001` đều sai.
- Repeated count và unknown option bị từ chối.
- `--fail-execution` là flag, không nhận value.
- `execute(...)` tính đúng `checksum=6` khi count 3.
- `--fail-execution` đi vào execution error, không bị hiểu là input error.
- Validation hoàn tất trước khi có side effects.

### B. Process-level integration test

Chạy các lệnh **`java -jar` thật**:

1. `--count=3` → exit 0.
2. `--count=abc` → exit 2.
3. `--count=3 --fail-execution` → exit 10.
4. Đặt timeout cho child process để tránh test treo.
5. Đối chiếu stdout/stderr và actual process status.
6. Xác nhận context đóng tài nguyên sau khi run hoàn tất.
7. Chạy trong cùng môi trường Java, launcher và OS như production khi có thể.

Ví dụ dùng Java 17 `ProcessBuilder` (một đoạn minh họa trong test class đã có import):

~~~java
Process child = new ProcessBuilder(
        "java", "-jar",
        "build/libs/one-shot-job.jar", "--count=3")
        .inheritIO()
        .start();

boolean finished = child.waitFor(30, TimeUnit.SECONDS);
if (!finished) {
    child.destroyForcibly();
    throw new IllegalStateException("job timed out");
}
if (child.exitValue() != 0) {
    throw new AssertionError(
            "Unexpected exit code: " + child.exitValue());
}
~~~

Đoạn cần import `java.util.concurrent.TimeUnit` và một JAR đã build. **Không gọi trực tiếp `main()` chứa `System.exit(...)` trong cùng JVM chạy JUnit tests**, vì nó có thể kết thúc luôn process test runner. Để unit-test, tách parser/execution/exit-code calculation; để kiểm tra OS status, dùng subprocess.

## 14. Cleanup và lỗi buộc kết thúc

`SpringApplication.exit(context)` đóng Spring context trong đường kết thúc chủ động, cho các bean có destroy callback cơ hội trả tài nguyên. Nhưng có những sự cố không theo đường này:

- `SpringApplication.run(...)` ném lỗi trước khi trả context.
- Process nhận `SIGKILL` hoặc container hết thời gian chờ kết thúc.
- JVM bị crash hoặc máy mất điện.
- Có thread I/O treo hoặc cleanup bị cắt ngang.
- Side effect remote đã xảy ra nhưng ứng dụng chưa nhận phản hồi.

Do đó `@PreDestroy` và `finally` rất cần thiết nhưng **không thể là bảo đảm duy nhất về đúng một lần thực thi**. Tác vụ thực tế cần durable status, retry/idempotency và khả năng resume/đối soát.

Không thêm `System.exit(0)` vào exception handler chung với mục đích “thoát gọn” khi job thất bại. Như vậy OS nhận success giả, khiến CI/JOB controller không có cơ sở phát hiện lỗi.

## 15. Những lỗi phổ biến

**Lỗi 1 — “Runner đã được gọi nên job chắc chắn thành công”.** Sai. Runner có thể throw, catch lỗi hoặc chỉ submit async work chưa hoàn tất.

**Lỗi 2 — “In mã lỗi vào log là đủ”.** Sai. Cần process exit status khác 0.

**Lỗi 3 — “SpringApplication.exit(context) tự kết thúc JVM”.** Không. Nó trả mã và đóng context; `System.exit(code)` yêu cầu JVM exit với status.

**Lỗi 4 — “Cứ catch Exception thì Spring Boot tự đánh dấu failure”.** Không nếu runner return bình thường. Bạn phải ghi outcome hoặc ném exception theo hợp đồng.

**Lỗi 5 — “Lỗi đầu vào và lỗi thực thi có thể gộp mã 2”.** Gây khó vận hành vì một loại nên sửa input, loại khác có thể retry.

**Lỗi 6 — “Mọi lỗi khác 0 nên retry ngay”.** Invalid input thường không tự hết; execution error phải xét transient/permanent và idempotency.

**Lỗi 7 — “Kết quả của một CompletableFuture chưa hoàn tất vẫn có thể báo success”.** Không. Cần await và xác nhận outcome theo timeout.

**Lỗi 8 — “Có ExitCodeGenerator bean thì mọi startup failure sớm đều có mã riêng”.** Không chắc. Exception có thể xảy ra trước khi bean được tạo.

**Lỗi 9 — “Dùng Gradle bootRun để kiểm tra chính xác mã 2/10 do Java trả”.** Không chắc vì Gradle là process wrapper; chạy JAR trực tiếp.

**Lỗi 10 — “Mã 0 có nghĩa job sẽ không bao giờ chạy lại”.** Không. Cron/scheduler/retry/manual run có thể chạy lại; cần durable job ID và idempotency.

**Lỗi 11 — “Không có exception nghĩa là tất cả dữ liệu đã commit”.** Không nếu code swallow errors hoặc side effect bất đồng bộ.

**Lỗi 12 — “System.exit(0) là cách cleanup tốt nhất”.** Không. Nó có thể kết thúc trước khi xác nhận outcome, đóng resources hoặc worker completion.

## 16. Checklist thiết kế tác vụ chạy một lần

1. Định nghĩa success/input error/execution error và mã 0/2/10 bằng tài liệu.
2. Sử dụng `WebApplicationType.NONE` nếu không cần HTTP.
3. Parse và validate `ApplicationArguments` **trước side effects**.
4. Phân loại lỗi input theo hợp đồng, không biến bug thành lỗi input.
5. Dùng `ApplicationRunner` để chạy đúng một công việc được điều phối rõ.
6. Không trả success khi background tasks chưa hoàn tất hoặc transaction chưa commit.
7. Có một nơi lưu outcome và một điểm quyết định exit status.
8. Gọi `SpringApplication.exit(context)` để lấy mã, đóng context, rồi `System.exit(code)` khi cần OS status.
9. Xử lý riêng lỗi bootstrap trước khi runner chạy.
10. Test logic và test subprocess với actual exit code.
11. Tránh retry vô hạn lỗi input; thiết kế retry/backoff cho lỗi thực thi thích hợp.
12. Có idempotency, durable job state, checkpoint khi xử lý dữ liệu quan trọng.
13. Log job ID, outcome, processed count, failure stage và thời gian chạy; không lộ secret.
14. Kiểm tra cả tình huống process bị force kill, chưa kịp cleanup.
15. Xác minh chính sách Kubernetes Job/CI hiểu đúng mã thoát.

### Tài liệu tham khảo

- Spring Boot 3.3 — SpringApplication / ApplicationRunner / Application Exit: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — SpringApplication Javadoc, `exit(...)`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 — `ApplicationArguments`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Boot 3.3 — `ExitCodeGenerator`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html
- Spring Boot 3.3 — `ExitCodeExceptionMapper`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeExceptionMapper.html
- Java 17 — `ProcessBuilder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html
- Kubernetes — Job: https://kubernetes.io/docs/concepts/workloads/controllers/job/

**Ghi nhớ:** một one-shot Spring Boot job cần **phân loại chính xác kết quả nghiệp vụ, đóng ApplicationContext và truyền đúng mã thoát cho hệ điều hành**. Trong ví dụ: **0 = thành công**, **2 = lỗi đầu vào**, **10 = lỗi thực thi**. `ApplicationRunner` chạy job; `ExitCodeGenerator` mang kết quả; `SpringApplication.exit` đóng context và trả mã; `System.exit` truyền mã tới shell/orchestrator. Chỉ báo thành công khi toàn bộ công việc cần thiết đã thực sự hoàn tất.
