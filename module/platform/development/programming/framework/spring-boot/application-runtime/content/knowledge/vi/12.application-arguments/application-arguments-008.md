# Kiểm tra đầu vào, thông báo cách dùng và tránh ghi bí mật ra log trong Spring Boot

## 1. Bài toán: đối số khởi động cũng là dữ liệu không đáng tin cậy

Một ứng dụng Spring Boot có thể nhận tham số từ dòng lệnh:

```bash
java -jar job.jar --mode=import --input=data.csv
```

Ví dụ này có hai option: `mode` và `input`. Người dùng có thể gõ thiếu option, nhập sai tên, lặp một option, đưa giá trị trống hoặc vô tình cung cấp mật khẩu ở vị trí mà hệ điều hành hay hệ thống logging nhìn thấy.

Một chương trình có hành vi khởi động đáng tin cậy cần thực hiện ba việc phối hợp:

1. **Kiểm tra đầu vào (validation):** xác định những option được hỗ trợ, số lượng giá trị, tính bắt buộc, định dạng và quan hệ giữa các option.
2. **Thông báo cách dùng (usage/help):** giải thích cú pháp hợp lệ, ví dụ chạy và lý do bị từ chối mà không tiết lộ dữ liệu nhạy cảm.
3. **Bảo vệ dữ liệu bí mật:** không in token, mật khẩu, khóa, connection string có credential hay toàn bộ đối số thô vào log, exception, metrics hoặc thông điệp lỗi.

Trong Spring Boot, ta thường sử dụng `ApplicationArguments` trong `ApplicationRunner` để kiểm tra đối số sau khi container đã dựng xong. `CommandLineRunner` nhận mảng `String[]` gốc nếu thực sự cần tự xử lý chuỗi. Cần chọn phương án phù hợp với thời điểm kiểm tra.

**Nguyên tắc xuyên suốt:** dữ liệu dòng lệnh là input bên ngoài, không nên tin cậy chỉ vì nó được truyền cho phương thức `main(String[] args)`.

## 2. Spring Boot xử lý tham số ứng dụng như thế nào?

Một ứng dụng Java có entry point:

```java
public static void main(String[] args) {
    SpringApplication.run(MyApplication.class, args);
}
```

Dòng trên là minh họa, cần một class `MyApplication` có cấu hình Spring Boot và import `SpringApplication`. Mảng `args` do JVM cung cấp, sau khi shell đã phân tách các đối số theo quy tắc của shell.

Spring Boot tạo đối tượng `ApplicationArguments` khi khởi chạy. API chủ yếu:

| API | Ý nghĩa |
| --- | --- |
| `getSourceArgs()` | Trả lại mảng đối số gốc. **Có thể chứa secret**, không log trực tiếp |
| `getOptionNames()` | Tập tên option được nhận dạng, ví dụ `mode`, `input` |
| `containsOption("mode")` | Có xuất hiện option tên `mode` hay không |
| `getOptionValues("mode")` | Danh sách giá trị gắn với option; có thể `null` nếu option vắng |
| `getNonOptionArgs()` | Các đối số không theo cú pháp option, ví dụ `data.csv` |
| `ApplicationRunner.run(ApplicationArguments)` | Callback sau refresh, nhận object đã phân loại đối số |
| `CommandLineRunner.run(String...)` | Callback sau refresh, nhận các chuỗi gốc |

**Lưu ý cụ thể với `getOptionValues`:**

- Option **không xuất hiện**: trả `null`.
- Option **có xuất hiện nhưng không có giá trị**, chẳng hạn `--verbose`: trả danh sách rỗng.
- Option `--mode=import`: trả danh sách có phần tử `"import"`.
- Option bị lặp, như `--mode=check --mode=import`: có thể nhận nhiều giá trị; cần quy tắc rõ ràng để từ chối hoặc xử lý.
- Option có giá trị rỗng `--mode=`: không được xem là mode hợp lệ, ngay cả khi parser vẫn tạo đối tượng option.

Phân biệt `null` với `List.of()` rất quan trọng: `--help` dạng cờ không có giá trị là hợp lệ, nhưng `--mode` không có giá trị thì không hợp lệ trong một CLI yêu cầu mode cụ thể.

### Cú pháp option nên dùng nhất quán

Với Spring Boot, dạng dễ kiểm soát là:

```bash
java -jar job.jar --mode=check
java -jar job.jar --mode=import --input=data.csv
java -jar job.jar --help
```

Khi truyền giá trị cho option, ưu tiên `--key=value`. Đừng mặc định rằng:

```bash
java -jar job.jar --mode import
```

được parser hiểu giống `--mode=import`. Trong cơ chế phân loại command-line option của Spring Boot, `--mode` có thể được xem là cờ không giá trị và `import` thành đối số không phải option. Đây là lý do hướng dẫn sử dụng phải trình bày đúng cú pháp và validation phải kiểm tra **cả option values lẫn positional arguments**.

Các công cụ shell/CLI khác có thể chấp nhận `--mode import`; đừng bê giả định của parser đó vào `ApplicationArguments` mà không kiểm thử.

## 3. Ba tầng validation: cú pháp, ngữ nghĩa và môi trường

Không nên chỉ kiểm tra “có option hay không”. Một chương trình đáng tin cần phân biệt:

| Tầng | Câu hỏi | Ví dụ lỗi | Cách xử lý |
| --- | --- | --- | --- |
| Cú pháp | Có dùng đúng tên và định dạng option? | `--mdoe=check`, `--mode`, lặp `--mode` | Báo cú pháp hợp lệ, từ chối đầu vào |
| Ngữ nghĩa | Giá trị có thuộc miền cho phép? Các option có tương thích? | `--mode=erase`, mode import thiếu input | Báo giá trị hợp lệ, điều kiện bắt buộc |
| Môi trường | Có quyền truy cập tài nguyên và cấu hình cần thiết? | File không tồn tại, thiếu quyền đọc, cấu hình credential chưa cấp | Báo lỗi môi trường theo cách an toàn, không phơi dữ liệu |

Ví dụ quy tắc cho một công cụ:

- `--help`: in hướng dẫn, không thực thi nghiệp vụ.
- `--mode=check`: chạy kiểm tra, không nhận `--input`.
- `--mode=import --input=data.csv`: chạy quy trình nhập dữ liệu, bắt buộc có `input`.
- Không chấp nhận positional arguments.
- Không chấp nhận option lạ trong CLI đơn giản.
- Không chấp nhận mode ngoài tập `check` / `import`.
- Không chấp nhận giá trị trống hoặc lặp lại cho option chỉ có một giá trị.
- Không nhận API token bằng option dòng lệnh. Credential được cấp qua môi trường hoặc secret manager phù hợp.

Những quy tắc này phải được tài liệu hóa và kiểm thử. Một option có thể hợp lệ về cú pháp nhưng không hợp lệ về ngữ nghĩa: `--mode=import` đúng cấu trúc nhưng thiếu `--input`.

## 4. Fail fast nhưng không để lộ dữ liệu người dùng

Khi thiếu hoặc sai tham số cần thiết, chương trình nên từ chối **trước khi thực hiện công việc nghiệp vụ**, đồng thời in hướng dẫn dễ hành động.

Ví dụ thông báo tốt:

```text
Input error: --mode must be check or import.
Usage:
  java -jar job.jar --mode=check
  java -jar job.jar --mode=import --input=data.csv
  java -jar job.jar --help
```

Ví dụ thông báo không nên dùng:

```text
Invalid args: [--mode=import, --input=/private/customer-list.csv,
               --api-token=secret-value-here]
```

Không phải mọi đường dẫn đều là secret, nhưng đường dẫn có thể tiết lộ cấu trúc hệ thống, tên khách hàng hoặc vị trí nội bộ. Một API token trong dòng lệnh còn nguy hiểm hơn vì có thể xuất hiện trong history, process list, crash report hoặc log.

Vì vậy:

- **Nói rõ tên tham số cần sửa** nếu tên đó là hằng số do chương trình kiểm soát.
- Với giá trị không hợp lệ, ưu tiên mô tả miền hợp lệ thay vì echo nguyên giá trị.
- Không in mảng `args` hoặc `ApplicationArguments.getSourceArgs()`.
- Không ghép secret vào message của exception.
- Dùng mã lỗi/exception có thông điệp không nhạy cảm.
- Có thể in usage ra `System.err` khi sai đầu vào, `System.out` khi người dùng yêu cầu `--help`.
- Không im lặng bỏ qua option lạ; việc gõ sai có thể khiến chương trình chạy sai chế độ.

**Định nghĩa fail fast ở đây là fail trước nghiệp vụ trong runner**, không có nghĩa Spring Boot chưa tạo context. `ApplicationRunner` được gọi **sau** refresh, có thể sau khi bean hoặc web server đã khởi tạo. Nếu một giá trị bắt buộc phải hợp lệ **trước khi tạo bean**, hãy dùng kiểm tra cấu hình sớm hơn; phần này được phân biệt tại mục 11.

## 5. Ví dụ hoàn chỉnh: CLI Spring Boot có validation và usage an toàn

Ví dụ dưới đây dùng Java 17+ và Spring Boot 3.3.x. Chạy non-web để không mở cổng HTTP. Mã cố tình **không thật sự đọc file**: nó tập trung vào kiểm tra tham số và chính sách log an toàn, giúp bạn nhìn rõ kết quả mà không cần dữ liệu thực.

### 5.1. Cấu trúc project

```text
safe-args-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          args/
            SafeArgsApplication.java
      resources/
        application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'safe-args-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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

Phiên bản 3.3.13 được chọn để minh họa hành vi của nhánh Spring Boot 3.3; dự án đang triển khai thực tế nên dùng phiên bản được tổ chức còn hỗ trợ và cập nhật bảo mật. Để chạy với `./gradlew`, project cần Gradle wrapper tương thích; file build trên không tự tạo wrapper.

`src/main/resources/application.properties`:

```properties
spring.application.name=safe-args-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
```

### 5.2. Source Java 17+

File `src/main/java/demo/args/SafeArgsApplication.java`:

```java
package demo.args;

import java.io.PrintStream;
import java.util.List;
import java.util.Set;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SafeArgsApplication {

    private static final Set<String> ALLOWED_OPTIONS =
            Set.of("help", "mode", "input");

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(SafeArgsApplication.class, args)) {
            // Đóng context tường minh sau khi runner hoàn tất.
        }
    }

    @Bean
    ApplicationRunner checkedJobRunner() {
        return arguments -> {
            // Chỉ hỗ trợ các option có tên được công bố.
            if (!ALLOWED_OPTIONS.containsAll(arguments.getOptionNames())) {
                reject("Unsupported option.");
            }

            // --help phải đứng một mình và không nhận giá trị.
            if (arguments.containsOption("help")) {
                List<String> helpValues =
                        arguments.getOptionValues("help");

                if (!helpValues.isEmpty()
                        || arguments.getOptionNames().size() != 1
                        || !arguments.getNonOptionArgs().isEmpty()) {
                    reject("Use --help without other arguments.");
                }

                printUsage(System.out);
                return;
            }

            // Không cho phép đối số positional ngoài dự kiến.
            if (!arguments.getNonOptionArgs().isEmpty()) {
                reject("Unexpected positional argument.");
            }

            String mode = oneValue(arguments, "mode", true);
            String input = oneValue(arguments, "input", false);

            if (!Set.of("check", "import").contains(mode)) {
                reject("--mode must be check or import.");
            }

            if ("import".equals(mode) && input == null) {
                reject("--input is required for import mode.");
            }

            if ("check".equals(mode) && input != null) {
                reject("--input is only supported in import mode.");
            }

            // Chỉ log mode đã xác thực và trạng thái boolean.
            // Tuyệt đối không log input path hay raw arguments.
            System.out.println("validated mode=" + mode);
            System.out.println("input supplied=" + (input != null));

            // Logic nghiệp vụ thực tế chỉ được gọi sau validation.
        };
    }

    private static String oneValue(
            ApplicationArguments args, String name, boolean required) {
        List<String> values = args.getOptionValues(name);

        if (values == null) {
            if (required) {
                reject("Missing required --" + name + ".");
            }
            return null;
        }

        if (values.size() != 1
                || values.get(0) == null
                || values.get(0).isBlank()) {
            reject("--" + name + " requires exactly one nonempty value.");
        }

        return values.get(0);
    }

    private static void reject(String message) {
        System.err.println("Input error: " + message);
        printUsage(System.err);

        // Không đưa đối số thô vào exception message.
        throw new IllegalArgumentException("Invalid command-line arguments.");
    }

    private static void printUsage(PrintStream out) {
        out.println("Usage:");
        out.println("  ./gradlew bootRun --args='--mode=check'");
        out.println(
                "  ./gradlew bootRun --args='--mode=import --input=data.csv'");
        out.println("  ./gradlew bootRun --args='--help'");
    }
}
```

**Giải thích từng quyết định:**

1. `SafeArgsApplication` là Spring Boot entry point. `SpringApplication.run` tạo/refresh context và gọi runner.
2. `checkedJobRunner` là một `ApplicationRunner` được đăng ký qua `@Bean`. Nó kiểm tra option trước khi thực hiện công việc.
3. `ALLOWED_OPTIONS` chỉ chứa tên option mà CLI hỗ trợ. Chương trình không in tên option lạ do người dùng cung cấp để tránh đưa dữ liệu ngoài ý muốn vào log.
4. `--help` được xử lý trước yêu cầu về `mode`. Người dùng có thể xem cách dùng khi chưa biết cú pháp.
5. `--help` chỉ được chấp nhận **khi đứng một mình**. `--help=anything` hoặc `--help --mode=check` sẽ bị từ chối.
6. `oneValue` phân biệt option vắng mặt, không có giá trị, giá trị rỗng và nhiều giá trị.
7. `mode` được kiểm tra theo whitelist trước khi in ra. `input` chỉ được ghi log ở dạng boolean, không ghi đường dẫn thực.
8. `reject` in thông báo và usage ra stderr, rồi ném exception có message cố định không chứa dữ liệu người dùng.
9. `try-with-resources` đóng context sau khi `run` thành công, phù hợp ứng dụng CLI ngắn hạn. Với ứng dụng web/daemon, không sao chép cách đóng ngay context này.
10. Nếu runner ném lỗi, `run` không trả về context cho khối try; Spring Boot có đường xử lý startup failure của chính nó. Không kỳ vọng log của startup fail chỉ gồm những dòng trong `reject`.

### 5.3. Chạy các trường hợp hợp lệ

Khi project có Gradle wrapper, chạy:

```bash
./gradlew bootRun --args='--mode=check'
```

Các dòng do code demo in ra:

```text
validated mode=check
input supplied=false
```

Thử mode import:

```bash
./gradlew bootRun --args='--mode=import --input=data.csv'
```

Các dòng:

```text
validated mode=import
input supplied=true
```

Không có đường dẫn `data.csv` trong phần output từ code, dù chương trình đã nhận và kiểm tra sự tồn tại về mặt cú pháp của option. Demo **chưa đọc file**; trong ứng dụng thực phải kiểm tra đường dẫn và quyền truy cập ở tầng nghiệp vụ phù hợp.

### 5.4. Trợ giúp cho người dùng

Chạy:

```bash
./gradlew bootRun --args='--help'
```

Các dòng do `printUsage` in ra:

```text
Usage:
  ./gradlew bootRun --args='--mode=check'
  ./gradlew bootRun --args='--mode=import --input=data.csv'
  ./gradlew bootRun --args='--help'
```

Sau khi in usage, runner trả về bình thường. **Spring Boot vẫn có thể phát `ApplicationReadyEvent`** bởi `--help` không phải lỗi trong mã này; nó chỉ làm runner bỏ qua nghiệp vụ. Với một CLI non-web ngắn hạn, context được đóng ở cuối `try` trong `main`.

Nếu ứng dụng có nhiều runner, `return` trong một runner **không dừng những runner khác**. Muốn `--help` ngăn mọi công việc khác, cần có cơ chế điều phối rõ hoặc một runner duy nhất quản lý toàn bộ startup task, thay vì dựa vào việc return cục bộ.

### 5.5. Trường hợp lỗi có thể tái hiện

**Thiếu mode:**

```bash
./gradlew bootRun
```

Phần đầu thông báo từ code:

```text
Input error: Missing required --mode.
Usage:
  ./gradlew bootRun --args='--mode=check'
  ./gradlew bootRun --args='--mode=import --input=data.csv'
  ./gradlew bootRun --args='--help'
```

Sau đó Spring Boot có thể log startup failure và stack trace; Gradle có thể báo task `bootRun` thất bại. Không coi khối trên là **toàn bộ** stdout/stderr của tiến trình.

**Sai mode:**

```bash
./gradlew bootRun --args='--mode=delete'
```

Thông báo chính:

```text
Input error: --mode must be check or import.
```

**Thiếu input trong mode import:**

```bash
./gradlew bootRun --args='--mode=import'
```

Thông báo:

```text
Input error: --input is required for import mode.
```

**Lặp mode:**

```bash
./gradlew bootRun --args='--mode=check --mode=import'
```

Thông báo:

```text
Input error: --mode requires exactly one nonempty value.
```

**Giá trị mode rỗng:**

```bash
./gradlew bootRun --args='--mode='
```

Kết quả từ validation có thể là:

```text
Input error: --mode requires exactly one nonempty value.
```

Các ví dụ lỗi trên đều kéo theo usage in từ `reject`. Logic không in nguyên giá trị input sai vào message, ngoại trừ các giá trị literal được code định nghĩa sẵn trong mô tả miền hợp lệ.

**Option lạ:**

```bash
./gradlew bootRun --args='--mdoe=check'
```

Thông báo:

```text
Input error: Unsupported option.
```

Vì vậy gõ nhầm tên option không bị âm thầm coi như chạy chế độ mặc định. Việc không echo tên option lạ là một chính sách log thận trọng: tên option có thể do người dùng tùy ý đặt và đôi khi chứa chuỗi nhạy cảm.

## 6. Khi nào dùng ApplicationRunner, khi nào dùng CommandLineRunner?

Có thể kiểm tra input ở cả hai interface:

```java
@Component
public final class RawArgsRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        // Phải tự phân loại option và positional arguments.
    }
}
```

Đây là đoạn class minh họa, cần import `Component` và `CommandLineRunner`, đặt trong file `RawArgsRunner.java` ở package được scan. Nó không cung cấp các phương thức `getOptionValues` hoặc `getNonOptionArgs`.

`ApplicationRunner` thường tiện hơn vì dùng `ApplicationArguments`:

```java
@Component
public final class StructuredArgsRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        boolean dryRun = args.containsOption("dry-run");
        System.out.println("dryRun=" + dryRun);
    }
}
```

Đoạn trên cần import `Component`, `ApplicationRunner` và `ApplicationArguments`. Một cờ `--dry-run` không cần giá trị; nhưng nếu muốn chỉ chấp nhận dạng cờ, nên xác nhận không có giá trị ngoài ý muốn:

```java
if (args.containsOption("dry-run")) {
    List<String> values = args.getOptionValues("dry-run");

    if (values != null && !values.isEmpty()) {
        throw new IllegalArgumentException(
                "--dry-run must not have a value.");
    }
}
```

Đoạn này nằm trong một method có biến `args` kiểu `ApplicationArguments`, với import `java.util.List`. Không log bất kỳ giá trị thực nào khi báo lỗi.

**Đừng đăng ký cả `RawArgsRunner` và `StructuredArgsRunner` vào demo đầy đủ ở mục 5 rồi kỳ vọng output không thay đổi.** Những đoạn này là các biến thể để giải thích API; nếu thêm làm bean thật, chúng sẽ tham gia thứ tự runner và có thể in thêm log.

## 7. ApplicationArguments nhận option nhiều giá trị ra sao?

Một số CLI cho phép option lặp lại:

```bash
java -jar job.jar --tag=finance --tag=nightly
```

Khi đó `getOptionValues("tag")` có thể chứa hai phần tử. Ứng dụng cần quyết định **cho phép nhiều giá trị hay không**.

Nếu option chỉ được dùng một lần, đoạn `oneValue` ở mục 5 yêu cầu đúng một phần tử.

Nếu option hợp lệ khi lặp, có thể xác nhận danh sách không rỗng và mỗi phần tử đều đạt điều kiện:

```java
List<String> tags = args.getOptionValues("tag");

if (tags == null) {
    tags = List.of();
}

for (String tag : tags) {
    if (tag == null || !tag.matches("[a-zA-Z0-9_-]{1,32}")) {
        throw new IllegalArgumentException("Invalid --tag option.");
    }
}
```

Đây là snippet đặt trong method có `args` kiểu `ApplicationArguments`; cần import `java.util.List`. Regex giới hạn ký tự được phép, không cho phép một tag bất kỳ trở thành log injection hay nhãn metric không giới hạn.

**Chú ý:** Regex chỉ kiểm tra cú pháp; nó không xác định tag có hợp lệ theo nghiệp vụ hay không. Nếu tag là mã khách hàng hoặc tên môi trường, cần kiểm tra allowlist/registry phù hợp trước khi sử dụng.

Không sử dụng:

```java
System.out.println("tags=" + tags);
```

trong mã production khi chưa đánh giá rõ tags có thể chứa PII hoặc dữ liệu nhạy cảm. Một trường hợp tưởng vô hại có thể trở thành kênh lộ dữ liệu khi input sau này được mở rộng.

## 8. Vì sao không nên đưa secret vào command-line arguments?

Ví dụ cần tránh:

```bash
java -jar job.jar --api-token=my-super-secret-token
java -Dservice.password=my-super-secret-password -jar job.jar
```

Hai dòng này là **ví dụ phản diện**, không phải cú pháp được khuyến nghị sử dụng. Ngay cả khi code không log, bí mật vẫn có thể bị lộ qua:

- **Shell history**: lệnh có thể được lưu vào lịch sử terminal.
- **Danh sách tiến trình**: tùy hệ điều hành, cấu hình quyền và công cụ quan sát, process arguments có thể được hiển thị.
- **Hệ thống điều phối**: command spec, job logs hoặc thông tin triển khai có thể chứa đối số.
- **Crash/error reporting**: metadata khởi chạy có thể được thu thập để chẩn đoán.
- **CI/CD logs**: step có thể in lại lệnh đã chạy hoặc tham số truyền vào.
- **Support tickets và screenshots**: người dùng thường chụp toàn bộ terminal khi báo lỗi.

**Không log secret** là điều cần làm, nhưng **không truyền secret trong CLI ngay từ đầu** mới giảm nhiều rủi ro.

### Những kênh cấp secret phù hợp hơn

Tùy môi trường triển khai:

1. **Secret manager** của nền tảng: cung cấp secret qua cơ chế nhận dạng và cấp quyền kiểm soát; ưu tiên khi có hạ tầng phù hợp.
2. **File bí mật được mount với phân quyền hạn chế**: container hoặc host cung cấp file và ứng dụng đọc an toàn. Không đưa file vào source repository.
3. **Biến môi trường**: dễ dùng trong demo và một số môi trường, nhưng **không hoàn toàn an toàn**; có thể bị người có quyền xem process environment, cấu hình deployment hoặc tool debugging đọc được.
4. **Cơ chế identity/role ngắn hạn**: tránh lưu credential tĩnh nếu có thể nhận token bằng danh tính của workload.

Trong các kênh này, cần kiểm soát vòng đời, quyền truy cập tối thiểu, rotation, không log dữ liệu và cách xử lý khi secret bị lộ. Không có kênh nào tự tạo bảo đảm tuyệt đối.

### Ví dụ đọc secret từ môi trường mà không in giá trị

```java
String token = System.getenv("APP_API_TOKEN");

if (token == null || token.isBlank()) {
    throw new IllegalStateException(
            "Required credential APP_API_TOKEN is unavailable.");
}

// Sử dụng token với client được cấu hình đúng.
// Không in token, không nối token vào exception message.
```

Đây là snippet trong một method Java có quyền truy cập `System.getenv`. Phần tích hợp thực tế cần SDK/HTTP client tương ứng và chính sách bảo vệ credential. Đừng làm `System.out.println(token)` hoặc `log.debug("token={}", token)` kể cả trong môi trường development.

**Tư duy quan trọng:** thông báo thiếu secret nêu **tên cấu hình** do code định nghĩa, không nêu giá trị secret hay dữ liệu nội bộ.

## 9. Những thói quen logging dễ làm rò rỉ bí mật

### 9.1. In toàn bộ args

```java
// Tránh: có thể chứa password, token hoặc đường dẫn nhạy cảm.
System.out.println(Arrays.toString(args));

// Tránh: dữ liệu nguồn có thể chứa mọi option truyền vào.
log.info("startup args={}", applicationArguments.getSourceArgs());
```

Hai đoạn là minh họa các mẫu **không nên dùng**; cần import `Arrays` và biến `log`/`applicationArguments` thích hợp nếu đặt trong một class thật.

Thay bằng:

```java
log.info(
        "Startup validation completed, mode={}, inputSupplied={}",
        safeMode,
        input != null);
```

Đoạn này minh họa khi đã có logger SLF4J `log`, một `safeMode` được kiểm tra theo allowlist và một biến `input`. Không phải chương trình biên dịch độc lập. Tham số log nên là dữ liệu **đã xác minh không nhạy cảm**, không chỉ được đổi tên từ `rawArgs` thành `safeMode`.

### 9.2. Ghép input vào exception

Không nên:

```java
throw new IllegalArgumentException(
        "Invalid token: " + suppliedToken);
```

Ngoại lệ có thể đi tới log tự động của Spring Boot, APM hoặc crash-reporting. Thay bằng:

```java
throw new IllegalArgumentException(
        "Invalid credential configuration.");
```

Đây là snippet minh họa. Khi báo lỗi xác thực, cũng tránh tiết lộ quá nhiều thông tin giúp người dùng không có quyền suy đoán trạng thái nội bộ.

### 9.3. Logging nguyên Environment hoặc properties

```java
// Tránh trong startup diagnostics không kiểm soát:
environment.getPropertySources().forEach(System.out::println);
```

Một số property source hoặc object debug representation có thể chứa thông tin cấu hình nhạy cảm; logging không có bộ lọc có thể làm lộ dữ liệu.

Khi cần quan sát cấu hình, nên:

- Chỉ log **tên property** đã được cho phép hoặc trạng thái `configured=true/false`.
- Log giá trị **chỉ sau khi xác minh là an toàn** (ví dụ mode đã qua allowlist).
- Dùng tính năng sanitize/redact của công cụ vận hành khi có, nhưng không dựa hoàn toàn vào filter mặc định.
- Kiểm tra các trường log của agent, reverse proxy, job orchestration và endpoint diagnostics.

### 9.4. Chỉ che một phần token có đủ không?

Ví dụ `token=abc****xyz` vẫn tiết lộ một phần thông tin và có thể tạo rủi ro nếu được kết hợp với những log khác. Nếu không có nhu cầu vận hành rõ ràng, **đừng log token ở bất kỳ dạng nào**. Khi cần tương quan, có thể log một mã định danh không nhạy cảm do hệ thống quản lý riêng, không phải một lát cắt của secret.

### 9.5. Log injection qua newline hoặc ký tự điều khiển

Đối số người dùng có thể chứa newline, tab hoặc ký tự điều khiển. Khi đưa nguyên vào log, một chuỗi có thể làm giả dòng log mới hoặc làm hỏng cấu trúc phân tích.

Ví dụ:

```text
--operator=alice
WARN: system compromised
```

Đây là minh họa dữ liệu có nhiều dòng, không phải lệnh shell cần chạy. Cách giảm rủi ro:

- Chỉ log trường đã qua validation và có tập giá trị hạn chế.
- Nếu bắt buộc log text tự do, dùng structured logging, encode/escape và giới hạn độ dài.
- Không đưa dữ liệu tự do thành log key, metric name hoặc label có cardinality không giới hạn.
- Giữ message lỗi dựa trên template cố định, không nối raw user input.

## 10. Thông báo help/usage nên thiết kế thế nào?

Một help message tốt trả lời được bốn câu hỏi:

1. Chương trình làm gì?
2. Cú pháp chạy đúng là gì?
3. Những option nào bắt buộc/tùy chọn?
4. Có ví dụ hợp lệ nào để sao chép và thay đổi?

Mẫu thân thiện:

```text
Usage:
  java -jar job.jar --mode=check
  java -jar job.jar --mode=import --input=data.csv
  java -jar job.jar --help

Options:
  --mode=check    Verify configuration without importing.
  --mode=import   Import a supported file.
  --input=FILE    Required only for import mode.
  --help          Show this help text.

Security:
  Supply credentials via an approved secret mechanism.
  Do not pass passwords or API tokens on the command line.
```

Không nhất thiết mọi chương trình phải in chính xác mẫu trên. Trong ví dụ runnable mục 5, `printUsage` cố tình ngắn để output dễ kiểm tra. Với CLI thực tế, bổ sung mô tả, lệnh ví dụ cho Linux/Windows phù hợp và chỉ rõ exit code được cam kết.

**Những điều không nên làm:**

- Dồn tất cả lựa chọn vào một dòng rất dài, không xuống hàng.
- Chỉ báo `Invalid input` nhưng không chỉ cách sửa.
- In toàn bộ đối số người dùng mỗi khi lỗi.
- Hiển thị giá trị bí mật hiện có như một “default” trong help.
- Gợi ý cách truyền token bằng `--password=...` trong hướng dẫn mặc định.
- Dùng những option chưa được ứng dụng hỗ trợ, khiến ví dụ copy chạy sai.

### stdout và stderr

Thông lệ hữu ích:

- `--help` hợp lệ: in usage ra **stdout** và hoàn tất bình thường.
- Input không hợp lệ: in thông báo lỗi/usage ra **stderr**, đánh dấu startup thất bại phù hợp.
- Log vận hành: dùng framework logging với policy có kiểm soát.
- Kết quả máy đọc: nếu CLI được dùng trong script, giữ stdout có định dạng ổn định, không trộn JSON/CSV với progress log.

Dùng `System.err` để báo lỗi không tự động khiến exit code khác 0; lỗi/exit code cần có cơ chế riêng. Ngược lại, ném exception mà không in cách dùng có thể cho exit code thất bại nhưng trải nghiệm người dùng kém.

## 11. Thời điểm validation: ApplicationRunner không phải chặn mọi side effect trước refresh

`ApplicationRunner` được Spring Boot gọi **sau khi context đã refresh** và sau `ApplicationStartedEvent`, nhưng trước `ApplicationReadyEvent`.

```text
main(args)
   |
   +-- Tạo SpringApplication
   +-- Chuẩn bị Environment và configuration
   +-- Tạo context
   +-- Nạp bean definitions, refresh
   |      +-- tạo singleton cần thiết
   |      +-- có thể khởi động web server
   |
   +-- ApplicationStartedEvent
   |
   +-- ApplicationRunner / CommandLineRunner
   |      +-- Validate CLI arguments
   |      +-- Thực hiện công việc nếu hợp lệ
   |
   +-- ApplicationReadyEvent
   |
   +-- run() trả về nếu thành công
```

Do đó lời khuyên “validate sớm” phải có giới hạn:

- Với một công cụ CLI không mở web server, runner là điểm hợp lý để validate **trước nghiệp vụ**.
- Với ứng dụng web, web server có thể bắt đầu lắng nghe trong quá trình refresh **trước runner**. Đừng dựa duy nhất vào runner để ngăn mọi tương tác HTTP khi cấu hình đầu vào sai.
- Một `@PostConstruct` hoặc singleton initializer có thể đã tạo kết nối database hay gọi bên ngoài trước runner; runner không thể quay ngược các side effect đó.
- Nếu giá trị cấu hình quyết định bean nào được tạo, hãy validate ngay trong binding/configuration lifecycle phù hợp.

### Validation cấu hình qua @ConfigurationProperties

Với dữ liệu cấu hình có cấu trúc (khác với parser option bespoke), có thể dùng:

```java
@ConfigurationProperties(prefix = "job")
@Validated
public record JobProperties(
        @NotBlank String mode,
        @NotBlank String destination) {
}
```

Đoạn này là **mẫu minh họa cần cấu hình bổ sung**: import `ConfigurationProperties`, `Validated`, `jakarta.validation.constraints.NotBlank`; cần đăng ký properties bean (ví dụ `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`) và có provider Bean Validation phù hợp, thường bằng `spring-boot-starter-validation`. Tên `job.mode` / `job.destination` được bind từ các nguồn property chuẩn khi đã cấu hình.

Ví dụ property:

```properties
job.mode=check
job.destination=output
```

Nếu một field không được cấu hình hoặc vi phạm điều kiện, lỗi binding/validation có thể ngăn startup trong giai đoạn tạo bean phù hợp, **trước khi đến ApplicationRunner**. Tuy nhiên đây không phải cam kết kiểm tra xảy ra trước **mọi** bean hoặc mọi side effect; thứ tự các dependency còn phụ thuộc quá trình refresh.

Cần tránh sử dụng annotation validation kiểu `@NotBlank` rồi kỳ vọng tự có hiệu lực nếu chưa đăng ký provider/cấu hình binding phù hợp.

### Khi nào cần EnvironmentPostProcessor?

`EnvironmentPostProcessor` được thiết kế để tương tác với environment rất sớm, trước khi context được dựng hoàn chỉnh. Nếu cần áp dụng một chính sách **nguồn property** hoặc phát hiện cấu hình sai trước refresh, có thể dùng extension point thích hợp. Tuy nhiên nó cần đăng ký đúng cách và không có các bean nghiệp vụ để injection thông thường.

Đừng chuyển toàn bộ CLI logic sang một hook quá sớm chỉ vì tên gọi “fail fast”: thao tác sử dụng repository, transaction hoặc component do Spring quản lý cần bối cảnh sau refresh.

## 12. Exit code và ý nghĩa thất bại

CLI được gọi bởi shell, scheduler hoặc CI/CD thường cần mã thoát:

- `0`: thành công, bao gồm trường hợp in `--help` hợp lệ nếu đó là chính sách của ứng dụng.
- Giá trị khác `0`: lỗi cú pháp, lỗi cấu hình, lỗi xử lý dữ liệu hoặc lỗi hạ tầng.
- Có thể phân loại các mã khác nhau theo hợp đồng CLI, nhưng cần bảo đảm code thực thi đúng ở mọi đường đi.

Trong ví dụ mục 5, `IllegalArgumentException` thoát khỏi runner làm `SpringApplication.run` thất bại và quá trình chạy ứng dụng có thể kết thúc lỗi. **Ví dụ không cam kết một mã thoát cụ thể, chẳng hạn 2**, vì chính sách exit code còn phụ thuộc cách chạy, Boot failure handling và trình khởi chạy.

Spring Boot cung cấp `ExitCodeGenerator` và `SpringApplication.exit(...)` cho những kịch bản cần điều khiển mã thoát. Ví dụ một exception khai báo mã lỗi:

```java
import org.springframework.boot.ExitCodeGenerator;

public final class InvalidCliOptionsException
        extends RuntimeException implements ExitCodeGenerator {

    public InvalidCliOptionsException() {
        super("Invalid command-line arguments.");
    }

    @Override
    public int getExitCode() {
        return 2;
    }
}
```

Đây là class Java đầy đủ có thể nằm trong file `InvalidCliOptionsException.java`. Việc triển khai `ExitCodeGenerator` giúp Boot có thể **lấy mã lỗi từ exception trong quy trình startup**; việc JVM thực sự trả về mã 2 còn phụ thuộc đường xử lý và cách ứng dụng/launcher kết thúc, nên phải kiểm thử end-to-end.

Ví dụ dừng một ứng dụng sau khi `run` **thành công** với exit code được tính từ context:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(SomeApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
```

Đây là đoạn **minh họa**, yêu cầu `SomeApplication` tồn tại và import `SpringApplication`, `ConfigurableApplicationContext`. Nếu `run` ném exception thì đoạn lấy `context` không được thực thi; không thể dùng riêng đoạn này để xử lý mọi lỗi tham số. Ngoài ra `System.exit` kết thúc JVM, vì vậy không nên đưa nó vào thư viện hoặc server dùng chung một cách tùy tiện.

### Một lưu ý về --help

Một runner in help rồi `return` thường được Boot xem là **runner hoàn thành thành công**, không phải “hủy toàn bộ startup”. Nếu chương trình có nhiều runner hoặc là web service, những bean/runner khác vẫn có thể làm việc. Để hỗ trợ `--help` như một lệnh CLI thật sự với exit code/short-circuit rõ ràng, hãy thiết kế entry point hoặc orchestration một cách chuyên biệt, thay vì nghĩ `return` của một runner có tác dụng với toàn bộ `SpringApplication`.

## 13. Validate đường dẫn file mà không tiết lộ thông tin nhạy cảm

Với option `--input=...`, kiểm tra “chuỗi khác rỗng” chỉ là bước đầu. Nếu ứng dụng thật sự đọc file, thường cần:

1. Chuyển chuỗi thành `Path` theo ngữ nghĩa hệ thống.
2. Xác định đường dẫn tuyệt đối/tương đối, working directory và một thư mục gốc được phép.
3. Kiểm tra file có tồn tại, là regular file, có thể đọc và đúng định dạng được hỗ trợ.
4. Xem xét symlink, canonical path và ranh giới thư mục được cho phép.
5. Tránh thông báo lỗi chứa đường dẫn nhạy cảm hoặc nội dung file.
6. Thực hiện đọc bằng resource handling đúng cách, ví dụ `try-with-resources`.
7. Không tin rằng kiểm tra `Files.exists` trước đó bảo đảm file vẫn tồn tại ở thời điểm mở — có thể có thay đổi giữa kiểm tra và sử dụng.

Ví dụ snippet minh họa:

```java
Path path = Path.of(inputPath).toAbsolutePath().normalize();

if (!Files.isRegularFile(path) || !Files.isReadable(path)) {
    throw new IllegalArgumentException(
            "Input file is missing or unreadable.");
}
```

Đoạn này cần import `java.nio.file.Path` và `java.nio.file.Files`, biến `inputPath` đã có. Nó **chưa giải quyết đầy đủ vấn đề traversal/symlink và kiểm soát access**. Trong hệ thống xử lý file không tin cậy, cần xác lập allowed base directory, cân nhắc `toRealPath` khi phù hợp và kiểm soát quyền mở file ở thời điểm sử dụng.

Đừng log:

```java
System.err.println("Cannot open secret input: " + inputPath);
```

nếu đường dẫn có thể tiết lộ thông tin. Thông báo an toàn nên có mã lỗi cố định và hướng dẫn chung, đồng thời chỉ ghi thêm ngữ cảnh đã được phân loại là an toàn trong hệ thống diagnostics có quyền kiểm soát.

## 14. Tránh nhầm application arguments với cấu hình nội bộ của Spring Boot

Khi nhận `--key=value`, Spring Boot còn có thể đưa command-line properties vào `Environment` làm nguồn cấu hình ưu tiên cao, nếu cơ chế command-line property được bật.

Ví dụ:

```bash
java -jar job.jar --spring.profiles.active=prod --mode=check
```

Trường `spring.profiles.active` có ý nghĩa với Spring Boot, trong khi `mode` là option của CLI nghiệp vụ.

**Cần thận trọng với allowlist trong ví dụ mục 5.** `ALLOWED_OPTIONS` chỉ có `help`, `mode` và `input`, vì đây là **CLI nhỏ cố ý chỉ hỗ trợ ba option**. Do đó nó sẽ từ chối `--spring.profiles.active=prod` nếu truyền cùng vào `ApplicationArguments`.

Trong một ứng dụng thực tế cần cả Boot flags và CLI flags, có vài lựa chọn:

- Mở rộng allowlist một cách có chủ đích cho những cấu hình Bootstrap được phép qua CLI.
- Cung cấp cấu hình Spring Boot qua file/environment hoặc cách cấu hình riêng, không trộn vào cú pháp CLI nghiệp vụ.
- Dùng cơ chế phân tích command line chuyên dụng cho các lệnh phức tạp, xác định rõ option nào thuộc framework, option nào thuộc business.

**Không mặc định bất kỳ tên `spring.*` nào cũng an toàn** chỉ vì nó thuộc namespace framework: một số property có thể thay đổi môi trường chạy, logging, web server hoặc hành vi bảo mật.

Nếu ứng dụng là service phục vụ HTTP, thiết kế command-line validation phải phối hợp với chính sách deployment. Với một batch CLI biệt lập, whitelist nghiêm ngặt như ví dụ là lựa chọn hợp lý.

## 15. Những kiểu dữ liệu cần validate kỹ hơn chuỗi

Một CLI có thể nhận thêm số lượng bản ghi, timeout, ngày tháng hoặc boolean. Đừng chỉ parse xong là coi hợp lệ.

### 15.1. Số nguyên có giới hạn

```java
int batchSize;
try {
    batchSize = Integer.parseInt(rawBatchSize);
} catch (NumberFormatException ex) {
    throw new IllegalArgumentException(
            "--batch-size must be an integer.");
}

if (batchSize < 1 || batchSize > 1000) {
    throw new IllegalArgumentException(
            "--batch-size must be between 1 and 1000.");
}
```

Đoạn này cần `rawBatchSize` là chuỗi nhận từ option đã kiểm tra số lượng giá trị. Không đưa nguyên `rawBatchSize` vào lỗi; nếu chứa dữ liệu nhạy cảm hoặc dòng mới, log sẽ an toàn hơn.

### 15.2. Enum mode theo allowlist

```java
Set<String> modes = Set.of("check", "import");

if (!modes.contains(mode)) {
    throw new IllegalArgumentException(
            "--mode must be check or import.");
}
```

`mode` ở đây đã được xác định là một chuỗi không rỗng. Ưu điểm của allowlist là chỉ một số giá trị kiểm soát được đi vào nghiệp vụ và log, thay vì cho phép chuỗi tùy ý điều khiển trạng thái.

### 15.3. Duration

Đầu vào `--timeout=15s` cần parse theo cú pháp đã công bố và kiểm tra min/max, ví dụ phải dương và không vượt hạn mức bảo vệ. Có thể chọn `Duration.parse("PT15S")` nếu quyết định dùng cú pháp ISO-8601, hoặc API của Spring Boot cho cách viết đơn vị thân thiện khi tương thích. **Không âm thầm chấp nhận mọi đơn vị từ các parser khác nhau** nếu usage chỉ hướng dẫn một chuẩn.

### 15.4. Boolean flag

`--dry-run` dạng cờ không giá trị có thể được kiểm tra bằng `containsOption`. Nếu cú pháp công bố là `--dry-run=true|false`, phải parse và validate giá trị, không chỉ kiểm tra option xuất hiện. Lẫn lộn hai kiểu dễ khiến `--dry-run=false` vẫn được coi là bật khi code chỉ dùng `containsOption`.

### 15.5. Ngày/thời gian

Với `--date=2026-11-09`, dùng `LocalDate.parse` và kiểm tra miền ngày nghiệp vụ. Tránh dùng `new Date(...)` với chuỗi tùy ý hoặc rely vào timezone mặc định khi việc tính toán phụ thuộc mốc thời gian. Không phải dữ liệu được Java parse thành công cũng hợp lệ với hợp đồng API của CLI.

## 16. Testing: ma trận các trường hợp cần kiểm chứng

Một test tốt nên tách **parser/validator** khỏi logic nghiệp vụ để có thể kiểm tra nhanh. Ma trận tham khảo:

| Dòng lệnh | Kết quả mong đợi |
| --- | --- |
| `--help` | In usage ra stdout, bỏ qua nghiệp vụ của runner tương ứng |
| `--mode=check` | Hợp lệ, không cần input |
| `--mode=import --input=data.csv` | Hợp lệ về tham số |
| Không có args | Báo thiếu `--mode` |
| `--mode` | Báo mode cần một giá trị |
| `--mode=` | Báo giá trị mode rỗng |
| `--mode=delete` | Báo mode không thuộc allowlist |
| `--mode=check --mode=import` | Báo mode được khai báo lặp |
| `--mode=import` | Báo thiếu `--input` |
| `--mode=check --input=data.csv` | Báo input không hợp lệ ở mode check |
| `--mode=import --input=` | Báo giá trị input rỗng |
| `--mdoe=check` | Báo option không hỗ trợ |
| `--mode=check extra.csv` | Báo positional argument |
| `--help --mode=check` | Báo help phải đứng riêng |
| `--help=something` | Báo help không nhận giá trị |
| `--mode=check --api-token=SECRET` | Từ chối option lạ; không echo secret |

**Không dùng secret thật trong test.** Chuỗi `SECRET` trong dòng cuối chỉ là dữ liệu giả. Điều cần kiểm chứng là output, exception và logs không chứa payload giả được gắn nhãn nhạy cảm.

### Unit test không cần khởi động toàn bộ context

Spring Boot có `DefaultApplicationArguments` để tạo đối tượng từ mảng chuỗi:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.DefaultApplicationArguments;

ApplicationArguments args = new DefaultApplicationArguments(
        "--mode=import", "--input=data.csv");

System.out.println(args.getOptionValues("mode"));
System.out.println(args.getNonOptionArgs().size());
```

Kết quả:

```text
[import]
0
```

Đây là snippet đặt trong method hoặc JShell được cấu hình classpath Spring Boot phù hợp; không phải chương trình Java thuần chạy bằng `javac` mà không thêm thư viện.

Khi tách validation thành một service nhận `ApplicationArguments`, có thể test service với `DefaultApplicationArguments` mà không cần dựng toàn bộ context.

### Test output không chứa dữ liệu nhạy cảm

Ý tưởng:

1. Tạo một secret giả có chuỗi dễ nhận dạng, ví dụ `SENSITIVE_TEST_VALUE_123`.
2. Đưa secret giả vào một option không được hỗ trợ hoặc một input cố ý sai.
3. Capture stdout, stderr và logging output trong phạm vi test.
4. Assert **không có secret giả trong bất kỳ kênh output nào**.
5. Assert thông báo lỗi có hướng dẫn sử dụng và trạng thái thất bại phù hợp.

**Cẩn trọng:** test trong cùng tiến trình không bao quát mọi kênh như shell history, process list và log của scheduler. Muốn bảo đảm an toàn triển khai, phải đánh giá cả hạ tầng chạy lệnh.

### Integration test cho ApplicationRunner

Một bean `ApplicationRunner` được gọi bởi `SpringApplication` trong startup. Nếu chỉ dựng `ApplicationContext` bằng một công cụ kiểm tra bean definition, **không tự suy ra** runner sẽ được gọi. Test integration nên dùng đường bootstrap đúng với `SpringApplication.run` hoặc kiểm thử trực tiếp method `run` khi đã tách phụ thuộc.

Không kiểm thử bằng cách đóng context của toàn bộ một test suite đang được cache chỉ để quan sát exit code, vì có thể ảnh hưởng các test khác.

## 17. Lỗi phổ biến và hướng khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `args.getOptionValues("mode").get(0)` gây NPE | Option `mode` không xuất hiện | Kiểm tra `null` trước khi lấy phần tử |
| Gọi `get(0)` gây IndexOutOfBoundsException | Người dùng nhập `--mode` không có giá trị | Kiểm tra size và giá trị trước |
| Một option lặp vẫn được chấp nhận | Chỉ lấy phần tử đầu, bỏ qua các giá trị khác | Yêu cầu đúng một giá trị cho single-value option |
| `--mode import` không cho kết quả dự kiến | Parser xem `--mode` là flag, `import` là positional | Dùng `--mode=import` và document cú pháp |
| Gõ sai option nhưng job vẫn chạy | Không kiểm tra danh sách option names | Đặt allowlist/tên option được hỗ trợ |
| `--help` in đúng nhưng runner khác vẫn chạy | `return` chỉ kết thúc runner hiện tại | Dùng orchestrator hoặc thiết kế entry point riêng |
| `--help` không hiện usage | Logic yêu cầu mode trước khi xử lý help | Ưu tiên xử lý help hợp lệ trước mandatory options |
| Lỗi đầu vào nhưng exit code vẫn 0 | Chỉ in stderr rồi return | Có đường báo lỗi/exit code thật sự |
| Log chứa `--password=...` | Ghi `args`, `getSourceArgs` hoặc exception message chứa input | Không log raw args; dùng error message cố định |
| Log đã che token nhưng token vẫn lộ qua CI | Lệnh chứa secret được scheduler echo | Không truyền secret qua CLI; đổi cơ chế cấp |
| `--input` chứa newline gây hỏng log | In nguyên raw input | Không echo hoặc encode/escape với giới hạn |
| Runner validate thất bại nhưng web server đã mở | Runner chạy sau context refresh | Dùng config validation sớm hơn/readiness gating |
| Kiểm tra đường dẫn đúng nhưng đọc vẫn lỗi | Race condition, symlink, quyền hay file biến mất | Kiểm tra khi mở file và xử lý exception an toàn |
| Mode hợp lệ nhưng code còn thao tác nguy hiểm | Validation chỉ kiểm tra cú pháp, chưa kiểm tra quyền/nghiệp vụ | Thêm authorization và policy trước side effect |
| Test pass local nhưng khác khi chạy JAR | Khác args, environment, working directory | Test đúng dòng lệnh, nguồn config và cách đóng gói |
| Bật debug khiến lộ cấu hình | Log level/diagnostics quá chi tiết hoặc không có redaction phù hợp | Giới hạn log và kiểm tra secret hygiene trên môi trường vận hành |

Một quy trình chẩn đoán nhanh:

1. Chụp lại **cú pháp lệnh đã được làm sạch bí mật**; không yêu cầu người dùng gửi nguyên token.
2. Xác định đối số thuộc option, flag hay positional.
3. Kiểm tra giá trị vắng, trống, lặp hoặc nằm ngoài miền hợp lệ.
4. Kiểm tra thứ tự validation: help, allowlist, positional, required options, quan hệ giữa các option.
5. Xem lúc validation chạy: trước refresh hay sau refresh; side effect nào đã xảy ra trước đó?
6. Xác nhận thông báo lỗi và mã thoát theo hợp đồng CLI.
7. Kiểm tra stdout, stderr, stack trace, application logs và log của hạ tầng xem có lộ dữ liệu không.
8. Test trường hợp success, error và secret giả trước khi triển khai.

## 18. Checklist cho ứng dụng sản xuất

Trước khi đưa một CLI Spring Boot vào CI/CD, cron hoặc hệ thống batch, kiểm tra:

- [ ] Có tài liệu usage rõ, ví dụ hợp lệ và bảng option bắt buộc/tùy chọn.
- [ ] Dùng `ApplicationArguments` khi cần phân biệt option và positional.
- [ ] Kiểm tra tên option không được hỗ trợ và phát hiện lỗi gõ.
- [ ] Kiểm tra option vắng, giá trị trống, số lượng giá trị và giá trị lặp.
- [ ] Có allowlist/range cho mode, số lượng và giới hạn thời gian.
- [ ] Kiểm tra quan hệ giữa các option, không chỉ từng option riêng lẻ.
- [ ] `--help` có ngữ nghĩa, output và điều kiện kết thúc rõ.
- [ ] Lỗi đầu vào trả trạng thái thất bại, không chỉ in log.
- [ ] Chưa có side effect nghiệp vụ trước validation phù hợp.
- [ ] Không log `args`, `getSourceArgs`, bí mật hoặc property sources nguyên dạng.
- [ ] Không ghép raw input vào exception message.
- [ ] Credential được cấp từ cơ chế an toàn hơn command line.
- [ ] Đường dẫn file được kiểm tra quyền, kiểu file, allowed directory và rủi ro symlink.
- [ ] Test đầu vào bất thường, lặp option, newline và dữ liệu nhạy cảm giả.
- [ ] Có chính sách log retention, access control và redaction phù hợp.
- [ ] Có test end-to-end cho exit code và output trong môi trường triển khai thật.
- [ ] Runner không block vô hạn, và các công việc async được điều phối rõ ràng.
- [ ] ApplicationReadyEvent/readiness thực tế không bị hiểu nhầm với việc runner chỉ mới bắt đầu một thread.

## 19. Ghi nhớ

- **Đầu vào CLI là input không tin cậy**, dù được truyền từ `main`.
- **`ApplicationArguments`** giúp phân loại option, values và non-option args. `getOptionValues` có thể `null` hoặc danh sách rỗng; phải xử lý cả hai.
- **Validation tốt** bao gồm cú pháp, miền giá trị, quan hệ giữa các option và điều kiện môi trường.
- **Help/usage tốt** đưa ra cú pháp chạy đúng và cách sửa lỗi, không in thông tin người dùng không cần thiết.
- **Không log toàn bộ args**: secret có thể lộ qua application logs, exception, shell history, process list, CI/CD hoặc orchestration.
- **Không đưa token lên dòng lệnh nếu có lựa chọn bảo vệ tốt hơn**; ưu tiên secret manager, identity/workload hoặc cơ chế secret được quản lý đúng quyền.
- **`ApplicationRunner` chạy sau refresh**. Nó phù hợp cho kiểm tra trước nghiệp vụ CLI, không thay thế validation cấu hình sớm khi bean/web server chưa được phép khởi tạo.
- **Mã thoát cần được thiết kế và kiểm thử thực tế**. In stderr không tự đổi exit code; `--help` return từ một runner không dừng mọi runner khác.
- **Giá trị log phải được cho phép rõ ràng**, không chỉ là raw input đã đổi tên.

### Tài liệu tham khảo

- [Spring Boot 3.3 — Using ApplicationRunner or CommandLineRunner](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): thời điểm runner trong startup và tham số ứng dụng.
- [Spring Boot 3.3 — ApplicationArguments API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html): các phương thức `containsOption`, `getOptionValues`, `getNonOptionArgs` và `getSourceArgs`.
- [Spring Boot 3.3 — DefaultApplicationArguments API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/DefaultApplicationArguments.html): tiện ích xây dựng/kiểm thử đối số.
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): command-line property sources và cấu hình ngoài.
- [Spring Boot 3.3 — Exit Codes](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): `ExitCodeGenerator` và quản lý mã thoát.
- [Spring Framework — Binding and Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation): validation của `@ConfigurationProperties`.
