# Kiểm tra có một bean, không có bean, tên bean và danh tính đối tượng

## 1. Mục tiêu của kiểm thử Spring ApplicationContext

Khi viết Spring Boot auto-configuration hoặc cấu hình ứng dụng, chỉ xác nhận context khởi động thành công là chưa đủ. Một cấu hình có thể khởi động bình thường nhưng vẫn đăng ký sai số lượng bean, sai tên, tạo bean mặc định dù đã có bean tùy chỉnh, hoặc trả về những instance khác nhau ngoài ý muốn.

Các câu hỏi cần kiểm thử thường là:

- Có bean thuộc một type hay không?
- Có đúng **một** bean thuộc type đó hay có nhiều candidate?
- Khi feature bị tắt, bean có thực sự vắng mặt không?
- Bean được đăng ký dưới tên nào? Có alias không?
- Tra cứu theo type và tra cứu theo name có trả về **cùng một object** không?
- Hai lần gọi `getBean` có trả về cùng reference hay tạo instance mới?
- Một bean do ứng dụng cung cấp có khiến auto-configuration nhường chỗ không?

Spring Test và Spring Boot Test cung cấp nhiều API để trả lời những câu hỏi này. Với kiểm thử auto-configuration độc lập, công cụ phù hợp nhất thường là **`ApplicationContextRunner`** kết hợp **`AssertableApplicationContext`** và AssertJ.

Bài dùng Java 17 và Spring Boot 3.3.13 làm baseline minh họa. Các ví dụ có thể chạy trong Maven project độc lập.

## 2. Phân biệt bean tồn tại, bean definition và object instance

Ba khái niệm này liên quan nhưng không đồng nghĩa.

### 2.1. Bean tồn tại trong ApplicationContext

Một bean có thể được tra cứu theo tên hoặc type:

~~~java
context.containsBean("reportClient");
context.getBean("reportClient");
context.getBean(ReportClient.class);
~~~

- `containsBean(name)` trả lời liệu context có thể tra cứu bean theo tên đó hay không.
- `getBean(name)` trả về instance, hoặc ném `NoSuchBeanDefinitionException` nếu không tìm thấy.
- `getBean(type)` tra cứu theo type; nếu không có bean thì ném `NoSuchBeanDefinitionException`, nếu có nhiều candidate không phân biệt được thì ném `NoUniqueBeanDefinitionException`.

Khi mục tiêu chỉ là kiểm tra có/không, không cần gọi `getBean` rồi bắt exception. Dùng assertion chuyên biệt sẽ làm ý định test rõ hơn.

### 2.2. Bean definition và singleton đã đăng ký

Spring quản lý bean thông qua metadata/definition và các instance được tạo từ đó. Hai API có phạm vi khác nhau:

| API | Ý nghĩa |
| --- | --- |
| `containsBean(name)` | Có thể tra cứu bean theo tên, kể cả alias và bean ở parent context |
| `containsLocalBean(name)` | Bean có trong context hiện tại, không chỉ kế thừa từ parent |
| `containsBeanDefinition(name)` | Có bean definition mang tên đó trong bean factory hiện tại |
| `getBeanDefinition(name)` | Lấy metadata definition nếu definition tồn tại |
| `getSingleton(name)` | Lấy singleton instance đã được tạo/đăng ký theo tên, có thể trả null nếu chưa có |

Không dùng `containsBeanDefinition` để thay thế hoàn toàn kiểm tra bean tồn tại. Một singleton có thể được đăng ký trực tiếp mà không có bean definition thông thường; ngược lại, bean definition có thể tồn tại nhưng instance chưa được khởi tạo vì lazy initialization.

Với kiểm thử contract auto-configuration, câu hỏi thường là bean có thể được ứng dụng tra cứu hay không. Vì vậy, ưu tiên assertion trên ApplicationContext theo name/type; chỉ kiểm tra definition hoặc singleton registry khi đó thực sự là điều đang cần xác minh.

### 2.3. Bean name không phải object identity

Tên bean là khóa tra cứu trong container. Object identity là việc hai biến có trỏ tới **cùng một reference** hay không.

Ví dụ:

~~~java
ReportClient byName = context.getBean("reportClient", ReportClient.class);
ReportClient byType = context.getBean(ReportClient.class);
~~~

Hai biến có thể tham chiếu cùng bean singleton:

~~~java
assertThat(byName).isSameAs(byType);
~~~

Đây là phép kiểm tra identity. `isEqualTo` chỉ kiểm tra equality theo `equals()`, không chứng minh hai biến trỏ tới cùng object.

## 3. Chọn API assertion phù hợp

Với `ApplicationContextRunner`, callback nhận `AssertableApplicationContext`. Spring Boot cung cấp các assertion chuyên dụng:

~~~java
assertThat(context).hasBean("reportClient");
assertThat(context).doesNotHaveBean("reportClient");
assertThat(context).hasSingleBean(ReportClient.class);
assertThat(context).doesNotHaveBean(ReportClient.class);
~~~

Ý nghĩa:

| Assertion | Điều được xác nhận |
| --- | --- |
| `hasBean("name")` | Có thể tra cứu bean theo tên |
| `doesNotHaveBean("name")` | Không có bean tra cứu được theo tên |
| `hasSingleBean(Type.class)` | Có đúng một bean có thể gán cho type |
| `doesNotHaveBean(Type.class)` | Không có bean thuộc type |
| `context.getBean(type)` | Lấy bean theo type sau khi đã xác nhận số lượng phù hợp |
| `context.getBean(name, type)` | Lấy bean theo tên và kiểm tra kiểu tương thích |

Nếu muốn kiểm tra chính xác danh sách tên bean, dùng bean factory:

~~~java
String[] names =
        context.getBeanFactory().getBeanNamesForType(ReportClient.class);

assertThat(names).containsExactly("reportClient");
~~~

`getBeanNamesForType` trả về tên bean definition/candidate theo type, không trả về một entry riêng cho mỗi alias. Muốn kiểm tra alias, dùng `getAliases` hoặc tra cứu alias bằng `getBean(alias)`.

Đừng dùng `hasSingleBean` khi ý định là kiểm tra một bean cụ thể theo tên. Một type có thể có nhiều bean hợp lệ; khi đó kiểm tra theo name và kiểm tra số lượng theo type là hai assertion khác nhau.

## 4. Kiểm tra có đúng một bean theo type

Ví dụ ứng dụng muốn có đúng một `ReportClient`:

~~~java
runner.run(context -> {
    assertThat(context).hasSingleBean(ReportClient.class);

    ReportClient client = context.getBean(ReportClient.class);
    assertThat(client.endpoint()).isEqualTo("https://reports.example.test");
});
~~~

`hasSingleBean` hữu ích hơn việc chỉ gọi `getBean(ReportClient.class)`. Nếu có hai bean cùng type, `getBean(type)` ném `NoUniqueBeanDefinitionException`; assertion diễn đạt rõ yêu cầu cardinality ngay tại dòng kiểm tra.

Nếu muốn cho phép nhiều bean, kiểm tra danh sách tên:

~~~java
String[] names =
        context.getBeanFactory().getBeanNamesForType(ReportClient.class);

assertThat(names).contains("primaryReportClient", "archiveReportClient");
assertThat(names).hasSize(2);
~~~

Hãy quyết định test đang kiểm tra điều gì:

- **Có ít nhất một bean:** dùng `hasBean(name)` hoặc kiểm tra mảng tên không rỗng.
- **Có đúng một bean:** dùng `hasSingleBean(type)`.
- **Có chính xác các bean mong đợi:** kiểm tra danh sách tên.
- **Không có bean:** dùng `doesNotHaveBean`.

Tránh assertion yếu như `assertThat(context.getBeansOfType(ReportClient.class)).isNotNull()`: map rỗng vẫn không null, nên test có thể pass dù không có bean nào.

## 5. Kiểm tra không có bean

Khi một feature bị tắt, auto-configuration thường không nên tạo default service bean. Hãy xác nhận cả theo type và tên:

~~~java
runner.withPropertyValues("acme.reports.enabled=false")
        .run(context -> {
            assertThat(context).doesNotHaveBean(ReportClient.class);
            assertThat(context).doesNotHaveBean("reportClient");
        });
~~~

Không nên kiểm tra vắng mặt bằng cách chỉ viết:

~~~java
assertThat(context.getBeanNamesForType(ReportClient.class)).isEmpty();
~~~

Cách đó hợp lệ nếu mục tiêu chính là xác nhận type lookup không có kết quả, nhưng assertion của Spring Boot thể hiện ý định trực tiếp hơn và cho thông báo lỗi dễ đọc.

Cũng không nên bắt mọi exception:

~~~java
assertThatThrownBy(() -> context.getBean(ReportClient.class))
        .isInstanceOf(Exception.class);
~~~

Exception có thể đến từ lỗi khởi tạo bean, dependency hỏng hoặc ambiguity; test như vậy có thể pass vì sai nguyên nhân. Nếu buộc phải kiểm tra exception của API lookup, hãy assert đúng exception type và setup context cụ thể.

## 6. Kiểm tra bean name và alias

### 6.1. Tên mặc định từ @Bean

Nếu không chỉ định tên, Spring dùng tên method làm bean name:

~~~java
@Bean
ReportClient reportClient() {
    return new ReportClient("https://reports.example.test");
}
~~~

Tên bean mặc định là `reportClient`.

Có thể chỉ định tên rõ ràng:

~~~java
@Bean("primaryReportClient")
ReportClient reportClient() {
    return new ReportClient("https://reports.example.test");
}
~~~

Khi đó, tên tra cứu chính là `primaryReportClient`, không phải tên method `reportClient`.

### 6.2. Khai báo nhiều alias

Annotation `@Bean` nhận nhiều tên; tên đầu tiên là bean name chính, các tên còn lại là alias:

~~~java
@Bean(name = {"reportClient", "reports"})
ReportClient reportClient() {
    return new ReportClient("https://reports.example.test");
}
~~~

Kiểm thử:

~~~java
assertThat(context).hasBean("reportClient");
assertThat(context).hasBean("reports");

ReportClient primary =
        context.getBean("reportClient", ReportClient.class);
ReportClient alias =
        context.getBean("reports", ReportClient.class);

assertThat(alias).isSameAs(primary);
assertThat(context.getBeanFactory().getAliases("reportClient"))
        .contains("reports");
~~~

Alias không tạo thêm bean instance. Nó là một tên khác để tra cứu cùng bean. Vì vậy `getBeanNamesForType(ReportClient.class)` thường chỉ liệt kê tên canonical `reportClient`, còn `getAliases("reportClient")` trả về alias `reports`.

### 6.3. Phân biệt @Qualifier, @Primary và bean name

- `@Qualifier` giúp chọn candidate phù hợp khi inject dependency.
- `@Primary` đánh dấu candidate ưu tiên khi có nhiều bean cùng type và injection cần một candidate duy nhất.
- Bean name là tên trong container để tra cứu.
- Alias là tên bổ sung cho cùng bean.

`@Primary` không xóa bean khác, không làm số lượng bean giảm và không bảo đảm `getBean(type)` chỉ có một bean definition. Nếu test cần đúng một bean, hãy kiểm tra số lượng thật thay vì suy ra từ việc inject thành công.

## 7. Kiểm tra object identity: isSameAs và isNotSameAs

### 7.1. Equality khác identity

Giả sử `ReportClient` là Java record:

~~~java
public record ReportClient(String endpoint) {
}
~~~

Record sinh `equals()` và `hashCode()` dựa trên component. Hai instance khác nhau nhưng cùng endpoint vẫn bằng nhau:

~~~java
ReportClient first = new ReportClient("https://reports.example.test");
ReportClient second = new ReportClient("https://reports.example.test");

assertThat(first).isEqualTo(second);
assertThat(first).isNotSameAs(second);
~~~

Nếu dùng `isEqualTo` để chứng minh Spring trả về cùng singleton, test có thể pass dù container đã tạo hai object riêng biệt. Dùng `isSameAs` để kiểm tra reference identity.

### 7.2. Kiểm tra cùng instance qua hai cách tra cứu

~~~java
ReportClient byName =
        context.getBean("reportClient", ReportClient.class);
ReportClient byType = context.getBean(ReportClient.class);

assertThat(byName).isSameAs(byType);
~~~

Với alias:

~~~java
ReportClient canonical =
        context.getBean("reportClient", ReportClient.class);
ReportClient alias =
        context.getBean("reports", ReportClient.class);

assertThat(alias).isSameAs(canonical);
~~~

Hai assertion xác nhận việc tra cứu theo type/name/alias cuối cùng đưa về cùng instance.

### 7.3. Kiểm tra singleton scope

Spring mặc định tạo bean scope singleton trong một ApplicationContext. Hai lần tra cứu bean singleton trả về cùng object:

~~~java
ReportClient first = context.getBean(ReportClient.class);
ReportClient second = context.getBean(ReportClient.class);

assertThat(second).isSameAs(first);
~~~

Singleton ở đây có nghĩa một instance cho mỗi bean definition trong mỗi container, không phải một instance toàn JVM. Hai ApplicationContext riêng biệt có thể có hai singleton instance khác nhau.

## 8. Phân biệt singleton và prototype

Prototype scope tạo một instance mới mỗi lần container được yêu cầu cung cấp bean:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
ReportClient reportClient() {
    return new ReportClient("https://reports.example.test");
}
~~~

Kiểm thử:

~~~java
ReportClient first = context.getBean(ReportClient.class);
ReportClient second = context.getBean(ReportClient.class);

assertThat(first).isNotSameAs(second);
assertThat(first).isEqualTo(second);
~~~

Hai object có cùng dữ liệu nên bằng nhau theo record, nhưng là hai reference riêng.

Lưu ý:

- Singleton là scope mặc định của Spring.
- Prototype tạo object mới mỗi lần tra cứu qua container.
- Spring không quản lý đầy đủ lifecycle destruction của prototype sau khi giao object cho caller.
- Nếu inject prototype trực tiếp vào singleton, prototype thường chỉ được resolve một lần lúc singleton được tạo. Muốn lấy instance mới theo từng lần sử dụng, dùng `ObjectProvider<T>`, `ObjectFactory<T>` hoặc scoped proxy phù hợp.

Ví dụ:

~~~java
@Component
class ReportJob {

    private final ObjectProvider<ReportClient> clients;

    ReportJob(ObjectProvider<ReportClient> clients) {
        this.clients = clients;
    }

    ReportClient newClientForJob() {
        return clients.getObject();
    }
}
~~~

Nếu `ReportClient` là prototype, mỗi lần `newClientForJob()` gọi provider sẽ yêu cầu một instance mới.

## 9. Kiểm tra bean trong parent context

ApplicationContext có thể tạo quan hệ cha–con. Khi tra cứu bean theo tên hoặc type, child context có thể nhìn thấy bean được kế thừa từ parent.

Điều này tạo khác biệt:

- `containsBean(name)` có thể trả true do bean ở parent.
- `containsLocalBean(name)` chỉ kiểm tra context hiện tại.
- `containsBeanDefinition(name)` chỉ kiểm tra bean definition trong bean factory hiện tại.
- `getBean(name)` có thể trả về instance của parent nếu child không có bean cùng tên.

Nếu test yêu cầu bean phải được tạo bởi auto-configuration của **child context**, chỉ assert `containsBean` là chưa đủ. Hãy kiểm tra `containsLocalBean`, bean definition hoặc tên bean trong local bean factory.

Khi cần liệt kê type bao gồm cả parent, dùng tiện ích `BeanFactoryUtils.beanNamesForTypeIncludingAncestors(...)`. Còn `getBeanNamesForType` trên local bean factory giúp kiểm tra bean do context hiện tại sở hữu.

Với phần lớn test auto-configuration đơn giản, không cần parent context. Chỉ thêm parent khi ứng dụng thật có cấu trúc context phân cấp và hành vi kế thừa là một phần contract cần xác minh.

## 10. Không tạo bean khi feature bị tắt: ví dụ auto-configuration

Ta dùng auto-configuration mẫu:

~~~java
@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean(name = {"reportClient", "reports"})
    @ConditionalOnProperty(
            prefix = "acme.reports",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @ConditionalOnMissingBean(ReportClient.class)
    ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
~~~

Có hai condition:

- `@ConditionalOnProperty` bật default client khi `acme.reports.enabled=true`; property vắng mặt cũng được bật do `matchIfMissing=true`.
- `@ConditionalOnMissingBean` cho phép ứng dụng cung cấp ReportClient riêng; nếu bean đó đã có, default method không được áp dụng.

Trong test, ta muốn kiểm tra:

1. Không khai báo property: default bean tồn tại.
2. `enabled=false`: không có default bean.
3. Ứng dụng khai báo custom bean: default bean nhường chỗ.
4. Tra cứu theo alias/name/type trả về cùng singleton instance.
5. Prototype bean cho ra reference mới ở mỗi lần tra cứu.

Đây là contract của auto-configuration; các test không cần khởi chạy HTTP server hay database.

## 11. Ví dụ Maven hoàn chỉnh — Java 17, Spring Boot 3.3.13

### 11.1. Cấu trúc thư mục

~~~text
bean-assertion-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/demo/
    │   │   ├── ReportClient.java
    │   │   └── autoconfigure/ReportsAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/demo/
            └── ReportsAutoConfigurationTests.java
~~~

### 11.2. pom.xml

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
    <groupId>com.example</groupId>
    <artifactId>bean-assertion-demo</artifactId>
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

### 11.3. ReportClient.java

**src/main/java/com/example/demo/ReportClient.java**

~~~java
package com.example.demo;

public record ReportClient(String endpoint) {
}
~~~

Record giúp ví dụ phân biệt equality và identity: hai record cùng endpoint có thể `equals` nhưng vẫn là hai instance riêng.

### 11.4. ReportsAutoConfiguration.java

**src/main/java/com/example/demo/autoconfigure/ReportsAutoConfiguration.java**

~~~java
package com.example.demo.autoconfigure;

import com.example.demo.ReportClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean(name = {"reportClient", "reports"})
    @ConditionalOnProperty(
            prefix = "acme.reports",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @ConditionalOnMissingBean(ReportClient.class)
    ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
~~~

### 11.5. AutoConfiguration.imports

Tạo file:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.demo.autoconfigure.ReportsAutoConfiguration
~~~

Resource này giúp Spring Boot 3.x phát hiện auto-configuration. Trong `ApplicationContextRunner`, ta cũng có thể nạp class trực tiếp qua `AutoConfigurations.of(...)`; vì vậy test vẫn kiểm tra được class ngay cả khi không chạy packaged JAR discovery.

### 11.6. ReportsAutoConfigurationTests.java

**src/test/java/com/example/demo/ReportsAutoConfigurationTests.java**

~~~java
package com.example.demo;

import com.example.demo.autoconfigure.ReportsAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

import static org.assertj.core.api.Assertions.assertThat;

class ReportsAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ReportsAutoConfiguration.class));

    @Test
    void createsExactlyOneDefaultBeanAndExposesItsAlias() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(ReportClient.class);
            assertThat(context).hasBean("reportClient");
            assertThat(context).hasBean("reports");

            String[] names = context.getBeanFactory()
                    .getBeanNamesForType(ReportClient.class);

            assertThat(names).containsExactly("reportClient");

            ReportClient byName =
                    context.getBean("reportClient", ReportClient.class);
            ReportClient byType = context.getBean(ReportClient.class);
            ReportClient byAlias =
                    context.getBean("reports", ReportClient.class);

            assertThat(byName).isSameAs(byType);
            assertThat(byAlias).isSameAs(byName);
            assertThat(context.getBeanFactory().getAliases("reportClient"))
                    .contains("reports");
        });
    }

    @Test
    void disabledFeatureHasNoBeanByTypeOrName() {
        runner.withPropertyValues("acme.reports.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);
                    assertThat(context).doesNotHaveBean("reportClient");
                    assertThat(context).doesNotHaveBean("reports");

                    assertThat(context.getBeanFactory()
                            .getBeanNamesForType(ReportClient.class))
                            .isEmpty();
                });
    }

    @Test
    void customBeanMakesAutoConfigurationBackOff() {
        runner.withUserConfiguration(CustomClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context).hasBean("customReportClient");
                    assertThat(context).doesNotHaveBean("reportClient");

                    ReportClient customByType =
                            context.getBean(ReportClient.class);
                    ReportClient customByName =
                            context.getBean(
                                    "customReportClient", ReportClient.class);

                    assertThat(customByName).isSameAs(customByType);
                    assertThat(customByType.endpoint())
                            .isEqualTo("https://custom.example.test");
                });
    }

    @Test
    void prototypeBeansAreDifferentReferencesEvenWhenEqual() {
        runner.withUserConfiguration(PrototypeClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);

                    ReportClient first = context.getBean(ReportClient.class);
                    ReportClient second = context.getBean(ReportClient.class);

                    assertThat(first).isEqualTo(second);
                    assertThat(first).isNotSameAs(second);
                });
    }

    @Test
    void singletonLookupReturnsTheSameReferenceEachTime() {
        runner.run(context -> {
            ReportClient first = context.getBean(ReportClient.class);
            ReportClient second = context.getBean("reports", ReportClient.class);

            assertThat(first).isSameAs(second);
        });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomClientConfiguration {

        @Bean
        ReportClient customReportClient() {
            return new ReportClient("https://custom.example.test");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrototypeClientConfiguration {

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        ReportClient prototypeReportClient() {
            return new ReportClient("https://prototype.example.test");
        }
    }
}
~~~

### 11.7. Chạy test

Trong thư mục chứa `pom.xml`:

~~~bash
mvn clean test
~~~

Kỳ vọng **năm test pass**. Mỗi test tạo context riêng, do đó property và bean của test này không rò sang test khác.

Test đầu kiểm tra đúng một bean theo type, tên canonical, alias và object identity. Test thứ hai kiểm tra vắng mặt theo type, tên và danh sách bean names. Test thứ ba xác nhận custom bean làm auto-configuration back off. Test thứ tư phân biệt equality với identity của prototype. Test cuối xác nhận singleton trả về cùng reference khi tra cứu lại.

## 12. Khi có nhiều bean cùng type

Giả sử context có:

~~~java
@Bean
ReportClient primaryReportClient() {
    return new ReportClient("https://primary.example.test");
}

@Bean
ReportClient archiveReportClient() {
    return new ReportClient("https://archive.example.test");
}
~~~

Khi đó:

- `hasBean("primaryReportClient")` và `hasBean("archiveReportClient")` đều đúng.
- `hasSingleBean(ReportClient.class)` không đúng vì có hai bean.
- `getBean(ReportClient.class)` có thể ném `NoUniqueBeanDefinitionException` nếu không có candidate ưu tiên phù hợp.
- `getBean("primaryReportClient", ReportClient.class)` vẫn tra cứu được bean theo tên.

Nếu ứng dụng dùng `@Primary`, injection theo type có thể chọn bean primary. Điều đó không làm bean còn lại biến mất. Test nên xác nhận cả số lượng và lựa chọn injection nếu cả hai là contract.

Không nên dùng `@Primary` để che một lỗi duplicate bean name. Hai bean definition trùng tên là vấn đề đăng ký; primary chỉ giải quyết lựa chọn giữa các candidate khác tên.

## 13. Kiểm tra tên bean an toàn và tránh phụ thuộc tên ngầm

Tên bean mặc định từ method `@Bean` tiện lợi nhưng có thể thay đổi khi refactor tên method. Nếu tên bean là một phần public contract (ví dụ consumer tra cứu bằng tên hoặc cấu hình khác tham chiếu tên đó), hãy khai báo tên rõ ràng:

~~~java
@Bean("reportClient")
ReportClient createClient() {
    return new ReportClient("https://reports.example.test");
}
~~~

Với component:

~~~java
@Component("reportClient")
class ReportClientComponent {
}
~~~

Kiểm thử tên bean giúp phát hiện thay đổi ngoài ý muốn khi method hoặc class được rename.

Tránh phụ thuộc vào tên sinh tự động cho nested configuration hoặc tên nội bộ không được công bố. Nếu chỉ cần inject theo type, ưu tiên constructor injection theo type và dùng `@Qualifier` khi có nhiều candidate.

## 14. Kiểm tra bean proxy và identity

Một số bean được bọc bởi AOP proxy, transaction proxy, scoped proxy hoặc infrastructure proxy. Trong trường hợp này, object được inject có thể là proxy thay vì target object bên trong.

Ví dụ:

- Hai dependency injection point cùng nhận một singleton proxy có thể vẫn là cùng reference.
- Proxy có thể khác class concrete của target; kiểm tra `instanceof` implementation có thể cho kết quả bất ngờ.
- Scoped proxy có thể giữ cùng proxy reference nhưng resolve target khác theo scope/request.
- AOP proxy không nên bị kiểm thử bằng cách so sánh trực tiếp với object được tạo bằng `new`.

Nếu mục tiêu là xác nhận Spring tạo một singleton bean, `isSameAs` giữa hai lần tra cứu từ cùng context là hợp lý. Nếu mục tiêu là xác nhận business target hoặc proxy behavior, dùng assertion phù hợp với contract, chẳng hạn kiểm tra interface, bean type dự đoán được hoặc hành vi được gọi qua proxy.

Không unwrap proxy chỉ để làm test pass nếu proxy là một phần semantics của ứng dụng. Hãy kiểm thử qua public interface và hành vi mà consumer thực sự sử dụng.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test gọi `getBean(type)` nhưng fail vì nhiều bean | Có nhiều candidate cùng type | Kiểm tra số lượng/tên hoặc tra cứu bằng qualifier/name |
| Test `isEqualTo` pass nhưng vẫn có hai instance | Equality không phải identity | Dùng `isSameAs` hoặc `isNotSameAs` |
| Kiểm tra alias như một bean thứ hai | Nhầm alias với bean definition | Kiểm tra `getAliases`; alias trỏ tới cùng bean |
| `getBeanNamesForType` không trả alias | API liệt kê canonical bean names | Dùng `getAliases` để kiểm tra alias |
| Bean có ở parent nhưng test tưởng child tạo ra | `containsBean` tìm được bean ở ancestor | Dùng `containsLocalBean` và local bean factory |
| Test absence ném exception không rõ nguyên nhân | Gọi `getBean` trực tiếp rồi bắt exception chung | Dùng `doesNotHaveBean` theo type/name |
| Prototype lookup lại vẫn cùng reference | Test đang tra cứu singleton hoặc inject prototype vào singleton | Gọi trực tiếp container/ObjectProvider và xác nhận scope |
| Hai bean cùng type nhưng inject vẫn thành công | Có `@Primary` hoặc `@Qualifier` | Không suy ra chỉ có một bean; assert số lượng riêng |
| Bean name đổi khi rename method | Dùng tên mặc định của `@Bean` | Đặt tên tường minh nếu tên là contract |
| Auto-configuration không back off dù có custom bean | Custom bean không cùng type/không được đăng ký đúng lúc | Kiểm tra return type, configuration và condition |
| Test context có state từ test khác | Dùng chung mutable static state hoặc context không cô lập | Tạo runner/context độc lập và tránh static mutable object |

## 16. Checklist chọn assertion

Trước khi viết test, xác định chính xác yêu cầu:

| Yêu cầu | Assertion/API |
| --- | --- |
| Có bean theo tên | `assertThat(context).hasBean("name")` |
| Không có bean theo tên | `assertThat(context).doesNotHaveBean("name")` |
| Có đúng một bean theo type | `assertThat(context).hasSingleBean(Type.class)` |
| Không có bean theo type | `assertThat(context).doesNotHaveBean(Type.class)` |
| Kiểm tra danh sách canonical names | `getBeanFactory().getBeanNamesForType(Type.class)` |
| Kiểm tra alias | `getBeanFactory().getAliases("canonicalName")` |
| Tra cứu cùng object theo hai cách | `assertThat(a).isSameAs(b)` |
| Xác nhận hai object khác reference | `assertThat(a).isNotSameAs(b)` |
| Xác nhận cùng giá trị nhưng khác object | `isEqualTo` kết hợp `isNotSameAs` |
| Kiểm tra bean chỉ thuộc child context | `containsLocalBean(name)` |
| Kiểm tra bean definition hiện tại | `containsBeanDefinition(name)` |
| Kiểm tra singleton/prototype | Tra cứu nhiều lần và assert identity |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Muốn xác nhận context có đúng một bean thuộc type `ReportClient`, dùng assertion nào?  
**Đáp án:** `assertThat(context).hasSingleBean(ReportClient.class)`.

**Câu 2.** Vì sao không dùng `isEqualTo` để chứng minh hai lần tra cứu trả về cùng singleton?  
**Đáp án:** Hai instance khác nhau có thể bằng nhau theo `equals()`. Dùng `isSameAs` để kiểm tra reference identity.

**Câu 3.** Một bean có hai alias có nghĩa Spring tạo ba instance không?  
**Đáp án:** Không. Alias là tên tra cứu bổ sung cho cùng bean; các lần tra cứu trả về cùng object theo scope của bean.

**Câu 4.** `getBeanNamesForType` có liệt kê alias như bean name riêng không?  
**Đáp án:** Không. API này liệt kê tên bean; dùng `getAliases` để lấy alias.

**Câu 5.** Khi feature tắt, làm sao kiểm tra bean không tồn tại theo cả type và tên?  
**Đáp án:** Kết hợp `doesNotHaveBean(ReportClient.class)` và `doesNotHaveBean("reportClient")`.

**Câu 6.** Prototype bean được tra cứu hai lần có cùng reference không?  
**Đáp án:** Không. Container tạo instance mới cho mỗi lần tra cứu prototype; hai object vẫn có thể bằng nhau theo `equals()`.

**Câu 7.** Vì sao `containsBean(name)` có thể true dù bean không được định nghĩa trong child context?  
**Đáp án:** Child context có thể tra cứu bean kế thừa từ parent. Dùng `containsLocalBean(name)` nếu cần xác nhận bean thuộc child.

**Câu 8.** `@Primary` có làm các bean cùng type khác biến mất không?  
**Đáp án:** Không. Nó chỉ đánh dấu candidate ưu tiên khi inject; số lượng bean trong context không đổi.

**Ghi nhớ:** Kiểm thử Spring bean cần phân biệt **tồn tại**, **số lượng**, **tên/alias** và **identity**. Dùng `hasBean`/`doesNotHaveBean` cho name, `hasSingleBean` cho cardinality theo type, `getBeanNamesForType` và `getAliases` cho metadata tra cứu, `isSameAs`/`isNotSameAs` cho reference. Với auto-configuration, `ApplicationContextRunner` cho phép xác minh các nhánh bật/tắt, custom-bean back-off và scope trong những context nhỏ, độc lập, dễ tái lập.

## 18. Tài liệu tham khảo

- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing)
- [Spring Boot 3.3 API — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot 3.3 API — AssertableApplicationContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context.assertj/AssertableApplicationContext.html)
- [Spring Framework — BeanFactory](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/beans/factory/BeanFactory.html)
- [Spring Framework — Bean scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
