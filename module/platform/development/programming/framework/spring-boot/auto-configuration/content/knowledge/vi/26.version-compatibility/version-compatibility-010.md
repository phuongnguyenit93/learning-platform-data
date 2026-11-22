# Chạy ma trận phiên bản để phát hiện thay đổi điều kiện và hành vi nhường chỗ

**Chủ đề:** Spring Boot Auto Configuration  
**Nhóm kiến thức:** Tương thích phiên bản  
**Mục tiêu:** Xây dựng một bộ kiểm thử chạy trên nhiều dòng Spring Boot để phát hiện sớm thay đổi trong class condition, property condition, bean condition, thứ tự đăng ký và hành vi back-off khi ứng dụng tự cung cấp bean. Bài dùng cùng một bộ test Java 17 chạy lần lượt với Spring Boot 2.6, 2.7 và 3.3.

## 1. Vì sao phải chạy test trên nhiều phiên bản?

Một thư viện auto-configuration có thể được ứng dụng sử dụng cùng nhiều phiên bản Spring Boot. Mỗi phiên bản mang theo một bộ Spring Framework, Spring Boot Autoconfigure, Binder, condition implementation và test support tương ứng.

Một test pass với Boot 3 không chứng minh thư viện vẫn hoạt động với Boot 2.6. Tương tự, việc source code biên dịch thành công không chứng minh condition sẽ match giống nhau trong runtime. Các thay đổi dependency, classpath, thứ tự auto-configuration hoặc cách ứng dụng đăng ký bean có thể làm kết quả thay đổi.

Ví dụ một thư viện có default service:

```java
@Bean
@ConditionalOnMissingBean(ReportService.class)
DefaultReportService reportService() {
    return new DefaultReportService();
}
```

Hành vi mong đợi:

- Khi feature được bật và không có `ReportService` do ứng dụng cung cấp, Spring tạo default service.
- Khi ứng dụng cung cấp một `ReportService`, auto-configuration nhường chỗ.
- Khi property tắt hoặc dependency tùy chọn vắng mặt, nhánh auto-configuration không được áp dụng.
- Khi user configuration và auto-configuration cùng xuất hiện, user bean phải được xét trước điều kiện back-off của auto-configuration.

Nếu một phiên bản có lỗi thứ tự đăng ký, khác biệt classpath hoặc thay đổi trong condition processing, một số trường hợp trên có thể không còn đúng. Ma trận phiên bản giúp kiểm tra cùng một hợp đồng hành vi trên từng dependency baseline.

## 2. Phân biệt hợp đồng ổn định và khác biệt có chủ đích

Không nên chỉ chạy một bộ test rồi giả định mọi phiên bản phải có cùng implementation nội bộ. Trước khi tạo matrix, hãy xác định:

1. **Hành vi phải ổn định:** feature bật thì default bean xuất hiện; user bean thay thế default; dependency tùy chọn thiếu thì nhánh đó không được kích hoạt.
2. **Hành vi phụ thuộc phiên bản:** API annotation có thể khác, Java baseline có thể khác, cách đăng ký auto-configuration có thể thay đổi.
3. **Hành vi không được giả định:** thứ tự ngẫu nhiên của classpath, tên bean do component scan tình cờ tạo ra, hoặc condition match chỉ vì một bean được khai báo ở một vị trí không được bảo đảm.

Ma trận dưới đây dùng ba mốc đại diện:

| Ma trận | Spring Boot | Mục đích |
| --- | --- | --- |
| Legacy baseline | 2.6.15 | Kiểm tra source/API và condition trên dòng 2.x trước cơ chế registration mới |
| Transition baseline | 2.7.18 | Kiểm tra dòng chuyển tiếp 2.x và các API auto-configuration mới |
| Modern baseline | 3.3.13 | Kiểm tra Spring Boot 3, Spring Framework 6 và Java 17 |

Đây là các phiên bản mốc để minh họa quy trình, không phải tuyên bố về trạng thái hỗ trợ hiện tại của các dòng phát hành. Trong dự án thật, thay chúng bằng phiên bản thấp nhất mà thư viện cam kết hỗ trợ và một hoặc nhiều phiên bản đang dùng trong sản phẩm.

### 2.1. Chọn JDK cho ma trận

Spring Boot 3 yêu cầu Java 17 trở lên. Boot 2.6 và 2.7 cũng có thể chạy trên Java 17, vì vậy ví dụ dùng một JDK 17 cho cả ba profile để cô lập biến số Spring Boot.

Nếu thư viện còn cam kết chạy trên Java 8 hoặc Java 11, cần một ma trận JDK riêng cho các dòng Boot cũ. Không thể dùng cùng một JDK 8 job để kiểm tra Boot 3.

Một ma trận đầy đủ có thể gồm hai chiều:

- Phiên bản Spring Boot.
- Phiên bản JDK mà dòng Boot đó hỗ trợ và thư viện cam kết hỗ trợ.

Đừng gộp kết quả của hai chiều thành một kết luận duy nhất. Lỗi do Java bytecode/API khác với lỗi do Spring condition hoặc auto-configuration ordering.

## 3. Những condition cần đưa vào ma trận

Một bộ kiểm thử auto-configuration hữu ích nên kiểm tra các nhóm sau:

| Nhóm condition | Điều cần kiểm tra | Cách tạo tình huống |
| --- | --- | --- |
| Class condition | Có class thì match; thiếu class thì no-match an toàn | Classpath bình thường và `FilteredClassLoader` |
| Property condition | Property thiếu, false và true cho kết quả đúng | `withPropertyValues(...)` |
| Bean condition | Default bean chỉ xuất hiện khi chưa có bean phù hợp | User configuration cung cấp bean cùng contract |
| Ordering | Bean condition nhìn thấy những bean được đăng ký trước nó | `AutoConfigurations.of(...)` và ordering annotation |
| Context type | Servlet/reactive condition chỉ match đúng loại context | `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner` |
| Bean hierarchy | Condition có xét parent context hay không | Parent/child context nếu thư viện dùng context hierarchy |

Không phải thư viện nào cũng cần tất cả nhóm. Hãy chọn theo annotation và extension point thực sự xuất hiện trong auto-configuration của bạn.

### 3.1. Class condition

`@ConditionalOnClass` và `@ConditionalOnMissingClass` điều khiển cấu hình theo sự hiện diện của class trên runtime classpath.

Một bài test chỉ chạy khi classpath đầy đủ không phát hiện được lỗi optional dependency. `FilteredClassLoader` cho phép mô phỏng một ứng dụng consumer không có thư viện tùy chọn mà không cần tạo một project Maven thứ hai.

Khi optional class vắng mặt, cần kiểm tra cả hai điều:

- Condition no-match và bean tùy chọn không xuất hiện.
- ApplicationContext vẫn khởi động, không gặp `NoClassDefFoundError` hoặc lỗi linkage.

Nếu class tùy chọn xuất hiện trong chữ ký của configuration class hoặc `@Bean` method không được cô lập đúng cách, condition có thể được đánh giá quá muộn để bảo vệ class loading. Với optional API, hãy đặt class condition ở cấp configuration phù hợp và giữ tham chiếu tới API tùy chọn trong nhánh đã được bảo vệ.

### 3.2. Property condition

`@ConditionalOnProperty` mặc định match khi property tồn tại và giá trị không bằng `false`. Để contract dễ hiểu và dễ test, nên khai báo rõ `havingValue` và quyết định `matchIfMissing`.

Ví dụ:

```java
@ConditionalOnProperty(
        prefix = "acme.feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
```

Ma trận cần có ít nhất:

- Property không được khai báo.
- Property được đặt thành `false`.
- Property được đặt thành `true`.

Nếu implementation dùng `matchIfMissing = true`, expected result phải được cập nhật theo contract đó. Không viết test dựa vào default ngầm mà không ghi rõ ý nghĩa khi property bị thiếu.

### 3.3. Bean condition và hành vi back-off

`@ConditionalOnMissingBean` cho phép ứng dụng thay thế default bean do auto-configuration cung cấp.

Điều kiện này được đánh giá dựa trên bean definitions đã được xử lý tại thời điểm đó. Vì vậy, Spring Boot khuyến nghị sử dụng bean conditions trên auto-configuration class: auto-configuration được nạp sau user-defined bean definitions, giúp điều kiện nhìn thấy bean do ứng dụng cung cấp.

Một test back-off phải mô phỏng đúng thứ tự đó. Dùng `AutoConfigurations.of(MyAutoConfiguration.class)` cho auto-configuration và `withUserConfiguration(...)` cho cấu hình của ứng dụng. Nếu đưa cả hai vào như các configuration thông thường, test có thể không đại diện cho thứ tự xử lý trong ứng dụng thật.

Cũng nên khai báo kiểu trả về của `@Bean` đủ cụ thể. Bean condition cần thông tin kiểu có sẵn từ method signature để nhận diện bean definition trước khi khởi tạo object.

## 4. `ApplicationContextRunner` là nền tảng của bộ test

`ApplicationContextRunner` tạo một ApplicationContext nhỏ cho mỗi test, cho phép thay đổi property, user configuration và classloader mà không phải khởi động toàn bộ ứng dụng.

Mẫu khởi tạo:

```java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(FeatureAutoConfiguration.class)
                );
```

Cấu hình auto-configuration qua `AutoConfigurations.of(...)` có ý nghĩa quan trọng:

- Auto-configuration được áp dụng theo cơ chế test support của Spring Boot.
- User configuration được xử lý theo vị trí thích hợp trước auto-configuration.
- Các bean condition như `@ConditionalOnMissingBean` có thể được kiểm tra đúng hành vi back-off.
- Mỗi lần gọi `run(...)` tạo một context độc lập, nên test không rò rỉ bean hoặc property sang test kế tiếp.

Một test nên tạo một tình huống rõ ràng và assert vào kết quả thực tế: context có lỗi không, có đúng một bean không, bean nào được dùng và default bean có bị loại hay không.

`ApplicationContextRunner` phù hợp cho condition/bean tests. Nó không thay thế integration test kiểm tra resource registration hoặc việc ứng dụng được đóng gói và khởi động từ artifact đã publish.

## 5. Tổ chức một project Maven chạy nhiều Boot baseline

Có thể dùng một project test chung và các Maven profile để chọn Spring Boot BOM. Mỗi lần chạy chỉ kích hoạt **một profile**, nhờ vậy toàn bộ dependency Spring Boot, Spring Framework, JUnit và AssertJ được căn chỉnh theo cùng một baseline.

### 5.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>condition-version-matrix</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <spring-boot.version>3.3.13</spring-boot.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

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

    <profiles>
        <profile>
            <id>boot-2.6</id>
            <properties>
                <spring-boot.version>2.6.15</spring-boot.version>
            </properties>
        </profile>

        <profile>
            <id>boot-2.7</id>
            <properties>
                <spring-boot.version>2.7.18</spring-boot.version>
            </properties>
        </profile>

        <profile>
            <id>boot-3.3</id>
            <properties>
                <spring-boot.version>3.3.13</spring-boot.version>
            </properties>
        </profile>
    </profiles>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>${java.version}</release>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

POM import Spring Boot BOM thay vì dùng một tập version Spring rời rạc. Khi profile thay `spring-boot.version`, Maven giải quyết các dependency Spring Boot và test tương ứng cùng một dòng.

Dự án không dùng `@AutoConfiguration` trong source chung của ví dụ vì annotation này không có trong Boot 2.6. Dùng `@Configuration(proxyBeanMethods = false)` giúp cùng bộ source test compile trên cả ba baseline. Trong module production chỉ hỗ trợ Boot 2.7 trở lên, có thể dùng `@AutoConfiguration` theo convention của phiên bản đó.

### 5.2. Chạy từng baseline

Tại thư mục chứa `pom.xml`:

```bash
mvn -Pboot-2.6 clean verify
mvn -Pboot-2.7 clean verify
mvn -Pboot-3.3 clean verify
```

Chạy từng lệnh riêng. Không bật đồng thời nhiều profile vì chúng cùng ghi đè một property `spring-boot.version`.

`clean` bảo đảm không dùng class hoặc resource được compile từ baseline trước. `verify` chạy các phase trước đó, bao gồm compile và test, rồi hoàn tất các bước verification được cấu hình trong Maven lifecycle.

Để xác nhận dependency graph đúng với profile đang chạy:

```bash
mvn -Pboot-2.6 dependency:tree
mvn -Pboot-2.7 dependency:tree
mvn -Pboot-3.3 dependency:tree
```

Kiểm tra rằng `spring-boot-autoconfigure`, `spring-boot-test` và Spring Framework đến từ cùng baseline mong đợi. Tránh ép một version Spring Framework riêng khiến test không còn đại diện cho dependency graph của Boot.

## 6. Ví dụ production code dùng chung cho ma trận

Ví dụ kiểm tra một feature tùy chọn có service mặc định. Service chỉ được đăng ký khi:

1. Class marker của thư viện optional có mặt.
2. `acme.feature.enabled=true`.
3. Ứng dụng chưa cung cấp `FeatureService`.

### 6.1. API: `FeatureService.java`

```java
package demo.api;

public interface FeatureService {
    String source();
}
```

### 6.2. Default implementation: `DefaultFeatureService.java`

```java
package demo.api;

public final class DefaultFeatureService implements FeatureService {

    @Override
    public String source() {
        return "auto";
    }
}
```

### 6.3. Optional marker class: `OptionalClient.java`

Trong project demo, đặt class này ở test source để mô phỏng một thư viện optional có mặt khi test bình thường:

```java
package demo.optional;

public final class OptionalClient {
}
```

Trong thư viện thật, đây sẽ là class thuộc dependency tùy chọn. Production auto-configuration chỉ dùng tên class trong condition, không import hoặc tham chiếu class optional trong chữ ký method.

### 6.4. Auto-configuration: `FeatureAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.DefaultFeatureService;
import demo.api.FeatureService;

import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "demo.optional.OptionalClient")
@ConditionalOnProperty(
        prefix = "acme.feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FeatureService.class)
    DefaultFeatureService defaultFeatureService() {
        return new DefaultFeatureService();
    }
}
```

Ba condition được đặt ở những vị trí có ý nghĩa khác nhau:

- `@ConditionalOnClass` kiểm tra classpath của feature.
- `@ConditionalOnProperty` kiểm tra ý định bật feature của ứng dụng.
- `@ConditionalOnMissingBean` trên bean method cho phép ứng dụng thay implementation mặc định.

Kiểu trả về của method là `DefaultFeatureService`, giúp Spring có thông tin kiểu cụ thể. Condition lại kiểm tra contract `FeatureService`, vì mọi implementation của contract này đều phải khiến default bean nhường chỗ.

Nếu optional API được dùng trực tiếp trong implementation, hãy cô lập các tham chiếu đó trong configuration branch có class-level condition. Ví dụ hiện tại chỉ dùng class marker bằng tên để tập trung vào ma trận condition.

## 7. Bộ test: `FeatureAutoConfigurationMatrixTests.java`

```java
package demo;

import demo.api.DefaultFeatureService;
import demo.api.FeatureService;
import demo.autoconfigure.FeatureAutoConfiguration;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureAutoConfigurationMatrixTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(FeatureAutoConfiguration.class)
                    );

    @Test
    void createsDefaultWhenOptionalClassAndPropertyArePresent() {
        this.contextRunner
                .withPropertyValues("acme.feature.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(context.getBean(FeatureService.class).source())
                            .isEqualTo("auto");
                    assertThat(context.getBeansOfType(DefaultFeatureService.class))
                            .hasSize(1);
                });
    }

    @Test
    void missingPropertyLeavesFeatureDisabled() {
        this.contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context.getBeansOfType(FeatureService.class)).isEmpty();
        });
    }

    @Test
    void explicitFalseLeavesFeatureDisabled() {
        this.contextRunner
                .withPropertyValues("acme.feature.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(FeatureService.class))
                            .isEmpty();
                });
    }

    @Test
    void missingOptionalClassDisablesFeatureWithoutLinkageFailure() {
        this.contextRunner
                .withClassLoader(new FilteredClassLoader("demo.optional"))
                .withPropertyValues("acme.feature.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(FeatureService.class))
                            .isEmpty();
                });
    }

    @Test
    void userServiceMakesAutoConfigurationBackOff() {
        this.contextRunner
                .withPropertyValues("acme.feature.enabled=true")
                .withUserConfiguration(UserFeatureConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(context.getBean(FeatureService.class).source())
                            .isEqualTo("user");
                    assertThat(context.getBeansOfType(DefaultFeatureService.class))
                            .isEmpty();
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFeatureConfiguration {

        @Bean
        CustomFeatureService customFeatureService() {
            return new CustomFeatureService();
        }
    }

    static class CustomFeatureService implements FeatureService {

        @Override
        public String source() {
            return "user";
        }
    }
}
```

Chú ý import `AutoConfigurations` và cách tạo runner. `FeatureAutoConfiguration` được đưa vào dưới dạng auto-configuration, còn `UserFeatureConfiguration` được thêm bằng `withUserConfiguration`. Đây là cách mô phỏng thứ tự user bean có mặt trước khi auto-configuration đánh giá `@ConditionalOnMissingBean`.

### 7.1. Ma trận expected result

| Test case | Optional class | Property | User `FeatureService` | Kết quả |
| --- | --- | --- | --- | --- |
| Default path | Có | `true` | Không | Có đúng một default service |
| Property missing | Có | Không khai báo | Không | Không có service |
| Property disabled | Có | `false` | Không | Không có service |
| Optional dependency absent | Không | `true` | Không | Context vẫn chạy, không có service |
| User override | Có | `true` | Có | Chỉ có user service, default back off |

Bộ test có năm phương thức. Khi chạy trên mỗi profile, tất cả năm tình huống phải giữ nguyên expected result nếu thư viện công bố cùng contract cho các dòng Boot đó.

### 7.2. Kết quả test mong đợi

Maven Surefire sẽ báo năm test được chạy và không có lỗi:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Tên thư mục report thường là:

```text
target/surefire-reports/
```

Có thể đọc XML report để xác nhận test nào chạy trong từng profile. Không chỉ nhìn dòng `BUILD SUCCESS`: hãy kiểm tra số test và bảo đảm không có test bị skip ngoài dự kiến.

## 8. Đưa ma trận vào CI

Chạy ba lệnh thủ công hữu ích khi phát triển. Trong CI, có thể khai báo matrix để mỗi profile chạy thành một job độc lập.

Ví dụ GitHub Actions:

```yaml
name: Spring Boot compatibility

on:
  push:
  pull_request:

jobs:
  condition-matrix:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        boot-profile:
          - boot-2.6
          - boot-2.7
          - boot-3.3

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Run condition and back-off tests
        run: mvn -B -P${{ matrix.boot-profile }} clean verify
```

`fail-fast: false` cho phép các baseline còn lại tiếp tục chạy khi một job thất bại. Điều đó giúp xem lỗi chỉ xuất hiện trên một dòng Boot hay xuất hiện trên tất cả.

Nếu build cần Java khác nhau theo dòng Boot, thêm chiều `java-version` và chỉ định các cặp hợp lệ. Đừng đưa một tổ hợp JDK/Boot không được hỗ trợ vào matrix rồi coi lỗi môi trường là lỗi condition.

## 9. Kiểm tra thứ tự auto-configuration khi dùng bean conditions

Một tình huống khác dễ thay đổi theo cấu trúc project là auto-configuration A phụ thuộc bean do auto-configuration B tạo:

```java
@Configuration(proxyBeanMethods = false)
class TransportAutoConfiguration {

    @Bean
    Transport transport() {
        return new DefaultTransport();
    }
}
```

Auto-configuration phụ thuộc:

```java
@Configuration(proxyBeanMethods = false)
@AutoConfigureAfter(TransportAutoConfiguration.class)
@ConditionalOnBean(Transport.class)
class TransportClientAutoConfiguration {

    @Bean
    TransportClient transportClient(Transport transport) {
        return new TransportClient(transport);
    }
}
```

`@ConditionalOnBean` chỉ nhìn thấy bean definitions đã được xử lý tại thời điểm condition chạy. Nếu client configuration được áp dụng trước configuration tạo `Transport`, condition có thể no-match dù bean sẽ được tạo ở bước sau.

Vì vậy:

- Dùng `@AutoConfigureAfter` hoặc `@AutoConfigureBefore` khi có quan hệ phụ thuộc giữa các auto-configuration.
- Test cả trường hợp prerequisite có mặt và vắng mặt.
- Đưa cả hai auto-configuration vào `AutoConfigurations.of(...)` để test ordering theo cơ chế Spring Boot.
- Không dựa vào thứ tự dòng trong file imports hoặc thứ tự khai báo tình cờ.

Ví dụ test ordering:

```java
private final ApplicationContextRunner orderedRunner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        TransportAutoConfiguration.class,
                        TransportClientAutoConfiguration.class
                ));
```

Nếu thứ tự là một phần của contract, hãy assert `TransportClient` có hoặc không theo trạng thái prerequisite. Không chỉ assert context khởi động thành công.

## 10. Kiểm tra back-off ở nhiều cấp

`@ConditionalOnMissingBean` thường được dùng để cho phép người dùng thay default bean. Cần xác định chính xác contract mà condition đang kiểm tra:

- Theo **type**: bất kỳ bean nào tương thích với type được chỉ định đều khiến default nhường chỗ.
- Theo **name**: chỉ bean có tên được chỉ định mới khiến condition no-match.
- Theo **annotation**: bean mang annotation phù hợp có thể tham gia quyết định.
- Theo **context hierarchy**: `search` quyết định có xét bean từ parent context hay không.

Nếu ứng dụng dùng parent/child context, hãy viết test riêng cho hierarchy thay vì suy luận từ test một context. Nếu condition cần bỏ qua một số implementation, kiểm tra thuộc tính `ignored` có phù hợp hay không.

Không nên chỉ kiểm tra rằng user bean tồn tại. Hãy kiểm tra thêm:

1. Có đúng một bean theo contract mà consumer yêu cầu không?
2. Bean được inject có phải user implementation không?
3. Default bean có thực sự không được đăng ký không?
4. Các bean khác không liên quan có còn tồn tại không?
5. Context có bị lỗi ambiguity vì ứng dụng cung cấp nhiều candidate không?

Một test back-off tốt kiểm tra identity hoặc hành vi của bean, không chỉ kiểm tra tên.

## 11. Phân biệt test condition với test registration

Ví dụ trên dùng:

```java
AutoConfigurations.of(FeatureAutoConfiguration.class)
```

Nó trực tiếp chỉ định class cần test. Điều đó rất phù hợp để kiểm tra condition và back-off, nhưng không chứng minh file đăng ký auto-configuration đã được đặt đúng hoặc được đóng gói vào JAR.

Với mỗi module phát hành, nên có thêm một integration test consumer:

- Ứng dụng test bật `@EnableAutoConfiguration` hoặc `@SpringBootApplication`.
- Không import trực tiếp auto-configuration class.
- Consumer chỉ thêm dependency của artifact cần kiểm tra.
- Assert default bean xuất hiện hoặc back off theo cấu hình.
- Kiểm tra JAR chứa registration resource đúng định dạng của dòng Boot đó.

Boot 2.6 dùng cơ chế registration cũ qua `spring.factories`; Boot 2.7 hỗ trợ giai đoạn chuyển tiếp; Boot 3 dùng `AutoConfiguration.imports`. Đây là một chiều tương thích khác với condition semantics. Không dùng kết quả của `AutoConfigurations.of(...)` để kết luận resource discovery đã đúng.

Nếu thư viện hỗ trợ nhiều dòng Boot nhưng dùng source hoặc artifact khác nhau, mỗi consumer test phải lấy đúng artifact và dependency graph của baseline tương ứng.

## 12. Đọc Condition Evaluation Report khi test thất bại

Khi một bean không xuất hiện như mong đợi, cần xác định condition nào no-match. Không nên sửa annotation ngay chỉ dựa trên việc bean không tồn tại.

Trong ứng dụng, chạy với:

```bash
java -jar app.jar --debug
```

Hoặc đặt:

```properties
debug=true
```

Spring Boot sẽ ghi Condition Evaluation Report, cho biết auto-configuration nào match và vì sao một số condition không match.

Nếu ứng dụng có Actuator và expose endpoint phù hợp, endpoint `conditions` cung cấp báo cáo condition ở dạng JSON. Hãy bảo vệ endpoint này theo chính sách vận hành của ứng dụng.

Trong test, có thể thêm `ConditionEvaluationReportLoggingListener` vào runner để ghi báo cáo ở mức log mong muốn. Chỉ dùng log để chẩn đoán; assertion trong test vẫn phải xác nhận expected bean và hành vi.

Các câu hỏi chẩn đoán:

- Class optional có thật sự visible qua classloader của context không?
- Property có đúng key, đúng profile và đúng giá trị không?
- `matchIfMissing` có làm feature bật khi thiếu property không?
- User bean có được đăng ký trước auto-configuration không?
- Bean method có return type đủ cụ thể để condition nhận diện không?
- Một auto-configuration prerequisite có chạy trước configuration đang kiểm tra `@ConditionalOnBean` không?
- Condition có đang xét parent context hoặc bean name khác với giả định không?

## 13. Khi một phiên bản trong matrix thất bại

Không sửa expected result ngay để làm CI xanh. Hãy phân loại nguyên nhân:

| Dấu hiệu | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Chỉ Boot 2.6 compile fail | Source dùng API chỉ có từ Boot 2.7 hoặc 3 | Dùng API chung, tách source/artifact theo baseline hoặc điều chỉnh phạm vi hỗ trợ |
| Chỉ Boot 3 fail khi khởi động | Java baseline, Spring Framework 6, dependency hoặc reflection khác | Đọc root cause và kiểm tra dependency alignment |
| Context không tạo default bean | Property/class condition no-match | Đọc Condition Evaluation Report và xác nhận test inputs |
| Default vẫn xuất hiện dù user bean có mặt | User config chưa được xử lý trước auto-config hoặc condition kiểm tra sai type/name | Dùng `AutoConfigurations.of`, sửa ordering/return type/condition |
| Optional class thiếu gây linkage error | Optional type bị tham chiếu ngoài nhánh được bảo vệ | Cô lập class condition và các tham chiếu optional |
| Chỉ test có classpath đầy đủ mới pass | Chưa test optional dependency absent | Dùng `FilteredClassLoader` hoặc consumer module thiếu dependency |
| Một auto-config phụ thuộc bean khác nhưng no-match | Ordering không đúng | Dùng `@AutoConfigureAfter`/`@AutoConfigureBefore` và test cả hai trạng thái |
| Bean xuất hiện hai lần | Auto-config bị import/scan trùng hoặc condition không back off | Kiểm tra registration, component scan và bean condition |

Một lỗi chỉ xuất hiện trên một baseline có thể là regression thật, nhưng cũng có thể do profile đang kéo sai version hoặc JDK không phù hợp. Trước khi thay implementation, xác nhận dependency tree và Surefire report của job thất bại.

## 14. Những lỗi thường gặp khi xây dựng version matrix

**Lỗi 1 — Chạy cùng một test suite nhưng dependency không được đổi theo profile.**  
Nếu test vẫn dùng một version Spring Boot cố định, matrix chỉ tạo nhiều job có cùng classpath. Dùng BOM hoặc dependency management được profile điều khiển và kiểm tra dependency tree.

**Lỗi 2 — Dùng nhiều profile cùng lúc.**  
Các profile cùng ghi đè `spring-boot.version`, làm kết quả phụ thuộc thứ tự/profile activation. Mỗi job chỉ bật một profile.

**Lỗi 3 — Dùng `@AutoConfiguration` trong source phải compile trên Boot 2.6.**  
Annotation này không có trong Boot 2.6. Nếu cần cùng source cho cả ba baseline, dùng annotation chung như `@Configuration(proxyBeanMethods = false)` hoặc tách artifact/source theo phiên bản.

**Lỗi 4 — Test user bean và auto-configuration như hai configuration thông thường.**  
`@ConditionalOnMissingBean` dựa trên bean definitions đã xử lý. Dùng `AutoConfigurations.of(...)` cho auto-configuration và `withUserConfiguration(...)` cho user config để test đúng back-off order.

**Lỗi 5 — Chỉ assert context không lỗi.**  
Context có thể khởi động nhưng default bean biến mất hoặc user bean không được chọn. Assert bean count, implementation và behavior thực tế.

**Lỗi 6 — Không kiểm tra optional class vắng mặt.**  
Classpath phát triển có đủ dependency nên lỗi class loading bị che. Dùng `FilteredClassLoader` để mô phỏng consumer thật.

**Lỗi 7 — Dùng test logic để kết luận registration resource đúng.**  
`AutoConfigurations.of(...)` truyền class trực tiếp. Thêm integration test dùng `@EnableAutoConfiguration` và kiểm tra artifact cuối.

**Lỗi 8 — Cho rằng `@ConditionalOnMissingBean` nhìn thấy mọi bean trong tương lai.**  
Condition chỉ xét bean definitions đã được xử lý. Dùng auto-configuration ordering và kiểm tra return type.

**Lỗi 9 — Không chạy `clean` giữa các baseline.**  
Output cũ có thể còn sót trong thư mục build. Chạy `clean verify` cho mỗi profile và tránh dùng chung thư mục output giữa các build song song.

**Lỗi 10 — Chỉ chạy phiên bản mới nhất.**  
Điều đó không phát hiện regression trên baseline thấp nhất mà thư viện vẫn công bố hỗ trợ. CI phải bao phủ ít nhất lowest supported version và các mốc chuyển đổi có rủi ro.

**Lỗi 11 — Sửa test expected theo implementation mới mà không xem lại contract.**  
Một condition no-match có thể là bug, không phải thay đổi được chấp nhận. Chỉ thay expected result khi contract sản phẩm thực sự thay đổi và có lý do tương thích rõ ràng.

## 15. Checklist trước khi phát hành

- [ ] Công bố rõ các dòng Spring Boot được hỗ trợ.
- [ ] Chọn JDK tương thích cho từng baseline.
- [ ] Dependency graph của mỗi job dùng đúng một Spring Boot BOM.
- [ ] Chạy `clean verify` riêng cho từng profile.
- [ ] Test property missing, false và true theo contract.
- [ ] Test optional class present và absent.
- [ ] Test default bean được tạo khi không có user bean.
- [ ] Test user bean khiến default back off.
- [ ] Test `@ConditionalOnBean` và ordering nếu auto-configuration có phụ thuộc bean khác.
- [ ] Test parent/child context nếu condition dùng context hierarchy.
- [ ] Assert bean identity/type/behavior, không chỉ assert context started.
- [ ] Đọc Condition Evaluation Report khi có no-match bất ngờ.
- [ ] Test registration resource và packaged artifact riêng với condition tests.
- [ ] Lưu report của từng baseline để so sánh khi nâng Boot version.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao một test pass trên Boot 3 không đủ chứng minh thư viện tương thích Boot 2.6?  
**Đáp án:** Mỗi dòng Boot mang dependency, Spring Framework và condition processing tương ứng. Chỉ chạy test trên dependency graph của Boot 3 không kiểm tra bytecode/API và runtime behavior của Boot 2.6.

**Câu 2.** Vì sao cần dùng một Spring Boot BOM cho mỗi job?  
**Đáp án:** BOM căn chỉnh các dependency Spring Boot/Spring Framework/test theo cùng baseline. Nếu trộn version, kết quả không đại diện cho một bản Boot thực tế.

**Câu 3.** `ApplicationContextRunner` giúp kiểm tra những gì?  
**Đáp án:** Tạo context nhỏ với property, user configuration, classloader và các auto-configuration được chỉ định để kiểm tra condition và bean behavior độc lập.

**Câu 4.** Vì sao test back-off dùng `AutoConfigurations.of(...)`?  
**Đáp án:** Nó đưa class vào luồng auto-configuration, giúp user bean được xử lý trước điều kiện `@ConditionalOnMissingBean` theo thứ tự mà Spring Boot sử dụng.

**Câu 5.** Khi optional class vắng mặt, cần assert điều gì?  
**Đáp án:** Condition no-match, bean tùy chọn không tồn tại và context không thất bại do `NoClassDefFoundError` hoặc lỗi linkage.

**Câu 6.** `@ConditionalOnProperty` nên kiểm tra các trường hợp nào?  
**Đáp án:** Property thiếu, explicit false và true; expected result phụ thuộc `havingValue` và `matchIfMissing` đã khai báo.

**Câu 7.** Vì sao `@ConditionalOnMissingBean` có thể không back off nếu test đăng ký cấu hình sai thứ tự?  
**Đáp án:** Condition chỉ thấy bean definitions đã xử lý. Nếu user bean chưa được đăng ký khi condition chạy, default có thể vẫn được tạo.

**Câu 8.** Test `AutoConfigurations.of(MyAutoConfiguration.class)` có xác nhận resource registration trong JAR không?  
**Đáp án:** Không. Nó truyền class trực tiếp. Cần integration test qua `@EnableAutoConfiguration` và kiểm tra JAR đã đóng gói.

**Câu 9.** Khi chỉ Boot 2.6 compile fail vì `@AutoConfiguration`, có thể xử lý thế nào?  
**Đáp án:** Dùng annotation tương thích chung như `@Configuration(proxyBeanMethods = false)`, hoặc tách artifact/source cho baseline khác nhau.

**Câu 10.** Vì sao phải assert bean thực tế được dùng thay vì chỉ assert context không lỗi?  
**Đáp án:** Context có thể khởi động nhưng chọn sai implementation, tạo default ngoài ý muốn hoặc không tạo bean cần thiết. Assertion phải kiểm tra contract runtime.

## 17. Nguyên tắc cần nhớ

- Một bộ test condition phải chạy trên từng Spring Boot baseline mà thư viện cam kết hỗ trợ.
- Dùng một BOM nhất quán cho mỗi job; không trộn dependency giữa các dòng Boot.
- `ApplicationContextRunner` kiểm tra property, classpath, user configuration và bean behavior trong context nhỏ.
- `FilteredClassLoader` phát hiện lỗi khi optional dependency không có mặt.
- `AutoConfigurations.of(...)` và `withUserConfiguration(...)` giúp kiểm tra đúng hành vi back-off của user bean.
- `@ConditionalOnMissingBean` chỉ xét bean definitions đã được xử lý; ordering và kiểu trả về của `@Bean` rất quan trọng.
- Kiểm tra property missing/false/true, class present/absent và user override theo contract.
- Condition tests không thay thế integration test registration và packaged JAR.
- Condition Evaluation Report giúp giải thích match/no-match; assertion mới xác nhận behavior.
- Không đổi expected result chỉ để làm ma trận xanh; hãy đối chiếu contract và nguyên nhân khác biệt trước.

### Tài liệu tham khảo chính thức

- [Spring Boot 2.6.15 — Creating Your Own Auto-configuration and Testing](https://docs.spring.io/spring-boot/docs/2.6.15/reference/htmlsingle/#features.developing-auto-configuration)
- [Spring Boot 2.7.18 — Testing Your Auto-configuration](https://docs.spring.io/spring-boot/docs/2.7.18/reference/htmlsingle/#features.developing-auto-configuration.testing)
- [Spring Boot 3.3.13 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3.13 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/)
- [Spring Boot 2.6.15 API — `@ConditionalOnMissingBean`](https://docs.spring.io/spring-boot/docs/2.6.15/api/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 2.7.18 API — `ApplicationContextRunner`](https://docs.spring.io/spring-boot/docs/2.7.18/api/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
