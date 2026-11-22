# Quan hệ giữa đối số --key=value và thuộc tính trong Spring Environment

## 1. Câu trả lời cốt lõi

Khi bạn khởi chạy một ứng dụng Spring Boot bằng:

```bash
java -jar myapp.jar --demo.message=hello --server.port=9090
```

hai phần bắt đầu bằng `--` là **đối số ứng dụng dạng option**, được truyền vào `String[] args` của `main`. Theo cấu hình mặc định của Spring Boot 3.3, `SpringApplication` **phân tích những option đó, chuyển chúng thành các thuộc tính và bổ sung một `PropertySource` vào Spring `Environment`**. Kết quả là các thành phần của ứng dụng có thể đọc:

```java
environment.getProperty("demo.message"); // "hello"
environment.getProperty("server.port");   // "9090"
```

Nếu ứng dụng Web đang sử dụng cấu hình server chuẩn, `--server.port=9090` còn có thể khiến server lắng nghe cổng 9090. Nhưng việc một thuộc tính xuất hiện trong `Environment` **không tự đảm bảo có thành phần tiêu thụ nó**: trong ứng dụng non-web, `server.port` có thể đọc được nhưng không mở cổng HTTP.

**Hãy nhớ ba phân biệt cơ bản:**

1. **`--key=value` là cách truyền option vào ứng dụng**, không phải biến môi trường của hệ điều hành và không phải Java system property.
2. **`Environment` là một tập hợp nhiều nguồn thuộc tính có thứ tự ưu tiên**. Command-line options được đưa vào một nguồn trong số đó; nó có thể ghi đè giá trị cùng khóa trong `application.properties`.
3. **`ApplicationArguments` giữ thông tin đối số**, gồm option, giá trị option và đối số không có tên. Đọc `ApplicationArguments` khác với hỏi `Environment` về **giá trị hiệu lực sau khi xét nhiều nguồn**.

Trong Spring Boot, có thể tắt riêng việc **đưa command-line options vào `Environment`**:

```java
SpringApplication application = new SpringApplication(MyApplication.class);
application.setAddCommandLineProperties(false);
application.run(args);
```

Khi đó các option vẫn được truyền vào `SpringApplication.run(args)` và có thể được xem qua `ApplicationArguments`, nhưng chúng **không còn tự ghi đè giá trị trong `Environment` qua command-line property source**. Phần 7 có một dự án chạy được để thấy sự khác biệt.

## 2. Đường đi từ dòng lệnh đến Environment

Sơ đồ logic:

```text
Shell / terminal / Gradle bootRun
        |
        |  --demo.message=from-cli
        |  --demo.retries=7
        |  orders.csv
        v
Java main(String[] args)
        |
        v
SpringApplication.run(args)
        |
        +-- DefaultApplicationArguments
        |      |-- option "demo.message" -> ["from-cli"]
        |      |-- option "demo.retries" -> ["7"]
        |      +-- non-option args -> ["orders.csv"]
        |
        +-- mặc định thêm CommandLinePropertySource
               vào ConfigurableEnvironment
                    |
                    +-- demo.message = "from-cli"
                    +-- demo.retries = "7"
                    |
                    v
             Environment.getProperty(...)
             @Value(...)
             @ConfigurationProperties(...)
                    |
                    v
             Các bean dùng cấu hình hiệu lực
```

Các giai đoạn không xảy ra hoàn toàn tách biệt như hai tiến trình khác nhau; sơ đồ nhằm diễn tả **hai cách nhìn trên cùng tập đối số đầu vào**:

- `ApplicationArguments` là API hỏi **đối số được truyền vào lần chạy**.
- `Environment` là API hỏi **thuộc tính hiệu lực của ứng dụng**, có thể đến từ CLI, system properties, OS environment, config data, default properties và các nguồn khác.

Điều này giải thích một tình huống thường gặp: nếu không truyền `--demo.message` nhưng có `demo.message` trong `application.properties`, `ApplicationArguments.containsOption("demo.message")` là `false` còn `Environment.getProperty("demo.message")` vẫn trả về giá trị từ file. Hai câu trả lời đều đúng; chúng trả lời **hai câu hỏi khác nhau**.

Một lưu ý về thời điểm: command-line property source được Spring Boot lắp vào `Environment` **trong quá trình chuẩn bị môi trường**, trước khi các bean thông thường được tạo và nhận cấu hình. Vì vậy một option được truyền sớm có thể ảnh hưởng đến `@ConditionalOnProperty`, `@ConfigurationProperties`, active profiles và các quyết định bootstrap khác tùy thuộc loại property.

## 3. Cú pháp option --key=value và non-option argument

Theo cú pháp command-line mà Spring dùng, option có hình thức:

```text
--optionName[=optionValue]
```

Các ví dụ:

| Đối số thực tế | Loại | Ý nghĩa khi phân tích |
|---|---|---|
| `--demo.message=hello` | Option có giá trị | Tên `demo.message`, giá trị `hello` |
| `--server.port=9090` | Option có giá trị | Tên `server.port`, giá trị `9090` |
| `--debug` | Option chỉ xuất hiện | Tên `debug` tồn tại, không có giá trị tường minh |
| `--demo.message=` | Option có giá trị chuỗi rỗng | Có dấu `=`, giá trị là `""` |
| `--demo.message="Xin chao"` | Option có giá trị chứa khoảng trắng | Shell ghép nội dung được quote thành một argument nếu quote đúng |
| `orders.csv` | Non-option | Một đối số vị trí; không tự biến thành khóa `orders.csv` |
| `--demo.message hello` | **Hai đối số** | Option `demo.message` không kèm giá trị; `hello` là non-option |
| `-Ddemo.message=hello` | Không phải cú pháp Spring `--` | Chỉ là JVM system property **nếu đặt vào vị trí tham số JVM trước `-jar`/main class** |

**Cần có hai dấu gạch ngang** để Spring Boot nhận diện option: `--key=value`. Một dấu như `-key=value` không phải biến thể đồng nghĩa của command-line option theo parser này.

**Cần có dấu bằng ngay sau key** nếu muốn truyền value. Dòng:

```bash
java -jar myapp.jar --demo.message hello
```

không tương đương:

```bash
java -jar myapp.jar --demo.message=hello
```

Trong dòng thứ nhất, `--demo.message` là một option không có giá trị; `hello` trở thành non-option. Việc parser phát hiện tên option **không có nghĩa** `Environment` đã có chuỗi `"hello"` cho khóa đó.

### Shell xử lý dấu nháy trước Java

Ví dụ:

```bash
java -jar myapp.jar --demo.message="Xin chao"
```

Shell thông thường chuyển phần được quote thành một đối số có value `Xin chao`, chứ không gửi dấu nháy như một phần của value. Quy tắc quote có khác biệt giữa Bash, PowerShell và Windows `cmd`; khi có ký tự đặc biệt như dấu cách, `$`, `&`, `!`, dấu gạch chéo hoặc dấu nháy lồng nhau, phải áp dụng quy tắc của **shell thực tế**.

Tham số `--` đứng riêng có ý nghĩa phân cách “kết thúc các option” trong parser command line kiểu POSIX; các đối số phía sau được coi là non-option. Dù vậy, đừng dùng phân cách này như cách cấu hình `Environment` bằng các giá trị có dấu `--` mà không thử nghiệm parser thực tế.

## 4. Environment không phải bản sao của String[] args

`org.springframework.core.env.Environment` là abstraction để hỏi **thuộc tính và profile của ứng dụng**. `ConfigurableEnvironment` còn cho phép xem các `PropertySource`. Trong runtime Spring Boot điển hình, nguồn command-line có tên:

```text
commandLineArgs
```

Nó được ưu tiên so với các nguồn cấu hình file thông thường. Hãy xem ví dụ:

**`src/main/resources/application.properties`:**

```properties
demo.message=from-file
demo.retries=2
```

Sau đó khởi chạy:

```bash
java -jar myapp.jar --demo.message=from-cli --demo.retries=7
```

Mặc định, giá trị **hiệu lực**:

| Khóa | Giá trị trong file | Giá trị CLI | `Environment.getProperty(...)` |
|---|---|---|---|
| `demo.message` | `from-file` | `from-cli` | `from-cli` |
| `demo.retries` | `2` | `7` | `"7"` khi đọc dạng `String` |
| `demo.unknown` | Không có | Không có | `null` nếu không có nguồn khác |
| `demo.other` | `file-only` | Không có | `file-only` nếu file định nghĩa |

**Không phải Spring sửa nội dung `application.properties` trên đĩa.** Spring chỉ giải quyết thuộc tính bằng cách duyệt những nguồn cấu hình theo thứ tự ưu tiên. Giá trị từ CLI có thể được chọn thay cho file **trong lần chạy đó**; file gốc vẫn giữ nguyên.

### Độ ưu tiên mặc định trong runtime Spring Boot

Một vài nguồn cấu hình thường gặp, từ thấp đến cao trong những trường hợp thông thường:

```text
defaultProperties của SpringApplication
      <
application.properties / application.yaml (config data)
      <
OS environment variables
      <
Java system properties (-Dkey=value)
      <
SPRING_APPLICATION_JSON
      <
Command-line options (--key=value)
```

Đây là **sơ đồ rút gọn**, không phải danh sách đầy đủ: JNDI, servlet params, random properties, nguồn thuộc tính tùy biến và các nguồn của môi trường test cũng có vị trí của chúng. Trong **test**, chẳng hạn `@TestPropertySource` hoặc `@DynamicPropertySource` có thể được ưu tiên cao hơn command-line arguments; vì vậy phát biểu chính xác là **CLI ưu tiên hơn các nguồn file trong runtime cấu hình mặc định**, không phải “CLI thắng mọi nguồn trong mọi tình huống”.

Với cùng khóa `demo.message`:

```properties
# application.properties
demo.message=from-file
```

```bash
# Java system property + app option trong cùng một lần chạy:
java -Ddemo.message=from-jvm -jar myapp.jar --demo.message=from-cli
```

Trong cấu hình chuẩn, `Environment.getProperty("demo.message")` trả về `from-cli`, vì command-line property source có độ ưu tiên cao hơn Java system properties. Nếu bỏ argument `--demo.message=...`, `from-jvm` có thể thắng `from-file`.

**Không gọi `System.getProperty("demo.message")` rồi kỳ vọng thấy `from-cli`.** `System.getProperty` đọc **JVM system properties**; Spring Boot không đồng nhất command-line `PropertySource` với bảng system properties của JVM.

## 5. ApplicationArguments: quan sát chính xác đối số người dùng đã truyền

Spring Boot cung cấp bean `ApplicationArguments` có thể tiêm vào component hoặc nhận trong `ApplicationRunner.run(...)`. Nó cho phép phân biệt đối số truyền trực tiếp và giá trị được lấy từ `Environment`.

Các phương thức hữu ích:

| API | Ý nghĩa |
|---|---|
| `getSourceArgs()` | Mảng `String[]` đối số gốc truyền vào `SpringApplication.run(args)` |
| `getOptionNames()` | Tập các tên option có dạng `--key[=value]` |
| `containsOption("demo.message")` | `true` nếu có option cùng tên, kể cả khi không có value |
| `getOptionValues("demo.message")` | Danh sách các giá trị của option; `null` nếu tên option không có |
| `getNonOptionArgs()` | Các đối số không thuộc nhóm option |

Ví dụ, với:

```bash
java -jar myapp.jar --name=Lan --tag=a --tag=b orders.csv
```

`ApplicationArguments` có thể cho:

```text
containsOption("name")  -> true
getOptionValues("name") -> [Lan]
getOptionValues("tag")  -> [a, b]
getNonOptionArgs()      -> [orders.csv]
```

**Phân biệt ba trường hợp rất quan trọng:**

- Không truyền `--name`: `getOptionValues("name")` trả về **`null`**.
- Truyền `--name` không có dấu `=`: tên option có mặt, `getOptionValues("name")` là **danh sách rỗng**.
- Truyền `--name=`: tên option có mặt, có **một giá trị là chuỗi rỗng**.

Một số công cụ log có thể hiển thị `[]` giống nhau khi phần tử chuỗi rỗng được in trong Java list, nên nếu cần phân biệt chắc chắn thì kiểm tra `values == null`, `values.size()` và `values.get(0).isEmpty()` thay vì chỉ nhìn chuỗi được in.

### Cách đọc an toàn

```java
List<String> values = arguments.getOptionValues("name");

String name = (values == null || values.isEmpty())
        ? "guest"
        : values.get(0);
```

Đây là **đoạn tích hợp** đặt trong code có biến `ApplicationArguments arguments` và import `java.util.List`. Nếu người dùng truyền `--name=`, `values` có một phần tử rỗng và `name` sẽ là chuỗi rỗng; nếu muốn chặn giá trị rỗng, cần kiểm tra thêm `name.isBlank()`.

### Cùng tên option lặp lại

```bash
java -jar myapp.jar --tag=a --tag=b
```

`ApplicationArguments.getOptionValues("tag")` lưu nhiều giá trị theo parser. Trong khi đó, `Environment.getProperty("tag")` là cách lấy **một property hiệu lực**; implementation `CommandLinePropertySource` của Spring Framework có thể biểu diễn nhiều giá trị thành một chuỗi phân tách bằng dấu phẩy. Vì thế khi tham số **có thể lặp**, cần một danh sách và đúng semantics của từng giá trị, `ApplicationArguments` thường rõ ràng hơn so với tự chia chuỗi trả về từ `Environment`.

## 6. Những cách đọc cùng một giá trị cấu hình

Giả sử có `demo.message` trong `Environment`, có nhiều cách truy xuất:

### 6.1. Environment

```java
String message = environment.getProperty("demo.message");
Integer retries = environment.getProperty("demo.retries", Integer.class);
```

`getProperty(String)` thông thường trả `String` hoặc `null` khi không tìm thấy; overload có `Class<T>` yêu cầu chuyển đổi kiểu sang `Integer`, `Boolean`, `Duration` tùy cơ chế conversion. Nếu người dùng truyền `--demo.retries=abc`, việc yêu cầu số nguyên không thể tự suy ra một số hợp lệ; cần xử lý lỗi cấu hình, không ép về giá trị tưởng tượng.

### 6.2. @Value

```java
@Value("${demo.message}")
private String message;
```

Đây là **field trong một bean do Spring quản lý**, cần import `org.springframework.beans.factory.annotation.Value`. Spring giải quyết placeholder từ cấu hình của `Environment` khi tạo và tiêm bean. Nếu khóa không có và không cung cấp default, startup có thể thất bại do không giải quyết được placeholder.

Có thể chỉ định fallback ở cấp injection:

```java
@Value("${demo.message:guest}")
private String message;
```

Nhưng fallback này chỉ dùng nếu không tìm thấy property thích hợp; nó **không thay thế thứ tự ưu tiên** của Environment. Với cấu hình có nhiều thuộc tính, ưu tiên cách binding theo một object cấu hình rõ kiểu.

### 6.3. @ConfigurationProperties

Spring Boot hỗ trợ binding nhiều property theo prefix vào một class/record:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoSettings(String message, int retries) {
}
```

Khi đăng ký bằng `@EnableConfigurationProperties(DemoSettings.class)` hoặc cơ chế scan thích hợp, `demo.message` và `demo.retries` từ Environment được bind thành object có kiểu rõ ràng.

Đối với ứng dụng lớn, `@ConfigurationProperties` thích hợp hơn một tập dài `@Value`: giúp gom cấu hình, hỗ trợ relaxed binding, metadata và validation khi cấu hình đầy đủ. Nó vẫn dựa vào Environment nên CLI option có thể ghi đè giá trị file **trong lần chạy hiện tại**.

**Quan trọng:** `ApplicationArguments` không tự động là `@ConfigurationProperties`. Chúng là hai API riêng; khi `setAddCommandLineProperties(false)` được bật, object `@ConfigurationProperties` không lấy các giá trị override từ command-line property source nữa dù `ApplicationArguments` vẫn thấy option.

## 7. Ví dụ hoàn chỉnh Spring Boot 3.3 + Java 17: quan sát cả hai đường đọc

Dự án này cho thấy **một tập đối số** được đọc ra bằng `ApplicationArguments` và `Environment` như thế nào, và điều gì đổi khi tắt command-line property source. Không cần Web server hoặc database.

### 7.1. Cấu trúc file

```text
cli-environment-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/clienv/
    │   ├── CliEnvironmentApplication.java
    │   └── DemoSettings.java
    └── resources/
        └── application.properties
```

**`settings.gradle`**:

```groovy
rootProject.name = 'cli-environment-demo'
```

**`build.gradle`** (Gradle Groovy DSL):

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

`spring-boot-starter` chứa hạ tầng ApplicationContext và external configuration cần thiết cho ví dụ. Không cần `spring-boot-starter-web`; chương trình được đặt `WebApplicationType.NONE` nên không mở HTTP server.

**`src/main/resources/application.properties`**:

```properties
spring.application.name=cli-environment-demo
demo.message=from-file
demo.retries=2
```

Đây là giá trị mặc định từ **config data**; khi CLI command-line property source được bật, người chạy có thể override chúng.

### 7.2. Record cho @ConfigurationProperties

**`src/main/java/com/example/clienv/DemoSettings.java`**:

```java
package com.example.clienv;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoSettings(String message, int retries) {
}
```

Java 17 hỗ trợ `record`; với một constructor chuẩn duy nhất, Spring Boot 3.3 có thể dùng constructor binding cho kiểu cấu hình này. `@ConfigurationProperties` **không đủ tự đăng ký bean** nếu không bật scan hoặc đăng ký tường minh; lớp chính phía dưới dùng `@EnableConfigurationProperties(DemoSettings.class)`.

### 7.3. Lớp main và ApplicationRunner in kết quả

**`src/main/java/com/example/clienv/CliEnvironmentApplication.java`**:

```java
package com.example.clienv;

import java.util.Arrays;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.ConfigurableEnvironment;

@SpringBootApplication
@EnableConfigurationProperties(DemoSettings.class)
public class CliEnvironmentApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(CliEnvironmentApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        // Demo: bật chế độ này bằng JVM system property trước "-jar".
        // Nó KHÔNG phải một option "--key=value" của Spring Boot.
        if (Boolean.getBoolean("example.disable-cli-properties")) {
            application.setAddCommandLineProperties(false);
        }

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            // Runner và ReadyEvent đã xử lý xong; đóng demo non-web.
        }
    }

    @Bean
    ApplicationRunner showEffectiveSettings(
            ConfigurableEnvironment environment,
            DemoSettings settings,
            @Value("${demo.message}") String viaValue) {

        return arguments -> {
            System.out.println("raw args = "
                    + Arrays.toString(arguments.getSourceArgs()));

            System.out.println("has message option = "
                    + arguments.containsOption("demo.message"));

            System.out.println("message option values = "
                    + arguments.getOptionValues("demo.message"));

            System.out.println("non-option args = "
                    + arguments.getNonOptionArgs());

            System.out.println("Environment demo.message = "
                    + environment.getProperty("demo.message"));

            System.out.println("Environment demo.retries = "
                    + environment.getProperty("demo.retries", Integer.class));

            System.out.println("@Value demo.message = " + viaValue);

            System.out.println("@ConfigurationProperties = "
                    + settings.message() + " / " + settings.retries());

            System.out.println("commandLineArgs present = "
                    + environment.getPropertySources()
                            .contains("commandLineArgs"));
        };
    }
}
```

**Phân tích mã:**

1. `SpringApplication` nhận nguyên `String[] args` vào `run`. Đây là điểm vào cho cả `ApplicationArguments` và việc chuyển options vào Environment theo mặc định.
2. `setWebApplicationType(WebApplicationType.NONE)` chỉ để giữ demo không có HTTP server, **không ảnh hưởng tới tính năng command-line property source**.
3. `Boolean.getBoolean("example.disable-cli-properties")` đọc một **Java system property**; khi giá trị là `true`, chương trình gọi `setAddCommandLineProperties(false)` **trước khi `run` bắt đầu**.
4. Phương thức `@Bean` trả `ApplicationRunner` để in kết quả sau khi context đã khởi tạo. Không tự gọi `run` của runner bằng tay.
5. `ApplicationArguments` được truyền vào callback `run(ApplicationArguments)` dưới tên `arguments`; nó thể hiện các option và non-option gốc.
6. `ConfigurableEnvironment.getProperty(...)` trả về thuộc tính **hiệu lực theo thứ tự nguồn**; overload `Integer.class` cho thấy conversion của giá trị chữ sang số.
7. Tham số `@Value("${demo.message}") String viaValue` được giải quyết khi Spring tạo bean runner, và `DemoSettings` được bind từ các property tương ứng.
8. Kiểm tra `commandLineArgs` nhằm minh họa một property source chuẩn trong cấu hình runtime của demo. Với custom Environment hoặc cách khởi động khác, tên/đường thêm nguồn có thể khác, nên đừng coi đây là cách duy nhất để kiểm tra mọi Spring application.
9. `try-with-resources` giúp đóng context sau khi `SpringApplication.run` trả về; ứng dụng Web thực tế thường phải giữ context chạy để phục vụ request.

### 7.4. Chạy mặc định và ghi đè bằng CLI

Từ thư mục có **Gradle Wrapper**:

```bash
./gradlew bootRun --args='--demo.message=from-cli --demo.retries=7 orders.csv'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args='--demo.message=from-cli --demo.retries=7 orders.csv'
```

Nếu chưa có Wrapper, tạo project qua Spring Initializr hoặc sinh Wrapper bằng bản Gradle tương thích; viết `build.gradle` không tự tạo file `gradlew`. Java 17+ và plugin tương thích là điều kiện để build chạy được.

Các dòng **do chương trình ví dụ in ra**, bỏ qua banner/log Spring Boot và Gradle:

```text
raw args = [--demo.message=from-cli, --demo.retries=7, orders.csv]
has message option = true
message option values = [from-cli]
non-option args = [orders.csv]
Environment demo.message = from-cli
Environment demo.retries = 7
@Value demo.message = from-cli
@ConfigurationProperties = from-cli / 7
commandLineArgs present = true
```

Quan sát quan hệ: `ApplicationArguments` nhìn thấy `--demo.message` được truyền trực tiếp; đồng thời `Environment`, `@Value` và `@ConfigurationProperties` đều lấy giá trị **from-cli**, không phải **from-file**. Giá trị nguyên `7` đã được chuyển kiểu cho `DemoSettings.retries()`.

### 7.5. Chạy không truyền option

```bash
./gradlew bootRun
```

Các giá trị có tính quyết định ở lần chạy này:

```text
raw args = []
has message option = false
message option values = null
non-option args = []
Environment demo.message = from-file
Environment demo.retries = 2
@Value demo.message = from-file
@ConfigurationProperties = from-file / 2
```

Khi **không có đối số command-line nào**, không nên viết assertion cứng rằng source tên `commandLineArgs` nhất định được thêm: một số đường triển khai chỉ cần tạo nguồn khi có arguments. Điều quan trọng là `demo.message` được lấy từ file, còn `ApplicationArguments` không có option `demo.message`.

### 7.6. Tắt việc đưa CLI vào Environment nhưng vẫn giữ ApplicationArguments

Đầu tiên build JAR:

```bash
./gradlew bootJar
```

Sau đó chạy:

```bash
java -Dexample.disable-cli-properties=true \
  -jar build/libs/cli-environment-demo-0.0.1-SNAPSHOT.jar \
  --demo.message=from-cli --demo.retries=7 orders.csv
```

Windows PowerShell viết trên một dòng để tránh nhầm ký tự xuống dòng của các shell:

```powershell
java -Dexample.disable-cli-properties=true -jar build/libs/cli-environment-demo-0.0.1-SNAPSHOT.jar --demo.message=from-cli --demo.retries=7 orders.csv
```

Kết quả chính xác từ các dòng do code in, khi file cấu hình `application.properties` vẫn như ban đầu:

```text
raw args = [--demo.message=from-cli, --demo.retries=7, orders.csv]
has message option = true
message option values = [from-cli]
non-option args = [orders.csv]
Environment demo.message = from-file
Environment demo.retries = 2
@Value demo.message = from-file
@ConfigurationProperties = from-file / 2
commandLineArgs present = false
```

Đây là thí nghiệm mấu chốt: **cùng một `String[] args`**, `ApplicationArguments` vẫn phân tích option **from-cli**, nhưng `Environment` không nhận giá trị ghi đè từ command-line property source nên quay về **from-file**. `@Value` và `@ConfigurationProperties` đi theo Environment, không trực tiếp lấy `getOptionValues`.

**Vị trí của `-D` rất quan trọng.** Trong câu lệnh Java, `-Dexample.disable-cli-properties=true` phải được đặt trước `-jar` để JVM hiểu là **Java system property**. Nếu chuyển nó ra phía sau tên JAR, nó sẽ trở thành đối số ứng dụng, không kích hoạt `Boolean.getBoolean(...)` như trong code.

## 8. So sánh bốn kênh cung cấp một thuộc tính

Cùng một ý nghĩa `demo.message` có thể được cung cấp qua những kênh khác nhau:

| Kênh | Ví dụ | Nơi đọc trực tiếp | Có xuất hiện trong `ApplicationArguments` không? |
|---|---|---|---|
| File cấu hình | `demo.message=from-file` trong `application.properties` | Spring `Environment` | Không |
| OS environment variable | `DEMO_MESSAGE=from-os` | OS process environment; Spring binder hỗ trợ ánh xạ tên | Không, trừ khi bạn cũng truyền nó thành app arg |
| Java system property | `-Ddemo.message=from-jvm` **trước `-jar`** | `System.getProperty` và Spring `Environment` | Không |
| Spring Boot command-line option | `--demo.message=from-cli` **sau JAR** | `ApplicationArguments`; mặc định cả Spring `Environment` | Có |

Khi nhiều nguồn cùng xác định một key, `Environment` chọn **nguồn ưu tiên cao nhất**, không quan tâm code nào tình cờ đọc property trước. Trong cấu hình chuẩn, command-line option được ưu tiên hơn Java system property, OS environment variable và file.

### Ví dụ dùng JVM system property

```bash
java -Ddemo.message=from-jvm -jar build/libs/cli-environment-demo-0.0.1-SNAPSHOT.jar
```

Không truyền `--demo.message`, nên `ApplicationArguments.containsOption("demo.message")` vẫn là `false`; nhưng `Environment.getProperty("demo.message")` có thể là `from-jvm`, ghi đè `from-file`.

### Ví dụ truyền đồng thời cả hai

```bash
java -Ddemo.message=from-jvm -jar build/libs/cli-environment-demo-0.0.1-SNAPSHOT.jar --demo.message=from-cli
```

Trong cấu hình chuẩn, `Environment` chọn `from-cli`, còn `System.getProperty("demo.message")` vẫn là `from-jvm`. **Spring không viết ngược option CLI vào JVM system properties.**

### Cảnh báo Gradle bootRun

`./gradlew bootRun --args='--demo.message=from-cli'` truyền option tới **ứng dụng**. Trong khi đó:

- `-Pname=value` là Gradle project property, không tự biến thành Spring Environment property.
- `-Dname=value` truyền vào JVM thực thi Gradle theo ngữ cảnh và không phải luôn được truyền cho JVM con chạy ứng dụng qua `bootRun`.
- Các tùy chọn của Gradle và các tùy chọn của ứng dụng được quản lý qua hai lớp parser khác nhau.

Để kiểm chứng một Java system property đúng trên **JVM ứng dụng**, cách dễ hiểu là chạy JAR bằng `java -D... -jar ...` như ví dụ, hoặc cấu hình rõ `systemProperty` cho tác vụ `bootRun` của Gradle.

## 9. Dùng --key=value để điều khiển Spring Boot runtime

Không chỉ property tự định nghĩa: nhiều khóa Spring Boot dùng cùng cơ chế:

```bash
java -jar myapp.jar --spring.profiles.active=dev
```

```bash
java -jar myapp.jar --spring.application.name=order-service
```

```bash
java -jar myapp.jar --server.port=9090
```

```bash
java -jar myapp.jar --spring.main.web-application-type=none
```

Ý nghĩa:

- `spring.profiles.active` chọn active profiles, từ đó có thể ảnh hưởng nhóm config data được tải và các bean theo `@Profile`.
- `spring.application.name` đặt tên ứng dụng dùng ở nhiều tích hợp/logging.
- `server.port` cấu hình cổng Web server nếu ứng dụng khởi tạo Web server được hỗ trợ.
- `spring.main.web-application-type` ảnh hưởng kiểu ứng dụng khi Spring Boot áp dụng cấu hình đó.

**Tính thời điểm là thiết yếu.** Một số khóa như `spring.config.name`, `spring.config.location`, `spring.config.additional-location` được đọc **rất sớm** để tìm file cấu hình. Truyền chúng qua CLI từ lúc chạy phù hợp hơn chỉnh `Environment` muộn sau khi bean đã tạo.

Nếu bạn gọi `application.setAddCommandLineProperties(false)`, đừng ngạc nhiên khi những option chỉ tồn tại trên CLI **không còn tham gia việc thiết lập Environment**. Việc bỏ command-line property source có thể ảnh hưởng cả cấu hình bootstrap, không chỉ các thuộc tính nghiệp vụ `demo.*`.

Lưu ý: một setter Java tường minh trên `SpringApplication` và một property trong `Environment` có thể tương tác theo quy tắc binding/khởi động cụ thể của Spring Boot. **Không suy đoán quy tắc ưu tiên setter so với property CLI từ thứ tự `PropertySource`**, vì chúng không phải hai `PropertySource` cùng loại. Để học chính xác quan hệ `--key=value` với `Environment`, hãy tách việc đó khỏi các setter bootstrap khác.

## 10. Khi nào dùng ApplicationArguments thay vì Environment?

**Dùng `ApplicationArguments` khi câu hỏi là “người chạy đã truyền gì?”**

- Kiểm tra người vận hành có truyền chính xác `--dry-run` hay không.
- Đọc một tham số positional như `report.csv`.
- Xử lý nhiều lần xuất hiện của một option như `--tag=a --tag=b`.
- Phân biệt option không xuất hiện với option có xuất hiện nhưng không có value.
- Đọc nguyên danh sách arguments đã truyền vào `SpringApplication.run(...)`, sau khi áp dụng các kiểm tra bảo mật cần thiết.

**Dùng `Environment`, `@Value` hoặc `@ConfigurationProperties` khi câu hỏi là “cấu hình ứng dụng hiệu lực là gì?”**

- Một property có fallback từ `application.properties`.
- Một cấu hình có thể được ghi đè bằng OS environment, Java `-D` hoặc CLI.
- Binding các kiểu `int`, `Duration`, `DataSize`, enum hay một object cấu hình có nhiều trường.
- Điều kiện tạo bean/auto-configuration dựa trên property.
- Cần cùng logic dù cấu hình được triển khai từ file, container environment hoặc dòng lệnh.

Điểm dễ sai:

```java
// Ví dụ sai về tư duy:
if (arguments.containsOption("demo.message")) {
    // Không có nghĩa đây là nguồn duy nhất cung cấp demo.message.
}
```

Nếu property có trong file hoặc OS environment mà không có option CLI, `containsOption` là `false` nhưng ứng dụng vẫn có cấu hình.

Ngược lại:

```java
// Ví dụ sai về tư duy:
String option = environment.getProperty("demo.message");
// Đây không nhất thiết là giá trị người vận hành đã truyền trong CLI.
```

Giá trị này có thể đến từ file hoặc system properties, thậm chí khi command-line property source bị tắt.

## 11. Các trường hợp biên: flag, rỗng, lặp, gõ sai và loại dữ liệu

### 11.1. --flag không đồng nghĩa --flag=true

```bash
java -jar myapp.jar --dry-run
```

`ApplicationArguments.containsOption("dry-run")` là `true`; `getOptionValues("dry-run")` là danh sách rỗng vì không có `=value`. Đừng tự tuyên bố `@ConfigurationProperties.booleanField` luôn trở thành `true` trong mọi cách parse chỉ nhờ option xuất hiện. Nếu cần kiểm tra **sự hiện diện của cờ**, `containsOption` rõ nghĩa nhất; nếu muốn cấu hình boolean theo property, dùng cú pháp tường minh:

```bash
java -jar myapp.jar --demo.dry-run=true
```

và binding field boolean tương ứng. Phân biệt cả `--flag=`, trong đó value là chuỗi rỗng, có thể không chuyển đổi hợp lệ đối với kiểu đích.

### 11.2. Lặp cùng key

```bash
java -jar myapp.jar --tag=red --tag=blue
```

`ApplicationArguments.getOptionValues("tag")` trả danh sách gồm cả `red` và `blue`. Nếu cần một danh sách có semantics rõ, xử lý bằng `ApplicationArguments` hoặc binding đúng kiểu collection; không tự cho rằng CLI đơn trị luôn có quy tắc “giá trị cuối thắng” như khi xử lý nhiều file cấu hình.

### 11.3. Sai tên property

Spring Boot không mặc định coi mọi option không nhận diện là lỗi. Ví dụ:

```bash
java -jar myapp.jar --demo.mesage=typo
```

Nếu code chỉ hỏi `demo.message`, nó không tự sửa lỗi chính tả `mesage` thành `message`. Một option lạ có thể tồn tại trong Environment nhưng **không có consumer** sử dụng nó. Nên đặt tên property thống nhất, có configuration metadata khi dùng `@ConfigurationProperties`, và kiểm tra/test các khóa quan trọng.

Relaxed binding giúp hỗ trợ các biến thể hợp lệ của tên khi bind, nhưng **không sửa lỗi gõ sai** tùy ý và không có nghĩa mọi API truy cập property đều diễn giải mọi dạng tên giống nhau. Đối với `@Value`, ưu tiên tên canonical dạng chữ thường và kebab-case khi phù hợp.

### 11.4. Sai kiểu dữ liệu

```bash
java -jar myapp.jar --demo.retries=banana
```

Nếu `demo.retries` được bind vào `int` của record `DemoSettings` trong ví dụ phần 7, Spring Boot sẽ không thể chuyển chuỗi `banana` thành số nguyên và startup có thể thất bại với lỗi binding/conversion. `Environment.getProperty("demo.retries")` ở dạng chuỗi có thể vẫn trả `banana` trước khi binding, nhưng điều đó không đảm bảo một consumer yêu cầu kiểu số sẽ chạy được.

Vì thế “có property” và “property hợp lệ với cấu hình nghiệp vụ” là **hai bước khác nhau**. Muốn thông báo lỗi sớm, hãy bổ sung validation thích hợp cho `@ConfigurationProperties` trong project thực tế; không nuốt lỗi rồi dùng default không kiểm soát.

### 11.5. Tên option có dấu gạch ngang và dấu chấm

Tên property nên thống nhất theo nhóm:

```text
--demo.max-retries=5
--demo.api-timeout=3s
```

Những khóa này thể hiện property theo dạng canonical dễ đọc và có thể bind vào các field tương ứng khi cấu hình `@ConfigurationProperties` đúng. Việc trực tiếp gọi `Environment.getProperty(...)` bằng một tên khác biệt về kiểu chữ/dấu gạch có thể có quy tắc khác với **relaxed binding** của Boot. Để tránh hiểu nhầm, minh họa `demo.message` dùng đúng cùng một tên từ CLI đến file, Environment, `@Value` và record.

### 11.6. Non-option không tự ghi đè property cùng tên

```bash
java -jar myapp.jar orders.csv
```

`orders.csv` xuất hiện trong `ApplicationArguments.getNonOptionArgs()`, nhưng không tự tạo property `demo.file=orders.csv`. Một số implementation `CommandLinePropertySource` có thể tổng hợp non-option args dưới một tên nguồn đặc biệt; đừng nhầm cơ chế đó với việc **mỗi positional argument tự trở thành property có tên tùy ý**.

### 11.7. Hai chữ -- trong vị trí đặc biệt

Nếu chương trình dùng đối số phân cách `--`, những chuỗi phía sau không nên bị coi là Spring options một cách tùy tiện. Khi lệnh có nhiều lớp như Gradle, Docker entrypoint, shell script hoặc launcher, cần xác định **lớp nào xử lý `--` trước**. Điều quan trọng nhất là giá trị thực tế đến `String[] args` của ứng dụng — có thể kiểm tra bằng `ApplicationArguments.getSourceArgs()` trong môi trường test không chứa secrets.

## 12. Chẩn đoán khi CLI không ghi đè cấu hình

Khi đã chạy `--demo.message=from-cli` nhưng service vẫn nhận `from-file`, hãy kiểm tra có hệ thống:

1. **Đúng cách truyền option chưa?** Lệnh có `--demo.message=from-cli` **sau tên JAR** hoặc trong `bootRun --args` không? Hay đã truyền nhầm `-D...`, `-P...`, hay `--demo.message from-cli`?
2. **Đúng `SpringApplication.run(args)` chưa?** Một `main` tự viết mà gọi `run(new String[0])` đã bỏ qua các đối số CLI nhận từ JVM.
3. **Có gọi `setAddCommandLineProperties(false)` không?** Nếu có, `ApplicationArguments` vẫn có thể thấy option, nhưng Environment không được override từ nguồn CLI.
4. **Đúng key chưa?** Kiểm tra `demo.message`, dấu chấm, dấu gạch, chữ hoa thường và lỗi gõ sai; với `@Value` dùng tên canonical khi có relaxed binding.
5. **Có consumer nào đang ghi đè hoặc chốt giá trị trước không?** Bean có lấy property sớm, tự chuyển vào trường cố định, hay mã khác đã thay đổi/loại bỏ property source?
6. **Tại thời điểm nào đo?** Trong một bean sau khi Environment chuẩn bị sẽ phù hợp để kiểm tra giá trị runtime. Đừng đọc Environment ở `ApplicationStartingEvent` khi nó chưa được chuẩn bị.
7. **Có test/devtools/custom property sources không?** Môi trường test có thể thêm nguồn ưu tiên cao hơn CLI; đừng khẳng định thứ tự runtime luôn áp dụng nguyên vẹn cho mọi test.
8. **Có nhiều process/replicas không?** Bạn có thể đang xem log hoặc request từ một instance khác với instance nhận CLI mới.

### Kiểm tra nguồn trong Environment một cách chọn lọc

Trong một bean/test có `ConfigurableEnvironment environment`:

```java
for (var source : environment.getPropertySources()) {
    if (source.containsProperty("demo.message")) {
        System.out.println(
                source.getName() + " -> "
                + source.getProperty("demo.message"));
    }
}
```

Đây là **đoạn tích hợp**, không phải chương trình Java chạy độc lập. Nó hữu ích khi cần biết một property xuất hiện ở những source nào. Việc in danh sách tất cả properties có thể lộ secrets; nên **chỉ kiểm tra khóa không nhạy cảm** và không bật dump cấu hình ở production.

Nếu dự án có Actuator được cấu hình và bảo vệ phù hợp, endpoint `/actuator/env` và `/actuator/configprops` hỗ trợ xác định nguồn/binding của cấu hình; chúng có thể che giá trị nhạy cảm theo mặc định và cần được kiểm soát truy cập. Không mở các endpoint này công khai chỉ để debug một tham số.

## 13. Bảo mật: command-line options dễ bị lộ hơn bạn nghĩ

Không đưa mật khẩu, private key, token hoặc connection secret lên CLI nếu có cơ chế an toàn hơn. Đối số tiến trình có thể hiện trong process listing, lịch sử shell, log ứng dụng/CI, file cấu hình triển khai, script vận hành hoặc công cụ quan sát. Đọc qua `ApplicationArguments` hay `Environment` **không tự làm dữ liệu nhạy cảm an toàn**.

Trong mã ví dụ phần 7, ta in args vì tất cả là dữ liệu giả không nhạy cảm. Với ứng dụng thật:

- Không log toàn bộ `getSourceArgs()` ở production.
- Không in toàn bộ `Environment.getPropertySources()` hoặc `SPRING_APPLICATION_JSON`.
- Dùng cơ chế quản lý secrets, environment injection hoặc tệp secret được bảo vệ tùy nền tảng (chúng cũng cần kiểm soát quyền và log).
- Dùng validation và thông báo lỗi không chứa value nhạy cảm.
- Hạn chế để người dùng ngoài hệ thống điều khiển tùy ý các property như endpoint management, logging hoặc profile.

`--key=value` là **cơ chế cấu hình tiện lợi**, không phải cơ chế phân quyền hay bảo mật.

## 14. Bài thực hành tự kiểm chứng

Dùng project `cli-environment-demo` ở phần 7. Mỗi bài nên chạy riêng và đối chiếu **cả hai kênh** `ApplicationArguments` và `Environment`:

**Bài A — không truyền CLI:** chạy `./gradlew bootRun`. Giải thích vì sao `containsOption("demo.message") == false` nhưng `Environment` vẫn trả `from-file`.

**Bài B — ghi đè file:** chạy với `--demo.message=from-cli --demo.retries=7 orders.csv`. Kiểm tra `ApplicationArguments`, `Environment`, `@Value` và `DemoSettings` đều phản ánh đúng nơi lấy dữ liệu; phân biệt positional `orders.csv`.

**Bài C — ưu tiên CLI so với JVM system property:** chạy JAR với `-Ddemo.message=from-jvm` và `--demo.message=from-cli`. Đọc đồng thời `System.getProperty("demo.message")` và `Environment.getProperty("demo.message")` trong runner; giải thích vì sao hai kết quả có thể khác.

**Bài D — tắt command-line property source:** chạy ví dụ `-Dexample.disable-cli-properties=true` ở phần 7. Giải thích vì sao `ApplicationArguments` vẫn có `from-cli` nhưng object cấu hình và `@Value` vẫn dùng `from-file`.

**Bài E — option thiếu value:** truyền `--demo.message other-file.csv`. Kiểm tra `getOptionValues("demo.message")` và `getNonOptionArgs()`. Quan sát phản ứng của việc bind cấu hình với option không có value; không mặc nhiên cho rằng `other-file.csv` là value của `demo.message`.

**Bài F — sai kiểu:** truyền `--demo.retries=not-a-number`. Xác định exception và bước binding thất bại, không diễn giải việc đó thành “Environment không nhận option”.

**Bài G — thêm một cấu hình mới:** thêm `demo.feature-enabled=false` trong file và một field boolean phù hợp vào record. Ghi đè bằng `--demo.feature-enabled=true`, đọc qua `Environment` và `@ConfigurationProperties`. Đảm bảo property name/field tuân theo quy tắc relaxed binding.

**Bài H — lặp option:** truyền `--tag=a --tag=b` và đọc bằng `ApplicationArguments.getOptionValues("tag")`. Giải thích vì sao có danh sách hai giá trị không đồng nghĩa rằng trong mọi consumer sẽ tự động có một mảng typed đúng mong muốn.

### Câu hỏi tự đánh giá

1. `--server.port=9090` được bổ sung vào `Environment` theo mặc định bằng cơ chế nào?
2. Nếu `application.properties` và CLI cùng định nghĩa `demo.message`, nguồn nào thắng trong runtime mặc định? Có phải file gốc bị sửa không?
3. Vì sao `ApplicationArguments.containsOption("demo.message")` có thể `false` khi `Environment.getProperty("demo.message")` có giá trị?
4. Khác biệt giữa `--key=value`, `-Dkey=value` và OS environment variable là gì?
5. `--name Lan` có tương đương `--name=Lan` không? `Lan` được parser xem là gì?
6. Khi `setAddCommandLineProperties(false)`, `ApplicationArguments.getSourceArgs()` có bị xóa không?
7. Vì sao khóa `demo.retries` có giá trị chữ `banana` trong Environment nhưng việc bind `int` thất bại?
8. Khi nào nên dùng `@ConfigurationProperties` thay vì tự parse `String[] args`?
9. Một property do CLI cung cấp chắc chắn có tác dụng với mọi module không? Vì sao?
10. Tại sao không nên in các đối số chứa secrets ra log?

Trả lời được các câu trên và kiểm chứng bằng chương trình giúp bạn phân biệt **đầu vào dòng lệnh**, **nguồn thuộc tính trong Spring**, **thứ tự ghi đè** và **cách sử dụng cấu hình đã binding**.

## 15. Tóm tắt ra quyết định

| Bạn cần biết | API/cơ chế phù hợp |
|---|---|
| Người dùng có truyền chính xác `--dry-run` không? | `ApplicationArguments.containsOption("dry-run")` |
| Người dùng truyền nhiều `--tag=value` nào? | `ApplicationArguments.getOptionValues("tag")` |
| Tham số không có tên như tên file là gì? | `ApplicationArguments.getNonOptionArgs()` |
| Thuộc tính hiệu lực sau khi xét file, env và CLI? | `Environment.getProperty("key")` |
| Cấu hình một nhóm property thành object typed? | `@ConfigurationProperties` |
| Tiêm một property đơn lẻ vào bean? | `@Value("${key}")` |
| Muốn CLI không tự ghi đè Environment? | `SpringApplication.setAddCommandLineProperties(false)` **trước run** |
| Cần biết property đến từ nguồn nào? | Kiểm tra `ConfigurableEnvironment.getPropertySources()`, có kiểm soát bảo mật |
| Cần bổ sung property source sớm hơn quá trình tạo bean? | `EnvironmentPostProcessor` hoặc cơ chế cấu hình Spring Boot thích hợp |

**Kết luận:** với cấu hình mặc định, `--key=value` đi vào `SpringApplication.run(args)`, được parse thành option và đưa vào một `PropertySource` của `Environment` có ưu tiên cao hơn file cấu hình. Vì vậy `Environment`, `@Value` và `@ConfigurationProperties` có thể thấy giá trị override. `ApplicationArguments` là đường đọc **đối số gốc**, không phải bản sao của cấu hình hiệu lực; tắt command-line property source không xóa những đối số này.

## Tài liệu chính thức

- Spring Boot 3.3, Externalized Configuration — thứ tự nguồn và phần *Accessing Command Line Properties*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3, `SpringApplication` — *Accessing Application Arguments*: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3, `ApplicationArguments` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Framework 6.1, `SimpleCommandLinePropertySource`: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/env/SimpleCommandLinePropertySource.html
- Spring Framework, `Environment` và `ConfigurableEnvironment`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html