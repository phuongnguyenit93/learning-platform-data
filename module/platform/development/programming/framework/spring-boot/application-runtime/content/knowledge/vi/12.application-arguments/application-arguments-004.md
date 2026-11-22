# Xử lý tùy chọn lặp lại hoặc không kèm giá trị trong Spring Boot

## 1. Mục tiêu của bài

Spring Boot cho phép ứng dụng nhận các đối số dòng lệnh như `--mode=batch`, `--verbose` hoặc `--tag=red --tag=blue`. Với các tùy chọn chỉ xuất hiện một lần và luôn có giá trị, việc đọc tham số khá đơn giản. Khó khăn bắt đầu khi:

- Một tên tùy chọn xuất hiện **nhiều lần**, mỗi lần có thể có giá trị khác nhau.
- Một tùy chọn xuất hiện như **cờ không kèm giá trị**, ví dụ `--dry-run`.
- Một tùy chọn có dấu bằng nhưng **giá trị là chuỗi rỗng**, ví dụ `--name=`.
- Một tùy chọn **hoàn toàn không xuất hiện**.
- Cùng một tên xuất hiện vừa có giá trị, vừa không có giá trị, ví dụ `--tag --tag=red`.
- Người dùng truyền đối số sai cú pháp như `--tag red`, tưởng rằng `red` là giá trị của `tag`.

Để xử lý đúng, cần hiểu hợp đồng của `org.springframework.boot.ApplicationArguments` và quy tắc phân tích đối số của Spring Framework. Bài này tập trung vào **đối số ứng dụng (application arguments)** trong Spring Boot Runtime, không phải đối số JVM, hệ thống cấu hình của shell hay cú pháp tham số của một công cụ CLI bất kỳ.

Sau bài học, bạn có thể phân biệt bốn trường hợp quan trọng: **vắng mặt**, **có mặt nhưng không giá trị**, **có một giá trị rỗng** và **có một hoặc nhiều giá trị thực**; sau đó xây dựng chính sách kiểm tra đầu vào phù hợp thay vì ngầm đoán.

## 2. Cú pháp tùy chọn mà Spring Boot phân tích

Spring Boot sử dụng `ApplicationArguments` để diễn giải các đối số được truyền cho `SpringApplication.run(args)`. Với bộ phân tích đối số thông thường, cú pháp của một tùy chọn là:

~~~text
--optionName[=optionValue]
~~~

Tên tùy chọn được mở đầu bằng **hai dấu gạch ngang**. Khi có giá trị, dấu `=` phải nối trực tiếp tên và giá trị trong **cùng một argument token**.

Một số ví dụ:

| Đối số | Phân loại | Ý nghĩa |
| --- | --- | --- |
| `--verbose` | Option | Có tùy chọn `verbose`, không truyền giá trị |
| `--verbose=true` | Option | Có tùy chọn `verbose` với chuỗi giá trị `"true"` |
| `--verbose=false` | Option | Có tùy chọn `verbose` với chuỗi giá trị `"false"` |
| `--name=` | Option | Có tùy chọn `name` với **một giá trị là chuỗi rỗng** |
| `--tag=red` | Option | `tag` có giá trị `red` |
| `--tag=red --tag=blue` | Hai option token | Cùng một tên `tag` có **hai giá trị** |
| `--tag=red,blue` | Một option token | Có **một** chuỗi `red,blue`; parser không tự tách dấu phẩy |
| `report.csv` | Non-option | Đối số vị trí, không thuộc một tên tùy chọn |
| `--tag report.csv` | Hai token | `tag` không có giá trị; `report.csv` là non-option |
| `-v` | Non-option trong parser này | Không tự đồng nghĩa với `--verbose` |
| `--` | Dấu kết thúc phần option | Những token phía sau được xem là non-option |

Ví dụ, các token được truyền vào `main(String[] args)` như sau:

~~~text
["--tag=red", "--tag=blue", "--verbose", "report.csv"]
~~~

tạo một tập option với hai giá trị của `tag`, một cờ `verbose` không có giá trị, và một non-option `report.csv`.

**Chú ý quan trọng về shell:** khi truyền giá trị chứa khoảng trắng, cần quote để shell chuyển nó thành một token, ví dụ:

~~~bash
java -jar app.jar --title="daily report"
~~~

Spring nhận một đối số tương ứng `--title=daily report`. Chính shell xử lý dấu quote; Java parser chỉ nhận các chuỗi đã tách token. Cách quote trên PowerShell, cmd.exe và Bash có thể khác ở những trường hợp phức tạp.

### Dấu kết thúc `--`

Dấu `--` (chỉ hai gạch ngang, không có tên option) đánh dấu kết thúc phần xử lý tùy chọn theo cú pháp parser thông thường. Ví dụ:

~~~bash
java -jar app.jar --verbose -- --tag=not-an-option report.csv
~~~

Ở đây `verbose` vẫn là option; các token sau dấu `--`, kể cả chuỗi bắt đầu bằng `--tag=`, được coi là non-option. Đây là cách hữu ích khi cần truyền tên file hoặc dữ liệu vị trí bắt đầu bằng `--`.

Không nhầm dấu `--` kết thúc option với `--tag`: một token có tên là một option không kèm giá trị; token chỉ chứa `--` là delimiter.

## 3. API ApplicationArguments cần biết

Spring Boot cung cấp interface `org.springframework.boot.ApplicationArguments`. Trong ứng dụng thực, bạn có thể inject nó vào bean hoặc nhận nó qua `ApplicationRunner.run(ApplicationArguments args)`.

| API | Giá trị trả về | Khi nào dùng? |
| --- | --- | --- |
| `containsOption(String name)` | `boolean` | Xác định option có hiện diện không, kể cả không có giá trị |
| `getOptionValues(String name)` | `List<String>` hoặc `null` | Lấy **tất cả giá trị** của một option lặp |
| `getOptionNames()` | `Set<String>` | Lấy các **tên duy nhất** của option |
| `getNonOptionArgs()` | `List<String>` | Lấy đối số vị trí, không phải option |
| `getSourceArgs()` | `String[]` | Lấy **toàn bộ token gốc** đã truyền cho `SpringApplication.run(...)` |

Đặc biệt, `getOptionValues(name)` có hợp đồng rõ ràng được Javadoc Spring Boot 3.5 ghi nhận:

| Cách truyền | `containsOption("foo")` | `getOptionValues("foo")` | Diễn giải |
| --- | --- | --- | --- |
| Không có `--foo` | `false` | `null` | Option **vắng mặt** |
| `--foo` | `true` | `[]` | Option có mặt, **không có giá trị** |
| `--foo=bar` | `true` | `["bar"]` | Một giá trị |
| `--foo=bar --foo=baz` | `true` | `["bar", "baz"]` | Nhiều giá trị |
| `--foo=` | `true` | Danh sách một phần tử `[""]` | **Một giá trị rỗng**, không phải danh sách rỗng |

**Không được viết `getOptionValues(name).isEmpty()` mà không xét khả năng trả về `null`.** Khi option vắng mặt, mã đó sẽ gây `NullPointerException`.

Một điều dễ đánh lừa khi debug Java: `List.of("").toString()` hiển thị trông giống `[]`, dù danh sách thật sự có một phần tử là chuỗi rỗng. Hãy kiểm tra **`size()` và độ dài của phần tử** để phân biệt một cách chắc chắn.

### Bốn trạng thái, không chỉ hai

Một mô hình quyết định an toàn:

~~~text
containsOption("foo")?
   |
   +-- false ---------------------------> ABSENT
   |
   +-- true
         |
         +-- getOptionValues("foo")      [khác null]
                |
                +-- size() == 0 --------> PRESENT_NO_VALUE
                |
                +-- size() >= 1
                       |
                       +-- phần tử "" ---> EXPLICIT_EMPTY_STRING
                       |
                       +-- phần tử khác -> VALUE(S)
~~~

Nếu option lặp có cả phần tử rỗng và giá trị thực, cần xác định chính sách nghiệp vụ: chấp nhận, loại chuỗi rỗng, hoặc báo lỗi.

### getOptionNames không cho biết số lần xuất hiện

`getOptionNames()` trả `Set<String>`. Vì thế:

~~~bash
--tag=red --tag=blue --tag=red
~~~

vẫn chỉ có **một tên `tag`** trong set. Nếu cần ba giá trị, dùng `getOptionValues("tag")`. Nếu muốn biết chính xác tên option đã xuất hiện bao nhiêu lần, kể cả những lần không kèm giá trị, có thể phải kiểm tra token gốc qua `getSourceArgs()`.

## 4. Vì sao option lặp lại được lưu thành danh sách?

Một số ứng dụng cần tập giá trị tự nhiên:

- `--include=*.java --include=*.xml`: nhiều mẫu lọc file.
- `--tag=finance --tag=priority`: nhiều nhãn.
- `--endpoint=https://a.example --endpoint=https://b.example`: nhiều địa chỉ thử theo thứ tự.
- `--role=reader --role=writer`: nhiều quyền được yêu cầu.
- `--feature=A --feature=B`: danh sách tính năng cần bật trong một tác vụ.

Tập giá trị có ý nghĩa nghiệp vụ. Chẳng hạn:

~~~java
List<String> tags = arguments.getOptionValues("tag");
if (tags == null) {
    tags = List.of();
}
~~~

Đây là **đoạn minh họa trong một scope đã có `ApplicationArguments arguments`**, không phải file Java chạy độc lập. Nó ánh xạ option vắng mặt thành danh sách rỗng theo chính sách *optional multi-value*. Tuy nhiên, nó làm mất sự khác nhau giữa **vắng mặt** và **có mặt nhưng không giá trị**; chỉ dùng cách này khi hai trạng thái được phép có cùng nghĩa.

Nếu yêu cầu nghiêm ngặt là người dùng đã nhập `--tag` thì phải kèm giá trị, cần kiểm tra riêng:

~~~java
boolean present = arguments.containsOption("tag");
List<String> values = arguments.getOptionValues("tag");

if (present && (values == null || values.isEmpty())) {
    throw new IllegalArgumentException(
            "--tag cần ít nhất một giá trị");
}
~~~

Đoạn trên cũng **chưa độc lập**, cần import `List` và biến `arguments`. Điều kiện `values == null` khi `present` là một bước phòng vệ; với triển khai Spring Boot thông thường, option đã có mặt thì nhận danh sách.

**Cần lưu ý:** `getOptionValues("tag")` chỉ phản ánh **giá trị được gắn với tên đó**. Nếu đầu vào pha trộn `--tag --tag=red`, một lần `--tag` không giá trị có thể không tạo phần tử `null` trong danh sách, trong khi `red` vẫn có mặt. Nếu quy định không cho phép *bất kỳ* lần xuất hiện nào thiếu giá trị, bạn cần phân tích token gốc hoặc dùng thư viện CLI có contract chặt hơn; chỉ nhìn danh sách giá trị chưa chắc đã đủ.

## 5. Flag không giá trị: chọn chính sách boolean rõ ràng

Một cờ như `--dry-run` thường được hiểu là bật tính năng. Nhưng cùng tên đó có thể được truyền như `--dry-run=false`. Ứng dụng phải **chọn và ghi rõ** một trong những hợp đồng:

**Chính sách A — chỉ cờ hiện diện:** `--dry-run` nghĩa là bật; `--dry-run=false` bị coi là sai cú pháp. Phù hợp với command-line utility đơn giản.

**Chính sách B — cờ hoặc boolean tường minh:** `--dry-run` nghĩa là `true`, `--dry-run=true` là `true`, `--dry-run=false` là `false`. Nếu vắng mặt, dùng giá trị mặc định (thường `false`).

**Chính sách C — bắt buộc có giá trị `true|false`:** `--dry-run` không có `=` bị xem là lỗi. Phù hợp khi mơ hồ có thể gây tác động nguy hiểm.

Không được lấy `containsOption("dry-run")` làm boolean cuối cùng nếu bạn muốn hỗ trợ `--dry-run=false`: `containsOption` vẫn trả **true** cho trường hợp đó.

Ví dụ triển khai Chính sách B, nhận đúng một giá trị boolean:

~~~java
static boolean booleanFlag(ApplicationArguments args,
                           String name, boolean defaultValue) {
    if (!args.containsOption(name)) {
        return defaultValue;
    }

    List<String> values = args.getOptionValues(name);
    if (values == null || values.isEmpty()) {
        return true; // "--name" không kèm giá trị.
    }
    if (values.size() != 1) {
        throw new IllegalArgumentException(
                "--" + name + " chỉ nhận một giá trị boolean");
    }

    return switch (values.get(0).toLowerCase(Locale.ROOT)) {
        case "true" -> true;
        case "false" -> false;
        default -> throw new IllegalArgumentException(
                "--" + name + " phải là true hoặc false");
    };
}
~~~

Đây là **phương thức minh họa**, cần import `ApplicationArguments`, `List` và `Locale`. Có thể đặt nó trong lớp Java hoàn chỉnh ở mục 7.

Với Chính sách B, các trường hợp:

| Input | Kết quả |
| --- | --- |
| Option không xuất hiện | `defaultValue` |
| `--dry-run` | `true` |
| `--dry-run=true` | `true` |
| `--dry-run=false` | `false` |
| `--dry-run=` | Lỗi: giá trị rỗng |
| `--dry-run=yes` | Lỗi nếu chỉ chấp nhận `true|false` |
| `--dry-run=true --dry-run=false` | Lỗi: nhiều giá trị mâu thuẫn |

Cách phân tích boolean nghiêm ngặt **tốt hơn** việc dùng `Boolean.parseBoolean(...)` không kiểm tra trước: Java chuyển mọi chuỗi khác `"true"` thành `false`, khiến lỗi chính tả dễ bị che giấu.

## 6. Phân biệt tùy chọn không giá trị và giá trị rỗng

Đây là lỗi khó nhận biết nhất khi chỉ đọc `toString()` của danh sách.

### 6.1. --flag: không có giá trị

~~~bash
java -jar app.jar --flag
~~~

Theo `ApplicationArguments`:

~~~text
containsOption("flag")  -> true
getOptionValues("flag") -> []
size()                  -> 0
~~~

Danh sách **không có phần tử nào**, nên không được gọi `get(0)` ngay.

### 6.2. --flag=: có một giá trị là ""

~~~bash
java -jar app.jar --flag=
~~~

Theo `ApplicationArguments`:

~~~text
containsOption("flag")  -> true
getOptionValues("flag") -> danh sách chứa ""
size()                  -> 1
get(0).length()         -> 0
~~~

Danh sách có **một phần tử** nhưng phần tử đó có độ dài bằng 0. Cách hiển thị trực tiếp bằng `List.toString()` có thể gây nhầm lẫn, nên in số phần tử hoặc đặt chuỗi trong dấu quote khi debug.

Tại tầng nghiệp vụ, cách xử lý khác nhau:

- Một option kiểu flag có thể chấp nhận `--flag` nhưng không chấp nhận `--flag=`.
- Một option kiểu chuỗi có thể chấp nhận `--name=` nếu người dùng muốn **xóa giá trị cũ**; không nhất thiết đồng nghĩa với option vắng mặt.
- Một option bắt buộc có dữ liệu thực cần từ chối cả `--name` và `--name=`.
- Một option được cho phép lặp có thể cần từ chối một phần tử `""` xen giữa các giá trị hợp lệ.

### 6.3. Không đồng nhất "" với null

Các trạng thái dưới đây không tương đương:

~~~text
null       => option không có registration trong ApplicationArguments
[]         => option có mặt, không có giá trị nào
[""]       => option có mặt, một chuỗi rỗng
["alpha"]  => option có mặt, một giá trị "alpha"
~~~

Nhất là trong logic cấu hình mang tính cập nhật (patch) hoặc điều khiển tính năng, `null`, danh sách rỗng và chuỗi rỗng có thể dẫn đến ba hành vi khác nhau.

## 7. Ví dụ hoàn chỉnh Java 17+ (Spring Boot 3.5.16)

Ví dụ sau minh họa trực tiếp ba nhóm: tùy chọn lặp `tag`, flag không kèm giá trị `verbose`, và chuỗi giá trị rỗng `empty`. Chương trình còn minh họa cờ có giá trị `enabled=false`, option vắng mặt `missing`, non-option `invoice.csv` và cách kiểm tra input trước khi xử lý.

Để dễ quan sát, ứng dụng đặt `WebApplicationType.NONE`: không mở HTTP server, các dòng output của chương trình có thể đối chiếu độc lập với log khởi động Spring Boot.

### 7.1. Cấu trúc Maven

~~~text
args-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/argsdemo/
                └── ArgsDemoApplication.java
~~~

**Tệp `pom.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>args-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
~~~

Đây là Maven project dành cho JDK 17+ và Spring Boot 3.5.16. Không dùng `spring-boot-starter-web` vì mục tiêu là demo nhận và phân tích đối số; các ứng dụng web vẫn dùng API `ApplicationArguments` tương tự.

### 7.2. Tệp Java đầy đủ

**Tệp `src/main/java/com/example/argsdemo/ArgsDemoApplication.java`:**

~~~java
package com.example.argsdemo;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ArgsDemoApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                ArgsDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }

    @Bean
    ApplicationRunner inspectArgs() {
        return args -> {
            System.out.println("tag -> " + describe(args, "tag"));
            System.out.println("verbose -> " + describe(args, "verbose"));
            System.out.println("empty -> " + describe(args, "empty"));
            System.out.println("missing -> " + describe(args, "missing"));
            System.out.println("enabled -> " + describe(args, "enabled"));

            System.out.println(
                    "nonOptions=" + args.getNonOptionArgs());
            System.out.println(
                    "sourceArgCount=" + args.getSourceArgs().length);

            // Một option đa trị: nếu xuất hiện thì phải có giá trị.
            List<String> tags = requiredValues(args, "tag");
            System.out.println("tagsValidated=" + tags);

            // Chính sách cờ: có mặt không giá trị => true.
            System.out.println(
                    "verboseFlag=" + booleanFlag(
                            args, "verbose", false));
            System.out.println(
                    "enabledFlag=" + booleanFlag(
                            args, "enabled", true));
        };
    }

    private static String describe(ApplicationArguments args,
                                   String name) {
        if (!args.containsOption(name)) {
            return "ABSENT";
        }

        List<String> values = args.getOptionValues(name);
        if (values == null || values.isEmpty()) {
            return "PRESENT_NO_VALUE";
        }

        // Đánh dấu chuỗi rỗng để tránh List.toString() gây nhầm.
        String display = values.stream()
                .map(v -> v.isEmpty() ? "<empty-string>" : v)
                .collect(Collectors.joining(", ", "[", "]"));

        return "VALUES(" + values.size() + ")=" + display;
    }

    private static List<String> requiredValues(
            ApplicationArguments args, String name) {

        if (!args.containsOption(name)) {
            return List.of();
        }

        List<String> values = args.getOptionValues(name);
        if (values == null || values.isEmpty()) {
            throw new IllegalArgumentException(
                    "--" + name + " phải có ít nhất một giá trị");
        }

        List<String> clean = new ArrayList<>();
        for (String value : values) {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException(
                        "--" + name + " không được có giá trị rỗng");
            }
            clean.add(value);
        }
        return List.copyOf(clean);
    }

    private static boolean booleanFlag(
            ApplicationArguments args,
            String name,
            boolean defaultValue) {

        if (!args.containsOption(name)) {
            return defaultValue;
        }

        List<String> values = args.getOptionValues(name);
        if (values == null || values.isEmpty()) {
            return true;
        }

        if (values.size() != 1) {
            throw new IllegalArgumentException(
                    "--" + name + " chỉ nhận một giá trị boolean");
        }

        return switch (values.get(0).toLowerCase(Locale.ROOT)) {
            case "true" -> true;
            case "false" -> false;
            default -> throw new IllegalArgumentException(
                    "--" + name + " phải là true hoặc false");
        };
    }
}
~~~

**Điểm cần quan sát trong mã:**

1. `ApplicationRunner` là bean được Spring Boot gọi sau khi context refresh. Nó nhận `ApplicationArguments` của cùng lần chạy qua tham số `run()`.
2. `describe(...)` phân biệt vắng mặt, không giá trị, có một hay nhiều giá trị; nó **không in trực tiếp một danh sách chứa chuỗi rỗng mà không đánh dấu**.
3. `requiredValues(...)` dùng danh sách các giá trị đã parse, từ chối `--tag` chỉ có mặt nhưng không giá trị, và từ chối `--tag=` có giá trị rỗng. Nó **chưa kiểm tra từng token gốc** để loại một lần `--tag` không giá trị khi đi kèm `--tag=red`; mục 10 trình bày cách giải quyết nếu hợp đồng cần nghiêm ngặt hơn.
4. `booleanFlag(...)` chọn chính sách: vắng mặt dùng mặc định; `--verbose` bật; `--enabled=false` tắt; nhiều giá trị boolean thì báo lỗi.
5. `@Bean` không yêu cầu tự parse `String[]` bằng cách tách thủ công; `ApplicationArguments` chính là API dành cho trường hợp này.
6. Các class và method đều nằm trong một tệp Java, không phụ thuộc database, network hoặc cơ chế thêm vào startup nào khác.

### 7.3. Lệnh chạy và stdout dự kiến

Tại thư mục chứa `pom.xml`:

~~~bash
mvn package
java -jar target/args-demo-0.0.1-SNAPSHOT.jar --tag=red --tag=blue --verbose --empty= --enabled=false invoice.csv
~~~

Lệnh truyền **sáu token** cho ứng dụng, theo đúng thứ tự:

~~~text
--tag=red
--tag=blue
--verbose
--empty=
--enabled=false
invoice.csv
~~~

Các dòng do **mã demo in ra** (bỏ qua banner và log của Spring Boot/Maven) có nội dung chính xác:

~~~text
tag -> VALUES(2)=[red, blue]
verbose -> PRESENT_NO_VALUE
empty -> VALUES(1)=[<empty-string>]
missing -> ABSENT
enabled -> VALUES(1)=[false]
nonOptions=[invoice.csv]
sourceArgCount=6
tagsValidated=[red, blue]
verboseFlag=true
enabledFlag=false
~~~

Tại sao output chính xác?

- `tag` có hai lần `--tag=value`, nên danh sách có hai phần tử `red`, `blue`.
- `verbose` xuất hiện dưới dạng `--verbose`, nên có mặt nhưng danh sách giá trị rỗng.
- `empty` xuất hiện dưới dạng `--empty=`, nên có một giá trị rỗng: `VALUES(1)`, không phải `PRESENT_NO_VALUE`.
- `missing` hoàn toàn không xuất hiện, nên `ABSENT`.
- `enabled=false` chứa giá trị chuỗi `false`; policy boolean biến nó thành `false`.
- `invoice.csv` không có tiền tố `--`, nên là non-option.
- `getSourceArgs().length` đếm số token gốc, không đếm số tên option duy nhất.
- `tagsValidated` giữ thứ tự các giá trị hợp lệ; `verboseFlag` lấy giá trị `true` theo quy ước có mặt không kèm giá trị.

Thử thay `--empty=` bằng `--empty`. Output của dòng đó chuyển từ `VALUES(1)=[<empty-string>]` sang `PRESENT_NO_VALUE`.

### 7.4. Một số lệnh thử thêm

**Chỉ có một giá trị tag:**

~~~bash
java -jar target/args-demo-0.0.1-SNAPSHOT.jar --tag=red
~~~

Lúc này phần tag sẽ là `VALUES(1)=[red]`, `tagsValidated=[red]`, `verboseFlag=false` (vì vắng mặt, mặc định false), `enabledFlag=true` (vì vắng mặt, mặc định true), `sourceArgCount=1` và `nonOptions=[]`.

**Tag không có giá trị:**

~~~bash
java -jar target/args-demo-0.0.1-SNAPSHOT.jar --tag
~~~

Dòng mô tả tag là `PRESENT_NO_VALUE`; sau đó `requiredValues(...)` ném `IllegalArgumentException`. Startup không hoàn tất theo đường thành công vì runner thất bại. Log exception và exit code có thể phụ thuộc môi trường.

**Tag có một phần tử rỗng:**

~~~bash
java -jar target/args-demo-0.0.1-SNAPSHOT.jar --tag=
~~~

Dòng mô tả là `VALUES(1)=[<empty-string>]`, sau đó `requiredValues(...)` từ chối vì giá trị rỗng.

**Lặp lại một flag với hai giá trị:**

~~~bash
java -jar target/args-demo-0.0.1-SNAPSHOT.jar --enabled=true --enabled=false
~~~

Dòng `enabled` có `VALUES(2)=[true, false]`; `booleanFlag(...)` ném lỗi vì policy **chỉ nhận một giá trị boolean**. Không áp đặt quy tắc “lần cuối thắng” một cách ngầm định.

**Một option và một non-option do tách bằng khoảng trắng:**

~~~bash
java -jar target/args-demo-0.0.1-SNAPSHOT.jar --tag red
~~~

`--tag` vẫn là option **không có giá trị**; `red` là non-option. Không nên coi đây là cú pháp tương đương `--tag=red`.

## 8. Nên dùng ApplicationArguments hay Environment/@Value?

Spring Boot còn đưa command-line arguments vào `Environment` dưới dạng một `CommandLinePropertySource` (trừ khi ứng dụng chủ động vô hiệu hóa việc bổ sung command-line properties). Vì vậy, trong nhiều dự án có thể đọc một giá trị qua `Environment.getProperty("name")`, `@Value` hoặc `@ConfigurationProperties`.

Tuy nhiên, **mục tiêu của hai API khác nhau**:

| Nhu cầu | Ưu tiên |
| --- | --- |
| Biết option có được truyền hay không, kể cả `--flag` không giá trị | `ApplicationArguments.containsOption()` |
| Giữ từng giá trị của `--tag=a --tag=b` | `ApplicationArguments.getOptionValues()` |
| Phân biệt vắng mặt, không giá trị, chuỗi rỗng | `ApplicationArguments` + kiểm tra size |
| Đếm chính xác số lần một token xuất hiện | `getSourceArgs()` và parser riêng nếu cần |
| Lấy một property cấu hình qua nhiều nguồn có thứ tự ưu tiên | `Environment` hoặc `@ConfigurationProperties` |
| Bind cấu hình ứng dụng có type, validation, cấu hình mặc định | `@ConfigurationProperties` và validation |
| Truy cập mảng đối số nguyên gốc | `getSourceArgs()` hoặc `CommandLineRunner` |

**Không nên tự chuyển danh sách giá trị thành một chuỗi và coi đó là dữ liệu gốc.** `CommandLinePropertySource` là một `PropertySource` phục vụ hệ thống cấu hình; quá trình chuyển nhiều giá trị sang một chuỗi property có thể làm mất thông tin phân tách gốc hoặc khiến nó trông giống một giá trị chứa dấu phẩy. Nếu cần giữ `["red", "blue"]` riêng rẽ, đọc trực tiếp `getOptionValues("tag")`.

Ví dụ `--tag=red,blue` chỉ là **một** giá trị `red,blue` theo `ApplicationArguments`; trong khi `--tag=red --tag=blue` là **hai** giá trị. Nếu nghiệp vụ muốn chấp nhận cả hai dạng, hãy ghi rõ hợp đồng và tự áp dụng bước tách dấu phẩy có kiểm tra. Nếu dữ liệu có thể chứa dấu phẩy hợp lệ, cách tách đơn giản bằng `String.split(",")` có thể làm sai dữ liệu.

### @ConfigurationProperties có thay ApplicationArguments được không?

Không hoàn toàn. `@ConfigurationProperties` rất phù hợp để bind cấu hình thành bean có kiểu, đặc biệt khi ứng dụng có nhiều nguồn cấu hình. Nhưng nó **không phải API diễn giải mọi khác biệt ở cấp token CLI** như một option vắng mặt so với một option chỉ có mặt không kèm giá trị.

Nếu đây là CLI có nhiều option đa trị, flag, quy tắc thiếu/đủ và yêu cầu báo lỗi gần với command line, `ApplicationArguments` (hoặc thư viện CLI chuyên dụng như picocli nếu hệ thống thực sự cần) thường là điểm vào rõ ràng hơn.

## 9. Lặp giá trị, lựa chọn default và chiến lược hợp nhất

Một option có nhiều giá trị không tự nói cho ứng dụng phải xử lý thế nào. Hãy xác định contract:

| Loại option | Ví dụ | Chính sách đề xuất |
| --- | --- | --- |
| Danh sách đa trị | `--tag=red --tag=blue` | Giữ nguyên thứ tự, validate từng phần tử |
| Tập hợp không trùng | `--feature=A --feature=A` | Có thể loại trùng có chủ đích, báo rõ |
| Một giá trị duy nhất | `--mode=fast` | Từ chối nhiều giá trị thay vì tự chọn |
| Boolean flag | `--dry-run` | Có mặt không giá trị => true theo policy |
| Boolean tường minh | `--dry-run=false` | Parse nghiêm ngặt `true|false` |
| Chuỗi có thể được xóa | `--label=` | Có thể cho phép `""` có ý nghĩa “xóa” |
| Chuỗi bắt buộc | `--endpoint=https://...` | Từ chối thiếu hoặc chuỗi rỗng |
| Đối số vị trí | `report.csv` | Xử lý bằng `getNonOptionArgs()` |

Không có một chính sách đúng cho tất cả nghiệp vụ. Đối với dữ liệu nghiêm trọng (thông tin môi trường, quyền hạn, thao tác xóa dữ liệu), đừng âm thầm dùng “giá trị cuối thắng” nếu người dùng nhập hai lần mâu thuẫn. Nếu có yêu cầu chọn giá trị đầu hoặc cuối, hãy ghi trong tài liệu CLI và kiểm thử điều đó.

### Tùy chọn vắng mặt có khác flag false không?

Có thể khác. Ví dụ một chương trình cập nhật cấu hình:

- Không có `--enabled`: **không thay đổi cấu hình hiện có**.
- `--enabled=true`: đặt thành true.
- `--enabled=false`: đặt thành false.

Trong bài toán này, biến boolean nguyên thủy không biểu đạt đủ ba trạng thái. Bạn có thể dùng `Boolean` nullable hoặc một kiểu enum/record biểu đạt `UNSPECIFIED`, `TRUE`, `FALSE`. Cần tránh tự đồng nhất trạng thái vắng mặt với false, vì điều đó có thể vô tình thay đổi cấu hình khi người dùng không chủ động yêu cầu.

Tương tự, `--name=` có thể có ý nghĩa **xóa** giá trị cũ, khác với không gửi `--name`. Phải xét nghiệp vụ trước khi chuẩn hóa chuỗi rỗng thành null.

## 10. Một vấn đề tinh vi: lặp option có và không có giá trị

Giả sử người dùng truyền:

~~~bash
java -jar app.jar --tag --tag=red --tag=blue
~~~

`containsOption("tag")` là true. Danh sách từ `getOptionValues("tag")` có thể vẫn chỉ chứa các **giá trị thực** như `["red", "blue"]`; lần `--tag` không có giá trị không nhất thiết xuất hiện dưới dạng một phần tử null. Đây là hệ quả của việc API **biểu diễn giá trị**, không phải nhật ký đầy đủ mọi lần xuất hiện của option.

Nếu nghiệp vụ yêu cầu mọi lần `--tag` đều phải có `=value`, kiểm tra theo token gốc. Đoạn sau là một helper có thể đặt trong class ở mục 7:

~~~java
private static boolean hasValuelessOccurrence(
        ApplicationArguments arguments, String name) {

    String token = "--" + name;

    for (String raw : arguments.getSourceArgs()) {
        if ("--".equals(raw)) {
            break; // Sau delimiter là non-option.
        }
        if (raw.equals(token)) {
            return true;
        }
    }
    return false;
}
~~~

Đây là **một phương thức Java hoàn chỉnh về cú pháp nhưng chưa phải chương trình độc lập**, vì nó cần `ApplicationArguments` và class chứa nó.

Sau đó, khi `tag` là multi-value bắt buộc:

~~~java
if (hasValuelessOccurrence(args, "tag")) {
    throw new IllegalArgumentException(
            "Mỗi --tag phải có dạng --tag=value");
}
List<String> tags = requiredValues(args, "tag");
~~~

Đoạn này **minh họa trong phạm vi class mục 7**: cần ghép method helper trên vào class. Cách này chặn đầu vào pha trộn có một lần `--tag` thiếu giá trị. Nó cố tình dừng tại dấu kết thúc `--` để không nhầm một token vị trí bắt đầu bằng `--tag` là option.

Nếu muốn đếm số lần option chính xác, bạn cũng có thể duyệt `getSourceArgs()` và đếm token bằng `"--tag".equals(raw)` hoặc `raw.startsWith("--tag=")` trước delimiter. **Đừng dùng `raw.startsWith("--tag")` đơn thuần** vì nó sẽ đếm nhầm `--tags`, `--tag-extra` và các tên khác.

### Lưu ý về thứ tự và tiền xử lý

Giữ `getSourceArgs()` để xử lý khi thật sự cần thông tin token-level, không phải vì `ApplicationArguments` “không tốt”. Với đa số ứng dụng, danh sách từ `getOptionValues` đủ để đọc các giá trị đã parse; việc tự viết parser khác đi có thể gây lệch cú pháp với Spring.

Nếu yêu cầu CLI trở nên phức tạp như short aliases (`-v`), required option groups, subcommands, help tự sinh, type conversion và message lỗi chi tiết, hãy cân nhắc thư viện CLI chuyên dụng thay vì duy trì một parser tự chế lớn.

## 11. Khác biệt giữa application arguments và JVM arguments

Những thứ có chữ “argument” không nhất thiết đi qua `ApplicationArguments`:

~~~bash
java -Xmx512m -Dapp.mode=fast -jar app.jar --tag=red --verbose
~~~

Phân biệt:

- `-Xmx512m` là tùy chọn của **JVM**, không nằm trong `String[] args` của ứng dụng.
- `-Dapp.mode=fast` đặt **Java system property**, cũng không phải token ứng dụng khi đặt trước `-jar`.
- `--tag=red` và `--verbose` nằm **sau tên JAR**, được Java chuyển cho `main(String[] args)`, rồi Spring Boot đưa vào `ApplicationArguments`.

Đặt các token ở sai vị trí có thể làm thay đổi hoàn toàn cách Java launcher và ứng dụng hiểu tham số. Đối với ứng dụng Docker/Kubernetes, cần kiểm tra rõ ENTRYPOINT và CMD/args: một chuỗi lệnh có thể được shell xử lý khác với mảng argv mà container runtime cung cấp.

### Khi chạy qua Maven

Có thể truyền đối số ứng dụng vào goal `spring-boot:run` bằng tham số plugin tương ứng (ví dụ `spring-boot.run.arguments`), nhưng cú pháp quote phụ thuộc shell và Maven. Để kiểm tra chính xác trường hợp lặp hoặc `--name=`, ví dụ trong bài dùng **`mvn package` + `java -jar ...`** giúp quan sát đầu vào đơn giản hơn.

## 12. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `NullPointerException` khi dùng `getOptionValues(...).size()` | Option vắng mặt nên trả null | Kiểm tra `containsOption` hoặc null trước khi dùng |
| `--verbose` được hiểu là false | Chỉ đọc danh sách rỗng hoặc dùng boolean parser sai | Định nghĩa policy: present/no-value => true nếu muốn cờ |
| `--verbose=false` vẫn bị hiểu true | Dùng mỗi `containsOption` | Đọc và parse `getOptionValues` |
| `--name=` bị nhầm với `--name` | `List.toString()` in mơ hồ | In size, length và đánh dấu chuỗi rỗng |
| `--tag=a --tag=b` chỉ còn một giá trị | Dùng `Environment.getProperty` hoặc tự overwrite vào `Map<String,String>` | Dùng `getOptionValues("tag")` |
| `--tag a` không cho tag bằng `a` | Parser yêu cầu cùng token `--tag=a` | Sửa cú pháp người dùng, hoặc dùng parser CLI khác theo nhu cầu |
| `--tag=a,b` không ra hai phần tử | Dấu phẩy nằm trong cùng một chuỗi giá trị | Chọn chính sách tự tách comma nếu muốn hỗ trợ |
| `--tag --tag=a` không bị phát hiện lần thiếu giá trị | Danh sách đã parse chỉ giữ giá trị | Kiểm tra `getSourceArgs()` trước delimiter |
| `--flag=true --flag=false` chạy với kết quả khó đoán | Không quy định policy trùng hoặc dùng giá trị đầu/cuối ngầm | Chặn trùng hoặc công bố rõ nguyên tắc ưu tiên |
| `-v` không bật verbose | Parser mặc định không tự ánh xạ short alias | Dùng `--verbose` hoặc thư viện CLI hỗ trợ alias |
| Một option sau dấu `--` không được parse | Đó là delimiter kết thúc option | Dùng đúng cú pháp hoặc kiểm tra non-options |
| `getOptionNames()` không có tên trùng | Phương thức trả về Set | Dùng getOptionValues hoặc source args tùy nhu cầu |
| Dữ liệu có khoảng trắng bị tách | Shell chưa quote giá trị | Quote thành một token theo shell đang dùng |
| Output chứa secret | In raw args hoặc password/token ra log | Chỉ in thông tin an toàn, redaction trước khi ghi |
| Runner báo lỗi sau log Started | Runner chạy sau `ApplicationStartedEvent` | Xác định lỗi trong `ApplicationRunner` và startup failure, không coi log Started là ready |

### Hướng chẩn đoán thực tế

1. Xác định **chuỗi token thực** mà `main(String[] args)` nhận được, không dựa vào bản lệnh đã bị shell thay đổi.
2. Kiểm tra `containsOption(name)` để phân biệt vắng mặt với có mặt.
3. Kiểm tra `getOptionValues(name) == null`, sau đó `size()` và nội dung từng phần tử; đừng chỉ nhìn `toString()`.
4. Kiểm tra `getNonOptionArgs()` nếu người dùng nhập `--name value` hoặc dùng delimiter `--`.
5. Nếu cần nhận diện từng lần xuất hiện, dùng `getSourceArgs()` và đếm đúng token, dừng ở delimiter.
6. Xác định option thuộc loại **cờ, đơn trị hay đa trị**, rồi áp dụng policy trùng, thiếu và rỗng tương ứng.
7. Khi parse thất bại, báo lỗi **có thể hành động được**: ví dụ “Mỗi --tag phải có dạng --tag=value”, thay vì để lỗi NPE/IndexOutOfBoundsException phát ra.
8. Không in toàn bộ command line chứa token, password hoặc thông tin nhạy cảm. Nếu cần chẩn đoán production, log tên option được phép và thông tin cấu trúc an toàn hơn log giá trị.

## 13. Bảo mật và khả năng vận hành

**Không log secrets qua command line.** Đối số như `--token=...`, `--password=...` có thể xuất hiện trong log, command history hoặc công cụ quan sát tiến trình tùy hệ điều hành. Khi hiển thị usage/debug, che giá trị nhạy cảm; với secret thực nên ưu tiên cơ chế quản lý bí mật được thiết kế phù hợp.

**Kiểm tra dữ liệu multi-value trước khi dùng.** Một option chứa danh sách endpoint, đường dẫn hoặc quyền hạn cần được validate từng giá trị. Không tự đưa toàn bộ chuỗi người dùng vào câu lệnh shell/SQL, không coi parser command-line là lớp bảo vệ dữ liệu.

**Đặt giới hạn hợp lý.** Nếu một option lặp được chấp nhận nhiều lần, cân nhắc giới hạn số lượng và độ dài mỗi giá trị. Một người dùng hoặc deployment sai cấu hình có thể truyền hàng nghìn giá trị, ảnh hưởng memory, thời gian khởi động và chi phí I/O.

**Không để flag mơ hồ gây hành vi nguy hiểm.** Các lệnh `--delete`, `--force`, `--allow-unsafe` cần hợp đồng explicit; có thể đòi xác nhận hoặc validation riêng thay vì ngầm suy từ option xuất hiện.

**Đừng biến parser thành cấu hình runtime thay đổi được.** `ApplicationArguments` mô tả input lúc bắt đầu `SpringApplication.run`. Nếu cần cập nhật cấu hình khi ứng dụng đã chạy, dùng cơ chế quản lý configuration/state thích hợp, không giả định các giá trị dòng lệnh sẽ tự thay đổi.

## 14. Câu hỏi kiểm tra kiến thức

**Câu 1:** Không truyền `--debug` thì `getOptionValues("debug")` là gì?

**Trả lời:** `null`, và `containsOption("debug")` là false.

**Câu 2:** Truyền `--debug` không có dấu bằng thì sao?

**Trả lời:** `containsOption("debug")` là true, còn `getOptionValues("debug")` là danh sách rỗng. Tùy nghiệp vụ, có thể xem đây là cờ bật.

**Câu 3:** Truyền `--debug=` có giống `--debug` không?

**Trả lời:** Không. Dạng có dấu bằng chứa **một chuỗi rỗng** trong danh sách giá trị; dạng không có dấu bằng là **danh sách không có phần tử**.

**Câu 4:** Truyền `--tag=red --tag=blue` thì `getOptionValues("tag")` trả gì?

**Trả lời:** Một danh sách chứa hai phần tử `red` và `blue` theo thứ tự đã được parse.

**Câu 5:** `getOptionNames()` có trả hai lần tên `tag` khi `tag` lặp hai lần không?

**Trả lời:** Không, vì kết quả là `Set<String>` tên option duy nhất, không phải nhật ký token.

**Câu 6:** Truyền `--foo bar` thì giá trị `foo` có phải `bar` không?

**Trả lời:** Không theo parser này. `--foo` là option không kèm giá trị, `bar` là non-option. Muốn có giá trị phải dùng `--foo=bar`.

**Câu 7:** `--tag=red,blue` có tự được tách thành hai giá trị không?

**Trả lời:** Không. Parser lưu một chuỗi `red,blue`. Nếu muốn tách dấu phẩy, ứng dụng phải tự định nghĩa và thực hiện bước chuyển đổi.

**Câu 8:** `--flag=false` có làm `containsOption("flag")` trả false không?

**Trả lời:** Không. `containsOption` kiểm tra sự hiện diện của tên, không parse giá trị boolean.

**Câu 9:** Khi có `--tag --tag=red`, có thể chắc chắn phát hiện lần thiếu giá trị chỉ bằng `getOptionValues("tag").size()` không?

**Trả lời:** Không. API chủ yếu lưu các giá trị gắn với tên. Nếu cần xác minh từng lần xuất hiện, xem token gốc `getSourceArgs()` theo đúng cú pháp parser.

**Câu 10:** Vì sao không nên log `getSourceArgs()` trong production?

**Trả lời:** Vì các token có thể chứa password, token, credential hoặc dữ liệu riêng. Nên redaction và ghi log cấu trúc an toàn.

## 15. Bài tập thực hành

### Bài tập A — phân biệt bốn trạng thái

Chạy ví dụ với các đầu vào:

~~~text
(không có --name)
--name
--name=
--name=Alice
~~~

Sửa dòng `describe` để kiểm tra option `name`. Ghi lại `containsOption`, kết quả `getOptionValues`, số phần tử và cách xử lý mong muốn của nghiệp vụ.

### Bài tập B — kiểm soát option lặp

Chạy:

~~~text
--tag=red --tag=blue --tag=red
~~~

Đặt ba policy thay thế: giữ nguyên cả ba, loại giá trị trùng, và báo lỗi nếu có giá trị trùng. Dùng `LinkedHashSet` nếu cần loại trùng mà vẫn giữ thứ tự xuất hiện. Trình bày tác động của mỗi lựa chọn lên kết quả.

### Bài tập C — kiểm tra lần xuất hiện thiếu giá trị

Chạy:

~~~text
--tag --tag=red --tag=blue
~~~

Thêm helper `hasValuelessOccurrence` ở mục 10 vào chương trình và từ chối input nếu bất kỳ token `--tag` nào không có `=value`. Sau đó chạy:

~~~text
--tag=red -- --tag
~~~

Giải thích vì sao token `--tag` **sau delimiter** phải được coi là non-option, không phải một lỗi của option `tag`.

### Bài tập D — boolean nghiêm ngặt

Kiểm tra bốn trường hợp:

~~~text
--enabled
--enabled=true
--enabled=false
--enabled=
~~~

So sánh với việc chỉ dùng `containsOption`. Giải thích vì sao policy hỗ trợ `false` tường minh không thể dùng duy nhất `containsOption`.

### Bài tập E — đối số JVM và application arguments

Chạy:

~~~bash
java -Dapp.note=test -jar target/args-demo-0.0.1-SNAPSHOT.jar --tag=red
~~~

Kiểm tra rằng `getSourceArgs()` của Spring Boot không chứa `-Dapp.note=test`, vì đó là Java system property được truyền cho JVM trước `-jar`.

## 16. Tài liệu tham khảo và ghi nhớ

Nguồn chính thức nên đối chiếu theo phiên bản thực tế của dự án:

- Spring Boot 3.5 — [ApplicationArguments Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ApplicationArguments.html): hợp đồng `containsOption`, `getOptionValues`, `getOptionNames`, `getSourceArgs` và non-options.
- Spring Boot 3.5 — [DefaultApplicationArguments Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/DefaultApplicationArguments.html): triển khai mặc định và constructor nhận `String... args`.
- Spring Boot 3.5 — [SpringApplication: Accessing Application Arguments](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): inject `ApplicationArguments`, so sánh runner và command-line properties.
- Spring Framework 6.2 — [SimpleCommandLinePropertySource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.3/javadoc-api/org/springframework/core/env/SimpleCommandLinePropertySource.html): cú pháp `--name[=value]`, option lặp, chuỗi rỗng và delimiter `--`.
- Spring Framework 6.2 — [CommandLineArgs](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/CommandLineArgs.html): dữ liệu chứa các option cùng danh sách giá trị.

**Những điểm quan trọng nhất:**

1. `ApplicationArguments.getOptionValues(name)` có **ba loại kết quả cơ bản**: `null` nếu option vắng mặt, danh sách rỗng nếu có mặt không giá trị, và danh sách một/nhiều chuỗi nếu có giá trị.
2. **`--foo` khác `--foo=`**: không giá trị khác với một giá trị là chuỗi rỗng.
3. **`--tag=red --tag=blue`** có hai giá trị; **`--tag=red,blue`** có một giá trị chứa dấu phẩy.
4. Dùng `containsOption` để kiểm tra **sự hiện diện**, không dùng nó một mình để parse boolean có thể nhận `false`.
5. Một option lặp có thể có lần xuất hiện không kèm giá trị; để kiểm tra **từng lần xuất hiện**, dùng `getSourceArgs()` và nhận diện đúng token.
6. Với parser thông thường, **`--tag red` không tương đương `--tag=red`**, và token sau delimiter `--` là non-option.
7. `getOptionNames()` chỉ cho **tên duy nhất**; `getNonOptionArgs()` cho đối số vị trí; `getSourceArgs()` cho đầu vào gốc.
8. Ứng dụng nên quy định rõ **option đơn trị/đa trị/boolean**, cách xử lý giá trị rỗng, trùng lặp và lỗi đầu vào, tránh tự lựa chọn bất ngờ.
9. Để đọc property theo hệ thống cấu hình, dùng `Environment`/`@ConfigurationProperties`; để giữ cấu trúc CLI và multi-value, dùng `ApplicationArguments`.
10. Không log đối số nhạy cảm; giới hạn input và báo lỗi rõ ràng trước khi tiến hành tác vụ nghiệp vụ.
