# Dùng --debug và báo cáo điều kiện để hỗ trợ truy vết lỗi khởi động Spring Boot

## 1. Mục tiêu của bài học

Khi ứng dụng Spring Boot khởi động thất bại, log thông thường có thể chỉ cho thấy một lỗi cuối cùng như “required a bean that could not be found”, “failed to bind properties” hoặc “Application run failed”. Để tìm **vì sao Spring quyết định tạo hoặc không tạo một bean**, bạn cần biết cách bật `--debug` và đọc **Condition Evaluation Report** (báo cáo đánh giá điều kiện).

Bài này thuộc nhóm **Lỗi khởi động** trong Spring Boot Application Runtime. Sau khi học, bạn có thể:

1. Bật debug đúng cách với `java -jar`, Maven, Gradle hoặc cấu hình `debug=true`.
2. Hiểu `--debug` làm tăng log ở đâu, và tại sao nó **không bật DEBUG cho toàn bộ ứng dụng**.
3. Nhận biết vai trò khác nhau của **FailureAnalyzer**, stack trace, `ApplicationFailedEvent` và Condition Evaluation Report.
4. Đọc các phần `Positive matches`, `Negative matches`, `Unconditional classes` và `Exclusions` của báo cáo.
5. Diễn giải `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty` và các điều kiện theo loại web application.
6. Lần ngược từ một lỗi thiếu bean về một điều kiện đã **không khớp**, và phân biệt đó với lỗi trong constructor, network, hoặc property binding.
7. Chạy một demo Java 17+ với Spring Boot 3.5.16: **cùng một JAR**, một lần startup thất bại vì property vắng mặt, một lần chạy thành công sau khi đặt property đúng.
8. Thu thập log có kiểm soát, tránh lộ thông tin nhạy cảm khi debug production và không coi debug như biện pháp sửa lỗi.

**Ý chính:** `--debug` cung cấp thêm **bằng chứng** để điều tra; nó không sửa bean definition, không tự thêm dependency, không tự cấp profile và không bảo đảm báo cáo điều kiện có đủ mọi nguyên nhân lỗi.

## 2. Bốn nguồn tín hiệu khi startup thất bại

Hãy phân biệt các lớp thông tin:

| Tín hiệu | Trả lời câu hỏi | Giới hạn |
| --- | --- | --- |
| **Exception/cause chain** | Lỗi nào trực tiếp khiến startup thất bại? | Lỗi cuối chưa chắc cho biết vì sao bean không được đăng ký |
| **FailureAnalyzer** | Spring Boot có thể mô tả lỗi bằng Description/Action dễ hiểu không? | Không có analyzer cho mọi loại exception |
| **Condition Evaluation Report** | Những cấu hình/bean có điều kiện được chấp nhận hay từ chối vì sao? | Không phải stack trace; không mô tả mọi thao tác I/O hoặc runtime failure |
| **DEBUG logs có chọn lọc** | Những bước xử lý liên quan Boot, container hoặc thư viện đã diễn ra như thế nào? | `--debug` không bật DEBUG cho tất cả package |

Dòng xử lý khái quát:

~~~text
SpringApplication.run(args)
   |
   +-- Environment / properties / active profiles
   +-- Tải configuration và auto-configuration candidates
   |     |
   |     +-- Đánh giá @Conditional... (OnClass, OnBean, OnProperty...)
   |     +-- Ghi ConditionOutcome vào ConditionEvaluationReport
   |
   +-- Đăng ký BeanDefinitions / refresh ApplicationContext
   |     +-- Tạo bean và inject dependencies
   |     +-- Nếu lỗi: cause chain, FailureAnalyzer, report (nếu có)
   |
   +-- ApplicationRunner / CommandLineRunner
   |     +-- Nếu lỗi: startup cũng có thể thất bại
   |
   +-- ApplicationReadyEvent
         +-- Startup thành công
~~~

Nếu lỗi xảy ra rất sớm, chẳng hạn không đọc được file cấu hình thiết yếu hoặc cấu hình logging bị lỗi trước khi context được tạo, **báo cáo điều kiện có thể không đầy đủ hoặc không xuất hiện**. Khi ấy hãy xem exception đầu tiên có ý nghĩa và nguồn cấu hình, thay vì cố “ép” có một report.

Trong đường thất bại, Spring Boot phát `ApplicationFailedEvent` nếu có ngoại lệ startup. Đó là event giúp tích hợp logging/monitoring, không phải một phương thức đồng nghĩa với `--debug`.

## 3. Bật --debug đúng cách

### 3.1. Chạy executable JAR

Cách thông dụng và rõ ràng nhất:

~~~bash
java -jar target/my-app.jar --debug
~~~

Với ứng dụng nhận command-line properties theo mặc định, tùy chọn `--debug` tương đương bật property `debug=true`. Các argument dạng `--name=value` được xử lý bởi Spring Boot Environment trong đường `SpringApplication.run(args)` thông thường.

Có thể khai báo bằng file cấu hình:

~~~properties
debug=true
~~~

Hoặc bật bằng tham số explicit:

~~~bash
java -jar target/my-app.jar --debug=true
~~~

**Không nhầm**:
- `--debug` đặt **sau tên JAR** là application argument.
- `-Ddebug=true` đặt **trước `-jar`** là JVM system property. Spring Environment có thể đọc system properties, nhưng nó là một cơ chế truyền cấu hình khác; không coi hai cú pháp là một loại command-line option.
- `-agentlib:jdwp=...` là Java Debugger (JDWP), phục vụ đặt breakpoint, **không phải** Spring Boot `--debug`.
- `debug=true` là property cấu hình **log**, không tự biến mọi bean thành chế độ kiểm thử.

### 3.2. Maven Spring Boot Plugin

Khi chạy từ Maven:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Plugin chuyển `--debug` cho ứng dụng. Cú pháp quoting của shell khác nhau giữa Bash, PowerShell và cmd khi có nhiều argument; với một argument đơn thì lệnh trên thường dễ dùng.

Nếu bạn chạy JAR trực tiếp, sử dụng `java -jar ... --debug` sẽ giảm sự nhầm lẫn giữa log/mã thoát của Maven wrapper và tiến trình Java thật.

### 3.3. Gradle bootRun

Với Gradle plugin hỗ trợ truyền args:

~~~bash
./gradlew bootRun --args='--debug'
~~~

Trên Windows hãy dùng Gradle wrapper phù hợp (`gradlew.bat`) và cú pháp quoting của terminal. Nếu build dùng Gradle cũ/thiết lập tùy biến, xác minh tham số đã được chuyển đến ứng dụng chứ không chỉ đến build process.

### 3.4. Khi không thể sửa command line

Có thể cấu hình qua `application.properties` hoặc nguồn Environment được Boot hỗ trợ:

~~~properties
debug=true
~~~

Để bật **riêng logger của condition report** thay vì toàn bộ chế độ debug, xem mục 8. Việc đọc config trong startup phụ thuộc thứ tự property sources; nếu một source ưu tiên cao override `debug=false`, phải xem nguồn cấu hình cuối cùng có hiệu lực.

### 3.5. Có cần bật --trace?

`--trace` hoặc `trace=true` bật tracing log cho một **tập logger lõi** rộng hơn (Spring portfolio và những thành phần được Boot cấu hình), nhưng không phải một phiên bản “sửa được lỗi hơn” của `--debug`. Nó có thể tạo log rất nhiều. Bắt đầu với **stack trace + FailureAnalyzer + --debug**; chỉ mở TRACE có chọn lọc khi thực sự cần.

## 4. --debug có làm gì và không làm gì?

Theo Spring Boot 3.5 Logging Reference, bật debug:
- Đổi mức log của **một số logger cốt lõi** (ví dụ Spring Boot, embedded container, Hibernate theo cấu hình mặc định).
- Cho phép hiển thị **Condition Evaluation Report** ở mức DEBUG khi listener/report sẵn có.
- Cung cấp bối cảnh tốt hơn khi điều tra việc lựa chọn auto-configuration.

Nhưng nó **không**:
- Đặt `logging.level.root=DEBUG` cho mọi logger.
- Bật breakpoint hoặc remote debugging.
- Bật profile `dev` hoặc `test`.
- Tự bật tất cả Actuator endpoints.
- Tự tạo bean đang thiếu.
- Sửa các lỗi port conflict, cấu hình DB, secret hoặc network.
- Bảo đảm exception nào cũng có một `FailureAnalyzer` chuyên biệt.
- Bảo đảm condition report có đầy đủ dữ liệu khi startup chết trước giai đoạn đánh giá điều kiện.
- Khiến một application đã chạy thất bại ở runtime tự in “báo cáo khởi động” cho từng request.

**So sánh lệnh**:

~~~properties
# Bật chế độ debug của Spring Boot cho các logger được chọn.
debug=true

# Bật DEBUG cho riêng package ứng dụng.
logging.level.com.example=DEBUG

# Bật DEBUG cho logger auto-configuration report.
logging.level.org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener=DEBUG

# Rất ồn; không phải lựa chọn mặc định để chẩn đoán startup.
logging.level.root=DEBUG
~~~

Các property độc lập với nhau. Nếu chỉ muốn in condition report mà không tăng mọi log nền, cấu hình logger ở dòng thứ ba là lựa chọn đáng cân nhắc.

## 5. Condition Evaluation Report là gì?

`ConditionEvaluationReport` thuộc package `org.springframework.boot.autoconfigure.condition`. Nó ghi nhận **kết quả đánh giá của các Condition** (kèm thông điệp tại sao match hoặc không match) khi Spring Boot xử lý configuration/auto-configuration.

Một auto-configuration thường chỉ nên tham gia khi những điều kiện phù hợp:

~~~java
@ConditionalOnClass(SomeLibrary.class)
@ConditionalOnProperty(prefix = "feature", name = "enabled", havingValue = "true")
@ConditionalOnMissingBean(SomeService.class)
~~~

Đây là **đoạn annotation minh họa**, không phải một class Java hoàn chỉnh; `SomeLibrary` và `SomeService` đại diện cho các type giả định. Ý nghĩa:

1. Phải có thư viện/type phù hợp trên classpath.
2. Property `feature.enabled` phải bằng giá trị yêu cầu.
3. Phải chưa có bean `SomeService` thích hợp để auto-configuration không ghi đè bean người dùng đã tự khai báo.

Mỗi điều kiện có thể dẫn tới:
- **Match**: cấu hình được phép đi tiếp.
- **No match**: cấu hình hoặc bean definition được bỏ qua theo thiết kế.
- **Một tổ hợp điều kiện**: chỉ cần một điều kiện quan trọng không thỏa, source đó có thể bị loại.

“Không khớp” là **hành vi bình thường** của auto-configuration; số lượng negative matches lớn **không có nghĩa ứng dụng bị lỗi**. Chúng chỉ hữu ích khi liên hệ tới **bean/feature đang thiếu**.

### Các phần thường thấy trong báo cáo

~~~text
CONDITIONS EVALUATION REPORT
============================

Positive matches:
-----------------
  ...
  Cấu hình/bean nào đạt điều kiện, kèm nguyên nhân

Negative matches:
-----------------
  ...
  Cấu hình/bean nào không đạt, kèm nguyên nhân

Exclusions:
-----------
  ...
  Auto-configuration classes bị loại trừ tường minh

Unconditional classes:
----------------------
  ...
  Các auto-configuration candidates không phụ thuộc điều kiện
~~~

Đây là **sơ đồ bố cục**, không phải log copy từ một lần chạy thực tế. Các heading, tên class, thứ tự và số lượng dòng có thể thay đổi theo phiên bản Spring Boot, classpath, dependencies, profiles và các bean do ứng dụng định nghĩa.

### Positive matches

Cho biết điều kiện đã đúng, chẳng hạn:
- Class cần thiết có trên classpath.
- Ứng dụng là servlet web application.
- Property được bật.
- Chưa có bean custom nên auto-configuration được phép cung cấp bean mặc định.

**Quan trọng:** positive match **không chứng minh bean đã được tạo thành công**. Condition có thể match nhưng constructor hoặc `@Bean` method vẫn ném exception khi instantiate.

### Negative matches

Cho biết điều kiện không thỏa, chẳng hạn:
- Class không có trên classpath.
- `@ConditionalOnProperty` không tìm thấy property hoặc giá trị khác yêu cầu.
- `@ConditionalOnMissingBean` thất bại vì đã có bean tương ứng.
- `@ConditionalOnWebApplication` không match vì ứng dụng chạy non-web.

**Quan trọng:** negative match **không tự động là lỗi**. Ví dụ ứng dụng CLI không cần servlet server thì WebMVC auto-config không match là điều đúng.

### Exclusions

Cho biết auto-configurations bị loại trừ bằng cấu hình như:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Đây là ví dụ có thể dùng trong project **cố ý không cần DataSource**. Nếu ứng dụng lại kỳ vọng Spring tạo DataSource, chính exclusion này có thể giải thích vì sao bean vắng mặt. Đừng copy cấu hình exclusion vào production chỉ để làm log “sạch”.

### Unconditional classes

Danh sách những auto-configuration candidates không có các điều kiện cần đánh giá. Sự xuất hiện trong danh sách **không tương đương** mọi bean bên trong chắc chắn đã được instantiate thành công. Nó chủ yếu hỗ trợ nhìn tổng thể quá trình lựa chọn cấu hình.

## 6. Hiểu các điều kiện quan trọng khi truy vết

| Condition | Nó kiểm tra gì? | Điểm cần xem khi không match |
| --- | --- | --- |
| `@ConditionalOnClass` | Class có trên classpath? | Thiếu dependency, version, starter, loại packaging |
| `@ConditionalOnMissingClass` | Class không có trên classpath? | Class có mặt nên nhánh “không có” không dùng |
| `@ConditionalOnBean` | Bean theo type/name đã tồn tại? | Bean không đăng ký, nằm ở context khác, không đúng type |
| `@ConditionalOnMissingBean` | Chưa có bean theo type/name? | Có bean custom khiến mặc định lùi lại (back-off) |
| `@ConditionalOnProperty` | Property có mặt/giá trị đúng? | Key sai, value khác, property source/profile chưa áp dụng |
| `@ConditionalOnBooleanProperty` | Giá trị boolean theo điều kiện? | Giá trị không đúng hoặc không tồn tại như yêu cầu |
| `@ConditionalOnWebApplication` | Context là web theo loại? | Thiếu web stack hoặc `WebApplicationType.NONE` |
| `@ConditionalOnNotWebApplication` | Context không phải web? | Đang có Servlet/Reactive context |
| `@ConditionalOnResource` | Resource trên classpath/URL tồn tại? | Đường dẫn hoặc packaging resource sai |
| `@ConditionalOnExpression` | Biểu thức SpEL đúng? | Giá trị expression hoặc thứ tự bean initialization |

Đây là các điều kiện Boot cung cấp, không phải các mức log. Một số condition được dùng ở `@Configuration` class, một số ở `@Bean` method; **nguồn (source)** trong report có thể là tên configuration class hoặc tên method tương ứng.

### Đọc property condition chính xác

Ví dụ:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "demo.greeting",
    name = "enabled",
    havingValue = "true")
GreetingService greetingService() {
    return () -> "hello";
}
~~~

Đây là một **đoạn method minh họa**, cần đặt vào class configuration và khai báo `GreetingService`. Nếu property `demo.greeting.enabled`:
- Vắng mặt → không match khi `matchIfMissing` mặc định false.
- Bằng `false` → không match.
- Bằng `true` → match.
- Có giá trị khác `true` khi sử dụng `havingValue="true"` → không match.

Khi không chỉ định `havingValue`, điều kiện mặc định của `@ConditionalOnProperty` thường coi property có mặt và không có giá trị chuỗi `false` là match; **đừng đánh đồng** với kiểm tra boolean nghiêm ngặt nếu dữ liệu có thể chứa giá trị lạ.

### Bean condition và thứ tự đăng ký

`@ConditionalOnBean` và `@ConditionalOnMissingBean` phụ thuộc vào những bean definitions đã được xử lý **tại thời điểm condition được đánh giá**. Vì thế Spring Boot khuyến nghị dùng chúng đặc biệt trong auto-configuration vốn được xử lý sau cấu hình do người dùng định nghĩa. Đừng đặt các annotation đó tùy tiện rồi giả định bean được khai báo ở bất cứ file nào cũng đã được biết ở thời điểm đánh giá.

### Class condition và dependency

Nếu report nói một thư viện còn thiếu:
1. Kiểm tra `pom.xml` hoặc Gradle dependencies có starter cần thiết.
2. Kiểm tra dependency scope (`test`, `provided`, `runtime`, optional...).
3. Kiểm tra dependency resolution và dependency tree.
4. Kiểm tra artifact cuối được đóng gói đúng, nhất là JAR/WAR hoặc image bị thiếu module.
5. Kiểm tra classpath đang chạy thực tế, không chỉ classpath trong IDE.

Không thêm toàn bộ starter bừa bãi chỉ để làm một condition match; phải biết feature cần thiết là gì.

## 7. Demo chạy được: thiếu bean do @ConditionalOnProperty

Ta tạo một ứng dụng Spring Boot 3.5.16, Java 17+, cố ý để một bean quan trọng **chỉ được tạo khi property bật**, trong khi một `ApplicationRunner` luôn yêu cầu bean đó. Nhờ vậy cùng một JAR có hai đường rõ ràng:

- Không có property → bean không đăng ký → startup thất bại.
- Có `--demo.greeting.enabled=true` → bean được đăng ký → runner chạy thành công.

Đây là ví dụ có chủ đích cho việc truy vết cấu hình, không mô phỏng lỗi network hay cơ sở dữ liệu.

### 7.1. Cấu trúc thư mục

~~~text
condition-debug-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/conditiondebug/
                └── ConditionDebugApplication.java
~~~

### 7.2. Tệp pom.xml

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
    <artifactId>condition-debug-demo</artifactId>
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

`spring-boot-starter` có Spring Framework, auto-configuration và logging phù hợp; không cần database, servlet container, Actuator hoặc profile riêng để chạy demo. Điều kiện không phụ thuộc môi trường ngoài.

### 7.3. File Java đầy đủ

Lưu thành `src/main/java/com/example/conditiondebug/ConditionDebugApplication.java`:

~~~java
package com.example.conditiondebug;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ConditionDebugApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConditionDebugApplication.class, args);
    }

    public interface GreetingService {
        String message();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.greeting",
            name = "enabled",
            havingValue = "true")
    GreetingService greetingService() {
        return () -> "hello";
    }

    @Bean
    ApplicationRunner greetingRunner(GreetingService service) {
        return args -> System.out.println(
                "RUNNER_GREETING=" + service.message());
    }
}
~~~

Đây là **một chương trình Java đầy đủ**, có một `main` và hai bean factory methods. `@SpringBootApplication` được meta-annotated như một configuration class; các method `@Bean` ở đây được Spring xử lý bình thường.

Cơ chế:
1. `greetingService()` chỉ được đăng ký thành bean nếu `demo.greeting.enabled=true`.
2. `greetingRunner(GreetingService service)` luôn yêu cầu một bean `GreetingService` khi container tạo runner bean.
3. Nếu property vắng mặt, Spring không đăng ký `greetingService`; việc tạo runner thiếu dependency và context refresh thất bại.
4. Nếu property bật, container tạo service, inject thành công và runner in một dòng khi startup kết thúc tới mốc runner.
5. Vì đây là CLI non-web, sau khi main/runner hoàn thành và không còn non-daemon thread, JVM thoát bình thường.

### 7.4. Biên dịch

Trong thư mục có `pom.xml`:

~~~bash
mvn package
~~~

Lệnh đóng gói tạo JAR:

~~~text
target/condition-debug-demo-0.0.1-SNAPSHOT.jar
~~~

Chạy bằng `java -jar` để dễ phân biệt process Java với Maven wrapper. Nếu Maven không resolve được dependency, đó là **lỗi build**, chưa phải lỗi khởi động mà `--debug` của Spring Boot có thể hỗ trợ.

### 7.5. Lần 1 — chạy không có property, chưa bật debug

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar
~~~

**Kết quả:** startup thất bại; không có dòng `RUNNER_GREETING=hello`. Một `FailureAnalyzer` thường cung cấp mô tả thiếu bean kiểu `GreetingService`, với hướng dẫn khai báo hoặc tạo bean phù hợp. Log thật có timestamp, thread, logger và tên class đầy đủ tùy phiên bản.

Bản **tóm tắt minh họa** (không phải log được copy nguyên văn từ một lần chạy):

~~~text
APPLICATION FAILED TO START

Description:
Parameter 0 of method greetingRunner ... required a bean of type
'...ConditionDebugApplication$GreetingService' that could not be found.

Action:
Consider defining a bean of type '...GreetingService'.
~~~

Đọc thông điệp này thấy **đang thiếu bean**, nhưng chưa thấy vì sao `greetingService()` không được đăng ký. Đây là lúc `--debug` hữu ích.

### 7.6. Lần 2 — vẫn thất bại, nhưng bật --debug

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --debug
~~~

Lỗi thiếu bean vẫn xảy ra, **debug không sửa lỗi**. Tuy nhiên log có thêm báo cáo điều kiện, tìm những từ khóa:

~~~text
CONDITIONS EVALUATION REPORT
Negative matches:
ConditionDebugApplication#greetingService
OnPropertyCondition
demo.greeting.enabled
~~~

Đây là **danh sách dấu hiệu cần tìm**, không phải các dòng log chắc chắn đứng liền nhau. Thông điệp thật có thể nói không tìm thấy property `enabled` theo prefix, hoặc property không bằng giá trị bắt buộc, và có thể có tên method/class ở định dạng khác.

Suy luận có căn cứ:

~~~text
Symptom:
  Không có bean GreetingService
        |
        v
Điều kiện của factory method:
  @ConditionalOnProperty(demo.greeting.enabled=true)
        |
        v
Negative match:
  Property không tồn tại hoặc không bằng true
        |
        v
Hệ quả:
  greetingService() không tạo bean
        |
        v
greetingRunner(GreetingService) không inject được
        |
        v
ApplicationContext refresh thất bại
~~~

Đây là cách nối **exception → bean bị thiếu → configuration source → điều kiện không match**. Đừng lấy một negative match ngẫu nhiên của database/web/security rồi kết luận nó gây lỗi; phải tìm source liên quan trực tiếp đến dependency đang thiếu.

**Đầu ra bổ sung tùy cấu hình:** Spring Boot có thể in lời nhắc kiểu chạy lại với `debug` nếu crash report chưa bật debug. Sau khi bật, phần Condition Evaluation Report có thể rất dài vì bao gồm nhiều auto-configurations không liên quan; đó là bình thường.

### 7.7. Lần 3 — sửa nguyên nhân, startup thành công

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --demo.greeting.enabled=true
~~~

Sau banner và log startup, **dòng do code demo tự in chính xác**:

~~~text
RUNNER_GREETING=hello
~~~

Tại sao?
- Property khớp `havingValue="true"`.
- Spring tạo bean `GreetingService`.
- Spring inject bean này vào method `greetingRunner`.
- Runner được gọi và in thông điệp.

JVM thường trả exit status **0** nếu không có lỗi ngoài dự kiến. Đây là chương trình CLI không-web, nên không có server cần dừng thủ công.

### 7.8. Lần 4 — thành công và vẫn bật debug để đối chiếu

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar \
  --demo.greeting.enabled=true --debug
~~~

Lệnh trên minh họa Bash/zsh với dấu `\` nối dòng. Trong PowerShell/cmd có thể đặt tất cả argument trên một dòng để tránh khác biệt shell:

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --demo.greeting.enabled=true --debug
~~~

Bây giờ:
- `RUNNER_GREETING=hello` vẫn được in.
- Report (nếu được log như cấu hình) có thể ghi factory method `greetingService` trong **positive matches** do property khớp.
- Các negative matches **khác** vẫn xuất hiện vì ứng dụng không dùng mọi tính năng auto-configuration.

So sánh **cùng một source, cùng một JAR, khác duy nhất property** là cách rất mạnh để xác định nguyên nhân của một điều kiện không khớp.

### 7.9. Thử giá trị false

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --demo.greeting.enabled=false --debug
~~~

Lần này property có mặt nhưng giá trị không đạt `havingValue="true"`, nên bean vẫn không được đăng ký và startup vẫn thất bại. Khác biệt với case property vắng mặt có thể được phản ánh trong ConditionOutcome message.

**Cẩn thận với kiểu boolean:** `@ConditionalOnProperty` trong ví dụ đang so sánh theo giá trị yêu cầu; nó không kiểm tra một đối tượng Java boolean đã được bind thành công trong mọi hoàn cảnh. Đối với cấu hình boolean phức tạp, hãy nắm rõ semantics của annotation và property source.

## 8. Chỉ in condition report mà không mở debug quá rộng

Tài liệu Spring Boot cho biết khi startup thất bại, có thể bật property `debug` **hoặc** bật mức DEBUG cho `ConditionEvaluationReportLoggingListener`.

Ví dụ trong `application.properties` để mở logger tập trung:

~~~properties
logging.level.org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener=DEBUG
~~~

Hoặc từ command line:

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --logging.level.org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener=DEBUG
~~~

Giá trị này nhắm tới logger của report listener. Nó không tương đương bật DEBUG cho package nghiệp vụ, không thể thay thế exception stack trace, và vẫn phải lưu ý report có thể không sẵn có nếu thất bại quá sớm.

### Điều chỉnh logging cho một subsystem cụ thể

Nếu report chỉ ra bean bị thiếu nhưng bạn cần biết bước nào khởi tạo thất bại, có thể bật thêm log cho đúng subsystem:

~~~properties
# Log ở package ứng dụng cần chẩn đoán.
logging.level.com.example.conditiondebug=DEBUG

# Ví dụ khi chẩn đoán web MVC trong app có MVC.
logging.level.org.springframework.web=DEBUG

# Ví dụ khi chẩn đoán Spring JDBC transaction.
logging.level.org.springframework.jdbc=DEBUG
~~~

Các ví dụ này **không nhất thiết tác động tới demo CLI** vì nó không có web/JDBC. Chỉ bật logger của tính năng thực sự có trong ứng dụng. Tránh `logging.level.root=TRACE` như bước đầu vì log có thể quá nhiều, khó tìm nguyên nhân và có nguy cơ lộ thông tin.

### Logging phải được cấu hình đủ sớm

Cấu hình logging của Spring Boot được thiết lập từ các giai đoạn rất sớm. Nếu lỗi xảy ra trước khi Environment/property sources được đọc đầy đủ, thay đổi trong một file cấu hình không được tải có thể không có tác dụng. Khi ấy dùng command-line property hoặc JVM/system environment phù hợp, và đọc kỹ lỗi đọc config đầu tiên.

## 9. Đọc báo cáo theo thứ tự: symptom → source → condition → remediation

Một workflow truy vết hiệu quả:

**Bước 1 — Lấy lỗi gốc.** Ghi lại exception type, method/constructor/class không inject được, property binding lỗi, port, file/resource hoặc message cụ thể.

**Bước 2 — Đọc FailureAnalyzer.** Nếu có phần `APPLICATION FAILED TO START` với `Description` và `Action`, đọc trước: nó thường mô tả nguyên nhân hành động tốt hơn một stack trace rất dài.

**Bước 3 — Bật --debug.** Chạy **cùng artifact** và giữ nguyên profiles, classpath, arguments ngoại trừ flag debug, để không thay đổi môi trường điều tra.

**Bước 4 — Tìm trong Condition Evaluation Report.** Tìm tên configuration class, method hoặc bean type liên quan tới lỗi ở bước 1. Đừng đọc tuần tự hàng trăm dòng khi đã biết tên bean bị thiếu.

**Bước 5 — Đọc chính xác condition outcome.** Ví dụ thiếu class, không tìm thấy property, giá trị property không như yêu cầu, bean đã tồn tại khiến default bean back-off, hoặc context không thuộc loại web cần thiết.

**Bước 6 — Kiểm tra cấu hình thực tế.** Xác nhận dependencies, profile, property source ưu tiên, env vars, tên bean và classpath chạy thực tế.

**Bước 7 — Đưa ra một giả thuyết kiểm chứng được.** Ví dụ “bean GreetingService bị bỏ qua vì demo.greeting.enabled thiếu”, không chỉ “Spring Boot auto-configuration lỗi”.

**Bước 8 — Sửa đúng nguyên nhân và chạy lại.** Nếu thêm property, kiểm tra report chuyển từ negative sang positive. Nếu thêm dependency, kiểm tra classpath thực. Nếu sửa code config, cần build artifact mới.

**Bước 9 — Tắt debug không cần thiết.** Giữ lại log nghiệp vụ/metrics đủ giám sát, không để debug quá rộng ở production.

### Ví dụ checklist chẩn đoán ngắn

~~~text
[ ] Tên exception/cause chain đã xác định
[ ] Có Description/Action từ FailureAnalyzer?
[ ] Cùng JAR và cùng profile giữa trước/sau --debug?
[ ] Condition report đã xuất hiện?
[ ] Tìm đúng configuration/method liên quan
[ ] Negative match là lỗi hay chỉ back-off bình thường?
[ ] Đối chiếu classpath, property values, bean definitions, web type
[ ] Test bản sửa với cùng môi trường
[ ] Xem root exception còn hay đã hết
[ ] Tắt logger chi tiết, không lưu secret
~~~

## 10. Phân tích các tình huống thực tế thường gặp

### 10.1. “Required a bean of type X that could not be found”

Khả năng:
- Bean X được bảo vệ bằng `@ConditionalOnProperty` nhưng key/value không khớp.
- Bean factory method X nằm trong config bị loại do `@ConditionalOnClass`.
- Class chứa `@Configuration` nằm ngoài package scanning hoặc không được import (đây là vấn đề scanning/import, **không chắc xuất hiện trong condition report**).
- Một profile bị thiếu, ví dụ `@Profile("prod")` không active; đây là condition của Spring Framework, dấu vết phụ thuộc giai đoạn và cơ chế report.
- Bean được đăng ký dưới type/name khác.
- Một `@ConditionalOnMissingBean` khiến bean mặc định back-off vì có một bean custom nhưng bean custom không đáp ứng injection mong đợi.

Cách xử lý: xem **bean definition nào đáng ra tạo X**, sau đó kiểm tra điều kiện/scope/scan chứ không tự thêm một `@Bean` thứ hai ngẫu nhiên.

### 10.2. “Property expected true but was false or missing”

Xem:
- `@ConditionalOnProperty(prefix=..., name=..., havingValue=...)`.
- Key YAML/properties có đúng namespace không?
- Profile-specific files có được load không?
- Property có bị override bởi env var/command line/Config Data không?
- Có dùng tên property và type đúng theo relaxed binding không?
- Một config server/Vault/secret source có thực sự được tải trước giai đoạn condition không?

Với ví dụ, `--demo.greeting.enabled=true` giải quyết. Trong hệ thống thật, sửa key đúng thay vì ép `matchIfMissing=true` bừa bãi; việc đó có thể kích hoạt feature khi chưa đủ dependency.

### 10.3. “@ConditionalOnClass did not find required class”

Đọc báo cáo như dấu hiệu classpath. Xác minh Maven/Gradle dependency và packaging JAR thực chạy. Không sửa bằng cách chỉ khai báo bean có tên tương tự type còn thiếu.

Ví dụ nếu auto-configuration servlet không match trong app CLI, đó là bình thường. Chỉ điều tra nếu ứng dụng thật sự kỳ vọng một servlet web server được tạo.

### 10.4. “@ConditionalOnMissingBean found beans of type ...”

Đây thường là hành vi **back-off đúng thiết kế**: Spring Boot không tạo mặc định vì ứng dụng đã có bean tùy chỉnh. Nếu bean custom hoạt động đúng, **không phải lỗi**.

Nếu bean custom cấu hình sai hoặc không đáp ứng type/qualifier mong đợi, hãy sửa bean custom. Không cần cố ép auto-configuration mặc định chạy song song.

### 10.5. “Not a servlet web application”

Nếu app được cấu hình `WebApplicationType.NONE` hoặc không có starter web, các servlet-specific auto-configurations không match là đúng. Nếu bạn mong có Tomcat/MVC, kiểm tra `spring-boot-starter-web`, SpringApplication web type, dependencies và những starter reactive/servlet đang có.

### 10.6. “Port 8080 already in use”

Đây thường là lỗi web server bind port, không phải do một condition không match. `FailureAnalyzer` có thể đưa ra Description/Action. Tập trung vào process đang dùng port, `server.port`, management port, network bind và quyền truy cập. Report điều kiện có thể chứng minh web server configuration đã được chọn, **nhưng không giải phóng cổng**.

### 10.7. “Failed to bind properties under ...”

Lỗi binding thường do type mismatch, giá trị sai format, validation, property source hoặc cấu hình YAML. Condition report có thể hữu ích nếu property còn quyết định một auto-configuration được load hay không, nhưng **thông báo binding error và cause chain mới là nguồn chính**.

Ví dụ property boolean được yêu cầu, nhưng config nhập một chuỗi không hợp lệ. Đừng kết luận chỉ từ một match/no-match nếu binding và condition áp dụng semantics khác nhau.

### 10.8. Bean đã match nhưng constructor ném lỗi

Một condition positive chỉ nói bean/cấu hình **đủ điều kiện được xét**, không chứng minh bean đã instantiate thành công. Nếu constructor gọi DB và ném `ConnectException`, xem exception, network, credentials và timeout. Report có thể chỉ xác nhận bean được đăng ký, nhưng nguyên nhân lỗi là **bên trong quá trình khởi tạo**.

### 10.9. Profile và môi trường khác nhau

Cùng code có thể tạo bean khác nhau vì:
- `spring.profiles.active`.
- `application-dev.yml` hoặc `application-prod.yml`.
- Env var trong container.
- `SPRING_APPLICATION_JSON`.
- Config server/secret manager.
- CLI overrides.
- Test property sources.
- Differences in dependency scope và classpath.

Khi đối chiếu hai report, cần ghi **artifact version, profiles, effective property sources và classpath**. Đừng kết luận một bản fix hiệu quả chỉ vì dev report khác prod report.

### 10.10. Cấu hình chạy sai ngay từ đầu

Nếu startup lỗi trước khi các auto-configuration conditions được đánh giá, report có thể không hiện. Ví dụ:
- YAML syntax sai làm config parser fail.
- Config import bắt buộc không truy cập được.
- Logging configuration lỗi khiến app không hoàn tất bootstrap.
- JVM không tải nổi main class.
- ClassNotFound/NoClassDefFoundError xảy ra quá sớm.

Trong các trường hợp này, **tìm lỗi đầu tiên có ý nghĩa theo thời gian** và kiểm tra packaging, config nguồn và command line. `--debug` hỗ trợ quan sát khi Boot chạy đủ xa, không phải công cụ thay thế mọi kiểm tra.

## 11. ConditionEvaluationReport API cho việc phân tích có cấu trúc

Ngoài logging, Spring Boot 3.5 cung cấp `org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport`. Javadoc có các API:

~~~java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

var bySource = report.getConditionAndOutcomesBySource();
var exclusions = report.getExclusions();
var unconditional = report.getUnconditionalClasses();
~~~

Đây là **đoạn minh họa trong code có một `ConfigurableApplicationContext context` hợp lệ**, không phải file Java độc lập. Import type `ConditionEvaluationReport` từ Spring Boot và cần context còn khả dụng. `getConditionAndOutcomesBySource()` trả map từ source name đến kết quả điều kiện; `getExclusions()` và `getUnconditionalClasses()` cho các phần tương ứng.

Phải hiểu hạn chế:
- Nếu startup thất bại trước khi main nhận được context, không thể đơn giản gọi `context.getBeanFactory()` từ main sau `SpringApplication.run`.
- Report chứa những điều kiện đã được ghi nhận; không phải một mô hình toàn diện của mọi bean/exception.
- Không nên dump nguyên map từ code nghiệp vụ/endpoint production chỉ để debug vì report có thông tin về cấu trúc ứng dụng.
- Khi cần startup failure report, **dùng listener/logging được Boot cung cấp** thường là tuyến an toàn và ít can thiệp hơn.

### ConditionEvaluationReportLoggingListener

Class `org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener` là một `ApplicationContextInitializer` viết report ra log. Ở Spring Boot 3.5, mặc định report được log mức DEBUG; trong case crash, nó có thể in lời nhắc bật debug.

Spring Boot cung cấp factory:

~~~java
ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
~~~

Đây là **đoạn minh họa** cần imports; khi dùng trong ngữ cảnh phù hợp như test `ApplicationContextRunner`, nó cho phép chọn mức log in report. Nó không phải thứ cần đăng ký lại một cách bừa bãi trong mọi ứng dụng vì Boot đã có cơ chế logging report cho đường startup.

### Ví dụ test auto-configuration bằng ApplicationContextRunner

Trong project có `spring-boot-starter-test` ở scope test, có thể kiểm tra một auto-configuration bằng `ApplicationContextRunner`:

~~~java
// Ví dụ ý tưởng trong JUnit test có dependency spring-boot-starter-test.
new ApplicationContextRunner()
    .withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))
    .withUserConfiguration(MyAutoConfiguration.class)
    .run(context -> {
        // Assert bean tồn tại/không tồn tại theo property trong test.
    });
~~~

Đoạn này **cố ý chỉ minh họa API**, không phải test runnable độc lập: cần class `MyAutoConfiguration` và các imports tương ứng. Việc test condition có thể xác minh rõ hành vi với/không có bean, property và classpath giả lập hơn là chỉ đọc log dài.

### Không dùng log report làm API nghiệp vụ

Condition report phục vụ **diagnostics và test**, không phải dữ liệu runtime cho quyết định nghiệp vụ. Nếu ứng dụng cần biết một feature có bật hay không, hãy dùng configuration properties, dependency injection hoặc feature flag contract rõ ràng thay vì parse text report.

## 12. Actuator /actuator/conditions: cách quan sát app đang chạy

Nếu ứng dụng đã startup **thành công** và có Spring Boot Actuator, endpoint `conditions` có thể cung cấp thông tin condition evaluation dưới dạng có cấu trúc. Đây là một công cụ bổ sung để phân tích “vì sao một auto-configuration được hoặc không được chọn” trong **ứng dụng đang sống**.

Trong ứng dụng web có dependency `spring-boot-starter-actuator` và được bảo vệ phù hợp, ví dụ:

~~~properties
management.endpoints.web.exposure.include=health,conditions
~~~

Sau đó có thể truy cập:

~~~text
GET /actuator/conditions
~~~

Response thông thường chứa các nhóm như `positiveMatches`, `negativeMatches`, `unconditionalClasses` trong cấu trúc phù hợp với context. Tên và cấu trúc field chi tiết tùy version Actuator.

**Đặc biệt chú ý:**
- Demo mục 7 chỉ có `spring-boot-starter`, **không có Actuator và không có web server**, nên không tồn tại `/actuator/conditions` ở demo đó. Muốn thử endpoint phải tự tạo ứng dụng web với Actuator.
- Một app đã **khởi động thất bại** không có HTTP endpoint để truy cập. Đừng yêu cầu `/actuator/conditions` trên một instance vừa crash.
- Endpoint conditions không được expose qua HTTP chỉ vì có Actuator trong cấu hình thông thường; phải cấu hình exposure và quyền truy cập thích hợp.
- Endpoint có thể tiết lộ class names, bean details và cấu trúc application. **Không phơi bày công khai** qua Internet; ưu tiên management port riêng, authentication/authorization và network policy.
- Không bật `management.endpoints.web.exposure.include=*` trong production chỉ để xem một report.

Nếu chỉ cần debug startup failure, **command line --debug** là đường đơn giản hơn, vì không phụ thuộc việc HTTP server startup thành công.

## 13. Kết hợp report với log và trace an toàn

Khi thu thập một incident, nên giữ tối thiểu:

~~~text
Incident ID:
Application/artifact version:
Spring Boot version:
JDK version:
Environment / active profiles:
Command line flags (đã lọc secrets):
Timestamp bắt đầu và kết thúc:
Exception type + causal chain:
FailureAnalyzer Description/Action:
Relevant Negative/Positive matches:
Source configuration/bean:
Hypothesis:
Fix applied:
Outcome after rerun:
~~~

Đây là mẫu phiếu điều tra, không phải dữ liệu tự động in bởi Spring.

### Không chia sẻ nguyên log nếu có secrets

DEBUG logs và stack traces có thể chứa:
- Environment property names/values trong một số thông điệp.
- Tên host, URL nội bộ, bean types, classpath, file paths.
- Username, connection strings hoặc headers nếu code/thư viện log thiếu kiểm soát.
- Chi tiết bảo mật và topology trong diagnostics.

Cần lọc/redact mật khẩu, token, API key, secret paths và thông tin khách hàng trước khi gửi log ra hệ thống bên ngoài. Không giả định mọi báo cáo condition có mật khẩu, nhưng cũng không coi toàn bộ log debug là dữ liệu công khai vô hại.

### Chạy debug trong môi trường production

Ưu tiên:
1. Tái hiện ở staging hoặc môi trường cách ly với artifact/config tương đương.
2. Bật logging **chọn lọc và có thời hạn** nếu cần debug production.
3. Giới hạn nơi lưu log, quyền truy cập và retention.
4. Tránh quá nhiều log làm tăng dung lượng, CPU, I/O hoặc che root cause.
5. Tắt mức DEBUG/TRACE sau khi thu đủ bằng chứng.

Không thay `spring.main.lazy-initialization`, xóa bean, thêm starter hoặc sửa các condition chỉ nhằm “cho app lên” trước khi hiểu tác động của thay đổi đó.

## 14. Dấu hiệu phân biệt condition report với các báo cáo khác

| Công cụ/thông tin | Khi nào có | Dùng cho |
| --- | --- | --- |
| Condition Evaluation Report | Khi conditions đã được đánh giá và logging/report sẵn có | Vì sao config/bean conditional match hay không |
| FailureAnalyzer output | Khi Boot có analyzer thích hợp cho exception | Nguyên nhân và hành động sửa cụ thể |
| Java exception stack trace | Khi exception/logging hiển thị | Nguồn phát sinh lỗi, cause chain |
| `ApplicationFailedEvent` | Khi startup chạy vào đường thất bại tương ứng | Tích hợp listeners/monitoring |
| `/actuator/conditions` | App chạy được, Actuator endpoint được cấu hình expose | Quan sát conditions trên app đang hoạt động |
| `ApplicationContextRunner` | Trong test auto-configuration | Kiểm tra match/back-off theo property/classpath |
| `ConditionEvaluationReport` API | Có bean factory/report để đọc | Phân tích có cấu trúc, công cụ nội bộ |
| Remote JVM debugger (JDWP) | Khi attach debugger được cấu hình | Theo dõi call stack/variables bằng breakpoint |

**Nhầm lẫn nguy hiểm:** Một report cho biết “DataSourceAutoConfiguration did not match” không nhất thiết là lý do ứng dụng thất bại vì một web controller khác. Chỉ dùng report khi có liên hệ nhân quả với symptom, exception và bean đang điều tra.

## 15. Quy trình truy vết mẫu theo tình huống

### Tình huống A — thiếu bean do property (demo)

~~~text
Symptom:
  GreetingService bean missing
Report:
  ConditionDebugApplication#greetingService -> Negative match
  demo.greeting.enabled không phải true
Remediation:
  --demo.greeting.enabled=true
Validation:
  RUNNER_GREETING=hello
~~~

Trong demo, thay đổi duy nhất là property, nên giả thuyết có độ tin cậy cao. Trong ứng dụng thật, hãy kiểm tra các điều kiện còn lại và classpath/bean scope.

### Tình huống B — auto-configuration bị loại trừ

~~~text
Symptom:
  Không có DataSource mặc định
Report:
  Exclusions chứa DataSourceAutoConfiguration
Remediation:
  Xem vì sao có spring.autoconfigure.exclude
  Chỉ xóa exclusion nếu ứng dụng thực sự cần auto-configured DataSource
Validation:
  Bean DataSource xuất hiện và kết nối được theo cấu hình
~~~

Không nên thêm `DataSourceAutoConfiguration` vào ứng dụng không cần DB chỉ vì report có Exclusions. Những exclusions có thể chủ động và hoàn toàn đúng.

### Tình huống C — bean custom làm auto-config back-off

~~~text
Symptom:
  Tưởng Spring Boot sẽ tạo bean mặc định
Report:
  @ConditionalOnMissingBean không match do bean custom hiện hữu
Remediation:
  Kiểm tra bean custom và yêu cầu injection/qualifier
Validation:
  Bean cần thiết đúng type và hành vi
~~~

Ở đây, việc không khớp là một phần của cơ chế ưu tiên cấu hình người dùng, không phải bug của Boot.

### Tình huống D — classpath bị thiếu

~~~text
Symptom:
  Bean liên quan Jackson/Servlet/JDBC không xuất hiện
Report:
  @ConditionalOnClass không tìm thấy type cần thiết
Remediation:
  Kiểm tra dependency, scope, packaging và artifact thực chạy
Validation:
  Type trên classpath, condition match nếu các điều kiện khác cũng đạt
~~~

Không phải cứ thêm đúng dependency là chắc chắn xong: có thể còn một `@ConditionalOnProperty` hoặc `@ConditionalOnWebApplication` khác.

### Tình huống E — bean được chọn nhưng fail khi tạo

~~~text
Symptom:
  BeanCreationException -> SQLException/ConnectException
Report:
  Configuration có thể Positive match
Remediation:
  Xem cause chain, credentials, network, DB URL, timeout
Validation:
  Bean được tạo và health check nghiệp vụ đạt
~~~

Kết quả positive không đủ để khẳng định hệ thống đã kết nối thành công; nó chỉ phản ánh **vòng đánh giá condition**.

### Tình huống F — không có report dù đã --debug

~~~text
Symptom:
  App dừng ở bootstrap/logging/config import
Report:
  Không thấy CONDITIONS EVALUATION REPORT
Remediation:
  Đọc exception sớm nhất, kiểm tra config/packaging/JVM args
Validation:
  App đi qua được phase bootstrap trước khi tiếp tục kiểm tra conditions
~~~

Không sửa bằng cách thử bật thêm hàng chục logger vô tội vạ khi lỗi gốc là file cấu hình không thể parse.

## 16. Những lỗi sử dụng --debug thường gặp

| Sai lầm | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| “--debug bật DEBUG cho mọi logger” | Boot chỉ chọn một số logger lõi | Dùng `logging.level.<package>=DEBUG` nếu cần |
| Dùng JDWP và nghĩ giống --debug | JDWP là debugger JVM | Phân biệt log diagnostics và breakpoint |
| Coi mọi Negative match là lỗi | Auto-config cố ý bỏ qua tính năng không dùng | Chỉ điều tra source liên quan symptom |
| Coi Positive match là bean đã khởi tạo xong | Constructor/Bean method vẫn có thể fail | Đối chiếu stack trace |
| Chạy debug với profile/classpath khác bản lỗi | Thay nhiều biến cùng lúc, khó kết luận | Giữ cùng artifact và config, chỉ bật debug |
| Không đọc FailureAnalyzer | Bỏ qua Description/Action cụ thể | Đọc analyzer trước report |
| Chỉ đọc dòng exception cuối | Bỏ qua root cause và nested causes | Theo cause chain và source config |
| Copy cấu hình exclusion để “giảm lỗi” | Có thể loại nhầm bean bắt buộc | Chỉ exclude khi hiểu feature |
| Thêm `matchIfMissing=true` để ép bean | Có thể bật feature sai môi trường | Sửa key/giá trị property đúng |
| Dump report ra HTTP công khai | Lộ cấu trúc ứng dụng | Bảo vệ Actuator conditions |
| Dùng /actuator/conditions khi app crash | Endpoint không còn phục vụ | Dùng startup logs và --debug |
| Không phân biệt Maven wrapper với JAR | Log/exit status có thể qua lớp wrapper | Khi cần, chạy `java -jar` trực tiếp |
| Bật root TRACE vô thời hạn | Log khổng lồ, quá tải hoặc lộ dữ liệu | Log có chọn lọc, thời hạn ngắn |
| Nghĩ debug sửa lỗi DB/port | Debug chỉ thêm thông tin | Sửa root cause thực |
| Không xác minh fix | Negative match có thể chuyển thành lỗi khác | Rerun và kiểm tra startup/behavior |
| Bỏ qua test khi nâng version Boot | Điều kiện/auto-config thay đổi qua version | So sánh behavior và report trên version mục tiêu |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `java -jar app.jar --debug` có tương đương `logging.level.root=DEBUG` không?

**Trả lời:** Không. Flag debug của Boot tăng log cho một tập core logger và hỗ trợ in condition report, không bật DEBUG cho mọi logger.

**Câu 2.** Condition Evaluation Report ghi điều gì?

**Trả lời:** Kết quả đánh giá những `Condition` được Spring Boot xử lý, theo từng configuration class/method source, kèm lý do match hoặc không match.

**Câu 3.** Nếu có 200 negative matches, ứng dụng chắc chắn lỗi?

**Trả lời:** Không. Nhiều auto-configuration cố ý không được dùng vì classpath, loại application hoặc property không phù hợp.

**Câu 4.** Report nói `@ConditionalOnMissingBean` không match vì một bean custom có sẵn. Đây có phải lỗi?

**Trả lời:** Thường là back-off đúng thiết kế. Chỉ là vấn đề nếu bean custom không cung cấp hành vi/type mà ứng dụng thực sự cần.

**Câu 5.** Vì sao demo mục 7 thiếu GreetingService?

**Trả lời:** `@ConditionalOnProperty` trên bean method đòi `demo.greeting.enabled=true`. Khi không có property, method không được đăng ký thành bean; method tạo runner yêu cầu GreetingService nên injection thất bại.

**Câu 6.** Thêm `--debug` có làm demo khởi động thành công không?

**Trả lời:** Không. Nó bổ sung report để chẩn đoán; muốn thành công cần đặt property đúng hoặc sửa thiết kế dependency.

**Câu 7.** Report nói bean positive match thì `BeanCreationException` không thể xảy ra?

**Trả lời:** Sai. Điều kiện match chỉ cho phép đăng ký/đánh giá cấu hình; constructor hoặc factory method vẫn có thể ném exception.

**Câu 8.** Khi app crash, có thể gọi `/actuator/conditions` để xem báo cáo không?

**Trả lời:** Không nếu HTTP endpoint đã không còn phục vụ. Actuator conditions hữu ích cho app đang chạy, có dependency, exposure và authorization phù hợp.

**Câu 9.** Làm sao bật riêng report logger?

**Trả lời:** Dùng `logging.level.org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener=DEBUG` hoặc bật `debug=true` cho chế độ mặc định.

**Câu 10.** Vì sao report không xuất hiện nếu YAML hỏng rất sớm?

**Trả lời:** Ứng dụng có thể chết trước khi đến giai đoạn các conditions được đánh giá và report đủ dữ liệu; phải ưu tiên lỗi parser/config đầu tiên.

**Câu 11.** `ApplicationStartedEvent` có được phát khi context refresh thất bại?

**Trả lời:** Không trong đường startup thông thường vì Started cần context refresh hoàn tất. Trên đường thất bại có `ApplicationFailedEvent` khi SpringApplication xử lý exception.

**Câu 12.** Có nên gửi nguyên DEBUG log production vào một issue công khai?

**Trả lời:** Không. Cần redact secret, host nội bộ và dữ liệu nhạy cảm, giới hạn người nhận và retention.

**Câu 13.** Một property vắng mặt và property bằng false có luôn cùng ConditionOutcome message?

**Trả lời:** Không. Cả hai đều có thể khiến điều kiện `havingValue=true` không match, nhưng thông điệp đánh giá có thể mô tả lý do khác nhau.

**Câu 14.** Khi báo cáo ghi class không có trên classpath, bước xác minh nào quan trọng nhất?

**Trả lời:** Kiểm tra dependency và artifact/classpath **thực chạy**, không chỉ file khai báo build trên máy local.

**Câu 15.** Condition report có thay thế stack trace hoặc FailureAnalyzer không?

**Trả lời:** Không. Nó bổ sung nguyên nhân tại tầng lựa chọn conditional configurations, còn failure analyzer và exception chain mô tả các kiểu lỗi startup rộng hơn.

## 18. Bài tập thực hành

### Bài tập A — xác định negative match

Chạy demo **không có property** với `--debug`. Tìm source `ConditionDebugApplication#greetingService` hoặc tên tương đương trong report. Ghi lại chính xác ConditionOutcome về `demo.greeting.enabled`. Giải thích vì sao runner bị thiếu dependency.

### Bài tập B — property vắng và property false

Chạy lần lượt:

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --debug
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --demo.greeting.enabled=false --debug
~~~

So sánh thông điệp negative match. Trong cả hai trường hợp, bean không có; tìm điểm khác nhau giữa **missing property** và **non-matching value** nếu report trình bày.

### Bài tập C — positive match và kết quả runner

Chạy với `--demo.greeting.enabled=true --debug`. Xác minh:
- App khởi động thành công.
- Có marker `RUNNER_GREETING=hello`.
- Source liên quan chuyển sang positive match (khi report được in).
- Những negative matches khác vẫn tồn tại bình thường.

### Bài tập D — thay chỉ định havingValue

Thử đổi `havingValue="true"` thành `havingValue="yes"` rồi rebuild. Dự đoán behavior với `--demo.greeting.enabled=true` và `--demo.greeting.enabled=yes`; giải thích vì sao check condition này dựa trên giá trị được chỉ định.

### Bài tập E — chỉ bật report logger

Không dùng `--debug`. Chạy app thiếu bean với:

~~~bash
java -jar target/condition-debug-demo-0.0.1-SNAPSHOT.jar --logging.level.org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener=DEBUG
~~~

So sánh lượng log với bản `--debug` và xác định report có xuất hiện không.

### Bài tập F — classpath condition

Thêm một configuration class có `@ConditionalOnClass` cho một type tùy chọn, rồi chạy khi type có/không có mặt trên classpath. Quan sát source và outcome; tránh tham chiếu trực tiếp vào một type không tồn tại trong signature của method bắt buộc load.

### Bài tập G — bean back-off

Tạo một auto-configuration có `@ConditionalOnMissingBean` và một bean custom cùng type. So sánh report có và không có bean custom; giải thích vì sao negative match có thể là đúng thiết kế.

### Bài tập H — sai đường dẫn cấu hình

Đổi `demo.greeting.enabled` thành một key sai chính tả. Chạy debug và kiểm tra report. Sau đó sửa property và chạy lại. Trình bày root cause theo chuỗi “missing bean → condition → property”.

### Bài tập I — port conflict khác condition mismatch

Tạo web app với Spring MVC, cố ý cho hai process cùng dùng một port. So sánh `FailureAnalyzer` với Condition Evaluation Report khi port bind thất bại. Không kết luận một negative match bất kỳ là nguyên nhân của lỗi port.

### Bài tập J — kiểm thử startup failure

Với `spring-boot-starter-test`, sử dụng `ApplicationContextRunner` để kiểm tra:
- Property false → bean conditional vắng.
- Property true → bean conditional có mặt.
- Bean custom tồn tại → default bean có `@ConditionalOnMissingBean` back-off.

Sử dụng assertion về bean presence và outcome, **không chỉ assert text log**, vì format log có thể thay đổi qua phiên bản.

## 19. Tài liệu chính thức

- [Spring Boot 3.5 — SpringApplication: Startup Failure](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): `FailureAnalyzer`, startup failure, bật `debug` hoặc logger của condition report.
- [Spring Boot 3.5 — Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html): `--debug`, `debug=true`, `--trace`, các logger được chọn và cấu hình logging levels.
- [Spring Boot 3.5 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html): điều kiện `OnClass`, `OnBean`, `OnMissingBean`, `OnProperty` và `ApplicationContextRunner`.
- [Spring Boot 3.5.16 — ConditionEvaluationReport Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html): condition outcomes by source, exclusions, unconditional classes.
- [Spring Boot 3.5.16 — ConditionEvaluationReportLoggingListener Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html): logger DEBUG, `forLogLevel(LogLevel)`.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): `conditions` endpoint và kiểm soát exposure.
- [Spring Boot 3.5.16 — ConditionalOnProperty Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): `prefix`, `name`, `havingValue`, `matchIfMissing`.

### Ghi nhớ cuối cùng

1. `--debug` cung cấp **thông tin truy vết**, không sửa lỗi khởi động.
2. Nó chỉ bật DEBUG cho **một tập core logger**, không đổi mọi logger sang DEBUG.
3. **Condition Evaluation Report** trả lời “điều kiện nào match/no-match và vì sao”, không đồng nghĩa stack trace.
4. `Negative matches` là bình thường; chỉ những source liên quan bean/feature bị thiếu mới là manh mối trực tiếp.
5. `Positive matches` không bảo đảm bean đã khởi tạo thành công.
6. Luôn kết hợp report với **FailureAnalyzer, exception cause chain, property sources, active profiles và classpath**.
7. Nếu startup thất bại quá sớm, report có thể không có; ưu tiên lỗi bootstrap đầu tiên.
8. `/actuator/conditions` dành cho app chạy được và phải được bảo vệ; không thay cho `--debug` của app đã crash.
9. Demo cho thấy chỉ cần thay `demo.greeting.enabled` từ vắng/false thành true, bean conditional được tạo và runner thành công.
10. Thu thập log an toàn, redact secrets, tắt debug sau điều tra và kiểm chứng fix bằng chạy lại đúng artifact/môi trường.
