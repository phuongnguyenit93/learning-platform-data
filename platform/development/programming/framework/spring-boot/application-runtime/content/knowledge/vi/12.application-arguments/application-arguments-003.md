# Đọc tên tùy chọn, sự tồn tại và danh sách giá trị với ApplicationArguments — Spring Boot 3.3

## 1. Mục tiêu

Khi chạy ứng dụng Spring Boot qua command line, ta thường truyền các đối số như `--mode=import`, `--region=apac`, `--verbose` hoặc tên tệp cần xử lý. Spring Boot cung cấp **`org.springframework.boot.ApplicationArguments`** để đọc các đối số đó theo cấu trúc, thay vì tự tách từng phần tử của `String[] args` trong `main()`.

Bài học tập trung vào ba thao tác chính:

1. **Đọc danh sách tên tùy chọn** bằng `getOptionNames()`.
2. **Kiểm tra một tùy chọn có được truyền hay không** bằng `containsOption(name)`.
3. **Đọc toàn bộ giá trị của một tùy chọn** bằng `getOptionValues(name)`.

Đặc biệt, bạn sẽ phân biệt **không có option**, **có option nhưng không có giá trị**, **có giá trị rỗng** và **một option lặp nhiều lần**. Đây là bốn trường hợp dễ gây lỗi trong ứng dụng CLI.

Bài dùng **Java 21 + Spring Boot 3.3.13 + Maven**, ví dụ chạy được, stdout xác định, JUnit test và hướng dẫn áp dụng trong `ApplicationRunner`. Không cần web server hay database.

## 2. Đối số ứng dụng gồm những loại nào?

Xét lệnh:

```bash
java -jar app.jar --mode=import --region=apac --region=eu --verbose orders.csv
```

Java truyền cho phương thức `main(String[] args)` một mảng gồm các chuỗi sau, theo thứ tự:

```text
--mode=import
--region=apac
--region=eu
--verbose
orders.csv
```

Spring Boot phân biệt:

| Token | Phân loại | Ý nghĩa |
| --- | --- | --- |
| `--mode=import` | Option có giá trị | Tùy chọn `mode`, một giá trị `import` |
| `--region=apac` | Option có giá trị | Tùy chọn `region`, giá trị đầu |
| `--region=eu` | Option cùng tên lặp lại | `region` có thêm giá trị `eu` |
| `--verbose` | Option không có giá trị | Tên `verbose` xuất hiện, không có phần `=value` |
| `orders.csv` | Non-option argument | Đối số vị trí, không bắt đầu bằng `--` |

**Cú pháp option chuẩn:** `--name` hoặc `--name=value`. Tên đưa vào `ApplicationArguments` là **`name`**, không kèm hai dấu gạch ngang.

Ví dụ có khoảng trắng trong một giá trị phải được shell truyền thành **một token**:

```bash
java -jar app.jar "--label=morning batch"
```

Phần value là `morning batch`. Cách quote cụ thể tùy hệ điều hành và shell; `ApplicationArguments` chỉ xử lý mảng token sau khi JVM đã nhận được chúng.

### 2.1. Một dấu gạch ngang không giống hai dấu

`-v` không được bộ phân tích option đơn giản của Spring Boot xem như tên option `v` theo cú pháp `--name`. Nó thuộc nhóm non-option arguments trong mô hình này.

Tương tự, lệnh:

```bash
java -jar app.jar --mode import
```

không có cùng ý nghĩa với `--mode=import`: `--mode` là **option không kèm giá trị**, còn `import` là **non-option**. Nếu muốn truyền giá trị, hãy dùng dấu `=` trong **cùng token**.

### 2.2. Dấu phẩy không có nghĩa là nhiều giá trị option

```bash
java -jar app.jar --region=apac,eu
```

Với cú pháp trên, `getOptionValues("region")` có **một phần tử** là chuỗi `apac,eu`, không phải hai phần tử `apac` và `eu`.

Muốn Spring giữ hai giá trị riêng, truyền lặp:

```bash
java -jar app.jar --region=apac --region=eu
```

Nếu nghiệp vụ cần phân tách danh sách dạng CSV, việc tách dấu phẩy phải do code của bạn thực hiện có chủ đích, bao gồm xử lý escaping/quoting phù hợp.

## 3. ApplicationArguments cung cấp những phương thức nào?

Interface `org.springframework.boot.ApplicationArguments` có các thao tác cốt lõi:

| Phương thức | Kiểu trả về | Diễn giải |
| --- | --- | --- |
| `getOptionNames()` | `Set<String>` | Tập **tên khác nhau** của các option xuất hiện |
| `containsOption(String name)` | `boolean` | Có xuất hiện option mang tên này hay không |
| `getOptionValues(String name)` | `List<String>` hoặc `null` | Các giá trị của option; **`null` khi không tồn tại** |
| `getNonOptionArgs()` | `List<String>` | Danh sách đối số không thuộc option |
| `getSourceArgs()` | `String[]` | Mảng đối số nguồn, chưa qua phân loại, giữ thứ tự token |

Chú ý:

- `getOptionNames()` trả về **Set**, vì thế một tên lặp nhiều lần vẫn chỉ xuất hiện **một lần trong tập tên**.
- Set này **không phải API bảo đảm thứ tự sắp xếp alphabet**. Nếu cần in kết quả ổn định, dùng `new TreeSet<>(args.getOptionNames())`.
- `containsOption("mode")` nhận chuỗi tên **không có** tiền tố `--`. `containsOption("--mode")` là kiểm tra **tên khác**, không đúng điều bạn muốn.
- Các tên option có thể chứa dấu chấm như `spring.profiles.active`; kiểm tra bằng chính tên đã truyền, ví dụ `containsOption("spring.profiles.active")`.
- `getOptionValues` không phân tích sang `boolean`, `int`, `Duration` hoặc enum. Các phần tử vẫn là **chuỗi**; ứng dụng chịu trách nhiệm kiểm tra và chuyển kiểu.
- `getSourceArgs()` hữu ích để debug và chuyển tiếp raw arguments nhưng không nên log bừa bãi vì command line có thể chứa thông tin nhạy cảm.

## 4. Bốn trạng thái cần phân biệt khi đọc giá trị

Đây là hợp đồng API quan trọng nhất của bài học:

| Input | `containsOption("flag")` | `getOptionValues("flag")` | Ý nghĩa |
| --- | --- | --- | --- |
| Không truyền `flag` | `false` | `null` | Option không tồn tại |
| `--flag` | `true` | `[]` | Option tồn tại nhưng **không kèm giá trị** |
| `--flag=` | `true` | `[""]` | Option tồn tại, có **một giá trị là chuỗi rỗng** |
| `--flag=yes` | `true` | `["yes"]` | Option có một giá trị |
| `--flag=a --flag=b` | `true` | `["a", "b"]` | Option lặp và có nhiều giá trị |

Ba giá trị **`null`**, **`[]`** và **`[""]`** có nghĩa khác nhau.

### 4.1. Vì sao `values == null` không giống `values.isEmpty()`?

Ví dụ:

```java
List<String> values = args.getOptionValues("flag");
if (values == null) {
    System.out.println("Không truyền --flag");
}
else if (values.isEmpty()) {
    System.out.println("Có --flag nhưng không có value");
}
else {
    System.out.println("Có value: " + values);
}
```

Đoạn trên là **minh họa bên trong `ApplicationRunner.run(...)`**, nơi biến `args` có kiểu `ApplicationArguments`. Thứ tự kiểm tra rất quan trọng: gọi `values.isEmpty()` **trước** khi kiểm tra `null` có thể gây `NullPointerException`.

### 4.2. Vì sao `List.toString()` dễ gây nhầm với chuỗi rỗng?

Đây là đặc điểm hiển thị của Java, không phải lỗi Spring Boot:

```java
System.out.println(List.of());   // []
System.out.println(List.of("")); // []
```

Cả hai có thể cùng in thành `[]` do `List.toString()` không thêm dấu nháy quanh phần tử. Vì thế nếu muốn **phân biệt danh sách rỗng và danh sách có một chuỗi rỗng trong log**, hãy hiển thị từng phần tử kèm dấu nháy hoặc in thêm `values.size()`.

Ví dụ: danh sách `[]` có `size()==0`; danh sách `[""]` có `size()==1` và phần tử đầu là chuỗi rỗng. Chương trình hoàn chỉnh ở mục 6 dùng hàm định dạng riêng để in `['']` thay vì chỉ dùng `List.toString()`.

### 4.3. Tên option lặp không tạo nhiều tên

Với:

```text
--region=apac --region=eu --region=us
```

- `getOptionNames()` chứa `"region"` **một lần**.
- `containsOption("region")` là `true`.
- `getOptionValues("region")` trả `["apac", "eu", "us"]` theo các giá trị xuất hiện trong đối số.
- Không cần duyệt `getSourceArgs()` để tự tìm các token bắt đầu bằng `--region=`.

**Chú ý:** nếu nhiều lần truyền cùng tên nhưng có một lần ở dạng cờ không giá trị, danh sách trả về chỉ chứa các **giá trị thực sự được chỉ định**. `containsOption` xác nhận tên xuất hiện; `getOptionValues` không phải danh sách từng lần xuất hiện kèm marker `null`.

### 4.4. Phân biệt tồn tại và “được bật”

`containsOption("trace") == true` chỉ chứng minh **option có mặt**. Nếu lệnh là:

```text
--trace=false
```

thì `containsOption("trace")` vẫn là `true`, còn `getOptionValues("trace")` chứa chuỗi `"false"`. Vì vậy không được dùng riêng `containsOption` để diễn giải một option có value theo kiểu Boolean.

Có hai thiết kế phổ biến:

- **Presence-only switch:** quy ước `--trace` nghĩa là bật trace, không nhận `=true/false`; ứng dụng kiểm tra sự có mặt và **từ chối** các giá trị không được phép.
- **Boolean-valued option:** quy ước `--trace=true` hoặc `--trace=false`; đọc chính xác **một chuỗi**, validate `true`/`false`, rồi chuyển thành Boolean.

Việc chọn thiết kế nào là **hợp đồng CLI của ứng dụng**, không phải điều `containsOption` tự quyết định.

## 5. ApplicationArguments được dùng khi nào trong Spring Boot?

### 5.1. ApplicationRunner là điểm truy cập thuận tiện

Spring Boot gọi các bean triển khai `ApplicationRunner` sau khi `ApplicationContext` đã refresh và trước `ApplicationReadyEvent`. Phương thức:

```java
void run(ApplicationArguments args) throws Exception;
```

nhận đối tượng arguments có cấu trúc ngay lúc khởi động. `ApplicationRunner` phù hợp với ứng dụng CLI, import dữ liệu, migration do app quản lý, chế độ chạy một lần, kiểm tra tham số startup.

`CommandLineRunner` cũng chạy ở pha này nhưng nhận `String... args` thô:

```java
void run(String... args) throws Exception;
```

Nếu cần `getOptionNames`, `containsOption` và `getOptionValues`, ưu tiên `ApplicationRunner` thay vì tự viết parser trên mảng `String[]`.

### 5.2. Injection ApplicationArguments vào bean

Spring Boot cũng cung cấp `ApplicationArguments` dưới dạng đối tượng có thể được inject trong context của `SpringApplication`. Ví dụ minh họa:

```java
@Component
public class ImportOptions {
    private final ApplicationArguments arguments;

    public ImportOptions(ApplicationArguments arguments) {
        this.arguments = arguments;
    }

    public boolean isDryRun() {
        return arguments.containsOption("dry-run");
    }
}
```

Đây là **mẫu bổ sung**, cần import `@Component` và `ApplicationArguments`. Nó không phải chương trình Java độc lập. Ưu điểm là các service muốn đọc option không phải dùng biến `static` hoặc mang `String[]` toàn cục. Tuy nhiên, đừng cho rằng việc truyền args vào `SpringApplication` tự biến mọi nội dung của chúng thành cấu hình đã kiểm tra kiểu.

### 5.3. Khác gì Environment và @ConfigurationProperties?

`ApplicationArguments` cung cấp cái nhìn **đúng tập token mà lần gọi `SpringApplication.run` nhận được**. `Environment` là hệ thống property sources của Spring Boot, có thể gộp command-line properties với `application.yaml`, environment variables, JVM system properties và các nguồn cấu hình khác. `@ConfigurationProperties` bind các property thành object có kiểu, hỗ trợ validation.

Do đó:

- Muốn biết **người vận hành có thực sự truyền `--dry-run` hay không**: `containsOption("dry-run")`.
- Muốn đọc **mọi lần truyền `--region=...`**: `getOptionValues("region")`.
- Muốn một cấu hình có default, override qua nhiều nguồn và kiểm tra kiểu: `@ConfigurationProperties`.
- Muốn điều khiển mode CLI thuần bằng một số arguments: `ApplicationRunner` + `ApplicationArguments` rất rõ ràng.

Đừng nhầm “giá trị option không được truyền” với “ứng dụng không có property tương ứng”: property vẫn có thể đến từ `application.yaml` hoặc nguồn khác.

### 5.4. JVM options khác application options

Ví dụ:

```bash
java -Dapp.mode=demo -jar app.jar --mode=import
```

`-Dapp.mode=demo` là **JVM system property**, không phải một phần tử trong mảng `String[] args` của ứng dụng. `--mode=import` sau `-jar app.jar` mới là **application argument** mà `ApplicationArguments` sẽ phân tích.

Vị trí dấu gạch và nơi đặt token trong command line rất quan trọng. Tránh nhầm `-D` của JVM với `--name=value` của ứng dụng.

## 6. Ví dụ Maven hoàn chỉnh: in tên, sự tồn tại và giá trị

Chúng ta xây một Spring Boot **non-web** để chỉ kiểm tra đối số. Ví dụ không sử dụng database hay REST controller, có đầu ra xác định cho các dòng chủ động in.

### 6.1. Cấu trúc dự án

```text
cli-arguments-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/args/
    │   └── CliArgumentsApplication.java
    └── test/java/com/example/args/
        └── ApplicationArgumentsContractTest.java
```

### 6.2. pom.xml

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cli-arguments-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter` đủ để tạo app console, còn `spring-boot-starter-test` cung cấp JUnit Jupiter ở test scope. Ví dụ chọn Java 21; Spring Boot 3.3 hỗ trợ Java 17 trở lên.

### 6.3. Code ứng dụng

Tệp `src/main/java/com/example/args/CliArgumentsApplication.java`:

```java
package com.example.args;

import java.util.Arrays;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CliArgumentsApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(CliArgumentsApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }

    @Bean
    ApplicationRunner showArguments() {
        return args -> {
            System.out.println("option names: "
                    + new TreeSet<>(args.getOptionNames()));

            show(args, "region");
            show(args, "trace");
            show(args, "blank");
            show(args, "missing");
            show(args, "mode");

            System.out.println("non-options: " + args.getNonOptionArgs());
            System.out.println("raw: " + Arrays.toString(args.getSourceArgs()));
        };
    }

    private static void show(ApplicationArguments args, String name) {
        List<String> values = args.getOptionValues(name);

        System.out.println(name
                + ": present=" + args.containsOption(name)
                + ", values=" + describe(values));
    }

    private static String describe(List<String> values) {
        if (values == null) {
            return "<absent>";
        }

        return values.stream()
                .map(value -> "'" + value + "'")
                .collect(Collectors.joining(", ", "[", "]"));
    }
}
```

**Vì sao code như vậy?**

- `ApplicationRunner` cho phép Boot inject `ApplicationArguments` trực tiếp vào callback `run`.
- `new TreeSet<>(args.getOptionNames())` bảo đảm **in tên theo alphabet**, tránh test phụ thuộc thứ tự duyệt `Set` không được cam kết.
- `show(...)` in đồng thời `containsOption` và các giá trị để phân biệt absent/present.
- `describe(null)` trả `<absent>`; `describe(List.of())` trả `[]`; `describe(List.of(""))` trả `['']`.
- Hàm `describe` chỉ dùng để minh họa với các giá trị không có dấu nháy đơn. Nếu cần logging tổng quát, dùng serializer có escaping hoặc in length/size rõ ràng; không log secret.
- `WebApplicationType.NONE` tránh khởi động HTTP server; ứng dụng tập trung vào thao tác CLI.

### 6.4. Build và chạy

Từ thư mục `cli-arguments-demo`, cần JDK 21, Maven và dependency tải được:

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/cli-arguments-demo-0.0.1-SNAPSHOT.jar --region=apac --region=eu --trace --blank= --mode=sync reports.csv
```

Các dòng do **chương trình chủ động in** theo thứ tự:

```text
option names: [blank, mode, region, trace]
region: present=true, values=['apac', 'eu']
trace: present=true, values=[]
blank: present=true, values=['']
missing: present=false, values=<absent>
mode: present=true, values=['sync']
non-options: [reports.csv]
raw: [--region=apac, --region=eu, --trace, --blank=, --mode=sync, reports.csv]
```

Spring Boot cũng có thể in banner và log tùy cấu hình; khối trên **không phải toàn bộ stdout**. Các giá trị đúng vì `region` xuất hiện hai lần, `trace` không có `=...`, `blank` có một giá trị rỗng, `missing` không xuất hiện và `reports.csv` là non-option.

### 6.5. Thử đổi cách truyền option

Thử:

```bash
java -jar target/cli-arguments-demo-0.0.1-SNAPSHOT.jar --mode run.csv
```

Các dòng đáng chú ý sẽ là:

```text
option names: [mode]
region: present=false, values=<absent>
trace: present=false, values=<absent>
blank: present=false, values=<absent>
missing: present=false, values=<absent>
mode: present=true, values=[]
non-options: [run.csv]
raw: [--mode, run.csv]
```

Điều này chứng minh `--mode run.csv` **không** khiến `run.csv` trở thành giá trị của `mode`: phải dùng `--mode=run.csv` nếu muốn nó là value của option.

### 6.6. Ví dụ với giá trị chứa dấu phẩy

Thử:

```bash
java -jar target/cli-arguments-demo-0.0.1-SNAPSHOT.jar --region=apac,eu
```

Khi đó dòng region là:

```text
region: present=true, values=['apac,eu']
```

Không có phép tách tự động theo dấu phẩy; đó là một giá trị chuỗi.

## 7. Unit test cho hợp đồng null, empty, empty-string và multi-value

Mặc dù demo trên là một ứng dụng Boot đầy đủ, bạn có thể kiểm tra riêng logic phân tích arguments **không cần chạy cả context** bằng `DefaultApplicationArguments`.

Tệp `src/test/java/com/example/args/ApplicationArgumentsContractTest.java`:

```java
package com.example.args;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.DefaultApplicationArguments;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ApplicationArgumentsContractTest {

    @Test
    void readsOptionNamesExistenceAndValues() {
        ApplicationArguments args = new DefaultApplicationArguments(
                "--region=apac",
                "--region=eu",
                "--trace",
                "--blank=",
                "reports.csv");

        assertEquals(Set.of("region", "trace", "blank"),
                args.getOptionNames());

        assertTrue(args.containsOption("region"));
        assertTrue(args.containsOption("trace"));
        assertFalse(args.containsOption("missing"));

        assertEquals(List.of("apac", "eu"),
                args.getOptionValues("region"));
        assertEquals(List.of(),
                args.getOptionValues("trace"));
        assertEquals(List.of(""),
                args.getOptionValues("blank"));
        assertNull(args.getOptionValues("missing"));

        assertEquals(List.of("reports.csv"), args.getNonOptionArgs());
        assertArrayEquals(new String[] {
                "--region=apac", "--region=eu",
                "--trace", "--blank=", "reports.csv"
        }, args.getSourceArgs());
    }

    @Test
    void separateTokenIsNotAnOptionValue() {
        ApplicationArguments args =
                new DefaultApplicationArguments("--mode", "import");

        assertTrue(args.containsOption("mode"));
        assertEquals(List.of(), args.getOptionValues("mode"));
        assertEquals(List.of("import"), args.getNonOptionArgs());
    }

    @Test
    void commaSeparatedInputIsSingleValue() {
        ApplicationArguments args =
                new DefaultApplicationArguments("--region=apac,eu");

        assertEquals(List.of("apac,eu"), args.getOptionValues("region"));
    }
}
```

Chạy:

```bash
mvn test
```

Kỳ vọng Maven báo **3 tests, 0 failures, 0 errors** (ngoài output do Maven plugin). Đây là unit test cho `ApplicationArguments` trên classpath Spring Boot; không cần `@SpringBootTest` vì ta không kiểm thử dependency injection hay `ApplicationContext` ở đây.

**Lợi ích của test:** chúng kiểm tra trực tiếp hành vi API, tránh kết luận dựa trên `List.toString()` dễ gây nhầm giữa `[]` và `[""]`.

## 8. Cách đọc option an toàn trong code thực tế

### 8.1. Tùy chọn bắt buộc đúng một giá trị

Giả sử chương trình yêu cầu `--mode=import` và không cho phép trống hoặc lặp:

```java
static String requireSingleNonBlank(
        ApplicationArguments args, String name) {

    List<String> values = args.getOptionValues(name);

    if (values == null) {
        throw new IllegalArgumentException(
                "Thiếu tùy chọn --" + name + "=...");
    }
    if (values.size() != 1 || values.get(0).isBlank()) {
        throw new IllegalArgumentException(
                "Tùy chọn --" + name + " phải có đúng một giá trị không rỗng");
    }
    return values.get(0);
}
```

Đây là **phương thức bổ sung vào một class Java có import `ApplicationArguments` và `List`**; không chạy độc lập. Nó bác bỏ các trường hợp:

- Không truyền option: `values == null`.
- Chỉ truyền `--mode`: danh sách rỗng.
- Truyền `--mode=`: danh sách có một chuỗi rỗng.
- Truyền nhiều lần `--mode=a --mode=b`: danh sách dài hơn một.
- Truyền khoảng trắng và yêu cầu non-blank: `String.isBlank()` bắt trường hợp chỉ có whitespace.

Nếu mode có tập giá trị hữu hạn, tiếp tục validate bằng `switch` hoặc enum, không chỉ lấy một chuỗi tùy ý.

### 8.2. Tùy chọn presence-only

Giả sử `--dry-run` chỉ là cờ bật:

```java
static boolean dryRunEnabled(ApplicationArguments args) {
    if (!args.containsOption("dry-run")) {
        return false;
    }
    List<String> values = args.getOptionValues("dry-run");
    if (values != null && !values.isEmpty()) {
        throw new IllegalArgumentException(
                "--dry-run không nhận giá trị; chỉ dùng --dry-run");
    }
    return true;
}
```

Đây là **phương thức minh họa**. `--dry-run=false` không phải là “không dry-run”; nó là input không đúng hợp đồng presence-only, nên ví dụ chủ động từ chối. Cách này tránh bật tính năng ngoài ý muốn vì chỉ kiểm tra tên.

### 8.3. Tùy chọn boolean thực sự

Nếu CLI cho phép `--audit=true` hoặc `--audit=false`, validate rõ ràng:

```java
static boolean readBoolean(ApplicationArguments args, String name) {
    String value = requireSingleNonBlank(args, name);
    if ("true".equalsIgnoreCase(value)) {
        return true;
    }
    if ("false".equalsIgnoreCase(value)) {
        return false;
    }
    throw new IllegalArgumentException(
            "--" + name + " chỉ chấp nhận true hoặc false");
}
```

**Đoạn này sử dụng phương thức `requireSingleNonBlank` ở trên**. Nó không âm thầm coi mọi chuỗi lạ như `Boolean.parseBoolean` (vốn trả `false` cho nhiều chuỗi không phải `"true"`).

### 8.4. Tùy chọn lặp và dữ liệu nhiều phần tử

```java
List<String> regions = args.getOptionValues("region");
if (regions == null || regions.isEmpty()) {
    throw new IllegalArgumentException(
            "Cần ít nhất một --region=value");
}

for (String region : regions) {
    if (region.isBlank()) {
        throw new IllegalArgumentException("Mã region không được rỗng");
    }
    // Dùng region theo thứ tự xuất hiện nếu ứng dụng yêu cầu.
}
```

Đây là **đoạn minh họa bên trong runner**, nơi có biến `args` kiểu `ApplicationArguments`. Nếu region phải thuộc danh sách cho phép, hãy validate thay vì đưa chuỗi không tin cậy vào query hoặc đường dẫn.

### 8.5. Khi nào không nên tự parse `ApplicationArguments`?

Với cấu hình ứng dụng có nhiều default, profile, file `.yaml`, environment variable và type conversion, `@ConfigurationProperties` cùng Bean Validation sẽ dễ bảo trì hơn. `ApplicationArguments` đặc biệt phù hợp với:

- Chế độ CLI one-shot.
- Nhiều tùy chọn cùng tên, cần giữ danh sách giá trị.
- Cần biết chính xác option có được truyền qua command line hay không.
- Cần thao tác với non-option positional arguments.
- Việc quyết định workflow startup trong `ApplicationRunner`.

Đừng nhồi mọi cấu hình dài hạn vào `ApplicationRunner` nếu chúng thực ra thuộc configuration model của Boot.

## 9. Tên option, kiểu dữ liệu, thứ tự và encoding

### 9.1. Tên option là khóa, không phải chuỗi `--key`

Đúng:

```java
args.containsOption("mode");
args.getOptionValues("mode");
```

Sai về ý nghĩa:

```java
args.containsOption("--mode");
args.getOptionValues("--mode");
```

Những lời gọi sai không tìm option mang tên `"mode"`; API không tự cắt `--` khỏi tên truyền vào phương thức.

### 9.2. Option names không phải thứ tự raw CLI

Giả sử:

```text
--region=apac --mode=import --region=eu
```

`getOptionNames()` là tập `{region, mode}` chứ không phải luồng token `[region, mode, region]`. Nếu muốn biết thứ tự **toàn bộ token gốc**, dùng `getSourceArgs()`. Nếu muốn danh sách **các giá trị của riêng region**, dùng `getOptionValues("region")`.

Để in tên có thứ tự dễ đọc, bọc trong `TreeSet`; không dựa trên iteration order của `Set`.

### 9.3. Những đối số mang dấu cách

Shell có thể xử lý quoting khác nhau giữa PowerShell, cmd, Bash và zsh. Spring Boot không nhận nguyên dòng lệnh chưa tách, mà nhận một `String[]`. Vì vậy muốn một giá trị chứa dấu cách, quote để shell chuyển nó thành một phần tử duy nhất:

```bash
java -jar app.jar "--output-dir=monthly reports"
```

Tại Java, value là `monthly reports` không chứa dấu quote ngoài. Để kiểm chứng thực tế, có thể in `Arrays.toString(args.getSourceArgs())` **chỉ trong môi trường kiểm thử không có secret**.

### 9.4. Multiple values không đồng nghĩa cấu hình đã được validate

`--region=apac --region=unknown` hợp lệ về mặt cú pháp, nhưng `unknown` có thể không hợp lệ theo business. `ApplicationArguments` **không** thay bạn phân biệt vùng hỗ trợ, số nguyên hợp lệ, file có tồn tại, quota hay quyền truy cập.

Tách rõ **parsing** (API Boot) và **validation** (quy tắc ứng dụng), rồi mới thực hiện hành động.

## 10. Lỗi thường gặp và hướng khắc phục

| Lỗi hoặc triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `NullPointerException` khi `getOptionValues(...).isEmpty()` | Option chưa được truyền, API trả `null` | Kiểm tra `null` trước hoặc `containsOption` |
| `containsOption("--debug")` trả `false` | Tên truyền vào có `--` | Dùng `containsOption("debug")` |
| `--mode import` không được đọc thành `mode=import` | Parser hiểu `--mode` là cờ và `import` là non-option | Dùng `--mode=import` |
| `--trace=false` vẫn bị coi là “có trace” | `containsOption` kiểm tra hiện diện, không parse Boolean | Dùng quy ước presence-only hoặc validate value boolean |
| `--blank=` và `--blank` in như nhau với `List.toString()` | Danh sách có `""` và danh sách rỗng cùng dễ hiển thị thành `[]` | Kiểm tra `size()`, in thêm dấu nháy hoặc serialization rõ ràng |
| `--region=apac,eu` chỉ có một phần tử | Parser không tự tách dấu phẩy | Truyền lặp `--region=...` hoặc parse CSV có chủ đích |
| Tên option in thứ tự khác giữa các lần chạy | `Set` không bảo đảm thứ tự alphabet | Dùng `TreeSet` để trình bày |
| `-v` không được `containsOption("v")` nhận | Không theo cú pháp `--name` | Dùng `--verbose` hoặc tự triển khai parser hỗ trợ short options |
| JVM `-Dmode=x` không có trong `getOptionNames()` | Là system property, không phải app arg | Truy cập qua `Environment`, không trộn hai loại |
| Mã đọc value không cho phép nhiều lần | Có nhiều `--name=value` làm list dài hơn một | Nêu rõ quy tắc một/nhiều giá trị và validate |
| Dùng option để nhập secret, rồi log raw args | Secret dễ lộ trong logs hoặc process inspection | Ưu tiên biến môi trường, secret store, không log secrets |
| Runner hoạt động trước khi bean sẵn sàng? | Hiểu nhầm lifecycle | `ApplicationRunner` chạy sau context refresh |
| Dùng `getOptionValues` để kỳ vọng default từ YAML | API chỉ đọc args truyền vào `SpringApplication` | Dùng `Environment` hoặc `@ConfigurationProperties` nếu cần hợp nhất cấu hình |

### 10.1. Debug theo trình tự

1. Kiểm tra lệnh gọi Java đặt `--option` **sau** tên JAR/main class.
2. Kiểm tra mỗi token đã đúng cú pháp `--name=value` chưa.
3. Kiểm tra tên truyền cho `containsOption` hoặc `getOptionValues` **không có** `--`.
4. In **danh sách tên đã sort** và non-options, chỉ khi dữ liệu thử nghiệm an toàn.
5. Phân biệt `null`, `[]`, `[""]` và `["a", "b"]`.
6. Kiểm tra logic validate kiểu và điều kiện bắt buộc.
7. Nếu hành vi kỳ vọng liên quan `application.yaml` hoặc env variable, kiểm tra xem bạn đang dùng nhầm API CLI với property binding hay không.

### 10.2. Khi startup thất bại do đối số

Nếu một `ApplicationRunner` ném `IllegalArgumentException` vì thiếu option bắt buộc, Spring Boot có thể xử lý như **startup failure** và không hoàn tất luồng ready bình thường. Với app CLI, nên in thông báo dễ hiểu và nêu cú pháp sử dụng; với service chạy dài hạn, nên cân nhắc có thật cần làm hỏng startup vì option đó không.

`ApplicationReadyEvent` chỉ xảy ra sau khi các runners trả về thành công. Không đặt tác vụ quan trọng vào runner trước khi biết các option cần thiết hợp lệ và có chính sách xử lý lỗi rõ ràng.

## 11. Tình huống áp dụng thực tế

### 11.1. CLI nhập dữ liệu theo vùng

Yêu cầu:

```bash
java -jar importer.jar --region=apac --region=eu --mode=incremental files.csv
```

Giải pháp:

- `containsOption("mode")` hoặc `requireSingleNonBlank(args, "mode")` để kiểm tra mode bắt buộc.
- `getOptionValues("region")` lấy **hai giá trị** thay vì parsing chuỗi thô.
- `getNonOptionArgs()` lấy `files.csv`; validate rằng có đúng một tên tệp nếu nghiệp vụ yêu cầu.
- Kiểm tra `region` nằm trong tập được hỗ trợ và file path không vượt phạm vi cho phép.

### 11.2. Dry-run an toàn

Yêu cầu:

```bash
java -jar importer.jar --dry-run input.csv
```

Thiết kế `--dry-run` như **presence-only**; dùng `containsOption("dry-run")`, và từ chối `--dry-run=false` nếu không nằm trong hợp đồng CLI. Khi flag được bật, tuyệt đối không thực hiện bước write thật.

### 11.3. Người vận hành truyền nhiều endpoints

Yêu cầu:

```bash
java -jar worker.jar --endpoint=https://a.example --endpoint=https://b.example
```

`getOptionValues("endpoint")` giữ hai chuỗi URL. Ứng dụng cần validate scheme, host, quyền kết nối và timeout. Chỉ vì parser trả được hai strings không có nghĩa endpoint an toàn hoặc sẵn sàng.

### 11.4. Chế độ nhập bằng property sources

Nếu ứng dụng có `app.import.mode` mặc định trong YAML và môi trường deploy cũng có env variable override, nên dùng `@ConfigurationProperties` để nhận giá trị đã áp dụng precedence của Spring. `ApplicationArguments.containsOption("app.import.mode")` chỉ trả `true` nếu tên ấy **thực sự có trong CLI token**; không thể thay việc resolve các property sources.

## 12. Bài tập và câu hỏi tự kiểm tra

1. Với `--foo=bar --debug`, `getOptionNames()` chứa gì? `getOptionValues("debug")` là gì?
2. Vì sao `getOptionValues("missing") == null` khác với `getOptionValues("debug").isEmpty()`?
3. Với `--blank=`, danh sách có bao nhiêu phần tử? Vì sao `List.toString()` không đủ để chứng minh?
4. Với `--region=apac --region=eu`, tên `"region"` xuất hiện bao nhiêu lần trong `getOptionNames()` và có bao nhiêu phần tử trong `getOptionValues()`?
5. Vì sao `--mode import` không tương đương `--mode=import`?
6. Nếu chỉ truyền `--trace=false`, `containsOption("trace")` trả giá trị gì? Viết quy tắc validate Boolean phù hợp.
7. Lý do nào khiến `new TreeSet<>(args.getOptionNames())` phù hợp khi viết assertion log?
8. Tự sửa demo để yêu cầu đúng một option `--mode=sync` hoặc `--mode=async`, từ chối không có, trống và lặp.
9. Hãy kiểm tra `getNonOptionArgs()` khi truyền thêm `reports.csv` và `2026-11.csv`.
10. Viết JUnit test cho `--flag`, `--flag=`, `--flag=yes` và trường hợp option absent.
11. Dùng `new DefaultApplicationArguments("--mode=export", "--mode=import")` rồi nêu vì sao không nên chỉ gọi `get(0)` nếu app yêu cầu một mode duy nhất.
12. Vì sao `ApplicationRunner` thuận tiện hơn `CommandLineRunner` cho việc đọc tên và danh sách giá trị?
13. Khi nào nên dùng `@ConfigurationProperties` thay vì trực tiếp đọc `ApplicationArguments`?
14. Viết thông báo lỗi có thể hành động được khi người dùng truyền `--region=` hoặc `--region` mà app yêu cầu mã region không rỗng.
15. Vì sao không nên in mọi giá trị `getSourceArgs()` trong production log?
16. Hãy viết test để phân biệt `--region=apac,eu` và `--region=apac --region=eu` mà không dựa vào cách format list.
17. Xem lại lệnh `java -Dapp.mode=demo -jar app.jar --mode=import`: token nào do JVM xử lý, token nào thuộc application arguments?
18. Với một cú pháp CLI mới cần short options, positional groups và subcommands phức tạp, vì sao có thể cần thư viện CLI parser chuyên dụng thay vì lạm dụng `ApplicationArguments`?

**Tiêu chí đạt:** viết được mã dùng chính xác `getOptionNames`, `containsOption`, `getOptionValues`, kiểm tra được ba trạng thái **null / empty list / list chứa chuỗi rỗng**, lấy được nhiều giá trị khi lặp `--name=value`, giải thích đúng output chương trình và biết chuyển sang typed configuration khi phù hợp.

## 13. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — `ApplicationArguments` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Boot 3.3 — `DefaultApplicationArguments` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/DefaultApplicationArguments.html
- Spring Boot 3.3 — SpringApplication, runners và command-line access: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework 6.1 — `SimpleCommandLinePropertySource` và option syntax: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/env/SimpleCommandLinePropertySource.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
