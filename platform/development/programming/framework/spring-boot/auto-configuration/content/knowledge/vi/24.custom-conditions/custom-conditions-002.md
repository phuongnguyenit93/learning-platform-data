# Triển khai Condition với dữ liệu đầu vào xác định và không có tác dụng phụ

## 1. Mục tiêu và vấn đề cần giải quyết

Spring cho phép bạn tự định nghĩa điều kiện để quyết định một class cấu hình hoặc một method `@Bean` có đủ điều kiện được đăng ký hay không. Cơ chế này hữu ích khi các annotation condition có sẵn như `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean` hoặc `@ConditionalOnWebApplication` chưa diễn đạt được quy tắc nghiệp vụ của thư viện.

Một custom condition chạy rất sớm trong vòng đời khởi tạo ApplicationContext. Nếu nó tạo bean, gọi dịch vụ bên ngoài, thay đổi registry, đọc thời gian hiện tại hoặc dựa vào trạng thái mutable, kết quả có thể khó lặp lại và làm hỏng quá trình khởi động.

Bài học này tập trung vào Spring Boot **3.3.13**, Spring Framework 6.1 và Java 17+. Mục tiêu là triển khai một `Condition` có các đặc điểm:

- **Input xác định:** dữ liệu đầu vào đến từ annotation metadata và `Environment` của context.
- **Kết quả thuần:** cùng metadata và cùng giá trị property luôn cho cùng một kết quả boolean.
- **Không có tác dụng phụ:** không tạo bean, không gọi `getBean()`, không ghi file, gọi mạng, truy cập database, thay đổi Environment hoặc đăng ký bean definition.
- **Có thể kiểm thử:** mỗi test tự khai báo property, không phụ thuộc máy chạy, thời điểm hoặc trạng thái của test khác.
- **Dễ chẩn đoán:** biết cách kết hợp custom condition với condition report khi phát triển auto-configuration.

Ví dụ xuyên suốt là một thư viện chỉ bật `RegionFeature` khi property `acme.region` khớp với vùng được ghi trong annotation `@ConditionalOnRegion`.

## 2. Condition là gì và chạy ở giai đoạn nào?

`org.springframework.context.annotation.Condition` là một SPI của Spring Framework. Một condition quyết định component có đủ điều kiện được đăng ký hay không.

Chữ ký chính:

~~~java
boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
);
~~~

Hai tham số cung cấp hai nhóm dữ liệu khác nhau:

| Tham số | Cung cấp | Dùng để làm gì? |
| --- | --- | --- |
| `ConditionContext` | Environment, BeanDefinitionRegistry, BeanFactory nếu có, ResourceLoader và ClassLoader | Đọc property, kiểm tra class/resource hoặc thông tin đăng ký cần thiết |
| `AnnotatedTypeMetadata` | Metadata annotation của class hoặc method đang được xét | Đọc thuộc tính của annotation, kể cả annotation tổng hợp |

Spring kiểm tra condition **ngay trước khi bean definition tương ứng được đăng ký**. Condition có thể cho phép hoặc từ chối đăng ký dựa trên những thông tin có thể xác định ở thời điểm đó.

Điều này có nghĩa `Condition` không phải callback chạy sau khi ứng dụng đã tạo đầy đủ bean. Khi `matches()` được gọi, nhiều bean có thể chưa tồn tại dưới dạng instance.

### 2.1. Condition khác với BeanFactoryPostProcessor và BeanPostProcessor

| Thành phần | Thời điểm và nhiệm vụ |
| --- | --- |
| `Condition` | Đánh giá một điều kiện trước khi component/bean definition được đăng ký |
| `BeanFactoryPostProcessor` | Làm việc với bean definitions và metadata của BeanFactory trước khi tạo bean thông thường |
| `BeanPostProcessor` | Can thiệp vào bean instance trong quá trình khởi tạo |

Spring yêu cầu `Condition` tuân theo các giới hạn tương tự `BeanFactoryPostProcessor`, đặc biệt **không được tương tác với bean instances**. Việc gọi `getBean()` từ condition có thể khiến bean được khởi tạo quá sớm, bỏ qua một phần lifecycle hoặc post-processing và tạo ra phụ thuộc khó kiểm soát.

Vì vậy, hãy xem `Condition` là một phép tính dựa trên metadata/context, không phải nơi thực hiện công việc nghiệp vụ.

### 2.2. @Conditional có thể đặt ở đâu?

`@Conditional` có thể được dùng:

- Trực tiếp trên class cấu hình.
- Trên method `@Bean`.
- Là meta-annotation của annotation tùy chỉnh.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(InternalRegionCondition.class)
class InternalConfiguration {
    // Các bean trong cấu hình này chỉ được đăng ký khi condition khớp.
}
~~~

Nếu đặt trên class cấu hình, các `@Bean`, `@Import` và `@ComponentScan` liên quan đến class đó đều chịu điều kiện. Nếu đặt trên method `@Bean`, điều kiện áp dụng cho bean definition do method đó cung cấp.

Các condition trên cùng class hoặc method được sắp xếp theo quy tắc `Ordered` và `@Order`. Tuy vậy, nên thiết kế mỗi condition độc lập, không dựa vào tác dụng phụ của condition chạy trước.

## 3. Thế nào là input xác định và condition không có tác dụng phụ?

Một condition tốt có thể mô tả như một hàm:

~~~text
result = matches(annotationMetadata, environmentSnapshot)
~~~

Nếu hai lần đánh giá có cùng metadata và cùng giá trị property thì kết quả phải giống nhau.

### 3.1. Nguồn input nên dùng

Các nguồn input phù hợp thường gồm:

- Thuộc tính annotation được khai báo rõ, ví dụ `@ConditionalOnRegion("internal")`.
- Property đã có trong `Environment`, ví dụ `acme.region=internal`.
- Sự hiện diện của class thông qua ClassLoader.
- Sự hiện diện của resource thông qua ResourceLoader.
- Bean definition metadata khi thật sự cần kiểm tra cấu trúc đăng ký và đã chọn đúng configuration phase.

Các giá trị này thuộc về context đang được khởi tạo. Test có thể cung cấp chúng tường minh để tái tạo cùng một tình huống.

### 3.2. Những nguồn làm kết quả khó xác định

Tránh đưa những yếu tố sau vào `matches()`:

| Nguồn | Vì sao gây khó kiểm soát? | Hướng xử lý |
| --- | --- | --- |
| `System.currentTimeMillis()` hoặc `LocalDateTime.now()` | Kết quả đổi theo thời điểm đánh giá | Đưa thời điểm thành property/input đã cố định nếu nghiệp vụ thực sự cần |
| `new Random()` hoặc `UUID.randomUUID()` | Cùng cấu hình nhưng có thể cho kết quả khác | Không dùng ngẫu nhiên để quyết định bean registration |
| HTTP, database, message broker | Phụ thuộc mạng, dịch vụ, timeout và trạng thái bên ngoài | Đưa việc kiểm tra vào bean/service sau khi context đã được tạo |
| Đọc file tùy ý trên máy | Phụ thuộc working directory, quyền truy cập và nội dung file | Dùng property hoặc resource condition có chủ đích |
| `System.getenv()` trực tiếp | Khó cô lập trong test và phụ thuộc máy chạy | Đọc property qua Spring `Environment` để test có thể ghi đè |
| Static mutable state | Kết quả phụ thuộc thứ tự test/context trước | Dùng biến cục bộ bất biến và input của context |
| `getBean()` | Có thể khởi tạo bean trước lifecycle bình thường | Chỉ đọc metadata/definition cần thiết, không lấy bean instance |
| Ghi registry hoặc sửa Environment | Condition làm thay đổi chính dữ liệu mà các condition khác đang đánh giá | Chỉ đọc context và trả boolean |

Không phải mọi thao tác đọc đều là tác dụng phụ. Đọc `Environment`, annotation metadata hoặc classpath là cách dùng bình thường. Vấn đề nằm ở việc condition thay đổi trạng thái, tạo tương tác bên ngoài hoặc phụ thuộc vào input không được kiểm soát.

### 3.3. Tính thuần và tính lặp lại

Hãy giữ implementation theo các nguyên tắc:

1. Dùng biến cục bộ cho giá trị trung gian.
2. Không lưu kết quả vào static field hoặc cache mutable.
3. Không thay đổi đối tượng được truyền qua `ConditionContext`.
4. Không giả định `matches()` chỉ được gọi đúng một lần.
5. Không phụ thuộc thứ tự các test hoặc context khác.
6. Xử lý property thiếu một cách rõ ràng.
7. Quy định rõ so sánh phân biệt hoa/thường, khoảng trắng và giá trị mặc định.

Trong ví dụ dưới đây, phép so sánh là **exact match, phân biệt hoa/thường**. `internal` khớp với `internal`; `Internal`, `internal ` và property bị thiếu đều không khớp. Quy tắc đơn giản này giúp test và hành vi dễ dự đoán.

## 4. Chọn API có sẵn trước khi viết custom Condition

Không phải mọi điều kiện đều cần tự triển khai. Spring Boot đã có nhiều condition tiêu chuẩn:

| Nhu cầu | API nên ưu tiên |
| --- | --- |
| Class có/không có trên classpath | `@ConditionalOnClass`, `@ConditionalOnMissingClass` |
| Property có giá trị cụ thể | `@ConditionalOnProperty` |
| Bean có/không tồn tại | `@ConditionalOnBean`, `@ConditionalOnMissingBean` |
| Một candidate có thể autowire | `@ConditionalOnSingleCandidate` |
| Resource tồn tại | `@ConditionalOnResource` |
| Context Servlet/Reactive | `@ConditionalOnWebApplication`, `@ConditionalOnNotWebApplication` |
| Điều kiện nghiệp vụ riêng kết hợp metadata/property theo quy tắc riêng | Custom `Condition` |

Custom condition phù hợp khi quy tắc cần đọc thuộc tính của annotation, kết hợp nhiều giá trị hoặc áp dụng một phép so sánh domain-specific mà annotation có sẵn không biểu diễn rõ.

Nếu chỉ cần kiểm tra `acme.feature.enabled=true`, hãy dùng `@ConditionalOnProperty`. Tự viết condition cho cùng một việc làm tăng mã cần bảo trì mà không mang lại giá trị.

## 5. Thiết kế annotation tùy chỉnh với input rõ ràng

Ta muốn người dùng viết:

~~~java
@ConditionalOnRegion("internal")
@AutoConfiguration
public class InternalRegionAutoConfiguration {
    // Bean dành cho region internal.
}
~~~

Annotation mang giá trị kỳ vọng. Property `acme.region` trong `Environment` mang giá trị thực tế. Condition chỉ so sánh hai giá trị này.

### 5.1. Annotation ConditionalOnRegion

File `src/main/java/demo/condition/ConditionalOnRegion.java`:

~~~java
package demo.condition;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(RegionCondition.class)
public @interface ConditionalOnRegion {

    String value();
}
~~~

Giải thích:

- `@Target(TYPE, METHOD)` cho phép dùng annotation trên class hoặc method.
- `@Retention(RUNTIME)` để Spring đọc được annotation khi xử lý cấu hình.
- `@Conditional(RegionCondition.class)` liên kết annotation với implementation.
- `value()` là input tường minh do người viết cấu hình cung cấp.

Annotation tổng hợp này không cần `@Component`. Nó chỉ mô tả một điều kiện có thể áp dụng lên component hoặc bean method.

**Lưu ý về kế thừa:** `@Conditional` không được khai báo `@Inherited`; annotation tùy chỉnh meta-annotated bằng `@Conditional` cũng không nên thêm `@Inherited`. Nếu cần áp dụng điều kiện, hãy đặt annotation trực tiếp lên class/method tương ứng.

## 6. Triển khai RegionCondition thuần và không có tác dụng phụ

File `src/main/java/demo/condition/RegionCondition.java`:

~~~java
package demo.condition;

import java.util.Map;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class RegionCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        Map<String, Object> attributes =
            metadata.getAnnotationAttributes(
                ConditionalOnRegion.class.getName()
            );

        if (attributes == null) {
            return false;
        }

        String expectedRegion = (String) attributes.get("value");
        String actualRegion =
            context.getEnvironment().getProperty("acme.region");

        return expectedRegion.equals(actualRegion);
    }
}
~~~

### 6.1. Phân tích từng bước

**Bước 1 — Đọc annotation metadata**

~~~java
Map<String, Object> attributes =
    metadata.getAnnotationAttributes(
        ConditionalOnRegion.class.getName()
    );
~~~

`AnnotatedTypeMetadata` cung cấp thuộc tính của annotation trên class hoặc method đang được xét. API này cũng đọc được thuộc tính của annotation tổng hợp (meta-annotation hierarchy) và hỗ trợ `@AliasFor` theo cơ chế merged annotations.

Nếu annotation không tồn tại trên metadata đang xét, implementation trả `false`. Với cách sử dụng đúng, condition được gọi thông qua `@ConditionalOnRegion` nên thuộc tính sẽ có mặt; nhánh null vẫn giúp xử lý an toàn.

**Bước 2 — Lấy giá trị kỳ vọng**

~~~java
String expectedRegion = (String) attributes.get("value");
~~~

Đây là input khai báo tĩnh trên annotation. Ví dụ `@ConditionalOnRegion("internal")` cho giá trị kỳ vọng là `internal`.

**Bước 3 — Đọc giá trị thực tế từ Environment**

~~~java
String actualRegion =
    context.getEnvironment().getProperty("acme.region");
~~~

`ConditionContext` cung cấp `Environment` của context hiện tại. Property được giải quyết theo thứ tự các property sources đã cấu hình trong Spring.

Trong test, ta có thể đặt property bằng `ApplicationContextRunner.withPropertyValues(...)`. Không cần đọc biến môi trường của hệ điều hành trực tiếp.

**Bước 4 — So sánh và trả kết quả**

~~~java
return expectedRegion.equals(actualRegion);
~~~

`String.equals` thực hiện so sánh chính xác và trả `false` nếu `actualRegion` là `null`. Condition chỉ trả boolean; Spring chịu trách nhiệm quyết định component/bean definition có được đăng ký hay không.

### 6.2. Vì sao implementation này không có tác dụng phụ?

Trong `matches()`:

- Không tạo hoặc lấy bean instance.
- Không sửa Environment hay BeanDefinitionRegistry.
- Không ghi file hoặc gọi network/database.
- Không đọc đồng hồ hoặc random.
- Không ghi trạng thái vào static field.
- Không thay đổi annotation metadata.
- Chỉ đọc hai giá trị và trả kết quả so sánh.

Do đó, cùng `@ConditionalOnRegion("internal")` và cùng `Environment` sẽ luôn tạo cùng kết quả. Condition cũng có thể được đánh giá lại trong context khác mà không mang theo trạng thái từ lần trước.

### 6.3. Không inject dependency như một bean thông thường

Không thiết kế condition theo kiểu:

~~~java
// Không nên dùng cách tiếp cận này trong Condition.
@Autowired
private RegionService regionService;
~~~

Condition được framework dùng trong giai đoạn xử lý đăng ký bean definition. Đây không phải nơi để yêu cầu Spring khởi tạo service rồi inject vào condition. Hãy lấy dữ liệu qua `ConditionContext` và `AnnotatedTypeMetadata`.

Nếu cần một service thực hiện logic phức tạp, hãy tạo bean/service sau khi context đã được tạo và để service đó thực hiện công việc ở runtime.

## 7. Dùng custom condition trong auto-configuration

File `src/main/java/demo/condition/RegionFeature.java`:

~~~java
package demo.condition;

public record RegionFeature(String region) {
}
~~~

File `src/main/java/demo/condition/RegionAutoConfiguration.java`:

~~~java
package demo.condition;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnRegion("internal")
public class RegionAutoConfiguration {

    @Bean
    public RegionFeature regionFeature() {
        return new RegionFeature("internal");
    }
}
~~~

Khi property `acme.region=internal`, class auto-configuration đủ điều kiện và bean `RegionFeature` được đăng ký. Khi property là `public` hoặc không tồn tại, class cấu hình bị condition veto và bean không được đăng ký.

### 7.1. Đăng ký auto-configuration trong JAR

Nếu thư viện được phát hành thành JAR để ứng dụng khác sử dụng, thêm file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
demo.condition.RegionAutoConfiguration
~~~

Imports file đăng ký auto-configuration candidate. Custom condition tiếp tục quyết định candidate đó có được áp dụng trong context hiện tại hay không.

Trong ví dụ test bên dưới, `AutoConfigurations.of(RegionAutoConfiguration.class)` đưa class trực tiếp vào runner để kiểm thử condition độc lập. Khi đóng gói thư viện thực tế, consumer Spring Boot sẽ phát hiện class qua imports file.

### 7.2. Condition trên class hay method?

Dùng trên class khi toàn bộ auto-configuration chỉ phù hợp với một input:

~~~java
@AutoConfiguration
@ConditionalOnRegion("internal")
public class InternalRegionAutoConfiguration {
    // Tất cả bean trong class phụ thuộc cùng một condition.
}
~~~

Dùng trên bean method khi chỉ một bean cần điều kiện đó:

~~~java
@AutoConfiguration
public class RegionAwareAutoConfiguration {

    @Bean
    @ConditionalOnRegion("internal")
    InternalRegionClient internalRegionClient() {
        return new InternalRegionClient();
    }

    @Bean
    @ConditionalOnRegion("public")
    PublicRegionClient publicRegionClient() {
        return new PublicRegionClient();
    }
}
~~~

Hai class client là kiểu minh họa. Điểm khác biệt là phạm vi điều kiện: class-level veto cả cấu hình; method-level chỉ veto bean definition tương ứng.

## 8. Kiểm thử tính xác định bằng ApplicationContextRunner

Một custom condition cần được kiểm tra với các input có thể tái tạo. Spring Boot cung cấp `ApplicationContextRunner` để tạo context nhỏ, cô lập cho từng kịch bản.

Các test dưới đây kiểm tra:

1. Region khớp chính xác.
2. Region khác giá trị kỳ vọng.
3. Property không được cung cấp.
4. Cùng input được chạy trên hai context độc lập nhưng cho cùng kết quả.

### 8.1. Cấu trúc dự án

~~~text
deterministic-condition-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/condition/
    │   │   ├── ConditionalOnRegion.java
    │   │   ├── RegionCondition.java
    │   │   ├── RegionFeature.java
    │   │   └── RegionAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/demo/condition/RegionConditionTests.java
~~~

### 8.2. File pom.xml

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

    <groupId>demo</groupId>
    <artifactId>deterministic-condition-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
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

### 8.3. File src/test/java/demo/condition/RegionConditionTests.java

~~~java
package demo.condition;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class RegionConditionTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(RegionAutoConfiguration.class)
            );

    @Test
    void matchesWhenRegionIsInternal() {
        this.contextRunner
            .withPropertyValues("acme.region=internal")
            .run(context -> {
                assertThat(context).hasSingleBean(RegionFeature.class);
                assertThat(context.getBean(RegionFeature.class).region())
                    .isEqualTo("internal");
            });
    }

    @Test
    void doesNotMatchWhenRegionIsDifferent() {
        this.contextRunner
            .withPropertyValues("acme.region=public")
            .run(context ->
                assertThat(context).doesNotHaveBean(RegionFeature.class)
            );
    }

    @Test
    void doesNotMatchWhenRegionPropertyIsMissing() {
        this.contextRunner.run(context ->
            assertThat(context).doesNotHaveBean(RegionFeature.class)
        );
    }

    @Test
    void sameInputProducesSameResultAcrossIndependentContexts() {
        for (int attempt = 0; attempt < 2; attempt++) {
            this.contextRunner
                .withPropertyValues("acme.region=internal")
                .run(context -> {
                    assertThat(context).hasSingleBean(RegionFeature.class);
                    assertThat(context.getBean(RegionFeature.class).region())
                        .isEqualTo("internal");
                });
        }
    }
}
~~~

### 8.4. Chạy test

Yêu cầu: JDK 17+, Maven 3.8+ và khả năng tải dependency. Trong thư mục dự án chạy:

~~~bash
mvn clean test
~~~

Bốn test cần đạt các kết quả:

| Test | Input | Kết quả |
| --- | --- | --- |
| `matchesWhenRegionIsInternal` | `acme.region=internal` | Có một `RegionFeature` |
| `doesNotMatchWhenRegionIsDifferent` | `acme.region=public` | Không có `RegionFeature` |
| `doesNotMatchWhenRegionPropertyIsMissing` | Property không được đặt | Không có `RegionFeature` |
| `sameInputProducesSameResultAcrossIndependentContexts` | Hai context đều có `acme.region=internal` | Cả hai context đều có một `RegionFeature` |

Maven Surefire báo bốn test thành công và `BUILD SUCCESS` nếu tất cả assertion đều đúng. Định dạng console và thời gian chạy có thể khác theo Maven/Surefire version; bảng trên mô tả kết quả logic cần kiểm chứng.

### 8.5. Vì sao ApplicationContextRunner phù hợp?

- Mỗi lần gọi `run()` tạo context riêng cho một kịch bản.
- `withPropertyValues()` cung cấp input rõ ràng cho `Environment`.
- `AutoConfigurations.of()` chỉ định chính xác auto-configuration cần test.
- Callback nhận context đã refresh để kiểm tra bean thực tế.
- Context được đóng sau callback, tránh rò rỉ trạng thái giữa các test.

Không cần sửa biến môi trường hệ điều hành hoặc gọi dịch vụ ngoài để test condition.

## 9. ConfigurationCondition: khi nào cần kiểm soát phase?

`Condition` thông thường phù hợp với đa số trường hợp. Nếu điều kiện phụ thuộc vào **thời điểm** đánh giá trong quá trình xử lý cấu hình, Spring Framework có interface chuyên biệt `ConfigurationCondition`.

Interface này cho phép chọn một trong hai phase:

| Phase | Thời điểm |
| --- | --- |
| `PARSE_CONFIGURATION` | Khi Spring đang phân tích cấu hình và các import |
| `REGISTER_BEAN` | Khi Spring đang đăng ký bean definitions |

Ví dụ khung triển khai:

~~~java
public final class ExistingDefinitionCondition
        implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        // Chỉ đọc bean-definition metadata nếu thực sự cần.
        // Không gọi getBean() và không sửa registry.
        return true;
    }
}
~~~

Đây là snippet minh họa, phần kiểm tra thực tế phụ thuộc quy tắc của thư viện.

Dùng `REGISTER_BEAN` khi condition cần đánh giá ở phase đăng ký bean, ví dụ kiểm tra một bean definition đã được đăng ký. Dù ở phase này, condition vẫn không được tương tác với bean instance.

Không dùng `ConfigurationCondition` chỉ vì muốn có thêm một interface. Với ví dụ đọc `Environment` và annotation metadata ở trên, `Condition` thông thường đã đủ.

## 10. Chẩn đoán condition trong Spring Boot

### 10.1. Khi cần message giải thích MATCH/NO MATCH

`Condition.matches()` trả về boolean nên bản thân interface không yêu cầu trả về message. Nếu phát triển custom condition dành riêng cho Spring Boot và muốn diagnostic message nhất quán với condition tích hợp, có thể kế thừa `SpringBootCondition`.

Base class này cung cấp `getMatchOutcome(...)` trả về `ConditionOutcome` cùng thông tin logging. Có thể tạo outcome bằng `ConditionOutcome.match("...")` hoặc `ConditionOutcome.noMatch("...")`.

Ví dụ khung:

~~~java
public final class RegionCondition extends SpringBootCondition {

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        // Tính toán từ annotation metadata và Environment.
        // Không tạo bean hoặc gọi dịch vụ ngoài.

        boolean matched = /* phép so sánh thuần */ true;

        if (matched) {
            return ConditionOutcome.match(
                "acme.region matched the required region"
            );
        }

        return ConditionOutcome.noMatch(
            "acme.region did not match the required region"
        );
    }
}
~~~

Đây là phần minh họa API; trong code thật hãy thay phép so sánh placeholder bằng logic thuần ở mục 6. `SpringBootCondition` có trách nhiệm ghi outcome theo cơ chế logging của Boot. Logic tính toán vẫn cần giữ deterministic và không có tác dụng phụ ngoài diagnostic do base class cung cấp.

Nếu không cần message riêng, dùng `Condition` từ Spring Framework như ví dụ chính là đơn giản nhất.

### 10.2. Condition report

Spring Boot ghi nhận condition outcomes trong `ConditionEvaluationReport`. Khi cần kiểm tra lý do auto-configuration không được áp dụng:

- Chạy ứng dụng với `--debug` để bật báo cáo điều kiện.
- Trong test, dùng `ConditionEvaluationReportLoggingListener` ở mức INFO hoặc DEBUG.
- Nếu cần report qua HTTP và ứng dụng đã cấu hình Actuator phù hợp, xem endpoint `/actuator/conditions`.

Condition report giúp trả lời condition nào matched hoặc no-match. Nó không thay thế assertion về bean thực tế trong test.

## 11. Những lỗi thường gặp và cách sửa

| Lỗi / cách làm sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `context.getBeanFactory().getBean(...)` trong `matches()` | Khởi tạo bean quá sớm, phá vỡ lifecycle/post-processing | Chỉ đọc metadata và Environment; để bean method xử lý dependency |
| Dùng `@Autowired` hoặc `@Value` trong condition | Condition không hoạt động như một bean thông thường được quản lý đầy đủ | Dùng `ConditionContext` và `AnnotatedTypeMetadata` |
| Gọi HTTP/database để quyết định đăng ký bean | Startup phụ thuộc mạng, timeout và dịch vụ bên ngoài | Đưa health check hoặc remote call vào bean/service sau khi context tạo |
| Dùng `LocalDate.now()` hoặc random | Cùng cấu hình có thể cho kết quả khác theo lần đánh giá | Truyền input cố định qua Environment/metadata |
| Đọc `System.getenv()` trực tiếp | Test khó ghi đè và phụ thuộc máy chạy | Dùng `Environment.getProperty()` |
| Ghi static flag để nhớ lần chạy trước | Context/test có thể ảnh hưởng lẫn nhau | Condition không trạng thái; mỗi lần tính từ input hiện tại |
| Sửa `BeanDefinitionRegistry` trong `matches()` | Condition tự thay đổi context đang được đánh giá | Trả boolean; để Spring đăng ký bean definition |
| Sửa Environment hoặc property source | Các condition sau có thể nhìn thấy input đã bị thay đổi | Chỉ đọc Environment |
| Không xử lý property thiếu | Có thể phát sinh NullPointerException | Định nghĩa rõ missing nghĩa là match hay no-match; dùng phép so sánh null-safe |
| Dùng custom Condition cho property boolean đơn giản | Tăng code và khó bảo trì | Ưu tiên `@ConditionalOnProperty` |
| Condition đọc bean definitions ở phase quá sớm | Chưa nhìn thấy definition cần thiết | Cân nhắc `ConfigurationCondition` và phase `REGISTER_BEAN` |
| Condition có logic phụ thuộc thứ tự condition khác | Kết quả khó đoán khi cấu hình thay đổi | Mỗi condition độc lập, chỉ trả kết quả dựa trên input của nó |

## 12. Quy trình thiết kế và review một custom Condition

Trước khi đưa condition vào thư viện, thực hiện các bước:

1. **Mô tả quy tắc bằng một câu:** ví dụ “chỉ đăng ký tính năng khi region trong Environment trùng với region trên annotation”.
2. **Liệt kê input:** annotation attribute nào, property nào, class/resource nào.
3. **Định nghĩa missing/default:** property không tồn tại thì match hay no-match? Có phân biệt chuỗi rỗng không?
4. **Chọn API có sẵn:** nếu condition tiêu chuẩn đã đáp ứng, không viết custom.
5. **Giữ implementation thuần:** không gọi bean instance, I/O, network, clock, random hoặc thay đổi registry/environment.
6. **Chọn phase phù hợp:** dùng `Condition` mặc định; chỉ dùng `ConfigurationCondition` khi thật sự cần kiểm soát phase.
7. **Viết test cho mọi nhánh:** match, no-match, property missing, metadata thiếu và cùng input trên nhiều context.
8. **Kiểm tra bean thực tế:** xác nhận bean có/không có trong `ApplicationContextRunner`, không chỉ gọi `matches()` trực tiếp.
9. **Thêm diagnostic phù hợp:** dùng `SpringBootCondition` nếu cần `ConditionOutcome` và logging.
10. **Ghi tài liệu cho người dùng:** property, giá trị annotation, default, quy tắc so sánh và tình huống bean bị bỏ qua.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `Condition.matches()` được gọi ở giai đoạn nào?  
**Đáp án:** Ngay trước khi component/bean definition tương ứng được đăng ký. Nó có thể cho phép hoặc veto việc đăng ký.

**Câu 2.** Vì sao không được gọi `getBean()` trong condition?  
**Đáp án:** Bean có thể bị khởi tạo quá sớm, trước lifecycle và post-processing thông thường; condition phải tuân theo giới hạn của BeanFactoryPostProcessor và không tương tác với bean instance.

**Câu 3.** `ConditionContext` cung cấp những input nào thường hữu ích?  
**Đáp án:** `Environment`, `BeanDefinitionRegistry`, `BeanFactory` nếu có, `ResourceLoader` và `ClassLoader`.

**Câu 4.** `AnnotatedTypeMetadata.getAnnotationAttributes()` dùng để làm gì?  
**Đáp án:** Đọc các thuộc tính của annotation trên class hoặc method đang được xét, bao gồm annotation tổng hợp/meta-annotation.

**Câu 5.** Cùng annotation nhưng property `acme.region` đổi từ `internal` sang `public` thì kết quả ví dụ là gì?  
**Đáp án:** `internal` khớp; `public` không khớp vì condition so sánh chính xác với giá trị annotation.

**Câu 6.** Vì sao nên test property missing?  
**Đáp án:** Vì missing là một input thực tế và cần có semantics rõ ràng. Ví dụ này fail closed: thiếu property thì không đăng ký feature.

**Câu 7.** Khi nào cần `ConfigurationCondition`?  
**Đáp án:** Khi cần chọn phase phân tích cấu hình (`PARSE_CONFIGURATION`) hoặc đăng ký bean (`REGISTER_BEAN`), thường do condition phụ thuộc vào bean-definition metadata.

**Câu 8.** Khi nào nên dùng `SpringBootCondition`?  
**Đáp án:** Khi condition dành cho Spring Boot cần trả `ConditionOutcome` và diagnostic logging nhất quán. Logic đánh giá vẫn phải deterministic và không có tác dụng phụ.

**Câu 9.** Nếu condition chỉ kiểm tra `acme.feature.enabled=true`, có nên tự viết class `Condition` không?  
**Đáp án:** Thường không. Dùng `@ConditionalOnProperty` là đủ và ít mã phải bảo trì hơn.

## 14. Ghi nhớ và tài liệu tham khảo

- `Condition` là SPI quyết định component có đủ điều kiện đăng ký hay không; `matches()` nhận `ConditionContext` và `AnnotatedTypeMetadata`.
- Condition chạy trước khi bean definition được đăng ký, vì vậy không tương tác với bean instances và không gọi `getBean()`.
- Dữ liệu tốt đến từ annotation metadata, Environment, classpath hoặc resource đã xác định.
- Cùng input phải cho cùng kết quả; tránh thời gian hiện tại, random, I/O, network, database và mutable static state.
- Custom composed annotation dùng `@Conditional(YourCondition.class)` để gắn condition vào class/method.
- Dùng `ConfigurationCondition` khi cần chọn phase; dùng `SpringBootCondition` khi cần `ConditionOutcome` và diagnostic logging.
- `ApplicationContextRunner` giúp kiểm thử từng input trong context độc lập; assertion về bean là bằng chứng hành vi cuối cùng.

Tài liệu chính thức:

1. Spring Framework 6.1 — [Condition Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html): thời điểm đánh giá và giới hạn không tương tác với bean instances.
2. Spring Framework 6.1 — [Conditional Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Conditional.html): phạm vi sử dụng trên class, method và meta-annotation.
3. Spring Framework 6.1 — [ConditionContext Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html): Environment, BeanFactory, registry, resource loader và class loader.
4. Spring Framework 6.1 — [AnnotatedTypeMetadata Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotatedTypeMetadata.html): đọc annotation attributes và meta-annotations.
5. Spring Framework 6.1 — [ConfigurationCondition Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html): `PARSE_CONFIGURATION` và `REGISTER_BEAN`.
6. Spring Boot 3.3.13 — [SpringBootCondition Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html): `ConditionOutcome` và diagnostic logging.
7. Spring Boot 3.3 — [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): custom auto-configuration, condition annotations, ApplicationContextRunner và condition report.
8. Spring Boot 3.3.13 — [ConditionEvaluationReport Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html).
