# Chọn ApplicationArguments hay mảng String[] trong Runner của Spring Boot

## 1. Bài toán: cùng là tham số lúc khởi động, nhưng cần đọc ở mức nào?

Khi chạy ứng dụng Spring Boot, người vận hành có thể truyền tham số:

~~~bash
java -jar app.jar --mode=batch --tag=one --tag=two --dry-run report.csv
~~~

Một runner có thể cần đọc **mode**, xác định cờ **dry-run**, nhận nhiều giá trị **tag** hoặc lấy tên tệp **report.csv**. Spring Boot cung cấp hai interface thực thi logic sau khi ApplicationContext đã refresh:

- **ApplicationRunner**: callback **run(ApplicationArguments args)** nhận đối tượng chứa cả tham số gốc và thông tin đã phân tích theo cú pháp option của Boot.
- **CommandLineRunner**: callback **run(String... args)** nhận **các chuỗi tham số gốc**, theo đúng thứ tự được chuyển tới SpringApplication, chưa được phân loại thành option và non-option.

Đây là **hai cách chọn biểu diễn dữ liệu đầu vào**, không phải hai loại vòng đời khác nhau. Cả hai được Spring Boot tìm dưới dạng **bean**, được gọi trong bước runner của SpringApplication, sau khi context refresh thành công và trước sự kiện **ApplicationReadyEvent**.

**Nguyên tắc chọn nhanh:**

- Chọn **ApplicationRunner** khi nghiệp vụ quan tâm cú pháp Spring Boot **--name[=value]**, các cờ như **--dry-run**, option lặp lại hoặc tham số không có tên (non-option).
- Chọn **CommandLineRunner** khi cần giữ **String[] nguyên bản** cho một công cụ/parser riêng, một API cũ, hoặc khi cách phân tích tham số của ứng dụng không trùng quy ước option của Spring.
- Nếu chỉ cần các giá trị cấu hình ổn định có thể đến từ file, Environment, CLI và cấu hình triển khai, cân nhắc **@ConfigurationProperties**, **Environment** hoặc cơ chế binding của Spring Boot, thay vì tự phân tích command line trong runner.

Bài học dùng **Java 17+ và Spring Boot 3.3.x** làm mốc, với trọng tâm là chọn đúng loại arguments trong **Runner**.

## 2. Hai interface và chữ ký chính xác

### 2.1. ApplicationRunner

Interface **org.springframework.boot.ApplicationRunner** khai báo:

~~~java
@FunctionalInterface
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

**ApplicationArguments** là abstraction có các method:

| Phương thức | Ý nghĩa | Kiểu trả về |
| --- | --- | --- |
| **getSourceArgs()** | Các token tham số gốc mà SpringApplication nhận | **String[]** |
| **getOptionNames()** | Các tên option đã phân tích, không gồm tiền tố **--** | **Set<String>** |
| **containsOption("name")** | Có xuất hiện option tên **name** hay không | **boolean** |
| **getOptionValues("name")** | Các giá trị của option; có quy tắc phân biệt vắng mặt và không có giá trị | **List<String>** hoặc **null** |
| **getNonOptionArgs()** | Các token không được phân loại là option | **List<String>** |

Ví dụ một method **ApplicationRunner** trong Spring bean:

~~~java
@Override
public void run(ApplicationArguments args) {
    boolean dryRun = args.containsOption("dry-run");
    List<String> tags = args.getOptionValues("tag");
    List<String> files = args.getNonOptionArgs();
    // Xử lý dữ liệu đã phân loại.
}
~~~

Đây là snippet, giả định class implements **ApplicationRunner** và đã import **java.util.List**. Bạn **không phải tự viết vòng lặp String[] để nhận diện --tag=...**, vì Boot đã cung cấp interface đọc option.

### 2.2. CommandLineRunner

Interface **org.springframework.boot.CommandLineRunner** khai báo:

~~~java
@FunctionalInterface
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

**String... args** là cú pháp **varargs** của Java; tại runtime, tham số này có kiểu **String[]**. Viết method implementation **run(String[] args)** hoặc **run(String... args)** đều tương thích về chữ ký Java, nhưng khi override thường chọn cú pháp varargs giống interface.

~~~java
@Override
public void run(String... args) {
    for (String token : args) {
        System.out.println(token);
    }
}
~~~

Runner nhìn thấy từng token nguyên bản, ví dụ **--mode=batch**, **--dry-run**, **report.csv**. Nó **không tự gọi getOptionValues**, vì không nhận ApplicationArguments trong tham số. Nếu cần phân tích option kiểu Boot, bạn có thể inject ApplicationArguments riêng vào bean, nhưng khi hầu hết logic dùng dữ liệu đã phân tích thì **ApplicationRunner** diễn đạt ý định rõ hơn.

### 2.3. Bảng so sánh

| Tiêu chí | ApplicationRunner | CommandLineRunner |
| --- | --- | --- |
| Callback | **run(ApplicationArguments)** | **run(String... args)** |
| Đầu vào chính | Dữ liệu đã phân tích theo quy ước Spring Boot | Chuỗi/token gốc |
| Đọc cờ **--dry-run** | **containsOption("dry-run")** | Tự kiểm tra token hoặc dùng parser khác |
| Đọc **--tag=one --tag=two** | **getOptionValues("tag") → ["one","two"]** | Nhận nguyên hai token |
| Lấy tham số vị trí | **getNonOptionArgs()** | Tự chọn token nào là tham số vị trí |
| Giữ nguyên đầu vào | **getSourceArgs()** | Chính **args** |
| Khả năng dùng **@Order** | Có | Có |
| Thời điểm callback | Sau refresh, trước ready | Sau refresh, trước ready |
| Mục đích phù hợp | CLI có cấu trúc đơn giản theo quy ước Boot | Forward raw args hoặc dùng parser riêng |

**Không có quy tắc “ApplicationRunner luôn chạy trước CommandLineRunner”.** Khi cả hai có mặt, Boot sắp xếp các runner theo cơ chế **Ordered** hoặc **@Order**. Không nên dựa vào thứ tự tên class hoặc interface.

## 3. Cú pháp option mà ApplicationArguments hiểu

Spring Boot sử dụng cơ chế phân tích tham số command line của Spring, với quy tắc chính:

~~~text
--optionName[=optionValue]
~~~

Một option bắt đầu bằng **hai dấu gạch ngang**. Giá trị, nếu có, đi sau dấu **=** trong **cùng token**.

Ví dụ:

~~~text
--mode=batch
--dry-run
--tag=one
--tag=two
report.csv
~~~

Với tập token này:

| Câu hỏi | Kết quả |
| --- | --- |
| **containsOption("mode")** | **true** |
| **getOptionValues("mode")** | **["batch"]** |
| **containsOption("dry-run")** | **true** |
| **getOptionValues("dry-run")** | **[]** |
| **getOptionValues("tag")** | **["one", "two"]** |
| **getOptionValues("missing")** | **null** |
| **getNonOptionArgs()** | **["report.csv"]** |
| **getSourceArgs()** | Mảng đủ năm token, theo đúng thứ tự nhập |

### 3.1. Ba trường hợp của getOptionValues phải phân biệt

**getOptionValues(name)** có ba trạng thái khác nhau theo API:

1. **Option không xuất hiện:** trả về **null**.
2. **Option xuất hiện nhưng không có giá trị**, ví dụ **--dry-run**: trả về **danh sách rỗng []**.
3. **Option có một hoặc nhiều giá trị**, ví dụ **--mode=batch** hoặc **--tag=one --tag=two**: trả về danh sách có phần tử.

Vì thế, code dưới đây **không an toàn**:

~~~java
String mode = args.getOptionValues("mode").get(0);
~~~

Nếu không có **--mode**, nó ném **NullPointerException**; nếu chỉ có **--mode** không kèm giá trị, nó có thể ném **IndexOutOfBoundsException**.

Cách kiểm tra rõ ràng:

~~~java
List<String> values = args.getOptionValues("mode");

if (values == null || values.size() != 1 ||
        values.get(0).isBlank()) {
    throw new IllegalArgumentException(
            "Cần đúng một --mode=<value>");
}

String mode = values.get(0);
~~~

Đoạn này giả định method đang ở trong **ApplicationRunner.run(...)** và đã import **List**. Nó chủ động từ chối **mode thiếu, rỗng hoặc xuất hiện lặp lại** thay vì âm thầm chọn một giá trị.

### 3.2. Cờ có mặt không giống option kiểu boolean

**containsOption("dry-run")** trả về **true** khi option có mặt, kể cả nếu token là:

~~~text
--dry-run=false
~~~

Vì đó vẫn là một option tên **dry-run**. Nếu ứng dụng muốn hỗ trợ cú pháp **--dry-run=true/false**, phải đọc và parse **getOptionValues("dry-run")** theo quy tắc boolean, hoặc sử dụng configuration binding thích hợp.

Ngược lại, với cờ thuần **--dry-run** không kèm **=**, **getOptionValues("dry-run")** là **[]**. Đừng gọi **get(0)** để lấy boolean. Hãy chọn rõ một trong hai hợp đồng:

- **Cờ hiện diện**: chỉ hỗ trợ **--dry-run**, đọc bằng containsOption và từ chối cách gán giá trị không đúng thiết kế.
- **Option có giá trị boolean**: hỗ trợ **--dry-run=true/false**, dùng parser boolean và kiểm tra giá trị hợp lệ.

Không trộn hai quy tắc một cách tùy tiện vì dễ khiến **--dry-run=false** bị hiểu nhầm là bật.

### 3.3. Option lặp lại

Với đầu vào:

~~~text
--tag=one --tag=two --tag=three
~~~

**getOptionValues("tag")** trả về danh sách gồm ba giá trị theo thứ tự xuất hiện. Nếu ứng dụng thiết kế **tag** như một tập nhiều giá trị, đây là hành vi hữu ích.

Nếu option chỉ nên có **một giá trị** như **--output=...**, hãy kiểm tra **size() == 1**; không tự mặc định lấy phần tử đầu/cuối mà không nêu rõ chính sách. Đối với **Set<String>** trả về từ getOptionNames, cũng không nên phụ thuộc thứ tự duyệt các tên option.

### 3.4. Tham số vị trí và cú pháp sai thường gặp

Những token không được nhận diện là option sẽ xuất hiện trong **getNonOptionArgs()**. Ví dụ:

~~~text
--mode=batch report.csv
~~~

**report.csv** là non-option. Nhưng:

~~~text
--mode batch
~~~

**không có nghĩa tương đương --mode=batch** đối với simple command-line parser của Spring. **--mode** là option có mặt nhưng chưa có giá trị; **batch** là non-option. Đây là lỗi thường gặp khi quen sử dụng các CLI parser kiểu GNU/POSIX hỗ trợ khoảng trắng giữa tên option và giá trị.

Để truyền **giá trị có dấu cách** mà vẫn là một token, shell phải giữ phần **--name=value** thành một đối số, ví dụ trên shell hỗ trợ trích dẫn:

~~~bash
java -jar app.jar "--report-title=Monthly Report"
~~~

Khi tới Java, token chứa cả dấu cách trong giá trị; các dấu quote dùng bởi shell thường không trở thành một phần của token Java.

### 3.5. Dấu -- kết thúc phần option

Parser của Spring hỗ trợ dấu **--** như ranh giới kết thúc việc đọc option. Những token theo sau sẽ được coi là non-option, kể cả khi bản thân chúng bắt đầu bằng hai dấu gạch ngang.

Ví dụ:

~~~text
--mode=batch -- --literal-option report.csv
~~~

Trường hợp này hữu ích khi chuyển phần còn lại của CLI thành dữ liệu thô cho công cụ khác. Tuy nhiên, cú pháp và việc shell/build tool chuyển dấu **--** cần được kiểm tra trong môi trường vận hành. Nếu CLI của ứng dụng phức tạp hơn, nên dùng parser chuyên dụng.

## 4. Cả hai nhận tham số ở cùng giai đoạn vòng đời

Trong Spring Boot, sau khi ApplicationContext refresh thành công, Boot phát **ApplicationStartedEvent**, sau đó gọi các **ApplicationRunner/CommandLineRunner**, rồi mới phát **ApplicationReadyEvent** và đánh dấu readiness sẵn sàng theo cơ chế availability.

~~~text
SpringApplication.run(raw String[] args)
    |
    +-- Chuẩn bị Environment, tạo ApplicationContext
    +-- Nạp definitions, refresh context
    +-- ApplicationStartedEvent
    |
    +-- Thu thập Runner beans
    +-- Sắp xếp theo Ordered / @Order
    +-- ApplicationRunner.run(ApplicationArguments)
    +-- CommandLineRunner.run(String...)
    |   (thứ tự hai loại do order quyết định)
    |
    +-- ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC
    +-- SpringApplication.run(...) trả về context
~~~

Hai runner không phải hai pha mặc định khác nhau. Cả hai chạy trong **một giai đoạn callRunners** sau refresh. Lập trình viên có thể khai báo nhiều bean của cả hai loại, ví dụ các bean kiểm tra cấu hình, tạo cache hay chạy một tác vụ startup.

**Hệ quả vận hành:**

- Runner đồng bộ chạy lâu có thể trì hoãn **ApplicationReadyEvent** và readiness.
- Exception không được xử lý từ một runner có thể khiến startup **thất bại**; không có ApplicationReadyEvent cho lần chạy thất bại đó.
- Web server có thể đã được khởi động trước khi runner hoàn tất, nên “đã mở cổng” không tương đương “đã ready”.
- Nếu một bean là **@Lazy** hoặc phụ thuộc nhiều tầng, cần bảo đảm Boot vẫn phát hiện các runner như mong muốn; không dùng lazy initialization như cách kiểm soát tùy tiện thời điểm chạy runner.
- Không cần tự gọi **runner.run(...)** trong main; Boot đã gọi các runner bean được đăng ký.

Nếu nhiều runner cần thứ tự xác định, thêm **@Order** hoặc triển khai **Ordered**. Giá trị order nhỏ hơn thường được gọi trước. Không dựa vào thứ tự method trong file mã nguồn.

## 5. Ví dụ Maven/Java 17+ hoàn chỉnh so sánh cùng một input

Ví dụ chạy ứng dụng **không có HTTP server** để dễ kiểm tra stdout. Nó tạo hai bean runner: một **ApplicationRunner** in dạng đã parse và một **CommandLineRunner** in raw args. **@Order** giúp thứ tự hai runner có thể dự đoán.

### 5.1. Tạo dự án

Sử dụng Java 17+, Maven 3.9+ và Spring Boot 3.3.13. Cấu trúc:

~~~text
runner-args-demo/
  pom.xml
  src/main/java/com/example/runner/RunnerArgsApplication.java
~~~

Nội dung **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>runner-args-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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

### 5.2. Mã Spring Boot

File **src/main/java/com/example/runner/RunnerArgsApplication.java**:

~~~java
package com.example.runner;

import java.util.Arrays;
import java.util.TreeSet;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class RunnerArgsApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(RunnerArgsApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            System.out.println("MAIN | active=" + context.isActive());
        }
    }

    @Component
    @Order(10)
    public static class ParsedRunner implements ApplicationRunner {

        @Override
        public void run(ApplicationArguments args) {
            // TreeSet chỉ để thứ tự tên option khi in được ổn định.
            System.out.println("PARSED | names="
                    + new TreeSet<>(args.getOptionNames()));
            System.out.println("PARSED | mode="
                    + args.getOptionValues("mode"));
            System.out.println("PARSED | tags="
                    + args.getOptionValues("tag"));
            System.out.println("PARSED | dry-run="
                    + args.containsOption("dry-run"));
            System.out.println("PARSED | dry-run values="
                    + args.getOptionValues("dry-run"));
            System.out.println("PARSED | missing="
                    + args.getOptionValues("missing"));
            System.out.println("PARSED | positionals="
                    + args.getNonOptionArgs());
            System.out.println("PARSED | source="
                    + Arrays.toString(args.getSourceArgs()));
        }
    }

    @Component
    @Order(20)
    public static class RawRunner implements CommandLineRunner {

        @Override
        public void run(String... args) {
            System.out.println("RAW | args="
                    + Arrays.toString(args));
        }
    }
}
~~~

Trong ứng dụng thật, hai runner có thể tách ra thành các tệp class riêng để dễ bảo trì. Ví dụ giữ chúng là **public static nested classes** có **@Component** để cùng trình bày trong một tệp; Spring Boot component scan vẫn quản lý chúng như bean.

### 5.3. Build và chạy với các tham số cụ thể

Tại thư mục **runner-args-demo**:

~~~bash
mvn -q -DskipTests package
java -jar target/runner-args-demo-1.0.0.jar --mode=batch --tag=one --tag=two --dry-run report.csv
~~~

Với Maven Wrapper trên Windows PowerShell, lệnh build tương ứng là:

~~~powershell
.\mvnw.cmd -q -DskipTests package
java -jar target/runner-args-demo-1.0.0.jar --mode=batch --tag=one --tag=two --dry-run report.csv
~~~

Lệnh dùng **java -jar** sau khi build nhằm tránh nhầm lẫn các tham số của Maven/plugin với tham số truyền tới chương trình Java. Các token trong lệnh đều không có khoảng trắng nên hoạt động tương tự trên các shell phổ biến.

**Các dòng chương trình tự in theo đúng thứ tự kỳ vọng:**

~~~text
PARSED | names=[dry-run, mode, tag]
PARSED | mode=[batch]
PARSED | tags=[one, two]
PARSED | dry-run=true
PARSED | dry-run values=[]
PARSED | missing=null
PARSED | positionals=[report.csv]
PARSED | source=[--mode=batch, --tag=one, --tag=two, --dry-run, report.csv]
RAW | args=[--mode=batch, --tag=one, --tag=two, --dry-run, report.csv]
MAIN | active=true
~~~

Log của Spring Boot, Maven hoặc JVM có thể xen giữa, nhưng **các dòng in từ mã mẫu** có nội dung như trên khi chạy đúng lệnh và không có tùy chỉnh runner khác.

**Tại sao kết quả đúng?**

- **ParsedRunner** mang **@Order(10)** nên chạy trước **RawRunner** mang **@Order(20)**.
- **ApplicationArguments** nhận ra ba tên option **mode**, **tag**, **dry-run**; dùng **TreeSet** khi in để thứ tự chữ cái ổn định.
- **--tag=one --tag=two** thành danh sách hai phần tử.
- **--dry-run** là flag có mặt nên **containsOption** là true nhưng danh sách value rỗng.
- **missing** không xuất hiện nên **getOptionValues** trả về null.
- **report.csv** là non-option; với **getSourceArgs** và RawRunner, mọi token vẫn tồn tại theo thứ tự ban đầu.
- **MAIN** chỉ in sau khi cả hai runner đồng bộ đã hoàn tất và **SpringApplication.run(...)** trả về context đang active.

**Lưu ý:** ứng dụng mẫu dùng **WebApplicationType.NONE** và **try-with-resources** để thoát chương trình sạch sau ví dụ CLI. Với một web service cần phục vụ HTTP lâu dài, đừng đóng context ngay sau **run(...)** như vậy.

## 6. Quyết định trong các tình huống thực tế

### 6.1. Dùng ApplicationRunner cho lệnh có option và đối số vị trí

Ví dụ tiện ích import:

~~~text
java -jar importer.jar --format=csv --dry-run data/input.csv
~~~

Bạn muốn:

- **format** có đúng một giá trị như **csv** hoặc **json**.
- **dry-run** là flag hiện diện.
- **data/input.csv** là đường dẫn vị trí duy nhất.

Đây là mô hình phù hợp với ApplicationRunner:

~~~java
@Override
public void run(ApplicationArguments args) {
    List<String> formats = args.getOptionValues("format");

    if (formats == null || formats.size() != 1) {
        throw new IllegalArgumentException(
                "Phải chỉ định đúng một --format=csv|json");
    }

    String format = formats.get(0);
    if (!format.equals("csv") && !format.equals("json")) {
        throw new IllegalArgumentException(
                "Format không hỗ trợ: " + format);
    }

    if (args.getNonOptionArgs().size() != 1) {
        throw new IllegalArgumentException(
                "Cần đúng một đường dẫn tệp đầu vào");
    }

    boolean dryRun = args.containsOption("dry-run");
    String inputFile = args.getNonOptionArgs().get(0);

    // Gọi service import đã được DI vào runner.
}
~~~

Đây là **snippet** dùng trong một class implements ApplicationRunner và cần import **List**. Logic validation nên tách thành hàm/class riêng nếu phức tạp, để kiểm thử mà không phải start toàn bộ context.

### 6.2. Dùng CommandLineRunner để chuyển tiếp nguyên token

Giả sử ứng dụng nhúng một parser đặc thù, cần giữ mọi token, kể cả **-v**, **--**, **-Dkey=value** và thứ tự ban đầu:

~~~java
@Component
class CustomCliRunner implements CommandLineRunner {

    private final CustomArgumentParser parser;

    CustomCliRunner(CustomArgumentParser parser) {
        this.parser = parser;
    }

    @Override
    public void run(String... args) {
        parser.execute(args);
    }
}
~~~

Đây là **snippet thiết kế**, với **CustomArgumentParser** là interface/class của ứng dụng do bạn tự xây dựng hoặc chọn từ thư viện phù hợp. Không phải chương trình độc lập. CommandLineRunner thích hợp vì parser có thể có cú pháp khác với **--name[=value]** và cần giữ nguyên token.

**Không nên tự viết lại parser phức tạp từ đầu** nếu CLI có subcommands, trợ giúp, kiểm tra type, mutually exclusive options hay quoting khó. Một thư viện CLI chuyên dụng có thể làm nhiệm vụ đó tốt hơn; CommandLineRunner chỉ là cầu nối đến parser.

### 6.3. Nếu chỉ cần một thuộc tính cấu hình?

Giả sử web service cần cấu hình **app.batch-size** có thể đặt trong:

~~~properties
app.batch-size=500
~~~

và ghi đè bằng:

~~~bash
java -jar app.jar --app.batch-size=1000
~~~

Nếu đây là **cấu hình ứng dụng**, thường nên dùng **@ConfigurationProperties** để bind và validate, hoặc **Environment**. Spring Boot theo mặc định đưa command-line option vào một **CommandLinePropertySource**, giúp property source từ CLI tham gia hệ thống ưu tiên cấu hình.

**ApplicationArguments** phù hợp khi cần chính xác các token/flag/repeated option của **lần chạy này**. **@ConfigurationProperties** phù hợp khi giá trị là **cấu hình có cấu trúc** nhận từ nhiều nguồn. Không nên dùng ApplicationRunner để tự phân tích lại tất cả file YAML, biến môi trường và hệ thống property sources.

### 6.4. ApplicationRunner vẫn lấy được String[] nếu cần

Chọn ApplicationRunner không làm mất thông tin gốc:

~~~java
@Override
public void run(ApplicationArguments args) {
    String[] original = args.getSourceArgs();
    // Có thể chuyển tiếp original cho API cần String[].
}
~~~

Nếu một runner cần **cả option có cấu trúc lẫn raw array**, **ApplicationRunner** là lựa chọn tự nhiên vì cung cấp **cả hai**. CommandLineRunner không cung cấp bộ method đã parse ngay trong tham số callback của nó.

## 7. Kiểm thử ApplicationArguments mà không cần khởi động Spring

Spring Boot cung cấp **DefaultApplicationArguments**, một implementation dùng cùng cú pháp option để bạn có thể test logic phân tích đầu vào.

Trong dự án có dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo **src/test/java/com/example/runner/ArgumentsParsingTest.java**:

~~~java
package com.example.runner;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.DefaultApplicationArguments;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ArgumentsParsingTest {

    @Test
    void parsesOptionsFlagsAndPositionals() {
        String[] source = {
                "--mode=batch",
                "--tag=one",
                "--tag=two",
                "--dry-run",
                "report.csv"
        };

        ApplicationArguments args =
                new DefaultApplicationArguments(source);

        assertArrayEquals(source, args.getSourceArgs());
        assertEquals(List.of("batch"), args.getOptionValues("mode"));
        assertEquals(List.of("one", "two"), args.getOptionValues("tag"));
        assertTrue(args.containsOption("dry-run"));
        assertEquals(List.of(), args.getOptionValues("dry-run"));
        assertNull(args.getOptionValues("missing"));
        assertEquals(List.of("report.csv"), args.getNonOptionArgs());
        assertFalse(args.containsOption("missing"));
    }

    @Test
    void missingValueIsDifferentFromMissingOption() {
        ApplicationArguments args =
                new DefaultApplicationArguments(
                        "--format",
                        "--other=csv",
                        "input.csv");

        assertTrue(args.containsOption("format"));
        assertEquals(List.of(), args.getOptionValues("format"));
        assertNull(args.getOptionValues("not-provided"));
        assertEquals(List.of("csv"), args.getOptionValues("other"));
        assertEquals(List.of("input.csv"), args.getNonOptionArgs());
    }
}
~~~

Lệnh chạy:

~~~bash
mvn test
~~~

**Các test này kiểm tra trực tiếp semantics của ApplicationArguments**: giữ nguồn gốc, option lặp, cờ không giá trị, phân biệt **null** và **[]**, cùng non-option args. Không cần mở HTTP server hay gọi SpringApplication.run để biết parser nhận đúng token.

### 7.1. Kiểm thử logic nghiệp vụ của runner

Một bước tốt hơn là **tách phần giải mã và kiểm tra tham số** thành một lớp nhỏ:

~~~text
ApplicationRunner.run(ApplicationArguments)
       |
       v
OptionsParser.parse(ApplicationArguments)
       |
       v
ImportOptions(format, dryRun, inputFile)
       |
       v
ImportService.execute(ImportOptions)
~~~

Lúc đó:

- Unit test **OptionsParser** dùng **DefaultApplicationArguments** và assert **ImportOptions** hoặc exception.
- Unit test **ImportService** xử lý nghiệp vụ bằng dữ liệu thuần Java.
- Chỉ viết một vài integration test để xác nhận Spring tạo runner bean, tiêm service đúng và gọi nó trong startup khi cần.

Tách như vậy giúp runner không trở thành một class vừa parse args vừa gọi network/database vừa xử lý business logic, khó kiểm tra và dễ làm chậm startup.

### 7.2. Kiểm thử CommandLineRunner

Với CommandLineRunner nhận **String[]**, cách unit test dễ nhất là gọi phần logic xử lý raw array trực tiếp, tránh khởi động toàn bộ Spring context:

~~~java
String[] raw = {"-v", "--", "--literal"};
customParser.execute(raw);
// Assert kết quả của parser đối với từng token đã cho.
~~~

Đây là snippet giả định có **customParser** của ứng dụng; không phải test hoàn chỉnh. Nếu runner phụ thuộc DI và bạn muốn xác nhận thứ tự startup, dùng test với SpringApplication/context thật, không chỉ test parser.

### 7.3. Thử nhiều lần với dữ liệu xấu

Một bộ test CLI đáng tin nên có:

- Không truyền tham số.
- Thiếu option bắt buộc.
- **--key** có mặt nhưng không có giá trị.
- **--key=** có giá trị rỗng.
- Option duy nhất xuất hiện hai lần.
- Cờ boolean được truyền thành **--flag=false**.
- Non-option có khoảng trắng hoặc Unicode và cách shell tạo token.
- Option lạ hoặc sai chính tả.
- Tên tệp bắt đầu bằng hai dấu gạch ngang, cần xử lý qua **--** nếu phù hợp.

Đặc biệt nên chọn một **chính sách rõ ràng** cho option lạ: từ chối, cảnh báo, hay cho phép chuyển tiếp. **getOptionNames()** có thể giúp xác định những tên option thực sự xuất hiện để validate theo allowlist.

## 8. Cùng dữ liệu nhưng Environment khác ApplicationArguments thế nào?

Khi ứng dụng chạy với:

~~~text
--app.mode=import --verbose data.csv
~~~

**ApplicationArguments** trả lời:

- Có option **app.mode** không? Có.
- Những value cụ thể cho option **app.mode** là gì? **["import"]**.
- Có cờ **verbose** không? Có; không có giá trị.
- Tham số vị trí nào được cung cấp? **["data.csv"]**.

**Environment** trả lời một câu hỏi khác: sau khi kết hợp tất cả PropertySource theo ưu tiên, giá trị hiện tại của property **app.mode** là gì? Có thể là giá trị từ CLI, system properties, environment variables hoặc Config Data.

| Trường hợp | Nên dùng |
| --- | --- |
| Cần biết **CLI có chủ động truyền --app.mode hay không** | **ApplicationArguments.containsOption("app.mode")** |
| Cần biết **mọi giá trị --tag lặp lại** | **ApplicationArguments.getOptionValues("tag")** |
| Cần giữ **thứ tự token gốc** | **ApplicationArguments.getSourceArgs()** hoặc **CommandLineRunner String[]** |
| Cần đọc **cấu hình cuối cùng** sau khi áp dụng precedence | **Environment** hoặc **@ConfigurationProperties** |
| Cần binding kiểu số, duration, boolean, validation theo cấu hình | **@ConfigurationProperties** / Boot Binder |
| Cần subcommands phức tạp (**import**, **export**, **migrate**) | **Parser CLI riêng**, có thể được gọi qua CommandLineRunner |

### 8.1. Khi vô hiệu hóa CLI property source

SpringApplication có API **setAddCommandLineProperties(false)** để không thêm tham số CLI làm PropertySource của Environment. Điều này **không có nghĩa String[] hoặc ApplicationArguments biến mất**: SpringApplication vẫn nhận các token và cung cấp chúng cho runner. Hai cơ chế cần tách biệt:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

Đây là snippet, giả định có lớp **MyApplication**. Khi tắt CLI property source, một cấu hình như **--app.mode=import** không còn tự ghi đè **app.mode** trong Environment theo đường CLI property source thông thường, nhưng ApplicationArguments vẫn cho phép xem option thuộc tham số của lần chạy.

Vì vậy, đừng lẫn **parsing arguments** với **property resolution**.

### 8.2. Tránh ghi bí mật ra log

Cả **String[] args** và **ApplicationArguments.getSourceArgs()** có thể chứa password, token, API key hoặc các giá trị nhạy cảm. Ví dụ đã in token gốc để học cách phân biệt hai API; **không copy đoạn log raw args này vào production**.

Trong production, log nên giới hạn vào các tên option an toàn và giá trị đã che. Cấu hình chứa bí mật nên dùng secret store/nguồn cấu hình phù hợp, thay vì để bí mật xuất hiện trên command line và có nguy cơ hiển thị trong process list hoặc log.

## 9. Những lỗi phổ biến khi chọn và đọc tham số

### 9.1. Dùng getOptionValues(...).get(0) ngay lập tức

Nếu option vắng mặt, kết quả là **null**; nếu có mặt nhưng thiếu value, danh sách rỗng. Kiểm tra cả hai trạng thái và số lượng phần tử trước khi gọi get(0).

### 9.2. Hiểu sai --name value

Với simple parser của Spring, giá trị option nên ở dạng **--name=value** trong cùng token. **--name value** là một option không giá trị và một non-option, không phải hai phần của cùng một option.

### 9.3. Coi containsOption là parse boolean

**containsOption("enabled")** là **true** với cả **--enabled** và **--enabled=false**. Nếu cần boolean thực sự, hãy đọc value và parse theo hợp đồng CLI.

### 9.4. Mất các option lặp lại

**getOptionValues("tag")** trả về **List<String>**. Nếu chỉ lấy phần tử đầu mà không nêu chính sách, ứng dụng có thể bỏ mất các tag được cung cấp sau. Thiết kế theo một hoặc nhiều giá trị và validate thích hợp.

### 9.5. Tự viết split(" ") trên chuỗi câu lệnh

**String[] args** đã được shell/JVM chia thành các token theo quy tắc gọi chương trình. Nếu bạn tự nối lại rồi **split(" ")**, những giá trị có khoảng trắng được quote có thể bị phá vỡ. Dùng nguyên các token từ args hoặc parser chuyên dụng.

### 9.6. Trộn nhầm tham số JVM và tham số ứng dụng

Ví dụ:

~~~bash
java -Xmx512m -jar app.jar --mode=batch
~~~

**-Xmx512m** là tùy chọn JVM, không phải token SpringApplication nhận trong **main(String[] args)**. Runner chỉ nhận các application arguments được chuyển tới SpringApplication.run. Điều tương tự xảy ra với các cờ dành riêng cho Maven/Gradle wrapper.

### 9.7. Dựa vào thứ tự ApplicationRunner trước CommandLineRunner

Cả hai nằm trong cùng giai đoạn. Nếu cần thứ tự, dùng **@Order** hoặc **Ordered**; nếu một task phụ thuộc kết quả task khác, thiết kế dependency rõ ràng thay vì trông chờ vào ngẫu nhiên.

### 9.8. Runner xử lý lâu hoặc ném lỗi không kiểm soát

Runner có thể làm chậm readiness; exception có thể khiến startup thất bại. Chọn timeout, chiến lược lỗi, retry và mức độ bắt buộc của task. Nếu chỉ cần chạy một tác vụ nền sau startup, đừng chặn runner bằng một vòng lặp vô hạn.

### 9.9. Cố dùng ApplicationArguments để xử lý CLI phức tạp

**ApplicationArguments** có parser option đơn giản, không phải framework đầy đủ cho lệnh con, help message, validation nhiều tùy chọn và completion. Với CLI phức tạp, dùng parser chuyên dụng và truyền raw args qua CommandLineRunner, hoặc kiến trúc CLI phù hợp khác.

### 9.10. Chọn String[] chỉ vì muốn in tham số

Nếu muốn kiểm tra cờ, đọc option nhiều giá trị và non-options mà không có parser riêng, dùng **ApplicationRunner** rõ ràng hơn. Nó vẫn giữ dữ liệu gốc qua **getSourceArgs()**.

## 10. Checklist chọn lựa trước khi viết runner

- [ ] Cần cú pháp option chuẩn **--name[=value]** hay cú pháp riêng?
- [ ] Cần **option names, flags, nhiều values, non-options**? Nếu có, ưu tiên ApplicationArguments.
- [ ] Cần **token nguyên bản và thứ tự**? String[] hoặc getSourceArgs.
- [ ] Có cần phân biệt **null**, **[]**, **[""]** không?
- [ ] Đã kiểm tra trường hợp thiếu, lặp hoặc giá trị sai định dạng chưa?
- [ ] Có đang dùng **containsOption** để đọc boolean sai nghĩa không?
- [ ] Giá trị là **cấu hình từ nhiều nguồn** hay là tham số CLI cụ thể?
- [ ] Có tránh log raw args chứa secret không?
- [ ] Runner có chạy trong khoảng thời gian hợp lý trước readiness không?
- [ ] Nếu nhiều runner có phụ thuộc, thứ tự **@Order/Ordered** đã được xác định chưa?
- [ ] Parser/validator được tách để có thể unit test không cần khởi động Spring chưa?

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Một ứng dụng cần option **--format=csv**, flag **--dry-run** và một đường dẫn tệp vị trí. Chọn runner nào?

**Đáp án:** **ApplicationRunner** thường phù hợp vì **ApplicationArguments** đã cung cấp **getOptionValues("format")**, **containsOption("dry-run")** và **getNonOptionArgs()**.

**Câu 2.** CommandLineRunner.run(String... args) có nhận nội dung khác về mặt token so với ApplicationArguments.getSourceArgs() không?

**Đáp án:** Trong lần SpringApplication khởi động thông thường với cùng raw arguments, chúng phản ánh **các token đầu vào gốc tương ứng**. ApplicationArguments còn có các truy vấn cấu trúc. **String...** chỉ là varargs Java, biểu diễn bằng String[].

**Câu 3.** **getOptionValues("trace")** trả về **null** khi nào và trả về **[]** khi nào?

**Đáp án:** **null** khi option không xuất hiện; **[]** khi option xuất hiện nhưng không có value, ví dụ **--trace**.

**Câu 4.** **--enabled=false** có làm **containsOption("enabled")** trả về false không?

**Đáp án:** **Không**. Option vẫn xuất hiện, nên containsOption trả về true; muốn boolean phải đọc và parse giá trị.

**Câu 5.** Với **--tag=a --tag=b**, có nên dùng **getOptionValues("tag").get(0)** rồi bỏ phần còn lại?

**Đáp án:** Chỉ khi ứng dụng công khai chính sách lấy giá trị đầu tiên. Nếu tag là danh sách, xử lý cả hai; nếu chỉ cho phép một tag, hãy từ chối đầu vào có nhiều value.

**Câu 6.** **--output result.txt** có phải option output mang value result.txt theo parser Spring mặc định không?

**Đáp án:** Không. **--output** được nhận là option không có value; **result.txt** là non-option. Dùng **--output=result.txt**.

**Câu 7.** Có thể dùng ApplicationRunner mà vẫn chuyển String[] raw cho thư viện legacy không?

**Đáp án:** Có, qua **ApplicationArguments.getSourceArgs()**.

**Câu 8.** Tại sao **@ConfigurationProperties** có thể tốt hơn đọc ApplicationArguments nếu ứng dụng cần một timeout cấu hình?

**Đáp án:** Vì timeout là cấu hình có thể đến từ Config Data, Environment, CLI và có thể bind kiểu/validate thống nhất. ApplicationArguments chỉ mô tả tham số lần chạy, không tự làm cấu hình nhiều nguồn.

**Câu 9.** Boot có tự gọi ApplicationRunner trước mọi CommandLineRunner không?

**Đáp án:** Không. Cả hai được sắp xếp theo order; nên dùng **@Order/Ordered** nếu thứ tự quan trọng.

**Câu 10.** Vì sao unit test **DefaultApplicationArguments** không cần start toàn bộ Spring Boot?

**Đáp án:** Vì nó là đối tượng Java cung cấp trực tiếp logic parsing arguments; có thể tạo bằng String[] và assert các kết quả trả về mà không cần ApplicationContext.

## 12. Kết luận và tài liệu chính thức

**ApplicationRunner** và **CommandLineRunner** chạy ở cùng thời điểm sau refresh, trước **ApplicationReadyEvent**; **khác biệt chính là biểu diễn tham số**. Chọn **ApplicationArguments** để xử lý các option **--name[=value]**, cờ, giá trị lặp, non-option và vẫn giữ raw args. Chọn **String[]** khi phải chuyển tiếp nguyên token hoặc sử dụng bộ phân tích cú pháp khác.

Đặc biệt nhớ ba trạng thái của **getOptionValues()**: **null** (không có option), **[]** (có option nhưng không có value), và **danh sách có phần tử** (có value). Dùng validation, tách parser khỏi logic nghiệp vụ, không log secrets, và không để runner kéo dài startup không cần thiết.

Tài liệu chính thức (theo Spring Boot 3.3.13 / Spring Framework 6.1):

- **Spring Boot 3.3 — SpringApplication, Accessing Application Arguments, Using ApplicationRunner or CommandLineRunner:** https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- **Spring Boot 3.3 — ApplicationRunner API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- **Spring Boot 3.3 — CommandLineRunner API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html
- **Spring Boot 3.3 — ApplicationArguments API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- **Spring Boot 3.3 — DefaultApplicationArguments API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/DefaultApplicationArguments.html
- **Spring Framework 6.1 — SimpleCommandLinePropertySource API:** https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/env/SimpleCommandLinePropertySource.html