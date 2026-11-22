# Đọc đối số gốc bằng getSourceArgs trong Spring Boot

## 1. getSourceArgs là gì?

Khi chạy một ứng dụng Spring Boot, người dùng có thể truyền các tham số:

~~~bash
java -jar app.jar --mode=batch --tag=one --tag=two --dry-run "report 2026.csv"
~~~

Một chương trình có thể cần truy cập **chính xác từng token ứng dụng nhận được**, gồm option, cờ, tham số vị trí và thứ tự chúng xuất hiện. Interface **org.springframework.boot.ApplicationArguments** cung cấp method:

~~~java
String[] originalTokens = arguments.getSourceArgs();
~~~

**getSourceArgs() trả về String[] gồm các đối số chưa qua phân loại của lần gọi SpringApplication.run(...)**. Ví dụ trên, khi dùng **Arrays.toString(originalTokens)**, kết quả là:

~~~text
[--mode=batch, --tag=one, --tag=two, --dry-run, report 2026.csv]
~~~

Mảng gồm năm phần tử; **report 2026.csv** là một phần tử có chứa khoảng trắng. Hai token **--tag=one** và **--tag=two** vẫn tồn tại đúng vị trí và chưa bị gộp thành một danh sách.

**Chú ý về chữ gốc:** đây là các token **được truyền vào SpringApplication**, không phải nguyên văn cả dòng lệnh trước khi shell xử lý. Các dấu nháy phục vụ quoting trong shell thường đã bị bỏ trước khi Java nhận tham số. Tương tự, getSourceArgs không tự thu thập các thuộc tính trong application.properties, biến môi trường hoặc JVM options.

Bài học tập trung vào cơ chế, thời điểm, cách dùng và kiểm thử **getSourceArgs()** trên Spring Boot 3.3.x với Java 17+.

## 2. So sánh getSourceArgs với các API khác của ApplicationArguments

**ApplicationArguments** cho phép vừa xem token gốc, vừa xem kết quả Spring phân tích cú pháp option.

| API | Dữ liệu | Mục đích |
| --- | --- | --- |
| **getSourceArgs()** | **String[]** gồm mọi token ban đầu | Bảo toàn token và thứ tự |
| **getOptionNames()** | **Set<String>** tên option | Liệt kê tên các option dạng **--name** |
| **containsOption(name)** | **boolean** | Kiểm tra option có mặt |
| **getOptionValues(name)** | **List<String>** hoặc **null** | Lấy các value của option |
| **getNonOptionArgs()** | **List<String>** | Lấy token không được parser xem là option |

Ví dụ đầu vào:

~~~text
--mode=batch --tag=one --tag=two --dry-run report.csv
~~~

Các kết quả tương ứng:

| Biểu thức | Kết quả |
| --- | --- |
| **Arrays.toString(args.getSourceArgs())** | **[--mode=batch, --tag=one, --tag=two, --dry-run, report.csv]** |
| **getOptionValues("mode")** | **[batch]** |
| **getOptionValues("tag")** | **[one, two]** |
| **containsOption("dry-run")** | **true** |
| **getOptionValues("dry-run")** | **[]** |
| **getOptionValues("unknown")** | **null** |
| **getNonOptionArgs()** | **[report.csv]** |

Có hai điểm quan trọng:

1. **getSourceArgs() không làm mất thông tin** khi framework cung cấp API phân loại option; cả hai cách nhìn cùng tồn tại.
2. **getSourceArgs() không parse giá trị**. Nó trả chuỗi **--mode=batch**, không trả riêng **batch**. Muốn ngữ nghĩa option, dùng các method phân loại hoặc parser khác.

### 2.1. Không phụ thuộc thứ tự của getOptionNames

**getSourceArgs()** là một mảng có thứ tự rõ ràng. Ngược lại **getOptionNames()** trả một **Set**; không nên suy ra thứ tự token gốc từ thứ tự duyệt set. Nếu cần xem mọi token theo đúng vị trí xuất hiện, dùng **getSourceArgs()**.

### 2.2. Option bị lặp lại

Với đầu vào:

~~~text
--tag=one --mode=batch --tag=two
~~~

getSourceArgs cho:

~~~text
[--tag=one, --mode=batch, --tag=two]
~~~

getOptionValues("tag") cho:

~~~text
[one, two]
~~~

Danh sách values hữu ích khi xử lý nhiều giá trị cùng tên, nhưng không còn thể hiện **mode** xuất hiện xen giữa hai token tag. Khi có một parser tùy chỉnh cần đọc thứ tự xen kẽ, mảng gốc là đầu vào phù hợp hơn.

## 3. Từ shell đến SpringApplication: raw nghĩa là gì?

Trình tự thường gặp:

~~~text
Dòng lệnh người dùng nhập
    |
    | shell xử lý quote, escape, expansion...
    v
JVM gọi main(String[] args)
    |
    | code chuyển String[] vào SpringApplication.run(...)
    v
SpringApplication xây dựng ApplicationArguments
    |
    +--> getSourceArgs()       : các token chưa phân loại
    |
    +--> getOptionValues(...) : giá trị sau parsing
    |
    +--> getNonOptionArgs()   : các token không phải option
~~~

Ví dụ:

~~~bash
java -jar app.jar "--description=Monthly Report"
~~~

Phần tử Java thông thường là:

~~~text
--description=Monthly Report
~~~

Đây **là một token**, không phải hai token. Dấu nháy chỉ giúp shell giữ dấu cách bên trong một phần tử; chúng **không phải ký tự còn nằm trong chuỗi Java** sau khi shell đã xử lý.

**Không thể dùng getSourceArgs để khôi phục cách người dùng đặt dấu nháy, nhiều khoảng trắng giữa các token hoặc các phép expansion đã được shell thực hiện.** Dữ liệu gốc ở tầng Spring là mảng Java, không phải bản ghi đầy đủ lịch sử terminal.

### 3.1. Không nhất thiết giống main args nếu code thay thế đối số

Code thông thường:

~~~java
public static void main(String[] args) {
    SpringApplication.run(App.class, args);
}
~~~

Khi đó token mà ApplicationArguments nhận tương ứng với **args** của main. Nhưng nếu lập trình viên làm:

~~~java
public static void main(String[] args) {
    String[] replacement = {"--mode=internal", "input.csv"};
    SpringApplication.run(App.class, replacement);
}
~~~

thì getSourceArgs thuộc lần SpringApplication này phản ánh **replacement**, không phải tham số nguyên bản mà terminal đã truyền vào main.

Hai đoạn trên là snippets giả định có lớp **App** và import **SpringApplication**.

### 3.2. JVM options không phải program arguments

~~~bash
java -Xmx512m -Dregion=asia -jar app.jar --mode=batch
~~~

**-Xmx512m** và **-Dregion=asia** đứng trước **-jar** là JVM options. **--mode=batch** đứng sau JAR là program argument truyền tới ứng dụng. getSourceArgs trong ví dụ thông thường phản ánh **--mode=batch**, không tự thêm các JVM options.

Nếu một token có tiền tố **-D** lại nằm sau tên JAR, nó là program argument bình thường, không tự tương đương với system property được thiết lập qua JVM launcher. Vị trí trong lệnh gọi có ý nghĩa.

### 3.3. Cấu hình trong file và biến môi trường không tự xuất hiện

Giả sử:

~~~properties
app.mode=nightly
~~~

được đặt trong application.properties, còn chương trình khởi chạy không có arguments. **Environment.getProperty("app.mode")** có thể đọc **nightly**, nhưng **getSourceArgs()** vẫn là mảng rỗng.

Không dùng raw source args để xác định toàn bộ cấu hình cuối cùng từ file, command line, OS environment, system properties và Config Data. Đó là trách nhiệm của **Environment**, **@ConfigurationProperties** và cơ chế binding.

## 4. Những token cần chú ý trong thực tế

### 4.1. Option có giá trị theo cú pháp Spring

Spring Boot có hỗ trợ cú pháp:

~~~text
--name=value
~~~

để phân tích option. Với:

~~~text
--mode batch
~~~

getSourceArgs giữ **hai phần tử**:

~~~text
[--mode, batch]
~~~

Nhưng khi dùng simple command-line parser của Spring, **--mode** là option **không có value**, còn **batch** là non-option. Đừng suy đoán chúng tương đương **--mode=batch**.

Nếu CLI thực sự dùng cú pháp **--mode batch** hay **-m batch**, mảng gốc có thể được chuyển tới parser chuyên dụng cho hợp đồng ấy.

### 4.2. Cờ không có value

~~~text
--dry-run
~~~

Raw array giữ nguyên **--dry-run**. ApplicationArguments diễn giải:

- **containsOption("dry-run") = true**
- **getOptionValues("dry-run") = []**

Khi option hoàn toàn không có, **getOptionValues("dry-run") = null**. Phân biệt rõ **vắng mặt** và **có mặt nhưng không có value**.

Không gọi **getOptionValues("mode").get(0)** khi chưa kiểm tra null, danh sách rỗng và số lượng value.

### 4.3. Boolean chưa được parse

Token:

~~~text
--dry-run=false
~~~

vẫn là một option **dry-run có mặt**: **containsOption("dry-run")** trả về true. Nếu nghiệp vụ cần giá trị boolean, hãy parse **getOptionValues("dry-run")** theo hợp đồng của ứng dụng hoặc dùng configuration binding. Đừng suy diễn false từ containsOption.

### 4.4. Token có khoảng trắng, Unicode, dấu bằng

getSourceArgs giữ từng chuỗi Java nhận được, ví dụ:

~~~text
--title=Báo cáo tháng 11
--signature=a=b=c
đơn-hàng-001.csv
~~~

Nếu shell đã tạo ba token với nội dung trên thì array vẫn gồm ba phần tử. Không dùng **split(" ")** để chia lại cả dòng vì sẽ phá chuỗi có khoảng trắng. Không dùng **split("=")** thiếu giới hạn nếu value cũng có dấu bằng.

### 4.5. Mảng rỗng và kiểm tra chỉ số

Nếu không có program arguments, getSourceArgs trả mảng có **length = 0**. Code an toàn:

~~~java
String[] source = args.getSourceArgs();

if (source.length == 0) {
    System.out.println("No program arguments");
} else {
    System.out.println(source[0]);
}
~~~

Đoạn này là snippet bên trong phương thức có biến **args** kiểu ApplicationArguments. Truy cập **source[0]** khi mảng rỗng gây **ArrayIndexOutOfBoundsException**.

## 5. Ví dụ Java 17+ chạy được: đối chiếu raw và parsed

Chương trình sau dùng **Spring Boot 3.3.13**, **Java 17+** và Maven. Nó chứa một **ApplicationRunner** để đọc getSourceArgs và các API đã parse, cùng một **CommandLineRunner** nhận String... để đối chiếu. Hai runner do Spring quản lý như bean, chạy sau khi context refresh thành công.

### 5.1. Tạo dự án

~~~text
source-args-demo/
  pom.xml
  src/main/java/com/example/args/SourceArgsDemo.java
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>source-args-demo</artifactId>
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

**src/main/java/com/example/args/SourceArgsDemo.java**:

~~~java
package com.example.args;

import java.util.Arrays;

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
public class SourceArgsDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(SourceArgsDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN | active=" + context.isActive());
        }
    }
}

@Component
@Order(10)
class SourceArgumentsRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        String[] raw = args.getSourceArgs();

        System.out.println("SOURCE | " + Arrays.toString(raw));
        System.out.println("COUNT | " + raw.length);
        System.out.println("FIRST | "
                + (raw.length == 0 ? "<none>" : raw[0]));
        System.out.println("MODE | " + args.getOptionValues("mode"));
        System.out.println("TAG | " + args.getOptionValues("tag"));
        System.out.println("DRY-RUN | " + args.containsOption("dry-run"));
        System.out.println("FILES | " + args.getNonOptionArgs());
    }
}

@Component
@Order(20)
class RawCommandRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("COMMAND | " + Arrays.toString(args));
    }
}
~~~

**Vì sao ba top-level classes trong một file hợp lệ?** Java cho phép một public top-level class là **SourceArgsDemo** và hai class không public cùng package trong cùng file. **@Component** nằm trong package được quét, nên hai runner được Spring đăng ký. **@Order(10)** và **@Order(20)** tạo thứ tự gọi rõ ràng.

### 5.2. Build và chạy

Tại thư mục dự án, sử dụng JDK 17+, Maven 3.9+:

~~~bash
mvn -q -DskipTests package
java -jar target/source-args-demo-1.0.0.jar --mode=batch --tag=one --tag=two --dry-run "report 2026.csv"
~~~

Trên Windows PowerShell, khi dự án có Maven Wrapper, có thể build bằng:

~~~powershell
.\mvnw.cmd -q -DskipTests package
java -jar target/source-args-demo-1.0.0.jar --mode=batch --tag=one --tag=two --dry-run "report 2026.csv"
~~~

**Các dòng do ứng dụng tự in, theo thứ tự kỳ vọng:**

~~~text
SOURCE | [--mode=batch, --tag=one, --tag=two, --dry-run, report 2026.csv]
COUNT | 5
FIRST | --mode=batch
MODE | [batch]
TAG | [one, two]
DRY-RUN | true
FILES | [report 2026.csv]
COMMAND | [--mode=batch, --tag=one, --tag=two, --dry-run, report 2026.csv]
MAIN | active=true
~~~

Log Spring Boot hoặc build tool có thể xuất hiện xen giữa. Không nên kỳ vọng toàn bộ stdout chỉ có đúng các dòng trên; đây là **các dòng được mã ví dụ chủ động in**.

### 5.3. Giải thích stdout

1. Shell chuyển **"report 2026.csv"** thành **một token** chứa dấu cách; vì vậy mảng có năm phần tử.
2. **SpringApplication.run(args)** giữ input để xây dựng **ApplicationArguments**.
3. **SourceArgumentsRunner** đọc raw token bằng getSourceArgs, đồng thời dùng các method đã parse.
4. **getOptionValues("mode")** là **[batch]**; option **tag** xuất hiện hai lần nên có **[one, two]**.
5. **containsOption("dry-run")** là true, vì cờ xuất hiện.
6. **getNonOptionArgs()** có **report 2026.csv**.
7. **RawCommandRunner** nhận các token tương đương qua **String... args**. **@Order** giúp thứ tự hai runner ổn định trong ví dụ.
8. **SpringApplication.run(...)** chỉ trả về sau khi các runner đồng bộ chạy xong; vì vậy **MAIN** in sau. **try-with-resources** đóng context của chương trình CLI ngay sau đó.

**Không đóng context ngay sau run trong một ứng dụng web cần tiếp tục phục vụ HTTP**; pattern trên thích hợp cho bài thực hành non-web.

## 6. getSourceArgs trong ApplicationRunner, CommandLineRunner và các bean

### 6.1. Đọc ngay trong ApplicationRunner

~~~java
@Component
class StartupRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        String[] rawTokens = args.getSourceArgs();
        // Parse/validate theo yêu cầu thực tế.
    }
}
~~~

Đây là snippet trong một package có các import tương ứng. **ApplicationRunner** là lựa chọn thuận tiện nếu một tác vụ cần **cả raw array và các truy vấn đã parse**.

### 6.2. So với CommandLineRunner

~~~java
@Component
class AnotherRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        String[] rawTokens = args;
        // Dùng rawTokens khi không cần API parsed của Boot.
    }
}
~~~

**String...** về bản chất là **String[]**. Trong lần SpringApplication chạy thông thường, CommandLineRunner nhận các program arguments tương ứng; chọn interface nào chủ yếu tùy **nhu cầu phân tích đầu vào**.

Không có thứ tự mặc định “ApplicationRunner luôn chạy trước CommandLineRunner”. Nếu cần thứ tự, dùng **@Order** hoặc **Ordered**.

### 6.3. Inject ApplicationArguments vào bean bình thường

Spring Boot cũng cho phép inject **ApplicationArguments**:

~~~java
@Component
class StartupInputSnapshot {

    private final String[] raw;

    StartupInputSnapshot(ApplicationArguments args) {
        this.raw = args.getSourceArgs().clone();
    }

    public String[] getRawCopy() {
        return raw.clone();
    }
}
~~~

Đoạn này là snippet, cần các import **@Component** và **ApplicationArguments**. Nó không tự kích hoạt runner. Nó chỉ lưu một **snapshot** để bean khác lấy bản sao khi thực sự cần.

**Tại sao clone?** Mảng **String[]** có thể bị thay đổi ở phía code sở hữu reference. API không nên được dùng như kênh chỉnh sửa cấu hình. Clone giúp lưu **bản sao có ownership rõ**. Vì phần tử của mảng là **String** bất biến nên clone mảng đủ để tách danh sách phần tử trong ví dụ này.

### 6.4. Không giả định mọi Spring context đều có bean ApplicationArguments

Khi ứng dụng được bootstrapped bằng **SpringApplication**, Boot đăng ký đối tượng ApplicationArguments để inject. Nhưng nếu bạn tự tạo một **AnnotationConfigApplicationContext** thuần rồi refresh mà không dùng SpringApplication, không nên mặc định context đó đã có bean ApplicationArguments. Khi unit test API, có thể tự tạo **DefaultApplicationArguments** mà không cần context.

## 7. Ứng dụng vào parsing và validation

### 7.1. Khi nào nên dùng raw array?

Dùng **getSourceArgs()** khi cần:

- Chuyển nguyên token sang CLI parser chuyên dụng.
- Bảo toàn thứ tự xen kẽ giữa flags, options và positional arguments.
- Hỗ trợ cú pháp khác Spring, ví dụ **-v**, **-f input.csv**, subcommands hoặc option có khoảng trắng giữa tên và value.
- Tạo snapshot cho kiểm thử compatibility với một API nhận **String[]**.
- Kiểm tra chính xác người gọi đã truyền những token nào, khác với việc đọc cấu hình cuối cùng.

### 7.2. Khi nào không nên dùng raw array?

Không cần tự parse raw nếu chỉ muốn đọc:

~~~text
--mode=batch --tag=a --tag=b --dry-run file.csv
~~~

Khi ấy:

~~~java
String mode = args.getOptionValues("mode").get(0);
boolean dryRun = args.containsOption("dry-run");
List<String> tags = args.getOptionValues("tag");
List<String> files = args.getNonOptionArgs();
~~~

Đây là snippet minh họa; trong code production phải **kiểm tra null/empty/count** trước **get(0)**. Phương án này tránh tự viết vòng lặp string parsing nếu cú pháp phù hợp với Spring.

### 7.3. Tách parsing khỏi nghiệp vụ

Thiết kế tốt hơn việc truyền String[] khắp application:

~~~text
ApplicationRunner.run(ApplicationArguments)
       |
       +-- getSourceArgs() hoặc getOptionValues(...)
       v
ArgumentParser / Validator
       |
       v
BatchOptions(mode, inputPath, dryRun)
       |
       v
BatchService.execute(BatchOptions)
~~~

**BatchOptions** có thể là Java record bất biến. Parser được unit test độc lập bằng data đầu vào; service nghiệp vụ không cần biết Boot có ApplicationArguments. Runner chỉ đóng vai trò adapter cho lifecycle và DI.

Nếu một công cụ CLI phức tạp có subcommands, help, short flags và option validation nâng cao, nên cân nhắc thư viện CLI chuyên dụng thay vì tự xây parser bằng split và startsWith.

## 8. Environment khác source arguments như thế nào?

Với cấu hình:

~~~properties
# application.properties
app.mode=from-file
~~~

và lệnh:

~~~bash
java -jar app.jar --app.mode=from-cli
~~~

**getSourceArgs()** cung cấp token **--app.mode=from-cli** vì đó là program argument. Theo cơ chế cấu hình mặc định, **Environment.getProperty("app.mode")** có thể trả về **from-cli** do nguồn CLI ưu tiên cao hơn file.

Nhưng nếu không truyền CLI:

- **getSourceArgs()** trả mảng rỗng.
- **Environment.getProperty("app.mode")** có thể đọc **from-file**.

Hai API vì vậy trả lời hai câu hỏi:

| Câu hỏi | API phù hợp |
| --- | --- |
| Chương trình nhận những token CLI nào? | **getSourceArgs()** |
| Người dùng có truyền option tên mode không? | **containsOption("mode")** |
| Người dùng đã truyền những giá trị của tag? | **getOptionValues("tag")** |
| Giá trị cấu hình cuối cùng của app.mode là gì? | **Environment/@ConfigurationProperties** |

### 8.1. setAddCommandLineProperties(false)

SpringApplication hỗ trợ:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

Đây là snippet giả định có **MyApplication**. Thiết lập này **không thêm option CLI làm command-line PropertySource** trong Environment theo đường mặc định. Nó **không có nghĩa source args biến mất**. ApplicationArguments vẫn phản ánh token truyền cho **app.run(args)**, và CommandLineRunner vẫn nhận raw arguments thông thường.

Do đó, việc **phân tích arguments** và **đưa CLI properties vào Environment** là hai chức năng riêng. Không nên dùng getSourceArgs để kiểm tra property effective cuối cùng.

## 9. An toàn dữ liệu và tính bất biến

### 9.1. Không chỉnh mảng framework để thay đổi startup

Không làm:

~~~java
args.getSourceArgs()[0] = "--mode=changed";
~~~

Cách này không phải API cập nhật Environment hay các option đã parse, lại có thể lỗi khi không có phần tử. Nó còn phụ thuộc việc implementation trả bản sao hay một reference cụ thể, điều không nên dùng làm giả định thiết kế.

Khi muốn lưu hoặc biến đổi cục bộ, tạo snapshot:

~~~java
String[] snapshot = args.getSourceArgs().clone();
~~~

Sau đó parse/validate trên **snapshot** của bạn và trả về object kết quả rõ ràng.

### 9.2. Không in raw arguments trong production

Mảng raw có thể chứa:

- **--password=...**
- **--api-token=...**
- Đường dẫn nội bộ hoặc private URL.
- Dữ liệu cá nhân hoặc giá trị nghiệp vụ nhạy cảm.

In **Arrays.toString(args.getSourceArgs())** có thể làm lộ toàn bộ vào log, CI, monitoring và trace. Ví dụ ở mục 5 chỉ sử dụng dữ liệu minh họa không nhạy cảm.

Trong hệ thống thật, **không log raw args mặc định**; nếu thật sự cần quan sát, log số lượng token hoặc các key an toàn, che giá trị theo allowlist nghiêm ngặt. Secret nên được cung cấp qua cơ chế quản lý bí mật phù hợp hơn thay vì gắn trên command line có nguy cơ hiển thị trong process list.

### 9.3. Không ghép token để chạy lại bằng shell

Không nên lấy String[] rồi làm:

~~~java
String combined = String.join(" ", args.getSourceArgs());
~~~

và đưa **combined** vào shell để chạy. Bạn sẽ mất ranh giới token khi có khoảng trắng và có thể tạo nguy cơ injection với dữ liệu không tin cậy.

Nếu cần chuyển tiếp cho một chương trình có executable cố định và đáng tin, sử dụng API nhận **danh sách token riêng biệt** như **ProcessBuilder**, nhưng vẫn phải xác thực đầu vào và kiểm soát chương trình đích. Không tự chạy công cụ tùy ý từ raw token chỉ vì chúng được cung cấp bởi SpringApplication.

## 10. Unit test bằng DefaultApplicationArguments

Để kiểm tra getSourceArgs, không cần khởi động ApplicationContext. Spring Boot cung cấp **DefaultApplicationArguments**, nhận **String...** hoặc **String[]**.

Thêm dependency test trong pom.xml:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo **src/test/java/com/example/args/SourceArgsTest.java**:

~~~java
package com.example.args;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.DefaultApplicationArguments;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SourceArgsTest {

    @Test
    void preservesSourceTokenOrder() {
        String[] input = {
                "--mode=batch",
                "--tag=one",
                "--tag=two",
                "--dry-run",
                "report 2026.csv"
        };
        ApplicationArguments args = new DefaultApplicationArguments(input);

        assertArrayEquals(input, args.getSourceArgs());
        assertEquals(List.of("one", "two"), args.getOptionValues("tag"));
        assertTrue(args.containsOption("dry-run"));
        assertEquals(List.of("report 2026.csv"), args.getNonOptionArgs());
    }

    @Test
    void rawTokensCanDifferFromParsedValues() {
        ApplicationArguments args = new DefaultApplicationArguments(
                "--mode",
                "batch",
                "-v"
        );

        assertArrayEquals(
                new String[] {"--mode", "batch", "-v"},
                args.getSourceArgs()
        );
        assertTrue(args.containsOption("mode"));
        assertEquals(List.of(), args.getOptionValues("mode"));
        assertEquals(List.of("batch", "-v"), args.getNonOptionArgs());
    }

    @Test
    void emptyArgumentsAreSupported() {
        ApplicationArguments args = new DefaultApplicationArguments();

        assertEquals(0, args.getSourceArgs().length);
        assertFalse(args.containsOption("mode"));
        assertNull(args.getOptionValues("mode"));
        assertEquals(List.of(), args.getNonOptionArgs());
    }

    @Test
    void cloneCreatesAnIndependentArray() {
        ApplicationArguments args =
                new DefaultApplicationArguments("--mode=batch", "file.csv");

        String[] returned = args.getSourceArgs();
        String[] snapshot = returned.clone();
        snapshot[0] = "--mode=changed";

        assertEquals("--mode=batch", returned[0]);
        assertEquals("--mode=changed", snapshot[0]);
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Các test xác minh **mảng gốc vẫn có đúng token**, **thứ tự được giữ**, **option được parse riêng**, **trường hợp không có argument** và **clone tạo ra một mảng độc lập**. Test cuối so sánh snapshot với mảng nhận về ở lần gọi đó; không giả định implementation lưu hay trả reference nội bộ theo một cách cụ thể.

### 10.1. Khi cần integration test

DefaultApplicationArguments kiểm tra riêng API parsing; nó chưa kiểm tra:

- Lệnh do shell, Docker, Maven/Gradle plugin hoặc hệ thống CI chuyển vào main đúng chưa.
- Ứng dụng thật có đưa đúng main args vào SpringApplication.run không.
- Runner có được đăng ký là bean và chạy sau refresh không.
- Các giá trị nhận từ launcher thực tế có đúng như người dùng mong đợi không.

Khi các yếu tố này quan trọng, chạy một integration/startup test với SpringApplication thật hoặc thực thi **java -jar** trong môi trường mục tiêu, và đối chiếu các token an toàn. Đừng chỉ kiểm tra unit test rồi suy đoán quoting/escaping của mọi shell đều giống nhau.

## 11. Các lỗi thường gặp

### 11.1. Tưởng source arguments là toàn bộ cấu hình runtime

**getSourceArgs()** không hợp nhất giá trị từ application.properties, OS environment hay Config Data. Cấu hình cuối cùng thuộc Environment và Binder.

### 11.2. Tưởng source arguments gồm JVM options

Tham số **-Xmx** hay **-D** đặt trước **-jar** được JVM launcher xử lý, thường không có trong args truyền tới main. Kiểm tra vị trí lệnh gọi.

### 11.3. Tự split toàn bộ chuỗi bằng khoảng trắng

Một token chứa **report 2026.csv** có thể bị tách thành hai chuỗi nếu bạn nối rồi split. Giữ cấu trúc **String[]/List<String>**.

### 11.4. Đọc source[0] khi không có args

Khi người dùng không truyền đối số, array có thể rỗng. Kiểm tra **length** trước khi truy cập chỉ số.

### 11.5. Hiểu nhầm --name value

Parser option đơn giản của Spring thường cần **--name=value**. Nếu có **--name value**, getSourceArgs vẫn giữ hai token, nhưng parser đã phân loại chúng theo semantics khác.

### 11.6. Dùng containsOption như parser boolean

**containsOption("flag")** trả về true với cả **--flag** và **--flag=false**, vì option vẫn có mặt. Muốn boolean phải đọc và validate value.

### 11.7. Xem array do getSourceArgs trả về như object cấu hình mutable

Không sửa trực tiếp array để kỳ vọng Boot cập nhật lại config. Tạo clone và parse thành object ứng dụng riêng.

### 11.8. In toàn bộ raw args vào production log

Raw args có thể chứa mật khẩu hoặc token. Ghi nhận giá trị an toàn có chủ đích, tránh lưu dữ liệu không cần thiết.

### 11.9. Dùng runner sai thời điểm

ApplicationRunner và CommandLineRunner được gọi sau refresh, trước **ApplicationReadyEvent**. Nếu callback chạy tác vụ lâu hoặc ném exception, startup/readiness có thể bị ảnh hưởng. Nếu chỉ cần dữ liệu đầu vào cho DI, inject ApplicationArguments vào bean; nếu cần I/O nghiệp vụ, chọn lifecycle phù hợp và kiểm soát lỗi.

### 11.10. Kỳ vọng thứ tự mặc định giữa hai loại runner

Không mặc định ApplicationRunner luôn chạy trước CommandLineRunner. Nếu cần thứ tự, dùng **Ordered/@Order**. Trong ví dụ, thứ tự được chỉ định cụ thể.

### 11.11. Dùng getSourceArgs để tái tạo command line nguyên văn

Không thể khôi phục chính xác dấu nháy và escaping đã được shell xử lý trước khi Java nhận token. Raw ở đây là **raw đối với parser của Spring**, không phải raw của terminal.

## 12. Checklist khi áp dụng

- [ ] Hiểu rõ **getSourceArgs()** phản ánh những token truyền cho **SpringApplication.run**.
- [ ] Biết phân biệt main args, JVM options, CLI properties và Environment effective values.
- [ ] Giữ đúng thứ tự khi chuyển token cho parser chuyên dụng.
- [ ] Không nối lại rồi split bằng khoảng trắng.
- [ ] Biết **getOptionValues** phù hợp hơn khi chỉ cần option đã parse.
- [ ] Xử lý mảng rỗng trước khi index.
- [ ] Clone nếu cần snapshot độc lập.
- [ ] Không sửa source array để thay đổi cấu hình.
- [ ] Không log raw secrets; tránh ghi dữ liệu nhạy cảm vào trace/metrics.
- [ ] Không đưa token chưa tin cậy vào shell.
- [ ] Test option lặp, dấu cách, Unicode, trường hợp không có arguments.
- [ ] Có kiểm thử qua launcher thực tế nếu việc chuyển token là quan trọng.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** **ApplicationArguments.getSourceArgs()** trả về kiểu gì?

**Đáp án:** **String[]** chứa các program arguments gốc đã truyền vào lần gọi SpringApplication.

**Câu 2.** Nếu shell chuyển **"--title=Monthly Sales"** thành một token, dấu nháy có còn trong chuỗi Java của getSourceArgs không?

**Đáp án:** Thông thường không. Chuỗi Java là **--title=Monthly Sales**; dấu nháy chỉ giúp shell giữ một token.

**Câu 3.** Với đầu vào **--mode batch**, getSourceArgs có bao nhiêu phần tử?

**Đáp án:** Hai: **--mode** và **batch**. Với parser simple command-line của Spring, token sau không tự thành value của option trước.

**Câu 4.** Nếu application.properties có **app.mode=prod** nhưng người dùng không truyền CLI args thì getSourceArgs có token **--app.mode=prod** không?

**Đáp án:** Không. File cấu hình không tự tạo source args.

**Câu 5.** Trong ApplicationRunner, làm sao lấy token gốc mà không chuyển sang CommandLineRunner?

**Đáp án:** Gọi **args.getSourceArgs()** bên trong **run(ApplicationArguments args)**.

**Câu 6.** Tại sao **getSourceArgs()** không phù hợp để biết giá trị cấu hình cuối cùng của **app.mode**?

**Đáp án:** Vì giá trị cuối còn phụ thuộc vào PropertySource khác và ưu tiên cấu hình. Dùng Environment/@ConfigurationProperties.

**Câu 7.** Nếu tắt command-line PropertySource bằng **setAddCommandLineProperties(false)**, getSourceArgs có mất token không?

**Đáp án:** Không. Việc cho phép CLI override Environment khác với việc SpringApplication nhận arguments.

**Câu 8.** Vì sao phải tránh **Arrays.toString(args.getSourceArgs())** trong production?

**Đáp án:** Vì các token có thể chứa secrets, thông tin cá nhân và nội dung vận hành cần bảo mật.

**Câu 9.** Cách nào giữ ranh giới token khi chuyển tiếp cho parser khác?

**Đáp án:** Truyền String[] hoặc List<String> trực tiếp; không nối thành chuỗi rồi split bằng dấu cách.

**Câu 10.** Có thể tạo ApplicationArguments trong unit test không cần startup Spring Boot không?

**Đáp án:** Có. Dùng **new DefaultApplicationArguments(String...)** để kiểm thử raw tokens và parsed options.

## 14. Ghi nhớ và tài liệu chính thức

**getSourceArgs()** trả về **String[] chứa các token gốc của một lần SpringApplication chạy**, giữ nguyên thứ tự mà chương trình đã chuyển cho Boot. API này thích hợp khi cần token nguyên bản, chuyển tiếp cho parser khác hoặc kiểm thử đầu vào. Nó **không** đại diện cho toàn bộ giá trị Environment và **không** khôi phục nguyên văn lệnh shell.

Khi chỉ cần option **--name=value**, cờ hoặc non-option, dùng API parsing của ApplicationArguments. Khi cần cấu hình có precedence, dùng Environment hoặc @ConfigurationProperties. Coi raw array là read-only, clone khi cần snapshot, bảo vệ thông tin nhạy cảm và kiểm thử qua launcher thật khi cần.

Tài liệu:

- **Spring Boot 3.3.13 — SpringApplication / Accessing Application Arguments:** https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- **Spring Boot 3.3 — ApplicationArguments API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- **Spring Boot 3.3 — DefaultApplicationArguments API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/DefaultApplicationArguments.html
- **Spring Boot 3.3 — ApplicationRunner API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- **Spring Boot 3.3 — CommandLineRunner API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html