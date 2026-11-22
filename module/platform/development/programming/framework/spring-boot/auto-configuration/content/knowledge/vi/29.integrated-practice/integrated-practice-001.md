# Dựng thí nghiệm so sánh ứng dụng có và không bật tự cấu hình

## 1. Mục tiêu của thí nghiệm

Spring Boot auto-configuration tự đăng ký bean dựa trên classpath, property, bean mà ứng dụng đã khai báo và loại ApplicationContext. Nhờ vậy, một ứng dụng có thể dùng thư viện chỉ bằng cách thêm starter và khai báo những giá trị cấu hình cần thiết.

Khi cần hiểu một bean đến từ đâu, hoặc vì sao một dependency làm ứng dụng khởi động khác đi, hãy dựng thí nghiệm có hai nhánh:

- **Auto-configuration bật:** Spring Boot nạp auto-configuration candidate, đánh giá condition và đăng ký các bean phù hợp.
- **Auto-configuration không được nạp:** context chỉ có những cấu hình người dùng đã đăng ký; bean mặc định từ auto-configuration mục tiêu không xuất hiện.

Sau đó thêm các nhánh phụ để phân biệt ba tình huống thường bị gộp nhầm:

1. Auto-configuration không được đưa vào context.
2. Auto-configuration được nạp nhưng condition không khớp.
3. Auto-configuration được nạp, condition khớp, nhưng bean mặc định nhường chỗ cho bean do người dùng cung cấp.

Ba tình huống có thể cho kết quả giống nhau ở assertion đơn giản như “không có ReportClient”, nhưng nguyên nhân và cách khắc phục khác nhau.

Bài dùng **Java 17 và Spring Boot 3.3.13** làm baseline. Thí nghiệm chính dùng **ApplicationContextRunner**, công cụ Spring Boot khuyến nghị để tạo các context nhỏ, độc lập và kiểm tra auto-configuration. Không cần database, HTTP server hay dịch vụ bên ngoài.

## 2. Auto-configuration hoạt động như thế nào?

### 2.1. Từ dependency đến bean

Một starter thường đưa các thư viện cần thiết vào classpath. Spring Boot phát hiện các auto-configuration class được công bố trong resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi dòng trong file là tên đầy đủ của một auto-configuration class. Spring Boot xem xét các class đó, áp dụng exclusions, ordering và condition, rồi đăng ký bean definitions phù hợp.

Ví dụ:

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

Nếu classpath có các thư viện cần thiết, property bật tính năng và ứng dụng chưa cung cấp bean thay thế, auto-configuration có thể đăng ký bean mặc định.

### 2.2. Condition quyết định cấu hình có áp dụng không

Các condition thường gặp:

| Condition | Câu hỏi |
| --- | --- |
| @ConditionalOnClass | Class/dependency cần thiết có trên classpath không? |
| @ConditionalOnMissingClass | Một class cụ thể có vắng mặt không? |
| @ConditionalOnProperty | Property có tồn tại và có giá trị mong đợi không? |
| @ConditionalOnBean | Bean prerequisite đã được đăng ký chưa? |
| @ConditionalOnMissingBean | Ứng dụng chưa cung cấp bean tương ứng phải không? |
| @ConditionalOnWebApplication | Context là servlet, reactive hay non-web? |

Một condition không khớp có nghĩa cấu hình hoặc bean method được bảo vệ không được áp dụng. Nó không nhất thiết làm ứng dụng khởi động thất bại.

### 2.3. Auto-configuration bật không có nghĩa mọi bean đều được tạo

Cần phân biệt:

- Candidate: class được Spring Boot xem xét.
- Configuration được áp dụng: class vượt qua các condition ở phạm vi class.
- Bean definition: metadata bean được đăng ký.
- Bean instance: object thực tế được tạo.

Một auto-configuration có thể được nạp nhưng một bean method bên trong bị condition loại. Một bean definition có thể tồn tại nhưng instance được khởi tạo lazy. Vì vậy, thí nghiệm nên kiểm tra đúng bean/type mà mình quan tâm, không chỉ đếm tổng số bean.

## 3. Ba cách “tắt” có ý nghĩa khác nhau

### 3.1. Không nạp auto-configuration trong thí nghiệm

Nếu tạo ApplicationContextRunner mà không thêm AutoConfigurations.of(...), runner không nạp auto-configuration mục tiêu:

~~~java
new ApplicationContextRunner()
        .run(context -> {
            assertThat(context).doesNotHaveBean(ReportClient.class);
        });
~~~

Đây là nhánh control để so sánh với runner có cấu hình được thêm tường minh. Nó hữu ích cho một thí nghiệm cô lập, nhưng không phải cách tắt auto-configuration toàn ứng dụng Spring Boot.

### 3.2. Nạp auto-configuration nhưng condition không khớp

Ví dụ feature chỉ bật khi property là true:

~~~java
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
~~~

Khi chạy với:

~~~properties
acme.reports.enabled=false
~~~

auto-configuration vẫn nằm trong tập candidate được xem xét, nhưng condition không khớp và bean tương ứng không được đăng ký.

Đây là cách tắt một feature có chủ đích bằng cấu hình. Không nên nhầm nó với việc loại class khỏi candidate list.

### 3.3. Exclude một auto-configuration cụ thể

Trong ứng dụng Spring Boot thật, có thể loại một auto-configuration cụ thể:

~~~java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class Application {
}
~~~

Hoặc dùng tên class:

~~~java
@SpringBootApplication(
        excludeName =
                "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")
public class Application {
}
~~~

Hoặc cấu hình:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Các cách này loại những class được chỉ định khỏi quá trình auto-configuration. Chúng không tự tắt mọi auto-configuration khác.

### 3.4. Không bật auto-configuration cho một context

@SpringBootApplication bao gồm @EnableAutoConfiguration, @ComponentScan và @SpringBootConfiguration.

Nếu cần dựng một context không bật auto-configuration để thí nghiệm, có thể dùng @SpringBootConfiguration cùng @ComponentScan mà không thêm @EnableAutoConfiguration:

~~~java
@SpringBootConfiguration
@ComponentScan(basePackages = "com.example.app.components")
public class ApplicationWithoutAutoConfiguration {
}
~~~

Cấu hình đó chỉ scan package component của ứng dụng. Nó không tự nạp các Boot auto-configuration candidates.

Context này phải tự khai báo các infrastructure bean mà trước đó Spring Boot tự cấu hình. Đây là cách so sánh toàn bộ chế độ cấu hình trong một thử nghiệm riêng. Trong ứng dụng thực tế, thường nên exclude một integration cụ thể hoặc điều khiển feature bằng property thay vì bỏ toàn bộ auto-configuration.

## 4. Thiết kế thí nghiệm có kiểm soát

Ta xây một auto-configuration nhỏ cho thư viện Acme Reports:

- Nếu acme.reports.enabled=true, tạo một ReportClient mặc định.
- Nếu property false hoặc không có, không tạo bean.
- Nếu ứng dụng cung cấp ReportClient riêng, auto-configuration phải back off.

Các biến thể cần so sánh:

| Mã | Auto-configuration | Property | Bean do ứng dụng cung cấp | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| A | Không nạp | true | Không | Không có ReportClient mặc định |
| B | Nạp | true | Không | Có ReportClient mặc định |
| C | Nạp | false | Không | Không có ReportClient |
| D | Nạp | true | Có custom bean | Chỉ có custom ReportClient |
| E | Nạp qua @EnableAutoConfiguration | true | Không | Imports resource phát hiện và tạo default |
| F | Nạp qua @EnableAutoConfiguration, exclude tên class | true | Không | Auto-configuration mục tiêu bị loại |

Giữ nguyên JDK, dependency, property và user configuration giữa các nhánh tương ứng. Chỉ thay đổi một yếu tố ở mỗi phép so sánh.

## 5. Tạo Maven project

### 5.1. Cấu trúc thư mục

~~~text
autoconfiguration-experiment/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/reports/
    │   │   ├── ReportClient.java
    │   │   └── autoconfigure/
    │   │       └── ReportsAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/acme/reports/autoconfigure/
            └── AutoConfigurationExperimentTests.java
~~~

### 5.2. pom.xml

~~~xml
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

    <groupId>com.acme</groupId>
    <artifactId>autoconfiguration-experiment</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Parent quản lý phiên bản dependency theo Spring Boot 3.3.13. spring-boot-autoconfigure cung cấp annotation và condition; spring-boot-starter-test cung cấp JUnit, AssertJ và Spring Boot test utilities.

## 6. Viết bean và auto-configuration

### 6.1. ReportClient.java

Tạo file src/main/java/com/acme/reports/ReportClient.java:

~~~java
package com.acme.reports;

public record ReportClient(String endpoint) {
}
~~~

Record giữ endpoint để thí nghiệm kiểm tra giá trị bean. Nó không tạo kết nối mạng.

### 6.2. ReportsAutoConfiguration.java

Tạo file src/main/java/com/acme/reports/autoconfigure/ReportsAutoConfiguration.java:

~~~java
package com.acme.reports.autoconfigure;

import com.acme.reports.ReportClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportClient.class)
    ReportClient reportClient() {
        return new ReportClient("https://default.example.test");
    }
}
~~~

Hai condition có phạm vi khác nhau:

- Condition trên class yêu cầu property bật. Nếu property không phải true, configuration không được áp dụng.
- Condition trên bean method yêu cầu chưa có ReportClient nào do ứng dụng cung cấp. Nếu user bean tồn tại, default method không đăng ký bean.

@ConditionalOnMissingBean thường được đặt trên auto-configuration vì Spring Boot xử lý auto-configuration sau user-defined bean definitions. Nhờ vậy, ứng dụng có cơ hội cung cấp implementation riêng trước khi default bean được xét.

### 6.3. AutoConfiguration.imports

Tạo file:

src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

Nội dung:

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

File này công bố auto-configuration cho ứng dụng tiêu thụ. Khi dùng @EnableAutoConfiguration hoặc @SpringBootApplication, Spring Boot có thể phát hiện class qua resource.

**Phân biệt hai cách nạp trong test:**

- AutoConfigurations.of(ReportsAutoConfiguration.class) thêm class tường minh vào runner, phù hợp để kiểm tra một auto-configuration độc lập.
- @EnableAutoConfiguration dùng cơ chế discovery của Spring Boot và đọc AutoConfiguration.imports. Cách này giúp kiểm tra resource có được đóng gói và phát hiện hay không.

Một test dùng AutoConfigurations.of không tự chứng minh file imports đã được đóng gói đúng.

## 7. Viết thí nghiệm bằng ApplicationContextRunner

Tạo file src/test/java/com/acme/reports/autoconfigure/AutoConfigurationExperimentTests.java.

~~~java
package com.acme.reports.autoconfigure;

import com.acme.reports.ReportClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationExperimentTests {

    private static final String ENABLED =
            "acme.reports.enabled=true";

    private static final String DISABLED =
            "acme.reports.enabled=false";

    private static final String AUTO_CONFIGURATION_NAME =
            "com.acme.reports.autoconfigure.ReportsAutoConfiguration";

    // Nhánh A: không nạp auto-configuration mục tiêu.
    private final ApplicationContextRunner withoutAutoConfiguration =
            new ApplicationContextRunner()
                    .withPropertyValues(ENABLED);

    // Nhánh B: nạp chính xác auto-configuration cần kiểm tra.
    private final ApplicationContextRunner withAutoConfiguration =
            this.withoutAutoConfiguration
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ReportsAutoConfiguration.class));

    @Test
    void withoutAutoConfigurationDoesNotCreateDefaultBean() {
        this.withoutAutoConfiguration.run(context -> {
            assertThat(context).doesNotHaveBean(ReportClient.class);
            assertThat(reportClientNames(context)).isEmpty();
        });
    }

    @Test
    void withAutoConfigurationAndEnabledPropertyCreatesDefaultBean() {
        this.withAutoConfiguration.run(context -> {
            assertThat(context).hasSingleBean(ReportClient.class);
            assertThat(reportClientNames(context))
                    .containsExactly("reportClient");

            assertThat(context.getBean(ReportClient.class).endpoint())
                    .isEqualTo("https://default.example.test");
        });
    }

    @Test
    void falsePropertyPreventsDefaultBeanRegistration() {
        this.withAutoConfiguration
                .withPropertyValues(DISABLED)
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);
                    assertThat(reportClientNames(context)).isEmpty();
                });
    }

    @Test
    void userBeanMakesDefaultAutoConfigurationBackOff() {
        this.withAutoConfiguration
                .withUserConfiguration(CustomReportConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(reportClientNames(context))
                            .containsExactly("customReportClient");

                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo("https://custom.example.test");
                });
    }

    @Test
    void userBeanStillExistsWhenAutoConfigurationIsNotLoaded() {
        this.withoutAutoConfiguration
                .withUserConfiguration(CustomReportConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(reportClientNames(context))
                            .containsExactly("customReportClient");
                });
    }

    @Test
    void enableAutoConfigurationDiscoversImportsResource() {
        new ApplicationContextRunner()
                .withUserConfiguration(BootAutoConfigurationEnabled.class)
                .withPropertyValues(ENABLED)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo("https://default.example.test");
                });
    }

    @Test
    void excludeNameRemovesThePublishedAutoConfiguration() {
        new ApplicationContextRunner()
                .withUserConfiguration(BootAutoConfigurationExcluded.class)
                .withPropertyValues(ENABLED)
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);
                });
    }

    private static String[] reportClientNames(
            AssertableApplicationContext context) {

        return context.getBeanFactory()
                .getBeanNamesForType(ReportClient.class);
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomReportConfiguration {

        @Bean
        ReportClient customReportClient() {
            return new ReportClient("https://custom.example.test");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class BootAutoConfigurationEnabled {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration(excludeName = AUTO_CONFIGURATION_NAME)
    static class BootAutoConfigurationExcluded {
    }
}
~~~

### 7.1. Ý nghĩa từng test

| Test | Điều kiện thay đổi | Điều cần chứng minh |
| --- | --- | --- |
| withoutAutoConfiguration... | Không thêm auto-config vào runner | Không có default bean |
| withAutoConfiguration... | Thêm auto-config, property true | Có default bean |
| falseProperty... | Auto-config vẫn được nạp, property false | Class được xét nhưng condition loại cấu hình |
| userBeanMakes... | Thêm custom bean trước auto-config | Default bean back off |
| userBeanStillExists... | Không nạp auto-config, vẫn có user config | Bean ứng dụng không phụ thuộc default |
| enableAutoConfiguration... | Dùng @EnableAutoConfiguration | Boot phát hiện class từ imports resource |
| excludeNameRemoves... | Exclude FQCN auto-config | Boot bỏ qua auto-config được chỉ định |

Hai test đầu là phép so sánh chính. Các test còn lại giúp tách nguyên nhân khi kết quả không như mong đợi.

### 7.2. Chạy thí nghiệm

Trong thư mục có pom.xml:

~~~bash
mvn clean test
~~~

Kết quả mong đợi: **bảy test pass**.

Test dùng ApplicationContextRunner, vì vậy không cần khởi động embedded server. Mỗi lần gọi run tạo một context riêng, thực hiện assertion rồi đóng context.

### 7.3. Bảng kết quả dự kiến

Các tên bean dưới đây là kết quả của bean type ReportClient, không phải tổng số bean trong ApplicationContext:

| Nhánh | Tên bean ReportClient | Endpoint |
| --- | --- | --- |
| Auto-config không nạp | [] | Không có |
| Auto-config nạp, enabled=true | [reportClient] | https://default.example.test |
| Auto-config nạp, enabled=false | [] | Không có |
| Auto-config nạp, có user bean | [customReportClient] | https://custom.example.test |
| Auto-config không nạp, có user bean | [customReportClient] | https://custom.example.test |
| Discovery qua imports | [reportClient] | https://default.example.test |
| Exclude class qua tên | [] | Không có |

Điểm cần rút ra:

- Không có auto-configuration không ngăn user configuration tạo bean.
- Property false ngăn feature ở mức condition.
- Custom bean được ưu tiên và làm default bean back off.
- @EnableAutoConfiguration kiểm tra đường discovery thực tế qua imports resource.
- Exclusion kiểm tra việc loại một candidate cụ thể.

## 8. Thử với ứng dụng Spring Boot thật

ApplicationContextRunner rất phù hợp để kiểm thử từng nhánh. Nếu cần kiểm tra hành vi của một ứng dụng được khởi chạy bằng SpringApplication, hãy tạo hai cấu hình rõ ràng.

### 8.1. Ứng dụng bật auto-configuration

~~~java
package com.example.app;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApplicationWithAutoConfiguration {
}
~~~

@SpringBootApplication bao gồm @EnableAutoConfiguration, nên Boot sẽ tìm các auto-configuration được công bố trong imports resource.

### 8.2. Ứng dụng không bật auto-configuration

~~~java
package com.example.app;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.context.annotation.ComponentScan;

@SpringBootConfiguration
@ComponentScan(basePackages = "com.example.app.components")
public class ApplicationWithoutAutoConfiguration {
}
~~~

Cấu hình này không có @EnableAutoConfiguration. Nó chỉ scan package component của ứng dụng; không tự nạp các Boot auto-configuration candidates.

Context này phải tự khai báo các infrastructure bean mà trước đó Spring Boot tự cấu hình. Ví dụ, nếu trước đó ứng dụng dựa vào auto-configuration để tạo Jackson mapper, task executor hoặc datasource, những bean đó có thể không còn.

Giữ package thư viện auto-configuration ngoài component scan. Nếu component scan bao phủ package thư viện, class @AutoConfiguration có thể bị phát hiện như một configuration thông thường; khi đó thí nghiệm không còn so sánh riêng đường auto-configuration.

### 8.3. Chỉ loại một auto-configuration trong ứng dụng thật

Thông thường, hãy giữ @SpringBootApplication và loại đúng integration không cần:

~~~java
@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class)
public class Application {
}
~~~

Hoặc cấu hình trong application.properties:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Không nên bỏ toàn bộ auto-configuration chỉ để loại một bean hoặc một integration.

## 9. Quan sát condition và nguồn bean

### 9.1. Bật Condition Evaluation Report

Chạy ứng dụng với:

~~~bash
java -jar target/autoconfiguration-experiment-1.0.0.jar --debug
~~~

Hoặc:

~~~properties
debug=true
~~~

Report cho biết auto-configuration nào match và không match, cùng lý do. Nếu ReportsAutoConfiguration không match vì property false, report giúp phân biệt nguyên nhân với việc class bị exclude hoặc không được phát hiện.

Trong test có thể thêm listener:

~~~java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .withConfiguration(
                AutoConfigurations.of(ReportsAutoConfiguration.class))
        .run(context -> {
            // Assertion của thí nghiệm
        });
~~~

Các import tương ứng:

~~~java
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
~~~

### 9.2. Kiểm tra bean theo type

Không nên chỉ nhìn tổng số bean. Dùng:

~~~java
String[] names = context.getBeanFactory()
        .getBeanNamesForType(ReportClient.class);

System.out.println(Arrays.toString(names));
~~~

Và import:

~~~java
import java.util.Arrays;
~~~

API này cho biết tên bean thuộc type cần kiểm tra. Nếu có nhiều implementation, danh sách giúp phát hiện candidate trùng.

### 9.3. Phân biệt bean definition và instance

Nếu bean được đánh dấu @Lazy, definition có thể tồn tại nhưng instance chưa được tạo. Khi kiểm tra:

~~~java
boolean definitionExists =
        context.getBeanFactory()
                .containsBeanDefinition("reportClient");

boolean singletonCreated =
        context.getBeanFactory()
                .containsSingleton("reportClient");
~~~

Hai giá trị có ý nghĩa khác nhau. Không dùng containsSingleton để kết luận auto-configuration có đăng ký bean definition hay không.

### 9.4. Kiểm tra source của bean definition

Khi bean xuất hiện ngoài dự kiến, xem metadata:

~~~java
BeanDefinition definition =
        context.getBeanFactory()
                .getBeanDefinition("reportClient");

System.out.println(definition.getResourceDescription());
System.out.println(definition.getFactoryBeanName());
System.out.println(definition.getFactoryMethodName());
~~~

Với bean được tạo bằng @Bean, factory method và configuration class thường giúp truy ra nơi đăng ký bean. Resource description có thể không có ở mọi loại definition.

## 10. Đo hiệu năng khi bật và tắt auto-configuration

Thí nghiệm ở trên xác minh **hành vi đăng ký bean**. Nó chưa phải benchmark startup của một ứng dụng production.

### 10.1. Những đại lượng nên đo

| Đại lượng | Cách hiểu |
| --- | --- |
| Startup time | Thời gian từ khi process bắt đầu đến mốc readiness thống nhất |
| Bean definitions | Số lượng và loại bean definition được đăng ký |
| Singleton instances | Số object được tạo khi context refresh hoàn tất |
| First-use latency | Độ trễ khi lần đầu sử dụng một bean lazy hoặc integration |
| Memory | Heap sau startup và sau khi workload ổn định |
| Request latency | Độ trễ của request sau khi ứng dụng sẵn sàng |

Không dùng tổng số bean duy nhất làm đại diện cho startup cost. Một auto-configuration có thể đăng ký nhiều bean nhẹ; một bean khác có thể tạo connection pool hoặc thực hiện I/O tốn kém.

### 10.2. So sánh công bằng

Để so sánh hai biến thể:

1. Dùng cùng JDK và cùng bản build.
2. Giữ nguyên dependency graph, profile, property và môi trường.
3. Chỉ thay đổi auto-configuration mục tiêu.
4. Khởi chạy process mới cho mỗi lần đo nếu muốn đo cold startup.
5. Chạy nhiều lần và so sánh median, p95; không chọn lần nhanh nhất.
6. Đo cùng một mốc readiness.
7. Đo cả first-use latency nếu bean được trì hoãn.
8. Ghi nhận heap và số bean mục tiêu sau khi ứng dụng đã ổn định.

Có thể dùng time trên Linux/macOS hoặc Measure-Command trên PowerShell để đo wall-clock process. Với server giữ process chạy liên tục, cần đo mốc readiness hoặc startup event thay vì đợi process kết thúc. Không so sánh một lần chạy từ IDE với một lần chạy từ JAR vì môi trường và classpath có thể khác nhau.

### 10.3. Đo startup steps

Spring Boot hỗ trợ ApplicationStartup để ghi nhận các bước trong quá trình khởi động. Có thể bật BufferingApplicationStartup:

~~~java
SpringApplication application =
        new SpringApplication(Application.class);

application.setApplicationStartup(
        new BufferingApplicationStartup(2048));

application.run(args);
~~~

Cần cấu hình cùng một instrumentation cho cả hai biến thể. Nếu có Actuator, có thể dùng startup endpoint theo cấu hình expose phù hợp để xem các bước tốn thời gian.

Đo bằng Java Flight Recorder cũng giúp quan sát class loading, allocation, garbage collection và hoạt động JVM. Hãy phân biệt thời gian tạo ApplicationContext với thời gian toàn process.

### 10.4. Không kết luận trước khi đo

Tắt một auto-configuration có thể giảm parsing, condition evaluation, bean definitions và instance liên quan. Tuy nhiên, nếu integration đó không tạo nhiều công việc trong lần chạy hiện tại, chênh lệch startup có thể rất nhỏ.

Ngược lại, tắt một auto-configuration cần thiết có thể khiến ứng dụng phải tự tạo nhiều bean, dẫn tới chi phí và độ phức tạp cao hơn.

Kết quả benchmark cần đi kèm hành vi ứng dụng. Một biến thể khởi động nhanh hơn nhưng thiếu datasource, health indicator hoặc serializer cần thiết không phải là một cải tiến hợp lệ.

## 11. Các lỗi thường gặp trong thí nghiệm

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không có bean ở cả hai nhánh | Property không bật hoặc condition khác không khớp | Kiểm tra property và Condition Evaluation Report |
| Test không auto-config vẫn có bean | User configuration hoặc component scan tự đăng ký bean | Kiểm tra nguồn bean và cấu hình runner |
| Property false nhưng bean vẫn tồn tại | Bean được đăng ký qua configuration khác | Tìm tất cả bean names và BeanDefinition source |
| Exclude không có tác dụng | Class được import trực tiếp hoặc component scan phát hiện | Kiểm tra đường nạp class; exclusion chỉ áp dụng cho auto-configuration import |
| Có hai bean cùng type | User bean và default bean cùng được đăng ký | Kiểm tra ConditionalOnMissingBean, ordering và nguồn definition |
| Custom bean không làm default back off | User configuration chưa được xử lý đúng lúc hoặc condition đặt sai | Giữ default trong auto-configuration path và kiểm tra runner |
| Test pass nhưng ứng dụng thật khác | Test nạp class trực tiếp, không kiểm tra imports hoặc component scan thực tế | Thêm test EnableAutoConfiguration và consumer smoke test |
| Đếm bean cho kết quả không ổn định | Đếm cả infrastructure bean và dependency khác | Kiểm tra bean names theo type mục tiêu |
| Startup nhanh hơn nhưng request đầu chậm | Chi phí khởi tạo bị chuyển sang first use | Đo cả startup và first-use latency |
| Tắt auto-config làm ứng dụng lỗi | Ứng dụng phụ thuộc bean infrastructure do Boot cung cấp | Chỉ exclude integration có chủ đích và cung cấp bean thay thế nếu cần |
| Dùng spring.autoconfigure.exclude nhưng vẫn có bean | Một đường đăng ký khác vẫn nạp class | Kiểm tra component scan, @Import và configuration khác |
| So sánh thời gian chỉ một lần | JIT, class loading, máy và process state gây nhiễu | Chạy nhiều process mới và so sánh phân phối kết quả |

## 12. Checklist hoàn thành thí nghiệm

### Thiết lập

- [ ] Cùng JDK, dependency và build artifact cho các nhánh.
- [ ] Ghi rõ auto-configuration mục tiêu.
- [ ] Ghi rõ property và user bean ở từng nhánh.
- [ ] Có nhánh control không nạp auto-configuration.
- [ ] Có nhánh nạp auto-configuration và property bật.
- [ ] Có nhánh condition không khớp.
- [ ] Có nhánh user bean khiến default back off.

### Quan sát

- [ ] Kiểm tra bean names theo type mục tiêu.
- [ ] Kiểm tra endpoint/giá trị bean khi bean xuất hiện.
- [ ] Kiểm tra imports discovery qua @EnableAutoConfiguration.
- [ ] Kiểm tra exclusion bằng tên class.
- [ ] Đọc Condition Evaluation Report khi kết quả khác dự kiến.
- [ ] Kiểm tra bean definition nếu nghi ngờ bean được đăng ký từ nguồn khác.

### Hiệu năng

- [ ] Chỉ thay đổi một biến giữa hai lần chạy.
- [ ] Dùng process mới cho cold startup.
- [ ] Chạy đủ lần để có median và p95.
- [ ] Đo cùng readiness marker.
- [ ] Đo first-use latency nếu có lazy bean.
- [ ] Ghi nhận memory và hành vi chức năng sau startup.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Trong thí nghiệm, làm sao tạo nhánh không nạp một auto-configuration cụ thể?  
**Đáp án:** Dùng ApplicationContextRunner không gọi withConfiguration(AutoConfigurations.of(...)) cho class đó.

**Câu 2.** Auto-configuration đã được nạp nhưng property false có giống với việc không nạp class không?  
**Đáp án:** Không. Class vẫn được xem xét, nhưng condition không khớp nên cấu hình/bean được bảo vệ không được đăng ký.

**Câu 3.** ConditionalOnMissingBean giúp gì trong thí nghiệm?  
**Đáp án:** Nó cho phép bean mặc định nhường chỗ khi user configuration đã cung cấp bean cùng type.

**Câu 4.** Vì sao cần test cả AutoConfigurations.of và @EnableAutoConfiguration?  
**Đáp án:** Cách thứ nhất cô lập một class để kiểm tra logic; cách thứ hai xác minh Boot phát hiện class qua AutoConfiguration.imports.

**Câu 5.** spring.autoconfigure.exclude có tắt toàn bộ auto-configuration không?  
**Đáp án:** Không. Nó loại các auto-configuration class được liệt kê. Muốn context không bật auto-configuration, không thêm @EnableAutoConfiguration/@SpringBootApplication vào configuration đó.

**Câu 6.** Vì sao không nên chỉ so sánh tổng số bean?  
**Đáp án:** Context còn có infrastructure bean và bean từ dependency khác. Hãy kiểm tra type/name của bean mục tiêu và nguồn definition.

**Câu 7.** Làm sao xác nhận auto-configuration class được phát hiện từ JAR?  
**Đáp án:** Dùng @EnableAutoConfiguration trong consumer test, sau đó kiểm tra resource AutoConfiguration.imports trong JAR đã đóng gói.

**Câu 8.** Khi bật auto-configuration, custom bean có nhất thiết bị thay bằng default không?  
**Đáp án:** Không. Nếu default bean có ConditionalOnMissingBean và user bean được đăng ký trước, default sẽ back off.

**Câu 9.** Có thể dùng thời gian một lần chạy mvn test làm startup benchmark không?  
**Đáp án:** Không nên. Test time bao gồm Maven, test discovery, JVM và nhiều context. Muốn đo startup ứng dụng, chạy cùng JAR trong process mới nhiều lần và dùng cùng readiness marker.

**Câu 10.** Nếu tắt auto-configuration làm ứng dụng khởi động nhanh hơn nhưng thiếu bean cần thiết thì có phải kết quả tốt không?  
**Đáp án:** Không. Hiệu năng chỉ có ý nghĩa khi biến thể vẫn đáp ứng đầy đủ hành vi và yêu cầu vận hành.

**Ghi nhớ:** Một thí nghiệm tốt tách được ba nguyên nhân: auto-configuration không được nạp, condition không khớp, và default bean back off vì user bean. Dùng ApplicationContextRunner để so sánh các context nhỏ, @EnableAutoConfiguration để kiểm tra imports discovery, exclusion để loại đúng integration trong ứng dụng thật, rồi đo startup và first-use latency trong cùng điều kiện.

## 14. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Using the @SpringBootApplication Annotation](https://docs.spring.io/spring-boot/3.3/reference/using/using-the-springbootapplication-annotation.html)
- [Spring Boot 3.3 — Auto-configuration Classes](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [ApplicationContextRunner — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
