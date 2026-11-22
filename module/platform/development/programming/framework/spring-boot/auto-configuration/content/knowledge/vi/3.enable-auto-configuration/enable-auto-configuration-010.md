# Thiết lập ứng dụng tối thiểu để quan sát tự cấu hình mà không cần máy chủ web

## 1. Mục tiêu và bức tranh tổng thể

Để hiểu **Spring Boot auto-configuration**, ta không cần tạo REST API, controller, cổng HTTP hoặc chạy Tomcat. Một ứng dụng console chỉ chứa `ApplicationContext` đã đủ để quan sát cách Spring Boot tìm các cấu hình ứng viên, đánh giá điều kiện, đăng ký bean và quyết định bean nào tồn tại.

Trong bài này, bạn sẽ tạo một ứng dụng Spring Boot tối thiểu bằng **Java 17+ và Spring Boot 3.3.13**. Ứng dụng khởi chạy ở chế độ **không phải web** (`WebApplicationType.NONE`), tự thoát sau khi in kết quả và minh họa ba hành vi:

1. Có cấu hình tự động và điều kiện phù hợp: Boot tạo một bean mặc định.
2. Ứng dụng khai báo bean của riêng nó: bean mặc định nhường chỗ vì `@ConditionalOnMissingBean`.
3. Tắt cấu hình bằng thuộc tính hoặc loại trừ auto-configuration: bean tự động không xuất hiện.

Chúng ta sẽ dùng hai nguồn bằng chứng: trạng thái bean trong `ApplicationContext` và *Condition Evaluation Report*, nơi Spring Boot ghi lại lý do điều kiện khớp/không khớp.

~~~text
                       Spring Boot console application
                                 |
        @SpringBootApplication  |  .web(WebApplicationType.NONE)
                                 v
                         AnnotationConfigApplicationContext
                                 |
                 @EnableAutoConfiguration được kích hoạt
                                 |
                   đọc AutoConfiguration.imports
                                 |
                   DemoAutoConfiguration ứng viên
                                 |
                 classpath/property/bean conditions
                                 |
                +----------------+----------------+
                |                                 |
             khớp điều kiện                  không khớp
                |                                 |
     BeanDefinition mặc định               không đăng ký
                |
      tạo bean khi context refresh
                |
                v
      ApplicationContext / ConditionEvaluationReport
                |
           in kết quả -> đóng context -> tiến trình kết thúc
~~~

**Giới hạn quan trọng:** tự cấu hình không phải chỉ hoạt động trong web app. Các cấu hình cho logging, JSON, task execution, properties, messaging và nhiều thư viện khác có thể hoạt động trong ứng dụng không có web server nếu dependency và điều kiện tương ứng phù hợp.

## 2. Chọn dependency nhỏ nhất đủ cho thí nghiệm

Ta dùng `spring-boot-starter` thay vì `spring-boot-starter-web`. Starter cơ bản cung cấp các thành phần cho vòng đời ứng dụng, auto-configuration, logging và context; nó **không** cần Servlet container hoặc Netty server để chạy ví dụ này.

### `pom.xml`

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

    <groupId>lab</groupId>
    <artifactId>auto-configuration-console</artifactId>
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

Bạn cần **JDK 17 trở lên** và Maven tương thích (ví dụ Maven 3.9+). Có thể dùng Gradle thay cho Maven; cơ chế auto-configuration không thay đổi. Lựa chọn Maven ở đây giúp ví dụ độc lập và dễ sao chép, không phụ thuộc cấu trúc build của một repository cụ thể.

### Cây thư mục hoàn chỉnh

~~~text
auto-configuration-console/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── lab/
        │       ├── app/
        │       │   └── InspectApplication.java
        │       ├── contract/
        │       │   └── DemoService.java
        │       └── autocfg/
        │           └── DemoAutoConfiguration.java
        └── resources/
            └── META-INF/
                └── spring/
                    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Trong cấu trúc này, class ứng dụng nằm ở `lab.app`; auto-configuration nằm ở package **ngang cấp** `lab.autocfg`, ngoài phạm vi component scan mặc định. Điều đó rất quan trọng để chứng minh class cấu hình được tải từ `AutoConfiguration.imports`, chứ không phải vô tình được tìm thấy bởi `@ComponentScan`.

## 3. Ba class Java và một file đăng ký ứng viên

### 3.1. Hợp đồng dịch vụ: `DemoService.java`

~~~java
package lab.contract;

public interface DemoService {
    String origin();
}
~~~

Đây là interface Java thông thường. Không có `@Component` nên Spring không tự tạo bean từ interface này. Nó cho phép ta quan sát một bean cùng kiểu có thể đến từ **auto-configuration** hoặc **cấu hình do ứng dụng tự khai báo**.

### 3.2. Cấu hình tự động: `DemoAutoConfiguration.java`

~~~java
package lab.autocfg;

import lab.contract.DemoService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(DemoService.class)
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class DemoAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(DemoService.class)
    public DemoService defaultDemoService() {
        return () -> "auto";
    }
}
~~~

Mỗi annotation đảm nhiệm một bước:

- `@AutoConfiguration`: khai báo đây là một lớp cấu hình tự động Spring Boot. Về bản chất, nó là cấu hình Spring với `proxyBeanMethods=false`.
- `@ConditionalOnClass(DemoService.class)`: chỉ áp dụng cấu hình nếu kiểu `DemoService` có trên classpath. Trong thí nghiệm, điều kiện này luôn đạt do interface nằm trong project.
- `@ConditionalOnProperty(...)`: chỉ áp dụng cấu hình nếu `demo.feature.enabled=true`; vì `matchIfMissing=true`, **không khai báo thuộc tính** cũng được tính là phù hợp.
- `@Bean`: cung cấp một định nghĩa bean tên `defaultDemoService`, kiểu `DemoService`.
- `@ConditionalOnMissingBean(DemoService.class)`: chỉ cho phép bean mặc định khi chưa có bean `DemoService` khác mà điều kiện có thể nhìn thấy.

Điều kiện ở mức **class** khác điều kiện ở mức **method**. Khi property không phù hợp, cả cấu hình tự động bị bỏ qua. Khi class vẫn đủ điều kiện nhưng ứng dụng đã có bean `DemoService`, chỉ bean mặc định bị bỏ qua. Hai kết quả đó sẽ được phân biệt bằng thí nghiệm.

**Không viết thêm `@ComponentScan` trên class auto-configuration.** Spring Boot khuyến nghị auto-configuration được đăng ký thông qua file imports và sử dụng `@Import` có chủ đích nếu cần chia nhỏ cấu hình. Trong thí nghiệm, component scan từ `lab.app` không nhìn thấy `lab.autocfg`.

### 3.3. Đăng ký ứng viên bằng `AutoConfiguration.imports`

Tạo tệp **đúng tên và đường dẫn**:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung chỉ một dòng:

~~~text
lab.autocfg.DemoAutoConfiguration
~~~

Mỗi dòng khai báo tên lớp đầy đủ của một auto-configuration ứng viên. Trong Spring Boot 3.x, file này là cơ chế đăng ký auto-configuration bằng JAR. Chỉ có annotation `@AutoConfiguration` trên Java class mà **không đăng ký trong imports** thì nó sẽ không được chọn tự động qua quy trình này.

**Phân biệt:** file `AutoConfiguration.imports` là danh sách **class ứng viên**, không phải danh sách bean sẽ chắc chắn có trong context. Spring Boot còn áp dụng exclusions, điều kiện classpath, property và bean.

### 3.4. Ứng dụng console: `InspectApplication.java`

~~~java
package lab.app;

import lab.contract.DemoService;
import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class InspectApplication {

    @Bean
    @ConditionalOnProperty(
        prefix = "demo",
        name = "custom",
        havingValue = "true"
    )
    DemoService customDemoService() {
        return () -> "custom";
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(InspectApplication.class)
                    .web(WebApplicationType.NONE)
                    .bannerMode(Banner.Mode.OFF)
                    .run(args)) {

            DemoService service =
                context.getBeanProvider(DemoService.class).getIfAvailable();

            ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

            ConditionEvaluationReport.ConditionAndOutcomes classConditions =
                report.getConditionAndOutcomesBySource().get(
                    "lab.autocfg.DemoAutoConfiguration"
                );

            System.out.println("webServer=" +
                (context instanceof WebServerApplicationContext));
            System.out.println("defaultBean=" +
                context.containsBean("defaultDemoService"));
            System.out.println("customBean=" +
                context.containsBean("customDemoService"));
            System.out.println("selected=" +
                (service == null ? "none" : service.origin()));
            System.out.println("autoConfigClassMatched=" +
                (classConditions != null && classConditions.isFullMatch()));
        }
    }
}
~~~

Ứng dụng có đúng một điểm khởi động `main`, một cấu hình mặc định được nhập tự động và một bean tùy chọn do người dùng định nghĩa:

- `@SpringBootApplication` kích hoạt `@EnableAutoConfiguration` và component scan. Class `lab.autocfg.DemoAutoConfiguration` **không** nằm trong vùng scan từ `lab.app`.
- `SpringApplicationBuilder(...).web(WebApplicationType.NONE)` buộc Boot sử dụng chế độ không phải web.
- `bannerMode(Banner.Mode.OFF)` loại banner, giúp log gọn hơn; đây **không** phải thao tác tắt auto-configuration.
- `try (ConfigurableApplicationContext ...)` bảo đảm context được đóng khi mã bên trong kết thúc.
- `customDemoService()` chỉ tạo bean nếu truyền `--demo.custom=true`.
- `context.getBeanProvider(DemoService.class).getIfAvailable()` cho phép kiểm tra cả trường hợp **không có bean** mà không làm ứng dụng lỗi.
- `ConditionEvaluationReport.get(context.getBeanFactory())` lấy báo cáo điều kiện bên trong context. Biến `classConditions` chỉ xem điều kiện **trên lớp auto-configuration**, không phản ánh đầy đủ các điều kiện của method `@Bean`.

Với ứng dụng nhỏ này, nếu bạn thay `getIfAvailable()` bằng injection bắt buộc theo kiểu `DemoService`, trường hợp không có bean có thể gây lỗi khi khởi động. Ta dùng lookup tùy chọn để các trạng thái đều quan sát được.

## 4. Vì sao `WebApplicationType.NONE` quan trọng?

Spring Boot thường suy ra loại ứng dụng từ classpath:

- **`SERVLET`:** dùng mô hình Servlet web application khi các loại class liên quan có mặt và phù hợp.
- **`REACTIVE`:** dùng mô hình reactive web application trong trường hợp classpath phù hợp.
- **`NONE`:** không khởi tạo web application context.

Mặc dù `spring-boot-starter` cơ bản không cần web server, ví dụ này còn **thiết lập NONE tường minh** để khóa mục tiêu thí nghiệm. Nếu sau này vô tình thêm web starter, mã vẫn chủ động chạy ở chế độ non-web.

Có ba cách thường gặp để chọn chế độ NONE:

~~~java
// Cách 1: builder, được dùng trong ví dụ đầy đủ.
new SpringApplicationBuilder(InspectApplication.class)
    .web(WebApplicationType.NONE)
    .run(args);
~~~

~~~java
// Cách 2: SpringApplication API.
SpringApplication application =
    new SpringApplication(InspectApplication.class);
application.setWebApplicationType(WebApplicationType.NONE);
application.run(args);
~~~

~~~properties
# Cách 3: src/main/resources/application.properties
spring.main.web-application-type=none
~~~

**Ba đoạn trên minh họa các lựa chọn thay thế**, không ghép đồng thời vào cùng một file. Cách thứ hai cần import `org.springframework.boot.SpringApplication` và `WebApplicationType`.

Chế độ NONE **không tắt Spring container** hoặc auto-configuration; nó chỉ nói rằng Spring Boot không tạo một web application context có embedded web server. Các bean độc lập với web vẫn được quản lý. Một số auto-configuration được đánh dấu `@ConditionalOnWebApplication` sẽ không khớp; những cấu hình có `@ConditionalOnNotWebApplication` có thể khớp tùy điều kiện khác.

### Không có web server khác gì không có cổng mở?

Ứng dụng non-web sẽ **không khởi động HTTP server mặc định của Spring Boot**. Tuy nhiên, nếu một bean do bạn tự viết hoặc một thư viện tùy ý chủ động mở socket, `WebApplicationType.NONE` không ngăn hoạt động đó. Trong ví dụ này không có bean mạng, nên không khởi động máy chủ HTTP.

Ta in `webServer=false` bằng cách kiểm tra context có phải `WebServerApplicationContext` hay không. Điều này xác nhận **loại context** thay vì cố gửi HTTP request đến một cổng đoán trước.

## 5. Chạy lần đầu và đọc kết quả

Đứng tại thư mục `auto-configuration-console` chứa `pom.xml`:

~~~bash
java -version
mvn -version
mvn -q spring-boot:run
~~~

Lưu ý: các lệnh kiểm tra version in thêm thông tin riêng. Lệnh Maven có thể in log Spring Boot; phần sau chỉ liệt kê **năm dòng do các câu `System.out.println` trong chương trình phát ra**, không phải toàn bộ stdout/stderr.

~~~text
webServer=false
defaultBean=true
customBean=false
selected=auto
autoConfigClassMatched=true
~~~

Diễn giải từng dòng:

1. `webServer=false`: context không phải loại `WebServerApplicationContext`.
2. `defaultBean=true`: bean `defaultDemoService` từ auto-configuration đã được đăng ký.
3. `customBean=false`: chưa bật điều kiện property của bean người dùng.
4. `selected=auto`: kiểu `DemoService` được giải quyết sang bean mặc định.
5. `autoConfigClassMatched=true`: các điều kiện của lớp `DemoAutoConfiguration` được ghi nhận khớp.

Tại sao không phải `selected=none`? Vì `DemoService` có trên classpath, `demo.feature.enabled` chưa có nên phù hợp với `matchIfMissing=true`, và chưa có bean cùng kiểu do ứng dụng cung cấp.

### Chạy JAR thay vì plugin Maven

~~~bash
mvn -q -DskipTests package
java -jar target/auto-configuration-console-1.0.0.jar
~~~

Khi `main` hoàn thành, context được đóng bởi `try-with-resources` và tiến trình bình thường sẽ kết thúc. Vì không có HTTP server, ứng dụng không cần chờ yêu cầu mạng. Các task hoặc thread nền nếu được thêm vào sau có thể thay đổi vòng đời tiến trình; đó là hành vi của những thành phần mới, không phải của ví dụ hiện tại.

## 6. Bốn trạng thái kiểm chứng quan trọng

### Trường hợp A — giữ mặc định

~~~bash
mvn -q spring-boot:run
~~~

Kết quả phần ứng dụng:

~~~text
webServer=false
defaultBean=true
customBean=false
selected=auto
autoConfigClassMatched=true
~~~

Cấu hình tự động có mặt, điều kiện class và method cùng đạt.

### Trường hợp B — ứng dụng tự khai báo bean

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.custom=true
~~~

Kết quả:

~~~text
webServer=false
defaultBean=false
customBean=true
selected=custom
autoConfigClassMatched=true
~~~

`@ConditionalOnProperty` trên `customDemoService` được thỏa mãn. Bean do ứng dụng khai báo được xử lý trước auto-configuration, nên điều kiện `@ConditionalOnMissingBean(DemoService.class)` ở bean mặc định không còn đạt.

**Điểm đặc biệt:** điều kiện **lớp** auto-configuration vẫn khớp (`autoConfigClassMatched=true`); chỉ điều kiện **phương thức** bean mặc định không khớp. Không kết luận cả auto-configuration bị vô hiệu chỉ vì bean mặc định nhường chỗ.

### Trường hợp C — tắt cấu hình bằng property

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.feature.enabled=false
~~~

Kết quả:

~~~text
webServer=false
defaultBean=false
customBean=false
selected=none
autoConfigClassMatched=false
~~~

Ở đây `@ConditionalOnProperty` **trên lớp** làm cấu hình không đủ điều kiện. Vì không có bean người dùng, context không có `DemoService`. `getIfAvailable()` trả `null` thay vì ném exception.

### Trường hợp D — tắt auto-configuration nhưng vẫn có bean tự khai báo

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments="--demo.custom=true --demo.feature.enabled=false"
~~~

Kết quả:

~~~text
webServer=false
defaultBean=false
customBean=true
selected=custom
autoConfigClassMatched=false
~~~

Bean người dùng không bị xóa khi auto-configuration không đạt điều kiện. Điều này cho thấy tự cấu hình có vai trò cung cấp giá trị mặc định theo ngữ cảnh, còn ứng dụng có thể quyết định bean của riêng mình.

### Bảng đối chiếu bốn lần chạy

| Biến đầu vào | Class auto-config phù hợp? | Bean mặc định | Bean người dùng | `selected` |
| --- | --- | --- | --- | --- |
| Không truyền property | Có | Có | Không | `auto` |
| `demo.custom=true` | Có | Không | Có | `custom` |
| `demo.feature.enabled=false` | Không | Không | Không | `none` |
| Cả hai property như D | Không | Không | Có | `custom` |

Trong cả bốn lần chạy, `webServer=false`. Việc bean khác nhau **không liên quan đến việc có HTTP server hay không**.

## 7. Quan sát Condition Evaluation Report

Kiểm tra tên bean bằng `containsBean` cho biết **kết quả**; báo cáo điều kiện giúp trả lời **vì sao**.

### Bật báo cáo qua `--debug`

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Chế độ `--debug` của Spring Boot kích hoạt log debug cho một số logger và giúp hiển thị *Condition Evaluation Report*. Trong output dài, hãy tìm `DemoAutoConfiguration` và `defaultDemoService`.

Bạn cần phân biệt:

- **Positive matches:** điều kiện đã phù hợp trong lần chạy.
- **Negative matches:** điều kiện đã được đánh giá nhưng không phù hợp.
- **Exclusions:** lớp auto-configuration đã bị người dùng loại trừ khỏi quá trình xem xét.
- **Unconditional classes:** các class auto-configuration được ghi nhận không yêu cầu điều kiện ở mức được tổng hợp.

Tên/nhóm hiển thị cụ thể trong report có thể khác theo phiên bản và mức logging. Đừng suy từ việc một class có tên trong report rằng tất cả bean của class ấy đều đã được khởi tạo.

Thử bật debug trong trường hợp bean người dùng:

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments="--debug --demo.custom=true"
~~~

Dự kiến thấy điều kiện lớp `DemoAutoConfiguration` phù hợp và điều kiện `@ConditionalOnMissingBean` của `defaultDemoService` **không phù hợp**. Đây là bằng chứng giải thích vì sao `defaultBean=false` dù class-level match là true.

### Đọc báo cáo bằng Java

Trong ví dụ, đoạn:

~~~java
ConditionEvaluationReport report =
    ConditionEvaluationReport.get(context.getBeanFactory());

ConditionEvaluationReport.ConditionAndOutcomes conditions =
    report.getConditionAndOutcomesBySource().get(
        "lab.autocfg.DemoAutoConfiguration"
    );

boolean matched =
    conditions != null && conditions.isFullMatch();
~~~

là **trích đoạn từ `main` hoàn chỉnh**. Đây là cách lấy nhóm kết quả của class auto-configuration và kiểm tra nó có toàn bộ điều kiện class phù hợp hay không.

Để xem điều kiện của phương thức, có thể tra cứu mục của source mang tên class kèm `#defaultDemoService` trong map của báo cáo:

~~~java
report.getConditionAndOutcomesBySource().entrySet().stream()
    .filter(entry ->
        entry.getKey().startsWith(
            "lab.autocfg.DemoAutoConfiguration"
        )
    )
    .forEach(entry ->
        System.out.println(entry.getKey()
            + " -> " + entry.getValue().isFullMatch())
    );
~~~

*Đoạn trên chạy bên trong `main`, khi đã có biến `report`.* Hãy dùng nó để quan sát riêng các source liên quan đến class này. Số lượng và thứ tự source được in có thể thay đổi giữa các tình huống, nên **không đưa ra một stdout cố định cho đoạn mở rộng**.

**Ranh giới của báo cáo:** `ConditionEvaluationReport` nói về việc đánh giá điều kiện, không phải bản kê cuối cùng của mọi object Java. Một bean definition có thể tồn tại nhưng instance chưa khởi tạo do `@Lazy`/scope; một bean có thể khởi tạo thất bại do dependency không hợp lệ. Khi cần kết luận bean đang tồn tại, luôn phối hợp đọc context.

## 8. Thử loại trừ ứng viên để phân biệt với điều kiện không phù hợp

Ngoài property điều kiện, Spring Boot cho phép tắt riêng một auto-configuration bằng `spring.autoconfigure.exclude`:

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--spring.autoconfigure.exclude=lab.autocfg.DemoAutoConfiguration
~~~

Với `demo.custom` không được bật, chương trình in:

~~~text
webServer=false
defaultBean=false
customBean=false
selected=none
autoConfigClassMatched=false
~~~

Trường hợp này nhìn giống kết quả C ở các dòng bean, nhưng **nguyên nhân khác**:

- **Property=false:** class nằm trong danh sách ứng viên nhưng điều kiện class không khớp.
- **Exclude:** class ứng viên bị loại trừ chủ động trước khi được xử lý như một auto-configuration hợp lệ.

Trong báo cáo debug, tìm mục **Exclusions** để xác minh nguyên nhân thứ hai. `autoConfigClassMatched=false` trong chương trình chỉ là kết quả tổng hợp của việc không tìm thấy nhóm điều kiện phù hợp; riêng boolean ấy không đủ phân biệt **bị exclude** và **không khớp property**.

Có thể exclude bằng annotation:

~~~java
@SpringBootApplication(
    excludeName = "lab.autocfg.DemoAutoConfiguration"
)
public class InspectApplication {
    // Các method khác giữ nguyên như ví dụ chính.
}
~~~

Đây là **đoạn minh họa cách thay annotation ở đầu class**, không phải chương trình độc lập. Khi dùng cách này, hãy bỏ exclude ở dòng lệnh để quan sát riêng tác dụng của annotation.

## 9. Thử xóa đăng ký trong imports

Tạm thời xóa dòng:

~~~text
lab.autocfg.DemoAutoConfiguration
~~~

khỏi file `AutoConfiguration.imports` (giữ file hợp lệ, không cần tự thêm class khác), rồi chạy lại mặc định. Vì `lab.autocfg` không nằm trong component scan từ `lab.app`, auto-configuration không được nhập thông qua cơ chế ứng viên. Kết quả thuộc loại không có bean mặc định:

~~~text
webServer=false
defaultBean=false
customBean=false
selected=none
autoConfigClassMatched=false
~~~

Đối với ứng dụng console, hành vi này cho thấy một class Java mang `@AutoConfiguration` **chưa đủ**; nó cần đường đăng ký để Boot tìm thấy. Khôi phục dòng trong imports trước khi thử các trường hợp tiếp theo.

Nếu bạn vẫn thấy bean mặc định sau khi xóa imports, kiểm tra xem class đã bị đưa vào component scan/`@Import` từ một nơi khác chưa và làm sạch bản build để bảo đảm resources đã được cập nhật.

## 10. Khi không muốn viết auto-configuration riêng

Bản tối thiểu để **quan sát auto-configuration sẵn có** chỉ cần starter cơ bản, `@SpringBootApplication` và một `main` chạy `WebApplicationType.NONE`. Ví dụ này có thể in tên những lớp cấu hình xuất hiện trong condition report mà không cần tự khai báo `DemoAutoConfiguration`:

~~~java
package lab.app;

import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class InspectDefaults {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 new SpringApplicationBuilder(InspectDefaults.class)
                     .web(WebApplicationType.NONE)
                     .bannerMode(Banner.Mode.OFF)
                     .run(args)) {

            ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

            long evaluatedSources =
                report.getConditionAndOutcomesBySource().size();

            System.out.println("evaluatedSources=" + evaluatedSources);
        }
    }
}
~~~

Đây là một **file Java hoàn chỉnh** (`lab/app/InspectDefaults.java`) nhưng cần có `pom.xml`/dependencies như mục 2 và nên chạy trong một project riêng hoặc cấu hình đúng main class nếu project có nhiều điểm khởi chạy. Số lượng `evaluatedSources` thay đổi theo classpath và version, nên **không đưa stdout cố định** cho kết quả này.

Ví dụ mở rộng có `DemoAutoConfiguration` hữu ích hơn trong việc học vì ta chủ động điều khiển ba loại điều kiện và giải thích được lý do thay đổi. Khi khám phá starter thật, hãy giữ cùng phương pháp quan sát và thay điều kiện phù hợp với dependency đang thử nghiệm.

## 11. Quan sát bean và bean definition chính xác hơn

### Tên bean hiện có

Cách in theo kiểu:

~~~java
String[] names =
    context.getBeanNamesForType(DemoService.class);
java.util.Arrays.sort(names);
System.out.println(java.util.Arrays.toString(names));
~~~

Đây là **đoạn mở rộng của chương trình hoàn chỉnh**, với biến `context` có sẵn. Trong bốn trạng thái cơ bản, dự kiến nhận được `[defaultDemoService]`, `[customDemoService]` hoặc `[]`.

### Có định nghĩa bean chưa chắc instance đã sẵn sàng

`containsBean("name")` và `getBeanNamesForType` cho biết tên/khả năng tra cứu bean của context. Nếu muốn nghiên cứu sâu hơn về đăng ký, dùng:

~~~java
var factory = context.getBeanFactory();
boolean definitionExists =
    factory.containsBeanDefinition("defaultDemoService");
System.out.println("definitionExists=" + definitionExists);
~~~

Trong ví dụ mặc định, dòng trên là `definitionExists=true`; khi auto-configuration bị loại hoặc bean mặc định nhường chỗ, `false`.

Đừng nhầm với thời điểm gọi constructor/factory method. Singleton mặc định thường được tạo trong quá trình refresh; bean lazy có thể trì hoãn; prototype tạo theo mỗi lần yêu cầu. `getBean(...)` có thể kích hoạt khởi tạo, nên khi chỉ muốn xem định nghĩa thì tránh gọi nó một cách không cần thiết.

### Nếu khởi động thất bại trước `main` đọc được report

`SpringApplicationBuilder.run(args)` có thể ném exception khi tạo context. Khi đó mã ở bên trong `try` **chưa được thực thi**, nên không có các dòng `System.out.println` dự kiến. Hãy chạy `--debug` và đọc exception nguyên nhân gốc; Spring Boot có thể hiển thị Condition Evaluation Report trước khi kết thúc do lỗi. Không nên kết luận “report trống” chỉ vì code sau `run` không kịp chạy.

## 12. Cách kiểm tra chắc chắn không chạy web server

Có ba phép kiểm tra độc lập nhưng mục đích khác nhau:

1. **Cấu hình ứng dụng:** mã có `.web(WebApplicationType.NONE)` hoặc property `spring.main.web-application-type=none`.
2. **Loại context:** `context instanceof WebServerApplicationContext` là `false` như ví dụ.
3. **Log khởi động:** không có thông báo một embedded HTTP server được khởi động cho ứng dụng này.

Không dùng việc thử `http://localhost:8080` rồi gặp lỗi kết nối làm bằng chứng duy nhất. Có thể server đã dùng cổng khác, hoặc một service riêng đã chiếm cổng. Ngược lại, với chế độ NONE, Boot không khởi chạy embedded web server dù có class web trên classpath.

**Lưu ý về dependency:** Nếu dùng `spring-boot-starter-web` hoặc `spring-boot-starter-webflux`, có thể kéo thêm nhiều thành phần và làm một số điều kiện classpath thay đổi. Chế độ NONE vẫn quyết định kiểu context, nhưng tập điều kiện non-web có thể khác. Để học cơ chế mà ít nhiễu, nên giữ `spring-boot-starter` cơ bản rồi thêm dependency từng lần có chủ đích.

## 13. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Ứng dụng khởi động HTTP server | Dùng starter web và chưa đặt `WebApplicationType.NONE` | Thêm `.web(WebApplicationType.NONE)` hoặc property tương ứng |
| Thiếu `defaultDemoService` ở lần chạy mặc định | Sai đường dẫn/tên file `AutoConfiguration.imports`, sai FQCN, class bị exclude hoặc condition không đạt | Kiểm tra file trong `src/main/resources`, package, tên class và report |
| `customBean=true` nhưng `defaultBean=false` | `@ConditionalOnMissingBean` hoạt động đúng | Đây là kết quả mong đợi, xem report của method |
| `selected=none` và app vẫn chạy | Dùng `getIfAvailable()` cho bean tùy chọn | Đây là kết quả mong đợi trong trạng thái C |
| `NoSuchBeanDefinitionException` | Truy cập bean bắt buộc trong khi không có instance/definition phù hợp | Dùng provider tùy chọn khi mục tiêu là quan sát, hoặc bổ sung cấu hình hợp lệ |
| Lệnh `--debug` in rất nhiều cấu hình | Nhiều auto-configuration từ Boot/starter được đánh giá | Tìm theo `DemoAutoConfiguration` và `defaultDemoService` |
| Không thấy phần debug conditions | Truyền sai tham số cho Maven plugin hoặc bật log chưa đúng | Thử `java -jar ... --debug` hoặc cấu hình logging theo hướng dẫn Boot |
| Class auto-config có annotation nhưng không được xử lý | Không có dòng FQCN trong `AutoConfiguration.imports`, hoặc class bị quét/nhập không đúng ý | Dùng imports và để package auto-config ngoài component scan |
| Maven không chạy do Java version | JDK quá cũ hoặc `JAVA_HOME` sai | Kiểm tra `java -version`, `mvn -version` và Java 17+ |
| Khác kết quả dự kiến về số dòng log/bean khác | Khác classpath/Boot version/log settings | So các dòng `System.out.println` thuộc demo, không đòi toàn bộ log giống hệt |
| Ứng dụng không thoát | Có thread nền, scheduler hoặc bean khác được thêm | Xem hoạt động background và lifecycle; demo gốc tự đóng context |

### Quy trình điều tra khi kết quả khác dự kiến

1. Kiểm tra `@SpringBootApplication` có đúng ở `lab.app.InspectApplication` không, và imports file nêu chính xác `lab.autocfg.DemoAutoConfiguration`.
2. Bảo đảm chỉ chạy đúng project, class chính, version Spring Boot và các tham số đang thử.
3. Kiểm tra `webServer=false` để loại trừ trường hợp đang chạy loại ứng dụng khác.
4. Kiểm tra `autoConfigClassMatched` trước: nếu `false`, tìm lý do class condition/exclude/imports; nếu `true` nhưng `defaultBean=false`, kiểm tra missing-bean trên method.
5. Kiểm tra `customBean` để xem ứng dụng có cung cấp một `DemoService` hay không.
6. Bật `--debug`, tìm đúng tên source và thông điệp điều kiện trong report. Không chỉ dựa trên việc một JAR có mặt.
7. Đối chiếu `getBeanNamesForType` hoặc `containsBeanDefinition` với các dòng in trước khi kết luận.

## 14. Tự luyện tập

1. **Đổi tính mặc định:** chuyển `matchIfMissing=true` thành `false`. Chạy không truyền property và chạy với `--demo.feature.enabled=true`. Giải thích sự thay đổi bằng đúng tham số của điều kiện.
2. **Thử bean của người dùng:** bật `--demo.custom=true`. Đọc phần report của `defaultDemoService` và chỉ ra lý do bean mặc định nhường chỗ.
3. **Tắt auto-configuration có chủ đích:** dùng `spring.autoconfigure.exclude`, sau đó bật `demo.custom=true`. Bean do người dùng có tồn tại không?
4. **Thử imports:** xóa dòng tên class trong file imports, chạy lại, khôi phục. Vì sao code vẫn biên dịch nhưng bean mặc định không xuất hiện?
5. **Dùng chế độ non-web trên classpath nhiều dependency:** thêm starter web, giữ `WebApplicationType.NONE`. So sánh loại context và số mục trong report; phân tích điều kiện nào thay đổi do classpath.
6. **So sánh định nghĩa và instance:** thêm `@Lazy` cho bean mặc định, quan sát khác biệt giữa `containsBeanDefinition` và việc gọi `getBeanProvider(...).getIfAvailable()`.
7. **Tự tạo một conditional thứ hai:** thêm `@ConditionalOnProperty(prefix = "demo.extra", name = "enabled", havingValue = "true")` trên một phương thức `@Bean` mới có tên khác. Kiểm tra các trạng thái thuộc tính và lý do report. Tránh tạo hai bean cùng kiểu `DemoService` nếu chưa giải quyết trường hợp inject mơ hồ.
8. **Giải thích nguyên nhân:** với `defaultBean=false`, hãy kể ba lý do khác nhau (class không được nhập, class condition sai, method condition sai) và nêu bằng chứng cần đọc để phân biệt.

**Điều kiện hoàn thành bài:** có thể tạo một ứng dụng Boot không có máy chủ HTTP, chủ động bật/tắt một auto-configuration, hiểu vì sao bean mặc định nhường chỗ cho bean ứng dụng, đọc `ConditionEvaluationReport` và kiểm tra kết quả thật bằng `ApplicationContext`.

## 15. Tài liệu tham khảo

- [Spring Boot 3.3 — SpringApplication, chạy ứng dụng và cấu hình khởi động](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — WebApplicationType Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html)
- [Spring Boot 3.3 — ConditionEvaluationReport Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html)
- [Spring Boot 3.3 — SpringApplicationBuilder Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html)
