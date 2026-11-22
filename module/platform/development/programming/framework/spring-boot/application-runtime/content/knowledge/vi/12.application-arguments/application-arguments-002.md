# Phân biệt đối số tùy chọn với đối số không có tên trong Spring Boot

## Mục tiêu học tập

Khi gọi `SpringApplication.run(args)`, ứng dụng nhận danh sách đối số dòng lệnh. Spring Boot cho phép đọc hai nhóm khác nhau: **option arguments** (đối số tùy chọn có tên) và **non-option arguments** (đối số không có tên, thường còn gọi là *positional arguments*). Phân biệt đúng hai nhóm giúp xây dựng CLI/batch job, kiểm tra tham số đầu vào, định tuyến tác vụ và tránh lỗi cấu hình.

Sau bài này, bạn có thể:

1. Nhận diện cú pháp option Spring Boot `--name` và `--name=value` so với các phần tử không có tiền tố `--`.
2. Dùng `ApplicationArguments` đọc `getOptionNames()`, `containsOption()`, `getOptionValues()`, `getNonOptionArgs()` và `getSourceArgs()`.
3. Phân biệt **option không tồn tại**, **cờ option không có giá trị** và **option có giá trị là chuỗi rỗng**.
4. Giải thích vì sao `--mode=import` khác `--mode import`, và vì sao `-v` không phải option `--v` trong parser mặc định.
5. Hiểu mối quan hệ giữa `ApplicationArguments`, `CommandLineRunner`, `ApplicationRunner` và `Environment`.
6. Chạy được ví dụ **Java 17+ / Spring Boot 3.3.13 / Gradle** minh họa cả cách đọc có cấu trúc lẫn raw arguments, với output rõ ràng.
7. Thiết kế validation an toàn cho positional arguments, cờ boolean, đường dẫn, số nguyên và input có thể chứa thông tin nhạy cảm.

**Ngữ cảnh:** Spring Boot Application Runtime → Đối số ứng dụng. Bài tập trung vào **phân loại đối số dòng lệnh** và cách ứng dụng sử dụng hai nhóm đối số, không thay thế một tài liệu đầy đủ về Spring Boot configuration binding hoặc các thư viện CLI chuyên dụng.

## 1. Hai nhóm đối số khác nhau ở đâu?

Giả sử người dùng chạy một chương trình import:

~~~bash
java -jar app.jar --mode=import --dry-run customers.csv archive.csv
~~~

Ở đây:

- `--mode=import` là **option có tên** `mode` và giá trị `import`.
- `--dry-run` là **option có tên** `dry-run` nhưng không đi kèm giá trị (một *flag*).
- `customers.csv` và `archive.csv` là hai **non-option arguments**, không có key/name; chương trình có thể quy ước chúng lần lượt là file đầu vào và file đầu ra.
- `java`, `-jar` và `app.jar` thuộc cú pháp gọi JVM, **không** phải ba phần tử mà `ApplicationArguments` nhận khi ứng dụng chạy từ JAR.

Từ góc nhìn của phương thức `main(String[] args)`, bốn phần tử đi vào mảng là:

~~~text
[--mode=import, --dry-run, customers.csv, archive.csv]
~~~

Spring Boot phân loại chính các phần tử đó, không “đọc nguyên văn câu lệnh shell” và cũng không tự hiểu `customers.csv` là file hợp lệ. Ý nghĩa file thứ nhất/file thứ hai do **ứng dụng** định nghĩa.

### Bảng so sánh

| Tiêu chí | Option argument | Non-option argument |
| --- | --- | --- |
| Cách viết với parser mặc định | `--name` hoặc `--name=value` | Không có tiền tố option `--name` |
| Ví dụ | `--mode=import`, `--dry-run` | `customers.csv`, `archive.csv`, `-v` |
| Có tên để lookup? | Có: `mode` hoặc `dry-run` | Không: thường dùng vị trí trong danh sách |
| API đọc chính | `containsOption("mode")`, `getOptionValues("mode")` | `getNonOptionArgs()` |
| Có lưu thứ tự? | Danh sách tên là `Set`, không dùng nó để suy ra thứ tự ban đầu | Danh sách positional giữ thứ tự sau khi parser xử lý |
| Có thể có nhiều phần tử? | Có nhiều tên option; hỗ trợ lặp cùng tên phụ thuộc parser/phiên bản | Có nhiều positional arguments |
| Có tự chuyển thành kiểu Java? | Không: phải parse/validate giá trị | Không: phải parse/validate từng phần tử |
| Có thể ảnh hưởng Spring Environment? | Theo mặc định, các option command-line được thêm vào `Environment` | Không tự trở thành property có tên theo cùng quy tắc |

**Quan trọng:** “Tùy chọn” ở đây là tên loại **cú pháp** (*option*), không có nghĩa tham số đó được phép thiếu về mặt nghiệp vụ. Ứng dụng có thể yêu cầu bắt buộc phải có `--mode=...` dù cú pháp của nó là *option argument*.

## 2. Cú pháp option của Spring Boot

Spring Boot dùng cơ chế phân tích đối số dòng lệnh đơn giản của Spring Framework. Với các phiên bản trong phạm vi bài học, dạng option chuẩn là:

~~~text
--optionName[=optionValue]
~~~

Dấu ngoặc vuông trong sơ đồ chỉ diễn đạt phần **có thể có**, không phải ký tự phải gõ vào terminal.

Các dạng phổ biến:

| Đầu vào | Phân loại | Ý nghĩa |
| --- | --- | --- |
| `--debug` | Option tên `debug` | Có tên nhưng không có giá trị |
| `--mode=import` | Option tên `mode` | Một giá trị `import` |
| `--port=8080` | Option tên `port` | Một chuỗi giá trị `8080`, chưa tự thành `int` |
| `--empty=` | Option tên `empty` | Một giá trị có độ dài 0 (chuỗi rỗng) |
| `--name=Lan` | Option tên `name` | Một giá trị `Lan` |
| `--name="Lan Anh"` | Option (nếu shell truyền thành một token) | Một giá trị có dấu cách `Lan Anh` |
| `input.csv` | Non-option | Một phần tử vị trí |
| `-v` | Non-option với parser mặc định này | Không được hiểu là short option của `--verbose` |
| `2026` | Non-option | Chuỗi `2026`, có thể parse thành năm |
| `-12` | Non-option | Chuỗi `-12`, cần parse nếu dùng làm số âm |

### Tên option không có tiền tố khi gọi API

Dù token gốc có `--`, code truy vấn chỉ dùng **tên**:

~~~java
boolean hasDebug = args.containsOption("debug");
List<String> modes = args.getOptionValues("mode");
~~~

Không dùng `containsOption("--debug")` hoặc `getOptionValues("--mode")` để tìm token được viết với tiền tố. API đã tách `--` khỏi tên option khi phân loại.

### Dấu bằng là ranh giới name/value

`--mode=import` là **một phần tử mảng `String[]`**. Parser tách tại dấu `=` đầu tiên sau tên. Nếu value chứa dấu bằng, ví dụ `--token=a=b`, phần value là `a=b`.

Ngược lại, hai token:

~~~text
--mode import
~~~

không được parser mặc định đọc như một cặp key/value bằng cú pháp không dấu bằng. Kết quả về mặt nhóm:

- `--mode`: một option hiện diện **không có giá trị gắn trực tiếp**.
- `import`: một non-option argument.

Đây là một trong những lỗi phổ biến nhất khi chuyển từ thư viện CLI khác sang `ApplicationArguments`.

### Dấu gạch đơn khác dấu gạch kép

Trong các CLI framework khác, `-v` thường là viết tắt của `--verbose`. Tuy nhiên parser mặc định của `ApplicationArguments` tập trung vào tiền tố `--`; một token `-v` vẫn có thể xuất hiện trong `getNonOptionArgs()`. **Không áp dụng ngầm quy tắc short option** của GNU getopt, picocli hoặc Apache Commons CLI.

Nếu muốn hỗ trợ `-v` như một option thực sự, ứng dụng phải tự xây quy tắc hoặc dùng một CLI parser thích hợp.

## 3. ApplicationArguments: giao diện đọc hai nhóm đối số

Spring Boot cung cấp `org.springframework.boot.ApplicationArguments`, được tạo từ những arguments truyền vào `SpringApplication.run(...)` và có thể inject vào một bean/runner.

Các phương thức:

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `getSourceArgs()` | `String[]` | Mảng token gốc, chưa phân loại |
| `getOptionNames()` | `Set<String>` | Tên các option đã nhận diện |
| `containsOption(String name)` | `boolean` | Có option với tên này hay không |
| `getOptionValues(String name)` | `List<String>` hoặc `null` | Các giá trị gắn với tên option |
| `getNonOptionArgs()` | `List<String>` | Danh sách positional/non-option sau parse |

Ví dụ một runner:

~~~java
@Component
public class InputReporter implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(args.getOptionNames());
        System.out.println(args.getNonOptionArgs());
    }
}
~~~

Đây là **đoạn minh họa**, cần các import `ApplicationRunner`, `ApplicationArguments`, `Component` và một Spring Boot project. `ApplicationRunner` là một bean callback được Boot gọi sau khi context refresh, trước `ApplicationReadyEvent`. Bài sẽ có project đầy đủ ở mục 7.

### Tại sao cần cả getSourceArgs và getNonOptionArgs?

Giả sử source args có thứ tự:

~~~text
[input.csv, --mode=import, output.csv, --dry-run]
~~~

`getSourceArgs()` giữ cả bốn token theo thứ tự gốc, trong khi `getNonOptionArgs()` chỉ chứa:

~~~text
[input.csv, output.csv]
~~~

Nếu muốn tìm hai vị trí file, hãy dùng `getNonOptionArgs()` và validate số lượng phần tử. Nếu muốn log **đầy đủ tokens** để chẩn đoán, `getSourceArgs()` hữu ích nhưng cần lọc bí mật trước khi log.

Một chương trình không nên tự suy ra “phần tử thứ ba của raw args luôn là file output” vì vị trí option có thể thay đổi và làm lệch chỉ số. Sau parse, positional list rõ nghĩa hơn.

## 4. Ba trạng thái getOptionValues dễ bị nhầm

Đây là phần quan trọng nhất khi dùng option argument.

Giả sử một chương trình nhận một trong các trường hợp:

~~~text
Trường hợp A: không có --dry-run
Trường hợp B: --dry-run
Trường hợp C: --dry-run=
Trường hợp D: --dry-run=false
~~~

Theo hợp đồng API:

| Trường hợp | `containsOption("dry-run")` | `getOptionValues("dry-run")` | Số phần tử |
| --- | --- | --- | --- |
| A: vắng mặt | `false` | `null` | Không có danh sách |
| B: cờ không giá trị | `true` | Danh sách rỗng `[]` | 0 |
| C: có một chuỗi rỗng | `true` | Danh sách chứa `""` | 1 |
| D: giá trị `false` | `true` | Danh sách chứa `"false"` | 1 |

**Bẫy khi in Java:** `List.of("").toString()` cũng tạo biểu diễn `[]`, rất dễ nhầm với một danh sách có 0 phần tử. Vì thế khi cần phân biệt `--flag` và `--flag=`, hãy **kiểm tra size và nội dung chuỗi**, không chỉ nhìn log `List.toString()`.

Hàm minh họa (đặt trong class phù hợp) để báo cáo chính xác:

~~~java
private static String describeOption(
        ApplicationArguments args, String name) {

    List<String> values = args.getOptionValues(name);

    if (values == null) {
        return "absent";
    }
    if (values.isEmpty()) {
        return "present, 0 values";
    }
    return "present, " + values.size()
            + " value(s); firstLength=" + values.get(0).length();
}
~~~

Đoạn này cần import `java.util.List` và `org.springframework.boot.ApplicationArguments`. Ví dụ hoàn chỉnh dùng đúng hàm này.

### Flag không tự chuyển thành boolean

Đối với `--dry-run`:

~~~java
boolean dryRun = args.containsOption("dry-run");
~~~

Điều này diễn giải **sự hiện diện** của flag. Nhưng với `--dry-run=false`, biểu thức trên **vẫn là true** vì option có mặt, chỉ khác giá trị.

Nếu ứng dụng chấp nhận cả `--dry-run`, `--dry-run=true` và `--dry-run=false`, nên có parser rõ ràng:

~~~java
private static boolean readBooleanFlag(
        ApplicationArguments args, String name) {

    List<String> values = args.getOptionValues(name);
    if (values == null) {
        return false;
    }
    if (values.isEmpty()) {
        return true;
    }
    if (values.size() != 1) {
        throw new IllegalArgumentException(
                "Expected at most one value for --" + name);
    }
    if ("true".equalsIgnoreCase(values.get(0))) {
        return true;
    }
    if ("false".equalsIgnoreCase(values.get(0))) {
        return false;
    }
    throw new IllegalArgumentException(
            "Expected --" + name + "=true or =false");
}
~~~

Đây là **mã minh họa**, không phải một class Java độc lập; cần các imports đã nêu và context gọi tương ứng. Hàm này xác định rõ chính sách: flag không có giá trị nghĩa là `true`, còn `--flag=` bị từ chối. Trong hệ thống thực tế, chính sách có thể khác nhưng phải nhất quán, có test và thông báo lỗi rõ.

## 5. Đối số không có tên là positional, không phải “không cần thiết”

Non-option arguments là chuỗi không được parser xem là option có tên. Thường gặp:

~~~bash
java -jar importer.jar --mode=import customers.csv archive.csv
~~~

Ứng dụng quy định:

- `getNonOptionArgs().get(0)` là đường dẫn file đầu vào;
- `getNonOptionArgs().get(1)` là đường dẫn file đầu ra;
- `--mode=import` là một option điều khiển cách chạy.

Tuy nhiên parser **không biết** hai file đó có tồn tại, thứ tự có hợp lệ hay có quyền truy cập hay không. Cần validate:

~~~java
List<String> files = args.getNonOptionArgs();

if (files.size() != 2) {
    throw new IllegalArgumentException(
            "Expected input and output file arguments");
}

Path input = Path.of(files.get(0));
Path output = Path.of(files.get(1));
~~~

Đây là đoạn minh họa, cần import `List`, `Path` và có biến `args` kiểu `ApplicationArguments`. Việc dựng `Path` chưa đủ để đảm bảo file có thể đọc/ghi; cần kiểm tra/handle I/O và đường dẫn an toàn khi thật sự dùng.

### Không dựa vào chỉ số raw token để tìm positional

Với cả hai cách gọi:

~~~text
--mode=import customers.csv archive.csv
customers.csv --mode=import archive.csv
~~~

`getNonOptionArgs()` đều cho ra một danh sách hai phần tử có nội dung file đầu vào/đầu ra theo thứ tự của **các non-option**. Ngược lại, `getSourceArgs()[0]` trong ví dụ đầu là option, nhưng trong ví dụ thứ hai là file đầu vào.

**Quy tắc thiết kế:** Đối với một CLI command, hãy tách rõ các option điều khiển (*mode*, *verbose*, *timeout*) khỏi các positional operands (*input*, *output*, *jobId*).

### Những token dễ bị hiểu nhầm

- `-n` không phải `--name` theo cú pháp parser đơn giản; không hứa nó được xử lý như một short option.
- `-5` là một non-option dạng chuỗi số âm trong bối cảnh parser này.
- `=abc` vẫn có thể là non-option; parser chỉ nhận option với đúng tiền tố `--`.
- `--name=value` là option có tên; một đường dẫn hoặc filename **bắt đầu bằng `--`** có thể bị phân loại thành option, nên cần quy ước rõ cách truyền. Đừng dựa vào hành vi parser POSIX của công cụ khác khi không kiểm thử phiên bản đang dùng.
- `--tag=a,b` chứa một giá trị chuỗi `a,b`; Spring không tự biến dấu phẩy thành hai phần tử của `getOptionValues("tag")`. Nếu nghiệp vụ muốn danh sách, hãy định nghĩa bước tách và quy tắc escape riêng.

## 6. Parser mặc định không phải một CLI framework đầy đủ

Spring Boot cung cấp cơ chế đủ dùng cho các nhu cầu ứng dụng phổ biến, nhưng đừng nhầm nó với một CLI parser chuyên dụng.

### Không có full schema validation tự động

`ApplicationArguments` không biết một option `--mode` chỉ được nhận `import` hoặc `validate`; nó không tự chuyển `--port=8080` thành `int` và không tự báo lỗi khi thiếu positional operand mà nghiệp vụ yêu cầu.

### Không mặc định hỗ trợ các cú pháp của công cụ khác

Những công cụ CLI khác có thể chấp nhận `-v`, `-o file`, nhóm short flags `-abc`, subcommand lồng nhau, dấu kết thúc option `--` hoặc dấu cách giữa key/value. **Đừng suy luận mọi cú pháp đó có cùng semantics trong Spring Boot 3.3**.

Với Spring Framework 6.1 thuộc phạm vi bài, tài liệu `SimpleCommandLinePropertySource` nêu dạng `--name[=value]`, không đưa ra một hợp đồng parser tổng quát như POSIX getopt. Nếu cần nhiều subcommand, tùy chọn bắt buộc, help sinh tự động, shell completion hoặc hỗ trợ short options, cân nhắc một CLI library chuyên dụng như picocli (với tích hợp được thiết kế riêng), thay vì tự ghép chuỗi ở nhiều nơi.

### Lặp lại cùng tên option là trường hợp phụ thuộc parser/phiên bản

`ApplicationArguments.getOptionValues(name)` có kiểu trả về danh sách và mô tả nhiều giá trị khi parser nền hỗ trợ. Nhưng **không được coi điều đó là bằng chứng** rằng mọi bản `SimpleCommandLineArgsParser` chấp nhận lặp `--tag=alpha --tag=beta`. Tài liệu Spring Framework 6.1 còn liệt kê cách lặp cùng option trong các ví dụ không hợp lệ, trong khi các bản mới có thay đổi.

Vì vậy ví dụ runnable trong bài dùng:

~~~text
--tag=alpha,beta
~~~

như **một option chứa đúng một string `alpha,beta`**. Khi cần hỗ trợ danh sách, hãy tách chuỗi có quy tắc rõ hoặc dùng một parser/phiên bản đã xác nhận hỗ trợ repeated options. Không viết test dựa vào một hành vi khác với dependency Spring Framework thực tế.

## 7. Ví dụ hoàn chỉnh: quan sát option và non-option trên Spring Boot

Ví dụ dùng **Java 17+**, **Spring Boot 3.3.13** và Gradle. Chạy non-web, không cần database. Có hai runner:

- `StructuredArgumentsRunner implements ApplicationRunner`: đọc các nhóm từ `ApplicationArguments`.
- `RawArgumentsRunner implements CommandLineRunner`: in lại mảng chuỗi được truyền nguyên dạng để đối chiếu.

Hai runner được sắp thứ tự bằng `@Order` để dòng output không phụ thuộc thứ tự component scanning.

### 7.1. Cấu trúc file

~~~text
application-arguments-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/args/
    ├── ArgumentsDemoApplication.java
    ├── StructuredArgumentsRunner.java
    └── RawArgumentsRunner.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'application-arguments-demo'
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
    mainClass = 'com.example.args.ArgumentsDemoApplication'
}
~~~

Sử dụng Gradle tương thích với Spring Boot 3.3 và JDK 17+. Tài nguyên được tải từ Maven Central nếu chưa cache sẵn. Không cần `spring-boot-starter-web` vì bài chỉ quan sát đối số và runner.

### 7.2. Main: truyền args cho SpringApplication

**`src/main/java/com/example/args/ArgumentsDemoApplication.java`:**

~~~java
package com.example.args;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ArgumentsDemoApplication {

    public static void main(String[] args) {

        SpringApplication application =
                new SpringApplication(ArgumentsDemoApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            System.out.println("MAIN: run returned");
        }

        System.out.println("MAIN: context closed");
    }
}
~~~

`SpringApplication.run(args)` là điểm Spring Boot nhận mảng string. Sau khi context refresh, Boot gọi các runner. `WebApplicationType.NONE` bảo đảm ví dụ không mở HTTP server. Khối `try-with-resources` đóng context sau khi runners hoàn tất; đây là **ứng dụng CLI minh họa**, không phải mẫu cho web server cần chạy lâu dài.

### 7.3. ApplicationRunner: đọc nhóm option/non-option

**`src/main/java/com/example/args/StructuredArgumentsRunner.java`:**

~~~java
package com.example.args;

import java.util.List;
import java.util.TreeSet;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public final class StructuredArgumentsRunner
        implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {

        System.out.println("APP: options="
                + new TreeSet<>(args.getOptionNames()));

        System.out.println("APP: mode="
                + args.getOptionValues("mode"));

        System.out.println("APP: tag="
                + args.getOptionValues("tag"));

        System.out.println("APP: hasDryRun="
                + args.containsOption("dry-run"));

        System.out.println("APP: dryRun="
                + describeOption(args, "dry-run"));

        System.out.println("APP: empty="
                + describeOption(args, "empty"));

        System.out.println("APP: missing="
                + describeOption(args, "missing"));

        System.out.println("APP: nonOptions="
                + args.getNonOptionArgs());
    }

    private static String describeOption(
            ApplicationArguments args, String name) {

        List<String> values = args.getOptionValues(name);

        if (values == null) {
            return "absent";
        }
        if (values.isEmpty()) {
            return "present, 0 values";
        }
        return "present, " + values.size()
                + " value(s); firstLength="
                + values.get(0).length();
    }
}
~~~

Tại đây:

- `new TreeSet<>(...)` chỉ dùng để **sắp xếp tên option khi in**, tránh suy ra thứ tự từ `Set`. Nó không thay đổi arguments gốc.
- `getOptionValues("tag")` trả về danh sách chứa một string `alpha,beta` trong lệnh ở mục tiếp theo.
- `describeOption(...)` tách ba trường hợp: vắng mặt, cờ không value, có một hoặc nhiều value; nó phân biệt chính xác `--dry-run` và `--empty=`.
- `getNonOptionArgs()` trả về danh sách các token không phải option, giữ thứ tự xuất hiện của chúng trong đầu vào.
- `@Order(10)` giúp runner này chạy trước `RawArgumentsRunner` có `@Order(20)`.

### 7.4. CommandLineRunner: quan sát toàn bộ raw args

**`src/main/java/com/example/args/RawArgumentsRunner.java`:**

~~~java
package com.example.args;

import java.util.Arrays;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public final class RawArgumentsRunner
        implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("CMD: raw="
                + Arrays.toString(args));
    }
}
~~~

`CommandLineRunner` nhận mảng raw, không cung cấp API phân loại option/non-option. Hai interface runner chạy **cùng giai đoạn startup**; thứ tự trong ví dụ đến từ `@Order`, không phải vì `ApplicationRunner` luôn chạy trước `CommandLineRunner`.

### 7.5. Chạy với cả hai loại đối số

Từ thư mục `application-arguments-demo`, dùng Gradle:

~~~bash
gradle bootRun --args="--mode=import --tag=alpha,beta input.csv --dry-run -v --empty="
~~~

Nếu project có Gradle Wrapper, dùng `./gradlew bootRun --args="..."` trên Linux/macOS hoặc `.\gradlew.bat bootRun --args="..."` trên Windows. Ví dụ project không tự tạo wrapper, nên cần Gradle đã cài hoặc bổ sung wrapper bằng công cụ dự án.

Trong lệnh này, các **application arguments** thực sự là:

~~~text
--mode=import
--tag=alpha,beta
input.csv
--dry-run
-v
--empty=
~~~

Tất cả token trên được truyền tới `main(String[] args)`; `--args=...` bên ngoài thuộc cú pháp của Gradle `bootRun`, không phải là một option mà `ApplicationArguments` của ứng dụng nhìn thấy.

### 7.6. Output dự kiến

Bỏ qua các dòng log khác của Gradle/Spring Boot, những dòng do ba Java class của demo tự in là:

~~~text
APP: options=[dry-run, empty, mode, tag]
APP: mode=[import]
APP: tag=[alpha,beta]
APP: hasDryRun=true
APP: dryRun=present, 0 values
APP: empty=present, 1 value(s); firstLength=0
APP: missing=absent
APP: nonOptions=[input.csv, -v]
CMD: raw=[--mode=import, --tag=alpha,beta, input.csv, --dry-run, -v, --empty=]
MAIN: run returned
MAIN: context closed
~~~

Đọc từng dòng:

1. `APP: options` chứa **tên option không có `--`**, được `TreeSet` sắp xếp.
2. `APP: mode=[import]` minh họa một option với một giá trị.
3. `APP: tag=[alpha,beta]` chứa **một** phần tử string `alpha,beta`, không phải hai giá trị riêng: nếu cần, phải tự parse dấu phẩy.
4. `APP: hasDryRun=true` khẳng định cờ có mặt.
5. `APP: dryRun=present, 0 values` khẳng định cờ `--dry-run` **không có giá trị**.
6. `APP: empty=present, 1 value(s); firstLength=0` khẳng định `--empty=` là **một chuỗi rỗng**.
7. `APP: missing=absent` cho biết `getOptionValues("missing")` trả `null`.
8. `APP: nonOptions=[input.csv, -v]` cho biết parser mặc định không coi `-v` là option hai dấu gạch.
9. `CMD: raw` giữ **toàn bộ** sáu token theo thứ tự.
10. `MAIN: run returned` và `MAIN: context closed` cho thấy đây là chương trình CLI tự kết thúc bình thường.

**Lưu ý khi đối chiếu:** Các bản Gradle/plugin hoặc môi trường có thể in thêm dòng hệ thống. Vì output được dựng từ mã ứng dụng, hãy so khớp *các dòng có tiền tố `APP`, `CMD` và `MAIN`* thay vì mọi dòng trên console.

## 8. Thí nghiệm đối chiếu các trường hợp biên

Chạy lại mỗi ví dụ với cùng project; nếu muốn giữ output ngắn, chỉ quan sát hai dòng `mode` và `nonOptions` cùng các dòng phân loại liên quan.

### 8.1. Có dấu bằng và không có dấu bằng

**Lệnh A:**

~~~bash
gradle bootRun --args="--mode=import input.csv"
~~~

Trong chương trình:

~~~text
APP: mode=[import]
APP: nonOptions=[input.csv]
~~~

**Lệnh B:**

~~~bash
gradle bootRun --args="--mode import input.csv"
~~~

Với parser mặc định, các phần liên quan thành:

~~~text
APP: mode=[]
APP: nonOptions=[import, input.csv]
~~~

Dòng `APP: mode=[]` ở lệnh B có nghĩa **danh sách không có giá trị** vì `--mode` là cờ. Không phải `mode` đã chứa chuỗi rỗng hoặc chữ `import`.

### 8.2. Option vắng mặt và option rỗng

So sánh:

~~~text
Cách 1: input.csv
Cách 2: --empty input.csv
Cách 3: --empty= input.csv
~~~

Với `getOptionValues("empty")`:

- Cách 1: `null`.
- Cách 2: một danh sách có **0** phần tử.
- Cách 3: một danh sách có **1** phần tử, phần tử đó là `""` có length 0.

Nếu chỉ in `List.toString()`, cách 2 và 3 đều có thể xuất hiện như `[]`. Đây là lý do project ví dụ in số lượng phần tử.

### 8.3. Chuỗi chứa dấu cách

Với một shell hỗ trợ quoting như ví dụ:

~~~bash
gradle bootRun --args="--name='Lan Anh' input.csv"
~~~

Cách shell/Gradle xử lý dấu nháy có thể khác theo môi trường; đừng khẳng định mọi terminal giữ nguyên một kiểu quoting. Điều cốt lõi là: nếu `main` nhận **một** token `--name=Lan Anh` (có dấu cách bên trong), parser coi toàn bộ phần sau dấu bằng là **một giá trị string**, không tự tách thành hai non-option.

Trong môi trường production, kiểm tra `getSourceArgs()` hoặc dùng một test tạo trực tiếp `DefaultApplicationArguments` để xác nhận chính xác tokens, thay vì tranh luận về chuỗi dấu nháy hiển thị trong shell.

### 8.4. Dấu phẩy không tự chia option values

~~~text
--tag=a,b,c
~~~

Đây là một token có value `a,b,c`. Nếu muốn tạo danh sách:

~~~java
List<String> tags = Arrays.stream(value.split(","))
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .toList();
~~~

Đoạn này là **minh họa**, yêu cầu biến `value` kiểu `String` và import `java.util.Arrays`. Chính ứng dụng quyết định có cho phép item trống, dấu phẩy trong dữ liệu, escape, hay quote hay không. Nếu đầu vào có format phức tạp, nên dùng CSV parser hoặc CLI framework phù hợp thay vì chỉ `split(",")`.

### 8.5. Số âm và short flag

~~~text
--limit=10 -5 -v
~~~

- `--limit=10` là option có một value `10`.
- `-5` và `-v` là non-option với parser này.
- `getNonOptionArgs()` là `[-5, -v]`.
- `getOptionValues("limit")` chứa string `"10"`, chưa tự biến thành số nguyên.

Nếu muốn đưa số âm vào một option có tên, dùng:

~~~text
--offset=-5
~~~

Khi đó option `offset` có value `"-5"`; bạn có thể gọi `Integer.parseInt` trong bước validation.

## 9. ApplicationArguments và Environment không phải một thứ

Một số option command-line còn tham gia Spring Boot configuration:

~~~bash
java -jar app.jar --server.port=9090 --spring.profiles.active=dev
~~~

Theo mặc định, Spring Boot đưa các **command-line options có tên** vào `Environment` dưới dạng một property source, với độ ưu tiên cấu hình được framework quy định. Do đó `--server.port=9090` có thể quyết định cổng server và `--spring.profiles.active=dev` có thể tham gia cấu hình profiles khi chạy đúng trong quá trình bootstrap.

Nhưng:

- `ApplicationArguments` là **mô hình parser cho argv**.
- `Environment` là **hệ thống giải quyết property** từ command line, environment variables, system properties, Config Data và các nguồn khác.
- `getNonOptionArgs()` trả danh sách positional operands; không tạo property tương ứng kiểu `server.port` chỉ bằng việc đặt token không có tên.
- `@ConfigurationProperties` là lựa chọn để bind configuration phức tạp, validate type và default; nó không thay thế positional parsing khi CLI cần operands theo thứ tự.

### Có thể tắt command-line property source mà vẫn đọc args

Spring Boot cho phép gọi trước `run`:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

Đây là **đoạn minh họa**, giả sử có lớp `MyApplication`. Thiết lập này loại việc thêm command-line option vào `Environment` theo cơ chế mặc định, nhưng không làm mảng `args` truyền vào `run` biến mất; `ApplicationArguments` vẫn có thể phân loại chúng.

Điều này hữu ích nếu muốn CLI arguments chỉ là dữ liệu nghiệp vụ và không vô tình override cấu hình hệ thống. Ngược lại, nếu triển khai của bạn chủ động dùng `--spring...` để cấu hình môi trường, hãy hiểu tác động của việc tắt property source trước khi sử dụng.

### Không đồng nhất option với Spring property

Một option tên `--mode=import` **có thể** xuất hiện trong command-line property source, nhưng ứng dụng chưa chắc đã định nghĩa một property `mode` hợp lệ. Cũng không phải mọi property trong `Environment` đều đến từ command line. Để biết một thông số đã được thiết lập từ đâu, cần xem các property source/Actuator `env` khi được bật và kiểm soát quyền truy cập dữ liệu nhạy cảm.

## 10. ApplicationRunner và CommandLineRunner xử lý args thế nào?

| Interface | Tham số callback | Điểm mạnh |
| --- | --- | --- |
| `ApplicationRunner` | `run(ApplicationArguments args)` | Trực tiếp đọc option/non-option, tránh tự viết parser |
| `CommandLineRunner` | `run(String... args)` | Nhận mảng raw; phù hợp công cụ muốn tự parse hoặc forwarding |

Cả hai đều là **Spring bean callback**, Spring Boot gọi sau khi application context refresh và trước mốc `ApplicationReadyEvent`. Thứ tự giữa hai loại không được quyết định bởi tên interface; ví dụ mục 7 dùng `@Order(10)`/`@Order(20)`.

Nếu một runner sử dụng đối số không hợp lệ và ném `IllegalArgumentException`, Spring Boot thường coi đó là lỗi trong startup, không chuyển tiếp đến ready thành công. Vì vậy hãy đưa validation cần thiết vào runner và ghi error message ngắn, rõ, không tiết lộ secret.

**Không nhầm với request parameters.** Trong Spring MVC/WebFlux, `@RequestParam` phân tích query parameter của **mỗi HTTP request**, hoàn toàn khác arguments truyền lúc process khởi động. `--mode=import` chỉ xuất hiện khi startup, không xuất hiện lại mỗi lần người dùng gọi URL.

## 11. Validation đầu vào theo hợp đồng CLI

Đừng chỉ dựa vào cú pháp parser. Hãy định nghĩa hợp đồng nghiệp vụ cho từng command.

Ví dụ command:

~~~text
importer [--mode=import|validate] [--dry-run] INPUT_FILE [OUTPUT_FILE]
~~~

Ở đây dấu ngoặc trong dòng trên biểu diễn **cú pháp mô tả CLI**, không phải các ký tự truyền vào `main`. Hợp đồng có thể là:

- `--mode` bắt buộc, có đúng một value thuộc tập `import` hoặc `validate`.
- `--dry-run` tùy chọn, nếu không có value thì được hiểu là bật.
- `INPUT_FILE` là positional operand bắt buộc.
- `OUTPUT_FILE` chỉ được phép trong mode `import`; nếu mode `validate` phải vắng mặt.
- Mọi option không thuộc danh sách cho phép sẽ bị từ chối để bắt lỗi gõ sai.

Ví dụ đoạn kiểm tra mode:

~~~java
List<String> modes = args.getOptionValues("mode");

if (modes == null || modes.size() != 1
        || modes.get(0).isBlank()) {
    throw new IllegalArgumentException(
            "Expected exactly one --mode=import|validate");
}

String mode = modes.get(0);

if (!mode.equals("import") && !mode.equals("validate")) {
    throw new IllegalArgumentException(
            "Unsupported mode: " + mode);
}
~~~

Đây là **đoạn minh họa trong `ApplicationRunner`**, cần `java.util.List` và biến `args` kiểu `ApplicationArguments`. Không đưa đoạn validation này vào project ví dụ mục 7 nếu muốn giữ stdout của phần demo đọc phân loại.

### Kiểm tra positional arguments

~~~java
List<String> files = args.getNonOptionArgs();

if (files.isEmpty() || files.size() > 2) {
    throw new IllegalArgumentException(
            "Expected INPUT_FILE and optional OUTPUT_FILE");
}
~~~

Nếu file đường dẫn cần có thật, hãy xử lý `Path.of(...)`, `Files.isRegularFile(...)` và ngoại lệ I/O phù hợp, không coi chỉ số có trong list là file chắc chắn an toàn. Đặc biệt, nếu ứng dụng chạy với quyền ghi rộng, cần xem xét path traversal và hạn chế nơi đọc/ghi.

### Kiểm tra option lạ

~~~java
Set<String> supported =
        Set.of("mode", "dry-run", "timeout");

for (String optionName : args.getOptionNames()) {
    if (!supported.contains(optionName)) {
        throw new IllegalArgumentException(
                "Unknown option: --" + optionName);
    }
}
~~~

Đoạn này cần import `java.util.Set` và biến `args` kiểu `ApplicationArguments`. Trong ứng dụng Spring Boot thực tế, nhiều option tên `spring.*` có thể được dùng cho cấu hình framework. **Không tự cấm toàn bộ option lạ một cách mù quáng** nếu ứng dụng cần hỗ trợ những option chuẩn của Boot hoặc thư viện. Hãy quyết định policy CLI rõ ràng và phù hợp với cách cấu hình đang triển khai.

### Thông tin nhạy cảm

Không ghi toàn bộ `getSourceArgs()` ra log ở production nếu arguments có thể chứa token, mật khẩu, khóa API, DSN chứa credential hoặc đường dẫn nhạy cảm. Arguments có thể bị nhìn thấy qua process list, shell history, CI logs và telemetry. Sử dụng secret manager, mounted secret hoặc cơ chế phù hợp của nền tảng; trong logs chỉ nên in những tên option cần chẩn đoán và đã được lọc.

## 12. Kiểm thử parser không cần khởi động toàn bộ ứng dụng

Nếu chỉ muốn kiểm tra cú pháp và cách phân loại, có thể khởi tạo `DefaultApplicationArguments` trực tiếp trong một test Java thay vì chờ Spring Boot startup.

Ví dụ phần thân của một bài test:

~~~java
ApplicationArguments parsed = new DefaultApplicationArguments(
        "--mode=import",
        "input.csv",
        "--dry-run",
        "--empty=");

System.out.println(parsed.containsOption("mode"));       // true
System.out.println(parsed.getOptionValues("mode"));       // [import]
System.out.println(parsed.getNonOptionArgs());            // [input.csv]
System.out.println(parsed.getOptionValues("dry-run").size()); // 0
System.out.println(parsed.getOptionValues("empty").size());   // 1
~~~

Đây là **đoạn minh họa**, cần import `org.springframework.boot.ApplicationArguments` và `org.springframework.boot.DefaultApplicationArguments`. Chú thích ở cuối dòng mô tả giá trị kết quả, không phải output được biên dịch sinh tự động. Đặt mã trong một phương thức Java có thể chạy trong project Spring Boot đã có dependencies.

Nếu muốn kiểm tra phân loại với dữ liệu thay đổi, nên sử dụng JUnit:

~~~java
@Test
void bareFlagAndEmptyValueAreDifferent() {
    ApplicationArguments parsed =
            new DefaultApplicationArguments(
                    "--dry-run", "--empty=");

    assertTrue(parsed.containsOption("dry-run"));
    assertEquals(0, parsed.getOptionValues("dry-run").size());
    assertEquals(1, parsed.getOptionValues("empty").size());
    assertEquals("", parsed.getOptionValues("empty").get(0));
    assertNull(parsed.getOptionValues("missing"));
}
~~~

Đây là **đoạn test minh họa**, không phải file JUnit độc lập. Cần `spring-boot-starter-test` (test scope), cấu hình `useJUnitPlatform()` của Gradle và imports JUnit Jupiter `@Test`/assertions. Điểm chính là test phải phân biệt `null`, list size 0 và list size 1 chứa chuỗi rỗng.

### Nên test thêm những tình huống nào?

- Thứ tự positional operands khi option xuất hiện xen giữa.
- Option có dấu bằng trong value (`--token=a=b`).
- Đường dẫn có khoảng trắng qua mảng String[] trực tiếp, tránh phụ thuộc shell.
- Không có positional, một positional, quá nhiều positional.
- Số âm (token `-5`), token `-v` và option `--offset=-5`.
- Cờ có value `--dry-run=false` so với cờ không value `--dry-run`.
- Kiểm tra xử lý unknown option, blank value và lỗi chuyển kiểu.
- Cú pháp truyền arguments từ Gradle, Maven, IDE, Docker/Kubernetes.
- Khác biệt parser giữa các phiên bản Spring Framework, đặc biệt khi dùng cú pháp lặp option hoặc option delimiter.

## 13. Lỗi thường gặp và cách sửa

**1. “Mọi token bắt đầu bằng dấu gạch là option.”** Sai. Parser mặc định được mô tả bằng `--name[=value]`; `-v` và `-12` không tự trở thành short option hợp lệ.

**2. “--mode import tương đương --mode=import.”** Sai với parser mặc định. `--mode` không có value gắn bằng dấu `=`; `import` là positional.

**3. “getOptionValues trả [] nghĩa là option không có.”** Sai. `null` biểu diễn vắng mặt, còn list size 0 biểu diễn cờ có mặt nhưng không value.

**4. “--empty= giống --empty.”** Sai: một trường hợp có **một chuỗi rỗng** và trường hợp kia có **không giá trị**.

**5. “containsOption('dry-run') kiểm tra giá trị boolean của option.”** Sai. Nó kiểm tra option có mặt hay không; `--dry-run=false` vẫn có `containsOption == true`.

**6. “getOptionNames trả thứ tự như argv.”** Không nên dựa vào thứ tự của `Set`. Nếu cần thứ tự token gốc, dùng `getSourceArgs()`; nếu chỉ muốn log tên theo alphabet, sort `Set` như ví dụ.

**7. “getNonOptionArgs chứa tất cả arguments.”** Không. Nó chỉ chứa positional/non-option; các token có dạng `--name=value` được đưa vào nhóm option.

**8. “Đối số không có tên luôn có thể bỏ qua.”** Không. Một positional như file đầu vào có thể là dữ liệu bắt buộc của một CLI command.

**9. “--tag=a,b mặc nhiên tạo hai giá trị option.”** Không: đó là một string value `a,b`. Tách dấu phẩy nếu hợp đồng nghiệp vụ yêu cầu.

**10. “Có List<String> nghĩa là luôn được lặp --tag=a --tag=b.”** Không. Hợp đồng list và hỗ trợ của parser/phiên bản là hai vấn đề. Không mang cú pháp của Spring Framework mới về Spring Boot 3.3 mà chưa kiểm tra.

**11. “CommandLineRunner và ApplicationRunner xử lý khác loại đối số.”** Cả hai nhận input từ cùng nguồn argv. Khác biệt là callback của `ApplicationRunner` có wrapper phân loại, còn `CommandLineRunner` nhận raw strings.

**12. “Chỉ cần khai báo --server.port là nó chỉ dùng cho CLI nghiệp vụ.”** Mặc định các command-line options cũng có thể tham gia `Environment`, nên tránh tên option trùng cấu hình framework nếu không chủ đích.

**13. “Ghi toàn bộ raw args trong production không rủi ro.”** Sai. Secret có thể lộ trong log, process list và pipeline; cần phân loại, lọc hoặc chọn kênh cấp secret khác.

**14. “Ứng dụng đã chạy rồi thì thay argv sẽ cập nhật bean ngay.”** Không. Arguments được parse khi khởi động; thay đổi cấu hình runtime có hợp đồng khác và không tự tái khởi tạo mọi bean.

**15. “Mỗi HTTP request đi qua ApplicationArguments.”** Không: `ApplicationArguments` gắn với lần `SpringApplication.run`. Query parameters của HTTP request được xử lý bằng web framework, không phải startup parser.

**16. “Spring Boot tự báo lỗi khi thiếu positional input.csv.”** Parser chỉ phân loại. Điều kiện bắt buộc, kiểu file, permissions và validation đều là trách nhiệm nghiệp vụ.

## 14. Bài thực hành

1. Phân loại thủ công: `--mode=import input.csv --dry-run output.csv`. Có bao nhiêu option names? Bao nhiêu positional arguments?
2. So sánh `--mode=import` với `--mode import` trong project. Điều gì xảy ra với `getOptionValues("mode")` và `getNonOptionArgs()`?
3. So sánh `--flag`, `--flag=`, `--flag=false` và trường hợp không có flag. Vì sao dùng mỗi `containsOption` không đủ để parse boolean có ba trạng thái?
4. Chạy demo mục 7. Tại sao `APP: tag=[alpha,beta]` không chứng minh có hai phần tử trong list? Hãy in `getOptionValues("tag").size()`.
5. Thay `--tag=alpha,beta` bằng `--tag=alpha`. Kết quả thay đổi như thế nào?
6. Truyền hai positional operands trước các option. `getNonOptionArgs()` có bảo toàn thứ tự hai operands không?
7. Truyền `-5` và `--offset=-5`. Hai giá trị âm thuộc nhóm nào?
8. Truyền `--name="Lan Anh"` bằng IDE program arguments. Sau đó in `getSourceArgs()` và kiểm tra liệu nó thành một hay hai tokens; shell quoting ảnh hưởng phần nào?
9. Viết validation cho contract: mode phải là `import`/`validate` và có một input file. Khi thiếu input, báo lỗi gì cho người dùng?
10. Thay đổi runner để fail startup khi mode không hợp lệ. Điều gì xảy ra với `ApplicationReadyEvent`?
11. Trong một project web, truyền `--server.port=9090` rồi xem môi trường ứng dụng. Vì sao không phải mọi CLI option đều chỉ phục vụ nghiệp vụ?
12. Thử `SpringApplication.setAddCommandLineProperties(false)` trước `run`. Vì sao `ApplicationArguments` vẫn có các arguments trong khi `Environment` không thêm command-line property source mặc định?
13. Viết JUnit test cho `DefaultApplicationArguments("--dry-run", "--empty=")`, assert size và độ dài chuỗi. Tại sao không nên chỉ so sánh `List.toString()`?
14. Thiết kế CLI nhập nhiều đường dẫn file, trong đó một đường dẫn có dấu cách hoặc bắt đầu bằng dấu gạch. Bạn sẽ đặt quy tắc quoting và validation ra sao để không phụ thuộc ngẫu nhiên vào shell?
15. Nếu cần short flags, subcommands, help, completion và validation theo schema, tại sao nên cân nhắc picocli thay vì cố biến `ApplicationArguments` thành một parser đầy đủ?
16. Nếu option `--api-token` chứa bí mật, vì sao log `Arrays.toString(args)` là rủi ro? Kênh cấu hình nào phù hợp hơn trong production?

## Ghi nhớ

- **Option** theo parser mặc định: `--name` hoặc `--name=value`. **Non-option**: các token không được nhận diện theo cú pháp option, thường là positional operands.
- `getOptionNames()` và `containsOption(name)` làm việc với **tên không có tiền tố `--`**.
- `getOptionValues(name)` có ba trạng thái: **null** khi vắng mặt, **list rỗng** cho cờ có mặt không value, hoặc **list có value**; `--name=` là một value chuỗi rỗng.
- `getNonOptionArgs()` chỉ trả các positional operands, còn `getSourceArgs()` giữ toàn bộ chuỗi argv gốc.
- **`--mode import` không phải `--mode=import`**. Dấu bằng phân cách tên và giá trị của cùng token.
- `ApplicationRunner` cho API phân loại thông qua `ApplicationArguments`; `CommandLineRunner` cho `String...` raw, cả hai chạy ở pha startup sau refresh.
- Parser chỉ phân loại, **không xác thực nghiệp vụ**. Hãy validate số lượng, dữ liệu, option bắt buộc, đường dẫn và chính sách lỗi.
- Command-line options có thể tham gia `Environment` theo mặc định, nhưng positional operands không tự trở thành named configuration properties.
- Khi cần cú pháp CLI nâng cao hoặc repeated options, hãy kiểm tra **phiên bản parser thực tế** hoặc dùng thư viện CLI chuyên dụng.

### Tài liệu tham khảo

- Spring Boot 3.3 — Application Arguments: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — ApplicationArguments API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Boot 3.3 — DefaultApplicationArguments API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/DefaultApplicationArguments.html
- Spring Framework 6.1 — SimpleCommandLinePropertySource: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/env/SimpleCommandLinePropertySource.html
- Spring Framework 6.1 — CommandLinePropertySource: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/env/CommandLinePropertySource.html
- Spring Boot 3.3 — ApplicationRunner API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3 — CommandLineRunner API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html
