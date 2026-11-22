# Không dựa vào thứ tự dòng trong tệp imports hoặc thứ tự dependency

## 1. Vấn đề cần giải quyết

Trong Spring Boot Auto Configuration, thư viện có thể đóng góp nhiều lớp auto-configuration. Một số lớp phải được **xét trước** hoặc **xét sau** lớp khác, đặc biệt khi dùng điều kiện như @ConditionalOnBean và @ConditionalOnMissingBean. Lỗi phổ biến là cố tạo thứ tự đó bằng cách:

- Đưa tên lớp lên trước hoặc xuống sau trong tệp **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.
- Đổi thứ tự khai báo thư viện trong **pom.xml**, **build.gradle** hoặc danh sách dependency.
- Dựa vào thứ tự thấy trong log của một lần chạy rồi coi đó là bảo đảm lâu dài.

Những cách trên không phải hợp đồng để điều phối auto-configuration. Spring Boot **thu thập và sắp xếp** các ứng viên auto-configuration theo metadata và quy tắc riêng. Để biểu diễn quan hệ giữa các auto-configuration, hãy dùng **@AutoConfiguration(before = ... / after = ...)** hoặc các annotation tương đương; dùng **@AutoConfigureOrder** khi cần mức ưu tiên chung.

> Quy tắc: **Thứ tự liệt kê trong nguồn không phải là thứ tự ngữ nghĩa được bảo đảm. Quan hệ cấu hình phải được khai báo tường minh.**

Bài này tập trung vào **thứ tự xử lý auto-configuration**, không nhầm với thứ tự tạo đối tượng bean hoặc thứ tự thực thi nghiệp vụ.

## 2. AutoConfiguration.imports có nhiệm vụ gì?

Với Spring Boot 3.x, một thư viện công bố các lớp auto-configuration qua resource có đường dẫn chính xác:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ nội dung:

~~~text
com.example.library.autoconfigure.ReportAutoConfiguration
com.example.library.autoconfigure.ClockAutoConfiguration
~~~

Mỗi dòng là tên class đầy đủ. Tệp nằm trong classpath của thư viện hoặc ứng dụng. Spring Boot dùng cơ chế import candidates để tìm các auto-configuration, kết hợp danh sách từ các nguồn thích hợp trên classpath rồi áp dụng quy trình chọn, lọc điều kiện và **sắp xếp**.

**Điều tệp imports bảo đảm:** giúp Spring Boot **phát hiện những class nào là ứng viên** auto-configuration.

**Điều tệp imports không bảo đảm:** lớp đứng ở dòng đầu được xử lý trước mọi lớp bên dưới; thứ tự giữa nhiều tệp imports trong các JAR là thứ tự nghiệp vụ cố định; hoặc bean của lớp đứng đầu được khởi tạo trước.

Spring Boot có thể cần:

1. Đọc ứng viên từ nhiều JAR có tệp imports.
2. Loại ứng viên lặp, xét loại trừ (exclude/excludeName hoặc thuộc tính liên quan).
3. Áp dụng cơ chế lọc ứng viên theo môi trường/classpath và metadata.
4. **Sắp xếp các auto-configuration** theo quan hệ trước/sau và ưu tiên được khai báo.
5. Xử lý bean definitions và điều kiện khi các cấu hình được xét.

Đây là mô hình khái quát; các bước nội bộ cụ thể có thể thay đổi theo phiên bản. **Không dựa vào số thứ tự dòng** để dự đoán thứ tự đăng ký trong ApplicationContext.

## 3. Vì sao thứ tự dependency không thay thế được thứ tự cấu hình?

Một dự án có thể viết:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>report-starter</artifactId>
        <version>1.0.0</version>
    </dependency>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>clock-starter</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
~~~

Đây là **đoạn XML minh họa của pom.xml**, không phải POM hoàn chỉnh. Việc report-starter được khai báo trước clock-starter không có nghĩa ReportAutoConfiguration được đánh giá trước ClockAutoConfiguration. Hệ thống build giải quyết phụ thuộc và tạo classpath; Spring Boot chịu trách nhiệm phát hiện, lọc và sắp xếp auto-configuration.

Tương tự với Gradle:

~~~groovy
dependencies {
    implementation 'com.example:report-starter:1.0.0'
    implementation 'com.example:clock-starter:1.0.0'
}
~~~

Đổi thứ tự hai dòng không phải cơ chế điều khiển dependency injection hoặc @ConditionalOnBean. Thứ tự classpath có thể khác theo công cụ build, cách đóng gói, phiên bản hoặc cấu trúc phụ thuộc; kể cả khi một thứ tự tình cờ cho kết quả mong muốn, nó vẫn **không diễn tả quan hệ auto-configuration** mà người bảo trì có thể tin cậy.

**Hai vai trò độc lập:**

| Câu hỏi | Thuộc về |
| --- | --- |
| Class của thư viện có được đưa lên classpath không? | Maven/Gradle dependency resolution |
| Auto-configuration nào được phát hiện? | AutoConfiguration.imports cùng cơ chế import của Spring Boot |
| Auto-configuration A phải được xử lý trước/sau B? | @AutoConfiguration(before/after), metadata ordering của Spring Boot |
| Bean X có được đăng ký không? | Điều kiện trên cấu hình/@Bean, ví dụ @ConditionalOnBean |
| Khi tạo bean Y, dependency X phải tồn tại? | Cơ chế dependency injection, @DependsOn nếu thực sự cần ràng buộc khởi tạo |

## 4. Khai báo thứ tự đúng cách

### 4.1. @AutoConfiguration(after = ...)

Nếu ReportAutoConfiguration chứa điều kiện cần quan sát bean do ClockAutoConfiguration đăng ký, khai báo:

~~~java
@AutoConfiguration(after = ClockAutoConfiguration.class)
public class ReportAutoConfiguration {
    // Các @Bean của báo cáo.
}
~~~

Đây là **đoạn minh họa class**, chưa phải chương trình độc lập. Ý nghĩa: Spring Boot nên **xử lý ClockAutoConfiguration trước ReportAutoConfiguration trong tập auto-configuration**, bất kể tệp imports liệt kê tên theo thứ tự nào.

Vẫn phải dùng điều kiện phù hợp như @ConditionalOnBean(Clock.class) nếu ReportService chỉ nên được đăng ký khi thực sự có Clock. **after không tự bảo đảm bean Clock tồn tại**: ClockAutoConfiguration có thể bị exclude, classpath không phù hợp, hoặc điều kiện nội bộ không thỏa.

### 4.2. @AutoConfiguration(before = ...)

Nếu lớp của bạn cần được xét trước lớp khác:

~~~java
@AutoConfiguration(before = ReportAutoConfiguration.class)
public class ClockAutoConfiguration {
    // Đăng ký bean được ReportAutoConfiguration xét đến.
}
~~~

Thông thường chỉ cần công bố quan hệ rõ ràng ở một phía. Tránh khai báo quan hệ mâu thuẫn hoặc chu trình kiểu A sau B nhưng B lại sau A. Một sơ đồ trước/sau phải có thể sắp xếp hợp lý.

**before/after chỉ mô tả quan hệ giữa các auto-configuration có liên quan**, không phải thứ tự toàn cục của mọi @Configuration do ứng dụng viết.

### 4.3. afterName/beforeName khi class khác là tùy chọn

Khi không muốn module phải phụ thuộc compile-time vào class của module tùy chọn, dùng **tên class đầy đủ ở dạng chuỗi**:

~~~java
@AutoConfiguration(
        afterName = "com.example.optional.OptionalStorageAutoConfiguration")
public class ReportingAutoConfiguration {
    // Các @Bean của reporting.
}
~~~

Ví dụ trên là **minh họa**, không yêu cầu OptionalStorageAutoConfiguration có mặt trên classpath để biên dịch ReportingAutoConfiguration. Nếu auto-configuration được tham chiếu không phải ứng viên đang được xử lý, quan hệ ấy không tự thêm module còn thiếu hoặc tạo bean của module đó.

### 4.4. Annotation tương đương và ưu tiên tổng quát

Trong Spring Boot có thể gặp các annotation:

- **@AutoConfigureAfter(SomeAutoConfiguration.class)** và **@AutoConfigureBefore(SomeAutoConfiguration.class)**: dạng khai báo quan hệ được dùng từ trước; @AutoConfiguration(after/before) cho phép thể hiện trực tiếp trên annotation chính.
- **@AutoConfigureOrder(n)**: dùng khi cần mức ưu tiên chung của một auto-configuration. Giá trị nhỏ hơn có độ ưu tiên cao hơn theo quy tắc ordered, nhưng quan hệ **before/after cụ thể** thể hiện dependency rõ hơn và nên được ưu tiên khi quan hệ có ý nghĩa.
- **@Order** của Spring Framework thường liên quan đến độ ưu tiên/collection hoặc thành phần được sắp thứ tự trong ngữ cảnh khác. Không dùng @Order gắn tùy tiện lên auto-configuration để thay thế cơ chế AutoConfigure ordering.

**Thực hành:** Dùng **after** khi bean/điều kiện của bạn cần quan sát kết quả cấu hình khác; dùng **before** khi cần cho cấu hình khác quan sát kết quả của bạn; dùng **afterName/beforeName** khi module kia tùy chọn; chỉ dùng **@AutoConfigureOrder** khi thực sự cần ưu tiên chung, không mô tả được một dependency cụ thể.

## 5. Vì sao thứ tự có thể thay đổi kết quả @ConditionalOnBean?

Giả sử:

- ClockAutoConfiguration khai báo bean Clock nếu chưa có Clock do người dùng cung cấp.
- ReportAutoConfiguration đăng ký ReportService **chỉ nếu** đã có bean Clock.

Nếu ReportAutoConfiguration được xử lý khi Clock bean definition **chưa được xử lý**, @ConditionalOnBean(Clock.class) có thể trả kết quả **không khớp**. Từ đó ReportService không được đăng ký, dù cấu hình Clock sẽ xuất hiện ở phần xử lý khác. Đây là tình huống cần khai báo **after**.

~~~text
Không khai báo quan hệ (không được bảo đảm):
  ReportAutoConfiguration
     |
     +-- @ConditionalOnBean(Clock.class) -> có thể chưa thấy Clock
  ClockAutoConfiguration
     |
     +-- đăng ký Clock quá muộn cho lần đánh giá trước

Khai báo @AutoConfiguration(after = ClockAutoConfiguration.class):
  ClockAutoConfiguration
     |
     +-- đăng ký bean definition Clock khi điều kiện phù hợp
  ReportAutoConfiguration
     |
     +-- @ConditionalOnBean(Clock.class) -> đã có thể thấy Clock
     +-- đăng ký ReportService
~~~

Cần phân biệt **bean definition đã được biết đến** với **đối tượng bean đã được khởi tạo**. Khi kiểm tra điều kiện, Spring Boot chủ yếu làm việc với thông tin bean definitions/context ở thời điểm đó; không nên diễn giải điều kiện như đợi mọi singleton được tạo xong rồi mới xét.

Tương tự, @ConditionalOnMissingBean là điều kiện “chưa thấy bean phù hợp” ở thời điểm đánh giá. Thông thường Spring Boot xử lý auto-configuration **sau** bean definitions do ứng dụng khai báo, để một bean tùy chỉnh có cơ hội khiến default của auto-configuration được bỏ qua. Nếu hai auto-configuration có quan hệ mặc định/tùy chọn với nhau, chúng vẫn nên công bố thứ tự cần thiết thay vì dựa vào dòng trong imports.

## 6. Ví dụ chạy được: đảo thứ tự imports nhưng kết quả vẫn đúng

Ví dụ dùng Java 17+ và **Spring Boot 3.3.5** với Maven. Ta cố tình để ReportAutoConfiguration **đứng trước** ClockAutoConfiguration trong imports, rồi khai báo after để diễn tả thứ tự thực sự mong muốn.

### 6.1. Cây thư mục

~~~text
order-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/
    │   │       ├── app/
    │   │       │   └── OrderDemoApplication.java
    │   │       └── library/autoconfigure/
    │   │           ├── ClockAutoConfiguration.java
    │   │           ├── ReportAutoConfiguration.java
    │   │           └── ReportService.java
    │   └── resources/
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/app/
            └── AutoConfigurationOrderTest.java
~~~

Lưu ý: lớp @SpringBootApplication nằm trong package **com.example.app**, còn auto-configuration ở **com.example.library.autoconfigure**, tránh để component scan thông thường quét các lớp auto-configuration và vô tình đăng ký chúng theo con đường khác. Đây là một chi tiết quan trọng khi tự thử auto-configuration ngay trong một project.

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>order-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
</project>
~~~

### 6.3. ClockAutoConfiguration.java

**src/main/java/com/example/library/autoconfigure/ClockAutoConfiguration.java**

~~~java
package com.example.library.autoconfigure;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ClockAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    Clock appClock() {
        // Fixed Clock chỉ để có kết quả ví dụ xác định.
        return Clock.fixed(
                Instant.parse("2026-01-02T03:04:05Z"),
                ZoneOffset.UTC);
    }
}
~~~

Đoạn này trả về một Clock cố định để stdout dễ kiểm chứng; ứng dụng thực tế thường dùng **Clock.systemUTC()** hoặc đồng hồ phù hợp nhu cầu. @ConditionalOnMissingBean(Clock.class) cho phép ứng dụng cung cấp Clock riêng và khiến bean dự phòng appClock không được đăng ký.

### 6.4. ReportService.java

**src/main/java/com/example/library/autoconfigure/ReportService.java**

~~~java
package com.example.library.autoconfigure;

import java.time.Clock;

public class ReportService {
    private final Clock clock;

    public ReportService(Clock clock) {
        this.clock = clock;
    }

    public String generatedAt() {
        return clock.instant().toString();
    }
}
~~~

ReportService phụ thuộc vào Clock. Constructor injection bảo đảm rằng khi tạo đối tượng ReportService, Spring phải giải quyết dependency Clock; nó **không tự bảo đảm** rằng một điều kiện @ConditionalOnBean ở giai đoạn đăng ký đã được đánh giá đúng thứ tự. Vì thế vẫn cần metadata thứ tự giữa hai auto-configuration.

### 6.5. ReportAutoConfiguration.java

**src/main/java/com/example/library/autoconfigure/ReportAutoConfiguration.java**

~~~java
package com.example.library.autoconfigure;

import java.time.Clock;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = ClockAutoConfiguration.class)
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnBean(Clock.class)
    @ConditionalOnMissingBean(ReportService.class)
    ReportService reportService(Clock clock) {
        return new ReportService(clock);
    }
}
~~~

Đây là **quan hệ thực sự quan trọng**: ReportAutoConfiguration phải được đánh giá **sau** ClockAutoConfiguration. @ConditionalOnBean chỉ đăng ký ReportService nếu lúc xét đã có Clock phù hợp; @ConditionalOnMissingBean(ReportService.class) cho phép người dùng tự khai báo ReportService riêng.

Nếu ClockAutoConfiguration bị exclude hoặc không đăng ký Clock, việc khai báo after không biến điều kiện thất bại thành đúng; khi đó ReportService cũng không được đăng ký trừ khi có nguồn Clock khác.

### 6.6. AutoConfiguration.imports — cố ý ghi thứ tự ngược

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.library.autoconfigure.ReportAutoConfiguration
com.example.library.autoconfigure.ClockAutoConfiguration
~~~

Report đứng ở dòng 1, Clock đứng ở dòng 2. **Không cần đổi hai dòng.** Spring Boot đọc ứng viên và xem xét @AutoConfiguration(after = ClockAutoConfiguration.class), thay vì dùng thứ tự dòng làm lời hứa về quan hệ xử lý.

### 6.7. OrderDemoApplication.java

**src/main/java/com/example/app/OrderDemoApplication.java**

~~~java
package com.example.app;

import com.example.library.autoconfigure.ReportService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showReport(ReportService service) {
        return args ->
                System.out.println("Report time: " + service.generatedAt());
    }
}
~~~

Chạy:

~~~bash
mvn spring-boot:run
~~~

Ngoài log khởi động của Spring Boot, CommandLineRunner in ra đúng dòng:

~~~text
Report time: 2026-01-02T03:04:05Z
~~~

**Diễn giải:** ClockAutoConfiguration cung cấp Clock; ReportAutoConfiguration được xử lý sau, @ConditionalOnBean(Clock.class) khớp, ReportService được đăng ký; CommandLineRunner nhận ReportService và in thời điểm cố định. Kết quả này không đòi hai dòng imports nằm ở thứ tự thuận.

### 6.8. Kiểm tra tự động bằng ApplicationContextRunner

Thêm file **src/test/java/com/example/app/AutoConfigurationOrderTest.java**:

~~~java
package com.example.app;

import java.time.Clock;
import com.example.library.autoconfigure.ClockAutoConfiguration;
import com.example.library.autoconfigure.ReportAutoConfiguration;
import com.example.library.autoconfigure.ReportService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationOrderTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(
                            ReportAutoConfiguration.class,
                            ClockAutoConfiguration.class));

    @Test
    void reportConfigurationIsEvaluatedAfterClockConfiguration() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(Clock.class);
            assertThat(context).hasSingleBean(ReportService.class);
            assertThat(context.getBean(ReportService.class).generatedAt())
                    .isEqualTo("2026-01-02T03:04:05Z");
        });
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Test cố tình truyền ReportAutoConfiguration trước ClockAutoConfiguration khi tạo bộ auto-configuration. Metadata after vẫn giúp các điều kiện được xét đúng quan hệ, nên test kiểm tra được Clock và ReportService cùng tồn tại. Output chi tiết của Maven phụ thuộc môi trường; **kết quả mong đợi là test passed, không có assertion failure**.

**Thử nghiệm có mục đích:** bỏ after khỏi ReportAutoConfiguration, để imports và danh sách trong test như trên. Nếu thứ tự quan sát lúc đó khiến điều kiện Report được đánh giá trước Clock, test sẽ không còn ReportService. Không nên xây hệ thống dựa vào việc thử nghiệm “vẫn pass trên máy mình” khi thiếu after: thứ tự không được tuyên bố là hợp đồng. Khôi phục after để thiết kế rõ ràng.

## 7. Thứ tự auto-configuration khác thứ tự tạo bean

Đây là một nhầm lẫn lớn:

- **@AutoConfiguration(after = X.class)**: liên quan đến **thứ tự xử lý các lớp auto-configuration/bean definitions**. Nó hữu ích với điều kiện cần thấy bean definitions đã được đăng ký.
- **Constructor injection**: khi tạo bean Y cần X, container phải giải quyết X trước để truyền vào constructor Y, miễn có dependency phù hợp.
- **@DependsOn("x")**: mô tả thêm sự phụ thuộc **khởi tạo/hủy bean** khi cần thứ tự lifecycle cụ thể ngoài constructor injection. Nếu bean x không tồn tại, cấu hình còn có thể gây lỗi.
- **ApplicationRunner/CommandLineRunner và lifecycle hooks**: điều khiển hoạt động sau khi context sẵn sàng hoặc theo lifecycle thích hợp; không nên dùng thứ tự imports để điều phối việc chạy nghiệp vụ.

Ví dụ minh họa:

~~~java
@Bean
@DependsOn("cacheInitializer")
public CacheWorker cacheWorker() {
    return new CacheWorker();
}
~~~

Đây chỉ là **phương thức minh họa bên trong class @Configuration**, giả định đã có bean mang tên cacheInitializer và class CacheWorker. @DependsOn dùng cho lifecycle bean, không thay thế @AutoConfiguration(after=...) để bảo đảm @ConditionalOnBean nhìn thấy bean definition tại thời điểm điều kiện được xét.

**Đừng nhầm @Order với @AutoConfigureOrder:** @Order thường được dùng để sắp thứ tự các thành phần như List<Handler> hoặc listener trong ngữ cảnh mà Spring hỗ trợ. Nó không phải cơ chế đáng tin để ép hai auto-configuration được xử lý theo quan hệ có điều kiện.

## 8. Điều kiện thực tế vẫn quyết định bean có được đăng ký hay không

Đánh giá đúng thứ tự **không có nghĩa** một auto-configuration nhất định sẽ tạo bean. Ngoài after/before còn phải xét:

- Class/dependency cần thiết có mặt trên classpath không (@ConditionalOnClass)?
- Bean prerequisite đã hiện diện khi điều kiện được đánh giá chưa (@ConditionalOnBean)?
- Ứng dụng đã cung cấp bean để auto-configuration mặc định phải nhường chỗ chưa (@ConditionalOnMissingBean)?
- Thuộc tính cấu hình hoặc profile có bật tính năng không (@ConditionalOnProperty, @Profile)?
- Auto-configuration có bị exclude hoặc không được phát hiện không?

Ví dụ, @AutoConfiguration(after = DatabaseAutoConfiguration.class) chỉ đặt quan hệ giữa các **ứng viên auto-configuration**, không tự thêm JDBC driver, không tạo DataSource nếu điều kiện của DatabaseAutoConfiguration không khớp, và không làm cho một bean bị exclude xuất hiện.

**Tư duy đúng:** thứ tự đảm bảo điều kiện được **xét trong ngữ cảnh mong muốn**; chính điều kiện và dependency quyết định bean được đăng ký/tạo.

## 9. Cách chẩn đoán khi thứ tự cho kết quả bất ngờ

Thực hiện lần lượt:

1. **Xác nhận class có thật sự là ứng viên:** tên đầy đủ phải nằm trong đúng đường dẫn AutoConfiguration.imports đóng gói trong JAR. Với Spring Boot 3.x, đừng dùng cơ chế spring.factories cũ làm nguồn đăng ký auto-configuration mặc định nếu dự án đang theo chuẩn imports.
2. **Kiểm tra cấu hình bị exclude hoặc điều kiện không khớp:** chạy với đối số **--debug** để xem báo cáo đánh giá điều kiện (Condition Evaluation Report). Nếu có Actuator và endpoint được cấu hình/expose phù hợp, endpoint **/actuator/conditions** cũng có thể giúp quan sát.
3. **Tìm @ConditionalOnBean/@ConditionalOnMissingBean:** ghi rõ bean type/name đang được kiểm tra và vì sao bean definition phải xuất hiện trước. Nếu là quan hệ giữa hai auto-configuration, khai báo after/before.
4. **Đọc lại phạm vi component scan:** auto-configuration bị quét như @Configuration thông thường có thể làm thử nghiệm không còn phản ánh đường nạp imports chính thức. Trong ví dụ này com.example.app không quét package com.example.library.autoconfigure.
5. **Kiểm tra classpath và bean được người dùng định nghĩa:** auto-configuration có thể được xử lý đúng thứ tự nhưng bean vẫn thiếu do điều kiện khác hoặc bị ứng dụng thay thế.
6. **Viết ApplicationContextRunner test:** nạp nhóm auto-configuration cụ thể, kiểm tra bean xuất hiện/vắng mặt khi bật/tắt prerequisite, thay đổi cấu hình người dùng, và cố ý đảo thứ tự liệt kê ứng viên. Test phải khẳng định **kết quả nghiệp vụ/bean**, không chỉ nhìn số dòng imports.

Không dùng việc tráo hai dòng trong imports hoặc hai dependency làm “cách sửa” một condition fail: cách đó để lại giả định ngầm và có thể hỏng khi đổi JAR, build tool hoặc Spring Boot version.

## 10. Những lỗi thiết kế cần tránh

| Cách làm dễ mắc | Vấn đề | Cách sửa |
| --- | --- | --- |
| Đặt ClassA ở dòng trước ClassB trong AutoConfiguration.imports để “ép chạy trước” | Dòng imports là danh sách ứng viên, không có hợp đồng ordering kiểu đó | Khai báo @AutoConfiguration(before/after) |
| Đổi vị trí hai starter trong pom.xml/build.gradle | Dependency declaration không mô tả quan hệ xử lý auto-configuration | Giữ dependency theo nhu cầu classpath; khai báo ordering bằng metadata Spring Boot |
| Dùng @Order thay after | @Order không phải công cụ đặc thù để biểu diễn quan hệ auto-configuration | Dùng after/before, hoặc @AutoConfigureOrder cho ưu tiên tổng quát |
| Dùng after và mặc định bean prerequisite chắc chắn tồn tại | after chỉ sắp thứ tự đánh giá, không làm condition tự khớp | Có @ConditionalOnBean hoặc kiểm tra prerequisite rõ ràng |
| Chuyển @ConditionalOnBean sang @Primary để “sửa thứ tự” | @Primary chọn ứng viên lúc inject, không bảo đảm bean definition có được đăng ký | Sửa điều kiện và ordering phù hợp |
| Đưa auto-configuration vào vùng component scan thông thường | Class có thể được xử lý như cấu hình ứng dụng, che đi lỗi imports/ordering | Tách package và nạp bằng AutoConfiguration.imports |
| Dùng after để ép method khởi động theo thứ tự | after không phải dependency lifecycle | Dùng dependency injection, @DependsOn hoặc lifecycle API phù hợp |
| Tạo vòng before/after giữa nhiều class | Quan hệ thứ tự mâu thuẫn, khó bảo trì | Thiết kế phụ thuộc có hướng, tránh vòng; tách cấu hình nếu cần |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Trong AutoConfiguration.imports, A đứng trước B. Có thể suy ra bean của A được đăng ký hoặc khởi tạo trước B không?  
**Đáp án:** Không. Tệp imports liệt kê ứng viên; Spring Boot có cơ chế sắp xếp auto-configuration. Thứ tự xử lý và thứ tự khởi tạo là hai vấn đề khác nhau.

**Câu 2.** ReportAutoConfiguration có @ConditionalOnBean(Clock.class); Clock được một auto-configuration khác đăng ký. Nên thể hiện điều gì?  
**Đáp án:** Khai báo **@AutoConfiguration(after = ClockAutoConfiguration.class)** để Report được xét sau Clock, đồng thời giữ điều kiện kiểm tra sự hiện diện thực tế của Clock.

**Câu 3.** Đổi thứ tự dependency Maven có bảo đảm điều kiện @ConditionalOnBean khớp không?  
**Đáp án:** Không. Dependency resolution quyết định classpath; nó không phải API cam kết thứ tự đánh giá các auto-configuration.

**Câu 4.** Muốn phụ thuộc vào thứ tự của auto-configuration tùy chọn nhưng không thêm compile-time dependency thì dùng gì?  
**Đáp án:** **afterName** hoặc **beforeName** với fully qualified class name; vẫn phải xử lý trường hợp auto-configuration kia vắng mặt.

**Câu 5.** @AutoConfiguration(after = X.class) có bảo đảm X tạo bean bắt buộc không?  
**Đáp án:** Không. X có thể bị loại trừ hoặc không khớp các điều kiện. after chỉ biểu diễn thứ tự giữa các ứng viên được xét.

**Câu 6.** Muốn bean worker được khởi tạo sau initializer, dù không phụ thuộc initializer qua constructor, dùng after trên auto-configuration được không?  
**Đáp án:** Không nên. Đây là ràng buộc **bean lifecycle**; cân nhắc @DependsOn hoặc thiết kế dependency rõ ràng, tùy yêu cầu.

## 12. Ghi nhớ để áp dụng

Trong Spring Boot Auto Configuration, **AutoConfiguration.imports trả lời “cấu hình nào có thể được nạp?”**, còn **@AutoConfiguration(before/after) trả lời “giữa các cấu hình liên quan, cấu hình nào cần được xét trước?”**. Maven/Gradle trả lời bài toán **cung cấp dependency trên classpath**. Các điều kiện @Conditional… quyết định bean có đăng ký hay không, còn dependency injection/lifecycle quyết định tạo và kết nối các bean ra sao.

Khi một auto-configuration cần nhìn thấy bean definition do auto-configuration khác cung cấp, hãy ghi quan hệ before/after ngay trên class, xác minh bằng ApplicationContextRunner và báo cáo điều kiện. **Không phụ thuộc vào thứ tự dòng trong imports hoặc thứ tự khai báo dependency.**
