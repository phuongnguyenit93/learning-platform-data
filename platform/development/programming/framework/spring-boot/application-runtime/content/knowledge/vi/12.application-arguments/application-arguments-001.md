# Cấu trúc ApplicationArguments và DefaultApplicationArguments trong Spring Boot

## 1. Tổng quan: đối số đi từ main tới ứng dụng như thế nào?

Khi chạy một ứng dụng Spring Boot bằng Java, phương thức `main(String[] args)` nhận các **application arguments** được truyền sau tên JAR hoặc main class. `SpringApplication.run(..., args)` nhận mảng đó để khởi động ứng dụng. Spring Boot cung cấp một abstraction có cấu trúc, tên là **`ApplicationArguments`**, để các bean đọc lại **chuỗi đối số gốc**, **option arguments** và **non-option arguments** mà không phải tự phân tích chuỗi bằng cách cắt ký tự.

`DefaultApplicationArguments` là **implementation mặc định** của interface `ApplicationArguments`. Nó nhận `String... args`, bảo quản khả năng truy cập các đối số nguồn và tạo biểu diễn đã phân tích cho option/non-option. Trong một ứng dụng Spring Boot thông thường, bạn chỉ cần inject **interface `ApplicationArguments`**; không cần tự tạo một `DefaultApplicationArguments` trong mỗi bean.

~~~mermaid
flowchart TD
  OS["Lệnh khởi động / terminal"] --> MAIN["main(String[] args)"]
  MAIN --> RUN["SpringApplication.run(App.class, args)"]
  RUN --> PARSE["DefaultApplicationArguments"]
  PARSE --> RAW["getSourceArgs(): raw String[]"]
  PARSE --> OPT["Option args: --key=value, --flag"]
  PARSE --> NON["Non-option args: file.csv, import"]
  RUN --> ENV["CommandLinePropertySource trong Environment (mặc định)"]
  PARSE --> BEAN["ApplicationArguments bean"]
  BEAN --> AR["ApplicationRunner.run(ApplicationArguments)"]
  BEAN --> INJECT["Constructor injection vào bean bất kỳ"]
~~~

Sơ đồ này thể hiện đường đi logic của dữ liệu, không khẳng định mọi node là một thread hoặc bean riêng. `ApplicationArguments` và `CommandLinePropertySource` dùng các đối số cùng nguồn, nhưng có API và mục đích khác nhau.

### Ba trường hợp điển hình

~~~bash
java -jar app.jar --spring.profiles.active=dev --debug input.csv
~~~

- `--spring.profiles.active=dev`: option có tên `spring.profiles.active`, giá trị `dev`.
- `--debug`: option dạng **flag**, có mặt nhưng **không được cung cấp giá trị**.
- `input.csv`: non-option/positional argument.
- `getSourceArgs()` trả toàn bộ chuỗi mảng ban đầu theo đúng thứ tự, không chỉ những option đã nhận diện.

Đừng nhầm `-Dspring.profiles.active=dev` với `--spring.profiles.active=dev`. Dạng `-D...` là **JVM system property** nếu đặt trước `-jar`; nó không phải application argument trong `String[] args`. Dạng `--...` đặt sau JAR được chuyển cho ứng dụng.

## 2. ApplicationArguments: contract của interface

Interface `org.springframework.boot.ApplicationArguments` mô tả những thao tác mà code có thể thực hiện với đối số của một lần chạy `SpringApplication`.

| API | Kiểu trả về | Chức năng |
| --- | --- | --- |
| `getSourceArgs()` | `String[]` | Mảng đối số **gốc**, chưa biến đổi thành các option |
| `getOptionNames()` | `Set<String>` | Tập tên những option đã được parser nhận diện |
| `containsOption(String name)` | `boolean` | Kiểm tra một option có xuất hiện hay không |
| `getOptionValues(String name)` | `List<String>` hoặc `null` | Lấy danh sách giá trị của một option, hỗ trợ lặp cùng tên |
| `getNonOptionArgs()` | `List<String>` | Những đối số không thuộc nhóm option |

Các phương thức này không thực hiện nghiệp vụ. Chúng trả dữ liệu từ việc phân tích đối số, để service/runner lựa chọn cách ứng xử.

### 2.1 getSourceArgs(): còn nguyên thứ tự đầu vào

Ví dụ truyền đúng bốn application arguments:

~~~bash
java -jar app.jar --region=vn --dry-run --region=sg orders.csv
~~~

Giá trị tương đương của `getSourceArgs()`:

~~~text
[--region=vn, --dry-run, --region=sg, orders.csv]
~~~

Mảng có **bốn phần tử** sau tên JAR. Trong code Java, có thể hiển thị bằng:

~~~java
System.out.println(java.util.Arrays.toString(
        arguments.getSourceArgs()));
~~~

`getSourceArgs()` cho phép lưu hoặc kiểm tra token nguồn, kể cả token không được ánh xạ thành property. Nhưng không nên dump mảng này lên production log nếu người vận hành có thể đưa token, password, access key hoặc dữ liệu riêng tư qua CLI.

### 2.2 getOptionNames(): tập tên, không phải danh sách giá trị

Từ lệnh trước, tên option là `region` và `dry-run`. Vì `getOptionNames()` trả về `Set`, không nên dựa vào thứ tự duyệt tập trong test hoặc output. Nếu cần output ổn định:

~~~java
System.out.println(new java.util.TreeSet<>(
        arguments.getOptionNames()));
~~~

Kết quả tương ứng:

~~~text
[dry-run, region]
~~~

Lặp `--region=...` không làm xuất hiện hai phần tử `region` trong tập tên; giá trị của option được giữ riêng qua `getOptionValues(...)`.

### 2.3 containsOption(): kiểm tra sự có mặt của cờ

~~~java
boolean dryRun = arguments.containsOption("dry-run");
~~~

Khi lệnh có `--dry-run`, biểu thức là `true` dù không có `=true`. Đây là cách phù hợp để kiểm tra một **cờ có mặt/không có mặt**.

Không nên giả định `containsOption("dry-run")` kiểm tra xem một chuỗi giá trị có thể chuyển thành boolean hay không. Nếu người dùng truyền `--dry-run=false`, option **vẫn có mặt**, nên `containsOption("dry-run")` vẫn bằng `true`; muốn hiểu giá trị false cần đọc `getOptionValues("dry-run")` hoặc bind sang cấu hình typed theo quy tắc phù hợp.

### 2.4 getOptionValues(): ba trạng thái phải xử lý đúng

Javadoc của `ApplicationArguments` quy định ba tình huống quan trọng:

| Dòng lệnh | `containsOption("mode")` | `getOptionValues("mode")` |
| --- | --- | --- |
| Không có `--mode` | `false` | `null` |
| `--mode` | `true` | Danh sách rỗng `[]` |
| `--mode=fast` | `true` | Danh sách một phần tử `["fast"]` |
| `--mode=fast --mode=safe` | `true` | Danh sách hai phần tử `["fast", "safe"]` |
| `--mode=` | `true` | Danh sách có **một chuỗi rỗng** `[""]` |

Điểm cuối đặc biệt dễ gây nhầm: `List.of("").toString()` cũng in giống `[]` vì chuỗi rỗng không hiển thị giữa dấu ngoặc. Do đó **không** dùng duy nhất output `toString()` để phân biệt flag `--mode` với option `--mode=`. Kiểm tra `size()` và `get(0).isEmpty()` sẽ rõ hơn.

~~~java
import java.util.List;

List<String> modes = arguments.getOptionValues("mode");

if (modes == null) {
    System.out.println("mode option is absent");
} else if (modes.isEmpty()) {
    System.out.println("mode is a flag without a value");
} else if (modes.get(0).isEmpty()) {
    System.out.println("mode has an explicitly empty value");
} else {
    System.out.println("first mode value=" + modes.get(0));
}
~~~

Đây là đoạn minh họa nằm trong method nhận được biến `arguments` kiểu `ApplicationArguments`, không phải file Java độc lập. Khi một option được lặp nhiều lần, cần quyết định chính sách nghiệp vụ: chỉ chấp nhận một giá trị, chấp nhận danh sách, hoặc báo lỗi. **Không** tự chọn “giá trị cuối thắng” cho mọi mục đích nếu specification chưa quy định.

### 2.5 getNonOptionArgs(): đối số theo vị trí

Một đối số không bắt đầu theo dạng option `--name` hoặc `--name=value` thường được parser xếp vào nhóm non-option. Ví dụ:

~~~bash
java -jar app.jar --format=csv import customers.csv
~~~

~~~text
getNonOptionArgs() => [import, customers.csv]
~~~

Đây là cơ sở để thiết kế ứng dụng CLI đơn giản như `import`, `export`, đường dẫn input file, hoặc tên tác vụ. Parser này không tự cung cấp schema position, xác thực extension hay kiểm tra file có tồn tại; đó là phần việc của mã ứng dụng.

## 3. DefaultApplicationArguments: implementation và cách nó phân tích

`org.springframework.boot.DefaultApplicationArguments` triển khai `ApplicationArguments`, có constructor:

~~~java
public DefaultApplicationArguments(String... args)
~~~

Nó thích hợp cho **unit test**, các thành phần cần phân tích một mảng arguments cho mục đích riêng, hoặc minh họa contract. Trong quá trình chạy `SpringApplication` thông thường, Boot cung cấp một `ApplicationArguments` bean tương ứng với args đã truyền cho `run(...)`. Nên phụ thuộc interface khi viết service/runner, tránh khóa mã ứng dụng vào chi tiết implementation.

### Tự tạo parser bên ngoài context

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.DefaultApplicationArguments;

ApplicationArguments parsed = new DefaultApplicationArguments(
        "--user=Lan",
        "--tag=red",
        "--tag=blue",
        "--dry-run",
        "orders.csv"
);

System.out.println(parsed.containsOption("dry-run"));
System.out.println(parsed.getOptionValues("tag"));
System.out.println(parsed.getNonOptionArgs());
~~~

Các dòng này nằm trong một method hoặc unit test. Kết quả:

~~~text
true
[red, blue]
[orders.csv]
~~~

**Quan trọng:** tạo `new DefaultApplicationArguments(...)` chỉ tạo một đối tượng Java phân tích chuỗi; nó **không khởi chạy Spring Boot**, **không thay đổi `Environment`**, và **không tự trở thành `ApplicationArguments` bean** trong context đang chạy.

### Quan hệ với Spring Framework command-line parsing

Implementation mặc định tận dụng chức năng phân tích option của Spring Framework, có quan hệ với `SimpleCommandLinePropertySource`/các thành phần parser command line. Những quy tắc quan sát được:

- Một option có dạng `--optionName` hoặc `--optionName=value`.
- Giá trị phải nằm trong cùng một token, nối bằng dấu `=`, không có khoảng trắng giữa tên và dấu bằng.
- `--name=Lan` là option có giá trị; `--name Lan` gồm option `name` **không giá trị**, còn `Lan` là non-option.
- `--list=red,blue` là **một** chuỗi giá trị `"red,blue"` trong `getOptionValues("list")`; parser ApplicationArguments không mặc nhiên chia nó thành hai phần tử chỉ vì có dấu phẩy.
- `--list=red --list=blue` là **hai** giá trị của cùng option.
- `--flag` là option không kèm giá trị; `--flag=` có một giá trị rỗng.
- Ký hiệu `--` đứng riêng là dấu kết thúc phần option theo parser Spring Framework: các token sau đó được coi là non-option, kể cả token trông giống `--key=value`.
- Token viết sai dạng `-mode=fast` không được coi là option có tên `mode` theo cú pháp `--`; hãy kiểm tra non-option thay vì tự suy diễn nó thành property.

Đây là một parser đơn giản, không phải thư viện CLI đầy đủ với subcommands, auto-completion, type validation và usage help. Nếu cần ứng dụng CLI lớn, có thể dùng thư viện chuyên biệt như Picocli và tích hợp phù hợp vào lifecycle Boot, nhưng không nên nhầm parser tùy biến với contract mặc định của `ApplicationArguments`.

### Những giả định không nên đưa vào code

1. **Không giả định thứ tự `Set`:** tên option được trả về theo `Set<String>`, không có hợp đồng giữ thứ tự CLI.
2. **Không giả định chỉ có một giá trị:** cùng option có thể xuất hiện nhiều lần.
3. **Không giả định option absent là empty list:** absent trả `null`.
4. **Không giả định flag có boolean true:** flag chỉ báo sự xuất hiện; chọn semantics boolean là quyết định của code.
5. **Không giả định non-option là file path hợp lệ:** parser chỉ phân loại token.
6. **Không giả định option được convert sang kiểu dữ liệu:** `getOptionValues` trả chuỗi; việc parse integer/date/enum phải được ứng dụng thực hiện hoặc giao cho Binder có validation.
7. **Không giả định việc tạo lại DefaultApplicationArguments sẽ tự thay giá trị của Spring Environment:** đây là hai con đường API khác nhau.

## 4. ApplicationArguments khác Environment và JVM arguments

Mỗi lớp dữ liệu có một mục tiêu:

| Nguồn hoặc API | Nhận từ đâu | Xem bằng gì | Ví dụ |
| --- | --- | --- | --- |
| `String[] args` trong `main` | Token sau main class/JAR | Trực tiếp trong Java | `--app.mode=dev` |
| `ApplicationArguments` | Những args chuyển vào `SpringApplication.run` | `containsOption`, `getOptionValues`, `getNonOptionArgs` | `--tag=alpha` |
| `DefaultApplicationArguments` | `String... args` truyền vào constructor | API của `ApplicationArguments` | Tạo parser trong test |
| `Environment` | Hợp nhất nhiều `PropertySource` | `getProperty(key)` | Giá trị `app.mode` từ CLI/YAML/OS/JVM |
| Java system properties | `-Dname=value` ở JVM trước `-jar` | `System.getProperty(name)` / `Environment` | `-Dapp.mode=dev` |
| OS environment variables | Process environment | `System.getenv(name)` / `Environment` | `APP_MODE=dev` |
| Spring config data | `application.yaml`/`application.properties` và profile-specific | `Environment`, `@ConfigurationProperties` | `app.mode: production` |

Spring Boot mặc định chuyển option dòng lệnh dạng `--key=value` thành Spring property trong `Environment` thông qua `CommandLinePropertySource`. Nguồn này thông thường có độ ưu tiên cao hơn các cấu hình file application. Ví dụ:

~~~yaml
# src/main/resources/application.yaml
app:
  mode: "configured"
~~~

~~~bash
java -jar app.jar --app.mode=cli
~~~

Với mặc định của Boot, `environment.getProperty("app.mode")` trả `"cli"`. Đồng thời `ApplicationArguments.getOptionValues("app.mode")` chứa `["cli"]`. Hai con đường cho giá trị tương ứng trong trường hợp đơn giản, nhưng API khác nhau.

### Điều gì xảy ra khi tắt command-line PropertySource?

Có thể tùy biến `SpringApplication` trước `run`:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

Đây là snippet cần class `MyApplication` thích hợp. Với cờ `false`:
- `ApplicationArguments` **vẫn phân tích và giữ** args được truyền.
- Spring Boot **không tự thêm** command-line PropertySource mặc định vào `Environment`.
- Nếu chỉ dựa vào `--app.mode=cli`, `environment.getProperty("app.mode")` sẽ không nhất thiết là `cli`; có thể lấy giá trị từ YAML, OS env, JVM property hoặc nguồn khác.
- Tương tự, `--spring.profiles.active=dev` không còn tự được đưa vào `Environment` bằng cơ chế CLI thông thường, nên không được tự suy rằng profile dev sẽ active chỉ vì token ấy tồn tại.

Đây là cách kiểm chứng rõ nhất rằng **`ApplicationArguments` không đồng nhất với `Environment`**.

### Lệnh Java: thứ tự -D và --key=value

~~~bash
# JVM property phải xuất hiện trước -jar.
java -Dapp.mode=jvm -jar app.jar

# Application argument xuất hiện sau tên JAR.
java -jar app.jar --app.mode=cli
~~~

Ví dụ thứ nhất có thể đọc bằng `System.getProperty("app.mode")`. Ở ví dụ thứ hai, `System.getProperty("app.mode")` không được JVM tự thêm chỉ vì có CLI option, nhưng Spring `Environment` có thể đọc được thông qua command-line PropertySource.

### Vì sao getOptionValues và Environment có thể không có cùng ý nghĩa?

`getOptionValues("tag")` có thể trả một list gồm nhiều giá trị, trong khi `Environment.getProperty("tag")` là một property string đã đi qua cơ chế `PropertySource` và có quy tắc biểu diễn/ưu tiên riêng. Nếu ứng dụng cần **giữ nguyên chính xác các giá trị lặp và thứ tự**, sử dụng `ApplicationArguments`. Nếu ứng dụng cần **configuration có type, default và thứ tự ưu tiên**, ưu tiên `@ConfigurationProperties`/Binder hoặc `Environment`.

Không nên dùng `Environment` để lấy mọi non-option token. Theo mặc định các token positional không tự trở thành Spring properties có tên tùy bạn tưởng tượng.

## 5. Đưa ApplicationArguments vào bean và runner

### Inject bằng constructor

Spring Boot đăng ký `ApplicationArguments` như một bean để các component có thể nhận qua constructor:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.stereotype.Component;

@Component
class ImportOptions {
    private final ApplicationArguments arguments;

    ImportOptions(ApplicationArguments arguments) {
        this.arguments = arguments;
    }

    boolean dryRun() {
        return arguments.containsOption("dry-run");
    }
}
~~~

Một component có thể truy cập args ngay khi nó được tạo. Nhưng nên hạn chế chạy tác vụ nghiệp vụ nặng trong constructor; chỉ lưu dependency hoặc validation nhẹ phù hợp.

### ApplicationRunner và CommandLineRunner

Hai loại runner này chạy trong giai đoạn cuối startup, sau khi `ApplicationContext` được refresh và trước `ApplicationReadyEvent` (trong đường khởi động thành công).

| Interface | Method | Đối số nhận vào | Dùng khi |
| --- | --- | --- | --- |
| `ApplicationRunner` | `run(ApplicationArguments args)` | Raw và parsed arguments qua interface | Muốn đọc option/non-option một cách có cấu trúc |
| `CommandLineRunner` | `run(String... args)` | Mảng raw string arguments | Muốn tự xử lý raw token hoặc giao cho parser khác |

Ví dụ khung:

~~~java
@Bean
ApplicationRunner parsedArgumentsTask() {
    return args -> {
        System.out.println(args.containsOption("dry-run"));
    };
}
~~~

~~~java
@Bean
CommandLineRunner rawArgumentsTask() {
    return args -> {
        System.out.println(java.util.Arrays.toString(args));
    };
}
~~~

Hai snippet là **hai phương án minh họa** đặt trong một class `@Configuration` hoặc `@SpringBootApplication` có import `@Bean` và các interface tương ứng; không phải hai chương trình đầy đủ. Nếu dùng nhiều runner và cần thứ tự, cấu hình `@Order` hoặc `Ordered` theo yêu cầu; không dựa vào thứ tự duyệt bean ngẫu nhiên. Một exception từ runner có thể khiến startup thất bại trước mốc ready.

### Không tự tạo DefaultApplicationArguments khi Boot đã cung cấp

Đoạn code kiểu:

~~~java
new DefaultApplicationArguments("--mode=fixed");
~~~

chỉ tạo một parser mới chứa đối số `--mode=fixed`. Nó không thể dùng để “đổi” args đã được Boot chuyển vào `ApplicationArguments` bean, và cũng không thay đổi command-line properties đã được xử lý cho context hiện tại.

Nếu cần parse một tập con token theo logic riêng, việc tạo parser thủ công có thể hợp lý. Nếu chỉ cần dữ liệu của lần khởi động hiện tại, inject `ApplicationArguments`. Đây là nguyên tắc làm code dễ test, nhất quán và tách trách nhiệm rõ.

## 6. Ví dụ Spring Boot hoàn chỉnh, Java 17+, Maven

Ví dụ này tập trung vào quan sát cấu trúc `ApplicationArguments`, không yêu cầu web server. Sử dụng Spring Boot 3.5.16 và Java 17+ với starter nền tảng.

Tạo các file:

~~~text
args-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/args/ArgsDemoApplication.java
    └── resources/application.yaml
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
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

### File src/main/resources/application.yaml

~~~yaml
spring:
  application:
    name: args-demo
  main:
    banner-mode: "off"

app:
  mode: "from-yaml"
~~~

Phần `app.mode` dùng để chứng minh command-line option có thể override YAML qua `Environment`.

### File src/main/java/com/example/args/ArgsDemoApplication.java

~~~java
package com.example.args;

import java.util.Arrays;
import java.util.List;
import java.util.TreeSet;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ArgsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ArgsDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showArguments(
            ApplicationArguments injectedArguments,
            Environment environment) {

        return parsed -> {
            System.out.println(
                    "source=" + Arrays.toString(parsed.getSourceArgs()));
            System.out.println(
                    "names=" + new TreeSet<>(parsed.getOptionNames()));
            System.out.println(
                    "verbosePresent="
                            + parsed.containsOption("verbose"));
            System.out.println(
                    "verboseValues="
                            + parsed.getOptionValues("verbose"));
            System.out.println(
                    "tags=" + parsed.getOptionValues("tag"));
            System.out.println(
                    "missing=" + parsed.getOptionValues("missing"));
            System.out.println(
                    "nonOptions=" + parsed.getNonOptionArgs());
            System.out.println(
                    "injectedSource="
                            + Arrays.toString(
                                    injectedArguments.getSourceArgs()));
            System.out.println(
                    "modeFromEnv="
                            + environment.getProperty("app.mode", "none"));

            List<String> tagValues = parsed.getOptionValues("tag");
            System.out.println(
                    "tagCount="
                            + (tagValues == null ? 0 : tagValues.size()));
        };
    }
}
~~~

**Vì sao code này chạy được?**

- `@SpringBootApplication` bật component scan và auto-configuration cơ bản.
- `@Bean` đăng ký một `ApplicationRunner` có method factory nhận hai dependency: `ApplicationArguments` và `Environment` do Boot/context quản lý.
- Trong lambda runner, `parsed` là `ApplicationArguments` được Boot đưa vào trực tiếp theo interface. `injectedArguments` cũng truy cập startup arguments của chính lần chạy đó.
- `TreeSet` chỉ dùng để sắp tên option trước khi in, tránh giả định thứ tự `Set`.
- `getOptionValues("missing")` được in trực tiếp để minh họa giá trị `null` khi option không có.
- `app.mode` có giá trị dự phòng trong YAML nhưng khi truyền từ CLI, Environment có thể chọn giá trị CLI có độ ưu tiên cao hơn.

### Build và chạy

Trong thư mục `args-demo`:

~~~bash
mvn -q -DskipTests package
java -jar target/args-demo-0.0.1-SNAPSHOT.jar \
  --app.mode=cli \
  --verbose \
  --tag=alpha \
  --tag=beta \
  import.csv
~~~

Dấu `\` nối dòng chỉ phù hợp các shell kiểu Bash/Unix. Trên Windows PowerShell hoặc cmd, có thể đặt toàn bộ lệnh `java -jar...` trên **một dòng**. Tên JAR dựa trên version/artifact trong `pom.xml` ở trên.

**Các dòng do `showArguments` in ra** theo đúng thứ tự của ví dụ:

~~~text
source=[--app.mode=cli, --verbose, --tag=alpha, --tag=beta, import.csv]
names=[app.mode, tag, verbose]
verbosePresent=true
verboseValues=[]
tags=[alpha, beta]
missing=null
nonOptions=[import.csv]
injectedSource=[--app.mode=cli, --verbose, --tag=alpha, --tag=beta, import.csv]
modeFromEnv=cli
tagCount=2
~~~

Spring Boot vẫn có thể ghi log khởi động; khối trên **chỉ** liệt kê output của runner, không khẳng định toàn bộ stdout chỉ chứa các dòng này.

Giải thích theo từng dòng:
1. `source` chứa đúng **năm** application arguments đứng sau tên JAR: mode, verbose, hai tag và tên file.
2. `names` sắp theo tên option. `import.csv` không là tên option.
3. `verbosePresent=true` vì `--verbose` có mặt, dù không có dấu bằng.
4. `verboseValues=[]` là một danh sách **không phần tử** của option không có giá trị.
5. `tags` có hai phần tử theo hai lần truyền `--tag=...`.
6. `missing=null` vì chưa hề có option `--missing`.
7. `nonOptions` chứa positional argument `import.csv`.
8. `injectedSource` cho thấy bean `ApplicationArguments` được inject dùng cùng dữ liệu startup.
9. `modeFromEnv=cli` cho thấy command-line PropertySource override `app.mode: from-yaml` theo mặc định.
10. `tagCount=2` xác nhận các option cùng tên được giữ thành list, không bị mất phần tử khi truy cập parsed API.

### Chạy không có option nào

~~~bash
java -jar target/args-demo-0.0.1-SNAPSHOT.jar
~~~

Những dòng quan trọng:

~~~text
source=[]
names=[]
verbosePresent=false
verboseValues=null
tags=null
missing=null
nonOptions=[]
injectedSource=[]
modeFromEnv=from-yaml
tagCount=0
~~~

Không có option `--verbose`, nên `getOptionValues("verbose")` trả **null**, khác với `verboseValues=[]` trong lượt chạy có flag. Đây là sự khác biệt cần ghi test.

### Chạy với giá trị rỗng và non-option đứng sau option

~~~bash
java -jar target/args-demo-0.0.1-SNAPSHOT.jar \
  --verbose= \
  --tag= \
  report.csv
~~~

Ở ví dụ này:
- `containsOption("verbose")` bằng `true`.
- `getOptionValues("verbose")` là danh sách **một phần tử**, phần tử đó là chuỗi rỗng.
- `getOptionValues("tag")` cũng có một chuỗi rỗng nên `tagCount=1`.
- `getNonOptionArgs()` là `[report.csv]`.

Nếu chỉ in `verboseValues` hoặc `tags` bằng `List.toString()`, chuỗi rỗng không hiển thị trực quan; vì vậy nhìn giống `[]` không đủ để kết luận danh sách rỗng. Để phân biệt, kiểm tra `size()`.

## 7. Unit test cho DefaultApplicationArguments mà không cần Spring context

Một lợi ích của `DefaultApplicationArguments` là bạn có thể kiểm thử parser trực tiếp mà không khởi động Spring Boot. Thêm dependency test trong `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Đây là đoạn cần đặt **bên trong `<dependencies>`** của POM đã có. Nó thêm JUnit Jupiter và công cụ kiểm thử do starter quản lý.

Tạo file `src/test/java/com/example/args/ArgumentsParsingTest.java`:

~~~java
package com.example.args;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.DefaultApplicationArguments;

import static org.junit.jupiter.api.Assertions.*;

class ArgumentsParsingTest {

    @Test
    void parsesRepeatedValuesFlagsAndPositionalArgs() {
        ApplicationArguments a = new DefaultApplicationArguments(
                "--region=vn",
                "--region=sg",
                "--dry-run",
                "orders.csv");

        assertArrayEquals(
                new String[] {
                    "--region=vn",
                    "--region=sg",
                    "--dry-run",
                    "orders.csv"
                },
                a.getSourceArgs());

        assertEquals(
                Set.of("region", "dry-run"),
                a.getOptionNames());

        assertEquals(
                List.of("vn", "sg"),
                a.getOptionValues("region"));

        assertTrue(a.containsOption("dry-run"));
        assertNotNull(a.getOptionValues("dry-run"));
        assertTrue(a.getOptionValues("dry-run").isEmpty());

        assertNull(a.getOptionValues("absent"));
        assertEquals(List.of("orders.csv"), a.getNonOptionArgs());
    }

    @Test
    void distinguishesEmptyStringFromNoValue() {
        ApplicationArguments a = new DefaultApplicationArguments(
                "--empty=",
                "--flag");

        assertTrue(a.containsOption("empty"));
        assertEquals(1, a.getOptionValues("empty").size());
        assertEquals("", a.getOptionValues("empty").get(0));

        assertTrue(a.containsOption("flag"));
        assertEquals(0, a.getOptionValues("flag").size());
    }

    @Test
    void separateTokenIsNotAutomaticallyOptionValue() {
        ApplicationArguments a = new DefaultApplicationArguments(
                "--name",
                "Lan");

        assertTrue(a.containsOption("name"));
        assertTrue(a.getOptionValues("name").isEmpty());
        assertEquals(List.of("Lan"), a.getNonOptionArgs());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Với Spring Boot Starter Test và version Java phù hợp, ba JUnit tests thể hiện kỳ vọng trên parser. `assertEquals(Set.of(...), a.getOptionNames())` không phụ thuộc thứ tự vì so sánh hai `Set`. Ngược lại, `List.of("vn","sg")` chủ động kiểm tra thứ tự hai giá trị option.

**Lưu ý:** đây là unit test cho `DefaultApplicationArguments`, không phải test rằng mọi `PropertySource` đã được chuẩn bị hoặc mọi profile đã active. Để test tương tác với `Environment` và config data, cần một Spring Boot startup/integration test tương ứng.

## 8. Quy tắc phân loại token: ví dụ đối chiếu nhanh

| Token đầu vào | Nhóm theo parser | Nội dung quan sát |
| --- | --- | --- |
| `--debug` | Option | Tên `debug` có mặt; list giá trị rỗng |
| `--debug=true` | Option | Tên `debug`; list `["true"]` |
| `--debug=false` | Option | Tên `debug` vẫn có mặt; list `["false"]` |
| `--port=8081` | Option | Tên `port`; list `["8081"]`; chưa phải số nguyên trong `ApplicationArguments` |
| `--port=` | Option | Tên `port`; một chuỗi rỗng |
| `--item=a --item=b` | Hai lần cùng option | `getOptionValues("item")` là `["a", "b"]` |
| `--item=a,b` | Một option | `getOptionValues("item")` là `["a,b"]` |
| `--item a` | Option + positional | `item` không có giá trị, `a` là non-option |
| `--help` | Option | Chỉ là cờ; Boot không tự xây command usage help cho mọi app |
| `input.txt` | Non-option | Phần tử trong `getNonOptionArgs()` |
| `-Dmy.flag=on` trước `-jar` | JVM option | Java system property; không thuộc `String[] args` |
| `--` | Dấu kết thúc option | Những token theo sau được parser xem là non-option |

**Đừng nhầm khái niệm option được phân tích với binding typed.** Parser cung cấp chuỗi. Nếu muốn kiểm tra `--port=abc` là một số cổng hợp lệ, ứng dụng phải parse/validate hoặc sử dụng Spring binding mechanism có cơ chế kiểm tra. Lỗi do parse sai kiểu ở bước nghiệp vụ khác với lỗi cú pháp parser.

### Khi option có nhiều giá trị

Các chiến lược xử lý phổ biến:
- **Single-value strict:** báo lỗi khi list có nhiều hơn một giá trị.
- **List-value:** chấp nhận lặp option và xử lý toàn bộ danh sách theo thứ tự xuất hiện.
- **Last-value override:** chỉ lấy phần tử cuối **nếu CLI contract của ứng dụng** chủ động quy định.
- **Optional flag:** dùng `containsOption` và không yêu cầu giá trị; nếu người dùng gõ `--flag=false`, kiểm tra rõ semantics vì `containsOption` vẫn true.

Ví dụ single-value strict, tự xử lý null/empty/multiple:

~~~java
static String requireSingleValue(
        ApplicationArguments args, String name) {

    List<String> values = args.getOptionValues(name);

    if (values == null || values.isEmpty()) {
        throw new IllegalArgumentException(
                "Missing option value: --" + name);
    }
    if (values.size() != 1) {
        throw new IllegalArgumentException(
                "Expected exactly one value for --" + name);
    }
    if (values.get(0).isBlank()) {
        throw new IllegalArgumentException(
                "Blank value is not allowed: --" + name);
    }
    return values.get(0);
}
~~~

Đây là **method** cần đặt trong một class và import `ApplicationArguments`/`List`; có thể dùng Java 17. Nó không phân biệt absent và flag trong thông điệp vì cả hai bị xem là thiếu giá trị, theo chủ đích của một option bắt buộc. Nếu cần báo lỗi chi tiết, tách hai case.

## 9. Lỗi thường gặp và cách sửa

### Truyền --debug nhưng getOptionValues("debug").get(0) ném lỗi

`--debug` là option **không có value**, nên `getOptionValues("debug")` trả list rỗng. Dùng `containsOption("debug")` nếu đây là flag, hoặc yêu cầu người dùng truyền `--debug=true` nếu thiết kế cần một giá trị.

### Không truyền --mode nhưng getOptionValues("mode").isEmpty() gây NullPointerException

Option absent có `getOptionValues(...) == null`. Kiểm tra null trước rồi mới kiểm tra empty. Unit test nên bao phủ cả absent, flag và explicitly empty value.

### Truyền --mode fast nhưng ứng dụng không nhận fast làm value

Cú pháp option value của parser là `--mode=fast`. Hai token `--mode` và `fast` không tương đương: `fast` là non-option. Dùng dấu bằng không có khoảng trắng giữa tên và value.

### Có hai --tag nhưng chỉ lấy được một giá trị

Nếu code sử dụng `getOptionValues("tag").get(0)`, nó tự bỏ qua những giá trị sau. API có khả năng trả **nhiều** phần tử; cần quyết định có chấp nhận lặp, lọc duplicate, hay báo lỗi.

### JVM -D không xuất hiện trong getSourceArgs()

`-D...` là option của JVM, cần đặt trước `-jar` hoặc main class để JVM xử lý. Muốn đọc JVM property, dùng `System.getProperty(...)`/`Environment`. Muốn chuyển dữ liệu qua `ApplicationArguments`, dùng `--...` sau tên JAR.

### application.yaml có giá trị khác getOptionValues

`ApplicationArguments` phản ánh **CLI args** của lần chạy, không tổng hợp mọi nguồn config. `Environment` hợp nhất CLI, file, OS environment và JVM system properties với thứ tự ưu tiên riêng. Nếu option CLI không có nhưng YAML có key, `getOptionValues(key)` vẫn có thể là `null`, trong khi `Environment.getProperty(key)` có giá trị.

### Không nhận được CLI option trong Environment

Kiểm tra application có gọi `setAddCommandLineProperties(false)` hay không, có truyền đúng args cho `SpringApplication.run`, và option có cú pháp `--key=value`. Cũng cần xem key đang được đọc có đúng tên và nguồn property phù hợp.

### Runner không thấy args dù main nhận được

Một lỗi cơ bản là bỏ truyền `args`:

~~~java
// Sai nếu muốn chuyển arguments từ main sang Boot:
SpringApplication.run(ArgsDemoApplication.class);
~~~

Sửa:

~~~java
SpringApplication.run(ArgsDemoApplication.class, args);
~~~

Khi gọi kiểu không truyền args, Boot sẽ thấy mảng argument rỗng từ lời gọi run đó. Không tự lấy lại thông tin CLI ở runner từ chỗ khác rồi coi đó là contract chuẩn.

### getOptionNames() thay đổi thứ tự giữa các lần test

`Set` không cam kết thứ tự CLI. Test nên so sánh tập phần tử, hoặc sort khi cần output hiển thị ổn định. Trong ví dụ runnable, dùng `new TreeSet<>(...)` để bảo đảm thứ tự chữ cái.

### Ghi mật khẩu vào log và gây rò rỉ

`getSourceArgs()` trả chuỗi gốc, có thể chứa bí mật từ operator. Không log toàn bộ arguments trong production, không đưa access token vào lệnh shell nếu có thể dùng secret manager hoặc cơ chế an toàn hơn. Khi cần debug, chỉ in tên option hoặc giá trị đã được che phù hợp.

### Đưa tác vụ dài vào constructor chỉ để đọc args

Đọc `ApplicationArguments` qua constructor được, nhưng không nên chạy cả một job I/O trong constructor. Với công việc cần context đã refresh, dùng `ApplicationRunner` hoặc `CommandLineRunner`. Cần nhớ runner chạy trước `ApplicationReadyEvent` và có thể trì hoãn readiness.

## 10. Kịch bản áp dụng thực tế

### CLI import dữ liệu

Một ứng dụng ETL có thể nhận:

~~~bash
java -jar etl.jar --source=customers.csv --dry-run
~~~

- `getOptionValues("source")` cho phép lấy input path.
- `containsOption("dry-run")` báo chế độ chỉ kiểm tra, không ghi.
- Logic nghiệp vụ kiểm tra đường dẫn, quyền đọc và cấu trúc CSV; parser không làm thay.
- Nếu `source` bắt buộc, dùng method validation như `requireSingleValue` ở trên.

### Chọn Spring profile khi chạy

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

`ApplicationArguments` vẫn nhận option `spring.profiles.active`. Trong mặc định của Boot, CLI properties được đưa vào `Environment` đủ sớm để hệ thống chọn profile và nạp config data phù hợp. Nhưng nếu tắt `setAddCommandLineProperties(false)`, không nên kết luận token trong `ApplicationArguments` vẫn tự kích hoạt profile.

### Chuyển một loạt tags

~~~bash
java -jar app.jar --tag=blue --tag=green --tag=red
~~~

Nếu API cần danh sách, lấy `getOptionValues("tag")`; đây là ba phần tử. Không dùng biểu diễn `--tag=blue,green,red` rồi giả định luôn nhận ba phần tử từ `getOptionValues`.

### Truyền vị trí file đầu vào

~~~bash
java -jar app.jar validate schema.json payload.json
~~~

`getNonOptionArgs()` có ba phần tử theo thứ tự: `validate`, `schema.json` và `payload.json`. Ứng dụng cần tự kiểm tra số lượng, tên subcommand và hợp lệ của file. Với CLI phức tạp và nhiều subcommand, nên dùng parser chuyên dụng.

## 11. Checklist trước khi đưa vào production

1. Chuyển đúng `String[] args` từ `main` vào `SpringApplication.run`.
2. Sử dụng `ApplicationArguments` cho dữ liệu CLI có cấu trúc, thay vì tự tách theo dấu cách trong một string.
3. Nhớ `DefaultApplicationArguments` là implementation có thể tự tạo trong test, không phải bean phải `new` lại trong mỗi component.
4. Kiểm tra **absent/null**, **flag/empty list** và **explicit empty string/single-element list**.
5. Quy định rõ semantics nếu cùng option xuất hiện nhiều lần.
6. Không dựa vào thứ tự duyệt `getOptionNames()`; sort khi in hoặc so sánh `Set`.
7. Phân biệt application CLI options, JVM `-D` và OS environment variables.
8. Nếu cần cấu hình hiệu lực, lấy từ `Environment`/`@ConfigurationProperties`, không giả định CLI args chứa mọi giá trị YAML/profile.
9. Không đưa password/token/raw source args lên production logs.
10. Nếu cần kiểm tra input trước ready, đặt validation ở runner hoặc giai đoạn phù hợp và xử lý failure có chủ đích.
11. Test parser thuần bằng `new DefaultApplicationArguments(...)`, nhưng kiểm tra cấu hình tích hợp bằng một Spring Boot test thực.
12. Đối chiếu tài liệu API theo đúng phiên bản Boot/Spring Framework đang sử dụng.

## 12. Câu hỏi tự kiểm tra

**1. `ApplicationArguments` có phải một class concrete bắt buộc khởi tạo bằng `new` không?**  
Không. Đó là interface; Boot thường cung cấp `ApplicationArguments` bean. `DefaultApplicationArguments` là implementation mặc định.

**2. `getSourceArgs()` khác `getOptionValues("tag")` thế nào?**  
`getSourceArgs()` trả mảng token gốc; `getOptionValues` chỉ trả danh sách giá trị của một option đã parse.

**3. Truyền `--dry-run`, `containsOption("dry-run")` và `getOptionValues("dry-run")` trả gì?**  
`true` và một danh sách rỗng.

**4. Không truyền `--dry-run`, `getOptionValues("dry-run")` trả gì?**  
`null`, không phải list rỗng.

**5. Truyền `--dry-run=`, điều gì khác?**  
Có một phần tử chuỗi rỗng trong danh sách giá trị; cần dùng `size()`/`get(0)` để phân biệt với flag không giá trị.

**6. `--tag=red --tag=blue` tạo mấy giá trị trong getOptionValues("tag")?**  
Hai chuỗi `red` và `blue`.

**7. `--tag=red,blue` có tự tạo hai giá trị không?**  
Không trong contract parser ở đây; nó là một chuỗi `red,blue`.

**8. `--name Lan` có làm Lan thành value của name không?**  
Không; option `name` không có value, `Lan` là non-option.

**9. Vì sao `Environment.getProperty("app.mode")` có thể có giá trị dù `getOptionValues("app.mode")` là null?**  
Vì Environment có những PropertySource khác như YAML, system properties hoặc OS env.

**10. Dùng `setAddCommandLineProperties(false)` có làm mất dữ liệu trong ApplicationArguments không?**  
Không; nó tắt việc đưa CLI option vào Environment bằng nguồn mặc định, không vô hiệu hóa API parsed args.

**11. ApplicationRunner nhận kiểu gì, CommandLineRunner nhận kiểu gì?**  
ApplicationRunner nhận `ApplicationArguments`; CommandLineRunner nhận `String... args`.

**12. Có nên in `Arrays.toString(getSourceArgs())` trong production log không?**  
Không mặc định, vì raw args có thể chứa bí mật.

## 13. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — ApplicationArguments API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ApplicationArguments.html): contract của năm phương thức.
- [Spring Boot 3.5 — DefaultApplicationArguments API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/DefaultApplicationArguments.html): implementation và constructor nhận `String... args`.
- [Spring Boot 3.5 — SpringApplication và Accessing Application Arguments](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): inject `ApplicationArguments`, runner và startup path.
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): command-line PropertySource và thứ tự ưu tiên.
- [Spring Framework 6.2 — SimpleCommandLinePropertySource](https://docs.spring.io/spring-framework/docs/6.2.3/javadoc-api/org/springframework/core/env/SimpleCommandLinePropertySource.html): cú pháp `--optName[=value]`, giá trị lặp, `--`.
- [Spring Boot 3.5 — SpringApplication API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html): tham số `run(...)` và `setAddCommandLineProperties(false)`.

Nội dung minh họa theo Spring Boot 3.5.x và Java 17+. Khi áp dụng cho một dự án khác, kiểm tra chính xác phiên bản các thư viện và quy ước CLI của ứng dụng trước khi sử dụng các hành vi mặc định trong mã nghiệp vụ.