# Tạo ứng dụng dòng lệnh Spring Boot không cần mở máy chủ web

## 1. Mục tiêu và khi nào dùng

**Ứng dụng dòng lệnh (CLI — Command-Line Interface)** chạy một tác vụ từ terminal, nhận tham số, thông báo kết quả và thường kết thúc với mã trạng thái của tiến trình. Không phải ứng dụng Spring Boot nào cũng cần phục vụ HTTP. Ví dụ điển hình gồm nhập dữ liệu định kỳ, xử lý tệp, tạo báo cáo, đồng bộ dữ liệu, công cụ bảo trì hoặc một job được hệ thống lập lịch gọi.

Spring Boot vẫn hữu ích cho CLI vì cung cấp **dependency injection**, quản lý bean, cấu hình theo profile, logging, tích hợp dữ liệu và quản lý vòng đời. Khác biệt cốt lõi là:

- **Ứng dụng web** thường tạo `ApplicationContext` có khả năng phục vụ web, rồi khởi động máy chủ nhúng khi có dependency và cấu hình thích hợp.
- **Ứng dụng CLI thuần** dùng Spring context không phải web, chạy logic nghiệp vụ và kết thúc. Nó không cần mở cổng HTTP, controller, servlet container hoặc reactive web server.

Trong phạm vi bài này, ta tạo chương trình Java 17+ có khả năng chạy:

~~~text
java -jar target/cli-demo-1.0.0.jar --name=Lan --repeat=2
~~~

Chương trình nạp các bean Spring, đọc hai tùy chọn dòng lệnh, in lời chào hai lần, đóng context rồi trả quyền điều khiển cho shell. **Không có máy chủ HTTP nào do Spring Boot khởi động**.

## 2. Spring Boot quyết định chạy web hay không như thế nào?

`SpringApplication` xác định `WebApplicationType` từ classpath nếu không được chỉ định rõ. Ba lựa chọn chính là:

| Giá trị | Ý nghĩa |
| --- | --- |
| `NONE` | Chạy một Spring `ApplicationContext` không phải web. Không khởi tạo máy chủ web nhúng. |
| `SERVLET` | Chạy ứng dụng web dựa trên Servlet khi stack phù hợp được cấu hình. |
| `REACTIVE` | Chạy ứng dụng web reactive khi stack phù hợp được cấu hình. |

Cách rõ ràng nhất cho CLI là đặt trong `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
~~~

Hoặc YAML:

~~~yaml
spring:
  main:
    web-application-type: none
~~~

Chọn **một** kiểu file cấu hình cho giá trị này để tránh cấu hình trùng. Khi đặt `none`, dù sau này dự án có thêm dependency liên quan tới web, Spring Boot vẫn được yêu cầu tạo ứng dụng không phải web. Những thư viện client HTTP để **gọi** dịch vụ bên ngoài không đồng nghĩa ứng dụng phải **mở** cổng HTTP nhận request.

Có thể cấu hình trực tiếp bằng Java:

~~~java
SpringApplication application = new SpringApplication(CliApplication.class);
application.setWebApplicationType(WebApplicationType.NONE);
application.run(args);
~~~

Đoạn trên chỉ minh họa một cách cấu hình khác; để biên dịch cần import `org.springframework.boot.SpringApplication` và `org.springframework.boot.WebApplicationType` cùng lớp `CliApplication` trong dự án. Các thuộc tính `spring.main.*` từ cấu hình ngoài có thể ghi đè giá trị API tương ứng, vì vậy cần kiểm tra những nguồn cấu hình đang có hiệu lực.

**Không đánh đồng `server.port=-1` với `WebApplicationType.NONE`:** thiết lập `server.port=-1` có thể tắt HTTP endpoint nhưng vẫn tạo web application context trong ứng dụng Servlet. `WebApplicationType.NONE` mới là lựa chọn phù hợp khi chủ đích là một ứng dụng **không phải web**.

## 3. Chạy tác vụ ở đâu? ApplicationRunner và CommandLineRunner

Phần `main()` chỉ nên bootstrap Spring. Hãy đặt logic cần chạy **sau khi bean đã được tạo và inject** vào một bean triển khai một trong hai interface:

| Interface | Tham số `run` | Nên dùng khi |
| --- | --- | --- |
| `CommandLineRunner` | `run(String... args)`, mảng đối số thô | Logic đơn giản, tự phân tích tham số hoặc không cần tùy chọn phức tạp |
| `ApplicationRunner` | `run(ApplicationArguments args)` | Cần phân biệt `--option=value` và đối số vị trí, đọc tùy chọn theo tên |

Cả hai được Spring Boot gọi sau khi `ApplicationContext` đã refresh thành công, trước lúc lời gọi `SpringApplication.run(...)` hoàn tất. Nếu có nhiều runner, có thể điều khiển thứ tự bằng `@Order` hoặc `Ordered`. Tránh dựa vào thứ tự quét classpath.

Dòng khởi động cho CLI:

~~~text
JVM -> CliApplication.main(args)
    -> SpringApplication.run(CliApplication.class, args)
       -> đọc Environment/profiles/properties
       -> tạo non-web ApplicationContext
       -> quét component và tạo bean
       -> inject dependency vào runner
       -> gọi ApplicationRunner/CommandLineRunner
    -> run(...) trả về ConfigurableApplicationContext
    -> đóng context, trả exit code cho hệ điều hành
~~~

Spring Boot vẫn có thể tạo kết nối cơ sở dữ liệu hoặc tài nguyên khác nếu dependency và cấu hình ứng dụng yêu cầu. Tắt web server **không tự tắt** những thành phần đó.

## 4. Dự án Maven hoàn chỉnh chạy được

Ví dụ sau dùng **Java 17+**, **Maven** và Spring Boot **3.3.13**. Để không cần plugin web, dự án chỉ khai báo `spring-boot-starter` cơ bản. Mọi tệp dưới đây có thể được tạo trong thư mục dự án `cli-demo`. Trước khi chạy, cài JDK tương thích và Maven; kiểm tra bằng `java -version` và `mvn -version`.

Cấu trúc dự án:

~~~text
cli-demo/
├─ pom.xml
└─ src/main/
   ├─ java/com/example/cli/
   │  ├─ CliApplication.java
   │  ├─ GreetingService.java
   │  └─ GreetingRunner.java
   └─ resources/
      └─ application.properties
~~~

### 4.1. `pom.xml`: starter cơ bản, không có Spring Web

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>cli-demo</artifactId>
    <version>1.0.0</version>

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

`spring-boot-starter` cung cấp các thành phần nền để bootstrap Spring Boot, auto-configuration và logging. Không khai báo web starter nên không kéo theo một web server chỉ vì ứng dụng cần Spring. Maven plugin đóng gói JAR để chạy bằng `java -jar`.

### 4.2. `application.properties`: buộc chạy không phải web

**Tệp `src/main/resources/application.properties`:**

~~~properties
spring.application.name=cli-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
~~~

`web-application-type=none` là thiết lập quan trọng nhất. `banner-mode=off` chỉ ẩn banner để output gọn hơn; không có tác dụng bật/tắt web server. Spring Boot vẫn có thể ghi log khởi động bình thường.

### 4.3. Lớp chính `CliApplication.java`

**Tệp `src/main/java/com/example/cli/CliApplication.java`:**

~~~java
package com.example.cli;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class CliApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(CliApplication.class, args);

        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
~~~

Lớp có `@SpringBootApplication` nằm trong package gốc `com.example.cli`, nên các component cùng package hoặc package con có thể được quét. `SpringApplication.run(...)` khởi tạo Spring context, inject các bean và gọi runner. Chỉ **sau khi runner chạy xong thành công**, `run(...)` mới trả context về `main()`.

`SpringApplication.exit(context)` đóng context và thu thập mã thoát từ các `ExitCodeGenerator` được đăng ký (nếu có). `System.exit(exitCode)` kết thúc JVM với mã đó để script, terminal hoặc scheduler nhận kết quả. Đối với chương trình CLI rất đơn giản, không có thread giữ JVM hoạt động, có thể để JVM tự thoát; dùng cách tường minh ở đây giúp minh họa vòng đời của job và exit code.

### 4.4. Logic nghiệp vụ `GreetingService.java`

**Tệp `src/main/java/com/example/cli/GreetingService.java`:**

~~~java
package com.example.cli;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

`@Service` đăng ký bean nghiệp vụ; nó không cần tự tạo `GreetingService` từ `main()`. Trong ứng dụng thực tế, service có thể xử lý dữ liệu hoặc gọi hệ thống bên ngoài; tách khỏi runner giúp logic dễ kiểm thử và tái sử dụng.

### 4.5. Tác vụ CLI `GreetingRunner.java`

**Tệp `src/main/java/com/example/cli/GreetingRunner.java`:**

~~~java
package com.example.cli;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class GreetingRunner implements ApplicationRunner {

    private final GreetingService greetingService;

    public GreetingRunner(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @Override
    public void run(ApplicationArguments args) {
        String name = optionOrDefault(args, "name", "bạn");
        String repeatText = optionOrDefault(args, "repeat", "1");

        int repeat;
        try {
            repeat = Integer.parseInt(repeatText);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "--repeat phải là một số nguyên", ex);
        }

        if (repeat < 1 || repeat > 10) {
            throw new IllegalArgumentException(
                    "--repeat phải nằm trong khoảng 1 đến 10");
        }

        for (int i = 0; i < repeat; i++) {
            System.out.println(greetingService.greet(name));
        }
        System.out.println("Đã in " + repeat + " lời chào.");
    }

    private static String optionOrDefault(
            ApplicationArguments args, String name, String defaultValue) {
        List<String> values = args.getOptionValues(name);

        if (values == null) {
            return defaultValue;
        }
        if (values.size() != 1 || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "--" + name + " cần đúng một giá trị không rỗng");
        }
        return values.get(0);
    }
}
~~~

**Giải thích:**

- `@Component` giúp Spring quản lý runner. Spring tạo `GreetingService` và truyền qua constructor; không dùng `new GreetingService()`.
- `ApplicationArguments.getOptionValues("name")` đọc `--name=Lan`. Khi tùy chọn vắng mặt, API trả `null`; ví dụ dùng mặc định `bạn`. Khi người dùng viết `--name` không có giá trị hoặc chỉ định giá trị rỗng, chương trình báo lỗi rõ ràng.
- `--repeat=N` yêu cầu một số nguyên từ 1 đến 10; giới hạn tránh một tác vụ nhập sai gây in lượng dữ liệu quá lớn.
- Đọc tên tùy chọn theo một chỗ giúp dễ mở rộng và xác định rõ quy tắc đầu vào.
- Khi runner ném exception, `SpringApplication.run(...)` coi quá trình khởi chạy thất bại; câu lệnh `SpringApplication.exit(context)` trong `main()` ở ví dụ chỉ được gọi trên đường chạy thành công.

Đây là chương trình đầy đủ: mỗi lớp `public` có tên tệp khớp tên lớp, các import đều được khai báo, không cần controller, `@EnableWebMvc` hay cấu hình máy chủ HTTP.

## 5. Biên dịch và chạy

Mở terminal tại thư mục chứa `pom.xml`, biên dịch và đóng gói bằng:

~~~bash
mvn clean package
~~~

Maven tạo executable JAR `target/cli-demo-1.0.0.jar` sau khi build thành công (tên xuất phát từ `artifactId` và `version` trong `pom.xml` trên).

Chạy:

~~~bash
java -jar target/cli-demo-1.0.0.jar --name=Lan --repeat=2
~~~

**Các dòng do mã ứng dụng in ra stdout, theo đúng thứ tự:**

~~~text
Xin chào, Lan!
Xin chào, Lan!
Đã in 2 lời chào.
~~~

Spring Boot có thể in thêm log khởi động hoặc log lỗi tùy cấu hình; ba dòng trên là output chính xác được tạo bởi `GreetingRunner`. Ứng dụng hoàn tất công việc và JVM thoát với code `0` trên đường chạy thành công. Không có Tomcat/Jetty/Netty web server nào được khởi động bởi cấu hình này.

Chạy không truyền tùy chọn:

~~~bash
java -jar target/cli-demo-1.0.0.jar
~~~

Các dòng do runner in:

~~~text
Xin chào, bạn!
Đã in 1 lời chào.
~~~

Có thể dùng Maven để chạy không qua JAR:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments="--name=Mai --repeat=3"
~~~

Nếu shell xử lý dấu nháy khác nhau, có thể đóng gói và chạy `java -jar` như trên để truyền tham số một cách dễ kiểm soát hơn. Trên Windows với Maven Wrapper từ Spring Initializr, dùng `.\mvnw.cmd`; trên Linux/macOS dùng `./mvnw`, nếu dự án đã có wrapper.

**Thử trường hợp dữ liệu sai:**

~~~bash
java -jar target/cli-demo-1.0.0.jar --repeat=0
java -jar target/cli-demo-1.0.0.jar --repeat=abc
java -jar target/cli-demo-1.0.0.jar --name=
~~~

Runner lần lượt báo lỗi giới hạn, lỗi định dạng số và lỗi giá trị rỗng. Ứng dụng khởi động thất bại nên không in dòng tổng kết hoàn thành và không nên được scheduler xem là một lần chạy thành công. Khi chẩn đoán lỗi, xem stack trace / failure analysis để tìm tham số gây ra sự cố.

## 6. Tham số dòng lệnh, cấu hình và các nguồn giá trị

Phân biệt ba loại thường gặp:

| Dạng | Ví dụ | Cách sử dụng |
| --- | --- | --- |
| Tùy chọn ứng dụng | `--name=Lan`, `--repeat=2` | Đọc qua `ApplicationArguments.getOptionValues(...)`; Spring Boot cũng đưa các option thích hợp vào `Environment`. |
| Đối số vị trí | `input.csv` | Đọc qua `ApplicationArguments.getNonOptionArgs()` hoặc mảng thô của `CommandLineRunner`. |
| Java system property | `-Dfile.encoding=UTF-8` | Đưa **trước** `-jar`: `java -Dfile.encoding=UTF-8 -jar ...`; tra qua API cấu hình tương ứng. |

Với Spring Boot, `--spring.profiles.active=dev` còn có thể chọn profile `dev`, `--logging.level.root=INFO` có thể thay đổi mức logging, tùy quy tắc ưu tiên nguồn cấu hình. Đó là các tùy chọn cấu hình framework; chương trình minh họa chỉ tự xử lý `name` và `repeat`.

Nếu cần biến một đối số vị trí thành đường dẫn tệp, cần kiểm tra tệp tồn tại, quyền truy cập, mã hóa và đầu ra trước khi xử lý. Không giả định chuỗi người dùng truyền vào luôn là đường dẫn hợp lệ hoặc nằm trong thư mục mong muốn.

### Khi nào dùng CommandLineRunner?

Nếu chỉ cần mảng chuỗi, có thể thay `GreetingRunner` bằng một `CommandLineRunner`:

~~~java
@Bean
CommandLineRunner quickTask(GreetingService service) {
    return args -> System.out.println(service.greet("CLI"));
}
~~~

Đây là đoạn **khai báo bean minh họa**, đặt trong một lớp cấu hình Spring có import `org.springframework.context.annotation.Bean` và `org.springframework.boot.CommandLineRunner`; `GreetingService` là class của dự án ở mục 4. Nếu thêm bean này cùng lúc với `GreetingRunner`, cả hai runner đều thực thi. Khi thay thế cách tiếp cận, hãy bỏ runner cũ hoặc điều phối thứ tự một cách rõ ràng. Khi cần phân tích `--option=value`, `ApplicationRunner` thường gọn hơn.

## 7. Kết thúc ứng dụng, tài nguyên và mã thoát

Một CLI tốt cần có điểm hoàn tất rõ ràng và báo kết quả đúng cho shell hoặc trình lập lịch.

- **Hoàn thành bình thường:** runner chạy xong, `SpringApplication.run(...)` trả về. Trong ví dụ, `SpringApplication.exit(context)` đóng Spring context rồi `System.exit(0)` kết thúc tiến trình khi không có `ExitCodeGenerator` báo lỗi.
- **Có lỗi trong runner:** exception làm quá trình chạy thất bại, Boot ghi lỗi và dọn dẹp context theo quy trình xử lý lỗi khởi động. Hãy để lỗi được ghi nhận, không nuốt exception rồi kết luận job thành công.
- **Tài nguyên do Spring quản lý:** bean có callback `@PreDestroy` hoặc `DisposableBean` được xử lý lúc đóng context. Với file stream, transaction hoặc tài nguyên tự mở bên ngoài Spring, vẫn cần dùng `try-with-resources`/cleanup tương ứng.
- **Thread nền:** scheduler, connection manager, thread do ứng dụng tự tạo có thể khiến JVM chưa tự thoát dù `run(...)` đã trả về. Không sử dụng scheduler vô hạn cho một job dự kiến chạy xong. `System.exit` tắt tiến trình nên cần đặt sau bước đóng tài nguyên và chỉ khi thật sự muốn kết thúc JVM.
- **Mã thoát:** hệ điều hành dùng `0` cho thành công; thường dùng giá trị khác `0` cho thất bại. Có thể sử dụng `ExitCodeGenerator` cùng `SpringApplication.exit(...)` để cung cấp mã cụ thể từ ứng dụng.

Ví dụ bean báo mã thoát:

~~~java
@Bean
ExitCodeGenerator customExitCode() {
    return () -> 0;
}
~~~

Đoạn này chỉ minh họa một bean trong lớp cấu hình Spring, cần import `org.springframework.context.annotation.Bean` và `org.springframework.boot.ExitCodeGenerator`. Không cần thêm bean luôn trả `0` vào chương trình chính: khi không có lỗi, `SpringApplication.exit(...)` mặc định có thể trả `0`. Trong thực tế, dùng `ExitCodeGenerator` để biểu thị kết quả nghiệp vụ cụ thể và có thể kiểm tra từ shell.

**Lưu ý kiểm thử:** không gọi `System.exit(...)` tùy tiện bên trong service hoặc runner vì nó chấm dứt cả JVM chạy test. Giữ trách nhiệm quyết định mã thoát ở điểm vào `main()`, kiểm thử logic nghiệp vụ và parser độc lập.

## 8. Không cần HTTP server, nhưng vẫn cần đúng kiến trúc Spring

Đặt `@SpringBootApplication` tại package gốc của module, ví dụ:

~~~text
com.example.cli
├─ CliApplication
├─ GreetingRunner
└─ GreetingService
~~~

Nhờ cơ chế component scan mặc định, runner và service được tạo dưới sự quản lý của Spring. Nếu đặt chúng trong package anh em nằm ngoài vùng quét hoặc quên `@Component`/`@Service`, thường sẽ xảy ra lỗi không tìm thấy bean khi inject. Không nên mở rộng quét toàn bộ classpath chỉ để xử lý một bean chưa được tìm thấy.

Một CLI **vẫn có thể** dùng JDBC, JPA, transaction, validation, HTTP client, messaging, configuration properties và DI. Thêm dependency thích hợp theo nhu cầu tác vụ. Tuy nhiên mỗi dependency có thể kích hoạt auto-configuration, tạo kết nối hoặc yêu cầu thuộc tính bổ sung. Nếu một kết nối cơ sở dữ liệu lỗi khiến CLI không khởi động, không nên kết luận là do `WebApplicationType.NONE`.

**Khi job dài hoặc chạy nền:** `ApplicationRunner` phù hợp cho quy trình khởi động/chạy một lần. Nếu cần retry, restart, checkpoint, phân lô lớn hoặc theo dõi nhiều bước, cân nhắc công cụ xử lý batch chuyên dụng như Spring Batch. Nếu muốn duy trì API HTTP để kích hoạt job từ xa, đó là yêu cầu kiến trúc web khác với phạm vi ứng dụng dòng lệnh này.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Log vẫn cho thấy web server đang chạy | `spring.main.web-application-type=none` không được nạp hoặc bị ghi đè bởi nguồn cấu hình ưu tiên cao hơn | Kiểm tra đúng `application.properties` trong classpath/JAR, profile, biến môi trường và tham số `spring.main.*` |
| Không mở cổng HTTP nhưng context vẫn là web | Chỉ thiết lập `server.port=-1` | Dùng `spring.main.web-application-type=none` để chuyển sang context không phải web |
| Không có dòng output của runner | Runner thiếu `@Component`/`@Bean`, ngoài vùng quét, hoặc lỗi xảy ra trước lúc runner chạy | Kiểm tra package, bean definition và nguyên nhân lỗi đầu tiên trong log |
| `No qualifying bean` khi inject service | Thiếu `@Service`/`@Bean` hoặc package sai | Đặt bean trong vùng quét, khai báo bean đúng |
| Tiến trình không tự kết thúc | Thread không phải daemon, scheduler, ứng dụng giữ tài nguyên hoặc tác vụ vẫn đang chạy | Kiểm tra thread dump, lifecycle, dừng tác vụ nền và đóng context đúng |
| Input `--repeat=abc` làm ứng dụng fail | Giá trị không phải số nguyên | Kiểm tra validate tùy chọn và hướng dẫn sử dụng CLI |
| `java -jar` báo không tìm thấy main manifest hoặc dependency | JAR thường chưa được plugin Spring Boot đóng gói thành executable archive | Kiểm tra `spring-boot-maven-plugin`, `mvn package`, tệp JAR thực tế |
| Kỳ vọng mở URL `localhost:8080` nhưng không truy cập được | Đang chạy non-web app nên không có HTTP endpoint | Đây là hành vi đúng khi dùng `NONE`; kiểm tra stdout/exit code thay vì trình duyệt |

Không nên đánh giá trạng thái của CLI bằng việc “port 8080 có mở hay không” như với web service. Các chỉ dấu có ý nghĩa hơn là **mã thoát, log, nội dung đầu ra, số bản ghi xử lý và kết quả tác vụ**.

## 10. Vận hành thực tế và cách kiểm thử

Đối với job chạy tự động, nên:

1. **Nhận đầu vào rõ ràng:** xác định những option bắt buộc, giá trị mặc định, giới hạn và thông báo lỗi. Nếu nhận file hoặc mật khẩu, tránh ghi dữ liệu nhạy cảm vào log.
2. **Giữ tác vụ có thể kiểm thử:** runner chỉ điều phối input/output và gọi service; tách logic xử lý khỏi `main()` cũng như framework.
3. **Xử lý lỗi đúng:** không bắt mọi `Exception` rồi in `Done`; để job báo thất bại với exit code phù hợp, kể cả khi đang được gọi bởi cron hoặc CI.
4. **Đóng tài nguyên:** ưu tiên Spring quản lý bean, đóng file/stream bằng `try-with-resources`, xử lý transaction cho các thay đổi dữ liệu.
5. **Chú ý tính chạy lại:** một job có thể bị scheduler chạy lại sau khi thất bại; tránh ghi dữ liệu trùng, cân nhắc idempotency và checkpoint nếu tác vụ lớn.
6. **Theo dõi thời gian hoàn tất:** job CLI thành công không phải là dịch vụ chạy mãi; với tác vụ dài, thêm log theo giai đoạn và chỉ số phù hợp.

Kiểm tra thủ công ít nhất ba tình huống trên dự án mục 4:

- **Không truyền option:** runner in lời chào mặc định và kết thúc với code `0`.
- **`--name=Lan --repeat=2`:** in chính xác hai lời chào cho Lan, sau đó một dòng tổng kết; không khởi động HTTP server.
- **`--repeat=0` hoặc `--repeat=abc`:** ứng dụng báo lỗi trước khi hoàn tất tác vụ; xác nhận scheduler hoặc script thấy trạng thái thất bại.

Nếu dùng shell Bash/Linux, có thể đọc exit code của lệnh vừa chạy bằng `echo $?`; với PowerShell, xem `$LASTEXITCODE` sau khi gọi `java -jar`. Không nhầm exit code của lệnh khác với kết quả JVM: cần kiểm tra ngay sau lệnh Java.

## 11. Bài tập củng cố

**Bài tập 1:** Thay `GreetingService` bằng `ReportService` tự tạo báo cáo từ một danh sách dữ liệu cố định, nhận `--format=text`. Đảm bảo phần phân tích option nằm trong runner và phần tạo báo cáo nằm trong service.

**Bài tập 2:** Thêm `--repeat=4` và dùng `@Order` để định thứ tự nếu tạo hai runner. Quan sát điều gì xảy ra khi không kiểm soát thứ tự và giải thích vì sao không nên dựa vào thứ tự classpath.

**Bài tập 3:** Tạm thêm dependency web thích hợp vào Maven rồi kiểm tra xem cấu hình `spring.main.web-application-type=none` còn ngăn web server khởi động không. Sau đó thử xóa riêng thuộc tính `none` để thấy sự khác biệt của auto-detection. Chỉ làm trong môi trường học tập, không thay cấu hình production một cách ngẫu nhiên.

**Câu hỏi tự kiểm tra:**

1. Có phải thêm `spring-boot-starter-web` mới chạy được `@SpringBootApplication`? **Không**. Starter cơ bản đã đủ cho CLI ví dụ.
2. Vì sao không chạy logic nghiệp vụ trực tiếp trước `SpringApplication.run()`? Vì các bean, injection và cấu hình runtime có thể chưa được khởi tạo.
3. `ApplicationRunner` khác `CommandLineRunner` ở đâu? Chủ yếu ở cách nhận đối số: `ApplicationArguments` đã phân tích option so với mảng `String[]` thô.
4. `server.port=-1` có thay thế `WebApplicationType.NONE` không? **Không**, vì nó không bảo đảm sử dụng non-web context.
5. Tại sao CLI nên có mã thoát rõ ràng? Vì shell, CI, cron và hệ thống điều phối cần biết job hoàn thành hay thất bại để xử lý tiếp.

## 12. Ghi nhớ và tài liệu tham khảo

Một ứng dụng CLI Spring Boot vẫn bắt đầu bằng `@SpringBootApplication` và `SpringApplication.run()`, nhưng dùng **`WebApplicationType.NONE`** để bỏ web runtime. Đặt tác vụ trong `ApplicationRunner` hoặc `CommandLineRunner`, nhận tham số rõ ràng, dùng bean Spring cho logic nghiệp vụ, đóng context khi hoàn tất và trả exit code đúng. Đó là mô hình phù hợp cho công cụ dòng lệnh và job hữu hạn.

Tài liệu chính thức:

- Spring Boot — SpringApplication, runners, application arguments, application exit: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Boot — Disabling the Web Server: https://docs.spring.io/spring-boot/how-to/webserver.html
- Spring Boot — Properties and Configuration: https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html
- Spring Boot — Starters and build systems: https://docs.spring.io/spring-boot/reference/using/build-systems.html
