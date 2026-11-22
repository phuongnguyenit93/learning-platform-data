# Tắt nguồn cấu hình dòng lệnh mà vẫn sử dụng ApplicationArguments

Spring Boot mặc định xử lý đối số dạng `--ten.thuoc.tinh=gia-tri` theo **hai mục đích khác nhau**:

1. Đưa chúng vào `Environment` dưới dạng một `CommandLinePropertySource` để có thể tham gia cơ chế externalized configuration.
2. Giữ thông tin đối số của lần gọi `SpringApplication.run(args)` để mã ứng dụng đọc qua `ApplicationArguments`.

Hai mục đích này **không phụ thuộc bắt buộc vào nhau**. Nếu không muốn người vận hành thay đổi cấu hình Spring chỉ bằng đối số `--key=value`, ta có thể gọi **`SpringApplication.setAddCommandLineProperties(false)`** trước `run(args)`. Khi đó Spring Boot không thêm property source dòng lệnh mặc định vào `Environment`, **nhưng `ApplicationArguments` vẫn tồn tại**, vẫn chứa raw arguments, option arguments và non-option arguments.

Đây là cách thiết kế phù hợp khi ứng dụng cần nhận lệnh nghiệp vụ như `--job=import` hoặc `--dry-run` mà không muốn các lệnh đó vô tình ghi đè cấu hình chung như `server.port`, `spring.profiles.active` hay `logging.level.root`.

Bài viết sử dụng **Java 17+ và Spring Boot 3.3.x**. API này cũng tồn tại ở những phiên bản Spring Boot khác, nhưng ví dụ dưới đây được viết theo Boot 3.3.

## 1. Hai luồng xử lý đối số — điểm cốt lõi

Giả sử ứng dụng chạy với:

~~~text
--demo.mode=from-cli --dry-run input.csv
~~~

Trong cấu hình mặc định của Spring Boot:

- `--demo.mode=from-cli` vừa được phân tích thành option `demo.mode` trong `ApplicationArguments`, vừa có thể trở thành property `demo.mode=from-cli` trong `Environment`.
- `--dry-run` là một option có tên nhưng không có giá trị.
- `input.csv` là non-option (đối số vị trí), không tự trở thành property tên `input.csv`.

Bây giờ bật chế độ **không thêm command-line properties**:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

Đây là mã minh họa cần có class cấu hình `MyApplication` và các import tương ứng. Phương thức `setAddCommandLineProperties(false)` phải được gọi trên **instance `SpringApplication` trước khi chạy**, vì lời gọi tĩnh `SpringApplication.run(MyApplication.class, args)` không cung cấp chỗ tùy biến instance này.

Sau khi tắt:

~~~text
                          String[] args
                                |
                   +------------+-------------+
                   |                          |
             ApplicationArguments       Spring Environment
             (vẫn phân tích args)        (không tự thêm
                   |                     commandLineArgs)
             --demo.mode=...                  |
             --dry-run                  application.properties
             input.csv                  env vars / -D / ...
~~~

Điều được tắt là **một kênh đưa arguments vào cấu hình**, không phải việc nhận arguments của JVM hoặc toàn bộ chức năng phân tích `ApplicationArguments`.

## 2. `setAddCommandLineProperties(false)` thay đổi điều gì?

| Hành vi | Mặc định (`true`) | Khi đặt `false` |
|---|---|---|
| `ApplicationArguments.getSourceArgs()` | Còn raw args | **Vẫn còn** raw args |
| `ApplicationArguments.containsOption("job")` | Có thể đọc option | **Vẫn đọc được** |
| `ApplicationArguments.getOptionValues("job")` | Có thể đọc giá trị | **Vẫn đọc được** |
| `ApplicationArguments.getNonOptionArgs()` | Có thể đọc đối số vị trí | **Vẫn đọc được** |
| `ApplicationRunner.run(ApplicationArguments)` | Nhận args | **Vẫn nhận args** |
| `CommandLineRunner.run(String...)` | Nhận raw args | **Vẫn nhận raw args** |
| `Environment.getProperty("demo.mode")` | Có thể lấy giá trị CLI, thường có ưu tiên cao | **Không lấy từ command-line property source mặc định** |
| `@Value("${demo.mode}")` | Có thể bị CLI ghi đè | Không bị ghi đè **bởi source CLI mặc định** |
| `@ConfigurationProperties` | Có thể bind property từ CLI | Không bind từ source CLI mặc định |
| File `application.properties`/YAML | Được nạp như bình thường | **Vẫn được nạp** |
| OS environment variables và JVM `-D` | Là nguồn cấu hình khác | **Vẫn hoạt động** |

Lưu ý hàng `Environment.getProperty(...)`: đặt `false` **không bắt buộc property phải là `null`**. Nếu cùng tên property được khai báo trong file, OS environment, Java system properties, default properties hoặc property source do ứng dụng thêm thủ công, giá trị ấy vẫn có thể được trả về. Điều không còn là **đường ghi đè mặc định từ `--key=value`**.

Cũng không nên gọi đây là tính năng “vô hiệu hóa mọi cấu hình dòng lệnh trên máy”. Ví dụ `-Ddemo.mode=from-jvm` là **JVM system property**, một nguồn khác với đối số ứng dụng `--demo.mode=...`.

## 3. Ví dụ chạy được: Environment lấy giá trị từ file, ApplicationArguments lấy từ CLI

Mục tiêu kiểm chứng ba điều:

1. Truyền `--demo.mode=from-cli` nhưng `Environment` vẫn sử dụng `demo.mode=from-file` trong `application.properties`.
2. `ApplicationArguments` vẫn thấy option `demo.mode`, flag `dry-run` và non-option `input.csv`.
3. `@Value` cũng đọc giá trị từ nguồn cấu hình bình thường, không tự lấy bản ghi đè từ CLI.

Tạo dự án Spring Boot 3.3.x, Java 17+, có dependency `spring-boot-starter`.

### File Java đầy đủ

Đặt tệp `src/main/java/com/example/arguments/NoCliPropertiesApplication.java`:

~~~java
package com.example.arguments;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class NoCliPropertiesApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(NoCliPropertiesApplication.class);

        // Tắt việc thêm commandLineArgs vào Spring Environment.
        // KHÔNG tắt việc phân tích và tiêm ApplicationArguments.
        app.setAddCommandLineProperties(false);

        // Không cần HTTP server cho ví dụ console.
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        // Đóng context sau khi runner hoàn tất.
        try (ConfigurableApplicationContext context = app.run(args)) {
            // Không có xử lý bổ sung.
        }
    }

    @Bean
    ApplicationRunner inspectArguments(
            Environment environment,
            @Value("${demo.mode}") String configuredMode,
            ApplicationArguments injectedArguments) {

        return runnerArguments -> {
            System.out.println(
                    "Environment demo.mode = "
                            + environment.getProperty("demo.mode"));
            System.out.println(
                    "@Value demo.mode = " + configuredMode);

            List<String> names =
                    new ArrayList<>(runnerArguments.getOptionNames());
            Collections.sort(names);
            System.out.println("Option names = " + names);

            System.out.println(
                    "CLI demo.mode values = "
                            + runnerArguments.getOptionValues("demo.mode"));
            System.out.println(
                    "CLI dry-run present = "
                            + runnerArguments.containsOption("dry-run"));
            System.out.println(
                    "CLI dry-run values = "
                            + runnerArguments.getOptionValues("dry-run"));
            System.out.println(
                    "CLI absent values = "
                            + runnerArguments.getOptionValues("absent"));
            System.out.println(
                    "Non-option args = "
                            + runnerArguments.getNonOptionArgs());
            System.out.println(
                    "Raw args = "
                            + Arrays.toString(
                                    injectedArguments.getSourceArgs()));
        };
    }
}
~~~

Ở đây có hai chỗ lấy `ApplicationArguments`:

- Tham số `ApplicationArguments injectedArguments` của factory method `@Bean` được Spring inject từ context.
- Tham số `runnerArguments` của `ApplicationRunner.run(...)` được Boot truyền khi gọi runner.

Cả hai đều có thể dùng để đọc đối số. Không cần tự tạo `DefaultApplicationArguments` hay tự viết parser cho các option thông thường.

### File cấu hình

Đặt `src/main/resources/application.properties`:

~~~properties
demo.mode=from-file
logging.level.root=INFO
~~~

Không đưa `demo.mode=from-cli` vào file cấu hình. Giá trị đó sẽ được truyền dưới dạng CLI argument, để kiểm tra khả năng tách hai nguồn.

### Chạy ứng dụng

Nếu dùng Gradle wrapper trong dự án đã cấu hình Spring Boot plugin:

~~~bash
./gradlew bootRun --args='--demo.mode=from-cli --dry-run input.csv'
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--demo.mode=from-cli --dry-run input.csv"
~~~

Nếu dùng Maven wrapper và Spring Boot Maven plugin đã cấu hình main class:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--demo.mode=from-cli --dry-run input.csv"
~~~

Các lệnh trên chỉ có ý nghĩa trong một **dự án Spring Boot có đủ dependency và plugin**. `NoCliPropertiesApplication.java` không biên dịch trực tiếp bằng `javac` nếu classpath thiếu Spring Boot/Spring Framework.

### Kết quả cần quan sát

Bỏ qua log startup của Spring Boot, các dòng **do runner trong ví dụ in ra** là:

~~~text
Environment demo.mode = from-file
@Value demo.mode = from-file
Option names = [demo.mode, dry-run]
CLI demo.mode values = [from-cli]
CLI dry-run present = true
CLI dry-run values = []
CLI absent values = null
Non-option args = [input.csv]
Raw args = [--demo.mode=from-cli, --dry-run, input.csv]
~~~

Thứ tự của `Option names` ở đây xác định vì code **tự sắp xếp** danh sách trước khi in. Không nên dựa vào thứ tự lặp trực tiếp của `getOptionNames()` cho output hoặc business logic.

**Điểm quyết định:** `Environment` và `@Value` đều in `from-file`, nhưng `ApplicationArguments.getOptionValues("demo.mode")` vẫn chứa `from-cli`. Việc tắt property source dòng lệnh **không làm mất dữ liệu đầu vào**.

Dòng `Raw args` cũng minh họa rằng các đối số vẫn giữ thứ tự khi được chuyển từ `String[] args` vào `SpringApplication.run(args)`.

## 4. API ApplicationArguments: raw, option và non-option

`org.springframework.boot.ApplicationArguments` là interface cung cấp cả mảng đối số gốc và dạng phân tích.

| API | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `getSourceArgs()` | `String[]` | Các argument gốc truyền cho SpringApplication. |
| `getOptionNames()` | `Set<String>` | Tên các option dạng `--name` hoặc `--name=value`. |
| `containsOption(String name)` | `boolean` | Có tồn tại option mang tên này hay không. |
| `getOptionValues(String name)` | `List<String>` hoặc `null` | Các giá trị đã phân tích của một option. |
| `getNonOptionArgs()` | `List<String>` | Đối số không thuộc dạng option, ví dụ tên file. |

Điểm thường gây lỗi là **ba trạng thái của `getOptionValues(...)`**:

~~~text
Không có option --foo          -> null
Có option --foo                -> []
Có option --foo=bar            -> [bar]
Có --foo=bar --foo=baz         -> [bar, baz]
~~~

Vì vậy nên kiểm tra trước khi lấy phần tử đầu:

~~~java
List<String> values = args.getOptionValues("job");
if (values == null) {
    throw new IllegalArgumentException("Missing --job option");
}
if (values.size() != 1 || values.get(0).isBlank()) {
    throw new IllegalArgumentException(
            "Require exactly one --job=<name> option");
}
String job = values.get(0);
~~~

Đây là đoạn minh họa sử dụng biến `args` kiểu `ApplicationArguments` trong một method có sẵn, không phải file Java độc lập. Kiểm tra kích thước danh sách giúp phân biệt option vắng mặt, flag không giá trị, một giá trị hợp lệ và nhiều giá trị lặp.

### Cú pháp option cần viết rõ

Với `ApplicationArguments`, dạng có giá trị nên viết:

~~~text
--job=import
~~~

Không nên mặc định:

~~~text
--job import
~~~

là hoàn toàn tương đương. Bộ phân tích command-line của Spring phân biệt option `--job` và non-option `import` nếu chúng được truyền thành hai token riêng mà không có dấu `=`.

Một flag như `--dry-run` có thể được kiểm tra bằng `containsOption("dry-run")`; còn với option có giá trị, kiểm tra `getOptionValues(...)` và validate dữ liệu nghiệp vụ.

Khi truyền argument từ shell, chú ý khoảng trắng và dấu nháy. Ví dụ:

~~~bash
java -jar app.jar --job=import "--input=/data/monthly report.csv"
~~~

Ở dạng trên, phần `--input=...` được shell giữ thành **một token**. Nếu không có dấu nháy, đường dẫn có khoảng trắng có thể bị tách thành nhiều arguments.

## 5. Vì sao ApplicationArguments vẫn có sẵn khi không có CommandLinePropertySource?

`SpringApplication` vẫn nhận nguyên `String[] args` ở lời gọi `run(args)` và có cơ chế tạo `ApplicationArguments` để phục vụ lifecycle và runner. Việc đăng ký `ApplicationArguments` như một bean trong context, cũng như việc truyền nó cho `ApplicationRunner`, là **một cơ chế khác** với việc đưa option CLI vào property sources của `Environment`.

Hai công dụng của cùng dữ liệu đầu vào:

~~~text
                            run(String[] args)
                                  |
                       Parse application args
                                  |
                 +----------------+------------------+
                 |                                   |
         ApplicationArguments                  Có thêm vào Environment?
                 |                                   |
       Injection / ApplicationRunner          setAddCommandLineProperties
                 |                              true / false
           Vẫn hoạt động                           |
                                  true: thêm source CLI
                                  false: không thêm source CLI
~~~

Khi đặt `false`, Boot không làm trống `String[] args`, không tắt `ApplicationRunner` và không vô hiệu hóa injection của `ApplicationArguments`.

### Tại sao không chỉ xóa `commandLineArgs` sau khi context chạy?

Cấu hình từ `Environment` có thể được dùng **ngay trong bootstrap** để chọn active profiles, nạp config data, cấu hình logging, đặt web server port và bind bean. Nếu đợi context chạy xong rồi mới xóa property source, những quyết định đó có thể **đã được áp dụng**.

Do đó, để tắt cách đưa CLI options vào `Environment` theo thiết kế, hãy đặt:

~~~java
app.setAddCommandLineProperties(false);
~~~

**trước** `app.run(args)`. Không xem việc xóa property source sau refresh là giải pháp tương đương hoặc luôn an toàn.

## 6. So sánh rõ Environment, @Value, @ConfigurationProperties và arguments

Giả sử bạn có:

~~~properties
# application.properties
demo.mode=from-file
~~~

Và chạy:

~~~text
--demo.mode=from-cli
~~~

Kết quả theo cơ chế bình thường:

| Cách đọc | Khi chưa tắt CLI property source | Khi đã tắt CLI property source |
|---|---|---|
| `Environment.getProperty("demo.mode")` | `from-cli` trong trường hợp không có nguồn ưu tiên cao hơn | `from-file` nếu không có nguồn khác ghi đè |
| `@Value("${demo.mode}")` | `from-cli` trong trường hợp tương tự | `from-file` trong trường hợp tương tự |
| `@ConfigurationProperties(prefix="demo")` | Có thể bind `mode=from-cli` | Sẽ không bind từ source CLI mặc định; dùng nguồn còn lại |
| `ApplicationArguments.getOptionValues("demo.mode")` | `[from-cli]` | **`[from-cli]`** |
| `ApplicationArguments.getSourceArgs()` | Gồm token `--demo.mode=from-cli` | **Vẫn gồm token đó** |

Bảng này giả định không có system property, environment variable, test property source hoặc cấu hình chương trình ưu tiên cao hơn đang đặt `demo.mode`. Đây là một mô hình **giải thích cơ chế**, không phải cam kết giá trị sẽ không thể thay đổi khi chạy trong môi trường khác.

`@ConfigurationProperties` đọc từ hệ thống configuration properties được dựng từ các nguồn `Environment` và binder; nó **không tự lấy raw arguments từ `ApplicationArguments`** chỉ vì có option cùng tên.

Nếu cần dùng giá trị của một option như thông số **lệnh nghiệp vụ**, hãy đọc và validate bằng `ApplicationArguments`. Nếu giá trị là **cấu hình dịch vụ** (database, server, logging, endpoint), hãy dùng nguồn cấu hình chính thức như config file, env vars hoặc system properties theo chính sách của ứng dụng.

## 7. Tác động đến các option quen thuộc của Spring Boot

Hãy xét một số command-line options trước đây thường được đưa vào `Environment`:

| Argument truyền vào `run(args)` | Khi source CLI bị tắt | Nơi còn đọc được |
|---|---|---|
| `--server.port=9090` | Không tự ghi đè `server.port` từ command-line source | `ApplicationArguments.getOptionValues("server.port")` |
| `--spring.profiles.active=dev` | Không tự kích hoạt profile `dev` từ command-line source | `ApplicationArguments.getOptionValues("spring.profiles.active")` |
| `--logging.level.root=DEBUG` | Không tự đổi root logging từ command-line source | `ApplicationArguments.getOptionValues("logging.level.root")` |
| `--spring.main.banner-mode=off` | Không tự đổi banner mode qua command-line property source | `ApplicationArguments.getOptionValues("spring.main.banner-mode")` |
| `--job=import` | Không tự trở thành property cấu hình `job` | `ApplicationArguments.getOptionValues("job")` |
| `--dry-run` | Không tự trở thành property cấu hình `dry-run` | `ApplicationArguments.containsOption("dry-run")` |

Một số lưu ý:

- Tắt command-line property source không cản một **đường cấu hình khác** như `SPRING_PROFILES_ACTIVE` hoặc `-Dspring.profiles.active=dev`. Ví dụ nếu profile `dev` đã được bật bởi environment variable, nó vẫn hoạt động.
- Một đoạn code do bạn tự viết có thể đọc `ApplicationArguments` rồi **chủ động** thay đổi application state/configuration. Việc đặt `false` không ngăn logic tự viết ấy.
- Tránh đưa các tham số mà Spring Boot cần dùng ở **giai đoạn nạp config data** vào một tùy chọn CLI rồi kỳ vọng chúng có hiệu lực dù đã tắt nguồn CLI. Ví dụ `--spring.config.location=...` sẽ không hoạt động như đường nạp cấu hình từ CLI mặc định.
- Nếu ứng dụng cần chuyển profile hoặc location cấu hình, hãy chọn một kênh được tổ chức cho việc đó, ví dụ environment variables hoặc JVM system properties, và kiểm tra thứ tự ưu tiên có hiệu lực.

Đây cũng là nguyên nhân nên tách nhóm arguments theo chức năng: **business command** khác với **runtime configuration**.

## 8. Phân biệt đối số ứng dụng với JVM system properties

Dễ nhầm nhất là hai câu lệnh:

~~~bash
java -Ddemo.mode=from-jvm -jar app.jar
java -jar app.jar --demo.mode=from-cli
~~~

Trong câu lệnh thứ nhất, `-Ddemo.mode=from-jvm` là **JVM system property**, được Java xử lý và đưa vào `System.getProperties()`. Nó không phải token trong `String[] args` của `main`.

Trong câu lệnh thứ hai, `--demo.mode=from-cli` là **đối số ứng dụng**. Nó thuộc `String[] args` và sẽ xuất hiện trong `ApplicationArguments`.

Khi dùng `setAddCommandLineProperties(false)`:

- Câu lệnh thứ nhất vẫn có thể đặt `demo.mode=from-jvm` trong `Environment`.
- Câu lệnh thứ hai không đưa `demo.mode=from-cli` vào `Environment` qua command-line source mặc định.
- Các token CLI vẫn có thể được lấy từ `ApplicationArguments`; `-D` JVM không tự nằm trong đó.

**Không coi `setAddCommandLineProperties(false)` là chính sách bảo mật toàn diện** cho cấu hình. Nó chỉ tắt một nguồn cấu hình; người vận hành còn có thể kiểm soát file, biến môi trường, system property, container settings hoặc tham số mà chính ứng dụng tự diễn giải.

## 9. Dùng ApplicationRunner để xử lý CLI nghiệp vụ

Khi một ứng dụng console thực hiện import/export hoặc batch job, nên tổ chức các tùy chọn theo **hợp đồng lệnh rõ ràng**:

~~~text
--job=import --input=/data/orders.csv --dry-run
~~~

Phần runner có thể:

1. Kiểm tra có đúng một `--job=<name>` và một `--input=<path>`.
2. Kiểm tra `job` thuộc tập được hỗ trợ, chẳng hạn `import`, `export`.
3. Diễn giải `--dry-run` thành chế độ xem trước.
4. Giữ cấu hình môi trường của dịch vụ từ `application.properties`, OS environment hoặc system properties.
5. Trả lỗi có ý nghĩa khi thiếu giá trị, lặp option không hợp lệ hoặc đường dẫn không tồn tại.

Ví dụ helper để lấy chính xác **một** giá trị:

~~~java
static String requireOneOption(
        ApplicationArguments args, String name) {

    List<String> values = args.getOptionValues(name);
    if (values == null || values.size() != 1) {
        throw new IllegalArgumentException(
                "Expected exactly one --" + name + "=<value>");
    }

    String value = values.get(0);
    if (value.isBlank()) {
        throw new IllegalArgumentException(
                "--" + name + " must not be blank");
    }
    return value;
}
~~~

Đây là **phương thức minh họa để đặt trong class có import `ApplicationArguments` và `java.util.List`**, không phải một file độc lập. Đoạn helper không tự thực thi import, validate dữ liệu file hay tạo transaction; mục đích là mô hình hóa cách kiểm tra input.

Trong runner có thể sử dụng:

~~~java
String job = requireOneOption(args, "job");
boolean dryRun = args.containsOption("dry-run");
~~~

Hai dòng trên là mã minh họa khi `args` là một `ApplicationArguments`. Khi muốn cho phép nhiều giá trị lặp của một option, đừng dùng `requireOneOption`; hãy duyệt danh sách `getOptionValues(...)` và có quy tắc xử lý rõ ràng.

### Runner chạy vào thời điểm nào?

`ApplicationRunner` được Spring Boot gọi **sau khi application context refresh** và trước khi `SpringApplication.run(...)` hoàn tất bình thường. Điều này phù hợp với tác vụ startup/batch cần bean đã được inject.

Nhưng `ApplicationRunner` không thay thế hoàn toàn một command parser chuyên dụng khi cú pháp lệnh trở nên phức tạp: subcommands, positional argument groups, validation phụ thuộc nhau, help/usage text, completion hoặc error code. Khi bài toán lớn, có thể cân nhắc dùng thư viện CLI phù hợp, trong khi vẫn giữ ranh giới cấu hình runtime và args nghiệp vụ rõ ràng.

## 10. So sánh với CommandLineRunner và constructor injection

Cả `ApplicationRunner` lẫn `CommandLineRunner` là những callback startup của Spring Boot:

| Phương thức | Dữ liệu nhận | Khi nào thuận tiện |
|---|---|---|
| `ApplicationRunner.run(ApplicationArguments args)` | Đối số đã phân loại thành option và non-option, đồng thời có raw args | Cần parse `--job=import`, `--dry-run`, hoặc đối số vị trí. |
| `CommandLineRunner.run(String... args)` | Mảng argument gốc | Cần tự parse theo cú pháp riêng hoặc chuyển nguyên args cho library khác. |
| Constructor injection của `ApplicationArguments` | Bean/class nhận một object arguments | Một service cần biết các tùy chọn ngay khi được tạo. |

Ví dụ `CommandLineRunner`:

~~~java
@Bean
CommandLineRunner rawRunner() {
    return sourceArgs -> {
        System.out.println(Arrays.toString(sourceArgs));
    };
}
~~~

Đây là đoạn minh họa đặt trong class cấu hình có import `CommandLineRunner` và `Arrays`. Nếu thêm trực tiếp vào chương trình ở mục 3, sẽ có **runner thứ hai** và thêm output, nên để kiểm chứng stdout của chương trình chính hãy giữ một runner duy nhất.

Constructor injection:

~~~java
@Component
public class JobOptions {

    private final ApplicationArguments args;

    public JobOptions(ApplicationArguments args) {
        this.args = args;
    }

    public boolean isDryRun() {
        return args.containsOption("dry-run");
    }
}
~~~

Đây là ví dụ class bổ sung, cần import `org.springframework.boot.ApplicationArguments` và `org.springframework.stereotype.Component`. Cả hai cách đều hoạt động sau khi đã tắt command-line property source: object `ApplicationArguments` vẫn có trong context, chỉ cơ chế đọc property qua `Environment` là thay đổi.

Với các ứng dụng lớn, nên cân nhắc việc để toàn bộ service đều đọc `ApplicationArguments` hay chỉ parse một lần tại lớp entry point rồi truyền một object cấu hình nghiệp vụ **đã validate** cho phần còn lại. Cách thứ hai giúp test service dễ hơn và hạn chế việc nghiệp vụ phụ thuộc trực tiếp vào Spring Boot.

## 11. So sánh trước–sau bằng một thay đổi duy nhất

Trong chương trình mục 3, thay đổi:

~~~java
app.setAddCommandLineProperties(false);
~~~

thành:

~~~java
app.setAddCommandLineProperties(true);
~~~

hoặc bỏ lời gọi (mặc định là `true`). Giữ nguyên `application.properties` và lệnh chạy:

~~~text
--demo.mode=from-cli --dry-run input.csv
~~~

Khi đó hai dòng đầu **thường đổi** thành:

~~~text
Environment demo.mode = from-cli
@Value demo.mode = from-cli
~~~

Những dòng từ `ApplicationArguments` **không đổi**, vì chính `args` đầu vào không đổi.

Thử nghiệm đối chứng này làm rõ mục tiêu của API: nó đổi **sự tham gia vào environment property resolution**, không đổi cách ứng dụng nhận `String[] args`.

Để kiểm tra bằng debugger, dừng ở `ApplicationRunner.run(...)` rồi quan sát:

- `environment.getProperty("demo.mode")`.
- `runnerArguments.getOptionValues("demo.mode")`.
- `runnerArguments.getSourceArgs()`.

Nếu cần kiểm tra property source bằng code, có thể inject `ConfigurableEnvironment` và đọc các tên trong `getPropertySources()`. Khi `setAddCommandLineProperties(false)` được dùng đúng và không có code tự thêm lại, source có tên mặc định `commandLineArgs` không được SpringApplication thêm vào.

## 12. Các lỗi phổ biến

**Lỗi 1 — “Đặt false thì `ApplicationArguments` bị rỗng.”**

Không. Hai cơ chế độc lập; ví dụ mục 3 cho thấy raw, option và non-option vẫn đầy đủ. Nếu dữ liệu trống, hãy kiểm tra bạn có thật sự truyền `args` vào `app.run(args)` hay không.

**Lỗi 2 — “Không thấy `--demo.mode=from-cli` trong Environment nghĩa là CLI bị mất.”**

Không. Dữ liệu vẫn ở `ApplicationArguments`, chỉ không còn là nguồn cấu hình trong `Environment` theo cơ chế mặc định.

**Lỗi 3 — “Có thể đặt false sau `run()`.”**

Không phù hợp với mục tiêu. Việc đọc cấu hình và khởi tạo bean đã bắt đầu hoặc hoàn tất. Hãy đặt tùy chọn **trước `run()`**.

**Lỗi 4 — “`@Value("${job}")` vẫn nên lấy `--job=import`.”**

Sau khi tắt CLI property source, điều đó **không còn được bảo đảm**. Nếu không có property `job` ở nguồn khác, biểu thức có thể không resolve hoặc nhận default theo khai báo. Với command nghiệp vụ, dùng `ApplicationArguments.getOptionValues("job")`.

**Lỗi 5 — “`getOptionValues("dry-run") == null` khi flag không có giá trị.”**

Sai nếu flag `--dry-run` có mặt: kết quả là **list rỗng `[]`**. `null` biểu thị option hoàn toàn không xuất hiện. Hãy dùng `containsOption(...)` để kiểm tra flag.

**Lỗi 6 — “`--job import` giống `--job=import`.”**

Không thể mặc định tương đương trong parser option của Spring Boot. Nên dùng cú pháp `--job=import` khi muốn một option có giá trị rõ ràng.

**Lỗi 7 — “Đặt false cấm cấu hình từ OS env hoặc JVM system properties.”**

Sai. Những nguồn đó độc lập và vẫn có thể ghi đè cấu hình từ file.

**Lỗi 8 — “Dùng false là đã an toàn khi cho người dùng truyền mọi tham số.”**

Chưa đủ. Code vẫn có thể đọc args và hành động theo chúng. Bạn vẫn cần validation, giới hạn quyền, allowlist các lệnh hợp lệ và tuyệt đối tránh log argument chứa secret.

**Lỗi 9 — “Thêm lệnh `--spring.profiles.active=prod` vẫn sẽ bật profile dù CLI properties đã tắt.”**

Không qua kênh command-line property source mặc định. Nếu app cần profile riêng, đặt từ một nguồn cấu hình được phép hoặc cấu hình chương trình có chủ đích.

**Lỗi 10 — “Có một `ApplicationArguments` dùng chung cho mọi lần khởi chạy khác nhau.”**

Đừng giả định vậy. Arguments gắn với một lần `SpringApplication.run(...)` và context được tạo. Khi chạy nhiều context hoặc test nhiều lần, cần biết args thuộc application nào.

## 13. Lưu ý bảo mật và vận hành

Mục tiêu thực tế của `setAddCommandLineProperties(false)` thường là **tách bạch trách nhiệm**, không phải ẩn argument hoặc tạo sandbox:

- **Về cấu hình:** `--server.port=...` và các option Boot khác không tự ghi đè environment từ command-line source mặc định.
- **Về nghiệp vụ:** `ApplicationArguments` vẫn đọc được và mã ứng dụng có thể phản ứng với `--job=delete`, `--dry-run`, `--input=...`. Bạn phải tự kiểm soát các lệnh này.
- **Về secret:** argument nằm trong process command line có thể bị lộ qua công cụ quan sát tiến trình, script, terminal history hoặc log. Đừng dùng `ApplicationArguments` như kho lưu bí mật.
- **Về cấu hình đa nguồn:** file, biến môi trường, system properties, config import và những property source được thêm thủ công vẫn hoạt động theo thứ tự ưu tiên. Không suy ra rằng đặt `false` làm configuration immutable.
- **Về test:** kiểm tra đồng thời hai phía: environment không nhận override từ CLI và `ApplicationArguments` vẫn nhận args. Chỉ test một phía sẽ dễ bỏ sót regression.

Nếu ứng dụng dựa trên framework triển khai khác gọi trực tiếp `SpringApplication.run(...)` mà bạn không kiểm soát đoạn main, cần tìm cách cấu hình `SpringApplication` **trước khi chạy** trong entry point thật sự; không nên sửa bean quá muộn để đạt hiệu quả tương tự.

## 14. Bài tập tự kiểm chứng

Dùng chương trình mục 3 với một runner duy nhất:

1. Chạy với `--demo.mode=from-cli --dry-run input.csv` và kiểm tra Environment vẫn là `from-file`.
2. Đổi giá trị CLI thành `--demo.mode=another`; quan sát `ApplicationArguments` thay đổi, nhưng Environment vẫn là `from-file`.
3. Bỏ `--dry-run`; `containsOption("dry-run")` trở thành `false` và `getOptionValues("dry-run")` trở thành `null`.
4. Thêm hai option `--tag=a --tag=b`; kiểm tra `getOptionValues("tag")` trả về danh sách hai giá trị theo thứ tự xuất hiện.
5. Bỏ `app.setAddCommandLineProperties(false)` rồi chạy lại; quan sát giá trị CLI có thể ghi đè `demo.mode` trong Environment.
6. Chạy với JVM system property `-Ddemo.mode=from-jvm`; kiểm tra rằng nguồn system property không bị API này tắt. Hãy đảm bảo đặt `-D` vào đúng tiến trình JVM của ứng dụng, không nhầm với JVM chạy Gradle/Maven.

### Nguồn tham khảo chính thức

- Spring Boot 3.3 – Externalized Configuration, mục *Accessing Command Line Properties*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 – SpringApplication, mục *Accessing Application Arguments*: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 – `SpringApplication.setAddCommandLineProperties(boolean)`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 – `ApplicationArguments` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html

**Kết luận:** Dùng `SpringApplication.setAddCommandLineProperties(false)` **trước** `run(args)` để không tự động biến CLI options thành Spring `Environment` properties. Dữ liệu vẫn còn nguyên trong `ApplicationArguments` và vẫn dùng được qua injection hoặc `ApplicationRunner`. Nhờ đó ứng dụng có thể nhận **lệnh nghiệp vụ** qua CLI mà vẫn giữ **cấu hình runtime** theo những nguồn đã được lựa chọn.
